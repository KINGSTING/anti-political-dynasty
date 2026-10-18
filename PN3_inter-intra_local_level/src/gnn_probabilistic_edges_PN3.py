"""
PN3 Kinship Edge Generation (v4) — production schema
-----------------------------------------------------
Output schema (matches PN2 master edges):
  edge_id, person_a_id, person_b_id, relation_label,
  civil_degree, kinship_type, source_document,
  is_ground_truth, probability
"""

import os
import re
import itertools
import pandas as pd

# ==================== PATHS ====================
NODES_CSV = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN3_inter-intra_local_level\data\inter-intra_local_nodes.csv"

OUT_DIR            = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN3_inter-intra_local_level\data"
GROUND_TRUTH_FILE  = os.path.join(OUT_DIR, "inter-intra_local_edges_ground_truth.csv")
PROBABILISTIC_FILE = os.path.join(OUT_DIR, "gnn_local_probabilistic_edges.csv")
MERGED_FILE        = os.path.join(OUT_DIR, "inter-intra_local_edges_merged.csv")
AUDIT_FILE         = os.path.join(OUT_DIR, "inter-intra_local_edges_audit.csv")

# ==================== CONFIG ====================
MIN_PROB_FOR_OUTPUT = 0.50
TIER_THRESHOLD      = {1: 0.50, 2: 0.85, 3: 0.85, 4: 0.80}
TIER_GEO_BONUS      = {1: 0.30, 2: 0.10, 3: 0.05, 4: 0.02}
TIER_LABELS = {1: "intra_lgu", 2: "intra_provincial",
               3: "intra_regional", 4: "inter_regional"}

START_EDGE_ID = 5000  # EDGE-005000, EDGE-005001, ...

SUFFIX_TOKENS = {"JR", "JR.", "SR", "SR.", "II", "III", "IV", "V", "VI"}

COMMON_SURNAMES = {
    "DELA CRUZ", "DELACRUZ", "REYES", "SANTOS", "GARCIA", "RAMOS", "MENDOZA",
    "BAUTISTA", "CASTILLO", "VILLANUEVA", "AQUINO", "CRUZ", "SANTIAGO",
    "GONZALES", "PEREZ", "RODRIGUEZ", "TORRES", "FLORES", "RIVERA",
    "DIAZ", "MARTINEZ", "AGUILAR", "NAVARRO", "MORALES", "DOMINGUEZ",
    "VILLAREAL", "MAGBANUA", "JAVIER", "TOLENTINO", "SALAZAR",
}

# Format: (person_id_a, person_id_b, relation_label, civil_degree, kinship_type)
MANUAL_KINSHIP_OVERRIDES = [
    # ("POL-PH-000123", "POL-PH-004567", "Sibling", 2, "Consanguinity"),
]

OUTPUT_COLUMNS = [
    "edge_id", "person_a_id", "person_b_id",
    "relation_label", "civil_degree", "kinship_type",
    "source_document", "is_ground_truth", "probability",
]
AUDIT_EXTRA = ["tier", "scope", "technical_label"]


# ==================== HELPERS ====================
def normalize_name(name):
    if pd.isna(name) or not str(name).strip():
        return ""
    s = str(name).upper().strip()
    s = re.sub(r"[^A-Z\s]", " ", s)
    return " ".join(s.split())


def normalize_surname(name):
    s = normalize_name(name)
    return re.sub(r"\b(JR\.?|SR\.?|II|III|IV|V|VI)\b", "", s).strip()


def extract_suffix_from_full(full_name, first_name, middle_name, last_name):
    if pd.isna(full_name) or not str(full_name).strip():
        return ""
    full_tokens = str(full_name).upper().replace(".", " ").split()
    known = set()
    for col in (first_name, middle_name, last_name):
        if pd.notna(col) and str(col).strip():
            for tok in str(col).upper().replace(".", " ").split():
                known.add(tok)
    found = [t for t in full_tokens if t in known | SUFFIX_TOKENS and t in SUFFIX_TOKENS]
    return found[-1] if found else ""


def get_province_key(psgc):
    if not psgc or pd.isna(psgc):
        return ""
    s = str(psgc).strip().zfill(10)
    if s.startswith("13"):
        return "1300000000"
    return s[:5] + "00000"


def get_region_key(psgc):
    if not psgc or pd.isna(psgc):
        return ""
    return str(psgc).strip().zfill(10)[:2]


def get_tier(a, b):
    if a["home_psgc"] == b["home_psgc"]:
        return 1
    if a["province_key"] == b["province_key"] and a["province_key"]:
        return 2
    if a["region_key"] == b["region_key"] and a["region_key"]:
        return 3
    return 4


def classify_relation(technical_label):
    """Technical pattern → (relation_label, civil_degree, kinship_type)."""
    t = technical_label
    has_family_boost = "Family_Boost" in t
    has_suffix_chain = "Suffix_Chain" in t
    has_bidir        = "Bidirectional_Interlock" in t
    has_cross        = "Cross_Interlock" in t and not has_bidir
    has_same_last    = "Same_Last_Name" in t
    has_same_mid     = "Same_Middle" in t

    if has_bidir:
        return "Spouse", 1, "Affinity"
    if has_family_boost and has_suffix_chain:
        # Same last + same mid + suffix chain = parent-child with matching middle (very strong)
        return "Parent_Child", 1, "Consanguinity"
    if has_family_boost:
        return "Sibling", 2, "Consanguinity"
    if has_suffix_chain:
        return "Parent_Child", 1, "Consanguinity"
    if has_cross:
        return "In_Law", 2, "Affinity"
    if has_same_mid and not has_same_last:
        return "Shared_Maternal_Line", 4, "Consanguinity"
    if has_same_last and not has_same_mid:
        return "Distant_Kin", 6, "Consanguinity"
    return "Unknown_Kin", 0, "Unknown"


# ==================== LOAD ====================
def load_nodes():
    nodes = pd.read_csv(NODES_CSV, dtype={"home_psgc": str}, keep_default_na=False)
    print(f"Loaded {len(nodes)} nodes")

    nodes["home_psgc"]    = nodes["home_psgc"].str.strip().str.zfill(10)
    nodes["last_clean"]   = nodes["last_name"].apply(normalize_surname)
    nodes["middle_clean"] = nodes["middle_name"].apply(normalize_surname)
    nodes["first_clean"]  = nodes["first_name"].apply(normalize_name)
    nodes["province_key"] = nodes["home_psgc"].apply(get_province_key)
    nodes["region_key"]   = nodes["home_psgc"].apply(get_region_key)
    nodes["suffix"] = nodes.apply(
        lambda r: extract_suffix_from_full(
            r["full_name_clean"], r["first_name"], r["middle_name"], r["last_name"]
        ), axis=1
    )
    nodes["base_first"] = nodes["first_clean"]

    print(f"Nodes with parsed suffix: {(nodes['suffix'] != '').sum()}")
    pre = len(nodes)
    nodes = nodes[nodes["last_clean"] != ""].reset_index(drop=True)
    print(f"Nodes with valid surname: {len(nodes)} (dropped {pre - len(nodes)})")
    print(f"Distinct provinces: {nodes['province_key'].nunique()}")
    print(f"Distinct regions  : {nodes['region_key'].nunique()}")
    return nodes


# ==================== SCORING ====================
def score_pair(a, b, tier):
    if a["person_id"] == b["person_id"]:
        return 0.0, "Same_Person", False

    last_a, last_b   = a["last_clean"],   b["last_clean"]
    mid_a,  mid_b    = a["middle_clean"], b["middle_clean"]
    first_a, first_b = a["first_clean"],  b["first_clean"]
    sfx_a,  sfx_b    = a["suffix"],       b["suffix"]

    same_last  = bool(last_a) and last_a == last_b
    same_mid   = (bool(mid_a) and mid_a == mid_b
                  and mid_a != last_a and mid_a != last_b)
    same_first = bool(first_a) and first_a == first_b
    diff_first = bool(first_a) and bool(first_b) and first_a != first_b

    # Duplicate check
    if same_first and same_last and same_mid and not (sfx_a or sfx_b):
        return 0.0, "Duplicate_Record", False

    score  = TIER_GEO_BONUS[tier]
    labels = [f"Tier{tier}"]

    if same_last:
        score += 0.30
        labels.append("Same_Last_Name")

    if same_mid:
        score += 0.25
        labels.append("Same_Middle")

    # Family boost + cross-LGU sibling confidence bonus
    if same_last and same_mid:
        score += 0.25
        labels.append("Family_Boost")
        if tier in (2, 3, 4) and diff_first:
            score += 0.06
            labels.append("Cross_LGU_Sibling_Bonus")

    # Suffix chain (parent-child)
    suffix_chain = False
    if same_last and first_a and first_a == first_b:
        if (sfx_a or sfx_b) and sfx_a != sfx_b:
            suffix_chain = True
            score += 0.35
            labels.append("Suffix_Chain")

    # Interlock
    cross_a = bool(mid_a) and mid_a == last_b and last_a != last_b
    cross_b = bool(mid_b) and mid_b == last_a and last_a != last_b
    if cross_a and cross_b:
        score += 0.30
        labels.append("Bidirectional_Interlock")
    elif cross_a or cross_b:
        score += 0.15
        labels.append("Cross_Interlock")

    # Common-surname penalty — SKIP when same-mid confirms relation
    if (tier >= 3 and same_last and not same_mid
            and (last_a in COMMON_SURNAMES or mid_a in COMMON_SURNAMES)):
        score -= 0.10
        labels.append("Common_Surname_Penalty")

    if same_first and not suffix_chain:
        score -= 0.10
        labels.append("Same_First_Penalty")

    score = max(0.0, min(0.99, score))

    # Ground truth restricted to Tier 1 confirmed patterns
    if tier == 1:
        is_gt = (
            (same_last and same_mid and diff_first)
            or suffix_chain
            or (cross_a and cross_b)
        )
    else:
        is_gt = False

    return score, "+".join(labels), is_gt


# ==================== EDGE GENERATION ====================
def generate_edges(nodes):
    print("\nEnumerating candidate pairs per tier...")
    edges, seen = [], set()

    def add_pair(a, b):
        key = tuple(sorted([a["person_id"], b["person_id"]]))
        if key in seen:
            return
        seen.add(key)

        tier = get_tier(a, b)
        prob, tech_label, is_gt = score_pair(a, b, tier)

        # Skip same-first-name noise (likely duplicates)
        if "Same_First_Penalty" in tech_label and "Suffix_Chain" not in tech_label:
            return

        if is_gt:
            prob = 1.00
        elif prob < MIN_PROB_FOR_OUTPUT:
            return

        relation, degree, kin_type = classify_relation(tech_label)

        edges.append({
            "person_a_id": a["person_id"],
            "person_b_id": b["person_id"],
            "relation_label": relation,
            "civil_degree": degree,
            "kinship_type": kin_type,
            "source_document": "Deterministic_Rule" if is_gt else "GNN_Inferred_Kinship",
            "is_ground_truth": is_gt,
            "probability": round(prob, 3),
            "tier": tier,
            "scope": TIER_LABELS[tier],
            "technical_label": tech_label,
        })

    # --- Tier 1 ---
    print("  [T1] Within-LGU...")
    for _, group in nodes.groupby(["home_psgc", "last_clean"]):
        if len(group) < 2: continue
        rows = group.to_dict("records")
        for a, b in itertools.combinations(rows, 2):
            add_pair(a, b)

    maiden = nodes[nodes["middle_clean"] != ""]
    for _, group in maiden.groupby(["home_psgc", "middle_clean"]):
        if len(group) < 2: continue
        rows = group.to_dict("records")
        for a, b in itertools.combinations(rows, 2):
            if a["last_clean"] != b["last_clean"]:
                add_pair(a, b)

    # --- Tier 2 ---
    print("  [T2] Cross-LGU within province...")
    for _, group in nodes.groupby(["province_key", "last_clean"]):
        if len(group) < 2 or not group.iloc[0]["province_key"]: continue
        rows = group.to_dict("records")
        for a, b in itertools.combinations(rows, 2):
            if a["home_psgc"] != b["home_psgc"]:
                add_pair(a, b)

    for _, group in maiden.groupby(["province_key", "middle_clean"]):
        if len(group) < 2 or not group.iloc[0]["province_key"]: continue
        rows = group.to_dict("records")
        for a, b in itertools.combinations(rows, 2):
            if a["home_psgc"] != b["home_psgc"] and a["last_clean"] != b["last_clean"]:
                add_pair(a, b)

    # --- Tier 3 ---
    print("  [T3] Cross-province within region...")
    for _, group in nodes.groupby(["region_key", "last_clean"]):
        if len(group) < 2 or not group.iloc[0]["region_key"]: continue
        rows = group.to_dict("records")
        for a, b in itertools.combinations(rows, 2):
            if a["province_key"] != b["province_key"]:
                add_pair(a, b)

    for _, group in maiden.groupby(["region_key", "middle_clean"]):
        if len(group) < 2 or not group.iloc[0]["region_key"]: continue
        rows = group.to_dict("records")
        for a, b in itertools.combinations(rows, 2):
            if a["province_key"] != b["province_key"] and a["last_clean"] != b["last_clean"]:
                add_pair(a, b)

    # --- Tier 4 ---
    print("  [T4] Cross-region (strict: same last + same mid)...")
    for _, group in nodes.groupby(["last_clean", "middle_clean"]):
        if len(group) < 2 or not group.iloc[0]["middle_clean"]: continue
        rows = group.to_dict("records")
        for a, b in itertools.combinations(rows, 2):
            if a["region_key"] != b["region_key"]:
                add_pair(a, b)

    # --- Manual OSINT overrides ---
    if MANUAL_KINSHIP_OVERRIDES:
        print(f"  [Manual] Adding {len(MANUAL_KINSHIP_OVERRIDES)} OSINT anchors...")
        id_to_node = nodes.set_index("person_id").to_dict("index")
        for pid_a, pid_b, relation, degree, kin_type in MANUAL_KINSHIP_OVERRIDES:
            if pid_a in id_to_node and pid_b in id_to_node:
                a, b = id_to_node[pid_a], id_to_node[pid_b]
                tier = get_tier(a, b)
                edges.append({
                    "person_a_id": pid_a, "person_b_id": pid_b,
                    "relation_label": relation,
                    "civil_degree": degree,
                    "kinship_type": kin_type,
                    "source_document": "OSINT_Verified",
                    "is_ground_truth": True,
                    "probability": 1.00,
                    "tier": tier,
                    "scope": TIER_LABELS[tier],
                    "technical_label": "Manual_OSINT",
                })

    print(f"  → {len(edges)} total candidate edges")
    return pd.DataFrame(edges)


# ==================== MAIN ====================
def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    nodes = load_nodes()
    df_edges = generate_edges(nodes)

    if df_edges.empty:
        print("No edges generated.")
        return

    # ---- Assign edge IDs sequentially ----
    df_edges = df_edges.reset_index(drop=True)
    df_edges["edge_id"] = [f"EDGE-{START_EDGE_ID + i:06d}" for i in range(len(df_edges))]

    # ---- Production view (9 columns per spec) ----
    df_prod = df_edges[OUTPUT_COLUMNS].copy()

    # ---- Tier-aware merge filter (GT always passes) ----
    def passes_tier(row):
        if row["is_ground_truth"]:
            return True
        return row["probability"] >= TIER_THRESHOLD[row["tier"]]

    # Need tier column for filter — pull from df_edges
    tier_lookup = df_edges.set_index("edge_id")["tier"]
    df_prod_with_tier = df_prod.copy()
    df_prod_with_tier["tier"] = df_prod_with_tier["edge_id"].map(tier_lookup)

    mask_pass = df_prod_with_tier.apply(passes_tier, axis=1)
    df_merged = df_prod[mask_pass.values].copy()

    df_gt   = df_prod[df_prod["is_ground_truth"] == True].copy()
    df_prob = df_prod[df_prod["is_ground_truth"] == False].copy()

    # ---- Write production files (9 columns) ----
    df_gt.to_csv(GROUND_TRUTH_FILE, index=False, encoding="utf-8-sig")
    df_prob.to_csv(PROBABILISTIC_FILE, index=False, encoding="utf-8-sig")
    df_merged.to_csv(MERGED_FILE, index=False, encoding="utf-8-sig")

    # ---- Audit file (9 + 3 diagnostic columns) ----
    df_audit = df_edges[OUTPUT_COLUMNS + AUDIT_EXTRA].copy()
    df_audit.to_csv(AUDIT_FILE, index=False, encoding="utf-8-sig")

    # ---- Summary ----
    print("\n" + "=" * 62)
    print("=== PN3 KINSHIP EDGE GENERATION (FINAL SCHEMA) ===")
    print("=" * 62)
    print(f"Ground truth edges   : {len(df_gt)}")
    print(f"Inferred edges       : {len(df_prob)}")
    print(f"Merged edges         : {len(df_merged)}")
    print(f"Audit (all candidates): {len(df_audit)}")

    merged_ids = set(df_merged["edge_id"])
    print("\n=== Merged breakdown by tier ===")
    for t in [1, 2, 3, 4]:
        cnt = df_edges[
            (df_edges["tier"] == t) & (df_edges["edge_id"].isin(merged_ids))
        ].shape[0]
        print(f"  Tier {t} ({TIER_LABELS[t]:<18}) : {cnt}")

    print("\n=== Merged breakdown by relation_label ===")
    print(df_merged["relation_label"].value_counts().to_string())

    print("\n=== Merged breakdown by kinship_type ===")
    print(df_merged["kinship_type"].value_counts().to_string())

    print("\n=== Merged breakdown by civil_degree ===")
    print(df_merged["civil_degree"].value_counts().sort_index().to_string())

    print("\n=== Sample output (first 5 rows) ===")
    print(df_merged.head(5).to_string(index=False))

    print(f"\nFiles written:")
    print(f"  {GROUND_TRUTH_FILE}")
    print(f"  {PROBABILISTIC_FILE}")
    print(f"  {MERGED_FILE}")
    print(f"  {AUDIT_FILE}")


if __name__ == "__main__":
    main()