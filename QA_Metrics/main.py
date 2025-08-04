import os
from collections import defaultdict
from itertools import islice
from typing import Any

import requests

import markdown_writer
from markdown_writer import initialize_markdown, append_markdown, write_table, compose_table

import youtrack_qa
from youtrack_qa import GetIssues

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

def convert_timestamp_to_date(timestamp):
    """Convert Unix timestamp in milliseconds to readable date string."""
    if not timestamp or timestamp == "N/A":
        return "N/A"
    try:
        # Convert milliseconds to seconds and create datetime object
        dt = datetime.fromtimestamp(int(timestamp) / 1000)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OverflowError):
        return str(timestamp)  # Return original value if conversion fails

def format_estimation(estimation):
    """Format estimation period value for display."""
    if not estimation or estimation == "N/A":
        return "N/A"
    try:
        # If it's already a string (formatted period), return as is
        if isinstance(estimation, str):
            return estimation
        # If it's a dict with presentation, extract it
        if isinstance(estimation, dict) and 'presentation' in estimation:
            return estimation['presentation']
        return str(estimation)
    except (ValueError, TypeError):
        return str(estimation)  # Return original value if formatting fails

def get_resharper_qa_issues():
    """Get all YouTrack issues from 'ReSharper QA' project and display all fields in a table."""
    append_markdown("## All Issues from ReSharper QA Project")
    append_markdown("Complete list of all issues from the ReSharper QA project with all available fields.")

    # Query to get all issues from ReSharper QA project
    query = 'project:{ReSharper QA}'
    
    append_markdown("> Query: " + query)

    # Get issues using the existing handler
    handler = GetIssues(client, query)
    issues = handler.get_issues()

    if not issues:
        append_markdown("No issues found in ReSharper QA project.")
        return

    append_markdown(f"**Total issues found:** {len(issues)}")

    # Define all possible fields that can be displayed
    headers = [
        "ID", "Summary", "Created", "Product", "Assignee", "Priority", "State", "Type", 
        "Feature State for QA", "ETA from Developer", 
        "Due Date", "Estimation", "Sprint", "Checklist", "Branch", 
        "Days Before Testing Starts", "Days In Testing", "When Development Finished", 
        "How Many Iterations of Testing"
    ]

    rows = []
    for issue in issues:
        row = [
            str(issue.id) if hasattr(issue, 'id') and issue.id else "N/A",
            str(issue.summary) if hasattr(issue, 'summary') and issue.summary else "N/A",
            convert_timestamp_to_date(issue.created) if hasattr(issue, 'created') and issue.created else "N/A",
            str(issue.product) if hasattr(issue, 'product') and issue.product else "N/A",
            str(issue.assignee) if hasattr(issue, 'assignee') and issue.assignee else "N/A",
            str(issue.priority) if hasattr(issue, 'priority') and issue.priority else "N/A",
            str(issue.state) if hasattr(issue, 'state') and issue.state else "N/A",
            str(issue.type) if hasattr(issue, 'type') and issue.type else "N/A",
            str(issue.feature_state_for_qa) if hasattr(issue, 'feature_state_for_qa') and issue.feature_state_for_qa else "N/A",
            convert_timestamp_to_date(issue.eta_from_developer) if hasattr(issue, 'eta_from_developer') and issue.eta_from_developer else "N/A",
            convert_timestamp_to_date(issue.due_date) if hasattr(issue, 'due_date') and issue.due_date else "N/A",
            format_estimation(issue.estimation) if hasattr(issue, 'estimation') and issue.estimation else "N/A",
            str(issue.sprint) if hasattr(issue, 'sprint') and issue.sprint else "N/A",
            str(issue.checklist) if hasattr(issue, 'checklist') and issue.checklist else "N/A",
            str(issue.branch) if hasattr(issue, 'branch') and issue.branch else "N/A",
            str(issue.days_before_testing_starts) if hasattr(issue, 'days_before_testing_starts') and issue.days_before_testing_starts else "N/A",
            str(issue.days_in_testing) if hasattr(issue, 'days_in_testing') and issue.days_in_testing else "N/A",
            convert_timestamp_to_date(issue.when_development_finished) if hasattr(issue, 'when_development_finished') and issue.when_development_finished else "N/A",
            str(issue.how_many_iterations_of_testing) if hasattr(issue, 'how_many_iterations_of_testing') and issue.how_many_iterations_of_testing else "N/A"
        ]

        rows.append(row)

    # Write the table to markdown
    write_table(headers, rows)

# Execute the single method
get_resharper_qa_issues()

print("ReSharper QA issues report generated.")

