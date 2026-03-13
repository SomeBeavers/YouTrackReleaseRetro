"""
Analyzes resolved issues tagged with a release-stopper tag.

For each issue reports:
  - Time from creation to measure tag added (days)
  - Time from measure tag added to resolved (days)
  - Time from measure tag added to first Fixed/Verified state (days)
  - State change history
  - Whether rider-release-stopper tag was removed while issue was still open
  - AI comment

* next to a date means tag addition was not found in activity history;
  issue creation date is used as a fallback.
"""

import csv
import os
import requests
from datetime import datetime, timezone
from openai import OpenAI

YOUTRACK_URL = "https://youtrack.jetbrains.com/api"
TOKEN = os.getenv("YOUTRACK_TOKEN")
RESOLVED_DATE_RANGE = "2025-01-01 .. today"
SEARCH_TAGS = ["dotnet-ex-release-stopper", "rider-ex-stopper"]
MEASURE_TAGS = ["dotnet-release-stopper", "rider-release-stopper"]
MEASURE_TAGS_FALLBACK = ["rider-ex-stopper"]
RIDER_RELEASE_STOPPER_TAG = "rider-release-stopper"
FIXED_STATES = {"Fixed", "Verified"}
ENABLE_AI_COMMENTS = True

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

client = requests.Session()
client.headers.update(headers)


def ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def fetch_issues() -> list[dict]:
    seen = set()
    result = []
    for tag in SEARCH_TAGS:
        query = f"tag: {tag} #Resolved resolved date: {RESOLVED_DATE_RANGE}"
        response = client.get(
            f"{YOUTRACK_URL}/issues",
            params={
                "fields": "idReadable,summary,created,resolved",
                "query": query,
                "$top": 1000,
            },
        )
        response.raise_for_status()
        for issue in response.json():
            if issue["idReadable"] not in seen:
                seen.add(issue["idReadable"])
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
    state_changes = []       # list of (from_state, to_state)
    first_fixed_dt = None
    rider_stopper_removed_while_open = False
    current_state = None

    for activity in activities:
        category_id = (activity.get("category") or {}).get("id", "")

        if category_id == "TagsCategory":
            for item in (activity.get("added") or []):
                if isinstance(item, dict):
                    name = item.get("name", "")
                    if name in MEASURE_TAGS:
                        primary_times.append(activity["timestamp"])
                    elif name in MEASURE_TAGS_FALLBACK:
                        fallback_times.append(activity["timestamp"])
            for item in (activity.get("removed") or []):
                if isinstance(item, dict) and item.get("name") == RIDER_RELEASE_STOPPER_TAG:
                    if current_state not in FIXED_STATES:
                        rider_stopper_removed_while_open = True

        elif category_id == "CustomFieldCategory":
            field_name = (activity.get("field") or {}).get("name", "")
            if field_name == "State":
                added = activity.get("added") or []
                removed = activity.get("removed") or []
                from_state = removed[0].get("name") if removed and isinstance(removed[0], dict) else current_state
                to_state = added[0].get("name") if added and isinstance(added[0], dict) else None
                if to_state:
                    if current_state is None:
                        current_state = from_state
                    state_changes.append((from_state, to_state))
                    current_state = to_state
                    if to_state in FIXED_STATES and first_fixed_dt is None:
                        first_fixed_dt = ms_to_dt(activity["timestamp"])

    tag_dt = None
    if primary_times:
        tag_dt = ms_to_dt(min(primary_times))
    elif fallback_times:
        tag_dt = ms_to_dt(min(fallback_times))

    if state_changes:
        all_states = ([state_changes[0][0]] if state_changes[0][0] else []) + [t for _, t in state_changes]
        state_history = " -> ".join(all_states)
    else:
        state_history = ""

    return {
        "tag_dt": tag_dt,
        "first_fixed_dt": first_fixed_dt,
        "state_history": state_history,
        "rider_stopper_removed_while_open": rider_stopper_removed_while_open,
    }


def ask_ai_stopper_comment(issue_id: str, summary: str, state_history: str,
                            days_to_tag: float, days_tag_to_first_fixed: float | None,
                            rider_stopper_removed: bool) -> str:
    ai_client = OpenAI()
    parts = [f"Issue {issue_id}: {summary}"]
    if state_history:
        parts.append(f"State history: {state_history}")
    parts.append(f"Days from creation to stopper tag: {days_to_tag:.1f}")
    if days_tag_to_first_fixed is not None:
        parts.append(f"Days from stopper tag to first Fixed/Verified state: {days_tag_to_first_fixed:.1f}")
    if rider_stopper_removed:
        parts.append("Note: rider-release-stopper tag was removed while the issue was still open.")
    completion = ai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a QA specialist analyzing release stopper issues. Be concise."},
            {"role": "user", "content": "\n".join(parts) + "\n\nProvide a brief 1-2 sentence comment on the nature and handling of this stopper issue."},
        ],
    )
    return completion.choices[0].message.content.strip()


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
        f.write(f"**Resolved date range:** {RESOLVED_DATE_RANGE}  \n\n")
        f.write(f"**Total issues:** {n} | **With tag history:** {n - no_history_count} | **Assumed tagged at creation (\\*):** {no_history_count}\n\n")
        f.write(f"**Average days to tag:** {avg_to_tag:.1f} | **Average days tag to resolved:** {avg_tag_to_resolved:.1f}\n\n")

        f.write("| Issue | Summary | Created | Tag Added | Resolved | Days to Tag | Days Tag to Resolved | Days Tag to First Fixed | State History | Removed While Open | AI Comment |\n")
        f.write("|---|---|---|---|---|---:|---:|---:|---|:---:|---|\n")
        for r in rows:
            issue_link = f"[{r['id']}](https://youtrack.jetbrains.com/issue/{r['id']})"
            first_fixed = f"{r['days_tag_to_first_fixed']:.1f}" if r["days_tag_to_first_fixed"] is not None else ""
            removed = "YES" if r["rider_stopper_removed_while_open"] else ""
            ai_comment = r.get("ai_comment", "")
            f.write(f"| {issue_link} | {r['summary']} | {r['created']} | {r['tag_added']} | {r['resolved']} | {r['days_to_tag']:.1f} | {r['days_tag_to_resolved']:.1f} | {first_fixed} | {r['state_history']} | {removed} | {ai_comment} |\n")
        f.write(f"| **Average** | | | | | **{avg_to_tag:.1f}** | **{avg_tag_to_resolved:.1f}** | | | | |\n")

    print(f"Markdown written to {MD_FILE}")


def write_csv(rows: list[dict]):
    with open(CSV_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Issue", "Link", "Summary", "Created", "Tag Added", "Resolved",
                         "Days to Tag", "Days Tag to Resolved", "Days Tag to First Fixed",
                         "State History", "Removed While Open", "AI Comment"])
        for r in rows:
            link = f"https://youtrack.jetbrains.com/issue/{r['id']}"
            first_fixed = f"{r['days_tag_to_first_fixed']:.1f}" if r["days_tag_to_first_fixed"] is not None else ""
            writer.writerow([
                r["id"], link, r["summary"], r["created"], r["tag_added"], r["resolved"],
                f"{r['days_to_tag']:.1f}", f"{r['days_tag_to_resolved']:.1f}", first_fixed,
                r["state_history"], "YES" if r["rider_stopper_removed_while_open"] else "",
                r.get("ai_comment", ""),
            ])
    print(f"CSV written to {CSV_FILE}")


def main():
    print(f"Fetching resolved issues tagged {SEARCH_TAGS}...")
    issues = fetch_issues()
    print(f"Found {len(issues)} issues.\n")

    rows = []
    for i, issue in enumerate(issues, 1):
        issue_id = issue["idReadable"]
        summary = issue["summary"]
        created_ms = issue.get("created")
        resolved_ms = issue.get("resolved")

        if not created_ms or not resolved_ms:
            print(f"  [SKIP] {issue_id}: missing created or resolved timestamp")
            continue

        created_dt = ms_to_dt(created_ms)
        resolved_dt = ms_to_dt(resolved_ms)

        print(f"  [{i}/{len(issues)}] {issue_id} — fetching activities...")
        act = fetch_activities(issue_id)

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

        row = {
            "id": issue_id,
            "summary": summary,
            "created": created_dt.strftime("%Y-%m-%d"),
            "tag_added": tag_dt.strftime("%Y-%m-%d") + ("*" if assumed else ""),
            "resolved": resolved_dt.strftime("%Y-%m-%d"),
            "days_to_tag": days_to_tag,
            "days_tag_to_resolved": days_tag_to_resolved,
            "days_tag_to_first_fixed": days_tag_to_first_fixed,
            "state_history": act["state_history"],
            "rider_stopper_removed_while_open": act["rider_stopper_removed_while_open"],
            "ai_comment": "",
        }

        if ENABLE_AI_COMMENTS:
            print(f"         asking AI for comment...")
            row["ai_comment"] = ask_ai_stopper_comment(
                issue_id, summary, act["state_history"],
                days_to_tag, days_tag_to_first_fixed,
                act["rider_stopper_removed_while_open"],
            )

        rows.append(row)

    if not rows:
        print("No data to display.")
        return

    rows.sort(key=lambda r: r["days_to_tag"], reverse=True)

    # Console table (condensed — full details in .md and .csv)
    col_id  = max(len(r["id"]) for r in rows) + 2
    col_sum = min(max(len(r["summary"]) for r in rows), 55) + 2
    col_tag = max(max(len(r["tag_added"]) for r in rows), len("Tag Added")) + 2
    col_date = 12
    col_days = 14
    col_flag = 8

    header = (
        f"{'Issue':<{col_id}}"
        f"{'Summary':<{col_sum}}"
        f"{'Created':<{col_date}}"
        f"{'Tag Added':<{col_tag}}"
        f"{'Resolved':<{col_date}}"
        f"{'Days to Tag':>{col_days}}"
        f"{'Days to Res.':>{col_days}}"
        f"{'Days to Fix':>{col_days}}"
        f"{'Rem.?':>{col_flag}}"
    )
    separator = "-" * len(header)
    print(f"\n{header}")
    print(separator)

    no_history_count = sum(1 for r in rows if r["tag_added"].endswith("*"))
    for r in rows:
        first_fixed_str = f"{r['days_tag_to_first_fixed']:.1f}" if r["days_tag_to_first_fixed"] is not None else "N/A"
        removed_str = "YES" if r["rider_stopper_removed_while_open"] else ""
        print(
            f"{r['id']:<{col_id}}"
            f"{r['summary'][:col_sum - 2]:<{col_sum}}"
            f"{r['created']:<{col_date}}"
            f"{r['tag_added']:<{col_tag}}"
            f"{r['resolved']:<{col_date}}"
            f"{r['days_to_tag']:>{col_days}.1f}"
            f"{r['days_tag_to_resolved']:>{col_days}.1f}"
            f"{first_fixed_str:>{col_days}}"
            f"{removed_str:>{col_flag}}"
        )

    n = len(rows)
    avg_to_tag = sum(r["days_to_tag"] for r in rows) / n
    avg_tag_to_resolved = sum(r["days_tag_to_resolved"] for r in rows) / n
    print(separator)
    print(
        f"{'Average':<{col_id + col_sum + col_date + col_tag + col_date}}"
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
