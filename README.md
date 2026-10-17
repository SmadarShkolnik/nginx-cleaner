# Clean nginx:1.25-bookworm

A drop-in replacement for `nginx:1.25-bookworm`. Every package that matters is compiled here from upstream source on a clean `debian:bookworm-slim`. It eliminates three CVEs: one by **backporting** an upstream nginx fix onto 1.25.5, and two by a **version bump** of OpenSSL. An automated test compares the new image against the original.

## Approach (research diary)

The full diary is [plans/my-plan.md](plans/my-plan.md).

1. Scanned the original image with Grype and Trivy, then merged both into an interactive triage page ([scan-result/start/nginx-cve-triage.html](scan-result/start/nginx-cve-triage.html)).
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

~4 min on an 8-core arm64 Docker VM. Everything is pinned: the `debian:bookworm-slim` base by digest (`BASE_IMAGE` in the [Makefile](Makefile), passed into both the Dockerfile and the Containerfile), and every download by SHA-256/512 ([build/versions.env](build/versions.env)).

### What gets built ([build/build.sh](build/build.sh))


| Package(s)                                            | Source                                                                                                                                                                                                              | Version shipped           |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------- |
| `libssl3`, `openssl` (+ `libssl-dev` for the build)   | upstream `openssl-3.0.22.tar.gz`, built with Debian's bookworm-security `debian/` packaging                                                                                                                         | `3.0.22-1~deb12u1+echo1`  |
| `nginx`, `nginx-module-{njs,xslt,geoip,image-filter}` | `nginx-1.25.5.tar.gz` + njs 0.8.4 via nginx.org's [pkg-oss](https://github.com/nginx/pkg-oss) @ `14d7f18` (the commit behind the upstream image) + [CVE-2026-15176.patch](build/patches/nginx/CVE-2026-15176.patch) | `1.25.5-1+echo1~bookworm` |


OpenSSL is built first so nginx links against it; nginx builds under nginx.org's path (`/data/builder/debuild/nginx-1.25.5`) so `nginx -V` stays identical, and `build.sh` checks the patch is in each package's quilt `series`.

### The image ([Containerfile](Containerfile))

A copy of docker-nginx's `mainline/debian/Dockerfile` @ `9abe4ae`: same base, `nginx` uid/gid 101, package set, `ENV`, label, entrypoint scripts, ports, `STOPSIGNAL`, `CMD`. Only difference: packages come from `out/debs`, and our `+echo1` ones are `apt-mark hold`ed.
Image size **66.7 MB** vs **67.7 MB** (`make sizes`).

## CVEs fixed


| CVE                | Severity                          | Component                                    | Method                                                                                                                  | Evidence                                                                                                                                                    |
| ------------------ | --------------------------------- | -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **CVE-2026-15176** | High (Grype) / Medium (nginx.org) | `nginx` 1.25.5, `ngx_http_map_uri_to_path()` | **Backport** of upstream `[ce1da78](https://github.com/nginx/nginx/commit/ce1da78)` (fixed upstream in 1.30.6 / 1.31.7) | [patch](build/patches/nginx/CVE-2026-15176.patch) · [test](test/test_cve_2026_15176.py) · [VEX](vex/nginx.openvex.json) · [diff](scan-result/fixed/diff.md) |
| **CVE-2025-15467** | Critical (Grype) / High (Trivy)   | `libssl3`, `openssl` 3.0.11                  | **Version bump** to OpenSSL 3.0.22                                                                                      | [versions.env](build/versions.env) · [diff](scan-result/fixed/diff.md)                                                                                      |
| **CVE-2024-5535**  | Critical (Grype) / Low (Trivy)    | `libssl3`, `openssl` 3.0.11                  | **Version bump** (same build)                                                                                           | [diff](scan-result/fixed/diff.md)                                                                                                                           |




### Proof the backport works

[test/test_cve_2026_15176.py](test/test_cve_2026_15176.py) loads upstream's reproducer (`location /foo/ { alias …; rewrite ^/foo/.*$ /x; return 200 $request_filename; }`) and sends `GET /foo/1`:


| Image    | Response                                                | Error log                                                                    |
| -------- | ------------------------------------------------------- | ---------------------------------------------------------------------------- |
| original | `200`, 19-byte body: 17 non-printable heap bytes + `/x` | nothing                                                                      |
| rebuilt  | `200`, empty body; workers keep running                 | `[alert] "alias" cannot be used in location "/foo/" where URI was rewritten` |


The test asserts both directions. On the original it checks the *leak signature*, not just a non-empty body: every `/foo/1` response must end with the rewrite marker `/x` **and** carry non-printable bytes in front of it — a correctly mapped filesystem path is printable, and the patched build returns an empty body, so neither can satisfy it. On the rebuilt image it requires the empty body + the alert.

### Rescan ([scan-result/fixed/](scan-result/fixed/), [diff.md](scan-result/fixed/diff.md))


|                                                                   | Trivy | Grype |
| ----------------------------------------------------------------- | ----- | ----- |
| baseline                                                          | 825   | 796   |
| rebuilt                                                           | 480   | 459   |
| removed by the OpenSSL bump (42 CVEs × 2 pkgs)                    | 84    | 84    |
| removed by the newer `bookworm-slim` base (Debian point releases) | 261   | 253   |
| added                                                             | 0     | 0     |


A plain `apt upgrade` already clears the OpenSSL CVEs (bookworm-security ships the same `3.0.22-1~deb12u1`); our value-add is the nginx backport, from-source provenance, and the `apt-mark hold` pin.

The backport is invisible to scanners (nginx stays `1.25.5`), so Grype keeps flagging CVE-2026-15176. [vex/nginx.openvex.json](vex/nginx.openvex.json) marks it `fixed` for our exact `+echo1` build, and `grype --vex` then drops it (last column of `diff.md`). Trivy never reports nginx CVEs (the nginx.org package isn't in its Debian DB), so the VEX demo uses Grype.

The VEX product `@id` is the human-readable tag `echo/nginx:1.25-bookworm`; what actually pins the fix is the `pkg:deb/.../nginx@1.25.5-1%2Becho1~bookworm` subcomponent purl. The image digest changes every build and is only known after it, so it can't be hard-coded here — for distribution the VEX should ship as an **OCI attestation** (e.g. `cosign attest --type openvex`), which binds the statement to the pushed image digest at publish time so the document travels with the image instead of alongside it.

## Compatibility: "working correctly" and what the test checks

For the **same request and the same mounted config**, the rebuilt image must be indistinguishable from `nginx:1.25-bookworm`. [test/test_compat.py](test/test_compat.py) (57 of the 59 checks in `make test`, ~15 s; the other 2 are the CVE regression above) asserts on every scenario:

- **Response** — identical status line, identical headers, and a **byte-identical body**.
- **Image & runtime** — identical container `Config` (`Entrypoint`, `Cmd`, `Env`, `Labels`, `StopSignal`, exposed ports, `User`, `WorkingDir`, `Volumes`), identical `nginx -V` and a passing `nginx -t`, the same `nginx` user, the same filesystem layout + permissions + file md5s under the nginx paths, and the same entrypoint log output.
- **Legitimately excluded** — `Date` (changes every response), and `ETag`/`Last-Modified` only for files shipped inside the packages (built at different times); mounted content is always compared exactly.

Coverage: default site (GET/HEAD, byte ranges, 404/405/413/414, conditional `304`, HTTP/1.0 without Host); robustness (bad/duplicate Host, CL+TE smuggling, NUL in URI, 9 KB URI, 20 KB header, bad method, pipelined keep-alive); custom config (`return`/`redirect`, `rewrite`, `alias`, `map` regex, `autoindex`, `gzip`, `proxy_pass` uploads incl. chunked + 413); entrypoint `envsubst` templates and startup log lines; all six dynamic module `.so` (njs http+stream, xslt, image-filter, geoip http+stream); and TLS exercising the bumped OpenSSL (TLS 1.2/1.3, ALPN h2/http1, a pinned cipher, HTTP/2 over TLS). The one intended behavioural difference — `alias`+`rewrite` without `break` now returns an empty `$request_filename` + an alert — is covered as *expected* by the CVE test above. As a control, injecting one `server_tokens off;` makes 16 checks fail, so the suite is proven to catch a real difference.

## Residual risk

In the default config (no TLS) little of the remaining vulnerable code is
reachable; risk grows when a user enables TLS or non-default directives.
The two OpenSSL CVEs I fixed are likely not reachable either: my triage
filtered by linked library, not by function, and I haven't verified it at
function level.


| Still there                                                                                                            | Why                                                           | Next                                                                                    |
| ---------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| 7 CVEs in OpenSSL 3.0.22                                                                                               | 3.0.x is end of life; 3.0.22 is the last release              | Move to OpenSSL 3.5 LTS and rerun the TLS tests                                         |
| Other nginx 1.25.5 CVEs                                                                                                | Scope was one backport; most need non-default directives      | Backport them the same way, or move to nginx 1.30.x                                     |
| ~480 base-OS findings (curl, perl, util-linux, glibc)                                                                  | nginx never runs them; removing curl would break healthchecks | Drop curl where healthchecks don't need it                                              |
| Build and delivery gaps: arm64 only, OpenSSL self-tests skipped, build tools not pinned, VEX not attached to the image | Out of scope for the assignment                               | Build on amd64, run OpenSSL's tests, pin build deps, ship the VEX as an OCI attestation |


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



## How I used AI (Claude Code)

**What I decided.** The triage filters (reachability by linked library, then severity and EPSS) and which CVEs to fix; what "drop-in" means for the test (byte-identical response and the same image/runtime); and that the CVE test must prove the *original* image is vulnerable, not just the patched one safe.

**What Claude Code built.** The build scripts, the Debian/pkg-oss packaging, the test harness,  the scan-diff script. Also made another agent with different context to be its reviewer.

**Where it hurt.** The mistakes surfaced only when things actually ran:, should have make it run several times, to make sure nothing it over assummed or over-engineered - It tended to add extras beyond the assignment that I later removed (identical builder to extra tests over the layers, double testing by many shapes - that was over to maintain.

**What I don't yet understand in depth and would learn next.** Debian packaging internals (end to end), the memory-level details of the C fix, and function-level (not just library-level) reachability.