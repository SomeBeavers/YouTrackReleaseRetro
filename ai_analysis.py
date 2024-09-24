from collections import defaultdict
from typing import Dict

from openai import OpenAI

AI_STEPS_MESSAGE = """
    To proceed with the analysis, follow these steps:

    1. **Step-by-Step Comparison**: Break down the issues and compare their frequencies. Calculate percentage changes where applicable. Don't print this info.

    2. **Trend Identification**: Look for any significant increases or decreases in issues. Determine if there are emerging patterns or persistent problems.

    3. **Concerns and Improvements**: Highlight any categories that have worsened or improved significantly. Assess if there are any issues that need urgent attention.

    4. **Recommendations**: Based on your findings, provide detailed recommendations to improve the quality of future releases. Prioritize areas with the most significant changes or potential impact.

    Take your time to analyze the data thoroughly and provide a comprehensive response. Focus on latest release. Reply using markdown syntax.
    """

AI_COMMENTS_MESSAGE = """
    The format is "**issue id:** [comments from users]". Please analyze the comments' mood. If comment user is upset than comment is negative. If user talks about the problem without negative emotions than comment is neutral. 
    
    Create a .md table with the results of the analysis: how many issues (positive, negative, neutral) are there and the common theme and the reason of the selected mood. YOU MUST show only table in the reply.
    """

AI_CONTENT_MESSAGE_CREATED_ISSUES_BY_TYPES = """
    Hello! I need your expertise to analyze the quality of ReSharper's latest release. Specifically, I would like you to:

    1. Identify Significant Trends or Changes: Highlight any notable trends, increases, or decreases in issues between releases.

    2. Highlight Areas of Concern or Improvement: Identify any areas that have shown significant changes or may indicate potential areas for improvement.

    3. Provide Actionable Recommendations: Based on your analysis, offer practical recommendations to address any identified issues or trends.
    
    4. Provide conclusions about the quality of the latest release.
    """

AI_SYSTEM_MESSAGE = "You are an expert Quality Assurance Specialist at JetBrains with extensive knowledge of ReSharper's functionality, release cycles, and quality metrics. Your task is to analyze the data about the recent ReSharper releases to make a conclusions about quality."


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
            "content": AI_CONTENT_MESSAGE_CREATED_ISSUES_BY_TYPES
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
            "content": AI_CONTENT_MESSAGE_CREATED_ISSUES_BY_TYPES
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

def ask_ai_about_comments(data: Dict[str,list]):
    #global client
    client = OpenAI()
    # Assemble the prompt manually
    prompt = ""
    ai_messages = [
        {"role": "system",
         "content": AI_SYSTEM_MESSAGE},
        {
            "role": "user",
            "content": f"I have the following data about comments from users in ReSharper bugtracker::\n\n"
                       +"".join([f"**{id}:** `{comments}`" for id, comments in data.items()])
        },
        {
            "role": "user",
            "content": AI_COMMENTS_MESSAGE
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

def ask_ai_about_comments_combine(data: list):
    #global client
    client = OpenAI()
    # Assemble the prompt manually
    prompt = ""
    ai_messages = [
        {"role": "system",
         "content": AI_SYSTEM_MESSAGE},
        {
            "role": "user",
            "content": f"Please combine the result of analysis in one table by summing counts by mood and specifying the average common theme:\n\n"
                       +"".join(data)
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