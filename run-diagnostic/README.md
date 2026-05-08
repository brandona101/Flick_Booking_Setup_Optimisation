# Run Diagnostic Tool

Imports a branch's booking setup export, applies scoring and rule logic, and visualises the current health of runs — surfacing issues before any optimisation work begins.

## Status

**Pilot** — live with VIC Hygiene. Expanding to Pest.

## What it does

- Accepts a branch ABS (AGB Booking Setup) export as input
- Applies configurable rules to assess setup quality (e.g. tech overlap, overloaded slots, unbalanced days)
- Scores each run against defined criteria
- Produces an interactive HTML visualisation of current run health

## Files

| File | Description |
|---|---|
| `flick_run_diagnostic_pilot.html` | Self-contained diagnostic tool (open in browser, import CSV) |
| `docs/hygiene_run_diagnostic_user_guide.docx` | User guide — Hygiene pilot |
| `docs/run_scoring_methodology.docx` | Scoring methodology and rule definitions |

## Usage

1. Export the branch ABS data from Dynamics 365 (use the SQL views in `ml-optimisation/pest/melbourne-commercial/sql/` as a reference for the required columns)
2. Open `flick_run_diagnostic_pilot.html` in a browser
3. Import the CSV export
4. Review the scored output — use filters to prioritise issues

## Next steps

- Consolidate Pest and Hygiene into a single unified tool
- Add custom rule configuration UI
- Integrate agreed-on set logic from the ML Optimisation workstream
