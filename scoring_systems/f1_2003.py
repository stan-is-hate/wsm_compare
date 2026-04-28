"""Formula 1 scoring (2003-2009).

Replaced the long-standing 10-6-4-3-2-1 system after Schumacher/Ferrari
dominance was deciding championships before season-end. Reduced the 1st/2nd
ratio from 1.67x to 1.25x and extended scoring to 8th place to keep
championships alive longer.

Scale: 10-8-6-5-4-3-2-1. Top 8 score; rest get 0.
1st/2nd ratio: 1.25x.
"""
from ._base import ScoringSystem

SYSTEM = ScoringSystem(
    name="F1 2003-2009",
    scale=[10, 8, 6, 5, 4, 3, 2, 1],
    description="Formula 1 (2003-2009). Top 8 only. Lower 1st/2nd ratio (1.25x).",
)
