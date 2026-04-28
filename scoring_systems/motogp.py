"""MotoGP scoring (current).

The current MotoGP scale rewards both winning and finishing. Even 10th place
earns 6 pts (24% of 1st), so a bad race doesn't catastrophically tank a
championship. Same scale used by World Superbike and Formula E (with bonuses).

Scale: 25-20-16-13-11-10-9-8-7-6. Top 10 score; rest get 0.
1st/2nd ratio: 1.25x. Flat tail (positions 5-10 are spaced by just 1 pt).
"""
from ._base import ScoringSystem

SYSTEM = ScoringSystem(
    name="MotoGP",
    scale=[25, 20, 16, 13, 11, 10, 9, 8, 7, 6],
    description="MotoGP (current). All 10 positions score well. 1.25x for winning.",
)
