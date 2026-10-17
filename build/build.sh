#!/usr/bin/env bash
# Build the .debs for our nginx:1.25-bookworm replacement from source.
#
#   1. OpenSSL: upstream 3.0.22 tarball + Debian's packaging  -> libssl3, openssl, libssl-dev
#      (version bump 3.0.11 -> 3.0.22; fixes CVE-2025-15467, CVE-2024-5535)
#   2. nginx 1.25.5 + modules via nginx.org's pkg-oss, with patches/nginx/*.patch applied
#      (backport of upstream ce1da78; fixes CVE-2026-15176)
#
# Runs inside debian:bookworm-slim (see build/Dockerfile). Every download is
# checked against a hash pinned in versions.env. Output: $OUT/*.deb
set -euxo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=versions.env
. "$HERE/versions.env"

WORK="${WORK:-/build}"
OUT="${OUT:-/out}"
NPROC="$(nproc)"
export DEBEMAIL="build@echo.invalid" DEBFULLNAME="Echo image build"
export DEBIAN_FRONTEND=noninteractive
mkdir -p "$WORK" "$OUT"

fetch() { # fetch <url> <dest> <algo> <hash>
    curl -fsSL --retry 3 -o "$2" "$1"
    echo "$4  $2" | "${3}sum" -c -
}

# --------------------------------------------------------------------------
# 1. OpenSSL version bump
# --------------------------------------------------------------------------
build_openssl() {
    local dir="$WORK/openssl" src
    mkdir -p "$dir" && cd "$dir"
    fetch "$OPENSSL_URL" "openssl_${OPENSSL_VERSION}.orig.tar.gz" sha256 "$OPENSSL_SHA256"
    fetch "$OPENSSL_DEBIAN_URL" openssl.debian.tar.xz sha256 "$OPENSSL_DEBIAN_SHA256"

    src="openssl-${OPENSSL_VERSION}"
    tar -xzf "openssl_${OPENSSL_VERSION}.orig.tar.gz"
    tar -C "$src" -xJf openssl.debian.tar.xz

    cd "$src"
    dch --newversion "$OPENSSL_DEB_VERSION" --force-distribution --distribution bookworm \
        "Rebuild from upstream OpenSSL ${OPENSSL_VERSION} tarball (version bump from 3.0.11)."
    apt-get build-dep -y --no-install-recommends ./

    # nocheck: skip OpenSSL's test suite to keep builds fast.
    # -B: arch-dependent packages only (skips libssl-doc); noudeb: skip installer udebs.
    DEB_BUILD_OPTIONS="nocheck parallel=$NPROC" DEB_BUILD_PROFILES="noudeb" \
        dpkg-buildpackage -B -us -uc

    cd "$dir"
    # Install our OpenSSL into the build root so nginx compiles and links against it.
    apt-get install -y --no-install-recommends --allow-downgrades \
        "./libssl3_${OPENSSL_DEB_VERSION}_"*.deb \
        "./libssl-dev_${OPENSSL_DEB_VERSION}_"*.deb \
        "./openssl_${OPENSSL_DEB_VERSION}_"*.deb
    cp libssl3_*.deb libssl-dev_*.deb openssl_*.deb "$OUT/"
}

# --------------------------------------------------------------------------
# 2. nginx 1.25.5 + modules (pkg-oss), with our backport patches
# --------------------------------------------------------------------------
build_nginx() {
    # nginx.org builds under /data/builder/debuild/nginx-<ver>; the path ends up in
    # -ffile-prefix-map inside `nginx -V`, so build at the same place to keep it identical.
    local builddir="/data/builder/debuild"
    local pkgoss="$builddir/nginx-$NGINX_VERSION" contrib
    mkdir -p "$builddir"
    git init -q "$pkgoss" && cd "$pkgoss"
    git remote add origin "$PKG_OSS_REPO"
    git fetch -q --depth 1 origin "$PKG_OSS_COMMIT"
    git checkout -q FETCH_HEAD
    contrib="$pkgoss/contrib"

    # The nginx tarball itself is fetched by pkg-oss and checked against its SHA512SUMS.
    # Two sources moved from hg.nginx.org to GitHub after this commit; repoint them.
    mkdir -p "$contrib/tarballs"
    fetch "$NJS_URL" "$contrib/tarballs/njs-${NJS_VERSION}.tar.gz" sha512 "$NJS_SHA512"
    echo "$NJS_SHA512  njs-${NJS_VERSION}.tar.gz" > "$contrib/src/njs/SHA512SUMS"

    echo "XSLSCRIPT_VERSION := $XSLSCRIPT_VERSION" > "$contrib/src/xslscript/version"
    echo "$XSLSCRIPT_SHA512  xslscript-${XSLSCRIPT_VERSION}.tar.gz" > "$contrib/src/xslscript/SHA512SUMS"
    sed -i 's#^XSLSCRIPT_URL.*#XSLSCRIPT_URL := $(GITHUB)/nginx/xslscript/archive/$(XSLSCRIPT_VERSION).tar.gz#' \
        "$contrib/src/xslscript/Makefile"

    # pkg-oss adds every contrib/src/nginx/*.patch to debian/patches/series of the
    # base package and of every module package.
    cp "$HERE"/patches/nginx/*.patch "$contrib/src/nginx/"

    cd "$pkgoss/debian"
    local releases=(
        "BASE_RELEASE=1${ECHO_SUFFIX}"
        "MODULE_RELEASE_njs=3${ECHO_SUFFIX}"
        "MODULE_RELEASE_xslt=1${ECHO_SUFFIX}"
        "MODULE_RELEASE_geoip=1${ECHO_SUFFIX}"
        "MODULE_RELEASE_image_filter=1${ECHO_SUFFIX}"
    )
    local targets=(base module-njs module-xslt module-geoip module-image-filter)

    # Generate the debian/ source trees, install their Build-Depends, then build.
    make "${releases[@]}" rules-base rules-module-njs rules-module-xslt \
        rules-module-geoip rules-module-image-filter
    for d in debuild-*/nginx-"$NGINX_VERSION"; do
        apt-get build-dep -y --no-install-recommends "./$d"
    done
    make "${releases[@]}" "${targets[@]}"

    # Every compiled tree must carry the backport in its quilt series. dpkg-source
    # applies the series before building (and fails if a patch does not apply),
    # then un-applies it again after the build.
    for d in debuild-*/nginx-"$NGINX_VERSION"; do
        for p in "$HERE"/patches/nginx/*.patch; do
            grep -qx "$(basename "$p")" "$d/debian/patches/series"
        done
    done

    # pkg-oss copies the built packages two levels up from debian/.
    cd "$builddir"
    find . -maxdepth 1 -name 'nginx*.deb' ! -name '*-dbg_*' -exec cp {} "$OUT/" \;
}

# Each stage can be built on its own so the Dockerfile can cache them separately.
#   build.sh openssl   -> OpenSSL debs only
#   build.sh nginx     -> nginx + modules (needs OpenSSL already built/installed)
#   build.sh [all]     -> both (default)
case "${1:-all}" in
    openssl) build_openssl ;;
    nginx)   build_nginx ;;
    all)     build_openssl; build_nginx ;;
    *)       echo "usage: build.sh [openssl|nginx|all]" >&2; exit 2 ;;
esac
ls -l "$OUT"
