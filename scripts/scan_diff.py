#!/usr/bin/env python3
"""Diff Trivy/Grype table reports of the baseline and the rebuilt image.

usage: scan_diff.py <baseline-dir> <fixed-dir> [CVE ...]
Reads baseline-{trivy,grype}.txt and {trivy,grype}.txt (+ grype-vex.txt if present)
and prints a Markdown summary: a headline, a per-scanner table broken down by
severity, the packages that drove the removals, and a per-CVE verdict for the
CVEs given on the command line.
"""
import os
import re
import sys
from collections import Counter

# Severity buckets, most to least serious. Anything else (Negligible, Unknown,
# blank) folds into "other".
SEV_ORDER = ["Critical", "High", "Medium", "Low"]


def norm_sev(s):
    s = (s or "").strip().title()
    return s if s in SEV_ORDER else "other"


def parse_grype(path):
    lines = open(path).read().splitlines()
    hdr = lines[0]
    cols = ["NAME", "INSTALLED", "FIXED IN", "TYPE", "VULNERABILITY", "SEVERITY"]
    pos = [hdr.index(c) for c in cols] + [hdr.index("EPSS") if "EPSS" in hdr else 10**6]
    rows = set()
    for l in lines[1:]:
        if l.strip():
            f = [l[pos[i]:pos[i + 1]].strip() for i in range(len(cols))]
            rows.add((f[0], f[4], norm_sev(f[5])))
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
            rows.add((lib, cells[1], norm_sev(cells[2])))
    return rows


def keymap(rows):
    """{(package, id): severity} — the identity of a finding is (package, id)."""
    return {(p, i): s for p, i, s in rows}


def sev_cells(keys, sev_of):
    """Markdown cells counting `keys` per severity bucket, using `sev_of`."""
    c = Counter(sev_of.get(k, "other") for k in keys)
    counts = [c.get(s, 0) for s in SEV_ORDER] + [c.get("other", 0)]
    return " | ".join(str(n) for n in counts)


def summarize(name, before, after):
    kb, ka = keymap(before), keymap(after)
    bset, aset = set(kb), set(ka)
    removed, added = bset - aset, aset - bset
    ids = lambda ks: {i for _, i in ks}
    head = ("| state | findings | unique IDs | "
            + " | ".join(SEV_ORDER) + " | other |")
    rule = "|---|---:|---:|" + "---:|" * (len(SEV_ORDER) + 1)
    rows = [
        (f"baseline", bset, kb), ("rebuilt", aset, ka),
        ("removed", removed, kb), ("added", added, ka),
    ]
    out = [f"### {name}", "", head, rule]
    for label, ks, sev_of in rows:
        out.append(f"| {label} | {len(ks)} | {len(ids(ks))} | {sev_cells(ks, sev_of)} |")
    out.append("")
    return out


def top_removed_packages(before, after, limit=8):
    removed = set(keymap(before)) - set(keymap(after))
    c = Counter(p for p, _ in removed)
    if not c:
        return []
    out = ["**What drove the removals (top packages, Grype):**", "",
           "| package | findings removed |", "|---|---:|"]
    out += [f"| {p} | {n} |" for p, n in c.most_common(limit)]
    out.append("")
    return out


def hi_crit(rows):
    return sum(1 for _, _, s in rows if s in ("Critical", "High"))


def main():
    base, fixed, cves = sys.argv[1], sys.argv[2], sys.argv[3:]
    reports = [
        ("Trivy", parse_trivy, os.path.join(base, "baseline-trivy.txt"), os.path.join(fixed, "trivy.txt")),
        ("Grype", parse_grype, os.path.join(base, "baseline-grype.txt"), os.path.join(fixed, "grype.txt")),
    ]
    vex_path = os.path.join(fixed, "grype-vex.txt")

    parsed = {}
    for name, parse, b, a in reports:
        parsed[name] = (parse(b), parse(a))

    # --- headline (per scanner; the two scanners overlap, so don't sum them) ---
    bits = []
    for name in ("Trivy", "Grype"):
        before, after = parsed[name]
        removed = len(set(keymap(before)) - set(keymap(after)))
        bits.append(f"{name} High+Critical {hi_crit(before)}→{hi_crit(after)} "
                    f"({removed} findings removed)")
    total_added = sum(len(set(keymap(a)) - set(keymap(b))) for b, a in parsed.values())
    added_note = "**0 added (no regressions)**" if total_added == 0 else f"**{total_added} ADDED**"

    out = ["# Scan diff: nginx:1.25-bookworm vs rebuilt image", "",
           f"**Result:** {'; '.join(bits)}. {added_note}.",
           "",
           "_A finding is one package x CVE pair; the same CVE in several packages "
           "counts once per package. Severity columns count findings._", ""]

    # --- per-scanner tables + removal drivers ---
    for name, parse, b, a in reports:
        before, after = parsed[name]
        out += summarize(name, before, after)
    out += top_removed_packages(*parsed["Grype"])

    # --- target CVEs ---
    if cves:
        vex_rows = parse_grype(vex_path) if os.path.exists(vex_path) else None
        present = {
            "Trivy baseline": {i for _, i, _ in parsed["Trivy"][0]},
            "Trivy rebuilt": {i for _, i, _ in parsed["Trivy"][1]},
            "Grype baseline": {i for _, i, _ in parsed["Grype"][0]},
            "Grype rebuilt": {i for _, i, _ in parsed["Grype"][1]},
        }
        pkg_of = {
            "Trivy baseline": parsed["Trivy"][0], "Trivy rebuilt": parsed["Trivy"][1],
            "Grype baseline": parsed["Grype"][0], "Grype rebuilt": parsed["Grype"][1],
        }
        columns = ["Trivy baseline", "Trivy rebuilt", "Grype baseline", "Grype rebuilt"]
        if vex_rows is not None:
            columns.append("Grype rebuilt + VEX")
            present["Grype rebuilt + VEX"] = {i for _, i, _ in vex_rows}
            pkg_of["Grype rebuilt + VEX"] = vex_rows

        def verdict(c):
            still = c in present["Trivy rebuilt"] or c in present["Grype rebuilt"]
            if not still:
                return "No longer reported"
            if vex_rows is not None and c not in present["Grype rebuilt + VEX"]:
                return "Cleared by VEX"
            return "Still reported"

        out += ["### Target CVEs", "",
                "Package(s) where each CVE is reported (`—` = not reported); "
                "verdict is derived only from these scans.", "",
                "| CVE | " + " | ".join(columns) + " | Verdict |",
                "|---|" + "---|" * (len(columns) + 1)]
        for c in cves:
            cells = []
            for col in columns:
                pk = sorted(p for p, i, _ in pkg_of[col] if i == c)
                cells.append(", ".join(pk) if pk else "—")
            out.append(f"| {c} | " + " | ".join(cells) + f" | {verdict(c)} |")
        out.append("")

    print("\n".join(out))


if __name__ == "__main__":
    main()
