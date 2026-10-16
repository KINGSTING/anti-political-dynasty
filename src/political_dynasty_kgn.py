"""
Interactive Kinship Network — pyvis (multi-position)
----------------------------------------------------
Only officials with at least one kinship edge are rendered.  Edge-less
nodes are dropped before the graph is built, so no hidden node ever
reaches the physics engine.

Every position uses a fixed-size shape (dot, star, square, triangle,
triangleDown, diamond) so the label renders OUTSIDE the shape.  vis.js
auto-sizes box / ellipse / circle / database / hexagon to fit their
label, which produces giant barrels for long names.
"""

import os
import re
import csv
import sys
import json
import unicodedata
from collections import Counter
import pandas as pd
import networkx as nx
from pyvis.network import Network

NODES_FILE  = "kinship_nodes.csv"
EDGES_FILE  = "kinship_edges.txt"
OUTPUT_HTML = "kinship_graph.html"

# Drop every node with zero kinship edges.  Only the connected core renders.
HIDE_ISOLATES = True

# Optional: if you later want certain edge-less positions kept as a
# search-only layer, list their canonical names here and set HIDE_ISOLATES
# logic below to retain them.  Currently empty — everything unconnected is
# dropped so the canvas stays clean and the physics engine stays fast.
ALWAYS_VISIBLE_POSITIONS = set()


# ---------------------------------------------------------------------------
# Position → symbol mapping.  FIXED-SIZE shapes only, so labels float outside.
# ---------------------------------------------------------------------------
POSITION_STYLE = {
    "President":      {"shape": "star",         "color": "#ffd700", "border": "#b8860b",
                       "size": 44, "label": "President",        "z": 100},
    "Vice President": {"shape": "star",         "color": "#d4d4d4", "border": "#808080",
                       "size": 38, "label": "Vice President",   "z": 95},
    "Senator":        {"shape": "dot",          "color": "#f5d6a0", "border": "#8a6b2e",
                       "size": 26, "label": "Senator",          "z": 60},
    "Congressman":    {"shape": "square",       "color": "#a9c8e8", "border": "#2e5a8a",
                       "size": 22, "label": "Congressman",      "z": 50},
    # ----- local executive -----
    "Governor":       {"shape": "triangle",     "color": "#90ee90", "border": "#2d6a2d",
                       "size": 28, "label": "Governor",         "z": 58},
    "Vice Governor":  {"shape": "triangleDown", "color": "#c6f57a", "border": "#4a6e10",
                       "size": 26, "label": "Vice Governor",    "z": 56},
    "Mayor":          {"shape": "dot",          "color": "#4ecdc4", "border": "#1a7a73",
                       "size": 24, "label": "Mayor",            "z": 54},
    "Vice Mayor":     {"shape": "dot",          "color": "#a0e5e0", "border": "#1a7a73",
                       "size": 20, "label": "Vice Mayor",       "z": 49},
    # ----- local legislative -----
    "Board Member":   {"shape": "diamond",      "color": "#87ceeb", "border": "#1e5f8a",
                       "size": 20, "label": "Board Member",     "z": 45},
    "City Councilor": {"shape": "dot",          "color": "#d8a3d8", "border": "#6a2c6a",
                       "size": 16, "label": "City Councilor",   "z": 42},
    "Councilor":      {"shape": "dot",          "color": "#f0d8f0", "border": "#8b458b",
                       "size": 14, "label": "Councilor (Mun.)", "z": 40},
}
DEFAULT_STYLE = {"shape": "dot", "color": "#cccccc", "border": "#666666",
                 "size": 18, "label": "Other", "z": 10}


POSITION_ALIASES = {
    "sangguniang panlalawigan member": "Board Member",
    "sangguniang panlalawigan":        "Board Member",
    "sp member":                        "Board Member",
    "sp":                               "Board Member",
    "provincial board member":          "Board Member",
    "provincial board":                 "Board Member",
    "board member":                     "Board Member",
    "sangguniang panlungsod member":    "City Councilor",
    "sangguniang panlungsod":           "City Councilor",
    "city councilor":                   "City Councilor",
    "city council member":              "City Councilor",
    "city council":                     "City Councilor",
    "sangguniang bayan member":         "Councilor",
    "sangguniang bayan":                "Councilor",
    "municipal councilor":              "Councilor",
    "councilor":                        "Councilor",
    "city mayor":                       "Mayor",
    "municipal mayor":                  "Mayor",
    "mayor":                            "Mayor",
    "alkalde":                          "Mayor",
    "punong lungsod":                   "Mayor",
    "punong bayan":                     "Mayor",
    "city vice mayor":                  "Vice Mayor",
    "municipal vice mayor":             "Vice Mayor",
    "vice mayor":                       "Vice Mayor",
    "bise alkalde":                     "Vice Mayor",
    "vice punong lungsod":              "Vice Mayor",
    "vice punong bayan":                "Vice Mayor",
}


def canonical_position(position):
    if not position:
        return None
    if position in POSITION_STYLE:
        return position
    return POSITION_ALIASES.get(position.strip().lower())


def style_for(position):
    return POSITION_STYLE.get(canonical_position(position), DEFAULT_STYLE)


# ---------------------------------------------------------------------------
# Edge styling
# ---------------------------------------------------------------------------
DEGREE_COLORS = {
    "1st degree": "#d62728", "2nd degree": "#ff7f0e", "3rd degree": "#2ca02c",
    "4th degree": "#1f77b4", "5th degree": "#9467bd", "6th degree": "#8c564b",
    "Unknown":    "#888888",
}
DEGREE_WIDTH = {
    "1st degree": 6, "2nd degree": 4, "3rd degree": 3, "4th degree": 2,
    "5th degree": 2, "6th degree": 1, "Unknown": 1,
}


# ---------------------------------------------------------------------------
# Name normalization + alias map
# ---------------------------------------------------------------------------
def normalize_name(s):
    s = (s or "").strip().replace('"', "").replace("'", "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^0-9a-z\s\-]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


NAME_ALIASES = {
    "sara duterte-carpio":           "sara zimmerman duterte-carpio",
    "ferdinand marcos jr":           "ferdinand bongbong marcos jr",
    "ronald singson":                "ronald v singson",
    "paolo duterte":                 "paolo z duterte",
    "omar duterte":                  "omar vincent sangkola duterte",
    "andrei duterte":                "andrei red duterte",
    "ferdinand martin romualdez":    "ferdinand martin g romualdez",
    "kenneth gatchalian":            "kenneth t gatchalian",
    "benjamin agarao jr":            "agarana, benjamin jr c",
    "carmelo lazatin jr":            "carmelo lazatin ii",
    "maria jamina katherine agarao": "maria jamina katherine baltazar agarao",
    "luis bernardez bersamin iv":    "luis jorobots bernardez bersamin iv",
    "jiselle rae aumentado villamor":"jiselле rae aumentado villamor",
    "nilo marco miranda demerey":    "nilo marco miranda demerey nan",
    "erlene luz villanueva dela cruz":"erlene luz villanueva dela cruz nan",
}


# ---------------------------------------------------------------------------
# Province → Region lookup
# ---------------------------------------------------------------------------
_PROVINCE_TO_REGION = {
    "metro manila": "NCR", "manila": "NCR", "quezon city": "NCR", "caloocan": "NCR",
    "makati": "NCR", "pasig": "NCR", "taguig": "NCR", "paranaque": "NCR",
    "las pinas": "NCR", "muntinlupa": "NCR", "marikina": "NCR", "valenzuela": "NCR",
    "malabon": "NCR", "navotas": "NCR", "san juan": "NCR", "mandaluyong": "NCR",
    "pasay": "NCR", "pateros": "NCR",
    "abra": "CAR", "apayao": "CAR", "benguet": "CAR", "ifugao": "CAR",
    "kalinga": "CAR", "mountain province": "CAR", "baguio": "CAR",
    "ilocos norte": "Region I", "ilocos sur": "Region I", "la union": "Region I",
    "pangasinan": "Region I", "dagupan": "Region I",
    "batanes": "Region II", "cagayan": "Region II", "isabela": "Region II",
    "nueva vizcaya": "Region II", "quirino": "Region II", "santiago": "Region II",
    "aurora": "Region III", "bataan": "Region III", "bulacan": "Region III",
    "nueva ecija": "Region III", "pampanga": "Region III", "tarlac": "Region III",
    "zambales": "Region III", "angeles": "Region III", "olongapo": "Region III",
    "batangas": "Region IV-A", "cavite": "Region IV-A", "laguna": "Region IV-A",
    "quezon": "Region IV-A", "rizal": "Region IV-A", "lucena": "Region IV-A",
    "antipolo": "Region IV-A",
    "marinduque": "MIMAROPA", "occidental mindoro": "MIMAROPA",
    "oriental mindoro": "MIMAROPA", "palawan": "MIMAROPA", "romblon": "MIMAROPA",
    "puerto princesa": "MIMAROPA",
    "albay": "Region V", "camarines norte": "Region V", "camarines sur": "Region V",
    "catanduanes": "Region V", "masbate": "Region V", "sorsogon": "Region V",
    "naga": "Region V", "legazpi": "Region V",
    "aklan": "Region VI", "antique": "Region VI", "capiz": "Region VI",
    "guimaras": "Region VI", "iloilo": "Region VI", "negros occidental": "Region VI",
    "bacolod": "Region VI",
    "bohol": "Region VII", "cebu": "Region VII", "negros oriental": "Region VII",
    "siquijor": "Region VII", "lapu-lapu": "Region VII", "mandaue": "Region VII",
    "biliran": "Region VIII", "eastern samar": "Region VIII", "leyte": "Region VIII",
    "northern samar": "Region VIII", "samar": "Region VIII",
    "southern leyte": "Region VIII", "tacloban": "Region VIII",
    "zamboanga del norte": "Region IX", "zamboanga del sur": "Region IX",
    "zamboanga sibugay": "Region IX", "zamboanga city": "Region IX",
    "pagadian": "Region IX",
    "bukidnon": "Region X", "camiguin": "Region X", "lanao del norte": "Region X",
    "misamis occidental": "Region X", "misamis oriental": "Region X",
    "cagayan de oro": "Region X", "iligan": "Region X",
    "davao de oro": "Region XI", "davao del norte": "Region XI",
    "davao del sur": "Region XI", "davao occidental": "Region XI",
    "davao oriental": "Region XI", "davao city": "Region XI",
    "cotabato": "Region XII", "sarangani": "Region XII", "south cotabato": "Region XII",
    "sultan kudarat": "Region XII", "general santos": "Region XII",
    "kidapawan": "Region XII",
    "agusan del norte": "Region XIII", "agusan del sur": "Region XIII",
    "dinagat islands": "Region XIII", "surigao del norte": "Region XIII",
    "surigao del sur": "Region XIII", "butuan": "Region XIII",
    "basilan": "BARMM", "lanao del sur": "BARMM", "maguindanao": "BARMM",
    "maguindanao del norte": "BARMM", "maguindanao del sur": "BARMM",
    "sulu": "BARMM", "tawi-tawi": "BARMM", "cotabato city": "BARMM",
}


def _norm(s):
    s = (s or "").strip().lower()
    s = s.replace("province of", " ").replace("city of", " ")
    s = re.sub(r"[^0-9a-zñáéíóú\s\-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def infer_region(location):
    key = _norm(location)
    if not key:
        return ""
    if key in _PROVINCE_TO_REGION:
        return _PROVINCE_TO_REGION[key]
    for suffix in (" province", " city", " municipality"):
        if key.endswith(suffix):
            k2 = key[: -len(suffix)].strip()
            if k2 in _PROVINCE_TO_REGION:
                return _PROVINCE_TO_REGION[k2]
    for name in sorted(_PROVINCE_TO_REGION, key=len, reverse=True):
        if re.search(r"\b" + re.escape(name) + r"\b", key):
            return _PROVINCE_TO_REGION[name]
    return ""


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def _clean(s):
    return (s or "").strip().strip('"').strip("'").strip()


def load_nodes(path):
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if not row or not _clean(row[0]):
                continue
            name     = _clean(row[0])
            position = _clean(row[1]) if len(row) > 1 else ""
            province = _clean(row[2]) if len(row) > 2 else ""
            region   = _clean(row[3]) if len(row) > 3 else ""

            if name.lower() in ("name", "full name"):
                continue
            if position.lower() in ("position", "positions"):
                continue

            extra = [_clean(c) for c in row[4:] if _clean(c)]
            if extra:
                province = ", ".join([p for p in [province] + extra if p])
            if not region:
                region = infer_region(province)

            rows.append({"Name": name, "Position": position,
                         "Province": province, "Region": region})
    return pd.DataFrame(rows)


_CSV_COL_A   = ("Vice-Governor", "Vice Governor", "a", "A", "Source")
_CSV_COL_B   = ("Related Official", "Related", "b", "B", "Target")
_CSV_COL_REL = ("Relation", "Relationship", "relation")
_CSV_COL_DEG = ("Degree Level", "Degree", "degree")
_CSV_COL_TYP = ("Consanguinity/Affinity", "Kinship Type", "Type",
                "kinship_type", "type")


def _pick(d, candidates):
    lower = {k.lower(): v for k, v in d.items() if k}
    for c in candidates:
        if c.lower() in lower and _clean(lower[c.lower()]):
            return _clean(lower[c.lower()])
    return ""


def _load_csv_edges(path):
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            a   = _pick(r, _CSV_COL_A)
            b   = _pick(r, _CSV_COL_B)
            rel = _pick(r, _CSV_COL_REL)
            deg = _pick(r, _CSV_COL_DEG)
            typ = _pick(r, _CSV_COL_TYP)
            if a and b:
                rows.append({"a": a, "b": b, "relation": rel,
                             "degree": deg, "kinship_type": typ})
            else:
                print(f"  [skip csv] {r}")
    return rows


def _load_colon_edges(path):
    pattern = re.compile(r"^(?P<a>.+?)\s*:\s*(?P<b>.+?)\s*->\s*(?P<rest>.+)$")
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.rstrip("\n").strip()
            if not line or line.startswith("#"):
                continue
            m = pattern.match(line)
            if not m:
                print(f"  [skip colon] {line}")
                continue

            rest = m.group("rest").strip()
            parts = [p.strip() for p in rest.split(":")]
            if len(parts) >= 3:
                rel = " : ".join(parts[:-2]); deg = parts[-2]; typ = parts[-1]
            elif len(parts) == 2:
                rel, typ = parts; deg = ""
            else:
                rel, deg, typ = parts[0], "", ""

            rows.append({
                "a": _clean(m.group("a")),
                "b": _clean(m.group("b")),
                "relation":     _clean(rel),
                "degree":       _clean(deg),
                "kinship_type": _clean(typ),
            })
    return rows


def load_edges(path):
    with open(path, encoding="utf-8-sig") as f:
        head = f.readline()
    is_csv = ("," in head) and ("->" not in head)
    rows = _load_csv_edges(path) if is_csv else _load_colon_edges(path)
    print(f"  edge format detected: {'CSV' if is_csv else 'colon'}")
    return pd.DataFrame(rows)


def deduplicate(df):
    seen, out = {}, []
    for _, row in df.iterrows():
        key = tuple(sorted([row["a"], row["b"]]))
        if key in seen:
            seen[key]["labels"].append((row["a"], row["relation"]))
            continue
        entry = {
            "a": row["a"], "b": row["b"],
            "labels": [(row["a"], row["relation"])],
            "degree": row["degree"],
            "kinship_type": row["kinship_type"],
        }
        seen[key] = entry
        out.append(entry)
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------
def build_graph(nodes_df, edges_df):
    G = nx.Graph()
    for _, row in nodes_df.iterrows():
        G.add_node(row["Name"], position=row["Position"],
                   province=row["Province"], region=row["Region"])

    node_lookup = {normalize_name(n): n for n in G.nodes}

    def resolve(name):
        key = normalize_name(name)
        if key in node_lookup:
            return node_lookup[key]
        target = NAME_ALIASES.get(key)
        if target and target in node_lookup:
            return node_lookup[target]
        return None

    missing = []
    for _, row in edges_df.iterrows():
        a = resolve(row["a"])
        b = resolve(row["b"])
        if a is None or b is None:
            missing.append((row["a"], row["b"]))
            continue
        rel = " / ".join(sorted(set(r for _, r in row["labels"])))
        title = (f"<b>{a} ↔ {b}</b><br>{rel}<br>"
                 f"{row['degree']} · {row['kinship_type']}")
        G.add_edge(a, b, relation=rel, degree=row["degree"],
                   kinship_type=row["kinship_type"], title=title)

    if missing:
        print(f"\n  [WARN] {len(missing)} edge(s) had an endpoint not in nodes file:")
        for a, b in missing[:15]:
            print(f"    - '{a}'  ↔  '{b}'")
        if len(missing) > 15:
            print(f"    ... and {len(missing) - 15} more")
        print("  Tip: add unresolved pairs to NAME_ALIASES using normalized names.")
    return G


# ---------------------------------------------------------------------------
# pyvis rendering
# ---------------------------------------------------------------------------
def render(G, output_html):
    net = Network(height="900px", width="100%",
                  bgcolor="#1a1a1a", font_color="#f0f0f0",
                  directed=False, cdn_resources="in_line")
    net.barnes_hut(gravity=-9000, central_gravity=0.3,
                   spring_length=240, spring_strength=0.04, damping=0.09)

    for node, data in G.nodes(data=True):
        position = data.get("position", "")
        st = style_for(position)
        loc = " · ".join(b for b in (data.get("province", ""),
                                     data.get("region", "")) if b)
        title = (f"<b>{node}</b><br>{position}<br>{loc}<br>"
                 f"<i>degree in graph: {G.degree(node)}</i>")
        net.add_node(
            node, label=node, title=title,
            shape=st["shape"], size=st["size"],
            color={"background": st["color"], "border": st["border"],
                   "highlight": {"background": "#ffffff", "border": st["border"]}},
            font={"size": 14, "face": "Segoe UI", "color": "#f0f0f0"},
            borderWidth=3,
            level=st.get("z", 10),
        )

    for u, v, data in G.edges(data=True):
        deg = data.get("degree", "Unknown")
        net.add_edge(
            u, v, title=data.get("title", ""),
            color={"color": DEGREE_COLORS.get(deg, "#888"),
                   "highlight": "#ffffff", "hover": "#ffffff"},
            width=DEGREE_WIDTH.get(deg, 1),
            label=data.get("relation", ""),
            font={"size": 11, "color": "#d0d0d0", "strokeWidth": 2,
                  "strokeColor": "#1a1a1a", "align": "middle"},
            smooth={"type": "continuous", "roundness": 0.2},
        )

    n = G.number_of_nodes()
    iters = 150 if n > 2000 else 300 if n > 1000 else 500 if n > 500 else 600

    net.set_options(f"""
    var options = {{
      "interaction": {{"hover": true, "tooltipDelay": 80,
                       "navigationButtons": true,
                       "keyboard": {{"enabled": true}}}},
      "physics": {{"stabilization": {{"enabled": true, "iterations": {iters},
                                     "updateInterval": 25}}}},
      "layout": {{"randomSeed": 42}}
    }}
    """)

    try:
        html = net.generate_html(notebook=False)
    except TypeError:
        html = net.generate_html()

    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)
    return output_html


# ---------------------------------------------------------------------------
# Dynamic legend
# ---------------------------------------------------------------------------
def build_legend_html(G):
    present, seen = [], set()
    for n in G.nodes:
        p = G.nodes[n].get("position", "")
        if not p:
            continue
        st = style_for(p)
        canonical_label = st.get("label", p)
        if canonical_label in seen:
            continue
        seen.add(canonical_label)
        present.append(canonical_label)
    present.sort(key=lambda lbl: -max(
        (s.get("z", 0) for s in POSITION_STYLE.values() if s.get("label") == lbl),
        default=10))

    shape_css = {
        "star":         "clip-path:polygon(50% 0,61% 35%,98% 35%,68% 57%,79% 91%,50% 70%,21% 91%,32% 57%,2% 35%,39% 35%);",
        "dot":          "border-radius:50%;",
        "square":       "",
        "triangle":     "clip-path:polygon(50% 0,100% 100%,0 100%);",
        "triangleDown": "clip-path:polygon(0 0,100% 0,50% 100%);",
        "diamond":      "transform:rotate(45deg);",
    }

    rows = []
    for lbl in present:
        st = next((s for s in POSITION_STYLE.values() if s.get("label") == lbl),
                  DEFAULT_STYLE)
        css = shape_css.get(st["shape"], "border-radius:50%;")
        rows.append(
            f'<span style="display:inline-block;width:14px;height:14px;'
            f'background:{st["color"]};border:2px solid {st["border"]};'
            f'{css}vertical-align:middle;margin-right:6px;"></span>{st["label"]}<br>')
    chambers_html = "".join(rows)

    return f"""
    <div style="position:fixed;top:12px;left:12px;z-index:9999;
                background:rgba(26,26,26,0.92);color:#f0f0f0;
                padding:14px 18px;border-radius:10px;
                font-family:'Segoe UI',sans-serif;font-size:13px;
                box-shadow:0 4px 18px rgba(0,0,0,0.5);max-width:300px;">
      <div style="font-weight:700;font-size:14px;margin-bottom:8px;">
        Political Kinship Network<br>
        <span style="font-weight:400;font-size:11px;opacity:0.75;">
          National &amp; Local Officials (2022–2025)
        </span>
      </div>
      <div style="margin-bottom:10px;line-height:1.7;">{chambers_html}</div>
      <div style="font-weight:600;margin-bottom:4px;">Civil Degree</div>
      <div style="line-height:1.7;">
        <span style="display:inline-block;width:26px;height:4px;
                     background:#d62728;vertical-align:middle;margin-right:8px;"></span>1st — parent / child / spouse<br>
        <span style="display:inline-block;width:26px;height:4px;
                     background:#ff7f0e;vertical-align:middle;margin-right:8px;"></span>2nd — sibling / in-law<br>
        <span style="display:inline-block;width:26px;height:4px;
                     background:#2ca02c;vertical-align:middle;margin-right:8px;"></span>3rd — aunt/uncle / niece/nephew<br>
        <span style="display:inline-block;width:26px;height:4px;
                     background:#1f77b4;vertical-align:middle;margin-right:8px;"></span>4th — first cousin
      </div>
    </div>
    """


# ---------------------------------------------------------------------------
# Search / filter panel
# ---------------------------------------------------------------------------
FILTER_PANEL = """
<div id="kn-panel" style="position:fixed;top:12px;right:12px;z-index:9999;
     background:rgba(26,26,26,0.92);color:#f0f0f0;padding:14px 18px;
     border-radius:10px;font-family:'Segoe UI',sans-serif;font-size:13px;
     box-shadow:0 4px 18px rgba(0,0,0,0.5);width:270px;">
  <div style="font-weight:700;font-size:14px;margin-bottom:8px;">
    Search &amp; Filter
  </div>

  <input id="kn-search" type="text" placeholder="Name, position, province…"
     style="width:100%;box-sizing:border-box;padding:6px 8px;border-radius:6px;
            border:1px solid #444;background:#111;color:#f0f0f0;font-size:12px;
            margin-bottom:9px;outline:none;">

  <label for="kn-region"
     style="display:block;font-size:11px;opacity:0.75;margin-bottom:3px;">Region</label>
  <select id="kn-region"
     style="width:100%;box-sizing:border-box;padding:5px 6px;border-radius:6px;
            border:1px solid #444;background:#111;color:#f0f0f0;font-size:12px;
            margin-bottom:9px;outline:none;">
    <option value="">All regions</option>
  </select>

  <label for="kn-province"
     style="display:block;font-size:11px;opacity:0.75;margin-bottom:3px;">Province / Location</label>
  <select id="kn-province"
     style="width:100%;box-sizing:border-box;padding:5px 6px;border-radius:6px;
            border:1px solid #444;background:#111;color:#f0f0f0;font-size:12px;
            outline:none;">
    <option value="">All provinces</option>
  </select>

  <div style="display:flex;gap:8px;margin-top:11px;">
    <button id="kn-reset" type="button"
       style="flex:1;padding:6px 0;border-radius:6px;border:1px solid #555;
              background:#2a2a2a;color:#f0f0f0;font-size:12px;cursor:pointer;">
      Reset
    </button>
    <button id="kn-fit" type="button"
       style="flex:1;padding:6px 0;border-radius:6px;border:1px solid #555;
              background:#2a2a2a;color:#f0f0f0;font-size:12px;cursor:pointer;">
      Fit view
    </button>
  </div>

  <div id="kn-count"
       style="margin-top:9px;font-size:11px;opacity:0.75;">…</div>
</div>
"""


_FILTER_JS = r"""
<script type="text/javascript">
(function () {
  var META = __META__;
  var IDS  = Object.keys(META);

  var searchEl = document.getElementById('kn-search');
  var regionEl = document.getElementById('kn-region');
  var provEl   = document.getElementById('kn-province');
  var countEl  = document.getElementById('kn-count');
  var resetEl  = document.getElementById('kn-reset');
  var fitEl    = document.getElementById('kn-fit');
  if (!searchEl) { return; }

  function uniqSorted(field, filterFn) {
    var seen = {}, out = [];
    IDS.forEach(function (id) {
      var v = META[id][field];
      if (!v || seen[v]) { return; }
      if (filterFn && !filterFn(id)) { return; }
      seen[v] = 1; out.push(v);
    });
    out.sort(function (a, b) { return a.localeCompare(b); });
    return out;
  }

  function fillSelect(sel, values, allLabel) {
    var cur = sel.value;
    while (sel.firstChild) { sel.removeChild(sel.firstChild); }
    var o0 = document.createElement('option');
    o0.value = ''; o0.textContent = allLabel; sel.appendChild(o0);
    values.forEach(function (v) {
      var o = document.createElement('option');
      o.value = v; o.textContent = v; sel.appendChild(o);
    });
    sel.value = (values.indexOf(cur) >= 0) ? cur : '';
  }

  var REGIONS   = uniqSorted('r');
  var PROVINCES = uniqSorted('p');
  fillSelect(regionEl, REGIONS,   'All regions');
  fillSelect(provEl,   PROVINCES, 'All provinces');

  function refreshProvinces() {
    var r = regionEl.value;
    var list = r ? uniqSorted('p', function (id) { return META[id].r === r; })
                 : PROVINCES;
    fillSelect(provEl, list, 'All provinces');
  }

  var net = null;
  var debounce = null;

  function schedule() {
    if (debounce) { clearTimeout(debounce); }
    debounce = setTimeout(apply, 140);
  }

  function apply() {
    if (!net) { return; }
    var q = (searchEl.value || '').trim().toLowerCase();
    var r = regionEl.value;
    var p = provEl.value;

    var visible = {}, shown = 0;

    IDS.forEach(function (id) {
      var m = META[id], ok = true;
      if (r && m.r !== r) { ok = false; }
      if (ok && p && m.p !== p) { ok = false; }
      if (ok && q) {
        var hay = (id + ' ' + (m.s || '') + ' ' +
                   (m.p || '') + ' ' + (m.r || '')).toLowerCase();
        if (hay.indexOf(q) === -1) { ok = false; }
      }
      visible[id] = ok;
      if (ok) { shown++; }
    });

    var nodesDS = net.body.data.nodes;
    var edgesDS = net.body.data.edges;

    nodesDS.update(IDS.map(function (id) {
      return { id: id, hidden: !visible[id] };
    }));
    edgesDS.update(edgesDS.get().map(function (e) {
      return { id: e.id, hidden: !(visible[e.from] && visible[e.to]) };
    }));

    countEl.textContent = shown + ' of ' + IDS.length + ' officials shown';

    if (shown > 0) { net.fit({ animation: false }); }
  }

  searchEl.addEventListener('input', schedule);
  provEl.addEventListener('change', schedule);
  regionEl.addEventListener('change', function () {
    refreshProvinces(); schedule();
  });
  resetEl.addEventListener('click', function () {
    searchEl.value = ''; regionEl.value = '';
    refreshProvinces(); provEl.value = '';
    apply();
  });
  fitEl.addEventListener('click', function () {
    if (net) { net.fit({ animation: { duration: 400 } }); }
  });

  var tries = 0;
  function ready() {
    if (window.network && window.network.body &&
        window.network.body.data && window.network.body.data.nodes &&
        window.network.body.data.edges) {
      net = window.network; apply(); return;
    }
    tries += 1;
    if (tries > 200) {
      countEl.textContent = 'Filter unavailable (graph not found).'; return;
    }
    setTimeout(ready, 100);
  }
  ready();
})();
</script>
"""


def build_filter_html(G):
    meta = {}
    for n in G.nodes:
        d = G.nodes[n]
        meta[str(n)] = {
            "p": d.get("province", ""),
            "r": d.get("region", ""),
            "s": d.get("position", ""),
        }
    meta_json = json.dumps(meta, ensure_ascii=False)
    return FILTER_PANEL + _FILTER_JS.replace("__META__", meta_json)


def inject(html, fragment, marker, before=True):
    idx = html.lower().find(marker.lower())
    if idx == -1:
        return html + "\n" + fragment
    if before:
        return html[:idx] + fragment + "\n" + html[idx:]
    return html[:idx + len(marker)] + "\n" + fragment + html[idx + len(marker):]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    for p in (NODES_FILE, EDGES_FILE):
        if not os.path.exists(p):
            sys.exit(f"Missing: {os.path.abspath(p)}")

    nodes_df = load_nodes(NODES_FILE)
    print(f"Loaded {len(nodes_df)} nodes")
    print(f"  positions: {sorted(set(nodes_df['Position']))}")
    print(f"  regions  : {len(set(r for r in nodes_df['Region'] if r))} distinct")
    print(f"  provinces: {len(set(p for p in nodes_df['Province'] if p))} distinct")

    def count_pos(mask_labels):
        m = nodes_df["Position"].str.strip().str.lower().isin(mask_labels)
        return nodes_df[m]["Name"].tolist()

    cc_nodes = count_pos({"city councilor", "city council member", "city council",
                          "sangguniang panlungsod member", "sangguniang panlungsod"})
    mc_nodes = count_pos({"councilor", "municipal councilor",
                          "sangguniang bayan member", "sangguniang bayan"})
    mayor_nodes = count_pos({"mayor", "city mayor", "municipal mayor", "alkalde",
                             "punong lungsod", "punong bayan"})
    vmayor_nodes = count_pos({"vice mayor", "city vice mayor", "municipal vice mayor",
                              "bise alkalde", "vice punong lungsod", "vice punong bayan"})
    sp_nodes = count_pos({"sangguniang panlalawigan member", "sangguniang panlalawigan",
                          "sp member", "sp", "provincial board member",
                          "provincial board", "board member"})
    vg_nodes = nodes_df[nodes_df["Position"] == "Vice Governor"]["Name"].tolist()

    print(f"  City Councilor nodes: {len(cc_nodes)}")
    print(f"  Municipal Councilor nodes: {len(mc_nodes)}")
    print(f"  Mayor nodes: {len(mayor_nodes)}")
    print(f"  Vice Mayor nodes: {len(vmayor_nodes)}")
    print(f"  Sangguniang Panlalawigan / Board Members: {len(sp_nodes)}")
    print(f"  Vice-Governor nodes: {len(vg_nodes)}")

    edges_df = load_edges(EDGES_FILE)
    print(f"Loaded {len(edges_df)} raw edges")

    edges_df = deduplicate(edges_df)
    print(f"After dedup: {len(edges_df)} undirected edges")

    # ---- Diagnostic: resolve edge endpoints to canonical node names first,
    #      so case and middle-name variants don't cause false "0 edges".
    node_lookup_all = {normalize_name(r["Name"]): r["Name"]
                       for _, r in nodes_df.iterrows()}

    def _resolve_for_count(name):
        key = normalize_name(name)
        if key in node_lookup_all:
            return node_lookup_all[key]
        target = NAME_ALIASES.get(key)
        if target and target in node_lookup_all:
            return node_lookup_all[target]
        return None

    edges_count = edges_df.copy()
    edges_count["a_r"] = edges_count["a"].apply(_resolve_for_count)
    edges_count["b_r"] = edges_count["b"].apply(_resolve_for_count)

    for label, group in (
        ("City Councilor",      cc_nodes),
        ("Municipal Councilor", mc_nodes),
        ("Mayor",               mayor_nodes),
        ("Vice Mayor",          vmayor_nodes),
        ("SP/Board Member",     sp_nodes),
        ("Vice-Governor",       vg_nodes),
    ):
        s = set(group)
        n = int((edges_count["a_r"].isin(s)
                 | edges_count["b_r"].isin(s)).sum())
        print(f"  edges touching a {label}: {n}")
    print()

    G = build_graph(nodes_df, edges_df)

    # Drop every edge-less node.  Compute the isolate list and prune in one
    # pass; no kept-isolate bookkeeping is needed because the visible graph
    # shows only the connected core.
    isolates = [n for n in G.nodes if G.degree(n) == 0]
    if HIDE_ISOLATES and isolates:
        G.remove_nodes_from(isolates)

    print(f"\nGraph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    if HIDE_ISOLATES and isolates:
        print(f"Dropped {len(isolates)} unconnected official(s) "
              f"(no kinship edges recorded).")

    if G.number_of_nodes() == 0:
        print("\n[FATAL] No edges matched. Name mismatch between files.")
        sys.exit(1)

    out = render(G, OUTPUT_HTML)

    with open(out, encoding="utf-8") as f:
        html = f.read()

    html = inject(html, build_legend_html(G), "<body>", before=False)
    html = inject(html, build_filter_html(G), "</body>", before=True)

    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n[OK] {os.path.abspath(out)}")

    print("\n--- Clusters ---")
    for i, comp in enumerate(nx.connected_components(G), 1):
        names = ", ".join(sorted(comp))
        if len(names) > 220:
            names = names[:217] + "..."
        print(f"  {i}: {names}")

    print("\n--- Edges ---")
    for u, v, d in G.edges(data=True):
        print(f"  {u} — {v}  ({d['relation']}, {d['degree']}, {d['kinship_type']})")


if __name__ == "__main__":
    main()