# Surface my-plan.md in the README and shorten it

- Created by: Claude Code session d24c8a9b-b6c6-4b83-9aa5-57f46a3cb866
- Date & time: 2026-10-16

## Decisions you made

- Change the README to show more of `plans/my-plan.md` (the research diary).
- Make the README shorter.

## Decisions I inferred

- Add a prominent **Approach (research diary)** section right after the intro that surfaces `plans/my-plan.md`: the triage funnel, the filter choices (runtime path = nginx binary, severity, fix type, EPSS ≥ 90th), and links to the diary, its two screenshots, and the triage page.
- Shorten the README from 165 lines to roughly half by condensing the verbose prose (Residual risk, Compatibility test table, Surprises, How-AI-was-used) into tight bullets, while keeping every table and link that carries real information (CVEs fixed, build table, backport proof, rescan).
- Remove the now-duplicated "why these CVEs were chosen" prose, since the Approach section covers it.
- Fix stale `Dockerfile.build` references to `build/Dockerfile` (renamed this session) while rewriting.
- No facts/numbers are changed; only trimmed and reorganized.
