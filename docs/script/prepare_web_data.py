"""
Prepare web-ready data files.

Copies source CSVs into web/data/ and generates PSGC name lookup JSON.
Run from repo root after pipeline has finished.
"""

import os
import shutil
import json

import pandas as pd

# ==================== PATHS ====================
BASE = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty"

PN1_DATA = os.path.join(BASE, "PN1_national_level", "data")
PN2_DATA = os.path.join(BASE, "PN2_national-subnational_level", "data")
PN3_DATA = os.path.join(BASE, "PN3_inter-intra_local_level", "data")

# ✅ FIXED: PSGC is in data/, not repo root
PSGC_FILE = os.path.join(BASE, "data", "PSGC-3Q-2026-Publication-Datafile.xlsx")

# Output folder
WEB_DATA = os.path.join(BASE, "web", "data")
os.makedirs(WEB_DATA, exist_ok=True)


# ==================== HELPERS ====================
copied = []
missing = []


def copy_file(src, dst, label):
    """Copy src -> dst and log result. Returns True if copied."""
    if os.path.exists(src):
        shutil.copy2(src, dst)
        size_kb = os.path.getsize(dst) / 1024
        print(f"  ✓ {label:<20} {size_kb:>9.1f} KB  ← {os.path.basename(src)}")
        copied.append((label, dst, size_kb))
        return True
    else:
        print(f"  ✗ {label:<20} MISSING      ← {src}")
        missing.append((label, src))
        return False


def prefer(final, fallback):
    """Prefer FINAL file if it exists, else the merged fallback."""
    if os.path.exists(final):
        return final
    return fallback


# ==================== PN1 ====================
print("\n=== PN1 (national) ===")
copy_file(
    os.path.join(PN1_DATA, "national_nodes.csv"),
    os.path.join(WEB_DATA, "PN1_nodes.csv"),
    "PN1_nodes",
)
copy_file(
    os.path.join(PN1_DATA, "national_edges.csv"),
    os.path.join(WEB_DATA, "PN1_edges.csv"),
    "PN1_edges",
)
copy_file(
    os.path.join(PN1_DATA, "national_seats.csv"),
    os.path.join(WEB_DATA, "PN1_seats.csv"),
    "PN1_seats",
)


# ==================== PN2 ====================
print("\n=== PN2 (national + subnational) ===")
pn2_edges_src = prefer(
    os.path.join(PN2_DATA, "national+subnational_edges_FINAL.csv"),
    os.path.join(PN2_DATA, "national+subnational_edges_merged.csv"),
)
copy_file(pn2_edges_src,
          os.path.join(WEB_DATA, "PN2_edges.csv"),
          "PN2_edges")
copy_file(
    os.path.join(PN2_DATA, "national+subnational_nodes.csv"),
    os.path.join(WEB_DATA, "PN2_nodes.csv"),
    "PN2_nodes",
)
copy_file(
    os.path.join(PN2_DATA, "national+subnational_seats.csv"),
    os.path.join(WEB_DATA, "PN2_seats.csv"),
    "PN2_seats",
)


# ==================== PN3 ====================
print("\n=== PN3 (local) ===")
pn3_edges_src = prefer(
    os.path.join(PN3_DATA, "inter-intra_local_edges_FINAL.csv"),
    os.path.join(PN3_DATA, "inter-intra_local_edges_merged.csv"),
)
copy_file(pn3_edges_src,
          os.path.join(WEB_DATA, "PN3_edges.csv"),
          "PN3_edges")
copy_file(
    os.path.join(PN3_DATA, "inter-intra_local_nodes.csv"),
    os.path.join(WEB_DATA, "PN3_nodes.csv"),
    "PN3_nodes",
)
copy_file(
    os.path.join(PN3_DATA, "inter-intra_local_seats.csv"),
    os.path.join(WEB_DATA, "PN3_seats.csv"),
    "PN3_seats",
)


# ==================== PSGC NAMES ====================
print("\n=== PSGC name lookup ===")
if not os.path.exists(PSGC_FILE):
    print(f"  ✗ PSGC file missing: {PSGC_FILE}")
    missing.append(("psgc_names", PSGC_FILE))
else:
    print(f"  Reading: {os.path.basename(PSGC_FILE)}")
    df = pd.read_excel(PSGC_FILE, sheet_name="PSGC")
    df.columns = [str(c).replace("\n", " ").strip() for c in df.columns]

    # Exclude 'Unnamed' columns (they can match 'NAME' by substring)
    col_dict = {
        c.upper(): c for c in df.columns
        if not str(c).upper().startswith("UNNAMED")
    }
    code_col = next(
        (col_dict[c] for c in col_dict if "10-DIGIT" in c or "PSGC" in c),
        None,
    )
    name_col = next(
        (col_dict[c] for c in col_dict if "NAME" in c),
        None,
    )

    if not (code_col and name_col):
        print(f"  ✗ Could not detect columns. Available: {list(col_dict.values())}")
        missing.append(("psgc_names", PSGC_FILE))
    else:
        print(f"  Columns: code='{code_col}', name='{name_col}'")
        psgc_map = {}
        for _, r in df.iterrows():
            raw = str(r[code_col]).strip() if pd.notna(r[code_col]) else ""
            if raw.endswith(".0"):
                raw = raw[:-2]
            code = raw.zfill(10)
            if code and code != "0000000000":
                psgc_map[code] = str(r[name_col]).strip()

        out_path = os.path.join(WEB_DATA, "psgc_names.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(psgc_map, f, ensure_ascii=False)

        size_kb = os.path.getsize(out_path) / 1024
        print(f"  ✓ psgc_names           {size_kb:>9.1f} KB  ({len(psgc_map):,} codes)")
        copied.append(("psgc_names", out_path, size_kb))


# ==================== SUMMARY ====================
print(f"\n{'=' * 60}")
print(f"=== SUMMARY ===")
print(f"{'=' * 60}")
print(f"Copied : {len(copied)} files")
print(f"Missing: {len(missing)} files")

if missing:
    print(f"\n⚠ Missing files:")
    for label, path in missing:
        print(f"  {label}: {path}")
    print(f"\n  → Ensure the pipeline has been run for the affected dataset(s).")
else:
    total_kb = sum(s for _, _, s in copied)
    print(f"\n✅ All web data ready at: {WEB_DATA}")
    print(f"   Total: {total_kb/1024:.1f} MB")
    print(f"\n   Next:")
    print(f"     python -m http.server 8000")
    print(f"   Then open:")
    print(f"     http://localhost:8000/web/")