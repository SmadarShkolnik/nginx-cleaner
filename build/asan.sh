#!/usr/bin/env bash
# DIAGNOSTIC — not part of `make all`, not a shipped artifact.
#
# Build nginx 1.25.5 with AddressSanitizer twice (without and with our
# CVE-2026-15176 backport) and run the upstream reproducer `GET /foo/1`.
# Expectation:
#   - unpatched: ASan reports a memory error in ngx_http_map_uri_to_path()
#     (with this reproducer: negative-size-param in memcpy, because the
#     rewritten URI "/x" is shorter than the location prefix "/foo/")
#   - patched:   no ASan error; the alias mapping is refused with an [alert]
#
# This is the memory-safety counterpart to test/test_cve_2026_15176.py (which
# observes the leaked *bytes* over HTTP); ASan shows the *overflow* directly.
#
# Runs inside debian:bookworm-slim (see `make asan`). Single process
# (master_process off) so the worker's ASan report lands on our captured stderr.
# Output: $OUT/asan-unpatched.log, $OUT/asan-patched.log
#
# NOTE: written offline while Docker was unavailable; run it for real with
# `make asan` and record the output before citing it as proof.
set -euxo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=versions.env
. "$HERE/versions.env"
OUT="${OUT:-/asan-out}"
WORK="${WORK:-/asan}"
PATCH="$HERE/patches/nginx/CVE-2026-15176.patch"
mkdir -p "$OUT" "$WORK"
cd "$WORK"

fetch() { curl -fsSL --retry 3 -o "$2" "$1"; echo "$4  $2" | "${3}sum" -c -; }
fetch "https://nginx.org/download/nginx-${NGINX_VERSION}.tar.gz" nginx.tar.gz sha256 "$NGINX_SRC_SHA256"

# Reproducer config. alias target is /tmp/ (exists); rewrite has no break/last.
cat > "$WORK/nginx.conf" <<'EOF'
daemon off;
master_process off;
error_log /dev/stderr info;
pid /tmp/asan-nginx.pid;
events { worker_connections 64; }
http {
    access_log off;
    server {
        listen 127.0.0.1:8080;
        location /foo/ {
            alias /tmp/;
            rewrite ^/foo/.*$ /x;
            return 200 $request_filename;
        }
    }
}
EOF

build_and_probe() { # <label> <apply_patch:0|1>
    local label="$1" apply="$2"
    local log="$OUT/asan-${label}.log"
    rm -rf "nginx-${NGINX_VERSION}"
    tar -xzf nginx.tar.gz
    ( cd "nginx-${NGINX_VERSION}"
      if [ "$apply" = 1 ]; then patch -p1 < "$PATCH"; fi
      # rewrite module needs PCRE; keep the build minimal otherwise.
      ./configure \
          --with-cc-opt='-fsanitize=address -fno-omit-frame-pointer -g -O0' \
          --with-ld-opt='-fsanitize=address' \
          --http-log-path=/dev/stdout --error-log-path=/dev/stderr \
          --without-http_gzip_module >/dev/null
      make -j"$(nproc)" >/dev/null )

    : > "$log"
    # halt_on_error=0: report the overflow but keep serving so curl gets a reply.
    ASAN_OPTIONS=halt_on_error=0:detect_leaks=0:abort_on_error=0 \
        "nginx-${NGINX_VERSION}/objs/nginx" -p "$WORK" -c "$WORK/nginx.conf" \
        >>"$log" 2>&1 &
    local pid=$!
    sleep 1
    curl -s -o /dev/null "http://127.0.0.1:8080/foo/1" || true
    sleep 1
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true

    echo "=== ${label}: ASan summary ==="
    if grep -q "ERROR: AddressSanitizer" "$log"; then
        echo "${label}: ASan error REPORTED"
        grep -nE "ERROR: AddressSanitizer|ngx_http_map_uri_to_path" "$log" | head
    else
        echo "${label}: no ASan error"
        grep -n "cannot be used in location" "$log" | head || true
    fi
}

build_and_probe unpatched 0
build_and_probe patched 1

echo "=== verdict ==="
if grep -q "ERROR: AddressSanitizer" "$OUT/asan-unpatched.log" \
   && grep -A3 "ERROR: AddressSanitizer" "$OUT/asan-unpatched.log" | grep -q "ngx_http_map_uri_to_path" \
   && ! grep -q "ERROR: AddressSanitizer" "$OUT/asan-patched.log"; then
    echo "PASS: ASan error in ngx_http_map_uri_to_path() only in the unpatched build"
else
    echo "CHECK: inspect $OUT/asan-unpatched.log and $OUT/asan-patched.log"
    exit 1
fi
