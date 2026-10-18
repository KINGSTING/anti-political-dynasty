"""
One-shot deduplicator for kinship_nodes.csv and kinship_edges.txt.
Backs up the originals to *.bak before writing.
"""

import csv
import shutil
import os

NODES_FILE = "kinship_nodes.csv"
EDGES_FILE = "kinship_edges.txt"


def backup(path):
    bak = path + ".bak"
    if os.path.exists(path):
        shutil.copy2(path, bak)
        print(f"  backed up -> {bak}")


def clean_nodes(path):
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        seen = {}
        unique = []
        dupes = 0
        for row in reader:
            if not row or not row[0].strip():
                continue
            name = row[0].strip()
            key = name.lower()
            if key in seen:
                dupes += 1
                # If a duplicate has more complete position/location, keep it
                existing = seen[key]
                if not existing[1] and row[1]:
                    unique[unique.index(existing)] = row
                    seen[key] = row
                continue
            seen[key] = row
            unique.append(row)

    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(unique)

    return dupes, len(unique)


def clean_edges(path):
    with open(path, encoding="utf-8-sig") as f:
        lines = [l.rstrip("\n") for l in f if l.strip()]

    seen = set()
    unique = []
    dupes = 0
    for line in lines:
        key = line.strip()
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        unique.append(line)

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(unique) + "\n")

    return dupes, len(unique)


def main():
    print(f"Backing up originals...")
    backup(NODES_FILE)
    backup(EDGES_FILE)
    print()

    n_dupes, n_kept = clean_nodes(NODES_FILE)
    print(f"Nodes: removed {n_dupes} duplicate rows, kept {n_kept} unique")

    e_dupes, e_kept = clean_edges(EDGES_FILE)
    print(f"Edges: removed {e_dupes} exact duplicate lines, kept {e_kept} unique")


if __name__ == "__main__":
    main()