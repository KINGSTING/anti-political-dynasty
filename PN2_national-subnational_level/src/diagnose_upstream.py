"""Check upstream node files for header artifacts."""

import os
import pandas as pd

BASE = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty"

FILES = [
    os.path.join(BASE, "PN1_national_level", "data", "national_nodes.csv"),
    os.path.join(BASE, "PN2_national-subnational_level", "data", "national+subnational_nodes.csv"),
    os.path.join(BASE, "PN3_inter-intra_local_level", "data", "inter-intra_local_nodes.csv"),
]

for f in FILES:
    if not os.path.exists(f):
        print(f"⚠ NOT FOUND: {f}")
        continue
    print(f"\n{'=' * 60}")
    print(f"File: {os.path.basename(f)}")
    print(f"{'=' * 60}")
    df = pd.read_csv(f, dtype=str, keep_default_na=False)
    print(f"  Total rows: {len(df)}")

    # Header artifact check
    header_like = df[df["person_id"].astype(str).str.strip().str.lower() == "person_id"]
    print(f"  Header artifacts (person_id == 'person_id'): {len(header_like)}")

    # Malformed rows
    bad = df[~df["person_id"].astype(str).str.startswith("POL-PH-", na=False)]
    print(f"  Malformed (not POL-PH-): {len(bad)}")

    # Duplicates
    dup_count = df["person_id"].duplicated().sum()
    print(f"  Duplicate person_id rows: {dup_count}")

    if len(bad):
        print(f"\n  Sample malformed rows (first 5):")
        print(bad.head(5).to_string(index=False))