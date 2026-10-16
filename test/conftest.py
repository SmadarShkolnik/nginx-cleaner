import os
import shutil
import uuid

import pytest

import harness
from harness import ORIG_IMAGE, NEW_IMAGE, docker


def pytest_report_header(config):
    return [f"original image: {ORIG_IMAGE}", f"new image:      {NEW_IMAGE}"]


@pytest.fixture(scope="session", autouse=True)
def images_present():
    for image in (ORIG_IMAGE, NEW_IMAGE):
        if not docker("image", "inspect", image, check=False).lstrip().startswith("["):
            pytest.exit(f"image {image} not found (run `make image` / `docker pull`)", 2)


@pytest.fixture(scope="session")
def network():
    name = f"nginx-compat-{uuid.uuid4().hex[:6]}"
    docker("network", "create", name)
    yield name
    docker("network", "rm", name, check=False)


@pytest.fixture(scope="session")
def workdir():
    path = os.path.join(harness.HERE, ".work")
    shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path)
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="session")
def tls_certs(workdir):
    """Self-signed cert, generated with the original image's openssl CLI."""
    certs = os.path.join(workdir, "certs")
    os.makedirs(certs)
    docker("run", "--rm", "-v", f"{certs}:/certs", "--entrypoint", "openssl", ORIG_IMAGE,
           "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
           "-subj", "/CN=localhost", "-keyout", "/certs/server.key", "-out", "/certs/server.crt")
    os.chmod(os.path.join(certs, "server.key"), 0o644)
    return certs
