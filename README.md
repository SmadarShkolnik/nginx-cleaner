# Clean nginx:1.25-bookworm

A drop-in replacement for `nginx:1.25-bookworm`. Every package that matters is compiled here from upstream source on a clean `debian:bookworm-slim`. It eliminates three CVEs: one by **backporting** an upstream nginx fix onto 1.25.5, and two by a **version bump** of OpenSSL. An automated test compares the new image against the original.

## Approach (research diary)

The full diary is [`plans/my-plan.md`](plans/my-plan.md)

1. Scanned the original image with Grype and Trivy, then merged both into an interactive triage page ([`scan-result/start/nginx-cve-triage.html`](scan-result/start/nginx-cve-triage.html)).
2. Filtered to what is worth fixing: **runtime path = "nginx binary"** (only nginx and the libraries it links to are reachable by traffic), **severity**, **fix type** (backport vs. version bump), and **EPSS ≥ 90th percentile** for bumps.
3. Picked one CVE from each category. The funnel:

   | | path | funnel | chosen |
   |---|---|---|---|
   | **Backport** | 534 → 99 nginx-binary | → 38 High → 3 backport candidates | CVE-2026-15176 ([screenshot](images/backport-cves-after-filtering.png)) |
   | **Bump** | 534 → 99 nginx-binary | → 7 Critical → 5 newer-Debian-source → 2 at EPSS ≥ 90th | CVE-2025-15467, CVE-2024-5535 ([screenshot](images/bump-critical-cves-after-filtering.png)) |

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

The deb build takes about 4 minutes on an 8-core arm64 Docker VM. Everything is pinned in [`build/versions.env`](build/versions.env), and every download is checked against a SHA-256/512 before use. `OPENSSL_CHECK=1 make deb` additionally runs OpenSSL's own test suite (off by default for speed).

### What gets built ([`build/build.sh`](build/build.sh))

| Package(s) | Source | Version shipped |
|---|---|---|
| `libssl3`, `openssl` (+ `libssl-dev` for the build) | upstream `openssl-3.0.22.tar.gz`, built with Debian's bookworm-security `debian/` packaging | `3.0.22-1~deb12u1+echo1` |
| `nginx`, `nginx-module-{njs,xslt,geoip,image-filter}` | `nginx-1.25.5.tar.gz` + njs 0.8.4, built with nginx.org's own packaging ([pkg-oss](https://github.com/nginx/pkg-oss) @ `14d7f18`, the commit behind the upstream image), plus [`build/patches/nginx/CVE-2026-15176.patch`](build/patches/nginx/CVE-2026-15176.patch) | `1.25.5-1+echo1~bookworm` |

OpenSSL is built and installed first so nginx links against it; nginx is built under nginx.org's own path (`/data/builder/debuild/nginx-1.25.5`) so `nginx -V` stays identical; pkg-oss applies the patch into the quilt `series` of every package, and `build.sh` checks it is there.

### The image ([`Containerfile`](Containerfile))

A copy of docker-nginx's `mainline/debian/Dockerfile` @ `9abe4ae` (the one that built 1.25.5): same base, `nginx` uid/gid 101, package set, `ENV`, label, entrypoint scripts ([`rootfs/`](rootfs/), byte-identical to the original — [`test/test_entrypoint.py`](test/test_entrypoint.py)), ports, `STOPSIGNAL` and `CMD`. Only difference: packages come from `out/debs` instead of the nginx.org apt repo. Our `+echo1` packages are `apt-mark hold`ed so an apt upgrade can't replace them ([`test/test_versions.py`](test/test_versions.py)).

Image size: **66.7 MB** vs the original **67.7 MB** (`make sizes`).

## CVEs fixed

| CVE | Severity | Component | Method | Evidence |
|---|---|---|---|---|
| **CVE-2026-15176** | High (Grype) / Medium (nginx.org) | `nginx` 1.25.5, `ngx_http_map_uri_to_path()` | **Backport** of upstream [`ce1da78`](https://github.com/nginx/nginx/commit/ce1da78) (fixed upstream in 1.30.6 / 1.31.7) | [patch](build/patches/nginx/CVE-2026-15176.patch) · [test](test/test_cve_2026_15176.py) · [VEX](vex/nginx.openvex.json) · [diff](scan-result/fixed/diff.md) |
| **CVE-2025-15467** | Critical (Grype) / High (Trivy) | `libssl3`, `openssl` 3.0.11 | **Version bump** to OpenSSL 3.0.22 | [versions.env](build/versions.env) · [diff](scan-result/fixed/diff.md) |
| **CVE-2024-5535** | Critical (Grype) / Low (Trivy) | `libssl3`, `openssl` 3.0.11 | **Version bump** (same build) | [diff](scan-result/fixed/diff.md) |
| CVE-2026-93479 *(extra)* | High (Grype) | `nginx` | **VEX `not_affected`**: nginx.org lists only 1.30.0–1.30.5 / 1.31.2–1.31.6, so Grype's match on 1.25.5 is a false positive | [VEX](vex/nginx.openvex.json) |

### Proof the backport works

[`test/test_cve_2026_15176.py`](test/test_cve_2026_15176.py) loads upstream's reproducer (`location /foo/ { alias …; rewrite ^/foo/.*$ /x; return 200 $request_filename; }`) and sends `GET /foo/1`:

| Image | Response | Error log |
|---|---|---|
| original | `200`, 19 bytes: `\x00` × 16 + `/x` — the path buffer is sized for the rewritten URI and the copy runs past it, returning heap bytes | nothing |
| rebuilt | `200`, empty body; workers keep running | `[alert] "alias" cannot be used in location "/foo/" where URI was rewritten` |

The test asserts both directions, so it fails if either the leak reappears or the reproducer stops triggering.

### Rescan ([`scan-result/fixed/`](scan-result/fixed/), [`diff.md`](scan-result/fixed/diff.md))

| | Trivy | Grype |
|---|---:|---:|
| baseline | 825 | 796 |
| rebuilt | 480 | 459 |
| removed by the OpenSSL bump (42 CVEs × 2 pkgs) | 84 | 84 |
| removed by the newer `bookworm-slim` base (Debian point releases) | 261 | 253 |
| added | 0 | 0 |

The backport is invisible to scanners (nginx stays `1.25.5`), so Grype keeps flagging CVE-2026-15176. [`vex/nginx.openvex.json`](vex/nginx.openvex.json) marks it `fixed` for our exact `+echo1` build, and `grype --vex` then drops it (last column of `diff.md`). Trivy never reports nginx CVEs (the nginx.org package isn't in its Debian DB), so the VEX demo uses Grype.

## Compatibility test ([`test/test_compat.py`](test/test_compat.py), 57 checks, ~15 s)

"Working correctly" = for the same request and mounted config, the new image returns the same status line, headers and byte-identical body, plus the same image config, `nginx -V`, user, file layout/contents under the nginx paths, and entrypoint output. Only `Date` (always changes) and packaged-file `ETag`/`Last-Modified` (mtimes differ between builds; mounted content is compared exactly) are excluded.

Coverage: image config + file md5s + `nginx -V`/`-t`; default site (GET/HEAD, ranges, 404/405/413/414, conditional 304); malformed requests (bad Host, CL+TE, NUL in URI, oversized header…); pipelined keep-alive; custom config (`rewrite`, `alias`, `map` regex, gzip, `proxy_pass` uploads incl. chunked + 413); entrypoint templates; all six dynamic modules (njs, xslt…); and TLS exercising the bumped OpenSSL (TLS 1.2/1.3, ALPN, pinned cipher, HTTP/2 over TLS). As a negative check, adding one `server_tokens off;` fails 16 checks and exits 1.

## Residual risk

**Priority (by reachability in the default config).** The default image serves no TLS and enables none of the directives the remaining nginx CVEs need, so little of the vulnerable code is actually reachable. What matters most is what activates with a common config change: terminate TLS and the OpenSSL surface — including the seven unfixed 3.0.22 CVEs — goes live; use `alias`+`rewrite`, `ssi`+`aio`, HTTP/3 or session tickets and the still-present nginx core CVEs become reachable. The ~480 base-OS findings are largely unreachable (nginx never executes curl, perl or util-linux). The build-process items are supply-chain integrity and reproducibility concerns, not runtime exploits.

| Risk | Still there | Why left | Next |
|---|---|---|---|
| OpenSSL 3.0.x CVEs | 7 CVEs in 3.0.22 (last public 3.0.x, unsupported): CVE-2026-84782, -54872, -35189, -75805, -75806, -77696, CVE-2025-27587 | 3.0.22 is the newest 3.0.x Debian packages; leaving 3.0 needs new packaging | Move to OpenSSL 3.5 LTS (same `libssl.so.3` ABI) with a full TLS regression run |
| Unpatched nginx 1.25.5 CVEs | Grype flags CVE-2026-97205, -97629, -95101; nginx.org also lists CVE-2026-42945, -9256, -42533 (scanners miss these) | Scope was one backport; most need non-default directives | Backport the core-module ones the same way, or move to 1.30.x |
| Base OS / curl findings | ~480 Trivy findings in curl/libcurl, libtiff (image-filter only), perl, util-linux; some in `glibc` | nginx never executes them; dropping curl would break healthcheck drop-in compatibility | Drop curl (~76 fewer) where healthchecks don't need it; keep tracking glibc |
| Fixed OpenSSL CVEs, low reachability | CVE-2025-15467 (CMS parsing) and CVE-2024-5535 (empty ALPN) sit in code nginx never calls; default config serves no TLS | Fixed anyway: nginx links libssl3 directly and both scanners flag it | Record the non-reachability as a VEX justification; re-evaluate if TLS termination is enabled |
| arm64 only | Built and tested on arm64 | My Docker VM is arm64; the pipeline itself is arch-neutral | Build and run the full test suite on amd64 in CI before release |
| OpenSSL test suite skipped | Default build uses `DEB_BUILD_OPTIONS=nocheck`, so OpenSSL's self-tests don't run | Kept off for build speed; `OPENSSL_CHECK=1 make deb` runs them on demand | Run `OPENSSL_CHECK=1` in CI and gate releases on it |
| Build deps not pinned | apt build-dependencies install whatever bookworm currently offers, so the build is not byte-for-byte reproducible | Shipped sources and their hashes are pinned; the build-time toolchain is not | Pin build-deps (snapshot.debian.org or recorded versions) for a reproducible build |
| Our versions can be replaced | `+echo1` sorts below a future Debian `3.0.22-1~deb12u2`, so a newer base or an apt upgrade could replace or reject our packages | Unavoidable without changing the version scheme | Mitigated now with `apt-mark hold` ([test_versions.py](test/test_versions.py)); longer term, an epoch or a version that always sorts highest |
| VEX must travel with the image | CVE-2026-15176 still shows in scanners unless grype is run with `vex/nginx.openvex.json`; the backport is not a version change | VEX is the standard way to state "fixed but version unchanged" | Attach the VEX as an OCI attestation so it ships with the image |

## Notes and what I'd do differently

- Grype's nginx matching is unreliable both ways (false positive on CVE-2026-93479, misses real advisories); triage needs the vendor advisory.
- The backport returns `200 ""` + an alert, not a 500 — that's upstream behaviour; the unpatched 19-byte heap leak is the clearest proof of the bug.
- pkg-oss @ 1.25.5 still points at `hg.nginx.org` (now 404s); njs/xslscript are repointed to GitHub with pinned hashes, and every download is checked with `curl -f` + hash (one "tarball" turned out to be a 404 page).
- `dpkg-source` un-applies quilt patches after the build, so the check verifies the `series` and the runtime test proves the behaviour.
- The OpenSSL bump matches what bookworm-security already ships; compiling from the upstream tarball is what makes it ours. With more time: a bump target Debian doesn't ship, amd64 CI, image signing + VEX as an OCI attestation, and a fuzz-style differential test.
- **AI (Claude Code):** used for parsing scanner output into the triage page, cross-checking advisories, finding the exact upstream commits, and the test harness. It needed correction too (assumed a 500, pinned a 404 page's hash, wrote a placeholder commit) — each caught by actually running the build/tests/scans.

## Repo layout

```
build/          Dockerfile, build.sh, versions.env, patches/nginx/CVE-2026-15176.patch
Containerfile   final image from out/debs
rootfs/         docker-entrypoint.sh + docker-entrypoint.d/ (verbatim from docker-nginx@9abe4ae)
test/           harness.py, test_compat.py, test_cve_2026_15176.py, test_entrypoint.py, test_versions.py, configs/, www/
vex/            nginx.openvex.json
scripts/        scan_diff.py
scan-result/    start/ (baseline + triage page), fixed/ (rescan, VEX run, diff.md)
plans/          decision log + my-plan.md (research diary)
images/         triage screenshots referenced by my-plan.md
```
