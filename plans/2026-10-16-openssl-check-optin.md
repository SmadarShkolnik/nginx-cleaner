# Opt-in OpenSSL test suite (OPENSSL_CHECK)

- Created by: Claude Code session d24c8a9b-b6c6-4b83-9aa5-57f46a3cb866
- Date & time: 2026-10-16

## Decisions you made

- `build/build.sh` builds OpenSSL with `DEB_BUILD_OPTIONS=nocheck`, so OpenSSL's own test suite never runs.
- Add an opt-in way to run it, e.g. an `OPENSSL_CHECK=1` variable passed through the Makefile and the build Dockerfile as a build arg.
- Keep `nocheck` as the default so normal builds stay fast.
- Run it once to confirm the tests pass.
- Report how long the build took with and without it.
- Add a note to the README's residual-risk section.

## Decisions I inferred

- Plumbing: Makefile var `OPENSSL_CHECK ?= 0` → `docker build --build-arg OPENSSL_CHECK=$(OPENSSL_CHECK)` → `ARG OPENSSL_CHECK` in `build/Dockerfile` → passed as an env var into the `build.sh` RUN → `build.sh` includes `nocheck` only when `OPENSSL_CHECK != 1`.
- Only the OpenSSL package gets the test suite. nginx stays `nocheck` (not in scope).
- Timing is measured as cold builds (`--no-cache`) of the `builder` stage both ways, so the only real difference is the test suite; apt/download overhead is paid by both. Reported as wall-clock from `date`.
- Proof the suite ran and passed: the `OPENSSL_CHECK=1` build succeeds (with `set -e`, a failed test aborts the build), and `/build.log` in the builder image contains OpenSSL's harness output ("Result: PASS" / "All tests successful").
- The stale ENTRYPOINT/CMD lines and the `Dockerfile.build` comment already in `build/Dockerfile` are left as-is (out of scope; `--output type=local` ignores them).
