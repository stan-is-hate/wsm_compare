"""MotoGP-Extended scoring (variant, not a real-world system).

Custom variant: keeps MotoGP's top half (25-20-16-13-11) but extends the tail
all the way down to 1 for last in a 10-athlete field. The result is a smooth
2-pt-gap curve from 5th place down to 10th, instead of MotoGP's flat
6-7-8-9-10 tail.

The idea: keep MotoGP's "winning matters meaningfully" property (5-pt gap from
1st to 2nd) without making last place worth almost as much as mid-pack. Useful
for fields where you want the bottom of the order to actually matter.

Scale: 25-20-16-13-11-9-7-5-3-1. Top 10 score; rest get 0 (in larger fields).
1st/2nd ratio: 1.25x (same as standard MotoGP).
"""
from ._base import ScoringSystem

SYSTEM = ScoringSystem(
    name="MotoGP Extended",
    scale=[25, 20, 16, 13, 11, 9, 7, 5, 3, 1],
    description="MotoGP-style top, but tail extends to 1 for last (steeper bottom half).",
)
