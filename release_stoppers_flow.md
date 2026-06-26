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
