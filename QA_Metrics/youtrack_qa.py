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

class YouTrackQA:
    def __init__(self, id: str, summary: str, created: int, custom_fields: List[dict]):
        self.id = id
        self.summary = summary
        self.created = created
        self.custom_fields = custom_fields
        self.comments = []

        # Core issue fields
        self.product = None  # enum (single)
        self.assignee = None  # user (single)
        self.priority = None  # enum (single)
        self.state = None  # state (single)
        self.type = None  # enum (single)
        self.subsystem = None  # enum (single)
        self.available_in = None  # enum (multiple)
        
        # QA-specific fields
        self.feature_state_for_qa = None  # enum (single)
        self.eta_from_developer = None  # date
        self.due_date = None  # date
        self.estimation = None  # period
        self.sprint = None  # enum (single)
        self.checklist = None  # string
        self.branch = None  # string
        self.days_before_testing_starts = None  # integer
        self.days_in_testing = None  # integer
        self.when_development_finished = None  # date
        self.how_many_iterations_of_testing = None  # integer


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
    
    # Get issue product from Custom Fields (enum single).
    def parse_issue_product(self, custom_fields: List[dict]) -> str:
        for field in custom_fields:
            if field['name'] == 'Product' and field['value'] is not None:
                return field['value']['name']
        return None

    # Get issue assignee from Custom Fields (user single).
    def parse_issue_assignee(self, custom_fields: List[dict]) -> str:
        for field in custom_fields:
            if field['name'] == 'Assignee' and field['value'] is not None:
                return field['value']['name']
        return None

    # Get feature state for QA from Custom Fields (enum single).
    def parse_issue_feature_state_for_qa(self, custom_fields: List[dict]) -> str:
        for field in custom_fields:
            if field['name'] == 'Feature State (for QA)' and field['value'] is not None:
                return field['value']['name']
        return None

    # Get ETA from Developer from Custom Fields (date).
    def parse_issue_eta_from_developer(self, custom_fields: List[dict]) -> int:
        for field in custom_fields:
            if field['name'] == 'ETA from Developer' and field['value'] is not None:
                return field['value']
        return None

    # Get due date from Custom Fields (date).
    def parse_issue_due_date(self, custom_fields: List[dict]) -> int:
        for field in custom_fields:
            if field['name'] == 'Due date' and field['value'] is not None:
                return field['value']
        return None

    # Get estimation from Custom Fields (period).
    def parse_issue_estimation(self, custom_fields: List[dict]) -> str:
        for field in custom_fields:
            if field['name'] == 'Estimation' and field['value'] is not None:
                # Extract presentation from PeriodValue object
                if isinstance(field['value'], dict) and 'presentation' in field['value']:
                    return field['value']['presentation']
                # If it's already a string, return as is
                if isinstance(field['value'], str):
                    return field['value']
                return str(field['value'])
        return None

    # Get sprint from Custom Fields (enum single).
    def parse_issue_sprint(self, custom_fields: List[dict]) -> str:
        for field in custom_fields:
            if field['name'] == 'Sprint' and field['value'] is not None:
                return field['value']['name']
        return None

    # Get checklist from Custom Fields (string).
    def parse_issue_checklist(self, custom_fields: List[dict]) -> str:
        for field in custom_fields:
            if field['name'] == 'Checklist' and field['value'] is not None:
                return field['value']
        return None

    # Get branch from Custom Fields (string).
    def parse_issue_branch(self, custom_fields: List[dict]) -> str:
        for field in custom_fields:
            if field['name'] == 'Branch' and field['value'] is not None:
                return field['value']
        return None

    # Get days before testing starts from Custom Fields (integer).
    def parse_issue_days_before_testing_starts(self, custom_fields: List[dict]) -> int:
        for field in custom_fields:
            if field['name'] == 'Days Before Testing Starts' and field['value'] is not None:
                return field['value']
        return None

    # Get days in testing from Custom Fields (integer).
    def parse_issue_days_in_testing(self, custom_fields: List[dict]) -> int:
        for field in custom_fields:
            if field['name'] == 'Days In Testing' and field['value'] is not None:
                return field['value']
        return None

    # Get when development finished from Custom Fields (date).
    def parse_issue_when_development_finished(self, custom_fields: List[dict]) -> int:
        for field in custom_fields:
            if field['name'] == 'When Development Finished' and field['value'] is not None:
                return field['value']
        return None

    # Get how many iterations of testing from Custom Fields (integer).
    def parse_issue_how_many_iterations_of_testing(self, custom_fields: List[dict]) -> int:
        for field in custom_fields:
            if field['name'] == 'How Many Iterations of Testing' and field['value'] is not None:
                return field['value']
        return None
    # endregion

    # Get list of YouTrack issues.
    def get_issues(self) -> List[YouTrackQA]:
        api_query = f"{YOUTRACK_URL}/issues?fields=idReadable,summary,created,customFields(name,value(name,presentation))&query={requests.utils.quote(self.query)}"
        response = self.client.get(api_query)
        response.raise_for_status()

        data = response.json()
        youtrack_issues = [YouTrackQA(issue['idReadable'], issue['summary'], issue['created'], issue['customFields']) for issue in data]

        for issue in youtrack_issues:
            issue.id = issue.id
            issue.summary = issue.summary
            issue.type = self.parse_issue_type(issue.custom_fields)
            issue.priority = self.parse_issue_priority(issue.custom_fields)
            issue.state = self.parse_issue_state(issue.custom_fields)
            issue.product = self.parse_issue_product(issue.custom_fields)
            issue.assignee = self.parse_issue_assignee(issue.custom_fields)
            issue.feature_state_for_qa = self.parse_issue_feature_state_for_qa(issue.custom_fields)
            issue.eta_from_developer = self.parse_issue_eta_from_developer(issue.custom_fields)
            issue.due_date = self.parse_issue_due_date(issue.custom_fields)
            issue.estimation = self.parse_issue_estimation(issue.custom_fields)
            issue.sprint = self.parse_issue_sprint(issue.custom_fields)
            issue.checklist = self.parse_issue_checklist(issue.custom_fields)
            issue.branch = self.parse_issue_branch(issue.custom_fields)
            issue.days_before_testing_starts = self.parse_issue_days_before_testing_starts(issue.custom_fields)
            issue.days_in_testing = self.parse_issue_days_in_testing(issue.custom_fields)
            issue.when_development_finished = self.parse_issue_when_development_finished(issue.custom_fields)
            issue.how_many_iterations_of_testing = self.parse_issue_how_many_iterations_of_testing(issue.custom_fields)

        return youtrack_issues
