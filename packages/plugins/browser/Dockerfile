ARG BASE_IMAGE=ubuntu:24.04
FROM ${BASE_IMAGE}
ARG BASE_IMAGE
LABEL com.rediacc.base-image="${BASE_IMAGE}"

WORKDIR /repo

RUN apt-get update && apt-get install -y curl tar && \
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
