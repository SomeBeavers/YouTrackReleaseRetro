"""Tests for the latest-major-release slice in release_stoppers.py.

The rolling resolved-date window mixes several release cycles; this slice narrows the report to
one release. Pure — no network, and no dependence on today's date (`today` is injected).

Run with the project venv:
    .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import release_stoppers as rs  # noqa: E402

CALENDAR = {
    "2025.3": date(2025, 11, 11),
    "2026.1": date(2026, 3, 30),
    "2026.1.4": date(2026, 7, 2),     # a patch, never a "major"
    "2026.2": date(2026, 7, 22),
    "2026.3": date(2026, 11, 10),     # not shipped as of the dates used below
}


def focus_row(issue_id, planned, tag_added="2026-07-01", regression="", anomalies=(),
              in_planned=True, first_available="2026.2", project="RIDER"):
    return {"id": issue_id, "project": project, "summary": "s", "planned_for": planned,
            "tag_added": tag_added, "created": "2026-06-01", "resolved": "2026-07-10",
            "days_to_tag": 1.0, "days_tag_to_resolved": 2.0, "days_tag_to_first_fixed": 1.5,
            "days_tag_to_release": 10, "planned_for_date": "2026-07-22", "available_in": [],
            "in_planned": in_planned, "first_available": first_available,
            "state_history": "Open -> Tag added -> Fixed", "removed_while_open": False,
            "removed_while_open_state": "", "end_state": "Fixed", "unclear_states": [],
            "reopened": False, "tag_after_fixed": False, "tag_groups": 1,
            "flow_anomalies": list(anomalies), "subsystem": "Build", "regression": regression,
            "signal": "", "votes": 0, "support_tickets": 0, "affected_licenses": 0}


class TestMajorRelease(unittest.TestCase):
    def test_patch_versions_fold_into_their_major(self):
        self.assertEqual(rs.major_release("2026.2.1"), "2026.2")
        self.assertEqual(rs.major_release("2026.2.0.3"), "2026.2")
        self.assertEqual(rs.major_release("2026.2"), "2026.2")

    def test_non_version_values_have_no_major(self):
        for value in ("Backlog", "No planned for", "", "   ", None, "2026", "next release"):
            with self.subTest(value=value):
                self.assertEqual(rs.major_release(value), "")

    def test_x_placeholder_still_maps_to_its_major(self):
        # "2025.2.X" is a real value in the data; it belongs to the 2025.2 cycle.
        self.assertEqual(rs.major_release("2025.2.X"), "2025.2")


class TestLatestShippedMajor(unittest.TestCase):
    def test_picks_the_newest_release_that_has_shipped(self):
        self.assertEqual(rs.latest_shipped_major(CALENDAR, date(2026, 8, 25)), "2026.2")

    def test_ignores_a_release_that_has_not_shipped_yet(self):
        # A day before 2026.2 GA, the latest shipped major is still 2026.1.
        self.assertEqual(rs.latest_shipped_major(CALENDAR, date(2026, 7, 21)), "2026.1")

    def test_ignores_patch_releases(self):
        # 2026.1.4 shipped 2026-07-02 but is not a major release.
        self.assertEqual(rs.latest_shipped_major(CALENDAR, date(2026, 7, 3)), "2026.1")

    def test_empty_when_nothing_has_shipped(self):
        self.assertEqual(rs.latest_shipped_major(CALENDAR, date(2020, 1, 1)), "")
        self.assertEqual(rs.latest_shipped_major({}, date(2026, 8, 25)), "")


class TestReleaseSlice(unittest.TestCase):
    def rows(self):
        return [focus_row("R-1", "2026.2"), focus_row("R-2", "2026.2.1"),
                focus_row("R-3", "2026.1"), focus_row("R-4", ""), focus_row("R-5", "Backlog")]

    def test_slice_includes_patches_and_excludes_other_cycles(self):
        self.assertEqual([r["id"] for r in rs.release_slice(self.rows(), "2026.2")],
                         ["R-1", "R-2"])

    def test_slice_of_an_absent_release_is_empty(self):
        self.assertEqual(rs.release_slice(self.rows(), "2026.3"), [])

    def test_tag_date_strips_the_assumed_marker(self):
        self.assertEqual(rs.tag_date({"tag_added": "2026-07-01*"}), date(2026, 7, 1))
        self.assertEqual(rs.tag_date({"tag_added": "2026-07-01"}), date(2026, 7, 1))
        self.assertIsNone(rs.tag_date({"tag_added": ""}))


class TestReleaseFocusBlocks(unittest.TestCase):
    GA = date(2026, 7, 22)

    def rows(self):
        return [
            focus_row("R-1", "2026.2", tag_added="2026-07-01"),                    # before GA
            focus_row("R-2", "2026.2", tag_added="2026-07-22"),                    # on GA day
            focus_row("R-3", "2026.2.1", tag_added="2026-08-01",
                      regression=rs.REGRESSION_BY_TAG),                            # after GA
            focus_row("R-4", "2026.2", tag_added="", anomalies=[rs.ANOMALY_REOPENED]),
            focus_row("R-9", "2026.1"),                                            # other cycle
        ]

    def summary(self):
        blocks = rs.release_focus_blocks(self.rows(), "2026.2", self.GA)
        return {row[0]: (row[1], row[2]) for row in blocks[0][2]}

    def test_no_blocks_when_the_release_has_no_tickets(self):
        self.assertEqual(rs.release_focus_blocks(self.rows(), "2026.3", None), [])

    def test_ga_day_counts_as_before_not_after(self):
        summary = self.summary()
        self.assertEqual(summary["Tagged on or before GA"][0], 2)
        self.assertEqual(summary["Tagged after GA"][0], 1)

    def test_unusable_tag_date_is_reported_not_silently_bucketed(self):
        self.assertEqual(self.summary()["No usable tag date"][0], 1)

    def test_ticket_share_is_of_the_whole_cohort_other_shares_are_of_the_slice(self):
        summary = self.summary()
        self.assertEqual(summary["Tickets"], (4, 4 / 5))          # 4 of 5 rows overall
        self.assertEqual(summary["Regressions"], (1, 1 / 4))      # 1 of the 4 in the slice

    def test_unshipped_release_reports_no_ga_date_and_no_split(self):
        rows = [focus_row("R-1", "2026.3", tag_added="2026-08-01")]
        summary = {row[0]: (row[1], row[2])
                   for row in rs.release_focus_blocks(rows, "2026.3", None)[0][2]}
        self.assertEqual(summary["GA date"][0], "not shipped yet")
        self.assertEqual(summary["No usable tag date"][0], 1)     # nothing to compare against

    def test_percentiles_put_the_release_beside_the_whole_cohort(self):
        blocks = rs.release_focus_blocks(self.rows(), "2026.2", self.GA)
        captions = [b[0] for b in blocks]
        self.assertIn("Days to Tag", captions)
        header = next(b[1] for b in blocks if b[0] == "Days to Tag")
        self.assertEqual(header[0], "Percentile")
        self.assertTrue(any(h.startswith("2026.2 (") for h in header))
        self.assertTrue(any(h.startswith(f"{rs.ALL_RELEASES_LABEL} (") for h in header))

    def test_expected_sections_present_and_well_formed(self):
        blocks = rs.release_focus_blocks(self.rows(), "2026.2", self.GA)
        captions = [b[0] for b in blocks]
        for expected in ("2026.2 summary", "Exact Planned for within the release", "By product",
                         "By affected area", "Flow anomalies", "Tickets"):
            self.assertIn(expected, captions)
        for caption, header, data, formats in blocks:
            self.assertEqual(len(header), len(formats), caption)
            for row in data:
                self.assertLessEqual(len(row), len(header), caption)

    def test_ticket_block_lists_only_the_slice(self):
        blocks = rs.release_focus_blocks(self.rows(), "2026.2", self.GA)
        _, header, data, _ = next(b for b in blocks if b[0] == "Tickets")
        self.assertEqual(header, rs.ISSUE_TABLE_HEADER)
        self.assertEqual([row[0] for row in data], ["R-1", "R-2", "R-3", "R-4"])

    def test_exact_planned_breakdown_keeps_ga_and_patch_apart(self):
        blocks = rs.release_focus_blocks(self.rows(), "2026.2", self.GA)
        _, _, data, _ = next(b for b in blocks
                             if b[0] == "Exact Planned for within the release")
        self.assertEqual([(row[0], row[1]) for row in data], [("2026.2", 3), ("2026.2.1", 1)])


class TestReleaseSheets(unittest.TestCase):
    def test_tab_is_named_for_the_release(self):
        rows = [focus_row("R-1", "2026.2")]
        sheets = rs.release_sheets(rows, "2026.2", date(2026, 7, 22))
        self.assertEqual([title for title, _ in sheets], ["Release 2026.2"])

    def test_no_tab_without_a_release_or_without_tickets(self):
        rows = [focus_row("R-1", "2026.2")]
        self.assertEqual(rs.release_sheets(rows, "", None), [])
        self.assertEqual(rs.release_sheets(rows, "2026.3", None), [])


if __name__ == "__main__":
    unittest.main()
