"""
Analyzes resolved issues tagged with a release-stopper tag.

For each issue reports:
  - Time from creation to measure tag added (days)
  - Time from measure tag added to resolved (days)
  - Time from measure tag added to first Fixed/Verified state (days)
  - Planned for (or Fix versions fallback) at end of tag-added day, with site release date
  - Available in (current) versions
  - Whether the Planned for version is contained in any Available in entry
  - First (oldest by site release date) Available in version
  - State + tag event history, e.g. "Open -> Triaged -> Tag added -> Fixed"
  - Whether rider-release-stopper tag was removed while issue was still open

On top of the per-issue table it rolls up:
  - Percentiles (25/50/75/90/95/99 + Valid N) for each day-metric, per project and overall
  - Stopper volume and share by product, and by Planned for version
  - Affected area from the Subsystem field, cross-tabbed by project, plus each project's top area
  - Regressions (.net-regression tag, or the word "regression" in summary/description)
  - A customer-signal watchlist (linked support tickets / votes / affected licenses)
  - Flow conformance: how often a ticket deviates from the expected stopper lifecycle, and how
    (unclear states, tag removed while unresolved, tagged after the fix landed, reopened,
    separated tag groups), plus end states and Planned vs Available

With --compare it also measures COMPARISON_COHORTS (other JetBrains products, same window
and metric definitions) and reports the percentiles side by side.

Renderings: console, Markdown, one CSV per table, and an .xlsx workbook with a tab per rollup.

Two discovery paths feed the report:
  A. Issues that currently carry a stopper tag (SEARCH_TAGS) — works for ReSharper/Rider.
  B. SCAN_PROJECTS (dotMemory/dotTrace/DPA/Profiler) strip the stopper tag once the issue is
     resolved, so the current-tag query misses them. For these we scan all resolved
     Show-Stopper/Critical issues and keep the ones whose activity history shows a
     release-stopper tag was *added* at some point.

* next to a date means tag addition was not found in activity history;
  issue creation date is used as a fallback.
"""

import argparse
import csv
import os
import re
import requests
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import NamedTuple

from release_versions import PRODUCT_CODE, get_release_calendar, get_version_dates

YOUTRACK_URL = "https://youtrack.jetbrains.com/api"
TOKEN = os.getenv("YOUTRACK_TOKEN")
RESOLVED_DATE_RANGE = "2025-01-01 .. today"
RESOLVED_CLAUSE = f"#Resolved resolved date: {RESOLVED_DATE_RANGE}"
SEARCH_TAGS = ["dotnet-ex-release-stopper", "rider-ex-stopper"]
MEASURE_TAGS = ["dotnet-release-stopper", "rider-release-stopper"]
MEASURE_TAGS_FALLBACK = ["rider-ex-stopper"]
RIDER_RELEASE_STOPPER_TAG = "rider-release-stopper"
# rider-ex-stopper is also applied to EAP stoppers. An issue that carried rider-eap-stopper but
# never a real release-stopper tag (MEASURE_TAGS) is an EAP-only stopper and is excluded.
EAP_STOPPER_TAG = "rider-eap-stopper"

# Projects that remove the stopper tag after an issue is resolved, so the current-tag query
# (SEARCH_TAGS) misses them. Discovered instead by scanning activity history (Path B).
SCAN_PROJECTS = ["DMRY", "DTRC", "DPA", "PROF"]
SCAN_PRIORITIES = ["Show-Stopper", "Critical"]
# Any of these tags being *added* in history => the issue was treated as a release stopper.
STOPPER_TAGS = set(SEARCH_TAGS) | set(MEASURE_TAGS)
FIXED_STATES = {"Fixed", "Verified"}
PLANNED_FOR_FIELD = "Planned for"
FIX_VERSION_FIELDS = ("Fix version", "Fixed in build")
AVAILABLE_IN_FIELD = "Available in"
SUBSYSTEM_FIELD = "Subsystem"
SUPPORT_TICKETS_FIELD = "Linked Support Tickets"
AFFECTED_LICENSES_FIELD = "Affected licenses"

# Fields requested for every issue on both discovery paths.
ISSUE_FIELDS = (
    "idReadable,summary,description,votes,created,resolved,tags(name),"
    "customFields(name,value(name,presentation))"
)

# Regression classification. The tag is authoritative; the text match is a weaker secondary
# signal (the word "regression" in the summary or description) and is labelled separately.
REGRESSION_TAG = ".net-regression"
REGRESSION_TEXT_RE = re.compile(r"regress", re.IGNORECASE)
REGRESSION_BY_TAG = f"{REGRESSION_TAG} tag"
REGRESSION_BY_TEXT = "mentions regression"

# Customer-signal thresholds for the watchlist.
VOTES_SIGNAL_MIN = 2
SUPPORT_SIGNAL_MIN = 1
NO_SUBSYSTEM_LABEL = "(no subsystem)"
UNKNOWN_STATE_LABEL = "(unknown)"


class TagVocabulary(NamedTuple):
    """Which tags mark a release blocker, for one product family.

    Passed explicitly into parse_activities so a comparison cohort can use another product's
    vocabulary without mutating module state — fetch_all_activities parses on worker threads,
    where swapping globals between cohorts would be a race.
    """
    measure: tuple[str, ...]      # anchors tag_dt; defines "really was a release blocker"
    fallback: tuple[str, ...]     # anchors tag_dt when no measure tag was ever added
    stopper: frozenset            # any of these being added means "was treated as a blocker"
    eap: str | None = None        # carrying only this one means EAP-only, and is excluded

    @classmethod
    def of(cls, measure, fallback=(), extra_stopper=(), eap=None):
        return cls(tuple(measure), tuple(fallback),
                   frozenset(measure) | frozenset(extra_stopper), eap)


DEFAULT_VOCABULARY = TagVocabulary.of(
    measure=MEASURE_TAGS, fallback=MEASURE_TAGS_FALLBACK,
    extra_stopper=SEARCH_TAGS, eap=EAP_STOPPER_TAG,
)
BUILD_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")
NEXT_PUBLIC_BUILD_RE = re.compile(r"^Next\s+(\d+(?:\.\d+)*)\s+public build$", re.IGNORECASE)
EAP_RC_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(EAP|RC)\s+(\d+)$", re.IGNORECASE)

# Planned GA dates not yet published on jetbrains.com/resharper/download/other/. These only
# fill gaps: once a version ships, the real site date wins (see build_release_calendar). A
# stale guess must never override what actually happened.
FUTURE_RELEASES: dict[str, date] = {
    "2026.2": date(2026, 7, 9),
}

http_headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

client = requests.Session()
client.headers.update(http_headers)


def build_release_calendar(site_dates: dict[str, date],
                           planned: dict[str, date] | None = None,
                           verbose: bool = False) -> dict[str, date]:
    """Merge the published release calendar with FUTURE_RELEASES guesses.

    Published site dates always win: a planned date only fills a gap for a version that has not
    shipped yet. Overriding the other way round silently skews Days Tag to Release whenever a
    release slips (2026.2 was planned for 2026-07-09 and actually shipped 2026-07-22).
    """
    planned = FUTURE_RELEASES if planned is None else planned
    calendar = dict(planned)
    calendar.update(site_dates)
    still_future = [v for v in planned if v not in site_dates]
    if verbose:
        superseded = sorted(v for v in planned if v in site_dates and site_dates[v] != planned[v])
        print(f"Loaded {len(calendar)} releases ({len(still_future)} planned, not yet shipped).")
        for v in superseded:
            print(f"  {v}: shipped {site_dates[v]}, superseding the planned {planned[v]}")
        print()
    return calendar


def ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def strip_build_suffix(s: str | None) -> str:
    """'2025.3 EAP 4 (253.24325.45)' -> '2025.3 EAP 4'. Idempotent on clean input."""
    if not s:
        return ""
    return BUILD_SUFFIX_RE.sub("", s).strip()


def normalize_for_lookup(s: str | None) -> str:
    """Convert a (already strip_build_suffix'd) display version to the site lookup key.

    'Next 2025.1 public build' -> '2025.1'
    '2025.3 EAP 4'             -> '2025.3'  (promoted to parent GA)
    '2025.3 RC 1'              -> '2025.3'
    Pass-through otherwise (e.g., '2025.3', '2025.3.X').
    """
    if not s:
        return ""
    m = NEXT_PUBLIC_BUILD_RE.match(s)
    if m:
        return m.group(1)
    m = EAP_RC_RE.match(s)
    if m:
        return m.group(1)
    return s


def cf_to_str(value) -> str | None:
    """Single-value custom field -> string, handling dict | [dict] | None."""
    if value is None:
        return None
    if isinstance(value, list):
        if not value:
            return None
        v = value[0]
        return (v.get("name") or v.get("presentation")) if isinstance(v, dict) else str(v)
    if isinstance(value, dict):
        return value.get("name") or value.get("presentation")
    return str(value)


def cf_to_int(value) -> int:
    """Integer custom field -> int, 0 when absent. YouTrack sends these as bare numbers."""
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("name") or value.get("presentation")
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def classify_regression(tags: list[str], summary: str, description: str | None) -> str:
    """'.net-regression tag' | 'mentions regression' | '' — tag wins over the text match."""
    if REGRESSION_TAG in tags:
        return REGRESSION_BY_TAG
    if REGRESSION_TEXT_RE.search(f"{summary}\n{description or ''}"):
        return REGRESSION_BY_TEXT
    return ""


def classify_signal(votes: int, support_tickets: int) -> str:
    """Customer-signal label for the watchlist: 'Support+votes' | 'Support' | 'Votes' | ''."""
    has_votes = votes >= VOTES_SIGNAL_MIN
    has_support = support_tickets >= SUPPORT_SIGNAL_MIN
    if has_votes and has_support:
        return "Support+votes"
    if has_support:
        return "Support"
    if has_votes:
        return "Votes"
    return ""


def cf_to_list(value) -> list[str]:
    """Multi-value custom field -> list of strings (skips empty entries)."""
    if value is None:
        return []
    if isinstance(value, list):
        return [n for v in value if isinstance(v, dict) for n in [v.get("name") or v.get("presentation")] if n]
    if isinstance(value, dict):
        n = value.get("name") or value.get("presentation")
        return [n] if n else []
    return [str(value)]


def value_at_cutoff(changes: list[dict], cutoff_ms: float, current_value: str | None) -> str | None:
    """Field value as of cutoff_ms, given chronological change events and the current value.

    Each change is {"ts", "added", "removed"} where 'removed' is the value before the change.
    Logic: the first change strictly after the cutoff has its 'removed' equal to the value at cutoff.
    If no change happens after the cutoff, the current value is also the value at cutoff.
    """
    for c in changes:
        if c["ts"] > cutoff_ms:
            return c["removed"]
    return current_value


def planned_in_available(planned: str | None, available_clean: list[str]) -> bool:
    """True only if the planned version exactly matches a (normalized) Available in entry.

    A later patch release does NOT count: Available in '2026.1.1' when Planned for '2026.1' is
    No, because the fix slipped past the planned release into a subsequent update. EAP/RC/Next
    public build entries already normalize to their GA version (e.g. '2026.1 EAP 5' -> '2026.1'
    via normalize_for_lookup), so they still match a GA 'Planned for'.
    """
    if not planned:
        return False
    planned_key = normalize_for_lookup(strip_build_suffix(planned))
    return planned_key in available_clean


def oldest_available(
    lookup_versions: list[str],
    site_releases_map: dict[str, date],
) -> tuple[str, date] | None:
    """Returns (site_version, site_date) for the oldest Available in entry that exists on the site.

    Returns None if no entry matches a site release (so First Available stays empty
    rather than showing a string that's not on the site).
    """
    dated = [(n, site_releases_map[n]) for n in lookup_versions if n in site_releases_map]
    if not dated:
        return None
    dated.sort(key=lambda x: x[1])
    return dated[0]


def fetch_issues() -> list[dict]:
    seen = set()
    result = []
    for tag in SEARCH_TAGS:
        query = f"tag: {tag} {RESOLVED_CLAUSE}"
        response = client.get(
            f"{YOUTRACK_URL}/issues",
            params={
                "fields": ISSUE_FIELDS,
                "query": query,
                "$top": 1000,
            },
        )
        response.raise_for_status()
        for issue in response.json():
            if issue["idReadable"] not in seen:
                seen.add(issue["idReadable"])
                issue["_cf"] = {f.get("name"): f.get("value") for f in issue.get("customFields", [])}
                result.append(issue)
    return result


def fetch_activities(issue_id: str, vocabulary: TagVocabulary | None = None) -> dict:
    """Fetch tag and state change activities, return all parsed data."""
    response = client.get(
        f"{YOUTRACK_URL}/issues/{issue_id}/activities",
        params={
            "fields": "timestamp,added(name),removed(name),category(id),field(name)",
            "categories": "TagsCategory,CustomFieldCategory",
            "$top": 1000,
        },
    )
    response.raise_for_status()
    return parse_activities(response.json(), vocabulary)


def parse_activities(activities: list[dict], vocabulary: TagVocabulary | None = None) -> dict:
    """Parse raw YouTrack activity items (Tags + CustomField categories) into derived fields.

    Pure function (no I/O) so it can be unit-tested with mocked activity payloads.
    `vocabulary` selects which tags count as blockers; defaults to the dotnet tags.
    """
    vocab = DEFAULT_VOCABULARY if vocabulary is None else vocabulary
    activities = sorted(activities, key=lambda a: a.get("timestamp", 0))

    primary_times = []
    fallback_times = []
    timeline = []           # list of (timestamp, label)
    initial_state = None
    current_state = None
    first_fixed_dt = None
    stopper_removed_states = []  # state in effect each time a release-stopper tag (MEASURE_TAGS) was removed
    stopper_tag_added = False
    eap_stopper_added = False
    planned_for_changes = []
    fix_versions_changes = []

    for activity in activities:
        ts = activity.get("timestamp", 0)
        category_id = (activity.get("category") or {}).get("id", "")

        if category_id == "TagsCategory":
            for item in (activity.get("added") or []):
                if isinstance(item, dict):
                    name = item.get("name", "")
                    if name in vocab.stopper:
                        stopper_tag_added = True
                    if vocab.eap and name == vocab.eap:
                        eap_stopper_added = True
                    if name in vocab.measure:
                        primary_times.append(ts)
                        timeline.append((ts, "Tag added"))
                    elif name in vocab.fallback:
                        fallback_times.append(ts)
                        timeline.append((ts, "Tag added"))
            for item in (activity.get("removed") or []):
                if isinstance(item, dict) and item.get("name") in vocab.measure:
                    stopper_removed_states.append(current_state)
                    timeline.append((ts, "Tag removed"))

        elif category_id == "CustomFieldCategory":
            field_name = (activity.get("field") or {}).get("name", "")
            added = activity.get("added")
            removed = activity.get("removed")
            added_v = added[0].get("name") if isinstance(added, list) and added and isinstance(added[0], dict) else None
            removed_v = removed[0].get("name") if isinstance(removed, list) and removed and isinstance(removed[0], dict) else None

            if field_name == "State":
                from_state = removed_v if removed_v is not None else current_state
                to_state = added_v
                if to_state:
                    if initial_state is None and from_state:
                        initial_state = from_state
                    current_state = to_state
                    timeline.append((ts, to_state))
                    if to_state in FIXED_STATES and first_fixed_dt is None:
                        first_fixed_dt = ms_to_dt(ts)
            elif field_name == PLANNED_FOR_FIELD:
                planned_for_changes.append({"ts": ts, "added": added_v, "removed": removed_v})
            elif field_name in FIX_VERSION_FIELDS:
                fix_versions_changes.append({"ts": ts, "added": added_v, "removed": removed_v})

    tag_dt = None
    if primary_times:
        tag_dt = ms_to_dt(min(primary_times))
    elif fallback_times:
        tag_dt = ms_to_dt(min(fallback_times))

    # A removal recorded before any State change has no preceding state in hand at the time; the
    # ticket was in its initial state throughout, so use that for the breakdown. Kept separate
    # from stopper_removed_states so the Removed While Open verdict is untouched.
    removed_states_labelled = [s if s else initial_state for s in stopper_removed_states]

    timeline.sort(key=lambda e: e[0])
    labels = [label for _, label in timeline]
    if initial_state and (not labels or labels[0] != initial_state):
        labels.insert(0, initial_state)
    state_history = " -> ".join(labels) if labels else ""

    return {
        "tag_dt": tag_dt,
        "first_fixed_dt": first_fixed_dt,
        "state_history": state_history,
        "timeline_labels": labels,      # ordered events: state names + Tag added / Tag removed
        "stopper_removed_states": stopper_removed_states,
        "removed_states_labelled": removed_states_labelled,
        "stopper_tag_added": stopper_tag_added,
        "eap_stopper_added": eap_stopper_added,
        "release_stopper_added": bool(primary_times),  # a real release-stopper tag (MEASURE_TAGS) was added
        "planned_for_changes": planned_for_changes,
        "fix_versions_changes": fix_versions_changes,
    }


def fetch_priority_candidates() -> list[dict]:
    """Path B: resolved Show-Stopper/Critical issues in SCAN_PROJECTS, paginated.

    These projects strip the stopper tag after resolution, so a current-tag query misses them.
    Qualification (a stopper tag was added in history) is decided later from activities.
    """
    priority_clause = ", ".join(SCAN_PRIORITIES)
    query = (
        f"project: {', '.join(SCAN_PROJECTS)} {RESOLVED_CLAUSE} "
        f"Priority: {priority_clause}"
    )
    result = []
    skip = 0
    while True:
        response = client.get(
            f"{YOUTRACK_URL}/issues",
            params={
                "fields": ISSUE_FIELDS,
                "query": query,
                "$top": 1000,
                "$skip": skip,
            },
        )
        response.raise_for_status()
        chunk = response.json()
        for issue in chunk:
            issue["_cf"] = {f.get("name"): f.get("value") for f in issue.get("customFields", [])}
            result.append(issue)
        if len(chunk) < 1000:
            break
        skip += 1000
    return result


def fetch_resolved_state_map() -> dict[str, set[str]]:
    """{project shortName: set of State values whose isResolved is true}.

    Used to decide whether an issue was unresolved (#unresolved) at the moment a stopper tag
    was removed. Scoped per project because the same state name can be resolved in one project
    and unresolved in another (e.g. 'Shelved').
    """
    response = client.get(
        f"{YOUTRACK_URL}/admin/projects",
        params={
            "fields": "shortName,customFields(field(name),bundle(values(name,isResolved)))",
            "$top": 1000,
        },
    )
    response.raise_for_status()
    result: dict[str, set[str]] = {}
    for proj in response.json():
        sn = proj.get("shortName")
        if not sn:
            continue
        for cf in proj.get("customFields") or []:
            if (cf.get("field") or {}).get("name") == "State":
                values = (cf.get("bundle") or {}).get("values") or []
                result[sn] = {v.get("name") for v in values if v.get("isResolved")}
    return result


def fetch_all_activities(issue_ids: list[str],
                        vocabulary: TagVocabulary | None = None) -> dict[str, dict]:
    """Fetch activities for many issues concurrently. Returns {issue_id: activity_dict}."""
    with ThreadPoolExecutor(max_workers=16) as executor:
        results = executor.map(lambda iid: (iid, fetch_activities(iid, vocabulary)), issue_ids)
        return dict(results)


# --------------------------------------------------------------------------------------
# Flow conformance (does the ticket follow the expected stopper lifecycle?)
# --------------------------------------------------------------------------------------

# Expected ("normal") lifecycle:
#   intake / triage / open / in-progress
#     -> one or more consecutive "Tag added"
#     -> Fixed in Branch / Fixed
#     -> optional Verified
#     -> optional final "Tag removed"
# Anything else is reported as one or more named anomalies below. A ticket is "not normal" if it
# has at least one; the same ticket can carry several, so the anomaly counts overlap and only the
# not-normal total is a partition of the cohort.

TAG_ADDED_LABEL = "Tag added"
TAG_REMOVED_LABEL = "Tag removed"
TAG_LABELS = (TAG_ADDED_LABEL, TAG_REMOVED_LABEL)

# Where the fix is considered to have landed, for flow purposes. Wider than FIXED_STATES on
# purpose: the expected flow reads "Fixed in Branch / Fixed", while FIXED_STATES anchors the
# Days Tag to First Fixed metric and must not change.
FIX_LANDED_STATES = frozenset(FIXED_STATES) | {"Fixed in Branch"}

# States that mean the ticket was not a clearly understood, reproducible defect.
UNCLEAR_STATES = ("Duplicate", "Can't Reproduce", "Incomplete", "Waiting for Info",
                  "To Reproduce", "Wait for Reply", "Obsolete")
REOPENED_STATE = "Reopened"

ANOMALY_UNCLEAR = "Unclear ticket state"
ANOMALY_TAG_REMOVED_OPEN = "Tag removed while unresolved"
ANOMALY_TAG_AFTER_FIXED = "Tag added after first Fixed / Verified"
ANOMALY_REOPENED = "Reopened"
ANOMALY_SPLIT_TAGS = "Separated Tag added groups"
# Reported in this order — it is the order the retrospective deck presents them in.
FLOW_ANOMALIES = (ANOMALY_UNCLEAR, ANOMALY_TAG_REMOVED_OPEN, ANOMALY_TAG_AFTER_FIXED,
                  ANOMALY_REOPENED, ANOMALY_SPLIT_TAGS)


def state_labels(labels: list[str]) -> list[str]:
    """Timeline with the tag events stripped, leaving the state transitions."""
    return [l for l in labels if l not in TAG_LABELS]


def count_tag_added_groups(labels: list[str]) -> int:
    """Number of runs of consecutive "Tag added" events.

    More than one run means the tag was taken off and put back with real work in between, i.e.
    the stopper decision was revisited rather than simply re-applied.
    """
    groups = 0
    for index, label in enumerate(labels):
        if label == TAG_ADDED_LABEL and (index == 0 or labels[index - 1] != TAG_ADDED_LABEL):
            groups += 1
    return groups


def tag_added_after_first_fixed(labels: list[str]) -> bool:
    """True when a stopper tag was added after the fix had already landed.

    "Landed" includes Fixed in Branch, matching the expected-flow wording above; note that is
    deliberately wider than FIXED_STATES, which anchors the Days Tag to First Fixed metric and is
    left alone. Any tag added after that point counts, not just the first one, so a ticket
    re-tagged after its fix is flagged here as well as under separated tag groups.
    """
    landed = next((i for i, l in enumerate(labels) if l in FIX_LANDED_STATES), None)
    return landed is not None and TAG_ADDED_LABEL in labels[landed + 1:]


def analyze_flow(labels: list[str], removed_while_open: bool) -> dict:
    """Flow findings for one ticket, from its ordered event timeline. Pure."""
    states = state_labels(labels)
    unclear = [s for s in UNCLEAR_STATES if s in states]
    tag_groups = count_tag_added_groups(labels)
    anomalies = []
    if unclear:
        anomalies.append(ANOMALY_UNCLEAR)
    if removed_while_open:
        anomalies.append(ANOMALY_TAG_REMOVED_OPEN)
    if tag_added_after_first_fixed(labels):
        anomalies.append(ANOMALY_TAG_AFTER_FIXED)
    if REOPENED_STATE in states:
        anomalies.append(ANOMALY_REOPENED)
    if tag_groups > 1:
        anomalies.append(ANOMALY_SPLIT_TAGS)
    return {
        "end_state": states[-1] if states else "",
        "unclear_states": unclear,
        "reopened": REOPENED_STATE in states,
        "tag_after_fixed": tag_added_after_first_fixed(labels),
        "tag_groups": tag_groups,
        "anomalies": anomalies,
    }

def compute_row(
    issue: dict,
    act: dict,
    site_releases_map: dict,
    resolved_state_map: dict[str, set[str]],
    default_resolved_states: set[str],
    is_tagged: bool,
) -> dict | None:
    """Turn one issue + its parsed activities into a report row, or None if it doesn't qualify.

    Pure function (no I/O). `act` is the dict returned by parse_activities; `issue` carries
    idReadable, summary, created, resolved and a "_cf" map of custom-field values.
    `is_tagged` is True for Path A issues (currently carry a stopper tag) which always qualify.
    """
    issue_id = issue["idReadable"]
    created_ms = issue.get("created")
    resolved_ms = issue.get("resolved")
    if not created_ms or not resolved_ms:
        return None

    # Exclude EAP-only stoppers: carried rider-eap-stopper but never a real release-stopper tag.
    if act["eap_stopper_added"] and not act["release_stopper_added"]:
        return None

    # Path B candidates qualify only if a stopper tag was added in history; Path A always qualifies.
    if not is_tagged and not act["stopper_tag_added"]:
        return None

    created_dt = ms_to_dt(created_ms)
    resolved_dt = ms_to_dt(resolved_ms)

    # Stopper tag removed while the issue was in an unresolved (#unresolved) state.
    resolved_states = resolved_state_map.get(issue_id.split("-")[0], default_resolved_states)
    removed_while_open = any(s not in resolved_states for s in act["stopper_removed_states"])
    # The state the ticket sat in when the tag came off, for the removal breakdown. A removal with
    # no known preceding state still counts as "while unresolved" above, so label it rather than
    # dropping it.
    open_removals = [labelled for raw, labelled
                     in zip(act["stopper_removed_states"], act["removed_states_labelled"])
                     if raw not in resolved_states]
    removed_while_open_state = (next((s for s in open_removals if s), UNKNOWN_STATE_LABEL)
                                if open_removals else "")
    flow = analyze_flow(act["timeline_labels"], removed_while_open)

    tag_dt = act["tag_dt"]
    assumed = tag_dt is None
    if assumed:
        tag_dt = created_dt

    days_to_tag = (tag_dt - created_dt).total_seconds() / 86400
    days_tag_to_resolved = (resolved_dt - tag_dt).total_seconds() / 86400
    days_tag_to_first_fixed = (
        (act["first_fixed_dt"] - tag_dt).total_seconds() / 86400
        if act["first_fixed_dt"] is not None else None
    )

    # End-of-day cutoff (UTC) on the tag-added date — captures values "set within the day".
    eod = tag_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    cutoff_ms = eod.timestamp() * 1000

    cfs = issue.get("_cf", {})
    current_planned = cf_to_str(cfs.get(PLANNED_FOR_FIELD))
    current_fix = next((cf_to_str(cfs[f]) for f in FIX_VERSION_FIELDS if cfs.get(f)), None)

    planned_for = value_at_cutoff(act["planned_for_changes"], cutoff_ms, current_planned)
    if not planned_for:
        planned_for = value_at_cutoff(act["fix_versions_changes"], cutoff_ms, current_fix)

    available_display = [strip_build_suffix(v) for v in cf_to_list(cfs.get(AVAILABLE_IN_FIELD))]
    available_display = [v for v in available_display if v]
    available_lookup = [normalize_for_lookup(v) for v in available_display]

    in_planned = planned_in_available(planned_for, available_lookup)

    oldest = oldest_available(available_lookup, site_releases_map)
    first_avail = oldest[0] if oldest else ""
    first_avail_date = oldest[1] if oldest else None

    # Date for Planned For; fall back to First Available's date if Planned For has no site match.
    site_date = site_releases_map.get(planned_for) if planned_for else None
    if site_date is None:
        site_date = first_avail_date
    planned_for_date = site_date.isoformat() if site_date else ""
    days_tag_to_release = (site_date - tag_dt.date()).days if site_date else None

    tags = [t.get("name") for t in issue.get("tags", []) if t.get("name")]
    votes = cf_to_int(issue.get("votes"))
    support_tickets = cf_to_int(cfs.get(SUPPORT_TICKETS_FIELD))

    return {
        "id": issue_id,
        "project": issue_id.split("-")[0],
        "summary": issue["summary"],
        "subsystem": cf_to_str(cfs.get(SUBSYSTEM_FIELD)) or "",
        "votes": votes,
        "support_tickets": support_tickets,
        "affected_licenses": cf_to_int(cfs.get(AFFECTED_LICENSES_FIELD)),
        "regression": classify_regression(tags, issue["summary"], issue.get("description")),
        "signal": classify_signal(votes, support_tickets),
        "created": created_dt.strftime("%Y-%m-%d"),
        "tag_added": tag_dt.strftime("%Y-%m-%d") + ("*" if assumed else ""),
        "resolved": resolved_dt.strftime("%Y-%m-%d"),
        "days_to_tag": days_to_tag,
        "days_tag_to_resolved": days_tag_to_resolved,
        "days_tag_to_first_fixed": days_tag_to_first_fixed,
        "planned_for": planned_for or "",
        "planned_for_date": planned_for_date,
        "days_tag_to_release": days_tag_to_release,
        "available_in": available_display,
        "in_planned": in_planned,
        "first_available": first_avail,
        "state_history": act["state_history"],
        "removed_while_open": removed_while_open,
        "removed_while_open_state": removed_while_open_state,
        "end_state": flow["end_state"],
        "unclear_states": flow["unclear_states"],
        "reopened": flow["reopened"],
        "tag_after_fixed": flow["tag_after_fixed"],
        "tag_groups": flow["tag_groups"],
        "flow_anomalies": flow["anomalies"],
    }


def format_in_planned(in_planned: bool, planned_for: str, first_available: str) -> str:
    """In Planned cell: blank unless both a planned version and a site-matched first-available exist."""
    if not (planned_for and first_available):
        return ""
    return "YES" if in_planned else "NO"


# --------------------------------------------------------------------------------------
# Rollups (percentiles / volumes)
# --------------------------------------------------------------------------------------

# (label, row key, reversed) — reversed metrics use PERCENTILE(values, 1 - p), see NOTE below.
ROLLUP_METRICS = (
    ("Days to Tag", "days_to_tag", False),
    ("Days Tag to Resolved", "days_tag_to_resolved", False),
    ("Days Tag to First Fixed", "days_tag_to_first_fixed", False),
    ("Days Tag to Release", "days_tag_to_release", True),
)
PERCENTILES = (("25th", 0.25), ("50th (Median)", 0.50), ("75th", 0.75),
               ("90th", 0.90), ("95th", 0.95), ("99th", 0.99))
ALL_PROJECTS = "All"
BLANK_PLANNED_LABEL = "(blank)"
ONE = Decimal(1)
ASSUMED_TAG_NOTE = (
    "An assumed tag date (no tag-add event in history, marked * in the table) forces Days to Tag "
    "to 0. The assumed rate differs by product, so compare Days to Tag on the history-only basis."
)
REVERSED_PERCENTILE_NOTE = (
    "Days Tag to Release uses a reversed percentile threshold: formulas use 1-p, so 90th "
    "means 90% of tickets were tagged at least this many days before release."
)


def percentile_inc(values: list[Decimal], p: Decimal) -> Decimal | None:
    """Linear-interpolated inclusive percentile — matches Google Sheets PERCENTILE/PERCENTILE.INC.

    Interpolates in Decimal: with one-decimal inputs a midpoint like 201.15 stays exact, so it
    rounds the same way the spreadsheet does (binary floats land on 201.1499... and round down).
    """
    s = sorted(values)
    n = len(s)
    if n == 0:
        return None
    if n == 1:
        return s[0]
    rank = p * (n - 1)
    lo = int(rank)
    hi = min(lo + 1, n - 1)
    return s[lo] + (rank - lo) * (s[hi] - s[lo])


def fmt_1dp(value: float | Decimal | None) -> str:
    """One decimal place, rounding halves away from zero (Sheets' ROUND, not Python's)."""
    if value is None:
        return ""
    d = value if isinstance(value, Decimal) else Decimal(repr(float(value)))
    return str(d.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def fmt_share(count: int, total: int) -> str:
    return f"{Decimal(count * 100) / Decimal(total):.1f}%" if total else ""


def rollup_projects(rows: list[dict]) -> list[str]:
    """Column order for rollups: "All", then projects by descending volume."""
    return [ALL_PROJECTS] + [p for p, _ in Counter(r["project"] for r in rows).most_common()]


def metric_values(rows: list[dict], key: str, project: str) -> list[Decimal]:
    """Non-empty values of one metric for one project (or all), as published (rounded to 1dp).

    Rounding before aggregating keeps the percentiles consistent with the per-issue table:
    both are computed from the same one-decimal numbers the report actually shows.
    """
    return [Decimal(fmt_1dp(r[key])) for r in rows
            if (project == ALL_PROJECTS or r["project"] == project) and r[key] is not None]


def build_percentile_table(rows: list[dict]) -> dict:
    """{metric_label: {"reversed": bool, "n": {project: int}, "p": {pct_label: {project: str}}}}."""
    projects = rollup_projects(rows)
    table = {}
    for label, key, is_reversed in ROLLUP_METRICS:
        by_project = {p: metric_values(rows, key, p) for p in projects}
        table[label] = {
            "reversed": is_reversed,
            "n": {p: len(v) for p, v in by_project.items()},
            "p": {
                pct_label: {
                    p: fmt_1dp(percentile_inc(v, ONE - p_dec if is_reversed else p_dec))
                    for p, v in by_project.items()
                }
                for pct_label, p_dec in ((lbl, Decimal(repr(val))) for lbl, val in PERCENTILES)
            },
        }
    return table


def build_volume(rows: list[dict], label_of) -> list[tuple[str, int, str]]:
    """[(label, count, share)] by descending count, for a per-row grouping key."""
    total = len(rows)
    counts = Counter(label_of(r) for r in rows)
    return [(label, count, fmt_share(count, total)) for label, count in counts.most_common()]


def product_volume(rows: list[dict]) -> list[tuple[str, int, str]]:
    return build_volume(rows, lambda r: r["project"])


def planned_version_volume(rows: list[dict]) -> list[tuple[str, int, str]]:
    return build_volume(rows, lambda r: r["planned_for"].strip() or BLANK_PLANNED_LABEL)


def subsystem_label(row: dict) -> str:
    return row["subsystem"].strip() or NO_SUBSYSTEM_LABEL


def crosstab_volume(rows: list[dict], label_of) -> list[tuple[str, int, str, dict[str, int]]]:
    """[(label, total, share, {project: count})] by descending total."""
    total = len(rows)
    per_project: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        per_project[label_of(r)][r["project"]] += 1
    counts = Counter({label: sum(c.values()) for label, c in per_project.items()})
    return [(label, n, fmt_share(n, total), dict(per_project[label])) for label, n in counts.most_common()]


def subsystem_volume(rows: list[dict]) -> list[tuple[str, int, str, dict[str, int]]]:
    """Affected area per Subsystem — the deterministic stand-in for hand-made clusters."""
    return crosstab_volume(rows, subsystem_label)


def top_subsystem_per_project(rows: list[dict]) -> list[tuple[str, int, str, int, str]]:
    """[(project, total tickets, top subsystem, its count, its share within the project)]."""
    out = []
    for project, total in Counter(r["project"] for r in rows).most_common():
        subsystems = Counter(subsystem_label(r) for r in rows if r["project"] == project)
        label, count = subsystems.most_common(1)[0]
        out.append((project, total, label, count, fmt_share(count, total)))
    return out


def regression_rows(rows: list[dict]) -> list[dict]:
    """Stoppers classified as regressions, tag-flagged ones first."""
    return sorted((r for r in rows if r["regression"]),
                  key=lambda r: (r["regression"] != REGRESSION_BY_TAG, r["project"], r["id"]))


def regression_volume(rows: list[dict]) -> list[tuple[str, int, str]]:
    """Regression count and share of all stoppers, split by how it was classified."""
    total = len(rows)
    counts = Counter(r["regression"] for r in rows if r["regression"])
    return [(label, n, fmt_share(n, total)) for label, n in counts.most_common()]


def flow_conformance(rows: list[dict]) -> list[tuple[str, int, str]]:
    """Normal vs not-normal split. Not-normal = at least one flow anomaly."""
    total = len(rows)
    not_normal = sum(1 for r in rows if r["flow_anomalies"])
    return [("Not normal", not_normal, fmt_share(not_normal, total)),
            ("Normal", total - not_normal, fmt_share(total - not_normal, total))]


def flow_anomaly_volume(rows: list[dict]) -> list[tuple[str, int, str]]:
    """Ticket count per anomaly. These overlap — one ticket can carry several."""
    total = len(rows)
    counts = Counter(a for r in rows for a in r["flow_anomalies"])
    return [(name, counts.get(name, 0), fmt_share(counts.get(name, 0), total))
            for name in FLOW_ANOMALIES if counts.get(name)]


def unclear_state_volume(rows: list[dict]) -> list[tuple[str, int, str]]:
    """Tickets that passed through each unclear state (a ticket can appear under several)."""
    total = len(rows)
    counts = Counter(s for r in rows for s in r["unclear_states"])
    return [(state, counts[state], fmt_share(counts[state], total))
            for state, _ in counts.most_common()]


def end_state_volume(rows: list[dict]) -> list[tuple[str, int, str]]:
    """Where tickets finished. Unclear end states are the interesting tail."""
    return build_volume(rows, lambda r: r["end_state"] or UNKNOWN_STATE_LABEL)


def tag_removal_state_volume(rows: list[dict]) -> list[tuple[str, int, str]]:
    """For tags removed while unresolved: the state the ticket sat in at removal."""
    removed = [r for r in rows if r["removed_while_open"]]
    total = len(removed)
    counts = Counter(r["removed_while_open_state"] or UNKNOWN_STATE_LABEL for r in removed)
    return [(state, count, fmt_share(count, total)) for state, count in counts.most_common()]


def planned_vs_available_volume(rows: list[dict]) -> list[tuple[str, int, str]]:
    """Release-planning quality: did the fix ship in the version it was planned for?

    Blank means the question cannot be answered - either no Planned for was set, or no Available in
    entry matched the release calendar - so it is reported rather than folded into "no".
    """
    def label(row):
        verdict = format_in_planned(row["in_planned"], row["planned_for"], row["first_available"])
        return {"YES": "Planned == Available",
                "NO": "Planned != Available"}.get(verdict, "Not comparable")
    return build_volume(rows, label)


def flow_anomaly_rows(rows: list[dict]) -> list[dict]:
    """Tickets that deviated from the expected lifecycle, most anomalies first."""
    return sorted((r for r in rows if r["flow_anomalies"]),
                  key=lambda r: (-len(r["flow_anomalies"]), r["project"], r["id"]))

def signal_rows(rows: list[dict]) -> list[dict]:
    """Stoppers carrying customer signal, strongest first."""
    return sorted((r for r in rows if r["signal"]),
                  key=lambda r: (-r["support_tickets"], -r["votes"], -r["affected_licenses"], r["id"]))


MD_FILE = os.path.join("reports", "release_stoppers.md")
CSV_FILE = os.path.join("reports", "release_stoppers.csv")
PERCENTILES_CSV_FILE = os.path.join("reports", "release_stoppers_percentiles.csv")
PRODUCT_VOLUME_CSV_FILE = os.path.join("reports", "release_stoppers_product_volume.csv")
PLANNED_VOLUME_CSV_FILE = os.path.join("reports", "release_stoppers_planned_versions.csv")
SUBSYSTEM_CSV_FILE = os.path.join("reports", "release_stoppers_subsystems.csv")
REGRESSIONS_CSV_FILE = os.path.join("reports", "release_stoppers_regressions.csv")
WATCHLIST_CSV_FILE = os.path.join("reports", "release_stoppers_watchlist.csv")
COMPARISON_CSV_FILE = os.path.join("reports", "release_stoppers_comparison.csv")


XLSX_FILE = os.path.join("reports", "release_stoppers.xlsx")

# Cell number formats for the workbook. None = General (text or unformatted).
FMT_TEXT = None
FMT_NUM1 = "0.0"
FMT_INT = "0"
FMT_PCT = "0.0%"


def issue_url(issue_id: str) -> str:
    return f"https://youtrack.jetbrains.com/issue/{issue_id}"


def num_or_none(text: str) -> float | None:
    """'201.2' -> 201.2, '' -> None. Input comes from fmt_1dp, so it is always a plain decimal."""
    return float(text) if text else None


def share_value(count: int, total: int) -> float | None:
    """Share as a true fraction, for cells the spreadsheet formats and charts itself."""
    return (count / total) if total else None


ISSUE_TABLE_HEADER = ["Issue", "Project", "Link", "Summary", "Created", "Tag Added", "Resolved",
                      "Days to Tag", "Days Tag to Resolved", "Days Tag to First Fixed",
                      "Planned For", "Planned For Date", "Days Tag to Release", "Available In",
                      "In Planned", "First Available", "State History", "Removed While Open"]
ISSUE_TABLE_FORMATS = ([FMT_TEXT] * 7 + [FMT_NUM1] * 3 + [FMT_TEXT] * 2 + [FMT_INT]
                       + [FMT_TEXT] * 5)


def issue_table_row(r: dict) -> list:
    """One per-issue row, shared by the CSV and workbook writers so they cannot drift.

    Day counts are real numbers rounded to one decimal — the same values the percentiles
    aggregate, so every rendering agrees.
    """
    return [
        r["id"], r["project"], issue_url(r["id"]), r["summary"], r["created"], r["tag_added"],
        r["resolved"],
        num_or_none(fmt_1dp(r["days_to_tag"])),
        num_or_none(fmt_1dp(r["days_tag_to_resolved"])),
        num_or_none(fmt_1dp(r["days_tag_to_first_fixed"])),
        r["planned_for"], r["planned_for_date"], r["days_tag_to_release"],
        ", ".join(r["available_in"]),
        format_in_planned(r["in_planned"], r["planned_for"], r["first_available"]),
        r["first_available"], r["state_history"], "YES" if r["removed_while_open"] else "",
    ]


def write_markdown(rows: list[dict], no_history_count: int):
    os.makedirs("reports", exist_ok=True)
    n = len(rows)
    avg_to_tag = sum(r["days_to_tag"] for r in rows) / n
    avg_tag_to_resolved = sum(r["days_tag_to_resolved"] for r in rows) / n

    with open(MD_FILE, "w", encoding="utf-8") as f:
        f.write("# Release Stoppers Analysis\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}  \n")
        f.write(f"**Search tags:** {', '.join(SEARCH_TAGS)}  \n")
        f.write(f"**Measure tags:** {', '.join(MEASURE_TAGS)}  \n")
        f.write(f"**Resolved date range:** {RESOLVED_DATE_RANGE}  \n")
        f.write(f"**History-scanned projects (tag removed after resolution):** {', '.join(SCAN_PROJECTS)} — {', '.join(SCAN_PRIORITIES)} only  \n\n")
        f.write(f"**Total issues:** {n} | **With tag history:** {n - no_history_count} | **Assumed tagged at creation (\\*):** {no_history_count}\n\n")
        f.write(f"**Average days to tag:** {avg_to_tag:.1f} | **Average days tag to resolved:** {avg_tag_to_resolved:.1f}\n\n")

        f.write("| Issue | Project | Summary | Created | Tag Added | Resolved | Days to Tag | Days Tag to Resolved | Days Tag to First Fixed | Planned For | Planned For Date | Days Tag to Release | Available In | In Planned | First Available | State History | Removed While Open |\n")
        f.write("|---|---|---|---|---|---|---:|---:|---:|---|---|---:|---|:---:|---|---|:---:|\n")
        for r in rows:
            issue_link = md_issue_link(r["id"])
            first_fixed = fmt_1dp(r["days_tag_to_first_fixed"])
            days_to_release = r["days_tag_to_release"] if r["days_tag_to_release"] is not None else ""
            available_in_str = ", ".join(r["available_in"])
            in_planned_str = format_in_planned(r["in_planned"], r["planned_for"], r["first_available"])
            removed = "YES" if r["removed_while_open"] else ""
            f.write(
                f"| {issue_link} | {r['project']} | {r['summary']} | {r['created']} | {r['tag_added']} | {r['resolved']} | "
                f"{fmt_1dp(r['days_to_tag'])} | {fmt_1dp(r['days_tag_to_resolved'])} | {first_fixed} | "
                f"{r['planned_for']} | {r['planned_for_date']} | {days_to_release} | {available_in_str} | "
                f"{in_planned_str} | {r['first_available']} | "
                f"{r['state_history']} | {removed} |\n"
            )
        f.write(f"| **Average** | | | | | | **{avg_to_tag:.1f}** | **{avg_tag_to_resolved:.1f}** | | | | | | | | | |\n")

        write_markdown_rollups(f, rows)

    print(f"Markdown written to {MD_FILE}")


def write_markdown_rollups(f, rows: list[dict]):
    """Percentile and volume rollups, appended after the per-issue table."""
    projects = rollup_projects(rows)
    table = build_percentile_table(rows)

    f.write("\n## Percentiles by metric and project\n\n")
    for label, data in table.items():
        f.write(f"### {label}\n\n")
        f.write("| Percentile | p | " + " | ".join(projects) + " |\n")
        f.write("|---|---:|" + "---:|" * len(projects) + "\n")
        f.write("| Valid N | | " + " | ".join(str(data["n"][p]) for p in projects) + " |\n")
        for pct_label, p_val in PERCENTILES:
            cells = " | ".join(data["p"][pct_label][p] for p in projects)
            f.write(f"| {pct_label} | {p_val:.0%} | {cells} |\n")
        if data["reversed"]:
            f.write(f"\n> **Note:** {REVERSED_PERCENTILE_NOTE}\n")
        f.write("\n")

    n = len(rows)
    f.write("## Product volume\n\n")
    f.write("| Product | Stopper Count | Share |\n|---|---:|---:|\n")
    for product, count, share in product_volume(rows):
        f.write(f"| {product} | {count} | {share} |\n")
    f.write(f"| **Total** | **{n}** | **{fmt_share(n, n)}** |\n\n")

    f.write("## Planned version volume\n\n")
    f.write("| Planned Version | Stopper Count | Share |\n|---|---:|---:|\n")
    for version, count, share in planned_version_volume(rows):
        f.write(f"| {version} | {count} | {share} |\n")
    f.write(f"| **Total** | **{n}** | **{fmt_share(n, n)}** |\n")

    projects_only = [p for p in projects if p != ALL_PROJECTS]

    f.write("\n## Affected area (Subsystem)\n\n")
    write_md_crosstab(f, "Affected area", subsystem_volume(rows), projects_only, n)

    f.write("\n## Top affected area per project\n\n")
    f.write("| Project | Total tickets | Top area | Count | Share within project |\n")
    f.write("|---|---:|---|---:|---:|\n")
    for project, total, label, count, share in top_subsystem_per_project(rows):
        f.write(f"| {project} | {total} | {label} | {count} | {share} |\n")

    regressions = regression_rows(rows)
    f.write(f"\n## Regressions ({len(regressions)} of {n})\n\n")
    f.write("| Classified by | Count | Share of all stoppers |\n|---|---:|---:|\n")
    for label, count, share in regression_volume(rows):
        f.write(f"| {label} | {count} | {share} |\n")
    if regressions:
        f.write("\n### Regressions by affected area\n\n")
        write_md_crosstab(f, "Affected area", subsystem_volume(regressions), projects_only,
                          len(regressions))
        f.write("\n### Regression tickets\n\n")
        f.write("| Issue | Project | Classified by | Affected area | Summary | Created | Resolved | Planned For | Available In |\n")
        f.write("|---|---|---|---|---|---|---|---|---|\n")
        for r in regressions:
            f.write(f"| {md_issue_link(r['id'])} | {r['project']} | {r['regression']} | "
                    f"{subsystem_label(r)} | {r['summary']} | {r['created']} | {r['resolved']} | "
                    f"{r['planned_for']} | {', '.join(r['available_in'])} |\n")

    not_normal = sum(1 for r in rows if r["flow_anomalies"])
    f.write(f"\n## Flow conformance ({not_normal} of {n} outside the expected lifecycle)\n\n")
    f.write("Expected: intake/triage/open/in-progress -> one or more consecutive *Tag added* -> "
            "*Fixed in Branch* / *Fixed* -> optional *Verified* -> optional final *Tag removed*. "
            "A ticket is counted as not normal if it shows at least one of the anomalies below; "
            "the anomalies overlap, so only the conformance split is a partition.\n")
    write_md_blocks(f, flow_blocks(rows))

    watchlist = signal_rows(rows)
    f.write(f"\n## Customer-signal watchlist ({len(watchlist)} of {n})\n\n")
    f.write(f"Stoppers with at least {SUPPORT_SIGNAL_MIN} linked support ticket(s) or "
            f"{VOTES_SIGNAL_MIN} vote(s). *QA note* and *Initial classification* are left blank "
            f"for manual review.\n\n")
    f.write("| Signal | Issue | Project | Affected area | Summary | Created | Resolved | "
            "Available In | Support tickets | Affected licenses | Votes | QA note | Initial classification |\n")
    f.write("|---|---|---|---|---|---|---|---|---:|---:|---:|---|---|\n")
    for r in watchlist:
        f.write(f"| {r['signal']} | {md_issue_link(r['id'])} | {r['project']} | {subsystem_label(r)} | "
                f"{r['summary']} | {r['created']} | {r['resolved']} | {', '.join(r['available_in'])} | "
                f"{r['support_tickets']} | {r['affected_licenses']} | {r['votes']} | | |\n")


def cell_text(value, number_format=None) -> str:
    """Render a block cell as text for Markdown/CSV, honouring the column's number format."""
    if value is None or value == "":
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if number_format == FMT_PCT:
            return f"{Decimal(repr(value * 100)).quantize(Decimal('0.1'), ROUND_HALF_UP)}%"
        if number_format == FMT_NUM1:
            return fmt_1dp(value)
    return str(value)


def write_md_blocks(f, blocks, heading_level: int = 3):
    """Render (caption, header, rows, formats) blocks as Markdown tables."""
    hashes = "#" * heading_level
    for caption, header, data_rows, formats in blocks:
        if caption:
            f.write(f"\n{hashes} {caption}\n\n")
        else:
            f.write("\n")
        f.write("| " + " | ".join(header) + " |\n")
        f.write("|" + "".join("---:|" if fmt in (FMT_NUM1, FMT_INT, FMT_PCT) else "---|"
                              for fmt in formats) + "\n")
        for row in data_rows:
            padded = list(row) + [None] * (len(header) - len(row))
            f.write("| " + " | ".join(cell_text(v, fmt) for v, fmt in zip(padded, formats)) + " |\n")


def write_csv_blocks(path: str, blocks):
    """Write blocks to one CSV, stacked with a blank line between them."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for index, (caption, header, data_rows, formats) in enumerate(blocks):
            if index:
                writer.writerow([])
            if caption:
                writer.writerow([caption])
            writer.writerow(header)
            for row in data_rows:
                padded = list(row) + [None] * (len(header) - len(row))
                writer.writerow([cell_text(v, fmt) for v, fmt in zip(padded, formats)])
    print(f"CSV written to {path}")


INVALID_SHEET_CHARS = str.maketrans({c: '-' for c in '[]:*?/' + chr(92)})


def sheet_name(title: str) -> str:
    """Excel rejects [ ] : * ? / and backslash in sheet names, and caps them at 31 chars."""
    return title.translate(INVALID_SHEET_CHARS)[:31]

def md_issue_link(issue_id: str) -> str:
    return f"[{issue_id}]({issue_url(issue_id)})"


def write_md_crosstab(f, label_header: str, volume, projects: list[str], total: int):
    """Label | Total | Share | one column per project."""
    f.write(f"| {label_header} | Total | Share | " + " | ".join(projects) + " |\n")
    f.write("|---|---:|---:|" + "---:|" * len(projects) + "\n")
    for label, count, share, per_project in volume:
        cells = " | ".join(str(per_project.get(p, 0)) for p in projects)
        f.write(f"| {label} | {count} | {share} | {cells} |\n")
    f.write(f"| **Total** | **{total}** | **{fmt_share(total, total)}** | "
            + " | ".join("" for _ in projects) + " |\n")


FLOW_CSV_FILE = os.path.join("reports", "release_stoppers_flow.csv")


def flow_blocks(rows: list[dict]) -> list[tuple]:
    """The flow-conformance tables as (caption, header, rows, formats) blocks.

    Denominators differ by table and are named in each header: the anomaly and state tables are
    shares of all tickets, the removal breakdown is a share of removals only.
    """
    total = len(rows)
    removals = sum(1 for r in rows if r["removed_while_open"])
    count_formats = [FMT_TEXT, FMT_INT, FMT_PCT]

    def counted(caption, label_header, share_header, volume, denominator):
        return (caption, [label_header, "Tickets", share_header],
                [[label, count, share_value(count, denominator)] for label, count, _ in volume],
                count_formats)

    anomalies = flow_anomaly_rows(rows)
    blocks = [
        counted("Flow conformance", "Flow", "Share", flow_conformance(rows), total),
        counted("Anomalies (overlapping — a ticket can carry several)", "Anomaly",
                "Share of all tickets", flow_anomaly_volume(rows), total),
        counted("Unclear ticket states passed through", "State", "Share of all tickets",
                unclear_state_volume(rows), total),
        counted("End state", "End state", "Share of all tickets", end_state_volume(rows), total),
        counted("Tag removed while unresolved — state at removal", "Previous state",
                "Share of removals", tag_removal_state_volume(rows), removals),
        counted("Planned vs Available", "Verdict", "Share of all tickets",
                planned_vs_available_volume(rows), total),
    ]
    if anomalies:
        blocks.append((
            "Tickets outside the expected flow",
            ["Issue", "Project", "Anomalies", "Anomaly count", "End state", "Unclear states",
             "Tag added groups", "Reopened", "Tag after first fix", "Summary", "State History"],
            [[r["id"], r["project"], "; ".join(r["flow_anomalies"]), len(r["flow_anomalies"]),
              r["end_state"], ", ".join(r["unclear_states"]), r["tag_groups"],
              "YES" if r["reopened"] else "", "YES" if r["tag_after_fixed"] else "",
              r["summary"], r["state_history"]] for r in anomalies],
            [FMT_TEXT] * 3 + [FMT_INT] + [FMT_TEXT] * 2 + [FMT_INT] + [FMT_TEXT] * 4,
        ))
    return blocks


def write_flow_csv(rows: list[dict]):
    write_csv_blocks(FLOW_CSV_FILE, flow_blocks(rows))


def print_flow(rows: list[dict]):
    total = len(rows)
    not_normal = sum(1 for r in rows if r["flow_anomalies"])
    print(f"\nFlow conformance: {not_normal} of {total} tickets deviate from the expected "
          f"lifecycle ({fmt_share(not_normal, total)})")
    for label, count, share in flow_anomaly_volume(rows):
        print(f"    {label:<40}{count:>5}{share:>8}")
    if any(r["removed_while_open"] for r in rows):
        print("  Tag removed while unresolved, by state at removal:")
        for label, count, share in tag_removal_state_volume(rows)[:8]:
            print(f"    {label:<40}{count:>5}{share:>8}")
    print("  Planned vs Available:")
    for label, count, share in planned_vs_available_volume(rows):
        print(f"    {label:<40}{count:>5}{share:>8}")

def write_comparison(rows: list[dict], cohorts: dict[str, list[dict]]):
    """Append the cross-product comparison to the report and write it as its own CSV."""
    blocks = comparison_blocks({DOTNET_COHORT_NAME: rows, **cohorts})
    with open(MD_FILE, "a", encoding="utf-8") as f:
        f.write("\n## Cross-product comparison\n\n")
        f.write("Other JetBrains products measured over the same window "
                f"(`{RESOLVED_DATE_RANGE}`) with the same metric definitions, each against its "
                "own product's release calendar.\n")
        for cohort in COMPARISON_COHORTS:
            if cohort.name in cohorts and cohort.note:
                f.write(f"\n- **{cohort.name}** - {cohort.note}\n")
        write_md_blocks(f, blocks)
    print(f"Comparison appended to {MD_FILE}")
    write_csv_blocks(COMPARISON_CSV_FILE, blocks)


def write_rollup_csvs(rows: list[dict]):
    """One CSV per rollup, shaped for pasting into the tracking spreadsheet's tabs."""
    projects = rollup_projects(rows)
    table = build_percentile_table(rows)

    with open(PERCENTILES_CSV_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Metric", "Percentile", "p"] + projects)
        for label, data in table.items():
            writer.writerow([label, "Valid N", ""] + [data["n"][p] for p in projects])
            for pct_label, p_val in PERCENTILES:
                writer.writerow([label, pct_label, f"{p_val:.0%}"]
                                + [data["p"][pct_label][p] for p in projects])
        writer.writerow([])
        writer.writerow(["Note", REVERSED_PERCENTILE_NOTE])
    print(f"CSV written to {PERCENTILES_CSV_FILE}")

    n = len(rows)
    for path, header, data in (
        (PRODUCT_VOLUME_CSV_FILE, "Product", product_volume(rows)),
        (PLANNED_VOLUME_CSV_FILE, "Planned Version", planned_version_volume(rows)),
    ):
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([header, "Stopper Count", "Share"])
            writer.writerows(data)
            writer.writerow(["Total", n, fmt_share(n, n)])
        print(f"CSV written to {path}")

    projects_only = [p for p in projects if p != ALL_PROJECTS]
    with open(SUBSYSTEM_CSV_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Affected area", "Total", "Share"] + projects_only)
        for label, count, share, per_project in subsystem_volume(rows):
            writer.writerow([label, count, share] + [per_project.get(p, 0) for p in projects_only])
        writer.writerow(["Total", n, fmt_share(n, n)])
        writer.writerow([])
        writer.writerow(["Project", "Total tickets", "Top area", "Top area count",
                         "Top area share within project"])
        writer.writerows(top_subsystem_per_project(rows))
    print(f"CSV written to {SUBSYSTEM_CSV_FILE}")

    with open(REGRESSIONS_CSV_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Classified by", "Count", "Share of all stoppers"])
        writer.writerows(regression_volume(rows))
        writer.writerow([])
        writer.writerow(["Issue", "Project", "Link", "Classified by", "Affected area", "Summary",
                         "Created", "Resolved", "Planned For", "Available In"])
        for r in regression_rows(rows):
            writer.writerow([r["id"], r["project"], issue_url(r["id"]), r["regression"],
                             subsystem_label(r), r["summary"], r["created"], r["resolved"],
                             r["planned_for"], ", ".join(r["available_in"])])
    print(f"CSV written to {REGRESSIONS_CSV_FILE}")

    with open(WATCHLIST_CSV_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Signal", "Issue", "Project", "Link", "Affected area", "Summary",
                         "Created", "Resolved", "Available In", "Support tickets",
                         "Affected licenses", "Votes", "QA note", "Initial classification"])
        for r in signal_rows(rows):
            writer.writerow([r["signal"], r["id"], r["project"], issue_url(r["id"]),
                             subsystem_label(r), r["summary"], r["created"], r["resolved"],
                             ", ".join(r["available_in"]), r["support_tickets"],
                             r["affected_licenses"], r["votes"], "", ""])
    print(f"CSV written to {WATCHLIST_CSV_FILE}")


def write_csv(rows: list[dict]):
    with open(CSV_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(ISSUE_TABLE_HEADER)
        writer.writerows(issue_table_row(r) for r in rows)
    print(f"CSV written to {CSV_FILE}")


# --------------------------------------------------------------------------------------
# Comparison cohorts (other JetBrains products, same window and metric definitions)
# --------------------------------------------------------------------------------------

class ComparisonCohort(NamedTuple):
    """Another product's release blockers, measured the same way for a like-for-like read."""
    name: str
    query: str                    # YouTrack query; RESOLVED_CLAUSE is appended
    vocabulary: TagVocabulary
    product_code: str             # which release calendar dates Days Tag to Release
    note: str = ""


DOTNET_COHORT_NAME = "dotnet"
COMPARISON_COHORTS = (
    ComparisonCohort(
        name="IJPL+JBR",
        query="project: IJPL, JBR tag: blocking-release, blocking-release-idea",
        vocabulary=TagVocabulary.of(measure=("blocking-release", "blocking-release-idea")),
        product_code="IIU",
        note="IntelliJ platform + JetBrains Runtime; ships on the IDEA calendar, not ReSharper's.",
    ),
)

# Percentiles are reported on two bases. An assumed tag date (no tag-add event in history) forces
# Days to Tag to 0, and the assumed rate differs sharply between products, so the history-only
# basis is the fair one for that metric.
COMPARISON_BASES = (("all rows", False), ("tag date in history only", True))


def cohort_issue_query(cohort: ComparisonCohort) -> str:
    return f"{cohort.query} {RESOLVED_CLAUSE}"


def fetch_cohort_issues(cohort: ComparisonCohort) -> list[dict]:
    """All issues matching a cohort's query, paginated (these sets can exceed one page)."""
    result, skip = [], 0
    while True:
        response = client.get(
            f"{YOUTRACK_URL}/issues",
            params={"fields": ISSUE_FIELDS, "query": cohort_issue_query(cohort),
                    "$top": 1000, "$skip": skip},
        )
        response.raise_for_status()
        chunk = response.json()
        for issue in chunk:
            issue["_cf"] = {f.get("name"): f.get("value") for f in issue.get("customFields", [])}
            result.append(issue)
        if len(chunk) < 1000:
            return result
        skip += 1000


def build_cohort_rows(cohort: ComparisonCohort, resolved_state_map: dict[str, set[str]],
                      default_resolved_states: set[str]) -> list[dict]:
    """Fetch and measure one comparison cohort. Every issue matched the tag query, so all qualify."""
    issues = fetch_cohort_issues(cohort)
    print(f"  {cohort.name}: {len(issues)} issues matched")
    calendar = get_release_calendar(cohort.product_code)
    activities = fetch_all_activities([i["idReadable"] for i in issues], cohort.vocabulary)
    rows = []
    for issue in issues:
        row = compute_row(issue, activities[issue["idReadable"]], calendar,
                          resolved_state_map, default_resolved_states, True)
        if row is not None:
            rows.append(row)
    assumed = sum(1 for r in rows if r["tag_added"].endswith("*"))
    print(f"  {cohort.name}: {len(rows)} rows ({len(rows) - assumed} with tag history, "
          f"{assumed} assumed at creation)")
    return rows


def history_only(rows: list[dict]) -> list[dict]:
    """Rows whose tag date came from activity history, i.e. Days to Tag is really measured."""
    return [r for r in rows if not r["tag_added"].endswith("*")]


def cohort_summary_block(cohorts: dict[str, list[dict]]) -> tuple:
    header = ["Cohort", "Issues", "With tag history", "Assumed at creation", "Assumed %",
              "Release calendar", "Query"]
    by_name = {c.name: c for c in COMPARISON_COHORTS}
    data = []
    for name, rows in cohorts.items():
        cohort = by_name.get(name)
        kept = len(history_only(rows))
        assumed = len(rows) - kept
        data.append([name, len(rows), kept, assumed, share_value(assumed, len(rows)),
                     cohort.product_code if cohort else PRODUCT_CODE,
                     cohort_issue_query(cohort) if cohort else
                     f"tag: {', '.join(SEARCH_TAGS)} {RESOLVED_CLAUSE} (+ history scan of "
                     f"{', '.join(SCAN_PROJECTS)})"])
    return ("Cohorts", header, data,
            [FMT_TEXT, FMT_INT, FMT_INT, FMT_INT, FMT_PCT, FMT_TEXT, FMT_TEXT])


def comparison_blocks(cohorts: dict[str, list[dict]]) -> list[tuple]:
    """Percentile comparison as (caption, header, rows, formats) blocks.

    One block per metric; a column per cohort per basis, so the assumed-tag artifact is visible
    side by side instead of hidden in a single number.
    """
    columns = [(name, basis_label, drop_assumed)
               for name in cohorts
               for basis_label, drop_assumed in COMPARISON_BASES]
    tables = {(name, label): build_percentile_table(history_only(rows) if drop else rows)
              for name, rows in cohorts.items()
              for label, drop in COMPARISON_BASES}

    blocks = [cohort_summary_block(cohorts)]
    header = ["Percentile"] + [f"{name} ({label})" for name, label, _ in columns]
    formats = [FMT_TEXT] + [FMT_NUM1] * len(columns)
    for metric, _, is_reversed in ROLLUP_METRICS:
        caption = metric + ("   (reversed: percentiles use 1-p)" if is_reversed else "")
        data = [["Valid N"] + [tables[(n, l)][metric]["n"][ALL_PROJECTS] for n, l, _ in columns]]
        data += [[label] + [num_or_none(tables[(n, l)][metric]["p"][label][ALL_PROJECTS])
                            for n, l, _ in columns]
                 for label, _ in PERCENTILES]
        blocks.append((caption, header, data, formats))
    blocks.append((None, ["Note"], [[REVERSED_PERCENTILE_NOTE], [ASSUMED_TAG_NOTE]], [FMT_TEXT]))
    return blocks

def xlsx_sheets(rows: list[dict],
                cohorts: dict[str, list[dict]] | None = None) -> list[tuple[str, list[tuple]]]:
    """Workbook layout: [(sheet title, [(caption, header, data rows, column formats), ...])].

    Pure — no openpyxl needed, so the layout is testable on its own. Tabs mirror the tracking
    spreadsheet; shares and day counts are real numbers so the spreadsheet can chart them.
    """
    n = len(rows)
    projects = rollup_projects(rows)
    projects_only = [p for p in projects if p != ALL_PROJECTS]

    percentile_blocks = []
    for metric, data in build_percentile_table(rows).items():
        caption = metric + (" (reversed: percentiles use 1-p)" if data["reversed"] else "")
        block_rows = [["Valid N", ""] + [data["n"][p] for p in projects]]
        block_rows += [[label, f"{p_val:.0%}"] + [num_or_none(data["p"][label][p]) for p in projects]
                       for label, p_val in PERCENTILES]
        percentile_blocks.append((caption, ["Percentile", "p"] + projects, block_rows,
                                  [FMT_TEXT, FMT_TEXT] + [FMT_NUM1] * len(projects)))
    percentile_blocks.append((None, ["Note"], [[REVERSED_PERCENTILE_NOTE]], [FMT_TEXT]))

    def volume_block(label_header, volume):
        return (None, [label_header, "Stopper Count", "Share"],
                [[label, count, share_value(count, n)] for label, count, _ in volume]
                + [["Total", n, share_value(n, n)]],
                [FMT_TEXT, FMT_INT, FMT_PCT])

    def crosstab_block(volume, total):
        return (None, ["Affected area", "Total", "Share"] + projects_only,
                [[label, count, share_value(count, total)]
                 + [per_project.get(p, 0) for p in projects_only]
                 for label, count, _, per_project in volume],
                [FMT_TEXT, FMT_INT, FMT_PCT] + [FMT_INT] * len(projects_only))

    regressions = regression_rows(rows)
    regression_blocks = [
        (None, ["Classified by", "Count", "Share of all stoppers"],
         [[label, count, share_value(count, n)] for label, count, _ in regression_volume(rows)],
         [FMT_TEXT, FMT_INT, FMT_PCT]),
    ]
    if regressions:
        regression_blocks.append(("Regressions by affected area",
                                  *crosstab_block(subsystem_volume(regressions), len(regressions))[1:]))
        regression_blocks.append((
            "Regression tickets",
            ["Issue", "Project", "Link", "Classified by", "Affected area", "Summary", "Created",
             "Resolved", "Planned For", "Available In"],
            [[r["id"], r["project"], issue_url(r["id"]), r["regression"], subsystem_label(r),
              r["summary"], r["created"], r["resolved"], r["planned_for"],
              ", ".join(r["available_in"])] for r in regressions],
            [FMT_TEXT] * 10,
        ))

    watchlist = signal_rows(rows)
    return [
        ("Release stoppers", [(None, ISSUE_TABLE_HEADER,
                               [issue_table_row(r) for r in rows], ISSUE_TABLE_FORMATS)]),
        ("Percentiles", percentile_blocks),
        ("Product volume", [volume_block("Product", product_volume(rows))]),
        ("Planned versions", [volume_block("Planned Version", planned_version_volume(rows))]),
        ("Affected areas", [
            crosstab_block(subsystem_volume(rows), n),
            ("Top affected area per project",
             ["Project", "Total tickets", "Top area", "Top area count", "Share within project"],
             [[project, total, label, count, share_value(count, total)]
              for project, total, label, count, _ in top_subsystem_per_project(rows)],
             [FMT_TEXT, FMT_INT, FMT_TEXT, FMT_INT, FMT_PCT]),
        ]),
        ("Regressions", regression_blocks),
        ("Watchlist", [(
            f"Signal: >= {SUPPORT_SIGNAL_MIN} support ticket(s) or >= {VOTES_SIGNAL_MIN} vote(s). "
            f"QA note / Initial classification are left blank for manual review.",
            ["Signal", "Issue", "Project", "Link", "Affected area", "Summary", "Created",
             "Resolved", "Available In", "Support tickets", "Affected licenses", "Votes",
             "QA note", "Initial classification"],
            [[r["signal"], r["id"], r["project"], issue_url(r["id"]), subsystem_label(r),
              r["summary"], r["created"], r["resolved"], ", ".join(r["available_in"]),
              r["support_tickets"], r["affected_licenses"], r["votes"], "", ""]
             for r in watchlist],
            [FMT_TEXT] * 9 + [FMT_INT] * 3 + [FMT_TEXT] * 2,
        )]),
        ("Flow", flow_blocks(rows)),
    ] + comparison_sheets(rows, cohorts)


def comparison_sheets(rows: list[dict],
                      cohorts: dict[str, list[dict]] | None) -> list[tuple[str, list[tuple]]]:
    """The Comparison tab plus one raw-data tab per comparison cohort (empty if none were run)."""
    if not cohorts:
        return []
    combined = {DOTNET_COHORT_NAME: rows, **cohorts}
    sheets = [("Comparison", comparison_blocks(combined))]
    for name, cohort_rows in cohorts.items():
        sheets.append((sheet_name(name), [(None, ISSUE_TABLE_HEADER,
                                           [issue_table_row(r) for r in cohort_rows],
                                           ISSUE_TABLE_FORMATS)]))
    return sheets


def write_xlsx(rows: list[dict], cohorts: dict[str, list[dict]] | None = None):
    """One workbook, one tab per rollup. Skipped with a note if openpyxl isn't installed."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font
        from openpyxl.utils import get_column_letter
    except ImportError:
        print(f"Skipping {XLSX_FILE}: openpyxl is not installed (pip install openpyxl)")
        return

    bold = Font(bold=True)
    caption_font = Font(bold=True, italic=True)
    link_font = Font(color="0563C1", underline="single")

    wb = Workbook()
    wb.remove(wb.active)
    for title, blocks in xlsx_sheets(rows, cohorts):
        ws = wb.create_sheet(title[:31])  # Excel caps sheet names at 31 chars
        widths: dict[int, int] = {}
        freeze_at = None
        for index, (caption, header, data_rows, formats) in enumerate(blocks):
            if index:
                ws.append([])  # blank spacer between stacked blocks
                # NB: don't probe ws["A1"] to detect emptiness — reading a cell creates it,
                # which would push the first block down a row.
            if caption:
                ws.append([caption])
                ws.cell(row=ws.max_row, column=1).font = caption_font
            ws.append(header)
            for cell in ws[ws.max_row]:
                cell.font = bold
                cell.alignment = Alignment(vertical="top", wrap_text=True)
            if freeze_at is None:
                freeze_at = ws.max_row + 1
            for data_row in data_rows:
                ws.append(data_row)
                for col, (value, number_format) in enumerate(zip(data_row, formats), start=1):
                    cell = ws.cell(row=ws.max_row, column=col)
                    if number_format and isinstance(value, (int, float)):
                        cell.number_format = number_format
                    if isinstance(value, str) and value.startswith("https://"):
                        cell.hyperlink = value
                        cell.font = link_font
            for row in [header] + list(data_rows):
                for col, value in enumerate(row, start=1):
                    widths[col] = max(widths.get(col, 0), len(str(value if value is not None else "")))
        for col, width in widths.items():
            ws.column_dimensions[get_column_letter(col)].width = min(max(width + 2, 9), 60)
        if freeze_at:
            ws.freeze_panes = f"A{freeze_at}"

    wb.save(XLSX_FILE)
    print(f"Workbook written to {XLSX_FILE} ({len(wb.sheetnames)} tabs)")


def main(compare: bool = False):
    # Path A: issues that currently carry a stopper tag (always qualify).
    print(f"Fetching resolved issues tagged {SEARCH_TAGS}...")
    issues = fetch_issues()
    tagged_ids = {issue["idReadable"] for issue in issues}
    print(f"Found {len(issues)} currently-tagged issues.")

    # Path B: SCAN_PROJECTS strip the tag after resolution — scan history instead.
    print(f"Fetching {SCAN_PRIORITIES} candidates in {SCAN_PROJECTS}...")
    candidates = fetch_priority_candidates()
    added = 0
    for issue in candidates:
        if issue["idReadable"] not in tagged_ids:
            issues.append(issue)
            added += 1
    print(f"Found {len(candidates)} candidates ({added} not already tagged).\n")

    print("Fetching ReSharper release versions...")
    site_releases_map = build_release_calendar(dict(get_version_dates()), verbose=True)

    print("Fetching per-project resolved states...")
    resolved_state_map = fetch_resolved_state_map()
    # Fallback for projects missing from the map: union of resolved states across known projects.
    default_resolved_states = set().union(*resolved_state_map.values()) if resolved_state_map else set()
    print(f"Loaded resolved states for {len(resolved_state_map)} projects.\n")

    print(f"Fetching activities for {len(issues)} issues (parallel)...")
    activities = fetch_all_activities([issue["idReadable"] for issue in issues])

    rows = []
    for issue in issues:
        issue_id = issue["idReadable"]
        if not issue.get("created") or not issue.get("resolved"):
            print(f"  [SKIP] {issue_id}: missing created or resolved timestamp")
            continue
        row = compute_row(
            issue, activities[issue_id], site_releases_map,
            resolved_state_map, default_resolved_states, issue_id in tagged_ids,
        )
        if row is not None:
            rows.append(row)

    if not rows:
        print("No data to display.")
        return

    rows.sort(key=lambda r: r["days_to_tag"], reverse=True)

    col_id   = max(len(r["id"]) for r in rows) + 2
    col_proj = max(max(len(r["project"]) for r in rows), len("Project")) + 2
    col_sum  = min(max(len(r["summary"]) for r in rows), 40) + 2
    col_tag  = max(max(len(r["tag_added"]) for r in rows), len("Tag Added")) + 2
    col_pf   = max(max(len(r["planned_for"]) for r in rows), len("Planned For")) + 2
    col_fa   = max(max(len(r["first_available"]) for r in rows), len("First Avail.")) + 2
    col_date = 12
    col_days = 14
    col_flag = 8
    col_yn   = 12

    header = (
        f"{'Issue':<{col_id}}"
        f"{'Project':<{col_proj}}"
        f"{'Summary':<{col_sum}}"
        f"{'Created':<{col_date}}"
        f"{'Tag Added':<{col_tag}}"
        f"{'Resolved':<{col_date}}"
        f"{'Days to Tag':>{col_days}}"
        f"{'Days to Res.':>{col_days}}"
        f"{'Days to Fix':>{col_days}}"
        f"  {'Planned For':<{col_pf}}"
        f"{'Planned Date':<14}"
        f"{'Days to Rel.':>{col_days}}"
        f"  {'In Planned':<{col_yn}}"
        f"{'First Avail.':<{col_fa}}"
        f"{'Rem.?':>{col_flag}}"
    )
    separator = "-" * len(header)
    print(f"\n{header}")
    print(separator)

    no_history_count = sum(1 for r in rows if r["tag_added"].endswith("*"))
    for r in rows:
        first_fixed_str = f"{r['days_tag_to_first_fixed']:.1f}" if r["days_tag_to_first_fixed"] is not None else "N/A"
        days_to_rel_str = str(r["days_tag_to_release"]) if r["days_tag_to_release"] is not None else "N/A"
        in_planned_str = format_in_planned(r["in_planned"], r["planned_for"], r["first_available"])
        removed_str = "YES" if r["removed_while_open"] else ""
        print(
            f"{r['id']:<{col_id}}"
            f"{r['project']:<{col_proj}}"
            f"{r['summary'][:col_sum - 2]:<{col_sum}}"
            f"{r['created']:<{col_date}}"
            f"{r['tag_added']:<{col_tag}}"
            f"{r['resolved']:<{col_date}}"
            f"{r['days_to_tag']:>{col_days}.1f}"
            f"{r['days_tag_to_resolved']:>{col_days}.1f}"
            f"{first_fixed_str:>{col_days}}"
            f"  {r['planned_for']:<{col_pf}}"
            f"{r['planned_for_date']:<14}"
            f"{days_to_rel_str:>{col_days}}"
            f"  {in_planned_str:<{col_yn}}"
            f"{r['first_available']:<{col_fa}}"
            f"{removed_str:>{col_flag}}"
        )

    n = len(rows)
    avg_to_tag = sum(r["days_to_tag"] for r in rows) / n
    avg_tag_to_resolved = sum(r["days_tag_to_resolved"] for r in rows) / n
    print(separator)
    print(
        f"{'Average':<{col_id + col_proj + col_sum + col_date + col_tag + col_date}}"
        f"{avg_to_tag:>{col_days}.1f}"
        f"{avg_tag_to_resolved:>{col_days}.1f}"
    )
    print(f"\nTotal: {n}  |  With tag history: {n - no_history_count}  |  Assumed tagged at creation (*): {no_history_count}")
    removed_count = sum(1 for r in rows if r["removed_while_open"])
    if removed_count:
        print(f"Stopper tag removed while unresolved: {removed_count} issue(s)")

    print_rollups(rows)
    print_flow(rows)

    cohorts = {}
    if compare and COMPARISON_COHORTS:
        print(f"\nFetching {len(COMPARISON_COHORTS)} comparison cohort(s)...")
        for cohort in COMPARISON_COHORTS:
            cohort_rows = build_cohort_rows(cohort, resolved_state_map, default_resolved_states)
            if cohort_rows:
                cohorts[cohort.name] = cohort_rows
        if cohorts:
            print_comparison(rows, cohorts)

    write_markdown(rows, no_history_count)
    write_csv(rows)
    write_rollup_csvs(rows)
    write_flow_csv(rows)
    if cohorts:
        write_comparison(rows, cohorts)
    write_xlsx(rows, cohorts)


def print_comparison(rows: list[dict], cohorts: dict[str, list[dict]]):
    for caption, header, data_rows, formats in comparison_blocks(
            {DOTNET_COHORT_NAME: rows, **cohorts}):
        if caption == "Cohorts":
            print("\nCohorts")
            for row in data_rows:
                print(f"    {row[0]:<12}n={row[1]:<6}history={row[2]:<6}assumed={row[3]} "
                      f"({cell_text(row[4], FMT_PCT)})")
            continue
        if caption is None:
            continue
        print(f"\n{caption}")
        widths = [max(12, len(h) + 2) for h in header[1:]]
        print(f"    {'':<16}" + "".join(f"{h:>{w}}" for h, w in zip(header[1:], widths)))
        for row in data_rows:
            cells = "".join(f"{cell_text(v, f):>{w}}"
                            for v, f, w in zip(row[1:], formats[1:], widths))
            print(f"    {row[0]:<16}{cells}")


def print_rollups(rows: list[dict]):
    projects = rollup_projects(rows)
    table = build_percentile_table(rows)
    width = 10

    print("\nPercentiles by metric and project")
    for label, data in table.items():
        print(f"\n  {label}{'  (reversed: 1-p)' if data['reversed'] else ''}")
        print(f"    {'':<14}" + "".join(f"{p:>{width}}" for p in projects))
        print(f"    {'Valid N':<14}" + "".join(f"{data['n'][p]:>{width}}" for p in projects))
        for pct_label, _ in PERCENTILES:
            cells = "".join(f"{data['p'][pct_label][p]:>{width}}" for p in projects)
            print(f"    {pct_label:<14}{cells}")
    print(f"\n  Note: {REVERSED_PERCENTILE_NOTE}")

    n = len(rows)
    for title, volume in (("Product volume", product_volume(rows)),
                          ("Planned version volume", planned_version_volume(rows)),
                          ("Regressions", regression_volume(rows))):
        print(f"\n{title}")
        for label, count, share in volume:
            print(f"    {label:<24}{count:>6}{share:>9}")
        if title != "Regressions":
            print(f"    {'Total':<24}{n:>6}{fmt_share(n, n):>9}")

    print("\nAffected area (Subsystem) — top 10")
    for label, count, share, _ in subsystem_volume(rows)[:10]:
        print(f"    {label[:40]:<42}{count:>6}{share:>9}")

    print("\nTop affected area per project")
    for project, total, label, count, share in top_subsystem_per_project(rows):
        print(f"    {project:<8}{total:>6}  {label[:40]:<42}{count:>6}{share:>9}")

    watchlist = signal_rows(rows)
    print(f"\nCustomer-signal watchlist: {len(watchlist)} of {n} "
          f"(>= {SUPPORT_SIGNAL_MIN} support ticket(s) or >= {VOTES_SIGNAL_MIN} vote(s))")
    for r in watchlist[:15]:
        print(f"    {r['signal']:<15}{r['id']:<16}support={r['support_tickets']:<4}"
              f"votes={r['votes']:<5}licenses={r['affected_licenses']}")
    if len(watchlist) > 15:
        print(f"    ... {len(watchlist) - 15} more (see {WATCHLIST_CSV_FILE})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--compare", action="store_true",
                        help="also measure the comparison cohorts (%s) and add the "
                             "cross-product comparison to the report; roughly doubles runtime"
                             % ", ".join(c.name for c in COMPARISON_COHORTS))
    main(**vars(parser.parse_args()))
