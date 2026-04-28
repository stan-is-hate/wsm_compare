"""ScoringSystem dataclass — shared base for all scoring system modules."""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ScoringSystem:
    name: str
    scale: Optional[list]  # None = "WSM Linear" (N down to 1, generated dynamically)
    description: str

    def get_scale(self, field_size: int) -> list:
        """Return the scoring scale sized for the field.

        - If `scale` is None (WSM Linear), generates [N, N-1, ..., 1] for the field.
        - If `scale` is shorter than the field, pads with zeros (positions beyond
          the scale score 0).
        - If `scale` is longer than the field, slices to the field size.
        """
        if self.scale is None:
            return list(range(field_size, 0, -1))
        return list(self.scale[:field_size]) + [0] * max(0, field_size - len(self.scale))
