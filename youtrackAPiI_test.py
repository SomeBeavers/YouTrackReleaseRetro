import os
from typing import List, Dict

import matplotlib.pyplot as plt
import requests
from openai import OpenAI

dates243 = "2024-08-15 .. Today"
dates242 = "2024-04-10 .. 2024-08-14"
dates241 = "2023-12-07 .. 2024-04-09"
dates233 = "2023-08-02 .. 2023-12-06"
dates232 = "2023-04-05 .. 2023-08-01"

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


class GetIssues:
    def __init__(self, client: requests.Session, query: str = None):
        self.client = client
        self.query = query

    def parse_issue_type(self, custom_fields: List[dict]) -> str:
        for field in custom_fields:
            if field['name'] == 'Type' and field['value'] is not None:
                return field['value']['name']
        return None

    def parse_issue_priority(self, custom_fields: List[dict]) -> str:
        for field in custom_fields:
            if field['name'] == 'Priority' and field['value'] is not None:
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
            issue.priority = self.parse_issue_priority(issue.custom_fields)

        return youtrack_issues

    def get_bugs_by_priority(self) -> Dict[str, int]:
        youtrack_issues = self.get_issues()

        issue_priority_counts = {}

        for issue in youtrack_issues:
            if issue.type == "Bug" and issue.priority:
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

    def plot_issues_by_type(self, issue_type_counts: Dict[str, int], dates: str):
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

def get_data(query:str)-> Dict[str, int]:
    issues_handler = GetIssues(client, query)
    issues_by_type = issues_handler.get_issues_by_type()
    bugs_by_priority = issues_handler.get_bugs_by_priority()
    issues_handler.plot_issues_by_type(issues_by_type, cycle_dates_query)
    return issues_by_type

def AskAI():
    global client
    client = OpenAI()
    # Assemble the prompt manually
    prompt = ""
    for message in [
        {"role": "system",
         "content": "You are an expert Quality Assurance Lead at JetBrains with extensive knowledge of ReSharper's functionality, release cycles, and quality metrics. Your task is to analyze the distribution of issues reported in the recent ReSharper releases, providing a detailed comparison and actionable insights."},
        {
            "role": "user",
            "content": """
    Hello! I need your expertise to analyze the quality of ReSharper's recent releases. Specifically, I would like you to:

    1. Compare the Distribution of Issues: Examine and compare the distribution of issue types reported in the current release (242) with those in the previous release (241).

    2. Identify Significant Trends or Changes: Highlight any notable trends, increases, or decreases in issue types between the two releases.

    3. Highlight Areas of Concern or Improvement: Identify any issue categories that have shown significant changes or may indicate potential areas for improvement.

    4. Provide Actionable Recommendations: Based on your analysis, offer practical recommendations to address any identified issues or trends.
    """
        },
        {
            "role": "user",
            "content": f"Here is the data for the analysis:\n\n"
                       f"**Current release (242) data:**\n```{issues_by_type}```\n\n"
                       f"**Previous release (241) data:**\n```{issues_by_type_old}```"
        },
        {
            "role": "user",
            "content": """
    To proceed with the analysis, follow these steps:

    1. **Step-by-Step Comparison**: Break down the issue types in both releases and compare their frequencies. Calculate percentage changes where applicable.

    2. **Trend Identification**: Look for any significant increases or decreases in issue types. Determine if there are emerging patterns or persistent problems.

    3. **Concerns and Improvements**: Highlight any categories that have worsened or improved significantly. Assess if there are any issues that need urgent attention.

    4. **Recommendations**: Based on your findings, provide detailed recommendations to improve the quality of future releases. Prioritize areas with the most significant changes or potential impact.

    Take your time to analyze the data thoroughly and provide a comprehensive response.
    """
        }
    ]:
        prompt += f"{message['role'].capitalize()}: {message['content'].strip()}\n\n"
    # Print the assembled prompt
    print(prompt)
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system",
             "content": "You are an expert Quality Assurance Lead at JetBrains with extensive knowledge of ReSharper's functionality, release cycles, and quality metrics. Your task is to analyze the distribution of issues reported in the recent ReSharper releases, providing a detailed comparison and actionable insights."},
            {
                "role": "user",
                "content": """
Hello! I need your expertise to analyze the quality of ReSharper's recent releases. Specifically, I would like you to:

1. Compare the Distribution of Issues: Examine and compare the distribution of issue types reported in the current release (242) with those in the previous release (241).

2. Identify Significant Trends or Changes: Highlight any notable trends, increases, or decreases in issue types between the two releases.

3. Highlight Areas of Concern or Improvement: Identify any issue categories that have shown significant changes or may indicate potential areas for improvement.

4. Provide Actionable Recommendations: Based on your analysis, offer practical recommendations to address any identified issues or trends.
"""
            },
            {
                "role": "user",
                "content": f"Here is the data for the analysis:\n\n"
                           f"**Current release (242) data:**\n```{issues_by_type}```\n\n"
                           f"**Previous release (241) data:**\n```{issues_by_type_old}```"
            },
            {
                "role": "user",
                "content": """
To proceed with the analysis, follow these steps:

1. **Step-by-Step Comparison**: Break down the issue types in both releases and compare their frequencies. Calculate percentage changes where applicable.

2. **Trend Identification**: Look for any significant increases or decreases in issue types. Determine if there are emerging patterns or persistent problems.

3. **Concerns and Improvements**: Highlight any categories that have worsened or improved significantly. Assess if there are any issues that need urgent attention.

4. **Recommendations**: Based on your findings, provide detailed recommendations to improve the quality of future releases. Prioritize areas with the most significant changes or potential impact.

Take your time to analyze the data thoroughly and provide a comprehensive response.
"""
            }
        ]
    )
    print(completion.choices[0].message.content)

client = requests.Session()
client.headers.update(headers)

cycle_dates_query = f"created: {dates242}"
additional_query = "created by: jetbrains-team"
query = f"project:ReSharper and {cycle_dates_query} and {additional_query}"

issues_by_type = get_data(query)

cycle_dates_old_query = f"created: {dates241}"
query_old = f"project:ReSharper and {cycle_dates_old_query} and {additional_query}"

issues_by_type_old = get_data(query_old)

# Bugs created by users after release "project: resharper created by: -jetbrains-team created: 2024-08-15 .. today sort by: priority"
cycle_dates_query = f"created: {dates243}"
additional_query = "created by: -jetbrains-team"
query = f"project:ReSharper and {cycle_dates_query} and {additional_query}"

issues_by_type = get_data(query)

# Send data to AI
#AskAI()
