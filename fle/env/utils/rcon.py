import os
import re
from glob import glob
from itertools import chain
from pathlib import Path
from typing import List, Optional
from typing_extensions import deprecated

from timeit import default_timer as timer

# Suppress SyntaxWarning from slpp on Python 3.12+
import warnings

warnings.filterwarnings("ignore", category=SyntaxWarning, module="slpp")
from slpp import slpp as lua

import io
import contextlib


def _load_script(filename):
    with open(filename, "r", encoding="utf-8") as file:
        script_string = file.read()
        pruned = Path(filename).name[:-4]
        return pruned, script_string


def _load_scripts(scripts):
    script_dict = {}
    for filename in scripts:
        pruned, script_string = _load_script(filename)
        script_dict[pruned] = script_string
    return script_dict


def _get_mods_dir():
    override = os.environ.get("FLE_MODS_DIR")
    if override:
        return override
    path = os.path.dirname(Path(os.path.dirname(os.path.realpath(__file__))))
    return path + "/mods"


def _get_dir(name="tools"):
    override = os.environ.get(f"FLE_{name.upper()}_DIR")
    if override:
        return override
    path = os.path.dirname(Path(os.path.dirname(os.path.realpath(__file__))))
    return path + f"/{name}"


_SKIPPED_TOOL_DIRS: set[str] = set()


def _report_skipped_tool_dirs(dirpath: str, server_file: str, client_file: str) -> None:
    """LOCAL PATCH (FLE defect #50): make skipped tool directories visible.

    A directory only counts as a tool when it has **both** `server.lua` and
    `client.py`. `lua_manager.setup_tools` and `_get_tool_names` (below) both
    filter on that, and used to do it **silently** -- so a tool that is on disk
    (e.g. `inspect_entities`, `get_messages`) looked available while it was never
    registered (the "probe vs reality" family, cf. F6b / docs/06 #50). Warn once
    per directory per process so repeated re-init does not flood the log.
    """
    has_server = os.path.isfile(server_file)
    has_client = os.path.isfile(client_file)
    if not has_server and not has_client:
        return  # not a tool directory at all -- stay quiet
    if dirpath in _SKIPPED_TOOL_DIRS:
        return
    _SKIPPED_TOOL_DIRS.add(dirpath)
    print(
        "WARNING: skipping tool directory "
        f"'{dirpath}': it has {'server.lua' if has_server else 'client.py'} "
        f"but no {'client.py' if has_server else 'server.lua'} "
        "-- the tool is NOT registered and its Lua is NOT pushed"
    )


def _get_tool_names(name="tools") -> List[str]:
    tool_dir = _get_dir(name)
    lua_files = []

    # Walk through all directories
    for dirpath, _, filenames in os.walk(tool_dir):
        # Skip processing files if this is a valid tool directory
        if dirpath == tool_dir:
            continue

        # First check if this is a valid tool directory
        server_file = os.path.join(dirpath, "server.lua")
        client_file = os.path.join(dirpath, "client.py")

        if os.path.isfile(server_file) and os.path.isfile(client_file):
            # If valid, collect all .lua files in this directory
            for filename in filenames:
                if filename.endswith(".lua"):
                    # Get the relative path from tool_dir
                    full_path = os.path.join(dirpath, filename)
                    lua_files.append(full_path)
        else:
            # LOCAL PATCH (FLE defect #50): was a silent skip.
            _report_skipped_tool_dirs(dirpath, server_file, client_file)

    return lua_files


def _get_lib_names():
    init_dir = _get_mods_dir()
    return list(
        chain.from_iterable(
            glob(os.path.join(x[0], "*.lua")) for x in os.walk(init_dir)
        )
    )


def _load_mods(filename):
    inits = _get_lib_names()
    try:
        init = [init for init in inits if init.endswith(filename + ".lua")][0]
        name, script = _load_script(init)
        return script
    except IndexError:
        raise ValueError(f"No init found with the name {filename}")


def _load_initialisation_scripts():
    return _load_scripts(_get_lib_names())


def _remove_numerical_keys(dictionary):
    pruned = {}
    if not isinstance(dictionary, dict):
        return dictionary
    parts = []
    for key, value in dictionary.items():
        if isinstance(key, int):
            if isinstance(value, dict):
                parts.append(_remove_numerical_keys(value))
            elif isinstance(value, str):
                parts.append(value.replace("!!", '"').strip())
            else:
                parts.append(value)
        else:
            pruned[key] = value

    if parts:
        pruned = parts
    return pruned


class LuaConversionError(Exception):
    """Custom exception for Lua conversion errors"""

    pass


class LuaParseResult(tuple):
    """The `(value, elapsed)` pair returned by `_lua2python`, plus a `.error` reason.

    LOCAL PATCH (FLE defect #51): a *parse failure* and an *empty response* both used
    to come back as a bare `(None, elapsed)`, so callers could not tell "there was no
    data" from "the Lua parser blew up" and had to guess (e.g. `get_warnings` simply
    returned "no alerts" when parsing failed). The tuple shape is deliberately kept --
    unpacking and `is None` checks are unchanged -- and `.error` now carries the reason
    for the parse-failure case (``None`` for an empty response).
    """

    error: Optional[str] = None
    empty: bool = True

    @classmethod
    def ok(cls, value, elapsed):
        result = cls((value, elapsed))
        result.empty = False
        return result

    @classmethod
    def failed(cls, reason, elapsed):
        result = cls((None, elapsed))
        result.error = reason
        result.empty = False
        return result


def _check_output_for_errors(command, response, output):
    """Check captured stdout for known Lua parsing errors"""
    ERRORS = {
        "unexp_end_string": "Unexpected end of string while parsing Lua string.",
        "unexp_end_table": "Unexpected end of table while parsing Lua string.",
        "mfnumber_minus": "Malformed number (no digits after initial minus).",
        "mfnumber_dec_point": "Malformed number (no digits after decimal point).",
        "mfnumber_sci": "Malformed number (bad scientific format).",
    }

    for error_key, error_msg in ERRORS.items():
        if error_msg in output:
            raise LuaConversionError(
                f"Lua parsing error: {error_msg} for command:\n'{command}' with response:\n'{response}'"
            )


def _lua2python(command, response, *parameters, trace=False, start=0, raise_on_error=False):
    """Decode a Lua response into Python.

    Returns a `LuaParseResult` -- a `(value, elapsed)` tuple (unpack/write-back
    compatible) that also carries `.error` / `.empty`, see `LuaParseResult`.

    LOCAL PATCH (FLE defect #51):
      * a parse failure is no longer indistinguishable from an empty response --
        `.error` carries the reason and `.empty` is False;
      * pass `raise_on_error=True` to get a `LuaConversionError` instead of a
        `None` value (for callers that must not silently continue).
    Default behaviour (return `(None, elapsed)`, no exception) is unchanged, because
    `controller.execute()` deliberately relies on `parsed is None` to fall back to
    scraping the raw RCON dump for the error string.
    """
    stdout = io.StringIO()

    with contextlib.redirect_stdout(stdout):
        if not response:
            return LuaParseResult((None, (timer() - start)))

        try:
            # Handle the case where response is a complete table
            if response.strip().startswith("{") and response.strip().endswith("}"):
                output = lua.decode(response)
            else:
                # Handle the case where we need to extract the last line
                splitted = response.split("\n")[-1]
                if "[string" in splitted:
                    splitted = re.sub(r"\[string[^\]]*\]", "", splitted)
                output = lua.decode(splitted)

            if isinstance(output, dict) and "b" in output:
                output["b"] = _remove_numerical_keys(output["b"])

            return LuaParseResult.ok(output, (timer() - start))

        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
            if raise_on_error:
                excerpt = response if len(response) <= 300 else response[:300] + "…"
                raise LuaConversionError(
                    f"Could not parse Lua response for command '{command}': {reason}\n"
                    f"response: {excerpt}"
                ) from e
            if trace:
                print(f"Parsing error: {reason}")
            return LuaParseResult.failed(reason, (timer() - start))


@deprecated("Doesn't handle nested structures that well")
def _lua2python_old(command, response, *parameters, trace=False, start=0):
    # Capture stdout using StringIO
    stdout = io.StringIO()

    with contextlib.redirect_stdout(stdout):
        if trace:
            print(command, parameters, response)

        if response:
            if trace:
                print(f"success: {command}")
            end = timer()

            if response[0] != "{":
                splitted = response.split("\n")[-1]

                if "[string" in splitted:
                    a, b = splitted.split("[string")
                    splitted = a + '["' + b.replace('"', "!!")
                    splitted = re.sub(r",\s*}\s*$", "", splitted) + '"]}'

                try:
                    output = lua.decode(splitted)
                except Exception:
                    # Capture any decode errors
                    output = None
            else:
                try:
                    output = lua.decode(response)
                except Exception:
                    # Capture any decode errors
                    output = None

            if trace:
                print(
                    "{hbar}\nCOMMAND: {command}\nPARAMETERS: {parameters}\n\n{response}\n\nOUTPUT:{output}".format(
                        hbar="-" * 100,
                        command=command,
                        parameters=parameters,
                        response=response,
                        output=output,
                    )
                )

            # Check captured stdout for errors
            captured_output = stdout.getvalue()
            _check_output_for_errors(command, response, captured_output)

            # remove numerical keys
            if isinstance(output, dict) and "b" in output:
                pruned = _remove_numerical_keys(output["b"])
                output["b"] = pruned

            return output, (end - start)
        else:
            if trace:
                print(f"failure: {command} \t")
            end = timer()

            try:
                return lua.decode(response), (end - start)
            except Exception:
                # Check captured stdout for errors before returning None
                captured_output = stdout.getvalue()
                _check_output_for_errors(command, response, captured_output)
                return None, (end - start)
