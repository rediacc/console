ARG BASE_IMAGE=ubuntu:24.04
FROM ${BASE_IMAGE}
ARG BASE_IMAGE
LABEL com.rediacc.base-image="${BASE_IMAGE}"

WORKDIR /repo

# Switch to the Azure-hosted Ubuntu mirror. archive.ubuntu.com routinely
# becomes completely unreachable from Azure-hosted GitHub runners for
# 5-30 minute windows (Microsoft Azure <-> Canonical CDN routing flakes),
# and no amount of retrying inside the build makes that work. The Azure
# mirror is in the same data centers as the runners and effectively never
# loses connectivity from them. The retry-with-purge loop stays as defence
# in depth for the rarer "Mirror sync in progress / File has unexpected
# size" race (launchpad #2107223). Acquire::http::Timeout=30 fails each
# stuck HTTP request fast (default is 120s) so a bad attempt does not eat
# 20 minutes before the next retry begins.
RUN find /etc/apt -name 'ubuntu.sources' -o -name 'sources.list' 2>/dev/null \
        | xargs -r sed -i \
            -e 's|http://archive\.ubuntu\.com/ubuntu|http://azure.archive.ubuntu.com/ubuntu|g' \
            -e 's|http://security\.ubuntu\.com/ubuntu|http://azure.archive.ubuntu.com/ubuntu|g' \
    && for i in 1 2 3 4 5; do \
        rm -rf /var/lib/apt/lists/*; \
        if apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 update \
            && apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 install -y curl; then \
            break; \
        fi; \
        if [ "$i" = "5" ]; then echo "apt operations failed after 5 attempts" >&2; exit 1; fi; \
        echo "apt attempt $i/5 failed, retrying in $((i * 30))s..." >&2; \
        sleep $((i * 30)); \
    done \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

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
