"""Formula 1 scoring (2010-present).

Introduced for the 2010 season after Jenson Button clinched the 2009
championship by accumulating consistent finishes once Brawn lost early-season
dominance. The new scale steepened the top end — winning a race became
significantly more valuable than safe podiums.

Scale: 25-18-15-12-10-8-6-4-2-1. Top 10 score; rest get 0.
1st/2nd ratio: 1.39x. Steep drops from 1st (25) to 2nd (18) to 3rd (15).
"""
from ._base import ScoringSystem

SYSTEM = ScoringSystem(
    name="F1 2010-present",
    scale=[25, 18, 15, 12, 10, 8, 6, 4, 2, 1],
    description="Formula 1 (2010+). Steep top, drops off after 10th.",
)
