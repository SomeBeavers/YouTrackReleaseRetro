import os
import requests
from typing import List, Dict

from datetime import datetime

YOUTRACK_URL = "https://youtrack.jetbrains.com/api"
TOKEN = os.getenv("YOUTRACK_TOKEN")

PRIORITY = "Priority"
SUBSYSTEM = "Subsystem"

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
        self.available_in = None
        self.comments = []


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

    # Get issue subsystem from Custom Fields.
    def parse_issue_Avaiable_in(self, custom_fields: List[dict]) -> str:
        for field in custom_fields:
            if field['name'] == 'Available in':
                value = field['value']

                # Check if the value is None
                if value is None:
                    return None

                # If it's a list, extract values from the list
                if isinstance(value, list):
                    # Assuming you want to join multiple values in the list
                    return ', '.join([v['name'] for v in value if 'name' in v])

                # If it's a dictionary, extract the 'name'
                if isinstance(value, dict) and 'name' in value:
                    return value['name']

        return None  # Return None if 'Available in' is not found

    # Get list of YouTrack issues.
    def get_issues(self) -> List[YouTrackIssue]:
        api_query = f"{YOUTRACK_URL}/issues?fields=idReadable,summary,customFields(name,value(name))&query={requests.utils.quote(self.query)}"
        response = self.client.get(api_query)
        response.raise_for_status()

        data = response.json()
        youtrack_issues = [YouTrackIssue(issue['idReadable'], issue['summary'], issue['customFields']) for issue in data]

        for issue in youtrack_issues:
            issue.id = issue.id
            issue.summary = issue.summary
            issue.type = self.parse_issue_type(issue.custom_fields)
            issue.priority = self.parse_issue_priority(issue.custom_fields)
            issue.subsystem = self.parse_issue_subystem(issue.custom_fields)
            issue.available_in = self.parse_issue_Avaiable_in(issue.custom_fields)

        return youtrack_issues

    def get_issues_with_comments(self) -> List[YouTrackIssue]:
        api_query = f"{YOUTRACK_URL}/issues?fields=idReadable,summary,comments(id,text,author(email),created),customFields(name,value(name))&query={requests.utils.quote(self.query)}"
        response = self.client.get(api_query)
        response.raise_for_status()

        data = response.json()
        youtrack_issues = [YouTrackIssue(issue['idReadable'], issue['summary'], issue['customFields']) for issue in data]

        for issue, issue_data in zip(youtrack_issues, data):
            issue.id = issue.id
            issue.type = self.parse_issue_type(issue.custom_fields)
            issue.priority = self.parse_issue_priority(issue.custom_fields)
            issue.subsystem = self.parse_issue_subystem(issue.custom_fields)
            issue.available_in = self.parse_issue_Avaiable_in(issue.custom_fields)

            # If comments exist, iterate over them
            comments = issue_data.get('comments', [])
            for comment in comments:
                # # Convert the 'created' timestamp to a datetime object for comparison
                # created_date = datetime.fromtimestamp(comment['created'] / 1000)  # Assuming timestamp is in milliseconds

                author_email = comment.get('author', {}).get('email', 'Unknown')  # Using 'fullName' for YouTrack's User type

                issue.comments.append({
                    'id': comment['id'],
                    'text': comment['text'],
                    'author': author_email,
                    'created': comment['created'] # Optional: format the datetime
                })

        return youtrack_issues


    #Dict[str, Dict[str, int]]
    def get_issues_by(self) -> Dict[str, Dict[str, int]]:
        youtrack_issues = self.get_issues()

        issue_priority_counts = {}
        issue_subsystem_counts = {}

        for issue in youtrack_issues:
            if issue.priority:
                if issue.priority in issue_priority_counts:
                    issue_priority_counts[issue.priority] += 1
                else:
                    issue_priority_counts[issue.priority] = 1
            if issue.subsystem:
                if issue.subsystem in issue_subsystem_counts:
                    issue_subsystem_counts[issue.subsystem] += 1
                else:
                    issue_subsystem_counts[issue.subsystem] = 1

        print("__")

        for type_name, count in issue_priority_counts.items():
            print(f"{type_name}: {count}")

        print("__")
        for type_name, count in issue_subsystem_counts.items():
            print(f"{type_name}: {count}")

        return { f"{PRIORITY}": issue_priority_counts,
                 f"{SUBSYSTEM}": issue_subsystem_counts}

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

