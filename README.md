# Anti-Political Dynasty Law Simulator

## A Multi-Axis Graph Network Engine and Decision-Support System for Evidence-Based Policymaking in the Philippines

---

## Overview

The **Anti-Political Dynasty Law Simulator** is an ex-ante Evidence-Based Policymaking (EBPM) decision-support system and graph simulation engine designed to model the structural, temporal, and geographic impacts of proposed Anti-Political Dynasty legislation in the Philippines.

Despite Article II, Section 26 of the 1987 Philippine Constitution explicitly mandating the prohibition of political dynasties, enabling legislation has suffered from nearly four decades of congressional impasse. This project bridges the gap between constitutional intent and statutory execution by providing lawmakers, election administrators, and policy researchers with a computational tool to evaluate legislative proposals before enactment.

---

## The Problem

Political dynasties represent one of the most enduring structural impediments to competitive democratic governance in the Philippines. Empirical studies consistently demonstrate that concentrated political power within family networks correlates with:

- Higher poverty incidence
- Lower local governance performance
- Distorted public procurement
- Suppression of political competition

Legislative efforts to enact an anti-political dynasty law have repeatedly stalled due to two primary challenges:

1. **Policy Parameter Conflict**: Lawmakers debate key statutory definitions—whether prohibitions should extend to the 2nd degree (k=2) or 4th civil degree (k=4), whether the ban applies only to simultaneous office-holding or includes immediate succession, and whether restrictions apply within the same LGU or extend vertically between national and local officials.

2. **Empirical Gap**: Policy debates occur in an empirical vacuum. Lawmakers and the Commission on Elections (COMELEC) lack computational tools to forecast how specific legislative drafts will alter candidate eligibility, create municipal council vacancies, or shift administrative verification workloads.

---

## The Solution

This project constructs a **network-graph decision-support system** that models the impact of proposed bills—such as House Bill No. 8389 and various Senate proposals—against a 24-year longitudinal dataset of Philippine election winners (2001–2025) integrated with multi-source kinship network graphs.

### Key Features

- **3-Tiered Policy Note Architecture**: Models impacts at national, national-to-subnational, and intra-local levels
- **5-Axis Legislative Rule Engine**: Parameterizes bills across prohibited civil degree, temporal/succession mode, jurisdictional scope, kinship definitions, and elective scope
- **8 Legislative Scenarios**: Tests proposals ranging from House Bill No. 8389 to maximalist Senate reform proposals
- **Interactive Policy Sandbox**: Renders spatial heatmaps and kinship network graphs in real time

---

## System Architecture

### 3-Tiered Policy Note Architecture

| Tier | Scope | Positions Covered |
|------|-------|-------------------|
| **PN1: National Level** | Horizontal kinship density | President, VP, Senators, House Representatives |
| **PN2: National-to-Subnational** | Vertical power projection | National Officials ↔ Governors, Mayors & Vice Mayors |
| **PN3: Intra-Local Municipal** | Internal LGU dynamics | Mayors, Vice Mayors ↔ Sangguniang Bayan Councilors |

### 5 Legislative Policy Axes

1. **Prohibited Civil Degree (k)**: Sets kinship distance threshold (k ∈ {2, 3, 4})
   - k=2: Spouses, Parents, Children, Siblings, Grandparents, Grandchildren
   - k=3: Adds Uncles, Aunts, Nephews, Nieces
   - k=4: Adds First Cousins

2. **Temporal & Occurrence Mode**: Simultaneous Prohibition, Immediate Succession, Position-Swapping, Cooling-Off Periods

3. **Jurisdictional & Geographic Scope**: Same Jurisdiction Only, Vertical Interlock Ban, Nationwide Blanket

4. **Kinship Definition**: Consanguinity (blood), Affinity (marriage), Common-Law/Cohabiting unions, Illegitimate lines

5. **Elective Scope & Exemptions**: Party-List nominees, Barangay-level officials

---

## Scenario Testing Matrix

| Scenario | Name | Degree (k) | Temporal Scope | Jurisdictional Scope |
|----------|------|------------|----------------|----------------------|
| S1 | House Baseline (HB 8389) | k=2 | Simultaneous Only | Same LGU/District |
| S2 | HB 8389 + Succession | k=2 | Simultaneous & Immediate Succession | Same LGU/District |
| S3 | Senate Moderate (Vertical) | k=2 | Simultaneous Only | Vertical District Interlock |
| S4 | Senate Committee Standard | k=2 | Simultaneous & Immediate Succession | Vertical District Interlock |
| S5 | Expanded Kinship (3rd Degree) | k=3 | Simultaneous & Immediate Succession | Vertical District Interlock |
| S6 | Comprehensive Reform (4th Degree) | k=4 | Simultaneous & Immediate Succession | Vertical District Interlock |
| S7 | Nationwide 2nd Degree | k=2 | Simultaneous & Immediate Succession | Nationwide Blanket |
| S8 | Maximalist Reform (SK Standard) | k=4 | Simultaneous & Succession + 1-Term Buffer | Nationwide Blanket |

---

## Analytical Metrics

The simulation engine calculates four primary metrics:

### 1. Disqualification & Vacancy Creation Rates
- **DQ_Rate**: Percentage of 2025 candidates rendered ineligible
- **Vac_Rate**: Proportion of elective seats left open for non-dynastic entrants

### 2. Dynastic Seat Occupancy Rate (DSOR)
Measures historical family concentration for any permanent seat across the 24-year dataset. A seat with DSOR ≥ 0.75 indicates near-total family monopoly.

### 3. Term-Limit Relay Rate (TLRR)
Measures the frequency with which 3-term-capped officials successfully hand over their exact seat to a relative in the subsequent election cycle.

### 4. Council Monopoly Dissolution Index (CMDI)
Evaluates local executive-legislative capture by measuring the reduction in multi-seat family clusters within a single Sangguniang Bayan.

---

## Database Schema

### Core Tables

| Table | Purpose |
|-------|---------|
| `nodes_politicians` | Standardized individual profiles with maternal maiden names for consanguinity resolution |
| `seats_master` | Permanent elective positions independent of cycle incumbents |
| `electoral_history` | Electoral results across 9 cycles (2001–2025) |
| `edges_kinship` | Verified familial relationships between politicians |

---

## Technical Stack

| Component | Technology |
|-----------|------------|
| Database & Processing | Python (pandas, NetworkX, SQLAlchemy), PostgreSQL |
| API Layer | FastAPI (high-speed JSON payload filtering) |
| Frontend | React (Next.js), Cytoscape.js (kinship graphs), Leaflet.js (PSGC choropleth mapping) |

---

## Implementation Roadmap

### Phase 1: Data Ingestion & Schema Mapping
- Standardize `nodes_politicians`, `seats_master`, `electoral_history` (2001–2025), and `edges_kinship`

### Phase 2: PN1 Simulation Sandbox
- Run Scenarios S1–S8 on national nodes to validate disqualification functions

### Phase 3: Multi-PN Cascading Execution
- Expand queries to execute PN2 (vertical interlocks) and PN3 (municipal council capture)

### Phase 4: Policy Brief Publication & Microsite Deployment
- Package empirical results into Policy Notes 1, 2, and 3
- Launch interactive simulation dashboard for legislative stakeholders

---

## Key Policy Findings

### Exposing Loopholes in HB 8389
The simulation reveals that HB 8389 (Scenario S1) leaves vertical district interlocks untouched—allowing a District Representative parent and Municipal Mayor child to hold office concurrently without statutory conflict.

### Quantifying the Impact of Succession Bans
Adding immediate succession prohibitions (Scenarios S2 and S4) yields significant reductions in dynastic persistence by blocking direct parent-to-child term rotation.

### Administrative Feasibility for COMELEC
- **k=2 within same LGU**: Requires verifying standard birth and marriage certificates
- **k=4 with vertical interlocks**: Requires cross-jurisdictional graph matching across thousands of candidates

The simulator provides COMELEC with empirical estimation of candidate verification processing times and identifies data-integration requirements between local election officers and the Philippine Statistics Authority (PSA).

---

## Theoretical Framework

This research grounds the computational simulation engine in four established frameworks:

1. **Regulatory Impact Assessment (RIA)**: Ex-ante evaluation of systemic effects before enactment
2. **Digital Era Governance (DEG)**: Integration of data analytics and computational modeling into administrative processes
3. **Local Executive-Legislative Capture**: Modeling intra-local networks to measure restoration of local legislative independence
4. **Bureaucratic Integrity vs. Structural Patronage Networks**: Quantifying kinship graph density as a metric for structural patronage risk

---

## Project Significance

By integrating 24 years of electoral history with kinship network analysis, this research transforms the long-standing political debate over anti-dynasty legislation into an empirical, data-driven science. The simulator provides public administrators, election officials, and lawmakers with an ex-ante evaluation tool to measure the precise impact of legislative choices.

Ultimately, this decision-support system bridges the gap between constitutional intent and statutory execution, advancing evidence-based policymaking in Philippine public administration.

---

## Contributing

This project welcomes contributions from researchers, developers, and policy analysts interested in:

- Electoral data standardization and validation
- Graph database optimization
- Policy parameter modeling
- Visualization and UI/UX design
- Policy brief writing and stakeholder engagement

---

## License

[To be determined]

---

## Contact

For inquiries regarding this research project, please contact the project team.

---

*"By parameterizing bill proposals across five policy axes and eight test scenarios, the simulator provides public administrators, election officials, and lawmakers with an ex-ante evaluation tool to measure the precise impact of legislative choices."*
