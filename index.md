---
title: WSM Compare
description: Strongman competitions re-scored under different real-world scoring systems
---

# WSM Compare

We re-scored 15 real strongman competitions (Arnold, Rogue, SMOE, WSM — both men's and women's) under 7 real-world scoring systems (current strongman, multiple eras of F1, MotoGP, plus a custom MotoGP variant) to see how the winners differ when the scoring philosophy changes.

Data sourced from [Strongman Archives](https://strongmanarchives.com/). Math verified against official published totals.

## How often the winner changes across systems

Counts of who wins each men's comp under each system, across 9 men's comps over 3 years:

| Scoring system | M. Hooper | Other winners |
|---|---|---|
| WSM Linear (current) | **7 / 9** | E. Singleton, R. Nel |
| F1 2003-2009 | **7 / 9** | L. Hatton, T. Stoltman |
| MotoGP | **7 / 9** | L. Hatton, T. Stoltman |
| MotoGP Extended | **7 / 9** | L. Hatton, T. Stoltman |
| F1 2010-present | **6 / 9** | L. Hatton, T. Stoltman, R. Nel |
| F1 1961-1990 | **5 / 9** | H. Björnsson, L. Hatton, T. Stoltman, R. Nel |
| F1 1991-2002 | **4 / 9** | L. Hatton (2), H. Björnsson, T. Stoltman, R. Nel |

The same winner emerges under most reasonable systems. The two F1 systems with the steepest top end and shortest tail (1961-1990 and 1991-2002, both top-6-only) produce the most reshuffling.

## Comps where the scoring system flips the winner

5 of the 9 men's comps have at least one alternate winner depending on the system used:

| Comp | Winner under WSM Linear | Alternate winner | Systems where alternate wins |
|---|---|---|---|
| **WSM 2026 finals** | M. Hooper (54) | R. Nel | F1 2010+, F1 1991-02, F1 1961-90 |
| **WSM 2025 finals** | R. Nel (47) | T. Stoltman | every other system tested |
| **SMOE 2024** | M. Hooper (117) | H. Björnsson | F1 1991-02, F1 1961-90 only |
| **SMOE 2025** | E. Singleton (93.5) | L. Hatton | every other system tested |
| **Arnold 2025** | M. Hooper (51.5) | L. Hatton | F1 1991-2002 only |

The remaining 4 men's comps (Arnold 2024, Arnold 2026, Rogue 2024, Rogue 2025) produce the same winner under all 7 systems.

See [the full cross-comp summary]({{ '/reports/_summary.html' | relative_url }}) for every winner under every system.

## Browse individual comp reports

Each report shows full standings under all 7 scoring systems, podium-by-system, and winner-flip analysis.

### Men's
- **WSM:** [2026 finals]({{ '/reports/wsm2026_finals.html' | relative_url }}) · [2025 finals]({{ '/reports/wsm2025_finals.html' | relative_url }})
- **Arnold Strongman Classic:** [2026]({{ '/reports/arnold2026.html' | relative_url }}) · [2025]({{ '/reports/arnold2025.html' | relative_url }}) · [2024]({{ '/reports/arnold2024.html' | relative_url }})
- **Rogue Invitational:** [2025]({{ '/reports/rogue2025.html' | relative_url }}) · [2024]({{ '/reports/rogue2024.html' | relative_url }})
- **Strongest Man on Earth:** [2025]({{ '/reports/smoe2025.html' | relative_url }}) · [2024]({{ '/reports/smoe2024.html' | relative_url }})

### Women's
- **Arnold Strongman Classic:** [2026]({{ '/reports/arnold2026_w.html' | relative_url }}) · [2025]({{ '/reports/arnold2025_w.html' | relative_url }}) · [2024]({{ '/reports/arnold2024_w.html' | relative_url }})
- **Rogue Invitational:** [2025]({{ '/reports/rogue2025_w.html' | relative_url }}) · [2024]({{ '/reports/rogue2024_w.html' | relative_url }})

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

## How ties and edge cases are handled

- **Scale length follows the comp's full roster**, including DNS athletes. A comp with 10 athletes uses a 10-position scale, regardless of how many actually competed in any event. DNS always scores 0.
- **Tie averaging:** athletes sharing a placement (e.g. all `T2`) split the points across the positions they consume. Three athletes tied at T2 → positions 2, 3, 4 → each gets the average of the points for those positions.
- **Scale truncation in big fields:** systems with short scales (F1 1991-2002 has 6 positions) zero-pad. In a 16-athlete comp under F1 1991-2002, positions 7-16 all score 0.
- **No-lift / withdrew rules vary across comps.** WSM 2026 treats `(No lift)` as DNS. SMOE 2024 treats no-lifts as competing-but-last. The data encodes whichever interpretation matches each comp's published totals.

---

[Source code on GitHub](https://github.com/stan-is-hate/wsm_compare)
