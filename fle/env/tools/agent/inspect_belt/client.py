from typing import Dict, List

from fle.env.entities import Position
from fle.env.tools import Tool


class InspectBelt(Tool):
    """Structural read-out of the items sitting on transport belts.

    LOCAL PATCH (2026-10-15) -- see docs/02 §7.83 / docs/06 #73.

    The rendered map cannot express belt lanes: the full render packs a whole
    belt tile into 16 px, so its two lanes end up ~1.75 px apart, and a lane
    carrying two item types cannot be told apart from a single-item one.  The
    underlying data has always been available (``get_transport_line``); this
    tool just exposes it.
    """

    def __init__(self, *args):
        super().__init__(*args)

    def __call__(self, position: Position, radius: float = 1) -> List[Dict]:
        """
        Read the contents of the two lanes of every belt around a position.

        :param position: Centre of the search (a Position object)
        :param radius: Search radius in tiles; clamped to 0..8
        :return: one dict per belt, sorted by (y, x):
                 {belt_type, x, y, direction, left: {item: count}, right: {...},
                  mixed: bool}
                 ``belt_type`` is hyphen-free on purpose (FLE's response transport
                 splits hyphenated top-level string values).

        ``left`` / ``right`` are the belt's own lanes as seen by the traveller
        (e.g. the north half of an east-facing belt).  ``mixed`` is True when a
        single lane carries more than one item type -- the case the images
        silently hide.
        """
        if not isinstance(position, Position):
            raise ValueError("The first argument must be a Position object")

        r = 1 if radius is None else max(0.0, min(float(radius), 8.0))

        response, elapsed = self.execute(
            self.player_index, position.x, position.y, r
        )

        if not isinstance(response, dict):
            raise Exception("Could not inspect belts at the given position.", response)

        belts = response.get("belts", [])
        return belts if isinstance(belts, list) else list(belts.values())
