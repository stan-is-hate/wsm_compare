# Tests

Test suite for `wsm_compare.py`. Uses Python's stdlib `unittest` — zero external dependencies.

## Running

From the project root:

```sh
python3 -m unittest discover tests
```

For more detail:

```sh
python3 -m unittest discover tests -v
```

To run a single test class or method:

```sh
python3 -m unittest tests.test_wsm_compare.ComputeEventPointsTests
python3 -m unittest tests.test_wsm_compare.IntegrationTests.test_wsm2026_hooper_total_wsm_linear
```

## What's covered

- **`parse_placement`** — solo positions, tied positions (`T2`, `T15`), DNS variants (`DNS`, `WD`, `WITHDREW`, `DQ`, empty), whitespace handling.
- **`get_scale`** — WSM Linear at field 10/16, F1 2010+ truncation, F1 2003-2009 zero-padding.
- **`compute_event_points`** — no ties, 2-way / 3-way / 6-way ties at T2, all-DNS, mixed DNS + competing.
- **`get_field_size`** — counting non-DNS athletes.
- **`count_wins_and_top3`** — 1st-place wins, top-3 finishes, ties, DNS handling.
- **`load_comp`** — basic parse, 2-athlete comps, all-DNS events, non-ASCII names (Fojtů, Björnsson), empty CSV.
- **Integration** — totals computed from actual `comps/wsm2026_finals.csv` and `comps/arnold2025.csv` match official results (Hooper 54 / 51.5, Nel 52, Hatton 49, Björnsson 42.5).

## Fixtures

Unit tests for `load_comp` create temp CSVs via `tempfile.NamedTemporaryFile` and clean up in `tearDown`. Integration tests read the real CSVs from `comps/`.

## Speed

Suite runs in well under a second. No I/O beyond temp file creation and reading the (tiny) `comps/*.csv` files.
