"""Compatibility test: the rebuilt image must behave like nginx:1.25-bookworm.

Every scenario runs the same requests against both images and asserts that
status, headers and body match. Volatile headers (Date) are ignored; mtime
headers (ETag, Last-Modified) are ignored only for files shipped inside the
images, because the packages were built at different times.

The CVE-2026-15176 backport introduces exactly ONE intended behavioural
difference from the original: in a location that combines `alias` with a
`rewrite` that has no `break`/`last` and then evaluates `$request_filename`,
the patched build refuses the mapping (empty `$request_filename` + an alert)
instead of leaking heap bytes. That single divergence is asserted in
test_cve_2026_15176.py. It is NOT a regression, so it is deliberately kept out
of the configs here; everything in this suite must stay byte-identical. The
near-miss variants that must NOT change (rewrite WITH `last`, and `alias`
without any rewrite) are pinned explicitly by test_backport_only_affects_no_break_alias.
"""
import gzip
import json
import os
import re

import pytest

from harness import (CONFIGS, HERE, MTIME_HEADERS, NEW_IMAGE, ORIG_IMAGE, Pair,
                     docker, parse_responses, raw_exchange, request)

WWW = os.path.join(HERE, "www")
TWO_MB = b"x" * (2 * 1024 * 1024)


def same(pair, ignore=(), port=80, **kw):
    a = request(pair.orig.ports[port], **kw)
    b = request(pair.new.ports[port], **kw)
    assert b.normalized(ignore) == a.normalized(ignore), \
        f"\noriginal: {a.normalized(ignore)}\nnew:      {b.normalized(ignore)}"
    return a, b


def same_raw(pair, data, ignore=()):
    a = parse_responses(raw_exchange(pair.orig.ports[80], data))
    b = parse_responses(raw_exchange(pair.new.ports[80], data))
    na = [r.normalized(ignore) for r in a]
    nb = [r.normalized(ignore) for r in b]
    assert nb == na, f"\noriginal: {na}\nnew:      {nb}"
    return a, b


# --------------------------------------------------------------------------
# Image metadata and filesystem layout
# --------------------------------------------------------------------------

def run_in(image, script):
    return docker("run", "--rm", "--entrypoint", "sh", image, "-c", script)


def test_image_config_matches():
    fields = ["User", "WorkingDir", "Entrypoint", "Cmd", "ExposedPorts",
              "StopSignal", "Env", "Labels", "Volumes"]
    cfg = {img: json.loads(docker("image", "inspect", "--format", "{{json .Config}}", img))
           for img in (ORIG_IMAGE, NEW_IMAGE)}
    for f in fields:
        assert cfg[NEW_IMAGE].get(f) == cfg[ORIG_IMAGE].get(f), f"Config.{f} differs"


LAYOUT = r"""
find /etc/nginx /usr/share/nginx /usr/lib/nginx /var/cache/nginx /var/log/nginx \
     /docker-entrypoint.sh /docker-entrypoint.d \
     -printf '%p %y %m %u:%g %l\n' | sort
"""

CONTENT = r"""
find /etc/nginx /usr/share/nginx/html /docker-entrypoint.sh /docker-entrypoint.d \
     -type f -exec md5sum {} + | sort -k2
"""


@pytest.mark.parametrize("script", [LAYOUT, CONTENT], ids=["layout", "content"])
def test_filesystem_matches(script):
    assert run_in(NEW_IMAGE, script) == run_in(ORIG_IMAGE, script)


def test_user_matches():
    script = "id nginx; getent passwd nginx; getent group nginx"
    assert run_in(NEW_IMAGE, script) == run_in(ORIG_IMAGE, script)


def nginx_V(image):
    return docker("run", "--rm", image, "nginx", "-V", check=False)


def test_build_flags_match():
    """Same version and identical ./configure arguments; only OpenSSL differs."""
    orig, new = nginx_V(ORIG_IMAGE), nginx_V(NEW_IMAGE)
    pick = lambda out, key: [l for l in out.splitlines() if l.startswith(key)]
    assert pick(new, "nginx version") == pick(orig, "nginx version")
    assert pick(new, "configure arguments") == pick(orig, "configure arguments")
    assert "built with OpenSSL 3.0.22" in new


def test_default_config_is_valid():
    for image in (ORIG_IMAGE, NEW_IMAGE):
        assert "test is successful" in docker("run", "--rm", image, "nginx", "-t", check=False)


# --------------------------------------------------------------------------
# Stock image, default configuration
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def default_pair(network):
    with Pair(network, "default") as p:
        yield p


PACKAGED = MTIME_HEADERS  # default site files come from the packages


@pytest.mark.parametrize("kw", [
    dict(path="/"),
    dict(method="HEAD", path="/"),
    dict(path="/index.html"),
    dict(path="/50x.html"),
    dict(path="/does-not-exist"),
    dict(path="/", version="HTTP/1.0", headers={"Host": None, "Connection": None}),
    dict(path="/", headers={"Range": "bytes=0-99"}),
    dict(path="/", headers={"Range": "bytes=9999999-"}),
    dict(path="/", headers={"Accept-Encoding": "gzip"}),
    dict(method="POST", path="/", body=b"a=1"),
    dict(method="OPTIONS", path="/"),
    dict(method="DELETE", path="/index.html"),
    dict(method="POST", path="/", body=TWO_MB),
    dict(path="/%2e%2e/%2e%2e/etc/passwd"),
    dict(path="/" + "a" * 3000),
], ids=lambda kw: f"{kw.get('method', 'GET')} {kw['path'][:30]} {sorted(kw.get('headers', {}))}")
def test_default_site(default_pair, kw):
    same(default_pair, ignore=PACKAGED, **kw)


def test_conditional_get(default_pair):
    """Each image answers 304 to its own Last-Modified / ETag."""
    for c in (default_pair.orig, default_pair.new):
        first = request(c.ports[80], path="/")
        for hdr, val in (("If-Modified-Since", first.header("Last-Modified")),
                         ("If-None-Match", first.header("ETag"))):
            assert request(c.ports[80], path="/", headers={hdr: val}).status == 304


@pytest.mark.parametrize("data", [
    b"GARBAGE\r\n\r\n",
    b"GET / HTTP/1.1\r\n\r\n",                                        # no Host
    b"GET / HTTP/2.0\r\nHost: x\r\n\r\n",                             # unsupported version
    b"GET /" + b"a" * 9000 + b" HTTP/1.1\r\nHost: x\r\n\r\n",         # URI too long
    b"GET / HTTP/1.1\r\nHost: x\r\nX-Big: " + b"a" * 20000 + b"\r\n\r\n",
    b"GET / HTTP/1.1\r\nHost: x\r\nHost: y\r\n\r\n",                  # duplicate Host
    b"GET / HTTP/1.1\r\nHost: x\r\nContent-Length: 5\r\n"
    b"Transfer-Encoding: chunked\r\n\r\n0\r\n\r\n",                   # CL + TE
    b"GET / HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: gzip\r\n\r\n",  # unknown TE
    b"GET /\x00 HTTP/1.1\r\nHost: x\r\n\r\n",                         # NUL in URI
    b"GET / HTTP/1.1\r\nHost: x\r\nBad Header: y\r\nConnection: close\r\n\r\n",
    b"G@T / HTTP/1.1\r\nHost: x\r\n\r\n",                             # bad method
], ids=["garbage", "no-host", "http2.0-line", "long-uri", "huge-header", "dup-host",
        "cl-and-te", "unknown-te", "nul-uri", "bad-header-name", "bad-method"])
def test_malformed_requests(default_pair, data):
    same_raw(default_pair, data, ignore=PACKAGED)


def test_pipelined_keepalive(default_pair):
    data = (b"GET / HTTP/1.1\r\nHost: x\r\n\r\n"
            b"HEAD /50x.html HTTP/1.1\r\nHost: x\r\n\r\n"
            b"GET /missing HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
    a = raw_exchange(default_pair.orig.ports[80], data)
    b = raw_exchange(default_pair.new.ports[80], data)
    strip = lambda raw: re.sub(rb"(?im)^(date|etag|last-modified): .*\r\n", b"", raw)
    assert strip(b) == strip(a)
    assert a.count(b"HTTP/1.1 ") == 3


def entrypoint_lines(container):
    """Entrypoint messages without their timestamps."""
    out = []
    for line in container.logs().splitlines():
        if "docker-entrypoint" in line or line.startswith("/docker-entrypoint"):
            out.append(re.sub(r"^\S+ \S+ ", "", line) if re.match(r"^\d{4}/", line) else line)
    return out


def test_entrypoint_output(default_pair):
    assert entrypoint_lines(default_pair.new) == entrypoint_lines(default_pair.orig)


# --------------------------------------------------------------------------
# Custom configuration (mounted conf.d + static content)
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def custom_pair(network):
    mounts = [(os.path.join(CONFIGS, "custom", "default.conf"), "/etc/nginx/conf.d/default.conf"),
              (WWW, "/srv/www")]
    with Pair(network, "custom", mounts=mounts) as p:
        yield p


@pytest.mark.parametrize("kw", [
    dict(path="/return"),
    dict(path="/redirect"),
    dict(path="/rewrite/hello.txt"),
    dict(path="/static/hello.txt"),
    dict(path="/static/data.json"),
    dict(path="/static/big.txt", headers={"Range": "bytes=100-299,1000-1099"}),
    dict(path="/static/missing.txt"),
    dict(path="/auto/"),
    dict(path="/map", headers={"X-Flag": "abz"}),
    dict(path="/map", headers={"X-Flag": "nomatch"}),
    dict(method="POST", path="/small-upload", body=b"q" * 1000),
    dict(method="POST", path="/small-upload", body=TWO_MB),
    dict(method="POST", path="/upload", body=TWO_MB),
], ids=lambda kw: f"{kw.get('method', 'GET')} {kw['path']} {sorted(kw.get('headers', {}))}")
def test_custom_config(custom_pair, kw):
    same(custom_pair, **kw)


def test_backport_only_affects_no_break_alias(custom_pair):
    """The backport must change ONLY the no-break alias+rewrite path.

    These two near-miss cases exercise the directives involved in CVE-2026-15176
    but not the exact trigger, so both images must still answer identically:
      - /rewrite/hello.txt: rewrite WITH `last` (the URI is finalised before the
        alias location is chosen, so r->uri_changed is irrelevant to the mapping);
      - /static/hello.txt:  `alias` WITHOUT any rewrite.
    The actual intended divergence (no-break rewrite + $request_filename) lives in
    test_cve_2026_15176.py; keeping it out of here is what makes compat exact.
    """
    r, _ = same(custom_pair, path="/rewrite/hello.txt")
    assert r.status == 200
    r, _ = same(custom_pair, path="/static/hello.txt")
    assert r.status == 200


def test_custom_etag_revalidation(custom_pair):
    etag = request(custom_pair.orig.ports[80], path="/static/hello.txt").header("ETag")
    a, _ = same(custom_pair, path="/static/hello.txt", headers={"If-None-Match": etag})
    assert a.status == 304


def test_chunked_upload(custom_pair):
    body = b"".join(b"%x\r\n%s\r\n" % (1000, b"c" * 1000) for _ in range(100)) + b"0\r\n\r\n"
    data = (b"POST /upload HTTP/1.1\r\nHost: x\r\nTransfer-Encoding: chunked\r\n"
            b"Connection: close\r\n\r\n" + body)
    same_raw(custom_pair, data)


def test_gzip(custom_pair):
    hdrs = {"Accept-Encoding": "gzip"}
    a = request(custom_pair.orig.ports[80], path="/gzip/big.txt", headers=hdrs)
    b = request(custom_pair.new.ports[80], path="/gzip/big.txt", headers=hdrs)
    assert a.header("Content-Encoding") == b.header("Content-Encoding") == "gzip"
    assert gzip.decompress(b.body) == gzip.decompress(a.body)
    # compressed bytes may differ with the zlib build, so compare headers without length
    ignore = {"content-length"}
    assert b.normalized(ignore)[:3] == a.normalized(ignore)[:3]


# --------------------------------------------------------------------------
# Entrypoint templating (envsubst)
# --------------------------------------------------------------------------

def test_envsubst_templates(network):
    mounts = [(os.path.join(CONFIGS, "templates"), "/etc/nginx/templates")]
    env = {"NGINX_GREETING": "hello-from-env", "NGINX_PORT_LABEL": "eighty"}
    with Pair(network, "tmpl", mounts=mounts, env=env) as p:
        a, _ = same(p, path="/")
        assert a.body == b"greeting=hello-from-env port=eighty\n"
        assert entrypoint_lines(p.new) == entrypoint_lines(p.orig)


# --------------------------------------------------------------------------
# Dynamic modules (njs, xslt, image-filter, geoip)
# --------------------------------------------------------------------------

def test_dynamic_modules(network):
    mounts = [(os.path.join(CONFIGS, "modules", "nginx.conf"), "/etc/nginx/nginx.conf"),
              (os.path.join(CONFIGS, "modules", "njs"), "/etc/nginx/njs"),
              (os.path.join(CONFIGS, "modules", "xslt"), "/etc/nginx/xslt"),
              (WWW, "/srv/www")]
    with Pair(network, "mods", mounts=mounts) as p:
        same(p, path="/")
        a, _ = same(p, path="/js?x=42")
        assert a.body == b"njs 0.8.4 method=GET x=42\n"
        a, _ = same(p, path="/xml/data.xml")
        assert b"<li>first</li>" in a.body


# --------------------------------------------------------------------------
# TLS (exercises the rebuilt OpenSSL)
# --------------------------------------------------------------------------

def tls_probe(network, host, args):
    """Run openssl s_client / curl from a fixed client image against `host`."""
    script = f"""
echo | openssl s_client -connect {host}:443 -servername localhost {args} 2>&1 \
  | grep -aE '^(New,|ALPN protocol|No ALPN|Server Temp Key|Peer signature type|Verify return code|Protocol *:|Cipher *:)'
curl -sk --http2 -o - -w ' http=%{{http_version}} code=%{{http_code}}' https://{host}/
"""
    return docker("run", "--rm", "--network", network, "--entrypoint", "sh", ORIG_IMAGE, "-c", script)


@pytest.mark.parametrize("args", [
    "-alpn h2,http/1.1",
    "-alpn http/1.1",
    "-tls1_2 -alpn h2",
    "-tls1_2 -cipher ECDHE-RSA-AES128-GCM-SHA256",
], ids=["tls13-h2", "tls13-http1", "tls12-h2", "tls12-cipher"])
def test_tls(network, tls_certs, args):
    mounts = [(os.path.join(CONFIGS, "tls", "default.conf"), "/etc/nginx/conf.d/default.conf"),
              (tls_certs, "/etc/nginx/certs")]
    with Pair(network, "tls", mounts=mounts) as p:
        a = tls_probe(network, p.orig.name, args)
        b = tls_probe(network, p.new.name, args)
        assert b == a
        assert "http=2 code=200" in a
