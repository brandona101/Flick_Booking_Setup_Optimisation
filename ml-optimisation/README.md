# ML Optimisation

Machine learning clustering to generate optimised base run structures for branches — covering geographic grouping, frequency-stratified slot assignment, and capacity balancing.

## Status

**Active** — Melbourne Commercial Pest (GM-MCP) pilot in Run 4. Expanding to additional Pest branches and Hygiene.

## Approach

Constrained discrete optimisation using frequency-stratified K-means clustering with:
- MAD-based outlier exclusion before zone seeding
- Geometric median centroids (outlier-robust)
- Tabu-search capacity rebalancing
- Spatial majority filter for topology cleanup

Full algorithm detail: [`pest/melbourne-commercial/CLAUDE.md`](./pest/melbourne-commercial/CLAUDE.md)

## Service lines

| Service line | Status | Branch(es) |
|---|---|---|
| [Pest](./pest/) | Active — MCP pilot | Melbourne Commercial Pest (GM-MCP) |
| [Hygiene](./hygiene/) | Planned | TBD |

## Output

Each branch run produces:
- `*New Date Pattern` assignments per booking setup (`{week}-{DayName}` format)
- Per-tech capacity summary
- Topology diagnostics (enclave rate, disconnected zones)
- Interactive HTML dashboard (per-tech maps with slot layers)

Outputs are **not committed** — generated locally from source scripts and reviewed by branch before AGB import.

## Pipeline (current — Python local; target — Databricks)

```
Phase 0: Portfolio distribution analysis  →  phase0_distribution.py
Phase 1: Geographic clustering + slot assignment  →  phase1_clustering.py
         Joint slots variant  →  phase1_joint_slots.py
         Dashboard generation  →  phase1_visualise.py / phase1js_visualise.py
```

## Databricks migration

Pending data engineer assessment. Target stack: PySpark / MLlib (distributed K-means), Hyperopt (Bayesian hyperparameter optimisation). Scripts are library-agnostic to ease migration.
