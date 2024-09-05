import os
from datetime import datetime
from typing import List, Dict

REPORTS_DIR = "reports"
IMAGES_DIR = os.path.join(REPORTS_DIR, "images")
MARKDOWN_FILE = os.path.join(REPORTS_DIR, "ReSharper_Quality_Report.md")

def initialize_markdown():
    with open(MARKDOWN_FILE, 'w', encoding='utf-8') as md_file:
        md_file.write("# ReSharper Release Quality Analysis Report\n\n")
        md_file.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d')}\n\n")
        md_file.write("## Table of Contents\n")
        md_file.write("- [Issue Types Analysis](#Issues-Created-By-jetbrains-team-vs-Fixed)\n")
        md_file.write("- [Issue Priorities Analysis](#issue-priorities-analysis)\n")
        md_file.write("- [Bugs Prior to Release](#bugs-prior-to-release)\n")
        md_file.write("- [AI Insights](#ai-insights)\n\n")

def append_markdown(content: str):
    with open(MARKDOWN_FILE, 'a', encoding='utf-8') as md_file:
        md_file.write(content + "\n\n")

def write_table(headers: List[str], rows: List[List[str]]):
    table = "| " + " | ".join(headers) + " |\n"
    table += "| " + " | ".join(['---'] * len(headers)) + " |\n"
    for row in rows:
        table += "| " + " | ".join(row) + " |\n"
    append_markdown(table)

def log_issues_by_type(data: Dict[str, Dict[str, int]]):
    append_markdown("## Issue Types Analysis\n")
    headers = ["Release", "Issue Type", "Count"]
    rows = []
    for release, issues in data.items():
        for issue_type, count in issues.items():
            rows.append([release, issue_type, str(count)])
    write_table(headers, rows)

def log_issues_by_priority(data: Dict[str, Dict[str, int]]):
    append_markdown("## Issue Priorities Analysis\n")
    headers = ["Release", "Priority", "Count"]
    rows = []
    for release, issues in data.items():
        for priority, count in issues.items():
            rows.append([release, priority, str(count)])
    write_table(headers, rows)

def log_created_vs_fixed(image_path: str):
    append_markdown("### Created vs Fixed Issues\n")
    relative_image_path = os.path.relpath(image_path, REPORTS_DIR)
    append_markdown(f"![Created vs Fixed Issues]({relative_image_path})")