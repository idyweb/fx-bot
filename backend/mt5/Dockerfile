# Stage 1: Base image with apt packages
FROM ghcr.io/linuxserver/baseimage-kasmvnc:debianbookworm AS base

ENV TITLE=MetaTrader
ENV WINEARCH=win64
ENV WINEPREFIX="/config/.wine"
ENV DISPLAY=:0
ENV HOME=/config
ENV DEBIAN_FRONTEND=noninteractive

# Ensure the directory exists with correct permissions
RUN mkdir -p /config/.wine && \
    chown -R abc:abc /config/.wine && \
    chmod -R 755 /config/.wine && \
    mkdir -p /tmp/runtime-abc && \
    chown abc:abc /tmp/runtime-abc && \
    chmod 700 /tmp/runtime-abc

# Install Wine and dependencies from Bookworm repositories
RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        wine \
        wine32 \
        wine64 \
        libwine \
        fonts-wine \
        cabextract \
        dos2unix \
        python3-pip \
        python3-full \
        wget \
        unzip \
        netcat-openbsd \
        xvfb \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Stage 2: Final Image
# We skip the complex build-time Wine setup because it causes ownership issues
# and relies on the fragile volume-baked prefix anyway.
FROM base

COPY app /app
COPY scripts /scripts
RUN dos2unix /scripts/*.sh && \
    chmod +x /scripts/*.sh

COPY /root /
RUN touch /var/log/mt5_setup.log && \
    chown abc:abc /var/log/mt5_setup.log && \
    chmod 644 /var/log/mt5_setup.log

EXPOSE 3000 5000 5001 8001 18812
VOLUME /config
