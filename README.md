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

`release_stoppers.py` builds the release-stopper report. The full logic — two issue-discovery paths,
the EAP-only exclusion, tag-date resolution, the version-fit metrics, and the rollup conventions —
is described in [`release_stoppers_flow.md`](release_stoppers_flow.md).

It writes, alongside a console rendering:

| File | Contents |
|---|---|
| `reports/release_stoppers.md` | Per-issue table + all rollups, in one readable document |
| `reports/release_stoppers.csv` | Per-issue table |
| `reports/release_stoppers_percentiles.csv` | Percentiles per metric × project (+ `Valid N`) |
| `reports/release_stoppers_product_volume.csv` | Stopper count and share by product |
| `reports/release_stoppers_planned_versions.csv` | Stopper count and share by `Planned for` version |
| `reports/release_stoppers_subsystems.csv` | Affected area by `Subsystem` × project, and each project's top area |
| `reports/release_stoppers_regressions.csv` | Regression counts by classification + the regression tickets |
| `reports/release_stoppers_watchlist.csv` | Tickets with customer signal (support tickets / votes / licenses) |
| `reports/release_stoppers.xlsx` | All of the above as one Excel workbook, a tab per rollup |

### Excel workbook

`reports/release_stoppers.xlsx` holds everything in one file — tabs *Release stoppers*, *Percentiles*,
*Product volume*, *Planned versions*, *Affected areas*, *Regressions*, *Watchlist*. Headers are frozen,
issue links are clickable, and day counts and shares are written as real numbers (not text) so they
can be charted directly. Upload it to Google Drive and Sheets will convert it.

It needs `openpyxl`; without it the run still produces everything else and prints a note:

```bash
.venv\Scripts\python.exe -m pip install openpyxl
```

Charts are not written into the workbook — a chart built on an imported sheet has to be created once
in Sheets. If you would rather keep the charts in an existing Google Sheet alive, the data has to be
written into that sheet in place via the Sheets API, which needs Google credentials this script does
not have.

### CSVs

The CSVs are shaped to paste straight into the tracking spreadsheet's tabs. Percentiles follow
Google Sheets' `PERCENTILE.INC`, and `Days Tag to Release` uses a reversed (`1 − p`) threshold — see
the [rollups section](release_stoppers_flow.md#rollups) for why.

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

The row-building and rollup logic is covered by `tests/test_release_stoppers.py` (no network needed —
it feeds mocked tickets through the pure `parse_activities` / `compute_row` functions and checks
Created, Tag Added, Days, Planned For, In Planned, First Available, State History, Removed While
Open, etc., then the percentile/volume builders on top of them):

```bash
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

