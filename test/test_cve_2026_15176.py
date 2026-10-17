"""CVE-2026-15176: upstream reproducer (nginx ce1da78), alias + rewrite without break + $request_filename.

Original image: GET /foo/1 returns non-printable bytes followed by "/x".
Patched image: empty body and an "alias cannot be used" alert; workers keep running.
"""
import os
import time

import pytest

from harness import CONFIGS, Pair, request

ALERT = '"alias" cannot be used in location "/foo/" where URI was rewritten'
PATHS = ["/foo/1", "/foo/" + "A" * 64]
LEAK_TAIL = b"/x"  # the rewrite target; ends every /foo/1 body on the original image


def printable(b):
    return all(0x20 <= c <= 0x7e for c in b)


@pytest.fixture(scope="module")
def cve_pair(network):
    mounts = [(os.path.join(CONFIGS, "cve", "default.conf"), "/etc/nginx/conf.d/default.conf")]
    with Pair(network, "cve", mounts=mounts) as p:
        yield p


def probe(container):
    results = [request(container.ports[80], path=p) for p in PATHS for _ in range(10)]
    time.sleep(0.5)
    return results, container.logs()


def test_patched_image_rejects_mapping(cve_pair):
    results, logs = probe(cve_pair.new)
    assert [(r.status, r.body) for r in results] == [(200, b"")] * len(results)
    assert logs.count(ALERT) == len(results)
    assert "exited on signal" not in logs
    # alias without rewrite keeps working
    ok = request(cve_pair.new.ports[80], path="/static/index.html")
    assert ok.status == 200 and b"Welcome to nginx!" in ok.body


def test_original_image_detects_vulnerability(cve_pair):
    """The test can see the bug: every /foo/1 body is non-printable bytes + "/x"."""
    results, logs = probe(cve_pair.orig)
    print(f"\noriginal image /foo/1 -> {results[0].status} body={results[0].body!r} "
          f"(len {len(results[0].body)}); alert_logged={ALERT in logs} "
          f"worker_crash={'exited on signal' in logs}")
    foo1 = results[:10]  # PATHS[0] x 10
    assert all(r.status == 200 for r in foo1)
    for r in foo1:
        assert r.body.endswith(LEAK_TAIL), r.body
        leaked = r.body[: -len(LEAK_TAIL)]
        assert leaked, r.body
        assert not printable(leaked), r.body
