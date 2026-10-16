import os
import pandas as pd
import networkx as nx
from pyvis.network import Network

def generate_full_kinship_network():
    nodes_csv = "politician_nodes.csv"
    edges_csv = "political_dynasties_edges.csv"
    output_html = "kinship_network.html"

    for fpath in [nodes_csv, edges_csv]:
        if not os.path.exists(fpath):
            print(f"Error: Missing required file -> {fpath}")
            return

    print("1. Loading base nodes and dynastic edges...")
    df_nodes = pd.read_csv(nodes_csv)
    df_edges = pd.read_csv(edges_csv)

    # Build a lookup dictionary for positions & units from our verified nodes file
    node_metadata = {}
    for _, row in df_nodes.iterrows():
        name = str(row['name']).strip()
        node_metadata[name] = {
            'position': str(row.get('position', 'Politician')),
            'unit': str(row.get('unit', 'Dynastic Family Member'))
        }

    # Detect edge columns dynamically
    col_a = 'person_a' if 'person_a' in df_edges.columns else 'Person_A'
    col_b = 'person_b' if 'person_b' in df_edges.columns else 'Person_B'
    rel_col = 'relation_label' if 'relation_label' in df_edges.columns else 'Relation_Label'

    print("2. Constructing fully connected network graph...")
    G = nx.Graph()

    # Collect ALL unique individuals mentioned in the edges file so no family ties are orphaned
    all_edge_nodes = set(df_edges[col_a].dropna().astype(str).str.strip()).union(
                       set(df_edges[col_b].dropna().astype(str).str.strip()))

    for name in all_edge_nodes:
        # Pull metadata if they were verified, otherwise default to a dynastic profile
        meta = node_metadata.get(name, {'position': 'Dynastic Politician', 'unit': 'Family Network'})
        G.add_node(name, title=f"Name: {name}<br>Position: {meta['position']}<br>Unit: {meta['unit']}", group=meta['position'])

    # Add edges between them
    added_edges = 0
    for _, row in df_edges.iterrows():
        p_a = str(row[col_a]).strip()
        p_b = str(row[col_b]).strip()
        relation = str(row.get(rel_col, "Family Tie"))

        if G.has_node(p_a) and G.has_node(p_b):
            G.add_edge(p_a, p_b, label=relation, title=f"Relation: {relation}")
            added_edges += 1

    print(f"\nNetwork Statistics:")
    print(f" - Total Connected Network Nodes: {G.number_of_nodes()}")
    print(f" - Total Active Dynastic Edges: {added_edges}")

    print("3. Generating updated interactive HTML network visualization...")
    net = Network(height="850px", width="100%", bgcolor="#1a1a1a", font_color="white", notebook=False)
    net.from_nx(G)
    
    # Adjust physics parameters to spread out clusters cleanly
    net.repulsion(node_distance=200, central_gravity=0.2, spring_length=150)
    net.save_graph(output_html)

    print(f"\n✅ Updated Kinship Network Complete! Saved to: {output_html}")

if __name__ == "__main__":
    generate_full_kinship_network()