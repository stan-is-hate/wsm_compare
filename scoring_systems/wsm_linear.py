"""World's Strongest Man scoring (current).

Linear: N points for 1st place down to 1 point for last, where N = field size.
Equal 1-pt gaps between every position. Used by WSM, Arnold Strongman Classic,
Rogue Invitational, SMOE, and most other modern strongman competitions.

1st/2nd ratio: 1.11x in a 10-athlete field (10/9). Rewards consistency
heavily — winning an event is worth only 1 more point than placing 2nd.
"""
from ._base import ScoringSystem

SYSTEM = ScoringSystem(
    name="WSM Linear",
    scale=None,  # Generated dynamically as [N, N-1, ..., 1] for the field size
    description="World's Strongest Man (current). N pts for 1st down to 1 for last. Equal gaps.",
)
