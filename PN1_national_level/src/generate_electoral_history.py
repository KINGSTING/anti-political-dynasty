import os
import time
import pandas as pd
import numpy as np

start_total = time.time()

# ---------------------------------------------------------
# STEP 1: Load Kinship Graph
# ---------------------------------------------------------
print("[1/5] Loading Kinship Graph (kinship_edges.txt)...")
kinship_map = {}
kinship_file = 'kinship_edges.txt'

if os.path.exists(kinship_file):
    with open(kinship_file, 'r', encoding='utf-8') as f:
        for line in f:
            if ':' in line and '->' in line:
                parts = line.strip().split(':')
                p1 = parts[0].strip().upper()
                p2_degree = parts[1].split('->')
                p2 = p2_degree[0].strip().upper()
                degree_str = parts[2].strip() if len(parts) > 2 else ''
                
                deg = None
                for token in degree_str.split():
                    if any(token.endswith(sfx) for sfx in ['st', 'nd', 'rd', 'th']):
                        deg = int(token[:-2])
                        break
                if deg is not None:
                    kinship_map[(p1, p2)] = deg
                    kinship_map[(p2, p1)] = deg
    print(f" -> Loaded {len(kinship_map)//2} kinship pairs.")
else:
    print(f" -> Warning: '{kinship_file}' not found. Degree fields will be left empty.")

# ---------------------------------------------------------
# STEP 2: Load Election Winners Data
# ---------------------------------------------------------
print("[2/5] Loading NLE Winners Dataset (NLE_Winners_2004-2025.csv)...")
t0 = time.time()
nle_file = 'data/NLE_Winners_2004-2025.csv'

if not os.path.exists(nle_file):
    # Fallback to parent directory if running from src/ folder
    nle_file = os.path.join('..', 'NLE_Winners_2004-2025.csv')

df_nle = pd.read_csv(nle_file, low_memory=False)
print(f" -> Loaded {len(df_nle):,} records in {time.time()-t0:.2f} seconds.")

# ---------------------------------------------------------
# STEP 3: Vectorized ID Standardization
# ---------------------------------------------------------
print("[3/5] Standardizing Person and Seat IDs...")
t0 = time.time()

# Fast vectorized string concatenation
last_name = df_nle['Last Name'].fillna('').astype(str).str.strip().str.upper().str.replace(' ', '_')
first_name = df_nle['First Name'].fillna('').astype(str).str.strip().str.upper().str.replace(' ', '_')
df_nle['person_id'] = 'PER-' + last_name + '-' + first_name

prov_col = df_nle['Province'].fillna('NAT').astype(str).str.strip().str.upper().str.replace(' ', '_')
city_col = df_nle['City'].fillna('NONE').astype(str).str.strip().str.upper().str.replace(' ', '_')
pos_col = df_nle['Position'].astype(str).str.strip().str.upper().str.replace(' ', '_').str.replace(',', '')

df_nle['seat_id'] = 'PH-' + pos_col + '-' + prov_col + '-' + city_col
df_nle['is_winner'] = True
print(f" -> IDs vectorized in {time.time()-t0:.2f} seconds.")

# ---------------------------------------------------------
# STEP 4: O(1) Pre-indexing for Position Swaps
# ---------------------------------------------------------
print("[4/5] Pre-building O(1) Index Maps for Position Swaps and Terms...")
t0 = time.time()

# (Year, person_id) -> set of seat_ids held in that year
person_seats_by_year = df_nle.groupby(['Year', 'person_id'])['seat_id'].apply(set).to_dict()

# Sort chronologically by seat and election year
df_nle = df_nle.sort_values(by=['seat_id', 'Year', 'Full Name']).reset_index(drop=True)
print(f" -> Index maps created in {time.time()-t0:.2f} seconds.")

# ---------------------------------------------------------
# STEP 5: Process Electoral History & Succession
# ---------------------------------------------------------
print("[5/5] Processing Predecessors, Succession, and Position Swaps...")
t0 = time.time()

records = []
seat_term_tracker = {}

grouped = df_nle.groupby('seat_id')
total_seats = len(grouped)
processed_seats = 0

for seat_id, group in grouped:
    processed_seats += 1
    
    # Debug Progress Log every 1,000 seats
    if processed_seats % 1000 == 0 or processed_seats == total_seats:
        pct = (processed_seats / total_seats) * 100
        print(f"   [LOG] Progress: {processed_seats}/{total_seats} seats processed ({pct:.1f}%)...")
        
    years = sorted(group['Year'].unique())
    year_to_winners = {y: group[group['Year'] == y]['person_id'].tolist() for y in years}
    year_to_names = {y: group[group['Year'] == y]['Full Name'].tolist() for y in years}
    
    for _, row in group.iterrows():
        yr = int(row['Year'])
        pid = row['person_id']
        fname = str(row['Full Name']).upper()
        
        prev_yr = yr - 3
        pred_id = ""
        pred_name = ""
        
        if prev_yr in year_to_winners and len(year_to_winners[prev_yr]) > 0:
            pred_id = year_to_winners[prev_yr][0]
            pred_name = year_to_names[prev_yr][0].upper()
            
        # Consecutive terms tracker
        if pred_id == pid:
            term_num = seat_term_tracker.get((seat_id, pid), 1) + 1
            if term_num > 3:
                term_num = 1
        else:
            term_num = 1
        seat_term_tracker[(seat_id, pid)] = term_num
        
        # Kinship relationship degree lookup
        deg = kinship_map.get((fname, pred_name), None) if (pred_name and pred_name != "") else None
        
        # Immediate family succession (degree <= 4)
        is_imm_succ = bool(deg is not None and deg <= 4 and pred_id != pid and pred_id != "")
        
        # Position Swap detection - O(1) set intersection
        is_swap = False
        if pred_id != "" and pred_id != pid:
            pred_seats_in_t = person_seats_by_year.get((yr, pred_id), set())
            cand_seats_in_t_minus_1 = person_seats_by_year.get((prev_yr, pid), set())
            
            # True if candidate's t-1 seat was taken by predecessor in t
            if pred_seats_in_t.intersection(cand_seats_in_t_minus_1):
                is_swap = True

        records.append({
            'history_id': f"EH-{yr}-{len(records)+1:06d}",
            'election_year': yr,
            'person_id': pid,
            'seat_id': seat_id,
            'is_winner': True,
            'consecutive_term_num': term_num,
            'predecessor_person_id': pred_id,
            'predecessor_relation_degree': int(deg) if deg is not None else '',
            'is_immediate_succession': is_imm_succ,
            'is_position_swap': is_swap
        })

df_history = pd.DataFrame(records)
print(f" -> Processed {len(df_history):,} records in {time.time()-t0:.2f} seconds.")

# ---------------------------------------------------------
# Export Final Output
# ---------------------------------------------------------
output_file = 'electoral_history.csv'
df_history.to_csv(output_file, index=False)
print(f"\n[SUCCESS] Saved '{output_file}' with {len(df_history):,} rows.")
print(f"Total execution time: {time.time()-start_total:.2f} seconds.")