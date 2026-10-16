# Implementation: build, patch and ship nginx:1.25-bookworm with the chosen CVEs

- Created by: Claude Code session 7bfebbd4-9648-4c80-a913-1f7427f407a3
- Date & time: 2026-10-16 15:25 IDT
- Instructions source: `Software Engineer - Build It, Patch It, Ship It.pdf`
- Full plan: `~/.claude/plans/snug-dazzling-duckling.md` (approved in this session)

## Decisions you made

- Use the CVEs you chose in `plans/my-plan.md`: one to fix by backport and one by version bump, filtered with the triage page. Screenshots are in `images/`.
- You approved the implementation plan.
- Questions I asked and your answers:
  - Q: "my-plan.md says 'I choose 1 from each category' but doesn't name them. Which backport CVE?" A: **CVE-2026-15176** (Recommended).
  - Q: "Which OpenSSL CVE is your bump pick? One OpenSSL rebuild fixes both, so you can count both." A: **Count both** (Recommended). That means CVE-2025-15467 and CVE-2024-5535.
  - Q: "How should the OpenSSL bump be built? Both fixes already exist in Debian's newer libssl3, so a plain current bookworm-slim base would fix them 'for free'. The bump only counts if you compile it yourself." A: **Upstream tarball** (Recommended). This means the upstream openssl-3.0.x tarball with Debian's `debian/` packaging, a new version set with `dch`, and `dpkg-buildpackage`.

## Decisions I inferred

- **CVE-2026-93479 is not backported.** nginx.org lists it as affecting only 1.30.0–1.30.5 and 1.31.2–1.31.6, so Grype's match on 1.25.5 is a false positive. It may be added to the VEX file as `not_affected`, as an extra.
- **Backport source.** The patch is upstream nginx commit `ce1da78` ("Avoid post-rewrite URI to path mapping with alias"), a one-line change in `ngx_http_map_uri_to_path()`. It is stored as `build/patches/nginx/CVE-2026-15176.patch`.
- **OpenSSL target.** The target is upstream **3.0.22**, the latest 3.0.x tag. The Debian packaging comes from bookworm-security `openssl 3.0.22-1~deb12u1`, and the package version is `3.0.22-1~deb12u1+echo1`. Both `libssl3` and the `openssl` CLI are shipped from that build.
- **nginx packaging.** nginx and its four modules are built with nginx.org's own `pkg-oss` at tag `1.25.5-1`, which keeps `nginx -V` identical. The release is `1~bookworm+echo1`.
- **Base and tag.** The final image is built `FROM debian:bookworm-slim` (current) and tagged `echo/nginx:1.25-bookworm`.
- **Tests and scans.**
  - The test is written in Python with pytest, because Go isn't installed here.
  - Rescan output goes to `scan-result/fixed/`.
  - The VEX demo uses `grype --vex`, because Trivy doesn't list nginx CVEs.
- **The test suite adds two cases beyond plain compatibility:**
  - a TLS scenario, to exercise the bumped OpenSSL
  - a separate CVE-2026-15176 regression test using upstream's reproducer config
- `plans/my-plan.md` is not changed.
