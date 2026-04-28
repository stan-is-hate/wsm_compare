# WSM Compare

A small Python tool that re-scores strongman competition results under different real-world scoring systems (current strongman, multiple eras of F1, MotoGP, plus a custom MotoGP variant). For results and analysis, see the rendered site:

🌐 **https://stan-is-hate.github.io/wsm_compare/**

This README covers the technical bits: running it, project layout, adding scoring systems, adding comps.

## Running it

Zero dependencies (Python stdlib only).

```bash
# Add a comp from Strongman Archives (auto-names from page title)
python3 wsm_compare.py fetch 2361
python3 wsm_compare.py fetch https://strongmanarchives.com/viewContest.php?id=2361
python3 wsm_compare.py fetch 2361 --name wsm2026_finals    # override filename

# Re-score under all systems
python3 wsm_compare.py compare comps/wsm2026_finals.csv     # one comp, stdout
python3 wsm_compare.py compare --all                         # all comps, stdout
python3 wsm_compare.py compare --report                      # all comps to markdown
```

Tests: `python3 -m unittest discover tests` (54 tests, ~0.4s)

## Project layout

```
wsm_compare/
├── wsm_compare.py            # CLI: fetch + compare subcommands
├── comps/                    # competition CSVs (one per single-contest comp)
├── reports/                  # generated markdown reports
├── scoring_systems/          # one module per scoring system
│   ├── _base.py              # ScoringSystem dataclass
│   ├── _registry.py          # ALL_SYSTEMS list, by_name lookup
│   └── <name>.py             # one file per system (wsm_linear, f1_2010, etc.)
├── tests/                    # unit + integration + CLI tests
├── index.md                  # GitHub Pages homepage (casual readers)
└── _config.yml               # Jekyll config
```

## CSV format

```csv
athlete,country,Event1,Event2,...
M. Hooper,CAN,1,T2,DNS,...
```

Placement values:
- `1`, `2`, `3` — solo placement
- `T2`, `T3` — tied (the script counts athletes with the same string to determine tie size and averages points across the positions they consume)
- `DNS` (or `WD`, `WITHDREW`, `DQ`) — did not compete / withdrew / no lift; always 0 pts

## Adding a new scoring system

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

## Adding a new comp

```bash
python3 wsm_compare.py fetch <strongmanarchives_url_or_id>
python3 wsm_compare.py compare --report
```

The fetch subcommand:
- Accepts a Strongman Archives URL or a bare contest ID
- Hits `/fetchContestResult.php` for canonical points
- Derives global per-event placements (athletes with same canonical pts in an event are tied)
- Auto-names the output file from the page `<title>` (`"Strongman Archives - 2026 WSM Final"` → `wsm2026_finals.csv`)
- Refuses to overwrite an existing file (use `--name` to override)
- Rate-limited to 1.5s between requests (be nice to a small community-run site)

## Methodological notes

- **Scale length follows the comp's full roster**, including DNS athletes. A comp with 10 athletes uses a 10-position scale, regardless of how many actually competed in any event. DNS always scores 0.
- **Tie averaging:** athletes sharing a placement (e.g. all `T2`) split points across positions consumed. 3 athletes at T2 → positions 2, 3, 4 → each gets `(scale[1] + scale[2] + scale[3]) / 3`.
- **Scale truncation in big fields:** systems with short scales (F1 1991-2002 has 6 positions) zero-pad. In a 16-athlete comp under F1 1991-2002, positions 7-16 all score 0.
- **No-lift / withdrew rules vary across comps.** WSM 2026 treats `(No lift)` as DNS. SMOE 2024 treats no-lifts as competing-but-last. The CSVs encode whichever interpretation matches the comp's published totals.

## Site structure

Two separate documents:
- `index.md` — rendered as the GitHub Pages homepage. Casual-reader summary of findings.
- `README.md` — this file. Technical reference for repo browsers and contributors. Excluded from Jekyll via `_config.yml` so it doesn't render at `/README.html` on the site.

## License

No license attached (yet). Open an issue if you want to use this for something.
