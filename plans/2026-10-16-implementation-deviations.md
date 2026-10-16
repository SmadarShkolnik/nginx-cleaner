# Implementation: decisions made while building (addendum)

- Created by: Claude Code session 7bfebbd4-9648-4c80-a913-1f7427f407a3
- Date & time: 2026-10-16 15:49 IDT
- Follows: `plans/2026-10-16-implementation-build-patch-ship.md`

## Decisions you made

- None new since `2026-10-16-implementation-build-patch-ship.md`. You approved the plan, and nothing below was decided by you.

## Decisions I inferred (during implementation)

These differ from, or add to, the approved plan. Each one has a reason.

### Build sources

- **pkg-oss commit `14d7f18` instead of tag `1.25.5-1`.**
  - The tag builds njs `0.8.4-1`, but the original image ships njs `0.8.4-3`.
  - Commit `14d7f18` on pkg-oss master is the one that bumped njs to release 3 while nginx was still 1.25.5.
- **njs and xslscript sources point to GitHub.**
  - pkg-oss at that commit downloads them from `hg.nginx.org`, which now returns HTML pages.
  - njs uses the GitHub tag archive (`njs-0.8.4/` tree), with a SHA-512 pinned by me. The GitHub *release* asset doesn't exist; I had first pinned the hash of its 404 page, and fixed that.
  - xslscript uses the version and SHA-512 from pkg-oss master.
- **The OpenSSL upstream tarball is checked twice.** It is the GitHub release asset, and its SHA-256 matches both openssl.org's `.sha256` file and Debian's `.dsc`.

### Package and build details

- **Release string is `1.25.5-1+echo1~bookworm`, not `1~bookworm+echo1`.**
  - pkg-oss always appends `~<codename>` to the release, so the suffix goes before it.
  - The result still sorts higher than the original `1~bookworm`.
  - OpenSSL is `3.0.22-1~deb12u1+echo1`.
- **The nginx build runs under `/data/builder/debuild/nginx-1.25.5`.**
  - That is nginx.org's build path. It is embedded in `nginx -V` through `-ffile-prefix-map`.
  - Using it makes the `configure arguments` line identical to the original's.
- **Patch check uses the quilt `series`, not a grep of the source tree.** `dpkg-source` un-applies patches after building, so the source tree no longer shows the fix. The runtime test proves the behaviour.
- **Build log goes to a file inside the builder.** Its tail is printed on failure, because BuildKit truncates step output at 2 MiB.

### Final image

- **No apt pin file was added.**
  - Our versions already sort above Debian's, so `apt-get upgrade` won't replace them.
  - A newer Debian security release would replace them, which is acceptable.
  - Not adding the file also keeps `/etc/apt` closer to the original.
- **`ENV` uses the legacy `ENV key value` syntax**, copied verbatim from upstream. Docker warns about it, but the resulting config is identical.

### Tests

- **CVE-2026-15176 test expectation changed.** The plan assumed a 500. The patched build actually answers `200` with an empty body plus the upstream `[alert]`. The test asserts that.
- **The original's response is recorded, not asserted.** It returns 19 bytes: 16 leaked heap bytes plus `/x`.

### VEX

- **Product and subcomponent identifiers:**
  - Product: the image reference `echo/nginx:1.25-bookworm`.
  - Subcomponent: `pkg:deb/debian/nginx@1.25.5-1%2Becho1~bookworm`, with no arch or distro qualifiers.
  - Found by testing what Grype honors. The image ID and `pkg:oci` forms were not applied to this local image.
  - The original's version is not matched.
- **CVE-2026-93479 is added to the VEX file as `not_affected`.** The plan listed this as optional.

### Delivery

- **Nothing was committed.** You didn't ask for a commit.
