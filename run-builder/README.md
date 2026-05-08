# Run Builder

A visual HTML tool for building runs from the ground up at a branch level — for branches that need a full overhaul rather than incremental adjustments.

## Status

**Planned** — concept stage. Builds on the visual layer developed in the ML Optimisation dashboard.

## Intended scope

- **Map-first interface:** Display all functional locations on an interactive map, coloured by current run assignment
- **Drag-to-assign:** Schedulers drag sites between runs or create new run groups directly on the map
- **Slot management:** Assign sites to `{week}-{day}` slots with live capacity tracking
- **Constraint display:** Show locked setups, preferred technicians, and site-level notes alongside geographic data
- **Export:** Output a completed run structure as a CSV importable into AGB

## Design principles

- Built as a self-contained HTML file (no server required) — opens in a browser, loads data locally
- Should work offline — branches may be running this without internet access
- Keeps branch schedulers in control — the tool is a canvas, not an auto-pilot
- Any output should pass through the Run Diagnostic tool before AGB import

## Relationship to other components

- Shares visual layer with: **ML Optimisation** dashboard (phase1_visualise.py outputs)
- Output validated by: **Run Diagnostic** before AGB import
- Alternative to: **ML Optimisation** for branches that prefer a manual approach or where ML outputs need heavy local adjustment
