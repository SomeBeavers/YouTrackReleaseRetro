"""Tests for the flow-conformance analysis in release_stoppers.py.

The expected stopper lifecycle and the named anomalies come from the .NET Release Stoppers
retrospective deck. Timelines here are the ordered event labels `parse_activities` produces
(state names interleaved with "Tag added" / "Tag removed"), so these tests are pure.

Run with the project venv:
    .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import release_stoppers as rs  # noqa: E402

# The lifecycle the deck calls normal.
NORMAL = ["Untriaged", "Triaged", "Open", "In Progress", "Tag added", "Tag added",
          "Fixed in Branch", "Fixed", "Verified", "Tag removed"]


def flow_row(issue_id, anomalies, unclear=(), end_state="Verified", removed_state="",
             removed=False, tag_groups=1, reopened=False, tag_after=False, project="RIDER"):
    """A compute_row()-shaped dict carrying only what the flow rollups read."""
    return {"id": issue_id, "project": project, "summary": "s", "state_history": "Open -> Fixed",
            "flow_anomalies": list(anomalies), "unclear_states": list(unclear),
            "end_state": end_state, "removed_while_open": removed,
            "removed_while_open_state": removed_state, "tag_groups": tag_groups,
            "reopened": reopened, "tag_after_fixed": tag_after,
            "in_planned": False, "planned_for": "", "first_available": ""}


class TestFlowPrimitives(unittest.TestCase):
    def test_state_labels_strips_tag_events(self):
        self.assertEqual(rs.state_labels(NORMAL),
                         ["Untriaged", "Triaged", "Open", "In Progress", "Fixed in Branch",
                          "Fixed", "Verified"])

    def test_consecutive_tag_adds_are_one_group(self):
        self.assertEqual(rs.count_tag_added_groups(["Tag added", "Tag added", "Fixed"]), 1)

    def test_tag_adds_split_by_other_events_are_separate_groups(self):
        self.assertEqual(rs.count_tag_added_groups(["Tag added", "Fixed", "Tag added"]), 2)
        self.assertEqual(rs.count_tag_added_groups(["Open", "Fixed"]), 0)

    def test_tag_after_fix_counts_fixed_in_branch_as_landed(self):
        # Deliberately wider than FIXED_STATES, matching the expected-flow wording.
        self.assertTrue(rs.tag_added_after_first_fixed(["Open", "Fixed in Branch", "Tag added"]))
        self.assertIn("Fixed in Branch", rs.FIX_LANDED_STATES)
        self.assertNotIn("Fixed in Branch", rs.FIXED_STATES)  # metric anchor left alone

    def test_tag_after_fix_counts_any_later_tag_not_just_the_first(self):
        # Tagged, fixed, then tagged again: still a tag added after the fix landed.
        self.assertTrue(rs.tag_added_after_first_fixed(
            ["Tag added", "Fixed", "Reopened", "Tag added"]))

    def test_tag_before_fix_is_not_flagged(self):
        self.assertFalse(rs.tag_added_after_first_fixed(NORMAL))
        self.assertFalse(rs.tag_added_after_first_fixed(["Tag added", "Open"]))  # never fixed


class TestAnalyzeFlow(unittest.TestCase):
    def test_expected_lifecycle_has_no_anomalies(self):
        flow = rs.analyze_flow(NORMAL, removed_while_open=False)
        self.assertEqual(flow["anomalies"], [])
        self.assertEqual(flow["end_state"], "Verified")
        self.assertEqual(flow["tag_groups"], 1)
        self.assertFalse(flow["reopened"])

    def test_each_anomaly_is_detected_on_its_own(self):
        cases = {
            rs.ANOMALY_UNCLEAR: (["Open", "Waiting for Info", "Tag added", "Fixed"], False),
            rs.ANOMALY_TAG_REMOVED_OPEN: (NORMAL, True),
            rs.ANOMALY_TAG_AFTER_FIXED: (["Open", "Fixed", "Tag added"], False),
            rs.ANOMALY_REOPENED: (["Tag added", "Fixed", "Reopened", "Verified"], False),
            rs.ANOMALY_SPLIT_TAGS: (["Tag added", "Open", "Tag added", "Verified"], False),
        }
        for expected, (labels, removed) in cases.items():
            with self.subTest(anomaly=expected):
                self.assertIn(expected, rs.analyze_flow(labels, removed)["anomalies"])

    def test_anomalies_are_reported_in_deck_order(self):
        labels = ["Open", "Duplicate", "Tag added", "Fixed", "Reopened", "Tag added", "Verified"]
        flow = rs.analyze_flow(labels, removed_while_open=True)
        self.assertEqual(flow["anomalies"],
                         [a for a in rs.FLOW_ANOMALIES if a in flow["anomalies"]])
        self.assertEqual(len(flow["anomalies"]), 5)      # all five at once

    def test_unclear_states_listed_in_canonical_order_without_duplicates(self):
        labels = ["Waiting for Info", "Duplicate", "Waiting for Info", "Fixed"]
        self.assertEqual(rs.analyze_flow(labels, False)["unclear_states"],
                         ["Duplicate", "Waiting for Info"])

    def test_end_state_ignores_a_trailing_tag_event(self):
        self.assertEqual(rs.analyze_flow(["Open", "Fixed", "Tag removed"], False)["end_state"],
                         "Fixed")

    def test_empty_timeline_is_handled(self):
        flow = rs.analyze_flow([], removed_while_open=False)
        self.assertEqual(flow["end_state"], "")
        self.assertEqual(flow["anomalies"], [])
        self.assertEqual(flow["tag_groups"], 0)


class TestParseActivitiesFlowOutput(unittest.TestCase):
    """The parser must expose the ordered timeline and label removals that predate any state."""

    @staticmethod
    def ms(day):
        from datetime import datetime, timezone
        return int(datetime(2026, 1, day, tzinfo=timezone.utc).timestamp() * 1000)

    def tag(self, name, day, removed=False):
        item = [{"name": name}]
        return {"timestamp": self.ms(day), "category": {"id": "TagsCategory"},
                "added": [] if removed else item, "removed": item if removed else []}

    def state(self, frm, to, day):
        return {"timestamp": self.ms(day), "category": {"id": "CustomFieldCategory"},
                "field": {"name": "State"}, "added": [{"name": to}],
                "removed": [{"name": frm}] if frm else []}

    def test_timeline_labels_are_exposed_in_order(self):
        acts = [self.state("Open", "Triaged", 2),
                self.tag(rs.MEASURE_TAGS[0], 3),
                self.state("Triaged", "Fixed", 4)]
        parsed = rs.parse_activities(acts)
        self.assertEqual(parsed["timeline_labels"], ["Open", "Triaged", "Tag added", "Fixed"])

    def test_removal_before_any_state_change_is_labelled_with_the_initial_state(self):
        # The tag came off on day 2, before the first State activity; the ticket was Triaged then.
        acts = [self.tag(rs.MEASURE_TAGS[0], 1),
                self.tag(rs.MEASURE_TAGS[0], 2, removed=True),
                self.state("Triaged", "Fixed", 3)]
        parsed = rs.parse_activities(acts)
        self.assertEqual(parsed["stopper_removed_states"], [None])   # unchanged, drives the verdict
        self.assertEqual(parsed["removed_states_labelled"], ["Triaged"])

    def test_labelled_removals_align_with_the_raw_list(self):
        acts = [self.tag(rs.MEASURE_TAGS[0], 1),
                self.tag(rs.MEASURE_TAGS[0], 2, removed=True),
                self.state("Triaged", "Open", 3),
                self.tag(rs.MEASURE_TAGS[0], 4),
                self.tag(rs.MEASURE_TAGS[0], 5, removed=True)]
        parsed = rs.parse_activities(acts)
        self.assertEqual(len(parsed["removed_states_labelled"]),
                         len(parsed["stopper_removed_states"]))
        self.assertEqual(parsed["removed_states_labelled"], ["Triaged", "Open"])


class TestFlowRollups(unittest.TestCase):
    def rows(self):
        return [
            flow_row("RIDER-1", []),
            flow_row("RIDER-2", [rs.ANOMALY_REOPENED], reopened=True, end_state="Fixed"),
            flow_row("RIDER-3", [rs.ANOMALY_UNCLEAR, rs.ANOMALY_TAG_REMOVED_OPEN],
                     unclear=["Duplicate"], removed=True, removed_state="Triaged",
                     end_state="Duplicate"),
            flow_row("DPA-1", [rs.ANOMALY_TAG_REMOVED_OPEN], removed=True,
                     removed_state="Open", project="DPA"),
        ]

    def test_conformance_split_is_a_partition(self):
        self.assertEqual(rs.flow_conformance(self.rows()),
                         [("Not normal", 3, "75.0%"), ("Normal", 1, "25.0%")])

    def test_anomaly_volume_overlaps_and_keeps_deck_order(self):
        volume = rs.flow_anomaly_volume(self.rows())
        self.assertEqual([label for label, _, _ in volume],
                         [rs.ANOMALY_UNCLEAR, rs.ANOMALY_TAG_REMOVED_OPEN, rs.ANOMALY_REOPENED])
        self.assertEqual([count for _, count, _ in volume], [1, 2, 1])

    def test_anomaly_volume_omits_anomalies_nobody_has(self):
        labels = [label for label, _, _ in rs.flow_anomaly_volume(self.rows())]
        self.assertNotIn(rs.ANOMALY_SPLIT_TAGS, labels)

    def test_unclear_and_end_state_volumes(self):
        self.assertEqual(rs.unclear_state_volume(self.rows()), [("Duplicate", 1, "25.0%")])
        self.assertEqual(dict((l, c) for l, c, _ in rs.end_state_volume(self.rows())),
                         {"Verified": 2, "Fixed": 1, "Duplicate": 1})

    def test_removal_breakdown_is_a_share_of_removals_not_of_all_tickets(self):
        # 2 of 4 tickets had the tag removed while unresolved -> each state is 50% of removals.
        self.assertEqual(rs.tag_removal_state_volume(self.rows()),
                         [("Triaged", 1, "50.0%"), ("Open", 1, "50.0%")])

    def test_planned_vs_available_reports_the_uncomparable_bucket(self):
        rows = [flow_row("A", []), flow_row("B", []), flow_row("C", [])]
        rows[0].update(in_planned=True, planned_for="2026.1", first_available="2026.1")
        rows[1].update(in_planned=False, planned_for="2026.1", first_available="2026.1.1")
        # rows[2] has no planned version at all -> not comparable, never counted as a miss
        self.assertEqual(rs.planned_vs_available_volume(rows),
                         [("Planned == Available", 1, "33.3%"),
                          ("Planned != Available", 1, "33.3%"),
                          ("Not comparable", 1, "33.3%")])

    def test_anomaly_rows_are_sorted_by_anomaly_count(self):
        self.assertEqual([r["id"] for r in rs.flow_anomaly_rows(self.rows())],
                         ["RIDER-3", "DPA-1", "RIDER-2"])

    def test_blocks_are_well_formed(self):
        for caption, header, data, formats in rs.flow_blocks(self.rows()):
            self.assertEqual(len(header), len(formats), caption)
            for row in data:
                self.assertLessEqual(len(row), len(header), caption)


if __name__ == "__main__":
    unittest.main()
