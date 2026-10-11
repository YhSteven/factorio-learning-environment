import builtins
import inspect
import marshal
import types


class SerializableFunction:
    """Wrapper to make function objects serializable and callable with signature information"""

    def __init__(self, func, instance=None):
        """Initialize with a function"""
        self.code_bytes = marshal.dumps(func.__code__)
        self.name = func.__name__
        self.defaults = func.__defaults__
        # LOCAL PATCH (FLE defect #45): keep the *real* closure. It used to be hardcoded
        # to `None`, so reconstructing any function that references a free variable --
        # a returned inner function (`closure_returned`) or a function wrapped by a
        # decorator (`decorator`) -- raised
        # `TypeError: arg 5 (closure) must be tuple`, i.e. the whole step failed.
        # Keeping the original cells (not copies) preserves `nonlocal` sharing across
        # calls. ⚠️ Cells are neither marshallable nor picklable, so such a function is
        # filtered out of the pickled game state by `is_serializable` (it raises
        # TypeError, which that guard swallows); it stays fully usable in-process,
        # which is where agent code actually runs.
        self.closure = func.__closure__
        self.docstring = func.__doc__

        # Store signature information including annotations
        try:
            sig = inspect.signature(func)
            # Get annotations directly from the function
            annotations = getattr(func, "__annotations__", {})

            # Store parameters with their annotations
            self.parameters = []
            for name, param in sig.parameters.items():
                annotation = None
                # Check if this is a custom FLE function with structured annotations
                if "args" in annotations and isinstance(annotations["args"], dict):
                    annotation = annotations["args"].get(name, None)
                else:
                    # Standard Python function annotations
                    annotation = annotations.get(name, None)

                annotation_str = None
                if annotation:
                    annotation_str = getattr(annotation, "__name__", str(annotation))
                self.parameters.append((name, str(param), annotation_str))

            # Store return annotation
            self.return_annotation = None
            if "args" in annotations and isinstance(annotations["args"], dict):
                # Custom FLE function annotation structure
                self.return_annotation = annotations["args"].get("return", None)
            else:
                # Standard Python function annotation
                self.return_annotation = annotations.get("return", None)

            if self.return_annotation:
                self.return_annotation = getattr(
                    self.return_annotation, "__name__", str(self.return_annotation)
                )

        except (ValueError, TypeError):
            self.parameters = []
            self.return_annotation = None

        # These won't be pickled
        self._instance = instance
        self._cached_func = None
        # LOCAL PATCH (FLE defect #46): the *live* globals dict of the namespace
        # currently evaluating (set by `bind`). When present, `reconstruct` uses it
        # directly instead of building a throw-away copy, so `global x; x = ...`
        # inside the function writes back to the caller's namespace.
        self._globals_dict = None

    def __getstate__(self):
        """Control which attributes are pickled"""
        return {
            "code_bytes": self.code_bytes,
            "name": self.name,
            "defaults": self.defaults,
            "closure": self.closure,
            "docstring": self.docstring,
            "parameters": self.parameters,
            "return_annotation": self.return_annotation,
        }

    def __setstate__(self, state):
        """Restore state after unpickling"""
        self.code_bytes = state["code_bytes"]
        self.name = state["name"]
        self.defaults = state["defaults"]
        self.closure = state["closure"]
        if "docstring" in state:
            self.docstring = state["docstring"]
        if "parameters" in state:
            self.parameters = state["parameters"]
        if "return_annotation" in state:
            self.return_annotation = state["return_annotation"]
        self._instance = None
        self._cached_func = None

    def __str__(self):
        """Return a string representation with function signature and docstring"""
        # Build parameter list preserving type annotations
        param_strs = []
        for name, param_str, annotation in self.parameters:
            if annotation:
                # Handle default values
                if "=" in param_str:
                    param_name, default = param_str.split("=", 1)
                    param_strs.append(f"{name}: {annotation}={default.strip()}")
                else:
                    param_strs.append(f"{name}: {annotation}")
            else:
                # No type annotation, use original parameter string
                param_strs.append(param_str)

        # Combine into function signature
        signature = f"({', '.join(param_strs)})"
        result = f"def {self.name}{signature}"

        # Add return annotation if it exists
        if self.return_annotation:
            result += f" -> {self.return_annotation}"

        # Add docstring if it exists
        if self.docstring:
            result += f'\n"""{self.docstring}"""'

        return result

    def bind(self, instance, globals_dict=None):
        """Bind this function to an instance after unpickling

        LOCAL PATCH (FLE defect #46): `globals_dict` may be the live eval namespace
        of the current step. `reconstruct` then uses it as the function's `__globals__`
        so module-level rebinding inside the function (e.g. `global x; x = x + 1`)
        is visible to the rest of the step instead of being written to a copy that
        is thrown away. Defaults to None ⇒ legacy behaviour (build a fresh dict).
        """
        self._instance = instance
        self._globals_dict = globals_dict
        self._cached_func = None
        return self

    def __call__(self, *args, **kwargs):
        """Make the serialized function directly callable"""
        # Always reconstruct to get fresh globals - this ensures global statements work correctly
        if self._instance is None:
            raise RuntimeError("Function must be bound to an instance before calling")
        self._cached_func = self.reconstruct(self._instance, self)
        return self._cached_func(*args, **kwargs)

    @staticmethod
    def reconstruct(instance, func_data):
        """Reconstruct a function with proper globals from the instance"""
        # LOCAL PATCH (FLE defect #46): if the namespace handed us its live eval
        # namespace (see `bind`), use it as `__globals__` verbatim -- writes to
        # module-level names then land in the namespace that is actually being
        # evaluated, so `global x; x = ...` behaves like CPython.
        live_globals = getattr(func_data, "_globals_dict", None)
        if live_globals is not None:
            globals_dict = live_globals
            globals_dict.setdefault("__builtins__", builtins)
        else:
            globals_dict = {}

            # Add builtins first (so instance attributes can override them)
            for name in dir(builtins):
                if not name.startswith("_"):
                    globals_dict[name] = getattr(builtins, name)

            # Add instance attributes (includes tools, log, etc.)
            for name in dir(instance):
                if not name.startswith("_"):
                    globals_dict[name] = getattr(instance, name)

            # Add persistent variables to ensure global statements work correctly
            if hasattr(instance, "persistent_vars"):
                globals_dict.update(instance.persistent_vars)

        # Route print() inside agent-defined functions to the namespace log,
        # so output is captured and returned to the agent as STDOUT.
        if hasattr(instance, "log"):
            globals_dict["print"] = instance.log

        code = marshal.loads(func_data.code_bytes)

        new_func = types.FunctionType(
            code, globals_dict, func_data.name, func_data.defaults, func_data.closure
        )
        return new_func
