# Run Maintenance

Given an existing set of runs, surfaces improvement opportunities and supports targeted adjustments — without a full rebuild.

## Status

**Planned** — design phase. Will follow Run Diagnostic tool maturity.

## Intended scope

- **Tech overlap detection:** Flag sites serviced by multiple technicians on the same day — candidates for consolidation
- **Overloaded run identification:** Surface day-slots exceeding capacity thresholds, with suggested redistribution moves
- **Underloaded run identification:** Flag technicians with significant spare capacity that could absorb nearby work
- **Boundary FL review:** Show functional locations that sit on the geographic edge of a run, where reassignment to an adjacent run would improve routing
- **Guided adjustment UI:** Allow schedulers to accept, reject, or modify each suggested change with a live preview of impact

## Design principles

- Changes should be surgical — this tool is for tuning existing runs, not rebuilding them
- Each suggested change shows the routing/capacity impact before the user accepts it
- All changes are exportable as a diff for AGB re-import
- Branch locks (customer-committed service days) are respected and surfaced as constraints

## Relationship to other components

- Feeds from: **Run Diagnostic** (identifies which runs need attention)
- Feeds into: **AGB re-import** (adjusted setups exported and re-applied)
- Complements: **ML Optimisation** (ML handles ground-up build; this handles ongoing maintenance)
