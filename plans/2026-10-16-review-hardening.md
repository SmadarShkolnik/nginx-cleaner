# Echo skeptical-review hardening pass

- Created by: Claude Code session d24c8a9b-b6c6-4b83-9aa5-57f46a3cb866
- Date & time: 2026-10-16 21:23 IDT
- Trigger: pasted "skeptical reviewer" request — close the weakest points, keep `make all` green, update README only where facts change.

## Blocking environment fact (verified this session)

`docker run --rm hello-world` still fails with
`write /var/lib/desktop-containerd/.../meta.db: input/output error`, and
`/System/Volumes/Data` is 100% full (~580 MiB free). So **nothing can be built,
scanned, or run** right now. Every item below is split into what I can do
**offline** (edit code/docs with logic that holds against the already-recorded
behaviour) and what needs a **healthy Docker + free disk** to produce or verify.
I will not claim `make all` is green, or that any new build/scan artifact is
real, until Docker is fixed and I have run it.

## Decisions you made (from the Echo request)

- Act as a skeptical reviewer first; write this plan before any change; only implement after approval; ask before anything ambiguous.
- Keep `make all` green; update the README only where the facts change.
- **P1.1** `test/test_cve_2026_15176.py`: `len(body) > 0` on the original image is too weak (a correct, non-leaking `/x` response would also pass). Assert something **only a leak can produce** — the body differs from the correct mapping and carries bytes beyond `"/x"` (e.g. `len > 2`, or non-printable bytes). Explain why the new assertion can't pass by accident.
- **P1.2 (optional, if feasible in reasonable time)** An ASan build of nginx 1.25.5 as a **separate make target** (not part of `make all`) showing a heap-buffer-overflow on `/foo/1` without the patch and none with it. If too costly, write down what I tried.
- **P2.3** Add a fair comparison: `nginx:1.25-bookworm` + `apt-get update && apt-get upgrade` vs our image. Show which CVEs we remove that a plain apt upgrade does **not**. Add to `diff.md` and the README rescan section. If the OpenSSL bump gives nothing beyond apt upgrade, say so plainly.
- **P2.4** Reconcile triage with residual risk: the README says CVE-2025-15467 / CVE-2024-5535 sit in code nginx never calls, while triage filtered by "library nginx links to". Add a short paragraph on **library-level vs function-level reachability** (e.g. which libssl symbols nginx/modules import via `nm -D` / `objdump -T`) and state the conclusion.
- **P3.5** Check whether upstream `ce1da78` has other hunks or an accompanying test in nginx-tests; if feasible run the relevant nginx-tests (alias, rewrite, map) against the patched build and record the result.
- **P3.6** Document the intended behaviour change (alias + rewrite without break now yields empty `$request_filename` + alert) as the **only** expected diff vs the original, and make the compat test treat it explicitly as expected.
- **P4.7** Pin `FROM debian:bookworm-slim` by digest in both `build/Dockerfile` and `Containerfile` (record the digest in `versions.env` if practical).
- **P4.8** Make the VEX product identifier the image digest (or document why the tag is used); note in the README that the VEX should ship as an OCI attestation. SBOM via syft is a bonus.
- **P4.9** `apt-mark hold` currently covers `nginx`, `libssl3`, `openssl` but not `nginx-module-*`; hold them too and extend `test_versions.py`.
- End with a short summary: what changed, what I couldn't do and why, which README claims are now stronger.

## Open questions for you (ambiguous — asked before implementing)

1. **Docker is down.** Proceed with all offline code/doc edits now and mark the build/scan/run items as TODO-until-Docker-healthy, or hold everything until Docker + disk are fixed?
2. **ASan (P1.2) and nginx-tests (P3.5)** are the two most expensive items and both need a working Docker. Real attempt once Docker is back, or document-the-attempt only (write down the target/approach and the expected result without running)?
3. **VEX identifier (P4.8).** The image digest changes every build and is only known *after* the build (chicken-and-egg for a checked-in file). Keep the human-readable tag `echo/nginx:1.25-bookworm` as the product `@id`, keep the exact `pkg:deb/...+echo1` purl subcomponent (which is what actually pins the fix), and document why + add the OCI-attestation note — or switch the `@id` to a digest placeholder that CI fills in?
4. **Reachability evidence (P2.4).** The `nm -D` / `objdump -T` symbol check needs the built binaries (Docker). Write the library-vs-function paragraph now as a reasoned argument and add the concrete symbol evidence when Docker is back, or defer the whole paragraph until I can run the symbol check?

## Proposed approach per item (pending approval)

### P1.1 — stronger CVE assertion  [offline edit; `make test` re-verify needs Docker]
Recorded original body for `/foo/1` is NUL-prefixed heap bytes followed by `"/x"`
(≈17–19 bytes). The correct, non-leaking value of `$request_filename` after the
`rewrite … /x` is the alias-mapped path of the rewritten URI — a short printable
string ending in `x`, never containing NUL. New assertions on every `/foo/1`:
- body **contains a NUL byte** (`b"\x00" in r.body`) — a correctly mapped
  filesystem path is printable and cannot contain `\x00`; only an over-read into
  the uninitialised/adjacent heap produces it;
- body is **longer than any benign mapping** and **differs from the patched
  empty body** (`len(r.body) > 2`).
Why it can't pass by accident: a non-vulnerable nginx either returns the empty
body (patched) or a clean printable path (hypothetical correct mapping); neither
contains `\x00`. The NUL assertion keys on the over-read itself, not on response
length. Keep the existing `print()`.

### P1.2 — ASan build target  [Docker-blocked]
Add `make asan` (separate, not in `all`): build nginx 1.25.5 with
`-fsanitize=address -g` (unpatched and patched), run the `/foo/1` reproducer,
capture the ASan `heap-buffer-overflow` report for the unpatched build and its
absence for the patched one into `scan-result/asan/`. Scope depends on Q2.

### P2.3 — honest apt-upgrade baseline  [Docker-blocked]
New target `make scan-apt-baseline`: start from `nginx:1.25-bookworm`, run
`apt-get update && apt-get upgrade -y`, commit to a throwaway image, Trivy+Grype
it into `scan-result/apt-upgrade/`, and diff **our image vs the apt-upgraded
image** (extend `scan_diff.py` with a third column set or a second invocation).
Report the delta the OpenSSL-from-source bump adds beyond apt upgrade; if apt
upgrade already pulls `3.0.22-1~deb12u1` (bookworm-security) the honest answer is
"the bump matches apt upgrade; what's ours is building it from the upstream
tarball + the nginx backport" — state that plainly. Add a short rescan subsection
to the README.

### P2.4 — library vs function reachability  [paragraph offline; symbol evidence Docker-blocked]
Short README paragraph: triage filtered at **library** granularity (nginx links
`libssl3`, so both scanners flag its CVEs), but reachability is a **function**
question (does nginx/any loaded module call the vulnerable code path?). Evidence
plan: `objdump -T` / `nm -D --undefined-only` the nginx binary and each
`ngx_*module*.so` for the libssl symbols behind CVE-2025-15467 (CMS) and
CVE-2024-5535 (SSL_select_next_proto / ALPN). Conclusion to state: fixed anyway
because the linkage is direct and scanners flag it, but in the default (no-TLS)
config the code is not reached — recorded as a VEX justification candidate.

### P3.5 — upstream commit completeness + nginx-tests  [offline diff check; test run Docker-blocked]
Offline: re-fetch `ce1da78` and confirm the patch we ship is the complete diff
(single hunk in `ngx_http_core_module.c`) and whether the commit shipped an
nginx-tests case; record findings. Running the perl nginx-tests against the
patched build is Docker-blocked; scope per Q2.

### P3.6 — document the one expected behaviour diff  [offline]
Add an explicit note (test + README) that the **only** intended behaviour change
vs the original is: `alias` + `rewrite` (no break) + `$request_filename` now
yields empty `$request_filename` + an alert, instead of the leaked body. The
compat suite's configs don't exercise this path, so compat stays byte-identical;
make that explicit with a comment and keep the CVE test as the authority on the
expected diff.

### P4.7 — pin base image by digest  [needs digest; edits offline]
Resolve the current `debian:bookworm-slim` digest (registry API or, once Docker
is back, `docker buildx imagetools inspect`), record `DEBIAN_BASE_DIGEST` in
`versions.env`, and change both `FROM debian:bookworm-slim` lines to
`FROM debian:bookworm-slim@sha256:…`. Note the arch caveat (a digest pins one
manifest / arch unless I pin the index digest).

### P4.8 — VEX identifier + OCI attestation note  [offline JSON/docs; SBOM Docker-blocked]
Per Q3. Default proposal: keep the tag `@id`, keep the `+echo1` purl
subcomponent, add a `status_notes`/README line that the VEX must ship as an OCI
attestation (e.g. `cosign attest --type openvex`) so the product identity binds
to the pushed image digest at publish time. SBOM via syft = bonus, Docker-blocked.

### P4.9 — hold the module packages  [offline edits; verify Docker-blocked]
`Containerfile`: extend `apt-mark hold` to the four
`nginx-module-{xslt,geoip,image-filter,njs}` packages. `test_versions.py`:
add the module packages to the held-set assertion (and, if they carry our
`+echo1`, to the version map). Verification needs Docker.

## Decisions I inferred (subject to the questions above)

- One plan file (this one) covers all 9 items rather than nine files, since it's a single review pass; each Q&A answer will be appended here.
- New artifacts go in new dirs: `scan-result/apt-upgrade/`, `scan-result/asan/`; existing `scan-result/fixed/` is untouched except `diff.md` regeneration.
- `make all` stays `deb image test`; `asan` and `scan-apt-baseline` are separate opt-in targets so the default stays fast and green.
- README edits are limited to: rescan section (apt-upgrade delta), a reachability paragraph, the VEX/OCI note, and the residual-risk "Next" lines that these changes close — no restructuring of other sections.
- I will not overwrite or delete any existing plan file.

## Record of Q&A

Asked 2026-10-16 21:23 IDT, answered same session:

1. **Docker down — proceed how?** → *Offline work now.* Do all code/doc edits whose logic holds against already-recorded behaviour; mark every build/scan/run verification as TODO-until-Docker-healthy; claim nothing green until actually run.
2. **ASan (P1.2) & nginx-tests (P3.5) scope?** → *Attempt for real when Docker is back.* Add the targets now; build+run them for real once Docker/disk are healthy and record real output; if too costly, write down what I tried.
3. **VEX identifier (P4.8)?** → *Keep tag + purl, document + OCI note.* Keep `@id` = tag, keep the `+echo1` purl subcomponent, add README/status note that the VEX must ship as an OCI attestation (e.g. `cosign attest --type openvex`).
4. **Reachability evidence (P2.4)?** → *Write reasoned paragraph now, add symbol evidence later.* Add the library-vs-function paragraph now; fill concrete `objdump`/`nm` evidence when Docker is back.

## Implementation status (offline pass, 2026-10-16)

Docker-blocked verification and the two heavy targets (ASan, nginx-tests, apt-upgrade rescan, symbol evidence, all `make` runs) remain TODO until `docker run --rm hello-world` succeeds and disk is freed. Offline edits done this pass are listed in the final summary.

## Final summary (offline pass)

### What changed
- **P1.1** `test/test_cve_2026_15176.py`: replaced `len(body)>0` with a leak-signature assertion — each `/foo/1` body must end with `/x` and have non-printable bytes in front of it. Added `printable()` helper + a "why it can't pass by accident" comment. Logic validated offline against recorded/hypothetical bodies.
- **P3.6** `test/test_compat.py`: module docstring now states the one intended behavioural diff; added `test_backport_only_affects_no_break_alias` pinning the near-miss cases (rewrite WITH `last`, alias WITHOUT rewrite) as unchanged. Compat count 57→58 in README.
- **P4.7** Pinned `debian:bookworm-slim` by OCI-index digest `sha256:7c7b2c96…c587` (covers amd64+arm64) in `build/Dockerfile`, `Containerfile`, `Makefile`; recorded `DEBIAN_BASE_DIGEST` in `versions.env`; added offline `test_base_image_digest_is_pinned_and_consistent`.
- **P4.9** `apt-mark hold` now also covers the four `nginx-module-*`; `test_versions.py` gained `test_modules_are_our_echo_build` + a module-aware held-set check.
- **P4.8** VEX kept tag `@id` + `+echo1` purl; README now documents why the tag is used and that the VEX should ship as an OCI attestation.
- **P2.4** README: library-level-vs-function-level reachability paragraph; conclusion stated (fixed but unreachable in default config); objdump/nm symbol evidence deferred to Docker.
- **P2.3** Added `make scan-apt-baseline` + env-labelled `scan_diff.py` output; README "Honest baseline" subsection states plainly that apt upgrade already clears the OpenSSL CVEs (our value = provenance + pin + the nginx backport apt can't give). Exact numbers pending a real scan.
- **P1.2 / P3.5 (run part)** Added opt-in `make asan` + `build/asan.sh` and `make nginx-tests` + `build/nginx-tests.sh` (nginx source hash pinned; nginx-tests commit pinned). Written offline, syntax-checked, unrun.
- **P3.5 (completeness)** Verified upstream `ce1da78` is a single +1/-1 hunk, no other files, no bundled test (GitHub API); noted in the patch header.
- Housekeeping: deterministic tie-break in `scan_diff.py` (regenerated `diff.md`); fixed stale `Dockerfile.build` reference in `build.sh`.

### What I couldn't do (and why)
- Could not run `make all`/`deb`/`image`/`test`/`scan`/`vex`, `make asan`, `make nginx-tests`, `make scan-apt-baseline`, or the objdump/nm symbol check: Docker is down (containerd `meta.db` I/O error) and the host disk is 100% full. All build/scan/run verification is deferred until `docker run --rm hello-world` succeeds.
- Offline-verified instead: CVE leak-signature logic (simulated bodies), full pytest **collection** (85 items, no import errors), the digest-sync test (passes), `diff.md` regeneration is byte-stable, both shell scripts `bash -n`-clean, and `make -n` on the new targets.

### Residual (honesty notes)
- The leak assertion fails conservatively if a truly vulnerable build ever leaked only-printable bytes (recorded bytes are NUL, so this is a non-issue in practice; a false *negative*, never a false pass).
- `asan.sh` / `nginx-tests.sh` are unverified until run; they may need small fixes on first real execution.

### README claims now stronger
- The backport proof asserts the leak itself, not non-emptiness.
- "Fixed but unreachable" is reconciled with the library-level triage.
- Reproducibility: base image pinned by digest; honest apt-upgrade comparison is explicit rather than implied.
- Supply chain: module packages held; VEX distribution path (OCI attestation) documented.
