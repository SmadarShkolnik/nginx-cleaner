# Document what "working correctly" means + test coverage in the README

- Created by: Claude Code session d24c8a9b-b6c6-4b83-9aa5-57f46a3cb866
- Date & time: 2026-10-17 (IDT)
- Trigger: "Document what 'working correctly' means and what your test covers — in the README".

## Decisions you made

- In the README, explicitly document (a) the definition of "working correctly" / equivalence, and (b) what the compatibility test actually covers.

## Decisions I inferred

- Replace the single dense "Request/response" bullet with two clear parts under the Compatibility section:
  1. **What "working correctly" means** — the equivalence contract (same status line, headers, byte-identical body; plus image config, `nginx -V`/`-t`, user, filesystem layout/perms/md5s, entrypoint output) and exactly what is excluded and why (`Date`; packaged-file `ETag`/`Last-Modified`), drawn from `test/test_compat.py`.
  2. **What the test covers** — a grouped list (metadata/filesystem, default site, robustness, custom config, entrypoint, modules, TLS, negative control) with the 58-checks / ~15 s figure.
- Keep the other coverage bullets (package-set diff, nginx-tests, official-images, the one intended difference) as a short "Beyond request/response" list.
- Keep all facts/counts; don't change other sections. This intentionally re-expands what the earlier pass compressed, because documenting it is the explicit ask.
