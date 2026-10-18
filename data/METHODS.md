# Methodology — Anti-Political-Dynasty Data Pipeline

A comprehensive, multi-signal approach to mapping political kinship networks across the Philippines at three independent administrative levels, with transparent evidence tiers for every claim.

---

## 1. Overview

### 1.1 Three independent datasets

The pipeline produces **three structurally separate datasets** that share a common person-ID namespace (`POL-PH-######`) and a common edge schema, but are not merged in the data layer. Cross-dataset analysis is a **dashboard concern** — joined at query time on `person_id`.

| Dataset | Scope | Nodes | Edges | Purpose |
|---|---|---|---|---|
| **PN1** `PN1_national_level/` | National (President, VP, Senators, HOR) | 344 | 116 | Top-tier national dynasties |
| **PN2** `PN2_national-subnational_level/` | National + subnational (Governors, HOR) | 3,552 | 2,507 | Vertical dynastic chains |
| **PN3** `PN3_inter-intra_local_level/` | Local (Provinces, Cities, Municipalities) | 17,805 | 2,543 | Horizontal dynasties at LGU scale |

**Why separate?** Each dataset represents a different political tier with **different data-availability profiles**. National politicians are heavily covered by journalistic sources; local politicians are documented only in LGU-level incumbent files. Merging them into a single graph would obscure which edges derive from which evidence base.

### 1.2 Shared schema

Every edge in every dataset carries:

| Column | Type | Meaning |
|---|---|---|
| `edge_id` | string | Sequential identifier `EDGE-######` |
| `person_a_id`, `person_b_id` | string | `POL-PH-` prefixed IDs |
| `relation_label` | string | Semantic relation (Sibling, Parent_Child, etc.) |
| `civil_degree` | int | Philippine Civil Code degree (1 = parent/child, 2 = sibling, 4 = first cousin, 6 = distant) |
| `kinship_type` | string | `Consanguinity` (blood) or `Affinity` (marriage) |
| `source_document` | string | Which pipeline stage produced the edge |
| `is_ground_truth` | bool | `True` only for edges at P=1.00 |
| `probability` | float | Confidence in [0, 1] |

PN3 edges additionally carry **four diagnostic columns** (`fuzzy_verdict`, `structural_verdict`, `pulitiklan_verdict`, `consensus_level`) that expose the evidence trail per edge.

### 1.3 Data sources

| Source | Type | Coverage | Used for |
|---|---|---|---|
| `Provincial_incumbents.xlsx` | LGU-level | 992 provincial officials | PN3 node extraction |
| `city_incumbents.xlsx` | LGU-level | 1,982 city officials | PN3 node extraction |
| `Municipal_incumbents.xlsx` | LGU-level | 14,831 municipal officials | PN3 node extraction |
| `PSGC-3Q-2026-Publication-Datafile.xlsx` | Reference | All 1,717 LGUs | LGU resolution for all datasets |
| `ASoG-POLITICAL-DYNASTIES-DATASET-V2016.xlsx` | Curated | Ateneo School of Government verified dynasties | External verification (Method 4) |
| `CSP-65-STATISTICAL-INVENTORY...pdf` | Official | Commission on Audit inventory | External verification (Method 4) |
| `political_dynasty_v8.5.csv` | Research | 11 MB curated dynasty corpus | External verification (Method 4) |
| `NLE_Winners_2004-2025.csv` | Electoral | 17 MB national/local election winners | Name index for verification |
| `# PULITIKLAN — Visayas coverage.txt` | Journalistic | 442 KB verified Visayas research | **Primary external verification** |
| `luzon-research.md` | Journalistic | 231 KB verified Luzon research | **Primary external verification** |

**Note on Pulitiklan:** Mindanao has no Pulitiklan coverage. Mindanao edges are classified as `baseline_mindanao` — preserved without penalty, explicitly flagged as outside external verification.

---

## 2. Pipeline architecture

### 2.1 High-level flow

```
Source files (XLSX, PDF, TXT)
    │
    ▼
┌──────────────────────────────────────────┐
│  Stage 1 — Node & Seat Extraction        │
│  • LGU resolution via PSGC               │
│  • Name normalization                    │
│  • 100% PSGC match target                │
└──────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────┐
│  Stage 2 — Rule-Based Edge Generation    │
│  • Surname/middle/suffix patterns        │
│  • 4-tier geographic hierarchy           │
│  • Candidate edges with base probabilities│
└──────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────┐
│  Stage 3 — Four-Signal Validation        │
│  Signal A: Fuzzy name matching           │
│  Signal B: Structural metrics            │
│  Signal C: Pulitiklan cross-validation   │
│  Signal D: Deterministic rule patterns   │
└──────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────┐
│  Stage 4 — Consensus Voting              │
│  • 8-level priority ladder               │
│  • Every edge gets one consensus label   │
│  • Production edge file ready            │
└──────────────────────────────────────────┘
    │
    ▼
Dashboard (joins PN1/PN2/PN3 on person_id)
```

### 2.2 Stage 1 — Node & seat extraction

**Purpose:** convert source incumbent lists into a canonical person registry with verified LGU assignments.

**Process:**

1. **Name normalization** — title case with Philippine conventions (particles `Dela`, `Del`, `San` lowercase; suffixes `JR`, `III` uppercase)
2. **LGU resolution** — for each person, match `(Region, Province, City/Municipality)` against the PSGC hierarchy
3. **Fallback hierarchy** — `{province}_{city}` → `{region}_{city}` → `NCR_{city}` → `fallback[city]` → `""`
4. **Alias resolution** — apply province aliases (`NORTH COTABATO` → `COTABATO`, `WESTERN SAMAR` → `SAMAR`) and region aliases (`ARMM` → `BARMM`, `REGION IV-A` → `CALABARZON`) before lookup
5. **Footnote stripping** — remove PSA publication markers (`Lucenaa/` → `LUCENA`) via regex
6. **Seat generation** — derive seat records from LGU level (Province → Governor + Vice Gov + Board Members; City → Mayor + Vice Mayor + Councilors; Municipality → Mayor + Vice Mayor + Councilors)

**PN3 result:** 17,805 nodes at **100% PSGC match rate** (0 unmatched after Lucena fix).

### 2.3 Stage 2 — Rule-based edge generation

**Purpose:** generate candidate kinship edges using structural patterns of Philippine naming conventions.

**Scoring rules:**

| Pattern | Signal | Base probability |
|---|---|---|
| Same LGU + same last name + same middle + different first | Sibling signature | **1.00** (ground truth) |
| Same LGU + same last name + suffix chain (Jr/Sr/III) | Parent-child namesake | **1.00** (ground truth) |
| Same LGU + bidirectional interlock (A.mid = B.last AND B.mid = A.last) | Married couple | **1.00** (ground truth) |
| Same LGU + same last name only | Distant kin | 0.60 |
| Same LGU + same middle only | Shared maternal line | 0.55 |
| Cross-LGU (same province) + sibling signature | Cross-LGU sibling | 0.90 |

**Geographic tiers:**

| Tier | Definition | Geographic bonus |
|---|---|---|
| T1 | Same LGU | +0.30 |
| T2 | Different LGU, same province | +0.10 |
| T3 | Different province, same region | +0.05 |
| T4 | Different region | +0.02 |

**Cross-LGU sibling bonus:** +0.06 for T2/T3/T4 siblings, bringing cross-provincial siblings to P=0.96.

**PN3 result:** 2,699 candidate edges (386 ground-truth at P=1.00).

### 2.4 Stage 3 — Four-signal validation

#### Signal A — Fuzzy name matching

**Purpose:** catch variant spellings missed by exact matching, and filter common-surname noise.

**Implementation:**
- **Jaro-Winkler similarity** on normalized names (uppercase, diacritics stripped, suffix stripped)
- **Collapse matching** (`DELA CRUZ` = `DELACRUZ` after whitespace removal)
- **Soundex/Metaphone** for phonetic variants
- **Threshold gates:** JW ≥ 0.92 = `variant_confirmed`; 0.85 ≤ JW < 0.92 = `variant_likely`; phonetic-only disabled (too noisy)

**Part A — validation:** demote `Distant_Kin`/`Shared_Maternal_Line` edges on common surnames (CRUZ, REYES, TAN, etc.) by −0.15/−0.10. Edges below P=0.50 are dropped.

**Part B — expansion:** discover new edges via variant surname spellings within the same LGU. Requires `variant_confirmed` OR `variant_likely` + middle-name match.

**Dynastic exceptions:** common-surname edges restored when surname is documented as dynastic in that province (`SINGSON` in Ilocos Sur, `TAN` in Cebu, `AMPATUAN` in Maguindanao).

**PN3 result:** 182 noise edges dropped, 26 legitimate variants discovered → **2,543 edges**.

#### Signal B — Structural metrics

**Purpose:** validate edges via graph topology.

**Why not Leiden?** Leiden community detection was evaluated but found **inapplicable** on PN3's graph: 49% of components are size-2 dyads (no internal structure), average degree 1.41 (too sparse for community splitting). All resolutions/seeds converged to identical partitions — the "100% strong" result was a tautology.

**Replacement — edge-level metrics:**
- **Common-neighbor count** (triangles)
- **Jaccard overlap** of neighbor sets
- **Adamic-Adar score** (rarer shared neighbors weighted higher)
- **Bridge detection** (would edge removal disconnect the component?)
- **Endpoint clustering coefficients**

**Verdict hierarchy:**
- `strong_cluster` (Jaccard ≥ 0.40) → confidence 0.90
- `cluster_confirmed` (Jaccard ≥ 0.20) → confidence 0.75
- `weak_cluster` → confidence 0.50
- `chain` (no triangles) → confidence 0.30
- `bridge` (disconnects component) → confidence 0.15
- `isolated` (dyad) → confidence 0.00

**Design principle:** absence of structural evidence **does not penalize** — dyads are legitimate (two isolated siblings with no other kinship edges). `isolated` edges rely on other signals.

**PN3 result:** 1,106 edges confirmed (43.5%), 1,437 unverifiable (56.5%).

#### Signal C — Pulitiklan external verification

**Purpose:** cross-reference edges against published journalism.

**Sources:**
- `# PULITIKLAN — Visayas coverage and.txt` (442 KB, 3,723 sentences)
- `luzon-research.md` (231 KB, 1,930 sentences)

**Two-stage matching:**
1. **Full-name index** (72,715 variants across all datasets) — precise matching
2. **Surname index** (9,963 unique surnames) — broad recall for "mentioned"

**Kinship pair extraction:** sentences with ≥2 full-name matches **or** family-plural references (`"the Aquinos"`, `"Marcos family"`) + kinship keyword (`"father"`, `"married to"`, `"cousin"`, `"family"`).

**Verdicts:**
- `verified_explicit` — explicit kinship statement found
- `verified_mentioned` — both names appear in Pulitiklan
- `contradicted` — Pulitiklan says "not related"
- `baseline_mindanao` — Mindanao region (Pulitiklan has no coverage)
- `unverifiable` — Luzon/Visayas but not in Pulitiklan

**PN3 result:** 99 verified explicit, 546 verified mentioned, 978 baseline Mindanao, 917 unverifiable, **3 contradicted** (investigated as duplicate records, not kinship errors).

#### Signal D — Deterministic rule patterns

The stage-2 ground-truth edges (sibling signature, suffix chain, bidirectional interlock) are re-tagged `Rule_Based_GT` in the final consensus — treated as high-confidence anchors.

### 2.5 Stage 4 — Consensus voting

**Priority ladder** (highest priority wins on conflict):

| Priority | Consensus Level | Rule | Final P | GT? |
|---|---|---|---|---|
| 1 | `Contradicted` | Pulitiklan denies kinship | 0.10 | ❌ |
| 2 | `Duplicate_Record` | Same person under different IDs | 0.10 | ❌ |
| 3 | `Verified_Pulitiklan` | External source confirms | **1.00** | ✅ |
| 4 | `Rule_Based_GT` | Deterministic rule pattern | **1.00** | ✅ |
| 5 | `Baseline_Mindanao` | Mindanao, Pulitiklan silent | preserve rule P | ❌ |
| 6 | `Consensus_High` | 2+ orthogonal signals agree | 0.95 | ❌ |
| 7 | `Single_Method` | 1 signal confirms | preserve rule P | ❌ |
| 8 | `Low_Confidence` | 0 signals confirm | preserve rule P | ❌ |

**Why Contradicted has higher priority than Verified:** when sources conflict, the safer choice (skepticism) wins for a political-integrity dataset.

**Why Rule_Based_GT beats Baseline_Mindanao:** a Mindanao edge that *also* matches a deterministic sibling pattern has stronger evidence than "Mindanao + same surname" alone. The `pulitiklan_verdict` column still says `baseline_mindanao` for Mindanao-specific filtering.

**Three-signal vote** (for priority 6-8):
```
votes = (rule_probability >= 0.85) +
        (fuzzy_verdict in {variant_confirmed, variant_likely}) +
        (structural_confidence >= 0.75)
```

**PN3 result:**

| Level | Count | % |
|---|---|---|
| Verified_Pulitiklan | 99 | 3.9% |
| Rule_Based_GT | 359 | 14.1% |
| Baseline_Mindanao | 844 | 33.2% |
| Consensus_High | 33 | 1.3% |
| Single_Method | 505 | 19.9% |
| Low_Confidence | 696 | 27.4% |
| Contradicted | 3 | 0.1% |
| Duplicate_Record | 4 | 0.2% |
| **Ground truth total** | **458** | **18.0%** |

---

## 3. Design principles

### 3.1 Multi-signal consensus, not single-method

Every edge is evaluated by **four orthogonal signals**, each attacking the problem from a distinct angle:

| Signal | Question asked | Blind spot |
|---|---|---|
| Rule-based | Do names follow structural patterns? | Typographic variants |
| Fuzzy | Are names character-level matches? | Graph context |
| Structural | Does graph topology support the edge? | Dyads |
| Pulitiklan | Does an external source confirm? | Mindanao, obscure LGUs |

**No single signal is trusted alone.** Consensus requires ≥2 signals for "high confidence." External verification overrides everything.

### 3.2 Absence of evidence ≠ evidence of absence

Structural `isolated` edges and Pulitiklan `baseline_mindanao` edges are **preserved, not penalized** — because they are legitimately unverifiable, not confirmed false. The distinction matters:

- **Confirmed false** → `Contradicted`, P=0.10, hidden
- **Unverifiable** → preserved at rule-based P, marked as `Single_Method` or `Low_Confidence`

### 3.3 Explicit data-gap policy

Pulitiklan has no Mindanao coverage. Rather than dropping Mindanao edges (which would hide 38% of PN3) or treating them as false negatives, the pipeline **explicitly tags** them `baseline_mindanao`. Downstream consumers know exactly what evidence exists (or doesn't) for each region.

### 3.4 Transparency per edge

Every production edge carries **four diagnostic columns** plus a `consensus_level`. The dashboard can display, filter, and explain every connection:
- "Why is this edge shown?" → check `signal_count` and consensus level
- "How confident am I?" → check `probability` and `is_ground_truth`
- "What's the evidence?" → check `fuzzy_verdict`, `structural_verdict`, `pulitiklan_verdict`

---

## 4. Confidence assessment

### 4.1 Layer-by-layer

| Layer | Confidence | Basis |
|---|---|---|
| **Nodes** | **99.9%** | 100% PSGC-matched; 0.04% duplicate rate |
| **Seats** | **99.5%** | Directly derived from nodes + PSGC |
| **Edges (overall)** | **~55–65%** | Weighted across confidence tiers |
| **Ground-truth edges (458)** | **~90%** | Pulitiklan-verified + deterministic patterns |
| **Overall recall** | **~40–60%** | Estimated; not directly measured |

### 4.2 Composite confidence

Weighted across all dimensions: **~72%**. But this number conflates very-high-confidence layers (nodes, seats) with genuinely-uncertain ones (edges), so layer-specific reporting is preferred.

### 4.3 Use-case mapping

| Question | Confidence | Reason |
|---|---|---|
| "Who holds office X?" | 99.9% | Direct from source |
| "Is this pair *definitely* related?" | ~90% (if GT) | Pulitiklan or deterministic |
| "Show all kinship" | ~65% | Includes all tiers |
| "How many dynasties total?" | ~40–60% recall | Undercounting is likely |

---

## 5. Limitations

### 5.1 Recall is unknown

The 458 ground-truth edges represent **confirmed true positives**, but the pipeline cannot measure how many **true kinship connections it missed**. Estimated recall of 40–60% means for every confirmed edge, 1–1.5 real edges are likely missing — mostly distant cousins, cross-region family ties, and Mindanao dynasties outside Pulitiklan's coverage.

### 5.2 Maternal-maiden signal at scale (underexploited)

The middle-name-as-mother's-maiden convention is **unique to the Philippines** in Southeast Asia. This signal catches **cross-surname kinship** that surname-only matching misses. However, the pipeline has **not isolated** the maternal-maiden contribution from the overall signal — a v2 analysis opportunity that could be a genuine research contribution.

### 5.3 Mindanao verification gap

38.5% of PN3 edges are `baseline_mindanao` — preserved but unverified. Expanding Pulitiklan coverage to Mindanao (or adding ASoG/COA coverage) would convert this to verified evidence and raise GT to ~30%.

### 5.4 Duplicate nodes (0.04%)

8 confirmed duplicate pairs in PN3 (four exact-name, four typo variants). These generate spurious intra-duplicate edges, which the consensus logic correctly classifies as `Duplicate_Record` and excludes from the default view. A full fix requires node-level deduplication + pipeline re-run.

### 5.5 No ablation study

The pipeline's four signals are **demonstrably orthogonal** (each catches edges the others miss), but the **ensemble has not been benchmarked against single-method baselines**. Without an ablation study, the claim "combined > best single method" is plausible but unproven. This is the highest-ROI addition for a publication-grade methodology.

---

## 6. Novelty assessment

### 6.1 What is not novel

Every individual component is well-established in the literature:

- Jaro-Winkler / Soundex / Metaphone — 1960s–1990s record linkage
- Rule-based kinship scoring — standard genealogical inference
- Edge-level structural metrics — network science since Adamic-Adar (2003)
- Consensus voting — ML ensembles since Random Forests (2001)
- Civil degree of kinship — Philippine Civil Code (1949)
- External source verification — standard data validation

**A reviewer would correctly call the pipeline "standard methods."**

### 6.2 What is novel

| Contribution | Novelty |
|---|---|
| **Scale** — 17,805 local officials, all 1,717 LGUs | No public dataset covers full local level |
| **4-tier geographic hierarchy** | Distinguishes horizontal (same LGU) from vertical (cross-province/region) dynasties — a conceptual refinement over flat models |
| **Maternal maiden name as first-class signal** | Rarely done at scale; unique to Philippine naming |
| **Mindanao baseline policy** | Explicit data-gap handling — methodologically honest, rarely done |
| **4-signal consensus with priority ladder** | Specific priority ordering reflects domain reasoning |
| **Pulitiklan as external ground truth** | Journalism-as-validation is uncommon in ML pipelines |

### 6.3 Publication venues

| Audience | Fit |
|---|---|
| **Dashboard / product** | Novelty irrelevant — utility is what matters |
| **Philippine political science journals** (PJPS, Kasarinlan) | **Publishable** — the dataset itself is a contribution |
| **Regional CS/ML venues** (Philippine Computing Society, PAAS) | **Publishable** — scale + framework + honest data-gap handling |
| **Dataset venues** (Nature Scientific Data, KDD Datasets) | **Publishable** — first comprehensive PH kinship dataset |
| **Top-tier ML** (NeurIPS, KDD, WWW) | **Not novel enough without ablation + accuracy benchmarks** |

**Recommended framing:** "First comprehensive multi-tier political kinship dataset for the Philippines, built via 4-signal consensus with explicit regional data-gap handling." This is a **dataset paper**, not a method paper — and that's the strongest defensible claim.

---

## 7. Reproducibility

### 7.1 Full pipeline (PN3 example)

```powershell
# 1. Node extraction — 17,805 nodes, 100% PSGC
python PN3_inter-intra_local_level\src\extract_inter-intra_local.py

# 2. Seat generation — 17,805 seats, 0 gap
python PN3_inter-intra_local_level\src\extract_inter-intra_local_seats.py

# 3. Rule-based edges — 2,699 candidate edges
python PN3_inter-intra_local_level\src\gnn_probabilistic_edges_PN3.py

# 4. Fuzzy validation — 2,543 edges
python PN3_inter-intra_local_level\src\fuzzy_validate_edges.py

# 5. Structural metrics — enrichment, no edge changes
python PN3_inter-intra_local_level\src\structural_metrics_validate.py

# 6. Duplicate detection — 8 confirmed pairs
python PN3_inter-intra_local_level\src\find_duplicate_nodes.py

# 7. Pulitiklan cross-validation — 99 verified, 978 baseline
python PN3_inter-intra_local_level\src\cross_validate_pulitiklan.py

# 8. Final consensus — 458 GT edges, 18.0%
python PN3_inter-intra_local_level\src\final_consensus_edges.py
```

### 7.2 Output files

| File | Purpose | Dashboard reads? |
|---|---|---|
| `inter-intra_local_edges_FINAL.csv` | **Production edge file** | ✅ Yes |
| `inter-intra_local_edges_FINAL_gt.csv` | 458 GT edges only | For papers/validation |
| `inter-intra_local_edges_FINAL_audit.csv` | Flagged edges (contradicted + duplicates + low-conf) | For manual review |
| `final_consensus_report.txt` | Full distribution + samples | Human reference |

### 7.3 Idempotency

All scripts are **fully deterministic and idempotent**:
- Re-running produces identical output given identical input
- Master files are never blindly appended — existing records are dropped before replacement
- Edge IDs are re-sequenced deterministically (`EDGE-005000` onwards)

---

## 8. Known issues (v1)

### 8.1 Duplicate nodes

8 confirmed duplicate pairs in PN3 (0.04% of 17,805). Full list in `duplicate_candidates.csv`. **Scheduled fix for v2** via node-level deduplication + pipeline re-run.

### 8.2 Lucena footnote marker

PSA 3Q-2026 publishes Lucena City's name as `City of Lucenaa/` — the `a/` is a footnote marker for "highly urbanized city" glued to the name string. Resolved via `MANUAL_PSGC_OVERRIDES` in the node extractor and via footnote-stripping in `clean_location_name`. This class of bug is now handled for all HUCs.

### 8.3 PN2 header artifact

`national+subnational_nodes.csv` contains 1–3 header-artifact rows (`person_id = "person_id"`). This causes `set_index` crashes in downstream scripts. Sanitizer added to `fuzzy_validate_edges_PN2.py` and `find_duplicate_nodes_PN2.py` — drops these rows before processing. **Source-level fix scheduled for v2.**

---

## 9. Roadmap (v2)

| Priority | Task | Effort | Impact |
|---|---|---|---|
| **High** | Ablation study — drop each signal, measure precision/recall | 1 week | Proves ensemble > single-method |
| **High** | Precision/recall vs. ASoG 2016 gold standard | 3–4 days | Replaces estimates with measurements |
| **Medium** | Node-level deduplication + pipeline re-run | 1 day | Eliminates 8 duplicate nodes |
| **Medium** | Expand Pulitiklan coverage to Mindanao | 2–3 weeks research | Converts 844 baseline → verified |
| **Low** | Maternal-maiden ablation analysis | 1 week | Novel research contribution |
| **Low** | Refactor common pipeline code across PN1/PN2/PN3 | 2 days | Maintainability |

---

## 10. Citation (if published)

> **[Authors]. (2026). *Anti-Political-Dynasty: A Multi-Signal Kinship Graph of Philippine Elected Officials.* Dataset, [venue].**

**Suggested abstract:**

> We present a comprehensive multi-tier kinship graph of Philippine elected officials covering 17,805 local politicians across all 1,717 LGUs, plus 3,552 national and subnational officials. Edges are generated via rule-based scoring (surname, maternal maiden name, generational suffixes, geographic proximity) and validated by four orthogonal signals: fuzzy name matching, graph structural metrics, and external verification against Pulitiklan journalistic research and the Ateneo School of Government dynasty dataset. A priority-ordered consensus ladder produces 458 ground-truth edges at P=1.00 (18% of total), with all remaining edges labeled by evidence tier. Our pipeline explicitly handles the Mindanao data-verification gap — Mindanao edges are preserved as `baseline_mindanao` rather than penalized, providing honest uncertainty quantification. The dataset is designed for anti-political-dynasty analysis and interactive dashboard exploration.

---

## Appendix A — Civil degree reference

| Degree | Relationship | Pipeline usage |
|---|---|---|
| 1 | Parent, child, spouse | `Parent_Child`, `Spouse` |
| 2 | Sibling, grandparent, grandchild, in-law | `Sibling`, `In_Law` |
| 4 | First cousin | `Shared_Maternal_Line` |
| 6 | Distant kin (same surname only) | `Distant_Kin` |

## Appendix B — PSGC hierarchy

```
Region (18 total)        10-digit PSGC, first 2 digits
    └── Province (82)    first 5 digits
            └── City / Municipality (1,488+147)
                    └── Barangay (not modeled)
```

For NCR (region code `13`), all cities are parented directly to the region — no intermediate province.

## Appendix C — Naming conventions

| Convention | Example | Signal |
|---|---|---|
| Given + mother's maiden (middle) + father's surname | `Maria Santos Cruz` | Middle = maternal family |
| Suffix chain (Jr, III) | `Juan Cruz Jr.` | Generational parent-child |
| Hyphenated surnames | `Mangudadatu-cerebo` | Marriage/lineage adoption |
| Particle prefixes | `Dela Cruz`, `Del Rosario`, `San Juan` | Multi-token surnames requiring whitespace normalization |

---

**Document status:** Complete methodology for v1 production. Revisions should be tracked in `METHODS.md` changelog.

# Methodology: Network Construction, Multi-Vector Kinship Inference, and Consensus Modeling for National–Subnational Dynastic Networks (PN2)

---

## 1. Overview and Architectural Framework

To map and analyze political dynasties across national and subnational levels in the Philippines, we construct an empirical network graph $G = (V, E)$, where $V$ represents political actors (nodes) and $E$ represents inferred or verified kinship connections (edges). The pipeline employs a multi-stage architecture designed to ingest raw candidate linkages, resolve orthographic variations, validate topological structure, integrate external cross-validation data, and apply a multi-signal consensus classification model.

```
+---------------------------+     +-------------------------------+
|  Raw Node Datasets (PN2)  | --> |  Sanitization & Deduplication | --> 3,550 Clean Nodes
+---------------------------+     +-------------------------------+

+---------------------------+     +-------------------------------+
| Raw & Merged Edge Candidates| -> | Fuzzy & Phonetic Matching v2  | --> 2,504 Candidate Edges
+---------------------------+     +-------------------------------+

                                                │
                                                ▼
                                  +-------------------------------+
                                  | Structural Metric Validation  |
                                  +-------------------------------+
                                                │
                                                ▼
                                  +-------------------------------+
                                  | Pulitiklan Cross-Validation   |
                                  +-------------------------------+
                                                │
                                                ▼
                                  +-------------------------------+
                                  | Multi-Signal Consensus Engine |
                                  +-------------------------------+
                                                │
                                                ▼
                                  +-------------------------------+
                                  | Undirected Canonicalization   | --> 1,252 Canonical Edges
                                  +-------------------------------+

```

---

## 2. Node Dataset Sanitization and Standardization

The node registry $V$ was assembled by merging national electoral data (PN1) with subnational municipal and provincial leadership rosters (PN2).

1. **Concatenation Artifact Removal**: Raw source concatenation introduced header rows into data fields. Records where `person_id` failed to match the canonical identifier pattern `POL-PH-[0-9]{6}` were identified and dropped.
2. **Entity Normalization**: Each node profile was standardized across the following attributes:
* **Full Name Normalization**: Strip diacritics (Unicode NFD decomposition), remove standard generational suffixes (e.g., *JR*, *SR*, *III*), and normalize whitespace.
* **Subnational Geographic Tagging**: Standardize Local Government Unit (LGU) identifiers to 10-digit Philippine Standard Geographic Codes (PSGC).


3. **Registry Resolution**: Duplicate `person_id` entries were deduplicated using a priority retention rule, yielding a clean node registry of $\vert{}V\vert{} = 3,550$ unique political actors.

---

## 3. Multi-Vector Kinship Edge Inference

Candidate kinship ties $E_{\text{cand}}$ were generated through three complementary detection vectors: rule-based maternal/paternal surname matching, phonetic and string-distance variant resolution, and local geographic blocking.

### 3.1. Fuzzy String Matching and Phonetic Blocking

To capture spelling variations, typos, and naming conventions in election records, candidate pairs within the same LGU (blocking by 10-digit PSGC) were evaluated using Jaro-Winkler similarity ($JW$) alongside Soundex and Metaphone algorithms:

$$\text{Sim}(s_1, s_2) = JW(s_1, s_2)$$

Edge candidates were classified into string-matching confidence tiers:

* **Variant Confirmed**: $JW(s_1, s_2) \ge 0.92$ or identical character composition under whitespace collapse.
* **Variant Likely**: $0.85 \le JW(s_1, s_2) < 0.92$.
* **Phonetic Match**: $0.75 \le JW(s_1, s_2) < 0.85$ with matching Soundex or Metaphone representations.

### 3.2. Surname Frequency Discounting and Dynastic Exceptions

High-frequency Philippine surnames (e.g., *Dela Cruz*, *Reyes*, *Santos*, *Garcia*) produce false-positive kinship matches when paired solely on name similarity.

1. **Common Surname Penalty**: Candidates sharing a high-frequency surname without middle-name alignment were demoted by adjusting their baseline probability:
$$P_{\text{adjusted}} = \max(0.0, P_{\text{raw}} - \Delta_{\text{common}})$$


where $\Delta_{\text{common}} \in [0.10, 0.15]$.
2. **Dynastic Exception Overrides**: Established dynastic families in specific geographic regions exhibiting high surname frequency (e.g., *Tan* in Sulu/Samar, *Ampatuan* and *Hataman* in BARMM, *Marcos* and *Singson* in Region I) were exempted from probability penalties using prefix-matched PSGC lookup tables.

---

## 4. Graph Structural Topology Validation

To validate inferred linkages, candidate edges were embedded into a global network graph to evaluate local cluster density and triadic closure. For every candidate edge $e_{ij} = (v_i, v_j)$, the local network topology was evaluated across multiple structural metrics:

* **Jaccard Coefficient**:
$$J(v_i, v_j) = \frac{\vert{}\Gamma(v_i) \cap \Gamma(v_j)\vert{}}{\vert{}\Gamma(v_i) \cup \Gamma(v_j)\vert{}}$$


* **Adamic-Adar Index**:
$$AA(v_i, v_j) = \sum_{u \in \Gamma(v_i) \cap \Gamma(v_j)} \frac{1}{\log \vert{}\Gamma(u)\vert{}}$$



Where $\Gamma(v_i)$ denotes the neighborhood set of node $v_i$. Each edge was assigned a structural confidence score based on topological position:

* **Strong Cluster / Cluster Confirmed**: Edge participates in closed triadic structures ($\ge 1$ common neighbor) with high local clustering coefficients ($AA \ge 1.0$).
* **Bridge / Isolated**: Edge serves as the sole connection between distinct components or connects peripheral nodes without shared neighborhood density.

In total, $1,350$ edges ($53.9\%$) were structurally confirmed by triadic closure and component density.

---

## 5. Multi-Signal Consensus Classification Engine

To determine final edge validity and probability $P(e_{ij})$, candidate linkages were processed through a multi-signal consensus framework integrating fuzzy string metrics, structural confidence, rule-based ground truth, and external cross-validation matching (*Pulitiklan* database).

Each edge was classified into one of eight mutually exclusive hierarchical consensus tiers:

| Consensus Tier | Condition / Logic | Final Probability ($P$) | Ground Truth Flag |
| --- | --- | --- | --- |
| **Verified_Pulitiklan** | Explicit match with verified external Pulitiklan record | $1.00$ | `True` |
| **Rule_Based_GT** | Explicit ground truth tie (e.g., direct maternal maiden match) | $1.00$ | `True` |
| **Baseline_Mindanao** | Regional baseline linkage from verified BARMM/Mindanao registries | $P_{\text{raw}}$ | `False` |
| **Consensus_High** | $\ge 2$ independent detection signals (probability $\ge 0.85$, confirmed fuzzy variant, structural confidence $\ge 0.75$) | $0.95$ | `False` |
| **Single_Method** | Supported by exactly 1 detection vector | $P_{\text{raw}}$ | `False` |
| **Low_Confidence** | Weak signal support without external or structural confirmation | $P_{\text{raw}}$ | `False` |
| **Contradicted** | Conflicted by external registry cross-validation | $0.10$ | `False` |
| **Duplicate_Record** | Identified as duplicate node identity artifact | $0.10$ | `False` |

---

## 6. Undirected Canonicalization and Graph Deduplication

Kinship in political networks represents an undirected, symmetric relation: if actor $v_i$ shares a dynastic kinship tie with actor $v_j$, $v_j$ symmetrically shares that tie with $v_i$. Directed candidate pair generation produces reciprocal edge records $(v_i, v_j)$ and $(v_j, v_i)$ (e.g., *Sister* and *Brother* directional entries).

To prevent artificial doubling of network density, degree centrality, and clustering metrics, reciprocal candidate pairs were collapsed into single canonical undirected edges:

$$\text{pair\_key}(v_i, v_j) = \big(\min(\text{ID}_i, \text{ID}_j), \, \max(\text{ID}_i, \text{ID}_j)\big)$$

When duplicate directional entries occurred for a given $\text{pair\_key}$, a deterministic priority rule selected the primary canonical edge:

1. Maximize `is_ground_truth` status (`True` > `False`).
2. Maximize final consensus probability $P(e_{ij})$.
3. Maximize total supporting signal count.

---

## 7. Results and Network Validation

The canonicalization process successfully collapsed $2,504$ reciprocal candidate entries into $1,252$ unique undirected edges.

```
Canonical Edge Distribution (N = 1,252)
================================================================================
Verified_Pulitiklan  [████] 108 (8.6%)
Rule_Based_GT        [█████] 119 (9.5%)
Baseline_Mindanao    [█████████████████] 393 (31.4%)
Consensus_High       [█████] 120 (9.6%)
Single_Method        [█████████████] 309 (24.7%)
Low_Confidence       [█████████] 198 (15.8%)
Contradicted         [▏] 1 (0.1%)
Duplicate_Record     [▏] 4 (0.3%)
================================================================================
Ground Truth Total   : 227 / 1,252 edges (18.1%)
High Confidence Set  : 740 / 1,252 edges (59.1%)

```

Validation testing confirmed zero self-loops, $100\%$ edge classification coverage, zero duplicate node pairs, strictly bounded edge probabilities $P \in [0.0, 1.0]$, and complete $P = 1.00$ assignment across all verified ground-truth linkages.