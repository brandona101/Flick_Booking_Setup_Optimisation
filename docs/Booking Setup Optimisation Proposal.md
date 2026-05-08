
**Author:** [Brandon Atkinson]
**Date:** March 2026
**Version:** 0.5 (Draft for Review)
**Audience:** Internal Leadership

---

## 1. Executive Summary

Flick's transition to Flick 360 (Dynamics 365) introduced scheduling tools - the Scheduling Assistant and Resource Scheduling Optimisation (RSO) - that, while capable in standard deployments, have not proven fit for the operational complexity and volume of Flick's business streams. The Hygiene division addressed this in Q4 2025 by implementing Auto Generate Bookings (AGB), restoring the runs-based scheduling efficiency of the legacy FOL system.

Commercial Pest is now seeking to adopt AGB. Unlike Hygiene, Pest has no pre-existing runs structure to migrate from, meaning a direct AGB rollout without foundational work would transfer significant scheduling burden to branches rather than relieving it.

This proposal outlines the **Booking Setup Optimisation (BSO) project**, structured across two phases:

**Phase 1** runs concurrently across four workstreams - data remediation, AGB rollout, internal development of the grouping model logic, and a Planned Capacity Review BI overhaul. AGB is activated branch-by-branch as each branch's data is cleaned, with the grouping model iterating against real data throughout.

**Phase 2** begins once the model logic is sufficiently validated: Fusion 5 implements it as a native Dynamics feature and builds the surrounding system components required to make it operational at scale.

|             | Workstream                                              | Summary                                                                                                                         |
| ----------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **Phase 1** | **W1 - Data Remediation**                               | Standardise Pest (and Hygiene) recurrence configurations and incident durations across the portfolio.                           |
|             | **W2 - Grouping Model Development**                     | Internally develop, test, and iteratively refine the clustering model logic using live branch data as AGB rolls out.            |
|             | **W3 - AGB Rollout (Pest)**                             | Activate AGB for Pest branches progressively as data remediation is completed, with model output informing Setup Templates.     |
|             | **W4 - Planned Capacity Review BI**                     | Overhaul the existing Booking Setup BI to provide actionable capacity and overlap insights across all branches and technicians. |
| **Phase 2** | **W5 - System Implementation / Recurring Optimisation** | Fusion 5 implements the validated model as a native Dynamics feature and builds all required system components.                 |

This project also establishes the foundation for a future **Intraday Scheduling tool** - a downstream initiative that, contingent on BSO outcomes, would flatten daily schedules, insert travel time, and manage same-day disruptions such as sick leave.

---

## 2. Background & Problem Statement

### 2.1 Legacy Approach (FOL)
In FOL, both Hygiene and Commercial Pest operations were built around a planned runs-based scheduling model:
- **Hygiene** operated on a Week 1 Monday-Week 4 Friday geographic day structure.
- **Commercial Pest** pre-allocated setups to technicians with the following month's schedule prepared in advance.

While resource-intensive to maintain, this model delivered consistency for technicians, customers, and schedulers - enabling efficiency gains and stronger customer relationships.

### 2.2 Flick 360 Transition
Upon moving to Flick 360, this was replaced by the Scheduling Assistant and RSO. Both tools fell short of Flick's operational requirements, resulting in:
- Increased manual scheduling effort at branch level.
- Loss of routing consistency and technician-site familiarity.
- Day structures that do not account for geography or site consolidation.

AGB was subsequently implemented for Hygiene in Q4 2025 to restore runs-based scheduling. Commercial Pest has identified the same need.

### 2.3 Why Pest Is More Complex
A direct AGB rollout for Pest - without the foundational work this proposal addresses - faces several compounding challenges:

| Challenge | Detail |
|---|---|
| No pre-existing run structure | Pest did not use runs management in FOL. There is no routing data or technician-day structure to migrate from. |
| Data inconsistencies | Recurrence frequency mismatches, incorrect job durations, and non-standard setup configurations are prevalent across Pest setups. |
| Branch resourcing constraints | Building a Setup Template from scratch requires deep local knowledge of services and geography - a significant ask given current branch workloads. |
| Limited bulk-edit capability | Bulk manipulation of runs via spreadsheet import is currently restricted to 2-3 people nationally. |
| Dynamic portfolio | New sales, cancellations, and contract re-signs mean any Setup Template must accommodate regular rebalancing to remain effective. |

---

## 3. Proposed Solution

### 3.1 Overview

The BSO project is structured in two phases. Phase 1 does the groundwork and gets AGB live for Pest. Phase 2 makes the optimisation self-sustaining within Flick 360.

The four Phase 1 workstreams run in parallel, with each informing the others as branches are progressively activated:

| Workstream | What it does |
|---|---|
| **W1 - Data Remediation** | Fix the data quality issues that would prevent AGB from working correctly and undermine the grouping model's accuracy. |
| **W2 - Grouping Model Development** | Develop the logic that determines how services should be grouped - by site, by geography, and by technician - to produce efficient, consistent runs. |
| **W3 - AGB Rollout (Pest)** | Activate AGB for Pest branches progressively as their data is cleaned, using grouping model outputs to establish initial run structures. |
| **W4 - Planned Capacity BI** | Overhaul the existing scheduling BI to give branch managers and national operations a clear view of technician capacity, workload balance, and scheduling gaps. |

Phase 2 takes the model logic proven in Phase 1 and works with Flick's development partner (Fusion 5) to implement it as a native Flick 360 feature - enabling branches to run and review schedule optimisations each month without manual or bulk re-import workarounds. The scope and sequencing of Phase 2 will be determined once Phase 1 outputs are available. Fusion 5 is welcome to contribute to Phase 1 where able and to begin considering the system design in parallel, however the Phase 2 build should be driven by what the internal initiative produces.

---

### 3.2 Workstream 1 - Data Remediation

Standardise the portfolio data to a quality level sufficient for AGB to generate correctly and for the grouping model to produce accurate outputs.

| #   | Requirement                                    | Detail                                                                                                                                                                                                                                                                                           |
| --- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| D1  | **Standardise Pest Recurrence Frequencies**    | All Pest setups should operate on a calendar-anchor basis (First Monday of the Month through to 4th Friday of the Month). Mixed frequency types within a branch must be resolved prior to / during that branch's AGB activation.                                                                 |
| D2  | **Standardise Hygiene Recurrence Frequencies** | Hygiene setups should be week-based exclusively (e.g. 4-weekly, not monthly). Deviations should be corrected to ensure consistent AGB behaviour across both streams.                                                                                                                             |
| D3  | **Pest Incident Duration Audit & Bulk Update** | Accurate job durations are a prerequisite for the model to generate valid daily templates. A bulk review and update of Pest incident durations should be completed ahead of each branch's first model run. *(Note: A task for this has been raised in Monday.)*                                  |
| D4  | **Standardise Booking Setup Branch**           | The branch listed on each setup must reflect the branch performing the service, to allow for accurate filtering, re-importing, and model segmentation. There are currently 576 setups with this discrepancy. A corrected export is already available and can be re-imported with minimal effort. |

---

### 3.3 Workstream 2 - Grouping Model Development

The grouping model is the core of the BSO project. It takes a branch's full portfolio of services and determines the most efficient way to assign them to technicians and days - building consistent, repeatable runs that reduce travel and eliminate unnecessary site visits.

Rather than specifying the full model upfront and handing it to a developer to build, the approach is to develop and validate it against real branch data as AGB rolls out. Each branch activated on AGB provides an additional dataset to test and refine the model against - meaning by the time it is handed to Fusion 5 for system implementation, the logic is proven in practice rather than in theory.

**Anchor-based allocation.** The model allocates work starting from the most frequently serviced sites. The highest-frequency setup at each site acts as an anchor point - it is placed first, and all other services at that site are aligned to the same technician and day. The model then works down through frequency tiers, placing the next most frequent unallocated services and aligning their sites around them, repeating until everything is assigned. This approach ensures the most constrained services - those with the least scheduling flexibility - are placed first, reducing the risk of conflicts emerging later in the process.

The model is structured in tiers of increasing sophistication. Tiers 1 and 2 are the immediate priority; further tiers will be added as earlier ones are validated.

| Tier | Focus | What it optimises |
|---|---|---|
| **1** | **Site grouping** | All services at the same site are assigned to the same technician and day, eliminating unnecessary repeat visits. |
| **2** | **Geographic grouping** | Sites are clustered geographically so each technician's day covers a coherent area, minimising travel. Adjacent days are assigned to adjacent areas so the weekly route flows logically across the region. |
| **3** | **Workload balancing** | Technician available hours and customer time windows are factored in to ensure daily templates are achievable. |
| **4** | **Technician fit** | Technician skills, site familiarity, and customer preferences are applied as a final assignment layer. |

**Three design principles apply throughout:**

- **Service continuity.** The model should not change a customer's service day unless the routing benefit genuinely warrants it. Unnecessary changes disrupt customers, technicians, and schedulers - undermining the consistency the model is designed to create.

- **Seasonal load balancing.** Lower-frequency services (e.g. quarterly, 6-monthly) can cluster into the same period if left unmanaged, creating unachievable workload spikes and distorting revenue forecasting. The model will check that these services are spread evenly across the year - while applying a bias toward each service's existing schedule position, so that customers are not significantly shifted from when they currently expect their service.

- **Validated before committed.** Model outputs are reviewed by branch schedulers before being applied, and assessed against defined metrics at each tier. This keeps the business in control and avoids embedding flawed logic into a permanent system feature.

---

### 3.4 Workstream 3 - AGB Rollout (Pest)

Pest branches will be activated on AGB progressively as their data remediation is completed. Branches do not need to wait for the full grouping model to be finalised - those that want to move earlier can do so, with model-generated run structures applied once available.

For the initial rollout, model outputs will be applied via bulk import. Branches will review the proposed run structure, apply their local knowledge of customers and technician capabilities, and lock any services with fixed requirements before AGB is switched on. A support window will follow each branch activation.

---

### 3.5 Workstream 4 - Planned Capacity Review BI

The existing Booking Setup BI was built quickly for Hygiene and is not fit for purpose across both business streams. A rebuilt version will give branch managers and national operations real-time visibility of:

| Insight Area | Detail |
|---|---|
| **Technician Capacity** | Which technicians are over or under-utilised based on their scheduled workload, using forward-looking booking dates that update as setup changes are made. |
| **Technician Overlap** | Where the same site is being visited by multiple technicians on the same day, flagging consolidation opportunities. |
| **Schedule Coverage** | Whether all active service agreements have a booking setup generating work orders, surfacing any gaps. |

This BI will be a key tool for validating grouping model outputs and monitoring scheduling health on an ongoing basis.

---

### 3.6 Future Opportunity - Intraday Scheduling

A successful BSO implementation creates the conditions for a further scheduling improvement down the track. Once technicians have consistent, geographically coherent runs, an intraday scheduling tool could sequence each day's bookings in the most efficient order, insert realistic travel time between jobs, and manage same-day disruptions - automatically slotting priority work into gaps created by sick leave or cancellations.

This is not in scope for the current project, but it is the logical next step and its effectiveness depends directly on the quality of the run structure BSO creates.

---

### 3.7 Workstream 5 - System Implementation (Phase 2)

Once the grouping model has been validated through Phase 1, the next step is to work with Fusion 5 to implement it as a permanent, self-service feature within Flick 360. The scope of this work will be confirmed once Phase 1 outputs are available, but the key capabilities required are:

- The ability for branches to **lock specific services** to a fixed technician or day, ensuring agreed customer commitments are never overridden by an optimisation run.
- A **branch-facing review interface** where proposed schedule changes can be reviewed and approved before they take effect.
- **Configurable settings** allowing branches to adjust the model's priorities to reflect local conditions - without requiring development support.
- An **automated monthly optimisation run**, producing an updated run structure for branch review each month with changes effective the following period.
- Supporting system changes including a reduced work order generation window and improved bulk schedule management tooling, to be coordinated with the Agreement Restructure project.

---

## 4. Indicative Phasing

The below represents an indicative view of how the project is expected to progress. Specific timelines will be confirmed as the initiative gets underway and Fusion 5's involvement in Phase 2 is scoped.

### Phase 1

Phase 1 workstreams begin concurrently. The dependency that governs pace is data remediation - branches cannot activate AGB, and the model cannot produce reliable outputs, until their data meets the minimum standard.

| Stage | Key Activities |
|---|---|
| **Initiation** | Data audits begin across D1-D4. First branches identified for AGB activation. Model development begins against initial data export. BI requirements defined. |
| **Early rollout** | Remediation underway. First branches with clean data activate AGB. Tier 1 model logic developed and tested. BI in build. |
| **Main rollout** | Remediation substantially complete. Tier 1 validated; Tier 2 development begins. AGB activation continues across remaining branches. BI delivered to pilot branches. |
| **Consolidation** | Majority of branches on AGB. Tier 2 assessed against metrics. Model documented and ready for handover. BI nationally available. |

### Phase 2

Phase 2 scoping and sequencing will be confirmed once the Phase 1 model is validated and ready for handover to Fusion 5. Fusion 5 may begin contributing to system component design during Phase 1 to reduce lead time.

---

## 5. How We Will Measure Success

### 5.1 Success Criteria

| # | Criterion |
|---|---|
| SC1 | All Pest branches are live on AGB, with no net increase in manual scheduling effort at branch level. |
| SC2 | Data quality requirements are met for each branch prior to AGB activation. |
| SC3 | Branch-locked service constraints are never overridden by an optimisation run. |
| SC4 | Each model tier produces measurable improvement against at least one key metric relative to the prior baseline. |
| SC5 | Branches can adjust model settings and weightings without requiring development support. |
| SC6 | The model is sufficiently validated and documented to hand over to Fusion 5 for system implementation. |
| SC7 | The refreshed BI provides accurate, actionable capacity and overlap visibility across all branches. |
| SC8 | Month-to-month service day changes are minimised - the model only moves services when the routing benefit is material. |

### 5.2 Key Metrics

Metrics are captured at four points: before the project begins, after AGB is activated (before model optimisation), after each model tier is applied, and after Phase 2 go-live. This allows the business to isolate and communicate the value added at each stage.

| Metric | What it measures |
|---|---|
| **Site Visits** | Total unique site visits per month across the portfolio. Fewer is better. |
| **Site Overlap Rate** | Percentage of multi-service sites where all services fall on the same technician and day. Higher is better. |
| **Total Travel Distance / Technician / Day** | Estimated straight-line travel per technician per day including from home address. Lower is better. |
| **Daily Workload Variance** | How evenly scheduled hours are distributed across technicians in a branch each day. Lower variance is better. |
| **Locked Setup Compliance Rate** | Percentage of branch-locked services preserved correctly through each optimisation run. Should be 100%. |
| **Month-on-Month Change Rate** | Percentage of services with a changed technician or day between optimisation runs. Lower indicates better continuity. |
| **Technician Utilisation Range** | Spread between the most and least utilised technicians in a branch. Narrowing over time indicates improving balance. |
| **AGB Activation Rate** | Percentage of Pest branches with AGB live. |

---

## 6. Benefits

### 6.1 Immediate Time Savings

AGB removes the need for schedulers to manually create work orders each month. With approximately 23,000 Commercial Pest work orders due in April:

> **23,000 × 10 seconds ÷ 60 (seconds) ÷ (minutes)  = approximately 64 hours saved per month from generation alone.**

Beyond generation, adjusting runs in bulk is significantly faster than re-booking through the Scheduling Assistant - even before any optimisation is applied.

### 6.2 Less Time in the Field, More Time on Site

Grouping services by site and geography means technicians spend more time on-site and less time driving between unrelated jobs. Every site visit also carries a fixed overhead - parking, signatures, retrieving equipment - that applies once per site regardless of how many services are performed there. Consolidating multiple services to the same site on the same day absorbs that overhead across all of them, directly increasing the productive proportion of a technician's day.

### 6.3 Consistency for Technicians and Customers

Structured, repeatable runs mean technicians cover the same areas on the same days each cycle. Customers receive more predictable service. Technicians build familiarity with their sites, improving both efficiency and compliance outcomes.

### 6.4 Better Forecasting and Capacity Management

Spreading lower-frequency services evenly across the year - rather than letting them cluster into the same periods - produces a more consistent monthly workload and a more accurate revenue forecast. The refreshed BI gives managers live visibility of capacity and utilisation, so imbalances can be caught and corrected before they affect service delivery.

### 6.5 Lower Risk, Higher Confidence

Building and validating the model logic against real data before committing to a system build means the business can course-correct early. Fusion 5 receives a proven, documented model rather than a theoretical specification - reducing the risk of building something that does not reflect operational reality.

### 6.6 Platform for Future Improvement

A consistent, optimised run structure is the prerequisite for further scheduling capability - including the intraday scheduling tool outlined in Section 3.6. The value of this project compounds over time as each subsequent improvement builds on the foundation it creates.

---

## 7. Risks & Considerations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Data quality insufficient for accurate model output | High | High | Data remediation is a prerequisite per branch - model outputs are not used to generate a Setup Template until D1, D2, and D4 are resolved for that branch. |
| Branches activate AGB on unclean data | Medium | Medium | Minimum data standards enforced as an activation gate, including for early-adopter branches. |
| Model logic difficult to translate into a system build | Medium | High | Fusion 5 engaged early. Model is documented and validated before Phase 2 scoping begins, allowing implementation constraints to be identified in advance. |
| Service continuity vs optimisation quality tension | Medium | Medium | Stability bias is configurable - branches can increase optimisation aggressiveness where some disruption is acceptable. |
| Branch adoption resistance | Medium | Medium | Branches review and approve all model outputs before they are applied. Locked setups ensure customer commitments are always honoured. |
| Portfolio churn undermines optimised templates | High | Medium | Monthly rebalance cadence built into Phase 2. Ad hoc rebalance capability assessed for high-churn branches. |
| Bulk recurrence changes conflict with Agreement Restructure project | Medium | High | All bulk recurrence changes coordinated with the Agreement Restructure project before execution. |
| Scope creep into Tiers 3/4 delays Tier 1/2 delivery | Medium | High | Tiers 3/4 are out of scope for Phase 1, gated by a separate assessment following Tier 1/2 validation. |
