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
    apt-get install -y curl && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN curl -L "https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.$(uname -m)" -o /usr/local/bin/ttyd && \
    chmod +x /usr/local/bin/ttyd

# Environment variables for socket configuration
ENV SOCKET_DIR=/sockets
ENV PLUGIN_NAME=Terminal

ENTRYPOINT ["/bin/bash", "-c"]

CMD ["cd /tmp && \
    ttyd \
    --url-arg \
    --writable \
    --interface ${SOCKET_DIR}/${PLUGIN_NAME}.sock \
    /bin/bash"]
