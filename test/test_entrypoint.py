"""The entrypoint scripts must be byte-identical to the origin nginx image.

Our Containerfile ships its own copies of the docker-entrypoint scripts
(rootfs/), mirroring nginxinc/docker-nginx at the commit the Containerfile
pins. If upstream ever changes a script, or ours drifts, the drop-in promise
("same entrypoint behaviour as nginx:1.25-bookworm") quietly breaks. These
tests pin that promise.

Origin = nginxinc/docker-nginx @ ORIGIN_COMMIT (the official nginx:1.25-bookworm
image is built from it). The pinned hashes below were taken from that commit:

    c=9abe4ae
    b=https://raw.githubusercontent.com/nginxinc/docker-nginx/$c
    curl -fsSL $b/mainline/debian/docker-entrypoint.sh | sha256sum
    for f in 10-listen-on-ipv6-by-default.sh 15-local-resolvers.envsh \
             20-envsubst-on-templates.sh 30-tune-worker-processes.sh; do
        curl -fsSL $b/entrypoint/$f | sha256sum
    done

Run the remote re-check with:  ENTRYPOINT_VERIFY_REMOTE=1 pytest test_entrypoint.py
"""
import hashlib
import os
import urllib.request

import pytest

from harness import NEW_IMAGE, ORIG_IMAGE, HERE, docker

ORIGIN_COMMIT = "9abe4ae"

# path inside the image  ->  (sha256 at ORIGIN_COMMIT, upstream repo path)
ENTRYPOINTS = {
    "/docker-entrypoint.sh": (
        "3372fd90162da30d09f62c245e9c6bfd620fb0bb5b48ab54b16e804c2b9e8aae",
        "mainline/debian/docker-entrypoint.sh"),
    "/docker-entrypoint.d/10-listen-on-ipv6-by-default.sh": (
        "8c5d2c912416126c7d65651600b166c00ad9ca3e3af82487ddd5a5da94fb8fb5",
        "entrypoint/10-listen-on-ipv6-by-default.sh"),
    "/docker-entrypoint.d/15-local-resolvers.envsh": (
        "3659a4a271496f6a8f0785a1d7e57a9348803e90c08fe57431fe3ee19b010644",
        "entrypoint/15-local-resolvers.envsh"),
    "/docker-entrypoint.d/20-envsubst-on-templates.sh": (
        "253c8724acff9f5c0d0e8938e71fe7c33097d40031a5bc9c7f59dfd2ba5f1377",
        "entrypoint/20-envsubst-on-templates.sh"),
    "/docker-entrypoint.d/30-tune-worker-processes.sh": (
        "1f068aa49da8df46bfd5a917debf110af9b115370739e3be34af83ebf583fbce",
        "entrypoint/30-tune-worker-processes.sh"),
}

ROOTFS = os.path.join(os.path.dirname(HERE), "rootfs")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def rootfs_path(image_path: str) -> str:
    # /docker-entrypoint.sh -> rootfs/docker-entrypoint.sh
    return os.path.join(ROOTFS, image_path.lstrip("/"))


def image_file_sha(image: str, path: str) -> str:
    # Read the file straight out of the image without starting its entrypoint.
    out = docker("run", "--rm", "--entrypoint", "sha256sum", image, path)
    return out.strip().split()[0]


def image_entrypoint_set(image: str) -> set:
    listing = docker("run", "--rm", "--entrypoint", "sh", image, "-c",
                     "ls -1 /docker-entrypoint.sh /docker-entrypoint.d/*")
    return {p.strip() for p in listing.splitlines() if p.strip()}


@pytest.mark.parametrize("path", sorted(ENTRYPOINTS))
def test_rootfs_source_matches_origin(path):
    """The repo's own copy (rootfs/) equals the origin repo at the pinned commit."""
    expected = ENTRYPOINTS[path][0]
    with open(rootfs_path(path), "rb") as fh:
        got = sha256(fh.read())
    assert got == expected, f"{path}: rootfs {got} != origin {expected}"


@pytest.mark.parametrize("path", sorted(ENTRYPOINTS))
def test_shipped_image_matches_origin(path):
    """What the rebuilt image actually ships equals the origin and the original image."""
    expected = ENTRYPOINTS[path][0]
    assert image_file_sha(NEW_IMAGE, path) == expected, f"{path}: rebuilt image != origin"
    assert image_file_sha(ORIG_IMAGE, path) == expected, f"{path}: original image != origin"


def test_entrypoint_set_is_identical():
    """No entrypoint script added or removed versus the original image."""
    assert image_entrypoint_set(NEW_IMAGE) == image_entrypoint_set(ORIG_IMAGE) \
        == set(ENTRYPOINTS)


@pytest.mark.skipif(os.environ.get("ENTRYPOINT_VERIFY_REMOTE") != "1",
                    reason="set ENTRYPOINT_VERIFY_REMOTE=1 to re-check pins against GitHub")
@pytest.mark.parametrize("path", sorted(ENTRYPOINTS))
def test_pins_still_match_upstream(path):
    """Keeps the pinned hashes honest: re-fetch origin and confirm they're current."""
    expected, repo_path = ENTRYPOINTS[path]
    url = f"https://raw.githubusercontent.com/nginxinc/docker-nginx/{ORIGIN_COMMIT}/{repo_path}"
    with urllib.request.urlopen(url, timeout=20) as resp:
        got = sha256(resp.read())
    assert got == expected, f"{repo_path}: upstream {got} != pinned {expected}"
