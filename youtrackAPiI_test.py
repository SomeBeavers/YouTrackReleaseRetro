import os
from typing import List, Dict

import matplotlib.pyplot as plt
import requests
from openai import OpenAI

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

class GetIssues:
    def __init__(self, client: requests.Session, query: str = None):
        self.client = client
        self.query = query

    def parse_issue_type(self, custom_fields: List[dict]) -> str:
        for field in custom_fields:
            if field['name'] == 'Type' and field['value'] is not None:
                return field['value']['name']
        return None

    def get_issues(self) -> List[YouTrackIssue]:
        api_query = f"{YOUTRACK_URL}/issues?fields=id,summary,customFields(name,value(name))&query={requests.utils.quote(self.query)}"
        response = self.client.get(api_query)
        response.raise_for_status()

        data = response.json()
        youtrack_issues = [YouTrackIssue(issue['id'], issue['summary'], issue['customFields']) for issue in data]

        for issue in youtrack_issues:
            issue.type = self.parse_issue_type(issue.custom_fields)

        return youtrack_issues

    def get_issues_by_type(self) -> Dict[str, int]:
        api_query = f"{YOUTRACK_URL}/issues?fields=id,summary,customFields(name,value(name))&query={requests.utils.quote(self.query)}"
        response = self.client.get(api_query)
        response.raise_for_status()

        data = response.json()
        youtrack_issues = [YouTrackIssue(issue['id'], issue['summary'], issue['customFields']) for issue in data]

        issue_type_counts = {}

        for issue in youtrack_issues:
            issue_type = self.parse_issue_type(issue.custom_fields)
            if issue_type:
                if issue_type in issue_type_counts:
                    issue_type_counts[issue_type] += 1
                else:
                    issue_type_counts[issue_type] = 1

        print("__")

        for type_name, count in issue_type_counts.items():
            print(f"{type_name}: {count}")

        return issue_type_counts

    def plot_issues_by_type(self, dates: str):
        issue_type_counts = self.get_issues_by_type()

        # Sort issue types by count in descending order
        sorted_issue_types = sorted(issue_type_counts.items(), key=lambda x: x[1], reverse=True)
        sorted_labels, sorted_counts = zip(*sorted_issue_types)

        total_count = sum(sorted_counts)

        # Function to display the number of tickets on the pie chart
        def absolute_number(pct):
            absolute = int(round(pct * total_count / 100.0))
            return f'{absolute}'

        # Plotting the pie chart
        plt.figure(figsize=(8, 8))
        plt.pie(sorted_counts, labels=sorted_labels, autopct=absolute_number, startangle=140)
        plt.title(f'Distribution of Issues by Type Created by JetBrains Team ({dates})')
        plt.show()


# Example usage:
client = requests.Session()
client.headers.update(headers)
cycle_dates_query = "created: 2024-04-09 .. 2024-08-14"
additional_query = "created by: jetbrains-team"
query = f"project:ReSharper and {cycle_dates_query} and {additional_query}"

issues_handler = GetIssues(client, query)
issues_by_type = issues_handler.get_issues_by_type()
issues_handler.plot_issues_by_type(cycle_dates_query)

cycle_dates_old_query = "created: 2023-12-06 .. 2024-04-09"
query_old = f"project:ReSharper and {cycle_dates_old_query} and {additional_query}"
issues_handler_old = GetIssues(client, query_old)
issues_by_type_old = issues_handler_old.get_issues_by_type()
issues_handler_old.plot_issues_by_type(cycle_dates_old_query)


client = OpenAI()

completion = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "You are a highly skilled Quality Assurance Lead at JetBrains."},
        {
            "role": "user",
            "content": """
Hello! I need your expertise to help analyze the quality of ReSharper's releases. What conclusion could be made from the following data? It shows the distribution of Issues by Type Created by members of JetBrains in the release.

Current release (242):
Previous release (241):
"""
        },
        {
            "role": "assistant",
            "content": f"Current release data: {issues_by_type}\nPrevious release data: {issues_by_type_old}"
        }
    ]
)

print(completion.choices[0].message.content)
