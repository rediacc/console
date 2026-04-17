ARG BASE_IMAGE=ubuntu:24.04
FROM ${BASE_IMAGE}
ARG BASE_IMAGE
LABEL com.rediacc.base-image="${BASE_IMAGE}"

WORKDIR /repo

# `apt-get update` is wrapped in a retry loop because archive.ubuntu.com
# mirrors occasionally serve a stale Packages.gz whose checksum no longer
# matches the freshly-uploaded InRelease ("File has unexpected size, Mirror
# sync in progress?"). Apt caches the bad InRelease, so each retry must
# purge /var/lib/apt/lists first to force a fresh metadata download. See
# https://bugs.launchpad.net/ubuntu/+source/apt/+bug/2107223 (open upstream).
RUN for i in 1 2 3 4 5; do \
        if apt-get update; then break; fi; \
        if [ "$i" = "5" ]; then echo "apt-get update failed after 5 attempts" >&2; exit 1; fi; \
        echo "apt-get update attempt $i/5 failed, purging cache and retrying..." >&2; \
        rm -rf /var/lib/apt/lists/*; \
        sleep 15; \
    done && \
    apt-get install -y curl tar && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Install filebrowser - pinned version for reliable CI builds
# GitHub API can be rate-limited, causing dynamic version lookup to fail
# Update FILEBROWSER_VERSION manually when upgrading
ARG FILEBROWSER_VERSION=2.55.0
RUN curl -fsSL "https://github.com/filebrowser/filebrowser/releases/download/v${FILEBROWSER_VERSION}/linux-amd64-filebrowser.tar.gz" | tar -xz -C /usr/local/bin && \
    chmod +x /usr/local/bin/filebrowser

# Environment variables for socket configuration
ENV SOCKET_DIR=/sockets
ENV PLUGIN_NAME=Browser

ENTRYPOINT ["/bin/bash", "-c"]

CMD ["cd /tmp && \
    filebrowser \
    --disable-exec \
    --disable-preview-resize \
    --disable-thumbnails \
    --disable-type-detection-by-header \
    --noauth \
    --root /repo \
    --socket ${SOCKET_DIR}/${PLUGIN_NAME}.sock \
    --socket-perm 384"]
