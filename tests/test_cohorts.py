"""Tests for the comparison-cohort machinery in release_stoppers.py.

Covers the parts that let another JetBrains product be measured the same way: the
product-parameterised release calendar, retargetable tag vocabularies, and the
comparison/rendering blocks. No network access — the one HTTP-facing function
(`release_versions.fetch_releases`) is stubbed.

Run with the project venv:
    .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

import io
import os
import sys
import unittest
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import release_stoppers as rs  # noqa: E402
import release_versions as rv  # noqa: E402


def ms(date_str: str) -> int:
    y, m, d = map(int, date_str.split("-"))
    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp() * 1000)


def tag_added(name: str, ts: int) -> dict:
    return {"timestamp": ts, "category": {"id": "TagsCategory"},
            "added": [{"name": name}], "removed": []}


def state_change(frm, to, ts: int) -> dict:
    return {"timestamp": ts, "category": {"id": "CustomFieldCategory"}, "field": {"name": "State"},
            "added": [{"name": to}] if to else [], "removed": [{"name": frm}] if frm else []}


def cohort_row(project: str, index: int, assumed: bool) -> dict:
    """A compute_row()-shaped dict carrying only what the comparison reads."""
    return {"id": f"{project}-{index}", "project": project, "summary": "s",
            "created": "2026-01-01", "tag_added": "2026-01-02" + ("*" if assumed else ""),
            "resolved": "2026-02-01", "days_to_tag": float(index),
            "days_tag_to_resolved": float(index), "days_tag_to_first_fixed": float(index),
            "days_tag_to_release": index, "planned_for": "2026.1",
            "planned_for_date": "2026-03-30", "days_tag_to_release_date": None,
            "available_in": [], "in_planned": False, "first_available": "",
            "state_history": "Open", "removed_while_open": False, "subsystem": "Build",
            "regression": "", "signal": "", "votes": 0, "support_tickets": 0,
            "affected_licenses": 0}


def make_cohort(project: str, n: int, assumed: int = 0) -> list[dict]:
    return [cohort_row(project, i, assumed=i < assumed) for i in range(n)]


# --------------------------------------------------------------------------------------
# Release calendar: product-parameterised, GA takes precedence
# --------------------------------------------------------------------------------------

class TestReleaseCalendarSource(unittest.TestCase):
    """IIU repeats one version string across GA/RC/EAP rows; the GA date must win."""

    # Newest-first, as the data service returns it.
    IIU_LIKE = [
        {"version": "2026.2", "type": "release", "date": "2026-07-16"},
        {"version": "2026.2", "type": "rc", "date": "2026-07-09"},
        {"version": "2026.2", "type": "eap", "date": "2026-05-07"},
        {"version": "2026.3", "type": "eap", "date": "2026-08-19"},
        {"version": "no-date", "type": "release", "date": None},
        {"version": None, "type": "release", "date": "2026-01-01"},
    ]

    def calendar(self, payload):
        original = rv.fetch_releases
        rv.fetch_releases = lambda product_code=rv.PRODUCT_CODE: payload
        try:
            return rv.get_release_calendar("TEST")
        finally:
            rv.fetch_releases = original

    def test_ga_wins_over_rc_and_eap(self):
        self.assertEqual(self.calendar(self.IIU_LIKE)["2026.2"], date(2026, 7, 16))

    def test_ga_wins_even_when_listed_last(self):
        self.assertEqual(self.calendar(list(reversed(self.IIU_LIKE)))["2026.2"],
                         date(2026, 7, 16))

    def test_unshipped_version_keeps_its_prerelease_date(self):
        self.assertEqual(self.calendar(self.IIU_LIKE)["2026.3"], date(2026, 8, 19))

    def test_entries_missing_version_or_date_are_skipped(self):
        calendar = self.calendar(self.IIU_LIKE)
        self.assertNotIn("no-date", calendar)
        self.assertNotIn(None, calendar)


# --------------------------------------------------------------------------------------
# Tag vocabularies
# --------------------------------------------------------------------------------------

class TestTagVocabulary(unittest.TestCase):
    def test_default_matches_the_module_constants(self):
        v = rs.DEFAULT_VOCABULARY
        self.assertEqual(v.measure, tuple(rs.MEASURE_TAGS))
        self.assertEqual(v.fallback, tuple(rs.MEASURE_TAGS_FALLBACK))
        self.assertEqual(v.stopper, frozenset(rs.STOPPER_TAGS))
        self.assertEqual(v.eap, rs.EAP_STOPPER_TAG)

    def test_of_folds_search_tags_into_the_stopper_set(self):
        v = rs.TagVocabulary.of(measure=("a",), fallback=("b",), extra_stopper=("c",))
        self.assertEqual(v.stopper, frozenset({"a", "c"}))
        self.assertIsNone(v.eap)

    def test_custom_vocabulary_retargets_the_parser(self):
        acts = [state_change("Open", "Triaged", ms("2026-01-02")),
                tag_added("blocking-release", ms("2026-01-05")),
                state_change("Triaged", "Fixed", ms("2026-01-09"))]
        parsed = rs.parse_activities(acts, rs.TagVocabulary.of(measure=("blocking-release",)))
        self.assertEqual(parsed["tag_dt"], rs.ms_to_dt(ms("2026-01-05")))
        self.assertTrue(parsed["stopper_tag_added"])
        self.assertIn("Tag added", parsed["state_history"])

    def test_default_vocabulary_ignores_another_products_tags(self):
        acts = [tag_added("blocking-release", ms("2026-01-05"))]
        parsed = rs.parse_activities(acts)
        self.assertIsNone(parsed["tag_dt"])
        self.assertFalse(parsed["stopper_tag_added"])

    def test_vocabulary_without_an_eap_tag_never_flags_eap_only(self):
        acts = [tag_added(rs.EAP_STOPPER_TAG, ms("2026-01-05")),
                tag_added("blocking-release", ms("2026-01-06"))]
        vocab = rs.TagVocabulary.of(measure=("blocking-release",))
        self.assertFalse(rs.parse_activities(acts, vocab)["eap_stopper_added"])
        # The dotnet vocabulary does flag it, which is what drives the EAP-only exclusion.
        self.assertTrue(rs.parse_activities(acts)["eap_stopper_added"])


# --------------------------------------------------------------------------------------
# Comparison cohorts
# --------------------------------------------------------------------------------------

class TestComparisonCohorts(unittest.TestCase):
    def test_query_appends_the_shared_resolved_clause(self):
        cohort = rs.COMPARISON_COHORTS[0]
        query = rs.cohort_issue_query(cohort)
        self.assertTrue(query.startswith(cohort.query))
        self.assertIn(rs.RESOLVED_CLAUSE, query)
        self.assertIn(rs.RESOLVED_DATE_RANGE, query)

    def test_history_only_drops_assumed_tag_dates(self):
        rows = make_cohort("RIDER", 3, assumed=2)
        self.assertEqual([r["id"] for r in rs.history_only(rows)], ["RIDER-2"])

    def test_summary_block_reports_the_assumed_rate_per_cohort(self):
        cohorts = {rs.DOTNET_COHORT_NAME: make_cohort("RIDER", 10, assumed=4),
                   "IJPL+JBR": make_cohort("IJPL", 8, assumed=2)}
        caption, header, data, formats = rs.cohort_summary_block(cohorts)
        self.assertEqual(caption, "Cohorts")
        self.assertEqual(len(header), len(formats))
        by_name = {row[0]: row for row in data}
        self.assertEqual(by_name["dotnet"][1:5], [10, 6, 4, 0.4])
        self.assertEqual(by_name["IJPL+JBR"][1:5], [8, 6, 2, 0.25])
        self.assertEqual(by_name["IJPL+JBR"][5], "IIU")      # measured on its own calendar
        self.assertEqual(by_name["dotnet"][5], rv.PRODUCT_CODE)

    def blocks(self):
        return rs.comparison_blocks({rs.DOTNET_COHORT_NAME: make_cohort("RIDER", 10, assumed=4),
                                     "IJPL+JBR": make_cohort("IJPL", 8, assumed=2)})

    def test_one_block_per_metric_with_a_column_per_cohort_and_basis(self):
        metric_blocks = [b for b in self.blocks() if b[0] and b[0] != "Cohorts"]
        self.assertEqual(len(metric_blocks), len(rs.ROLLUP_METRICS))
        _, header, data, formats = metric_blocks[0]
        self.assertEqual(header, ["Percentile", "dotnet (all rows)",
                                  "dotnet (tag date in history only)", "IJPL+JBR (all rows)",
                                  "IJPL+JBR (tag date in history only)"])
        self.assertEqual(len(formats), len(header))
        self.assertEqual(data[0][0], "Valid N")
        self.assertEqual(data[0][1:], [10, 6, 8, 6])
        self.assertEqual([r[0] for r in data[1:]], [label for label, _ in rs.PERCENTILES])

    def test_reversed_metric_is_flagged_and_both_notes_come_last(self):
        blocks = self.blocks()
        self.assertIn("reversed", [b[0] for b in blocks if b[0]][-1])
        self.assertEqual(blocks[-1][2],
                         [[rs.REVERSED_PERCENTILE_NOTE], [rs.ASSUMED_TAG_NOTE]])

    def test_no_comparison_sheets_without_cohorts(self):
        rows = make_cohort("RIDER", 3)
        self.assertEqual(rs.comparison_sheets(rows, None), [])
        self.assertEqual(rs.comparison_sheets(rows, {}), [])

    def test_cohort_data_is_dumped_as_a_full_issue_table(self):
        sheets = dict(rs.comparison_sheets(make_cohort("RIDER", 3),
                                           {"IJPL+JBR": make_cohort("IJPL", 8)}))
        self.assertEqual(list(sheets), ["Comparison", "IJPL+JBR"])
        _, header, data, formats = sheets["IJPL+JBR"][0]
        self.assertEqual(header, rs.ISSUE_TABLE_HEADER)
        self.assertEqual(len(data), 8)
        self.assertEqual(len(formats), len(header))


# --------------------------------------------------------------------------------------
# Shared block rendering
# --------------------------------------------------------------------------------------

class TestBlockRendering(unittest.TestCase):
    def test_cell_text_formats_by_column_type(self):
        self.assertEqual(rs.cell_text(0.7494, rs.FMT_PCT), "74.9%")
        self.assertEqual(rs.cell_text(1.0, rs.FMT_PCT), "100.0%")
        self.assertEqual(rs.cell_text(9.95, rs.FMT_NUM1), "10.0")
        self.assertEqual(rs.cell_text(439, rs.FMT_INT), "439")
        self.assertEqual(rs.cell_text("2026.1"), "2026.1")   # version strings stay text
        self.assertEqual(rs.cell_text(None), "")
        self.assertEqual(rs.cell_text(""), "")

    def test_sheet_name_strips_characters_excel_rejects(self):
        self.assertEqual(rs.sheet_name("IJPL/JBR"), "IJPL-JBR")
        self.assertEqual(rs.sheet_name("a[b]c:d*e?f"), "a-b-c-d-e-f")
        self.assertEqual(rs.sheet_name("back" + chr(92) + "slash"), "back-slash")
        self.assertEqual(rs.sheet_name("x" * 40), "x" * 31)

    def test_md_blocks_align_columns_and_pad_short_rows(self):
        buf = io.StringIO()
        rs.write_md_blocks(buf, [("Cap", ["A", "N"], [["x", 1.25], ["y"]],
                                 [rs.FMT_TEXT, rs.FMT_NUM1])])
        lines = [l for l in buf.getvalue().splitlines() if l.startswith("|")]
        self.assertEqual(lines[0], "| A | N |")
        self.assertEqual(lines[1], "|---|---:|")
        self.assertEqual(lines[2], "| x | 1.3 |")
        self.assertEqual(lines[3], "| y |  |")      # missing cell padded, not dropped

    def test_md_blocks_render_the_caption_as_a_heading(self):
        buf = io.StringIO()
        rs.write_md_blocks(buf, [("Days to Tag", ["A"], [], [rs.FMT_TEXT])], heading_level=2)
        self.assertIn("## Days to Tag", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
