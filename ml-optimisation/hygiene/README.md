# ML Optimisation — Hygiene

Clustering model for Hygiene branches. Planned as a follow-on from the Pest pilot, with customer-specific logic to be designed based on Hygiene's service patterns.

## Status

**Planned** — design not yet started. Hygiene has different recurrence patterns (week-based, not monthly calendar-anchor) and will require adapted clustering logic.

## Key differences from Pest

| Dimension | Pest | Hygiene |
|---|---|---|
| Recurrence type | Monthly - Week Pattern (Nth weekday) | Weekly-based (e.g. 4-weekly, 8-weekly) |
| Run structure | Week-of-month + day-of-week | Day-of-week (4-week cycle, anchored) |
| AGB status | Rolling out | Already live (implemented Q4 2025) |
| Data quality | Remediation in progress (D1–D4) | Generally cleaner — AGB already running |

## Starting point

VIC Hygiene data export is available as a reference dataset (`VIC Hygiene ABS.csv` — held locally, not committed). Use this to profile the Hygiene portfolio and define the adapted clustering approach before building scripts.

## Branches

_None yet — to be added once design is confirmed._
