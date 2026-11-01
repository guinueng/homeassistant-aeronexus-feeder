FROM ghcr.io/home-assistant/base:3.24
ARG BUILD_VERSION=1.1.3

RUN apk add --no-cache python3 \
    && addgroup -S aeronexus \
    && adduser -S -D -H -G aeronexus aeronexus

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY rootfs /

RUN chmod 0755 /etc/s6-overlay/s6-rc.d/aeronexus/run \
    /etc/s6-overlay/s6-rc.d/aeronexus/finish \
    && printf '%s\n' "${BUILD_VERSION}" > /usr/local/lib/aeronexus/app-version
