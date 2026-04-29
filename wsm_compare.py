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
    python3 wsm_compare.py fetch <url_or_id>                       # fetch from Strongman Archives
    python3 wsm_compare.py compare <csv>                            # re-score a comp, stdout
    python3 wsm_compare.py compare --all                            # all comps, stdout
    python3 wsm_compare.py compare --report                         # all comps to markdown + summary
    python3 wsm_compare.py compare --report <csv>                   # one comp to markdown
"""
import csv
import json
import re
import sys
import os
import glob
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from functools import cached_property

from scoring_systems._base import ScoringSystem
from scoring_systems._registry import ALL_SYSTEMS as SCORING_SYSTEMS

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COMPS_DIR = os.path.join(SCRIPT_DIR, "comps")
REPORTS_DIR = os.path.join(SCRIPT_DIR, "reports")

DNS_TOKENS = {"DNS", "WD", "WITHDREW", "DQ", ""}

# --- Strongman Archives fetch helpers (used by `fetch` subcommand) ---

_FETCH_ENDPOINT = "https://strongmanarchives.com/fetchContestResult.php"
_FETCH_HEADER_URL = "https://strongmanarchives.com/viewContest.php?id={cid}"
_FETCH_REQUEST_DELAY_SEC = 1.5
_fetch_last_request_time = [0.0]


def _fetch_throttle():
    elapsed = time.time() - _fetch_last_request_time[0]
    if elapsed < _FETCH_REQUEST_DELAY_SEC:
        time.sleep(_FETCH_REQUEST_DELAY_SEC - elapsed)
    _fetch_last_request_time[0] = time.time()


def fetch_event_names(contest_id):
    """Scrape event names from the contest page header."""
    _fetch_throttle()
    req = urllib.request.Request(
        _FETCH_HEADER_URL.format(cid=contest_id),
        headers={"User-Agent": "Mozilla/5.0 (wsm_compare canonical fetcher)"},
    )
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    m = re.search(rf'<table[^>]*id="ContestResults{contest_id}"[^>]*>(.*?)</table>', html, re.DOTALL)
    if not m:
        raise RuntimeError(f"Couldn't find results table for contest {contest_id}")
    headers = re.findall(r"<th[^>]*>\s*([^<]*?)\s*</th>", m.group(1))
    events = []
    for i, h in enumerate(headers[4:], start=4):
        h = h.strip()
        if h.lower() != "pts":
            events.append(h)
    return events


def fetch_data(contest_id):
    _fetch_throttle()
    body = urllib.parse.urlencode({"contestID": contest_id, "unitDisplay": "Metric"}).encode()
    req = urllib.request.Request(
        _FETCH_ENDPOINT,
        data=body,
        method="POST",
        headers={"User-Agent": "Mozilla/5.0 (wsm_compare canonical fetcher)"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _strip_html(s):
    """Strip HTML tags and decode common entities."""
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&nbsp;", " ").strip()
    return s


def _parse_row(row, n_events):
    """Each row: [#, athlete_html, country_html, total, evt1_result, evt1_pts, ...]."""
    name = _strip_html(row[1])
    country_text = _strip_html(row[2])
    country = country_text.split()[-1] if country_text else ""
    total = float(row[3])
    event_pts = []
    for i in range(n_events):
        result = _strip_html(str(row[4 + 2 * i]))
        pts_raw = row[4 + 2 * i + 1]
        pts = float(pts_raw) if pts_raw not in ("", None, "-") else 0.0
        event_pts.append(pts)
    return name, country, total, event_pts


def _derive_placement(athletes_pts):
    """Given {athlete: canonical_pts}, return {athlete: placement_string}."""
    competing = {a: p for a, p in athletes_pts.items() if p > 0}
    by_pts = defaultdict(list)
    for a, p in competing.items():
        by_pts[p].append(a)

    sorted_groups = sorted(by_pts.items(), key=lambda x: -x[0])

    placements = {}
    cur_pos = 1
    for pts, group in sorted_groups:
        n = len(group)
        if n == 1:
            placements[group[0]] = str(cur_pos)
        else:
            for a in group:
                placements[a] = f"T{cur_pos}"
        cur_pos += n

    for a, p in athletes_pts.items():
        if p == 0:
            placements[a] = "DNS"

    return placements


def parse_contest_id(url_or_id):
    """Accept either a Strongman Archives URL or a bare contest ID, return int.

    Examples:
      'https://strongmanarchives.com/viewContest.php?id=2361' → 2361
      '2361' → 2361
      'foo' → ValueError
    """
    s = str(url_or_id).strip()
    m = re.search(r"id=(\d+)", s)
    if m:
        return int(m.group(1))
    if s.isdigit():
        return int(s)
    raise ValueError(f"Can't extract contest ID from {url_or_id!r} (expected URL with ?id=N or bare integer)")


def _slug_from_title(title):
    """Convert a page title like 'Strongman Archives - 2026 WSM Final' into a slug like '2026_wsm_final'."""
    s = title.strip()
    # Strip the known site prefix
    prefix = "Strongman Archives - "
    if s.startswith(prefix):
        s = s[len(prefix):]
    # Lowercase, replace non-alphanumeric runs with single underscores
    s = re.sub(r"[^A-Za-z0-9]+", "_", s.lower())
    return s.strip("_")


def _derive_filename_from_page(contest_id):
    """Derive a filename slug from the contest page title."""
    _fetch_throttle()
    req = urllib.request.Request(
        _FETCH_HEADER_URL.format(cid=contest_id),
        headers={"User-Agent": "Mozilla/5.0 (wsm_compare canonical fetcher)"},
    )
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    m = re.search(r"<title>([^<]+)</title>", html)
    if not m:
        raise RuntimeError(f"Couldn't find <title> for contest {contest_id}")
    return _slug_from_title(m.group(1))


def fetch_csv(contest_id):
    """Fetch a contest from Strongman Archives and return CSV text."""
    events = fetch_event_names(contest_id)
    payload = fetch_data(contest_id)
    rows = payload["data"]

    athletes = []
    countries = {}
    pts_per_event = [{} for _ in events]
    for row in rows:
        name, country, _total, evt_pts = _parse_row(row, len(events))
        athletes.append(name)
        countries[name] = country
        for i, p in enumerate(evt_pts):
            pts_per_event[i][name] = p

    placements_per_event = [_derive_placement(pe) for pe in pts_per_event]

    safe_event_names = [re.sub(r"[^A-Za-z0-9]+", "_", e).strip("_") for e in events]
    lines = ["athlete,country," + ",".join(safe_event_names)]
    for a in athletes:
        row_cells = [a, countries[a]] + [placements_per_event[i][a] for i in range(len(events))]
        lines.append(",".join(row_cells))
    return "\n".join(lines) + "\n"


def get_scale(system, field_size):
    """Convenience: get the scoring scale for a ScoringSystem at a given field size."""
    return system.get_scale(field_size)


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
    """Returns (comp_name, athletes, countries, events) where events maps
    event_name to {athlete: placement_string}.
    """
    if not os.path.isfile(path):
        raise ValueError(f"CSV file not found: {path}")
    with open(path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        raise ValueError(f"Empty CSV: {path}")

    fieldnames = list(rows[0].keys())
    static = {"athlete", "country"}
    event_names = [f for f in fieldnames if f.lower() not in static]

    if not event_names:
        raise ValueError(f"CSV has no event columns: {path} (expected columns beyond 'athlete' and 'country')")

    athletes = [r["athlete"].strip() for r in rows]
    countries = {r["athlete"].strip(): r.get("country", "").strip() for r in rows}

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
    return comp_name, athletes, countries, events


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

    @cached_property
    def totals_dict(self):
        """Cached: totals as {athlete: total_pts}. Built once on first access."""
        return dict(self.sorted_totals)

    # Backwards-compat alias kept for callers that still use the method form.
    def sorted_totals_dict(self):
        return self.totals_dict


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
    comp_name, athletes, countries, events = load_comp(path)
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


def _comp_nav_metadata(comp_name):
    """Return (title, parent, nav_order) for a comp report — used in Jekyll front matter
    so just-the-docs can build the sidebar.

    Returns None if the comp name doesn't match the expected pattern; the report still
    gets written but without sidebar nav metadata.
    """
    is_women = comp_name.endswith("_w")
    base = comp_name[:-2] if is_women else comp_name
    parent = "Women's" if is_women else "Men's"

    m = re.match(r"^([a-z]+)(\d{4})(_finals)?$", base)
    if not m:
        return None
    series_raw, year_str, finals_suffix = m.group(1), m.group(2), m.group(3)

    series_pretty = {"wsm": "WSM", "arnold": "Arnold", "rogue": "Rogue", "smoe": "SMOE"}.get(series_raw)
    series_order = {"wsm": 1, "arnold": 2, "rogue": 3, "smoe": 4}.get(series_raw)
    if series_pretty is None or series_order is None:
        return None

    year = int(year_str)
    title_parts = [series_pretty, year_str]
    if finals_suffix:
        title_parts.append("Finals")
    title = " ".join(title_parts)

    # nav_order: smaller = first. Encode as series_order * 100 + (2030 - year)
    # so within each series the most recent year sorts first.
    nav_order = series_order * 100 + (2030 - year)
    return title, parent, nav_order


def write_comp_report(path, out_dir):
    """Generate a markdown report for a single comp."""
    comp_name, athletes, countries, events = load_comp(path)
    event_names = list(events.keys())
    results = compute_all_systems(athletes, events)

    lines = []
    w = lines.append

    # Jekyll front matter for sidebar nav (just-the-docs)
    nav = _comp_nav_metadata(comp_name)
    if nav is not None:
        title, parent, nav_order = nav
        w("---")
        w(f"title: {title}")
        w(f"parent: {parent}")
        w(f"nav_order: {nav_order}")
        w("---")
        w("")
        w(f"# {title}")
    else:
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

    # Podium comparison — overview before details
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
        header = "| # | Athlete | Country | **Total** |"
        sep = "|---|---------|---------|-----------|"
        for ev in event_names:
            header += f" {ev.replace('_', ' ')} |"
            sep += "----------|"
        w(header)
        w(sep)
        for rank, (a, total) in enumerate(res.sorted_totals, 1):
            row = f"| {rank} | {a} | {countries[a]} | **{fmt(total)}** |"
            for ev in event_names:
                row += f" {fmt(res.event_pts[ev][a])} |"
            w(row)
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
    # Front matter for just-the-docs sidebar
    w("---")
    w("title: Cross-Comp Summary")
    w("nav_order: 2")
    w("---")
    w("")
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
  wsm_compare.py fetch 2361                                         # fetch by ID
  wsm_compare.py fetch https://strongmanarchives.com/viewContest.php?id=2361
  wsm_compare.py fetch 2361 --name wsm2026_finals                   # override filename
  wsm_compare.py compare comps/wsm2026_finals.csv                   # one comp to stdout
  wsm_compare.py compare --all                                      # all comps to stdout
  wsm_compare.py compare --report                                   # generate all markdown reports
""",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_fetch = subparsers.add_parser("fetch", help="Fetch a contest from Strongman Archives and write a CSV to comps/")
    p_fetch.add_argument("url_or_id", help="Strongman Archives URL or bare contest ID (e.g., 2361)")
    p_fetch.add_argument("--name", help="Override the auto-derived output filename (without .csv extension)")

    p_compare = subparsers.add_parser("compare", help="Apply scoring systems to a single field (any CSV)")
    p_compare.add_argument("csv", nargs="?", help="Path to comp CSV (omit with --all/--report)")
    p_compare.add_argument("--all", action="store_true", help="Process all CSVs in comps/")
    p_compare.add_argument("--report", action="store_true", help="Write markdown reports to reports/")

    args = parser.parse_args()

    if args.command == "fetch":
        contest_id = parse_contest_id(args.url_or_id)
        csv_text = fetch_csv(contest_id)
        if args.name:
            name = args.name
        else:
            name = _derive_filename_from_page(contest_id)
        out_path = os.path.join(COMPS_DIR, f"{name}.csv")
        if os.path.exists(out_path):
            raise ValueError(f"Refusing to overwrite {out_path}; rename or delete it first.")
        with open(out_path, "w") as f:
            f.write(csv_text)
        n_athletes = len(csv_text.strip().split("\n")) - 1
        n_events = len(csv_text.split("\n")[0].split(",")) - 2
        print(f"Wrote {out_path} ({n_athletes} athletes, {n_events} events)")
        return

    elif args.command == "compare":
        # B1: --all is exclusive with a positional CSV
        if args.all and args.csv:
            parser.error("compare: cannot combine --all with a CSV path; pick one")
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


if __name__ == "__main__":
    # B2: surface ValueError as a clean stderr message instead of a traceback
    try:
        main()
    except ValueError as e:
        sys.stderr.write(f"error: {e}\n")
        sys.exit(2)
