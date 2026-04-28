---
title: WSM Compare
description: Strongman competitions re-scored under different real-world scoring systems
---

# WSM Compare
People often argue what would happen if strongman used a different scoring system.
We re-scored 15 real strongman competitions (Arnold, Rogue, SMOE, WSM — both men's and women's) under 7 real-world scoring systems (current strongman, multiple eras of F1, MotoGP, plus a custom MotoGP variant) to see what would actually happen.

**Of course** this is **not fair**. If athletes knew the scoring system was different, their whole approach to prep and events would be different and results won't be the same. Keep that in mind when browsing this data, because while it's a fun little "what-if", it doesn't work like that in reality.

Data sourced from [Strongman Archives](https://strongmanarchives.com/). Math verified against official published totals.

## How often the winner changes across systems

Counts of who wins each comp under each system, across 14 comps over 3 years (9 men's, 5 women's).

Bold = actual real-world winner (under current WSM Linear scoring). `x/7` = how many of the 7 tested scoring systems crowned that athlete.

### Men's

| Comp | Winners under different systems |
|---|---|
| WSM 2026 | **M. Hooper (4/7)**, R. Nel (3/7) |
| WSM 2025 | **R. Nel (1/7)**, T. Stoltman (6/7) |
| Arnold 2026 | **M. Hooper (7/7)** |
| Arnold 2025 | **M. Hooper (6/7)**, L. Hatton (1/7) |
| Arnold 2024 | **M. Hooper (7/7)** |
| Rogue 2025 | **M. Hooper (7/7)** |
| Rogue 2024 | **M. Hooper (7/7)** |
| SMOE 2025 | **E. Singleton (1/7)**, L. Hatton (6/7) |
| SMOE 2024 | **M. Hooper (5/7)**, H. Björnsson (2/7) |

### Women's

| Comp | Winners under different systems |
|---|---|
| Arnold 2026 | **O. Liashchuk (1/7)**, I. Carrasquillo (6/7) |
| Arnold 2025 | **I. Carrasquillo (7/7)** |
| Arnold 2024 | **A. Jardine (7/7)** |
| Rogue 2025 | **I. Carrasquillo (7/7)** |
| Rogue 2024 | **I. Carrasquillo (7/7)** |

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

## Findings

### Men's

- **4 of 9 men's comps are uncontroversial** — same winner under all 7 systems. Arnold 2024, Arnold 2026, Rogue 2024, Rogue 2025 all give M. Hooper the trophy regardless of scoring philosophy.

- **In the comps Hooper won under current WSM scoring, he also wins under most other systems.** The systems that take wins away from him are the steepest top-6-only F1 variants (F1 1961-1990 and F1 1991-2002), where mid-pack consistency scores zero and event wins matter most. Hooper is a "place 2nd-3rd in everything" athlete, not a "win 3 events outright" athlete — flatter scales reward his style.

- **The biggest reshuffling is at the close finals.** WSM 2025 (Nel by 0.5 pts) and SMOE 2025 (Singleton by 0.5 pts) each have actual winners who only prevail under 1 of 7 systems. Under every steeper system, the runner-up takes it. SMOE 2024 also flipped under 2 systems despite Hooper's clean 9-pt margin.

- **WSM 2026 sits in the middle** — Hooper won by 2 pts but only takes 4 of 7 systems. Nel wins under any system with a 1.39x or higher 1st/2nd ratio.

### Women's

- **4 of 5 women's comps are uncontroversial** — same winner under all 7 systems. Only Arnold 2026 flips.

- **I. Carrasquillo is the dominant figure across the women's dataset** — she wins 27 of 35 system-comp slots (5 comps × 7 systems = 35), including all 7 systems for Arnold 2025, Rogue 2024, and Rogue 2025. Functionally the women's-side equivalent of Hooper.

- **Arnold 2026 is the women's outlier.** O. Liashchuk took it under WSM Linear, but I. Carrasquillo wins under every other system tested. Same pattern as WSM 2025 on the men's side: a real-world winner who only prevails under one specific scoring philosophy.

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
