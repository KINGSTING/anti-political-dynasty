"""
PN3 Method 2 (replacement) — Edge-level structural metrics
-----------------------------------------------------------
Leiden community detection is inapplicable on the kinship graph because:
  - ~49% of components are size-2 dyads (no internal structure to resolve)
  - Average degree 1.41 — too sparse for meaningful community splitting
  - All Leiden resolutions/seeds converge to identical partitions, making
    the "100% strong" result a mathematical tautology of connected components

This script replaces Leiden with edge-level metrics that ARE meaningful
on sparse graphs:

  - Common-neighbor count (cn) — how many triangles does this edge sit in?
  - Jaccard overlap of neighbor sets — structural context shared by endpoints
  - Adamic-Adar score — rarer shared neighbors count more
  - Bridge detection — would removing this edge disconnect the component?
  - Endpoint clustering coefficients — local density around each endpoint

Design principle:
  Positive structural evidence (triangles, high Jaccard) boosts edges.
  Absence of structural evidence does NOT penalize — dyads are legitimately
  possible (two isolated siblings with no other kinship edges). Dyads are
  labeled "isolated" = structurally unverifiable, left to Method 4.

Output feeds into Method 4 consensus vote via structural_confidence ∈ [0,1].
"""

import os
import re

import networkx as nx
import pandas as pd

# ==================== PATHS ====================
BASE = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN3_inter-intra_local_level\data"
NODES_CSV   = os.path.join(BASE, "inter-intra_local_nodes.csv")
EDGES_CSV   = os.path.join(BASE, "inter-intra_local_edges_fuzzy_validated.csv")
OUT_CSV     = os.path.join(BASE, "inter-intra_local_edges_structurally_validated.csv")
OUT_REPORT  = os.path.join(BASE, "structural_validation_report.txt")

# ==================== CONFIG ====================
JACCARD_STRONG = 0.40
JACCARD_MEDIUM = 0.20


# ==================== HELPERS ====================
def normalize(s):
    if pd.isna(s):
        return ""
    s = str(s).upper().strip()
    s = re.sub(r"[^A-Z\s]", " ", s)
    s = " ".join(s.split())
    s = re.sub(r"\s+(JR|SR|II|III|IV|V|VI)$", "", s).strip()
    return s


def adamic_adar(G, a, b):
    """Weighted common-neighbor score. Rarer shared neighbors count more."""
    common = set(G.neighbors(a)) & set(G.neighbors(b))
    score = 0.0
    for c in common:
        deg = G.degree(c)
        if deg > 1:
            score += 1.0 / (deg ** 0.5)
    return score


def classify_edge(cn, jaccard, is_bridge, comp_size):
    """
    Verdict hierarchy (strongest → weakest).
    Component size == 2 short-circuits to "isolated" — dyads cannot be
    structurally validated by definition, so is_bridge is irrelevant there.
    """
    if comp_size == 2:
        return "isolated"
    if is_bridge:
        return "bridge"
    if cn == 0:
        return "chain"
    if jaccard >= JACCARD_STRONG:
        return "strong_cluster"
    if jaccard >= JACCARD_MEDIUM:
        return "cluster_confirmed"
    return "weak_cluster"


def verdict_to_confidence(verdict, adamic):
    """Composite structural confidence in [0, 1]."""
    base = {
        "isolated":           0.00,
        "bridge":             0.15,
        "chain":              0.30,
        "weak_cluster":       0.50,
        "cluster_confirmed":  0.75,
        "strong_cluster":     0.90,
    }.get(verdict, 0.0)
    boost = min(0.10, adamic * 0.05)
    return round(min(1.0, base + boost), 3)


# ==================== MAIN ====================
def main():
    # ---- Load ----
    print(f"Loading nodes: {NODES_CSV}")
    nodes = pd.read_csv(NODES_CSV, dtype={"home_psgc": str}, keep_default_na=False)
    nodes["home_psgc"] = nodes["home_psgc"].str.zfill(10)
    id2name = dict(zip(nodes["person_id"], nodes["full_name_clean"]))

    print(f"Loading fuzzy edges: {EDGES_CSV}")
    edges = pd.read_csv(EDGES_CSV, dtype=str, keep_default_na=False)
    edges["probability"] = edges["probability"].astype(float)
    print(f"  {len(edges)} edges")

    # ---- Build graph ----
    G = nx.Graph()
    for _, e in edges.iterrows():
        a, b = e["person_a_id"], e["person_b_id"]
        w = float(e["probability"])
        if G.has_edge(a, b):
            G[a][b]["weight"] = max(G[a][b]["weight"], w)
        else:
            G.add_edge(a, b, weight=w)

    print(f"\nGraph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # ---- Precompute global structures ----
    print("\nComputing global structures...")
    components = list(nx.connected_components(G))
    node_to_comp_size = {}
    for comp in components:
        sz = len(comp)
        for n in comp:
            node_to_comp_size[n] = sz
    print(f"  {len(components)} connected components")

    bridges = set(tuple(sorted(e)) for e in nx.bridges(G))
    print(f"  {len(bridges)} bridges")

    triangles_count = nx.triangles(G)
    total_triangles = sum(triangles_count.values()) // 3
    print(f"  {total_triangles} triangles")

    clustering = nx.clustering(G)
    print(f"  Clustering coefficients computed")

    # ---- Per-edge metrics ----
    print(f"\nComputing per-edge structural metrics for {len(edges)} edges...")
    results = []
    for _, e in edges.iterrows():
        a, b = e["person_a_id"], e["person_b_id"]

        na = set(G.neighbors(a))
        nb = set(G.neighbors(b))
        common = na & nb
        cn = len(common)

        union = len(na | nb)
        jaccard = round(cn / union, 3) if union > 0 else 0.0

        is_bridge = tuple(sorted([a, b])) in bridges
        comp_size = node_to_comp_size.get(a, 0)
        aa = round(adamic_adar(G, a, b), 3)
        cl_a = round(clustering.get(a, 0.0), 3)
        cl_b = round(clustering.get(b, 0.0), 3)

        verdict = classify_edge(cn, jaccard, is_bridge, comp_size)
        confidence = verdict_to_confidence(verdict, aa)

        results.append({
            "structural_verdict": verdict,
            "structural_confidence": confidence,
            "common_neighbors": cn,
            "jaccard": jaccard,
            "adamic_adar": aa,
            "is_bridge": is_bridge,
            "component_size": comp_size,
            "clustering_a": cl_a,
            "clustering_b": cl_b,
        })

    df_struct = pd.DataFrame(results)
    edges_enriched = pd.concat([edges.reset_index(drop=True), df_struct], axis=1)
    edges_enriched.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    # ---- Report ----
    report = []
    report.append("=== PN3 Structural Metrics Validation (Method 2 replacement) ===")
    report.append(f"Input edges : {len(edges)}")
    report.append(f"Graph       : {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    report.append(f"Components  : {len(components)}")
    report.append(f"Bridges     : {len(bridges)}")
    report.append(f"Triangles   : {total_triangles}")
    report.append("")

    dist = edges_enriched["structural_verdict"].value_counts()
    report.append("=== Structural verdict distribution ===")
    for v in ["strong_cluster", "cluster_confirmed", "weak_cluster",
              "chain", "bridge", "isolated"]:
        cnt = dist.get(v, 0)
        pct = cnt / len(edges_enriched) * 100
        report.append(f"  {v:<20}: {cnt:>5} ({pct:5.1f}%)")

    report.append("")
    report.append("=== Verdict × relation_label ===")
    cross = pd.crosstab(edges_enriched["relation_label"],
                        edges_enriched["structural_verdict"])
    report.append(cross.to_string())

    report.append("")
    report.append("=== Verdict × fuzzy_verdict ===")
    if "fuzzy_verdict" in edges_enriched.columns:
        cross2 = pd.crosstab(edges_enriched["fuzzy_verdict"],
                             edges_enriched["structural_verdict"])
        report.append(cross2.to_string())

    report.append("")
    report.append("=== Sample edges per verdict ===")
    for verdict in ["strong_cluster", "cluster_confirmed",
                    "bridge", "isolated"]:
        sample = edges_enriched[edges_enriched["structural_verdict"] == verdict].head(5)
        if len(sample):
            report.append(f"\n  [{verdict.upper()}]")
            for _, e in sample.iterrows():
                a = id2name.get(e["person_a_id"], "?")
                b = id2name.get(e["person_b_id"], "?")
                report.append(
                    f"    cn={e['common_neighbors']:<2} jac={e['jaccard']:<5} "
                    f"conf={e['structural_confidence']:<5}  {a} <-> {b}"
                )

    report.append("")
    report.append("=== How to use in Method 4 consensus ===")
    report.append("Positive structural evidence BOOSTS; absence does NOT penalize.")
    report.append("  strong_cluster (conf 0.90) → +0.05 boost")
    report.append("  cluster_confirmed (0.75)   → +0.02 boost")
    report.append("  weak_cluster (0.50)        → no change")
    report.append("  chain (0.30) / bridge (0.15) → no change, flag for manual review")
    report.append("  isolated (0.00)            → no change — dyads are legitimate,")
    report.append("                                just structurally unverifiable")

    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(report))

    # ---- Summary ----
    print(f"\n{'=' * 60}")
    print("=== SUMMARY ===")
    print(f"Structural verdicts:")
    for v in ["strong_cluster", "cluster_confirmed", "weak_cluster",
              "chain", "bridge", "isolated"]:
        cnt = dist.get(v, 0)
        pct = cnt / len(edges_enriched) * 100
        print(f"  {v:<20}: {cnt:>5} ({pct:5.1f}%)")

    confirmed = int(dist.get("strong_cluster", 0)
                    + dist.get("cluster_confirmed", 0)
                    + dist.get("weak_cluster", 0))
    unverifiable = int(dist.get("isolated", 0)
                       + dist.get("bridge", 0)
                       + dist.get("chain", 0))

    print(f"\nStructurally confirmed    : {confirmed} "
          f"({confirmed / len(edges_enriched) * 100:.1f}%)")
    print(f"Structurally unverifiable : {unverifiable} "
          f"({unverifiable / len(edges_enriched) * 100:.1f}%)")

    print(f"\nSaved:")
    print(f"  {OUT_CSV}")
    print(f"  {OUT_REPORT}")


if __name__ == "__main__":
    main()