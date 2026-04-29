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
    event_raw = []
    for i in range(n_events):
        result = _strip_html(str(row[4 + 2 * i]))
        pts_raw = row[4 + 2 * i + 1]
        pts = float(pts_raw) if pts_raw not in ("", None, "-") else 0.0
        event_pts.append(pts)
        event_raw.append(result)
    return name, country, total, event_pts, event_raw


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


def _fetch_contest_page_html(contest_id):
    """One throttled GET of the contest's view page; returns the HTML."""
    _fetch_throttle()
    req = urllib.request.Request(
        _FETCH_HEADER_URL.format(cid=contest_id),
        headers={"User-Agent": "Mozilla/5.0 (wsm_compare canonical fetcher)"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _derive_filename_from_page(contest_id):
    """Derive a filename slug from the contest page title."""
    html = _fetch_contest_page_html(contest_id)
    m = re.search(r"<title>([^<]+)</title>", html)
    if not m:
        raise RuntimeError(f"Couldn't find <title> for contest {contest_id}")
    return _slug_from_title(m.group(1))


def discover_wsm_year(final_contest_id):
    """Scrape a WSM Final's view page to find the year and the group IDs.

    Strongman Archives renders the WSM Final page with the final's results table
    plus the group tables embedded below, each preceded by an
    ``<h3>YYYY WSM Group N</h3>`` heading. The final itself is identified by the
    page ``<title>``. This layout is consistent across years, so it works for
    any WSM regardless of how many groups that year used.

    Returns a dict: {"year": "2026", "final_id": 2361, "groups": {1: 2478, …}}.
    Raises RuntimeError if the page doesn't match the expected structure.
    """
    html = _fetch_contest_page_html(final_contest_id)
    title_m = re.search(r"<title>([^<]+)</title>", html)
    if not title_m:
        raise RuntimeError(f"contest {final_contest_id}: no <title>")
    title = title_m.group(1)
    year_m = re.search(r"\b(19|20)\d{2}\b", title)
    if not year_m or "WSM" not in title.upper() or "FINAL" not in title.upper():
        raise RuntimeError(f"contest {final_contest_id}: <title>={title!r} doesn't look like a WSM Final page")
    year = re.search(r"\b((?:19|20)\d{2})\b", title).group(1)

    # All <table id="ContestResultsN"> tags in document order.
    table_ids = re.findall(r'<table\s+id="ContestResults(\d+)"', html)
    if not table_ids:
        raise RuntimeError(f"contest {final_contest_id}: no ContestResults tables on page")
    if int(table_ids[0]) != int(final_contest_id):
        raise RuntimeError(f"contest {final_contest_id}: first table id is {table_ids[0]}, expected the final")

    # Group headings in document order.
    group_headings = re.findall(
        rf'<h3[^>]*>\s*{year}\s+WSM\s+Group\s+(\d+)\s*</h3>', html, re.IGNORECASE)
    if len(group_headings) != len(table_ids) - 1:
        raise RuntimeError(
            f"contest {final_contest_id}: found {len(group_headings)} group headings "
            f"but {len(table_ids) - 1} group tables — page layout may have changed")

    groups = {int(num): int(tid) for num, tid in zip(group_headings, table_ids[1:])}
    return {"year": year, "final_id": int(final_contest_id), "groups": groups}


def _save_contest_csvs(contest_id, name, comps_dir):
    """Fetch a contest once and write both the placement CSV and the raw CSV.
    Skips writing if the file already exists. Returns (placement_path, raw_path)."""
    placement_path = os.path.join(comps_dir, f"{name}.csv")
    raw_path = os.path.join(comps_dir, "raw", f"{name}.csv")
    if os.path.exists(placement_path) and os.path.exists(raw_path):
        return placement_path, raw_path, False  # already cached

    events, athletes, countries, pts_per_event, raw_per_event = fetch_contest_payload(contest_id)
    safe_events = _safe_event_names(events)

    placements_per_event = [_derive_placement(pe) for pe in pts_per_event]
    placement_lines = ["athlete,country," + ",".join(safe_events)]
    for a in athletes:
        placement_lines.append(",".join([a, countries[a]] +
                                        [placements_per_event[i][a] for i in range(len(events))]))
    with open(placement_path, "w") as f:
        f.write("\n".join(placement_lines) + "\n")

    os.makedirs(os.path.dirname(raw_path), exist_ok=True)
    raw_lines = ["athlete,country," + ",".join(safe_events)]
    for a in athletes:
        raw_lines.append(",".join([a, countries[a]] +
                                  [raw_per_event[i][a].replace(",", " ") for i in range(len(events))]))
    with open(raw_path, "w") as f:
        f.write("\n".join(raw_lines) + "\n")
    return placement_path, raw_path, True


def _update_contest_ids_manifest(comps_dir, entries):
    """Append/update entries in comps/contest_ids.csv, deduplicating by slug.

    entries: list of (slug, contest_id). Existing slugs are overwritten with
    the new contest_id. The output stays sorted by slug.
    """
    manifest_path = os.path.join(comps_dir, "contest_ids.csv")
    existing = {}
    if os.path.exists(manifest_path):
        with open(manifest_path) as f:
            for row in csv.DictReader(f):
                existing[row["slug"]] = row["contest_id"]
    for slug, cid in entries:
        existing[slug] = str(cid)
    with open(manifest_path, "w") as f:
        f.write("slug,contest_id\n")
        for slug in sorted(existing):
            f.write(f"{slug},{existing[slug]}\n")


def fetch_contest_payload(contest_id):
    """One HTTP round-trip; return event names + parsed rows.

    Returns (events, athletes, countries, pts_per_event, raw_per_event) where:
      events            : [event_name, ...]
      athletes          : [athlete_name, ...] in the order returned by SA
      countries         : {athlete: country}
      pts_per_event     : [{athlete: pts}, ...] aligned with events
      raw_per_event     : [{athlete: raw_str}, ...] aligned with events — the
                          original "9 in 37.06 s" / "13 reps" / "(No lift)" text
    """
    events = fetch_event_names(contest_id)
    rows = fetch_data(contest_id)["data"]

    athletes = []
    countries = {}
    pts_per_event = [{} for _ in events]
    raw_per_event = [{} for _ in events]
    for row in rows:
        name, country, _total, evt_pts, evt_raw = _parse_row(row, len(events))
        athletes.append(name)
        countries[name] = country
        for i, (p, r) in enumerate(zip(evt_pts, evt_raw)):
            pts_per_event[i][name] = p
            raw_per_event[i][name] = r
    return events, athletes, countries, pts_per_event, raw_per_event


def _safe_event_names(events):
    return [re.sub(r"[^A-Za-z0-9]+", "_", e).strip("_") for e in events]


def fetch_csv(contest_id):
    """Fetch a contest from Strongman Archives and return CSV text (placements)."""
    events, athletes, countries, pts_per_event, _ = fetch_contest_payload(contest_id)
    placements_per_event = [_derive_placement(pe) for pe in pts_per_event]

    lines = ["athlete,country," + ",".join(_safe_event_names(events))]
    for a in athletes:
        row_cells = [a, countries[a]] + [placements_per_event[i][a] for i in range(len(events))]
        lines.append(",".join(row_cells))
    return "\n".join(lines) + "\n"


def fetch_raw_csv(contest_id):
    """Fetch a contest and return CSV text with raw event values (e.g. '9 in 37.06 s')."""
    events, athletes, countries, _, raw_per_event = fetch_contest_payload(contest_id)
    lines = ["athlete,country," + ",".join(_safe_event_names(events))]
    for a in athletes:
        row_cells = [a, countries[a]] + [raw_per_event[i][a].replace(",", " ") for i in range(len(events))]
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


# IOC 3-letter country codes (the format Strongman Archives uses) → ISO 3166-1
# alpha-2 codes used to build flag emoji via regional indicator characters.
# Extend this when a new country shows up in the dataset.
_IOC_TO_ISO2 = {
    "AUS": "AU", "CAN": "CA", "CZE": "CZ", "EST": "EE", "GBR": "GB",
    "GHA": "GH", "IRL": "IE", "ISL": "IS", "ITA": "IT", "LAT": "LV",
    "MEX": "MX", "NED": "NL", "NZL": "NZ", "POL": "PL", "PUR": "PR",
    "RSA": "ZA", "UKR": "UA", "USA": "US",
}


def _country_with_flag(country):
    """'CAN' → '🇨🇦 CAN'. Returns the bare code if no mapping is known so the
    table still renders sensibly when a new country shows up.
    """
    iso2 = _IOC_TO_ISO2.get(country)
    if not iso2 or len(iso2) != 2:
        return country
    flag = "".join(chr(0x1F1E6 + (ord(ch) - ord("A"))) for ch in iso2)
    return f"{flag} {country}"


def _pretty_comp_name(comp_name):
    """Display name for a comp slug ('arnold2026_w' → 'Arnold 2026 W'). Falls
    back to a readable form of the slug if the name doesn't match the pattern.
    """
    nav = _comp_nav_metadata(comp_name)
    if nav:
        return nav[0]
    return comp_name.replace("_", " ").title()


def _comp_nav_metadata(comp_name):
    """Return (title, parent, nav_order) for a comp report — used in Jekyll front matter
    so just-the-docs can build the sidebar.

    All comp reports live under one parent ("Scoring systems") in a flat list,
    sorted: WSM finals → Arnolds → Rogues → SMOEs; within a series, newest year
    first; within a year, men's first then women's.

    Returns None if the comp name doesn't match the expected pattern; the report still
    gets written but without sidebar nav metadata.
    """
    is_women = comp_name.endswith("_w")
    base = comp_name[:-2] if is_women else comp_name

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
    if is_women:
        title_parts.append("W")
    title = " ".join(title_parts)

    # Sort key: series block (×100), year recency (×10), then men/women.
    nav_order = series_order * 100 + (2030 - year) * 10 + (5 if is_women else 0)
    return title, "Scoring systems", nav_order


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
        row = f"| {a} | {_country_with_flag(countries[a])} |"
        for ev in event_names:
            row += f" {get_placement_display(events[ev][a])} |"
        wins, top3 = count_wins_and_top3(events, a)
        row += f" {wins} | {top3} |"
        w(row)
    w("{: .sortable }")
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
            row = f"| {rank} | {a} | {_country_with_flag(countries[a])} | **{fmt(total)}** |"
            for ev in event_names:
                row += f" {fmt(res.event_pts[ev][a])} |"
            w(row)
        w("{: .sortable }")
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


_WSM_GROUP_RE = re.compile(r"^wsm(\d{4})_g(\d+)$")


def _group_color(group_num, total_groups):
    """Light pastel hex color for group_num (1-indexed) with hues evenly spaced
    around the wheel by total_groups. Same group_num/total_groups → same color
    on every table so the two tables on a page stay visually consistent.
    """
    h = ((group_num - 1) * 360.0 / total_groups) % 360
    s, lightness = 0.70, 0.88
    c = (1 - abs(2 * lightness - 1)) * s
    x = c * (1 - abs((h / 60.0) % 2 - 1))
    m = lightness - c / 2
    if h < 60:    r1, g1, b1 = c, x, 0
    elif h < 120: r1, g1, b1 = x, c, 0
    elif h < 180: r1, g1, b1 = 0, c, x
    elif h < 240: r1, g1, b1 = 0, x, c
    elif h < 300: r1, g1, b1 = x, 0, c
    else:         r1, g1, b1 = c, 0, x
    r, g, b = int((r1 + m) * 255), int((g1 + m) * 255), int((b1 + m) * 255)
    return f"#{r:02x}{g:02x}{b:02x}"


def parse_raw_result(s):
    """Parse a Strongman Archives raw result string into a comparison key.

    Returns a tuple where higher → better placement, or None for DNS / withdrew /
    unparseable. Within one event, all athletes' keys must share the same shape
    so tuple comparison is meaningful (true for every WSM event format we've
    seen — count+time/distance share a 3-tuple, reps-only share a 1-tuple, etc.).

    Recognized formats (covers WSM 2025-2026; extend here for older events):
      "X in T s"   (count + time)        →  (X, 0,  -T)
      "X + D m"    (count + partial m)   →  (X, D,   0)
      "D m"        (distance only)       →  (0, D,   0)
      "X reps"                           →  (X,)
      "T s"        (time only, lower=better) → (-T,)
      "W kg"       (weight only)         →  (W,)
      "(Withdrew)" / "(No lift)" / ""    → None  (DNS-equivalent)
    """
    s = s.strip()
    if not s or (s.startswith("(") and s.endswith(")")):
        return None
    m = re.match(r"^(\d+)\s+in\s+([\d.]+)\s*s$", s)
    if m:
        return (int(m.group(1)), 0.0, -float(m.group(2)))
    m = re.match(r"^(\d+)\s*\+\s*([\d.]+)\s*m$", s)
    if m:
        return (int(m.group(1)), float(m.group(2)), 0.0)
    m = re.match(r"^(\d+)\s+reps?$", s)  # "X reps" or "1 rep"
    if m:
        return (int(m.group(1)),)
    m = re.match(r"^(\d+)\s+stones?$", s)  # "X stones" or "1 stone"
    if m:
        return (int(m.group(1)),)
    m = re.match(r"^([\d.]+)\s*s$", s)
    if m:
        return (-float(m.group(1)),)
    m = re.match(r"^([\d.]+)\s*m$", s)
    if m:
        return (0, float(m.group(1)), 0.0)
    m = re.match(r"^([\d.]+)\s*kg$", s)
    if m:
        return (float(m.group(1)),)
    return None


def _placements_from_keys(athlete_keys):
    """Convert {athlete: comparison_key_or_None} into {athlete: placement_str}.

    None → "DNS". Equal keys share a placement (T-prefixed).
    """
    keyed = [(a, k) for a, k in athlete_keys.items() if k is not None]
    placements = {a: "DNS" for a, k in athlete_keys.items() if k is None}
    keyed.sort(key=lambda x: x[1], reverse=True)

    cur_pos = 1
    i = 0
    while i < len(keyed):
        j = i
        while j + 1 < len(keyed) and keyed[j + 1][1] == keyed[i][1]:
            j += 1
        n = j - i + 1
        if n == 1:
            placements[keyed[i][0]] = str(cur_pos)
        else:
            for k in range(i, j + 1):
                placements[keyed[k][0]] = f"T{cur_pos}"
        cur_pos += n
        i = j + 1
    return placements


def _load_raw_comp(path):
    """Read a raw-data CSV. Returns (athletes, countries, events_dict)."""
    with open(path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        return [], {}, {}
    event_names = [k for k in rows[0].keys() if k not in ("athlete", "country")]
    athletes = [r["athlete"] for r in rows]
    countries = {r["athlete"]: r["country"] for r in rows}
    events = {ev: {r["athlete"]: r[ev] for r in rows} for ev in event_names}
    return athletes, countries, events


def compute_pooled_groups_standings(year, comps_dir):
    """Pool every group athlete for a WSM year and score them as one virtual
    N-athlete comp under WSM Linear (1st = N pts, last = 1 pt). Group count is
    discovered from the filesystem — older WSMs may have 4 groups, newer ones
    5 or 6. Reads raw event values from comps/raw/wsm{year}_g*.csv. Returns
    None if no raw CSVs are found.
    """
    raw_paths = sorted(
        glob.glob(os.path.join(comps_dir, "raw", f"wsm{year}_g*.csv")),
        key=lambda p: int(re.search(r"_g(\d+)\.csv$", p).group(1)),
    )
    if not raw_paths:
        return None

    all_athletes = []
    countries = {}
    group_of = {}
    event_names = None
    raw_per_event = None
    group_nums = []
    for p in raw_paths:
        g = int(re.search(r"_g(\d+)\.csv$", p).group(1))
        group_nums.append(g)
        ath, ctry, evs = _load_raw_comp(p)
        if event_names is None:
            event_names = list(evs.keys())
            raw_per_event = {ev: {} for ev in event_names}
        elif list(evs.keys()) != event_names:
            raise ValueError(f"WSM {year} group {g} events {list(evs.keys())} don't match {event_names}")
        for a in ath:
            all_athletes.append(a)
            countries[a] = ctry[a]
            group_of[a] = g
            for ev in event_names:
                raw_per_event[ev][a] = evs[ev][a]

    # Per-event pooled placements + WSM-Linear points across the full pooled field.
    n = len(all_athletes)
    scale = list(range(n, 0, -1))  # WSM Linear: N, N-1, ..., 1
    placement_per_event = {}
    pts_per_event = {}
    unparseable_per_event = {}
    for ev in event_names:
        keys = {}
        unparseable = []
        for a in all_athletes:
            raw = (raw_per_event[ev][a] or "").strip()
            k = parse_raw_result(raw)
            keys[a] = k
            # If the raw string isn't empty and isn't a parenthesized DNS marker
            # but still didn't parse, the parser is missing a format — flag it.
            if k is None and raw and not (raw.startswith("(") and raw.endswith(")")):
                unparseable.append((a, raw))
        unparseable_per_event[ev] = unparseable
        placement_per_event[ev] = _placements_from_keys(keys)
        pts_per_event[ev] = compute_event_points(placement_per_event[ev], scale)

    athlete_total = {a: sum(pts_per_event[ev][a] for ev in event_names) for a in all_athletes}
    group_nums_unique = sorted(set(group_nums))
    group_total = {g: sum(athlete_total[a] for a in all_athletes if group_of[a] == g)
                   for g in group_nums_unique}

    return {
        "athletes": all_athletes,
        "countries": countries,
        "group_of": group_of,
        "group_nums": group_nums_unique,
        "event_names": event_names,
        "raw_per_event": raw_per_event,
        "placement_per_event": placement_per_event,
        "pts_per_event": pts_per_event,
        "athlete_total": athlete_total,
        "group_total": group_total,
        "unparseable_per_event": unparseable_per_event,
    }


def write_wsm_groups_report(year, comps_dir, out_dir):
    """Generate the WSM groups-as-teams report for a year.

    Pools all group athletes into one virtual comp, scores under WSM Linear
    using raw event data (times/reps/distances), then sums per group. Renders
    two color-coded tables: group totals (5 rows) and individual standings (25
    rows). Same group → same row color across both tables. Returns the output
    path, or None if raw data is missing.
    """
    pooled = compute_pooled_groups_standings(year, comps_dir)
    if pooled is None:
        return None

    # Warn loudly if any event had unparseable values — earlier years may use
    # event formats this parser doesn't yet recognize.
    for ev, unparseable in pooled["unparseable_per_event"].items():
        for athlete, raw in unparseable:
            print(f"WARNING: WSM {year} {ev}: unparseable result for {athlete!r}: {raw!r}",
                  file=sys.stderr)

    athletes = pooled["athletes"]
    group_of = pooled["group_of"]
    group_nums = pooled["group_nums"]
    event_names = pooled["event_names"]
    raw_per_event = pooled["raw_per_event"]
    placement_per_event = pooled["placement_per_event"]
    pts_per_event = pooled["pts_per_event"]
    athlete_total = pooled["athlete_total"]
    group_total = pooled["group_total"]
    countries = pooled["countries"]
    n_groups = len(group_nums)
    n_athletes = len(athletes)
    color_for = {g: _group_color(g, n_groups) for g in group_nums}

    group_ranking = sorted(group_total.items(), key=lambda x: -x[1])
    athlete_ranking = sorted(athletes, key=lambda a: -athlete_total[a])

    # Roster sizes (informational — old WSMs may have uneven group sizes)
    group_sizes = {g: sum(1 for a in athletes if group_of[a] == g) for g in group_nums}

    lines = []
    w = lines.append

    w("---")
    w(f"title: WSM {year}")
    w("parent: WSM group strength")
    w(f"nav_order: {2030 - int(year)}")
    w("---")
    w("")
    w(f"# WSM {year} — Groups as Teams")
    w("")
    sizes_str = ", ".join(f"Group {g}: {group_sizes[g]}" for g in group_nums)
    w(f"{n_groups} groups, {n_athletes} athletes total ({sizes_str}). All pooled into a "
      f"single virtual {n_athletes}-athlete comp, scored under **WSM Linear** "
      f"(1st = {n_athletes} pts, last = 1 pt) on raw event data — actual times, reps, distances "
      "— *not* within-group placements. Per-group total = sum of its members' points. "
      "This addresses claims that some groups were stacked harder than others.")
    w("")

    w("## Group totals")
    w("")
    w('<table class="rainbow">')
    w("<thead><tr><th>Rank</th><th>Group</th><th>Total points</th></tr></thead>")
    w("<tbody>")
    for rank, (g, total) in enumerate(group_ranking, 1):
        bg = color_for[g]
        w(f'<tr style="background:{bg}"><td>{rank}</td><td><strong>Group {g}</strong></td>'
          f'<td><strong>{fmt(total)}</strong></td></tr>')
    w("</tbody>")
    w("</table>")
    w("")

    w(f"## Individual standings (pooled across all {n_athletes})")
    w("")
    w("Each cell shows the within-pool placement (the points-determining number) "
      "with the raw result underneath. Click any column header to sort by that column "
      "— e.g. click an event name to see who was best at that event.")
    w("")
    w('<table class="rainbow sortable">')
    header = "<tr><th>#</th><th>Athlete</th><th>Group</th><th>Country</th>"
    for ev in event_names:
        header += f"<th>{ev.replace('_', ' ')}</th>"
    header += "<th>Total</th></tr>"
    w("<thead>" + header + "</thead>")
    w("<tbody>")
    for rank, a in enumerate(athlete_ranking, 1):
        g = group_of[a]
        bg = color_for[g]
        cells = [str(rank), a, str(g), _country_with_flag(countries[a])]
        for ev in event_names:
            place = placement_per_event[ev][a]
            raw = raw_per_event[ev][a]
            pts = pts_per_event[ev][a]
            if place == "DNS":
                cells.append(f'<span title="{raw}">DNS (0)</span>')
            else:
                cells.append(f'<strong>{place}</strong> · {raw} <em>({fmt(pts)})</em>')
        cells.append(f"<strong>{fmt(athlete_total[a])}</strong>")
        row = "".join(f"<td>{c}</td>" for c in cells)
        w(f'<tr style="background:{bg}">{row}</tr>')
    w("</tbody>")
    w("</table>")
    w("")

    # Methodology
    w("## How results are ranked across groups")
    w("")
    w("Strongman Archives publishes raw results — `\"9 in 37.06 s\"`, `\"13 reps\"`, "
      "`\"35.03 s\"`, `\"2 + 6.10 m\"`, etc. For each event, every athlete is converted "
      "into a sortable key with the same shape:")
    w("")
    w("- `X in T s` (count + time): rank by count desc, then time asc. More implements first; faster as tiebreaker.")
    w("- `X + D m` (count + partial distance): same primary, then partial distance desc — beats `X in T s` at the same X.")
    w("- `X reps` / `W kg`: rank by the number desc.")
    w("- `T s` alone (time-only events like Truck Pull): rank by time asc.")
    w("- `(Withdrew)` / `(No lift)` / blank: DNS, scores 0.")
    w("")
    w("The pooled 25-athlete placement string is fed into WSM Linear (`[25, 24, …, 1]`), "
      "with tie-averaging where multiple athletes share a key. Sum across 5 events for "
      "the athlete total, then sum athletes per group.")
    w("")

    out_path = os.path.join(out_dir, f"wsm{year}_groups.md")
    os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return out_path


def write_combined_report(comps_dir, out_dir):
    """Generate a combined cross-comp summary report."""
    all_paths = sorted(glob.glob(os.path.join(comps_dir, "*.csv")))
    # contest_ids.csv is the slug→ID manifest, not a comp.
    all_paths = [p for p in all_paths if os.path.basename(p) != "contest_ids.csv"]
    # Group CSVs feed into the WSM-groups report only — don't generate
    # individual reports for them or include them in the cross-comp summary.
    paths = [p for p in all_paths
             if not _WSM_GROUP_RE.match(os.path.basename(p).replace(".csv", ""))]
    all_results = []
    for path in paths:
        _, results = write_comp_report(path, out_dir)
        comp_name = os.path.basename(path).replace(".csv", "")
        all_results.append((comp_name, results))

    # WSM groups-as-teams reports — one per year that has all the group CSVs.
    group_years = sorted({m.group(1) for p in all_paths
                          if (m := _WSM_GROUP_RE.match(os.path.basename(p).replace(".csv", "")))})
    written_group_years = []
    for year in group_years:
        if write_wsm_groups_report(year, comps_dir, out_dir) is not None:
            written_group_years.append(year)

    # Refresh the WSM group strength parent stub. just-the-docs auto-generates
    # a children TOC for any page with `has_children: true`, so the body just
    # needs the section description — the per-year links come from the theme.
    if written_group_years:
        repo_root = os.path.dirname(os.path.abspath(out_dir))
        parent_path = os.path.join(repo_root, "wsm_groups.md")
        parent_lines = [
            "---",
            "title: WSM group strength",
            "nav_order: 3",
            "has_children: true",
            "---",
            "",
            "# WSM groups as teams",
            "",
            "WSM is the only series here that runs groups before the final. "
            "These pages pool every athlete from every group into one virtual comp, "
            "scored under WSM Linear using raw event data (actual times, reps, distances). "
            "Per-group total = sum of its members' points. Addresses claims that some "
            "groups were stacked harder than others.",
            "",
        ]
        with open(parent_path, "w") as f:
            f.write("\n".join(parent_lines))

    lines = []
    w = lines.append
    # Front matter for just-the-docs sidebar
    w("---")
    w("title: Cross-comp details")
    w("parent: Scoring systems")
    w("nav_order: 1")
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
    w("{: .sortable }")
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
        row = f"| **{_pretty_comp_name(comp_name)}** |"
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
        row = f"| **{_pretty_comp_name(comp_name)}** |"
        for sn in sys_names:
            gap = results[sn].sorted_totals[0][1] - results[sn].sorted_totals[1][1]
            row += f" {fmt(gap)} |"
        w(row)
    w("{: .sortable }")
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
        w(f"| **{_pretty_comp_name(comp_name)}** | {len(winners)} | {', '.join(sorted(winners))} |")
    w("{: .sortable }")
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

    out_path = os.path.join(out_dir, "summary.md")
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return out_path


def run_all(comps_dir):
    paths = sorted(glob.glob(os.path.join(comps_dir, "*.csv")))
    paths = [p for p in paths if os.path.basename(p) != "contest_ids.csv"]
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

    p_fetch_year = subparsers.add_parser(
        "fetch-wsm-year",
        help="Given a WSM Final URL or ID, auto-discover the group IDs and fetch the final + every group",
    )
    p_fetch_year.add_argument("url_or_id", help="WSM Final URL or bare contest ID (e.g., 2361 or the 2024 final's id)")

    p_compare = subparsers.add_parser("compare", help="Apply scoring systems to a single field (any CSV)")
    p_compare.add_argument("csv", nargs="?", help="Path to comp CSV (omit with --all/--report)")
    p_compare.add_argument("--all", action="store_true", help="Process all CSVs in comps/")
    p_compare.add_argument("--report", action="store_true", help="Write markdown reports to reports/")

    args = parser.parse_args()

    if args.command == "fetch":
        contest_id = parse_contest_id(args.url_or_id)
        events, athletes, countries, pts_per_event, raw_per_event = fetch_contest_payload(contest_id)
        if args.name:
            name = args.name
        else:
            name = _derive_filename_from_page(contest_id)

        # Placement CSV (the canonical comp file)
        placements_per_event = [_derive_placement(pe) for pe in pts_per_event]
        safe_events = _safe_event_names(events)
        placement_lines = ["athlete,country," + ",".join(safe_events)]
        for a in athletes:
            placement_lines.append(",".join([a, countries[a]] +
                                            [placements_per_event[i][a] for i in range(len(events))]))
        out_path = os.path.join(COMPS_DIR, f"{name}.csv")
        if os.path.exists(out_path):
            raise ValueError(f"Refusing to overwrite {out_path}; rename or delete it first.")
        with open(out_path, "w") as f:
            f.write("\n".join(placement_lines) + "\n")

        # Raw CSV (preserves the original "9 in 37.06 s" / "13 reps" / "(No lift)"
        # text — used for cross-group pooled scoring.)
        raw_dir = os.path.join(COMPS_DIR, "raw")
        os.makedirs(raw_dir, exist_ok=True)
        raw_lines = ["athlete,country," + ",".join(safe_events)]
        for a in athletes:
            raw_lines.append(",".join([a, countries[a]] +
                                      [raw_per_event[i][a].replace(",", " ") for i in range(len(events))]))
        raw_path = os.path.join(raw_dir, f"{name}.csv")
        with open(raw_path, "w") as f:
            f.write("\n".join(raw_lines) + "\n")

        print(f"Wrote {out_path} and {raw_path} ({len(athletes)} athletes, {len(events)} events)")
        return

    elif args.command == "fetch-wsm-year":
        final_id = parse_contest_id(args.url_or_id)
        info = discover_wsm_year(final_id)
        year = info["year"]
        print(f"WSM {year} (final={final_id}): groups {info['groups']}")
        manifest_entries = [(f"wsm{year}_finals", final_id)]
        manifest_entries += [(f"wsm{year}_g{g}", info["groups"][g]) for g in sorted(info["groups"])]
        for slug, cid in manifest_entries:
            _, _, fetched = _save_contest_csvs(cid, slug, COMPS_DIR)
            status = "wrote" if fetched else "cached"
            print(f"  {status} {slug}.csv (cid={cid})")
        _update_contest_ids_manifest(COMPS_DIR, manifest_entries)
        print(f"Updated {os.path.join(COMPS_DIR, 'contest_ids.csv')}")
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
