"""
PN3 FINAL CONSENSUS — production edge file
-------------------------------------------
Combines four orthogonal signals into a single defensible edge file:

  Signal 1 — Rule-based probability   (from gnn_probabilistic_edges_PN3.py)
  Signal 2 — Fuzzy name verdict       (from fuzzy_validate_edges.py)
  Signal 3 — Structural verdict       (from structural_metrics_validate.py)
  Signal 4 — Pulitiklan verdict       (from cross_validate_pulitiklan.py)

Consensus levels (priority order):
  1. Contradicted         — Pulitiklan denies the kinship         → P=0.10, audit only
  2. Duplicate_Record     — Same person under different person_id → P=0.10, audit only
  3. Verified_Pulitiklan  — External source confirms               → P=1.00, GT
  4. Rule_Based_GT        — Deterministic rule (sibling/PC)        → P=1.00, GT
  5. Baseline_Mindanao    — Mindanao, Pulitiklan silent            → preserve rule-based P
  6. Consensus_High       — 2+ orthogonal signals agree            → P=0.95
  7. Single_Method        — 1 orthogonal signal                    → preserve rule-based P
  8. Low_Confidence       — 0 corroborating signals                → preserve rule-based P
"""

import os
import pandas as pd
from rapidfuzz.distance import JaroWinkler

# ==================== PATHS ====================
BASE = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty"
PN3_DATA = os.path.join(BASE, "PN3_inter-intra_local_level", "data")

INPUT_EDGES         = os.path.join(PN3_DATA, "cross_validation", "PN3_pulitiklan_cross_validation.csv")
NODES_CSV           = os.path.join(PN3_DATA, "inter-intra_local_nodes.csv")
DUPLICATE_CANDIDATES = os.path.join(PN3_DATA, "cross_validation", "duplicate_candidates.csv")

OUT_FINAL  = os.path.join(PN3_DATA, "inter-intra_local_edges_FINAL.csv")
OUT_GT     = os.path.join(PN3_DATA, "inter-intra_local_edges_FINAL_gt.csv")
OUT_AUDIT  = os.path.join(PN3_DATA, "inter-intra_local_edges_FINAL_audit.csv")
OUT_REPORT = os.path.join(PN3_DATA, "final_consensus_report.txt")


# ==================== HELPERS ====================
def safe_float(val, default=0.0):
    """CSV column → float, gracefully handling empty/None/nan."""
    if val is None or pd.isna(val):
        return default
    s = str(val).strip()
    if s == "" or s.lower() == "nan":
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def is_true(val):
    """CSV boolean → Python bool, handling both 'True'/'true'/'1'."""
    return str(val).strip().lower() in ("true", "1", "yes", "t")


def identify_true_duplicates(nodes_df, candidates_df):
    """
    Filter candidate duplicate pairs to only TRUE duplicates.

    Discriminator: true duplicates have near-identical FIRST names
    (>= 0.90 JW); siblings have different first names.
    """
    if candidates_df is None or candidates_df.empty:
        return set()

    id_to_node = nodes_df.set_index("person_id").to_dict("index")
    true_dupes = set()

    for _, row in candidates_df.iterrows():
        a, b = row["person_a"], row["person_b"]
        node_a = id_to_node.get(a, {})
        node_b = id_to_node.get(b, {})

        first_a = str(node_a.get("first_name", "")).upper().strip()
        first_b = str(node_b.get("first_name", "")).upper().strip()
        mid_a   = str(node_a.get("middle_name", "")).upper().strip()
        mid_b   = str(node_b.get("middle_name", "")).upper().strip()

        if not first_a or not first_b:
            continue

        first_sim = JaroWinkler.normalized_similarity(first_a, first_b)
        mid_match = mid_a == mid_b and bool(mid_a)
        overall_sim = safe_float(row.get("similarity", "0"))

        if first_sim >= 0.90 and mid_match and overall_sim >= 0.92:
            true_dupes.add((a, b))
            true_dupes.add((b, a))

    return true_dupes


def final_consensus(row, true_dupes):
    """
    Apply 4-signal consensus logic. Returns (probability, consensus_level, is_gt).
    """
    a, b = row["person_a_id"], row["person_b_id"]
    pv = str(row.get("pulitiklan_verdict", "")).strip()
    fv = str(row.get("fuzzy_verdict", "")).strip()
    prob = safe_float(row.get("probability"), default=0.0)
    orig_gt = is_true(row.get("is_ground_truth", "False"))
    struct_conf = safe_float(row.get("structural_confidence"), default=0.0)

    # ---- Priority 1: Pulitiklan contradiction ----
    if pv == "contradicted":
        return 0.10, "Contradicted", False

    # ---- Priority 2: Confirmed duplicate nodes ----
    if (a, b) in true_dupes:
        return 0.10, "Duplicate_Record", False

    # ---- Priority 3: External source verification ----
    if pv == "verified_explicit":
        return 1.00, "Verified_Pulitiklan", True

    # ---- Priority 4: Preserve original rule-based GT (deterministic) ----
    if orig_gt:
        return 1.00, "Rule_Based_GT", True

    # ---- Priority 5: Mindanao baseline ----
    if pv == "baseline_mindanao":
        return prob, "Baseline_Mindanao", False

    # ---- Priority 6: Standard 3-signal consensus vote ----
    votes = 0
    if prob >= 0.85:
        votes += 1                                        # rule-based strong
    if fv in ("variant_confirmed", "variant_likely"):
        votes += 1                                        # fuzzy discovered variant
    if struct_conf >= 0.75:
        votes += 1                                        # structural clustering confirms

    if votes >= 2:
        return 0.95, "Consensus_High", False
    if votes == 1:
        return prob, "Single_Method", False
    return prob, "Low_Confidence", False


def count_signals(row, true_dupes):
    """Count how many of the 4 signals support this edge (0-4)."""
    count = 0
    if safe_float(row.get("probability"), 0) >= 0.85:
        count += 1
    if str(row.get("fuzzy_verdict", "")).strip() in ("variant_confirmed", "variant_likely"):
        count += 1
    if safe_float(row.get("structural_confidence"), 0) >= 0.75:
        count += 1
    if str(row.get("pulitiklan_verdict", "")).strip() == "verified_explicit":
        count += 1
    return count


# ==================== MAIN ====================
def main():
    print("=" * 70)
    print("=== PN3 FINAL CONSENSUS ===")
    print("=" * 70)

    # ---- Load ----
    print(f"\nLoading edges: {INPUT_EDGES}")
    if not os.path.exists(INPUT_EDGES):
        print(f"CRITICAL: input file not found. Run cross_validate_pulitiklan.py first.")
        return
    edges = pd.read_csv(INPUT_EDGES, dtype=str, keep_default_na=False)
    print(f"  {len(edges)} edges")

    print(f"Loading nodes: {NODES_CSV}")
    nodes = pd.read_csv(NODES_CSV, dtype=str, keep_default_na=False)
    print(f"  {len(nodes)} nodes")
    id2name = dict(zip(nodes["person_id"], nodes["full_name_clean"]))

    candidates = None
    if os.path.exists(DUPLICATE_CANDIDATES):
        print(f"Loading duplicate candidates: {DUPLICATE_CANDIDATES}")
        candidates = pd.read_csv(DUPLICATE_CANDIDATES, dtype=str, keep_default_na=False)
        print(f"  {len(candidates)} candidate pairs")
    else:
        print("⚠ No duplicate candidates — skipping dedupe logic")

    # ---- Identify true duplicates ----
    true_dupes = identify_true_duplicates(nodes, candidates)
    print(f"  → {len(true_dupes) // 2} confirmed duplicate pairs (near-identical first names)")

    # ---- Apply consensus ----
    print(f"\nApplying consensus...")
    results = []
    for _, row in edges.iterrows():
        prob, level, is_gt = final_consensus(row, true_dupes)
        results.append({
            "final_probability": prob,
            "consensus_level":   level,
            "final_is_gt":       is_gt,
            "signal_count":      count_signals(row, true_dupes),
        })

    df_cons = pd.DataFrame(results)

    # ---- Build output ----
    edges_out = edges.copy()
    edges_out["original_probability"] = edges_out["probability"]
    edges_out["probability"]     = df_cons["final_probability"].round(3)
    edges_out["consensus_level"] = df_cons["consensus_level"]
    edges_out["is_ground_truth"] = df_cons["final_is_gt"]
    edges_out["signal_count"]    = df_cons["signal_count"]

    # Column ordering — production first, diagnostic after
    priority_cols = [
        "edge_id", "person_a_id", "person_b_id",
        "relation_label", "civil_degree", "kinship_type",
        "consensus_level", "probability", "original_probability",
        "is_ground_truth", "signal_count", "source_document",
        # Diagnostic signals
        "fuzzy_verdict", "fuzzy_score",
        "structural_verdict", "structural_confidence",
        "pulitiklan_verdict",
    ]
    present = [c for c in priority_cols if c in edges_out.columns]
    remaining = [c for c in edges_out.columns if c not in present]
    edges_out = edges_out[present + remaining]

    # ---- Save production file ----
    edges_out.to_csv(OUT_FINAL, index=False, encoding="utf-8-sig")
    print(f"\n✅ Saved production file: {OUT_FINAL}")

    # ---- Save GT subset ----
    gt = edges_out[edges_out["is_ground_truth"] == True].copy()
    gt.to_csv(OUT_GT, index=False, encoding="utf-8-sig")
    print(f"✅ Saved GT subset:      {OUT_GT} ({len(gt)} edges)")

    # ---- Save audit subset ----
    audit_levels = ["Contradicted", "Duplicate_Record", "Low_Confidence"]
    audit = edges_out[edges_out["consensus_level"].isin(audit_levels)].copy()
    audit.to_csv(OUT_AUDIT, index=False, encoding="utf-8-sig")
    print(f"✅ Saved audit subset:   {OUT_AUDIT} ({len(audit)} edges)")

    # ---- Distribution ----
    dist = edges_out["consensus_level"].value_counts()
    ordered_levels = [
        "Verified_Pulitiklan", "Rule_Based_GT", "Baseline_Mindanao",
        "Consensus_High", "Single_Method", "Low_Confidence",
        "Contradicted", "Duplicate_Record",
    ]
    gt_count = int((edges_out["is_ground_truth"] == True).sum())

    # ---- Report ----
    report = []
    report.append("=" * 70)
    report.append("=== PN3 FINAL CONSENSUS REPORT ===")
    report.append("=" * 70)
    report.append(f"Total edges               : {len(edges_out)}")
    report.append(f"Confirmed duplicate pairs : {len(true_dupes) // 2}")
    report.append(f"Ground truth edges        : {gt_count} ({gt_count/len(edges_out)*100:.1f}%)")
    report.append("")

    report.append("=== Distribution by consensus_level ===")
    for level in ordered_levels:
        cnt = int(dist.get(level, 0))
        pct = cnt / len(edges_out) * 100 if len(edges_out) else 0
        marker = "✅ GT" if level in ("Verified_Pulitiklan", "Rule_Based_GT") else "  "
        report.append(f"  {marker}  {level:<22}: {cnt:>5} ({pct:5.1f}%)")
    report.append("")

    report.append("=== Consensus × relation_label ===")
    cross = pd.crosstab(edges_out["relation_label"], edges_out["consensus_level"])
    report.append(cross.to_string())
    report.append("")

    report.append("=== Consensus × signal_count ===")
    cross2 = pd.crosstab(edges_out["signal_count"], edges_out["consensus_level"])
    report.append(cross2.to_string())
    report.append("")

    # Sample edges per level
    report.append("=== Sample edges per consensus level ===")
    for level in ordered_levels:
        sub = edges_out[edges_out["consensus_level"] == level]
        if len(sub) == 0:
            continue
        report.append(f"\n  [{level}] ({len(sub)} edges)")
        for _, e in sub.head(5).iterrows():
            a = id2name.get(e["person_a_id"], "?")
            b = id2name.get(e["person_b_id"], "?")
            report.append(
                f"    P={e['probability']:<5} sig={e['signal_count']}/4  "
                f"{e['relation_label']:<20}  {a} ↔ {b}"
            )

    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print(f"✅ Saved report:         {OUT_REPORT}")

    # ---- Console summary ----
    print(f"\n{'=' * 70}")
    print("=== FINAL DISTRIBUTION ===")
    print(f"{'=' * 70}")
    for level in ordered_levels:
        cnt = int(dist.get(level, 0))
        pct = cnt / len(edges_out) * 100 if len(edges_out) else 0
        marker = "✅" if level in ("Verified_Pulitiklan", "Rule_Based_GT") else "  "
        print(f"  {marker}  {level:<22}: {cnt:>5} ({pct:5.1f}%)")
    print(f"\nGround truth: {gt_count} / {len(edges_out)} ({gt_count/len(edges_out)*100:.1f}%)")

    # ---- Validation ----
    print(f"\n{'=' * 70}")
    print("=== VALIDATION CHECKS ===")
    print(f"{'=' * 70}")

    checks = []
    # All edges have consensus_level
    checks.append(("All edges classified", edges_out["consensus_level"].notna().all() and (edges_out["consensus_level"] != "").all()))
    # GT edges all have P=1.00
    gt_prob_ok = (edges_out[edges_out["is_ground_truth"] == True]["probability"].astype(float) == 1.0).all()
    checks.append(("All GT edges at P=1.00", gt_prob_ok))
    # No self-loops
    checks.append(("No self-loops", (edges_out["person_a_id"] != edges_out["person_b_id"]).all()))
    # No duplicate edge_ids
    checks.append(("No duplicate edge_ids", not edges_out["edge_id"].duplicated().any()))
    # No duplicate person pairs
    pairs = edges_out.apply(lambda r: tuple(sorted([r["person_a_id"], r["person_b_id"]])), axis=1)
    checks.append(("No duplicate person pairs", not pairs.duplicated().any()))
    # Probability in [0, 1]
    probs = edges_out["probability"].astype(float)
    checks.append(("All probabilities in [0, 1]", ((probs >= 0) & (probs <= 1)).all()))

    all_pass = True
    for name, ok in checks:
        status = "✅" if ok else "❌"
        print(f"  {status} {name}")
        if not ok:
            all_pass = False

    if all_pass:
        print(f"\n✅ ALL CHECKS PASSED — production file is ready for dashboard")
    else:
        print(f"\n❌ Some checks failed — review before shipping")


if __name__ == "__main__":
    main()