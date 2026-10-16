import os
import re
import pandas as pd

# Load national nodes
nodes_file = os.path.join('PN1_national_level', 'data', 'national_nodes.csv')
if not os.path.exists(nodes_file):
    nodes_file = 'national_nodes.csv'

df_nodes = pd.read_csv(nodes_file)

# Build name-to-person_id lookup
name_to_pid = {}
for _, row in df_nodes.iterrows():
    pid = row['person_id']
    full_clean = str(row['full_name_clean']).strip().upper()
    first = str(row['first_name']).strip().upper()
    middle = str(row['middle_name']).strip().upper() if pd.notna(row['middle_name']) else ''
    last = str(row['last_name']).strip().upper()
    
    name_to_pid[full_clean] = pid
    name_to_pid[f"{first} {last}"] = pid
    if middle:
        name_to_pid[f"{first} {middle} {last}"] = pid
        name_to_pid[f"{first} {middle[0]}. {last}"] = pid
        
    if pd.notna(row['aliases']):
        for alias in str(row['aliases']).split(','):
            a_clean = alias.strip().upper()
            if a_clean:
                name_to_pid[a_clean] = pid
                name_to_pid[f"{a_clean} {last}"] = pid

def resolve_person(name_raw):
    clean = name_raw.strip().upper()
    if clean in name_to_pid:
        return name_to_pid[clean]
    for k, v in name_to_pid.items():
        if len(k) > 4 and (k in clean or clean in k):
            return v
    return None

# Parse text lines
kinship_file = 'kinship_edges_2.txt'
if not os.path.exists(kinship_file):
    kinship_file = 'kinship_edges.txt'

edges = []
seen = set()

with open(kinship_file, 'r', encoding='utf-8') as f:
    for line in f:
        line_str = line.strip()
        if not line_str or ':' not in line_str or '->' not in line_str:
            continue
        parts = line_str.split(':')
        p1 = parts[0].strip()
        p2_rel = parts[1].split('->')
        p2 = p2_rel[0].strip()
        rel = p2_rel[1].strip()
        deg_str = parts[2].strip() if len(parts) > 2 else ''
        type_str = parts[3].strip() if len(parts) > 3 else 'Consanguinity'
        
        pid1 = resolve_person(p1)
        pid2 = resolve_person(p2)
        
        if pid1 and pid2 and pid1 != pid2:
            key = (pid1, pid2, rel)
            if key in seen:
                continue
            seen.add(key)
            
            deg = 1
            deg_match = re.search(r'(\d+)', deg_str)
            if deg_match:
                deg = int(deg_match.group(1))
                
            ktype = 'Consanguinity'
            if 'AFFINITY' in type_str.upper():
                ktype = 'Affinity'
            elif 'COMMON' in type_str.upper():
                ktype = 'Common_Law'
                
            edges.append({
                'edge_id': f"EDGE-{len(edges)+1:06d}",
                'person_a_id': pid1,
                'person_b_id': pid2,
                'relation_label': rel,
                'civil_degree': deg,
                'kinship_type': ktype,
                'source_document': 'PulitiKlan'
            })

df_edges = pd.DataFrame(edges)
output_path = os.path.join('PN1_national_level', 'data', 'edges_kinship.csv')
os.makedirs(os.path.dirname(output_path), exist_ok=True)
df_edges.to_csv(output_path, index=False)
print(f"[SUCCESS] Saved {len(df_edges)} national kinship edges to '{output_path}'.")