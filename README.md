# WSM Compare

Compare strongman competition results under different real-world scoring systems (WSM Linear, F1 across eras, MotoGP, etc.) to see how the scoring philosophy affects the winner.

## Why?

The 2026 WSM final was decided by 2 points: Mitchell Hooper beat Rayno Nel 54-52 under the current WSM scoring (10-9-8-7-6-5-4-3-2-1). But Nel won 3 events outright while Hooper won only 1. Under different scoring systems — F1, MotoGP, older WSM rules — the winner could have been different. This tool runs that what-if analysis across multiple competitions.

## What's here

- `wsm_compare.py` — single-script tool, no dependencies (stdlib only)
- `comps/` — competition results in CSV format (one file per comp)
- `reports/` — generated markdown reports (per-comp + cross-comp summary)

## Usage

Three subcommands:

### `compare` — apply scoring systems to a single field

Works on any CSV. Computes athlete totals under each scoring system; produces standings, podium, and winner-flip analysis.

```bash
python3 wsm_compare.py compare comps/wsm2026_finals.csv         # one comp, stdout
python3 wsm_compare.py compare --all                             # all comps, stdout
python3 wsm_compare.py compare --report                          # all comps to markdown + cross-summary
python3 wsm_compare.py compare --report comps/arnold2025.csv     # one comp to markdown
```

### `groups` — compare groups as teams

Requires a CSV with a `group` column. Sums each group's athletes' points to crown the strongest group under each scoring system.

```bash
python3 wsm_compare.py groups comps/wsm2026_groups.csv           # stdout
python3 wsm_compare.py groups --report comps/wsm2026_groups.csv  # markdown
```

### `pool` — pool all athletes into a single stack rank

Requires a CSV with a `group` column. Ranks all athletes in one big stack rank, with a BONUS top-10 control (qualifiers re-ranked within their subset). The top-10 control reproduces WSM's official "Prelim Score" carryover.

```bash
python3 wsm_compare.py pool comps/wsm2026_groups.csv             # stdout
python3 wsm_compare.py pool --report comps/wsm2026_groups.csv    # markdown
```

## CSV format

```csv
athlete,country,Event1,Event2,...
M. Hooper,CAN,1,T2,DNS,...
```

Placement values:
- `1`, `2`, `3` — solo placement
- `T2`, `T3` — tied (script counts athletes with the same string to determine tie size and averages points across positions consumed)
- `DNS` — did not compete / withdrew / no lift (always 0 pts)

### Group-stage CSV (`group` column)

For multi-group competitions (like the WSM group stage), add a `group` column. Placements should be **global across all athletes** (e.g., 1-25 across all 5 groups), not within-group:

```csv
group,athlete,country,Event1,Event2,...
1,R. Nel,RSA,1,18,...
1,N. Guardione,USA,T9,11,...
...
```

The `groups` and `pool` subcommands require this column.

The Top-10 subset control in `pool` mode reproduces WSM's official "Prelim Score" carryover when WSM Linear is used. Verified against WSM 2026 official totals (Hooper 37, Nel 34, Andrade 31, Williams 29, Fojtů 27, Kordiyaka 26.5, Licis 25.5, Mitchell 25.5, Ragg 20.5 — all match exactly).

## Scoring systems tested

| System | Scale (top 10) | 1st/2nd ratio | Origin |
|--------|---------------|--------------|--------|
| WSM Linear | 10-9-8-7-6-5-4-3-2-1 | 1.11x | World's Strongest Man, current. Equal gaps. |
| F1 2010-present | 25-18-15-12-10-8-6-4-2-1 | 1.39x | Formula 1, current. Steep top, drops off. |
| F1 2003-2009 | 10-8-6-5-4-3-2-1 | 1.25x | F1, mid-2000s. Top 8 only. |
| F1 1991-2002 | 10-6-4-3-2-1 | 1.67x | F1, Schumacher era. Top 6 only. |
| F1 1961-1990 | 9-6-4-3-2-1 | 1.50x | F1, Senna/Prost era. Top 6 only. |
| MotoGP | 25-20-16-13-11-10-9-8-7-6 | 1.25x | MotoGP, current. All 10 score well. |

## Adding a comp

1. Drop a new CSV in `comps/` with placements (extracted from event-by-event results)
2. Run `python3 wsm_compare.py --report` to regenerate reports

## Tie handling

When multiple athletes share a placement (e.g., all marked `T2`), they share the points averaged across the positions they consume. Example: 3 athletes tied at T2 → they occupy positions 2, 3, 4 → each gets `(scale[1] + scale[2] + scale[3]) / 3`.

## Field size

Scale length is set by the total number of athletes in the comp, not the number who competed in a specific event. DNS athletes still occupy implicit positions at the bottom of the field but always score 0.

## Findings (across the 5 comps included)

- **Hooper wins under most systems in most comps** — he's so consistent that even steeper scoring rarely flips him to a loss
- **SMOE 2024 is the most system-sensitive comp** — Björnsson won 5 of 8 events but lost under WSM Linear; he'd win under any system with both a 1.25x+ ratio and a steep tail
- **WSM 2026 is on the bubble** — Nel needs a 1.39x+ ratio (F1 2010+) to beat Hooper
- **Rogue 2025 is uncontroversial** — Hooper wins under every system tested
- **F1 2003-2009 produces the same winners as WSM Linear in 4 of 5 comps** — closest match to the current strongman philosophy

See `reports/_summary.md` for full details.
