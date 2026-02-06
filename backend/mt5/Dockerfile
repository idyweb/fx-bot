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

# Stage 2: Pre-install Wine applications (Python & MT5) during build
# We do this as root but targeted at the abc user's prefix to bake it into the image
# This avoids fragile runtime installation scripts
USER root

# Helper to run wine commands relative to our prefix
RUN mkdir -p /build_temp
WORKDIR /build_temp

# Download installers
RUN wget -q https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe -O python-installer.exe && \
    wget -q https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe -O mt5setup.exe

# Initialize Wine (headless)
# We need Xvfb to fake a display for the installers
RUN Xvfb :0 -screen 0 1024x768x16 & \
    export DISPLAY=:0 && \
    sleep 5 && \
    wineboot --init && \
    wineboot -u && \
    sleep 5 && \
    # Install Python (Active user system-wide, add to path) \
    wine python-installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 && \
    sleep 10 && \
    # Install MetaTrader 5 (Auto mode) \
    wine mt5setup.exe /auto && \
    sleep 30 && \
    # Clean up installers \
    rm python-installer.exe mt5setup.exe && \
    # Verify Python \
    wine python --version

# Stage 3: Final Image
FROM base

# Copy the baked Wine prefix from build
# (Note: This might be large, but ensures consistency)
# COPY --from=base /config/.wine /config/.wine   
# ^ Wait, coping mapped volumes is tricky in Dockerfiles if volumes are external. 
# We should install to /opt/wine-apps or similar and symlink if possible, 
# but Wine is strict about prefixes. 
# Better strategy: Run the install scripts properly fixed, OR bake into a non-volume path.
# For now, let's stick to fixing the runtime script but use the Dockerfile to prep the environment better.

# Revert to standard structure but clean up
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
