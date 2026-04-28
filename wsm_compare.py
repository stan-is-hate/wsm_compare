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
from dataclasses import dataclass
from typing import Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COMPS_DIR = os.path.join(SCRIPT_DIR, "comps")
REPORTS_DIR = os.path.join(SCRIPT_DIR, "reports")

DNS_TOKENS = {"DNS", "WD", "WITHDREW", "DQ", ""}


# --- Real-world scoring systems ---

@dataclass(frozen=True)
class ScoringSystem:
    name: str
    scale: Optional[list]  # None = "WSM Linear" (N down to 1)
    description: str

    def get_scale(self, field_size: int) -> list:
        """Slice the scale to the field size, padding with zeros if needed."""
        if self.scale is None:
            return list(range(field_size, 0, -1))
        return self.scale[:field_size] + [0] * max(0, field_size - len(self.scale))


SCORING_SYSTEMS = [
    ScoringSystem("WSM Linear", None,
                  "World's Strongest Man (current). N pts for 1st down to 1 for last. Equal gaps."),
    ScoringSystem("F1 2010-present", [25, 18, 15, 12, 10, 8, 6, 4, 2, 1],
                  "Formula 1 (2010+). Steep top, drops off after 10th."),
    ScoringSystem("F1 2003-2009", [10, 8, 6, 5, 4, 3, 2, 1],
                  "Formula 1 (2003-2009). Top 8 only. Lower 1st/2nd ratio (1.25x)."),
    ScoringSystem("F1 1991-2002", [10, 6, 4, 3, 2, 1],
                  "Formula 1 (1991-2002). Top 6 only. Schumacher era. 1.67x for winning."),
    ScoringSystem("F1 1961-1990", [9, 6, 4, 3, 2, 1],
                  "Formula 1 (1961-1990). Top 6 only. Senna/Prost era. 1.5x for winning."),
    ScoringSystem("MotoGP", [25, 20, 16, 13, 11, 10, 9, 8, 7, 6],
                  "MotoGP (current). All 10 positions score well. 1.25x for winning."),
]


# Backwards-compatible shim for tests/external callers that pass a tuple-style entry.
# Tests originally used `(name, scale, desc)` tuples; the function now also accepts
# ScoringSystem instances directly.
def get_scale(system_entry, field_size):
    if isinstance(system_entry, ScoringSystem):
        return system_entry.get_scale(field_size)
    name, scale, _ = system_entry
    return ScoringSystem(name, scale, "").get_scale(field_size)


def parse_placement(s):
    """Returns (position_int, is_dns). Position is for sorting; ties detected by raw string.

    Raises ValueError on malformed input (e.g., 'Tabc', '1.5', 'foo').
    """
    s = s.strip()
    if s in DNS_TOKENS:
        return None, True
    try:
        if s.startswith("T"):
            pos = int(s[1:])
        else:
            pos = int(s)
    except ValueError:
        raise ValueError(f"Malformed placement value: {s!r} (expected integer, T-prefixed integer, or DNS)")
    if pos < 1:
        raise ValueError(f"Invalid placement value: {s!r} (position must be >= 1)")
    return pos, False


def compute_event_points(placements_by_athlete, scale):
    """Given {athlete: placement_string}, return {athlete: points}.

    Tied athletes (same placement string like 'T2') share the points
    averaged across the positions they occupy.
    """
    groups = defaultdict(list)
    for athlete, p_str in placements_by_athlete.items():
        pos, is_dns = parse_placement(p_str)
        if not is_dns:
            groups[p_str].append((athlete, pos))

    sorted_groups = sorted(groups.items(), key=lambda kv: kv[1][0][1])

    points = {a: 0 for a in placements_by_athlete}
    cur_idx = 0  # 0-indexed position
    for _, athletes in sorted_groups:
        n = len(athletes)
        slot_pts = [scale[i] if i < len(scale) else 0 for i in range(cur_idx, cur_idx + n)]
        avg = sum(slot_pts) / n
        for athlete, _ in athletes:
            points[athlete] = avg
        cur_idx += n

    return points


def load_comp(path):
    """Returns (comp_name, athletes, countries, events, groups) where:
       - events maps event_name to {athlete: placement_string}
       - groups maps athlete to group_id (or None if no 'group' column in CSV)
    """
    with open(path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        raise ValueError(f"Empty CSV: {path}")

    fieldnames = list(rows[0].keys())
    static = {"athlete", "country", "group"}
    event_names = [f for f in fieldnames if f.lower() not in static]

    if not event_names:
        raise ValueError(f"CSV has no event columns: {path} (expected columns beyond 'athlete' and 'country')")

    has_groups = "group" in (f.lower() for f in fieldnames)

    athletes = [r["athlete"].strip() for r in rows]
    countries = {r["athlete"].strip(): r.get("country", "").strip() for r in rows}
    groups = {r["athlete"].strip(): r.get("group", "").strip() for r in rows} if has_groups else None

    events = {}
    for ev in event_names:
        events[ev] = {r["athlete"].strip(): r[ev].strip() for r in rows}

    # Validate every placement parses cleanly — fail fast with athlete/event context
    for ev, placements in events.items():
        for athlete, p_str in placements.items():
            try:
                parse_placement(p_str)
            except ValueError as e:
                raise ValueError(f"{path}: athlete {athlete!r}, event {ev!r}: {e}")

    comp_name = os.path.basename(path).replace(".csv", "")
    return comp_name, athletes, countries, events, groups


def fmt(v):
    return str(int(v)) if v == int(v) else f"{v:.1f}"


def get_placement_display(p_str):
    """For display, prettify placement strings."""
    p_str = p_str.strip()
    if not p_str or p_str in DNS_TOKENS:
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


@dataclass
class SystemResult:
    sorted_totals: list  # list of (athlete, total_pts) sorted desc
    event_pts: dict      # event_name -> {athlete: pts}
    scale: list

    def sorted_totals_dict(self):
        """Convenience: return totals as {athlete: total_pts}."""
        return dict(self.sorted_totals)


def determine_qualifiers(athletes, groups, events, n_per_group=2):
    """Top N per group based on WSM Linear scoring with global placements.

    Returns: list of qualifier athlete names, in original group order.
    """
    wsm_linear = next(s for s in SCORING_SYSTEMS if s.name == "WSM Linear")
    scale = wsm_linear.get_scale(len(athletes))
    totals = {a: 0.0 for a in athletes}
    for placements in events.values():
        pts = compute_event_points(placements, scale)
        for a in athletes:
            totals[a] += pts[a]

    qualifiers = []
    by_group = defaultdict(list)
    for a in athletes:
        by_group[groups[a]].append(a)
    for g in sorted(by_group.keys()):
        sorted_in_group = sorted(by_group[g], key=lambda a: -totals[a])
        qualifiers.extend(sorted_in_group[:n_per_group])
    return qualifiers


def derive_subset_placements(subset_athletes, events):
    """Re-rank a subset of athletes within each event based on their global placements.

    Returns: {event_name: {athlete: subset_placement_string}}.
    """
    subset_events = {}
    for ev, placements in events.items():
        subset_placements = {a: placements[a] for a in subset_athletes}
        subset_events[ev] = _rerank_placements(subset_placements)
    return subset_events


def _rerank_placements(placements):
    """Take a subset of placement strings and produce within-subset placements.

    Athletes with the same global placement string remain tied.
    """
    by_p_str = defaultdict(list)
    dns = []
    for athlete, p_str in placements.items():
        pos, is_dns = parse_placement(p_str)
        if is_dns:
            dns.append(athlete)
        else:
            by_p_str[p_str].append((athlete, pos))

    sorted_p_strs = sorted(by_p_str.keys(), key=lambda s: by_p_str[s][0][1])

    result = {}
    cur_rank = 1
    for p_str in sorted_p_strs:
        athletes_at = by_p_str[p_str]
        n = len(athletes_at)
        rank_str = str(cur_rank) if n == 1 else f"T{cur_rank}"
        for athlete, _ in athletes_at:
            result[athlete] = rank_str
        cur_rank += n
    for a in dns:
        result[a] = "DNS"
    return result


def compute_all_systems(athletes, events):
    """Compute totals for every athlete under every scoring system.

    Returns: {system_name: SystemResult}.
    """
    total_field_size = len(athletes)
    results = {}
    for system in SCORING_SYSTEMS:
        scale = system.get_scale(total_field_size)
        totals = {a: 0.0 for a in athletes}
        event_pts = {}
        for ev, placements in events.items():
            pts = compute_event_points(placements, scale)
            event_pts[ev] = pts
            for a in athletes:
                totals[a] += pts[a]
        sorted_totals = sorted(totals.items(), key=lambda x: -x[1])
        results[system.name] = SystemResult(sorted_totals, event_pts, scale)
    return results


def run_comp(path, verbose=True):
    comp_name, athletes, countries, events, groups = load_comp(path)
    event_names = list(events.keys())
    results = compute_all_systems(athletes, events)

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

        print()
        print("=" * 110)
        print(f"STANDINGS UNDER EACH SCORING SYSTEM — {comp_name.upper()}")
        print("=" * 110)

        for system in SCORING_SYSTEMS:
            res = results[system.name]
            ratio = res.scale[0] / res.scale[1] if res.scale[1] > 0 else float('inf')
            scale_preview = res.scale[:min(10, len(res.scale))]
            ellipsis = '...' if len(res.scale) > 10 else ''
            print(f"\n  {system.name}  [scale: {scale_preview}{ellipsis}, 1st/2nd: {ratio:.2f}x]")
            print(f"  {system.description}")
            print(f"  {'#':<4}{'Athlete':<22}{'Pts':<8}")
            print("  " + "-" * 30)
            for rank, (a, total) in enumerate(res.sorted_totals, 1):
                print(f"  {rank:<4}{a:<22}{fmt(total):<8}")

        # Side-by-side podium
        print()
        print("=" * 110)
        print(f"PODIUM PER SYSTEM — {comp_name.upper()}")
        print("=" * 110)
        print(f"\n  {'System':<20} {'1st':<28} {'2nd':<28} {'3rd':<28}")
        print("  " + "-" * 100)
        for system in SCORING_SYSTEMS:
            res = results[system.name]
            line = f"  {system.name:<20}"
            for athlete, total in res.sorted_totals[:3]:
                line += f" {athlete + ' (' + fmt(total) + ')':<28}"
            print(line)

    return comp_name, results


def _require_groups(groups, mode_name):
    if groups is None:
        raise ValueError(f"{mode_name} mode requires a CSV with a 'group' column")


def write_groups_report(path, out_dir):
    """Generate a markdown report comparing groups as teams.

    Sums each group's athletes' points under each scoring system to crown
    the strongest group.
    """
    comp_name, athletes, countries, events, groups = load_comp(path)
    _require_groups(groups, "groups")
    results = compute_all_systems(athletes, events)
    sys_names = [s.name for s in SCORING_SYSTEMS]
    group_ids = sorted(set(groups.values()))

    lines = []
    w = lines.append
    w(f"# {comp_name.replace('_', ' ').upper()} — Groups as Teams")
    w("")
    w(f"**{len(athletes)} athletes across {len(group_ids)} groups, {len(events)} events**")
    w("")
    w("Each group's total = sum of its athletes' points under each scoring system.")
    w("Athletes' points are computed from their global placements (1-N across the full field).")
    w("")

    # Group totals
    w("## Group Standings")
    w("")
    header = "| Rank | Group |"
    sep = "|------|-------|"
    for sn in sys_names:
        header += f" {sn} |"
        sep += "-------|"
    w(header)
    w(sep)
    group_totals_by_sys = {}
    for sn in sys_names:
        gt = defaultdict(float)
        for a in athletes:
            gt[groups[a]] += results[sn].sorted_totals_dict()[a]
        group_totals_by_sys[sn] = gt

    ranked_groups = sorted(group_ids, key=lambda g: -group_totals_by_sys["WSM Linear"][g])
    for rank, g in enumerate(ranked_groups, 1):
        row = f"| {rank} | **G{g}** |"
        for sn in sys_names:
            row += f" {fmt(group_totals_by_sys[sn][g])} |"
        w(row)
    w("")

    # Per-group breakdown
    w("## Group Breakdowns (WSM Linear)")
    w("")
    for g in ranked_groups:
        members = sorted(
            [a for a in athletes if groups[a] == g],
            key=lambda a: -results["WSM Linear"].sorted_totals_dict()[a],
        )
        w(f"### Group {g} — {fmt(group_totals_by_sys['WSM Linear'][g])} pts")
        w("")
        w("| Athlete | Country | WSM Linear pts |")
        w("|---------|---------|----------------|")
        for a in members:
            pts = results["WSM Linear"].sorted_totals_dict()[a]
            w(f"| {a} | {countries[a]} | {fmt(pts)} |")
        w("")

    # Strongest group per system
    w("## Strongest Group Per System")
    w("")
    w("| System | Winner | Pts | Runner-up | Pts | Gap |")
    w("|--------|--------|-----|-----------|-----|-----|")
    for sn in sys_names:
        gt = group_totals_by_sys[sn]
        sorted_gs = sorted(gt.items(), key=lambda x: -x[1])
        gap = sorted_gs[0][1] - sorted_gs[1][1]
        w(f"| {sn} | G{sorted_gs[0][0]} | {fmt(sorted_gs[0][1])} | G{sorted_gs[1][0]} | {fmt(sorted_gs[1][1])} | {fmt(gap)} |")
    w("")

    out_path = os.path.join(out_dir, f"{comp_name}_groups.md")
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return out_path, results


def write_pool_report(path, out_dir):
    """Generate a markdown report pooling all athletes into a single stack rank.

    BONUS: also includes top 10 (qualifiers) re-ranked within their subset
    as a control matching WSM's official 'Prelim Score' carryover.
    """
    comp_name, athletes, countries, events, groups = load_comp(path)
    _require_groups(groups, "pool")
    event_names = list(events.keys())
    results = compute_all_systems(athletes, events)
    sys_names = [s.name for s in SCORING_SYSTEMS]

    lines = []
    w = lines.append
    w(f"# {comp_name.replace('_', ' ').upper()} — Pooled Stack Rank")
    w("")
    w(f"**{len(athletes)} athletes pooled across all groups, {len(event_names)} events**")
    w("")
    w("All athletes ranked against each other globally per event, points summed across events.")
    w("Group affiliation shown for context but not used in scoring.")
    w("")

    # Full pooled standings under each system
    w("## Pooled Standings (All Athletes)")
    w("")
    for system in SCORING_SYSTEMS:
        res = results[system.name]
        ratio = res.scale[0] / res.scale[1] if res.scale[1] > 0 else float('inf')
        w(f"### {system.name}")
        w("")
        w(f"_{system.description}_")
        w("")
        w(f"**Scale:** `{res.scale}` — **1st/2nd ratio:** {ratio:.2f}x")
        w("")
        w("| # | Athlete | Country | Group | " + " | ".join(ev for ev in event_names) + " | **Total** |")
        w("|---|---------|---------|-------|" + "|".join("-------" for _ in event_names) + "|-----------|")
        for rank, (a, total) in enumerate(res.sorted_totals, 1):
            row = f"| {rank} | {a} | {countries[a]} | G{groups[a]} |"
            for ev in event_names:
                row += f" {fmt(res.event_pts[ev][a])} |"
            row += f" **{fmt(total)}** |"
            w(row)
        w("")

    # Top 10 subset (BONUS)
    qualifiers = determine_qualifiers(athletes, groups, events, n_per_group=2)
    subset_events = derive_subset_placements(qualifiers, events)
    subset_results = compute_all_systems(qualifiers, subset_events)

    w("## Top 10 Subset Control (Qualifiers Re-Ranked)")
    w("")
    w(f"The top 2 per group ({len(qualifiers)} athletes — qualifiers under WSM Linear) re-ranked within their subset on each event. Mirrors WSM's official 'Prelim Score' carryover when WSM Linear is applied.")
    w("")
    w("**Subset placements per event:**")
    w("")
    w("| # | Athlete | Country | Group | " + " | ".join(subset_events.keys()) + " |")
    w("|---|---------|---------|-------|" + "|".join("-------" for _ in subset_events) + "|")
    subset_wsm = subset_results["WSM Linear"].sorted_totals
    for rank, (a, _) in enumerate(subset_wsm, 1):
        row = f"| {rank} | {a} | {countries[a]} | G{groups[a]} |"
        for ev in subset_events:
            row += f" {get_placement_display(subset_events[ev][a])} |"
        w(row)
    w("")

    w("**Top 10 standings under each system:**")
    w("")
    w("| # | Athlete | Country | Group | " + " | ".join(sys_names) + " |")
    w("|---|---------|---------|-------|" + "|".join("-------" for _ in sys_names) + "|")
    for rank, (a, _) in enumerate(subset_wsm, 1):
        row = f"| {rank} | {a} | {countries[a]} | G{groups[a]} |"
        for sn in sys_names:
            total = subset_results[sn].sorted_totals_dict()[a]
            row += f" {fmt(total)} |"
        w(row)
    w("")

    w("**Top 10 winner per system:**")
    w("")
    for sn in sys_names:
        winner_a, winner_pts = subset_results[sn].sorted_totals[0]
        w(f"- **{sn}:** {winner_a} ({fmt(winner_pts)} pts)")
    w("")

    out_path = os.path.join(out_dir, f"{comp_name}_pool.md")
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return out_path, results, subset_results


def write_comp_report(path, out_dir):
    """Generate a markdown report for a single comp."""
    comp_name, athletes, countries, events, groups = load_comp(path)
    event_names = list(events.keys())
    results = compute_all_systems(athletes, events)

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

    # Standings under each system
    w("## Standings Under Each Scoring System")
    w("")
    for system in SCORING_SYSTEMS:
        res = results[system.name]
        ratio = res.scale[0] / res.scale[1] if res.scale[1] > 0 else float('inf')

        w(f"### {system.name}")
        w("")
        w(f"_{system.description}_")
        w("")
        w(f"**Scale:** `{res.scale}` — **1st/2nd ratio:** {ratio:.2f}x")
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
        for rank, (a, total) in enumerate(res.sorted_totals, 1):
            row = f"| {rank} | {a} | {countries[a]} |"
            for ev in event_names:
                row += f" {fmt(res.event_pts[ev][a])} |"
            row += f" **{fmt(total)}** |"
            w(row)
        w("")

    # Podium comparison
    w("## Podium Per System")
    w("")
    w("| System | 1st/2nd ratio | 1st | 2nd | 3rd |")
    w("|--------|---------------|-----|-----|-----|")
    for system in SCORING_SYSTEMS:
        res = results[system.name]
        ratio = res.scale[0] / res.scale[1] if res.scale[1] > 0 else float('inf')
        line = f"| {system.name} | {ratio:.2f}x |"
        for athlete, total in res.sorted_totals[:3]:
            line += f" {athlete} ({fmt(total)}) |"
        w(line)
    w("")

    # Winner-flip analysis
    winners = {sn: results[sn].sorted_totals[0][0] for sn in results}
    unique_winners = set(winners.values())
    w("## Winner Flip Analysis")
    w("")
    if len(unique_winners) > 1:
        w("This comp produces **different winners** under different scoring systems:")
        w("")
        by_winner = defaultdict(list)
        for sn, w_name in winners.items():
            by_winner[w_name].append(sn)
        for winner_name, sys_list in by_winner.items():
            w(f"- **{winner_name}** wins under: {', '.join(sys_list)}")
        w("")
    else:
        w(f"**{next(iter(unique_winners))}** wins under every scoring system tested. No flip.")
        w("")

    out_path = os.path.join(out_dir, f"{comp_name}.md")
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return out_path, results


def run_groups(path):
    """Print groups-as-teams comparison to stdout."""
    comp_name, athletes, countries, events, groups = load_comp(path)
    _require_groups(groups, "groups")
    results = compute_all_systems(athletes, events)
    sys_names = [s.name for s in SCORING_SYSTEMS]
    group_ids = sorted(set(groups.values()))

    print("=" * 110)
    print(f"GROUPS AS TEAMS: {comp_name.upper()}  ({len(athletes)} athletes / {len(group_ids)} groups)")
    print("=" * 110)

    group_totals_by_sys = {}
    for sn in sys_names:
        gt = defaultdict(float)
        for a in athletes:
            gt[groups[a]] += results[sn].sorted_totals_dict()[a]
        group_totals_by_sys[sn] = gt

    print(f"\n  {'Rank':<6}{'Group':<8}", end="")
    for sn in sys_names:
        print(f"{sn[:14]:<16}", end="")
    print()
    print("  " + "-" * (14 + 16 * len(sys_names)))

    ranked = sorted(group_ids, key=lambda g: -group_totals_by_sys["WSM Linear"][g])
    for rank, g in enumerate(ranked, 1):
        print(f"  {rank:<6}G{g:<7}", end="")
        for sn in sys_names:
            print(f"{fmt(group_totals_by_sys[sn][g]):<16}", end="")
        print()

    print(f"\n  Strongest group per system:")
    for sn in sys_names:
        gt = group_totals_by_sys[sn]
        winner_g = max(gt, key=lambda g: gt[g])
        print(f"    {sn}: Group {winner_g} ({fmt(gt[winner_g])} pts)")
    print()


def run_pool(path):
    """Print pooled stack rank + top-10 subset to stdout."""
    comp_name, athletes, countries, events, groups = load_comp(path)
    _require_groups(groups, "pool")
    results = compute_all_systems(athletes, events)
    sys_names = [s.name for s in SCORING_SYSTEMS]

    print("=" * 110)
    print(f"POOLED STACK RANK: {comp_name.upper()}  ({len(athletes)} athletes)")
    print("=" * 110)

    for system in SCORING_SYSTEMS:
        res = results[system.name]
        print(f"\n  {system.name}")
        print(f"  {'#':<4}{'Athlete':<22}{'Grp':<5}{'Pts':<8}")
        print("  " + "-" * 40)
        for rank, (a, total) in enumerate(res.sorted_totals, 1):
            print(f"  {rank:<4}{a:<22}G{groups[a]:<4}{fmt(total):<8}")

    qualifiers = determine_qualifiers(athletes, groups, events, n_per_group=2)
    subset_events = derive_subset_placements(qualifiers, events)
    subset_results = compute_all_systems(qualifiers, subset_events)

    print()
    print("=" * 110)
    print(f"TOP 10 SUBSET CONTROL — {comp_name.upper()}")
    print("=" * 110)
    print("(Top 2 per group re-ranked within subset; matches WSM's official 'Prelim Score' under WSM Linear)")

    print(f"\n  {'#':<4}{'Athlete':<22}{'Grp':<5}", end="")
    for sn in sys_names:
        print(f"{sn[:14]:<16}", end="")
    print()
    print("  " + "-" * (33 + 16 * len(sys_names)))

    subset_wsm = subset_results["WSM Linear"].sorted_totals
    for rank, (a, _) in enumerate(subset_wsm, 1):
        print(f"  {rank:<4}{a:<22}G{groups[a]:<4}", end="")
        for sn in sys_names:
            total = subset_results[sn].sorted_totals_dict()[a]
            print(f"{fmt(total):<16}", end="")
        print()
    print()


def write_combined_report(comps_dir, out_dir):
    """Generate a combined cross-comp summary report."""
    paths = sorted(glob.glob(os.path.join(comps_dir, "*.csv")))
    all_results = []
    for path in paths:
        _, results = write_comp_report(path, out_dir)
        comp_name = os.path.basename(path).replace(".csv", "")
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
    for system in SCORING_SYSTEMS:
        scale_10 = system.get_scale(10)
        ratio = scale_10[0] / scale_10[1] if scale_10[1] > 0 else float('inf')
        scale_str = "-".join(fmt(x) for x in scale_10)
        w(f"| **{system.name}** ({scale_str}) | {system.description} | {ratio:.2f}x |")
    w("")

    # Cross-comp winner table
    w("## Cross-Competition Winners")
    w("")
    sys_names = [s.name for s in SCORING_SYSTEMS]
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
            winner_name, winner_pts = results[sn].sorted_totals[0]
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
            gap = results[sn].sorted_totals[0][1] - results[sn].sorted_totals[1][1]
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
        winners = {results[sn].sorted_totals[0][0] for sn in sys_names}
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
            winner_counts[results[sn].sorted_totals[0][0]] += 1
        w(f"- **{sn}:** " + ", ".join(f"{a} ({n})" for a, n in sorted(winner_counts.items(), key=lambda x: -x[1])))
    w("")

    # Methodological notes
    w("## Methodological Notes")
    w("")
    w("- **Scale length follows the comp's full roster**, including DNS athletes. A comp with 10 athletes uses a 10-position scale, regardless of how many actually competed in any given event. DNS athletes always score 0 but conceptually occupy positions at the bottom of the field.")
    w("- **Tie averaging:** athletes sharing a placement string (e.g. all marked `T2`) split the points for the positions they collectively consume. 3 athletes at T2 → positions 2, 3, 4 → each gets `(scale[1] + scale[2] + scale[3]) / 3`.")
    w("- **Scale truncation in big fields:** systems with short scales (F1 1991-2002 has only 6 positions; F1 2003-2009 has 8) zero-pad in larger fields. In a 16-athlete comp under F1 1991-2002, positions 7-16 all score 0. This means the linear ordering at the tail is lost — useful to know if a comp's mid-pack matters.")
    w("- **Scale truncation in small fields:** systems with long scales (F1 2010+, MotoGP — both 10 positions) get sliced to fit smaller fields. A 9-athlete comp under F1 2010+ uses `[25, 18, 15, 12, 10, 8, 6, 4, 2]` — the last `1` is dropped. This mildly steepens the system.")
    w("- **Event names with markdown-special characters** (pipes `|`, brackets) will break the rendered tables. Use underscores or plain text in CSV column headers.")
    w("- **No-lift / withdrew rules vary across comps.** WSM 2026 treats a `(No lift)` on max events as DNS (0 pts). SMOE 2024 treats no-lifts as competing-but-last. The CSVs here encode whichever interpretation matches the comp's published totals; cross-comp comparison should account for this.")
    w("")

    out_path = os.path.join(out_dir, "_summary.md")
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return out_path


def run_all(comps_dir):
    paths = sorted(glob.glob(os.path.join(comps_dir, "*.csv")))
    all_results = []
    for path in paths:
        all_results.append(run_comp(path, verbose=True))
        print()

    # Cross-comp summary
    print()
    print("=" * 110)
    print("CROSS-COMPETITION WINNER SUMMARY")
    print("=" * 110)

    sys_names = [s.name for s in SCORING_SYSTEMS]
    print(f"\n  {'Comp':<22}", end="")
    for sn in sys_names:
        print(f"{sn[:18]:<20}", end="")
    print()
    print("  " + "-" * (22 + 20 * len(sys_names)))

    for comp_name, results in all_results:
        print(f"  {comp_name:<22}", end="")
        for sn in sys_names:
            winner_name, winner_pts = results[sn].sorted_totals[0]
            print(f"{(winner_name + ' (' + fmt(winner_pts) + ')')[:18]:<20}", end="")
        print()


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="WSM scoring system comparison.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  wsm_compare.py compare comps/wsm2026_finals.csv          # one comp to stdout
  wsm_compare.py compare --all                              # all comps to stdout
  wsm_compare.py compare --report                           # all comps to markdown + summary
  wsm_compare.py compare --report comps/arnold2025.csv      # one comp to markdown
  wsm_compare.py groups comps/wsm2026_groups.csv            # groups-as-teams to stdout
  wsm_compare.py groups --report comps/wsm2026_groups.csv   # groups-as-teams to markdown
  wsm_compare.py pool comps/wsm2026_groups.csv              # pooled + top-10 to stdout
  wsm_compare.py pool --report comps/wsm2026_groups.csv     # pooled + top-10 to markdown
""",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_compare = subparsers.add_parser("compare", help="Apply scoring systems to a single field (any CSV)")
    p_compare.add_argument("csv", nargs="?", help="Path to comp CSV (omit with --all/--report)")
    p_compare.add_argument("--all", action="store_true", help="Process all CSVs in comps/")
    p_compare.add_argument("--report", action="store_true", help="Write markdown reports to reports/")

    p_groups = subparsers.add_parser("groups", help="Compare groups as teams (requires 'group' column)")
    p_groups.add_argument("csv", help="Path to comp CSV with 'group' column")
    p_groups.add_argument("--report", action="store_true", help="Write markdown report to reports/")

    p_pool = subparsers.add_parser("pool", help="Pool all athletes into a single stack rank + top-10 control (requires 'group' column)")
    p_pool.add_argument("csv", help="Path to comp CSV with 'group' column")
    p_pool.add_argument("--report", action="store_true", help="Write markdown report to reports/")

    args = parser.parse_args()

    if args.command == "compare":
        if args.all and args.report:
            summary_path = write_combined_report(COMPS_DIR, REPORTS_DIR)
            print(f"Wrote per-comp reports + {summary_path}")
        elif args.all:
            run_all(COMPS_DIR)
        elif args.report:
            if args.csv:
                out_path, _ = write_comp_report(args.csv, REPORTS_DIR)
                print(f"Wrote {out_path}")
            else:
                summary_path = write_combined_report(COMPS_DIR, REPORTS_DIR)
                print(f"Wrote per-comp reports + {summary_path}")
        elif args.csv:
            run_comp(args.csv)
        else:
            parser.error("compare requires either a CSV path, --all, or --report")
    elif args.command == "groups":
        if args.report:
            out_path, _ = write_groups_report(args.csv, REPORTS_DIR)
            print(f"Wrote {out_path}")
        else:
            run_groups(args.csv)
    elif args.command == "pool":
        if args.report:
            out_path, _, _ = write_pool_report(args.csv, REPORTS_DIR)
            print(f"Wrote {out_path}")
        else:
            run_pool(args.csv)


if __name__ == "__main__":
    main()
