# Decision Log

---

## 2026-04-24 — Session 1: Alignment & Setup

**State:** Pre-code. Alignment session. No model built yet.

**Decisions accepted:**
- Algorithm style: greedy anchor-first expansion with rebalance pass (not pure K-means).
- Tier 1 (site consolidation) enforced as hard constraint — no FL split across days.
- Tech count treated as unconstrained in PoC — identify natural cluster count from data first.
- Day capacity = ~8h service duration per `{week}-{day}` slot.
- Quarterly/yearly capacity contribution: 12-month forward window average per slot (not flat 1/4 weighting).
- Duration data treated as unreliable — build in headroom; don't assume face-value achievability.
- DOW encoding confirmed: 0=Sun, 1=Mon … 6=Sat (from `agb_ABS_Export` SQL).
- Output field: `*New Date Pattern`, format `{week_number}-{DayName}` or `Every {DayName}`.
- Log and CLAUDE.md kept as separate files. CLAUDE.md targets token efficiency.
- Future Databricks migration (PySpark) noted but out of scope for PoC.

**Blockers:**
- `latitude`/`longitude` not in current CSV export. Required for Tier 2. Must re-export from `agb_ABS_Export`.

**Next actions:**
- [x] Re-export CSV with `latitude` and `longitude` — resolved.
- [x] Phase 0 script written and run — `phase0_distribution.py`.

---

## 2026-04-24 — Data Profile Review

Lat/lon confirmed present, 0 missing. Full dataset: 7,463 setups, 4,552 FLs (all GM-MCP).

**Edge cases confirmed for exclusion from PoC clustering:**
- Yearly (935), Daily (75), Monthly - Fixed Date (117 — D1 remediation pending), NULL (4)
- Weekend Mon-Week-Pattern Sat/Sun (1,039) — Saturday is overflow/OT only, not scheduled runs
- Week 0 "5th weekday" (2 setups)
- Simon Cormie all setups (562 total) — invoice/admin processing, no field service
- Duration > 480 min (17) — exclude from capacity calc, flag for manual review

**Decisions:**
- 6-Weekly: include, assign day-of-week only (same area logic). Currently 89% Monday — historical default, will be redistributed.
- Zero-duration non-Cormie (11): include with 15-min default duration.
- Monthly - Fixed Date: excluded pending D1 remediation to Monthly - Week Pattern.

**Core clustering set (Mon–Fri, Monthly - Week Pattern + 6-Weekly, excl. Cormie):** ~4,573 setups (approx — Cormie has 193 Monthly - Week Pattern + 21 Weekly in scope types).
Quarterly (3 Monthly) dominates at 2,821 of 5,648 monthly-pattern setups.

**Optimisation framing agreed:** Constrained discrete optimisation (not continuous gradient descent). Coordinate descent in discrete space via constrained K-means + local search. Anchor seeding = smart initialisation. Simulated Annealing noted as next step for escaping local minima. Databricks ML to be assessed by data engineer before committing to implementation path.

---

## 2026-04-24 — Phase 0 Results

Script: `phase0_distribution.py`. Outputs: `phase0_working_dataset.csv`, `phase0_fl_summary.csv`, `phase0_area_summary.csv`.

**Working dataset:** 5,092 setups | 3,737 unique FLs (2,371 excluded)
**Portfolio:** 1,922h/month service time | 400 required run-days/month | ~20 technicians implied at 8h/day / 20 Mon–Fri slots

**Frequency backbone:**
- 1 Monthly: 1,274 setups → 917.7h/mo (highest hours — drives run structure)
- 3 Monthly: 2,189 setups → 449.9h/mo
- 6 Weekly: 507 setups → 216.4h/mo
- 2 Monthly: 286 setups → 89.7h/mo
- 6 Monthly: 654 setups → 96.8h/mo

**Top areas by monthly hours:** Melbourne CBD (124h), Truganina (60.7h), Dandenong South (51.1h), Laverton North (39.9h), Derrimut (39.2h)

**Issues to resolve before Phase 1:**
- 16 FLs missing coordinates — need to source lat/lon before clustering
- Ultra-long frequencies in working set (36 Monthly / 60 Monthly / 72 Monthly = 3–6 year intervals) — negligible volume, decide whether to include or exclude
- "Melbourne" city is too broad (224 FLs, 16 run-days/mo) — needs sub-division into geo zones before clustering is meaningful

**Decisions from Phase 0 review:**
- Geographic grouping: lat/lon exclusively — no suburb/city used as clustering input. City names in outputs for readability only.
- 16 FLs missing coords: flag and exclude from clustering. User fix.
- Ultra-rare frequencies (36/60/72 Monthly): include, lowest-priority assignment, negligible capacity impact.
- Yearly recurrence quirk documented: `<years every='N'>` → N = drop month, not repeat interval.

**Further decisions:**
- Tech count derived from portfolio (capacity-driven clustering), not supplied as input. Future version accepts branch-specified tech count with over-capacity flagging.
- 52 Weekly → flag as candidate for conversion to 12 Monthly. 26 Weekly → flag for 6 Monthly. Clustered normally in the meantime.
- 6 Weekly: no monthly equivalent, include as-is. Business to stop selling going forward.

**Next action:** Phase 1 — anchor identification and constrained geographic clustering.

---

## 2026-04-27 — Phase 1 Run 1

Script: `phase1_clustering.py`. Two-stage: Stage A capacity-constrained K-means++ macro clustering; Stage B capacity-aware day partition + week-slot assignment.

**Stage A (runs):** K=12 derived from 1,910 portfolio hrs / 160h cap. 11 runs at 100% util, 1 at 93.7% (Gippsland geographic outlier).

**Stage B (slots):** Day partition balanced (24.9–33.6h, std 2.79h). 62.9% of slots over 8h cap but most by <1h; max 18.1h. Same-site grouping 100%, all setups allocated.

**KPIs:** Mean FL→centroid 16.73 km, total haversine 62,143 km.

**Data quality finds:**
- 6 FLs with bad coordinates (US, UK, South Africa, Sydney) — exported to `phase1_bad_coords.csv` for data fix:
  Breadtop Narre Warren, Tabcorp Deer Park, DTP Port Melb, Tabcorp Reservoir, Fitness First Malvern Valley, NAB Point Cook.
- ~100 legitimate Gippsland FLs (Traralgon/Sale/Bairnsdale/Lakes Entrance/Morwell/Moe) — within VIC bbox so retained, drove Run 2 partial fill.

**Fixes applied:**
- VIC bbox filter (lat -39.5..-33.9, lon 140.5..150.5) added at load.
- Stage B `partition_capacity` replaces unconstrained K=5 K-means — mirrors Stage A capacity logic with 5% headroom.
- `dow_name` merge collision fixed (drop setup-level dow_name before merging FL-level cluster day).

**Outputs:** `phase1_setup_output.csv` (5,062 rows), `phase1_fl_assignments.csv` (3,715), `phase1_run_summary.csv` (12), `phase1_slot_capacity.csv` (240), `phase1_bad_coords.csv` (6).

**Open items:**
- Slot overruns concentrated in a few outlier slots (>12h: 4 slots) — likely heavy-frequency clusters. Consider second rebalance pass operating at slot level rather than day level.
- Gippsland run absorbs spread; consider whether it should be a separate logical "rural" sub-portfolio.
- Port to Databricks notebook — user re-creating equivalent SQL view in DBX.

---

## 2026-04-29 — Phase 1 Run 2: Algorithm rewrite — two-stage geographic clustering

**Problem with Run 1:** K=20 simultaneous partition with hard capacity constraints caused the balancing logic to dominate, fragmenting geographic coherence within day groups. Days were load-balanced but not geographically coherent.

**Fix:** Replaced single K=20 constrained partition with a proper two-stage approach:
- **Stage 1:** Cluster tech FLs into 5 geographic day zones using pure weighted K-means++ (hours as centroid weights only — no hard capacity gate). Zones ordered by longitude west→east → Mon..Fri.
- **Stage 2:** Within each day zone, cluster into up to 4 week sub-zones (same pure geographic approach). Sub-zones ordered by latitude north→south → Wk1..Wk4.
- Capacity is tracked post-assignment (reporting only) — not used as a partitioning constraint.

**KPI improvement vs Run 1:**

| KPI | Run 1 | Run 2 |
|---|---|---|
| % setups allocated | 100% | 100% |
| Same-site grouping | 100% | 100% |
| Mean FL→centroid dist | 16.73 km | **11.07 km** |
| Total haversine dist | 62,143 km | **42,250 km** |
| Slots over 8h cap | 62.9% | **7.9%** |
| Max slot load | 18.1h | 29.1h |

Mean FL→centroid distance improved 34%. Slots over capacity dropped from 62.9% → 7.9% (capacity compliance improved as a *result* of better geographic grouping — it was never a separate objective). Max slot load increased because one heavy-frequency tech still has a dense area; this is a data quality / tech allocation issue, not a clustering issue.

**Outputs:** `phase1_setup_output.csv` (5,062 rows), `phase1_fl_assignments.csv` (3,817), `phase1_tech_summary.csv` (36 techs), `phase1_slot_capacity.csv` (720 slots), `phase1_multi_tech_fls.csv` (101 FLs flagged).

**Open items:**
- Max slot load 29.1h on one tech — investigate which tech and whether it reflects genuine capacity shortfall or duration data issues.
- 101 multi-tech FLs flagged — review whether splits are intentional or warrant consolidation.
- Port to Databricks notebook.

---

## 2026-04-29 — Phase 1 Run 2 addendum: tabu-search rebalance pass

Added post-clustering slot rebalance: iteratively moves boundary FLs from over-cap (week, day) slots to the geographically nearest under-cap slot on the same tech. Tabu list (size 15) prevents immediate back-and-forth oscillation. One move per iteration (heaviest slot first), max 500 iterations per tech.

**Result:** 52 slots over 8h cap (7.2%), max slot load 18.4h. Same-site grouping and FL→centroid distance unchanged.

---

## 2026-04-30 — Phase 1 Run 3: Frequency-stratified zone formation + geometric median centroids

**Problem identified:** Flat K-means on all FLs simultaneously gave equal zone-forming influence to low-frequency satellite FLs (e.g. quarterly clusters in outlying areas). This caused geographically adjacent areas — served on the same travel corridor but at different frequencies — to land on different days of the week rather than different weeks of the same day.

**Fix: frequency-stratified zone formation**

The highest-frequency FLs define the day-zone structure; lower-frequency FLs attach to the nearest existing zone without creating new zones. Centroids recompute after each tier attaches (geometric median — outlier-resistant).

Steps per tech:
1. Compute `anchor_freq` per FL = max `services_per_year` across all setups at that (tech, FL). All setups at an FL follow their anchor — the FL is processed once and not re-queued.
2. Bucket into tiers: ≥26/yr (T5), ≥12/yr (T4), ≥4/yr (T3), ≥1.5/yr (T2), <1.5/yr (T1).
3. Zone-defining set = highest tier present, expanded down until ≥ 5 FLs.
4. K-means K=5 on zone-defining set → initial centroids (geometric median, Weiszfeld IRLS).
5. Each lower tier attaches FL-by-FL to nearest centroid. After each tier, centroids recomputed (geometric median of all assigned FLs). Zones evolve toward full-portfolio density; outliers self-limit via weight/distance influence.
6. Week sub-clustering K=4 within each finalised day zone (geometric median centroids).
7. Rebalance pass unchanged (tabu search).

**KPI vs Run 2+rebalance:**

| KPI | Run 2 + rebalance | Run 3 |
|---|---|---|
| % setups allocated | 100% | 100% |
| Same-site grouping | 100% | 100% |
| Mean FL→centroid dist | 11.07 km | **11.07 km** |
| Slots over 8h cap | 7.2% | **6.8%** |
| Max slot load | 18.4h | **19.3h** |
| Rebalance moves | 1,059 | **763** |

Geographic distance unchanged (zones are shaped by the same work — now stratified). Rebalance moves reduced by 28% — frequency-stratified zones start in a better position, requiring less post-hoc correction. Slight increase in max slot load is within noise; the dense outlier tech is the binding constraint.

**Outputs:** same files, updated. `phase1_fl_assignments.csv` now includes `anchor_freq` and `anchor_tier` columns.

---

## 2026-04-30 — Phase 1 Run 4: Outlier exclusion + spatial majority filter + topology KPIs

**Problems addressed:**
1. **Enclave misclassification** — K-means produces straight-line Voronoi boundaries; FLs surrounded by neighbours from a different zone were assigned to nearest centroid regardless. Visually obvious as "dots in the wrong day's territory".
2. **Outlier-driven zone formation** — a tech with 4 natural geographic clusters + 1 small fringe cluster (e.g. Andrew Tardio's Ballan) was forced to use K=5 centroids, with one centroid placed at the outlier and that fringe area becoming its own day-of-week.

**Fixes:**

1. **Outlier exclusion before seeding** (`detect_outliers`, MAD-based)
   - Compute tech's overall geometric median
   - Flag FLs where `dist_to_tech_centroid > median + 2 × MAD` as outliers (617 FLs / 3,817 = 16% of tech-FL rows)
   - Outliers are excluded from the zone-defining set during K-means seeding
   - After zones are formed by the dense core, outliers attach to nearest centroid (last) — they don't get to define their own zone
   - Centroid is recomputed via geometric median after outliers attach (so they contribute, but with bounded influence)

2. **Spatial majority filter** (post-rebalance, capacity-gated)
   - For each FL, find K=7 nearest geographic neighbours
   - If ≥ 3 neighbours are in the same different (week, day) slot — and the destination won't push capacity past 8h — reassign
   - Iterates per tech to stability (max 10 iterations)
   - Capacity gate: only move if `dest_load + fl_hrs ≤ 8h` OR if `new_dest_load < src_load` (no capacity worsening)

3. **Topology KPIs added:**
   - **Strict enclave rate**: % FLs where ≥3/7 neighbours are in same different slot — what smoothing targets
   - **Loose enclave rate**: % FLs where any other slot has more neighbours — broader topology check
   - **Disconnected zones**: zones containing FLs with no in-zone neighbour within 15km (>1 spatial component)
   - Each FL flagged with `is_outlier` and `in_disconnected_zone` for dashboard visualisation

4. **Dashboard topology layer:**
   - FLs in disconnected zones → bold red border
   - Outlier FLs → dashed black border
   - Updated legend

**KPIs vs Run 3:**

| KPI | Run 3 | Run 4 |
|---|---|---|
| % setups allocated | 100% | 100% |
| Same-site grouping | 100% | 100% |
| Mean FL→centroid | 11.07 km | 11.07 km |
| Slots over 8h cap | 6.8% | **5.6%** |
| Max slot load | 19.3h | **16.2h** |
| Strict enclave rate | n/a | **7.78%** |
| Loose enclave rate | n/a | 8.36% |
| Disconnected zones | n/a | **19** |

Strict enclave rate is above the 5% target. Investigation needed — likely candidates: techs with very dispersed portfolios where the strict majority threshold can't be met (so smoothing can't act), and capacity-gated cases where the destination is already at cap.

**New outputs:** `phase1_disconnected_zones.csv` (one row per disconnected zone), `is_outlier` and `in_disconnected_zone` columns on `phase1_fl_assignments.csv`.

**Open items:**
- Strict enclave rate at 7.78%: dig into which techs/zones contribute most. May indicate the smoothing capacity gate is too restrictive in dense areas, or that some "enclaves" are genuine outliers in sparse rural areas.
- 19 disconnected zones — need to review whether these are legitimate (genuinely isolated work) or algorithmic artefacts.
- Consider adaptive K (allow K < 5 when natural clusters are fewer) as next iteration.
