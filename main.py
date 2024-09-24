import os
from collections import defaultdict
from itertools import islice

import requests

import markdown_writer
from markdown_writer import initialize_markdown, append_markdown, write_table

import youtrack
from youtrack import GetIssues

import plotter
from plotter import plot_created_vs_fixed_by_category, plot_multiple_priority_dicts, plot_by_subsystems_several_releases

import re

from datetime import datetime

import ai_analysis
from ai_analysis import ask_ai_issues_by_types, ask_ai_issues_by_priorities_2_weeks, ask_ai_issues_between_bugfixes

dates242_2weeks = "2024-08-15 .. 2024-08-29"
dates242_1 = "2024-08-15 .. 2024-08-19"
dates242_2 = "2024-08-20 .. 2024-08-25"
dates242_3 = "2024-08-26 .. 2024-08-30"
dates242 = "2024-04-10 .. 2024-08-14"
START_DATE_242 = datetime(2024, 4, 10)
END_DATE_242 = datetime(2024, 8, 14)

dates_242_available_in = "2024.2.*"

dates241_2weeks = "2024-04-10 .. 2024-04-24"
dates241 = "2023-12-07 .. 2024-04-09"
dates233_2weeks = "2023-12-07 .. 2023-12-21"
dates233 = "2023-08-02 .. 2023-12-06"
dates232_2weeks = "2023-08-02 .. 2023-08-16"
dates232 = "2023-04-05 .. 2023-08-01"


# Create directories if they don't exist
os.makedirs(markdown_writer.IMAGES_DIR, exist_ok=True)

# Initialize the markdown file
initialize_markdown()

client = requests.Session()
client.headers.update(youtrack.headers)

# TODO: update release version
def extract_2024_2_value(available_in: str):
    # Use a regex to match "2024.2.*"
    match = re.search(r'2024\.2\.[^\s]*', available_in)
    return match.group(0) if match else None

def get_issues_by_subsystems():
    append_markdown("## Issues Created By Subsystems")

    # 242
    cycle_dates_query_242 = f"created: {dates242}"
    query_242 = f"project:ReSharper and {cycle_dates_query_242}"

    handler = GetIssues(client, query_242)
    issues_242 = handler.get_issues_by()
    # sorted_subsystems_242 = dict(sorted(issues_242[youtrack.SUBSYSTEM].items(), key=lambda item: item[1], reverse=True))


    # 241
    cycle_dates_query_241 = f"created: {dates241}"
    query_241 = f"project:ReSharper and {cycle_dates_query_241}"

    handler = GetIssues(client, query_241)
    issues_241 = handler.get_issues_by()


    created_by_subsystem= {
        f"Release 241": issues_241[youtrack.SUBSYSTEM],
        f"Release 242": issues_242[youtrack.SUBSYSTEM],
        # f"Release 242": sorted_subsystems_242,
    }

    created_by_priority= {
        f"Release 241": issues_241[youtrack.PRIORITY],
        f"Release 242": issues_242[youtrack.PRIORITY],
        # f"Release 242": sorted_subsystems_242,
    }

    plot3 = plot_by_subsystems_several_releases(created_by_subsystem, "Issues created by subsystems", youtrack.SUBSYSTEM)
    append_markdown("![Issues created 'by subsystem'](images/" + os.path.basename(plot3) + ")")

    plot4 = plot_multiple_priority_dicts(created_by_priority, "Issues created by priority", youtrack.PRIORITY)
    append_markdown("![Issues created by priority](images/" + os.path.basename(plot4) + ")")

def get_issues_created_by_jetbrains_team_vs_fixed():
    # Get tickets created by jetbrains-team
    append_markdown("## Issues Created By jetbrains-team vs Fixed")

    # 242
    cycle_dates_query_242 = f"created: {dates242}"
    additional_query = "created by: jetbrains-team and created by: -dotnet-support"
    query_242 = f"project:ReSharper and {cycle_dates_query_242} and ({additional_query})"

    handler = GetIssues(client, query_242)
    issues_by_priority_242 = handler.get_all_issues_by_priority()
    issues_by_type_242 = handler.get_issues_by_type()

    # 241
    cycle_dates_query_241 = f"created: {dates241}"
    query_241 = f"project:ReSharper and {cycle_dates_query_241} and ({additional_query})"

    handler = GetIssues(client, query_241)
    issues_by_priority_241 = handler.get_all_issues_by_priority()
    issues_by_type_241 = handler.get_issues_by_type()

    # 233
    cycle_dates_query_233 = f"created: {dates233}"
    query_233 = f"project:ReSharper and {cycle_dates_query_233} and ({additional_query})"

    handler = GetIssues(client, query_233)
    issues_by_priority_233 = handler.get_all_issues_by_priority()
    issues_by_type_233 = handler.get_issues_by_type()

    # 232
    cycle_dates_query_232 = f"created: {dates232}"
    query_232 = f"project:ReSharper and {cycle_dates_query_232} and ({additional_query})"

    handler = GetIssues(client, query_232)
    issues_by_priority_232 = handler.get_all_issues_by_priority()
    issues_by_type_232 = handler.get_issues_by_type()

    created_by_jetbrains_team = {
        f"Release 232 ({cycle_dates_query_232})": issues_by_priority_232,
        f"Release 233 ({cycle_dates_query_233})": issues_by_priority_233,
        f"Release 241 ({cycle_dates_query_241})": issues_by_priority_241,
        f"Release 242 ({cycle_dates_query_242})": issues_by_priority_242,
    }

    created_by_jetbrains_team_by_type = {
        f"Release 232": issues_by_type_232,
        f"Release 233": issues_by_type_233,
        f"Release 241": issues_by_type_241,
        f"Release 242": issues_by_type_242,
    }

    # Get fixed tickets created by jetbrains-team

    # 242
    additional_query_fixed = "created by: jetbrains-team and created by: -dotnet-support and (state: fixed or state: Verified)"
    query_242_fixed = f"project:ReSharper and {cycle_dates_query_242} and ({additional_query_fixed})"

    handler = GetIssues(client, query_242_fixed)
    fixed_issues_by_priority_242 = handler.get_all_issues_by_priority()
    fixed_issues_by_type_242 = handler.get_issues_by_type()

    # 241
    query_241_fixed = f"project:ReSharper and {cycle_dates_query_241} and {additional_query_fixed}"

    handler = GetIssues(client, query_241_fixed)
    fixed_issues_by_priority_241 = handler.get_all_issues_by_priority()
    fixed_issues_by_type_241 = handler.get_issues_by_type()

    # 233
    query_233_fixed = f"project:ReSharper and {cycle_dates_query_233} and {additional_query_fixed}"

    handler = GetIssues(client, query_233_fixed)
    fixed_issues_by_priority_233 = handler.get_all_issues_by_priority()
    fixed_issues_by_type_233 = handler.get_issues_by_type()

    # 232
    query_232_fixed = f"project:ReSharper and {cycle_dates_query_232} and {additional_query_fixed}"

    handler = GetIssues(client, query_232_fixed)
    fixed_issues_by_priority_232 = handler.get_all_issues_by_priority()
    fixed_issues_by_type_232 = handler.get_issues_by_type()

    fixed_by_jetbrains_team = {
        f"Release 232 ({cycle_dates_query_232})": fixed_issues_by_priority_232,
        f"Release 233 ({cycle_dates_query_233})": fixed_issues_by_priority_233,
        f"Release 241 ({cycle_dates_query_241})": fixed_issues_by_priority_241,
        f"Release 242 ({cycle_dates_query_242})": fixed_issues_by_priority_242,
    }

    fixed_by_jetbrains_team_by_type = {
        f"Release 232": fixed_issues_by_type_232,
        f"Release 233": fixed_issues_by_type_233,
        f"Release 241": fixed_issues_by_type_241,
        f"Release 242": fixed_issues_by_type_242,
    }

    plot1 = plot_created_vs_fixed_by_category(plotter.PRIORITIES, created_by_jetbrains_team, fixed_by_jetbrains_team,
                                              "Distribution of issues by priorities (created by jetbrains-team vs fixed)")
    append_markdown("![Issues created by jetbrains-team by priority](images/" + os.path.basename(plot1) + ")")

    plot2 = plot_created_vs_fixed_by_category(plotter.TYPES, created_by_jetbrains_team_by_type,
                                              fixed_by_jetbrains_team_by_type,
                                              "Distribution of issues by types (created by jetbrains-team vs fixed)")
    append_markdown("![Issues created by jetbrains-team by types](images/" + os.path.basename(plot2) + ")")

    # # Send data to AI
    # append_markdown("## AI analysis for issues created by jetbrains-team")
    # ai_response = ask_ai_issues_by_types(created_by_jetbrains_team, fixed_by_jetbrains_team)
    # append_markdown(f"\n{ai_response}\n")

def get_issues_created_by_users_2_weeks_after_release():
    # Bugs created by users 2 weeks after release "project: resharper created by: -jetbrains-team created: 2024-08-15 .. today sort by: priority"
    append_markdown("## Issues created by users 2 weeks after the release")

    # 242
    dates242_2weeks_query = f"created: {dates242_2weeks}"
    additional_query = "created by: -jetbrains-team or created by: dotnet-support"
    query = f"project:ReSharper and {dates242_2weeks_query} and ({additional_query})"

    issues_handler = GetIssues(client, query)
    issues_by_priority_242 = issues_handler.get_bugs_by_priority()
    # issues_handler.plot_issues_by_priority(issues_by_priority_242, cycle_dates_query_242)

    # 241
    dates241_2weeks_query = f"created: {dates241_2weeks}"
    query = f"project:ReSharper and {dates241_2weeks_query} and ({additional_query})"

    issues_handler = GetIssues(client, query)
    issues_by_priority_241 = issues_handler.get_bugs_by_priority()
    # issues_handler.plot_issues_by_priority(issues_by_priority_241, cycle_dates_query_241)

    # 233
    dates233_2weeks_query = f"created: {dates233_2weeks}"
    query = f"project:ReSharper and {dates233_2weeks_query} and ({additional_query})"

    issues_handler = GetIssues(client, query)
    issues_by_priority_233 = issues_handler.get_bugs_by_priority()

    # 232
    dates232_2weeks_query = f"created: {dates232_2weeks}"
    query = f"project:ReSharper and {dates232_2weeks_query} and ({additional_query})"

    issues_handler = GetIssues(client, query)
    issues_by_priority_232 = issues_handler.get_bugs_by_priority()

    priority_dicts = {
        f"Release 232 ({dates232_2weeks_query})": issues_by_priority_232,
        f"Release 233 ({dates233_2weeks_query})": issues_by_priority_233,
        f"Release 241 ({dates241_2weeks_query})": issues_by_priority_241,
        f"Release 242 ({dates242_2weeks_query})": issues_by_priority_242,
    }

    plot3 = plot_multiple_priority_dicts(priority_dicts, "Issues created by users 2 weeks after the release", youtrack.PRIORITY)
    append_markdown("![Issues created by jetbrains-team by priority](images/" + os.path.basename(plot3) + ")")

    # # Send data to AI
    # append_markdown("## AI analysis for issues created by users 2 weeks after release")
    # ai_response = ask_ai_issues_by_priorities_2_weeks(priority_dicts)
    # append_markdown(f"\n{ai_response}\n")

def get_issues_in_bugfix():
    # Bugs created by users in 242 between bugfixes
    append_markdown("## Issues created by users in 242 release between bugfixes")

    # 2024.2 - 2024.2.1
    created_242_1 = f"created: {dates242_1}"
    additional_query = "created by: -jetbrains-team or created by: dotnet-support"
    query_242_1 = f"project:ReSharper and {created_242_1} and ({additional_query})"

    issues_handler = GetIssues(client, query_242_1)
    issues_by_priority_242_1 = issues_handler.get_bugs_by_priority()

    # 2024.2.1 - 2024.2.2
    created_242_2 = f"created: {dates242_2}"
    query_242_2 = f"project:ReSharper and {created_242_2} and ({additional_query})"

    issues_handler = GetIssues(client, query_242_2)
    issues_by_priority_242_2 = issues_handler.get_bugs_by_priority()

    # 2024.2.2 - 2024.2.3
    created_242_3 = f"created: {dates242_3}"
    query_242_3 = f"project:ReSharper and {created_242_3} and ({additional_query})"

    issues_handler = GetIssues(client, query_242_3)
    issues_by_priority_242_3 = issues_handler.get_bugs_by_priority()

    created_by_users = {
        f"2024.2 - 2024.2.1": issues_by_priority_242_1,
        f"2024.2.1 - 2024.2.2": issues_by_priority_242_2,
        f"2024.2.2 - 2024.2.3": issues_by_priority_242_3,
    }

    plot4 = plot_multiple_priority_dicts(created_by_users, "Issues created by users between bugfixes", youtrack.PRIORITY)
    append_markdown("![Issues created by jetbrains-team by priority](images/" + os.path.basename(plot4) + ")")

    # # Send data to AI
    # append_markdown("## AI analysis for issues created by users between bugfixes")
    # ai_response = ask_ai_issues_between_bugfixes(created_by_users)
    # append_markdown(f"\n{ai_response}\n")


    # additional_query_fixed = "(state: fixed or state: Verified)"
    # query_242_1_fixed = query_242_1 + f" and {additional_query_fixed}"
    # handler = GetIssues(client, query_242_1_fixed)
    # fixed_issues_by_priority_242_1 = handler.get_all_issues_by_priority()


# Issues fixed in bugfix: Available in: 2024.2.*
def get_issues_fixed_in_bugfix():
    # Issues fixed in bugfix
    append_markdown("## Issues which were fixed in bugfix")

    # 2024.2.*
    available_in_bugfix = f"Available in: {dates_242_available_in}"
    additional_query = "#resolved"
    query_242_1 = f"project:ReSharper and {available_in_bugfix} and ({additional_query})"

    issues_handler = GetIssues(client, query_242_1)
    issues_available_in_bugfix_242 = issues_handler.get_issues()

    # Function to extract the first matching 2024.2.* value from the "Available in" field


    # Sort the issues first by "Available in" (filtered for 2024.2.*), then by "Subsystem", and lastly by "Priority"
    sorted_issues = sorted(
        issues_available_in_bugfix_242,
        key=lambda issue: (
            extract_2024_2_value(issue.available_in) if issue.available_in else "",
            issue.subsystem if issue.subsystem else "",
            plotter.PRIORITIES.index(issue.priority) if issue.priority in plotter.PRIORITIES else len(plotter.PRIORITIES)  # Sort by priority based on its index in PRIORITIES
        )
    )

    # Prepare table data
    headers = ["Available in", "Subsystem", "Priority", "Summary"]
    rows = []

    for issue in sorted_issues:
        # Extract only the 2024.2.* value to display
        available_in_value = extract_2024_2_value(issue.available_in)
        if available_in_value:
            rows.append([
                available_in_value,
                issue.subsystem if issue.subsystem else "N/A",
                issue.priority if issue.priority else "N/A",
                issue.summary,
            ])

    # Write the table to markdown
    write_table(headers, rows)

def split_dict(input_dict, n):
    """Helper function to split dictionary into chunks of n items."""
    iterator = iter(input_dict)
    for _ in range(0, len(input_dict), n):
        yield {k: input_dict[k] for k in islice(iterator, n)}

# Get users comments added during release cycle
def get_users_comments():
    append_markdown("## Users comments added during release cycle")

    # 2024.2.*
    commented_242 = f"commented: {dates242}"
    # additional_query = "#unresolved"
    query_242 = f"project:ReSharper and ({commented_242}) "

    issues_handler = GetIssues(client, query_242)
    issues_242 = issues_handler.get_issues_with_comments()


    # Define the date range for filtering comments
    start_date = START_DATE_242
    end_date = END_DATE_242

    issue_comments_data = defaultdict(list)

    # Process issues and filter comments based on date and email
    for issue in issues_242:
        filtered_comments = []
        for comment in issue.comments:
            # Convert the created timestamp to a datetime object
            created_date = datetime.fromtimestamp(comment['created'] / 1000)  # Assuming timestamp is in milliseconds

            # Check if the comment was created between the start and end dates
            if start_date <= created_date <= end_date:
                # Safely check if the author's email is available and doesn't contain "@jetbrains.com"
                author = comment.get('author', None)
                if author and '@jetbrains.com' not in author:
                    filtered_comments.append(comment)
                    issue_comments_data[issue.id].append(comment['text'])

        # Replace the issue's comments with the filtered comments
        issue.comments = filtered_comments

    # print(issue_comments_data)
    # print("------------------------------------------")

    # Split the data into two parts
    num_splits = 4
    issue_comments_data_chunks = list(split_dict(issue_comments_data, len(issue_comments_data) // num_splits or 1))

    ai_responses = []

    for i in range(num_splits):
        # Pass chunk to AI
        append_markdown(f"## AI analysis for user's comments (Part {i})")
        ai_response_part1 = ai_analysis.ask_ai_about_comments(issue_comments_data_chunks[i])
        append_markdown(f"\n{ai_response_part1}\n")
        ai_responses.append(ai_response_part1)

    append_markdown(f"## AI analysis for user's comments (final)")
    final_response = ai_analysis.ask_ai_about_comments_combine(ai_responses)
    append_markdown(f"\n{final_response}\n")


# Run
get_issues_by_subsystems()
# get_issues_created_by_jetbrains_team_vs_fixed()
# get_issues_created_by_users_2_weeks_after_release()
# get_issues_in_bugfix()
# get_issues_fixed_in_bugfix()
# get_users_comments()

print(f"Report is generated.")

