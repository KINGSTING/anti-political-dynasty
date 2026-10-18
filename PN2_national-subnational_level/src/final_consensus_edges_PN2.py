"""
PN2 FINAL CONSENSUS — production edge file
-------------------------------------------
Merges fuzzy + structural signals (from edges_structurally_validated.csv)
with pulitiklan verdicts (from the earlier cross_validation run) and produces
the production edge file with consensus_level labels.
"""

import os
import pandas as pd
from rapidfuzz.distance import JaroWinkler

# ==================== PATHS ====================
BASE = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty"
PN2_DATA = os.path.join(BASE, "PN2_national-subnational_level", "data")
PN3_CV   = os.path.join(BASE, "PN3_inter-intra_local_level", "data", "cross_validation")

INPUT_EDGES          = os.path.join(PN2_DATA, "edges_structurally_validated.csv")
PULITIKLAN_CV        = os.path.join(PN3_CV, "PN2_pulitiklan_cross_validation.csv")
NODES_CSV            = os.path.join(PN2_DATA, "national+subnational_nodes.csv")
DUPLICATE_CANDIDATES = os.path.join(PN2_DATA, "cross_validation", "duplicate_candidates.csv")

OUT_FINAL  = os.path.join(PN2_DATA, "national+subnational_edges_FINAL.csv")
OUT_GT     = os.path.join(PN2_DATA, "national+subnational_edges_FINAL_gt.csv")
OUT_AUDIT  = os.path.join(PN2_DATA, "national+subnational_edges_FINAL_audit.csv")
OUT_REPORT = os.path.join(PN2_DATA, "final_consensus_report.txt")


def safe_float(val, default=0.0):
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
    return str(val).strip().lower() in ("true", "1", "yes", "t")


def identify_true_duplicates(nodes_df, candidates_df):
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
    a, b = row["person_a_id"], row["person_b_id"]
    pv = str(row.get("pulitiklan_verdict", "")).strip()
    fv = str(row.get("fuzzy_verdict", "")).strip()
    prob = safe_float(row.get("probability"), default=0.0)
    orig_gt = is_true(row.get("is_ground_truth", "False"))
    struct_conf = safe_float(row.get("structural_confidence"), default=0.0)

    if pv == "contradicted":
        return 0.10, "Contradicted", False
    if (a, b) in true_dupes:
        return 0.10, "Duplicate_Record", False
    if pv == "verified_explicit":
        return 1.00, "Verified_Pulitiklan", True
    if orig_gt:
        return 1.00, "Rule_Based_GT", True
    if pv == "baseline_mindanao":
        return prob, "Baseline_Mindanao", False

    votes = 0
    if prob >= 0.85:
        votes += 1
    if fv in ("variant_confirmed", "variant_likely"):
        votes += 1
    if struct_conf >= 0.75:
        votes += 1

    if votes >= 2:
        return 0.95, "Consensus_High", False
    if votes == 1:
        return prob, "Single_Method", False
    return prob, "Low_Confidence", False


def count_signals(row, true_dupes):
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


def main():
    print("=" * 70)
    print("=== PN2 FINAL CONSENSUS ===")
    print("=" * 70)

    print(f"\nLoading structurally-validated edges: {INPUT_EDGES}")
    if not os.path.exists(INPUT_EDGES):
        print(f"CRITICAL: {INPUT_EDGES} not found. Run fuzzy + structural first.")
        return
    edges = pd.read_csv(INPUT_EDGES, dtype=str, keep_default_na=False)
    print(f"  {len(edges)} edges")

    print(f"\nLoading Pulitiklan cross-validation: {PULITIKLAN_CV}")
    if not os.path.exists(PULITIKLAN_CV):
        print(f"⚠ Not found — all edges will default to 'unverifiable' pulitiklan_verdict")
        edges["pulitiklan_verdict"] = ""
    else:
        cv = pd.read_csv(PULITIKLAN_CV, dtype=str, keep_default_na=False)
        print(f"  {len(cv)} cross-validation records")
        # Merge by (person_a_id, person_b_id) — stable key regardless of edge_id renumbering
        key_cv = cv.assign(_k=cv["person_a_id"] + "|" + cv["person_b_id"]).set_index("_k")["pulitiklan_verdict"].to_dict()
        key_cv_rev = cv.assign(_k=cv["person_b_id"] + "|" + cv["person_a_id"]).set_index("_k")["pulitiklan_verdict"].to_dict()
        merged_verdicts = []
        for _, r in edges.iterrows():
            k = f"{r['person_a_id']}|{r['person_b_id']}"
            v = key_cv.get(k, key_cv_rev.get(k, "unverifiable"))
            merged_verdicts.append(v)
        edges["pulitiklan_verdict"] = merged_verdicts
        matched = sum(1 for v in merged_verdicts if v != "unverifiable")
        print(f"  → {matched}/{len(edges)} edges matched to a cross-validation record")

    print(f"\nLoading nodes: {NODES_CSV}")
    nodes = pd.read_csv(NODES_CSV, dtype=str, keep_default_na=False)
    print(f"  {len(nodes)} nodes")

    candidates = None
    if os.path.exists(DUPLICATE_CANDIDATES):
        print(f"\nLoading duplicate candidates: {DUPLICATE_CANDIDATES}")
        candidates = pd.read_csv(DUPLICATE_CANDIDATES, dtype=str, keep_default_na=False)
        print(f"  {len(candidates)} candidate pairs")

    true_dupes = identify_true_duplicates(nodes, candidates)
    print(f"  → {len(true_dupes) // 2} confirmed duplicate pairs")

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
    edges_out = edges.copy()
    edges_out["original_probability"] = edges_out["probability"]
    edges_out["probability"]     = df_cons["final_probability"].round(3)
    edges_out["consensus_level"] = df_cons["consensus_level"]
    edges_out["is_ground_truth"] = df_cons["final_is_gt"]
    edges_out["signal_count"]    = df_cons["signal_count"]

    # Deduplicate reciprocal / duplicate person pairs into single canonical undirected edges
    print("\nDeduplicating reciprocal person pairs into canonical undirected edges...")
    before_count = len(edges_out)
    edges_out["_gt_bool"] = edges_out["is_ground_truth"].astype(bool)
    edges_out["_prob_num"] = pd.to_numeric(edges_out["probability"], errors="coerce").fillna(0)
    edges_out["_sig_num"] = pd.to_numeric(edges_out["signal_count"], errors="coerce").fillna(0)
    edges_out["pair_key"] = edges_out.apply(
        lambda r: tuple(sorted([str(r["person_a_id"]).strip(), str(r["person_b_id"]).strip()])), axis=1
    )

    edges_out = (
        edges_out.sort_values(
            by=["_gt_bool", "_prob_num", "_sig_num"],
            ascending=[False, False, False],
        )
        .drop_duplicates(subset=["pair_key"], keep="first")
        .drop(columns=["pair_key", "_gt_bool", "_prob_num", "_sig_num"])
        .reset_index(drop=True)
    )
    edges_out["edge_id"] = [f"EDGE-{i+1:06d}" for i in range(len(edges_out))]
    print(f"  → Deduplicated: {before_count} -> {len(edges_out)} canonical edges")

    priority_cols = [
        "edge_id", "person_a_id", "person_b_id",
        "relation_label", "civil_degree", "kinship_type",
        "consensus_level", "probability", "original_probability",
        "is_ground_truth", "signal_count", "source_document",
        "fuzzy_verdict", "fuzzy_score",
        "structural_verdict", "structural_confidence",
        "pulitiklan_verdict",
    ]
    present = [c for c in priority_cols if c in edges_out.columns]
    remaining = [c for c in edges_out.columns if c not in present]
    edges_out = edges_out[present + remaining]

    edges_out.to_csv(OUT_FINAL, index=False, encoding="utf-8-sig")
    print(f"\n✅ Saved production file: {OUT_FINAL}")

    gt = edges_out[edges_out["is_ground_truth"] == True].copy()
    gt.to_csv(OUT_GT, index=False, encoding="utf-8-sig")
    print(f"✅ Saved GT subset:      {OUT_GT} ({len(gt)} edges)")

    audit_levels = ["Contradicted", "Duplicate_Record", "Low_Confidence"]
    audit = edges_out[edges_out["consensus_level"].isin(audit_levels)].copy()
    audit.to_csv(OUT_AUDIT, index=False, encoding="utf-8-sig")
    print(f"✅ Saved audit subset:   {OUT_AUDIT} ({len(audit)} edges)")

    dist = edges_out["consensus_level"].value_counts()
    ordered_levels = [
        "Verified_Pulitiklan", "Rule_Based_GT", "Baseline_Mindanao",
        "Consensus_High", "Single_Method", "Low_Confidence",
        "Contradicted", "Duplicate_Record",
    ]
    gt_count = int((edges_out["is_ground_truth"] == True).sum())

    print(f"\n{'=' * 70}")
    print("=== FINAL DISTRIBUTION ===")
    print(f"{'=' * 70}")
    for level in ordered_levels:
        cnt = int(dist.get(level, 0))
        pct = cnt / len(edges_out) * 100 if len(edges_out) else 0
        marker = "✅" if level in ("Verified_Pulitiklan", "Rule_Based_GT") else "  "
        print(f"  {marker}  {level:<22}: {cnt:>5} ({pct:5.1f}%)")
    print(f"\nGround truth: {gt_count} / {len(edges_out)} ({gt_count/len(edges_out)*100:.1f}%)")

    print(f"\n{'=' * 70}")
    print("=== VALIDATION CHECKS ===")
    print(f"{'=' * 70}")
    checks = []
    checks.append(("All edges classified", edges_out["consensus_level"].notna().all() and (edges_out["consensus_level"] != "").all()))
    gt_prob_ok = (edges_out[edges_out["is_ground_truth"] == True]["probability"].astype(float) == 1.0).all()
    checks.append(("All GT edges at P=1.00", gt_prob_ok))
    checks.append(("No self-loops", (edges_out["person_a_id"] != edges_out["person_b_id"]).all()))
    checks.append(("No duplicate edge_ids", not edges_out["edge_id"].duplicated().any()))
    pairs = edges_out.apply(lambda r: tuple(sorted([r["person_a_id"], r["person_b_id"]])), axis=1)
    checks.append(("No duplicate person pairs", not pairs.duplicated().any()))
    probs = edges_out["probability"].astype(float)
    checks.append(("All probabilities in [0, 1]", ((probs >= 0) & (probs <= 1)).all()))

    all_pass = True
    for name, ok in checks:
        print(f"  {'✅' if ok else '❌'} {name}")
        if not ok:
            all_pass = False

    print(f"\n{'✅ ALL CHECKS PASSED' if all_pass else '❌ Some checks failed'}")

    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write(f"=== PN2 FINAL CONSENSUS REPORT ===\n")
        f.write(f"Total edges: {len(edges_out)}\n")
        f.write(f"Ground truth: {gt_count} ({gt_count/len(edges_out)*100:.1f}%)\n\n")
        for level in ordered_levels:
            cnt = int(dist.get(level, 0))
            pct = cnt / len(edges_out) * 100 if len(edges_out) else 0
            f.write(f"  {level:<22}: {cnt:>5} ({pct:5.1f}%)\n")
    print(f"✅ Saved report:         {OUT_REPORT}")


if __name__ == "__main__":
    main()