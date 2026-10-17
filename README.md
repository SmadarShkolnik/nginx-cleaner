# Clean nginx:1.25-bookworm

A drop-in replacement for `nginx:1.25-bookworm`. Every package that matters is compiled here from upstream source on a clean `debian:bookworm-slim`. It eliminates three CVEs: one by **backporting** an upstream nginx fix onto 1.25.5, and two by a **version bump** of OpenSSL. An automated test compares the new image against the original.

## Approach (research diary)

The full diary is `[plans/my-plan.md](plans/my-plan.md)`

1. Scanned the original image with Grype and Trivy, then merged both into an interactive triage page (`[scan-result/start/nginx-cve-triage.html](scan-result/start/nginx-cve-triage.html)`).
2. Filtered to what is worth fixing: **runtime path = "nginx binary"** (only nginx and the libraries it links to are reachable by traffic), **severity**, **fix type** (backport vs. version bump), and **EPSS ≥ 90th percentile** for bumps.
3. Picked one CVE from each category. The funnel:

  |              | path                  | funnel                                                  | chosen                                                                                            |
  | ------------ | --------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
  | **Backport** | 534 → 99 nginx-binary | → 38 High → 3 backport candidates                       | CVE-2026-15176 ([screenshot](doc-pictures/backport-cves-after-filtering.png))                     |
  | **Bump**     | 534 → 99 nginx-binary | → 7 Critical → 5 newer-Debian-source → 2 at EPSS ≥ 90th | CVE-2025-15467, CVE-2024-5535 ([screenshot](doc-pictures/bump-critical-cves-after-filtering.png)) |




## Build

Needs Docker with BuildKit, plus `python3`/`pytest`, `trivy` and `grype`.

```sh
make all     # = make deb image test
make deb     # build/Dockerfile: compile the .debs from source  -> out/debs/
make image   # Containerfile: install the .debs                 -> echo/nginx:1.25-bookworm
make test    # test/: compatibility + CVE regression tests (non-zero exit on mismatch)
make scan    # Trivy + Grype on the new image -> scan-result/fixed/, diff vs scan-result/start/
make vex     # Grype with vex/nginx.openvex.json applied
make sizes   # original vs new image size
```

~4 min on an 8-core arm64 Docker VM. Everything is pinned in `[build/versions.env](build/versions.env)` — the `debian:bookworm-slim` base by digest, every download by SHA-256/512. `OPENSSL_CHECK=1 make deb` also runs OpenSSL's test suite (off by default). Opt-in diagnostics (not in `make all`): `make asan`, `make nginx-tests`, `make scan-apt-baseline`.

### What gets built (`[build/build.sh](build/build.sh)`)


| Package(s)                                            | Source                                                                                                                                                                                                                | Version shipped           |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| `libssl3`, `openssl` (+ `libssl-dev` for the build)   | upstream `openssl-3.0.22.tar.gz`, built with Debian's bookworm-security `debian/` packaging                                                                                                                           | `3.0.22-1~deb12u1+echo1`  |
| `nginx`, `nginx-module-{njs,xslt,geoip,image-filter}` | `nginx-1.25.5.tar.gz` + njs 0.8.4 via nginx.org's [pkg-oss](https://github.com/nginx/pkg-oss) @ `14d7f18` (the commit behind the upstream image) + `[CVE-2026-15176.patch](build/patches/nginx/CVE-2026-15176.patch)` | `1.25.5-1+echo1~bookworm` |


OpenSSL is built first so nginx links against it; nginx builds under nginx.org's path (`/data/builder/debuild/nginx-1.25.5`) so `nginx -V` stays identical, and `build.sh` checks the patch is in each package's quilt `series`.

### The image (`[Containerfile](Containerfile)`)

A copy of docker-nginx's `mainline/debian/Dockerfile` @ `9abe4ae`: same base, `nginx` uid/gid 101, package set, `ENV`, label, entrypoint scripts, ports, `STOPSIGNAL`, `CMD`. Only difference: packages come from `out/debs`, and our `+echo1` ones are `apt-mark hold`ed.
Image size **66.7 MB** vs **67.7 MB** (`make sizes`).

## CVEs fixed


| CVE                      | Severity                          | Component                                    | Method                                                                                                                     | Evidence                                                                                                                                                    |
| ------------------------ | --------------------------------- | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **CVE-2026-15176**       | High (Grype) / Medium (nginx.org) | `nginx` 1.25.5, `ngx_http_map_uri_to_path()` | **Backport** of upstream `[ce1da78](https://github.com/nginx/nginx/commit/ce1da78)` (fixed upstream in 1.30.6 / 1.31.7)    | [patch](build/patches/nginx/CVE-2026-15176.patch) · [test](test/test_cve_2026_15176.py) · [VEX](vex/nginx.openvex.json) · [diff](scan-result/fixed/diff.md) |
| **CVE-2025-15467**       | Critical (Grype) / High (Trivy)   | `libssl3`, `openssl` 3.0.11                  | **Version bump** to OpenSSL 3.0.22                                                                                         | [versions.env](build/versions.env) · [diff](scan-result/fixed/diff.md)                                                                                      |
| **CVE-2024-5535**        | Critical (Grype) / Low (Trivy)    | `libssl3`, `openssl` 3.0.11                  | **Version bump** (same build)                                                                                              | [diff](scan-result/fixed/diff.md)                                                                                                                           |
| CVE-2026-93479 *(extra)* | High (Grype)                      | `nginx`                                      | **VEX** `not_affected`: nginx.org lists only 1.30.0–1.30.5 / 1.31.2–1.31.6, so Grype's match on 1.25.5 is a false positive | [VEX](vex/nginx.openvex.json)                                                                                                                               |




### Proof the backport works

`[test/test_cve_2026_15176.py](test/test_cve_2026_15176.py)` loads upstream's reproducer (`location /foo/ { alias …; rewrite ^/foo/.*$ /x; return 200 $request_filename; }`) and sends `GET /foo/1`:


| Image    | Response                                                                                                                             | Error log                                                                    |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| original | `200`, 19 bytes: `\x00` × 16 + `/x` — the path buffer is sized for the rewritten URI and the copy runs past it, returning heap bytes | nothing                                                                      |
| rebuilt  | `200`, empty body; workers keep running                                                                                              | `[alert] "alias" cannot be used in location "/foo/" where URI was rewritten` |


The test asserts both directions. On the original it checks the *leak signature*, not just a non-empty body: every `/foo/1` response must end with the rewrite marker `/x` **and** carry non-printable bytes in front of it — a correctly mapped filesystem path is printable, and the patched build returns an empty body, so neither can satisfy it. On the rebuilt image it requires the empty body + the alert. `make asan` adds the memory-safety view (the overflow itself).

### Rescan (`[scan-result/fixed/](scan-result/fixed/)`, `[diff.md](scan-result/fixed/diff.md)`)


|                                                                   | Trivy | Grype |
| ----------------------------------------------------------------- | ----- | ----- |
| baseline                                                          | 825   | 796   |
| rebuilt                                                           | 480   | 459   |
| removed by the OpenSSL bump (42 CVEs × 2 pkgs)                    | 84    | 84    |
| removed by the newer `bookworm-slim` base (Debian point releases) | 261   | 253   |
| added                                                             | 0     | 0     |


The backport is invisible to scanners (nginx stays `1.25.5`), so Grype keeps flagging CVE-2026-15176. `[vex/nginx.openvex.json](vex/nginx.openvex.json)` marks it `fixed` for our exact `+echo1` build, and `grype --vex` then drops it (last column of `diff.md`). Trivy never reports nginx CVEs (the nginx.org package isn't in its Debian DB), so the VEX demo uses Grype.

The VEX product `@id` is the human-readable tag `echo/nginx:1.25-bookworm`; what actually pins the fix is the `pkg:deb/.../nginx@1.25.5-1%2Becho1~bookworm` subcomponent purl. The image digest changes every build and is only known after it, so it can't be hard-coded here — for distribution the VEX should ship as an **OCI attestation** (e.g. `cosign attest --type openvex`), which binds the statement to the pushed image digest at publish time so the document travels with the image instead of alongside it.

#### Honest baseline: vs a plain `apt upgrade`

`make scan-apt-baseline` rebuilds `nginx:1.25-bookworm` with `apt-get update && apt-get upgrade -y`, scans it, and diffs **that** against our image (`scan-result/fixed/diff-vs-apt-upgrade.md`) to show only what we remove beyond what a user gets for free. The honest expectation, from Debian's security tracker: bookworm-security already ships `openssl 3.0.22-1~deb12u1` (the exact Debian source our bump reuses), so **a plain apt upgrade clears the same OpenSSL CVEs** — our version bump adds provenance (built from the upstream tarball) and the `apt-mark hold` pin, not extra CVE coverage. What apt upgrade does **not** give: the CVE-2026-15176 backport (no fixed nginx package exists at 1.25.5), and it would also drift nginx to nginx.org's newer mainline. The exact per-CVE delta is produced by the target above (pending a healthy Docker; not yet run this pass).

## Compatibility: what was copied from upstream, and what tests it

The original image comes from two upstream sources, copied from the exact commits that built nginx 1.25.5. Each behaviour-defining part has a test that fails when it differs (full audit: `[plans/2026-10-17-upstream-fidelity-audit-and-amd64.md](plans/2026-10-17-upstream-fidelity-audit-and-amd64.md)`).

### 1. Image assembly — `[docker-nginx](https://github.com/nginxinc/docker-nginx)` @ `9abe4ae`


| Copied                                                                                                  | Where           | Test                                                              |
| ------------------------------------------------------------------------------------------------------- | --------------- | ----------------------------------------------------------------- |
| `ENTRYPOINT`, `CMD`, `EXPOSE`, `STOPSIGNAL`, `ENV`, `LABEL` (no `USER`/`WORKDIR`/`VOLUME`, as upstream) | `Containerfile` | `test_compat.py::test_image_config_matches`                       |
| `nginx` user, uid/gid 101, home `/nonexistent`, shell `/bin/false`                                      | `Containerfile` | `test_compat.py::test_user_matches`                               |
| Exact package set (`curl`, `gettext-base`, `ca-certificates`, 4 `nginx-module-*`), nothing extra        | `Containerfile` | `test_packages.py` (dpkg-query diff)                              |
| Entrypoint scripts, byte-identical + `0755`                                                             | `rootfs/`       | `test_entrypoint.py` (sha256) + `test_filesystem_matches` (perms) |
| Log symlinks to `/dev/stdout`,`/dev/stderr`; `/docker-entrypoint.d`                                     | `Containerfile` | `test_compat.py::test_filesystem_matches`                         |




### 2. nginx build — `[pkg-oss](https://github.com/nginx/pkg-oss)` @ `14d7f18`


| Copied                                                                             | Where                | Test                                                          |
| ---------------------------------------------------------------------------------- | -------------------- | ------------------------------------------------------------- |
| nginx 1.25.5, njs 0.8.4 **release 3** (the commit, not the tag)                    | `build/versions.env` | `test_versions.py`                                            |
| `configure` flags + build path `/data/builder/debuild` (keep `nginx -V` identical) | `build/build.sh`     | `test_compat.py::test_build_flags_match`                      |
| Default config and HTML, file layout/perms                                         | nginx `.deb`         | `test_compat.py::test_filesystem_matches` (md5 + layout)      |
| Dynamic modules (njs, xslt, geoip, image-filter — 6 `.so`)                         | `build/build.sh`     | `test_compat.py::test_dynamic_modules` + `test_custom_config` |




### What "working correctly" means

For the **same request and the same mounted config**, the rebuilt image must be indistinguishable from `nginx:1.25-bookworm`. `[test_compat.py](test/test_compat.py)` asserts, on every scenario:

- **Response** — identical status line, identical headers, and a **byte-identical body**.
- **Image & runtime** — identical container `Config` (`Entrypoint`, `Cmd`, `Env`, `Labels`, `StopSignal`, exposed ports, `User`, `WorkingDir`, `Volumes`), identical `nginx -V` and a passing `nginx -t`, the same `nginx` user, the same filesystem layout + permissions + file md5s under the nginx paths, and the same entrypoint log output.
- **Legitimately excluded** — `Date` (changes every response); and `ETag`/`Last-Modified` **only** for files shipped inside the packages (built at different times). Mounted content is always compared exactly.

If any of those differ, the test fails and prints both sides. As a control, injecting one `server_tokens off;` makes 16 checks fail — so the suite is proven to catch a real difference, not just pass.

### What the test covers (`[test_compat.py](test/test_compat.py)`, 58 checks, ~15 s)

- **Metadata & filesystem** — image config, `nginx` user/uid/gid, `nginx -V`/`-t`, directory layout + perms, file md5s.
- **Default site** — GET/HEAD, byte ranges, 404/405/413/414, conditional `304`, HTTP/1.0 without Host.
- **Robustness** — malformed requests (bad/duplicate Host, CL+TE smuggling, NUL in URI, 9 KB URI, 20 KB header, bad method) and pipelined keep-alive.
- **Custom config** — `return`/`redirect`, `rewrite`, `alias`, `map` regex, `autoindex`, `gzip`, and `proxy_pass` uploads (incl. chunked + 413).
- **Entrypoint** — `envsubst` templates and the startup log lines.
- **Dynamic modules** — all six `.so` (njs http+stream, xslt, image-filter, geoip http+stream).
- **TLS** (exercises the bumped OpenSSL) — TLS 1.2/1.3, ALPN h2/http1, a pinned cipher, and HTTP/2 over TLS.



### Beyond request/response

- **Package-set diff** (`[test_packages.py](test/test_packages.py)`) — `dpkg-query` on both images; only our seven `+echo1` rebuilds and base version bumps are allowed, anything else fails with the diff printed.
- **nginx's own test suite** (`[build/nginx-tests.sh](build/nginx-tests.sh)` → `[nginx/nginx-tests](https://github.com/nginx/nginx-tests)` @ `ec44bc80`) — run against the nginx binary **inside** each image and diffed vs the original (`[scripts/nginx_tests_compare.py](scripts/nginx_tests_compare.py)`); only the CVE-2026-15176 case may differ. *Implemented; not yet run (Docker down).*
- **Official-images** — `docker-library/official-images` has **no** nginx-specific tests, only generic bashbrew defaults; nothing to run.
- **The one intended difference** — `alias`+`rewrite` without `break` now yields empty `$request_filename` + an alert, tested as *expected* (`[test_cve_2026_15176.py](test/test_cve_2026_15176.py)`) with the near-miss cases pinned unchanged (`test_backport_only_affects_no_break_alias`).



### Architecture

Built and tested on **arm64**. **amd64:** a CI workflow (`[.github/workflows/ci.yml](.github/workflows/ci.yml)`) and `make deb-amd64`/`image-amd64` (QEMU) exist but **have not been run**, so no multi-arch support is claimed.

## Residual risk

Little vulnerable code is reachable in the default (no-TLS) config; risk rises with config — TLS activates the OpenSSL surface, and `alias`+`rewrite`/`ssi`+`aio`/HTTP/3 reach the nginx core CVEs. The ~480 base-OS findings are largely unreachable (nginx never runs curl/perl/util-linux); build-process items are supply-chain, not runtime. Triage was *library*-level (nginx links `libssl3`), but reachability is a *function* question — the two fixed OpenSSL CVEs sit in code nginx never calls, fixed only because the linkage is real (symbol-level evidence pending Docker).


| Risk                     | Detail                                                                                                 | Next                                                                                                       |
| ------------------------ | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| OpenSSL 3.0.x CVEs       | 7 unfixed in 3.0.22 (last public 3.0.x); newest 3.0.x Debian ships                                     | Move to OpenSSL 3.5 LTS (same ABI) + TLS regression                                                        |
| Unpatched nginx CVEs     | Grype flags 3 (CVE-2026-97205/-97629/-95101); nginx.org lists 3 more; most need non-default directives | Backport like we did, or move to 1.30.x                                                                    |
| Base OS / curl           | ~480 findings (curl, libtiff, perl, util-linux, glibc), none executed by nginx                         | Drop curl (~76 fewer) where healthchecks allow; track glibc                                                |
| arm64 only               | Built/tested on arm64 only                                                                             | Run CI (`[.github/workflows/ci.yml](.github/workflows/ci.yml)`) / `make deb-amd64` natively, gate on green |
| OpenSSL `nocheck`        | Self-tests skipped for build speed                                                                     | `OPENSSL_CHECK=1 make deb` in CI                                                                           |
| Build deps not pinned    | Toolchain not pinned, so not byte-reproducible (sources+hashes are pinned)                             | Pin via snapshot.debian.org                                                                                |
| Versions can be replaced | `+echo1` sorts below a future `3.0.22-1~deb12u2`                                                       | Mitigated by `apt-mark hold`; longer term use an epoch                                                     |
| VEX must travel          | CVE-2026-15176 shows unless grype runs with the VEX (backport ≠ version change)                        | Ship the VEX as an OCI attestation                                                                         |




## What I'd do next

This repo is a one-off, manual fix for one image. To make it work at scale:

- **Triage as code:** turn my manual filtering (reachability, severity, EPSS)
into rules that rank CVEs for any image, not only nginx.
- **Every fix proves itself:** require a test that fails on the old image and
passes on the new one before a fix is accepted.
- **Honest metric:** count only the CVEs fixed beyond what a plain
`apt upgrade` would fix.
- **Automate the loop:** a new CVE triggers rebuild, tests and rescan, and a
person steps in only on failure.



## Repo layout

```
build/          Dockerfile, build.sh, versions.env, patches/nginx/CVE-2026-15176.patch, asan.sh, nginx-tests.sh
Containerfile   final image from out/debs
rootfs/         docker-entrypoint.sh + docker-entrypoint.d/ (verbatim from docker-nginx@9abe4ae)
test/           harness.py, test_compat.py, test_cve_2026_15176.py, test_entrypoint.py, test_versions.py, test_packages.py, configs/, www/
vex/            nginx.openvex.json
scripts/        scan_diff.py, nginx_tests_compare.py
.github/        workflows/ci.yml (native amd64 build + test)
scan-result/    start/ (baseline + triage page), fixed/ (rescan, VEX run, diff.md); apt-upgrade/, asan/, nginx-tests/ are produced by the opt-in diagnostics
plans/          decision log + my-plan.md (research diary)
doc-pictures/   triage screenshots referenced by my-plan.md
```



## Personal Summary

This was my first time working with Debian packaging that deeply.

**What I understand and made decisions on:**

- Choose CVEs by the following filters:
  - Reachability-based triage: only nginx and the libraries it links to are
   exposed to traffic, so I filtered on that, then by severity and EPSS.
- The tetsting for logistic & compact, building high level stages

**What Claude Code built and I verified through tests:**

- Debian packaging internals (dpkg-buildpackage, quilt, debian/rules) and
nginx's pkg-oss build.
- OpenSSL ABI compatibility across 3.x versions.
- The memory-level details of the CVE-2026-15176 overflow in C.

**What I'd learn next:**

- Debian packaging end to end (building one small package by hand)
- Reading C patches at the memory level
- Function-level reachability analysis (not only library-level)

