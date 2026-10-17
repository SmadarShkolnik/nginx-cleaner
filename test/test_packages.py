"""Package-set parity: the new image must install the SAME Debian packages as
nginx:1.25-bookworm, with only an explicit, documented set of differences.

Allowed differences (everything else fails, and the test prints the diff):
  1. our from-source rebuilds, which carry the +echo1 suffix (nginx, libssl3,
     openssl, and the four nginx-module-* packages);
  2. plain version bumps of a package that exists in BOTH images, coming from the
     newer bookworm-slim base / Debian security updates (same name, new version).

What is NOT allowed and fails loudly:
  - a package present in one image but not the other (something added or dropped);
  - one of our packages that lost its +echo1 suffix (Debian silently replaced it).

This is the "exact apt package set, and nothing extra" check from the upstream
Dockerfile audit; `dpkg-query` is the source of truth, not the install list.
"""
import pytest

from harness import NEW_IMAGE, ORIG_IMAGE, docker

# Our from-source packages: they legitimately differ (the +echo1 suffix).
ECHO_PACKAGES = {
    "nginx", "libssl3", "openssl",
    "nginx-module-xslt", "nginx-module-geoip",
    "nginx-module-image-filter", "nginx-module-njs",
}
ECHO_SUFFIX = "+echo1"


def installed(image):
    """{package: version} for everything dpkg knows is installed in `image`."""
    out = docker("run", "--rm", "--entrypoint", "dpkg-query", image,
                 "-W", "-f", "${Package} ${Version}\n")
    pkgs = {}
    for line in out.splitlines():
        if line.strip():
            name, _, ver = line.partition(" ")
            pkgs[name] = ver
    return pkgs


@pytest.fixture(scope="module")
def pkg_sets():
    return installed(ORIG_IMAGE), installed(NEW_IMAGE)


def test_no_packages_added_or_removed(pkg_sets):
    orig, new = pkg_sets
    added = sorted(set(new) - set(orig))
    removed = sorted(set(orig) - set(new))
    msg = []
    if added:
        msg.append("added (in new, not original): "
                   + ", ".join(f"{p}={new[p]}" for p in added))
    if removed:
        msg.append("removed (in original, not new): "
                   + ", ".join(f"{p}={orig[p]}" for p in removed))
    assert not msg, "\n".join(msg)


def test_version_differences_are_expected(pkg_sets):
    """Every version difference must be ours (+echo1) or a base-refresh bump."""
    orig, new = pkg_sets
    shared = set(orig) & set(new)
    changed = {p: (orig[p], new[p]) for p in sorted(shared) if orig[p] != new[p]}

    # Our packages must still carry +echo1 (not silently replaced by Debian).
    lost_echo = {p: changed[p] for p in ECHO_PACKAGES & set(changed)
                 if ECHO_SUFFIX not in changed[p][1]}
    assert not lost_echo, \
        "our packages lost the +echo1 suffix (Debian replaced them): " + \
        "; ".join(f"{p}: {o} -> {n}" for p, (o, n) in lost_echo.items())

    # Our packages that are MISSING from the changed set would mean the original
    # already had our version - impossible unless the images were mixed up.
    missing_echo = {p for p in ECHO_PACKAGES & set(new)
                    if ECHO_SUFFIX not in new[p]}
    assert not missing_echo, \
        f"expected +echo1 build not found for: {sorted(missing_echo)}"

    # Everything else that changed is a plain Debian version bump from the newer
    # base; allowed, but print it so a human can eyeball the review.
    base_bumps = {p: v for p, v in changed.items() if p not in ECHO_PACKAGES}
    print(f"\n{len(base_bumps)} base/security version bumps (allowed):")
    for p, (o, n) in sorted(base_bumps.items()):
        print(f"  {p}: {o} -> {n}")
    print(f"{len(ECHO_PACKAGES & set(changed))} of our +echo1 rebuilds:")
    for p in sorted(ECHO_PACKAGES & set(changed)):
        print(f"  {p}: {changed[p][0]} -> {changed[p][1]}")
