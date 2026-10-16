import os
import re
import pandas as pd

# File paths
input_csv = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\municipal_mayors_and_vice_mayors.csv"
output_nodes_csv = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\municipal_nodes.csv"
national_nodes_csv = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN2_national-subnational_level\data\national+subnational_nodes.csv"
psgc_excel_path = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PSGC-3Q-2026-Publication-Datafile.xlsx"


def clean_location_name(name):
    """Standardizes province/municipality names for high-accuracy string matching."""
    if pd.isna(name):
        return ""

    name = str(name).upper().strip()

    # Strip common administrative prefixes and suffixes
    name = re.sub(r"^(CITY OF|MUNICIPALITY OF)\s+", "", name)
    name = re.sub(r"\s+(CITY|MUNICIPALITY)$", "", name)

    # Standardize common Philippine geographic abbreviations
    abbrev_map = {
        r"\bSTO\b": "SANTO",
        r"\bSTA\b": "SANTA",
        r"\bST\b": "SAINT",
        r"\bPRES\b": "PRESIDENT",
        r"\bGEN\b": "GENERAL",
        r"\bGOV\b": "GOVERNOR",
    }

    # Strip non-alphanumeric characters
    name = re.sub(r"[^A-Z0-9\s]", " ", name)
    words = name.split()

    cleaned_words = []
    for w in words:
        w_sub = w
        for pattern, repl in abbrev_map.items():
            w_sub = re.sub(pattern, repl, w_sub)
        cleaned_words.append(w_sub)

    return " ".join(cleaned_words)


def title_case(text):
    """Converts name strings to proper Title Case while handling Philippine honorifics, particles, and suffixes."""
    if pd.isna(text) or not str(text).strip():
        return ""

    text = str(text).strip()
    words = text.split()
    formatted_words = []

    roman_and_suffixes = {"II", "III", "IV", "V", "VI", "JR.", "SR.", "JR", "SR"}
    particles = {"DELA", "DEL", "DE", "DOS", "SAN", "SANTA", "VAN"}

    for word in words:
        w_upper = word.upper()
        if w_upper in roman_and_suffixes:
            formatted_words.append(w_upper)
        elif w_upper in particles:
            formatted_words.append(word.capitalize())
        else:
            formatted_words.append(word.capitalize())

    return " ".join(formatted_words)


def infer_gender(first_name):
    """Predicts gender ('M' or 'F') using common Philippine first name indicators."""
    if pd.isna(first_name) or not str(first_name).strip():
        return "M"

    fn_lower = str(first_name).strip().lower()

    female_roots = {
        "maria", "ma.", "ma", "mary", "ana", "ann", "anne", "marissa", "joy",
        "grace", "rose", "princess", "cristina", "lourdes", "catherine", "elizabeth",
        "cherry", "corazon", "gloria", "mercedes", "carmelita", "imelda", "lorna",
        "liezel", "divina", "shirley", "lea", "evelyn", "fe", "gina", "rowena",
        "ruby", "alma", "arlene", "cheryl", "daisy", "hazel", "ivy", "jessica",
        "karen", "linda", "mercy", "nida", "norma", "ophelia", "pearl", "remedios",
        "sandra", "tess", "vicky", "wilma", "yolanda", "yvette", "zenaida", "jean",
        "flor", "light", "star", "chona", "donna", "elsa", "helen"
    }

    words = re.findall(r"\w+", fn_lower)
    for word in words:
        if word in female_roots:
            return "F"
        if len(word) > 3 and word.endswith("a") and word not in {"joshua", "luca", "ezra", "siddhartha", "bonifacio"}:
            return "F"

    return "M"


def load_psgc_mapping(excel_path):
    """Directly loads the 'PSGC' worksheet and extracts 10-digit PSGC codes."""
    print(f"Loading PSGC Excel file: {excel_path}...")
    psgc_map = {}
    fallback_map = {}

    if not os.path.exists(excel_path):
        print(f"CRITICAL ERROR: File not found at '{excel_path}'!")
        return psgc_map, fallback_map

    xls = pd.ExcelFile(excel_path)

    # Target the 'PSGC' sheet directly as seen in the Excel workbook
    target_sheet = None
    for sheet in xls.sheet_names:
        if sheet.strip().upper() == "PSGC":
            target_sheet = sheet
            break

    if target_sheet is None:
        target_sheet = xls.sheet_names[2] if len(xls.sheet_names) >= 3 else xls.sheet_names[0]

    print(f"-> Reading target worksheet: '{target_sheet}'")
    df_psgc = pd.read_excel(xls, sheet_name=target_sheet)

    # Filter OUT 'Unnamed' columns so 'Unnamed: 0' never matches 'Name'
    df_psgc.columns = [str(c).replace("\n", " ").strip() for c in df_psgc.columns]
    col_dict = {
        c.upper(): c for c in df_psgc.columns
        if pd.notna(c) and str(c).strip() and not str(c).upper().startswith("UNNAMED")
    }

    psgc_col = next((col_dict[c] for c in col_dict if "10-DIGIT" in c or "PSGC" in c), None)
    name_col = next((col_dict[c] for c in col_dict if "NAME" in c), None)
    level_col = next((col_dict[c] for c in col_dict if "GEOGRAPH" in c or "LEVEL" in c), None)

    if not (psgc_col and name_col and level_col):
        print(f"CRITICAL ERROR: Failed to map columns. Valid columns found: {list(col_dict.values())}")
        return psgc_map, fallback_map

    print(f"-> Mapped columns: Code='{psgc_col}', Name='{name_col}', Level='{level_col}'")

    current_province = ""
    current_region = ""

    for _, row in df_psgc.iterrows():
        level_val = str(row[level_col]).strip().upper() if pd.notna(row[level_col]) else ""
        raw_name = str(row[name_col]).strip() if pd.notna(row[name_col]) else ""
        clean_name = clean_location_name(raw_name)

        # Standardize 10-digit zero-padded PSGC code
        psgc_raw = str(row[psgc_col]).strip() if pd.notna(row[psgc_col]) else ""
        if psgc_raw.endswith(".0"):
            psgc_raw = psgc_raw[:-2]
        psgc_code = psgc_raw.zfill(10)

        # Track active geographic hierarchy
        if level_val in ["REG", "REGION"]:
            current_region = clean_name
            current_province = ""
        elif level_val in ["PROV", "PROVINCE", "DIST", "DISTRICT"]:
            current_province = clean_name
        elif level_val in ["CITY", "MUN", "SUBMUN"]:
            if current_province:
                psgc_map[f"{current_province}_{clean_name}"] = psgc_code
            if current_region:
                psgc_map[f"{current_region}_{clean_name}"] = psgc_code

            # Handle NCR Cities
            if "NCR" in current_region or "NATIONAL CAPITAL REGION" in current_region:
                psgc_map[f"NCR_{clean_name}"] = psgc_code
                psgc_map[f"NATIONAL CAPITAL REGION_{clean_name}"] = psgc_code

            # Direct municipality name fallback
            if clean_name not in fallback_map:
                fallback_map[clean_name] = psgc_code

    print(f"-> Successfully indexed {len(psgc_map)} PSGC LGU entries from Excel!")
    return psgc_map, fallback_map


def get_start_person_id(national_nodes_path, default_start=586):
    """Auto-detects highest existing POL-PH ID to ensure continuous ID numbering."""
    if os.path.exists(national_nodes_path):
        try:
            df_existing = pd.read_csv(national_nodes_path)
            if "person_id" in df_existing.columns and not df_existing.empty:
                id_nums = df_existing["person_id"].astype(str).str.extract(r"POL-PH-(\d+)")[0].dropna().astype(int)
                if not id_nums.empty:
                    max_id = id_nums.max()
                    print(f"-> Detected existing database. Highest ID: POL-PH-{max_id:06d}")
                    return max_id + 1
        except Exception as e:
            print(f"Warning: Could not parse existing database ({e}). Starting at default ID.")
    return default_start


def generate_municipal_nodes():
    print(f"Loading input file: {input_csv}")
    df = pd.read_csv(input_csv)

    # Parse 10-digit PSGC codes from 'PSGC' worksheet
    psgc_map, fallback_map = load_psgc_mapping(psgc_excel_path)

    # Auto-detect starting POL-PH ID
    start_id = get_start_person_id(national_nodes_csv, default_start=586)
    print(f"Generating person_id sequence from POL-PH-{start_id:06d}...")

    nodes = []
    matched_count = 0

    for idx, row in df.iterrows():
        current_id_num = start_id + idx
        person_id = f"POL-PH-{current_id_num:06d}"

        # Clean and title-case name fields
        fn = title_case(row.get("First Name", ""))
        mn = title_case(row.get("Middle Name", ""))
        ln = title_case(row.get("Last Name", ""))
        sfx = title_case(row.get("Suffix", ""))

        # Assemble clean full name
        name_parts = [p for p in [fn, mn, ln, sfx] if p]
        full_name_clean = " ".join(name_parts)

        # Middle Name is maternal maiden surname
        maternal_maiden_name = mn if mn else ""

        # Infer gender
        gender = infer_gender(fn)

        # Lookup 10-digit PSGC code
        prov_clean = clean_location_name(row.get("Province", ""))
        reg_clean = clean_location_name(row.get("Region", ""))
        muni_clean = clean_location_name(row.get("City/Municipality", ""))

        primary_key = f"{prov_clean}_{muni_clean}"
        region_key = f"{reg_clean}_{muni_clean}"
        ncr_key = f"NCR_{muni_clean}"

        home_psgc = psgc_map.get(
            primary_key,
            psgc_map.get(
                region_key,
                psgc_map.get(ncr_key, fallback_map.get(muni_clean, ""))
            )
        )

        if home_psgc:
            matched_count += 1

        # Generate alias
        alias_parts = [p for p in [fn, ln, sfx] if p]
        aliases = " ".join(alias_parts)

        nodes.append({
            "person_id": person_id,
            "full_name_clean": full_name_clean,
            "first_name": fn,
            "middle_name": mn,
            "last_name": ln,
            "maternal_maiden_name": maternal_maiden_name,
            "gender": gender,
            "home_psgc": home_psgc,
            "aliases": aliases,
        })

    df_nodes = pd.DataFrame(nodes)

    # Save standalone municipal nodes CSV
    df_nodes.to_csv(output_nodes_csv, index=False, encoding="utf-8-sig")
    print(f"\n==========================================")
    print(f"SUCCESS: Generated {len(df_nodes)} municipal person nodes!")
    print(f"PSGC Match Rate: {matched_count}/{len(df_nodes)} ({matched_count/len(df_nodes)*100:.1f}%)")
    print(f"Saved standalone file to: {output_nodes_csv}")

    # Overwrite/Append to main national+subnational_nodes.csv
    if os.path.exists(national_nodes_csv):
        df_national = pd.read_csv(national_nodes_csv)
        # Drop previous municipal entries if re-running to avoid duplicate appending
        df_national_clean = df_national[~df_national["person_id"].isin(df_nodes["person_id"])].copy()
        df_combined = pd.concat([df_national_clean, df_nodes], ignore_index=True)
        df_combined.to_csv(national_nodes_csv, index=False, encoding="utf-8-sig")
        print(f"Updated master database at: {national_nodes_csv} (Total records: {len(df_combined)})")

    print("\nSample Output Preview:")
    print(df_nodes[["person_id", "full_name_clean", "gender", "home_psgc", "aliases"]].head(10).to_string())


if __name__ == "__main__":
    generate_municipal_nodes()