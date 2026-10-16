"""
Congressional Kinship Graph Extractor v2
-----------------------------------------
Fixes:
  - Converts "Last, First M." -> "First Last" for Wikidata search
  - Global rate limiter (1 request / 1.5s)
  - Retry on HTTP 429 with exponential backoff (5, 15, 45s)
  - Checkpoints to kinship_progress.json so you can resume
"""

import os
import csv
import re
import sys
import json
import time
import urllib.parse
import urllib.request
import urllib.error

HOR_FILE      = os.path.join("data", "HOR_members.txt")
SENATORS_FILE = os.path.join("data", "Senate_members.txt")
NODES_FILE    = "kinship_nodes.csv"
EDGES_FILE    = "kinship_edges.txt"
AUDIT_FILE    = "kinship_edges_audit.csv"
RAW_DUMP      = "kinship_edges_all_wikidata.csv"
PROGRESS_FILE = "kinship_progress.json"

USER_AGENT = "KinshipGraphBot/1.0 (research; contact: local)"
WD_API     = "https://www.wikidata.org/w/api.php"

REL_PROPS = {
    "P22":   ("Father",  "1st degree", "Consanguinity"),
    "P25":   ("Mother",  "1st degree", "Consanguinity"),
    "P26":   ("Spouse",  "1st degree", "Affinity"),
    "P3373": ("Sibling", "1st degree", "Consanguinity"),
    "P40":   ("Child",   "1st degree", "Consanguinity"),
}

# ---------------------------------------------------------------------------
# Rate-limited HTTP with retry
# ---------------------------------------------------------------------------

_LAST_CALL = [0.0]
_MIN_INTERVAL = 1.5  # seconds between requests


def _wait():
    now = time.time()
    elapsed = now - _LAST_CALL[0]
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _LAST_CALL[0] = time.time()


def http_get(url, params=None, timeout=30, retries=(5, 15, 45)):
    full = url
    if params:
        full = url + "?" + urllib.parse.urlencode(params)
    last_err = None
    for attempt in range(len(retries) + 1):
        _wait()
        req = urllib.request.Request(full, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429 and attempt < len(retries):
                wait = retries[attempt]
                print(f"    [429] sleeping {wait}s...")
                time.sleep(wait)
                continue
            if 500 <= e.code < 600 and attempt < len(retries):
                wait = retries[attempt]
                print(f"    [{e.code}] sleeping {wait}s...")
                time.sleep(wait)
                continue
            raise
        except Exception as e:
            last_err = e
            if attempt < len(retries):
                time.sleep(retries[attempt])
                continue
            raise
    raise last_err


# ---------------------------------------------------------------------------
# Name conversion
# ---------------------------------------------------------------------------

def to_wikidata_name(name):
    """
    'Abalos, JC M.' -> 'JC Abalos'
    'Aquino, Jose "Joboy" II S.' -> 'Jose II Aquino'
    'Angara, Rommel Rico T.' -> 'Rommel Rico Angara'
    """
    # Strip quotes/nicknames
    name = re.sub(r'"[^"]*"', "", name)
    # Remove trailing degrees like ', M.D.', ', RN', ', DPA'
    name = re.sub(r",\s*(M\.?D\.?|RN|DPA|Atty\.?|Dr\.?|Engr\.?)\s*$", "", name, flags=re.IGNORECASE)
    if "," in name:
        left, right = name.split(",", 1)
        surname = left.strip()
        rest = right.strip()
    else:
        parts = name.split()
        if len(parts) < 2:
            return name.strip()
        surname = parts[-1]
        rest = " ".join(parts[:-1])
    # Remove single-letter initials from rest (JC M. -> JC)
    rest = re.sub(r"\b[A-Z]\.\s*", "", rest)
    # Collapse whitespace
    rest = re.sub(r"\s+", " ", rest).strip()
    return f"{rest} {surname}".strip()


def surname(name):
    if "," in name:
        return name.split(",", 1)[0].strip().lower()
    parts = name.split()
    return parts[-1].strip(".,").lower() if parts else ""


def first_tokens(name):
    if "," in name:
        rest = name.split(",", 1)[1]
    else:
        parts = name.split()
        rest = " ".join(parts[:-1])
    rest = re.sub(r'"[^"]*"', "", rest)
    return [t.strip(".,").lower() for t in rest.split() if len(t.strip(".,")) > 1]


def build_index(officials):
    idx = {}
    for o in officials:
        s = surname(o["name"])
        if s:
            idx.setdefault(s, []).append(o)
    return idx


def match_official(candidate, index):
    if not candidate:
        return None
    toks = re.findall(r"[a-zA-Z]+", candidate.lower())
    if not toks:
        return None
    for i, t in enumerate(toks):
        if t not in index:
            continue
        for o in index[t]:
            ftoks = first_tokens(o["name"])
            if not ftoks:
                continue
            other = [x for j, x in enumerate(toks) if j != i]
            if any(ft in other for ft in ftoks):
                return o
    return None


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_hor(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines[1:]:
        line = line.rstrip("\n")
        if not line.strip():
            continue
        parts = line.rsplit(",", 2)
        if len(parts) < 3:
            continue
        name, district, province = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if not name:
            continue
        loc = f"{province} Party-list" if district.lower() == "party-list" else f"{district}, {province}"
        rows.append({"name": name, "location": loc, "chamber": "Congressman"})
    return rows


def load_senators(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines[1:]:
        line = line.rstrip("\n")
        if not line.strip():
            continue
        parts = line.rsplit(",", 2)
        if len(parts) < 3:
            continue
        name, _pos, loc = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if not name:
            continue
        rows.append({"name": name, "location": loc, "chamber": "Senator"})
    return rows


# ---------------------------------------------------------------------------
# Wikidata
# ---------------------------------------------------------------------------

def wd_search(name):
    try:
        data = http_get(WD_API, {
            "action": "wbsearchentities",
            "search": name,
            "language": "en",
            "format": "json",
            "limit": 5,
            "type": "item",
        })
        return [{"id": h.get("id"), "label": h.get("label", ""),
                 "description": h.get("description", "")}
                for h in data.get("search", [])]
    except Exception as e:
        print(f"    [search error] {e}")
        return []


def wd_get_claims(qid):
    try:
        data = http_get(WD_API, {
            "action": "wbgetentities",
            "ids": qid,
            "format": "json",
            "props": "claims|labels|descriptions",
            "languages": "en",
        })
        ent = data.get("entities", {}).get(qid, {})
        return {
            "claims": ent.get("claims", {}),
            "label": ent.get("labels", {}).get("en", {}).get("value", qid),
            "description": ent.get("descriptions", {}).get("en", {}).get("value", ""),
        }
    except Exception as e:
        print(f"    [claims error] {e}")
        return {"claims": {}, "label": qid, "description": ""}


def wd_get_label(qid):
    """Get English label for a single QID."""
    ent = wd_get_claims(qid)
    return ent["label"], ent["description"]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    for p in (HOR_FILE, SENATORS_FILE):
        if not os.path.exists(p):
            sys.exit(f"Missing: {os.path.abspath(p)}")

    hor = load_hor(HOR_FILE)
    senators = load_senators(SENATORS_FILE)
    print(f"Loaded {len(hor)} HOR, {len(senators)} senators")

    officials = hor + senators
    index = build_index(officials)

    all_people = {}
    for o in officials:
        key = o["name"].lower()
        if key not in all_people:
            all_people[key] = o
    print(f"Unique officials: {len(all_people)}\n")

    # Load progress
    progress = {}
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, encoding="utf-8") as f:
                progress = json.load(f)
            print(f"Resuming: {len(progress)} officials already resolved\n")
        except Exception:
            progress = {}

    # ---- Phase 1: resolve officials to QIDs ----
    print("Phase 1: Resolving officials to Wikidata QIDs")
    print("(this will take ~15 min; progress saved to kinship_progress.json)\n")

    for i, (key, o) in enumerate(all_people.items(), 1):
        if key in progress:
            continue
        wd_name = to_wikidata_name(o["name"])
        print(f"[{i}/{len(all_people)}] {o['name']}  ->  '{wd_name}'")
        hits = wd_search(wd_name)
        chosen = None
        for h in hits:
            desc = (h.get("description") or "").lower()
            if any(k in desc for k in ["philippin", "politician", "congress", "senator", "representative"]):
                chosen = h
                break
        if not chosen and hits:
            chosen = hits[0]
        if chosen:
            print(f"    -> {chosen['id']}  ({chosen['label']} — {chosen['description'][:70]})")
            progress[key] = {
                "qid": chosen["id"],
                "wd_label": chosen["label"],
                "wd_description": chosen["description"],
            }
        else:
            print(f"    no hit")
            progress[key] = None
        # checkpoint
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(progress, f, indent=2)

    resolved = []
    for key, o in all_people.items():
        p = progress.get(key)
        if p and p.get("qid"):
            resolved.append({"official": o, "qid": p["qid"],
                             "wd_label": p["wd_label"], "wd_description": p["wd_description"]})
    print(f"\nResolved {len(resolved)} / {len(all_people)} officials\n")

    # ---- Phase 2: fetch family relations ----
    print("Phase 2: Fetching family relations from Wikidata\n")
    raw_edges = []
    for i, r in enumerate(resolved, 1):
        qid = r["qid"]
        name = r["official"]["name"]
        print(f"[{i}/{len(resolved)}] {name} ({qid})")
        ent = wd_get_claims(qid)
        claims = ent["claims"]
        rels = []
        for prop, (label, degree, ktype) in REL_PROPS.items():
            for claim in claims.get(prop, []):
                dv = claim.get("mainsnak", {}).get("datavalue", {})
                val = dv.get("value", {})
                if isinstance(val, dict) and val.get("id"):
                    rels.append({"relative_qid": val["id"], "relation_label": label,
                                 "degree": degree, "kinship_type": ktype})
        if not rels:
            print("    (none)")
            continue
        for rel in rels:
            rel_name, rel_desc = wd_get_label(rel["relative_qid"])
            match = match_official(rel_name, index)
            print(f"    {rel['relation_label']:8s} -> {rel_name}" +
                  (f"  [MATCH: {match['name']}]" if match else ""))
            raw_edges.append({
                "official_name": name,
                "official_qid": qid,
                "official_chamber": r["official"]["chamber"],
                "official_location": r["official"]["location"],
                "relative_qid": rel["relative_qid"],
                "relative_wd_label": rel_name,
                "relative_wd_desc": rel_desc,
                "relation_label": rel["relation_label"],
                "kinship_type": rel["kinship_type"],
                "civil_degree": rel["degree"],
                "matched_official": match,
            })

    # ---- Phase 3: keep only chamber-crossing edges ----
    kept = []
    for e in raw_edges:
        m = e["matched_official"]
        if not m:
            continue
        if m["name"].lower() == e["official_name"].lower():
            continue
        kept.append({
            "person_a": e["official_name"],
            "person_a_chamber": e["official_chamber"],
            "person_a_location": e["official_location"],
            "person_b": m["name"],
            "person_b_chamber": m["chamber"],
            "person_b_location": m["location"],
            "relation_label": e["relation_label"],
            "kinship_type": e["kinship_type"],
            "civil_degree": e["civil_degree"],
            "source": f"Wikidata {e['official_qid']} → {e['relative_qid']}",
        })

    seen, deduped = set(), []
    for e in kept:
        key = tuple(sorted([e["person_a"].lower(), e["person_b"].lower()])) + (e["relation_label"].lower(),)
        if key not in seen:
            seen.add(key)
            deduped.append(e)

    print(f"\nRaw edges: {len(raw_edges)}")
    print(f"Chamber-crossing edges: {len(deduped)}\n")

    # ---- Phase 4: write output ----
    nodes = {}
    for e in deduped:
        nodes.setdefault(e["person_a"], (e["person_a_chamber"], e["person_a_location"]))
        nodes.setdefault(e["person_b"], (e["person_b_chamber"], e["person_b_location"]))

    with open(NODES_FILE, "w", encoding="utf-8") as f:
        f.write("Name, Position, Location from\n")
        for n, (pos, loc) in sorted(nodes.items()):
            f.write(f"{n}, {pos}, {loc}\n")

    with open(EDGES_FILE, "w", encoding="utf-8") as f:
        for e in deduped:
            f.write(f"{e['person_a']} : {e['person_b']} -> "
                    f"{e['relation_label']} : {e['civil_degree']}\n")

    with open(AUDIT_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["person_a", "person_b", "relation_label", "kinship_type",
                    "civil_degree", "source"])
        for e in deduped:
            w.writerow([e["person_a"], e["person_b"], e["relation_label"],
                        e["kinship_type"], e["civil_degree"], e["source"]])

    with open(RAW_DUMP, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["official", "official_qid", "relation", "relative",
                    "relative_qid", "relative_description", "matched_in_db"])
        for e in raw_edges:
            w.writerow([e["official_name"], e["official_qid"],
                        e["relation_label"], e["relative_wd_label"],
                        e["relative_qid"], e["relative_wd_desc"],
                        "yes" if e["matched_official"] else "no"])

    print(f"[OK] {os.path.abspath(NODES_FILE)}  ({len(nodes)} nodes)")
    print(f"[OK] {os.path.abspath(EDGES_FILE)}  ({len(deduped)} edges)")
    print(f"[OK] {os.path.abspath(AUDIT_FILE)}")
    print(f"[OK] {os.path.abspath(RAW_DUMP)}  (all relations, incl. non-officials)")

    print("\n--- Edges produced ---")
    for e in deduped:
        print(f"  {e['person_a']} : {e['person_b']} -> "
              f"{e['relation_label']} : {e['civil_degree']}")


if __name__ == "__main__":
    main()