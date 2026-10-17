"""The final image must ship exactly our +echo1 packages, not Debian's.

Our OpenSSL version 3.0.22-1~deb12u1+echo1 sorts BELOW a future Debian
3.0.22-1~deb12u2 (dpkg: `1+echo1` < `2`), so a newer bookworm-slim or an apt
upgrade could silently replace our from-source build. The Containerfile pins
these with `apt-mark hold`; this test fails loudly if the image ever carries
anything but our builds.

Expected versions are read from build/versions.env so a future bump is tracked
automatically.
"""
import os

import pytest

from harness import NEW_IMAGE, HERE, docker

REPO = os.path.dirname(HERE)
VERSIONS_ENV = os.path.join(REPO, "build", "versions.env")


def _env(key):
    with open(VERSIONS_ENV) as fh:
        for line in fh:
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1]
    raise KeyError(f"{key} not found in {VERSIONS_ENV}")


ECHO_SUFFIX = _env("ECHO_SUFFIX")                 # +echo1
OPENSSL_VERSION = _env("OPENSSL_DEB_VERSION")     # 3.0.22-1~deb12u1+echo1
# nginx version = <upstream>-1<echo>~bookworm, built from BASE_RELEASE=1<echo> in build.sh.
NGINX_VERSION = f'{_env("NGINX_VERSION")}-1{ECHO_SUFFIX}~bookworm'  # 1.25.5-1+echo1~bookworm

EXPECTED = {
    "libssl3": OPENSSL_VERSION,
    "openssl": OPENSSL_VERSION,
    "nginx": NGINX_VERSION,
}


def test_base_image_digest_is_pinned_and_consistent():
    """build/Dockerfile and Containerfile must pin the exact DEBIAN_BASE_DIGEST.

    Offline guard (no docker): a drifting or unpinned base silently changes the
    build, so the digest in versions.env must appear in both files' FROM lines.
    """
    digest = _env("DEBIAN_BASE_DIGEST")
    assert digest.startswith("sha256:") and len(digest) == 71, digest
    pin = f"debian:bookworm-slim@{digest}"
    for rel in ("build/Dockerfile", "Containerfile"):
        text = open(os.path.join(REPO, rel)).read()
        assert pin in text, f"{rel} does not pin {pin}"
        assert "FROM debian:bookworm-slim\n" not in text and \
               "FROM debian:bookworm-slim " not in text, \
               f"{rel} still has an unpinned FROM debian:bookworm-slim"


def installed_version(pkg):
    return docker("run", "--rm", "--entrypoint", "dpkg-query", NEW_IMAGE,
                  "-W", "-f", "${Version}", pkg).strip()


@pytest.mark.parametrize("pkg,expected", sorted(EXPECTED.items()))
def test_image_has_our_echo_version(pkg, expected):
    got = installed_version(pkg)
    assert ECHO_SUFFIX in got, \
        f"{pkg}: {got!r} is not an {ECHO_SUFFIX} build - Debian may have replaced it"
    assert got == expected, f"{pkg}: image has {got!r}, expected our {expected!r}"


# Every from-source package that must not be replaced by an apt upgrade: the
# three in EXPECTED plus the four nginx.org modules (also built with +echo1).
MODULE_PACKAGES = {
    "nginx-module-xslt", "nginx-module-geoip",
    "nginx-module-image-filter", "nginx-module-njs",
}
HELD_PACKAGES = set(EXPECTED) | MODULE_PACKAGES


def test_our_packages_are_held():
    """apt-mark hold must keep an apt upgrade from swapping our packages out."""
    held = set(docker("run", "--rm", "--entrypoint", "apt-mark", NEW_IMAGE,
                      "showhold").split())
    missing = HELD_PACKAGES - held
    assert not missing, f"not held: {sorted(missing)} (held: {sorted(held)})"


@pytest.mark.parametrize("pkg", sorted(MODULE_PACKAGES))
def test_modules_are_our_echo_build(pkg):
    """The shipped modules must be our +echo1 builds, not Debian/nginx.org ones."""
    got = installed_version(pkg)
    assert ECHO_SUFFIX in got, \
        f"{pkg}: {got!r} is not an {ECHO_SUFFIX} build - it may have been replaced"
