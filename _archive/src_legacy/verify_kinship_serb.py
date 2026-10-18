"""
GWEN Cross-Validation of Kinship Edges Against SERB PDF
=========================================================
Reads kinship_nodes.csv, kinship_edges.txt, and the SERB PDF.
For each edge involving a target position (default: Governor),
locates PDF pages mentioning BOTH surnames, then asks Qwen whether
the text supports, contradicts, or is silent on the claimed relation.

Outputs: kinship_verification.csv (per-edge, per-page verdict)
"""

import os
import re
import csv
import json
import sys
import time
import httpx
from collections import defaultdict
from openai import OpenAI
from pypdf import PdfReader

# ---------- Config ----------
PDF_PATH      = os.path.join("data", "CSP-65-STATISTICAL-INVENTORY-OF-POTENTIAL-POLITICAL-DYNASTS.pdf")
NODES_FILE    = "kinship_nodes.csv"
EDGES_FILE    = "kinship_edges.txt"
OUTPUT_CSV    = "kinship_verification.csv"
PROGRESS_FILE = "kinship_verification_progress.json"

TARGET_POSITION = "Governor"   # set to "ALL" to verify every edge
MODEL = "qwen2.5:7b"
MAX_CHARS_PER_PAGE = 6000
MAX_PAGES_PER_EDGE = 3

client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
    timeout=httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=10.0),
)

# ---------- Prompts ----------
SYSTEM_PROMPT = """You verify whether a source text supports a kinship claim about Philippine politicians.

You will receive a CLAIM and a TEXT EXCERPT. Judge ONLY against the excerpt.

Reply with ONLY a JSON object:
{"status": "<supported|contradicted|partial|not_mentioned>", "evidence": "<exact quote or empty>"}

Definitions:
- supported     : text states or clearly implies the claimed relation
- contradicted  : text states a DIFFERENT relation for the same two people
- partial       : text mentions both people but does not state their relation
- not_mentioned : text does not mention one or both people, or is silent

Rules:
1. Quote evidence VERBATIM from the excerpt.
2. If evidence is empty, status MUST be "not_mentioned".
3. Do NOT use outside knowledge. Do NOT infer from surname alone.
4. Output pure JSON, nothing else."""

USER_TEMPLATE = """CLAIM: {a} and {b} are {relation} ({degree} civil degree, {ktype}).

TEXT:
{text}

Respond with JSON only."""

# ---------- Loading ----------
def load_nodes(path):
    nodes = {}
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if not row or not row[0].strip():
                continue
            nodes[row[0].strip().lower()] = {
                "display": row[0].strip(),
                "position": row[1].strip() if len(row) > 1 else "",
                "location": row[2].strip() if len(row) > 2 else "",
            }
    return nodes

def load_edges(path):
    pattern = re.compile(
        r"^(?P<a>.+?)\s*:\s*(?P<b>.+?)\s*->\s*(?P<rel>.+?)\s*:\s*"
        r"(?P<deg>[^:]+?)\s*:\s*(?P<type>\w+)\s*$"
    )
    edges = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.rstrip("\n").strip()
            if not line:
                continue
            m = pattern.match(line)
            if not m:
                continue
            edges.append({
                "a": m.group("a").strip(), "b": m.group("b").strip(),
                "relation": m.group("rel").strip(),
                "degree": m.group("deg").strip(),
                "kinship_type": m.group("type").strip(),
            })
    return edges

# ---------- PDF helpers ----------
def load_pdf_pages(path):
    if not os.path.exists(path):
        sys.exit(f"Missing PDF: {os.path.abspath(path)}")
    reader = PdfReader(path)
    pages = []
    for i, p in enumerate(reader.pages):
        try:
            text = p.extract_text() or ""
        except Exception:
            text = ""
        pages.append((i + 1, text))
    return pages

def surname_of(name):
    n = re.sub(r'"[^"]*"', " ", name)
    n = re.sub(r"\b(Jr|Sr|II|III|IV|V)\.?\b", " ", n, flags=re.IGNORECASE)
    toks = [t for t in re.split(r"\s+", n) if len(t) > 1]
    return toks[-1] if toks else ""

def find_pages_for_edge(pages, name_a, name_b):
    sa = surname_of(name_a).lower()
    sb = surname_of(name_b).lower()
    if not sa or not sb:
        return []
    hits = []
    for num, text in pages:
        if not text or len(text.strip()) < 30:
            continue
        low = text.lower()
        if sa in low and (sa == sb or sb in low):
            hits.append((num, text))
    return hits

def window_around(text, names, size=MAX_CHARS_PER_PAGE):
    if len(text) <= size:
        return text
    low = text.lower()
    positions = [low.find(surname_of(n).lower()) for n in names if surname_of(n)]
    positions = [p for p in positions if p >= 0]
    if not positions:
        return text[:size]
    center = min(positions)
    half = size // 2
    lo = max(0, center - half)
    return text[lo:lo + size]

# ---------- Model ----------
def salvage_json_object(s):
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    start = s.find("{")
    if start == -1:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(s)):
        c = s[i]
        if esc: esc = False; continue
        if c == "\\": esc = True; continue
        if c == '"': in_str = not in_str; continue
        if in_str: continue
        if c == "{": depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None

def call_model(edge, page_text):
    user = USER_TEMPLATE.format(
        a=edge["a"], b=edge["b"], relation=edge["relation"],
        degree=edge["degree"].replace(" degree", ""),
        ktype=edge["kinship_type"], text=page_text,
    )
    t0 = time.time()
    try:
        r = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": user}],
            temperature=0.0, seed=42, max_tokens=400,
        )
        data = salvage_json_object(r.choices[0].message.content or "")
        dt = time.time() - t0
        if not data or "status" not in data:
            return {"status": "parse_error", "evidence": ""}, dt
        status = str(data.get("status", "")).strip().lower()
        evidence = str(data.get("evidence", "")).strip()
        if status == "supported" and not evidence:
            status = "not_mentioned"
        return {"status": status, "evidence": evidence}, dt
    except httpx.ReadTimeout:
        return {"status": "timeout", "evidence": ""}, time.time() - t0
    except Exception as e:
        return {"status": f"error:{type(e).__name__}", "evidence": ""}, time.time() - t0

# ---------- Main ----------
def main():
    for p in (PDF_PATH, NODES_FILE, EDGES_FILE):
        if not os.path.exists(p):
            sys.exit(f"Missing: {os.path.abspath(p)}")

    nodes = load_nodes(NODES_FILE)
    edges = load_edges(EDGES_FILE)
    print(f"Loaded {len(nodes)} nodes, {len(edges)} edges")

    if TARGET_POSITION == "ALL":
        targets = edges
    else:
        targets = [e for e in edges if any(
            nodes.get(e[s].lower(), {}).get("position") == TARGET_POSITION
            for s in ("a", "b")
        )]
    print(f"  {len(targets)} edges involve a {TARGET_POSITION}\n")

    pages = load_pdf_pages(PDF_PATH)
    print(f"Loaded PDF: {len(pages)} pages\n")

    work = []
    for e in targets:
        hits = find_pages_for_edge(pages, e["a"], e["b"])[:MAX_PAGES_PER_EDGE]
        work.append((e, hits))

    total = sum(len(h) for _, h in work)
    print(f"Plan: {total} model calls across {len(work)} edges\n")

    progress = {}
    if os.path.exists(PROGRESS_FILE):
        try:
            progress = json.load(open(PROGRESS_FILE, encoding="utf-8"))
            print(f"Resuming: {len(progress)} (edge, page) pairs cached\n")
        except Exception:
            progress = {}

    results, idx = [], 0
    for e, hits in work:
        if not hits:
            results.append({**e, "pdf_page": "", "status": "no_matching_pages", "evidence": ""})
            continue
        for page_num, page_text in hits:
            key = f"{e['a']}|{e['b']}|{e['relation']}|{page_num}"
            if key in progress:
                results.append(progress[key])
                continue
            idx += 1
            print(f"[{idx}/{total}] {e['a']} ↔ {e['b']} (p{page_num})...",
                  end=" ", flush=True)
            window = window_around(page_text, [e["a"], e["b"]])
            verdict, dt = call_model(e, window)
            print(f"{verdict['status']} ({dt:.1f}s)")
            row = {**e, "pdf_page": page_num,
                   "status": verdict["status"], "evidence": verdict["evidence"]}
            results.append(row)
            progress[key] = row
            json.dump(progress, open(PROGRESS_FILE, "w", encoding="utf-8"),
                      indent=2, ensure_ascii=False)

    with open(OUTPUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["person_a", "person_b", "relation", "degree",
                    "kinship_type", "pdf_page", "status", "evidence"])
        for r in results:
            w.writerow([r["a"], r["b"], r["relation"], r["degree"],
                        r["kinship_type"], r.get("pdf_page", ""),
                        r["status"], r.get("evidence", "")])

    print(f"\n[OK] Wrote {OUTPUT_CSV}\n")

    agg = defaultdict(list)
    for r in results:
        agg[(r["a"], r["b"], r["relation"])].append(r["status"])

    RANK = {"supported": 4, "partial": 3, "contradicted": 2,
            "not_mentioned": 1, "no_matching_pages": 0,
            "parse_error": 0, "timeout": 0}

    print("=== Per-edge verdict ===")
    for (a, b, rel), statuses in sorted(agg.items()):
        best = max(statuses, key=lambda s: RANK.get(s, 0))
        tag = "✓" if best == "supported" else "·" if best in ("partial", "not_mentioned") else "✗"
        print(f"  {tag} {a} ↔ {b} ({rel}): {best}  [{'/'.join(statuses)}]")

    # Summary
    counts = defaultdict(int)
    for r in results:
        counts[r["status"]] += 1
    print("\n=== Summary (per edge-page call) ===")
    for s, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {s}: {n}")


if __name__ == "__main__":
    main()