"""Tests for release_stoppers.py logic.

Run with the project venv:
    .venv\\Scripts\\python.exe -m unittest discover -s tests -v
(or `pytest tests/` if pytest is installed — these are plain unittest.TestCase classes).

No network access is needed: the YouTrack-facing functions are split into pure parsers
(`parse_activities`) and a pure row builder (`compute_row`). Tickets are mocked as the
issue dict + raw activity payload that those functions consume, modelled on real issues
with different variations of Project, Planned for, Available in, State History, and
"removed while open".
"""

import os
import sys
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import release_stoppers as rs  # noqa: E402


# --------------------------------------------------------------------------------------
# Fixtures / builders
# --------------------------------------------------------------------------------------

def ms(date_str: str, hour: int = 0, minute: int = 0) -> int:
    """Epoch milliseconds (UTC) for a 'YYYY-MM-DD' date."""
    y, m, d = map(int, date_str.split("-"))
    return int(datetime(y, m, d, hour, minute, tzinfo=timezone.utc).timestamp() * 1000)


def tag_added(name: str, ts: int) -> dict:
    return {"timestamp": ts, "category": {"id": "TagsCategory"},
            "added": [{"name": name}], "removed": []}


def tag_removed(name: str, ts: int) -> dict:
    return {"timestamp": ts, "category": {"id": "TagsCategory"},
            "added": [], "removed": [{"name": name}]}


def state_change(frm, to, ts: int) -> dict:
    return {"timestamp": ts, "category": {"id": "CustomFieldCategory"}, "field": {"name": "State"},
            "added": [{"name": to}] if to else [], "removed": [{"name": frm}] if frm else []}


def field_change(field: str, frm, to, ts: int) -> dict:
    return {"timestamp": ts, "category": {"id": "CustomFieldCategory"}, "field": {"name": field},
            "added": [{"name": to}] if to else [], "removed": [{"name": frm}] if frm else []}


def issue(idr, summary, created, resolved, planned=None, available=None, fix=None,
          subsystem=None, support=None, licenses=None, votes=None, tags=None,
          description=None) -> dict:
    cf = {}
    if planned is not None:
        cf[rs.PLANNED_FOR_FIELD] = {"name": planned}
    if available is not None:
        cf[rs.AVAILABLE_IN_FIELD] = [{"name": v} for v in available]
    if fix is not None:
        cf[rs.FIX_VERSION_FIELDS[0]] = {"name": fix}
    if subsystem is not None:
        cf[rs.SUBSYSTEM_FIELD] = {"name": subsystem}
    if support is not None:
        cf[rs.SUPPORT_TICKETS_FIELD] = support
    if licenses is not None:
        cf[rs.AFFECTED_LICENSES_FIELD] = licenses
    out = {"idReadable": idr, "summary": summary, "created": created, "resolved": resolved,
           "_cf": cf}
    if votes is not None:
        out["votes"] = votes
    if tags is not None:
        out["tags"] = [{"name": t} for t in tags]
    if description is not None:
        out["description"] = description
    return out


# Site release calendar (version -> GA/patch date).
SITE = {
    "2025.1": date(2025, 4, 16),
    "2025.1.3": date(2025, 6, 18),
    "2025.2": date(2025, 8, 14),
    "2026.1": date(2026, 3, 11),
    "2026.1.1": date(2026, 4, 1),
}

# Per-project resolved-state names (subset that matters for these tests).
RESOLVED = {"Fixed", "Verified", "Obsolete", "Duplicate", "Can't Reproduce",
            "As Designed", "Declined", "Won't fix", "Answered"}
RESOLVED_MAP = {p: set(RESOLVED) for p in ("RSRP", "RIDER", "DMRY", "DTRC", "DPA")}
DEFAULT_RESOLVED = set(RESOLVED)


def build_row(issue_dict, acts, is_tagged=False):
    """parse the raw activities then compute the report row, as main() does per issue."""
    act = rs.parse_activities(acts)
    return rs.compute_row(issue_dict, act, SITE, RESOLVED_MAP, DEFAULT_RESOLVED, is_tagged)


# --------------------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------------------

class TestHelpers(unittest.TestCase):
    def test_strip_build_suffix(self):
        self.assertEqual(rs.strip_build_suffix("2025.3 EAP 4 (253.24325.45)"), "2025.3 EAP 4")
        self.assertEqual(rs.strip_build_suffix("2025.1"), "2025.1")
        self.assertEqual(rs.strip_build_suffix(None), "")

    def test_normalize_for_lookup(self):
        self.assertEqual(rs.normalize_for_lookup("Next 2025.1 public build"), "2025.1")
        self.assertEqual(rs.normalize_for_lookup("2025.3 EAP 4"), "2025.3")
        self.assertEqual(rs.normalize_for_lookup("2025.3 RC 1"), "2025.3")
        self.assertEqual(rs.normalize_for_lookup("2025.1.3"), "2025.1.3")  # patch not collapsed

    def test_cf_to_str_and_list(self):
        self.assertEqual(rs.cf_to_str({"name": "2025.1"}), "2025.1")
        self.assertEqual(rs.cf_to_str([{"name": "2025.1"}]), "2025.1")
        self.assertIsNone(rs.cf_to_str(None))
        self.assertEqual(rs.cf_to_list([{"name": "a"}, {"name": "b"}]), ["a", "b"])
        self.assertEqual(rs.cf_to_list(None), [])

    def test_planned_in_available_exact_match(self):
        # Patch release does NOT satisfy a GA "Planned for".
        self.assertFalse(rs.planned_in_available("2026.1", ["2026.1.1"]))
        self.assertTrue(rs.planned_in_available("2026.1", ["2026.1"]))
        self.assertTrue(rs.planned_in_available("2025.1", ["2025.1", "2025.1.3"]))
        self.assertFalse(rs.planned_in_available("2025.1", ["2025.1.3"]))
        self.assertFalse(rs.planned_in_available("", ["2025.1"]))

    def test_value_at_cutoff(self):
        changes = [{"ts": ms("2025-02-01"), "added": "2025.2", "removed": "2025.1"}]
        # cutoff before the change -> value at cutoff is the 'removed' (old) value
        self.assertEqual(rs.value_at_cutoff(changes, ms("2025-01-05"), "2025.2"), "2025.1")
        # cutoff after the change -> current value
        self.assertEqual(rs.value_at_cutoff(changes, ms("2025-03-01"), "2025.2"), "2025.2")

    def test_oldest_available(self):
        got = rs.oldest_available(["2025.2", "2025.1"], SITE)
        self.assertEqual(got[0], "2025.1")
        self.assertEqual(got[1], date(2025, 4, 16))
        self.assertIsNone(rs.oldest_available(["9999.9"], SITE))

    def test_format_in_planned(self):
        self.assertEqual(rs.format_in_planned(True, "2025.1", "2025.1"), "YES")
        self.assertEqual(rs.format_in_planned(False, "2026.1", "2026.1.1"), "NO")
        self.assertEqual(rs.format_in_planned(True, "", "2025.1"), "")   # no planned -> blank
        self.assertEqual(rs.format_in_planned(True, "2025.1", ""), "")   # no first-available -> blank


# --------------------------------------------------------------------------------------
# parse_activities
# --------------------------------------------------------------------------------------

class TestParseActivities(unittest.TestCase):
    def test_measure_tag_sets_tag_dt_and_flags(self):
        acts = [
            state_change("Open", "Triaged", ms("2025-01-02")),
            tag_added(rs.MEASURE_TAGS[0], ms("2025-01-05")),
            state_change("Triaged", "Fixed", ms("2025-01-10")),
            state_change("Fixed", "Verified", ms("2025-01-12")),
        ]
        a = rs.parse_activities(acts)
        self.assertEqual(a["tag_dt"], rs.ms_to_dt(ms("2025-01-05")))
        self.assertTrue(a["stopper_tag_added"])
        self.assertTrue(a["release_stopper_added"])
        self.assertFalse(a["eap_stopper_added"])
        self.assertEqual(a["first_fixed_dt"], rs.ms_to_dt(ms("2025-01-10")))
        self.assertEqual(a["state_history"], "Open -> Triaged -> Tag added -> Fixed -> Verified")

    def test_fallback_tag_sets_tag_dt_not_release(self):
        fallback_tag = rs.MEASURE_TAGS_FALLBACK[0]
        acts = [tag_added(fallback_tag, ms("2025-01-05"))]
        a = rs.parse_activities(acts)
        self.assertEqual(a["tag_dt"], rs.ms_to_dt(ms("2025-01-05")))  # anchored from fallback tag
        self.assertFalse(a["release_stopper_added"])  # not a MEASURE (real release-stopper) tag
        self.assertEqual(a["stopper_tag_added"], fallback_tag in rs.STOPPER_TAGS)

    def test_eap_only(self):
        acts = [tag_added(rs.EAP_STOPPER_TAG, ms("2025-01-05"))]
        a = rs.parse_activities(acts)
        self.assertTrue(a["eap_stopper_added"])
        self.assertFalse(a["release_stopper_added"])
        self.assertFalse(a["stopper_tag_added"])  # rider-eap-stopper is not a STOPPER_TAG
        self.assertIsNone(a["tag_dt"])

    def test_removed_state_captured(self):
        acts = [
            state_change("Open", "Triaged", ms("2025-01-02")),
            tag_added(rs.MEASURE_TAGS[0], ms("2025-01-03")),
            state_change("Triaged", "Obsolete", ms("2025-01-08")),
            tag_removed(rs.MEASURE_TAGS[0], ms("2025-01-09")),
        ]
        a = rs.parse_activities(acts)
        self.assertEqual(a["stopper_removed_states"], ["Obsolete"])


# --------------------------------------------------------------------------------------
# compute_row — mocked tickets with variations
# --------------------------------------------------------------------------------------

class TestComputeRow(unittest.TestCase):
    def assertRow(self, row, **expected):
        for key, val in expected.items():
            self.assertEqual(row[key], val, msg=f"row[{key!r}]")

    def test_planned_matches_available_fixed(self):
        iss = issue("RSRP-1", "x", ms("2025-01-01"), ms("2025-01-20"),
                    planned="2025.1", available=["2025.1 EAP 3 (251.1)", "2025.1"])
        acts = [
            state_change("Open", "Triaged", ms("2025-01-02")),
            tag_added(rs.MEASURE_TAGS[0], ms("2025-01-05")),
            state_change("Triaged", "Fixed", ms("2025-01-10")),
            state_change("Fixed", "Verified", ms("2025-01-12")),
        ]
        row = build_row(iss, acts, is_tagged=True)
        self.assertRow(
            row, project="RSRP", created="2025-01-01", tag_added="2025-01-05",
            resolved="2025-01-20", days_to_tag=4.0, days_tag_to_resolved=15.0,
            days_tag_to_first_fixed=5.0, planned_for="2025.1",
            available_in=["2025.1 EAP 3", "2025.1"], in_planned=True,
            first_available="2025.1", planned_for_date="2025-04-16",
            days_tag_to_release=101, removed_while_open=False,
            state_history="Open -> Triaged -> Tag added -> Fixed -> Verified",
        )

    def test_patch_release_not_in_planned(self):
        iss = issue("RSRP-2", "x", ms("2026-01-01"), ms("2026-02-01"),
                    planned="2026.1", available=["2026.1.1"])
        acts = [
            state_change("Open", "Triaged", ms("2026-01-02")),
            tag_added(rs.MEASURE_TAGS[0], ms("2026-01-05")),
            state_change("Triaged", "Fixed", ms("2026-01-20")),
        ]
        row = build_row(iss, acts, is_tagged=True)
        self.assertRow(row, planned_for="2026.1", first_available="2026.1.1",
                       in_planned=False, planned_for_date="2026-03-11")
        # tri-state display: both present -> explicit NO
        self.assertEqual(rs.format_in_planned(row["in_planned"], row["planned_for"],
                                              row["first_available"]), "NO")

    def test_scan_project_removed_after_resolved_obsolete(self):
        iss = issue("DMRY-3", "x", ms("2026-03-01"), ms("2026-03-13"))
        acts = [
            state_change("Open", "Triaged", ms("2026-03-02")),
            tag_added(rs.MEASURE_TAGS[0], ms("2026-03-05")),
            state_change("Triaged", "Obsolete", ms("2026-03-10")),
            tag_removed(rs.MEASURE_TAGS[0], ms("2026-03-12")),
        ]
        row = build_row(iss, acts, is_tagged=False)  # qualifies via stopper_tag_added
        self.assertRow(
            row, project="DMRY", tag_added="2026-03-05", days_to_tag=4.0,
            days_tag_to_resolved=8.0, days_tag_to_first_fixed=None,
            removed_while_open=False, planned_for="", available_in=[],
            first_available="", planned_for_date="", days_tag_to_release=None,
            state_history="Open -> Triaged -> Tag added -> Obsolete -> Tag removed",
        )

    def test_reopen_removed_while_verified_is_not_open(self):
        iss = issue("RIDER-4", "x", ms("2025-02-01"), ms("2025-03-01"))
        acts = [
            state_change("Open", "Triaged", ms("2025-02-02")),
            tag_added(rs.MEASURE_TAGS[0], ms("2025-02-03")),
            state_change("Triaged", "Fixed", ms("2025-02-05")),
            state_change("Fixed", "Verified", ms("2025-02-06")),
            tag_removed(rs.MEASURE_TAGS[0], ms("2025-02-07")),  # removed while Verified (resolved)
            state_change("Verified", "Reopened", ms("2025-02-10")),
            state_change("Reopened", "Fixed", ms("2025-02-20")),
        ]
        row = build_row(iss, acts, is_tagged=True)
        self.assertFalse(row["removed_while_open"])

    def test_removed_while_unresolved_is_open(self):
        iss = issue("DTRC-5", "x", ms("2025-02-01"), ms("2025-02-20"))
        acts = [
            state_change("Open", "Triaged", ms("2025-02-02")),
            tag_added(rs.MEASURE_TAGS[0], ms("2025-02-03")),
            tag_removed(rs.MEASURE_TAGS[0], ms("2025-02-04")),  # removed while Triaged (unresolved)
            state_change("Triaged", "Fixed", ms("2025-02-10")),
        ]
        row = build_row(iss, acts, is_tagged=False)
        self.assertTrue(row["removed_while_open"])

    def test_eap_only_excluded_even_if_tagged(self):
        iss = issue("RIDER-6", "x", ms("2025-01-01"), ms("2025-01-10"))
        acts = [
            tag_added(rs.EAP_STOPPER_TAG, ms("2025-01-03")),
            state_change("Open", "Fixed", ms("2025-01-05")),
        ]
        self.assertIsNone(build_row(iss, acts, is_tagged=True))
        self.assertIsNone(build_row(iss, acts, is_tagged=False))

    def test_not_a_stopper_excluded(self):
        iss = issue("DPA-7", "x", ms("2025-01-01"), ms("2025-01-10"))
        acts = [state_change("Open", "Fixed", ms("2025-01-05"))]  # no stopper tag ever
        self.assertIsNone(build_row(iss, acts, is_tagged=False))

    def test_assumed_tagged_at_creation(self):
        iss = issue("RSRP-8", "x", ms("2025-01-01"), ms("2025-01-10"))
        acts = [state_change("Open", "Fixed", ms("2025-01-05"))]  # no tag-add activity
        row = build_row(iss, acts, is_tagged=True)  # Path A: qualifies, tag date assumed
        self.assertRow(row, tag_added="2025-01-01*", days_to_tag=0.0,
                       days_tag_to_resolved=9.0, days_tag_to_first_fixed=4.0,
                       state_history="Open -> Fixed")

    def test_planned_from_fix_versions_fallback(self):
        iss = issue("RSRP-9", "x", ms("2025-01-01"), ms("2025-01-15"), fix="2025.2")
        acts = [
            state_change("Open", "Triaged", ms("2025-01-02")),
            tag_added(rs.MEASURE_TAGS[0], ms("2025-01-05")),
            state_change("Triaged", "Fixed", ms("2025-01-10")),
        ]
        row = build_row(iss, acts, is_tagged=True)
        self.assertRow(row, planned_for="2025.2", planned_for_date="2025-08-14",
                       available_in=[], first_available="")
        # planned set but no site-matched first-available -> In Planned blank
        self.assertEqual(rs.format_in_planned(row["in_planned"], row["planned_for"],
                                              row["first_available"]), "")

    def test_planned_reconstructed_at_tag_day_cutoff(self):
        # Current Planned for is 2025.2, but at tag time (Jan 5) it was still 2025.1.
        iss = issue("RSRP-10", "x", ms("2025-01-01"), ms("2025-03-01"),
                    planned="2025.2", available=["2025.1"])
        acts = [
            state_change("Open", "Triaged", ms("2025-01-02")),
            tag_added(rs.MEASURE_TAGS[0], ms("2025-01-05")),
            field_change(rs.PLANNED_FOR_FIELD, "2025.1", "2025.2", ms("2025-02-01")),
            state_change("Triaged", "Fixed", ms("2025-02-10")),
        ]
        row = build_row(iss, acts, is_tagged=True)
        self.assertRow(row, planned_for="2025.1", in_planned=True,
                       first_available="2025.1", planned_for_date="2025-04-16")


class TestReleaseCalendar(unittest.TestCase):
    """A planned date must never override a version that actually shipped."""

    PLANNED = {"2026.2": date(2026, 7, 9), "2026.3": date(2026, 11, 1)}

    def test_shipped_date_beats_the_planned_guess(self):
        # 2026.2 was planned for 9 Jul and shipped 22 Jul; the site date has to win, or every
        # 2026.2 stopper's Days Tag to Release is understated by 13 days.
        site = {"2026.1": date(2026, 3, 30), "2026.2": date(2026, 7, 22)}
        calendar = rs.build_release_calendar(site, self.PLANNED)
        self.assertEqual(calendar["2026.2"], date(2026, 7, 22))

    def test_planned_date_fills_a_gap_for_an_unshipped_version(self):
        calendar = rs.build_release_calendar({"2026.1": date(2026, 3, 30)}, self.PLANNED)
        self.assertEqual(calendar["2026.3"], date(2026, 11, 1))
        self.assertEqual(calendar["2026.2"], date(2026, 7, 9))

    def test_site_entries_are_all_preserved(self):
        site = {"2025.1": date(2025, 4, 16), "2026.2": date(2026, 7, 22)}
        calendar = rs.build_release_calendar(site, self.PLANNED)
        self.assertEqual(calendar["2025.1"], site["2025.1"])
        self.assertEqual(set(calendar), {"2025.1", "2026.2", "2026.3"})

    def test_empty_planned_map_is_a_passthrough(self):
        site = {"2026.2": date(2026, 7, 22)}
        self.assertEqual(rs.build_release_calendar(site, {}), site)


# --------------------------------------------------------------------------------------
# Rollups: percentiles and volumes
# --------------------------------------------------------------------------------------

def rollup_row(project: str, to_tag=0.0, to_resolved=0.0, to_fixed=None,
               to_release=None, planned="", subsystem="", regression="", votes=0,
               support=0, licenses=0, issue_id=None, summary="s") -> dict:
    """Minimal compute_row()-shaped dict — only the fields the rollups read."""
    return {"id": issue_id or f"{project}-1", "project": project, "summary": summary,
            "days_to_tag": to_tag, "days_tag_to_resolved": to_resolved,
            "days_tag_to_first_fixed": to_fixed, "days_tag_to_release": to_release,
            "planned_for": planned, "subsystem": subsystem, "regression": regression,
            "votes": votes, "support_tickets": support, "affected_licenses": licenses,
            "signal": rs.classify_signal(votes, support),
            "created": "2026-01-01", "resolved": "2026-02-01", "available_in": [],
            "removed_while_open": False, "removed_while_open_state": "",
            "end_state": "Verified", "unclear_states": [], "reopened": False,
            "tag_after_fixed": False, "tag_groups": 1, "flow_anomalies": [],
            "state_history": "Open -> Tag added -> Fixed", "in_planned": False,
            "first_available": "", "tag_added": "2026-01-02", "planned_for_date": ""}


class TestPercentileHelpers(unittest.TestCase):
    def test_percentile_inc_interpolates_like_sheets(self):
        vals = [Decimal(str(v)) for v in (1, 2, 3, 4)]
        # rank = p*(n-1): 0.5*3 = 1.5 -> midpoint of 2 and 3
        self.assertEqual(rs.percentile_inc(vals, Decimal("0.5")), Decimal("2.5"))
        self.assertEqual(rs.percentile_inc(vals, Decimal("0.25")), Decimal("1.75"))
        self.assertEqual(rs.percentile_inc(vals, Decimal("0")), Decimal("1"))
        self.assertEqual(rs.percentile_inc(vals, Decimal("1")), Decimal("4"))

    def test_percentile_inc_edge_cases(self):
        self.assertIsNone(rs.percentile_inc([], Decimal("0.5")))
        self.assertEqual(rs.percentile_inc([Decimal("7.5")], Decimal("0.99")), Decimal("7.5"))

    def test_percentile_midpoint_stays_exact(self):
        # Binary floats would land on 201.1499... and round down; Decimal keeps 201.15.
        vals = [Decimal("201.1"), Decimal("201.2")]
        self.assertEqual(rs.fmt_1dp(rs.percentile_inc(vals, Decimal("0.5"))), "201.2")

    def test_fmt_1dp_rounds_halves_up(self):
        self.assertEqual(rs.fmt_1dp(1.85), "1.9")   # Python's format() gives 1.8
        self.assertEqual(rs.fmt_1dp(9.95), "10.0")
        self.assertEqual(rs.fmt_1dp(Decimal("6.25")), "6.3")
        self.assertEqual(rs.fmt_1dp(-64.05), "-64.1")
        self.assertEqual(rs.fmt_1dp(0), "0.0")
        self.assertEqual(rs.fmt_1dp(None), "")

    def test_fmt_share(self):
        self.assertEqual(rs.fmt_share(65, 338), "19.2%")
        self.assertEqual(rs.fmt_share(338, 338), "100.0%")
        self.assertEqual(rs.fmt_share(1, 0), "")


class TestRollups(unittest.TestCase):
    def test_project_columns_ordered_by_volume(self):
        rows = [rollup_row("RSRP")] + [rollup_row("RIDER")] * 3 + [rollup_row("DPA")] * 2
        self.assertEqual(rs.rollup_projects(rows), ["All", "RIDER", "DPA", "RSRP"])

    def test_metric_values_skips_none_and_filters_by_project(self):
        rows = [rollup_row("RIDER", to_fixed=1.0), rollup_row("RIDER", to_fixed=None),
                rollup_row("DPA", to_fixed=3.0)]
        self.assertEqual(rs.metric_values(rows, "days_tag_to_first_fixed", "All"),
                         [Decimal("1.0"), Decimal("3.0")])
        self.assertEqual(rs.metric_values(rows, "days_tag_to_first_fixed", "RIDER"),
                         [Decimal("1.0")])

    def test_metric_values_rounds_to_published_precision(self):
        # Percentiles are computed from the same one-decimal numbers the table prints.
        rows = [rollup_row("RIDER", to_tag=1.24), rollup_row("RIDER", to_tag=1.26)]
        self.assertEqual(rs.metric_values(rows, "days_to_tag", "All"),
                         [Decimal("1.2"), Decimal("1.3")])

    def test_valid_n_counts_only_present_values(self):
        rows = [rollup_row("RIDER", to_fixed=1.0), rollup_row("RIDER", to_fixed=None)]
        table = rs.build_percentile_table(rows)
        self.assertEqual(table["Days to Tag"]["n"]["All"], 2)
        self.assertEqual(table["Days Tag to First Fixed"]["n"]["All"], 1)

    def test_days_tag_to_release_uses_reversed_percentile(self):
        # 90th of a reversed metric = PERCENTILE(values, 0.10), i.e. a lower-tail threshold:
        # "90% of tickets were tagged at least this many days before release".
        rows = [rollup_row("RIDER", to_release=d) for d in range(1, 11)]
        table = rs.build_percentile_table(rows)
        self.assertTrue(table["Days Tag to Release"]["reversed"])
        self.assertFalse(table["Days to Tag"]["reversed"])
        self.assertEqual(table["Days Tag to Release"]["p"]["90th"]["All"], "1.9")
        self.assertEqual(table["Days Tag to Release"]["p"]["25th"]["All"], "7.8")
        # Non-reversed metric over the same values keeps the plain orientation.
        rows = [rollup_row("RIDER", to_tag=float(d)) for d in range(1, 11)]
        self.assertEqual(rs.build_percentile_table(rows)["Days to Tag"]["p"]["90th"]["All"], "9.1")

    def test_product_volume_counts_and_shares(self):
        rows = [rollup_row("RIDER")] * 3 + [rollup_row("DPA")]
        self.assertEqual(rs.product_volume(rows),
                         [("RIDER", 3, "75.0%"), ("DPA", 1, "25.0%")])

    def test_planned_version_volume_labels_blanks(self):
        rows = ([rollup_row("RIDER", planned="2026.1")] * 2
                + [rollup_row("RIDER", planned="")]
                + [rollup_row("RIDER", planned="   ")]
                + [rollup_row("RIDER", planned="No planned for")])
        self.assertEqual(
            rs.planned_version_volume(rows),
            [("2026.1", 2, "40.0%"), (rs.BLANK_PLANNED_LABEL, 2, "40.0%"),
             ("No planned for", 1, "20.0%")],
        )


class TestComputeRowClassificationFields(unittest.TestCase):
    """compute_row must surface the fields the new rollups group by."""

    def test_classification_fields_populated(self):
        # Modelled on RSRP-503287: 2 support tickets, 394 affected licenses, no votes.
        iss = issue("RSRP-503287", "License Vault requires auth for each active VS instance",
                    ms("2026-03-20"), ms("2026-05-22"), planned="2026.1",
                    subsystem="Licensing and Evaluation", support=2, licenses=394, votes=0)
        row = build_row(iss, [tag_added(rs.MEASURE_TAGS[0], ms("2026-03-21"))], is_tagged=True)
        self.assertEqual(row["subsystem"], "Licensing and Evaluation")
        self.assertEqual(row["support_tickets"], 2)
        self.assertEqual(row["affected_licenses"], 394)
        self.assertEqual(row["votes"], 0)
        self.assertEqual(row["signal"], "Support")
        self.assertEqual(row["regression"], "")

    def test_regression_tag_and_votes_from_issue(self):
        # Modelled on RIDER-132740: carries .net-regression alongside the stopper tag.
        iss = issue("RIDER-132740", "Failed to upload application APK file to device",
                    ms("2025-12-01"), ms("2026-01-10"), votes=4,
                    tags=[rs.REGRESSION_TAG, "rider-ex-stopper"])
        row = build_row(iss, [tag_added(rs.MEASURE_TAGS[1], ms("2025-12-02"))], is_tagged=True)
        self.assertEqual(row["regression"], rs.REGRESSION_BY_TAG)
        self.assertEqual(row["signal"], "Votes")

    def test_absent_fields_default_to_empty_not_none(self):
        # Projects that don't define these fields must not break the rollups.
        iss = issue("DMRY-1", "x", ms("2025-01-01"), ms("2025-02-01"))
        row = build_row(iss, [tag_added(rs.MEASURE_TAGS[0], ms("2025-01-02"))], is_tagged=True)
        self.assertEqual(row["subsystem"], "")
        self.assertEqual((row["votes"], row["support_tickets"], row["affected_licenses"]), (0, 0, 0))
        self.assertEqual((row["signal"], row["regression"]), ("", ""))
        self.assertEqual(rs.subsystem_label(row), rs.NO_SUBSYSTEM_LABEL)


# --------------------------------------------------------------------------------------
# Classification: regressions and customer signal
# --------------------------------------------------------------------------------------

class TestClassification(unittest.TestCase):
    def test_cf_to_int(self):
        self.assertEqual(rs.cf_to_int(255), 255)
        self.assertEqual(rs.cf_to_int("394"), 394)
        self.assertEqual(rs.cf_to_int({"name": "2"}), 2)
        self.assertEqual(rs.cf_to_int([{"presentation": "7"}]), 7)
        self.assertEqual(rs.cf_to_int(None), 0)      # field absent -> 0, not None
        self.assertEqual(rs.cf_to_int([]), 0)
        self.assertEqual(rs.cf_to_int("n/a"), 0)

    def test_regression_tag_wins_over_text(self):
        self.assertEqual(rs.classify_regression([rs.REGRESSION_TAG], "a regression", "x"),
                         rs.REGRESSION_BY_TAG)
        self.assertEqual(rs.classify_regression([rs.REGRESSION_TAG, "other"], "s", None),
                         rs.REGRESSION_BY_TAG)

    def test_regression_text_match_in_summary_or_description(self):
        self.assertEqual(rs.classify_regression([], "Regression in build", None),
                         rs.REGRESSION_BY_TEXT)
        self.assertEqual(rs.classify_regression([], "s", "This regressed in 2026.1"),
                         rs.REGRESSION_BY_TEXT)
        self.assertEqual(rs.classify_regression([], "s", None), "")
        self.assertEqual(rs.classify_regression(["unrelated-tag"], "s", "no such word"), "")

    def test_signal_labels(self):
        self.assertEqual(rs.classify_signal(votes=8, support_tickets=2), "Support+votes")
        self.assertEqual(rs.classify_signal(votes=0, support_tickets=1), "Support")
        self.assertEqual(rs.classify_signal(votes=2, support_tickets=0), "Votes")
        self.assertEqual(rs.classify_signal(votes=1, support_tickets=0), "")

    def test_signal_thresholds_are_inclusive(self):
        self.assertEqual(rs.classify_signal(rs.VOTES_SIGNAL_MIN - 1, 0), "")
        self.assertEqual(rs.classify_signal(rs.VOTES_SIGNAL_MIN, 0), "Votes")
        self.assertEqual(rs.classify_signal(0, rs.SUPPORT_SIGNAL_MIN), "Support")


class TestAffectedAreaRollups(unittest.TestCase):
    def test_subsystem_crosstab_counts_per_project(self):
        rows = [rollup_row("RIDER", subsystem="Build"), rollup_row("RIDER", subsystem="Build"),
                rollup_row("DPA", subsystem="Build"), rollup_row("RIDER", subsystem="Debugger")]
        volume = rs.subsystem_volume(rows)
        self.assertEqual([(l, n, s) for l, n, s, _ in volume],
                         [("Build", 3, "75.0%"), ("Debugger", 1, "25.0%")])
        self.assertEqual(volume[0][3], {"RIDER": 2, "DPA": 1})
        self.assertEqual(volume[1][3], {"RIDER": 1})

    def test_missing_subsystem_is_labelled(self):
        rows = [rollup_row("RIDER", subsystem=""), rollup_row("RIDER", subsystem="   ")]
        self.assertEqual(rs.subsystem_volume(rows)[0][0], rs.NO_SUBSYSTEM_LABEL)

    def test_top_subsystem_per_project(self):
        rows = ([rollup_row("RIDER", subsystem="Build")] * 3
                + [rollup_row("RIDER", subsystem="Debugger")]
                + [rollup_row("DPA", subsystem="Profiler")])
        self.assertEqual(rs.top_subsystem_per_project(rows),
                         [("RIDER", 4, "Build", 3, "75.0%"), ("DPA", 1, "Profiler", 1, "100.0%")])


class TestRegressionAndWatchlistRollups(unittest.TestCase):
    def test_regression_rows_tag_first_then_text(self):
        rows = [rollup_row("RIDER", regression=rs.REGRESSION_BY_TEXT, issue_id="RIDER-2"),
                rollup_row("RIDER", regression=rs.REGRESSION_BY_TAG, issue_id="RIDER-1"),
                rollup_row("RIDER", regression="", issue_id="RIDER-3")]
        self.assertEqual([r["id"] for r in rs.regression_rows(rows)], ["RIDER-1", "RIDER-2"])

    def test_regression_volume_shares_are_of_all_stoppers(self):
        rows = ([rollup_row("RIDER", regression=rs.REGRESSION_BY_TAG)] * 3
                + [rollup_row("RIDER", regression=rs.REGRESSION_BY_TEXT)]
                + [rollup_row("RIDER")] * 6)
        self.assertEqual(rs.regression_volume(rows),
                         [(rs.REGRESSION_BY_TAG, 3, "30.0%"), (rs.REGRESSION_BY_TEXT, 1, "10.0%")])

    def test_regressions_reuse_the_subsystem_crosstab(self):
        rows = [rollup_row("RIDER", subsystem="Build", regression=rs.REGRESSION_BY_TAG),
                rollup_row("RIDER", subsystem="Editor")]
        volume = rs.subsystem_volume(rs.regression_rows(rows))
        self.assertEqual([(l, n, s) for l, n, s, _ in volume], [("Build", 1, "100.0%")])

    def test_watchlist_excludes_unsignalled_and_sorts_strongest_first(self):
        rows = [rollup_row("RIDER", votes=1, issue_id="RIDER-quiet"),
                rollup_row("RIDER", votes=50, issue_id="RIDER-votes"),
                rollup_row("RIDER", support=3, votes=1, issue_id="RIDER-support"),
                rollup_row("RIDER", support=3, votes=9, issue_id="RIDER-both")]
        self.assertEqual([(r["id"], r["signal"]) for r in rs.signal_rows(rows)],
                         [("RIDER-both", "Support+votes"), ("RIDER-support", "Support"),
                          ("RIDER-votes", "Votes")])

    def test_watchlist_breaks_ties_on_licenses_then_id(self):
        rows = [rollup_row("RIDER", votes=5, licenses=10, issue_id="RIDER-b"),
                rollup_row("RIDER", votes=5, licenses=99, issue_id="RIDER-a"),
                rollup_row("RIDER", votes=5, licenses=10, issue_id="RIDER-a2")]
        self.assertEqual([r["id"] for r in rs.signal_rows(rows)],
                         ["RIDER-a", "RIDER-a2", "RIDER-b"])


# --------------------------------------------------------------------------------------
# Workbook layout
# --------------------------------------------------------------------------------------

class TestSpreadsheetValues(unittest.TestCase):
    def test_num_or_none(self):
        self.assertEqual(rs.num_or_none("201.2"), 201.2)
        self.assertEqual(rs.num_or_none("-59.9"), -59.9)
        self.assertEqual(rs.num_or_none("0.0"), 0.0)
        self.assertIsNone(rs.num_or_none(""))

    def test_share_value_is_a_fraction(self):
        self.assertEqual(rs.share_value(65, 338), 65 / 338)
        self.assertEqual(rs.share_value(338, 338), 1.0)
        self.assertIsNone(rs.share_value(1, 0))

    def test_issue_table_row_emits_numbers_for_day_counts(self):
        row = rollup_row("RIDER", to_tag=565.66, to_resolved=9.4, to_fixed=None, to_release=54)
        row.update(tag_added="2026-02-04", planned_for_date="2026-03-30", in_planned=True,
                   first_available="2026.1", state_history="Open -> Fixed",
                   removed_while_open=False)
        cells = rs.issue_table_row(row)
        self.assertEqual(dict(zip(rs.ISSUE_TABLE_HEADER, cells))["Days to Tag"], 565.7)
        self.assertEqual(dict(zip(rs.ISSUE_TABLE_HEADER, cells))["Days Tag to Resolved"], 9.4)
        # Absent metric stays empty rather than becoming 0.
        self.assertIsNone(dict(zip(rs.ISSUE_TABLE_HEADER, cells))["Days Tag to First Fixed"])
        self.assertEqual(len(cells), len(rs.ISSUE_TABLE_HEADER))

    def test_issue_table_header_and_formats_line_up(self):
        self.assertEqual(len(rs.ISSUE_TABLE_HEADER), len(rs.ISSUE_TABLE_FORMATS))


class TestXlsxSheets(unittest.TestCase):
    def sheets(self):
        rows = [
            rollup_row("RIDER", to_tag=1.0, to_resolved=2.0, to_fixed=3.0, to_release=10,
                       planned="2026.1", subsystem="Build", votes=5, issue_id="RIDER-1"),
            rollup_row("RIDER", to_tag=3.0, to_resolved=4.0, to_release=20, planned="",
                       subsystem="", support=2, issue_id="RIDER-2",
                       regression=rs.REGRESSION_BY_TAG),
            rollup_row("DPA", to_tag=5.0, to_resolved=6.0, to_release=30, planned="2026.2",
                       subsystem="Profiler", issue_id="DPA-1"),
        ]
        for r in rows:
            r.update(tag_added="2026-01-02", planned_for_date="2026-03-30", in_planned=False,
                     first_available="", state_history="Open", removed_while_open=False)
        return dict((title, blocks) for title, blocks in rs.xlsx_sheets(rows)), rows

    def test_expected_tabs_in_order(self):
        sheets, _ = self.sheets()
        self.assertEqual(list(sheets), ["Release stoppers", "Percentiles", "Product volume",
                                        "Planned versions", "Affected areas", "Regressions",
                                        "Watchlist", "Flow"])

    def test_sheet_titles_fit_excels_limit(self):
        sheets, _ = self.sheets()
        for title in sheets:
            self.assertLessEqual(len(title), 31, title)

    def test_every_block_has_aligned_header_rows_and_formats(self):
        sheets, _ = self.sheets()
        for title, blocks in sheets.items():
            for caption, header, data_rows, formats in blocks:
                self.assertEqual(len(header), len(formats), f"{title}: {caption}")
                for data_row in data_rows:
                    self.assertLessEqual(len(data_row), len(header), f"{title}: {caption}")

    def test_percentiles_tab_has_a_block_per_metric_plus_note(self):
        sheets, _ = self.sheets()
        blocks = sheets["Percentiles"]
        captions = [b[0] for b in blocks]
        self.assertEqual(len(blocks), len(rs.ROLLUP_METRICS) + 1)
        self.assertTrue(captions[0].startswith("Days to Tag"))
        self.assertIn("reversed", captions[3])           # Days Tag to Release
        self.assertEqual(blocks[-1][2], [[rs.REVERSED_PERCENTILE_NOTE]])

    def test_percentile_cells_are_numbers_not_strings(self):
        sheets, _ = self.sheets()
        _, header, data_rows, _ = sheets["Percentiles"][0]
        valid_n, first_pct = data_rows[0], data_rows[1]
        self.assertEqual(valid_n[0], "Valid N")
        self.assertEqual(valid_n[2], 3)                  # All
        self.assertIsInstance(first_pct[2], float)

    def test_shares_are_fractions_so_the_spreadsheet_formats_them(self):
        sheets, _ = self.sheets()
        _, _, data_rows, formats = sheets["Product volume"][0]
        self.assertEqual(formats[2], rs.FMT_PCT)
        self.assertEqual(data_rows[0][:2], ["RIDER", 2])
        self.assertAlmostEqual(data_rows[0][2], 2 / 3)
        self.assertEqual(data_rows[-1], ["Total", 3, 1.0])

    def test_regressions_tab_omits_ticket_blocks_when_there_are_none(self):
        rows = [rollup_row("RIDER", subsystem="Build", issue_id="RIDER-1")]
        rows[0].update(tag_added="2026-01-02", planned_for_date="", in_planned=False,
                       first_available="", state_history="Open", removed_while_open=False)
        blocks = dict(rs.xlsx_sheets(rows))["Regressions"]
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0][2], [])


if __name__ == "__main__":
    unittest.main()
