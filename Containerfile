# Drop-in replacement for nginx:1.25-bookworm, installed from our own .debs (out/debs, see build/).
# Mirrors docker-nginx mainline/debian/Dockerfile at commit 9abe4ae (nginx 1.25.5, njs 0.8.4-3):
# same base, user/group, packages, env, entrypoint scripts, ports, stop signal and command.
#   docker build -f Containerfile -t echo/nginx:1.25-bookworm .
FROM debian:bookworm-slim

LABEL maintainer="NGINX Docker Maintainers <docker-maint@nginx.com>"

ENV NGINX_VERSION   1.25.5
ENV NJS_VERSION     0.8.4
ENV NJS_RELEASE     3~bookworm
ENV PKG_RELEASE     1~bookworm

RUN --mount=type=bind,source=out/debs,target=/tmp/debs \
    set -x \
# create nginx user/group first, to be consistent throughout docker variants
    && groupadd --system --gid 101 nginx \
    && useradd --system --gid nginx --no-create-home --home /nonexistent --comment "nginx user" --shell /bin/false --uid 101 nginx \
    && apt-get update \
    && apt-get install --no-install-recommends --no-install-suggests -y \
        ca-certificates \
        /tmp/debs/libssl3_*.deb \
        /tmp/debs/openssl_*.deb \
        /tmp/debs/nginx_*.deb \
        /tmp/debs/nginx-module-xslt_*.deb \
        /tmp/debs/nginx-module-geoip_*.deb \
        /tmp/debs/nginx-module-image-filter_*.deb \
        /tmp/debs/nginx-module-njs_*.deb \
        gettext-base \
        curl \
    && rm -rf /var/lib/apt/lists/* \
# forward request and error logs to docker log collector
    && ln -sf /dev/stdout /var/log/nginx/access.log \
    && ln -sf /dev/stderr /var/log/nginx/error.log \
# create a docker-entrypoint.d directory
    && mkdir /docker-entrypoint.d

COPY rootfs/docker-entrypoint.sh /
COPY rootfs/docker-entrypoint.d/10-listen-on-ipv6-by-default.sh /docker-entrypoint.d
COPY rootfs/docker-entrypoint.d/15-local-resolvers.envsh /docker-entrypoint.d
COPY rootfs/docker-entrypoint.d/20-envsubst-on-templates.sh /docker-entrypoint.d
COPY rootfs/docker-entrypoint.d/30-tune-worker-processes.sh /docker-entrypoint.d
ENTRYPOINT ["/docker-entrypoint.sh"]

EXPOSE 80

STOPSIGNAL SIGQUIT

CMD ["nginx", "-g", "daemon off;"]
