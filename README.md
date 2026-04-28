# WSM Compare

What if strongman comps used different scoring systems? This tool re-scores 15 real competitions (Arnold, Rogue, SMOE, WSM — both men's and women's) under 7 real-world scoring systems (current strongman, multiple eras of F1, MotoGP, plus a custom MotoGP variant) and shows how the winners change.

All data sourced from [Strongman Archives](https://strongmanarchives.com/). Math verified against official totals.

## TL;DR

**Mitchell Hooper dominates regardless of scoring system.** Across 9 men's comps over 3 years, here's how many he wins under each:

| Scoring system | Hooper wins | Other winners |
|---|---|---|
| WSM Linear (current) | **7 / 9** | E. Singleton, R. Nel |
| F1 2003-2009 | **7 / 9** | L. Hatton, T. Stoltman |
| MotoGP | **7 / 9** | L. Hatton, T. Stoltman |
| MotoGP Extended | **7 / 9** | L. Hatton, T. Stoltman |
| F1 2010-present | **6 / 9** | L. Hatton, T. Stoltman, R. Nel |
| F1 1961-1990 | **5 / 9** | H. Björnsson, L. Hatton, T. Stoltman, R. Nel |
| F1 1991-2002 | **4 / 9** | L. Hatton (2), H. Björnsson, T. Stoltman, R. Nel |

The "Hooper got lucky with the scoring system" theory doesn't really hold up. He'd win the majority of his comps under any reasonable scoring philosophy. Only the steepest, top-6-only old F1 systems significantly reshuffle the deck — and even those crown Hooper in 4-5 of 9.

## Comps where the scoring system actually changes the winner

5 of 9 men's comps have at least one scoring system that flips the winner:

| Comp | Real winner (WSM Linear) | Alternate winner (under some systems) |
|---|---|---|
| **WSM 2026 finals** | M. Hooper (54) | R. Nel — wins under F1 2010+, F1 1991-02, F1 1961-90 |
| **WSM 2025 finals** | R. Nel (47) | T. Stoltman — wins under every other system tested |
| **SMOE 2024** | M. Hooper (117) | H. Björnsson — wins under F1 1991-02 and F1 1961-90 only |
| **SMOE 2025** | E. Singleton (93.5) | L. Hatton — wins under every other system tested |
| **Arnold 2025** | M. Hooper (51.5) | L. Hatton — wins under F1 1991-2002 only |

The rest (Arnold 2024, Arnold 2026, Rogue 2024, Rogue 2025) are uncontroversial — same winner under all 7 systems.

**See [`reports/_summary.md`](reports/_summary.md) for the full cross-comp table and methodological notes.**

## WSM coverage (group stage + pool + finals)

The WSM analysis is its own thing — the group stage gets multiple analyses (groups-as-teams, pooled stack rank, top-10 control matching the official prelim carryover) on top of the finals breakdown.

- **[WSM 2026](reports/wsm2026.md)** — full coverage: group stage + pool + finals. The 2-pt Hooper/Nel result.
- **[WSM 2025](reports/wsm2025.md)** — finals only. Nel beat Stoltman by 0.5 pts under WSM Linear; Stoltman wins under everything else.

## Browse individual comp reports

Each report shows full standings under all 7 scoring systems plus podium-by-system and winner-flip analysis.

### Men's
- **Arnold Strongman Classic:** [2026](reports/arnold2026.md) · [2025](reports/arnold2025.md) · [2024](reports/arnold2024.md)
- **Rogue Invitational:** [2025](reports/rogue2025.md) · [2024](reports/rogue2024.md)
- **Strongest Man on Earth:** [2025](reports/smoe2025.md) · [2024](reports/smoe2024.md)

### Women's
- **Arnold Strongman Classic:** [2026](reports/arnold2026_w.md) · [2025](reports/arnold2025_w.md) · [2024](reports/arnold2024_w.md)
- **Rogue Invitational:** [2025](reports/rogue2025_w.md) · [2024](reports/rogue2024_w.md)

## Scoring systems tested

| System | Scale (top 10) | 1st/2nd ratio | Origin |
|---|---|---|---|
| WSM Linear | 10-9-8-7-6-5-4-3-2-1 | 1.11x | World's Strongest Man, current. Equal gaps. |
| F1 2010-present | 25-18-15-12-10-8-6-4-2-1 | 1.39x | Formula 1, current. Steep top, drops off. |
| F1 2003-2009 | 10-8-6-5-4-3-2-1 | 1.25x | F1, mid-2000s. Top 8 only. |
| F1 1991-2002 | 10-6-4-3-2-1 | 1.67x | F1, Schumacher era. Top 6 only. |
| F1 1961-1990 | 9-6-4-3-2-1 | 1.50x | F1, Senna/Prost era. Top 6 only. |
| MotoGP | 25-20-16-13-11-10-9-8-7-6 | 1.25x | MotoGP, current. All 10 score well. |
| MotoGP Extended | 25-20-16-13-11-10-9-8-7-6-5-4-3-2-1 | 1.25x | Variant: MotoGP extended to 15 positions for bigger fields. |

## Running it yourself

Zero dependencies (Python stdlib only).

```bash
# Compare scoring systems on a comp
python3 wsm_compare.py compare comps/wsm2026_finals.csv         # one comp, stdout
python3 wsm_compare.py compare --all                              # all comps, stdout
python3 wsm_compare.py compare --report                           # all comps to markdown

# Group-stage modes (require a 'group' column in the CSV)
python3 wsm_compare.py groups comps/wsm2026_prelim.csv            # groups as teams
python3 wsm_compare.py pool comps/wsm2026_prelim.csv              # pooled stack rank + top-10

# Fetch canonical results from Strongman Archives
python3 fetch_canonical.py 1462 > comps/smoe2024.csv              # SMOE 2024
```

Tests: `python3 -m unittest discover tests` (60 tests, ~0.3s)

## Project layout

```
wsm_compare/
├── wsm_compare.py            # main CLI tool
├── fetch_canonical.py        # rate-limited fetcher for Strongman Archives
├── comps/                    # competition CSVs (15 files)
├── reports/                  # generated markdown reports
├── scoring_systems/          # one module per scoring system
│   ├── _base.py              # ScoringSystem dataclass
│   ├── _registry.py          # ALL_SYSTEMS list, by_name lookup
│   └── <name>.py             # one file per system (wsm_linear, f1_2010, etc.)
└── tests/                    # 60 unit + integration + CLI tests
```

### Adding a new scoring system

1. Create `scoring_systems/<name>.py`:
   ```python
   from ._base import ScoringSystem
   SYSTEM = ScoringSystem(
       name="My System",
       scale=[10, 8, 6, 4, 2, 1],   # or None for "WSM Linear" (N down to 1)
       description="One-line description, including origin/era.",
   )
   ```
2. Register it in `scoring_systems/_registry.py`.
3. Run `python3 wsm_compare.py compare --report` to regenerate reports.

### Adding a new comp

```bash
python3 fetch_canonical.py <strongmanarchives_contest_id> > comps/<name>.csv
python3 wsm_compare.py compare --report
```

## Methodological notes

- **Scale length follows the comp's full roster**, including DNS athletes. A comp with 10 athletes uses a 10-position scale, regardless of how many actually competed in any event. DNS always scores 0.
- **Tie averaging:** athletes sharing a placement string (e.g. all `T2`) split points across positions consumed. 3 athletes at T2 → positions 2, 3, 4 → each gets `(scale[1] + scale[2] + scale[3]) / 3`.
- **Scale truncation in big fields:** systems with short scales (F1 1991-2002 has 6 positions) zero-pad. In a 16-athlete comp under F1 1991-2002, positions 7-16 all score 0.
- **No-lift / withdrew rules vary across comps.** WSM 2026 treats `(No lift)` as DNS. SMOE 2024 treats no-lifts as competing-but-last. The CSVs encode whichever interpretation matches the comp's published totals.
