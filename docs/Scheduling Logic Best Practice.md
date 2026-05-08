**Author:** [Brandon Atkinson]
**Date:** March 25th 2026
**Version:** 0.1
**Audience:** Fusion 5 (Technical Implementation)

---

## 1. Purpose & Scope

This document defines the scheduling logic and best practice principles that should underpin the Scheduling Enhancements. It is intended to give Fusion 5 a clear understanding of how optimised runs should be constructed - both the reasoning behind each decision and the order in which decisions should be made.

The logic is split into two layers:

- **General Logic** - concepts and rules that apply universally across all business streams.
- **Stream-Specific Considerations** - nuances that apply specifically to Hygiene or Commercial Pest.

A "run" in this context refers to a technician's assigned set of services for a given day, structured such that services in the same geographic area recur consistently on that day each cycle. The goal of any scheduling enhancement should be to construct these runs in a way that minimises travel, reduces unnecessary site visits, and creates a consistent, repeatable schedule for technicians, customers, and schedulers alike.

---

## 2. Key Terminology

| Term | Definition |
|---|---|
| **Functional Location (FL)** | The physical site at which a service is performed. Multiple bookings / services may exist against a single FL. |
| **Booking Setup** | The recurrence configuration that drives when and how often a work order is generated for a given service. |
| **Recurrence Frequency** | The actual scheduling frequency derived from the booking setup's recurrence settings (e.g. 4-weekly, monthly). This is the source of truth for scheduling logic - not the static `Product Service Frequency` field on the setup, which may not match. |
| **Setup Template** | The configured output of the BSO process - a technician-day-site mapping that AGB executes against to generate work orders. |
| **Anchor Point** | The highest-frequency setup at a given FL. Anchor points form the structural basis around which all other services at that site are grouped. |
| **Run** | A technician's recurring daily workload within a defined geographic area. |
| **Geo Zone / Area** | A defined geographic grouping of FLs used to assess work distribution and inform run boundaries. |

---

## 3. General Logic

The principles in this section apply universally across Hygiene and Commercial Pest.

### 3.1 Core Objective

The critical priority of any run optimisation is the **reduction of travel time and site visits** through improved same-site service grouping and consistent geographic routing. This delivers efficiency gains for technicians, schedulers, and customers, and directly improves margins by reducing non-productive time.

Every decision in the scheduling logic should be evaluated against this objective.

### 3.2 Duration Calculations

Accurate duration estimates are essential for validating that a day's allocated work is achievable within available hours. Two components make up a visit's total duration:

#### 3.2.1 Service Duration

The time required to perform the service itself. How this is calculated differs by stream - see Sections 4 and 5.

#### 3.2.2 Site Start Time (5-Minute Overhead)

Every unique FL visited in a day incurs a fixed overhead (previously reflected as **5 minutes**) to account for parking, retrieving products from the van, obtaining signatures, and other site entry activities.

This 5-minute overhead applies **per unique FL per day** - not per individual booking. Where multiple bookings are scheduled at the same FL on the same day, the overhead is shared equally across those bookings.

**Formula:**

```
Site start overhead per booking = 5 min / number of bookings at that FL on that day
```

**Examples:**

- 1 booking at FL on a given day: overhead = 5 min (full overhead absorbed by the single booking)
- 2 bookings at FL on a given day: overhead = 2.5 min each
- 4 bookings at FL on a given day: overhead = 1.25 min each

This reinforces why consolidating multiple services at the same FL to the same day is a priority - it directly reduces the effective overhead per booking and increases the productive proportion of a technician's day.

#### 3.2.3 Total Visit Duration

```
Total visit duration = service duration + (5 min / bookings at FL that day)
```

### 3.3 Assessing Distribution and Capacity

Before any grouping or allocation decisions are made, it is necessary to understand how work is distributed across the portfolio - geographically and temporally. This baseline informs how many resource days are required in each area per month or 4-weekly cycle.

**The primary source of data for this assessment is the booking setup's future booking dates.** Each setup generates a series of projected booking dates based on its current recurrence settings, extending up to 12 months ahead. Aggregating these dates across all setups for a branch provides a forward-looking picture of when and where work will fall - without relying on historical actuals, which may reflect inefficient prior scheduling.

Distribution should be assessed across:

- **Geographic area** (suburb, geo zone, or equivalent) - how many hours of work fall in each area per cycle.
- **Recurrence frequency** - the volume breakdown of weekly, 2-weekly, 4-weekly, monthly services etc.
- **Technician** - current allocation of work per technician to identify over- and under-capacity resources prior to rebalancing.

This distribution assessment should ideally be performed iteratively throughout the grouping process - not only as a one-time upfront exercise - so that emerging imbalances can be identified and corrected before they are embedded in the final Setup Template.

### 3.4 Anchor Points

An **anchor point** is the highest-frequency setup at a given FL. Anchor points are the structural foundation of the grouping process - they are allocated first, and all other services at the same FL are aligned to match.

**Why anchor points?**

Higher-frequency services recur more often, are more constrained in where they can be placed within a cycle, and therefore have less scheduling flexibility. Starting with the most constrained services and building outward ensures the final template is achievable - rather than discovering conflicts after lower-frequency work has already been allocated.

**Identifying anchor points:**

For each FL, identify the setup with the highest recurrence frequency (i.e. shortest interval between services). Where an FL has only one setup, that setup is by definition the anchor.

**Important:** Frequency must be derived from the actual **recurrence settings** on the booking setup, not the `Product Service Frequency` field. The latter is a static label that may not reflect the true scheduling cadence.

### 3.5 Grouping and Allocation Process

The grouping process follows a top-down frequency order. All FLs are worked through from highest to lowest recurrence frequency, anchoring and allocating progressively.

The recommended sequence is as follows:

**Step 1 - Establish geographic distribution**

Using future booking dates (see 3.3), determine the volume of work per geographic area per cycle. This sets the foundation for how many run days are needed in each area and provides the canvas onto which anchor points are placed.

**Step 2 - Identify and allocate anchor points (highest frequency first)**

Starting with the most frequent services in the portfolio:

1. Identify all FLs that have a setup at this frequency.
2. These become the anchor points for their respective FLs.
3. Allocate each anchor point to a technician and day, grouping by geographic area. Apply day adjacency logic (see 3.6) to ensure neighbouring days cover neighbouring areas.
4. All other setups at the same FL - regardless of their own frequency - are flagged for alignment to this anchor in Step 3.

**Step 3 - Align lower-frequency services to their FL's anchor**

For each FL with an anchor point now allocated:

- All lower-frequency setups at that FL should be assigned to the **same technician** as the anchor.
- Their day of week / week of month assignment should match the anchor where the recurrence allows, or be placed on the nearest compatible day where it does not.

This ensures all services at a site are handled by the same technician, building familiarity and reducing site visits.

**Step 4 - Repeat for the next frequency tier**

Move to the next frequency level (e.g. from weekly to 2-weekly) and repeat Steps 2-3 for any FLs not yet allocated. Continue descending through frequency tiers until all setups have been assigned.

**Step 5 - Review and rebalance**

Once all setups have been allocated, review run capacities and key metrics (see Section 6 of the BSO proposal). Identify over- and under-capacity runs and rebalance as needed. This step should also be performed iteratively during allocation, not only at the end.

### 3.6 Day Adjacency Logic

When assigning services across days of the week, days should be treated as geographically contiguous where possible. The geographic area covered on a Monday should be adjacent to the area covered on Tuesday, which should be adjacent to Wednesday, and so on - such that a technician's weekly route forms a logical geographic progression across the region rather than jumping between disparate areas.

**Twice-weekly services:**

Where a service requires attendance twice per week and one or both days are locked (e.g. a customer requiring Tuesday and Friday), the geographic cluster assigned to Friday should be proximate to the Tuesday cluster. This ensures that re-attendance travel is minimised and the overall weekly route remains coherent.

### 3.7 Service Continuity

A setup optimisation model should apply a **stability bias**: changes to a service's assigned technician, day of week, or week of month should only be made when the grouping improvement meaningfully warrants it.

Month-to-month churn in service days is disruptive for technicians, schedulers, and customers - and undermines the consistency that AGB and Setup Templates are designed to deliver. The model should preference retaining existing assignments where they remain reasonably efficient, rather than optimising for theoretical perfection at the cost of operational continuity.

Where changes are made, they should cascade logically - i.e. if an anchor point's day changes, all aligned lower-frequency services at that FL should be updated to follow.

### 3.8 Non-Regular Frequency Distribution

For services outside the standard high-frequency tiers - Hygiene services greater than 4-weekly and Pest services greater than monthly - the model must consider not just where services are grouped, but when across the year they fall.

Left unmanaged, low-frequency services (8-weekly, 12-weekly, 6-monthly, annual etc.) can cluster into the same generation cycle, producing periods where a branch's workload is unachievable and revenue is skewed. The model should assess the forward 12-month distribution of these services using projected booking dates and, where over-concentration is identified, stagger affected services across adjacent cycles to smooth the load.

**Existing schedule bias must be applied.** Adjustments should be as small as possible while still achieving a meaningful improvement in distribution. This protects against three risks:

- **Customer expectations** - low-frequency customers have an established expectation of when their service falls.
- **Billing impact** - shifting a service compresses or extends the effective billing cycle.
- **Service gap risk** - moving a service that is due soon into a later cycle can create an unacceptably long gap between attendances, potentially breaching contract terms.

Where no adjustment can be made within a tolerable threshold without triggering one of the above risks, the service should be flagged for manual review rather than automatically rescheduled.

---

## 4. Hygiene - Specific Considerations

### 4.1 Volume and Site Visit Reduction

Hygiene operations typically involve a significantly higher volume of bookings and FLs than Pest. This makes the reduction of site visits per day a particularly high-priority objective - the overhead savings from consolidating multiple bookings at the same FL on the same day compound significantly at scale.

When reviewing Hygiene run efficiency, site visit count and site overlap rate (see BSO proposal metrics) are the most sensitive indicators of scheduling quality.

### 4.2 Duration Calculation

For Hygiene, service durations can be calculated from first principles using a product-based formula, provided the business agrees on a standard duration per unit per product:

```
Service duration = unit quantity x agreed duration per unit (per product)
```

The agreed duration per unit per product should be maintained as a lookup reference - e.g. Product A = X minutes per unit, Product B = Y minutes per unit. This allows durations to be calculated consistently and systematically across the portfolio, reducing reliance on manually entered estimates which may be inconsistent.

**Total booking duration:**

```
Total booking duration = (unit quantity x duration per unit) + (5 min / bookings at FL that day)
```

---

## 5. Commercial Pest - Specific Considerations

### 5.1 Duration Accuracy

Duration accuracy is a more significant concern for Pest than for Hygiene. Pest job durations are more variable - driven by site size, pest pressure, treatment type, and technician method - and the consequences of underestimating them are more acute, as a single long job can destabilise an entire day's run.

Prior to any Setup Optimisation run for a Pest branch, a **duration audit** should be completed to validate that all incident durations are a reasonable reflection of actual service time. Where durations are materially incorrect, a bulk update should be performed before the model runs. Understated durations risk the model constructing daily templates that cannot be realistically completed within available hours.

### 5.2 Duration Calculation

Unlike Hygiene, Pest service durations cannot be reliably derived from a product-per-unit formula given the variability in service type and site conditions. The model should rely on the **incident duration** recorded on the booking setup as the primary input, subject to the audit and standardisation described in 5.1.

The site start overhead is applied in the same way as Hygiene:

```
Total booking duration = incident duration + (5 min / bookings at FL that day)
```

### 5.4 Recurrence Configuration

All Pest setups should operate on a calendar-anchor basis:

- Valid: First Monday of the Month, Second Tuesday of the Month ... through to 4th Friday of the Month.
- Not valid: Mixed interval-based recurrences (e.g. "every 30 days") within the same branch.

The model should validate recurrence configuration prior to running and flag any setups that do not conform. Non-conforming setups should be remediated before inclusion in the grouping process (see D1 in the BSO proposal).

---

## 6. Summary - Recommended Implementation Order

The following sequence summarises the recommended order of operations for the BSO model when processing a branch:

1. **Validate data** - confirm recurrence configurations are conformant (Pest: calendar-anchor; Hygiene: week-based). Flag non-conforming setups for remediation before proceeding.
2. **Extract future booking dates** - aggregate projected booking dates from all setups to establish geographic and temporal work distribution.
3. **Assess distribution** - determine work volume per geographic area and per frequency tier. Establish how many resource days are required per area per cycle.
4. **Identify anchor points** - for each FL, identify the highest-frequency setup as the anchor.
5. **Allocate anchors (highest frequency first)** - group by geography, apply day adjacency logic, respect locked setups.
6. **Align lower-frequency services** - assign remaining setups at each FL to match their anchor's technician and day where possible.
7. **Repeat for next frequency tier** - continue until all setups are allocated.
8. **Review and rebalance** - assess run capacities and key metrics. Identify imbalances and adjust. Apply service continuity principle - only change assignments where the improvement materially warrants it.
9. **Output Setup Template** - produce the recommended technician-day-site mapping for branch review and approval.
10. Balance portfolio distribution for servicing and revenue across a 12 month period, improving budget accuracy.

---

