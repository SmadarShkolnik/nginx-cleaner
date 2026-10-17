# Shorten README: Build, Compatibility, Residual risk

- Created by: Claude Code session d24c8a9b-b6c6-4b83-9aa5-57f46a3cb866
- Date & time: 2026-10-17 (IDT)
- Trigger: "make the Build part in the README shorter, also the Compatibility and Residual risk".

## Decisions you made

- Shorten three README sections: **Build**, **Compatibility**, and **Residual risk**. Nothing else changes.

## Decisions I inferred

- "Shorter" = trim verbose prose, keep every fact, table, link and test name that carries information. No facts/numbers changed.
- **Build:** condense the three paragraphs (pinning, diagnostics) into tight lines; keep the `make` block and both tables.
- **Compatibility:** keep the two upstream-source tables (they are the substance) but compress their "why it matters" wording and the intro; collapse the "Request/response equivalence" and "Beyond request/response" prose into shorter bullets; keep all test names, links, and the Architecture line.
- **Residual risk:** keep the 9-row table intact; compress the two lead paragraphs into one shorter prioritised paragraph that still states reachability + the library-vs-function point.
- Leave CVEs fixed / Proof / Rescan / Honest baseline / What I'd do next / Personal Summary untouched.
