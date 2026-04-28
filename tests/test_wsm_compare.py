"""Tests for wsm_compare.py.

Run from project root with:
    python3 -m unittest discover tests
"""
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

# Make wsm_compare importable when running tests from project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import wsm_compare as wc


# Pull scoring system entries by name so tests don't depend on list order.
def _system(name):
    return next(s for s in wc.SCORING_SYSTEMS if s.name == name)


WSM_LINEAR = _system("WSM Linear")
F1_2010 = _system("F1 2010-present")
F1_2003 = _system("F1 2003-2009")


class ParsePlacementTests(unittest.TestCase):
    """parse_placement converts placement strings to (position, is_dns)."""

    def test_simple_numbers(self):
        cases = [
            ("1", (1, False)),
            ("2", (2, False)),
            ("10", (10, False)),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(wc.parse_placement(raw), expected)

    def test_tied_placements(self):
        self.assertEqual(wc.parse_placement("T2"), (2, False))
        self.assertEqual(wc.parse_placement("T15"), (15, False))

    def test_dns_variants(self):
        for raw in ("DNS", "WD", "WITHDREW", "DQ", ""):
            with self.subTest(raw=raw):
                self.assertEqual(
                    wc.parse_placement(raw),
                    (None, True),
                    f"{raw!r} should be treated as DNS",
                )

    def test_whitespace_handling(self):
        self.assertEqual(wc.parse_placement(" 1 "), (1, False))
        self.assertEqual(wc.parse_placement(" T3 "), (3, False))
        self.assertEqual(wc.parse_placement("  DNS  "), (None, True))

    def test_malformed_raises(self):
        for raw in ("Tabc", "1.5", "foo", "T", "1a", "abc"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    wc.parse_placement(raw)

    def test_zero_or_negative_raises(self):
        for raw in ("0", "-1", "T0", "T-3"):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    wc.parse_placement(raw)


class GetScaleTests(unittest.TestCase):
    """get_scale slices/pads the scoring scale to the given field size."""

    def test_wsm_linear_field_10(self):
        self.assertEqual(
            wc.get_scale(WSM_LINEAR, 10),
            [10, 9, 8, 7, 6, 5, 4, 3, 2, 1],
        )

    def test_wsm_linear_field_16(self):
        self.assertEqual(
            wc.get_scale(WSM_LINEAR, 16),
            list(range(16, 0, -1)),
        )

    def test_f1_2010_field_10(self):
        self.assertEqual(
            wc.get_scale(F1_2010, 10),
            [25, 18, 15, 12, 10, 8, 6, 4, 2, 1],
        )

    def test_f1_2010_field_5_smaller(self):
        # Smaller field truncates the scale.
        self.assertEqual(
            wc.get_scale(F1_2010, 5),
            [25, 18, 15, 12, 10],
        )

    def test_f1_2003_field_10_padded_with_zeros(self):
        # F1 2003-2009 only scored top 8 — positions 9 and 10 get zero.
        self.assertEqual(
            wc.get_scale(F1_2003, 10),
            [10, 8, 6, 5, 4, 3, 2, 1, 0, 0],
        )


class ComputeEventPointsTests(unittest.TestCase):
    """compute_event_points handles ties via average of consumed positions."""

    def test_no_ties_three_athletes(self):
        scale = [10, 9, 8]
        points = wc.compute_event_points(
            {"A": "1", "B": "2", "C": "3"}, scale,
        )
        self.assertEqual(points, {"A": 10, "B": 9, "C": 8})

    def test_two_way_tie_at_t2(self):
        # A and B share T2. They consume positions 2 and 3 (0-indexed: 1, 2).
        # Each gets avg(scale[1], scale[2]) = avg(9, 8) = 8.5.
        scale = [10, 9, 8, 7]
        points = wc.compute_event_points(
            {"W": "1", "A": "T2", "B": "T2", "D": "4"}, scale,
        )
        self.assertEqual(points["W"], 10)
        self.assertEqual(points["A"], 8.5)
        self.assertEqual(points["B"], 8.5)
        self.assertEqual(points["D"], 7)

    def test_three_way_tie_at_t2(self):
        # A, B, C all T2; D at position 5 (next slot after the 3-way tie).
        # T2 athletes consume positions 2,3,4 → avg(9,8,7) = 8.
        # D consumes position 5 → scale[4] = 6.
        scale = [10, 9, 8, 7, 6]
        points = wc.compute_event_points(
            {"W": "1", "A": "T2", "B": "T2", "C": "T2", "D": "5"}, scale,
        )
        self.assertEqual(points["W"], 10)
        self.assertEqual(points["A"], 8)
        self.assertEqual(points["B"], 8)
        self.assertEqual(points["C"], 8)
        self.assertEqual(points["D"], 6)

    def test_six_way_tie_at_t2_with_ten_pt_scale(self):
        # Six athletes tied at T2 consume positions 2..7 → avg(9,8,7,6,5,4) = 6.5.
        scale = list(range(10, 0, -1))  # [10,9,8,7,6,5,4,3,2,1]
        placements = {"W": "1"}
        for name in ("A", "B", "C", "D", "E", "F"):
            placements[name] = "T2"
        placements["L"] = "8"
        placements["M"] = "9"
        placements["N"] = "10"
        points = wc.compute_event_points(placements, scale)
        self.assertEqual(points["W"], 10)
        for name in ("A", "B", "C", "D", "E", "F"):
            self.assertEqual(points[name], 6.5, f"{name} tied at T2 should get 6.5")
        self.assertEqual(points["L"], 3)  # scale[7]
        self.assertEqual(points["M"], 2)  # scale[8]
        self.assertEqual(points["N"], 1)  # scale[9]

    def test_all_dns(self):
        scale = [10, 9, 8]
        points = wc.compute_event_points(
            {"A": "DNS", "B": "DNS", "C": "DNS"}, scale,
        )
        self.assertEqual(points, {"A": 0, "B": 0, "C": 0})

    def test_mixed_dns_and_competing(self):
        # DNS athletes get 0; competing athletes start consuming scale from position 0.
        scale = [10, 9, 8, 7, 6]
        points = wc.compute_event_points(
            {"A": "1", "B": "2", "C": "DNS", "D": "3", "E": "DNS"},
            scale,
        )
        self.assertEqual(points["A"], 10)
        self.assertEqual(points["B"], 9)
        self.assertEqual(points["D"], 8)
        self.assertEqual(points["C"], 0)
        self.assertEqual(points["E"], 0)


class CountWinsAndTop3Tests(unittest.TestCase):
    """count_wins_and_top3 counts 1st-place finishes and top-3 finishes."""

    def test_basic(self):
        events = {
            "E1": {"A": "1", "B": "2", "C": "3"},
            "E2": {"A": "2", "B": "1", "C": "3"},
            "E3": {"A": "1", "B": "4", "C": "5"},
        }
        wins_a, top3_a = wc.count_wins_and_top3(events, "A")
        self.assertEqual((wins_a, top3_a), (2, 3))
        wins_b, top3_b = wc.count_wins_and_top3(events, "B")
        self.assertEqual((wins_b, top3_b), (1, 2))
        wins_c, top3_c = wc.count_wins_and_top3(events, "C")
        self.assertEqual((wins_c, top3_c), (0, 2))

    def test_ties_count_as_wins_and_top3(self):
        # T1 still parses as position 1, T3 still parses as position 3 (top3).
        events = {
            "E1": {"A": "T1", "B": "T1"},
            "E2": {"A": "T3", "B": "1"},
        }
        wins_a, top3_a = wc.count_wins_and_top3(events, "A")
        self.assertEqual((wins_a, top3_a), (1, 2))

    def test_dns_ignored(self):
        events = {
            "E1": {"A": "DNS"},
            "E2": {"A": "1"},
        }
        wins, top3 = wc.count_wins_and_top3(events, "A")
        self.assertEqual((wins, top3), (1, 1))


class LoadCompTests(unittest.TestCase):
    """load_comp parses a comp CSV into athletes/countries/events."""

    def _write_csv(self, content):
        """Write CSV content to a temp file, return path. Cleaned up in tearDown."""
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8",
        )
        f.write(content)
        f.close()
        self._tmp_files.append(f.name)
        return f.name

    def setUp(self):
        self._tmp_files = []

    def tearDown(self):
        for p in self._tmp_files:
            try:
                os.unlink(p)
            except OSError:
                pass

    def test_basic_parse(self):
        path = self._write_csv(textwrap.dedent("""\
            athlete,country,Event1,Event2
            Alice,USA,1,T2
            Bob,CAN,T2,1
            Charlie,GBR,DNS,3
        """))
        comp_name, athletes, countries, events, _ = wc.load_comp(path)
        self.assertEqual(athletes, ["Alice", "Bob", "Charlie"])
        self.assertEqual(countries, {"Alice": "USA", "Bob": "CAN", "Charlie": "GBR"})
        self.assertEqual(list(events.keys()), ["Event1", "Event2"])
        self.assertEqual(events["Event1"], {"Alice": "1", "Bob": "T2", "Charlie": "DNS"})
        self.assertEqual(events["Event2"], {"Alice": "T2", "Bob": "1", "Charlie": "3"})
        # comp_name is the basename without .csv
        self.assertTrue(comp_name)
        self.assertFalse(comp_name.endswith(".csv"))

    def test_two_athletes_one_event(self):
        path = self._write_csv(textwrap.dedent("""\
            athlete,country,OnlyEvent
            Alice,USA,1
            Bob,CAN,2
        """))
        _, athletes, _, events, _ = wc.load_comp(path)
        self.assertEqual(athletes, ["Alice", "Bob"])
        self.assertEqual(len(events), 1)
        self.assertEqual(events["OnlyEvent"], {"Alice": "1", "Bob": "2"})

    def test_all_dns_in_one_event(self):
        path = self._write_csv(textwrap.dedent("""\
            athlete,country,E1,E2
            Alice,USA,1,DNS
            Bob,CAN,2,DNS
            Charlie,GBR,3,DNS
        """))
        _, athletes, _, events, _ = wc.load_comp(path)
        # compute_event_points returns dict with all athletes at 0.
        scale = wc.get_scale(WSM_LINEAR, 3)
        pts = wc.compute_event_points(events["E2"], scale)
        self.assertEqual(pts, {"Alice": 0, "Bob": 0, "Charlie": 0})

    def test_non_ascii_names(self):
        # Fojtů and Björnsson must round-trip cleanly.
        path = self._write_csv(textwrap.dedent("""\
            athlete,country,E1
            O. Fojtů,CZE,1
            H. Björnsson,ISL,2
        """))
        _, athletes, countries, events, _ = wc.load_comp(path)
        self.assertIn("O. Fojtů", athletes)
        self.assertIn("H. Björnsson", athletes)
        self.assertEqual(countries["O. Fojtů"], "CZE")
        self.assertEqual(countries["H. Björnsson"], "ISL")
        self.assertEqual(events["E1"]["H. Björnsson"], "2")

    def test_empty_csv_raises(self):
        # CSV with only the header row → no data rows → ValueError.
        path = self._write_csv("athlete,country,E1\n")
        with self.assertRaises(ValueError):
            wc.load_comp(path)

    def test_no_event_columns_raises(self):
        # CSV with athlete,country only (no event columns) → ValueError.
        path = self._write_csv(textwrap.dedent("""\
            athlete,country
            Alice,USA
            Bob,CAN
        """))
        with self.assertRaisesRegex(ValueError, "no event columns"):
            wc.load_comp(path)

    def test_malformed_placement_raises_with_context(self):
        # Malformed cell → ValueError that names the athlete and event.
        path = self._write_csv(textwrap.dedent("""\
            athlete,country,Deadlift,Squat
            Alice,USA,1,T2
            Bob,CAN,2,Tabc
        """))
        with self.assertRaisesRegex(ValueError, "Bob.*Squat"):
            wc.load_comp(path)


class IntegrationTests(unittest.TestCase):
    """End-to-end checks against the actual comp CSVs in comps/.

    Validates that totals under WSM Linear match the official competition results.
    """

    @classmethod
    def setUpClass(cls):
        cls.comps_dir = os.path.join(PROJECT_ROOT, "comps")

    def _totals(self, csv_name, system_entry):
        """Compute {athlete: total_points} for a given CSV under a scoring system."""
        path = os.path.join(self.comps_dir, csv_name)
        _, athletes, _, events, _ = wc.load_comp(path)
        scale = wc.get_scale(system_entry, len(athletes))
        totals = {a: 0.0 for a in athletes}
        for ev_placements in events.values():
            pts = wc.compute_event_points(ev_placements, scale)
            for a in athletes:
                totals[a] += pts[a]
        return totals, events, scale

    def test_wsm2026_hooper_total_wsm_linear(self):
        totals, _, _ = self._totals("wsm2026_finals.csv", WSM_LINEAR)
        self.assertEqual(totals["M. Hooper"], 54, "Hooper WSM Linear total should be 54")

    def test_wsm2026_nel_total_wsm_linear(self):
        totals, _, _ = self._totals("wsm2026_finals.csv", WSM_LINEAR)
        self.assertEqual(totals["R. Nel"], 52, "Nel WSM Linear total should be 52")

    def test_wsm2026_hooper_max_log_event(self):
        # Hooper is T2 in Max Log alongside Fojtů, scale [10,9,...] → avg(9,8) = 8.5.
        _, events, scale = self._totals("wsm2026_finals.csv", WSM_LINEAR)
        max_log = wc.compute_event_points(events["Max_Log"], scale)
        self.assertEqual(max_log["M. Hooper"], 8.5)
        self.assertEqual(max_log["O. Fojtů"], 8.5)

    def test_arnold2025_top3_totals_wsm_linear(self):
        totals, _, _ = self._totals("arnold2025.csv", WSM_LINEAR)
        self.assertEqual(totals["M. Hooper"], 51.5, "Hooper Arnold 2025 total should be 51.5")
        self.assertEqual(totals["L. Hatton"], 49, "Hatton Arnold 2025 total should be 49")
        self.assertEqual(totals["H. Björnsson"], 42.5, "Björnsson Arnold 2025 total should be 42.5")


class GroupModeTests(unittest.TestCase):
    """Group-stage CSV handling: load_comp groups dict, qualifiers, subset re-ranking."""

    @classmethod
    def setUpClass(cls):
        cls.path = os.path.join(PROJECT_ROOT, "comps", "wsm2026_prelim.csv")

    def test_load_comp_returns_groups_dict(self):
        _, athletes, _, _, groups = wc.load_comp(self.path)
        self.assertIsNotNone(groups, "groups dict should be populated when 'group' column present")
        self.assertEqual(groups["M. Hooper"], "3")
        self.assertEqual(groups["R. Nel"], "1")
        self.assertEqual(len(set(groups.values())), 5)

    def test_load_comp_groups_none_when_absent(self):
        _, _, _, _, groups = wc.load_comp(os.path.join(PROJECT_ROOT, "comps", "wsm2026_finals.csv"))
        self.assertIsNone(groups)

    def test_determine_qualifiers_picks_top_2_per_group(self):
        _, athletes, _, events, groups = wc.load_comp(self.path)
        qualifiers = wc.determine_qualifiers(athletes, groups, events, n_per_group=2)
        self.assertEqual(len(qualifiers), 10)
        # Each group represented exactly twice
        from collections import Counter
        counts = Counter(groups[a] for a in qualifiers)
        self.assertEqual(set(counts.values()), {2})
        # Top contenders should be in there
        self.assertIn("M. Hooper", qualifiers)
        self.assertIn("R. Nel", qualifiers)
        self.assertIn("A. Andrade", qualifiers)
        self.assertIn("O. Fojtů", qualifiers)

    def test_top10_subset_matches_official_prelim_carryover(self):
        """Top 10 re-ranked under WSM Linear should match WSM 2026 official prelim totals."""
        _, athletes, _, events, groups = wc.load_comp(self.path)
        qualifiers = wc.determine_qualifiers(athletes, groups, events, n_per_group=2)
        subset_events = wc.derive_subset_placements(qualifiers, events)
        subset_results = wc.compute_all_systems(qualifiers, subset_events)
        wsm_totals = subset_results["WSM Linear"].sorted_totals_dict()
        # Official WSM 2026 prelim scores from Strongman Archives
        self.assertEqual(wsm_totals["M. Hooper"], 37)
        self.assertEqual(wsm_totals["R. Nel"], 34)
        self.assertEqual(wsm_totals["A. Andrade"], 31)
        self.assertEqual(wsm_totals["E. Williams"], 29)
        self.assertEqual(wsm_totals["O. Fojtů"], 27)
        self.assertEqual(wsm_totals["P. Kordiyaka"], 26.5)
        self.assertEqual(wsm_totals["M. Licis"], 25.5)
        self.assertEqual(wsm_totals["T. Mitchell"], 25.5)
        self.assertEqual(wsm_totals["M. Ragg"], 20.5)

    def test_groups_mode_rejects_non_group_csv(self):
        path = os.path.join(PROJECT_ROOT, "comps", "wsm2026_finals.csv")
        with self.assertRaisesRegex(ValueError, "groups mode requires"):
            wc.write_groups_report(path, tempfile.mkdtemp())

    def test_pool_mode_rejects_non_group_csv(self):
        path = os.path.join(PROJECT_ROOT, "comps", "wsm2026_finals.csv")
        with self.assertRaisesRegex(ValueError, "pool mode requires"):
            wc.write_pool_report(path, tempfile.mkdtemp())


class RerankPlacementsTests(unittest.TestCase):
    """_rerank_placements: derive within-subset placements from global ones."""

    def test_empty(self):
        self.assertEqual(wc._rerank_placements({}), {})

    def test_single_athlete(self):
        self.assertEqual(wc._rerank_placements({"A": "5"}), {"A": "1"})

    def test_distinct_globals_become_ranks(self):
        # Globals 3, 7, 12 → subset ranks 1, 2, 3
        result = wc._rerank_placements({"A": "12", "B": "3", "C": "7"})
        self.assertEqual(result, {"B": "1", "C": "2", "A": "3"})

    def test_tied_globals_stay_tied(self):
        # Two athletes globally T2 → both T1 within subset
        result = wc._rerank_placements({"A": "T2", "B": "T2", "C": "9"})
        self.assertEqual(result["A"], "T1")
        self.assertEqual(result["B"], "T1")
        self.assertEqual(result["C"], "3")  # 2 tied athletes consume positions 1+2, so C is 3rd

    def test_all_tied(self):
        result = wc._rerank_placements({"A": "T5", "B": "T5", "C": "T5"})
        for v in result.values():
            self.assertEqual(v, "T1")

    def test_dns_pass_through(self):
        result = wc._rerank_placements({"A": "1", "B": "DNS", "C": "5"})
        self.assertEqual(result["A"], "1")
        self.assertEqual(result["B"], "DNS")
        self.assertEqual(result["C"], "2")


class DeriveSubsetPlacementsTests(unittest.TestCase):
    """derive_subset_placements: re-rank a subset across all events."""

    def test_basic(self):
        events = {
            "E1": {"A": "1", "B": "T2", "C": "T2", "D": "5"},
            "E2": {"A": "DNS", "B": "1", "C": "3", "D": "2"},
        }
        # Subset of A, B, C
        result = wc.derive_subset_placements(["A", "B", "C"], events)
        # E1: A=1, B=T2, C=T2 → A=1, B=T2, C=T2 (D excluded)
        self.assertEqual(result["E1"]["A"], "1")
        self.assertEqual(result["E1"]["B"], "T2")
        self.assertEqual(result["E1"]["C"], "T2")
        # E2: A=DNS, B=1, C=3 → A=DNS, B=1, C=2
        self.assertEqual(result["E2"]["A"], "DNS")
        self.assertEqual(result["E2"]["B"], "1")
        self.assertEqual(result["E2"]["C"], "2")


class ReportFileTests(unittest.TestCase):
    """Positive tests: write_*_report actually creates files with expected content."""

    @classmethod
    def setUpClass(cls):
        cls.prelim = os.path.join(PROJECT_ROOT, "comps", "wsm2026_prelim.csv")
        cls.finals = os.path.join(PROJECT_ROOT, "comps", "wsm2026_finals.csv")

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_compare_report_creates_file(self):
        out_path, _ = wc.write_comp_report(self.finals, self.tmp)
        self.assertTrue(os.path.isfile(out_path))
        with open(out_path) as f:
            content = f.read()
        self.assertIn("WSM Linear", content)
        self.assertIn("M. Hooper", content)
        self.assertIn("Winner Flip Analysis", content)

    def test_groups_report_creates_file_with_known_total(self):
        out_path, _ = wc.write_groups_report(self.prelim, self.tmp)
        self.assertTrue(out_path.endswith("_groups.md"))
        self.assertTrue(os.path.isfile(out_path))
        with open(out_path) as f:
            content = f.read()
        self.assertIn("## Group Standings", content)
        self.assertIn("401.5", content, "Group 3 total under WSM Linear should be 401.5")

    def test_pool_report_creates_file_with_top10_subset(self):
        out_path, _, _ = wc.write_pool_report(self.prelim, self.tmp)
        self.assertTrue(out_path.endswith("_pool.md"))
        with open(out_path) as f:
            content = f.read()
        self.assertIn("Pooled Standings", content)
        self.assertIn("Top 10 Subset Control", content)
        # Hooper's WSM Linear top-10 total should be 37 (the official prelim score)
        self.assertIn("37", content)


class CLITests(unittest.TestCase):
    """End-to-end CLI tests via subprocess. Catches argparse bugs that unit tests miss."""

    SCRIPT = os.path.join(PROJECT_ROOT, "wsm_compare.py")

    def _run(self, *args, expect_success=False):
        result = subprocess.run(
            [sys.executable, self.SCRIPT, *args],
            capture_output=True, text=True,
        )
        if expect_success:
            self.assertEqual(result.returncode, 0, f"expected success, got: {result.stderr}")
        return result

    def test_help_lists_subcommands(self):
        result = self._run("--help", expect_success=True)
        for sub in ("compare", "groups", "pool"):
            self.assertIn(sub, result.stdout)

    def test_no_subcommand_errors(self):
        result = self._run()
        self.assertNotEqual(result.returncode, 0)

    def test_compare_no_args_errors_helpfully(self):
        result = self._run("compare")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("compare requires", result.stderr.lower() + result.stdout.lower() + result.stderr)

    def test_compare_all_with_csv_rejected(self):
        # B1: --all + CSV should be rejected, not silently ignored
        result = self._run("compare", "--all", os.path.join(PROJECT_ROOT, "comps", "wsm2026_finals.csv"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot combine --all", result.stderr)

    def test_missing_csv_clean_error(self):
        # B2: missing CSV should give a clean stderr message, not a Python traceback
        result = self._run("compare", "/tmp/does_not_exist_xyz.csv")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("CSV file not found", result.stderr)

    def test_groups_on_non_group_csv_clean_error(self):
        result = self._run("groups", os.path.join(PROJECT_ROOT, "comps", "wsm2026_finals.csv"))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("groups mode requires", result.stderr)

    def test_pool_on_non_group_csv_clean_error(self):
        result = self._run("pool", os.path.join(PROJECT_ROOT, "comps", "wsm2026_finals.csv"))
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("pool mode requires", result.stderr)

    def test_invalid_subcommand(self):
        result = self._run("invalidmode")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid choice", result.stderr)


class QualifierOrderTests(unittest.TestCase):
    """determine_qualifiers returns athletes in deterministic group order."""

    def test_qualifiers_grouped_by_group_id(self):
        path = os.path.join(PROJECT_ROOT, "comps", "wsm2026_prelim.csv")
        _, athletes, _, events, groups = wc.load_comp(path)
        qualifiers = wc.determine_qualifiers(athletes, groups, events, n_per_group=2)
        # Adjacent qualifiers should share the same group (top-2 pairs together)
        for i in range(0, len(qualifiers), 2):
            self.assertEqual(
                groups[qualifiers[i]], groups[qualifiers[i + 1]],
                f"Pair at index {i} should be from same group",
            )
        # Group order should be natural-sorted (1, 2, 3, 4, 5)
        group_order = [groups[qualifiers[i]] for i in range(0, len(qualifiers), 2)]
        self.assertEqual(group_order, sorted(group_order, key=wc._natural_group_key))


class ScoringSystemsPackageTests(unittest.TestCase):
    """Verify the scoring_systems package structure works."""

    def test_init_has_no_code(self):
        """Project rule: scoring_systems/__init__.py contains only docstring."""
        init_path = os.path.join(PROJECT_ROOT, "scoring_systems", "__init__.py")
        with open(init_path) as f:
            content = f.read()
        # Strip the module docstring; what's left should be empty/whitespace.
        import ast
        tree = ast.parse(content)
        non_doc_nodes = [n for n in tree.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
        self.assertEqual(non_doc_nodes, [], "scoring_systems/__init__.py should contain no code beyond a docstring")

    def test_registry_exposes_all_systems(self):
        from scoring_systems._registry import ALL_SYSTEMS
        names = [s.name for s in ALL_SYSTEMS]
        # Locked-in names — order matches display order in reports
        self.assertIn("WSM Linear", names)
        self.assertIn("F1 2010-present", names)
        self.assertIn("MotoGP", names)
        self.assertIn("MotoGP Extended", names)

    def test_by_name_lookup(self):
        from scoring_systems._registry import by_name
        self.assertEqual(by_name("WSM Linear").name, "WSM Linear")
        with self.assertRaises(ValueError):
            by_name("Nonexistent System")

    def test_each_system_module_exports_SYSTEM(self):
        """Every <name>.py in scoring_systems/ (excluding _-prefixed) exports a `SYSTEM` constant."""
        import importlib
        ss_dir = os.path.join(PROJECT_ROOT, "scoring_systems")
        for fn in os.listdir(ss_dir):
            if fn.endswith(".py") and not fn.startswith("_"):
                mod_name = "scoring_systems." + fn[:-3]
                with self.subTest(module=mod_name):
                    mod = importlib.import_module(mod_name)
                    self.assertTrue(hasattr(mod, "SYSTEM"), f"{mod_name} must export a SYSTEM constant")
                    from scoring_systems._base import ScoringSystem
                    self.assertIsInstance(mod.SYSTEM, ScoringSystem)


if __name__ == "__main__":
    unittest.main()
