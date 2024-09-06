from typing import Dict

from openai import OpenAI

AI_STEPS_MESSAGE = """
    To proceed with the analysis, follow these steps:

    1. **Step-by-Step Comparison**: Break down the issue types in releases and compare their frequencies. Calculate percentage changes where applicable.

    2. **Trend Identification**: Look for any significant increases or decreases in issue types. Determine if there are emerging patterns or persistent problems.

    3. **Concerns and Improvements**: Highlight any categories that have worsened or improved significantly. Assess if there are any issues that need urgent attention.

    4. **Recommendations**: Based on your findings, provide detailed recommendations to improve the quality of future releases. Prioritize areas with the most significant changes or potential impact.

    Take your time to analyze the data thoroughly and provide a comprehensive response. Focus on latest release. Reply using markdown syntax.
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


def ask_ai_issues_by_types(created: Dict[str, Dict[str, int]], fixed: Dict[str, Dict[str, int]]) -> str:
    #global client
    client = OpenAI()
    # Assemble the prompt manually
    prompt = ""
    ai_messages = [
        {"role": "system",
         "content": AI_SYSTEM_MESSAGE},
        {
            "role": "user",
            "content": AI_CONTENT_MESSAGE_CREATED_ISSUES_BY_TYPES
        },
        {
            "role": "user",
            "content": f"Amount of issues found by ReSharper's QAs of each type in each release:\n\n"
                       + "\n\n".join([f"**{release}:**\n```{issues}```"
                                      for release, issues in created.items()])
                       + "\n\n"
                       + f"Amount of issues (found by ReSharper's QAs) which were fixed by developers in each release:\n\n"
                       + "\n\n".join([f"**{release}:**\n```{issues}```"
                                      for release, issues in fixed.items()])
        },
        {
            "role": "user",
            "content": AI_STEPS_MESSAGE
        }
    ]
    for message in ai_messages:
        prompt += f"{message['role'].capitalize()}: {message['content'].strip()}\n\n"
    # Print the assembled prompt
    print(prompt)

    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=ai_messages
    )
    ai_response = completion.choices[0].message.content
    print(ai_response)

    return ai_response

def ask_ai_issues_by_priorities_2_weeks(data: Dict[str, Dict[str, int]]) -> str:
    #global client
    client = OpenAI()
    # Assemble the prompt manually
    prompt = ""
    ai_messages = [
        {"role": "system",
         "content": AI_SYSTEM_MESSAGE},
        {
            "role": "user",
            "content": AI_CONTENT_MESSAGE_CREATED_ISSUES_BY_PRIORITIES
        },
        {
            "role": "user",
            "content": f"Here is the data for the analysis. It shows distributions of issues by priority reported by users 2 weeks after each release:\n\n"
                       + "\n\n".join([f"**{release}:**\n```{issues}```"
                                      for release, issues in data.items()])
        },
        {
            "role": "user",
            "content": AI_STEPS_MESSAGE
        }
    ]
    for message in ai_messages:
        prompt += f"{message['role'].capitalize()}: {message['content'].strip()}\n\n"
    # Print the assembled prompt
    print(prompt)

    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=ai_messages
    )
    ai_response = completion.choices[0].message.content
    print(ai_response)

    return ai_response

def ask_ai_issues_between_bugfixes(data: Dict[str, Dict[str, int]]) -> str:
    #global client
    client = OpenAI()
    # Assemble the prompt manually
    prompt = ""
    ai_messages = [
        {"role": "system",
         "content": AI_SYSTEM_MESSAGE},
        {
            "role": "user",
            "content": AI_CONTENT_MESSAGE_CREATED_ISSUES_BY_PRIORITIES
        },
        {
            "role": "user",
            "content": f"Here is the data for the analysis. It shows distributions of issues created by users between bugfixes:\n\n"
                       + "\n\n".join([f"**{release}:**\n```{issues}```"
                                      for release, issues in data.items()])
        },
        {
            "role": "user",
            "content": AI_STEPS_MESSAGE
        }
    ]
    for message in ai_messages:
        prompt += f"{message['role'].capitalize()}: {message['content'].strip()}\n\n"
    # Print the assembled prompt
    print(prompt)

    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=ai_messages
    )
    ai_response = completion.choices[0].message.content
    print(ai_response)

    return ai_response
