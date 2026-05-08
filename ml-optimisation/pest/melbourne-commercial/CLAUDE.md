# BSO Grouping Model — Project Reference

## Context
Flick 360 (Dynamics 365). Commercial Pest division. Goal: build a clustering algorithm that assigns booking setups to `{week_of_month}-{day_of_week}` slots (e.g. "2-Wednesday") to form efficient, geographically coherent run structures for AGB.  
Pilot branch: **Melbourne Commercial Pest** (`vel_branchcode = GM-MCP`).  
Output feeds back into the `*New Date Pattern` field on each booking setup, reviewed by branch before AGB commit.

Full context: `Booking Setup Optimisation Proposal.md`, `Scheduling Logic Best Practice.md`.

---

## Data

**Source file:** `Melbourne Commercial AGB - Test Data (24-04-26).csv`  
**Origin SQL views:** `dbo.agb_ABS_Export` (base) → `pbi.BA_AGBS_AllBranch` (branch export)

Column prefix conventions: `%` = metadata/read-only, `~` = editable input, `*` = algorithm output.

| Column | Notes |
|---|---|
| `%booking_setup_id` | Setup GUID — primary key |
| `%FL_id` | Functional Location GUID — site grouping key (Tier 1) |
| `FL_name`, `Address 1`, `city` | Human-readable site info |
| `latitude`, `longitude` | **Not in current CSV export — must be added.** In base view `agb_ABS_Export`. Required for Tier 2. |
| `Current Duration` | Incident duration (minutes). Treat as unreliable — may overstate actual time. |
| `~New Duration` | Corrected duration field (editable). Use if populated, else `Current Duration`. |
| `%frequency_type` | `Weekly`, `Weekly - Multi Day`, `Monthly - Week Pattern`, `Monthly - Fixed Date`, `Yearly`, `Daily` |
| `Recurrence Frequency` | Human label e.g. `3 Monthly`, `1 Weekly` |
| `num_recurrences` | Numeric interval (e.g. `3` for quarterly) |
| `services_per_year` | Pre-calculated: `12/N` monthly, `52/N` weekly, `1` yearly |
| `%recc_dow_number` | Day-of-week: **0=Sun, 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat** |
| `%recc_week_number` | Week-of-month (1–4). For `Monthly - Week Pattern`: from `<weekdef>`. For `Weekly`: 4-week cycle position anchored to 19 May 2025. |
| `%start_date` | Parsed from recurrence XML `<start>`. MM/DD/YYYY in XML → DATE |
| `%is_valid_start_date` | `Valid`/`Invalid`. Invalid = first occurrence shifts forward one cycle. Pre-remediated before model runs. |
| `Current Date Pattern` | Existing assignment. Format: `{week}-{DayName}` or `Every {DayName}` |
| `Serviced Date Pattern` | Most frequent actual completed pattern from work order history |
| `*New Date Pattern` | **Algorithm output.** Same format as Current Date Pattern. |
| `*Preferred Resource` | Existing preferred tech (unreliable / not fully allocated). Use for baseline comparison only. |

**Day capacity target:** ~8h service duration per cluster-day + haversine travel allowance (TBD).

---

## Recurrence String Format

XML. Key tags:

```xml
<!-- Monthly - Week Pattern (quarterly, 4th Friday) -->
<root><pattern><period>monthly</period><option>everyWeekday</option>
  <months every='3'><weekdef>4</weekdef><weekday>5</weekday></months></pattern>
  <range><start>07/01/2025</start><option>endBy</option><end>12/31/2099</end></range></root>
```

- `<months every='N'>` — recur every N months
- `<weekdef>` — week of month (1–4)
- `<weekday>` — day of week (0=Sun … 6=Sat)
- `<weeks every='N'><days>` — weekly, N-week interval, day number
- `<years every='N'>` — yearly, but **`N` = month number the service drops in** (e.g. `every='11'` = November), NOT a repeat interval. All yearly setups fire once per year. This is a Dynamics-specific quirk — do not treat `every` as a frequency multiplier for yearly types.
- All pre-parsed fields already available in CSV. Raw string rarely needed by model.

---

## Algorithm Design

### Phase 0 — Portfolio Distribution Analysis
Before clustering, establish the work volume landscape.

1. Parse `services_per_year` and `Current Duration` (or `~New Duration`) per setup.
2. Calculate **monthly duration contribution** per FL: `duration × (services_per_year / 12)`.
3. Aggregate by suburb/area → hours per area per month.
4. Determine required number of run-days per area (at 8h capacity).
5. Output: area heatmap, frequency breakdown, FL count by tier.

This sets the canvas — how many cluster-days we need and roughly where.

### Phase 1 — Implemented Algorithm (as of Run 4)

Script: `phase1_clustering.py`. Per-tech pipeline:

**Stage 0 — Outlier detection (MAD-based)**
- Compute tech's geometric median. Distance each FL → median.
- Flag FLs where `dist > median + 2×MAD` as outliers. ~16% of tech-FL rows.
- Outliers excluded from zone-seeding; attach last after zones are formed.

**Stage 1 — Zone-defining set (frequency-stratified)**
- `anchor_freq` per FL = max `services_per_year` across all setups at (tech, FL).
- `anchor_tier`: ≥26/yr→T5, ≥12/yr→T4, ≥4/yr→T3, ≥1.5/yr→T2, else T1.
- Zone-defining set = highest tier present (non-outlier), expanded down until ≥5 FLs.

**Stage 2 — K=5 day zones (pure geographic)**
- K-means++ on zone-defining set. Hours as centroid weights only — no capacity gate during seeding.
- Centroids refined via geometric median (Weiszfeld IRLS — outlier-robust).

**Stage 3 — Lower-tier attachment**
- Each lower tier attaches FL-by-FL to nearest centroid.
- After each tier, centroids recomputed (geometric median of all assigned FLs).
- Outliers attach last; final centroid recompute.

**Stage 4 — Day-of-week ordering**
- Zones ordered by longitude west→east → Mon..Fri.

**Stage 5 — Week sub-clustering**
- Within each day zone, K=4 geographic sub-clusters ordered by latitude north→south → Wk1..Wk4.

**Stage 6 — Tabu-search rebalance**
- Iteratively moves boundary FLs from heaviest over-cap (week, day) slot to nearest under-cap slot on same tech.
- Tabu list (size 15) prevents oscillation. One move per iteration (heaviest slot first), max 500 iterations per tech.

**Stage 7 — Spatial majority filter** (post-rebalance)
- For each FL, find K=7 nearest geographic neighbours.
- If ≥3 neighbours are in the same different slot → reassign (capacity-gated: `dst_load + fl_hrs ≤ 8h` OR `new_dst_load < src_load`).
- Iterates per tech to stability (max 10 iterations).

**Stage 8 — Topology diagnostics**
- Flood-fill connected-component analysis per (tech, week, day) zone (gap > 15km = new component).
- FLs in disconnected zones and outlier FLs flagged on `tech_fl`.

**Key constants:**
```
CAPACITY_PER_DAY_HRS = 8.0
OUTLIER_MAD_MULTIPLIER = 2.0
ENCLAVE_K_NEIGHBORS = 7
ENCLAVE_MIN_MAJORITY = 3
ENCLAVE_MAX_ITER = 10
DISCONNECTED_GAP_KM = 15
```

**Anchor + same-site enforcement:** All setups at (tech, FL) share the FL's zone/week assignment. `anchor_freq` and `anchor_tier` columns propagated to setup-level output.

**Output columns added in Phase 1:**
`anchor_freq`, `anchor_tier`, `is_outlier`, `in_disconnected_zone` on `phase1_fl_assignments.csv`.

**Tech count is derived from the portfolio, not supplied as an input.** The algorithm clusters until 8h capacity is reached, then seeds a new run — the number of technicians required emerges from the data. A future version may accept a branch-specified tech count as a constraint, with the model redistributing work to fit and flagging over-capacity day-slots (likely indicating duration data issues or genuine capacity shortfalls requiring additional resource).

**6-Weekly handling:** Uses the Hygiene 4-week cycle concept (anchored to 19 May 2025 = Week 1). Cannot be guaranteed to align with a monthly drop — best effort is to assign the same **day-of-week** as the geographic cluster it belongs to. Output slot: `Every {DayName}` (no week number). 6-weekly is currently 89% Monday — historical default, not geographic; re-clustering will redistribute. No equivalent monthly frequency exists — these are legacy and the business should stop selling them; existing ones treated as-is.

**52 Weekly and 26 Weekly — suggest recurrence conversion:**
- `52 Weekly` (every 52 weeks) ≈ `12 Monthly` (annual). Flag in output as candidate for conversion to `12 Monthly` for consistency.
- `26 Weekly` (every 26 weeks) ≈ `6 Monthly` (bi-annual). Flag in output as candidate for conversion to `6 Monthly`.
- These setups are clustered normally using their derived `services_per_year`; the conversion flag is a data quality recommendation only, not a clustering gate.

**Clustering scope — PoC inclusions/exclusions:**

| Frequency type | Action |
|---|---|
| Monthly - Week Pattern, Mon–Fri | **Include** — core set (~4,609 setups) |
| 6 Weekly | **Include** — day-of-week assignment only |
| Monthly - Week Pattern, Sat/Sun | Exclude — overflow/OT only |
| Monthly - Fixed Date | Exclude — awaiting D1 remediation |
| Yearly | Exclude — edge case |
| Daily | Exclude — edge case |
| NULL | Exclude |
| Simon Cormie (all 562 setups) | Exclude — invoice/admin processing, not field service |
| Zero-duration (non-Cormie, 11 setups) | Include with 15-min default duration |
| Duration > 480 min (2 setups in working set) | Exclude from capacity calc pending manual review |
| Week 0 "5th weekday" (2 setups) | Exclude |
| Ultra-rare monthly (36 / 60 / 72 Monthly — 3–6 year intervals) | Include — ride along as lowest-priority assignments; negligible capacity contribution |

---

## KPIs

| KPI | Definition | Target | Run 4 |
|---|---|---|---|
| % setups allocated | Setups with a valid `*New Date Pattern` / total | ↑ | 100% |
| Same-site grouping rate | % multi-setup FLs with all setups on same slot | 100% | 100% |
| Mean FL→centroid distance | Avg haversine FL to zone centroid (km) | ↓ | 11.07 km |
| Total haversine distance | Sum FL→centroid across all techs (km) | ↓ | ~42,250 km |
| Slots over 8h cap | % of (tech, week, day) slots exceeding 8h | ↓ | 5.6% |
| Max slot load | Heaviest single slot (hours) | ↓ | 16.2h |
| Strict enclave rate | % FLs where ≥3/7 nearest neighbours are in a different slot | ≤5% | **7.78%** |
| Loose enclave rate | % FLs where any other slot has more neighbours than current | ↓ | 8.36% |
| Disconnected zones | (tech, week, day) zones with >1 spatial component (gap >15km) | ↓ | 19 |

---

## Key Business Rules

- **Anchor first:** Place highest-frequency services first; lower-frequency services at same FL align to anchor.
- **Same-site = same day:** Tier 1 is non-negotiable. No FL split across days without explicit lock override.
- **Stability bias:** Only move `Current Date Pattern` when routing benefit materially warrants it. Prefer retaining existing assignment.
- **Pest recurrence format:** All setups must be `Monthly - Week Pattern` (Nth weekday). `Monthly - Fixed Date`, `Yearly`, `Daily` are edge cases — flag for manual review before including in clustering.
- **Duration reliability:** Treat `Current Duration` as potentially overstated. Build in headroom; don't assume capacity is achievable at face value.
- **Lock support (future):** Model must support locked setups that cannot be changed. Not enforced in PoC but architecture should accommodate.

---

## File Index

| File | Purpose |
|---|---|
| `CLAUDE.md` | This file — project reference |
| `LOG.md` | Decision log (dated entries) |
| `Booking Setup Optimisation Proposal.md` | Project proposal — background, tiers, metrics |
| `Scheduling Logic Best Practice.md` | Algorithm logic spec for Fusion 5 |
| `AGB Base Export Query.sql` | `dbo.agb_ABS_Export` view — source of all setup data |
| `AGB Branch Ready Export.sql` | `pbi.BA_AGBS_AllBranch` — branch-facing export view |
| `Melbourne Commercial AGB - Test Data (24-04-26).csv` | Pilot dataset (GM-MCP) |
| `phase0_distribution.py` | Phase 0 — portfolio distribution analysis |
| `phase0_working_dataset.csv` | Phase 0 output — filtered working set (5,092 setups) |
| `phase0_fl_summary.csv` | Phase 0 output — FL-level summary |
| `phase0_area_summary.csv` | Phase 0 output — area-level hours summary |
| `phase1_clustering.py` | Phase 1 — main clustering algorithm (Run 4) |
| `phase1_setup_output.csv` | Phase 1 output — setup-level assignments (5,062 rows) |
| `phase1_fl_assignments.csv` | Phase 1 output — FL-level assignments with topology flags |
| `phase1_tech_summary.csv` | Phase 1 output — per-tech capacity summary |
| `phase1_slot_capacity.csv` | Phase 1 output — per-slot load (720 slots) |
| `phase1_disconnected_zones.csv` | Phase 1 output — disconnected zone diagnostics |
| `phase1_bad_coords.csv` | Phase 1 output — 6 FLs with bad/foreign coordinates |
| `phase1_visualise.py` | Dashboard generator — per-tech HTML maps with topology layer |

---

## Dataset Profile (GM-MCP, 2026-04-24)

| Metric | Value |
|---|---|
| Total setups | 7,463 |
| Unique FLs | 4,552 |
| FLs with multiple setups | 1,779 |
| Missing lat/lon | 0 |
| Setups with preferred resource | 7,347 (98%) |
| On AGB | 7,333 (98%) |
| Mean duration | 46.4 min |

**Frequency type split:**

| Type | Count | Handling |
|---|---|---|
| Monthly - Week Pattern | 5,648 | Core clustering target |
| Yearly | 935 | Edge case — flag, exclude from PoC clustering |
| Weekly (6-weekly dominant) | 684 | Secondary — include but treat carefully |
| Monthly - Fixed Date | 117 | Non-conforming per D1 — flag for remediation |
| Daily (45 Daily) | 75 | Edge case — exclude |
| NULL | 4 | Exclude |

**Recurrence frequency (top):** 3 Monthly (2,821), 1 Monthly (1,616), 6 Monthly (953).

**DOW in Monthly - Week Pattern:** Mon–Fri ~866–1,042 each. Sat 343, Sun 696 — weekend services require separate run logic; exclude from Mon–Fri clustering PoC.

**Week-of-month distribution:** Wk1 1,814 / Wk2 1,064 / Wk3 1,352 / Wk4 1,416.

**Known data quality issues:**
- **Simon Cormie setups (562 total):** Exclude entirely — invoice/admin processing, not field service.
- Remaining zero-duration setups (7 after Cormie exclusion) → substitute 15 min default duration.
- **FLs missing lat/lon (16):** Flag and exclude from clustering. Easy for users to correct by updating the FL record.
- 17 setups with duration > 480 min — clearly erroneous; flag for manual review, exclude from capacity calculations until corrected.
- 2 "5th weekday" setups (Week 0: `0-Monday`, `0-Thursday`) — no reliable monthly slot; exclude.
- 1,039 weekend `Monthly - Week Pattern` (Sat/Sun) — Saturday is overflow/overtime only, not scheduled runs. Exclude from PoC clustering entirely.
- 117 `Monthly - Fixed Date` — non-conforming (D1 remediation required); exclude until converted to `Monthly - Week Pattern`.

---

## Optimisation Approach

This is a **constrained discrete optimisation** problem (not continuous gradient descent). The algorithm is constrained K-means with anchor initialisation + local search refinement — functionally equivalent to coordinate descent in discrete space.

**Objective:** Minimise total intra-cluster haversine distance, subject to:
- Hard: all setups at same FL assigned to same cluster (Tier 1)
- Hard: cluster capacity ≤ ~8h service duration per day-slot
- Soft: day adjacency (Mon cluster centroid adjacent to Tue, etc.)

**Implemented pipeline (Phase 1 Run 4):**
1. Phase 0 — density analysis → canvas
2. Per-tech: outlier detection (MAD) → frequency-stratified K=5 day zones → K=4 week sub-zones
3. Tabu-search rebalance (capacity)
4. Spatial majority filter with capacity gate (topology cleanup)
5. Topology diagnostics (enclave rate, disconnected zones)

**Local minima risk:** Anchor seeding mitigates this by ensuring a business-aligned initialisation. Simulated Annealing is the natural next step if we need to search more broadly (relevant for Databricks ML discussion).

**Cluster shape caveat:** Because the input data reflects human-made (non-optimised) resource allocations, the real work distribution is unlikely to form compact radial clusters around centroids. Expect irregular, elongated, or corridor-shaped groupings (e.g. following industrial strips or arterial roads). K-means centroid distance as a quality metric may therefore understate or misrepresent true cluster compactness. Flag this when selecting or interpreting KPIs post-optimisation — average pairwise intra-cluster distance or convex hull area may be more honest than distance-to-centroid for irregularly shaped clusters.

**Geographic grouping uses lat/lon exclusively.** Suburb/city labels are not used as clustering inputs — coordinates are the only geographic signal. City names appear in outputs for human readability only. This avoids inconsistent suburb naming and lets the algorithm discover natural geographic zones from the data itself.

**Databricks ML:** Keep approach library-agnostic for now. MLlib (distributed K-means) and Hyperopt (Bayesian optimisation over hyperparameters) are the likely tools. Pending data engineer input on what's available.

## Open Items

- [ ] **Strict enclave rate 7.78% (target ≤5%)** — above target. Investigate which techs contribute most. Likely: capacity gate too restrictive in dense areas, and genuine boundary FLs that can't reach ≥3/7 majority. Consider adaptive relaxation or per-tech analysis.
- [ ] **19 disconnected zones** — review whether legitimate (isolated rural work) or algorithmic artefact (outlier exclusion leaving sub-groups stranded).
- [ ] **Adaptive K** — allow K < 5 when tech portfolio has fewer than 5 natural geographic clusters. Structural fix for the "Ballan" class of problem (isolated FLs forced into their own day zone).
- [ ] Confirm travel allowance method (haversine to centroid confirmed for PoC; revisit with intraday sequencing later).
- [ ] Data engineer to demonstrate Databricks ML component — assess fit before committing to implementation path.
- [ ] Port to Databricks notebook.
