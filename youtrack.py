import os
import requests
from typing import List, Dict

from datetime import datetime

YOUTRACK_URL = "https://youtrack.jetbrains.com/api"
TOKEN = os.getenv("YOUTRACK_TOKEN")

PRIORITY = "Priority"
SUBSYSTEM = "Subsystem"
CREATED_DATE = "Created"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

class YouTrackIssue:
    def __init__(self, id: str, summary: str, created: int, custom_fields: List[dict]):
        self.id = id
        self.summary = summary
        self.created = created,
        self.custom_fields = custom_fields
        self.type = None
        self.priority = None
        self.subsystem = None
        self.available_in = None
        self.comments = []
        self.state = None
        self.daysInUntriaged = None
        self.daysInToReproduce = None
        self.daysInReadyForTesting = None


class GetIssues:
    def __init__(self, client: requests.Session, query: str = None):
        self.client = client
        self.query = query

    # region Methods for parsing custom fields of issue
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

    # Get issue state from Custom Fields.
    def parse_issue_state(self, custom_fields: List[dict]) -> str:
        for field in custom_fields:
            if field['name'] == 'State' and field['value'] is not None:
                return field['value']['name']
        return None

    def parse_issue_days_in_untriaged(self, custom_fields: List[dict]) -> int:
        for field in custom_fields:
            if field['name'] == 'Days in Untriaged' and field['value'] is not None:
                return field['value']
        return None

    def parse_issue_days_in_to_reproduce(self, custom_fields: List[dict]) -> int:
        for field in custom_fields:
            if field['name'] == 'Days in To Reproduce' and field['value'] is not None:
                return field['value']
        return None

    def parse_issue_days_in_ready_for_testing(self, custom_fields: List[dict]) -> int:
        for field in custom_fields:
            if field['name'] == 'Days in Ready for testing' and field['value'] is not None:
                return field['value']
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
    # endregion

    # Get list of YouTrack issues.
    def get_issues(self) -> List[YouTrackIssue]:
        api_query = f"{YOUTRACK_URL}/issues?fields=idReadable,summary,created,customFields(name,value(name))&query={requests.utils.quote(self.query)}"
        response = self.client.get(api_query)
        response.raise_for_status()

        data = response.json()
        youtrack_issues = [YouTrackIssue(issue['idReadable'], issue['summary'], issue['created'], issue['customFields']) for issue in data]

        for issue in youtrack_issues:
            issue.id = issue.id
            issue.summary = issue.summary
            issue.type = self.parse_issue_type(issue.custom_fields)
            issue.priority = self.parse_issue_priority(issue.custom_fields)
            issue.subsystem = self.parse_issue_subystem(issue.custom_fields)
            issue.available_in = self.parse_issue_Avaiable_in(issue.custom_fields)
            issue.state = self.parse_issue_state(issue.custom_fields)
            issue.daysInUntriaged = self.parse_issue_days_in_untriaged(issue.custom_fields)
            issue.daysInToReproduce = self.parse_issue_days_in_to_reproduce(issue.custom_fields)
            issue.daysInReadyForTesting = self.parse_issue_days_in_ready_for_testing(issue.custom_fields)

        return youtrack_issues

    def get_issues_with_comments(self) -> List[YouTrackIssue]:
        api_query = f"{YOUTRACK_URL}/issues?fields=idReadable,summary,created,comments(id,text,author(email),created),customFields(name,value(name))&query={requests.utils.quote(self.query)}"
        response = self.client.get(api_query)
        response.raise_for_status()

        data = response.json()
        youtrack_issues = [YouTrackIssue(issue['idReadable'], issue['summary'], issue['created'], issue['customFields']) for issue in data]

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

    """
    Aggregates and counts issues by various parameters.

    This method retrieves issues and calculates the count of issues grouped by:
    - Priority: Counts issues based on their priority levels.
    - Subsystem: Counts issues based on the subsystem they belong to.
    - Creation Date: Counts issues grouped by their creation date (in 'YYYY-MM-DD' format).

    Returns:
        Dict[str, Dict[str, int]]: A dictionary containing counts for each parameter:
            - "priority": A dictionary with priority levels as keys and their respective counts as values.
            - "subsystem": A dictionary with subsystem names as keys and their respective counts as values.
            - "created_date": A dictionary with creation dates (in 'YYYY-MM-DD') as keys and their respective counts as values.
    """
    def get_issues_count_by_various_parameters(self) -> Dict[str, Dict[str, int]]:
        youtrack_issues = self.get_issues()

        issue_priority_counts = {}
        issue_subsystem_counts = {}
        issue_date_counts = {}

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
            # Count by creation date
            if issue.created:
                # Convert timestamp to date
                created_date = datetime.fromtimestamp(issue.created[0] / 1000).date().strftime('%Y-%m-%d')
                issue_date_counts[created_date] = issue_date_counts.get(created_date, 0) + 1

        return { f"{PRIORITY}": issue_priority_counts,
                 f"{SUBSYSTEM}": issue_subsystem_counts,
                 f"{CREATED_DATE}": issue_date_counts,
                 }

    def get_issues_count_by_priority(self) -> Dict[str, int]:
        youtrack_issues = self.get_issues()

        issue_priority_counts = {}

        for issue in youtrack_issues:
            if issue.priority:
                if issue.priority in issue_priority_counts:
                    issue_priority_counts[issue.priority] += 1
                else:
                    issue_priority_counts[issue.priority] = 1

        return issue_priority_counts

    def get_bugs_count_by_priority(self) -> Dict[str, int]:
        youtrack_issues = self.get_issues()

        issue_priority_counts = {}

        for issue in youtrack_issues:
            if (issue.type == "Bug" or issue.type == "Performance Problem" or issue.type == "Usability Problem" or issue.type == "Exception") and issue.priority:
                if issue.priority in issue_priority_counts:
                    issue_priority_counts[issue.priority] += 1
                else:
                    issue_priority_counts[issue.priority] = 1

        return issue_priority_counts

    def get_issues_count_by_type(self) -> Dict[str, int]:
        youtrack_issues = self.get_issues()

        issue_type_counts = {}

        for issue in youtrack_issues:
            if issue.type:
                if issue.type in issue_type_counts:
                    issue_type_counts[issue.type] += 1
                else:
                    issue_type_counts[issue.type] = 1

        return issue_type_counts

