"""
Phase 0 — Portfolio Distribution Analysis
BSO Grouping Model | Melbourne Commercial Pest (GM-MCP)
--------------------------------------------------------
Applies all PoC exclusion filters, derives monthly work-hour contribution
per setup, aggregates to FL and suburb level, and estimates required
run-day slots per area at 8h daily capacity.

Outputs (written to same directory as input):
  phase0_working_dataset.csv  — filtered setup-level dataset for Phase 1+
  phase0_fl_summary.csv       — FL-level aggregation (anchor, hours, coords)
  phase0_area_summary.csv     — suburb-level aggregation + required run-days
"""

import io
import os
import sys
import numpy as np
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── Config ────────────────────────────────────────────────────────────────────

DIR              = os.path.dirname(os.path.abspath(__file__))
DATA_FILE        = os.path.join(DIR, "Melbourne Commercial AGB - Test Data (24-04-26).csv")
CAPACITY_MINS    = 8 * 60          # 480 min — target service hours per run-day
DEFAULT_DUR_MINS = 15              # substitute for zero-duration non-Cormie setups
MAX_DUR_MINS     = 480             # flag and exclude from capacity if above this
WORKING_DAYS     = 20              # Mon–Fri slots per month (4 weeks × 5 days)

# DOW numeric → name (0=Sun … 6=Sat, matching Dynamics encoding)
DOW_MAP = {'0': 'Sunday', '1': 'Monday', '2': 'Tuesday', '3': 'Wednesday',
           '4': 'Thursday', '5': 'Friday', '6': 'Saturday'}


# ── 1. Load ───────────────────────────────────────────────────────────────────

df = pd.read_csv(DATA_FILE, encoding='utf-8-sig', dtype=str)
df.columns = df.columns.str.strip()
print(f"Loaded : {len(df):,} setups")


# ── 2. Exclusion filters ──────────────────────────────────────────────────────

excluded = pd.Series(False, index=df.index)
log = {}

def exclude(mask, label):
    global excluded
    # only count setups not already excluded
    new = mask & ~excluded
    log[label] = int(new.sum())
    excluded |= mask

# Simon Cormie — all setups (invoice/admin processing, no field service)
exclude(df['*Preferred Resource'].str.contains('Simon Cormie', na=False), 'Simon Cormie (all)')

# Non-target frequency types
exclude(df['%frequency_type'] == 'Yearly',               'Yearly')
exclude(df['%frequency_type'] == 'Daily',                'Daily')
exclude(df['%frequency_type'] == 'Monthly - Fixed Date', 'Monthly - Fixed Date (D1 pending)')
exclude(df['%frequency_type'].isna() |
        df['%frequency_type'].str.strip().isin(['', 'NULL']), 'NULL frequency')

# Weekend Monthly - Week Pattern (Sat/Sun — overflow/OT only, not scheduled runs)
exclude(
    (df['%frequency_type'] == 'Monthly - Week Pattern') &
    (df['%recc_dow_number'].isin(['0', '6'])),
    'Weekend Mon-Week-Pattern (Sat/Sun)'
)

# Week 0 "5th weekday" anomalies — no reliable monthly slot
exclude(
    (df['%frequency_type'] == 'Monthly - Week Pattern') &
    (df['%recc_week_number'] == '0'),
    'Week 0 (5th weekday)'
)

print("\n── Exclusions ───────────────────────────────────────────────────────")
for reason, count in log.items():
    print(f"  {reason:<45s}: {count:>4,}")
print(f"  {'Total excluded':<45s}: {excluded.sum():>4,}")

df = df[~excluded].copy()
print(f"\nWorking dataset : {len(df):,} setups | {df['%FL_id'].nunique():,} unique FLs")


# ── 3. Derive services_per_year ───────────────────────────────────────────────
# Not present in CSV export — derived from frequency_type + num_recurrences.
# Monthly types : 12 / N    (e.g. 3 Monthly → 12/3 = 4 services/year)
# Weekly types  : 52 / N    (e.g. 6 Weekly  → 52/6 ≈ 8.67 services/year)

num_rec = pd.to_numeric(df['num_recurrences'], errors='coerce')
is_monthly = df['%frequency_type'].str.contains('Monthly', na=False)
is_weekly  = df['%frequency_type'].str.contains('Weekly',  na=False)

df['services_per_year'] = np.where(
    is_monthly, 12.0 / num_rec,
    np.where(is_weekly, 52.0 / num_rec, np.nan)
)
df['services_per_month'] = df['services_per_year'] / 12.0

null_spy = df['services_per_year'].isna().sum()
if null_spy:
    print(f"\n  Warning: {null_spy} setups with unresolvable services_per_year — excluded from capacity")


# ── 4. Effective duration ─────────────────────────────────────────────────────
# Use ~New Duration if populated, else Current Duration.
# Zero-duration (non-Cormie): substitute 15 min default.
# >480 min: flag and exclude from capacity calculations.

new_dur = pd.to_numeric(df['~New Duration'].replace('', np.nan), errors='coerce')
cur_dur = pd.to_numeric(df['Current Duration'], errors='coerce')
df['effective_duration'] = new_dur.fillna(cur_dur)

zero_mask = df['effective_duration'] == 0
print(f"\n  Zero-duration (non-Cormie) → {DEFAULT_DUR_MINS} min default : {zero_mask.sum()}")
df.loc[zero_mask, 'effective_duration'] = DEFAULT_DUR_MINS

df['duration_flagged'] = df['effective_duration'] > MAX_DUR_MINS
print(f"  Duration > {MAX_DUR_MINS} min (flagged, excluded from capacity) : {df['duration_flagged'].sum()}")

# Capacity duration: NaN for flagged setups so they don't skew calculations
df['capacity_duration'] = df['effective_duration'].where(~df['duration_flagged'], np.nan)


# ── 5. Monthly contribution ───────────────────────────────────────────────────
# Hours a setup contributes to the workload each month on average.
# For quarterly: duration × (1/3) — it drops once every 3 months, averaged.

df['monthly_contrib_mins'] = df['capacity_duration'] * df['services_per_month']
df['monthly_contrib_hrs']  = df['monthly_contrib_mins'] / 60.0

# Human-readable DOW name
df['dow_name'] = df['%recc_dow_number'].map(DOW_MAP).fillna('Unknown')


# ── 6. FL-level aggregation ───────────────────────────────────────────────────

df['latitude']  = pd.to_numeric(df['latitude'],  errors='coerce')
df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')

fl = df.groupby('%FL_id').agg(
    FL_name             = ('FL_name',             'first'),
    city                = ('city',                'first'),
    address             = ('Address 1',           'first'),
    latitude            = ('latitude',            'first'),
    longitude           = ('longitude',           'first'),
    setup_count         = ('%booking_setup_id',   'count'),
    monthly_contrib_hrs = ('monthly_contrib_hrs', 'sum'),
    anchor_spy          = ('services_per_year',   'max'),   # highest freq = anchor
    frequency_types     = ('%frequency_type',     lambda x: ' | '.join(sorted(x.dropna().unique()))),
    dow_names           = ('dow_name',            lambda x: ' | '.join(sorted(x.dropna().unique()))),
).reset_index()

fl['monthly_contrib_hrs'] = fl['monthly_contrib_hrs'].round(3)

print(f"\n── FL Summary ───────────────────────────────────────────────────────")
print(f"  FLs with multiple setups        : {(fl['setup_count'] > 1).sum():,}")
print(f"  FL monthly hours — mean         : {fl['monthly_contrib_hrs'].mean():.2f}h")
print(f"  FL monthly hours — median       : {fl['monthly_contrib_hrs'].median():.2f}h")
print(f"  FL monthly hours — 90th pctile  : {fl['monthly_contrib_hrs'].quantile(0.9):.2f}h")
print(f"  FL monthly hours — max          : {fl['monthly_contrib_hrs'].max():.2f}h")
print(f"  FLs missing coordinates         : {fl['latitude'].isna().sum()}")


# ── 7. Area-level aggregation ─────────────────────────────────────────────────

area = fl.groupby('city').agg(
    fl_count            = ('%FL_id',              'count'),
    setup_count         = ('setup_count',         'sum'),
    total_monthly_hrs   = ('monthly_contrib_hrs', 'sum'),
    centroid_lat        = ('latitude',            'mean'),
    centroid_lon        = ('longitude',           'mean'),
).reset_index()

# Required run-days: total monthly hours / 8h capacity, rounded up to nearest 0.5
area['required_run_days'] = np.ceil(area['total_monthly_hrs'] / (CAPACITY_MINS / 60) * 2) / 2
area = area.sort_values('total_monthly_hrs', ascending=False).reset_index(drop=True)

total_hrs      = area['total_monthly_hrs'].sum()
total_run_days = area['required_run_days'].sum()

print(f"\n── Area Summary (top 25 by monthly hours) ───────────────────────────")
print(f"  {'City':<32} {'FLs':>5} {'Setups':>7} {'Mo. hrs':>9} {'Run-days/mo':>12}")
print(f"  {'-'*32} {'-'*5} {'-'*7} {'-'*9} {'-'*12}")
for _, row in area.head(25).iterrows():
    city = str(row['city']) if pd.notna(row['city']) else '(unknown)'
    print(f"  {city:<32} {int(row['fl_count']):>5} {int(row['setup_count']):>7} "
          f"{row['total_monthly_hrs']:>8.1f}h {row['required_run_days']:>11.1f}")

print(f"\n  Total areas in portfolio   : {len(area):,}")
print(f"  Portfolio monthly hours    : {total_hrs:,.1f}h")
print(f"  Required run-days / month  : {total_run_days:.0f}")
print(f"  Available Mon–Fri slots    : {WORKING_DAYS} (4 weeks × 5 days)")
print(f"  Implied technicians needed : ≥{total_run_days / WORKING_DAYS:.1f} "
      f"(run-days / available slots — assumes one tech per slot)")


# ── 8. Frequency tier breakdown ───────────────────────────────────────────────

print(f"\n── Frequency Tier Breakdown (working dataset) ───────────────────────")
tier = (
    df.groupby('Recurrence Frequency')
    .agg(
        setup_count         = ('%booking_setup_id',   'count'),
        fl_count            = ('%FL_id',              'nunique'),
        avg_duration_mins   = ('effective_duration',  'mean'),
        monthly_hrs         = ('monthly_contrib_hrs', 'sum'),
    )
    .sort_values('setup_count', ascending=False)
)
tier['avg_duration_mins'] = tier['avg_duration_mins'].round(1)
tier['monthly_hrs']       = tier['monthly_hrs'].round(1)
print(tier.to_string())


# ── 9. Save outputs ───────────────────────────────────────────────────────────

df.to_csv(os.path.join(DIR, 'phase0_working_dataset.csv'),  index=False)
fl.to_csv(os.path.join(DIR, 'phase0_fl_summary.csv'),       index=False)
area.to_csv(os.path.join(DIR, 'phase0_area_summary.csv'),   index=False)

print(f"\n── Saved ────────────────────────────────────────────────────────────")
print(f"  phase0_working_dataset.csv   ({len(df):,} rows)")
print(f"  phase0_fl_summary.csv        ({len(fl):,} rows)")
print(f"  phase0_area_summary.csv      ({len(area):,} rows)")
