"""Formula 1 scoring (1991-2002).

Schumacher/Häkkinen era. Bumped the win value from 9 to 10, otherwise unchanged
from the 1961-1990 system. Top 6 only — 7th place onward earned nothing.

Scale: 10-6-4-3-2-1. Top 6 score; rest get 0.
1st/2nd ratio: 1.67x — biggest win premium of any real F1 system.
"""
from ._base import ScoringSystem

SYSTEM = ScoringSystem(
    name="F1 1991-2002",
    scale=[10, 6, 4, 3, 2, 1],
    description="Formula 1 (1991-2002). Top 6 only. Schumacher era. 1.67x for winning.",
)
