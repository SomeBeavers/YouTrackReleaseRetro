import os
from collections import defaultdict
from itertools import islice
from typing import Any

import requests

import markdown_writer
from markdown_writer import initialize_markdown, append_markdown, write_table, compose_table

import youtrack
from youtrack import GetIssues

import plotter
from plotter import *

import re

import dates
from dates import *

import datetime
from datetime import date, datetime

import ai_analysis
from ai_analysis import *

# Create directories if they don't exist
os.makedirs(markdown_writer.IMAGES_DIR, exist_ok=True)

# Initialize the markdown file
initialize_markdown()

client = requests.Session()
client.headers.update(youtrack.headers)

def get_all_issues_count():
    append_markdown("## Issues Created During Release Cycle (including issues from jetbrains-team)")
    append_markdown("Defect Arrival Rate: Helps in understanding the stability of the release. A decreasing defect arrival rate over time usually indicates improving quality.")

    # TODO: add new release here (copy previous + update)

    # 251
    cycle_dates_query_251 = f"created: {dates251}"
    query_251 = f"project:ReSharper and {cycle_dates_query_251}"

    append_markdown("> Query : " + query_251)

    handler = GetIssues(client, query_251)
    issues_251 = handler.get_issues_count_by_various_parameters()

    #region Old releases
    # 243
    cycle_dates_query_243 = f"created: {dates243}"
    query_243 = f"project:ReSharper and {cycle_dates_query_243}"

    handler = GetIssues(client, query_243)
    issues_243 = handler.get_issues_count_by_various_parameters()

    # 242
    cycle_dates_query_242 = f"created: {dates242}"
    query_242 = f"project:ReSharper and {cycle_dates_query_242}"

    handler = GetIssues(client, query_242)
    issues_242 = handler.get_issues_count_by_various_parameters()

    # 241
    cycle_dates_query_241 = f"created: {dates.dates241}"
    query_241 = f"project:ReSharper and {cycle_dates_query_241}"

    handler = GetIssues(client, query_241)
    issues_241 = handler.get_issues_count_by_various_parameters()

    #endregion

    created_by_subsystem= {
        f"Release 241": issues_241[youtrack.SUBSYSTEM],
        f"Release 242": issues_242[youtrack.SUBSYSTEM],
        f"Release 243": issues_243[youtrack.SUBSYSTEM],
        f"Release 251": issues_251[youtrack.SUBSYSTEM],
        # TODO: add new release here
    }

    created_by_priority= {
        f"Release 241": issues_241[youtrack.PRIORITY],
        f"Release 242": issues_242[youtrack.PRIORITY],
        f"Release 243": issues_243[youtrack.PRIORITY],
        f"Release 251": issues_251[youtrack.PRIORITY],
        # TODO: add new release here
    }

    plot3 = plot_by_subsystems_several_releases(created_by_subsystem, "Issues created by subsystems", youtrack.SUBSYSTEM)
    append_markdown("![Issues created 'by subsystem'](images/" + os.path.basename(plot3) + ")")

    # Send data to AI
    append_markdown("### AI analysis")
    ai_response = ask_ai_issues_count_by_subsystem_several_releases(created_by_subsystem)
    append_markdown(f"\n{ai_response}\n")

    plot4 = plot_by_priority_several_releases(created_by_priority, "Issues created by priority", youtrack.PRIORITY)
    append_markdown("![Issues created by priority](images/" + os.path.basename(plot4) + ")")

    # Send data to AI
    append_markdown("### AI analysis")
    ai_response = ask_ai_issues_count_by_priority_several_releases(created_by_priority)
    append_markdown(f"\n{ai_response}\n")

def get_issues_created_by_jetbrains_team_vs_fixed():
    # Get tickets created by jetbrains-team
    append_markdown("## Issues Created By jetbrains-team vs Fixed")
    append_markdown("How many issues were created by jetbrains-team are fixed? Should we adjust testing?")

    # TODO: add new release here (copy previous + update)
    # 251
    cycle_dates_query_251 = f"created: {dates251}"
    additional_query = "created by: jetbrains-team and created by: -dotnet-support"
    query_251 = f"project:ReSharper and {cycle_dates_query_251} and ({additional_query})"

    append_markdown("> Query : " + query_251)

    handler = GetIssues(client, query_251)
    issues_by_priority_251 = handler.get_issues_count_by_priority()
    issues_by_type_251 = handler.get_issues_count_by_type()

    #region Old releases
    # 243
    cycle_dates_query_243 = f"created: {dates243}"
    query_243 = f"project:ReSharper and {cycle_dates_query_243} and ({additional_query})"

    handler = GetIssues(client, query_243)
    issues_by_priority_243 = handler.get_issues_count_by_priority()
    issues_by_type_243 = handler.get_issues_count_by_type()

    # 242
    cycle_dates_query_242 = f"created: {dates242}"
    additional_query = "created by: jetbrains-team and created by: -dotnet-support"
    query_242 = f"project:ReSharper and {cycle_dates_query_242} and ({additional_query})"

    handler = GetIssues(client, query_242)
    issues_by_priority_242 = handler.get_issues_count_by_priority()
    issues_by_type_242 = handler.get_issues_count_by_type()

    # 241
    cycle_dates_query_241 = f"created: {dates241}"
    query_241 = f"project:ReSharper and {cycle_dates_query_241} and ({additional_query})"

    handler = GetIssues(client, query_241)
    issues_by_priority_241 = handler.get_issues_count_by_priority()
    issues_by_type_241 = handler.get_issues_count_by_type()

    # 233
    cycle_dates_query_233 = f"created: {dates233}"
    query_233 = f"project:ReSharper and {cycle_dates_query_233} and ({additional_query})"

    handler = GetIssues(client, query_233)
    issues_by_priority_233 = handler.get_issues_count_by_priority()
    issues_by_type_233 = handler.get_issues_count_by_type()

    # 232
    cycle_dates_query_232 = f"created: {dates232}"
    query_232 = f"project:ReSharper and {cycle_dates_query_232} and ({additional_query})"

    handler = GetIssues(client, query_232)
    issues_by_priority_232 = handler.get_issues_count_by_priority()
    issues_by_type_232 = handler.get_issues_count_by_type()
    #endregion

    created_by_jetbrains_team_by_priority = {
        f"Release 232": issues_by_priority_232,
        f"Release 233": issues_by_priority_233,
        f"Release 241": issues_by_priority_241,
        f"Release 242": issues_by_priority_242,
        f"Release 243": issues_by_priority_243,
        f"Release 251": issues_by_priority_251,
        # TODO: add new release here
    }

    created_by_jetbrains_team_by_type = {
        f"Release 232": issues_by_type_232,
        f"Release 233": issues_by_type_233,
        f"Release 241": issues_by_type_241,
        f"Release 242": issues_by_type_242,
        f"Release 243": issues_by_type_243,
        f"Release 251": issues_by_type_251,
        # TODO: add new release here
    }

    # Get fixed tickets created by jetbrains-team

    # TODO: add new release here (copy previous + update)
    # 243
    additional_query_fixed = "created by: jetbrains-team and created by: -dotnet-support and (state: fixed or state: Verified)"
    query_251_fixed = f"project:ReSharper and {cycle_dates_query_251} and ({additional_query_fixed})"

    append_markdown("> Query : " + query_251_fixed)

    handler = GetIssues(client, query_251_fixed)
    fixed_issues_by_priority_251 = handler.get_issues_count_by_priority()
    fixed_issues_by_type_251 = handler.get_issues_count_by_type()

    #region Old releases
    # 243
    query_243_fixed = f"project:ReSharper and {cycle_dates_query_243} and ({additional_query_fixed})"

    handler = GetIssues(client, query_243_fixed)
    fixed_issues_by_priority_243 = handler.get_issues_count_by_priority()
    fixed_issues_by_type_243 = handler.get_issues_count_by_type()

    # 242
    additional_query_fixed = "created by: jetbrains-team and created by: -dotnet-support and (state: fixed or state: Verified)"
    query_242_fixed = f"project:ReSharper and {cycle_dates_query_242} and ({additional_query_fixed})"

    handler = GetIssues(client, query_242_fixed)
    fixed_issues_by_priority_242 = handler.get_issues_count_by_priority()
    fixed_issues_by_type_242 = handler.get_issues_count_by_type()

    # 241
    query_241_fixed = f"project:ReSharper and {cycle_dates_query_241} and {additional_query_fixed}"

    handler = GetIssues(client, query_241_fixed)
    fixed_issues_by_priority_241 = handler.get_issues_count_by_priority()
    fixed_issues_by_type_241 = handler.get_issues_count_by_type()

    # 233
    query_233_fixed = f"project:ReSharper and {cycle_dates_query_233} and {additional_query_fixed}"

    handler = GetIssues(client, query_233_fixed)
    fixed_issues_by_priority_233 = handler.get_issues_count_by_priority()
    fixed_issues_by_type_233 = handler.get_issues_count_by_type()

    # 232
    query_232_fixed = f"project:ReSharper and {cycle_dates_query_232} and {additional_query_fixed}"

    handler = GetIssues(client, query_232_fixed)
    fixed_issues_by_priority_232 = handler.get_issues_count_by_priority()
    fixed_issues_by_type_232 = handler.get_issues_count_by_type()
    #endregion

    fixed_by_jetbrains_team_by_priority = {
        f"Release 232": fixed_issues_by_priority_232,
        f"Release 233": fixed_issues_by_priority_233,
        f"Release 241": fixed_issues_by_priority_241,
        f"Release 242": fixed_issues_by_priority_242,
        f"Release 243": fixed_issues_by_priority_243,
        f"Release 251": fixed_issues_by_priority_251,
        # TODO: add new release here
    }

    fixed_by_jetbrains_team_by_type = {
        f"Release 232": fixed_issues_by_type_232,
        f"Release 233": fixed_issues_by_type_233,
        f"Release 241": fixed_issues_by_type_241,
        f"Release 242": fixed_issues_by_type_242,
        f"Release 243": fixed_issues_by_type_243,
        f"Release 251": fixed_issues_by_type_251,
        # TODO: add new release here
    }

    plot1 = plot_created_vs_fixed_by_category(plotter.PRIORITIES, created_by_jetbrains_team_by_priority, fixed_by_jetbrains_team_by_priority,
                                              "Distribution of issues by priorities (created by jetbrains-team vs fixed)")
    append_markdown("![Issues created by jetbrains-team by priority](images/" + os.path.basename(plot1) + ")")

    # Send data to AI
    append_markdown("### AI analysis")
    ai_response = ask_ai_created_by_team_vs_fixed_issues_by_priority(created_by_jetbrains_team_by_priority, fixed_by_jetbrains_team_by_priority)
    append_markdown(f"\n{ai_response}\n")

    plot2 = plot_created_vs_fixed_by_category(plotter.TYPES, created_by_jetbrains_team_by_type,
                                              fixed_by_jetbrains_team_by_type,
                                              "Distribution of issues by types (created by jetbrains-team vs fixed)")
    append_markdown("![Issues created by jetbrains-team by types](images/" + os.path.basename(plot2) + ")")

    # Send data to AI
    append_markdown("### AI analysis")
    ai_response = ask_ai_created_by_team_vs_fixed_issues_by_type(created_by_jetbrains_team_by_type, fixed_by_jetbrains_team_by_type)
    append_markdown(f"\n{ai_response}\n")

def get_issues_created_by_NOT_jetbrains_team_vs_fixed():
    # Get tickets created by users
    append_markdown("## Issues Created By Users vs Fixed")
    append_markdown("How many users' issues are fixed?")

    # TODO: add new release here (copy previous + update)
    # 251
    cycle_dates_query_251 = f"created: {dates251}"
    additional_query = "created by: -jetbrains-team or created by: dotnet-support"
    query_251 = f"project:ReSharper and {cycle_dates_query_251} and ({additional_query})"

    append_markdown("> Query : " + query_251)

    handler = GetIssues(client, query_251)
    issues_by_priority_251 = handler.get_issues_count_by_priority()
    issues_by_type_251 = handler.get_issues_count_by_type()

    #region Old releases
    # 243
    cycle_dates_query_243 = f"created: {dates243}"
    query_243 = f"project:ReSharper and {cycle_dates_query_243} and ({additional_query})"

    handler = GetIssues(client, query_243)
    issues_by_priority_243 = handler.get_issues_count_by_priority()
    issues_by_type_243 = handler.get_issues_count_by_type()

    # 242
    cycle_dates_query_242 = f"created: {dates242}"
    additional_query = "created by: -jetbrains-team or created by: dotnet-support"
    query_242 = f"project:ReSharper and {cycle_dates_query_242} and ({additional_query})"

    handler = GetIssues(client, query_242)
    issues_by_priority_242 = handler.get_issues_count_by_priority()
    issues_by_type_242 = handler.get_issues_count_by_type()

    # 241
    cycle_dates_query_241 = f"created: {dates.dates241}"
    query_241 = f"project:ReSharper and {cycle_dates_query_241} and ({additional_query})"

    handler = GetIssues(client, query_241)
    issues_by_priority_241 = handler.get_issues_count_by_priority()
    issues_by_type_241 = handler.get_issues_count_by_type()

    # 233
    cycle_dates_query_233 = f"created: {dates.dates233}"
    query_233 = f"project:ReSharper and {cycle_dates_query_233} and ({additional_query})"

    handler = GetIssues(client, query_233)
    issues_by_priority_233 = handler.get_issues_count_by_priority()
    issues_by_type_233 = handler.get_issues_count_by_type()

    # 232
    cycle_dates_query_232 = f"created: {dates.dates232}"
    query_232 = f"project:ReSharper and {cycle_dates_query_232} and ({additional_query})"

    handler = GetIssues(client, query_232)
    issues_by_priority_232 = handler.get_issues_count_by_priority()
    issues_by_type_232 = handler.get_issues_count_by_type()
    #endregion

    created_issues_by_priority = {
        f"Release 232": issues_by_priority_232,
        f"Release 233": issues_by_priority_233,
        f"Release 241": issues_by_priority_241,
        f"Release 242": issues_by_priority_242,
        f"Release 243": issues_by_priority_243,
        f"Release 251": issues_by_priority_251,
        # TODO: add new release here
    }

    created_issues_by_type = {
        f"Release 232": issues_by_type_232,
        f"Release 233": issues_by_type_233,
        f"Release 241": issues_by_type_241,
        f"Release 242": issues_by_type_242,
        f"Release 243": issues_by_type_243,
        f"Release 251": issues_by_type_251,
        # TODO: add new release here
    }

    # Get fixed tickets created by users

    # TODO: add new release here (copy previous + update)
    # 251
    additional_query_fixed = "(created by: -jetbrains-team or created by: dotnet-support) and (state: fixed or state: Verified)"
    query_251_fixed = f"project:ReSharper and {cycle_dates_query_251} and ({additional_query_fixed})"

    append_markdown("> Query : " + query_251_fixed)

    handler = GetIssues(client, query_251_fixed)
    fixed_issues_by_priority_251 = handler.get_issues_count_by_priority()
    fixed_issues_by_type_251 = handler.get_issues_count_by_type()

    #region Old releases
    # 243
    query_243_fixed = f"project:ReSharper and {cycle_dates_query_243} and ({additional_query_fixed})"

    handler = GetIssues(client, query_243_fixed)
    fixed_issues_by_priority_243 = handler.get_issues_count_by_priority()
    fixed_issues_by_type_243 = handler.get_issues_count_by_type()

    # 242
    additional_query_fixed = "(created by: -jetbrains-team or created by: dotnet-support) and (state: fixed or state: Verified)"
    query_242_fixed = f"project:ReSharper and {cycle_dates_query_242} and ({additional_query_fixed})"

    handler = GetIssues(client, query_242_fixed)
    fixed_issues_by_priority_242 = handler.get_issues_count_by_priority()
    fixed_issues_by_type_242 = handler.get_issues_count_by_type()

    # 241
    query_241_fixed = f"project:ReSharper and {cycle_dates_query_241} and {additional_query_fixed}"

    handler = GetIssues(client, query_241_fixed)
    fixed_issues_by_priority_241 = handler.get_issues_count_by_priority()
    fixed_issues_by_type_241 = handler.get_issues_count_by_type()

    # 233
    query_233_fixed = f"project:ReSharper and {cycle_dates_query_233} and {additional_query_fixed}"

    handler = GetIssues(client, query_233_fixed)
    fixed_issues_by_priority_233 = handler.get_issues_count_by_priority()
    fixed_issues_by_type_233 = handler.get_issues_count_by_type()

    # 232
    query_232_fixed = f"project:ReSharper and {cycle_dates_query_232} and {additional_query_fixed}"

    handler = GetIssues(client, query_232_fixed)
    fixed_issues_by_priority_232 = handler.get_issues_count_by_priority()
    fixed_issues_by_type_232 = handler.get_issues_count_by_type()
    #endregion

    fixed_issues_by_priority = {
        f"Release 232": fixed_issues_by_priority_232,
        f"Release 233": fixed_issues_by_priority_233,
        f"Release 241": fixed_issues_by_priority_241,
        f"Release 242": fixed_issues_by_priority_242,
        f"Release 243": fixed_issues_by_priority_243,
        f"Release 251": fixed_issues_by_priority_251,
        # TODO: add new release here
    }

    fixed_issues_by_type = {
        f"Release 232": fixed_issues_by_type_232,
        f"Release 233": fixed_issues_by_type_233,
        f"Release 241": fixed_issues_by_type_241,
        f"Release 242": fixed_issues_by_type_242,
        f"Release 243": fixed_issues_by_type_243,
        f"Release 251": fixed_issues_by_type_251,
        # TODO: add new release here
    }

    plot1 = plot_created_vs_fixed_by_category(plotter.PRIORITIES, created_issues_by_priority, fixed_issues_by_priority,
                                              "Distribution of issues by priorities (created by users vs fixed)")
    append_markdown("![Issues created by users by priority](images/" + os.path.basename(plot1) + ")")

    # Send data to AI
    append_markdown("### AI analysis")
    ai_response = ask_ai_created_by_not_team_vs_fixed_issues_by_priority(created_issues_by_priority, fixed_issues_by_priority)
    append_markdown(f"\n{ai_response}\n")

    plot2 = plot_created_vs_fixed_by_category(plotter.TYPES, created_issues_by_type,
                                              fixed_issues_by_type,
                                              "Distribution of issues by types (created by users vs fixed)")
    append_markdown("![Issues created by users by types](images/" + os.path.basename(plot2) + ")")

    # Send data to AI
    append_markdown("### AI analysis")
    ai_response = ask_ai_created_by_not_team_vs_fixed_issues_by_type(created_issues_by_type, fixed_issues_by_type)
    append_markdown(f"\n{ai_response}\n")

def get_issues_created_by_users_2_weeks_after_release():
    # Bugs created by users 2 weeks after release
    append_markdown("## Issues created by users 2 weeks after the release")
    append_markdown("Is release Ok?")

    # TODO: add new release here (copy previous + update)
    # 251
    dates251_2weeks_query = f"created: {dates251_2weeks}"
    additional_query = "created by: -jetbrains-team or created by: dotnet-support"
    query_251 = f"project:ReSharper and {dates251_2weeks_query} and ({additional_query})"

    append_markdown("> Query : " + query_251)

    issues_handler = GetIssues(client, query_251)
    issues_by_priority_251 = issues_handler.get_bugs_count_by_priority()

    #region Old releases
    # 243
    dates243_2weeks_query = f"created: {dates243_2weeks}"
    query_243 = f"project:ReSharper and {dates243_2weeks_query} and ({additional_query})"

    issues_handler = GetIssues(client, query_243)
    issues_by_priority_243 = issues_handler.get_bugs_count_by_priority()

    # 242
    dates242_2weeks_query = f"created: {dates242_2weeks}"
    additional_query = "created by: -jetbrains-team or created by: dotnet-support"
    query = f"project:ReSharper and {dates242_2weeks_query} and ({additional_query})"

    issues_handler = GetIssues(client, query)
    issues_by_priority_242 = issues_handler.get_bugs_count_by_priority()

    # 241
    dates241_2weeks_query = f"created: {dates.dates241_2weeks}"
    query = f"project:ReSharper and {dates241_2weeks_query} and ({additional_query})"

    issues_handler = GetIssues(client, query)
    issues_by_priority_241 = issues_handler.get_bugs_count_by_priority()
    # issues_handler.plot_issues_by_priority(issues_by_priority_241, cycle_dates_query_241)

    # 233
    dates233_2weeks_query = f"created: {dates.dates233_2weeks}"
    query = f"project:ReSharper and {dates233_2weeks_query} and ({additional_query})"

    issues_handler = GetIssues(client, query)
    issues_by_priority_233 = issues_handler.get_bugs_count_by_priority()

    # 232
    dates232_2weeks_query = f"created: {dates.dates232_2weeks}"
    query = f"project:ReSharper and {dates232_2weeks_query} and ({additional_query})"

    issues_handler = GetIssues(client, query)
    issues_by_priority_232 = issues_handler.get_bugs_count_by_priority()
    #endregion

    priority_dicts = {
        f"Release 232": issues_by_priority_232,
        f"Release 233": issues_by_priority_233,
        f"Release 241": issues_by_priority_241,
        f"Release 242": issues_by_priority_242,
        f"Release 243": issues_by_priority_243,
        f"Release 251": issues_by_priority_251,
        # TODO: add new release here
    }

    plot3 = plot_by_priority_several_releases(priority_dicts, "Issues created by users 2 weeks after the release", youtrack.PRIORITY)
    append_markdown("![Issues created by jetbrains-team by priority](images/" + os.path.basename(plot3) + ")")

    # Send data to AI
    append_markdown("### AI analysis")
    ai_response = ask_ai_issues_by_priorities_2_weeks(priority_dicts)
    append_markdown(f"\n{ai_response}\n")

def get_status_of_stoppers_and_criticals_created_by_users_2_weeks_after_release():
    # Status of Show-Stoppers & Criticals created by users 2 weeks after release
    append_markdown("## Status of Show-Stoppers & Criticals created by users 2 weeks after release")
    append_markdown("NOTE: Measures the time taken to resolve critical issues, helping assess the team's agility in addressing urgent problems")

    dates_2weeks_query = f"created: {dates.current_release_2weeks}"
    additional_query = "(created by: -jetbrains-team or created by: dotnet-support) and (priority: Show-stopper or Priority: Critical)"
    query = f"project:ReSharper and {dates_2weeks_query} and ({additional_query})"
    append_markdown("> Query: " + query)

    issues_handler = GetIssues(client, query)
    issues_statuses = issues_handler.get_issues()

    # Sort the issues first by "Priority" then by "Subsystem"
    sorted_issues = sorted(
        issues_statuses,
        key=lambda issue: (
            plotter.PRIORITIES.index(issue.priority) if issue.priority in plotter.PRIORITIES else len(
                plotter.PRIORITIES),  # Sort by priority based on its index in PRIORITIES
            issue.subsystem if issue.subsystem else "",
        )
    )

    # Prepare table data
    headers = ["ID", "State", "Available in", "Subsystem", "Priority", "Summary"]
    rows = []

    for issue in sorted_issues:
        rows.append([
            issue.id,
            issue.state,
            issue.available_in if issue.available_in else "N/A",
            issue.subsystem if issue.subsystem else "N/A",
            issue.priority if issue.priority else "N/A",
            issue.summary,
        ])


    # Write the table to markdown
    table = write_table(headers, rows)

    # Send data to AI
    append_markdown("### AI analysis")
    ai_response = ask_ai_status_of_stoppers_and_criticals_created_by_users_2_weeks_after_release(table)
    append_markdown(f"\n{ai_response}\n")

def get_bugs_created_by_users_between_bugfixes():
    append_markdown("## Bugs created by users between bugfixes")
    append_markdown("How many bugs are there after the bugfix? Are we adding more bugs then we are fixing?")

    issues_by_priority_1 = None
    issues_by_priority_2 = None
    issues_by_priority_3 = None
    issues_by_priority_4 = None
    issues_by_priority_5 = None
    issues_by_priority_6 = None
    issues_by_priority_7 = None
    issues_by_priority_8 = None
    issues_by_priority_9 = None

    additional_query = "created by: -jetbrains-team or created by: dotnet-support"

    if current_release_bugfix_1 is not None:
        created_1 = f"created: {current_release_bugfix_1}"
        query_1 = f"project:ReSharper and {created_1} and ({additional_query})"

        append_markdown("> Query : " + query_1)

        issues_handler = GetIssues(client, query_1)
        issues_by_priority_1 = issues_handler.get_bugs_count_by_priority()

    if current_release_bugfix_2 is not None:
        created_2 = f"created: {current_release_bugfix_2}"
        query_2 = f"project:ReSharper and {created_2} and ({additional_query})"
        issues_handler = GetIssues(client, query_2)
        issues_by_priority_2 = issues_handler.get_bugs_count_by_priority()

    if current_release_bugfix_3 is not None:
        created_3 = f"created: {current_release_bugfix_3}"
        query_3 = f"project:ReSharper and {created_3} and ({additional_query})"
        issues_handler = GetIssues(client, query_3)
        issues_by_priority_3 = issues_handler.get_bugs_count_by_priority()

    if current_release_bugfix_4 is not None:
        created_4 = f"created: {current_release_bugfix_4}"
        query_4 = f"project:ReSharper and {created_4} and ({additional_query})"
        issues_handler = GetIssues(client, query_4)
        issues_by_priority_4 = issues_handler.get_bugs_count_by_priority()

    if current_release_bugfix_5 is not None:
        created_5 = f"created: {current_release_bugfix_5}"
        query_5 = f"project:ReSharper and {created_5} and ({additional_query})"
        issues_handler = GetIssues(client, query_5)
        issues_by_priority_5 = issues_handler.get_bugs_count_by_priority()

    if current_release_bugfix_6 is not None:
        created_6 = f"created: {current_release_bugfix_6}"
        query_6 = f"project:ReSharper and {created_6} and ({additional_query})"
        issues_handler = GetIssues(client, query_6)
        issues_by_priority_6 = issues_handler.get_bugs_count_by_priority()

    if current_release_bugfix_7 is not None:
        created_7 = f"created: {current_release_bugfix_7}"
        query_7 = f"project:ReSharper and {created_7} and ({additional_query})"
        issues_handler = GetIssues(client, query_7)
        issues_by_priority_7 = issues_handler.get_bugs_count_by_priority()

    if current_release_bugfix_8 is not None:
        created_8 = f"created: {current_release_bugfix_8}"
        query_8 = f"project:ReSharper and {created_8} and ({additional_query})"
        issues_handler = GetIssues(client, query_8)
        issues_by_priority_8 = issues_handler.get_bugs_count_by_priority()

    if current_release_bugfix_9 is not None:
        created_9 = f"created: {current_release_bugfix_9}"
        query_9 = f"project:ReSharper and {created_9} and ({additional_query})"
        issues_handler = GetIssues(client, query_9)
        issues_by_priority_9 = issues_handler.get_bugs_count_by_priority()

    created_by_users: dict[str, Any] = {}
    if issues_by_priority_1 is not None:
        created_by_users[f"{current_release} - {current_release}.1"] = issues_by_priority_1
    if issues_by_priority_2 is not None:
        created_by_users[f"{current_release} - {current_release}.2"] = issues_by_priority_2
    if issues_by_priority_3 is not None:
        created_by_users[f"{current_release} - {current_release}.3"] = issues_by_priority_3
    if issues_by_priority_4 is not None:
        created_by_users[f"{current_release} - {current_release}.4"] = issues_by_priority_4
    if issues_by_priority_5 is not None:
        created_by_users[f"{current_release} - {current_release}.5"] = issues_by_priority_5
    if issues_by_priority_6 is not None:
        created_by_users[f"{current_release} - {current_release}.6"] = issues_by_priority_6
    if issues_by_priority_7 is not None:
        created_by_users[f"{current_release} - {current_release}.7"] = issues_by_priority_7
    if issues_by_priority_8 is not None:
        created_by_users[f"{current_release} - {current_release}.8"] = issues_by_priority_8
    if issues_by_priority_9 is not None:
        created_by_users[f"{current_release} - {current_release}.9"] = issues_by_priority_9


    plot4 = plot_by_priority_several_releases(created_by_users, "Issues created by users between bugfixes", youtrack.PRIORITY)
    append_markdown("![Issues created by jetbrains-team by priority](images/" + os.path.basename(plot4) + ")")

    # Send data to AI
    append_markdown("### AI analysis")
    ai_response = ask_ai_issues_between_bugfixes(created_by_users)
    append_markdown(f"\n{ai_response}\n")

def get_issues_fixed_in_bugfix():
    append_markdown("## Issues which were fixed in bugfix")
    append_markdown("What fixes go to bugfix?")

    available_in_bugfix = f"Available in: {current_release_available_in}"
    additional_query = "#resolved"
    query = f"project:ReSharper and {available_in_bugfix} and ({additional_query})"

    append_markdown("> Query : " + query)

    issues_handler = GetIssues(client, query)
    issues_fixed_in_bugfix = issues_handler.get_issues()

    # Sort the issues first by "Available in", then by "Subsystem", and lastly by "Priority"
    sorted_issues = sorted(
        issues_fixed_in_bugfix,
        key=lambda issue: (
            extract_available_in_value(issue.available_in) if issue.available_in else "",
            issue.subsystem if issue.subsystem else "",
            plotter.PRIORITIES.index(issue.priority) if issue.priority in plotter.PRIORITIES else len(plotter.PRIORITIES)  # Sort by priority based on its index in PRIORITIES
        )
    )

    headers = ["Available in", "Subsystem", "Priority", "Summary"]
    rows = []

    for issue in sorted_issues:
        available_in_value = extract_available_in_value(issue.available_in)
        if available_in_value:
            rows.append([
                available_in_value,
                issue.subsystem if issue.subsystem else "N/A",
                issue.priority if issue.priority else "N/A",
                issue.summary,
            ])

    # Write the table to markdown
    table = write_table(headers, rows)

    # Send data to AI
    append_markdown("### AI analysis")
    ai_response = ask_ai_issues_fixed_in_bugfix(table)
    append_markdown(f"\n{ai_response}\n")

def get_list_of_created_issues():
    append_markdown("## Issues created during release cycle")
    append_markdown("What issues are created during release cycle?")

    cycle_dates_query = f"created: {current_release_dates}"
    query = f"project:ReSharper and {cycle_dates_query} and subsystem: -QA"

    append_markdown("> Query : " + query)

    handler = GetIssues(client, query)
    issues = handler.get_issues()

    # Sort the issues first by "Subsystem", and then by "Priority"
    sorted_issues = sorted(
        issues,
        key=lambda issue: (
            issue.subsystem if issue.subsystem else "",
            plotter.PRIORITIES.index(issue.priority) if issue.priority in plotter.PRIORITIES else len(plotter.PRIORITIES)  # Sort by priority based on its index in PRIORITIES
        )
    )

    headers = ["Subsystem", "Priority", "Summary", "State", "Type"]
    rows = []

    for issue in sorted_issues:
        rows.append([
            issue.subsystem if issue.subsystem else "N/A",
            issue.priority if issue.priority else "N/A",
            issue.summary,
            issue.state,
            issue.type if issue.type else "N/A",
        ])

    table = compose_table(headers, rows)

    # Send data to AI
    append_markdown("### AI analysis")
    ai_response = ask_ai_created_issues(table)
    append_markdown(f"\n{ai_response}\n")

def get_users_comments():
    append_markdown("## Users comments added during release cycle")

    commented = f"commented: {current_release_dates}"
    # additional_query = "#unresolved"
    query = f"project:ReSharper and ({commented}) "

    append_markdown("> Query " + current_release +": " + query)

    issues_handler = GetIssues(client, query)
    issues = issues_handler.get_issues_with_comments()

    # Define the date range for filtering comments
    start_date = current_release_START_DATE
    end_date = current_release_END_DATE

    issue_comments_data = defaultdict(list)

    # Process issues and filter comments based on date and email
    for issue in issues:
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

    # Sort issues by the number of comments in descending order
    sorted_issues = sorted(issue_comments_data.items(), key=lambda x: len(x[1]), reverse=True)

    # Get the top 10 issues
    top_10_issues = sorted_issues[:10]

    # Print the results
    append_markdown("### Top 10 Issues with Most User Comments")
    for issue_id, comments in top_10_issues:
        append_markdown(f"- **Issue ID**: {issue_id}, **Comments**: {len(comments)}")

    # Split the data into parts
    num_splits = 4
    issue_comments_data_chunks = list(split_dict(issue_comments_data, len(issue_comments_data) // num_splits or 1))

    ai_responses = []

    for i in range(num_splits):
        # Pass chunk to AI
        append_markdown(f"### AI analysis for user's comments (Part {i})")
        ai_response_part1 = ai_analysis.ask_ai_about_comments(issue_comments_data_chunks[i])
        append_markdown(f"\n{ai_response_part1}\n")
        ai_responses.append(ai_response_part1)

    append_markdown(f"### AI analysis for user's comments (final)")
    final_response = ai_analysis.ask_ai_about_comments_combine(ai_responses)
    append_markdown(f"\n{final_response}\n")

def get_planned_vs_actually_done():
    append_markdown("## Planned vs actually done")
    append_markdown("How many issues which were assigned to specific Fix version were actually done?")
    append_markdown("Seems like priorities are incorrect because many criticals are not fixed.")

    # TODO: add new release here (copy previous + update)
    # 251
    additional_query = f"tag: {planned_251}"
    query_251 = f"project:ReSharper and ({additional_query})"

    append_markdown("> Query : " + query_251)

    handler = GetIssues(client, query_251)
    issues_by_priority_251 = handler.get_issues_count_by_priority()
    issues_by_type_251 = handler.get_issues_count_by_type()

    # 243
    additional_query = f"tag: {planned_243}"
    query_243 = f"project:ReSharper and ({additional_query})"

    handler = GetIssues(client, query_243)
    issues_by_priority_243 = handler.get_issues_count_by_priority()
    issues_by_type_243 = handler.get_issues_count_by_type()

    planned_issues_by_priority = {
        f"Release 243": issues_by_priority_243,
        f"Release 251": issues_by_priority_251,
        # TODO: add new release here
    }

    planned_issues_by_type = {
        f"Release 243": issues_by_type_243,
        f"Release 251": issues_by_type_251,
        # TODO: add new release here
    }

    # Get fixed

    # TODO: add new release here (copy previous + update)
    # 251
    additional_query_fixed = f"tag: {planned_251} and (state: fixed or state: Verified)"
    query_251_fixed = f"project:ReSharper and ({additional_query_fixed})"

    handler = GetIssues(client, query_251_fixed)
    fixed_issues_by_priority_251 = handler.get_issues_count_by_priority()
    fixed_issues_by_type_251 = handler.get_issues_count_by_type()

    # 243
    additional_query_fixed = f"tag: {planned_243} and (state: fixed or state: Verified)"
    query_243_fixed = f"project:ReSharper and ({additional_query_fixed})"

    handler = GetIssues(client, query_243_fixed)
    fixed_issues_by_priority_243 = handler.get_issues_count_by_priority()
    fixed_issues_by_type_243 = handler.get_issues_count_by_type()

    fixed_planned_issues_by_priority = {
        f"Release 243": fixed_issues_by_priority_243,
        f"Release 251": fixed_issues_by_priority_251,
        # TODO: add new release here
    }

    fixed_planned_issues_by_type = {
        f"Release 243": fixed_issues_by_type_243,
        f"Release 251": fixed_issues_by_type_251,
        # TODO: add new release here
    }

    plot1 = plot_created_vs_fixed_by_category(plotter.PRIORITIES, planned_issues_by_priority, fixed_planned_issues_by_priority,
                                              "Distribution of issues planned vs Fixed by priorities")
    append_markdown("![Issues planned vs Fixed by priority](images/" + os.path.basename(plot1) + ")")

    # Send data to AI
    append_markdown("### AI analysis")
    ai_response = ask_ai_planned_vs_fixed_issues_by_priority(planned_issues_by_priority, fixed_planned_issues_by_priority)
    append_markdown(f"\n{ai_response}\n")

    plot2 = plot_created_vs_fixed_by_category(plotter.TYPES, planned_issues_by_type,
                                              fixed_planned_issues_by_type,
                                              "Distribution of issues planned vs Fixed by types")
    append_markdown("![Issues planned vs Fixed by types](images/" + os.path.basename(plot2) + ")")

    # Send data to AI
    append_markdown("### AI analysis")
    ai_response = ask_ai_planned_vs_fixed_issues_by_type(planned_issues_by_type, fixed_planned_issues_by_type)
    append_markdown(f"\n{ai_response}\n")

def get_users_issues_by_dates():
    append_markdown("## Users issues by dates")
    append_markdown("When do users create more tickets?")
    append_markdown("The rate at which new defects are reported over time. Helps in understanding the stability of the release. A decreasing defect arrival rate over time usually indicates improving quality.")

    # TODO: add new year here

    # 2025
    dates_query = f"created: {year_2025}"
    additional_query = "created by: -jetbrains-team or created by: dotnet-support"
    query_2025 = f"project:ReSharper and {dates_query} and ({additional_query})"

    append_markdown("> Query : " + query_2025)

    issues_handler = GetIssues(client, query_2025)
    issues_by_date_2025 = issues_handler.get_issues_count_by_various_parameters()

    # 2024
    dates_query = f"created: {year_2024}"
    query_2024 = f"project:ReSharper and {dates_query} and ({additional_query})"

    issues_handler = GetIssues(client, query_2024)
    issues_by_date_2024 = issues_handler.get_issues_count_by_various_parameters()

    created_by_date= {
        f"Year 2024": issues_by_date_2024[youtrack.CREATED_DATE],
        f"Year 2025": issues_by_date_2025[youtrack.CREATED_DATE],
        # TODO: add new year here
    }

    plot = plot_ticket_creation_dates_same_axis(created_by_date, [2024, 2025],"Issues created by users (by creation date)")
    append_markdown("![Issues created by users (by creation date)](images/" + os.path.basename(plot) + ")")

    # Send data to AI
    append_markdown("### AI analysis")
    ai_response = ask_ai_issues_created_by_users_by_creation_date(created_by_date)
    append_markdown(f"\n{ai_response}\n")

def get_regressions_found_during_release_cycle():
    append_markdown("## Regressions found during release cycle")
    append_markdown("How many regressions were found during release cycle?")

    # TODO: add new release here (copy previous + update)
    # 251
    dates_251_query = f"created: {dates251}"
    additional_query = "tag: {.net-regression}"
    query_251 = f"project:ReSharper and {dates_251_query} and ({additional_query})"

    append_markdown("> Query : " + query_251)

    issues_handler = GetIssues(client, query_251)
    issues_251 = issues_handler.get_issues()

    #region Old releases
    # 243
    dates_243_query = f"created: {dates243}"
    query_243 = f"project:ReSharper and {dates_243_query} and ({additional_query})"

    issues_handler = GetIssues(client, query_243)
    issues_243 = issues_handler.get_issues()

    # 242
    dates_242_query = f"created: {dates242}"
    query_242 = f"project:ReSharper and {dates_242_query} and ({additional_query})"

    issues_handler = GetIssues(client, query_242)
    issues_242 = issues_handler.get_issues()
    #endregion

    # Count issues
    issue_counts: dict[str, int] = {
        "242": len(issues_242),
        "243": len(issues_243),
        "251": len(issues_251),
        # TODO: add new release here
    }

    # Plot the issue counts
    plot_title = "Regressions Found During Release Cycle"
    plot = plot_count_issues_as_bars(issue_counts, plot_title)
    append_markdown("![Regressions Found During Release Cycle](images/" + os.path.basename(plot) + ")")

def get_untriaged_time():
    append_markdown("## Untriaged time")
    append_markdown("How much time was spent on untriaged tickets?")

    # TODO: add new release here (copy previous + update)

    # 251
    dates_251_query = f"created: {dates251}"
    additional_query = "tag: -{moved from Rider} and type: -exception"
    query_251 = f"project:ReSharper and {dates_251_query} and ({additional_query})"

    append_markdown("> Query " + ": " + query_251)

    issues_handler = GetIssues(client, query_251)
    issues_251 = issues_handler.get_issues()

    # Calculate average daysInUntriaged
    total_days_in_untriaged = 0
    count = 0

    for issue in issues_251:
        if hasattr(issue, 'daysInUntriaged') and issue.daysInUntriaged is not None:
            total_days_in_untriaged += issue.daysInUntriaged
            count += 1

    average_days_in_untriaged = total_days_in_untriaged / count if count > 0 else 0

    append_markdown(f"Average days spent in untriaged state during 251 release cycle: {average_days_in_untriaged:.2f}")

    #region Old releases
    # 243
    dates_243_query = f"created: {dates243}"
    additional_query = "tag: -{moved from Rider} and type: -exception and QA_assigned: -{No qa assigned}"
    query_243 = f"project:ReSharper and {dates_243_query} and ({additional_query})"

    issues_handler = GetIssues(client, query_243)
    issues_243 = issues_handler.get_issues()

    # Calculate average daysInUntriaged
    total_days_in_untriaged = 0
    count = 0

    for issue in issues_243:
        if hasattr(issue, 'daysInUntriaged') and issue.daysInUntriaged is not None:
            total_days_in_untriaged += issue.daysInUntriaged
            count += 1

    average_days_in_untriaged = total_days_in_untriaged / count if count > 0 else 0

    append_markdown(f"Average days spent in untriaged state during 243 release cycle: {average_days_in_untriaged:.2f}")

    # 242
    dates_242_query = f"created: {dates242}"

    query_242 = f"project:ReSharper and {dates_242_query} and ({additional_query})"

    issues_handler = GetIssues(client, query_242)
    issues_242 = issues_handler.get_issues()

    # Calculate average daysInUntriaged
    total_days_in_untriaged = 0
    count = 0

    for issue in issues_242:
        if hasattr(issue, 'daysInUntriaged') and issue.daysInUntriaged is not None:
            total_days_in_untriaged += issue.daysInUntriaged
            count += 1

    average_days_in_untriaged = total_days_in_untriaged / count if count > 0 else 0

    append_markdown(f"Average days spent in untriaged state during 242 release cycle: {average_days_in_untriaged:.2f}")
    #endregion


#HELPERS
def extract_available_in_value(available_in: str):
    match = re.search(dates.REGEX_FOR_AVAILABLE_VERSION, available_in)
    return match.group(0) if match else None

def split_dict(input_dict, n):
    """Helper function to split dictionary into chunks of n items."""
    iterator = iter(input_dict)
    for _ in range(0, len(input_dict), n):
        yield {k: input_dict[k] for k in islice(iterator, n)}

# 1. Update dates
# 2. Run

get_all_issues_count() # All issues created during release cycle (including issues from jetbrains-team)
get_list_of_created_issues()
get_issues_created_by_jetbrains_team_vs_fixed()
get_issues_created_by_NOT_jetbrains_team_vs_fixed()
get_issues_created_by_users_2_weeks_after_release()
get_status_of_stoppers_and_criticals_created_by_users_2_weeks_after_release()
# get_bugs_created_by_users_between_bugfixes()
# get_issues_fixed_in_bugfix()
get_users_issues_by_dates()
get_planned_vs_actually_done()
get_users_comments()

# Without AI
get_regressions_found_during_release_cycle()
get_untriaged_time()

print(f"Report is generated.")

