"""
PN3 Kinship Graph Validation
----------------------------
Audits the local-level kinship graph against multiple invariants.
Output is designed for manual review — no auto-correction.
"""

import os
import networkx as nx
import numpy as np
import pandas as pd

# ==================== PATHS ====================
NODES_FILE         = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN3_inter-intra_local_level\data\inter-intra_local_nodes.csv"
MERGED_EDGES_FILE  = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN3_inter-intra_local_level\data\inter-intra_local_edges_merged.csv"
GT_EDGES_FILE      = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN3_inter-intra_local_level\data\inter-intra_local_edges_ground_truth.csv"
PROB_EDGES_FILE    = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN3_inter-intra_local_level\data\gnn_local_probabilistic_edges.csv"
AUDIT_EDGES_FILE   = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN3_inter-intra_local_level\data\inter-intra_local_edges_audit.csv"

EXPECTED_DEGREE = {
    "Parent_Child":          1,
    "Sibling":               2,
    "Spouse":                1,
    "In_Law":                2,
    "Shared_Maternal_Line":  4,
    "Distant_Kin":           6,
}

print("=" * 70)
print("=== PN3 LOCAL KINSHIP GRAPH — ROBUSTNESS AUDIT ===")
print("=" * 70)


# ==================== LOAD ====================
for p in [NODES_FILE, MERGED_EDGES_FILE]:
    if not os.path.exists(p):
        raise FileNotFoundError(f"Missing required file: {p}")

edges_df = pd.read_csv(MERGED_EDGES_FILE, dtype={
    "person_a_id": str, "person_b_id": str, "edge_id": str
}, keep_default_na=False)
nodes_df = pd.read_csv(NODES_FILE, dtype={"person_id": str, "home_psgc": str},
                       keep_default_na=False)

edges_df["person_a_id"] = edges_df["person_a_id"].str.strip()
edges_df["person_b_id"] = edges_df["person_b_id"].str.strip()
nodes_df["person_id"]   = nodes_df["person_id"].str.strip()

nodes_clean = nodes_df.drop_duplicates(subset=["person_id"], keep="first")
node_map    = nodes_clean.set_index("person_id").to_dict("index")

gt_edges       = edges_df[edges_df["is_ground_truth"] == True]
inferred_edges = edges_df[edges_df["is_ground_truth"] == False]

print(f"\nLoaded edges  : {len(edges_df)}")
print(f"Loaded nodes  : {len(nodes_clean)}")
print(f"Verified GT   : {len(gt_edges)}")
print(f"Inferred      : {len(inferred_edges)}")


# ==================== HELPERS ====================
def get_node_name(node, fallback_id=""):
    if not node:
        return fallback_id
    if "full_name_clean" in node and node["full_name_clean"]:
        return str(node["full_name_clean"]).strip()
    parts = [str(node.get(c, "")).strip() for c in
             ("first_name", "middle_name", "last_name")
             if node.get(c)]
    return " ".join(p for p in parts if p and p.lower() != "nan") or fallback_id


def get_psgc_code(node):
    if not node or "home_psgc" not in node:
        return ""
    raw = str(node["home_psgc"]).strip()
    if raw.endswith(".0"):
        raw = raw[:-2]
    return raw.zfill(10) if raw else ""


def surname_interlock_status(node_a, node_b):
    if not node_a or not node_b:
        return "Missing Node Data"

    last_a = str(node_a.get("last_name", "")).strip().upper()
    last_b = str(node_b.get("last_name", "")).strip().upper()
    mid_a  = str(node_a.get("middle_name", "")).strip().upper()
    mid_b  = str(node_b.get("middle_name", "")).strip().upper()

    same_last = bool(last_a and last_a == last_b)
    same_mid  = bool(mid_a and mid_b and mid_a == mid_b and mid_a != last_a and mid_a != last_b)
    cross     = bool((mid_a and mid_a == last_b and last_a != last_b) or
                     (mid_b and mid_b == last_a and last_a != last_b))

    if same_last and same_mid:
        return "Same Last + Same Middle (Sibling)"
    if same_last:
        return "Direct Last Name Match"
    if cross:
        return "Interlock Match (Cross-Surname)"
    if same_mid:
        return "Shared Maternal Line"
    return "Cross-Surname / Extended"


# ==================== AUDIT 0: SCHEMA INTEGRITY ====================
print("\n--- 0. SCHEMA INTEGRITY ---")

required_cols = ["edge_id", "person_a_id", "person_b_id", "relation_label",
                 "civil_degree", "kinship_type", "source_document",
                 "is_ground_truth", "probability"]
missing = [c for c in required_cols if c not in edges_df.columns]
print(f"Required columns present       : {'✓' if not missing else f'✗ MISSING {missing}'}")

# Self-loops
self_loops = edges_df[edges_df["person_a_id"] == edges_df["person_b_id"]]
print(f"Self-loops                     : {len(self_loops)} {'✓' if len(self_loops) == 0 else '✗'}")

# Duplicates (same pair, either direction)
edge_pairs = edges_df.apply(
    lambda r: tuple(sorted([r["person_a_id"], r["person_b_id"]])), axis=1
)
dup_pairs = edge_pairs.duplicated().sum()
print(f"Duplicate person pairs         : {dup_pairs} {'✓' if dup_pairs == 0 else '✗'}")

# Duplicate edge_ids
dup_ids = edges_df["edge_id"].duplicated().sum()
print(f"Duplicate edge_ids             : {dup_ids} {'✓' if dup_ids == 0 else '✗'}")

# Referential integrity: every person_id must exist in nodes
node_ids = set(nodes_clean["person_id"])
edge_person_ids = set(edges_df["person_a_id"]) | set(edges_df["person_b_id"])
orphan_ids = edge_person_ids - node_ids
print(f"Person IDs missing from nodes  : {len(orphan_ids)} {'✓' if len(orphan_ids) == 0 else '✗'}")
if orphan_ids:
    print(f"  Sample orphans: {list(orphan_ids)[:5]}")


# ==================== AUDIT 1: GROUND-TRUTH SANITY ====================
print("\n--- 1. GROUND-TRUTH SANITY ---")

gt_prob_wrong = gt_edges[gt_edges["probability"] < 1.0]
print(f"GT edges with P < 1.00         : {len(gt_prob_wrong)} {'✓' if len(gt_prob_wrong) == 0 else '✗'}")

# GT should only be intra_lgu (Tier 1) — check via shared_psgc if present, else flag
if "scope" in edges_df.columns:
    gt_not_t1 = gt_edges[gt_edges["scope"] != "intra_lgu"]
    print(f"GT edges outside intra_lgu     : {len(gt_not_t1)} {'✓' if len(gt_not_t1) == 0 else '✗'}")
else:
    print("GT edges outside intra_lgu     : (skipped — scope column absent in merged file)")

# GT relation labels should only be Sibling/Parent_Child/Spouse
valid_gt_labels = {"Sibling", "Parent_Child", "Spouse"}
bad_gt_labels = gt_edges[~gt_edges["relation_label"].isin(valid_gt_labels)]
print(f"GT edges with weak labels      : {len(bad_gt_labels)} {'✓' if len(bad_gt_labels) == 0 else '✗'}")
if len(bad_gt_labels):
    print(bad_gt_labels["relation_label"].value_counts().to_string())


# ==================== AUDIT 2: CIVIL DEGREE CONSISTENCY ====================
print("\n--- 2. CIVIL DEGREE × RELATION LABEL CONSISTENCY ---")

mismatches = []
for _, e in edges_df.iterrows():
    expected = EXPECTED_DEGREE.get(e["relation_label"])
    if expected is not None and int(e["civil_degree"]) != expected:
        mismatches.append((e["relation_label"], e["civil_degree"], expected))

if not mismatches:
    print("All relation labels have matching civil degrees ✓")
else:
    from collections import Counter
    counts = Counter(mismatches)
    for (rel, got, expected), n in counts.items():
        print(f"  ✗ {rel:<24} degree={got}, expected={expected}  ({n} edges)")


# ==================== AUDIT 3: KINSHIP TYPE CONSISTENCY ====================
print("\n--- 3. KINSHIP TYPE CONSISTENCY ---")

expected_kin_type = {
    "Sibling":              "Consanguinity",
    "Parent_Child":         "Consanguinity",
    "Shared_Maternal_Line": "Consanguinity",
    "Distant_Kin":          "Consanguinity",
    "Spouse":               "Affinity",
    "In_Law":               "Affinity",
}

bad_kin = edges_df[
    edges_df.apply(
        lambda r: expected_kin_type.get(r["relation_label"]) is not None
        and r["kinship_type"] != expected_kin_type[r["relation_label"]],
        axis=1,
    )
]
print(f"Kinship type mismatches        : {len(bad_kin)} {'✓' if len(bad_kin) == 0 else '✗'}")
if len(bad_kin):
    print(bad_kin[["relation_label", "kinship_type"]].value_counts().to_string())


# ==================== AUDIT 4: PROBABILITY DISTRIBUTION ====================
print("\n--- 4. INFERRED EDGE CONFIDENCE DISTRIBUTION ---")

if len(inferred_edges) > 0:
    probs = inferred_edges["probability"].values.astype(float)
    print(f"Count                          : {len(probs)}")
    print(f"Mean probability               : {np.mean(probs):.4f}")
    print(f"Median probability             : {np.median(probs):.4f}")
    print(f"Std deviation                  : {np.std(probs):.4f}")
    print(f"Min / Max                      : {probs.min():.3f} / {probs.max():.3f}")
    print(f"P >= 0.90                      : {(probs >= 0.90).sum()}")
    print(f"P 0.80–0.89                    : {((probs >= 0.80) & (probs < 0.90)).sum()}")
    print(f"P 0.70–0.79                    : {((probs >= 0.70) & (probs < 0.80)).sum()}")
    print(f"P 0.60–0.69                    : {((probs >= 0.60) & (probs < 0.70)).sum()}")
    print(f"P < 0.60                       : {(probs < 0.60).sum()}")
else:
    print("No inferred edges present.")


# ==================== AUDIT 5: RELATION LABEL DISTRIBUTION ====================
print("\n--- 5. RELATION LABEL DISTRIBUTION ---")
print(edges_df.groupby(["relation_label", "is_ground_truth"]).size().to_string())


# ==================== AUDIT 6: SURNAME & INTERLOCK ALIGNMENT ====================
print("\n--- 6. SURNAME & INTERLOCK ALIGNMENT ---")

direct = interlock = maternal = cross = missing = 0
for _, e in inferred_edges.iterrows():
    p_a = node_map.get(e["person_a_id"], {})
    p_b = node_map.get(e["person_b_id"], {})
    if not p_a or not p_b:
        missing += 1
        continue
    status = surname_interlock_status(p_a, p_b)
    if "Sibling" in status:
        direct += 1
    elif "Direct Last" in status:
        direct += 1
    elif "Interlock" in status:
        interlock += 1
    elif "Shared Maternal" in status:
        maternal += 1
    else:
        cross += 1

total = len(inferred_edges)
if total > 0:
    print(f"Same Last + Same Middle (Sib): {direct} ({direct/total*100:.2f}%)")
    print(f"Direct Last Name Match       : (included above)")
    print(f"Interlock Match              : {interlock} ({interlock/total*100:.2f}%)")
    print(f"Shared Maternal Line         : {maternal} ({maternal/total*100:.2f}%)")
    print(f"Cross-Surname / Extended     : {cross} ({cross/total*100:.2f}%)")
    print(f"Kin-aligned total            : {direct+interlock+maternal} "
          f"({(direct+interlock+maternal)/total*100:.2f}%)")
    if missing:
        print(f"Missing node attributes      : {missing}")


# ==================== AUDIT 7: GEOGRAPHIC COHERENCE ====================
print("\n--- 7. GEOGRAPHIC COHERENCE (PSGC) ---")

t1 = t2 = t3 = t4 = missing_psgc = 0
for _, e in edges_df.iterrows():
    p_a = node_map.get(e["person_a_id"], {})
    p_b = node_map.get(e["person_b_id"], {})
    psgc_a = get_psgc_code(p_a)
    psgc_b = get_psgc_code(p_b)
    if not psgc_a or not psgc_b:
        missing_psgc += 1
        continue
    if psgc_a == psgc_b:
        t1 += 1
    elif psgc_a[:5] == psgc_b[:5]:
        t2 += 1
    elif psgc_a[:2] == psgc_b[:2]:
        t3 += 1
    else:
        t4 += 1

total_geo = t1 + t2 + t3 + t4
if total_geo > 0:
    print(f"Tier 1 (same LGU)            : {t1:>5} ({t1/total_geo*100:5.2f}%)")
    print(f"Tier 2 (same province)       : {t2:>5} ({t2/total_geo*100:5.2f}%)")
    print(f"Tier 3 (same region)         : {t3:>5} ({t3/total_geo*100:5.2f}%)")
    print(f"Tier 4 (different region)    : {t4:>5} ({t4/total_geo*100:5.2f}%)")
if missing_psgc:
    print(f"Missing PSGC                 : {missing_psgc}")


# ==================== AUDIT 8: NETWORK TOPOLOGY ====================
print("\n--- 8. NETWORK TOPOLOGY & CLAN SIZES ---")

G = nx.Graph()
for _, e in edges_df.iterrows():
    G.add_edge(e["person_a_id"], e["person_b_id"],
               weight=e["probability"])

components = sorted(nx.connected_components(G), key=len, reverse=True)
sizes = [len(c) for c in components]

print(f"Total nodes in graph           : {G.number_of_nodes()}")
print(f"Total edges in graph           : {G.number_of_edges()}")
print(f"Total disjoint dynastic clans  : {len(components)}")
print(f"Largest single clan            : {sizes[0] if sizes else 0} officials")
print(f"Median clan size               : {int(np.median(sizes)) if sizes else 0} officials")
print(f"Average clan size              : {np.mean(sizes):.2f} officials" if sizes else "0")
print(f"Clans with >=10 members        : {sum(1 for s in sizes if s >= 10)}")
print(f"Clans with >=20 members        : {sum(1 for s in sizes if s >= 20)}")

print("\nTop 10 dynastic clans (size → sample surnames):")
for i, comp in enumerate(components[:10], 1):
    surnames = set()
    provinces = set()
    for pid in comp:
        node = node_map.get(pid, {})
        if node.get("last_name"):
            surnames.add(str(node["last_name"]).strip())
        psgc = get_psgc_code(node)
        if psgc:
            provinces.add(psgc[:5])
    sample_surnames = ", ".join(sorted(surnames)[:4])
    print(f"  {i:2d}. size={len(comp):3d} | surnames: {sample_surnames}"
          f" | prov blocks: {len(provinces)}")


# ==================== AUDIT 9: OSINT SAMPLE ====================
print("\n--- 9. RANDOMIZED OSINT SAMPLE ---")

for tier_filter, label in [
    (None, "All inferred"),
    ("ground_truth", "Ground truth"),
]:
    if label == "Ground truth":
        pool = gt_edges
    else:
        pool = inferred_edges
    if len(pool) == 0:
        continue
    n = min(10, len(pool))
    sample = pool.sample(n=n, random_state=42)
    print(f"\n  [{label} — {n} samples]")
    for _, e in sample.iterrows():
        p_a = node_map.get(e["person_a_id"], {})
        p_b = node_map.get(e["person_b_id"], {})
        name_a = get_node_name(p_a, e["person_a_id"])
        name_b = get_node_name(p_b, e["person_b_id"])
        psgc = get_psgc_code(p_a)
        status = surname_interlock_status(p_a, p_b)
        print(f"  [{e['probability']:.2f}] {name_a} <-> {name_b}")
        print(f"         PSGC={psgc} | {e['relation_label']} "
              f"(degree {e['civil_degree']}, {e['kinship_type']}) | {status}")


# ==================== FINAL VERDICT ====================
print("\n" + "=" * 70)
print("=== FINAL VERDICT ===")
issues = []
if len(self_loops) > 0:       issues.append(f"{len(self_loops)} self-loops")
if dup_pairs > 0:             issues.append(f"{dup_pairs} duplicate pairs")
if dup_ids > 0:               issues.append(f"{dup_ids} duplicate edge_ids")
if orphan_ids:                issues.append(f"{len(orphan_ids)} orphan person IDs")
if len(gt_prob_wrong) > 0:    issues.append(f"{len(gt_prob_wrong)} GT edges not at P=1.00")
if mismatches:                issues.append(f"{len(mismatches)} civil degree mismatches")
if len(bad_kin) > 0:          issues.append(f"{len(bad_kin)} kinship type mismatches")

if not issues:
    print("✓ ALL CHECKS PASSED — graph is production-ready")
else:
    print("⚠ ISSUES FOUND:")
    for i in issues:
        print(f"  • {i}")
print("=" * 70)