"""Tests for wsm_compare.py.

Run from project root with:
    python3 -m unittest discover tests
"""
import json
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
        comp_name, athletes, countries, events = wc.load_comp(path)
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
        _, athletes, _, events = wc.load_comp(path)
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
        _, athletes, _, events = wc.load_comp(path)
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
        _, athletes, countries, events = wc.load_comp(path)
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
        _, athletes, _, events = wc.load_comp(path)
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
        max_log = wc.compute_event_points(events["Max_Log_Lift"], scale)
        self.assertEqual(max_log["M. Hooper"], 8.5)
        self.assertEqual(max_log["O. Fojtů"], 8.5)

    def test_arnold2025_top3_totals_wsm_linear(self):
        totals, _, _ = self._totals("arnold2025.csv", WSM_LINEAR)
        self.assertEqual(totals["M. Hooper"], 51.5, "Hooper Arnold 2025 total should be 51.5")
        self.assertEqual(totals["L. Hatton"], 49, "Hatton Arnold 2025 total should be 49")
        self.assertEqual(totals["H. Björnsson"], 42.5, "Björnsson Arnold 2025 total should be 42.5")

    def test_all_comps_wsm_linear_winner_pinned(self):
        """Pins the WSM Linear winner+points for every CSV in comps/.

        If a refactor changes any of these, the test fails. To update intentionally,
        edit the EXPECTED dict below.
        """
        EXPECTED = {
            "arnold2024":         ("M. Hooper", 52),
            "arnold2024_w":       ("A. Jardine", 45),
            "arnold2025":         ("M. Hooper", 51.5),
            "arnold2025_w":       ("I. Carrasquillo", 60.5),
            "arnold2026":         ("M. Hooper", 36),
            "arnold2026_w":       ("O. Liashchuk", 50.5),
            "rogue2024":          ("M. Hooper", 54),
            "rogue2024_w":        ("I. Carrasquillo", 53),
            "rogue2025":          ("M. Hooper", 46),
            "rogue2025_w":        ("I. Carrasquillo", 50),
            "smoe2024":           ("M. Hooper", 117),
            "smoe2025":           ("E. Singleton", 93.5),
            "wsm2025_finals":     ("R. Nel", 47),
            "wsm2026_finals":     ("M. Hooper", 54),
        }
        for comp_name, (expected_winner, expected_pts) in EXPECTED.items():
            with self.subTest(comp=comp_name):
                totals, _, _ = self._totals(f"{comp_name}.csv", WSM_LINEAR)
                sorted_totals = sorted(totals.items(), key=lambda x: -x[1])
                actual_winner, actual_pts = sorted_totals[0]
                self.assertEqual(actual_winner, expected_winner,
                                 f"{comp_name} winner changed")
                self.assertEqual(actual_pts, expected_pts,
                                 f"{comp_name} winner pts changed")


class ReportFileTests(unittest.TestCase):
    """Positive tests: write_*_report actually creates files with expected content."""

    @classmethod
    def setUpClass(cls):
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
        self.assertIn("compare", result.stdout)
        self.assertNotIn("pool", result.stdout)
        self.assertNotIn("groups", result.stdout)

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

    def test_invalid_subcommand(self):
        result = self._run("invalidmode")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid choice", result.stderr)


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


class FilenameDerivationTests(unittest.TestCase):
    """Test the slug-derivation logic that turns page titles into CSV names."""

    def test_basic_title(self):
        # "2026 WSM Final" → "2026_wsm_final"
        self.assertEqual(wc._slug_from_title("Strongman Archives - 2026 WSM Final"),
                         "2026_wsm_final")

    def test_drops_known_prefix(self):
        # The "Strongman Archives - " prefix is stripped
        self.assertEqual(wc._slug_from_title("Strongman Archives - 2024 SMOE"),
                         "2024_smoe")

    def test_handles_no_prefix(self):
        # Title without prefix still slugifies
        self.assertEqual(wc._slug_from_title("Some Random Title"),
                         "some_random_title")

    def test_collapses_non_alphanumeric(self):
        # Periods, dashes, slashes etc become single underscores
        self.assertEqual(wc._slug_from_title("2025  Arnold-Strongman/Classic"),
                         "2025_arnold_strongman_classic")

    def test_strips_leading_trailing_underscores(self):
        # Leading/trailing underscores from edge characters get stripped
        self.assertEqual(wc._slug_from_title("- 2024 -"),
                         "2024")


class ParseContestIdTests(unittest.TestCase):
    """Test contest ID extraction from URL or bare integer."""

    def test_full_url(self):
        url = "https://strongmanarchives.com/viewContest.php?id=2361"
        self.assertEqual(wc.parse_contest_id(url), 2361)

    def test_partial_url(self):
        url = "viewContest.php?id=1462"
        self.assertEqual(wc.parse_contest_id(url), 1462)

    def test_bare_integer_string(self):
        self.assertEqual(wc.parse_contest_id("2361"), 2361)

    def test_int_passthrough(self):
        self.assertEqual(wc.parse_contest_id(2361), 2361)

    def test_invalid_input_raises(self):
        with self.assertRaisesRegex(ValueError, "Can't extract contest ID"):
            wc.parse_contest_id("not_a_url")


class FetchCsvMockedTests(unittest.TestCase):
    """End-to-end test of fetch_csv with mocked HTTP responses."""

    def test_fetch_csv_produces_expected_format(self):
        # Mock HTML for fetch_event_names (contains the headers table)
        mock_html = """<html><body>
        <table id="ContestResults1234">
        <thead>
        <tr>
          <th>#</th>
          <th>Competitor</th>
          <th>Country</th>
          <th>TOT. PTS</th>
          <th>Event A</th><th>Pts</th>
          <th>Event B</th><th>Pts</th>
        </tr>
        </thead>
        </table>
        </body></html>"""

        # Mock JSON for fetch_data (athletes + per-event canonical points)
        mock_json = {
            "data": [
                ["1", '<a>A. Athlete</a>', '<a><img>USA</a>', "5", "result1", 3, "result2", 2],
                ["2", '<a>B. Athlete</a>', '<a><img>CAN</a>', "3", "result1", 2, "result2", 1],
                ["3", '<a>C. Athlete</a>', '<a><img>GBR</a>', "0", "result1", 0, "result2", 0],
            ]
        }

        from unittest.mock import patch, MagicMock

        def fake_urlopen(req, *args, **kwargs):
            mock_resp = MagicMock()
            if "viewContest.php" in req.full_url:
                mock_resp.read.return_value = mock_html.encode("utf-8")
            else:
                mock_resp.read.return_value = json.dumps(mock_json).encode("utf-8")
            mock_resp.__enter__ = lambda s: s
            mock_resp.__exit__ = lambda *args: None
            return mock_resp

        with patch("wsm_compare.urllib.request.urlopen", side_effect=fake_urlopen):
            csv_text = wc.fetch_csv(1234)

        lines = csv_text.strip().split("\n")
        self.assertEqual(lines[0], "athlete,country,Event_A,Event_B")
        # A. Athlete has highest pts in both events → 1st in both
        self.assertIn("A. Athlete,USA,1,1", lines[1])
        # B. Athlete is 2nd in both
        self.assertIn("B. Athlete,CAN,2,2", lines[2])
        # C. Athlete has 0 pts → DNS in both
        self.assertIn("C. Athlete,GBR,DNS,DNS", lines[3])


if __name__ == "__main__":
    unittest.main()
