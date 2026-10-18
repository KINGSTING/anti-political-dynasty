import os
import csv
import re
import pandas as pd

def normalize_name(name):
    """Strips quotes, titles, suffixes, and punctuation for token comparison."""
    name = str(name).lower()
    name = re.sub(r'["“\'].*?["”\']', '', name) 
    name = re.sub(r'\b(jr\.?|sr\.?|iii|ii|iv|atty\.?|dr\.?|ma\.|maria|datu|bai|hadja)\b', '', name)
    name = re.sub(r'[^a-z\s]', ' ', name)
    return set(t for t in name.split() if len(t) > 1)

def format_nodes_pipeline():
    txt_path = "politician_nodes_list.txt"
    winners_csv = r"data/NLE_Winners_2004-2025.csv"
    output_csv = "politician_nodes.csv"

    if not os.path.exists(txt_path) or not os.path.exists(winners_csv):
        print("Error: Missing 'politician_nodes_list.txt' or OpenHalalan winners CSV file.")
        return

    print("1. Loading politician nodes and OpenHalalan 2025 election data...")
    with open(txt_path, "r", encoding="utf-8") as f:
        network_politicians = [line.strip() for line in f if line.strip()]

    df_winners = pd.read_csv(winners_csv, low_memory=False)
    df_winners.columns = [c.strip() for c in df_winners.columns]

    # Filter strictly for 2025 winners
    year_col = next((c for c in df_winners.columns if 'year' in c.lower()), 'Year')
    df_2025 = df_winners[df_winners[year_col] == 2025].copy()

    pos_col = next((c for c in df_2025.columns if 'position' in c.lower()), 'Position')
    prov_col = next((c for c in df_2025.columns if 'province' in c.lower()), 'Province')
    city_col = next((c for c in df_2025.columns if 'city' in c.lower() or 'municipality' in c.lower()), 'City')
    district_col = next((c for c in df_2025.columns if 'district' in c.lower()), None)

    # Build search identifier name for each winner row
    if 'Full Name' in df_2025.columns:
        df_2025['search_name'] = df_2025['Full Name'].astype(str)
    elif 'Last Name' in df_2025.columns and 'First Name' in df_2025.columns:
        df_2025['search_name'] = df_2025['Last Name'].astype(str) + " " + df_2025['First Name'].astype(str)
    else:
        cand_col = next((c for c in df_2025.columns if 'name' in c.lower()), df_2025.columns[0])
        df_2025['search_name'] = df_2025[cand_col].astype(str)

    # Index winners for fast matching
    winner_records = []
    for _, row in df_2025.iterrows():
        s_name = row['search_name']
        tokens = normalize_name(s_name)
        if not tokens:
            continue
        
        position = str(row[pos_col]).strip() if pos_col in row and pd.notna(row[pos_col]) else "Unspecified Position"
        prov = str(row[prov_col]).strip() if prov_col in row and pd.notna(row[prov_col]) else ""
        city = str(row[city_col]).strip() if city_col in row and pd.notna(row[city_col]) else ""
        district = str(row[district_col]).strip() if district_col and district_col in row and pd.notna(row[district_col]) else ""

        winner_records.append({
            'tokens': tokens,
            'position': position,
            'province': prov,
            'city': city,
            'district': district
        })

    print("2. Formatting positions and units based on office type...")
    csv_headers = ["name", "position", "unit"]
    matched_count = 0

    with open(output_csv, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=csv_headers)
        writer.writeheader()

        for net_name in network_politicians:
            net_tokens = normalize_name(net_name)
            if len(net_tokens) < 2:
                continue

            best_match = None
            for win in winner_records:
                if len(net_tokens.intersection(win['tokens'])) >= 2:
                    best_match = win
                    break

            if best_match is not None:
                pos_lower = best_match['position'].lower()

                # Rule 1: Senators
                if "senator" in pos_lower:
                    office = "Senator"
                    unit = "Senate"

                # Rule 2: Representatives / Congressmen
                elif any(w in pos_lower for w in ["representative", "congress", "member, house"]):
                    office = "Member of House of Representative"
                    unit = best_match['district'] if best_match['district'] else (best_match['province'] or "National/Partylist")

                # Rule 3: Executive & Local Officials (Governors, Mayors, etc.)
                else:
                    office = best_match['position'].title()
                    unit = f"{best_match['city']}, {best_match['province']}".strip(", ") or "Unspecified Unit"

                writer.writerow({
                    "name": net_name,
                    "position": office,
                    "unit": unit
                })
                matched_count += 1

    print(f"\n✅ Done! Generated {output_csv} with {matched_count} formatted 2025 incumbent nodes.")

if __name__ == "__main__":
    format_nodes_pipeline()