"""Registry: imports each scoring system module and exposes ALL_SYSTEMS.

To add a new scoring system:
  1. Create scoring_systems/<name>.py with a `SYSTEM = ScoringSystem(...)` constant
  2. Add an import + entry to ALL_SYSTEMS below

Order in ALL_SYSTEMS determines display order in stdout/report tables.
"""
from .wsm_linear import SYSTEM as WSM_LINEAR
from .f1_2010 import SYSTEM as F1_2010
from .f1_2003 import SYSTEM as F1_2003
from .f1_1991 import SYSTEM as F1_1991
from .f1_1961 import SYSTEM as F1_1961
from .motogp import SYSTEM as MOTOGP
from .motogp_extended import SYSTEM as MOTOGP_EXTENDED


ALL_SYSTEMS = [
    WSM_LINEAR,
    F1_2010,
    F1_2003,
    F1_1991,
    F1_1961,
    MOTOGP,
    MOTOGP_EXTENDED,
]


def by_name(name):
    """Look up a scoring system by name. Raises ValueError if not found."""
    for s in ALL_SYSTEMS:
        if s.name == name:
            return s
    raise ValueError(f"Unknown scoring system: {name!r} (available: {[s.name for s in ALL_SYSTEMS]})")
