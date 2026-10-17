# Upstream-fidelity audit + new tests + amd64

- Created by: Claude Code session d24c8a9b-b6c6-4b83-9aa5-57f46a3cb866
- Date & time: 2026-10-17 (IDT)
- Trigger: pasted "verify everything that defines the original nginx:1.25-bookworm is really copied and tested; add amd64 if feasible; update README." Plan-first, ask-before-ambiguous, implement-after-approval, `make all` stays green.

## Blocking environment fact (verified this session)

`docker run --rm hello-world` still fails with
`write /var/lib/desktop-containerd/.../meta.db: input/output error`. Disk now has
~5.3 GiB free (was ~580 MiB), so the earlier disk-full cause is gone, but the
containerd metadata store is **corrupted** and needs Docker Desktop →
Troubleshoot → **Clean / Purge data** to rebuild. Until then: no build, scan,
image inspect, or container run. Every "prove it: change → run → revert" step and
Parts B/C runtime steps are **deferred**; I prove offline where a test is offline.

## Decisions you made (from the request)

- Plan first (this file), ask before ambiguous, implement only after approval; `make all` stays green.
- **Part A** Audit against the two upstream sources at their exact commits — docker-nginx `mainline/debian/Dockerfile` @ `9abe4ae` and pkg-oss @ `14d7f18` — one row per behaviour-defining item: item | upstream source | where in repo | test | does the test fail if it differs (prove it). Cover at least: ENTRYPOINT/CMD/EXPOSE/STOPSIGNAL/ENV/LABEL/USER/WORKDIR/volumes; nginx user uid/gid 101, home, shell; exact apt package set and nothing extra; entrypoint scripts byte-identical + perms; log symlinks + /docker-entrypoint.d; nginx/njs versions, configure flags, build path; default config/HTML, layout/perms; all dynamic modules load and work. Any item not copied or not tested is a gap: fix or explain.
- **Part B** New tests: (1) package-set `dpkg-query -W` diff with an explicit allowed-difference list, printing the diff; (2) run nginx-tests (nginx/nginx-tests, pinned commit+hash) against the **new image's binary** for http core/alias/rewrite/map/ssl/modules, run the same subset against the **original image**, allow only the CVE-2026-15176 difference; (3) check docker-library/official-images for nginx tests, run if present else say so; (4) explicit expected-behaviour-change test documenting the single intended diff.
- **Part C** amd64 only if feasible: test `docker buildx` + QEMU for linux/amd64, measure time; if it works add `make deb-amd64`/`image-amd64` (or a `PLATFORM` var) and run the full suite on amd64 both sides; if too slow/broken, don't force it — add a GitHub Actions workflow on a native amd64 runner and document it wasn't run locally. Don't claim multi-arch unless amd64 tests actually passed.
- **Part D** Add the provided README section, replacing the current compatibility section where it overlaps; adjust every claim to what is actually implemented and passing (fix test names, mark not-done items), fill the Architecture line, no unverified claims.
- Finish with a short summary: gaps found, fixes, tests added, amd64 status, what I couldn't do and why.

## Part A — audit table

Upstream A1 = docker-nginx `mainline/debian/Dockerfile` @ `9abe4ae` (fetched this session).
Upstream A2 = pkg-oss @ `14d7f18` (drives `nginx -V` + default files; consumed by build.sh).
"Fails if differs?" legend: **Yes/offline** = proven offline this session; **Yes/Docker** = reasoned, the test clearly keys on the item but the change→run→revert proof needs Docker; **GAP** = not covered.

| # | Item | Upstream source | Where in repo | Test | Fails if differs? |
|---|---|---|---|---|---|
| 1 | `ENTRYPOINT ["/docker-entrypoint.sh"]` | A1 Dockerfile `ENTRYPOINT` | `Containerfile` | `test_compat.test_image_config_matches` (Config.Entrypoint) | Yes/Docker |
| 2 | `CMD ["nginx","-g","daemon off;"]` | A1 `CMD` | `Containerfile` | `test_image_config_matches` (Config.Cmd) | Yes/Docker |
| 3 | `EXPOSE 80` | A1 `EXPOSE` | `Containerfile` | `test_image_config_matches` (ExposedPorts) | Yes/Docker |
| 4 | `STOPSIGNAL SIGQUIT` | A1 `STOPSIGNAL` | `Containerfile` | `test_image_config_matches` (StopSignal) | Yes/Docker |
| 5 | `ENV` NGINX_VERSION/NJS_VERSION/NJS_RELEASE/PKG_RELEASE | A1 `ENV` ×4 | `Containerfile` | `test_image_config_matches` (Config.Env) | Yes/Docker |
| 6 | `LABEL maintainer=…` | A1 `LABEL` | `Containerfile` | `test_image_config_matches` (Config.Labels) | Yes/Docker |
| 7 | USER/WORKDIR/VOLUME — upstream sets **none** (runs as root; master drops privs) | A1 (absent) | `Containerfile` (also none) | `test_image_config_matches` (User, WorkingDir, Volumes all compared) | Yes/Docker |
| 8 | nginx user/group uid/gid 101, home `/nonexistent`, shell `/bin/false`, comment | A1 `groupadd/useradd` | `Containerfile` (same two lines) | `test_compat.test_user_matches` (`id`/`getent passwd`/`getent group`) | Yes/Docker |
| 9 | Exact apt package set (nginx, 4 modules, gettext-base, curl, ca-certificates) **and nothing extra** | A1 `$nginxPackages` + install | `Containerfile` install list | — today only partial (`nginx -V`, file layout); no whole-package-set assertion | **GAP → Part B1** |
| 10 | Entrypoint scripts byte-identical | A1 `COPY` ×5; scripts @ `9abe4ae` | `rootfs/` | `test_entrypoint.py` (sha256 vs pinned origin; offline + in-image) | Yes/offline |
| 11 | Entrypoint script permissions (0755) | upstream exec bits | `rootfs/*` = 0755 | `test_compat.test_filesystem_matches` LAYOUT (`%m`) | Yes/Docker |
| 12 | Log symlinks `access.log→/dev/stdout`, `error.log→/dev/stderr` | A1 `ln -sf` | `Containerfile` `ln -sf` | `test_filesystem_matches` LAYOUT (`%l` target) | Yes/Docker |
| 13 | `/docker-entrypoint.d` exists | A1 `mkdir` | `Containerfile` `mkdir` | `test_filesystem_matches` LAYOUT | Yes/Docker |
| 14 | nginx 1.25.5, njs 0.8.4 **release 3** | A2 pkg-oss @ 14d7f18 | `build/versions.env` | `test_versions.py` (nginx exact; njs via `+echo1` only) | Yes/Docker (njs-release = partial, see gap 20) |
| 15 | `configure` flags identical | A2 pkg-oss `debian/rules` | produced by `build/build.sh` | `test_compat.test_build_flags_match` (`nginx -V` configure args) | Yes/Docker |
| 16 | Build path `/data/builder/debuild/nginx-1.25.5` | A2 pkg-oss path | `build/build.sh` | `test_build_flags_match` (prefix-map shows in `nginx -V`) | Yes/Docker |
| 17 | Default config files + default HTML | A2 pkg-oss `debian/` | shipped by the nginx .deb | `test_filesystem_matches` CONTENT (md5) + LAYOUT | Yes/Docker |
| 18 | Dynamic modules load (njs, xslt, geoip, image-filter) | A1 module pkgs / A2 build | `build/build.sh`, `Containerfile` | `test_compat.test_dynamic_modules` + `test_custom_config` | Yes/Docker |
| 19 | OpenSSL version (our intended delta 3.0.11→3.0.22) | n/a (our change) | `build/versions.env` | `test_build_flags_match` ("built with OpenSSL 3.0.22") + `test_versions.py` | Yes/Docker |
| 20 | njs module exact version `1.25.5+0.8.4-3+echo1~bookworm` | A1 `NJS_VERSION/NJS_RELEASE` | build.sh `MODULE_RELEASE_njs` | only `+echo1` presence asserted | **minor GAP** — optionally pin njs module version in `test_versions.py` |

### Proven offline this session
- Item 10: editing a `rootfs/` script makes `test_entrypoint.test_rootfs_source_matches_origin` fail (sha mismatch); revert restores. (Will re-run to capture the exact PASS/FAIL lines.)
- Item 14/19 base pin: `test_versions.test_base_image_digest_is_pinned_and_consistent` already proven offline last pass.

### Gaps
- **Gap 9 (package set "nothing extra")** → add Part B1 package-set diff test.
- **Gap 20 (njs module exact version)** → minor; propose pinning it in `test_versions.py`.
- Everything else is copied and has a test that keys on it; only the change→run→revert proof is Docker-deferred.

## Part B — plan

1. **`test/test_packages.py`** (new): `dpkg-query -W -f '${Package} ${Version}\n'` in both images; compute added/removed/version-changed; allow ONLY (a) our `+echo1` packages (nginx, libssl3, openssl, 4 modules), (b) Debian security/point-release version bumps from the newer base (same package name, different version). Anything else → fail and print the diff. Docker-run deferred.
2. **nginx-tests against the image binary** (Part B2): refactor last pass's `build/nginx-tests.sh` + `make nginx-tests` so the suite runs with `TEST_NGINX_BINARY` = the nginx **inside** the image (via a container that mounts the checkout), for http/alias/rewrite/map/ssl/modules; run the same subset against `nginx:1.25-bookworm`; diff results; allow only the CVE-2026-15176 case. Pin commit `ec44bc80c4bfac1dbd8ffee3875101285f8502ac` + record a tarball hash. Docker-run deferred. (Open question Q3.)
3. **Official-images** (Part B3): **finding — none exist.** `docker-library/official-images` has no nginx entry in `test/config.sh` and no `test/tests/*nginx*` dir (checked this session); nginx images run only the generic defaults (`utc`, `override-cmd`, …) via their bashbrew harness. I'll record this in the README and, if Q2/approval wants it, add an opt-in target to run the generic suite (needs their harness + Docker). No fabricated results.
4. **Expected-behaviour-change test** (Part B4): already added last pass — `test_compat.test_backport_only_affects_no_break_alias` (near-miss unchanged) + `test_cve_2026_15176.py` (the intended diff). I'll add one explicitly-named assertion/marker tying them together as "expected diff, not regression," if not already clear enough.

## Part C — amd64 plan

- Feasibility (buildx+QEMU timing) can't be measured now (Docker down).
- Default proposal (Q2): add a **GitHub Actions** workflow (`.github/workflows/ci.yml`) that runs `make all` on a native `ubuntu-24.04` (amd64) runner, and a `PLATFORM ?= linux/arm64` variable + buildx path in the Makefile so `make deb PLATFORM=linux/amd64` is possible locally once Docker is back. README Architecture line → "CI workflow added, not yet run; amd64 not verified locally." **No multi-arch claim.**

## Part D — README plan
- Replace the current `## Compatibility test` section with the provided `## Compatibility: what was copied from upstream, and what tests it`, folding in the still-true specifics (58 checks, coverage list, the negative check) so nothing accurate is lost.
- Fix every claim to reality: name the real tests (`test_image_config_matches`, `test_user_matches`, `test_packages.py`, `test_entrypoint.py`, `test_filesystem_matches`, `test_build_flags_match`, `test_dynamic_modules`); mark nginx-tests / official-images / amd64 as implemented-but-not-run-yet (Docker) rather than asserting pass.
- Correct the dynamic-modules count if "six" is wrong (there are 4 module packages; verify against `test/configs/modules/nginx.conf`).
- Fill Architecture line per Part C. Leave the user-added "What I'd do next" and "Personal Summary" sections untouched.

## Open questions for you (asked before implementing)

1. **Docker is still down.** Do the whole pass offline (audit table done above; add the new tests, the amd64 CI workflow + PLATFORM path, and the README rewrite with unrun items clearly marked), deferring every container run and the change→run→revert proofs — or hold until Docker is repaired?
2. **amd64 (Part C):** add the GitHub Actions amd64 workflow + a `PLATFORM` buildx path now and mark the README "CI added, not run locally" — or skip CI and just mark amd64 "not done"?
3. **nginx-tests (Part B2):** run the suite against the **shipped image's nginx binary** (your wording) and diff vs the original image — i.e. rework last pass's from-source `nginx-tests.sh` — or keep building from source?
4. **README overlap (Part D):** fully **replace** the existing "Compatibility test" section with your draft (folding the accurate specifics into it) — or keep the old section and add the new one alongside?

## Decisions I inferred (subject to the questions)

- One plan file for this pass; Q&A appended below.
- Package-set allowed-difference list = our 7 `+echo1` packages + any same-name Debian version bump from the newer base; everything else fails.
- New tests live in `test/` and are collected by `make test`, but their Docker-dependent bodies are skipped/deferred until Docker is back (collection must stay green offline).
- No README claim of multi-arch or of any passing run that hasn't actually run.

## Record of Q&A

Asked & answered 2026-10-17:
1. **Docker down — approach?** → *Do it all offline now.* Add tests, amd64 CI + PLATFORM path, README rewrite; defer every container run and the change→run→revert proofs; claim nothing passing until run.
2. **amd64 (Part C)?** → *CI workflow + PLATFORM path.* GitHub Actions on a native amd64 runner + a `PLATFORM` buildx path; README Architecture = "CI added, not run locally"; no multi-arch claim.
3. **nginx-tests (Part B2)?** → *Run against the shipped image binary.* `TEST_NGINX_BINARY` = nginx inside our image; same subset against the original image; allow only the CVE-2026-15176 diff. Reworks last pass's from-source script.
4. **README overlap (Part D)?** → *Replace, folding in accurate specifics.* Replace the existing Compatibility section with the draft, keeping the true details; fix test names; mark unrun items.

## Final summary (offline pass, 2026-10-17)

### Gaps found
- **Gap 9** — no whole-package-set assertion ("exact set, nothing extra"): the install list was tested only indirectly (`nginx -V`, file layout). **Fixed** → `test/test_packages.py`.
- **Gap 20 (minor)** — njs module exact version not pinned (only `+echo1` presence). Left as-is; noted. Everything else in the audit is copied **and** has a test that keys on it.
- Not a gap but corrected: README had the right "six dynamic modules" count (6 `.so` from 4 packages — verified in `test/configs/modules/nginx.conf`).

### Tests / tooling added
- `test/test_packages.py` — dpkg-query parity with an explicit allow-list (our 7 `+echo1` rebuilds + base version bumps); fails on any added/dropped/un-`+echo1` package and prints the diff. Partition logic simulated offline (good case passes; extra/dropped/lost-echo all fail).
- `build/nginx-tests.sh` reworked to run the suite against the nginx **inside** each image; `scripts/nginx_tests_compare.py` diffs ours vs original and allows only the CVE case. `make nginx-tests` now runs both images + compares.
- `.github/workflows/ci.yml` — native amd64 `make all` + artifact upload.
- Makefile: `PLATFORM`/`PLATFORM_FLAG`, `deb-amd64`, `image-amd64` (QEMU), `--platform` threaded into `deb`/`image`/pull.
- README: Compatibility section fully replaced with the audited two-table version + "Beyond request/response" + Architecture; residual-risk arm64 row and repo layout updated.

### Proven offline
- Audit item 10 (entrypoint byte-identity): clean → 5 passed; append one byte to `rootfs/docker-entrypoint.sh` → `test_rootfs_source_matches_origin[/docker-entrypoint.sh]` FAILED; reverted clean.
- Full pytest **collection**: 87 items, no import errors. YAML valid, shell `bash -n` clean, Python compiles, `make -n` expands `nginx-tests`/`deb-amd64`/`image-amd64` correctly with `--platform`.

### amd64 status
Not verified locally — Docker is down and QEMU timing couldn't be measured. CI workflow + `make deb-amd64`/`image-amd64` are in place but **unrun**; README claims no multi-arch support.

### Part B3 — official-images
No nginx-specific tests exist in `docker-library/official-images` (no `test/config.sh` entry, no `test/tests/*nginx*`). nginx images get only the generic bashbrew defaults. Recorded in README; nothing nginx-specific to run.

### Couldn't do (Docker down — containerd meta.db corrupted, needs Clean/Purge)
All change→run→revert proofs for image-based audit rows (items 1–9, 11–19), and the real runs of `make all`, `make nginx-tests`, `make scan-apt-baseline`, `make asan`, and the amd64 CI/QEMU builds. Deferred until `docker run --rm hello-world` succeeds.
