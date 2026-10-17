"""CVE-2026-15176 regression test (behaviour is EXPECTED to differ from the original).

Upstream reproducer (nginx commit ce1da78): a location with "alias" + "rewrite"
(no break/last) + a directive that evaluates $request_filename. Before the fix,
the URI-to-path mapping runs with the rewritten (shorter) URI: the buffer is
sized for the wrong length and the copy runs past it. On the original image the
response body therefore contains heap bytes in front of "/x".

With the backport, ngx_http_map_uri_to_path() refuses the mapping and logs an
alert; $request_filename evaluates to nothing, so the body is empty. Workers
keep running.
"""
import os
import time

import pytest

from harness import CONFIGS, Pair, request

ALERT = '"alias" cannot be used in location "/foo/" where URI was rewritten'
PATHS = ["/foo/1", "/foo/" + "A" * 64]
# The rewrite sends the URI to "/x", so a response that actually ran the mapping
# ends with this 2-byte marker; anything in front of it is leaked heap.
LEAK_TAIL = b"/x"


def printable(b):
    """A real filesystem path is printable ASCII; heap over-read bytes are not."""
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
    """Proves the test can SEE the bug: the unpatched build leaks a body for /foo/1."""
    results, logs = probe(cve_pair.orig)
    print(f"\noriginal image /foo/1 -> {results[0].status} body={results[0].body!r} "
          f"(len {len(results[0].body)}); alert_logged={ALERT in logs} "
          f"worker_crash={'exited on signal' in logs}")
    # /foo/1 is PATHS[0], repeated 10 times -> results[0:10].
    foo1 = results[:10]
    assert all(r.status == 200 for r in foo1)
    # Assert the LEAK SIGNATURE, not just "non-empty". $request_filename is built
    # by copying into a buffer sized for the rewritten URI ("/x"), but the copy
    # uses the longer original reservation, so the body is [leaked heap bytes] + "/x".
    # For every /foo/1:
    #   1. it ends with the rewrite marker "/x" -> the mapping actually ran, and
    #   2. the bytes BEFORE that marker are non-printable -> they are heap, not a
    #      path (a filesystem path is printable ASCII).
    for r in foo1:
        assert r.body.endswith(LEAK_TAIL), r.body            # reproducer fired
        leaked = r.body[: -len(LEAK_TAIL)]
        assert leaked, r.body                                # bytes exist before "/x"
        assert not printable(leaked), r.body                 # ...and they are not a path
    # Why this cannot pass by accident:
    #  - The patched image returns b"" (see test_patched_image_rejects_mapping):
    #    empty body does not end with "/x", so a fixed build fails step 1.
    #  - A correct, non-leaking mapping would set $request_filename to a printable
    #    filesystem path (or empty); either way step 2 (non-printable prefix) fails.
    #  Only the out-of-bounds copy produces "/x" with a non-printable heap prefix,
    #  so the assertion keys on the over-read itself, not on response length.
