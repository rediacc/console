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
            && apt-get -o Acquire::Retries=3 install -y curl; then \
            break; \
        fi; \
        if [ "$i" = "5" ]; then echo "apt operations failed after 5 attempts" >&2; exit 1; fi; \
        echo "apt attempt $i/5 failed, retrying in $((i * 30))s..." >&2; \
        sleep $((i * 30)); \
    done && \
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
