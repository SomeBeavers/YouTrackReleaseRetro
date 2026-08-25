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
| `reports/release_stoppers_flow.csv` | Flow conformance: anomaly counts, unclear/end states, Planned vs Available |
| `reports/release_stoppers_release.csv` | The latest major release on its own, beside the full cohort |
| `reports/release_stoppers.xlsx` | All of the above as one Excel workbook, a tab per rollup |

### Focusing on one release

The rolling window spans several release cycles. The report also narrows to the newest major release
that has shipped — auto-detected from the release calendar, currently `2026.2` — and puts its
percentiles, volumes and flow anomalies next to the full cohort, plus a `Tagged before / after GA`
split. Patch versions count as part of their major release.

This is a filter over rows already fetched, so it costs nothing extra and runs by default. To pin a
different release:

```bash
.venv\Scripts\python.exe release_stoppers.py --release 2026.1
```

See the [release-focus section](release_stoppers_flow.md#latest-major-release-focus) for what
`Planned for` means here and how the GA split is measured.

### Comparing against other JetBrains products

```bash
.venv\Scripts\python.exe release_stoppers.py --compare
```

Measures the cohorts in `COMPARISON_COHORTS` — currently `IJPL+JBR` (`blocking-release`) — over the
same resolved-date window with the same metric definitions, and adds a **Cross-product comparison**
section to the report, `reports/release_stoppers_comparison.csv`, and a *Comparison* tab plus one
raw-data tab per cohort in the workbook. Roughly doubles runtime, so it is off by default.

Adding a product means one entry in `COMPARISON_COHORTS`: a YouTrack query, the tags that mark a
blocker there, and the product code for its release calendar. See the
[cohorts section](release_stoppers_flow.md#comparison-cohorts) for the two reporting bases and the
caveats that make a comparison fair.

### Excel workbook

`reports/release_stoppers.xlsx` holds everything in one file — tabs *Release stoppers*, *Percentiles*,
*Product volume*, *Planned versions*, *Affected areas*, *Regressions*, *Watchlist*, *Flow*,
*Release &lt;version&gt;*, and with `--compare` also *Comparison* and one tab of raw rows per
comparison cohort. Headers are frozen,
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

No network is needed for any of them — the YouTrack-facing code is split into pure parsers
(`parse_activities`) and pure builders (`compute_row`, the rollups), so tickets are mocked as the
dicts and activity payloads those consume:

| File | Covers |
|---|---|
| `tests/test_release_stoppers.py` | Row building (Created, Tag Added, Days, Planned For, In Planned, First Available, State History, Removed While Open), percentiles/volumes, classification, workbook layout |
| `tests/test_flow.py` | Flow conformance: the anomaly detectors, timeline exposure, and the flow rollups |
| `tests/test_release_focus.py` | Release detection, the major/patch grouping, and the release slice |
| `tests/test_cohorts.py` | Release-calendar GA precedence, tag vocabularies, comparison blocks and rendering |

```bash
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

