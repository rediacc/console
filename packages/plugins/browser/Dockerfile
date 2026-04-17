ARG BASE_IMAGE=ubuntu:24.04
FROM ${BASE_IMAGE}
ARG BASE_IMAGE
LABEL com.rediacc.base-image="${BASE_IMAGE}"

WORKDIR /repo

# Retry-with-purge wrapper around apt-get update + install. Handles both
# (1) the recurring "Mirror sync in progress / File has unexpected size" race
# (launchpad #2107223) that requires purging /var/lib/apt/lists between
# attempts, and (2) outright Azure-runner-to-archive.ubuntu.com network
# outages observed to last 5-10 minutes. Both update and install must be
# inside the loop because the install fetches .deb files from the same
# upstream mirrors that fail in either failure mode. Acquire::Retries=3
# layers HTTP-level retries inside each apt call.
RUN for i in 1 2 3 4 5; do \
        rm -rf /var/lib/apt/lists/*; \
        if apt-get -o Acquire::Retries=3 update \
            && apt-get -o Acquire::Retries=3 install -y curl tar; then \
            break; \
        fi; \
        if [ "$i" = "5" ]; then echo "apt operations failed after 5 attempts" >&2; exit 1; fi; \
        echo "apt attempt $i/5 failed, retrying in $((i * 30))s..." >&2; \
        sleep $((i * 30)); \
    done && \
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
