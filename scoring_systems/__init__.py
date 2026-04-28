"""Scoring systems package.

Each system lives in its own module and exports a `SYSTEM` constant.
To use, import from the explicit submodules:

    from scoring_systems._base import ScoringSystem
    from scoring_systems._registry import ALL_SYSTEMS, by_name

To add a new system, see scoring_systems/_registry.py.
"""
