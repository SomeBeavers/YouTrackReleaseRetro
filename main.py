import os
import requests

import markdown_writer
from markdown_writer import initialize_markdown, append_markdown

import youtrack
from youtrack import GetIssues

import plotter
from plotter import plot_created_vs_fixed

dates242_2weeks = "2024-08-15 .. 2024-08-29"
dates242 = "2024-04-10 .. 2024-08-14"
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

# Get tickets created by jetbrains-team
append_markdown("Get tickets created by jetbrains-team")
#242
append_markdown("242")

cycle_dates_query_242 = f"created: {dates242}"
additional_query = "created by: jetbrains-team"
query_242 = f"project:ReSharper and {cycle_dates_query_242} and {additional_query}"


handler = GetIssues(client, query_242)
issues_by_priority_242 = handler.get_all_issues_by_priority()
issues_by_type_242 = handler.get_issues_by_type()


#241
append_markdown("241")

cycle_dates_query_241 = f"created: {dates241}"
query_241 = f"project:ReSharper and {cycle_dates_query_241} and {additional_query}"

handler = GetIssues(client, query_241)
issues_by_priority_241 = handler.get_all_issues_by_priority()
issues_by_type_241 = handler.get_issues_by_type()

#233
append_markdown("233")

cycle_dates_query_233 = f"created: {dates233}"
query_233 = f"project:ReSharper and {cycle_dates_query_233} and {additional_query}"

handler = GetIssues(client, query_233)
issues_by_priority_233 = handler.get_all_issues_by_priority()
issues_by_type_233 = handler.get_issues_by_type()

#232
append_markdown("232")

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


# # Send data to AI
# ask_ai_issues_by_types(created_by_jetbrains_team_by_type)

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

plot1 = plot_created_vs_fixed(created_by_jetbrains_team, fixed_by_jetbrains_team)
append_markdown("![Issues by Type](images/" + os.path.basename(plot1) + ")")


#
# # Bugs created by users 2 weeks after release "project: resharper created by: -jetbrains-team created: 2024-08-15 .. today sort by: priority"
# #242
# dates242_2weeks_query = f"created: {dates242_2weeks}"
# additional_query = "created by: -jetbrains-team"
# query = f"project:ReSharper and {dates242_2weeks_query} and {additional_query}"
#
# issues_handler = GetIssues(client, query)
# issues_by_priority_242 = issues_handler.get_bugs_by_priority()
# #issues_handler.plot_issues_by_priority(issues_by_priority_242, cycle_dates_query_242)
#
# #241
# dates241_2weeks_query = f"created: {dates241_2weeks}"
# additional_query = "created by: -jetbrains-team"
# query = f"project:ReSharper and {dates241_2weeks_query} and {additional_query}"
#
# issues_handler = GetIssues(client, query)
# issues_by_priority_241 = issues_handler.get_bugs_by_priority()
# #issues_handler.plot_issues_by_priority(issues_by_priority_241, cycle_dates_query_241)
#
# #233
# dates233_2weeks_query = f"created: {dates233_2weeks}"
# additional_query = "created by: -jetbrains-team"
# query = f"project:ReSharper and {dates233_2weeks_query} and {additional_query}"
#
# issues_handler = GetIssues(client, query)
# issues_by_priority_233 = issues_handler.get_bugs_by_priority()
#
# #232
# dates232_2weeks_query = f"created: {dates232_2weeks}"
# additional_query = "created by: -jetbrains-team"
# query = f"project:ReSharper and {dates232_2weeks_query} and {additional_query}"
#
# issues_handler = GetIssues(client, query)
# issues_by_priority_232 = issues_handler.get_bugs_by_priority()
#
# priority_dicts = {
#     f"Release 242 ({dates242_2weeks_query})": issues_by_priority_242,
#     f"Release 241 ({dates241_2weeks_query})": issues_by_priority_241,
#     f"Release 233 ({dates233_2weeks_query})": issues_by_priority_233,
#     f"Release 232 ({dates232_2weeks_query})": issues_by_priority_232,
# }
#
# issues_handler.plot_multiple_priority_dicts(priority_dicts)
#
# # Send data to AI
# ask_ai_issues_by_priorities_2_weeks(priority_dicts)

print(f"Report is generated.")

