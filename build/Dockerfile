# Builds the .debs from source on a clean debian:bookworm-slim.
#   docker build -f build/Dockerfile.build --output type=local,dest=out/debs build/
FROM debian:bookworm-slim AS builder

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