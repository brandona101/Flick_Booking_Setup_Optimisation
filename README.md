# Flick Booking Setup Optimisation

Internal project — Flick Pest & Hygiene scheduling optimisation toolset.

Designed to support branches transitioning to AGB (Auto Generate Bookings) on Flick 360 (Dynamics 365), with tools spanning diagnostics, maintenance, manual overhauls, and ML-driven run generation.

---

## Components

| Component | Status | Description |
|---|---|---|
| [Run Diagnostic](./run-diagnostic/) | Pilot | Import runs, apply scoring logic, visualise current setup health |
| [Run Maintenance](./run-maintenance/) | Planned | Surface improvement opportunities (tech overlap, overloaded runs) and support targeted adjustments |
| [Run Builder](./run-builder/) | Planned | Visual HTML tool for building runs from the ground up at a branch level |
| [ML Optimisation](./ml-optimisation/) | Active (Pest — MCP) | Machine learning clustering to generate optimised base run structures |

---

## Project Background

See [`docs/Booking Setup Optimisation Proposal.md`](./docs/Booking%20Setup%20Optimisation%20Proposal.md) for the full project proposal, workstream breakdown, and success criteria.

Scheduling logic principles are documented in [`docs/Scheduling Logic Best Practice.md`](./docs/Scheduling%20Logic%20Best%20Practice.md).

---

## Data Handling

**No customer or operational data is committed to this repository.**  
All `.csv` files and generated dashboard outputs are gitignored. Source data is managed locally and accessed via Dynamics 365 / Databricks exports. See `.gitignore` for the full exclusion list.

---

## Roadmap

- **Now:** ML Optimisation pilot live for Melbourne Commercial Pest. Run Diagnostic tool in pilot with Hygiene.
- **Next:** Run Maintenance tooling. Expand ML Optimisation to additional Pest branches and Hygiene.
- **Future:** Run Builder (visual HTML). Databricks integration for ML pipeline. Fusion 5 system implementation (Phase 2).

---

## Contributing

This repo is maintained by the Flick BA/Ops team. Branch off `main` for any feature work. Keep data out of commits — use the `data/` subfolder within each component (gitignored) for local working files.
