"""
Phase 1 — Per-Tech Day/Week Clustering
BSO Grouping Model | Melbourne Commercial Pest (GM-MCP)
---------------------------------------------------------
Treats existing *Preferred Resource as the fixed tech grouping (PoC scope —
algorithmic tech allocation reserved for datasets without preferred resource).

Two-stage geographic clustering per tech:
  Stage 1: Cluster FLs into 5 day-of-week zones using pure geographic K-means
           (monthly hours as centroid weights only — no hard capacity gate).
           Zones ordered by longitude west→east = Mon..Fri.
  Stage 2: Within each day zone, cluster FLs into up to 4 week-of-month groups
           using the same pure geographic approach.
           Sub-zones ordered by latitude north→south = Wk1..Wk4.
  Compose: {week}-{day} per FL, applied to all setups at that (tech, FL).

Geography drives structure at both stages. Capacity is tracked and reported
after assignment (see slot_capacity output) but is NOT used as a hard
partitioning constraint — forcing balance at assignment time fragments
geographic coherence.

FL handling:
  - FLs with setups under multiple techs: NOT reassigned. Each setup keeps its
    own preferred-resource grouping (splits may be intentional). Flagged.
  - Unassigned setups: assigned to geographically nearest tech centroid.

6-Weekly setups: day-of-week only ("Every {DayName}", no week number).

Input   : phase0_working_dataset.csv, phase0_fl_summary.csv
Outputs : phase1_setup_output.csv       — setup-level *New Date Pattern
          phase1_fl_assignments.csv     — FL/tech-level (one row per (tech, FL))
          phase1_tech_summary.csv       — per-tech stats
          phase1_slot_capacity.csv      — per-{tech, week, day} load vs cap
          phase1_multi_tech_fls.csv     — FLs split across techs (for review)
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

# Topology / outlier handling
OUTLIER_MAD_MULTIPLIER = 2.0   # outlier if dist_to_tech_centroid > median + 2×MAD
ENCLAVE_K_NEIGHBORS    = 7     # neighbours considered for spatial majority filter
ENCLAVE_MIN_MAJORITY   = 3     # require ≥ this many of K neighbours in dominant
                                # slot before reassigning (3/7 ≈ 43%) — strict
                                # enough to avoid touching legit boundary FLs but
                                # permissive enough to clear true enclaves
ENCLAVE_MAX_ITER       = 10    # iterations of enclave smoothing per tech
DISCONNECTED_GAP_KM    = 15    # zone is "disconnected" if any FL has no same-zone
                                # neighbour within this distance

DOW_TO_NAME = {0:'Sunday', 1:'Monday', 2:'Tuesday', 3:'Wednesday',
               4:'Thursday', 5:'Friday', 6:'Saturday'}


# ── 1. Load + clean ───────────────────────────────────────────────────────────

fl_df    = pd.read_csv(FL_CSV)
setup_df = pd.read_csv(WORKING_CSV)

# Exclude FLs missing coordinates
valid = fl_df['latitude'].notna() & fl_df['longitude'].notna()
dropped_no_coords = fl_df.loc[~valid, '%FL_id'].tolist()
fl_df = fl_df[valid].reset_index(drop=True).copy()

# Victoria bbox sanity check
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
if len(bad_coords):
    bad_coords.to_csv(os.path.join(DIR, 'phase1_bad_coords.csv'), index=False)
print(f"Setups in clustering     : {len(setup_df):,}")


# ── 2. Haversine ──────────────────────────────────────────────────────────────

def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
    return 2 * R * np.arcsin(np.sqrt(a))


# ── 3. Setup-level prep: services_per_year, durations, monthly contrib ────────

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

# Coords from fl_df onto setup_df
setup_df = setup_df.merge(
    fl_df[['%FL_id','latitude','longitude']], on='%FL_id', how='left', suffixes=('','_fl'))


# ── 4. Determine tech per setup ───────────────────────────────────────────────

setup_df[PREF_COL] = setup_df[PREF_COL].fillna('').astype(str).str.strip()
setup_df['tech_raw'] = setup_df[PREF_COL]
setup_df['is_unassigned'] = setup_df['tech_raw'].isin(UNASSIGNED_TOKENS)

n_unassigned_initial = int(setup_df['is_unassigned'].sum())
print(f"\n── Tech grouping ─────────────────────────────────────────────────────")
print(f"Setups with preferred resource : {(~setup_df['is_unassigned']).sum():,}")
print(f"Setups unassigned              : {n_unassigned_initial:,}")

# Build tech centroids from assigned setups only
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

# Assign each unassigned setup to nearest tech by haversine to that tech's centroid
if n_unassigned_initial:
    tech_lat = tech_centroids['lat'].to_numpy()
    tech_lon = tech_centroids['lon'].to_numpy()
    tech_name = tech_centroids['tech_raw'].to_numpy()
    una_idx = setup_df.index[setup_df['is_unassigned']]
    for idx in una_idx:
        lat = setup_df.at[idx, 'latitude']
        lon = setup_df.at[idx, 'longitude']
        if pd.isna(lat) or pd.isna(lon):
            continue
        d = haversine(np.full(len(tech_lat), lat), np.full(len(tech_lon), lon),
                      tech_lat, tech_lon)
        setup_df.at[idx, 'tech_raw'] = tech_name[int(np.argmin(d))]
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
    multi_rows.to_csv(os.path.join(DIR, 'phase1_multi_tech_fls.csv'), index=False)


# ── 6. K-means helper (pure geographic, hours-weighted centroids) ─────────────

def kmeans_geographic(points, weights, k, rng, max_iter=50):
    """Pure geographic weighted K-means (K-means++ seed).
    Hours used only as centroid weights — no capacity gate.
    Geographic distance is the sole partitioning criterion."""
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

    # K-means++ weighted seed
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
        # Assign each point to nearest centroid
        dists  = np.sqrt(((points[:, None, :] - cents[None, :, :]) ** 2).sum(axis=2))
        new_labels = np.argmin(dists, axis=1)

        # Weighted centroid update
        new_cents = np.zeros((k, 2))
        for j in range(k):
            m = new_labels == j
            if m.any():
                w = weights[m]
                new_cents[j] = (points[m] * w[:, None]).sum(axis=0) / max(w.sum(), 1e-9)
            else:
                new_cents[j] = cents[j]   # dead cluster — keep centroid in place

        if np.array_equal(new_labels, labels) and np.allclose(cents, new_cents, atol=1e-9):
            break
        labels = new_labels
        cents  = new_cents

    return labels, cents


def geometric_median(points, weights, max_iter=30, tol=1e-7):
    """Weiszfeld geometric median: minimises sum(w_i * dist(x, p_i)).
    Outlier-robust — a distant FL contributes weight/distance, so the further
    it is the less it steers the centroid, unlike the squared-distance mean."""
    if len(points) == 0:
        return np.zeros(2)
    if len(points) == 1:
        return points[0].astype(float).copy()
    w = np.maximum(weights, 1e-9)
    estimate = (points * (w / w.sum())[:, None]).sum(axis=0)   # weighted mean start
    for _ in range(max_iter):
        dists    = np.maximum(np.sqrt(((points - estimate) ** 2).sum(axis=1)), 1e-9)
        irls_w   = w / dists
        new_est  = (points * irls_w[:, None]).sum(axis=0) / irls_w.sum()
        if np.sqrt(((new_est - estimate) ** 2).sum()) < tol:
            break
        estimate = new_est
    return estimate


def freq_tier(spy):
    """Map services_per_year to a priority tier (5=most frequent, 1=least)."""
    if spy >= 26:  return 5   # weekly / bi-weekly
    if spy >= 12:  return 4   # monthly
    if spy >= 4:   return 3   # 2-monthly / quarterly
    if spy >= 1.5: return 2   # 6-monthly
    return 1                   # yearly


def detect_outliers(distances, mad_multiplier=OUTLIER_MAD_MULTIPLIER):
    """Robust MAD-based outlier flag: True where distance > median + k×MAD.
    Adapts to each tech's portfolio spread — wide-territory techs aren't
    over-flagged, tight-territory techs aren't under-flagged."""
    if len(distances) == 0:
        return np.array([], dtype=bool)
    med = float(np.median(distances))
    mad = float(np.median(np.abs(distances - med)))
    if mad == 0.0:
        return np.zeros(len(distances), dtype=bool)
    return distances > (med + mad_multiplier * mad)


def pairwise_haversine(pts):
    """Symmetric n×n haversine matrix; diagonal = +inf for nearest-neighbour use."""
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
    """Number of connected components in a zone, treating two FLs as connected
    if their haversine distance ≤ gap_km. >1 → zone is spatially disconnected."""
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


# ── 7. Per-tech: frequency-stratified zone formation + week sub-clustering ─────
#
# Zone formation (day-of-week):
#   1. Each FL's anchor_freq = max services_per_year across its setups (for this
#      tech). This determines its tier. All setups at an FL follow their anchor —
#      the FL is processed once and pinned; lower-frequency setups at the same FL
#      are not re-queued in later tiers.
#   2. The zone-defining set = FLs at the highest tier present for this tech
#      (expanded down if needed to reach ≥ k_days FLs). These shape the day zones.
#   3. K-means K=5 on the zone-defining set → initial centroids (geometric median).
#   4. Each lower tier attaches FL-by-FL to the nearest centroid. After each tier
#      attaches, centroids are recomputed (geometric median of all FLs now in each
#      zone). Zones shift toward full-portfolio density but outliers self-limit via
#      the weight/distance influence formula.
#
# Week sub-clustering: K-means K=4 within each finalised day zone.
#

print(f"\n── Per-tech day/week clustering ─────────────────────────────────────")

rng = np.random.default_rng(RANDOM_SEED)

# Build (tech, FL) FL-level frame: one tech-FL row per setup-cluster.
# An FL split across techs gets one row per tech.
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

# Anchor frequency: for each (tech, FL), the highest services_per_year across
# all setups at that FL for that tech. This determines which tier the FL enters
# zone formation at — all lower-frequency setups at the FL follow automatically.
anchor_freq_df = (
    setup_df.groupby(['tech', '%FL_id'])['services_per_year']
    .max()
    .reset_index()
    .rename(columns={'services_per_year': 'anchor_freq'})
)
tech_fl = tech_fl.merge(anchor_freq_df, on=['tech', '%FL_id'], how='left')
tech_fl['anchor_freq'] = pd.to_numeric(tech_fl['anchor_freq'], errors='coerce').fillna(1.0)
tech_fl['anchor_tier'] = tech_fl['anchor_freq'].apply(freq_tier)

tech_summary_rows = []

for tech_name in sorted(tech_fl['tech'].unique()):
    sub   = tech_fl[tech_fl['tech'] == tech_name].copy()
    n     = len(sub)
    if n == 0:
        continue
    pts   = sub[['latitude', 'longitude']].to_numpy()
    w     = np.maximum(sub['monthly_hrs'].to_numpy(), 0.001)
    tiers = sub['anchor_tier'].to_numpy()
    k_days = min(5, n)

    # ── Stage 0: outlier detection — exclude geographically extreme FLs from
    #            seeding so they don't carve out their own zone (Ballan-class)
    if n >= max(5, k_days + 1):
        tech_cent = geometric_median(pts, w)
        dist_tech = haversine(pts[:, 0], pts[:, 1], tech_cent[0], tech_cent[1])
        outlier_mask = detect_outliers(dist_tech)
    else:
        outlier_mask = np.zeros(n, dtype=bool)

    # ── Stage 1: zone-defining set — top tier AND non-outlier, expand if needed
    top_tier  = int(tiers.max())
    zone_mask = (tiers >= top_tier) & (~outlier_mask)
    while zone_mask.sum() < k_days and top_tier > 1:
        top_tier -= 1
        zone_mask = (tiers >= top_tier) & (~outlier_mask)
    # Last resort: if non-outlier core can't fill k_days, drop the outlier filter
    if zone_mask.sum() < k_days:
        zone_mask = tiers >= top_tier
    zone_pts = pts[zone_mask]
    zone_w   = w[zone_mask]

    # ── Stage 2: K-means on zone-defining FLs → initial centroids ────────────
    day_labels_zone, day_cents = kmeans_geographic(zone_pts, zone_w, k_days, rng)
    for j in range(k_days):
        m = day_labels_zone == j
        if m.any():
            day_cents[j] = geometric_median(zone_pts[m], zone_w[m])

    # Stamp zone assignments for zone-defining FLs
    day_labels_all = np.full(n, -1, dtype=int)
    for arr_i, orig_i in enumerate(np.where(zone_mask)[0]):
        day_labels_all[orig_i] = int(day_labels_zone[arr_i])

    # ── Stage 3: attach lower-tier non-outlier FLs, recompute centroids ──────
    for tier in sorted({int(t) for t in tiers if t < top_tier}, reverse=True):
        tier_mask = (tiers == tier) & (day_labels_all == -1) & (~outlier_mask)
        if not tier_mask.any():
            continue
        for i in np.where(tier_mask)[0]:
            d = np.array([haversine(pts[i, 0], pts[i, 1],
                                    day_cents[j, 0], day_cents[j, 1])
                          for j in range(k_days)])
            day_labels_all[i] = int(np.argmin(d))
        # Recompute geometric-median centroids with all non-outlier FLs assigned
        for j in range(k_days):
            m = day_labels_all == j
            if m.sum() > 0:
                day_cents[j] = geometric_median(pts[m], w[m])

    # ── Stage 3b: attach outliers last (any tier) — they don't shape zones ───
    outlier_unassigned = outlier_mask & (day_labels_all == -1)
    for i in np.where(outlier_unassigned)[0]:
        d = np.array([haversine(pts[i, 0], pts[i, 1],
                                day_cents[j, 0], day_cents[j, 1])
                      for j in range(k_days)])
        day_labels_all[i] = int(np.argmin(d))
    # Final centroid update with all FLs (outliers contribute weight/distance
    # only — geometric median bounds their pull)
    for j in range(k_days):
        m = day_labels_all == j
        if m.sum() > 0:
            day_cents[j] = geometric_median(pts[m], w[m])

    # Safety net — assign any still-unassigned FLs to nearest centroid
    for i in np.where(day_labels_all == -1)[0]:
        d = np.array([haversine(pts[i, 0], pts[i, 1],
                                day_cents[j, 0], day_cents[j, 1])
                      for j in range(k_days)])
        day_labels_all[i] = int(np.argmin(d))

    # ── Stage 4: order day zones west→east → Mon..Fri ────────────────────────
    day_lon_order  = np.argsort(day_cents[:, 1])
    cluster_to_day = {int(day_lon_order[i]): DAYS[i] for i in range(k_days)}
    sub['day'] = [cluster_to_day[int(lbl)] for lbl in day_labels_all]

    # ── Stage 5: week sub-clustering (K=4) within each finalised day zone ────
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

        wk_lat_order    = np.argsort(-wk_cents[:, 0])   # north→south → Wk1..Wk4
        cluster_to_week = {int(wk_lat_order[i]): i + 1 for i in range(k_weeks)}
        for arr_i, df_idx in enumerate(day_idx):
            sub.at[df_idx, 'week'] = cluster_to_week[int(wk_labels[arr_i])]

    tech_fl.loc[sub.index, 'day']  = sub['day'].values
    tech_fl.loc[sub.index, 'week'] = sub['week'].values
    tech_fl.loc[sub.index, 'is_outlier'] = outlier_mask

    tech_summary_rows.append({
        'tech'       : tech_name,
        'fls'        : int(n),
        'monthly_hrs': float(sub['monthly_hrs'].sum()),
        'days_used'  : int(sub['day'].nunique()),
        'weeks_used' : int(sub['week'].nunique()),
        'outliers'   : int(outlier_mask.sum()),
    })

tech_summary = pd.DataFrame(tech_summary_rows).sort_values('monthly_hrs', ascending=False)
print(f"Techs processed        : {len(tech_summary):,}")
print(f"Total tech-FL rows     : {len(tech_fl):,}")
print(f"Total outlier FLs      : {int(tech_fl['is_outlier'].sum()):,}")
print(f"Hrs/tech mean / median : {tech_summary['monthly_hrs'].mean():.1f}h / "
      f"{tech_summary['monthly_hrs'].median():.1f}h")
print(f"Hrs/tech min / max     : {tech_summary['monthly_hrs'].min():.1f}h / "
      f"{tech_summary['monthly_hrs'].max():.1f}h")


# ── 7b. Rebalance: move boundary FLs from over-cap slots to nearby slots ──────
#
# After the two-stage geographic clustering some (week, day) slots may still
# exceed 8h capacity while adjacent slots on the same tech have headroom.
# This pass iteratively moves the most geographically suitable FL from the
# heaviest over-cap slot to the nearest under-cap slot:
#
#   For each over-cap slot (heaviest first):
#     For each FL in that slot:
#       For each other slot on the same tech:
#         feasible if: new_dest_load < src_load  (reduces the maximum)
#         score      : geo_gain = dist(FL→src_centroid) - dist(FL→dest_centroid)
#                      positive = FL is naturally closer to the destination
#     Apply the highest-scoring feasible (FL, dest_slot) move.
#   Repeat until no over-cap slots remain or no feasible move exists.
#
# Tier 1 is preserved: tech_fl has one row per (tech, FL), so moving a row
# moves all setups at that FL together.

MAX_REBALANCE_ITER = 500
TABU_SIZE          = 15   # block an FL from returning to its previous slot for this many moves


def rebalance_pass(tech_fl, label='Rebalance pass', verbose=True):
    """One full pass of the tabu rebalance over every tech. Modifies tech_fl
    in place. Returns total moves."""
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


rebalance_pass(tech_fl, label='Slot rebalance pass')


# ── 7c. Spatial majority filter (enclave smoothing — runs AFTER rebalance) ────
#
# K-means produces straight-line Voronoi boundaries; the rebalance pass moves
# FLs based on capacity. Both can leave an FL surrounded by neighbours from a
# different zone. This final pass reassigns any FL where ≥ ENCLAVE_MIN_MAJORITY
# of its K nearest neighbours are in the same (week, day) slot — and that slot
# is not the FL's current one. Strict majority (not plurality) avoids touching
# legitimate boundary FLs.

print(f"\n── Spatial majority filter (enclave smoothing) ──────────────────────")

total_smoothing_moves = 0

for tech_name in sorted(tech_fl['tech'].unique()):
    tech_idx = tech_fl.index[tech_fl['tech'] == tech_name]
    n = len(tech_idx)
    if n < ENCLAVE_K_NEIGHBORS + 1:
        continue

    pts     = tech_fl.loc[tech_idx, ['latitude', 'longitude']].to_numpy()
    fl_hrs  = tech_fl.loc[tech_idx, 'monthly_hrs'].to_numpy()
    dist    = pairwise_haversine(pts)
    nn_idx  = np.argsort(dist, axis=1)[:, :ENCLAVE_K_NEIGHBORS]

    tech_moves = 0
    for _ in range(ENCLAVE_MAX_ITER):
        days_arr  = tech_fl.loc[tech_idx, 'day'].to_numpy()
        weeks_arr = tech_fl.loc[tech_idx, 'week'].to_numpy().astype(int)

        # Current slot loads — used as capacity gate
        sub_now   = tech_fl.loc[tech_idx]
        slot_load = sub_now.groupby(['week', 'day'])['monthly_hrs'].sum().to_dict()

        moves_iter = 0
        for i in range(n):
            cur = (int(weeks_arr[i]), days_arr[i])
            counts = {}
            for j in nn_idx[i]:
                s = (int(weeks_arr[j]), days_arr[j])
                counts[s] = counts.get(s, 0) + 1
            maj_slot, maj_count = max(counts.items(), key=lambda x: x[1])
            if maj_count < ENCLAVE_MIN_MAJORITY or maj_slot == cur:
                continue

            # Capacity gate: don't move if destination would go over cap, unless
            # destination is currently lighter than source (i.e. we're not making
            # the maximum slot worse).
            src_load     = slot_load.get(cur, 0.0)
            dst_load     = slot_load.get(maj_slot, 0.0)
            new_dst_load = dst_load + fl_hrs[i]
            if new_dst_load > CAPACITY_PER_DAY_HRS and new_dst_load >= src_load:
                continue

            fl_row = tech_idx[i]
            tech_fl.at[fl_row, 'week'] = maj_slot[0]
            tech_fl.at[fl_row, 'day']  = maj_slot[1]
            slot_load[cur]      = max(0.0, src_load - fl_hrs[i])
            slot_load[maj_slot] = new_dst_load
            moves_iter += 1
        if moves_iter == 0:
            break
        tech_moves += moves_iter

    if tech_moves > 0:
        print(f"  {tech_name:<35} {tech_moves} reassignments")
    total_smoothing_moves += tech_moves

print(f"Total enclave reassignments : {total_smoothing_moves:,}")


# ── 7e. Topology diagnostics — flag disconnected-zone FLs on tech_fl ──────────
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
    disconnected_df.to_csv(os.path.join(DIR, 'phase1_disconnected_zones.csv'), index=False)


# ── 8. Apply (day, week) back to setups ───────────────────────────────────────

setup_df = setup_df.merge(
    tech_fl[['tech','%FL_id','day','week']], on=['tech','%FL_id'], how='left'
)

# 6-weekly: pattern is "Every {Day}" (no week)
def compose_pattern(r):
    if r['is_weekly']:
        return f"Every {r['day']}" if r['day'] else ''
    if r['is_mwp'] and r['week'] and r['day']:
        return f"{int(r['week'])}-{r['day']}"
    return ''

setup_df['*New Date Pattern'] = setup_df.apply(compose_pattern, axis=1)


# ── 9. Slot capacity tracking (per-tech × week × day) ─────────────────────────

# Each setup contributes effective_duration × services_per_month to its (tech, week, day) slot.
# Weekly setups: spread evenly across 4 weeks (assigned per-week not modelled — just for capacity).
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


# ── 10. Save outputs ──────────────────────────────────────────────────────────

# Setup-level (one row per setup)
setup_out_cols = [c for c in setup_df.columns if not c.endswith('_fl')]
setup_df[setup_out_cols].to_csv(os.path.join(DIR, 'phase1_setup_output.csv'), index=False)

# Tech-FL assignment level (one row per tech × FL — splits an FL across techs)
tech_fl.to_csv(os.path.join(DIR, 'phase1_fl_assignments.csv'), index=False)
tech_summary.to_csv(os.path.join(DIR, 'phase1_tech_summary.csv'), index=False)
slot_df.to_csv(os.path.join(DIR, 'phase1_slot_capacity.csv'), index=False)

print(f"\n── Saved ────────────────────────────────────────────────────────────")
print(f"  phase1_setup_output.csv      ({len(setup_df):,} rows)")
print(f"  phase1_fl_assignments.csv    ({len(tech_fl):,} rows)")
print(f"  phase1_tech_summary.csv      ({len(tech_summary):,} rows)")
print(f"  phase1_slot_capacity.csv     ({len(slot_df):,} rows)")
if multi_tech_fl_ids:
    print(f"  phase1_multi_tech_fls.csv    ({len(multi_tech_fl_ids):,} FLs flagged)")


# ── 11. KPIs ──────────────────────────────────────────────────────────────────

allocated = setup_df['*New Date Pattern'].astype(str).str.len() > 0
pct = allocated.mean() * 100

# Same-site grouping: FLs (per tech) where all setups at that (tech, FL) share a (week, day)
sf = setup_df.groupby(['tech','%FL_id']).agg(
    days=('day', lambda s: s.nunique()),
    weeks=('week', lambda s: s.nunique())).reset_index()
same_site = ((sf['days']==1) & (sf['weeks']<=1)).mean() * 100  # weeks==1 for monthly; 0 if all weekly

# Distance to per-tech centroid
fl_centroid = tech_fl.groupby('tech').agg(
    clat=('latitude', lambda s: np.average(s, weights=np.maximum(tech_fl.loc[s.index,'monthly_hrs'],0.001))),
    clon=('longitude', lambda s: np.average(s, weights=np.maximum(tech_fl.loc[s.index,'monthly_hrs'],0.001))),
).reset_index()
tf2 = tech_fl.merge(fl_centroid, on='tech')
tf2['d_km'] = haversine(tf2['latitude'], tf2['longitude'], tf2['clat'], tf2['clon'])

# Enclave rates — two views on the same K-NN topology check:
#   strict : ≥ ENCLAVE_MIN_MAJORITY of the K nearest neighbours are in the same
#            non-current slot. These are visually obvious enclaves (a dot in
#            another zone) and the targets of the smoothing pass.
#   loose  : any other slot has more neighbours than the FL's current slot.
#            Includes boundary FLs where neighbours are split across many slots —
#            a noisier signal, dominated by legitimate borders.
enclave_strict = 0
enclave_loose  = 0
enclave_total  = 0
for tech_name in tech_fl['tech'].unique():
    sub_t = tech_fl[tech_fl['tech'] == tech_name]
    n_t = len(sub_t)
    if n_t < ENCLAVE_K_NEIGHBORS + 1:
        continue
    pts_t = sub_t[['latitude', 'longitude']].to_numpy()
    slots = list(zip(sub_t['week'].astype(int).to_numpy(),
                     sub_t['day'].to_numpy()))
    dist  = pairwise_haversine(pts_t)
    nn    = np.argsort(dist, axis=1)[:, :ENCLAVE_K_NEIGHBORS]
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
        if maj_count >= ENCLAVE_MIN_MAJORITY and maj_slot != cur:
            enclave_strict += 1
strict_rate = (enclave_strict / enclave_total * 100) if enclave_total else 0.0
loose_rate  = (enclave_loose  / enclave_total * 100) if enclave_total else 0.0

print(f"\n── KPIs ─────────────────────────────────────────────────────────────")
print(f"  % setups allocated           : {pct:.2f}%")
print(f"  Same-site (tech,FL) grouping : {same_site:.2f}%")
print(f"  Mean FL→tech-centroid dist   : {tf2['d_km'].mean():.2f} km")
print(f"  Total FL→tech-centroid dist  : {tf2['d_km'].sum():,.1f} km")
print(f"  Enclave rate strict (≥{ENCLAVE_MIN_MAJORITY}/{ENCLAVE_K_NEIGHBORS})  : {strict_rate:.2f}% "
      f"({enclave_strict:,}/{enclave_total:,})  ← target ≤ 5%")
print(f"  Enclave rate loose (plurality): {loose_rate:.2f}% "
      f"({enclave_loose:,}/{enclave_total:,})")
print(f"  Disconnected zones (>{DISCONNECTED_GAP_KM}km gap)  : {len(disconnected_df):,}")
