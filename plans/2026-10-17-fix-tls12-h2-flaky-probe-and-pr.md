# Fix flaky TLS 1.2 + h2 probe, run diagnostics, open PR

- Created by: Claude Code session fcd7a5f0-d491-47dd-9791-d0cc92213a52
- Date & time: 2026-10-17 15:56 IDT
- Trigger: after recovering Docker from the disk-full corruption, "run the project build and tests", "make sure you test it all", then commit + push to a new branch and open a PR.

## Decisions you made

- Run the project build and tests (`make all`).
- Of the opt-in targets added since yesterday, run **only `make nginx-tests` and `make asan`** (answer to "include scan targets too, or just nginx-tests and asan?" → "just nginx-tests and asan").
- "Make sure you test it all."
- When finished: **create a new branch, push to it, and create a pull request**; you merge it manually on GitHub (not a direct push to `main`).

## Decisions I inferred

- `make all` result: 81 passed, 5 skipped (remote pin check, needs `ENTRYPOINT_VERIFY_REMOTE=1`), **1 failed: `test_compat.py::test_tls[tls12-h2]`**.
- Root cause (verified): with `-alpn h2`, nginx sends binary HTTP/2 frames after the handshake; when they reach `grep` it prints `binary file matches` instead of the matching lines, so the probe output is empty. Timing-dependent, reproduced on **both** the original and the rebuilt image — a test bug, not an image regression. Passes when other TLS tests warm up first; fails when `tls12-h2` runs first or alone.
- Fix: `grep -E` → `grep -aE` in `tls_probe()` (`test/test_compat.py`). Verified manually: 10/10 handshakes report `TLSv1.2` + `ALPN protocol: h2` on each image with `-a`.
- Skip `make scan`, `make vex`, `make scan-apt-baseline` (not chosen; would re-download ~6 GB of scanner DBs and overwrite `scan-result/fixed/`), and amd64 (QEMU, left to CI).
- `gh` CLI is not installed: push the branch and give a GitHub "compare" link to create the PR in the browser.
- Branch name: `review-hardening-and-diagnostics`. Commit includes all current uncommitted work (yesterday's/today's sessions) plus this fix and any diagnostic output that `nginx-tests` / `asan` produce under `scan-result/`.
- If `nginx-tests` or `asan` fail (both scripts note they were never run with Docker), report before committing rather than silently fixing.
- `make nginx-tests` result: identical on both images (8/11 files pass; `proxy.t` 3 subtests, `rewrite.t` 1, `rewrite_if.t` 8 fail on the original too — the pinned nginx-tests commit expects newer nginx behaviour). `alias*.t` and `js.t` match no file at the pinned commit, so they did not run.
- `make asan` first run failed before building: `build/asan.sh: line 54: label: unbound variable` — `local label=… log="…${label}…"` expands `$label` before it is assigned. Fix: split into two `local` lines.
- `make asan` second run: patched build OK (no ASan error, `[alert] "alias" cannot be used…`), but the unpatched build reported **`AddressSanitizer: negative-size-param (size=-3)`** in `memcpy` from `ngx_http_map_uri_to_path()` (`ngx_http_core_module.c:1942`), not a `heap-buffer-overflow`; the script only grepped for the latter, so the verdict was a false "CHECK". Why −3: the rewritten URI `/x` (2 bytes) is shorter than the location prefix `/foo/` (5 bytes). Fix: the check now accepts any `ERROR: AddressSanitizer` whose stack includes `ngx_http_map_uri_to_path`, and the patched build must have no ASan error; comments in `build/asan.sh` and the `asan` target in `Makefile` updated to match.
- `make asan` third run: **PASS** — ASan error in `ngx_http_map_uri_to_path()` only in the unpatched build.
- `plans/my-plan.md` has local changes but CLAUDE.md says to ignore it, so it is left out of the commit.
