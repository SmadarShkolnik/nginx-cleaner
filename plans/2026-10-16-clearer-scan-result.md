# Make the scan result more informative and clear

- Created by: Claude Code session d24c8a9b-b6c6-4b83-9aa5-57f46a3cb866
- Date & time: 2026-10-16

## Decisions you made

- Change the scan result to be more informative and clear.

## Decisions I inferred

- "Scan result" = `scan-result/fixed/diff.md`, produced by `scripts/scan_diff.py` (run by `make scan` / `make vex`). I improve the generator and regenerate the file.
- I did not ask a clarifying question; I made the changes that match the questions you already raised in this project (severity, how so many were removed, which target CVEs are actually fixed). Say the word if you want a different emphasis.
- Improvements, all computed from the existing saved scans (no Docker needed):
  1. A one-line **headline**: High+Critical before → after, total removed, and "0 added" called out as "no regressions".
  2. The per-scanner table keeps baseline/rebuilt/removed/added, now with a **severity split** (Critical/High/Medium/Low/other) for what remains and what was removed.
  3. A **"what drove the removals"** table: top packages by findings removed (answers "how did it remove so many").
  4. The target-CVE table gains a **Verdict** column: "No longer reported", "Cleared by VEX", or "Still reported", derived only from the scan data.
- Severity is normalized across scanners (Trivy UPPER vs Grype Capitalized) to Title case. Diffing of removed/added stays keyed on (package, CVE); severity is attached for the breakdown only.
- The baseline/rebuilt counts must not change (same inputs); only the presentation is richer.
