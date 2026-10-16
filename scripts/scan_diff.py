#!/usr/bin/env python3
"""Diff Trivy/Grype table reports of the baseline and the rebuilt image.

usage: scan_diff.py <baseline-dir> <fixed-dir> [CVE ...]
Reads baseline-{trivy,grype}.txt and {trivy,grype}.txt (+ grype-vex.txt if present)
and prints a Markdown summary. The CVEs given on the command line get a
per-report status table.
"""
import os
import re
import sys


def parse_grype(path):
    lines = open(path).read().splitlines()
    hdr = lines[0]
    cols = ["NAME", "INSTALLED", "FIXED IN", "TYPE", "VULNERABILITY", "SEVERITY"]
    pos = [hdr.index(c) for c in cols] + [hdr.index("EPSS") if "EPSS" in hdr else 10**6]
    rows = set()
    for l in lines[1:]:
        if l.strip():
            f = [l[pos[i]:pos[i + 1]].strip() for i in range(len(cols))]
            rows.add((f[0], f[4]))
    return rows


def parse_trivy(path):
    """Trivy's box table; merged cells mean 'same as above'."""
    rows, lib = set(), None
    for l in open(path).read().splitlines():
        if not l.startswith("│") or "─" in l:
            continue
        cells = [c.strip() for c in l.split("│")[1:-1]]
        if len(cells) != 7:
            continue
        if cells[0]:
            lib = cells[0]
        if cells[1] and re.match(r"^(CVE|TEMP|GHSA|DLA|DSA)-", cells[1]):
            rows.add((lib, cells[1]))
    return rows


def summarize(name, before, after):
    ids_b, ids_a = {v for _, v in before}, {v for _, v in after}
    out = [f"### {name}", "",
           "| | findings (pkg × ID) | unique IDs |", "|---|---:|---:|",
           f"| baseline | {len(before)} | {len(ids_b)} |",
           f"| rebuilt | {len(after)} | {len(ids_a)} |",
           f"| removed | {len(before - after)} | {len(ids_b - ids_a)} |",
           f"| added | {len(after - before)} | {len(ids_a - ids_b)} |", ""]
    return out


def main():
    base, fixed, cves = sys.argv[1], sys.argv[2], sys.argv[3:]
    reports = [
        ("Trivy", parse_trivy, os.path.join(base, "baseline-trivy.txt"), os.path.join(fixed, "trivy.txt")),
        ("Grype", parse_grype, os.path.join(base, "baseline-grype.txt"), os.path.join(fixed, "grype.txt")),
    ]
    vex = os.path.join(fixed, "grype-vex.txt")
    out = ["# Scan diff: nginx:1.25-bookworm vs rebuilt image", ""]
    status = {c: [] for c in cves}
    columns = []
    for name, parse, b, a in reports:
        before, after = parse(b), parse(a)
        out += summarize(name, before, after)
        for label, rows in ((f"{name} baseline", before), (f"{name} rebuilt", after)):
            columns.append(label)
            for c in cves:
                pk = sorted(p for p, v in rows if v == c)
                status[c].append(", ".join(pk) if pk else "—")
    if os.path.exists(vex):
        rows = parse_grype(vex)
        columns.append("Grype rebuilt + VEX")
        for c in cves:
            pk = sorted(p for p, v in rows if v == c)
            status[c].append(", ".join(pk) if pk else "—")
    if cves:
        out += ["### Target CVEs (package where reported, — = not reported)", "",
                "| CVE | " + " | ".join(columns) + " |",
                "|---|" + "---|" * len(columns)]
        out += [f"| {c} | " + " | ".join(status[c]) + " |" for c in cves]
    print("\n".join(out))


if __name__ == "__main__":
    main()
