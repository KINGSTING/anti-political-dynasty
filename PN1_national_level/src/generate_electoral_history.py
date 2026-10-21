#!/usr/bin/env python3
"""
generate_electoral_history.py
=============================
Author: AI Collaborator
Description: Generates an engineered Electoral History fact table (PN1_edges)
             by ingesting raw winners data (supporting custom headers/headerless files)
             and prepping it for succession ban simulations.
"""

import os
import pandas as pd

# Define Pipeline Paths
INPUT_WINNERS_CSV = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty\data\NLE_Winners_2004-2025.csv"
OUTPUT_HISTORY_CSV = r"PN1_national_level\data\electoral_history.csv"

# Canonical schema used consistently throughout the pipeline
EXPECTED_COLUMNS = [
    "last_name", "first_name", "middle_name", "source_agency", "title_suffix",
    "full_name_clean", "position", "party", "year", "province",
    "municipality", "region", "gender", "data_tag",
]

# Aliases: canonical name -> possible raw header variants (post basic normalization)
COLUMN_ALIASES = {
    "last_name":       ["lastname", "last", "surname", "family_name", "apelyido"],
    "first_name":      ["firstname", "first", "given_name", "given", "pangalan"],
    "middle_name":     ["middlename", "middle", "middle_initial", "mi"],
    "source_agency":   ["source", "agency", "data_source", "source_of_data"],
    "title_suffix":    ["suffix", "name_suffix", "title", "honorific"],
    "full_name_clean": ["clean_full_name", "full_name", "fullname",
                        "complete_name", "name", "candidate_name"],
    "position":        ["position_title", "office", "office_title", "seat",
                        "position_name"],
    "party":           ["political_party", "party_affiliation", "party_list", "partido"],
    "year":            ["election_year", "yr", "election_yr", "elec_year"],
    "province":        ["prov", "provincial_district", "probinsya"],
    "municipality":    ["city", "city_municipality", "municipality_city", "town",
                        "municipality_name", "city/municipality", "municipality/city",
                        "city_or_municipality", "lgu", "municity", "city_mun"],
    "region":          ["reg", "region_name", "rehiyon"],
    "gender":          ["sex", "gender_identity", "kasarian"],
    "data_tag":        ["tag", "data_label", "dataset_tag", "label", "remarks"],
}


def sanitize_and_normalize(text):
    """Standardizes raw human text inputs into predictable uppercase tokens."""
    if pd.isna(text) or not str(text).strip():
        return ""
    token = str(text).strip().upper()
    token = token.replace(" ", "_").replace(".", "").replace(",", "")
    token = token.replace("__", "_")
    return token


def normalize_column_names(df):
    """Lowercase/snake_case all columns, then map known aliases to canonical names."""
    df.columns = [str(c).strip().lower().replace(" ", "_").replace("-", "_")
                  for c in df.columns]

    reverse = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        reverse[canonical] = canonical
        for alias in aliases:
            reverse[alias] = canonical

    rename_map = {c: reverse[c] for c in df.columns if c in reverse}
    if rename_map:
        df = df.rename(columns=rename_map)

    # Collapse duplicate columns (e.g., both "Year" and "year" present)
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()]

    return df


def ensure_columns(df, required):
    """Create empty placeholders for any missing canonical columns."""
    for col in required:
        if col not in df.columns:
            print(f"⚠️  Missing expected column '{col}'; inserting empty placeholder.")
            df[col] = ""
    return df


def detect_header(first_line):
    """Return True if the first CSV line looks like a header row."""
    tokens = [t.strip().strip('"').strip("'").lower() for t in first_line.split(",")]
    known = {
        "year", "person_id", "last_name", "first_name", "last name", "first name",
        "position", "party", "province", "municipality", "region", "gender",
        "full_name", "full name", "source_agency",
    }
    return any(tok in known or tok.replace(" ", "_") in known for tok in tokens)


def main():
    print("🚀 Initiating Revised Electoral History Generation Pipeline...")

    if not os.path.exists(INPUT_WINNERS_CSV):
        raise FileNotFoundError(
            f"❌ Error: Raw Election Fact File not found at '{INPUT_WINNERS_CSV}'"
        )

    with open(INPUT_WINNERS_CSV, "r", encoding="utf-8-sig") as f:
        first_line = f.readline()

    if detect_header(first_line):
        print("📊 Column labels detected inside target CSV file asset.")
        df = pd.read_csv(INPUT_WINNERS_CSV, dtype=str, encoding="utf-8-sig")
        df = normalize_column_names(df)
    else:
        print("⚠️  Headerless raw CSV detected. Applying implicit 14-column layout.")
        df = pd.read_csv(
            INPUT_WINNERS_CSV, header=None, names=EXPECTED_COLUMNS,
            dtype=str, encoding="utf-8-sig",
        )

    # Guarantee every canonical column exists before we touch it
    df = ensure_columns(df, EXPECTED_COLUMNS)

    # ------------------------------------------------------------------
    # Derived keys
    # ------------------------------------------------------------------
    if ("person_id" not in df.columns
            or df["person_id"].fillna("").astype(str).str.strip().eq("").all()):
        print("🔗 Generating derived person_id tokens from name blocks...")
        df["person_id"] = (
            "PER-"
            + df["last_name"].fillna("").apply(sanitize_and_normalize)
            + "-"
            + df["first_name"].fillna("").apply(sanitize_and_normalize)
        )

    if ("seat_id" not in df.columns
            or df["seat_id"].fillna("").astype(str).str.strip().eq("").all()):
        print("🗺️  Building seat_id tokens from position + territory...")
        df["seat_id"] = (
            "PH-"
            + df["position"].fillna("").apply(sanitize_and_normalize)
            + "-"
            + df["province"].fillna("").apply(sanitize_and_normalize)
        )
        muni = df["municipality"].fillna("").astype(str).str.strip()
        is_local = muni != ""
        df.loc[is_local, "seat_id"] = (
            df.loc[is_local, "seat_id"]
            + "-"
            + muni[is_local].apply(sanitize_and_normalize)
        )

    # ------------------------------------------------------------------
    # Standardize value matrices (lowercase 'year' now — matches schema)
    # ------------------------------------------------------------------
    df["year"] = pd.to_numeric(df["year"], errors="coerce").fillna(2001).astype(int)
    df["person_id"] = df["person_id"].fillna("").apply(sanitize_and_normalize)
    df["seat_id"]   = df["seat_id"].fillna("").apply(sanitize_and_normalize)

    # ------------------------------------------------------------------
    # Ordering + slot ranks
    # ------------------------------------------------------------------
    df = df.sort_values(by=["seat_id", "year"]).reset_index(drop=True)

    print("💎 Allocating relative placement ranks to plural board seats...")
    df["seat_slot_rank"] = df.groupby(["seat_id", "year"]).cumcount() + 1

    # ------------------------------------------------------------------
    # Build output records
    # ------------------------------------------------------------------
    history_records = []
    print("🧬 Packaging historical election dataset rows...")
    for idx, row in df.iterrows():
        year_val = int(row["year"])
        history_records.append({
            "history_id":                  f"EH-{year_val}-{idx + 1:06d}",
            "election_year":               year_val,
            "person_id":                   row["person_id"],
            "seat_id":                     row["seat_id"],
            "seat_slot_rank":              int(row["seat_slot_rank"]),
            "is_winner":                   "True",
            "succession_type":             "GENERAL_ELECTION",
            "consecutive_term_num":        1,
            "predecessor_person_id":       "",
            "predecessor_relation_degree": "",
            "is_immediate_succession":     "False",
            "is_position_swap":            "False",
        })

    out_df = pd.DataFrame(history_records)
    os.makedirs(os.path.dirname(OUTPUT_HISTORY_CSV), exist_ok=True)
    out_df.to_csv(OUTPUT_HISTORY_CSV, index=False, encoding="utf-8")

    print(f"📊 Success! Generated {len(out_df)} historical election entries.")
    print(f"💾 File compiled securely at -> '{OUTPUT_HISTORY_CSV}'")


if __name__ == "__main__":
    main()