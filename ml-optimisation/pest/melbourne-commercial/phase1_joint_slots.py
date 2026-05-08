"""
Phase 1 (v2) — Joint 20-Slot Local Search Clustering
BSO Grouping Model | Melbourne Commercial Pest (GM-MCP)
---------------------------------------------------------
Alternative to phase1_clustering.py. Same data prep and same initial seeding
(frequency-stratified two-stage K-means). The difference is the refinement
step:

  v1 (phase1_clustering.py):
    init → tabu capacity rebalance → spatial majority filter (3/7 threshold)
  v2 (this file):
    init → joint neighbour-majority local search across all 20 slots
         → tabu capacity rebalance (backstop only)

The joint local search uses the same neighbour-count metric as the enclave
KPI: for each FL, count how many of its 7 nearest neighbours are in each
candidate (week, day) slot. Move to the slot with the highest count. This
matches the failure mode the KPI is measuring (an FL surrounded by
neighbours from a different slot) and addresses boundary cases like
Essendon Fields → Monday that K-means centroid distance gets wrong.

Differences from v1 spatial majority filter:
  - No 3/7 minimum (uses plurality, allowing 4/7 > 3/7 boundary corrections)
  - Tabu memory (size 15) prevents oscillation under the looser threshold
  - Iterates to convergence rather than fixed 10 iterations

Capacity gate is preserved during search: the K=5 days × K=4 weeks balance
established at init is structural and non-negotiable. A move is allowed only
if destination doesn't exceed 8h cap, OR if it improves the maximum slot load
(when the source itself is over-cap).

Soft convergence: per tech, iterate until no FL moves in a full pass, capped
by JOINT_MAX_ITER. Per-iteration move counts logged to phase1js_convergence.csv
to study the diminishing-returns curve.

Inputs   : phase0_working_dataset.csv, phase0_fl_summary.csv
Outputs  : phase1js_setup_output.csv      — setup-level *New Date Pattern
           phase1js_fl_assignments.csv    — FL/tech-level (one row per (tech, FL))
           phase1js_tech_summary.csv      — per-tech stats
           phase1js_slot_capacity.csv     — per-{tech, week, day} load vs cap
           phase1js_convergence.csv       — per-tech per-iteration log
           phase1js_disconnected_zones.csv
"""

import io, os, sys
import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── Config ────────────────────────────────────────────────────────────────────

DIR              = os.path.dirname(os.path.abspath(__file__))
WORKING_CSV      = os.path.join(DIR, 'phase0_working_dataset.csv')
FL_CSV           = os.path.join(DIR, 'phase0_fl_summary.csv')

CAPACITY_PER_DAY_HRS = 8.0
DAYS                 = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
WEEKS                = [1, 2, 3, 4]
RANDOM_SEED          = 42
PREF_COL             = '*Preferred Resource'
UNASSIGNED_TOKENS    = {'', 'nan', 'None', 'NULL', '(unassigned)'}

# Outlier handling (initial seeding only — same as v1)
OUTLIER_MAD_MULTIPLIER = 2.0
DISCONNECTED_GAP_KM    = 15

# Joint local search
JOINT_K_NEIGHBORS = 7     # k for neighbour-majority count (matches enclave KPI)
JOINT_TABU_SIZE   = 15    # block FL from returning to a just-left slot for N moves
JOINT_MAX_ITER    = 500   # safety cap; soft-convergence stops when no moves

# Capacity rebalance backstop (same as v1)
MAX_REBALANCE_ITER = 500
TABU_SIZE          = 15

DOW_TO_NAME = {0:'Sunday', 1:'Monday', 2:'Tuesday', 3:'Wednesday',
               4:'Thursday', 5:'Friday', 6:'Saturday'}


# ── 1. Load + clean ───────────────────────────────────────────────────────────

fl_df    = pd.read_csv(FL_CSV)
setup_df = pd.read_csv(WORKING_CSV)

valid = fl_df['latitude'].notna() & fl_df['longitude'].notna()
dropped_no_coords = fl_df.loc[~valid, '%FL_id'].tolist()
fl_df = fl_df[valid].reset_index(drop=True).copy()

VIC_LAT = (-39.5, -33.9)
VIC_LON = (140.5, 150.5)
in_vic = (fl_df['latitude'].between(*VIC_LAT) & fl_df['longitude'].between(*VIC_LON))
bad_coords = fl_df.loc[~in_vic, ['%FL_id','FL_name','city','latitude','longitude']]
fl_df = fl_df[in_vic].reset_index(drop=True).copy()

dropped_fls = dropped_no_coords + bad_coords['%FL_id'].tolist()
setup_df = setup_df[~setup_df['%FL_id'].isin(dropped_fls)].reset_index(drop=True).copy()

print(f"FLs in clustering set    : {len(fl_df):,}")
print(f"FLs dropped (no coords)  : {len(dropped_no_coords)}")
print(f"FLs dropped (outside VIC): {len(bad_coords)}")
print(f"Setups in clustering     : {len(setup_df):,}")


# ── 2. Haversine ──────────────────────────────────────────────────────────────

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
    return 2 * R * np.arcsin(np.sqrt(a))


# ── 3. Setup-level prep ───────────────────────────────────────────────────────

num_rec = pd.to_numeric(setup_df['num_recurrences'], errors='coerce')
is_monthly = setup_df['%frequency_type'].str.contains('Monthly', na=False)
is_weekly  = setup_df['%frequency_type'].str.contains('Weekly',  na=False)
setup_df['services_per_year']  = np.where(
    is_monthly, 12.0 / num_rec,
    np.where(is_weekly, 52.0 / num_rec, np.nan))
setup_df['services_per_month'] = setup_df['services_per_year'] / 12.0

new_dur = pd.to_numeric(setup_df['~New Duration'].replace('', np.nan), errors='coerce')
cur_dur = pd.to_numeric(setup_df['Current Duration'], errors='coerce')
setup_df['effective_duration'] = new_dur.fillna(cur_dur)
setup_df.loc[setup_df['effective_duration'] == 0, 'effective_duration'] = 15
setup_df['monthly_contrib_mins'] = setup_df['effective_duration'] * setup_df['services_per_month']
setup_df['monthly_contrib_hrs']  = setup_df['monthly_contrib_mins'] / 60.0

setup_df['is_mwp']    = setup_df['%frequency_type'] == 'Monthly - Week Pattern'
setup_df['is_weekly'] = is_weekly

setup_df = setup_df.merge(
    fl_df[['%FL_id','latitude','longitude']], on='%FL_id', how='left', suffixes=('','_fl'))


# ── 4. Tech assignment ────────────────────────────────────────────────────────

setup_df[PREF_COL] = setup_df[PREF_COL].fillna('').astype(str).str.strip()
setup_df['tech_raw'] = setup_df[PREF_COL]
setup_df['is_unassigned'] = setup_df['tech_raw'].isin(UNASSIGNED_TOKENS)

n_unassigned_initial = int(setup_df['is_unassigned'].sum())
print(f"\n── Tech grouping ─────────────────────────────────────────────────────")
print(f"Setups with preferred resource : {(~setup_df['is_unassigned']).sum():,}")
print(f"Setups unassigned              : {n_unassigned_initial:,}")

assigned = setup_df[~setup_df['is_unassigned']].copy()
tech_centroids = (
    assigned.groupby('tech_raw')
    .apply(lambda g: pd.Series({
        'lat': np.average(g['latitude'], weights=np.maximum(g['monthly_contrib_hrs'], 0.001)),
        'lon': np.average(g['longitude'], weights=np.maximum(g['monthly_contrib_hrs'], 0.001)),
        'hrs': g['monthly_contrib_hrs'].sum(),
        'fls': g['%FL_id'].nunique(),
    }))
    .reset_index()
)
print(f"Distinct techs in assigned set : {len(tech_centroids):,}")

if n_unassigned_initial:
    tech_lat = tech_centroids['lat'].to_numpy()
    tech_lon = tech_centroids['lon'].to_numpy()
    tech_name_arr = tech_centroids['tech_raw'].to_numpy()
    una_idx = setup_df.index[setup_df['is_unassigned']]
    for idx in una_idx:
        lat = setup_df.at[idx, 'latitude']
        lon = setup_df.at[idx, 'longitude']
        if pd.isna(lat) or pd.isna(lon):
            continue
        d = haversine(np.full(len(tech_lat), lat), np.full(len(tech_lon), lon),
                      tech_lat, tech_lon)
        setup_df.at[idx, 'tech_raw'] = tech_name_arr[int(np.argmin(d))]
    print(f"Unassigned reassigned by geo   : {n_unassigned_initial:,}")

setup_df['tech'] = setup_df['tech_raw']


# ── 5. Multi-tech FL flagging (no reassignment) ──────────────────────────────

fl_techs = setup_df.groupby('%FL_id')['tech'].nunique()
multi_tech_fl_ids = fl_techs[fl_techs > 1].index.tolist()
print(f"\nFLs with setups under multiple techs (split kept, flagged): {len(multi_tech_fl_ids):,}")

if multi_tech_fl_ids:
    multi_rows = (
        setup_df[setup_df['%FL_id'].isin(multi_tech_fl_ids)]
        .groupby(['%FL_id','tech'])
        .agg(setups=('%booking_setup_id','count'),
             monthly_hrs=('monthly_contrib_hrs','sum'))
        .reset_index()
        .merge(fl_df[['%FL_id','FL_name','city']], on='%FL_id'))


# ── 6. Helpers (verbatim from v1) ─────────────────────────────────────────────

def kmeans_geographic(points, weights, k, rng, max_iter=50):
    n = len(points)
    if n == 0:
        return np.array([], dtype=int), np.zeros((k, 2))
    if n <= k:
        labels = np.arange(n) % k
        cents  = np.zeros((k, 2))
        for j in range(k):
            m = labels == j
            cents[j] = points[m].mean(axis=0) if m.any() else points.mean(axis=0)
        return labels, cents

    total_w = weights.sum()
    first = int(rng.choice(n, p=weights / total_w))
    seeds = [first]
    for _ in range(k - 1):
        min_d = np.full(n, np.inf)
        for s in seeds:
            d = np.sqrt(((points - points[s]) ** 2).sum(axis=1))
            min_d = np.minimum(min_d, d)
        prob = (min_d ** 2) * weights
        if prob.sum() == 0:
            remaining = [i for i in range(n) if i not in seeds]
            seeds.append(int(rng.choice(remaining)) if remaining else seeds[-1])
            continue
        prob /= prob.sum()
        seeds.append(int(rng.choice(n, p=prob)))
    while len(seeds) < k:
        seeds.append(seeds[-1])

    cents  = points[list(dict.fromkeys(seeds))[:k]].astype(float).copy()
    if len(cents) < k:
        cents = np.vstack([cents, np.tile(cents[-1], (k - len(cents), 1))])

    labels = np.zeros(n, dtype=int)
    for iteration in range(max_iter):
        dists  = np.sqrt(((points[:, None, :] - cents[None, :, :]) ** 2).sum(axis=2))
        new_labels = np.argmin(dists, axis=1)
        new_cents = np.zeros((k, 2))
        for j in range(k):
            m = new_labels == j
            if m.any():
                w = weights[m]
                new_cents[j] = (points[m] * w[:, None]).sum(axis=0) / max(w.sum(), 1e-9)
            else:
                new_cents[j] = cents[j]
        if np.array_equal(new_labels, labels) and np.allclose(cents, new_cents, atol=1e-9):
            break
        labels = new_labels
        cents  = new_cents
    return labels, cents


def geometric_median(points, weights, max_iter=30, tol=1e-7):
    if len(points) == 0:
        return np.zeros(2)
    if len(points) == 1:
        return points[0].astype(float).copy()
    w = np.maximum(weights, 1e-9)
    estimate = (points * (w / w.sum())[:, None]).sum(axis=0)
    for _ in range(max_iter):
        dists    = np.maximum(np.sqrt(((points - estimate) ** 2).sum(axis=1)), 1e-9)
        irls_w   = w / dists
        new_est  = (points * irls_w[:, None]).sum(axis=0) / irls_w.sum()
        if np.sqrt(((new_est - estimate) ** 2).sum()) < tol:
            break
        estimate = new_est
    return estimate


def freq_tier(spy):
    if spy >= 26:  return 5
    if spy >= 12:  return 4
    if spy >= 4:   return 3
    if spy >= 1.5: return 2
    return 1


def detect_outliers(distances, mad_multiplier=OUTLIER_MAD_MULTIPLIER):
    if len(distances) == 0:
        return np.array([], dtype=bool)
    med = float(np.median(distances))
    mad = float(np.median(np.abs(distances - med)))
    if mad == 0.0:
        return np.zeros(len(distances), dtype=bool)
    return distances > (med + mad_multiplier * mad)


def pairwise_haversine(pts):
    n = len(pts)
    d = np.zeros((n, n))
    if n < 2:
        return d
    lats = pts[:, 0]
    lons = pts[:, 1]
    for i in range(n):
        d[i, i+1:] = haversine(lats[i], lons[i], lats[i+1:], lons[i+1:])
        d[i+1:, i] = d[i, i+1:]
    np.fill_diagonal(d, np.inf)
    return d


def count_zone_components(pts, gap_km=DISCONNECTED_GAP_KM):
    n = len(pts)
    if n <= 1:
        return n
    visited = [False] * n
    comps   = 0
    for start in range(n):
        if visited[start]:
            continue
        comps += 1
        stack = [start]
        while stack:
            i = stack.pop()
            if visited[i]:
                continue
            visited[i] = True
            for j in range(n):
                if not visited[j]:
                    if haversine(pts[i, 0], pts[i, 1], pts[j, 0], pts[j, 1]) <= gap_km:
                        stack.append(j)
    return comps


# ── 7. Initial seeding (frequency-stratified, identical to v1) ────────────────

print(f"\n── Initial seeding (same as v1) ─────────────────────────────────────")

rng = np.random.default_rng(RANDOM_SEED)

tech_fl = (
    setup_df.groupby(['tech', '%FL_id'])
    .agg(monthly_hrs=('monthly_contrib_hrs', 'sum'),
         setups=('%booking_setup_id', 'count'),
         latitude=('latitude', 'first'),
         longitude=('longitude', 'first'))
    .reset_index()
    .merge(fl_df[['%FL_id', 'FL_name', 'city']], on='%FL_id', how='left'))

tech_fl['day']        = ''
tech_fl['week']       = 0
tech_fl['is_outlier'] = False

anchor_freq_df = (
    setup_df.groupby(['tech', '%FL_id'])['services_per_year']
    .max()
    .reset_index()
    .rename(columns={'services_per_year': 'anchor_freq'})
)
tech_fl = tech_fl.merge(anchor_freq_df, on=['tech', '%FL_id'], how='left')
tech_fl['anchor_freq'] = pd.to_numeric(tech_fl['anchor_freq'], errors='coerce').fillna(1.0)
tech_fl['anchor_tier'] = tech_fl['anchor_freq'].apply(freq_tier)


for tech_name in sorted(tech_fl['tech'].unique()):
    sub   = tech_fl[tech_fl['tech'] == tech_name].copy()
    n     = len(sub)
    if n == 0:
        continue
    pts   = sub[['latitude', 'longitude']].to_numpy()
    w     = np.maximum(sub['monthly_hrs'].to_numpy(), 0.001)
    tiers = sub['anchor_tier'].to_numpy()
    k_days = min(5, n)

    if n >= max(5, k_days + 1):
        tech_cent = geometric_median(pts, w)
        dist_tech = haversine(pts[:, 0], pts[:, 1], tech_cent[0], tech_cent[1])
        outlier_mask = detect_outliers(dist_tech)
    else:
        outlier_mask = np.zeros(n, dtype=bool)

    top_tier  = int(tiers.max())
    zone_mask = (tiers >= top_tier) & (~outlier_mask)
    while zone_mask.sum() < k_days and top_tier > 1:
        top_tier -= 1
        zone_mask = (tiers >= top_tier) & (~outlier_mask)
    if zone_mask.sum() < k_days:
        zone_mask = tiers >= top_tier
    zone_pts = pts[zone_mask]
    zone_w   = w[zone_mask]

    day_labels_zone, day_cents = kmeans_geographic(zone_pts, zone_w, k_days, rng)
    for j in range(k_days):
        m = day_labels_zone == j
        if m.any():
            day_cents[j] = geometric_median(zone_pts[m], zone_w[m])

    day_labels_all = np.full(n, -1, dtype=int)
    for arr_i, orig_i in enumerate(np.where(zone_mask)[0]):
        day_labels_all[orig_i] = int(day_labels_zone[arr_i])

    for tier in sorted({int(t) for t in tiers if t < top_tier}, reverse=True):
        tier_mask = (tiers == tier) & (day_labels_all == -1) & (~outlier_mask)
        if not tier_mask.any():
            continue
        for i in np.where(tier_mask)[0]:
            d = np.array([haversine(pts[i, 0], pts[i, 1],
                                    day_cents[j, 0], day_cents[j, 1])
                          for j in range(k_days)])
            day_labels_all[i] = int(np.argmin(d))
        for j in range(k_days):
            m = day_labels_all == j
            if m.sum() > 0:
                day_cents[j] = geometric_median(pts[m], w[m])

    outlier_unassigned = outlier_mask & (day_labels_all == -1)
    for i in np.where(outlier_unassigned)[0]:
        d = np.array([haversine(pts[i, 0], pts[i, 1],
                                day_cents[j, 0], day_cents[j, 1])
                      for j in range(k_days)])
        day_labels_all[i] = int(np.argmin(d))
    for j in range(k_days):
        m = day_labels_all == j
        if m.sum() > 0:
            day_cents[j] = geometric_median(pts[m], w[m])

    for i in np.where(day_labels_all == -1)[0]:
        d = np.array([haversine(pts[i, 0], pts[i, 1],
                                day_cents[j, 0], day_cents[j, 1])
                      for j in range(k_days)])
        day_labels_all[i] = int(np.argmin(d))

    day_lon_order  = np.argsort(day_cents[:, 1])
    cluster_to_day = {int(day_lon_order[i]): DAYS[i] for i in range(k_days)}
    sub['day'] = [cluster_to_day[int(lbl)] for lbl in day_labels_all]

    sub['week'] = 1
    for day_name in sub['day'].unique():
        day_mask = sub['day'] == day_name
        day_idx  = sub.index[day_mask]
        d_pts    = pts[day_mask.values]
        d_w      = w[day_mask.values]
        n_day    = d_pts.shape[0]

        k_weeks = min(4, n_day)
        if k_weeks <= 1:
            sub.loc[day_idx, 'week'] = 1
            continue

        wk_labels, wk_cents = kmeans_geographic(d_pts, d_w, k_weeks, rng)
        for j in range(k_weeks):
            m = wk_labels == j
            if m.any():
                wk_cents[j] = geometric_median(d_pts[m], d_w[m])

        wk_lat_order    = np.argsort(-wk_cents[:, 0])
        cluster_to_week = {int(wk_lat_order[i]): i + 1 for i in range(k_weeks)}
        for arr_i, df_idx in enumerate(day_idx):
            sub.at[df_idx, 'week'] = cluster_to_week[int(wk_labels[arr_i])]

    tech_fl.loc[sub.index, 'day']  = sub['day'].values
    tech_fl.loc[sub.index, 'week'] = sub['week'].values
    tech_fl.loc[sub.index, 'is_outlier'] = outlier_mask

print(f"Tech-FL rows seeded         : {len(tech_fl):,}")
print(f"Outlier FLs flagged         : {int(tech_fl['is_outlier'].sum()):,}")


# ── 8. Joint local search (neighbour-majority + tabu + capacity gate) ────────
#
# For each FL i:
#   - count neighbours per slot among its JOINT_K_NEIGHBORS nearest other FLs
#   - target slot = slot with strictly highest count (tie-break stays in current)
#   - move only if:
#       * target ≠ current
#       * (i, current_slot) not in tabu (prevents A→B→A oscillation)
#       * dst_load + fl_hrs ≤ 8h, OR new dst_load < src_load (improves max)
#   - on move, append (i, prev_slot) to tabu; pop oldest if over JOINT_TABU_SIZE
#
# Iterates per-tech until no moves in a full pass or JOINT_MAX_ITER hit.
# Same metric as the enclave KPI — search optimises directly for what the KPI
# measures. Capacity gate preserves the K=5×K=4 partition balance from init.

print(f"\n── Joint 20-slot local search (neighbour-majority + tabu) ───────────")
print(f"  k_neighbors = {JOINT_K_NEIGHBORS}, tabu_size = {JOINT_TABU_SIZE}, "
      f"max_iter = {JOINT_MAX_ITER}, cap = {CAPACITY_PER_DAY_HRS}h")

ALL_SLOTS = [(w, d) for w in WEEKS for d in DAYS]
convergence_log = []

for tech_name in sorted(tech_fl['tech'].unique()):
    tech_idx = tech_fl.index[tech_fl['tech'] == tech_name]
    n = len(tech_idx)
    if n < JOINT_K_NEIGHBORS + 1:
        continue

    pts    = tech_fl.loc[tech_idx, ['latitude', 'longitude']].to_numpy()
    fl_hrs = tech_fl.loc[tech_idx, 'monthly_hrs'].to_numpy()
    pdist  = pairwise_haversine(pts)
    nn_idx = np.argsort(pdist, axis=1)[:, :JOINT_K_NEIGHBORS]

    weeks_arr = tech_fl.loc[tech_idx, 'week'].astype(int).to_numpy()
    days_arr  = tech_fl.loc[tech_idx, 'day'].to_numpy()
    slot_of   = [(int(weeks_arr[i]), days_arr[i]) for i in range(n)]

    tabu = []   # list of (fl_local_idx, slot_just_left)
    tech_total_moves = 0

    for it in range(JOINT_MAX_ITER):
        slot_load = {}
        for i, s in enumerate(slot_of):
            slot_load[s] = slot_load.get(s, 0.0) + fl_hrs[i]

        tabu_set = set(tabu)
        moves    = 0

        for i in range(n):
            cur = slot_of[i]
            counts = {}
            for j in nn_idx[i]:
                s = slot_of[j]
                counts[s] = counts.get(s, 0) + 1

            cur_count = counts.get(cur, 0)
            maj_slot  = cur
            maj_count = cur_count
            for s, c in counts.items():
                if c > maj_count:
                    maj_count = c
                    maj_slot  = s

            if maj_slot == cur:
                continue                                # no move
            if (i, maj_slot) in tabu_set:
                continue                                # tabu: don't return

            src_load     = slot_load.get(cur, 0.0)
            dst_load     = slot_load.get(maj_slot, 0.0)
            new_dst_load = dst_load + fl_hrs[i]
            if new_dst_load > CAPACITY_PER_DAY_HRS and new_dst_load >= src_load:
                continue                                # capacity gate

            slot_of[i]          = maj_slot
            slot_load[cur]      = max(0.0, src_load - fl_hrs[i])
            slot_load[maj_slot] = new_dst_load

            tabu.append((i, cur))
            if len(tabu) > JOINT_TABU_SIZE:
                tabu.pop(0)
            moves += 1

        convergence_log.append({
            'tech'  : tech_name,
            'iter'  : it + 1,
            'moves' : moves,
            'fls'   : n,
        })
        tech_total_moves += moves
        if moves == 0:
            break

    # Write back
    for arr_i, df_idx in enumerate(tech_idx):
        tech_fl.at[df_idx, 'week'] = slot_of[arr_i][0]
        tech_fl.at[df_idx, 'day']  = slot_of[arr_i][1]

    if tech_total_moves > 0:
        last_iter = max(r['iter'] for r in convergence_log if r['tech'] == tech_name)
        print(f"  {tech_name:<35} {tech_total_moves:>5} moves over {last_iter} iter")

convergence_df = pd.DataFrame(convergence_log)
convergence_df.to_csv(os.path.join(DIR, 'phase1js_convergence.csv'), index=False)
total_joint_moves = int(convergence_df['moves'].sum()) if len(convergence_df) else 0
print(f"Total joint search moves     : {total_joint_moves:,}")


# ── 9. Tabu capacity rebalance (backstop only) ───────────────────────────────

def rebalance_pass(tech_fl, label='Capacity rebalance pass', verbose=True):
    total = 0
    if verbose:
        print(f"\n── {label} ──────────────────────────────────────")
    for tech_name in sorted(tech_fl['tech'].unique()):
        tech_idx = tech_fl.index[tech_fl['tech'] == tech_name]
        if len(tech_idx) < 2:
            continue
        tech_moves = 0
        tabu = []
        for _iter in range(MAX_REBALANCE_ITER):
            sub       = tech_fl.loc[tech_idx]
            slot_load = sub.groupby(['week', 'day'])['monthly_hrs'].sum().to_dict()
            over      = {k: v for k, v in slot_load.items() if v > CAPACITY_PER_DAY_HRS}
            if not over:
                break
            src_wk, src_day = max(over, key=over.get)
            src_load = slot_load[(src_wk, src_day)]
            src_fls  = sub[(sub['week'] == src_wk) & (sub['day'] == src_day)]
            src_w   = np.maximum(src_fls['monthly_hrs'].to_numpy(), 0.001)
            src_lat = float(np.average(src_fls['latitude'].to_numpy(),  weights=src_w))
            src_lon = float(np.average(src_fls['longitude'].to_numpy(), weights=src_w))
            dest_info = {}
            for (dst_wk, dst_day), dst_load in slot_load.items():
                if (dst_wk, dst_day) == (src_wk, src_day):
                    continue
                dst_fls = sub[(sub['week'] == dst_wk) & (sub['day'] == dst_day)]
                if dst_fls.empty:
                    continue
                dst_w = np.maximum(dst_fls['monthly_hrs'].to_numpy(), 0.001)
                dest_info[(dst_wk, dst_day)] = (
                    float(np.average(dst_fls['latitude'].to_numpy(),  weights=dst_w)),
                    float(np.average(dst_fls['longitude'].to_numpy(), weights=dst_w)),
                    dst_load,
                )
            tabu_set = {(t[0], t[1], t[2]) for t in tabu}
            best_fl_idx    = None
            best_dest_slot = None
            best_geo_gain  = -np.inf
            for fl_idx in src_fls.index:
                fl_hrs = tech_fl.at[fl_idx, 'monthly_hrs']
                fl_lat = tech_fl.at[fl_idx, 'latitude']
                fl_lon = tech_fl.at[fl_idx, 'longitude']
                d_src  = haversine(fl_lat, fl_lon, src_lat, src_lon)
                for (dst_wk, dst_day), (dst_lat, dst_lon, dst_load) in dest_info.items():
                    if (fl_idx, dst_wk, dst_day) in tabu_set:
                        continue
                    if dst_load + fl_hrs >= src_load:
                        continue
                    d_dst    = haversine(fl_lat, fl_lon, dst_lat, dst_lon)
                    geo_gain = d_src - d_dst
                    if geo_gain > best_geo_gain:
                        best_geo_gain  = geo_gain
                        best_fl_idx    = fl_idx
                        best_dest_slot = (dst_wk, dst_day)
            if best_fl_idx is None:
                break
            prev_wk  = int(tech_fl.at[best_fl_idx, 'week'])
            prev_day = tech_fl.at[best_fl_idx, 'day']
            dst_wk, dst_day = best_dest_slot
            tech_fl.at[best_fl_idx, 'week'] = dst_wk
            tech_fl.at[best_fl_idx, 'day']  = dst_day
            tabu.append((best_fl_idx, prev_wk, prev_day))
            if len(tabu) > TABU_SIZE:
                tabu.pop(0)
            tech_moves += 1
            total      += 1
        if verbose and tech_moves > 0:
            print(f"  {tech_name:<35} {tech_moves} moves")
    if verbose:
        print(f"Total FL moves              : {total:,}")
    return total


rebalance_pass(tech_fl, label='Capacity rebalance backstop')


# ── 10. Topology diagnostics ─────────────────────────────────────────────────

tech_fl['in_disconnected_zone'] = False
disconnected_rows = []
for tech_name in tech_fl['tech'].unique():
    sub_t = tech_fl[tech_fl['tech'] == tech_name]
    for (wk, day), g in sub_t.groupby(['week', 'day']):
        if len(g) <= 1:
            continue
        pts_z = g[['latitude', 'longitude']].to_numpy()
        comps = count_zone_components(pts_z, gap_km=DISCONNECTED_GAP_KM)
        if comps > 1:
            tech_fl.loc[g.index, 'in_disconnected_zone'] = True
            disconnected_rows.append({
                'tech'       : tech_name,
                'week'       : int(wk),
                'day'        : day,
                'fls'        : int(len(g)),
                'components' : int(comps),
                'monthly_hrs': float(g['monthly_hrs'].sum()),
            })
disconnected_df = pd.DataFrame(disconnected_rows)
if len(disconnected_df):
    disconnected_df.to_csv(os.path.join(DIR, 'phase1js_disconnected_zones.csv'), index=False)


# ── 11. Apply (day, week) back to setups ─────────────────────────────────────

setup_df = setup_df.merge(
    tech_fl[['tech','%FL_id','day','week']], on=['tech','%FL_id'], how='left'
)


def compose_pattern(r):
    if r['is_weekly']:
        return f"Every {r['day']}" if r['day'] else ''
    if r['is_mwp'] and r['week'] and r['day']:
        return f"{int(r['week'])}-{r['day']}"
    return ''


setup_df['*New Date Pattern'] = setup_df.apply(compose_pattern, axis=1)


# ── 12. Slot capacity tracking ───────────────────────────────────────────────

slot_rows = []
for tech_name, grp in setup_df.groupby('tech'):
    for w_ in WEEKS:
        for d_ in DAYS:
            mwp_load = grp[(grp['is_mwp']) & (grp['week']==w_) & (grp['day']==d_)]['monthly_contrib_mins'].sum()
            wkly_load = grp[(grp['is_weekly']) & (grp['day']==d_)]['monthly_contrib_mins'].sum() / 4.0
            load_hrs = (mwp_load + wkly_load) / 60.0
            slot_rows.append({'tech':tech_name,'week':w_,'day':d_,
                              'load_hrs':round(load_hrs,2),
                              'capacity_hrs':CAPACITY_PER_DAY_HRS,
                              'over_capacity': load_hrs > CAPACITY_PER_DAY_HRS})
slot_df = pd.DataFrame(slot_rows)
over = slot_df['over_capacity'].sum()
print(f"\n── Slot capacity ────────────────────────────────────────────────────")
print(f"Total slots (techs × 4 wk × 5 day): {len(slot_df):,}")
print(f"Slots over 8h cap                : {over:,} ({over/len(slot_df)*100:.1f}%)")
print(f"Mean / max slot load             : {slot_df['load_hrs'].mean():.2f}h / "
      f"{slot_df['load_hrs'].max():.2f}h")


# ── 13. Tech summary ─────────────────────────────────────────────────────────

tech_summary_rows = []
for tech_name in sorted(tech_fl['tech'].unique()):
    sub = tech_fl[tech_fl['tech'] == tech_name]
    tech_summary_rows.append({
        'tech'       : tech_name,
        'fls'        : int(len(sub)),
        'monthly_hrs': float(sub['monthly_hrs'].sum()),
        'days_used'  : int(sub['day'].nunique()),
        'weeks_used' : int(sub['week'].nunique()),
        'outliers'   : int(sub['is_outlier'].sum()),
    })
tech_summary = pd.DataFrame(tech_summary_rows).sort_values('monthly_hrs', ascending=False)


# ── 14. Save outputs ─────────────────────────────────────────────────────────

setup_out_cols = [c for c in setup_df.columns if not c.endswith('_fl')]
setup_df[setup_out_cols].to_csv(os.path.join(DIR, 'phase1js_setup_output.csv'), index=False)
tech_fl.to_csv(os.path.join(DIR, 'phase1js_fl_assignments.csv'), index=False)
tech_summary.to_csv(os.path.join(DIR, 'phase1js_tech_summary.csv'), index=False)
slot_df.to_csv(os.path.join(DIR, 'phase1js_slot_capacity.csv'), index=False)

print(f"\n── Saved ────────────────────────────────────────────────────────────")
print(f"  phase1js_setup_output.csv      ({len(setup_df):,} rows)")
print(f"  phase1js_fl_assignments.csv    ({len(tech_fl):,} rows)")
print(f"  phase1js_tech_summary.csv      ({len(tech_summary):,} rows)")
print(f"  phase1js_slot_capacity.csv     ({len(slot_df):,} rows)")
print(f"  phase1js_convergence.csv       ({len(convergence_df):,} rows)")
if len(disconnected_df):
    print(f"  phase1js_disconnected_zones.csv ({len(disconnected_df):,} rows)")


# ── 15. KPIs (same definitions as v1) ────────────────────────────────────────

allocated = setup_df['*New Date Pattern'].astype(str).str.len() > 0
pct = allocated.mean() * 100

sf = setup_df.groupby(['tech','%FL_id']).agg(
    days=('day', lambda s: s.nunique()),
    weeks=('week', lambda s: s.nunique())).reset_index()
same_site = ((sf['days']==1) & (sf['weeks']<=1)).mean() * 100

fl_centroid = tech_fl.groupby('tech').agg(
    clat=('latitude', lambda s: np.average(s, weights=np.maximum(tech_fl.loc[s.index,'monthly_hrs'],0.001))),
    clon=('longitude', lambda s: np.average(s, weights=np.maximum(tech_fl.loc[s.index,'monthly_hrs'],0.001))),
).reset_index()
tf2 = tech_fl.merge(fl_centroid, on='tech')
tf2['d_km'] = haversine(tf2['latitude'], tf2['longitude'], tf2['clat'], tf2['clon'])

ENCLAVE_K = 7
ENCLAVE_MIN = 3
enclave_strict = 0
enclave_loose  = 0
enclave_total  = 0
for tech_name in tech_fl['tech'].unique():
    sub_t = tech_fl[tech_fl['tech'] == tech_name]
    n_t = len(sub_t)
    if n_t < ENCLAVE_K + 1:
        continue
    pts_t = sub_t[['latitude', 'longitude']].to_numpy()
    slots = list(zip(sub_t['week'].astype(int).to_numpy(),
                     sub_t['day'].to_numpy()))
    dist  = pairwise_haversine(pts_t)
    nn    = np.argsort(dist, axis=1)[:, :ENCLAVE_K]
    for i in range(n_t):
        cur = slots[i]
        counts = {}
        for j in nn[i]:
            counts[slots[j]] = counts.get(slots[j], 0) + 1
        maj_slot, maj_count = max(counts.items(), key=lambda x: x[1])
        cur_count = counts.get(cur, 0)
        enclave_total += 1
        if maj_count > cur_count and maj_slot != cur:
            enclave_loose += 1
        if maj_count >= ENCLAVE_MIN and maj_slot != cur:
            enclave_strict += 1
strict_rate = (enclave_strict / enclave_total * 100) if enclave_total else 0.0
loose_rate  = (enclave_loose  / enclave_total * 100) if enclave_total else 0.0

print(f"\n── KPIs ─────────────────────────────────────────────────────────────")
print(f"  % setups allocated           : {pct:.2f}%")
print(f"  Same-site (tech,FL) grouping : {same_site:.2f}%")
print(f"  Mean FL→tech-centroid dist   : {tf2['d_km'].mean():.2f} km")
print(f"  Total FL→tech-centroid dist  : {tf2['d_km'].sum():,.1f} km")
print(f"  Enclave rate strict (≥{ENCLAVE_MIN}/{ENCLAVE_K})  : {strict_rate:.2f}% "
      f"({enclave_strict:,}/{enclave_total:,})  ← v1 was 7.78%")
print(f"  Enclave rate loose (plurality): {loose_rate:.2f}% "
      f"({enclave_loose:,}/{enclave_total:,})")
print(f"  Disconnected zones (>{DISCONNECTED_GAP_KM}km gap)  : {len(disconnected_df):,}  ← v1 was 19")


# ── 16. Convergence summary (diminishing-returns curve) ──────────────────────

if len(convergence_df):
    print(f"\n── Convergence (aggregate across techs) ─────────────────────────────")
    agg = convergence_df.groupby('iter').agg(
        moves      =('moves', 'sum'),
        techs_active=('moves', lambda s: int((s > 0).sum())),
    ).reset_index()
    print(f"  iter  total_moves  techs_still_moving")
    for _, r in agg.head(20).iterrows():
        print(f"  {int(r['iter']):>4}  {int(r['moves']):>11,}  {int(r['techs_active']):>3}")
    if len(agg) > 20:
        print(f"  ... ({len(agg) - 20} more rows in phase1js_convergence.csv)")
    max_iter_used = int(convergence_df['iter'].max())
    print(f"\n  Max iterations used by any tech: {max_iter_used}")
