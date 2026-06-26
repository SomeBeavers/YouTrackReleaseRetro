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

Two discovery paths feed the report:
  A. Issues that currently carry a stopper tag (SEARCH_TAGS) — works for ReSharper/Rider.
  B. SCAN_PROJECTS (dotMemory/dotTrace/DPA/Profiler) strip the stopper tag once the issue is
     resolved, so the current-tag query misses them. For these we scan all resolved
     Show-Stopper/Critical issues and keep the ones whose activity history shows a
     release-stopper tag was *added* at some point.

* next to a date means tag addition was not found in activity history;
  issue creation date is used as a fallback.
"""

import csv
import os
import re
import requests
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

from release_versions import get_version_dates

YOUTRACK_URL = "https://youtrack.jetbrains.com/api"
TOKEN = os.getenv("YOUTRACK_TOKEN")
RESOLVED_DATE_RANGE = "2025-01-01 .. today"
SEARCH_TAGS = ["dotnet-ex-release-stopper", "rider-ex-stopper"]
MEASURE_TAGS = ["dotnet-release-stopper", "rider-release-stopper"]
MEASURE_TAGS_FALLBACK = ["rider-ex-stopper", "dotnet-ex-release-stopper"]
RIDER_RELEASE_STOPPER_TAG = "rider-release-stopper"

# Projects that remove the stopper tag after an issue is resolved, so the current-tag query
# (SEARCH_TAGS) misses them. Discovered instead by scanning activity history (Path B).
SCAN_PROJECTS = ["DMRY", "DTRC", "DPA", "PROF"]
SCAN_PRIORITIES = ["Show-Stopper", "Critical"]
# Any of these tags being *added* in history => the issue was treated as a release stopper.
STOPPER_TAGS = set(SEARCH_TAGS) | set(MEASURE_TAGS)
FIXED_STATES = {"Fixed", "Verified"}
PLANNED_FOR_FIELD = "Planned for"
FIX_VERSION_FIELDS = ("Fix versions", "Fixed in build")
AVAILABLE_IN_FIELD = "Available in"
BUILD_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")
NEXT_PUBLIC_BUILD_RE = re.compile(r"^Next\s+(\d+(?:\.\d+)*)\s+public build$", re.IGNORECASE)
EAP_RC_RE = re.compile(r"^(\d+(?:\.\d+)*)\s+(EAP|RC)\s+(\d+)$", re.IGNORECASE)

# Planned GA dates not yet on jetbrains.com/resharper/download/other/. Merged into the site map.
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
    """True if any cleaned Available in entry version-prefix-matches the planned version."""
    if not planned:
        return False
    for av in available_clean:
        if av.startswith(planned):
            tail = av[len(planned):]
            if tail == "" or not tail[0].isdigit():
                return True
    return False


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
        query = f"tag: {tag} #Resolved resolved date: {RESOLVED_DATE_RANGE}"
        response = client.get(
            f"{YOUTRACK_URL}/issues",
            params={
                "fields": "idReadable,summary,created,resolved,customFields(name,value(name,presentation))",
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


def fetch_activities(issue_id: str) -> dict:
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
    activities = sorted(response.json(), key=lambda a: a.get("timestamp", 0))

    primary_times = []
    fallback_times = []
    timeline = []           # list of (timestamp, label)
    initial_state = None
    current_state = None
    first_fixed_dt = None
    rider_stopper_removed_while_open = False
    stopper_tag_added = False
    planned_for_changes = []
    fix_versions_changes = []

    for activity in activities:
        ts = activity.get("timestamp", 0)
        category_id = (activity.get("category") or {}).get("id", "")

        if category_id == "TagsCategory":
            for item in (activity.get("added") or []):
                if isinstance(item, dict):
                    name = item.get("name", "")
                    if name in STOPPER_TAGS:
                        stopper_tag_added = True
                    if name in MEASURE_TAGS:
                        primary_times.append(ts)
                        timeline.append((ts, "Tag added"))
                    elif name in MEASURE_TAGS_FALLBACK:
                        fallback_times.append(ts)
                        timeline.append((ts, "Tag added"))
            for item in (activity.get("removed") or []):
                if isinstance(item, dict) and item.get("name") == RIDER_RELEASE_STOPPER_TAG:
                    if current_state not in FIXED_STATES:
                        rider_stopper_removed_while_open = True
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

    timeline.sort(key=lambda e: e[0])
    labels = [label for _, label in timeline]
    if initial_state and (not labels or labels[0] != initial_state):
        labels.insert(0, initial_state)
    state_history = " -> ".join(labels) if labels else ""

    return {
        "tag_dt": tag_dt,
        "first_fixed_dt": first_fixed_dt,
        "state_history": state_history,
        "rider_stopper_removed_while_open": rider_stopper_removed_while_open,
        "stopper_tag_added": stopper_tag_added,
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
        f"project: {', '.join(SCAN_PROJECTS)} #Resolved "
        f"resolved date: {RESOLVED_DATE_RANGE} Priority: {priority_clause}"
    )
    result = []
    skip = 0
    while True:
        response = client.get(
            f"{YOUTRACK_URL}/issues",
            params={
                "fields": "idReadable,summary,created,resolved,customFields(name,value(name,presentation))",
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


def fetch_all_activities(issue_ids: list[str]) -> dict[str, dict]:
    """Fetch activities for many issues concurrently. Returns {issue_id: activity_dict}."""
    with ThreadPoolExecutor(max_workers=16) as executor:
        results = executor.map(lambda iid: (iid, fetch_activities(iid)), issue_ids)
        return dict(results)


MD_FILE = os.path.join("reports", "release_stoppers.md")
CSV_FILE = os.path.join("reports", "release_stoppers.csv")


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
            issue_link = f"[{r['id']}](https://youtrack.jetbrains.com/issue/{r['id']})"
            first_fixed = f"{r['days_tag_to_first_fixed']:.1f}" if r["days_tag_to_first_fixed"] is not None else ""
            days_to_release = r["days_tag_to_release"] if r["days_tag_to_release"] is not None else ""
            available_in_str = ", ".join(r["available_in"])
            in_planned_str = "YES" if r["in_planned"] else ("NO" if r["planned_for"] else "")
            removed = "YES" if r["rider_stopper_removed_while_open"] else ""
            f.write(
                f"| {issue_link} | {r['project']} | {r['summary']} | {r['created']} | {r['tag_added']} | {r['resolved']} | "
                f"{r['days_to_tag']:.1f} | {r['days_tag_to_resolved']:.1f} | {first_fixed} | "
                f"{r['planned_for']} | {r['planned_for_date']} | {days_to_release} | {available_in_str} | "
                f"{in_planned_str} | {r['first_available']} | "
                f"{r['state_history']} | {removed} |\n"
            )
        f.write(f"| **Average** | | | | | | **{avg_to_tag:.1f}** | **{avg_tag_to_resolved:.1f}** | | | | | | | | | |\n")

    print(f"Markdown written to {MD_FILE}")


def write_csv(rows: list[dict]):
    with open(CSV_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Issue", "Project", "Link", "Summary", "Created", "Tag Added", "Resolved",
                         "Days to Tag", "Days Tag to Resolved", "Days Tag to First Fixed",
                         "Planned For", "Planned For Date", "Days Tag to Release", "Available In",
                         "In Planned", "First Available",
                         "State History", "Removed While Open"])
        for r in rows:
            link = f"https://youtrack.jetbrains.com/issue/{r['id']}"
            first_fixed = f"{r['days_tag_to_first_fixed']:.1f}" if r["days_tag_to_first_fixed"] is not None else ""
            days_to_release = r["days_tag_to_release"] if r["days_tag_to_release"] is not None else ""
            available_in_str = ", ".join(r["available_in"])
            in_planned_str = "YES" if r["in_planned"] else ("NO" if r["planned_for"] else "")
            writer.writerow([
                r["id"], r["project"], link, r["summary"], r["created"], r["tag_added"], r["resolved"],
                f"{r['days_to_tag']:.1f}", f"{r['days_tag_to_resolved']:.1f}", first_fixed,
                r["planned_for"], r["planned_for_date"], days_to_release, available_in_str,
                in_planned_str, r["first_available"],
                r["state_history"], "YES" if r["rider_stopper_removed_while_open"] else "",
            ])
    print(f"CSV written to {CSV_FILE}")


def main():
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
    site_releases_map = dict(get_version_dates())  # version -> date
    site_releases_map.update(FUTURE_RELEASES)
    print(f"Loaded {len(site_releases_map)} releases ({len(FUTURE_RELEASES)} future).\n")

    print(f"Fetching activities for {len(issues)} issues (parallel)...")
    activities = fetch_all_activities([issue["idReadable"] for issue in issues])

    rows = []
    for issue in issues:
        issue_id = issue["idReadable"]
        summary = issue["summary"]
        created_ms = issue.get("created")
        resolved_ms = issue.get("resolved")

        if not created_ms or not resolved_ms:
            print(f"  [SKIP] {issue_id}: missing created or resolved timestamp")
            continue

        act = activities[issue_id]

        # Path B candidates qualify only if a stopper tag was added in history.
        # Path A issues (currently tagged) always qualify.
        if issue_id not in tagged_ids and not act["stopper_tag_added"]:
            continue

        created_dt = ms_to_dt(created_ms)
        resolved_dt = ms_to_dt(resolved_ms)

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

        rows.append({
            "id": issue_id,
            "project": issue_id.split("-")[0],
            "summary": summary,
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
            "rider_stopper_removed_while_open": act["rider_stopper_removed_while_open"],
        })

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
        in_planned_str = "YES" if r["in_planned"] else ("NO" if r["planned_for"] else "")
        removed_str = "YES" if r["rider_stopper_removed_while_open"] else ""
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
    removed_count = sum(1 for r in rows if r["rider_stopper_removed_while_open"])
    if removed_count:
        print(f"Rider-release-stopper removed while open: {removed_count} issue(s)")

    write_markdown(rows, no_history_count)
    write_csv(rows)


if __name__ == "__main__":
    main()
