"""
Build position lookup for PN3 nodes.

Replays the exact extraction filter logic from extract_inter-intra_local.py
to map each existing person_id -> their position. Uses sequential order match
since the extraction is deterministic (same source files, same iteration order).

Output: web/data/PN3_positions.json
"""

import os
import re
import json
from collections import Counter

import pandas as pd

# ==================== PATHS ====================
BASE = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty"

PROVINCIAL_XLSX = os.path.join(BASE, "data", "Provincial_incumbents.xlsx")
CITY_XLSX       = os.path.join(BASE, "data", "city_incumbents.xlsx")
MUNICIPAL_XLSX  = os.path.join(BASE, "data", "Municipal_incumbents.xlsx")

PN3_NODES = os.path.join(BASE, "PN3_inter-intra_local_level", "data",
                         "inter-intra_local_nodes.csv")

OUT_PN3 = os.path.join(BASE, "web", "data", "PN3_positions.json")
os.makedirs(os.path.dirname(OUT_PN3), exist_ok=True)

# ==================== SAME KEYWORDS AS EXTRACTOR ====================
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


# ==================== SAME HELPERS AS EXTRACTOR ====================
def title_case(text):
    if pd.isna(text) or not str(text).strip():
        return ""
    text = str(text).strip()
    if text.lower() in ("n/a", "na", "n.a.", "-", "none", "null", "nan"):
        return ""
    suffixes = {"II", "III", "IV", "V", "VI", "JR.", "SR.", "JR", "SR"}
    particles = {"DELA", "DEL", "DE", "DOS", "SAN", "SANTA", "VAN"}
    formatted = []
    for word in text.split():
        w = word.upper()
        if w in suffixes:
            formatted.append(w)
        elif w in particles:
            formatted.append(word.capitalize())
        else:
            formatted.append(word.capitalize())
    return " ".join(formatted)


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
    return info


def extract_name_from_row(row, col_info):
    return (
        str(row[col_info["first"]]).strip() if col_info.get("first") and pd.notna(row[col_info["first"]]) else "",
        str(row[col_info["middle"]]).strip() if col_info.get("middle") and pd.notna(row[col_info["middle"]]) else "",
        str(row[col_info["last"]]).strip() if col_info.get("last") and pd.notna(row[col_info["last"]]) else "",
        str(row[col_info["suffix"]]).strip() if col_info.get("suffix") and pd.notna(row[col_info["suffix"]]) else "",
    )


# ==================== POSITION MAPPING ====================
def canonical_position(raw_pos, level):
    """Map raw position text to canonical position_type key."""
    p = raw_pos.upper().strip()

    if level == "provincial":
        if "VICE GOVERNOR" in p or "VICE-GOVERNOR" in p or "VICEGOVERNOR" in p:
            return "Vice_Governor"
        if "GOVERNOR" in p:
            return "Governor"
        if "BOARD MEMBER" in p or "SP MEMBER" in p or "SANGGUNIANG PANLALAWIGAN" in p:
            return "Board_Member"

    elif level == "city":
        if "VICE MAYOR" in p or "VICE-MAYOR" in p or "VICEMAYOR" in p:
            return "City_Vice_Mayor"
        if "MAYOR" in p:
            return "City_Mayor"
        if "COUNCILOR" in p or "SP MEMBER" in p or "SANGGUNIANG PANLUNGSOD" in p:
            return "City_Councilor"

    elif level == "municipal":
        if "VICE MAYOR" in p or "VICE-MAYOR" in p or "VICEMAYOR" in p:
            return "Municipal_Vice_Mayor"
        if "MAYOR" in p:
            return "Municipal_Mayor"
        if "COUNCILOR" in p or "SB MEMBER" in p or "SANGGUNIANG BAYAN" in p:
            return "Municipal_Councilor"

    return "Unknown"


# ==================== MAIN ====================
def main():
    print("=" * 60)
    print("=== Building PN3 Position Lookup ===")
    print("=" * 60)

    # 1. Load existing nodes in extraction order
    print(f"\nLoading nodes: {PN3_NODES}")
    if not os.path.exists(PN3_NODES):
        print(f"CRITICAL: {PN3_NODES} not found.")
        return
    nodes = pd.read_csv(PN3_NODES, dtype={"home_psgc": str}, keep_default_na=False)
    node_ids = nodes["person_id"].tolist()
    print(f"  {len(node_ids)} existing nodes")

    # 2. Replay extraction filter — positions come out in same order
    print(f"\nReplaying extraction filter on source files:")
    matched_positions = []

    files_config = [
        (PROVINCIAL_XLSX, "provincial"),
        (CITY_XLSX,       "city"),
        (MUNICIPAL_XLSX,  "municipal"),
    ]

    for xlsx, level in files_config:
        if not os.path.exists(xlsx):
            print(f"  ✗ MISSING: {xlsx}")
            continue
        print(f"  Reading {os.path.basename(xlsx)} ({level})")
        xls = pd.ExcelFile(xlsx)

        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet_name)
            if df.empty:
                continue
            df.columns = [str(c).strip() for c in df.columns]
            col_info = detect_columns(df)
            pos_col = col_info.get("position")
            if not pos_col:
                continue

            for _, row in df.iterrows():
                pos_str = str(row[pos_col]).strip() if pd.notna(row[pos_col]) else ""
                if not pos_str:
                    continue
                if not any(kw.upper() in pos_str.upper() for kw in POSITION_KEYWORDS[level]):
                    continue

                first, middle, last, suffix = extract_name_from_row(row, col_info)
                fn = title_case(first)
                ln = title_case(last)
                if not (fn or ln):
                    continue

                matched_positions.append({
                    "position_type": canonical_position(pos_str, level),
                    "raw_position": pos_str,
                    "level": level,
                })

    # 3. Verify match count
    print(f"\nMatched rows from source : {len(matched_positions)}")
    print(f"Existing nodes in CSV    : {len(node_ids)}")

    if len(matched_positions) != len(node_ids):
        print(f"\n⚠ MISMATCH ({len(matched_positions)} vs {len(node_ids)})")
        print(f"  Likely cause: source files changed, or extraction logic drifted.")
        print(f"  Aborting to avoid wrong assignments.")
        return

    # 4. Zip up — same order, same IDs
    lookup = {}
    for pid, pos in zip(node_ids, matched_positions):
        lookup[pid] = pos

    # 5. Save
    with open(OUT_PN3, "w", encoding="utf-8") as f:
        json.dump(lookup, f, ensure_ascii=False)
    size_kb = os.path.getsize(OUT_PN3) / 1024
    print(f"\n✓ Saved: {OUT_PN3} ({size_kb:.1f} KB)")

    # 6. Distribution summary
    counts = Counter(p["position_type"] for p in matched_positions)
    print(f"\n=== Position distribution ===")
    for pos, cnt in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {pos:<25} {cnt:>6}")


if __name__ == "__main__":
    main()