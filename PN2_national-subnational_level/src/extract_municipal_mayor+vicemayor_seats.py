import os
import pandas as pd

# File paths
municipal_nodes_csv = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\municipal_nodes.csv"
master_nodes_csv = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN2_national-subnational_level\data\national+subnational_nodes.csv"
output_seats_csv = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\municipal_seats.csv"
master_seats_csv = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN2_national-subnational_level\data\national+subnational_seats.csv"


def get_parent_psgc(psgc_code):
    """Calculates the parent province or NCR regional PSGC code."""
    psgc_str = str(psgc_code).strip()
    if psgc_str.endswith(".0"):
        psgc_str = psgc_str[:-2]

    length = len(psgc_str)

    # 10-digit PSGC handling
    if length == 10:
        psgc_str = psgc_str.zfill(10)
        if psgc_str.startswith("13"):
            return "1300000000"  # NCR parent code
        return psgc_str[:5] + "00000"  # Provincial parent code

    # 9-digit PSGC handling
    elif length == 9:
        psgc_str = psgc_str.zfill(9)
        if psgc_str.startswith("13"):
            return "130000000"  # NCR parent code
        return psgc_str[:4] + "00000"  # Provincial parent code

    return ""


def generate_municipal_seats():
    print("Loading municipal nodes dataset...")

    # Load home_psgc from municipal_nodes.csv or master_nodes.csv
    nodes_df = None
    if os.path.exists(municipal_nodes_csv):
        nodes_df = pd.read_csv(municipal_nodes_csv)
    elif os.path.exists(master_nodes_csv):
        nodes_df = pd.read_csv(master_nodes_csv)

    if nodes_df is None or "home_psgc" not in nodes_df.columns:
        print("CRITICAL ERROR: Could not locate municipal node file with 'home_psgc' column.")
        return

    # Filter out missing/empty home_psgc codes
    valid_nodes = nodes_df[nodes_df["home_psgc"].notna() & (nodes_df["home_psgc"] != "")].copy()
    unique_psgcs = valid_nodes["home_psgc"].unique()

    print(f"-> Extracted {len(unique_psgcs)} unique municipal jurisdiction PSGC codes.")

    seats = []

    for psgc in unique_psgcs:
        psgc_str = str(psgc).strip()
        if psgc_str.endswith(".0"):
            psgc_str = psgc_str[:-2]

        # Standardize padding
        if len(psgc_str) in [9, 10]:
            psgc_str = psgc_str.zfill(len(psgc_str))
        else:
            continue

        parent_psgc = get_parent_psgc(psgc_str)

        # 1. Municipal Mayor seat
        seats.append({
            "seat_id": f"PH-MUNI-{psgc_str}-MAYOR",
            "jurisdiction_code": psgc_str,
            "position_type": "Municipal_Mayor",
            "jurisdiction_level": "Municipality",
            "max_consecutive_terms": 3,
            "parent_jurisdiction_code": parent_psgc,
        })

        # 2. Municipal Vice Mayor seat
        seats.append({
            "seat_id": f"PH-MUNI-{psgc_str}-VICEMAYOR",
            "jurisdiction_code": psgc_str,
            "position_type": "Municipal_Vice_Mayor",
            "jurisdiction_level": "Municipality",
            "max_consecutive_terms": 3,
            "parent_jurisdiction_code": parent_psgc,
        })

    df_seats = pd.DataFrame(seats)

    # Save standalone municipal_seats.csv
    df_seats.to_csv(output_seats_csv, index=False, encoding="utf-8-sig")
    print(f"\nSUCCESS: Generated {len(df_seats)} municipal seat records!")
    print(f"Saved standalone file to: {output_seats_csv}")

    # Append / Update master national+subnational_seats.csv
    if os.path.exists(master_seats_csv):
        df_master = pd.read_csv(master_seats_csv)

        # Drop duplicate seat_ids if re-running
        df_master_clean = df_master[~df_master["seat_id"].isin(df_seats["seat_id"])].copy()
        df_combined = pd.concat([df_master_clean, df_seats], ignore_index=True)

        df_combined.to_csv(master_seats_csv, index=False, encoding="utf-8-sig")
        print(f"Updated master seats file at: {master_seats_csv} (Total seat records: {len(df_combined)})")
    else:
        # Create directory if missing
        os.makedirs(os.path.dirname(master_seats_csv), exist_ok=True)
        df_seats.to_csv(master_seats_csv, index=False, encoding="utf-8-sig")
        print(f"Created master seats file at: {master_seats_csv}")

    print("\nSample Output Preview:")
    print(df_seats.head(10).to_string())


if __name__ == "__main__":
    generate_municipal_seats()