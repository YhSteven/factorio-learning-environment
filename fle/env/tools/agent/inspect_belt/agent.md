# inspect_belt

The `inspect_belt` tool reads what is actually sitting on the belts around a point,
**lane by lane**. Every Factorio belt carries two independent lanes, and when a single
lane holds more than one item type the rendered map cannot show it (the full render
packs a whole belt tile into 16 px, so the two lanes are only ~1.75 px apart). This
tool is the structured way to see that.

## Basic Usage

```python
inspect_belt(position: Position, radius: float = 1) -> List[Dict]
```

### Parameters

- `position`: centre of the search -- a `Position` object (a belt's `.position` or a
  coordinate you choose). Not an `Entity`: pass `entity.position`.
- `radius`: search radius in tiles, clamped to `0..8` (default `1`). Radius `0` reads
  the single tile at `position`.

### Return Value

A list with one dict per belt found, **sorted by (y, x)**:

```python
{
  "belt_type": "transport_belt",   # transport_belt / fast_transport_belt / splitter / ...
  "x": -7.5,                       # belt centre
  "y": 164.5,
  "direction": 12,                 # 16-way direction (0=N, 4=E, 8=S, 12=W)
  "left":  {"speed-module": 4},                       # LEFT lane as seen by the traveller
  "right": {"productivity-module": 1, "processing-unit": 3},
  "mixed": True,                   # True when one lane holds 2+ item types
}
```

- `left` / `right` are the belt's **own** lanes relative to its direction of travel --
  e.g. for an east-facing belt, `left` is the north half and `right` the south half.
  (`left` <- `get_transport_line(1)`, `right` <- `get_transport_line(2)`; verified
  2026-10-16 by a burner inserter whose `drop_position` lands on the far lane.)
- Counts are per lane and per item type. An empty belt still appears in the list, with
  empty `left` / `right` tables (`{}`) and `mixed: False`.
- Sides of the belt that carry nothing read as `{}`, not as an error.

**`belt_type` note**: the value is hyphen-free (`fast_transport_belt`, not
`fast-transport-belt`) on purpose -- FLE's response transport splits hyphenated
top-level string values, so the underscored form is the one that survives intact.
The `left` / `right` dict **keys** keep their hyphens (`copper-plate`), which is fine.

## Common Usage Patterns

1. **Is a lane carrying mixed items?** (what the pictures hide)

```python
for belt in inspect_belt(Position(x=4.5, y=152.5), radius=1):
    if belt["mixed"]:
        print(belt["x"], belt["y"],
              "L:", belt["left"], "R:", belt["right"])
```

2. **Which side feeds a target machine?** read the lane next to its input:

```python
from fle.env.entities import Prototype
iron = place_entity(Prototype.StoneFurnace, Direction.DOWN, Position(x=10.5, y=10.5))
feed = inspect_belt(Position(x=iron.position.x, y=iron.position.y - 1.5))
side = "left" if feed and feed[0]["left"] else "right"
```

3. **Poll a small area** to find where a belt jam starts:

```python
for belt in inspect_belt(player_location, radius=3):
    total = sum(belt["left"].values()) + sum(belt["right"].values())
    if total == 0:
        print("empty belt at", belt["x"], belt["y"])   # starvation upstream
```

## Notes

- **Read-only**: `inspect_belt` never modifies the world and costs no game time.
- It reports **items currently on the belt**, not machine buffers -- use
  `inspect_inventory(entity)` for chests / furnaces / assemblers.
- `radius` is capped at `8` to keep the response small in dense factories; run it
  around your actual work area rather than the whole base.
- Underground belts and splitters are included; an underground belt only exposes the
  lane contents of the two ends it owns, same rule as a normal belt.
