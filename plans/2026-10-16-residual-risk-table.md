# Rework the README "Residual risk" section into a uniform table

- Created by: Claude Code session d24c8a9b-b6c6-4b83-9aa5-57f46a3cb866
- Date & time: 2026-10-16

## Decisions you made

- Revise "Residual risk" so every item follows the same structure: what is still there, why it was left, what I would do next.
- Start the section with a one-paragraph prioritised assessment of which remaining risks matter most, based on whether the vulnerable code is reachable by nginx in the default configuration.
- Fill gaps: add a "Next" for the arm64-only item and the low-reachability item.
- Add build-process risks: OpenSSL built with nocheck; apt build-deps not pinned (not fully reproducible); our +echo1 versions sort below a future Debian 3.0.22-1~deb12u2 (newer base/apt upgrade could replace them); CVE-2026-15176 still shows in scanners unless the VEX travels with the image.
- Keep it concise and factual, don't overstate, don't change other sections.
- Do it in a table. Show the diff before saving.
- You reviewed the diff and approved ("yes change").

## Decisions I inferred

- Table columns: Risk / Still there / Why left / Next.
- Where mitigations already exist this session I state them factually without overstating: apt-mark hold for the version-sort risk, and OPENSSL_CHECK=1 for the nocheck risk.
- Only the Residual risk section is replaced; all other sections untouched.
