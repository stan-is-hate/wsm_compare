"""MotoGP-Extended scoring (variant, not a real-world system).

Extends the standard MotoGP scale (25-20-16-13-11-10-9-8-7-6) past 10th place
all the way down to 1 for 15th, supporting larger fields like SMOE (16
athletes) where standard MotoGP would zero-pad positions 11+.

Top 10 are identical to standard MotoGP. Positions 11-15 add a 5-4-3-2-1
tail. Position 16+ score 0 (same as MotoGP for those positions).

Scale: 25-20-16-13-11-10-9-8-7-6-5-4-3-2-1.
1st/2nd ratio: 1.25x (same as standard MotoGP).
"""
from ._base import ScoringSystem

SYSTEM = ScoringSystem(
    name="MotoGP Extended",
    scale=[25, 20, 16, 13, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1],
    description="MotoGP scale extended to 15 positions (5-4-3-2-1 tail) for larger fields.",
)
