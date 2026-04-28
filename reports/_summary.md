# WSM Scoring System Comparison — All Comps

Cross-competition analysis across multiple real-world scoring systems.

## Scoring Systems Tested

| System | Origin | 1st/2nd ratio (10-athlete field) |
|--------|--------|----------------------------------|
| **WSM Linear** (10-9-8-7-6-5-4-3-2-1) | World's Strongest Man (current). N pts for 1st down to 1 for last. Equal gaps. | 1.11x |
| **F1 2010-present** (25-18-15-12-10-8-6-4-2-1) | Formula 1 (2010+). Steep top, drops off after 10th. | 1.39x |
| **F1 2003-2009** (10-8-6-5-4-3-2-1-0-0) | Formula 1 (2003-2009). Top 8 only. Lower 1st/2nd ratio (1.25x). | 1.25x |
| **F1 1991-2002** (10-6-4-3-2-1-0-0-0-0) | Formula 1 (1991-2002). Top 6 only. Schumacher era. 1.67x for winning. | 1.67x |
| **F1 1961-1990** (9-6-4-3-2-1-0-0-0-0) | Formula 1 (1961-1990). Top 6 only. Senna/Prost era. 1.5x for winning. | 1.50x |
| **MotoGP** (25-20-16-13-11-10-9-8-7-6) | MotoGP (current). All 10 positions score well. 1.25x for winning. | 1.25x |

## Cross-Competition Winners

| Comp | WSM Linear | F1 2010-present | F1 2003-2009 | F1 1991-2002 | F1 1961-1990 | MotoGP |
|------|-------|-------|-------|-------|-------|-------|
| **arnold2025** | M. Hooper (51.5) | M. Hooper (104.8) | M. Hooper (44) | L. Hatton (35) | M. Hooper (33) | M. Hooper (112.3) |
| **rogue2025** | M. Hooper (46) | M. Hooper (112) | M. Hooper (47) | M. Hooper (39) | M. Hooper (37) | M. Hooper (120) |
| **smoe2024** | M. Hooper (115.5) | H. Björnsson (140) | M. Hooper (58) | H. Björnsson (53) | H. Björnsson (48) | H. Björnsson (151) |
| **smoe2025** | L. Hatton (93.5) | L. Hatton (109.5) | L. Hatton (44) | L. Hatton (37) | L. Hatton (34.5) | L. Hatton (114.5) |
| **wsm2026_finals** | M. Hooper (54) | R. Nel (115) | M. Hooper (48) | R. Nel (41) | R. Nel (38) | M. Hooper (121) |
| **wsm2026_prelim** | M. Hooper (105.5) | R. Nel (66) | R. Nel (26) | R. Nel (23) | R. Nel (21) | R. Nel (71) |

## 1st-vs-2nd Gap Per System

How close was the comp under each system? Smaller gap = more sensitive to system choice.

| Comp | WSM Linear | F1 2010-present | F1 2003-2009 | F1 1991-2002 | F1 1961-1990 | MotoGP |
|------|-------|-------|-------|-------|-------|-------|
| **arnold2025** | 2.5 | 0.8 | 1 | 1 | 0 | 0.3 |
| **rogue2025** | 6.5 | 16.5 | 8.5 | 8.5 | 8.5 | 16.5 |
| **smoe2024** | 7.5 | 0.5 | 3 | 7 | 4 | 2.5 |
| **smoe2025** | 0.5 | 22.5 | 8.5 | 13.8 | 11.8 | 13.5 |
| **wsm2026_finals** | 2 | 3 | 1 | 3 | 1 | 2 |
| **wsm2026_prelim** | 7.5 | 4.2 | 1 | 4 | 3 | 0.8 |

## Winner Flips Per Comp

How many distinct winners does each comp produce across the 6 scoring systems?

| Comp | Distinct winners | Winners |
|------|-----------------|---------|
| **arnold2025** | 2 | L. Hatton, M. Hooper |
| **rogue2025** | 1 | M. Hooper |
| **smoe2024** | 2 | H. Björnsson, M. Hooper |
| **smoe2025** | 1 | L. Hatton |
| **wsm2026_finals** | 2 | M. Hooper, R. Nel |
| **wsm2026_prelim** | 2 | M. Hooper, R. Nel |

## Per-System Winner Distribution

Under each scoring system, who wins how many comps?

- **WSM Linear:** M. Hooper (5), L. Hatton (1)
- **F1 2010-present:** M. Hooper (2), R. Nel (2), H. Björnsson (1), L. Hatton (1)
- **F1 2003-2009:** M. Hooper (4), L. Hatton (1), R. Nel (1)
- **F1 1991-2002:** L. Hatton (2), R. Nel (2), M. Hooper (1), H. Björnsson (1)
- **F1 1961-1990:** M. Hooper (2), R. Nel (2), H. Björnsson (1), L. Hatton (1)
- **MotoGP:** M. Hooper (3), H. Björnsson (1), L. Hatton (1), R. Nel (1)

## Methodological Notes

- **Scale length follows the comp's full roster**, including DNS athletes. A comp with 10 athletes uses a 10-position scale, regardless of how many actually competed in any given event. DNS athletes always score 0 but conceptually occupy positions at the bottom of the field.
- **Tie averaging:** athletes sharing a placement string (e.g. all marked `T2`) split the points for the positions they collectively consume. 3 athletes at T2 → positions 2, 3, 4 → each gets `(scale[1] + scale[2] + scale[3]) / 3`.
- **Scale truncation in big fields:** systems with short scales (F1 1991-2002 has only 6 positions; F1 2003-2009 has 8) zero-pad in larger fields. In a 16-athlete comp under F1 1991-2002, positions 7-16 all score 0. This means the linear ordering at the tail is lost — useful to know if a comp's mid-pack matters.
- **Scale truncation in small fields:** systems with long scales (F1 2010+, MotoGP — both 10 positions) get sliced to fit smaller fields. A 9-athlete comp under F1 2010+ uses `[25, 18, 15, 12, 10, 8, 6, 4, 2]` — the last `1` is dropped. This mildly steepens the system.
- **Event names with markdown-special characters** (pipes `|`, brackets) will break the rendered tables. Use underscores or plain text in CSV column headers.
- **No-lift / withdrew rules vary across comps.** WSM 2026 treats a `(No lift)` on max events as DNS (0 pts). SMOE 2024 treats no-lifts as competing-but-last. The CSVs here encode whichever interpretation matches the comp's published totals; cross-comp comparison should account for this.

