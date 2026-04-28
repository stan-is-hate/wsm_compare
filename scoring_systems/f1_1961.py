"""Formula 1 scoring (1961-1990).

The classic three-decade-long system through the Senna/Prost era. 9 points
for a win, 1.5x premium over 2nd. Top 6 score; the rest of the field earned
nothing.

Scale: 9-6-4-3-2-1. Top 6 score; rest get 0.
1st/2nd ratio: 1.50x.
"""
from ._base import ScoringSystem

SYSTEM = ScoringSystem(
    name="F1 1961-1990",
    scale=[9, 6, 4, 3, 2, 1],
    description="Formula 1 (1961-1990). Top 6 only. Senna/Prost era. 1.5x for winning.",
)
