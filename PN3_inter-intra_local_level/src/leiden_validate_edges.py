"""
PN3 Method 2 — Leiden structural validation (v2)
------------------------------------------------
Two fixes over v1:
1. Uses leidenalg directly (not cdlib — its optional deps fail silently).
2. Builds a PATH-AUGMENTED graph (2-hop co-cluster edges) so family clusters
   become dense K_n cliques. Community detection is meaningful only when
   there's actual structure — the original graph is ~94% dyadic pairs.

Also reports component-size diagnostics so you can see which edges
can actually be structurally validated vs which are fundamentally dyadic.
"""

import os
import re
from collections import Counter, defaultdict

import networkx as nx
import pandas as pd

# ==================== PATHS ====================
BASE = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN3_inter-intra_local_level\data"
NODES_CSV   = os.path.join(BASE, "inter-intra_local_nodes.csv")
EDGES_CSV   = os.path.join(BASE, "inter-intra_local_edges_fuzzy_validated.csv")
OUT_CSV     = os.path.join(BASE, "inter-intra_local_edges_leiden_validated.csv")
OUT_REPORT  = os.path.join(BASE, "leiden_validation_report.txt")

# ==================== CONFIG ====================
RESOLUTIONS = [0.5, 1.0, 1.5]
SEEDS       = [0, 1, 2]
STRONG_THRESH   = 0.80
MODERATE_THRESH = 0.50
MAX_NEIGHBORS_FOR_AUGMENT = 30   # skip hubs to prevent combinatorial explosion


# ==================== HELPERS ====================
def normalize(s):
    if pd.isna(s):
        return ""
    s = str(s).upper().strip()
    s = re.sub(r"[^A-Z\s]", " ", s)
    s = " ".join(s.split())
    s = re.sub(r"\s+(JR|SR|II|III|IV|V|VI)$", "", s).strip()
    return s


def run_leiden_direct(G, resolution, seed):
    """
    Try leidenalg directly. This is the only path that guarantees real Leiden.
    Returns (node2com dict, method_name) or (None, reason).
    """
    try:
        import igraph as ig
        import leidenalg
    except ImportError as e:
        return None, f"import_error: {e}"

    try:
        node_list = list(G.nodes())
        node2idx  = {n: i for i, n in enumerate(node_list)}
        edge_list = [(node2idx[a], node2idx[b]) for a, b in G.edges()]
        weights   = [float(G[a][b].get("weight", 1.0)) for a, b in G.edges()]

        g = ig.Graph(n=len(node_list), edges=edge_list,
                     edge_attrs={"weight": weights})

        partition = leidenalg.find_partition(
            g,
            leidenalg.RBConfigurationVertexPartition,
            weights="weight",
            resolution_parameter=resolution,
            seed=seed,
        )

        node2com = {node_list[i]: partition.membership[i]
                    for i in range(len(node_list))}
        return node2com, "leidenalg"

    except Exception as e:
        return None, f"leiden_runtime_error: {e}"


def build_path_augmented_graph(G, max_neighbors=30):
    """
    For each node, connect its neighbors pairwise (2-hop edges).
    A 5-person family cluster becomes a K5 clique.
    Existing edges get a small weight boost (they have corroborating support).
    """
    G_aug = G.copy()
    augmented_edges = 0
    for node in G.nodes():
        nbrs = list(G.neighbors(node))
        if len(nbrs) > max_neighbors:
            continue  # skip hubs
        for i, a in enumerate(nbrs):
            for b in nbrs[i+1:]:
                if not G_aug.has_edge(a, b):
                    G_aug.add_edge(a, b, weight=0.3, augmented=True)
                    augmented_edges += 1
                else:
                    # Existing kinship edge with shared neighbor — reinforce it
                    G_aug[a][b]["weight"] = G_aug[a][b]["weight"] * 1.1
    return G_aug, augmented_edges


def consensus_label(frac):
    if frac >= STRONG_THRESH:   return "strong"
    if frac >= MODERATE_THRESH: return "moderate"
    return "weak"


def component_size_bucket(size):
    if size <= 2:   return "dyad"
    if size <= 5:   return "small_cluster"
    if size <= 10:  return "medium_cluster"
    return "large_cluster"


# ==================== MAIN ====================
def main():
    # ---- Load ----
    print(f"Loading nodes: {NODES_CSV}")
    nodes = pd.read_csv(NODES_CSV, dtype={"home_psgc": str}, keep_default_na=False)
    nodes["home_psgc"] = nodes["home_psgc"].str.zfill(10)
    id2name = dict(zip(nodes["person_id"], nodes["full_name_clean"]))
    id2node = nodes.set_index("person_id").to_dict("index")

    print(f"Loading fuzzy edges: {EDGES_CSV}")
    edges = pd.read_csv(EDGES_CSV, dtype=str, keep_default_na=False)
    edges["probability"] = edges["probability"].astype(float)
    print(f"  {len(edges)} edges")

    # ---- Build original graph ----
    G = nx.Graph()
    for _, e in edges.iterrows():
        a, b = e["person_a_id"], e["person_b_id"]
        w = float(e["probability"])
        if G.has_edge(a, b):
            G[a][b]["weight"] = max(G[a][b]["weight"], w)
        else:
            G.add_edge(a, b, weight=w)

    print(f"\nOriginal graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # ---- Component-size diagnostics ----
    components = list(nx.connected_components(G))
    sizes = [len(c) for c in components]
    size_dist = Counter(component_size_bucket(s) for s in sizes)

    print(f"Connected components: {len(components)}")
    print(f"  Dyads (size 2)     : {size_dist.get('dyad', 0)}")
    print(f"  Small  (3-5)       : {size_dist.get('small_cluster', 0)}")
    print(f"  Medium (6-10)      : {size_dist.get('medium_cluster', 0)}")
    print(f"  Large  (11+)       : {size_dist.get('large_cluster', 0)}")

    # Per-edge component size map
    edge_comp_size = {}
    for comp in components:
        sz = len(comp)
        for a in comp:
            for b in G.neighbors(a):
                edge_comp_size[(a, b)] = sz

    # ---- Augmented graph ----
    print(f"\n=== Building path-augmented graph ===")
    G_aug, n_aug = build_path_augmented_graph(G, MAX_NEIGHBORS_FOR_AUGMENT)
    print(f"  Augmented graph: {G_aug.number_of_nodes()} nodes, "
          f"{G_aug.number_of_edges()} edges (+{n_aug} 2-hop edges)")

    # ---- Leiden runs on AUGMENTED graph ----
    print(f"\n=== Running real Leiden on augmented graph ({len(RESOLUTIONS)}×{len(SEEDS)}) ===")
    runs_direct = []
    runs_aug    = []
    leiden_worked = False

    for res in RESOLUTIONS:
        for seed in SEEDS:
            # Direct graph (baseline)
            node2com_direct, method_direct = run_leiden_direct(G, res, seed)
            # Augmented graph (real structure)
            node2com_aug, method_aug = run_leiden_direct(G_aug, res, seed)

            if method_direct == "leidenalg" and method_aug == "leidenalg":
                leiden_worked = True
                n_d = len(set(node2com_direct.values()))
                n_a = len(set(node2com_aug.values()))
                largest_a = max(Counter(node2com_aug.values()).values())
                print(f"  res={res} seed={seed}: direct={n_d} comms | "
                      f"augmented={n_a} comms (largest={largest_a})")
                runs_direct.append(node2com_direct)
                runs_aug.append(node2com_aug)
            else:
                print(f"  res={res} seed={seed}: SKIPPED ({method_direct})")

    if not runs_aug:
        print("\nCRITICAL: Leiden never ran. Install with:")
        print("  pip install python-igraph leidenalg")
        print("\nWriting partial diagnostic output (component sizes only)...")
        _write_diagnostic_only(edges, G, edge_comp_size, id2name, size_dist, OUT_CSV, OUT_REPORT)
        return

    # ---- Compute per-edge agreement on augmented graph ----
    print(f"\n=== Computing edge agreement on augmented graph ===")
    edge_agree = {}
    for a, b in G.edges():
        same = sum(1 for nc in runs_aug
                   if nc.get(a) is not None and nc.get(a) == nc.get(b))
        edge_agree[(a, b)] = same / len(runs_aug)

    # ---- Enrich edges ----
    display_communities = runs_aug[0]   # first augmented-graph run for community IDs

    edges["leiden_community_a"] = edges["person_a_id"].map(display_communities)
    edges["leiden_community_b"] = edges["person_b_id"].map(display_communities)
    edges["community_agree"] = [
        round(edge_agree.get((e["person_a_id"], e["person_b_id"]),
             edge_agree.get((e["person_b_id"], e["person_a_id"]), 0.0)), 3)
        for _, e in edges.iterrows()
    ]
    edges["component_size"] = [
        edge_comp_size.get((e["person_a_id"], e["person_b_id"]),
         edge_comp_size.get((e["person_b_id"], e["person_a_id"]), 0))
        for _, e in edges.iterrows()
    ]
    edges["component_bucket"] = edges["component_size"].apply(component_size_bucket)
    edges["leiden_consensus"]  = edges["community_agree"].apply(consensus_label)

    # ---- Save ----
    edges.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    # ---- Report ----
    report = []
    report.append("=== PN3 Leiden Structural Validation Report (v2) ===")
    report.append(f"Input edges        : {len(edges)}")
    report.append(f"Original graph     : {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    report.append(f"Augmented graph    : {G_aug.number_of_nodes()} nodes, {G_aug.number_of_edges()} edges (+{n_aug} 2-hop)")
    report.append(f"Leiden runs        : {len(runs_aug)} on augmented graph (real Leiden)")
    report.append("")

    report.append("=== Component-size distribution ===")
    for bucket, cnt in size_dist.items():
        report.append(f"  {bucket:<15}: {cnt}")

    report.append("")
    report.append("=== Edge-level structural consensus ===")
    dist = edges["leiden_consensus"].value_counts()
    for label in ["strong", "moderate", "weak"]:
        cnt = dist.get(label, 0)
        pct = cnt / len(edges) * 100
        report.append(f"  {label:<10}: {cnt:>5} ({pct:5.1f}%)")

    report.append("")
    report.append("=== Consensus × component_bucket ===")
    cross = pd.crosstab(edges["component_bucket"], edges["leiden_consensus"])
    report.append(cross.to_string())

    report.append("")
    report.append("=== Consensus × relation_label ===")
    cross2 = pd.crosstab(edges["relation_label"], edges["leiden_consensus"])
    report.append(cross2.to_string())

    # Sample weak edges
    weak = edges[edges["leiden_consensus"] == "weak"].copy()
    if len(weak):
        weak = weak.sort_values("community_agree").head(20)
        report.append("")
        report.append(f"=== 20 weakest edges (bridging / false positives) ===")
        for _, e in weak.iterrows():
            a = id2name.get(e["person_a_id"], "?")
            b = id2name.get(e["person_b_id"], "?")
            report.append(f"  [{e['community_agree']:.2f}] comp={e['component_size']:<3} "
                          f"{e['relation_label']:<22} {a} <-> {b}")

    # Top communities
    report.append("")
    report.append("=== Top 10 Leiden communities (augmented graph) ===")
    comm_members = defaultdict(list)
    for n, c in display_communities.items():
        comm_members[c].append(n)
    top = sorted(comm_members.items(), key=lambda x: len(x[1]), reverse=True)[:10]
    for cid, members in top:
        surnames = Counter()
        for pid in members:
            sn = normalize(id2node.get(pid, {}).get("last_name", ""))
            if sn:
                surnames[sn] += 1
        top_surnames = ", ".join(f"{s}({n})" for s, n in surnames.most_common(3))
        report.append(f"  Community {cid:>4}: {len(members):>3} members | {top_surnames}")

    with open(OUT_REPORT, "w", encoding="utf-8") as f:
        f.write("\n".join(report))

    # ---- Summary ----
    print(f"\n{'=' * 60}")
    print("=== SUMMARY ===")
    print(f"Real Leiden runs completed: {len(runs_aug)}")
    print(f"\nEdge structural consensus:")
    for label in ["strong", "moderate", "weak"]:
        cnt = dist.get(label, 0)
        pct = cnt / len(edges) * 100
        print(f"  {label:<10}: {cnt:>5} ({pct:5.1f}%)")
    print(f"\nBy component bucket:")
    print(edges.groupby(["component_bucket", "leiden_consensus"]).size().to_string())
    print(f"\nSaved:")
    print(f"  {OUT_CSV}")
    print(f"  {OUT_REPORT}")


def _write_diagnostic_only(edges, G, edge_comp_size, id2name, size_dist, out_csv, out_report):
    """Fallback output if Leiden couldn't run — just add component-size columns."""
    edges["component_size"] = [
        edge_comp_size.get((e["person_a_id"], e["person_b_id"]), 0)
        for _, e in edges.iterrows()
    ]
    edges["component_bucket"] = edges["component_size"].apply(component_size_bucket)
    edges.to_csv(out_csv, index=False, encoding="utf-8-sig")

    lines = ["=== Leiden unavailable — component-size diagnostics only ==="]
    for bucket, cnt in size_dist.items():
        lines.append(f"  {bucket}: {cnt}")
    lines.append("")
    lines.append("Install real Leiden with: pip install python-igraph leidenalg")
    with open(out_report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()