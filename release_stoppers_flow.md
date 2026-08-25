# `release_stoppers.py` — flow

![release_stoppers.py flow](diagrams/release_stoppers_flow.svg)

> Diagram source: [`diagrams/release_stoppers_flow.mmd`](diagrams/release_stoppers_flow.mmd).
> Regenerate the SVG/PNG with `npm run render:flow` (see the README).

## Tag sets used

| Set | Tags | Role |
|---|---|---|
| `SEARCH_TAGS` | `dotnet-ex-release-stopper`, `rider-ex-stopper` | Path A discovery (currently tagged) |
| `MEASURE_TAGS` | `dotnet-release-stopper`, `rider-release-stopper` | Anchor the `tag_dt` date (primary); define "real release stopper" |
| `MEASURE_TAGS_FALLBACK` | `rider-ex-stopper`, `dotnet-ex-release-stopper` | Anchor `tag_dt` when no primary tag was added |
| `STOPPER_TAGS` | union of `SEARCH_TAGS` + `MEASURE_TAGS` | Path B qualification (was the issue ever a stopper) |
| `EAP_STOPPER_TAG` | `rider-eap-stopper` | Triggers EAP-only exclusion when no `MEASURE_TAGS` ever added |

`SCAN_PROJECTS` = DMRY, DTRC, DPA, PROF · `SCAN_PRIORITIES` = Show-Stopper, Critical · `RESOLVED_DATE_RANGE` = 2025-01-01 .. today

## Issue fields used

`ISSUE_FIELDS` is requested on both discovery paths. Beyond the timing fields, the rollups read
`tags` (regression tag), `description` (regression text match), `votes`, and the custom fields
`Subsystem`, `Linked Support Tickets` and `Affected licenses`.

## Rollups

Step 6 aggregates the finished rows — pure functions, no I/O, so they are unit-testable and can be
re-run over a published CSV.

| Rollup | Shape | Notes |
|---|---|---|
| Percentiles | 4 metrics × (All + one column per project) | Rows: `Valid N`, 25th, 50th (Median), 75th, 90th, 95th, 99th |
| Product volume | one row per project | Stopper count + share of total |
| Planned version volume | one row per `Planned for` value | Empty `Planned for` is bucketed as `(blank)`; YouTrack's own literal `No planned for` stays separate |
| Affected area | one row per `Subsystem`, cross-tabbed by project | Empty `Subsystem` is bucketed as `(no subsystem)` |
| Top affected area per project | one row per project | Its largest `Subsystem` and that area's share within the project |
| Regressions | count by classification + a ticket table | Also re-uses the affected-area cross-tab, scoped to regressions |
| Customer-signal watchlist | one row per signalled ticket | `QA note` / `Initial classification` are emitted empty for manual review |

Project columns are ordered by descending volume, so `All, RIDER, RSRP, …`.

### Percentile conventions

Chosen to match the tracking spreadsheet cell-for-cell:

- Linear-interpolated *inclusive* percentile (`percentile_inc`), the same as Google Sheets
  `PERCENTILE` / `PERCENTILE.INC`: `rank = p × (n − 1)`, interpolating between neighbours.
- **`Days Tag to Release` is reversed**: the formula uses `1 − p`, so "90th" reads as *90% of
  tickets were tagged at least this many days before release*. Values therefore *decrease* down the
  column, and can go negative when the tag landed after the release date.
- `Valid N` counts only issues that have the metric — `Days Tag to First Fixed` is absent for
  issues that never reached Fixed/Verified, and `Days Tag to Release` needs a dated release.
- Aggregation happens on the values *as published* (one decimal), so the percentiles are consistent
  with the per-issue table above them.
- Interpolation and rounding run in `Decimal` with halves rounded away from zero. Both matter: a
  midpoint like `201.15` is `201.1499…` in binary float, and Python's own formatting would then
  round it *down* to `201.1` where the spreadsheet shows `201.2`.

### Workbook

`write_xlsx` renders the same rollups into `reports/release_stoppers.xlsx`, one tab each. The layout
is decided by `xlsx_sheets`, a pure function returning
`[(sheet title, [(caption, header, rows, column formats), ...])]`, so it is unit-testable without
openpyxl; `write_xlsx` only applies styling. Day counts and shares are written as numbers with a
display format (`0.0`, `0.0%`) rather than pre-rounded text, so the spreadsheet can chart them.
openpyxl is optional — the run reports and skips the workbook when it is missing.

### Affected area

`Subsystem` is used directly as the affected area, which keeps the grouping deterministic and
reproducible. The caveat is coverage: `Subsystem` is well populated in RIDER/RSRP but largely empty
in the profiler projects, so a large `(no subsystem)` bucket there is expected rather than a bug.

### Regression classification

Two signals, kept as separate labels because they are not equally trustworthy:

| Label | Source | Reliability |
|---|---|---|
| `.net-regression tag` | `REGRESSION_TAG` on the issue | Authoritative |
| `mentions regression` | `regress` matched in summary or description | Weak — a hint, not a verdict |

The tag wins when both apply. Note the text match is a poor proxy for a human "this is a regression"
call: tickets are often discussed as regressions without the word appearing in either field, and it
finds only a handful of extra tickets in practice. Drop `REGRESSION_BY_TEXT` from
`classify_regression` if only the tag should count.

### Customer-signal watchlist

A ticket is listed when it has at least `SUPPORT_SIGNAL_MIN` linked support tickets or
`VOTES_SIGNAL_MIN` votes; the `Signal` column records which fired (`Support`, `Votes`,
`Support+votes`). Ordered by support tickets, then votes, then affected licenses. The three
underlying fields are `Linked Support Tickets`, `votes` (a built-in issue field, not a custom one),
and `Affected licenses`; all default to `0` where a project doesn't define them.

This is a mechanical shortlist, deliberately wider than a hand-curated watchlist — tighten the two
thresholds to narrow it.
