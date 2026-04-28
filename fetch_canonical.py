#!/usr/bin/env python3
"""Fetch canonical contest results from Strongman Archives and emit CSV.

Usage:
    python3 fetch_canonical.py <contest_id>

Fetches https://strongmanarchives.com/fetchContestResult.php for the given ID,
derives global per-event placements from the canonical points, and prints a
CSV in the format wsm_compare expects (athlete,country,Event1,Event2,...).

Athletes with 0 pts in an event are treated as DNS.
"""
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict


ENDPOINT = "https://strongmanarchives.com/fetchContestResult.php"
HEADER_URL = "https://strongmanarchives.com/viewContest.php?id={cid}"

# Rate limit — be a polite citizen on a small community-run site.
REQUEST_DELAY_SEC = 1.5
_last_request_time = [0.0]


def _throttle():
    elapsed = time.time() - _last_request_time[0]
    if elapsed < REQUEST_DELAY_SEC:
        time.sleep(REQUEST_DELAY_SEC - elapsed)
    _last_request_time[0] = time.time()


def fetch_event_names(contest_id):
    """Scrape event names from the contest page header (the JSON only gives points)."""
    _throttle()
    req = urllib.request.Request(
        HEADER_URL.format(cid=contest_id),
        headers={"User-Agent": "Mozilla/5.0 (wsm_compare canonical fetcher)"},
    )
    with urllib.request.urlopen(req) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    m = re.search(rf'<table[^>]*id="ContestResults{contest_id}"[^>]*>(.*?)</table>', html, re.DOTALL)
    if not m:
        raise RuntimeError(f"Couldn't find results table for contest {contest_id}")
    headers = re.findall(r"<th[^>]*>\s*([^<]*?)\s*</th>", m.group(1))
    # First 4 are #, Competitor, Country, TOT.PTS. Then alternating Event/Pts.
    static = {h.strip().rstrip("&nbsp;").strip() for h in headers[:4]}
    events = []
    for i, h in enumerate(headers[4:], start=4):
        h = h.strip()
        if h.lower() != "pts":
            events.append(h)
    return events


def fetch_data(contest_id):
    _throttle()
    body = urllib.parse.urlencode({"contestID": contest_id, "unitDisplay": "Metric"}).encode()
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        method="POST",
        headers={"User-Agent": "Mozilla/5.0 (wsm_compare canonical fetcher)"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def strip_html(s):
    """Strip HTML tags and decode common entities. Returns plain text."""
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&nbsp;", " ").strip()
    return s


def parse_row(row, n_events):
    """Each row: [#, athlete_html, country_html, total, evt1_result, evt1_pts, evt2_result, evt2_pts, ...]."""
    rank = strip_html(str(row[0]))
    name = strip_html(row[1])
    country_text = strip_html(row[2])
    # country_text looks like "CAN" after stripping the flag tag
    country = country_text.split()[-1] if country_text else ""
    total = float(row[3])
    event_pts = []
    for i in range(n_events):
        result = strip_html(str(row[4 + 2 * i]))
        pts_raw = row[4 + 2 * i + 1]
        pts = float(pts_raw) if pts_raw not in ("", None, "-") else 0.0
        event_pts.append(pts)
    return name, country, total, event_pts


def derive_placement(athletes_pts):
    """Given {athlete: canonical_pts}, return {athlete: placement_string}.

    Athletes with 0 pts → 'DNS'. Athletes with the same pts are tied (T-prefix).
    """
    # Group by pts value (ignoring 0)
    competing = {a: p for a, p in athletes_pts.items() if p > 0}
    by_pts = defaultdict(list)
    for a, p in competing.items():
        by_pts[p].append(a)

    # Sort groups by pts descending (highest pts = best placement)
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

    # DNS for athletes with 0 pts
    for a, p in athletes_pts.items():
        if p == 0:
            placements[a] = "DNS"

    return placements


def fetch_csv(contest_id):
    events = fetch_event_names(contest_id)
    payload = fetch_data(contest_id)
    rows = payload["data"]

    athletes = []
    countries = {}
    pts_per_event = [{} for _ in events]
    for row in rows:
        name, country, _total, evt_pts = parse_row(row, len(events))
        athletes.append(name)
        countries[name] = country
        for i, p in enumerate(evt_pts):
            pts_per_event[i][name] = p

    # Derive placements per event
    placements_per_event = [derive_placement(pe) for pe in pts_per_event]

    # Build CSV
    safe_event_names = [re.sub(r"[^A-Za-z0-9]+", "_", e).strip("_") for e in events]
    lines = ["athlete,country," + ",".join(safe_event_names)]
    for a in athletes:
        row_cells = [a, countries[a]] + [placements_per_event[i][a] for i in range(len(events))]
        lines.append(",".join(row_cells))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        sys.exit(1)
    print(fetch_csv(int(sys.argv[1])), end="")
