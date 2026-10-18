import os
import re
import pandas as pd

# ============================================================
# CONFIGURATION
# ============================================================
PROVINCIAL_XLSX = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\data\Provincial_incumbents.xlsx"
MUNICIPAL_XLSX  = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\data\Municipal_incumbents.xlsx"
CITY_XLSX       = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\data\city_incumbents.xlsx"

OUTPUT_DIR = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN3_inter-intra_local_level\data"
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "inter-intra_local_nodes.csv")
DIAG_CSV   = os.path.join(OUTPUT_DIR, "unmatched_psgc_diagnostic.csv")

NATIONAL_NODES_CSV = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PN2_national-subnational_level\data\national+subnational_nodes.csv"
PSGC_EXCEL = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\PSGC-3Q-2026-Publication-Datafile.xlsx"

OUTPUT_COLUMNS = [
    "person_id", "full_name_clean", "first_name", "middle_name",
    "last_name", "maternal_maiden_name", "gender", "home_psgc", "aliases"
]

POSITION_KEYWORDS = {
    "provincial": [
        "VICE GOVERNOR", "VICE-GOVERNOR", "VICEGOVERNOR", "GOVERNOR",
        "BOARD MEMBER", "BOARD MEMBERS", "SANGGUNIANG PANLALAWIGAN", "SP MEMBER",
    ],
    "city": [
        "VICE MAYOR", "VICE-MAYOR", "VICEMAYOR", "MAYOR",
        "COUNCILOR", "COUNCILORS", "SANGGUNIANG PANLUNGSOD", "SP MEMBER",
    ],
    "municipal": [
        "VICE MAYOR", "VICE-MAYOR", "VICEMAYOR", "MAYOR",
        "COUNCILOR", "COUNCILORS", "SANGGUNIANG BAYAN", "SB MEMBER",
    ],
}

# ============================================================
# ALIAS MAPS — fix the 36 (and similar) via canonical renaming
# Keys use the output of clean_location_name (upper, no punctuation)
# ============================================================
PROVINCE_ALIASES = {
    # Historical / alternate names → PSGC canonical
    "NORTH COTABATO":          "COTABATO",
    "COTABATO NORTH COTABATO": "COTABATO",
    "WESTERN SAMAR":           "SAMAR",
    "SAMAR WESTERN SAMAR":     "SAMAR",
    "MT PROVINCE":             "MOUNTAIN PROVINCE",
    "MTN PROVINCE":            "MOUNTAIN PROVINCE",
    "COMPOSTELA VALLEY":       "DAVAO DE ORO",
    "DAVAO DE ORO COMPOSTELA VALLEY": "DAVAO DE ORO",
    "SHARIFF KABUNSUAN":       "MAGUINDANAO DEL NORTE",
    "JOLO":                    "SULU",
    "SULU JOLO":               "SULU",
}

REGION_ALIASES = {
    # BARMM history
    "ARMM":                                        "BARMM",
    "AUTONOMOUS REGION IN MUSLIM MINDANAO":        "BARMM",
    "AUTONOMOUS REGION FOR MUSLIM MINDANAO":       "BARMM",
    "MUSLIM MINDANAO AUTONOMOUS REGION":           "BARMM",

    # Short → canonical region names
    "REGION I":               "ILOCOS REGION",
    "REGION II":              "CAGAYAN VALLEY",
    "REGION III":             "CENTRAL LUZON",
    "REGION IV A":            "CALABARZON",
    "REGION IVA":             "CALABARZON",
    "REGION 4A":              "CALABARZON",
    "REGION IV B":            "MIMAROPA",
    "REGION IVB":             "MIMAROPA",
    "REGION 4B":              "MIMAROPA",
    "REGION V":               "BICOL REGION",
    "REGION VI":              "WESTERN VISAYAS",
    "REGION VII":             "CENTRAL VISAYAS",
    "REGION VIII":            "EASTERN VISAYAS",
    "REGION IX":              "ZAMBOANGA PENINSULA",
    "REGION X":               "NORTHERN MINDANAO",
    "REGION XI":              "DAVAO REGION",
    "REGION XII":             "SOCCSKSARGEN",
    "REGION XIII":            "CARAGA",

    # Alternate long names
    "ILOCOS":                 "ILOCOS REGION",
    "BICOL":                  "BICOL REGION",
    "CORDILLERA":             "CORDILLERA ADMINISTRATIVE REGION",
    "CAR":                    "CORDILLERA ADMINISTRATIVE REGION",
    "NCR":                    "NATIONAL CAPITAL REGION",
    "METRO MANILA":           "NATIONAL CAPITAL REGION",
}

# Explicit overrides for remaining stubborn cases.
# Populate after inspecting unmatched_psgc_diagnostic.csv.
# Key = (region_clean, province_clean, city_muni_clean); value = 10-digit PSGC
MANUAL_PSGC_OVERRIDES = {
    # Lucena City — HUC, source Excel places city name in both Province and City columns
    # Verify code from check_lucena.py output before relying on this
    ("CALABARZON", "LUCENA", "LUCENA"):  "0431200000",
    ("REGION IV A", "LUCENA", "LUCENA"): "0431200000",
}


# ============================================================
# TEXT CLEANING HELPERS
# ============================================================
def clean_location_name(name):
    """Standardizes province/municipality names for high-accuracy matching."""
    if pd.isna(name):
        return ""
    name = str(name).upper().strip()

    # ✅ NEW: strip parenthetical aliases BEFORE everything else.
    # "COTABATO (NORTH COTABATO)" → "COTABATO"
    # "SAMAR (WESTERN SAMAR)"     → "SAMAR"
    name = re.sub(r"\([^)]*\)", " ", name).strip()

    name = re.sub(r"^(CITY OF|MUNICIPALITY OF)\s+", "", name)
    name = re.sub(r"\s+(CITY|MUNICIPALITY)$", "", name)

    abbrev_map = {
        r"\bSTO\b": "SANTO", r"\bSTA\b": "SANTA", r"\bST\b": "SAINT",
        r"\bPRES\b": "PRESIDENT", r"\bGEN\b": "GENERAL", r"\bGOV\b": "GOVERNOR",
        r"\bMT\b": "MOUNTAIN",
    }
    name = re.sub(r"[^A-Z0-9\s]", " ", name)
    cleaned_words = []
    for w in name.split():
        w_sub = w
        for pattern, repl in abbrev_map.items():
            w_sub = re.sub(pattern, repl, w_sub)
        cleaned_words.append(w_sub)
    return " ".join(cleaned_words).strip()


def title_case(text):
    """Title-cases names with Philippine conventions; empties N/a placeholders."""
    if pd.isna(text) or not str(text).strip():
        return ""
    text = str(text).strip()
    # ✅ NEW: treat common placeholder strings as blank
    if text.lower() in ("n/a", "na", "n.a.", "-", "none", "null", "nan"):
        return ""

    formatted = []
    roman_and_suffixes = {"II", "III", "IV", "V", "VI", "JR.", "SR.", "JR", "SR"}
    particles = {"DELA", "DEL", "DE", "DOS", "SAN", "SANTA", "VAN"}
    for word in text.split():
        w_upper = word.upper()
        if w_upper in roman_and_suffixes:
            formatted.append(w_upper)
        elif w_upper in particles:
            formatted.append(word.capitalize())
        else:
            formatted.append(word.capitalize())
    return " ".join(formatted)


def infer_gender(first_name):
    """Predicts gender from common Philippine first names."""
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
        "flor", "light", "star", "chona", "donna", "elsa", "helen", "sittie",
        "shirlyn", "rochella", "emmylou", "rosalie", "ivy", "dawn",
    }
    for word in re.findall(r"\w+", fn_lower):
        if word in female_roots:
            return "F"
        if len(word) > 3 and word.endswith("a") and word not in {
            "joshua", "luca", "ezra", "siddhartha", "bonifacio"
        }:
            return "F"
    return "M"


def split_full_name(full_name):
    """Split combined name string into (first, middle, last, suffix)."""
    if not full_name or pd.isna(full_name):
        return "", "", "", ""
    name = str(full_name).strip()
    if not name:
        return "", "", "", ""
    suffix = ""
    for pattern, suff in [
        (r"[\s,]+(JR\.?)$", "JR."), (r"[\s,]+(SR\.?)$", "SR."),
        (r"[\s,]+(III)$", "III"),   (r"[\s,]+(IV)$", "IV"),
        (r"[\s,]+(II)$",  "II"),
    ]:
        m = re.search(pattern, name, re.IGNORECASE)
        if m:
            suffix = suff
            name = name[: m.start()].strip()
            break
    name = name.rstrip(",").strip()
    parts = name.split()
    if len(parts) >= 3:
        return parts[0], " ".join(parts[1:-1]), parts[-1], suffix
    if len(parts) == 2:
        return parts[0], "", parts[1], suffix
    if len(parts) == 1:
        return parts[0], "", "", suffix
    return "", "", "", ""


# ============================================================
# PSGC MAPPING
# ============================================================
def load_psgc_mapping(excel_path):
    """Returns (lgu_map, province_map, region_map, fallback_map)."""
    print(f"Loading PSGC Excel: {excel_path}...")
    lgu_map, province_map, region_map, fallback_map = {}, {}, {}, {}

    if not os.path.exists(excel_path):
        print(f"CRITICAL: file not found at '{excel_path}'")
        return lgu_map, province_map, region_map, fallback_map

    xls = pd.ExcelFile(excel_path)
    target_sheet = next((s for s in xls.sheet_names if s.strip().upper() == "PSGC"), None)
    if target_sheet is None:
        target_sheet = xls.sheet_names[2] if len(xls.sheet_names) >= 3 else xls.sheet_names[0]
    print(f"-> Reading worksheet: '{target_sheet}'")

    df_psgc = pd.read_excel(xls, sheet_name=target_sheet)
    df_psgc.columns = [str(c).replace("\n", " ").strip() for c in df_psgc.columns]
    col_dict = {c.upper(): c for c in df_psgc.columns
                if pd.notna(c) and not str(c).upper().startswith("UNNAMED")}

    psgc_col  = next((col_dict[c] for c in col_dict if "10-DIGIT" in c or "PSGC" in c), None)
    name_col  = next((col_dict[c] for c in col_dict if "NAME" in c), None)
    level_col = next((col_dict[c] for c in col_dict if "GEOGRAPH" in c or "LEVEL" in c), None)

    if not (psgc_col and name_col and level_col):
        print(f"CRITICAL: could not map columns. Available: {list(col_dict.values())}")
        return lgu_map, province_map, region_map, fallback_map

    print(f"-> Columns: Code='{psgc_col}', Name='{name_col}', Level='{level_col}'")

    current_province, current_region = "", ""

    for _, row in df_psgc.iterrows():
        level_val = str(row[level_col]).strip().upper() if pd.notna(row[level_col]) else ""
        raw_name = str(row[name_col]).strip() if pd.notna(row[name_col]) else ""
        clean_name = clean_location_name(raw_name)

        psgc_raw = str(row[psgc_col]).strip() if pd.notna(row[psgc_col]) else ""
        if psgc_raw.endswith(".0"):
            psgc_raw = psgc_raw[:-2]
        psgc_code = psgc_raw.zfill(10)

        if level_val in ("REG", "REGION"):
            current_region, current_province = clean_name, ""
            region_map[clean_name] = psgc_code
        elif level_val in ("PROV", "PROVINCE"):
            current_province = clean_name
            province_map[clean_name] = psgc_code
        elif level_val in ("DIST", "DISTRICT"):
            current_province = clean_name
            province_map.setdefault(clean_name, psgc_code)
        elif level_val in ("CITY", "MUN", "SUBMUN", "HUC", "ICC", "CITY (HUC)", "CITY (ICC)"):
            # HUCs and ICCs are politically independent → parent is REGION, not province.
            is_huc = level_val in ("HUC", "ICC", "CITY (HUC)", "CITY (ICC)")
            if current_province and not is_huc:
                lgu_map[f"{current_province}_{clean_name}"] = psgc_code
            if current_region:
                lgu_map[f"{current_region}_{clean_name}"] = psgc_code
                # ✅ Also register the aliased form so "CALABARZON" and "REGION IV A"
                #    both resolve to the same entry
                aliased_region = REGION_ALIASES.get(current_region, current_region)
                if aliased_region != current_region:
                    lgu_map[f"{aliased_region}_{clean_name}"] = psgc_code
            if "NCR" in current_region or "NATIONAL CAPITAL REGION" in current_region:
                lgu_map[f"NCR_{clean_name}"] = psgc_code
                lgu_map[f"NATIONAL CAPITAL REGION_{clean_name}"] = psgc_code
            fallback_map.setdefault(clean_name, psgc_code)

    print(f"-> Indexed {len(lgu_map)} LGUs, {len(province_map)} provinces, {len(region_map)} regions")
    return lgu_map, province_map, region_map, fallback_map


def _apply_aliases(reg_clean, prov_clean):
    """Translate alternate names to PSGC canonical names."""
    # Iteratively resolve so chained aliases collapse correctly
    for _ in range(3):
        new_reg  = REGION_ALIASES.get(reg_clean, reg_clean)
        new_prov = PROVINCE_ALIASES.get(prov_clean, prov_clean)
        if new_reg == reg_clean and new_prov == prov_clean:
            break
        reg_clean, prov_clean = new_reg, new_prov
    return reg_clean, prov_clean


def lookup_psgc(region, province, city_muni, level, psgc_lookups):
    """Resolve PSGC for a given level, using aliases + manual overrides."""
    lgu_map, province_map, region_map, fallback_map = psgc_lookups

    prov_clean = clean_location_name(province)
    reg_clean  = clean_location_name(region)
    muni_clean = clean_location_name(city_muni)

    # ✅ Apply aliases to both source names
    reg_clean, prov_clean = _apply_aliases(reg_clean, prov_clean)

    # ✅ Manual override check first
    override_key = (reg_clean, prov_clean, muni_clean)
    if override_key in MANUAL_PSGC_OVERRIDES:
        return MANUAL_PSGC_OVERRIDES[override_key]

    if level == "provincial":
        if prov_clean and prov_clean in province_map:
            return province_map[prov_clean]
        return ""

    # City / Municipal
    if prov_clean and muni_clean:
        key = f"{prov_clean}_{muni_clean}"
        if key in lgu_map:
            return lgu_map[key]
    if reg_clean and muni_clean:
        key = f"{reg_clean}_{muni_clean}"
        if key in lgu_map:
            return lgu_map[key]
    if muni_clean and f"NCR_{muni_clean}" in lgu_map:
        return lgu_map[f"NCR_{muni_clean}"]
    if muni_clean and muni_clean in fallback_map:
        return fallback_map[muni_clean]
    return ""


# ============================================================
# COLUMN DETECTION
# ============================================================
def detect_columns(df):
    info = {}
    for c in df.columns:
        cu = re.sub(r"\s+", " ", str(c).upper().strip().replace("_", " ").replace("-", " "))
        if "first" not in info and ("FIRST NAME" in cu or cu == "GIVEN NAME" or cu == "FIRST"):
            info["first"] = c
        elif "middle" not in info and ("MIDDLE NAME" in cu or cu in ("MIDDLE", "MID NAME")):
            info["middle"] = c
        elif "last" not in info and ("LAST NAME" in cu or "SURNAME" in cu or "FAMILY NAME" in cu or cu == "LAST"):
            info["last"] = c
        elif "suffix" not in info and ("SUFFIX" in cu or "EXTENSION" in cu):
            info["suffix"] = c
        elif "position" not in info and ("POSITION" in cu or cu in ("TITLE", "OFFICE", "ROLE", "DESIGNATION")):
            info["position"] = c
        elif "region" not in info and cu in ("REGION", "REGION NAME"):
            info["region"] = c
        elif "province" not in info and cu in ("PROVINCE", "PROVINCE NAME", "PROV"):
            info["province"] = c
        elif "city_muni" not in info and "CITY" in cu and "MUNICIPALITY" in cu:
            info["city_muni"] = c
        elif "city_muni" not in info and cu in ("CITY", "CITY NAME"):
            info["city_muni"] = c
        elif "city_muni" not in info and cu in ("MUNICIPALITY", "MUNICIPALITY NAME", "MUNI", "MUNI NAME"):
            info["city_muni"] = c
    if "first" not in info and "last" not in info:
        for c in df.columns:
            if str(c).upper().strip() in ("NAME", "FULL NAME", "FULLNAME", "PERSON NAME", "OFFICIAL NAME"):
                info["full_name"] = c
                break
    return info


def extract_name_from_row(row, col_info):
    if "full_name" in col_info and not ("first" in col_info or "last" in col_info):
        val = row[col_info["full_name"]]
        return split_full_name(val if pd.notna(val) else "")
    return (
        str(row[col_info["first"]]).strip() if col_info.get("first") and pd.notna(row[col_info["first"]]) else "",
        str(row[col_info["middle"]]).strip() if col_info.get("middle") and pd.notna(row[col_info["middle"]]) else "",
        str(row[col_info["last"]]).strip() if col_info.get("last") and pd.notna(row[col_info["last"]]) else "",
        str(row[col_info["suffix"]]).strip() if col_info.get("suffix") and pd.notna(row[col_info["suffix"]]) else "",
    )


# ============================================================
# NODE BUILDER
# ============================================================
def build_node(id_num, first, middle, last, suffix,
               region, province, city_muni, level, psgc_lookups,
               unmatched_diag):
    fn  = title_case(first)
    mn  = title_case(middle)
    ln  = title_case(last)
    sfx = title_case(suffix)
    if not (fn or ln):
        return None

    full_name_clean = " ".join([p for p in [fn, mn, ln, sfx] if p])
    maternal_maiden_name = mn if mn else ""
    gender = infer_gender(fn)
    home_psgc = lookup_psgc(region, province, city_muni, level, psgc_lookups)
    aliases = " ".join([p for p in [fn, ln, sfx] if p])

    if not home_psgc:
        reg_c  = clean_location_name(region)
        prov_c = clean_location_name(province)
        muni_c = clean_location_name(city_muni)
        reg_c2, prov_c2 = _apply_aliases(reg_c, prov_c)
        unmatched_diag.append({
            "person_id": f"POL-PH-{id_num:06d}",
            "full_name_clean": full_name_clean,
            "level": level,
            "region_raw": region,
            "province_raw": province,
            "city_muni_raw": city_muni,
            "region_clean": reg_c2,
            "province_clean": prov_c2,
            "city_muni_clean": muni_c,
        })

    return {
        "person_id": f"POL-PH-{id_num:06d}",
        "full_name_clean": full_name_clean,
        "first_name": fn,
        "middle_name": mn,
        "last_name": ln,
        "maternal_maiden_name": maternal_maiden_name,
        "gender": gender,
        "home_psgc": home_psgc,
        "aliases": aliases,
    }


# ============================================================
# PROCESSING
# ============================================================
def process_dataframe(df, col_info, level, psgc_lookups, start_id, unmatched_diag):
    nodes, current_id = [], start_id

    if "position" not in col_info:
        print(f"  -> WARNING: no position column detected. Columns: {list(df.columns)}")
        return nodes, current_id

    print(f"  -> Long format (position column: '{col_info['position']}')")
    for _, row in df.iterrows():
        pos_str = str(row[col_info["position"]]).strip() if pd.notna(row[col_info["position"]]) else ""
        if not pos_str:
            continue
        if not any(kw.upper() in pos_str.upper() for kw in POSITION_KEYWORDS[level]):
            continue

        region    = str(row[col_info["region"]]).strip() if col_info.get("region") and pd.notna(row[col_info["region"]]) else ""
        province  = str(row[col_info["province"]]).strip() if col_info.get("province") and pd.notna(row[col_info["province"]]) else ""
        city_muni = str(row[col_info["city_muni"]]).strip() if col_info.get("city_muni") and pd.notna(row[col_info["city_muni"]]) else ""

        first, middle, last, suffix = extract_name_from_row(row, col_info)
        if not (first or last):
            continue

        node = build_node(current_id, first, middle, last, suffix,
                          region, province, city_muni, level, psgc_lookups, unmatched_diag)
        if node:
            nodes.append(node)
            current_id += 1
    return nodes, current_id


def process_excel_file(file_path, level, psgc_lookups, start_id, unmatched_diag):
    print(f"\n{'=' * 60}\nProcessing: {file_path}\nLevel: {level}")
    if not os.path.exists(file_path):
        print("ERROR: file not found")
        return [], start_id
    xls = pd.ExcelFile(file_path)
    print(f"Sheets: {xls.sheet_names}")

    all_nodes, current_id = [], start_id
    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet_name)
        if df.empty:
            continue
        df.columns = [str(c).strip() for c in df.columns]
        print(f"\nSheet '{sheet_name}': {df.shape}, cols={list(df.columns)}")
        col_info = detect_columns(df)
        print(f"  Detected: {col_info}")
        nodes, current_id = process_dataframe(
            df, col_info, level, psgc_lookups, current_id, unmatched_diag
        )
        all_nodes.extend(nodes)
        print(f"  -> {len(nodes)} nodes")
    return all_nodes, current_id


# ============================================================
# ID SEQUENCE
# ============================================================
def get_start_person_id(national_nodes_path, default_start=586):
    if os.path.exists(national_nodes_path):
        try:
            df = pd.read_csv(national_nodes_path)
            if "person_id" in df.columns and not df.empty:
                ids = (df["person_id"].astype(str)
                       .str.extract(r"POL-PH-(\d+)")[0].dropna().astype(int))
                if not ids.empty:
                    max_id = int(ids.max())
                    print(f"-> Highest existing ID: POL-PH-{max_id:06d}")
                    return max_id + 1
        except Exception as e:
            print(f"Warning: could not parse existing DB ({e}).")
    return default_start


# ============================================================
# MAIN
# ============================================================
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    psgc_lookups = load_psgc_mapping(PSGC_EXCEL)
    start_id = get_start_person_id(NATIONAL_NODES_CSV, default_start=586)
    print(f"\nStarting ID at POL-PH-{start_id:06d}")

    all_nodes, unmatched_diag = [], []
    current_id = start_id
    for file_path, level in [
        (PROVINCIAL_XLSX, "provincial"),
        (CITY_XLSX,       "city"),
        (MUNICIPAL_XLSX,  "municipal"),
    ]:
        nodes, current_id = process_excel_file(
            file_path, level, psgc_lookups, current_id, unmatched_diag
        )
        all_nodes.extend(nodes)
        print(f"  --> Total from {os.path.basename(file_path)}: {len(nodes)}")

    if all_nodes:
        df_out = pd.DataFrame(all_nodes, columns=OUTPUT_COLUMNS)
        df_out.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        match_count = (df_out["home_psgc"].astype(str).str.strip() != "").sum()
        print(f"\n{'=' * 60}")
        print(f"SUCCESS: {len(df_out)} nodes → {OUTPUT_CSV}")
        print(f"PSGC match: {match_count}/{len(df_out)} ({match_count/len(df_out)*100:.2f}%)")

    if unmatched_diag:
        diag_df = pd.DataFrame(unmatched_diag)
        diag_df.to_csv(DIAG_CSV, index=False, encoding="utf-8-sig")
        print(f"\n⚠ {len(diag_df)} nodes still unmatched. Diagnostic saved to:")
        print(f"   {DIAG_CSV}")
        print("\nTop failing (region, province, city) triples:")
        summary = (diag_df.groupby(["level", "region_clean", "province_clean", "city_muni_clean"])
                   .size().sort_values(ascending=False).head(15))
        print(summary.to_string())
        print("\nAdd remaining cases to MANUAL_PSGC_OVERRIDES and re-run.")


if __name__ == "__main__":
    main()