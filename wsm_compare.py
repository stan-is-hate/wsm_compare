#!/usr/bin/env python3
"""WSM scoring system comparison.

Reads a competition CSV from comps/ and computes standings
under multiple real-world scoring systems.

CSV format:
    athlete,country,Event1,Event2,...
    Name,XYZ,1,T2,DNS,...

Placement values:
    1, 2, 3, ...    — solo placement
    T2, T3, ...     — tied at that position (script counts athletes with same string)
    DNS             — did not compete (0 pts always)

Usage:
    python3 wsm_compare.py comps/wsm2026_finals.csv
    python3 wsm_compare.py comps/arnold2025.csv
    python3 wsm_compare.py --all                  # run all CSVs in comps/ and print summary
    python3 wsm_compare.py --report               # generate markdown reports for all comps
    python3 wsm_compare.py --report comps/X.csv   # generate markdown report for one comp
"""
import csv
import sys
import os
import glob
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COMPS_DIR = os.path.join(SCRIPT_DIR, "comps")
REPORTS_DIR = os.path.join(SCRIPT_DIR, "reports")

# --- Real-world scoring systems ---
# (name, scale, description). scale=None means "WSM Linear" (N down to 1).
SCORING_SYSTEMS = [
    ("WSM Linear", None,
     "World's Strongest Man (current). N pts for 1st down to 1 for last. Equal gaps."),
    ("F1 2010-present", [25, 18, 15, 12, 10, 8, 6, 4, 2, 1],
     "Formula 1 (2010+). Steep top, drops off after 10th."),
    ("F1 2003-2009", [10, 8, 6, 5, 4, 3, 2, 1],
     "Formula 1 (2003-2009). Top 8 only. Lower 1st/2nd ratio (1.25x)."),
    ("F1 1991-2002", [10, 6, 4, 3, 2, 1],
     "Formula 1 (1991-2002). Top 6 only. Schumacher era. 1.67x for winning."),
    ("F1 1961-1990", [9, 6, 4, 3, 2, 1],
     "Formula 1 (1961-1990). Top 6 only. Senna/Prost era. 1.5x for winning."),
    ("MotoGP", [25, 20, 16, 13, 11, 10, 9, 8, 7, 6],
     "MotoGP (current). All 10 positions score well. 1.25x for winning."),
]


def parse_placement(s):
    """Returns (position_int, is_dns). Position is for sorting; ties detected by raw string."""
    s = s.strip()
    if s in ("DNS", "WD", "WITHDREW", "DQ", ""):
        return None, True
    if s.startswith("T"):
        return int(s[1:]), False
    return int(s), False


def get_scale(system_entry, field_size):
    """Slice the scale to the field size, padding with zeros if needed."""
    name, scale, _ = system_entry
    if scale is None:  # WSM Linear: N down to 1
        return list(range(field_size, 0, -1))
    return scale[:field_size] + [0] * max(0, field_size - len(scale))


def compute_event_points(placements_by_athlete, scale):
    """Given {athlete: placement_string}, return {athlete: points}.

    Tied athletes (same placement string like 'T2') share the points
    averaged across the positions they occupy.
    """
    # Group by raw placement string
    groups = defaultdict(list)
    dns_athletes = []
    for athlete, p_str in placements_by_athlete.items():
        pos, is_dns = parse_placement(p_str)
        if is_dns:
            dns_athletes.append(athlete)
        else:
            groups[p_str].append((athlete, pos))

    # Sort groups by position
    sorted_groups = sorted(groups.items(), key=lambda kv: kv[1][0][1])

    points = {a: 0 for a in placements_by_athlete}
    cur_idx = 0  # 0-indexed position
    for p_str, athletes in sorted_groups:
        n = len(athletes)
        # These athletes occupy positions cur_idx ... cur_idx + n - 1 (0-indexed)
        slot_pts = [scale[i] if i < len(scale) else 0 for i in range(cur_idx, cur_idx + n)]
        avg = sum(slot_pts) / n
        for athlete, _ in athletes:
            points[athlete] = avg
        cur_idx += n

    # DNS already has 0 from initialization
    return points


def load_comp(path):
    """Returns (comp_name, athletes, countries, events) where events maps event_name to {athlete: placement_string}."""
    with open(path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        raise ValueError(f"Empty CSV: {path}")

    fieldnames = list(rows[0].keys())
    static = {"athlete", "country"}
    event_names = [f for f in fieldnames if f.lower() not in static]

    athletes = [r["athlete"].strip() for r in rows]
    countries = {r["athlete"].strip(): r.get("country", "").strip() for r in rows}

    events = {}
    for ev in event_names:
        events[ev] = {r["athlete"].strip(): r[ev].strip() for r in rows}

    comp_name = os.path.basename(path).replace(".csv", "")
    return comp_name, athletes, countries, events


def get_field_size(event_placements):
    """Number of athletes who actually competed in this event (non-DNS)."""
    return sum(1 for p in event_placements.values() if not parse_placement(p)[1])


def fmt(v):
    return str(int(v)) if v == int(v) else f"{v:.1f}"


def get_placement_display(p_str):
    """For display, prettify placement strings."""
    p_str = p_str.strip()
    if not p_str or p_str in ("DNS", "WD", "WITHDREW", "DQ"):
        return "DNS"
    return p_str


def count_wins_and_top3(events, athlete):
    wins = top3 = 0
    for ev, placements in events.items():
        p_str = placements[athlete].strip()
        pos, is_dns = parse_placement(p_str)
        if is_dns:
            continue
        if pos == 1:
            wins += 1
        if pos <= 3:
            top3 += 1
    return wins, top3


def run_comp(path, verbose=True):
    comp_name, athletes, countries, events = load_comp(path)
    event_names = list(events.keys())

    if verbose:
        print("=" * 110)
        print(f"COMP: {comp_name.upper()}  ({len(athletes)} athletes, {len(event_names)} events)")
        print("=" * 110)

        # Placements table
        short = {ev: ev[:9] for ev in event_names}
        header = f"{'Athlete':<22}{'Country':<6}"
        for ev in event_names:
            header += f"{short[ev]:<10}"
        header += "  Wins Top3"
        print(f"\n{header}")
        print("-" * len(header))
        for a in athletes:
            row = f"{a:<22}{countries[a]:<6}"
            for ev in event_names:
                row += f"{get_placement_display(events[ev][a]):<10}"
            wins, top3 = count_wins_and_top3(events, a)
            row += f"  {wins:<4} {top3}"
            print(row)

    # Compute totals under each scoring system
    # The scale size = total athletes in comp (DNS still take up implicit positions)
    total_field_size = len(athletes)
    results = {}
    for sys_entry in SCORING_SYSTEMS:
        sys_name = sys_entry[0]
        scale = get_scale(sys_entry, total_field_size)
        totals = {a: 0.0 for a in athletes}
        for ev in event_names:
            pts = compute_event_points(events[ev], scale)
            for a in athletes:
                totals[a] += pts[a]
        sorted_totals = sorted(totals.items(), key=lambda x: -x[1])
        results[sys_name] = sorted_totals

    if verbose:
        print()
        print("=" * 110)
        print(f"STANDINGS UNDER EACH SCORING SYSTEM — {comp_name.upper()}")
        print("=" * 110)

        for sys_name, sorted_totals in results.items():
            sys_entry = next(s for s in SCORING_SYSTEMS if s[0] == sys_name)
            scale = get_scale(sys_entry, len(athletes))
            ratio = scale[0] / scale[1] if scale[1] > 0 else float('inf')
            print(f"\n  {sys_name}  [scale: {scale[:min(10, len(scale))]}{'...' if len(scale) > 10 else ''}, 1st/2nd: {ratio:.2f}x]")
            print(f"  {sys_entry[2]}")
            print(f"  {'#':<4}{'Athlete':<22}{'Pts':<8}")
            print("  " + "-" * 30)
            for rank, (a, total) in enumerate(sorted_totals, 1):
                print(f"  {rank:<4}{a:<22}{fmt(total):<8}")

        # Side-by-side podium
        print()
        print("=" * 110)
        print(f"PODIUM PER SYSTEM — {comp_name.upper()}")
        print("=" * 110)
        print(f"\n  {'System':<20} {'1st':<28} {'2nd':<28} {'3rd':<28}")
        print("  " + "-" * 100)
        for sys_name, sorted_totals in results.items():
            line = f"  {sys_name:<20}"
            for athlete, total in sorted_totals[:3]:
                line += f" {athlete + ' (' + fmt(total) + ')':<28}"
            print(line)

    return comp_name, results


def write_comp_report(path, out_dir):
    """Generate a markdown report for a single comp."""
    comp_name, athletes, countries, events = load_comp(path)
    event_names = list(events.keys())
    total_field_size = len(athletes)

    lines = []
    w = lines.append
    w(f"# {comp_name.replace('_', ' ').upper()}")
    w("")
    w(f"**{len(athletes)} athletes, {len(event_names)} events**")
    w("")

    # Placements table
    w("## Event Placements")
    w("")
    header = "| Athlete | Country |"
    sep = "|---------|---------|"
    for ev in event_names:
        header += f" {ev.replace('_', ' ')} |"
        sep += "----------|"
    header += " Wins | Top-3 |"
    sep += "------|-------|"
    w(header)
    w(sep)
    for a in athletes:
        row = f"| {a} | {countries[a]} |"
        for ev in event_names:
            row += f" {get_placement_display(events[ev][a])} |"
        wins, top3 = count_wins_and_top3(events, a)
        row += f" {wins} | {top3} |"
        w(row)
    w("")

    # Compute totals under each system
    results = {}
    for sys_entry in SCORING_SYSTEMS:
        sys_name = sys_entry[0]
        scale = get_scale(sys_entry, total_field_size)
        totals = {a: 0.0 for a in athletes}
        event_pts = {ev: {} for ev in event_names}
        for ev in event_names:
            pts = compute_event_points(events[ev], scale)
            event_pts[ev] = pts
            for a in athletes:
                totals[a] += pts[a]
        sorted_totals = sorted(totals.items(), key=lambda x: -x[1])
        results[sys_name] = (sorted_totals, event_pts, scale)

    # Standings under each system
    w("## Standings Under Each Scoring System")
    w("")
    for sys_entry in SCORING_SYSTEMS:
        sys_name = sys_entry[0]
        sorted_totals, event_pts, scale = results[sys_name]
        ratio = scale[0] / scale[1] if scale[1] > 0 else float('inf')

        w(f"### {sys_name}")
        w("")
        w(f"_{sys_entry[2]}_")
        w("")
        w(f"**Scale:** `{scale}` — **1st/2nd ratio:** {ratio:.2f}x")
        w("")
        header = "| # | Athlete | Country |"
        sep = "|---|---------|---------|"
        for ev in event_names:
            header += f" {ev.replace('_', ' ')} |"
            sep += "----------|"
        header += " **Total** |"
        sep += "-----------|"
        w(header)
        w(sep)
        for rank, (a, total) in enumerate(sorted_totals, 1):
            row = f"| {rank} | {a} | {countries[a]} |"
            for ev in event_names:
                row += f" {fmt(event_pts[ev][a])} |"
            row += f" **{fmt(total)}** |"
            w(row)
        w("")

    # Podium comparison
    w("## Podium Per System")
    w("")
    w("| System | 1st/2nd ratio | 1st | 2nd | 3rd |")
    w("|--------|---------------|-----|-----|-----|")
    for sys_entry in SCORING_SYSTEMS:
        sys_name = sys_entry[0]
        sorted_totals, _, scale = results[sys_name]
        ratio = scale[0] / scale[1] if scale[1] > 0 else float('inf')
        line = f"| {sys_name} | {ratio:.2f}x |"
        for athlete, total in sorted_totals[:3]:
            line += f" {athlete} ({fmt(total)}) |"
        w(line)
    w("")

    # Winner-flip analysis
    winners = {sn: results[sn][0][0][0] for sn in results}
    unique_winners = set(winners.values())
    if len(unique_winners) > 1:
        w("## Winner Flip Analysis")
        w("")
        w("This comp produces **different winners** under different scoring systems:")
        w("")
        by_winner = defaultdict(list)
        for sn, w_name in winners.items():
            by_winner[w_name].append(sn)
        for winner_name, sys_list in by_winner.items():
            w(f"- **{winner_name}** wins under: {', '.join(sys_list)}")
        w("")
    else:
        w("## Winner Flip Analysis")
        w("")
        w(f"**{list(unique_winners)[0]}** wins under every scoring system tested. No flip.")
        w("")

    out_path = os.path.join(out_dir, f"{comp_name}.md")
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    return out_path, results


def write_combined_report(comps_dir, out_dir):
    """Generate a combined cross-comp summary report."""
    paths = sorted(glob.glob(os.path.join(comps_dir, "*.csv")))
    all_results = []
    for path in paths:
        comp_name, _, _, _ = load_comp(path)
        _, results = write_comp_report(path, out_dir)
        all_results.append((comp_name, results))

    lines = []
    w = lines.append
    w("# WSM Scoring System Comparison — All Comps")
    w("")
    w("Cross-competition analysis across multiple real-world scoring systems.")
    w("")
    w("## Scoring Systems Tested")
    w("")
    w("| System | Origin | 1st/2nd ratio (10-athlete field) |")
    w("|--------|--------|----------------------------------|")
    for sys_entry in SCORING_SYSTEMS:
        sys_name, _, sys_desc = sys_entry
        scale_10 = get_scale(sys_entry, 10)
        ratio = scale_10[0] / scale_10[1] if scale_10[1] > 0 else float('inf')
        scale_str = "-".join(fmt(x) for x in scale_10)
        w(f"| **{sys_name}** ({scale_str}) | {sys_desc} | {ratio:.2f}x |")
    w("")

    # Cross-comp winner table
    w("## Cross-Competition Winners")
    w("")
    sys_names = [s[0] for s in SCORING_SYSTEMS]
    header = "| Comp |"
    sep = "|------|"
    for sn in sys_names:
        header += f" {sn} |"
        sep += "-------|"
    w(header)
    w(sep)
    for comp_name, results in all_results:
        row = f"| **{comp_name}** |"
        for sn in sys_names:
            sorted_totals = results[sn][0] if isinstance(results[sn], tuple) else results[sn]
            winner_name, winner_pts = sorted_totals[0]
            row += f" {winner_name} ({fmt(winner_pts)}) |"
        w(row)
    w("")

    # Per-comp 1st/2nd gap
    w("## 1st-vs-2nd Gap Per System")
    w("")
    w("How close was the comp under each system? Smaller gap = more sensitive to system choice.")
    w("")
    header = "| Comp |"
    sep = "|------|"
    for sn in sys_names:
        header += f" {sn} |"
        sep += "-------|"
    w(header)
    w(sep)
    for comp_name, results in all_results:
        row = f"| **{comp_name}** |"
        for sn in sys_names:
            sorted_totals = results[sn][0] if isinstance(results[sn], tuple) else results[sn]
            gap = sorted_totals[0][1] - sorted_totals[1][1]
            row += f" {fmt(gap)} |"
        w(row)
    w("")

    # Winner flip count per comp
    w("## Winner Flips Per Comp")
    w("")
    w("How many distinct winners does each comp produce across the 6 scoring systems?")
    w("")
    w("| Comp | Distinct winners | Winners |")
    w("|------|-----------------|---------|")
    for comp_name, results in all_results:
        winners = set()
        winner_list = []
        for sn in sys_names:
            sorted_totals = results[sn][0] if isinstance(results[sn], tuple) else results[sn]
            winners.add(sorted_totals[0][0])
            winner_list.append(sorted_totals[0][0])
        w(f"| **{comp_name}** | {len(winners)} | {', '.join(sorted(winners))} |")
    w("")

    # Per-system: who wins the most comps
    w("## Per-System Winner Distribution")
    w("")
    w("Under each scoring system, who wins how many comps?")
    w("")
    for sn in sys_names:
        winner_counts = defaultdict(int)
        for comp_name, results in all_results:
            sorted_totals = results[sn][0] if isinstance(results[sn], tuple) else results[sn]
            winner_counts[sorted_totals[0][0]] += 1
        w(f"- **{sn}:** " + ", ".join(f"{a} ({n})" for a, n in sorted(winner_counts.items(), key=lambda x: -x[1])))
    w("")

    out_path = os.path.join(out_dir, "_summary.md")
    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    return out_path


def run_all(comps_dir):
    paths = sorted(glob.glob(os.path.join(comps_dir, "*.csv")))
    all_results = []
    for path in paths:
        all_results.append(run_comp(path, verbose=True))
        print()

    # Cross-comp summary: who would have won each comp under each system
    print()
    print("=" * 110)
    print("CROSS-COMPETITION WINNER SUMMARY")
    print("=" * 110)

    sys_names = [s[0] for s in SCORING_SYSTEMS]
    print(f"\n  {'Comp':<22}", end="")
    for sn in sys_names:
        print(f"{sn[:18]:<20}", end="")
    print()
    print("  " + "-" * (22 + 20 * len(sys_names)))

    for comp_name, results in all_results:
        print(f"  {comp_name:<22}", end="")
        for sn in sys_names:
            winner = results[sn][0][0]
            print(f"{winner[:18]:<20}", end="")
        print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "--all":
        run_all(COMPS_DIR)
    elif sys.argv[1] == "--report":
        if len(sys.argv) > 2:
            out_path, _ = write_comp_report(sys.argv[2], REPORTS_DIR)
            print(f"Wrote {out_path}")
        else:
            summary_path = write_combined_report(COMPS_DIR, REPORTS_DIR)
            print(f"Wrote per-comp reports + {summary_path}")
    else:
        run_comp(sys.argv[1])
