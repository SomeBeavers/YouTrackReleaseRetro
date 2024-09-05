import os
from typing import Dict

import matplotlib.pyplot as plt
import numpy as np

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

def plot_issues_by_priority(priority_counts: Dict[str, int], dates: str) -> str:
    sorted_priorities = sorted(priority_counts.items(), key=lambda x: x[1], reverse=True)
    sorted_labels, sorted_counts = zip(*sorted_priorities)

    fig = plt.figure(figsize=(10, 6))
    plt.bar(sorted_labels, sorted_counts, color='skyblue')

    plt.title(f'Number of Issues by Priority ({dates})')
    plt.xlabel('Priority')
    plt.ylabel('Number of Issues')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()

    image_path = save_plot(fig, f'Number of Issues by Priority ({dates})')
    return image_path

def plot_multiple_priority_dicts(priority_dicts: Dict[str, Dict[str, int]], title: str) -> str:
    # Setting up the bar width
    bar_width = 0.2  # Adjust this to fit your needs
    index = np.arange(len(PRIORITIES))

    # Plotting each dictionary's data
    fig = plt.figure(figsize=(12, 6))

    for i, (label, priority_counts) in enumerate(priority_dicts.items()):
        counts = [priority_counts.get(priority, 0) for priority in PRIORITIES]
        plt.bar(index + i * bar_width, counts, bar_width, label=label)

    # Adding titles and labels
    plt.title(title)
    plt.xlabel('Priority')
    plt.ylabel('Number of Issues')
    plt.xticks(index + bar_width * (len(priority_dicts) - 1) / 2, PRIORITIES, rotation=45)
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
        rect = ax.bar(x + (i - 2) * width, fixed_values, width, label=f'{key}', color=color)
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