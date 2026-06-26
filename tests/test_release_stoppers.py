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


def issue(idr, summary, created, resolved, planned=None, available=None, fix=None) -> dict:
    cf = {}
    if planned is not None:
        cf[rs.PLANNED_FOR_FIELD] = {"name": planned}
    if available is not None:
        cf[rs.AVAILABLE_IN_FIELD] = [{"name": v} for v in available]
    if fix is not None:
        cf[rs.FIX_VERSION_FIELDS[0]] = {"name": fix}
    return {"idReadable": idr, "summary": summary, "created": created, "resolved": resolved, "_cf": cf}


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


if __name__ == "__main__":
    unittest.main()
