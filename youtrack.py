import os
import requests
from typing import List, Dict

YOUTRACK_URL = "https://youtrack.jetbrains.com/api"
TOKEN = os.getenv("YOUTRACK_TOKEN")

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

class YouTrackIssue:
    def __init__(self, id: str, summary: str, custom_fields: List[dict]):
        self.id = id
        self.summary = summary
        self.custom_fields = custom_fields
        self.type = None
        self.priority = None
        self.subsystem = None


class GetIssues:
    def __init__(self, client: requests.Session, query: str = None):
        self.client = client
        self.query = query

    # Get issue type from Custom Fields.
    def parse_issue_type(self, custom_fields: List[dict]) -> str:
        for field in custom_fields:
            if field['name'] == 'Type' and field['value'] is not None:
                return field['value']['name']
        return None

    # Get issue priority from Custom Fields.
    def parse_issue_priority(self, custom_fields: List[dict]) -> str:
        for field in custom_fields:
            if field['name'] == 'Priority' and field['value'] is not None:
                return field['value']['name']
        return None

    # Get issue subsystem from Custom Fields.
    def parse_issue_subystem(self, custom_fields: List[dict]) -> str:
        for field in custom_fields:
            if field['name'] == 'Subsystem' and field['value'] is not None:
                return field['value']['name']
        return None

    # Get list of YouTrack issues.
    def get_issues(self) -> List[YouTrackIssue]:
        api_query = f"{YOUTRACK_URL}/issues?fields=id,summary,customFields(name,value(name))&query={requests.utils.quote(self.query)}"
        response = self.client.get(api_query)
        response.raise_for_status()

        data = response.json()
        youtrack_issues = [YouTrackIssue(issue['id'], issue['summary'], issue['customFields']) for issue in data]

        for issue in youtrack_issues:
            issue.type = self.parse_issue_type(issue.custom_fields)
            issue.priority = self.parse_issue_priority(issue.custom_fields)
            issue.subsystem = self.parse_issue_subystem(issue.custom_fields)

        return youtrack_issues

    def get_all_issues_by_priority(self) -> Dict[str, int]:
        youtrack_issues = self.get_issues()

        issue_priority_counts = {}

        for issue in youtrack_issues:
            if issue.priority:
                if issue.priority in issue_priority_counts:
                    issue_priority_counts[issue.priority] += 1
                else:
                    issue_priority_counts[issue.priority] = 1

        print("__")

        for type_name, count in issue_priority_counts.items():
            print(f"{type_name}: {count}")

        return issue_priority_counts


    def get_bugs_by_priority(self) -> Dict[str, int]:
        youtrack_issues = self.get_issues()

        issue_priority_counts = {}

        for issue in youtrack_issues:
            if (issue.type == "Bug" or issue.type == "Performance Problem" or issue.type == "Usability Problem" or issue.type == "Exception") and issue.priority:
                if issue.priority in issue_priority_counts:
                    issue_priority_counts[issue.priority] += 1
                else:
                    issue_priority_counts[issue.priority] = 1

        print("__")

        for type_name, count in issue_priority_counts.items():
            print(f"{type_name}: {count}")

        return issue_priority_counts

    def get_issues_by_type(self) -> Dict[str, int]:
        youtrack_issues = self.get_issues()

        issue_type_counts = {}

        for issue in youtrack_issues:
            if issue.type:
                if issue.type in issue_type_counts:
                    issue_type_counts[issue.type] += 1
                else:
                    issue_type_counts[issue.type] = 1

        print("__")

        for type_name, count in issue_type_counts.items():
            print(f"{type_name}: {count}")

        return issue_type_counts

