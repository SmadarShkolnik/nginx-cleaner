# nginx:1.25-bookworm, rebuilt from source and patched

This is a drop-in replacement for `nginx:1.25-bookworm`. Every package that matters is compiled here from upstream source on a clean `debian:bookworm-slim`. It eliminates three CVEs: one by **backporting** an upstream nginx fix onto 1.25.5, and two by a **version bump** of OpenSSL. An automated test compares the new image against the original.

## Build

You need Docker with BuildKit, plus `python3` with `pytest`, `trivy` and `grype`.

```sh
make all     # = make deb image test
make deb     # build/Dockerfile.build: compile the .debs from source  -> out/debs/
make image   # Containerfile: install the .debs                      -> echo/nginx:1.25-bookworm
make test    # test/: compatibility + CVE regression tests (non-zero exit on mismatch)
make scan    # Trivy + Grype on the new image -> scan-result/fixed/, diff vs scan-result/start/
make vex     # Grype with vex/nginx.openvex.json applied
make sizes   # original vs new image size
```

The deb build takes about 4 minutes on an 8-core arm64 Docker VM. Everything is pinned in [`build/versions.env`](build/versions.env), and every download is checked against a SHA-256 or SHA-512 before it is used.

### What gets built ([`build/build.sh`](build/build.sh))

| Package(s) | Source | Version shipped |
|---|---|---|
| `libssl3`, `openssl` (+ `libssl-dev` for the build) | upstream `openssl-3.0.22.tar.gz`, built with Debian's bookworm-security `debian/` packaging | `3.0.22-1~deb12u1+echo1` |
| `nginx`, `nginx-module-{njs,xslt,geoip,image-filter}` | `nginx-1.25.5.tar.gz` + njs 0.8.4 + quickjs, built with nginx.org's own packaging ([pkg-oss](https://github.com/nginx/pkg-oss) @ `14d7f18`, the commit that produced the upstream image's njs `0.8.4-3`), plus [`build/patches/nginx/CVE-2026-15176.patch`](build/patches/nginx/CVE-2026-15176.patch) | `1.25.5-1+echo1~bookworm` |

- **OpenSSL is built first** and installed into the build root, so nginx compiles and links against it.
- **nginx is built under nginx.org's own path,** `/data/builder/debuild/nginx-1.25.5`. That path is embedded in `nginx -V` (`-ffile-prefix-map`), and using the same one makes the `configure arguments` line identical to the original's.
- **pkg-oss applies the patch everywhere.** Every `contrib/src/nginx/*.patch` goes into the quilt `series` of the base package and of each module package. `build.sh` checks that the patch is in every series it compiled.

### The image ([`Containerfile`](Containerfile))

This is a copy of docker-nginx's `mainline/debian/Dockerfile` at commit `9abe4ae` (the one that built 1.25.5).
- **Same as the original:** base image, `nginx` user and group (uid/gid 101), package set, `ENV`, label, entrypoint scripts, `EXPOSE 80`, `STOPSIGNAL SIGQUIT` and `CMD`.
- **Entrypoint scripts:** stored in [`rootfs/`](rootfs/) and byte-identical to the ones in the original image.
- **What changes:** packages come from `out/debs` (bind-mounted at build time) instead of the nginx.org apt repo.

## Image size

| Image | Size |
|---|---:|
| `nginx:1.25-bookworm` (original) | 67,665,983 bytes (67.7 MB) |
| `echo/nginx:1.25-bookworm` (this repo) | 66,710,639 bytes (66.7 MB) |

The new image is about 1 MB smaller. Most of the difference comes from the current bookworm package versions and from our own builds; the nginx.org apt keyring the original keeps in `/etc/apt/keyrings` is only 6.5 KB.

## CVEs fixed

| CVE | Severity | Component | Method | Evidence |
|---|---|---|---|---|
| **CVE-2026-15176** | High (Grype) / Medium (nginx.org) | `nginx` 1.25.5, `ngx_http_map_uri_to_path()` | **Backport** of upstream commit [`ce1da78`](https://github.com/nginx/nginx/commit/ce1da78) (fixed upstream in 1.30.6 / 1.31.7) | [patch](build/patches/nginx/CVE-2026-15176.patch) · [regression test](test/test_cve_2026_15176.py) · [VEX](vex/nginx.openvex.json) · [scan diff](scan-result/fixed/diff.md) |
| **CVE-2025-15467** | Critical (Grype) / High (Trivy) | `libssl3`, `openssl` 3.0.11 | **Version bump** to upstream OpenSSL 3.0.22 | [versions.env](build/versions.env) · [scan diff](scan-result/fixed/diff.md) |
| **CVE-2024-5535** | Critical (Grype) / Low (Trivy, OpenSSL) | `libssl3`, `openssl` 3.0.11 | **Version bump** (same build) | [scan diff](scan-result/fixed/diff.md) |
| CVE-2026-93479 *(extra)* | High (Grype) | `nginx` | **VEX `not_affected`**: nginx.org lists only 1.30.0–1.30.5 and 1.31.2–1.31.6 as vulnerable, so Grype's match on 1.25.5 is a false positive | [VEX](vex/nginx.openvex.json) |

[`plans/my-plan.md`](plans/my-plan.md) and the triage page ([`scan-result/start/nginx-cve-triage.html`](scan-result/start/nginx-cve-triage.html)) explain why these were chosen. In short:
- The nginx binary links libssl3 directly, and the two OpenSSL CVEs are Critical with high EPSS.
- CVE-2026-15176 is a real heap overflow in the nginx core, with a one-line upstream fix and a reproducer.

### Proof that the backport works

[`test/test_cve_2026_15176.py`](test/test_cve_2026_15176.py) loads upstream's reproducer config:

```nginx
location /foo/ { alias /usr/share/nginx/html/; rewrite ^/foo/.*$ /x; return 200 $request_filename; }
```

and sends `GET /foo/1`. The two images respond as follows.

| Image | Response | Error log |
|---|---|---|
| original | `200`, 19 bytes: `\x00` × 16 + `/x`. The path buffer is sized for the rewritten URI, and the copy runs past it, returning heap bytes. | nothing |
| rebuilt | `200`, empty body; workers keep running | `[alert] "alias" cannot be used in location "/foo/" where URI was rewritten` |

### Rescan ([`scan-result/fixed/`](scan-result/fixed/))

| | Trivy findings | Grype findings |
|---|---:|---:|
| baseline (`scan-result/start/`) | 825 | 796 |
| rebuilt | 480 | 459 |
| removed by the OpenSSL bump (42 CVEs × `libssl3` + `openssl`) | 84 | 84 |
| removed by the newer `bookworm-slim` base (Debian point releases, not my work) | 261 | 253 |
| added | 0 | 0 |

- **The backport doesn't show up as a version change.** Scanners match on package name and version, and nginx is still `1.25.5`, so Grype keeps reporting CVE-2026-15176 after the fix.
- **VEX makes the fix visible.** [`vex/nginx.openvex.json`](vex/nginx.openvex.json) is an OpenVEX document that marks it `fixed` for `pkg:deb/debian/nginx@1.25.5-1%2Becho1~bookworm` in `echo/nginx:1.25-bookworm`. With `grype --vex` the CVE disappears (see the last column of [`diff.md`](scan-result/fixed/diff.md)).
- **The VEX statement is version-specific.** It only matches our `+echo1` build: pointed at the original's version, `1.25.5-1~bookworm`, it doesn't apply.
- **Trivy never reports nginx CVEs.** The nginx.org package isn't in its Debian database, so the VEX demo uses Grype.

## Compatibility test

**What "working correctly" means.** For the same request and the same mounted configuration, the new image returns the same status line, the same headers and a byte-identical body. It also has the same image config, the same `nginx -V` build flags, the same user, the same file layout and contents under the nginx paths, and the same entrypoint output. Only these headers are excluded from comparison:
- **`Date`**, which changes on every request.
- **`ETag`/`Last-Modified` for files shipped inside the packages.** Their mtimes differ between the two builds. For mounted content they are compared exactly, and each image is checked to answer 304 to its own validators.

**What it covers** ([`test/test_compat.py`](test/test_compat.py), 57 checks, about 15 s):

| Area | Checks |
|---|---|
| Image | `docker inspect` Config (User, WorkingDir, Entrypoint, Cmd, ExposedPorts, StopSignal, Env, Labels, Volumes), file layout and modes/owners, md5 of every file under `/etc/nginx`, `/usr/share/nginx/html` and the entrypoint scripts, `id nginx`, `nginx -V` (version + configure arguments), `nginx -t` |
| Default site | `GET`/`HEAD` `/`, `/index.html`, `/50x.html`, 404, HTTP/1.0 without Host, `Range` (valid and unsatisfiable), `Accept-Encoding`, `POST`/`OPTIONS`/`DELETE` → 405, 2 MB body → 413, path traversal, long path, conditional GET → 304 |
| Malformed requests | garbage line, missing Host, `HTTP/2.0` request line, URI too long (414), 20 KB header, duplicate Host, CL+TE, unknown TE, NUL in URI, invalid header name, invalid method |
| Connection handling | pipelined keep-alive requests (`GET`, `HEAD`, 404) on one connection |
| Custom config | `return` + `add_header`, 301, `rewrite … last`, `alias`, multi-range on a large file, `autoindex`, `map` with regex captures, gzip (headers + decompressed body), `proxy_pass` uploads: small, 2 MB → 413, 2 MB with raised `client_max_body_size`, chunked |
| Entrypoint | default entrypoint log lines; `NGINX_ENVSUBST` templates in `/etc/nginx/templates` |
| Modules | `load_module` of all six dynamic modules; njs `js_content`; xslt transform |
| TLS (exercises the bumped OpenSSL) | `openssl s_client` from a fixed client container: TLS 1.3 + ALPN h2 / http/1.1, TLS 1.2 + ALPN, TLS 1.2 with a pinned cipher (protocol, cipher, key exchange, signature, ALPN, verify result), then HTTP/2 over TLS with curl |

**The suite catches real differences.** As a negative check, I added a single `server_tokens off;` to an otherwise identical image. 16 checks failed and pytest exited 1.

## Residual risk

- **Seven OpenSSL CVEs remain** in `libssl3`/`openssl` 3.0.22: CVE-2026-84782, CVE-2026-54872, CVE-2026-35189, CVE-2026-75805, CVE-2026-75806, CVE-2026-77696 and CVE-2025-27587. 3.0.22 is the last public 3.0.x, and OpenSSL 3.0 is no longer publicly supported.
  - **Next:** move to OpenSSL 3.5 LTS. It keeps the `libssl.so.3` ABI, but needs new Debian packaging and a full TLS regression run.
- **Other nginx CVEs that affect 1.25.5 are still present:**
  - **Flagged by Grype:** CVE-2026-97205 (AIO + SSI use-after-free), CVE-2026-97629 (TLS session tickets), CVE-2026-95101 (HTTP/3 body injection).
  - **Not flagged by either scanner,** although nginx.org lists them as affecting 1.25.5: CVE-2026-42945 and CVE-2026-9256 (rewrite module overflows), CVE-2026-42533 (map/regex) and several others in the [nginx advisories](https://nginx.org/en/security_advisories.html).
  - **Mitigation and next step:** most of these need specific configs (`alias`+`rewrite`, `ssi`+`aio`, HTTP/3, session tickets). The default config uses none of them. Next: backport the core-module ones the same way, starting with CVE-2026-42945 and CVE-2026-97205, or plan a move to 1.30.x.
- **Base OS and curl:** about 480 Trivy findings remain.
  - Most are in packages nginx never loads, such as curl/libcurl (38 each, mostly `won't fix`), libheif and libtiff (only via the opt-in image-filter module), and perl and util-linux.
  - Others are in `glibc`, which nginx does use.
  - **Next:** removing `curl` from the image would cut about 76 findings. It isn't done here because it would break drop-in compatibility for users whose healthchecks call `curl`.
- **Reachability of the fixed OpenSSL CVEs is low.** CVE-2025-15467 is in CMS parsing, which nginx never calls. CVE-2024-5535 needs an empty ALPN list, which nginx can't pass. The default config doesn't even listen on TLS. The bump is still right, because nginx loads libssl3 directly and both scanners flag it, but it's driven by the scanners, not by an exploit path.
- **This is an arm64 build.** The pipeline is architecture-neutral, but I only built and tested it on arm64.

## Surprises, and what I'd do differently

- **Grype's nginx matches are not reliable in either direction.** It flags CVE-2026-93479, which doesn't affect 1.25.5, and misses several advisories that do. Trivy reports no nginx CVEs at all for the nginx.org package. Triage needs the vendor advisory, not just the scanner.
- **The backport doesn't produce a 500.** I expected the patched build to fail the request. Instead `$request_filename` becomes empty and nginx answers `200 ""` with an alert in the log, which is upstream behaviour. The unpatched build's 19-byte response with leaked heap bytes is the clearest evidence of the bug.
- **Upstream sources have moved.** pkg-oss at 1.25.5 still points to `hg.nginx.org`, which now returns HTML pages instead of tarballs. The build repoints njs and xslscript to their GitHub archives with my own pinned hashes. In the process, one "tarball" I had hashed turned out to be a GitHub 404 page, so every pinned download is now checked with `curl -f` plus its hash.
- **`dpkg-source` un-applies quilt patches after the build.** Grepping the source tree afterwards for the fix fails even though the fix was compiled in. The check now verifies the quilt `series`, and the runtime test proves the behaviour.
- **The bump is in libraries the base image would update anyway.** Bookworm-security already ships OpenSSL 3.0.22, so a plain rebase would remove the same 84 findings. Compiling it from the upstream tarball is what makes the bump ours. With more time I'd choose a bump target Debian doesn't ship, such as OpenSSL 3.5 or a curl release fixing the `won't fix` set.
- **With more time I'd also:**
  - build for amd64 in CI
  - sign the image and attach the VEX as an OCI attestation
  - add a fuzz-style differential test (random request lines and headers against both images)

## How AI tools were used

I used Claude Code (Claude Opus) throughout.
- **Where it helped:**
  - Parsing both scanner formats into the interactive triage page.
  - Checking whether each candidate CVE actually affects 1.25.5 against nginx.org and the upstream commits, which is how the CVE-2026-93479 false positive was caught.
  - Finding the exact pkg-oss and docker-nginx commits that built the original image.
  - Writing the test harness.
- **Where it hurt or needed correction:**
  - It first assumed the patched build would return 500.
  - It pinned a hash of a 404 page.
  - It wrote a placeholder commit hash that had to be replaced.

  Each was caught by actually running the build, the tests and the scans. Decisions about which CVEs to fix were mine ([`plans/`](plans/)).

## Repo layout

```
build/          Dockerfile.build, build.sh, versions.env, patches/nginx/CVE-2026-15176.patch
Containerfile   final image from out/debs
rootfs/         docker-entrypoint.sh + docker-entrypoint.d/ (verbatim from docker-nginx@9abe4ae)
test/           harness.py, test_compat.py, test_cve_2026_15176.py, configs/, www/
vex/            nginx.openvex.json
scripts/        scan_diff.py
scan-result/    start/ (baseline reports + triage page), fixed/ (rescan, VEX run, diff.md)
plans/          decision log
```
