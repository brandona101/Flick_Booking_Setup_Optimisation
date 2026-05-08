# ML Optimisation — Pest

Clustering model for Commercial Pest branches. Assigns booking setups to `{week_of_month}-{day_of_week}` slots (e.g. `2-Wednesday`) to form geographically coherent, capacity-balanced run structures for AGB.

## Branches

| Branch | Code | Status | Notes |
|---|---|---|---|
| [Melbourne Commercial](./melbourne-commercial/) | GM-MCP | Active — Run 4 | Pilot branch |

## Adding a new branch

1. Export the branch ABS data using [`melbourne-commercial/sql/AGB Branch Ready Export.sql`](./melbourne-commercial/sql/AGB%20Branch%20Ready%20Export.sql) filtered to the branch code
2. Copy the `melbourne-commercial/` folder and rename to the branch code
3. Update the data path in `phase0_distribution.py`
4. Run Phase 0 to profile the portfolio, then Phase 1 for clustering
5. Review dashboard outputs with the branch before AGB import

## Key data requirements per branch

- All active setups must have `latitude` / `longitude` populated on the Functional Location
- Recurrence type must be `Monthly - Week Pattern` (Mon–Fri) for inclusion in clustering core
- Simon Cormie (or equivalent admin-only) resources must be identified for exclusion
- Duration data should be audited prior to clustering (D3 remediation)
