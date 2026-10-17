# Builds the .debs from source on a clean debian:bookworm-slim.
#   docker build -f build/Dockerfile --output type=local,dest=out/debs build/
# Base pinned by digest (DEBIAN_BASE_DIGEST in versions.env) for reproducibility;
# keep this digest and the Containerfile's in sync with versions.env.
FROM debian:bookworm-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587 AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential ca-certificates curl debhelper devscripts dpkg-dev \
        fakeroot file git libxml2-utils lsb-release quilt xsltproc xz-utils \
    && echo 'DEBUILD_LINTIAN=no' > /root/.devscripts

COPY build.sh versions.env /src/
# OPENSSL_CHECK=1 runs OpenSSL's test suite (default 0 = nocheck, fast).
# Passed from the Makefile via --build-arg; changing it re-runs the OpenSSL step.
ARG OPENSSL_CHECK=0
# Step 1 - OpenSSL. Cached independently of the nginx patches copied below, so
# editing a patch does not rebuild OpenSSL. Full log stays in the stage; on
# failure print its tail.
RUN OPENSSL_CHECK=${OPENSSL_CHECK} /src/build.sh openssl > /build-openssl.log 2>&1 \
    || { tail -n 150 /build-openssl.log; exit 1; }

# Step 2 - nginx + modules, with our backport patches. Patches are copied here
# (after step 1) so changing a patch only re-runs this layer.
COPY patches /src/patches
RUN /src/build.sh nginx > /build-nginx.log 2>&1 \
    || { tail -n 150 /build-nginx.log; exit 1; }

FROM scratch AS export
COPY --from=builder /out/ /