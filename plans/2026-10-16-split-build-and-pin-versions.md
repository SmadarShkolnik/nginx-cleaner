# Split OpenSSL/nginx build steps + pin our package versions

- Created by: Claude Code session d24c8a9b-b6c6-4b83-9aa5-57f46a3cb866
- Date & time: 2026-10-16

## Decisions you made

- Two improvements requested:
  1. Split the single `RUN /src/build.sh` into two cached steps — build OpenSSL first (after copying versions.env), then copy patches and build nginx — so an nginx patch change no longer rebuilds OpenSSL. Adjust `build.sh` so each function can run on its own (e.g. via an argument), keeping the full-log + tail-on-failure behaviour for both steps.
  2. Add a test asserting the final image has exactly our `+echo1` versions of libssl3, openssl and nginx (dpkg-query), and protect against a future Debian `3.0.22-1~deb12u2` replacing/rejecting our packages.
- You approved the plan.
- Q: Which protection mechanism — A (apt-mark hold, recommended), B (apt pinning), or C (version/epoch scheme)?
  A: **A** (apt-mark hold).

## Decisions I inferred

- The build Dockerfile is `build/Dockerfile` (renamed from `Dockerfile.build` earlier this session); edits apply there.
- `build.sh` gains a `case "${1:-all}"` dispatcher: `openssl`, `nginx`, or `all` (default). Shared setup (env, `fetch`, versions.env) runs for either step.
- Dockerfile: `COPY build.sh versions.env` → `RUN build.sh openssl` (logs `/build-openssl.log`) → `COPY patches` → `RUN build.sh nginx` (logs `/build-nginx.log`). Each keeps tail-on-failure. OpenSSL's debs and its install into the builder root persist across layers, so the nginx step still links against our OpenSSL.
- `apt-mark hold` is applied in `Containerfile` as its own `RUN` (so it can carry an explanatory comment; Dockerfile comments aren't allowed mid-`RUN` chain). Held packages: `nginx libssl3 openssl` (the three requested; nginx modules track the held nginx version and Debian ships no competing module packages).
- New `test/test_versions.py` reads `OPENSSL_DEB_VERSION`, `NGINX_VERSION`, `ECHO_SUFFIX` from `build/versions.env`, so it tracks future bumps instead of hardcoding. Expected: libssl3/openssl = `3.0.22-1~deb12u1+echo1`, nginx = `1.25.5-1+echo1~bookworm`; also asserts each contains `+echo1`.
- The stray `ENTRYPOINT/CMD` lines in the export stage are left as-is (out of scope).

## Verification still pending (Docker Desktop is down with input/output errors)

- Cannot yet rebuild to confirm the cache actually splits, nor run `test_versions.py` against the image. Edits are made now; these runs happen once Docker is healthy.
