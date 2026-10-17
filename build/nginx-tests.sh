#!/usr/bin/env bash
# DIAGNOSTIC — not part of `make all`, not a shipped artifact.
#
# Run the upstream nginx test suite (nginx/nginx-tests) against the nginx binary
# INSIDE a given image, so we exercise the exact shipped binary (ours = patched,
# or the original for comparison). `make nginx-tests` runs this for both images
# and scripts/nginx_tests_compare.py diffs the results: the only allowed new
# failure is the one caused by the CVE-2026-15176 backport.
#
#   usage: nginx-tests.sh <image> <outdir>
#
# Pinned nginx-tests commit (github.com/nginx/nginx-tests), resolved 2026-10-16.
# NOTE: written offline while Docker was unavailable; run it for real with
# `make nginx-tests` and record the output before citing it.
set -euxo pipefail

IMAGE="${1:?usage: nginx-tests.sh <image> <outdir>}"
OUTDIR="${2:?usage: nginx-tests.sh <image> <outdir>}"
NGINX_TESTS_COMMIT="ec44bc80c4bfac1dbd8ffee3875101285f8502ac"
mkdir -p "$OUTDIR"

# Test subset: http core + the directives the backport touches + ssl + modules.
# Globbed names (alias*/rewrite*/map*) catch whatever this revision ships.
SELECT='proxy.t rewrite.t rewrite_if.t rewrite_set.t map.t map_complex.t
        alias*.t ssl.t ssl_sni.t js.t xslt.t image_filter.t geoip.t'

# The harness runs in a container started FROM the image, so TEST_NGINX_BINARY is
# the nginx actually shipped in it. apt lists are stripped in the image, so update.
docker run --rm -e SELECT="$SELECT" -e COMMIT="$NGINX_TESTS_COMMIT" \
    -v "$OUTDIR:/out" --entrypoint sh "$IMAGE" -ec '
    apt-get update >/dev/null
    apt-get install -y --no-install-recommends \
        perl libio-socket-ssl-perl libcryptx-perl git ca-certificates >/dev/null
    git init -q /nt && cd /nt
    git remote add origin https://github.com/nginx/nginx-tests.git
    git fetch -q --depth 1 origin "$COMMIT"
    git checkout -q FETCH_HEAD
    export TEST_NGINX_BINARY=/usr/sbin/nginx TEST_NGINX_MODULES=/usr/lib/nginx/modules
    : > /out/summary.txt
    for pat in $SELECT; do
        for t in $pat; do
            [ -e "$t" ] || continue
            if prove -v "$t" > "/out/${t}.tap" 2>&1; then
                echo "PASS $t" >> /out/summary.txt
            else
                echo "FAIL $t" >> /out/summary.txt
            fi
        done
    done
    echo "=== summary for '"$IMAGE"' ==="; cat /out/summary.txt
'
