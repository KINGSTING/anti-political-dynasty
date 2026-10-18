import os
import pandas as pd

# ==================== PATHS ====================
NODES_CSV        = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN3_inter-intra_local_level\data\inter-intra_local_nodes.csv"
PSGC_EXCEL       = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PSGC-3Q-2026-Publication-Datafile.xlsx"
OUTPUT_SEATS_CSV = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN3_inter-intra_local_level\data\inter-intra_local_seats.csv"
MASTER_SEATS_CSV = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN2_national-subnational_level\data\national+subnational_seats.csv"

SEAT_COLUMNS = [
    "seat_id", "jurisdiction_code", "position_type",
    "jurisdiction_level", "max_consecutive_terms", "parent_jurisdiction_code",
]

# Position configuration per LGU level
LEVEL_CONFIG = {
    "Province": {
        "id_prefix": "PH-PROV",
        "top":    {"type": "Governor",          "suffix": "GOVERNOR"},
        "vice":   {"type": "Vice_Governor",     "suffix": "VICEGOVERNOR"},
        "member": {"type": "Board_Member",      "suffix": "BOARDMEMBER"},
    },
    "City": {
        "id_prefix": "PH-CITY",
        "top":    {"type": "City_Mayor",        "suffix": "MAYOR"},
        "vice":   {"type": "City_Vice_Mayor",   "suffix": "VICEMAYOR"},
        "member": {"type": "City_Councilor",    "suffix": "COUNCILOR"},
    },
    "Municipality": {
        "id_prefix": "PH-MUNI",
        "top":    {"type": "Municipal_Mayor",      "suffix": "MAYOR"},
        "vice":   {"type": "Municipal_Vice_Mayor", "suffix": "VICEMAYOR"},
        "member": {"type": "Municipal_Councilor",  "suffix": "COUNCILOR"},
    },
    "SubMunicipality": {
        "id_prefix": "PH-SUBMUN",
        "top":    {"type": "SubMunicipal_Mayor",      "suffix": "MAYOR"},
        "vice":   {"type": "SubMunicipal_Vice_Mayor", "suffix": "VICEMAYOR"},
        "member": {"type": "SubMunicipal_Councilor",  "suffix": "COUNCILOR"},
    },
}


# ==================== PSGC LEVEL MAP ====================
def load_psgc_level_map(excel_path):
    """Build {psgc_code: (level_name, parent_code)} from PSGC Excel."""
    if not os.path.exists(excel_path):
        print(f"CRITICAL: {excel_path} not found.")
        return {}

    xls = pd.ExcelFile(excel_path)
    target = next((s for s in xls.sheet_names if s.strip().upper() == "PSGC"), None)
    if not target:
        target = xls.sheet_names[2] if len(xls.sheet_names) >= 3 else xls.sheet_names[0]

    df = pd.read_excel(xls, sheet_name=target)
    df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]
    col_dict = {c.upper(): c for c in df.columns
                if pd.notna(c) and not str(c).upper().startswith("UNNAMED")}

    psgc_col  = next((col_dict[c] for c in col_dict if "10-DIGIT" in c or "PSGC" in c), None)
    level_col = next((col_dict[c] for c in col_dict if "GEOGRAPH" in c or "LEVEL" in c), None)
    if not (psgc_col and level_col):
        print("CRITICAL: Could not identify PSGC/level columns.")
        return {}

    level_map = {}
    region_code, prov_code = "", ""

    for _, row in df.iterrows():
        lv  = str(row[level_col]).strip().upper() if pd.notna(row[level_col]) else ""
        raw = str(row[psgc_col]).strip() if pd.notna(row[psgc_col]) else ""
        if raw.endswith(".0"):
            raw = raw[:-2]
        code = raw.zfill(10)
        if not code or code == "0000000000":
            continue

        norm, parent = "", ""
        if lv in ("REG", "REGION"):
            region_code, prov_code = code, ""
            norm = "Region"
        elif lv in ("PROV", "PROVINCE"):
            prov_code = code
            parent = region_code
            norm = "Province"
        elif lv in ("DIST", "DISTRICT"):
            parent = region_code
            norm = "District"
        elif lv == "CITY":
            parent = prov_code if prov_code else region_code
            norm = "City"
        elif lv == "MUN":
            parent = prov_code if prov_code else region_code
            norm = "Municipality"
        elif lv == "SUBMUN":
            parent = prov_code if prov_code else region_code
            norm = "SubMunicipality"

        if norm:
            level_map[code] = (norm, parent)

    return level_map


# ==================== HELPERS ====================
def get_parent_psgc(code):
    """Fallback: derive parent from PSGC string pattern."""
    s = str(code).strip()
    if s.endswith(".0"):
        s = s[:-2]
    s = s.zfill(10)
    if s.startswith("13"):
        return "1300000000"
    return s[:5] + "00000"


def make_seat(seat_id, psgc, position_type, level, parent):
    return {
        "seat_id": seat_id,
        "jurisdiction_code": psgc,
        "position_type": position_type,
        "jurisdiction_level": level,
        "max_consecutive_terms": 3,
        "parent_jurisdiction_code": parent,
    }


# ==================== MAIN ====================
def generate_inter_intra_local_seats():
    print(f"Loading nodes from: {NODES_CSV}")
    if not os.path.exists(NODES_CSV):
        print("CRITICAL: nodes file not found.")
        return

    # ✅ Hardened read: keep empty strings as "" instead of converting to NaN
    # Also force home_psgc to stay as string so leading zeros are preserved
    nodes = pd.read_csv(NODES_CSV, dtype={"home_psgc": str}, keep_default_na=False)
    print(f"  Loaded {len(nodes)} nodes")

    if "home_psgc" not in nodes.columns:
        print("CRITICAL: 'home_psgc' column missing.")
        return

    # Normalize home_psgc: strip ".0", whitespace, then zfill to 10 chars
    nodes["home_psgc"] = (
        nodes["home_psgc"].astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
    )

    # ✅ keep_default_na=False means empties stay "" — this filter now works as intended
    mask = (nodes["home_psgc"] != "") & (nodes["home_psgc"].str.lower() != "nan")
    valid = nodes[mask].copy()
    valid["home_psgc"] = valid["home_psgc"].str.zfill(10)

    print(f"  Valid nodes with PSGC: {len(valid)}")
    print(f"  Missing PSGC        : {len(nodes) - len(valid)}")

    # Load PSGC hierarchy
    print(f"\nLoading PSGC level map from: {PSGC_EXCEL}")
    level_map = load_psgc_level_map(PSGC_EXCEL)
    print(f"  Indexed {len(level_map)} PSGC codes")

    # Group by PSGC
    grouped = valid.groupby("home_psgc", sort=True)
    print(f"\nUnique LGUs in nodes: {len(grouped)}")

    seats = []
    stats = {}
    missing_psgc_codes = []
    fallback_used = []

    for psgc, group in grouped:
        count = len(group)
        info = level_map.get(psgc)

        if info:
            level_name, parent = info
        else:
            # Fallback heuristics — infer level from PSGC pattern
            if psgc.endswith("00000"):
                if psgc == "1300000000":
                    # NCR region itself — skip, not an LGU with seats
                    continue
                level_name = "Province"
            else:
                level_name = "City" if psgc.startswith("13") else "Municipality"
            parent = get_parent_psgc(psgc)
            missing_psgc_codes.append(psgc)

        # ✅ Fallback for non-LGU levels (District, Region, etc.) — do NOT drop
        if level_name not in LEVEL_CONFIG:
            if psgc.startswith("13") and not psgc.endswith("00000"):
                level_name = "City"
            elif psgc.endswith("00000") and psgc != "1300000000":
                level_name = "Province"
            else:
                level_name = "Municipality"
            parent = get_parent_psgc(psgc)
            if psgc not in missing_psgc_codes:
                missing_psgc_codes.append(psgc)
            fallback_used.append((psgc, count))

        cfg = LEVEL_CONFIG[level_name]
        stats[level_name] = stats.get(level_name, 0) + 1

        # 1) Top seat — Governor or Mayor
        if count >= 1:
            seats.append(make_seat(
                f"{cfg['id_prefix']}-{psgc}-{cfg['top']['suffix']}",
                psgc, cfg["top"]["type"], level_name, parent,
            ))

        # 2) Vice seat — Vice Governor or Vice Mayor
        if count >= 2:
            seats.append(make_seat(
                f"{cfg['id_prefix']}-{psgc}-{cfg['vice']['suffix']}",
                psgc, cfg["vice"]["type"], level_name, parent,
            ))

        # 3) Member seats — Board Members or Councilors (remainder)
        n_members = count - 2
        for i in range(1, n_members + 1):
            seats.append(make_seat(
                f"{cfg['id_prefix']}-{psgc}-{cfg['member']['suffix']}-{i:02d}",
                psgc, cfg["member"]["type"], level_name, parent,
            ))

    df_seats = pd.DataFrame(seats, columns=SEAT_COLUMNS)
    df_seats = df_seats.drop_duplicates(subset=["seat_id"], keep="first").reset_index(drop=True)

    # Save standalone output
    os.makedirs(os.path.dirname(OUTPUT_SEATS_CSV), exist_ok=True)
    df_seats.to_csv(OUTPUT_SEATS_CSV, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 60)
    print(f"SUCCESS: Generated {len(df_seats)} seat records")
    print(f"Saved standalone file to: {OUTPUT_SEATS_CSV}")

    print("\nBreakdown by jurisdiction level:")
    for lv, c in sorted(stats.items()):
        print(f"  {lv:20s}: {c} LGUs")

    print("\nBreakdown by position_type:")
    print(df_seats["position_type"].value_counts().to_string())

    # -------- Coverage sanity check --------
    print("\n--- Coverage Check ---")
    print(f"  Nodes (valid)         : {len(valid)}")
    print(f"  Seats generated       : {len(df_seats)}")
    print(f"  Gap                   : {len(valid) - len(df_seats)}")
    if len(valid) - len(df_seats) != 0:
        print("  ⚠ Gap non-zero — investigate LGUs with <2 nodes")

    # -------- Diagnostics for fallback usage --------
    if missing_psgc_codes:
        print(f"\nWARNING: {len(missing_psgc_codes)} PSGC codes not in PSGC Excel (fallback applied):")
        preview = missing_psgc_codes[:10]
        print(f"  {preview}{'...' if len(missing_psgc_codes) > 10 else ''}")

    if fallback_used:
        print(f"\nFallback level inferred for {len(fallback_used)} PSGC groups:")
        for psgc, cnt in fallback_used[:20]:
            print(f"  {psgc} ({cnt} nodes)")

    # -------- Update master seats file (idempotent) --------
    if os.path.exists(MASTER_SEATS_CSV):
        print(f"\nUpdating master file: {MASTER_SEATS_CSV}")
        try:
            master = pd.read_csv(MASTER_SEATS_CSV, dtype=str, keep_default_na=False)
        except Exception as e:
            print(f"  WARNING: Could not read master ({e}). Skipping update.")
            return

        existing = set(master["seat_id"].astype(str))
        new_seats = df_seats[~df_seats["seat_id"].isin(existing)]
        print(f"  Existing seat records : {len(master)}")
        print(f"  New seats to append   : {len(new_seats)}")

        if len(new_seats) > 0:
            combined = pd.concat([master, new_seats], ignore_index=True)
            combined.to_csv(MASTER_SEATS_CSV, index=False, encoding="utf-8-sig")
            print(f"  Updated master total  : {len(combined)} seat records")
        else:
            print("  Nothing new to add (master already up to date).")
    else:
        os.makedirs(os.path.dirname(MASTER_SEATS_CSV), exist_ok=True)
        df_seats.to_csv(MASTER_SEATS_CSV, index=False, encoding="utf-8-sig")
        print(f"\nCreated master seats file: {MASTER_SEATS_CSV}")

    print("\nSample output (first 10 rows):")
    print(df_seats.head(10).to_string())


if __name__ == "__main__":
    generate_inter_intra_local_seats()