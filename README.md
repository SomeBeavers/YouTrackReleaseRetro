# AI-Powered ReSharper Release Analyzer

## Description
This project aims to simplify the analysis of ReSharper releases by leveraging AI to process and interpret data from YouTrack. The Python-based tool will automatically gather information about issues from YouTrack, such as the number of tickets sorted by priority for each release in the current year. The AI component will then analyze this data to provide insights, trends, and potential areas for improvement.

## Features
- Analyze YouTrack issue data to identify release trends and quality metrics.
- Leverage OpenAI’s capabilities to generate meaningful insights from historical data.
- Provide actionable insights for continuous improvement in software releases.

## Requirements
- Python 3.7+
- A YouTrack permanent token [Get it here](https://www.jetbrains.com/help/youtrack/server/manage-permanent-token.html)
- An OpenAI API key [Get it here](https://platform.openai.com/api-keys)

## Setup

1. Set up environment variables for YouTrack and OpenAI tokens:
   - **For Windows**:
     ```bash
     set YOUTRACK_TOKEN=your_youtrack_token
     set OPENAI_API_KEY=your_openai_api_key
     ```
   - **For macOS/Linux**:
     ```bash
     export YOUTRACK_TOKEN=your_youtrack_token
     export OPENAI_API_KEY=your_openai_api_key
     ```

## Usage

Run the analyzer script `main.py`.

## Release stoppers analysis

`release_stoppers.py` builds the release-stopper report (`reports/release_stoppers.md` / `.csv`).
The full logic — two issue-discovery paths, the EAP-only exclusion, tag-date resolution, and the
version-fit metrics — is described in [`release_stoppers_flow.md`](release_stoppers_flow.md).

![release_stoppers.py flow](diagrams/release_stoppers_flow.svg)

### Regenerating the diagram

The diagram source is [`diagrams/release_stoppers_flow.mmd`](diagrams/release_stoppers_flow.mmd)
(Mermaid). After editing it, regenerate the SVG/PNG:

```bash
npm install        # first time only — installs @mermaid-js/mermaid-cli
npm run render:flow
```

`render:flow` writes `diagrams/release_stoppers_flow.svg` and `.png`. The first render downloads a
headless Chromium for the renderer (via puppeteer).

### Tests

The row-building logic is covered by `tests/test_release_stoppers.py` (no network needed — it feeds
mocked tickets through the pure `parse_activities` / `compute_row` functions and checks Created, Tag
Added, Days, Planned For, In Planned, First Available, State History, Removed While Open, etc.):

```bash
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

