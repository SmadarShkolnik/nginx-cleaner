# Builds the .debs from source on a clean debian:bookworm-slim.
#   docker build --build-arg BASE_IMAGE=... -f build/Dockerfile --output type=local,dest=out/debs build/
# BASE_IMAGE is the digest-pinned debian:bookworm-slim, set in the Makefile (`make deb`).
ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential ca-certificates curl debhelper devscripts dpkg-dev \
        fakeroot file git libxml2-utils lsb-release quilt xsltproc xz-utils \
    && echo 'DEBUILD_LINTIAN=no' > /root/.devscripts

COPY build.sh versions.env /src/
# Step 1 - OpenSSL. Cached independently of the nginx patches copied below, so
# editing a patch does not rebuild OpenSSL. Full log stays in the stage; on
# failure print its tail.
RUN /src/build.sh openssl > /build-openssl.log 2>&1 \
    || { tail -n 150 /build-openssl.log; exit 1; }

# Step 2 - nginx + modules, with our backport patches. Patches are copied here
# (after step 1) so changing a patch only re-runs this layer.
COPY patches /src/patches
RUN /src/build.sh nginx > /build-nginx.log 2>&1 \
    || { tail -n 150 /build-nginx.log; exit 1; }

FROM scratch AS export
COPY --from=builder /out/ /