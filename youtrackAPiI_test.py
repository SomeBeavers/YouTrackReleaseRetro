import os
from typing import List, Dict

import matplotlib.pyplot as plt
import requests
from openai import OpenAI

import numpy as np

AI_STEPS_MESSAGE = """
    To proceed with the analysis, follow these steps:

    1. **Step-by-Step Comparison**: Break down the issue types in releases and compare their frequencies. Calculate percentage changes where applicable.

    2. **Trend Identification**: Look for any significant increases or decreases in issue types. Determine if there are emerging patterns or persistent problems.

    3. **Concerns and Improvements**: Highlight any categories that have worsened or improved significantly. Assess if there are any issues that need urgent attention.

    4. **Recommendations**: Based on your findings, provide detailed recommendations to improve the quality of future releases. Prioritize areas with the most significant changes or potential impact.

    Take your time to analyze the data thoroughly and provide a comprehensive response. Focus on latest release.
    """

AI_CONTENT_MESSAGE_CREATED_ISSUES_BY_TYPES = """
    Hello! I need your expertise to analyze the quality of ReSharper's latest release. Specifically, I would like you to:

    1. Compare the Distribution of Issues: Examine and compare the distribution of issue types.

    2. Identify Significant Trends or Changes: Highlight any notable trends, increases, or decreases in issues between releases.

    3. Highlight Areas of Concern or Improvement: Identify any issue categories that have shown significant changes or may indicate potential areas for improvement.

    4. Provide Actionable Recommendations: Based on your analysis, offer practical recommendations to address any identified issues or trends.
    """

AI_CONTENT_MESSAGE_CREATED_ISSUES_BY_PRIORITIES = """
    Hello! I need your expertise to analyze the quality of ReSharper's latest release. Specifically, I would like you to:

    1. Compare the Distribution of Issues: Examine and compare the distribution of issue priorities.

    2. Identify Significant Trends or Changes: Highlight any notable trends, increases, or decreases in issues between releases.

    3. Highlight Areas of Concern or Improvement: Identify any issue categories that have shown significant changes or may indicate potential areas for improvement.

    4. Provide Actionable Recommendations: Based on your analysis, offer practical recommendations to address any identified issues or trends.
    """

AI_DESCRIPTION_OF_DATA = "It shows how many issues of each type were reported by ReSharper team members:"
AI_DESCRIPTION_OF_DATA_PRIORITIES_2_WEEKS = "It shows distributions of issues reported by users 2 weeks after each release by priority:"

AI_SYSTEM_MESSAGE = "You are an expert Quality Assurance Lead at JetBrains with extensive knowledge of ReSharper's functionality, release cycles, and quality metrics. Your task is to analyze the distribution of issues reported in the recent ReSharper releases, providing a detailed comparison and actionable insights."

dates242_2weeks = "2024-08-15 .. 2024-08-29"
dates242 = "2024-04-10 .. 2024-08-14"
dates241_2weeks = "2024-04-10 .. 2024-04-24"
dates241 = "2023-12-07 .. 2024-04-09"
dates233_2weeks = "2023-12-07 .. 2023-12-21"
dates233 = "2023-08-02 .. 2023-12-06"
dates232_2weeks = "2023-08-02 .. 2023-08-16"
dates232 = "2023-04-05 .. 2023-08-01"

PRIORITIES = ['Show-stopper', 'Critical', 'Major', 'Normal', 'Minor']

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

    def plot_issues_by_priority(self, priority_counts: Dict[str, int], dates: str):
        sorted_priorities = sorted(priority_counts.items(), key=lambda x: x[1], reverse=True)
        sorted_labels, sorted_counts = zip(*sorted_priorities)

        plt.figure(figsize=(10, 6))
        plt.bar(sorted_labels, sorted_counts, color='skyblue')

        plt.title(f'Number of Issues by Priority ({dates})')
        plt.xlabel('Priority')
        plt.ylabel('Number of Issues')
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.show()

    def plot_multiple_priority_dicts(self, priority_dicts: Dict[str, Dict[str, int]]):
        # Setting up the bar width
        bar_width = 0.2  # Adjust this to fit your needs
        index = np.arange(len(PRIORITIES))

        # Plotting each dictionary's data
        plt.figure(figsize=(12, 6))

        for i, (label, priority_counts) in enumerate(priority_dicts.items()):
            counts = [priority_counts.get(priority, 0) for priority in PRIORITIES]
            plt.bar(index + i * bar_width, counts, bar_width, label=label)

        # Adding titles and labels
        plt.title('Comparison of Issues by Priority Across Multiple Periods')
        plt.xlabel('Priority')
        plt.ylabel('Number of Issues')
        plt.xticks(index + bar_width * (len(priority_dicts) - 1) / 2, PRIORITIES, rotation=45)
        plt.legend()
        plt.tight_layout()

        plt.show()

    def plot_created_vs_fixed(self, data_created: Dict[str, Dict[str, int]], data_fixed: Dict[str, Dict[str, int]]):
        # Pastel colors for bars
        pastel_colors = [
            '#AEC6CF', '#FFB347', '#77DD77', '#FF6961',  # Original colors
            '#CFCFC4', '#FDFD96', '#836953', '#CB99C9',  # Additional pastel colors
            '#F49AC2', '#B39EB5', '#FFB6C1', '#FFD1DC'  # More pastel colors
        ]
        categories = PRIORITIES

        x = np.arange(len(categories))  # the label locations
        width = 0.15  # the width of the bars

        fig, ax = plt.subplots(figsize=(14, 8))

        fixed_bars = []

        # Loop through data and plot both created and fixed bars
        for i, (key, color) in enumerate(zip(data_created.keys(), pastel_colors)):
            # Extracting the values
            created_values = [data_created[key].get(priority, 0) for priority in categories]
            fixed_values = [data_fixed[key].get(priority, 0) for priority in categories]

            # Plotting the created bars with less visibility
            ax.bar(x + (i - 2) * width, created_values, width, label=f'{key} - created', color=color, alpha=0.4)

            # Plotting the fixed bars on top of the created bars
            rect = ax.bar(x + (i - 2) * width, fixed_values, width, label=f'{key}', color=color)
            fixed_bars.append(rect)

        # Add some text for labels, title and custom x-axis tick labels, etc.
        ax.set_xlabel('Priority')
        ax.set_ylabel('Count')
        ax.set_title('Distribution of Priorities')
        ax.set_xticks(x)
        ax.set_xticklabels(categories)
        ax.legend()

        # Function to add the numerical labels on top of the bars
        def add_labels(rects):
            for rect in rects:
                height = rect.get_height()
                ax.annotate('{}'.format(height),
                            xy=(rect.get_x() + rect.get_width() / 2, height),
                            xytext=(0, 3),  # 3 points vertical offset
                            textcoords="offset points",
                            ha='center', va='bottom')

        # Function to add the percentage labels on top of the bars
        def add_labels_percentage(rects, fixed_values, created_values):
            for rect, fixed, created in zip(rects, fixed_values, created_values):
                percent = (fixed / created) * 100 if created != 0 else 0
                ax.annotate(f'{percent:.1f}%',
                            xy=(rect.get_x() + rect.get_width() / 2, fixed),
                            xytext=(0, 3),  # 3 points vertical offset
                            textcoords="offset points",
                            ha='center', va='bottom')

        total_values = [sum(data_fixed[key].get(priority, 0) for key in data_fixed.keys()) for priority in categories]

        for rects in fixed_bars:
            add_labels(rects)

        fig.tight_layout()
        plt.show()


def ask_ai_issues_by_types(data: Dict[str, Dict[str, int]]):
    #global client
    client = OpenAI()
    # Assemble the prompt manually
    prompt = ""
    for message in [
        {"role": "system",
         "content": AI_SYSTEM_MESSAGE},
        {
            "role": "user",
            "content": AI_CONTENT_MESSAGE_CREATED_ISSUES_BY_TYPES
        },
        {
            "role": "user",
            "content": f"Here is the data for the analysis. {AI_DESCRIPTION_OF_DATA}\n\n"
                       + "\n\n".join([f"**{release}:**\n```{issues}```"
                                      for release, issues in data.items()])
        },
        {
            "role": "user",
            "content": AI_STEPS_MESSAGE
        }
    ]:
        prompt += f"{message['role'].capitalize()}: {message['content'].strip()}\n\n"
    # Print the assembled prompt
    print(prompt)

    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system",
             "content": AI_SYSTEM_MESSAGE},
            {
                "role": "user",
                "content": AI_CONTENT_MESSAGE_CREATED_ISSUES_BY_TYPES
            },
            {
                "role": "user",
                "content": f"Here is the data for the analysis. {AI_DESCRIPTION_OF_DATA}\n\n"
                           + "\n\n".join([f"**{release}:**\n```{issues}```"
                                          for release, issues in data.items()])
            },
            {
                "role": "user",
                "content": AI_STEPS_MESSAGE
            }
        ]
    )
    print(completion.choices[0].message.content)

def ask_ai_issues_by_priorities_2_weeks(data: Dict[str, Dict[str, int]]):
    #global client
    client = OpenAI()
    # Assemble the prompt manually
    prompt = ""
    for message in [
        {"role": "system",
         "content": AI_SYSTEM_MESSAGE},
        {
            "role": "user",
            "content": AI_CONTENT_MESSAGE_CREATED_ISSUES_BY_PRIORITIES
        },
        {
            "role": "user",
            "content": f"Here is the data for the analysis. {AI_DESCRIPTION_OF_DATA_PRIORITIES_2_WEEKS}\n\n"
                       + "\n\n".join([f"**{release}:**\n```{issues}```"
                                      for release, issues in data.items()])
        },
        {
            "role": "user",
            "content": AI_STEPS_MESSAGE
        }
    ]:
        prompt += f"{message['role'].capitalize()}: {message['content'].strip()}\n\n"
    # Print the assembled prompt
    print(prompt)

    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system",
             "content": AI_SYSTEM_MESSAGE},
            {
                "role": "user",
                "content": AI_CONTENT_MESSAGE_CREATED_ISSUES_BY_PRIORITIES
            },
            {
                "role": "user",
                "content": f"Here is the data for the analysis. {AI_DESCRIPTION_OF_DATA_PRIORITIES_2_WEEKS}\n\n"
                           + "\n\n".join([f"**{release}:**\n```{issues}```"
                                          for release, issues in data.items()])
            },
            {
                "role": "user",
                "content": AI_STEPS_MESSAGE
            }
        ]
    )
    print(completion.choices[0].message.content)

client = requests.Session()
client.headers.update(headers)

# Get tickets created by jetbrains-team
#242
cycle_dates_query_242 = f"created: {dates242}"
additional_query = "created by: jetbrains-team"
query_242 = f"project:ReSharper and {cycle_dates_query_242} and {additional_query}"

handler = GetIssues(client, query_242)
issues_by_priority_242 = handler.get_all_issues_by_priority()
issues_by_type_242 = handler.get_issues_by_type()

#241
cycle_dates_query_241 = f"created: {dates241}"
query_241 = f"project:ReSharper and {cycle_dates_query_241} and {additional_query}"

handler = GetIssues(client, query_241)
issues_by_priority_241 = handler.get_all_issues_by_priority()
issues_by_type_241 = handler.get_issues_by_type()

#233
cycle_dates_query_233 = f"created: {dates233}"
query_233 = f"project:ReSharper and {cycle_dates_query_233} and {additional_query}"

handler = GetIssues(client, query_233)
issues_by_priority_233 = handler.get_all_issues_by_priority()
issues_by_type_233 = handler.get_issues_by_type()

#232
cycle_dates_query_232 = f"created: {dates232}"
query_232 = f"project:ReSharper and {cycle_dates_query_232} and {additional_query}"

handler = GetIssues(client, query_232)
issues_by_priority_232 = handler.get_all_issues_by_priority()
issues_by_type_232 = handler.get_issues_by_type()


created_by_jetbrains_team = {
    f"Release 242 ({cycle_dates_query_242})": issues_by_priority_242,
    f"Release 241 ({cycle_dates_query_241})": issues_by_priority_241,
    f"Release 233 ({cycle_dates_query_233})": issues_by_priority_233,
    f"Release 232 ({cycle_dates_query_232})": issues_by_priority_232,
}

created_by_jetbrains_team_by_type = {
    f"Release 242": issues_by_type_242,
    f"Release 241": issues_by_type_241,
    f"Release 233": issues_by_type_233,
    f"Release 232": issues_by_type_232,
}

# Send data to AI
ask_ai_issues_by_types(created_by_jetbrains_team_by_type)

# Get fixed tickets created by jetbrains-team
#242
additional_query_fixed = "created by: jetbrains-team and (state: fixed or state: Verified)"
query_242_fixed = f"project:ReSharper and {cycle_dates_query_242} and {additional_query_fixed}"

handler = GetIssues(client, query_242_fixed)
fixed_issues_by_priority_242 = handler.get_all_issues_by_priority()
fixed_issues_by_type_242 = handler.get_issues_by_type()

#241
query_241_fixed = f"project:ReSharper and {cycle_dates_query_241} and {additional_query_fixed}"

handler = GetIssues(client, query_241_fixed)
fixed_issues_by_priority_241 = handler.get_all_issues_by_priority()
fixed_issues_by_type_241 = handler.get_issues_by_type()

#233
query_233_fixed = f"project:ReSharper and {cycle_dates_query_233} and {additional_query_fixed}"

handler = GetIssues(client, query_233_fixed)
fixed_issues_by_priority_233 = handler.get_all_issues_by_priority()
fixed_issues_by_type_233 = handler.get_issues_by_type()

#232
query_232_fixed = f"project:ReSharper and {cycle_dates_query_232} and {additional_query_fixed}"

handler = GetIssues(client, query_232_fixed)
fixed_issues_by_priority_232 = handler.get_all_issues_by_priority()
fixed_issues_by_type_232 = handler.get_issues_by_type()

fixed_by_jetbrains_team = {
    f"Release 242 ({cycle_dates_query_242})": fixed_issues_by_priority_242,
    f"Release 241 ({cycle_dates_query_241})": fixed_issues_by_priority_241,
    f"Release 233 ({cycle_dates_query_233})": fixed_issues_by_priority_233,
    f"Release 232 ({cycle_dates_query_232})": fixed_issues_by_priority_232,
}

handler.plot_created_vs_fixed(created_by_jetbrains_team, fixed_by_jetbrains_team)

# Bugs created by users 2 weeks after release "project: resharper created by: -jetbrains-team created: 2024-08-15 .. today sort by: priority"
#242
dates242_2weeks_query = f"created: {dates242_2weeks}"
additional_query = "created by: -jetbrains-team"
query = f"project:ReSharper and {dates242_2weeks_query} and {additional_query}"

issues_handler = GetIssues(client, query)
issues_by_priority_242 = issues_handler.get_bugs_by_priority()
#issues_handler.plot_issues_by_priority(issues_by_priority_242, cycle_dates_query_242)

#241
dates241_2weeks_query = f"created: {dates241_2weeks}"
additional_query = "created by: -jetbrains-team"
query = f"project:ReSharper and {dates241_2weeks_query} and {additional_query}"

issues_handler = GetIssues(client, query)
issues_by_priority_241 = issues_handler.get_bugs_by_priority()
#issues_handler.plot_issues_by_priority(issues_by_priority_241, cycle_dates_query_241)

#233
dates233_2weeks_query = f"created: {dates233_2weeks}"
additional_query = "created by: -jetbrains-team"
query = f"project:ReSharper and {dates233_2weeks_query} and {additional_query}"

issues_handler = GetIssues(client, query)
issues_by_priority_233 = issues_handler.get_bugs_by_priority()

#232
dates232_2weeks_query = f"created: {dates232_2weeks}"
additional_query = "created by: -jetbrains-team"
query = f"project:ReSharper and {dates232_2weeks_query} and {additional_query}"

issues_handler = GetIssues(client, query)
issues_by_priority_232 = issues_handler.get_bugs_by_priority()

priority_dicts = {
    f"Release 242 ({dates242_2weeks_query})": issues_by_priority_242,
    f"Release 241 ({dates241_2weeks_query})": issues_by_priority_241,
    f"Release 233 ({dates233_2weeks_query})": issues_by_priority_233,
    f"Release 232 ({dates232_2weeks_query})": issues_by_priority_232,
}

issues_handler.plot_multiple_priority_dicts(priority_dicts)

# Send data to AI
ask_ai_issues_by_priorities_2_weeks(priority_dicts)


