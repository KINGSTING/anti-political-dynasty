import pandas as pd
import re

def clean_name(name):
    name = str(name).lower()
    name = re.sub(r'["“\'].*?["”\']', '', name) 
    name = re.sub(r'\b(jr\.?|sr\.?|iii|ii|iv|atty\.?|dr\.?|ma\.|maria|datu|bai|hadja)\b', '', name)
    name = re.sub(r'[^a-z\s]', ' ', name)
    return re.sub(r'\s+', ' ', name).strip()

def build_master_dataset():
    print("1. Loading PULITIKLAN and Qwen Networks...")
    
    try:
        df_puli_nodes = pd.read_csv("pulitiklan_nodes.csv")
        df_puli_edges = pd.read_csv("pulitiklan_edges.csv")
        df_qwen_edges = pd.read_csv("political_dynasties_edges.csv")
    except FileNotFoundError as e:
        print(f"Error loading CSVs: {e}")
        return

    # Combine edges
    df_all_edges = pd.concat([df_puli_edges, df_qwen_edges], ignore_index=True)
    col_a = 'person_a' if 'person_a' in df_all_edges.columns else 'Person_A'
    col_b = 'person_b' if 'person_b' in df_all_edges.columns else 'Person_B'
    df_all_edges = df_all_edges.drop_duplicates(subset=[col_a, col_b], keep='first').copy()

    # Bring in Qwen nodes safely
    existing_nodes = set(df_puli_nodes['node_id'].dropna())
    qwen_names = set(df_all_edges[col_a].dropna()).union(set(df_all_edges[col_b].dropna()))
    missing_nodes = qwen_names - existing_nodes
    
    new_nodes_df = pd.DataFrame({
        'node_id': list(missing_nodes),
        'office_description': 'Unspecified Office',
        'location': 'Unspecified Location',
        'status': 'Incumbent' # Default Qwen extracted nodes as active
    })
    
    df_nodes = pd.concat([df_puli_nodes, new_nodes_df], ignore_index=True)

    # 2. Apply robust incumbent filtering (same logic as filter_incumbents.py)
    col_desc = 'office_description' if 'office_description' in df_nodes.columns else 'Description'
    col_id = 'node_id' if 'node_id' in df_nodes.columns else 'Name'

    def is_incumbent(row):
        desc_lower = str(row.get(col_desc, '')).lower()
        status_lower = str(row.get('status', '')).lower()
        
        if any(w in desc_lower for w in ['former', 'deceased', 'past candidate', 'historical']) and 'incumbent' not in desc_lower:
            return False
        if any(w in desc_lower for w in ['incumbent', 'current office']) or 'incumbent' in status_lower:
            return True
        if any(w in desc_lower for w in ['mayor', 'governor', 'representative', 'congressman', 'congresswoman', 'senator', 'councilor', 'board member', 'vice mayor', 'vice governor']):
            return True
        return False

    df_incumbent_nodes = df_nodes[df_nodes.apply(is_incumbent, axis=1)].copy()
    
    # Drop exact node duplicates keeping the first occurrence
    df_incumbent_nodes = df_incumbent_nodes.drop_duplicates(subset=[col_id], keep='first').copy()

    print(f"Total Incumbent Politicians Kept: {len(df_incumbent_nodes)}")

    print("\n3. Enriching with OpenHalalan 2025 Winners (Optional Geodata Match)...")
    try:
        df_winners = pd.read_csv("data/NLE_Winners_2004-2025.csv", low_memory=False)
        df_2025 = df_winners[df_winners['year'] == 2025].copy() if 'year' in df_winners.columns else df_winners.copy()
        
        cand_col = next((c for c in df_2025.columns if 'name' in c.lower()), df_2025.columns[0])
        prov_col = next((c for c in df_2025.columns if 'prov' in c.lower()), None)
        muni_col = next((c for c in df_2025.columns if 'city' in c.lower() or 'muni' in c.lower()), None)

        df_2025['match_name'] = df_2025[cand_col].apply(clean_name)
        df_incumbent_nodes['match_name'] = df_incumbent_nodes['node_id'].apply(clean_name)

        if 'location' not in df_incumbent_nodes.columns:
            df_incumbent_nodes['location'] = "Unspecified Location"

        enriched_count = 0
        for idx, node in df_incumbent_nodes.iterrows():
            s_words = set(node['match_name'].split())
            if not s_words:
                continue
            
            # Find matches in openhalalan
            match = df_2025[df_2025['match_name'].apply(lambda w: len(s_words.intersection(set(w.split()))) >= 2)]
            if not match.empty:
                top_match = match.iloc[0]
                enriched_count += 1
                if prov_col and pd.notna(top_match[prov_col]):
                    df_incumbent_nodes.at[idx, 'location'] = str(top_match[prov_col]).title()

        print(f"Successfully enriched geographic data for {enriched_count} politicians.")
    except FileNotFoundError:
        print("Note: OpenHalalan file not found, keeping existing text locations.")

    # 4. Filter Edges to only keep active connections where BOTH are incumbents
    incumbent_names = set(df_incumbent_nodes[col_id])
    df_incumbent_edges = df_all_edges[
        (df_all_edges[col_a].isin(incumbent_names)) & 
        (df_all_edges[col_b].isin(incumbent_names))
    ].copy()

    # Clean export
    df_incumbent_nodes.drop(columns=['match_name'], inplace=True, errors='ignore')
    
    df_incumbent_nodes.to_csv("master_incumbent_nodes.csv", index=False)
    df_incumbent_edges.to_csv("master_incumbent_edges.csv", index=False)

    print("\n✅ Master Dataset Compilation Complete!")
    print(f"Master Incumbent Nodes: {len(df_incumbent_nodes)}")
    print(f"Master Active Dynastic Connections: {len(df_incumbent_edges)}")
    print("Saved to: master_incumbent_nodes.csv and master_incumbent_edges.csv")

if __name__ == "__main__":
    build_master_dataset()