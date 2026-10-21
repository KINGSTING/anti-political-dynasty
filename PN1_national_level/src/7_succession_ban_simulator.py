#!/usr/bin/env python3
"""
7_succession_ban_simulator.py
=============================
PN1 Succession-Ban Simulator — 2025 national winners only.

Scope:
    • National seats only (President, VP, Senator, Party-List,
      Member of the House of Representatives).
    • Target election year: 2025.
    • For each 2025 national winner, find the most recent prior winner
      of the same seat family who is a relative within 4th civil degree.
    • Cycle-aware confidence tiers:
        - STRONG   = immediate predecessor cycle (Rep: 3y, Senate: 6y)
        - MODERATE = one full cycle skipped
        - WEAK     = 2+ cycles skipped
        - SUSPECT  = kin is *still in office* (Senate: 2022 kin of a 2025
                     winner is an ally, not a predecessor)
"""

import os
import re
import unicodedata
import pandas as pd

BASE_DIR = r"C:\Users\HP\Desktop\JJ\anti-political-dynasty"
DATA_DIR = os.path.join(BASE_DIR, "PN1_national_level", "data")

INPUT_HISTORY_CSV = os.path.join(DATA_DIR, "electoral_history.csv")
INPUT_KINSHIP_CSV = os.path.join(DATA_DIR, "national_edges_FINAL.csv")
INPUT_NODES_CSV   = os.path.join(DATA_DIR, "national_nodes.csv")
OUTPUT_REPORT_CSV = os.path.join(DATA_DIR, "dynastic_handoffs_2025_national.csv")

CIVIL_DEGREE_THRESHOLD = 4
TARGET_YEAR = 2025

NATIONAL_SEAT_PREFIXES = (
    "PH-SENATOR", "PH-PRESIDENT", "PH-VICE_PRESIDENT",
    "PH-PARTY_LIST", "PH-MEMBER_HOUSE_OF_REPRESENTATIVES",
    "PH-DISTRICT_REPRESENTATIVE", "PH-REPRESENTATIVE",
)

SUFFIX_TOKENS  = {"JR", "SR", "II", "III", "IV", "V", "VI"}
PREPEND_TOKENS = {"PER", "POL", "PH"}
# PATCH 1: also split on quotes and parentheses so nicknames like
#   Ferdinand Alexander "Sandro" Marcos  →  SANDRO becomes its own token.
NAME_SPLIT_RE  = re.compile(r"[\s_\-/,\.'\"()]+")

NICKNAME_TO_LEGAL = {
    "WIN": "SHERWIN",   "DICK": "RICHARD",  "MIGZ": "MIGUEL",
    "KIKO": "FRANCIS",  "PING": "PANFILO",  "TITO": "VICENTE",
    "BONG": "RAMON",    "BONGBONG": "FERDINAND", "NOYNOY": "BENIGNO",
    "JINGGOY": "JOSEPH","JV": "JOSEPH",     "TESSIE": "TERESITA",
    "SONNY": "JOSE",    "DIGONG": "RODRIGO", "DODOY": "RODRIGO",
    "BATO": "RONALD",   "BISTEK": "HERBERT","CHIZ": "FRANCIS",
    "TOL": "FRANCIS",   "GRINGO": "GREGORIO","BASTE": "SEBASTIAN",
    "PULONG": "PAOLO",  "RISA": "ANA",
}

# PATCH 2: Authoritative PER → POL overrides. Checked before every fuzzy tier.
# Fill these in whenever you've confirmed the mapping by hand.
MANUAL_PER_TO_POL_OVERRIDES = {
    "PER-MARCOS-SANDRO":    "POL-PH-000215",
    "PER-MARCOS-IMEE":      "POL-PH-000017",
    "PER-COJUANGCO-MARCOS": "POL-PH-000101",   # ← optional, see note below
}


# ---------------------------------------------------------------------------
# Name canonicalization
# ---------------------------------------------------------------------------
def _repair_mojibake(s):
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def _strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def _normalize(s):
    return _strip_accents(_repair_mojibake(str(s).strip())).upper()


def canonical_name_key(raw_name):
    if pd.isna(raw_name) or not str(raw_name).strip():
        return ""
    text = _normalize(raw_name)
    toks = [t for t in NAME_SPLIT_RE.split(text)
            if t and t not in PREPEND_TOKENS and t not in SUFFIX_TOKENS]
    return "|".join(sorted(toks)) if toks else ""


def _node_surnames(raw_name):
    if pd.isna(raw_name) or not str(raw_name).strip():
        return []
    toks = [t for t in NAME_SPLIT_RE.split(_normalize(raw_name))
            if t and t not in SUFFIX_TOKENS]
    if len(toks) < 2:
        return []
    forms = [toks[-1], toks[-2] + "_" + toks[-1]]
    if len(toks) >= 3 and toks[-3] in {"DE", "DEL", "DELA", "DELOS", "DELAS"}:
        forms.append(toks[-3] + "_" + toks[-2] + "_" + toks[-1])
    return list(dict.fromkeys(forms))


def _per_parts(body):
    if "-" not in body:
        return [], []
    last_seg, first_seg = body.split("-", 1)
    last_tokens = [t for t in last_seg.upper().split("_") if t]
    surnames = ["_".join(last_tokens[i:]) for i in range(len(last_tokens))]
    first_tokens = [t for t in first_seg.upper().replace("_", " ").split() if t]
    return surnames, first_tokens


def _expand_first(tok):
    return NICKNAME_TO_LEGAL.get(tok.upper(), tok.upper())


def sanitize(text):
    return "" if pd.isna(text) else str(text).strip().upper()


# ---------------------------------------------------------------------------
# Crosswalk (3-tier cascade + manual overrides)
# ---------------------------------------------------------------------------
def build_crosswalk(df_history, df_nodes, national_only=True):
    node_key_to_pol, node_by_token = {}, {}
    node_by_surname, node_first_tokens = {}, {}

    for _, row in df_nodes.iterrows():
        name = row.get("full_name_clean", "") or row.get("full_name", "")
        k = canonical_name_key(name)
        if not k:
            continue
        pol = row["person_id"]
        node_key_to_pol.setdefault(k, pol)
        for tok in k.split("|"):
            node_by_token.setdefault(tok, set()).add((k, pol))
        for surname in _node_surnames(name):
            node_by_surname.setdefault(surname, []).append(pol)
        node_first_tokens[pol] = set(k.split("|"))

    if national_only:
        mask = df_history["seat_id"].fillna("").str.startswith(NATIONAL_SEAT_PREFIXES)
        targets = df_history.loc[mask, "person_id"].dropna().unique()
        print(f"   → limiting crosswalk to national seats: {len(targets):,} unique PERs")
    else:
        targets = df_history["person_id"].dropna().unique()

    # PATCH 3: add manual_override tier
    mapping, unresolved = {}, []
    tier_counts = {"exact": 0, "subset": 0, "surname_nick": 0, "manual_override": 0}

    for per_id in targets:
        # Tier 0 — manual overrides win
        if per_id in MANUAL_PER_TO_POL_OVERRIDES:
            mapping[per_id] = MANUAL_PER_TO_POL_OVERRIDES[per_id]
            tier_counts["manual_override"] += 1
            continue

        body = per_id[4:] if per_id.upper().startswith("PER-") else per_id
        k = canonical_name_key(body)
        if not k:
            unresolved.append(per_id)
            continue

        # Tier 1 — exact
        if k in node_key_to_pol:
            mapping[per_id] = node_key_to_pol[k]
            tier_counts["exact"] += 1
            continue

        per_toks = set(k.split("|"))
        if len(per_toks) < 2:
            unresolved.append(per_id)
            continue

        # Tier 2 — subset with ≤1 diff
        candidates = None
        for tok in per_toks:
            bucket = node_by_token.get(tok, set())
            candidates = bucket if candidates is None else candidates & bucket
            if not candidates:
                break
        if candidates:
            matched = None
            for node_key, pol_id in candidates:
                if len(per_toks.symmetric_difference(node_key.split("|"))) <= 1:
                    matched = pol_id
                    break
            if matched:
                mapping[per_id] = matched
                tier_counts["subset"] += 1
                continue

        # Tier 3 — surname + nickname
        surnames, first_tokens = _per_parts(body)
        matched = None
        for surname in surnames:
            bucket = node_by_surname.get(surname)
            if not bucket:
                continue
            if len(bucket) == 1:
                matched = bucket[0]
                break
            for ft in first_tokens:
                expanded = _expand_first(ft)
                for pol_id in bucket:
                    if expanded in node_first_tokens.get(pol_id, set()):
                        matched = pol_id
                        break
                if matched:
                    break
            if matched:
                break
        if matched:
            mapping[per_id] = matched
            tier_counts["surname_nick"] += 1
            continue

        unresolved.append(per_id)

    # PATCH 3: extended diagnostic
    marcos_per = [p for p in targets if "MARCOS" in p.upper()]
    marcos_ok = [p for p in marcos_per if p in mapping]
    print(f"   → tier breakdown: exact={tier_counts['exact']:,}, "
          f"subset={tier_counts['subset']:,}, "
          f"surname+nickname={tier_counts['surname_nick']:,}, "
          f"manual={tier_counts['manual_override']:,}")
    print(f"   → MARCOS-family: {len(marcos_ok)}/{len(marcos_per)} resolved")
    for p in marcos_per:
        if p not in mapping:
            print(f"       ✗ still unresolved: {p}")
    return mapping, unresolved


# ---------------------------------------------------------------------------
# Cycle-aware classification
# ---------------------------------------------------------------------------
def _expected_term(seat_id):
    """Constitutional term length in years for a seat family."""
    if seat_id.startswith(("PH-SENATOR", "PH-PRESIDENT", "PH-VICE_PRESIDENT")):
        return 6
    return 3  # Rep, and all local offices


def _classify(gap, expected_term):
    if gap < expected_term:
        # Kin is still in office — same-cycle ally, not a predecessor
        return "SUSPECT (kin still in office)"
    if gap == expected_term:
        return "STRONG (immediate predecessor)"
    if gap == 2 * expected_term:
        return "MODERATE (one cycle skipped)"
    return "WEAK (multi-cycle gap)"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("🚀 PN1 — 2025 National Succession-Ban Simulation\n")

    for p in (INPUT_HISTORY_CSV, INPUT_KINSHIP_CSV, INPUT_NODES_CSV):
        if not os.path.exists(p):
            raise FileNotFoundError(f"❌ Missing required file asset at '{p}'")

    df_history = pd.read_csv(INPUT_HISTORY_CSV, dtype=str, keep_default_na=False)
    df_edges   = pd.read_csv(INPUT_KINSHIP_CSV, dtype=str, keep_default_na=False)
    df_nodes   = pd.read_csv(INPUT_NODES_CSV,   dtype=str, keep_default_na=False)

    print(f"📊 Loaded {len(df_history):,} election entries, "
          f"{len(df_edges):,} kinship edges, {len(df_nodes):,} nodes.")

    # ---- National-seat inventory ----
    nat_mask = df_history["seat_id"].fillna("").str.startswith(NATIONAL_SEAT_PREFIXES)
    df_nat = df_history[nat_mask].copy()
    df_nat["election_year"] = pd.to_numeric(
        df_nat["election_year"], errors="coerce").fillna(0).astype(int)
    winners = df_nat[df_nat["is_winner"].str.lower() == "true"].copy()
    print(f"🏛️  {len(winners):,} national winners across "
          f"{winners['seat_id'].nunique():,} national seat families.")

    winners_2025 = winners[winners["election_year"] == TARGET_YEAR]
    print(f"🎯 {len(winners_2025):,} winners in {TARGET_YEAR} "
          f"across {winners_2025['seat_id'].nunique():,} seats.")
    if winners_2025.empty:
        print(f"⚠️  No {TARGET_YEAR} national winners in the file — nothing to do.")
        return

    # ---- Crosswalk ----
    print("\n💎 Building PER → POL crosswalk (national scope)...")
    per_to_pol, _ = build_crosswalk(df_history, df_nodes, national_only=True)
    pol_in_graph = set()
    for _, r in df_edges.iterrows():
        pol_in_graph.add(sanitize(r.get("person_a_id", "")))
        pol_in_graph.add(sanitize(r.get("person_b_id", "")))
    overlap = set(per_to_pol.values()) & pol_in_graph
    print(f"🔗 {len(overlap):,} national resolved persons appear in the "
          f"{len(df_edges)}-edge kinship graph.")

    id_to_real_name = dict(zip(df_nodes["person_id"], df_nodes["full_name_clean"]))

    # ---- Kinship matrix ----
    kinship = {}
    for _, r in df_edges.iterrows():
        a, b = sanitize(r["person_a_id"]), sanitize(r["person_b_id"])
        rel = r.get("relation_label", "RELATIVE") or "RELATIVE"
        try:
            deg = int(r["civil_degree"])
        except (ValueError, KeyError):
            deg = CIVIL_DEGREE_THRESHOLD
        kinship[(a, b)] = kinship[(b, a)] = {"relation": rel, "degree": deg}

    # ---- 2025 winner vs prior kin-of-same-seat ----
    winners = winners.sort_values(["seat_id", "election_year"]).reset_index(drop=True)
    flagged = []
    stats = {"targets": 0, "with_prior": 0, "resolved": 0, "kin_hits": 0}

    for seat_id, group in winners.groupby("seat_id", sort=False):
        targets = group[group["election_year"] == TARGET_YEAR]
        priors  = group[group["election_year"] < TARGET_YEAR]
        if targets.empty or priors.empty:
            continue

        prior_years = sorted(priors["election_year"].unique(), reverse=True)
        expected_term = _expected_term(seat_id)

        for _, cur in targets.iterrows():
            stats["targets"] += 1
            stats["with_prior"] += 1
            cur_pol = per_to_pol.get(cur["person_id"])
            if not cur_pol:
                continue
            stats["resolved"] += 1

            hit = None
            for cycle_idx, pyear in enumerate(prior_years):
                year_priors = priors[priors["election_year"] == pyear]
                for _, prior in year_priors.iterrows():
                    prior_pol = per_to_pol.get(prior["person_id"])
                    if not prior_pol or prior_pol == cur_pol:
                        continue
                    link = kinship.get((cur_pol, prior_pol))
                    if link and link["degree"] <= CIVIL_DEGREE_THRESHOLD:
                        gap = TARGET_YEAR - int(pyear)
                        hit = {
                            "simulation_election_year":  TARGET_YEAR,
                            "seat_id":                   seat_id,
                            "successor_pol_id":          cur_pol,
                            "successor_name":            id_to_real_name.get(cur_pol, cur["person_id"]),
                            "predecessor_pol_id":        prior_pol,
                            "predecessor_name":          id_to_real_name.get(prior_pol, prior["person_id"]),
                            "predecessor_election_year": int(pyear),
                            "years_since_predecessor":   gap,
                            "prior_cycles_between":      cycle_idx,
                            "bloodline_relation":        link["relation"],
                            "civil_degree_distance":     link["degree"],
                            "confidence_tier":           _classify(gap, expected_term),
                            "simulation_disqualification_status": "BANNED",
                        }
                        break
                if hit:
                    break

            if hit:
                stats["kin_hits"] += 1
                flagged.append(hit)

    print(f"\n🗂️  {stats['targets']:,} {TARGET_YEAR} targets scanned")
    print(f"   → {stats['with_prior']:,} seats have a prior cycle to compare against")
    print(f"   → {stats['resolved']:,} targets resolved to a kinship-graph POL id")
    print(f"   → {stats['kin_hits']:,} had a relative as a previous seat holder")

    if not flagged:
        print("\n✅ No dynastic violations flagged for 2025 national winners.")
        return

    out = (pd.DataFrame(flagged)
           .drop_duplicates(subset=["seat_id", "successor_pol_id"])
           .sort_values(["seat_id", "predecessor_election_year"])
           .reset_index(drop=True))

    os.makedirs(os.path.dirname(OUTPUT_REPORT_CSV), exist_ok=True)
    out.to_csv(OUTPUT_REPORT_CSV, index=False, encoding="utf-8-sig")

    print(f"\n🚨 2025 NATIONAL SIMULATION COMPLETE — {len(out):,} flag(s).")
    print(f"💾 Report → '{OUTPUT_REPORT_CSV}'")

    print("\n=== Confidence-tier summary ===")
    print(out["confidence_tier"].value_counts().to_string())

    print("\n=== Flags by seat ===")
    print(out.groupby("seat_id").size().sort_values(ascending=False).to_string())

    print("\n=== All flagged pairs ===")
    print(out[["seat_id", "successor_name", "predecessor_name",
               "predecessor_election_year", "years_since_predecessor",
               "bloodline_relation", "confidence_tier"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()