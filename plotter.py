import os
from typing import Dict

import matplotlib.pyplot as plt
import numpy as np

import youtrack

import datetime
from datetime import datetime, timedelta

IMAGES_DIR = os.path.join("reports", "images")
PRIORITIES = ['Show-stopper', 'Critical', 'Major', 'Normal', 'Minor']
TYPES = ['Bug', 'Performance Problem', 'Security Problem', 'Exception', 'Usability Problem', 'Cosmetics', 'Improvement', 'Task', 'Feature', 'Plan', ]

def save_plot(fig, title: str) -> str:
    # Generate a safe filename
    filename = f"{title.replace(' ', '_').lower()}.png"
    filepath = os.path.join(IMAGES_DIR, filename)
    fig.savefig(filepath, bbox_inches='tight')
    plt.close(fig)  # Close the figure to free memory
    return filepath

def plot_issues_by_type(issue_type_counts: Dict[str, int], dates: str) -> str:
    # Sort issue types by count in descending order
    sorted_issue_types = sorted(issue_type_counts.items(), key=lambda x: x[1], reverse=True)
    sorted_labels, sorted_counts = zip(*sorted_issue_types)

    total_count = sum(sorted_counts)

    # Function to display the number of tickets on the pie chart
    def absolute_number(pct):
        absolute = int(round(pct * total_count / 100.0))
        return f'{absolute}'

    # Plotting the pie chart
    fig = plt.figure(figsize=(8, 8))
    plt.pie(sorted_counts, labels=sorted_labels, autopct=absolute_number, startangle=140)
    plt.title(f'Distribution of Issues by Type Created by JetBrains Team ({dates})')
    plt.show()

    # Save the plot and return the image path
    image_path = save_plot(fig, f'Distribution of Issues by Type Created by JetBrains Team ({dates})')
    return image_path

def plot_by_subsystems_several_releases(issues: Dict[str, Dict[str, int]], title: str, category: str) -> str:
    # Setting up the bar width
    bar_width = 0.2  # Adjust this to fit your needs
    index = 0

    all_subsystems = set()
    for subsystem_counts in issues.values():
        all_subsystems.update(subsystem_counts.keys())
    subsystems = sorted(all_subsystems)

    index = np.arange(len(subsystems))
    fig = plt.figure(figsize=(18, 8))

    for i, (label, subsystem_counts) in enumerate(issues.items()):
        counts = [subsystem_counts.get(subsystem, 0) for subsystem in subsystems]
        plt.bar(index + i * bar_width, counts, bar_width, label=label)


    # Adding titles and labels
    plt.title(title)
    plt.xlabel(category)
    plt.ylabel('Number of Issues')
    plt.xticks(index + bar_width * (len(issues) - 1) / 2, subsystems, rotation=90)
    plt.legend()
    plt.tight_layout()

    plt.show()

    image_path = save_plot(fig, title)
    return image_path

def plot_multiple_priority_dicts(issues: Dict[str, Dict[str, int]], title: str, category: str) -> str:
    # Setting up the bar width
    bar_width = 0.2  # Adjust this to fit your needs
    index = 0

    if category == youtrack.PRIORITY:
        index = np.arange(len(PRIORITIES))
        fig = plt.figure(figsize=(12, 6))
    if category == youtrack.SUBSYSTEM:
        all_subsystems = set()
        for subsystem_counts in issues.values():
            all_subsystems.update(subsystem_counts.keys())
        subsystems = sorted(all_subsystems)
        index = np.arange(len(subsystems))
        fig = plt.figure(figsize=(18, 8))


    if category == youtrack.PRIORITY:
        for i, (label, priority_counts) in enumerate(issues.items()):
            counts = [priority_counts.get(priority, 0) for priority in PRIORITIES]
            plt.bar(index + i * bar_width, counts, bar_width, label=label)
    if category == youtrack.SUBSYSTEM:
        for i, (label, subsystem_counts) in enumerate(issues.items()):
            counts = [subsystem_counts.get(subsystem, 0) for subsystem in subsystems]
            plt.bar(index + i * bar_width, counts, bar_width, label=label)

    # Adding titles and labels
    plt.title(title)
    plt.xlabel(category)
    plt.ylabel('Number of Issues')
    if category == youtrack.PRIORITY:
        plt.xticks(index + bar_width * (len(issues) - 1) / 2, PRIORITIES, rotation=45)
    if category == youtrack.SUBSYSTEM:
        plt.xticks(index + bar_width * (len(issues) - 1) / 2, subsystems, rotation=90)
    plt.legend()
    plt.tight_layout()

    plt.show()

    image_path = save_plot(fig, title)
    return image_path

def plot_created_vs_fixed_by_category(categories: list[str], data_created: Dict[str, Dict[str, int]], data_fixed: Dict[str, Dict[str, int]], title:str) -> str:
    # Pastel colors for bars
    pastel_colors = [
        '#AEC6CF', '#FFB347', '#77DD77', '#FF6961',  # Original colors
        '#CFCFC4', '#FDFD96', '#836953', '#CB99C9',  # Additional pastel colors
        '#F49AC2', '#B39EB5', '#FFB6C1', '#FFD1DC'  # More pastel colors
    ]

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
        rect = ax.bar(x + (i - 2) * width, fixed_values, width, label=f'{key} - fixed', color=color)
        fixed_bars.append(rect)

    # Add some text for labels, title and custom x-axis tick labels, etc.
    ax.set_xlabel('Priority')
    ax.set_ylabel('Count')
    ax.set_title(title)
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

    image_path = save_plot(fig, title)
    return image_path

def generate_all_days_in_year(year: int):
    """
    Generates a list of all dates in the given year in 'YYYY-MM-DD' format.
    """
    start_date = datetime(year, 1, 1)
    end_date = datetime(year + 1, 1, 1)
    return [(start_date + timedelta(days=i)).strftime('%Y-%m-%d') for i in range((end_date - start_date).days)]

def plot_ticket_creation_dates_same_axis(issues_by_date: Dict[str, Dict[str, int]], years: list[int],
                                         title: str) -> str:
    """
    Plots the distribution of ticket creation dates for multiple years on the same x-axis,
    where only the month and day matter, ignoring the year.

    Args:
        issues_by_date (Dict[str, Dict[str, int]]): A dictionary where keys are year labels (e.g., 'Year 2024')
                                                    and values are dictionaries with dates (YYYY-MM-DD) as keys
                                                    and issue counts as values.
        years (list[int]): A list of years to include in the plot.
        title (str): Title of the plot.

    Returns:
        str: Path to the saved plot image.
    """
    fig, ax = plt.subplots(figsize=(18, 6))

    # Define unique markers and colors for each year
    markers = ['o', 's', '^', 'D', 'P', '*']
    colors = ['red', 'blue', 'green', 'orange', 'purple', 'cyan']

    # Generate month-day labels for the x-axis
    month_day_labels = [datetime(2000, month, 1).strftime('%b') for month in range(1, 13)]
    x_ticks = [datetime(2000, month, 1).timetuple().tm_yday for month in range(1, 13)]

    for idx, year in enumerate(years):
        # Align the data for the current year based on day of the year
        year_data = issues_by_date.get(f"Year {year}", {})

        # Create a sorted list of (day_of_year, count) tuples
        sorted_data = sorted(
            [(datetime.strptime(date_str, '%Y-%m-%d').timetuple().tm_yday, count) for date_str, count in
             year_data.items()]
        )
        aligned_days, counts = zip(*sorted_data) if sorted_data else ([], [])

        # Plot lines and dots for the current year
        ax.plot(aligned_days, counts, color=colors[idx % len(colors)], linestyle='-', linewidth=1, label=f'{year}')
        ax.scatter(aligned_days, counts, color=colors[idx % len(colors)], marker=markers[idx % len(markers)], s=10)

    # Formatting the plot
    ax.set_title(title, fontsize=16)
    ax.set_xlabel('Date', fontsize=14)
    ax.set_ylabel('Number of Tickets', fontsize=14)
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(month_day_labels, rotation=45)
    ax.grid(True)
    ax.legend()

    plt.tight_layout()

    # Save and return the image path
    image_path = save_plot(fig, title)
    return image_path

def plot_regressions_by_release(issue_counts: Dict[str, int], title: str) -> str:
    """
    Plots the count of issues for different releases as a bar chart.

    Args:
        issue_counts (Dict[str, int]): A dictionary where keys are release identifiers (e.g., '242', '243')
                                       and values are issue counts.
        title (str): Title of the plot.

    Returns:
        str: Path to the saved plot image.
    """
    releases = list(issue_counts.keys())
    counts = list(issue_counts.values())

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.bar(releases, counts, color=['blue', 'orange'])

    # Formatting the plot
    ax.set_title(title, fontsize=16)
    ax.set_xlabel('Release', fontsize=14)
    ax.set_ylabel('Number of Regressions', fontsize=14)
    ax.grid(axis='y', linestyle='--', alpha=0.7)

    # Annotating the bar values
    for i, count in enumerate(counts):
        ax.text(i, count + 0.5, str(count), ha='center', fontsize=12)

    plt.tight_layout()

    # Save and return the image path
    image_path = save_plot(fig, title)
    return image_path