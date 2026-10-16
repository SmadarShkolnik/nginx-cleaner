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


def test_original_image_behaviour_recorded(cve_pair):
    """Not asserted: shows what the unpatched build returns for the same request."""
    results, logs = probe(cve_pair.orig)
    print(f"\noriginal image /foo/1 -> {results[0].status} body={results[0].body!r} "
          f"(len {len(results[0].body)}); alert_logged={ALERT in logs} "
          f"worker_crash={'exited on signal' in logs}")
