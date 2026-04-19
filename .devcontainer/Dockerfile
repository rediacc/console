# Prebuilt devcontainer image for rediacc-console
# Bakes in Node, Go + tools, Python, GitHub CLI, Playwright deps,
# Claude Code, and @openai/codex to avoid slow feature installation at startup.
#
# Build:  docker buildx build --platform linux/amd64,linux/arm64 -t ghcr.io/rediacc/devcontainer:latest .
# Usage:  Referenced by devcontainer.json
#
# Rebuild: On PR (build only) or push to main (build + publish)

FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

ARG NODE_VERSION=22
ARG GO_VERSION=1.24.12

# Align the vscode user with the Rediacc universal UID/GID (7111). This matches
# common.RediaccUID in renet and the host-side ownership of /mnt/rediacc/...
# mounts, so files created inside the container have the same UID as everything
# else on the platform. Without this, a container running as vscode cannot
# access paths owned by the universal user. Must happen before any later
# `USER vscode` block so subsequent layers inherit the new UID.
RUN groupmod -g 7111 vscode \
    && usermod -u 7111 -g 7111 vscode \
    && find / -xdev \( -uid 1000 -o -gid 1000 \) -exec chown -h 7111:7111 {} + 2>/dev/null || true

# =============================================================================
# Telemetry opt-outs (apply image-wide to build steps and runtime processes).
# Each variable is verified against the tool's official documentation; do not
# add unverified flags here. Generic DO_NOT_TRACK=1 is the de-facto standard
# (honored by Turborepo, uv, and others). VS Code telemetry is disabled via a
# baked settings.json below, and Go telemetry via `go telemetry off` during
# the Go-tools install step (GOTELEMETRY is a read-only env per go.dev docs).
# =============================================================================
ENV DO_NOT_TRACK=1 \
    DISABLE_TELEMETRY=1 \
    DISABLE_ERROR_REPORTING=1 \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
    DOTNET_CLI_TELEMETRY_OPTOUT=1 \
    POWERSHELL_TELEMETRY_OPTOUT=1 \
    AZURE_CORE_COLLECT_TELEMETRY=0 \
    HOMEBREW_NO_ANALYTICS=1 \
    CHECKPOINT_DISABLE=1 \
    NEXT_TELEMETRY_DISABLED=1 \
    ASTRO_TELEMETRY_DISABLED=1 \
    GATSBY_TELEMETRY_DISABLED=1 \
    NUXT_TELEMETRY_DISABLED=1 \
    TURBO_TELEMETRY_DISABLED=1 \
    SAM_CLI_TELEMETRY=0

# =============================================================================
# System packages + GitHub CLI + Python 3 + XFCE Desktop + VNC stack
# =============================================================================
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
            && apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 install -y --no-install-recommends \
                build-essential \
                python3 \
                python3-pip \
                python3-venv \
                gh \
                jq \
                curl \
                wget \
                unzip \
                xdg-utils \
                tmux \
                vim \
                xvfb \
                libgtk-3-0 \
                libnotify4 \
                libnss3 \
                libxss1 \
                libxtst6 \
                libatspi2.0-0 \
                libsecret-1-0 \
                xfce4 \
                xfce4-terminal \
                x11vnc \
                novnc \
                websockify \
                dbus-x11 \
                netcat-openbsd \
                gnome-keyring \
                clang \
                llvm \
                libbpf-dev \
                linux-headers-generic \
                qemu-kvm \
                libvirt-daemon-system \
                libvirt-clients \
                bridge-utils \
                virtinst \
                cloud-image-utils \
                genisoimage \
                dnsmasq-base \
                iputils-ping; then \
            break; \
        fi; \
        if [ "$i" = "5" ]; then echo "apt operations failed after 5 attempts" >&2; exit 1; fi; \
        echo "apt attempt $i/5 failed, retrying in $((i * 30))s..." >&2; \
        sleep $((i * 30)); \
    done \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Allow vscode user to manage VMs via libvirt
RUN usermod -aG libvirt,kvm vscode

# =============================================================================
# Docker CE CLI (no engine). The engine runs on the host; the hub bind-mounts
# a per-user Docker socket into the container at /var/run/docker.sock.
# =============================================================================
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
       > /etc/apt/sources.list.d/docker.list \
    && for i in 1 2 3 4 5; do \
        rm -rf /var/lib/apt/lists/*; \
        if apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 update \
            && apt-get -o Acquire::Retries=3 -o Acquire::http::Timeout=30 install -y --no-install-recommends docker-ce-cli docker-compose-plugin; then \
            break; \
        fi; \
        if [ "$i" = "5" ]; then echo "apt operations failed after 5 attempts" >&2; exit 1; fi; \
        echo "apt attempt $i/5 failed, retrying in $((i * 30))s..." >&2; \
        sleep $((i * 30)); \
    done \
    && rm -rf /var/lib/apt/lists/*

# =============================================================================
# Node.js via NVM (matching devcontainers/features/node pattern)
# =============================================================================
ENV NVM_DIR=/usr/local/share/nvm
ENV NVM_SYMLINK_CURRENT=true

RUN mkdir -p "$NVM_DIR" \
    && curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash \
    && . "$NVM_DIR/nvm.sh" \
    && nvm install ${NODE_VERSION} \
    && nvm alias default ${NODE_VERSION} \
    && nvm use default \
    && ln -sf "$(nvm which default | xargs dirname | xargs dirname)" "$NVM_DIR/current" \
    && npm install -g npm@10 \
    && npm cache clean --force

# Make node/npm available for subsequent RUN commands
ENV PATH="$NVM_DIR/current/bin:$PATH"

# =============================================================================
# Go (matching devcontainers/features/go pattern)
# =============================================================================
ENV GOROOT=/usr/local/go
ENV GOPATH=/go
ARG TARGETARCH

RUN curl -fsSL "https://go.dev/dl/go${GO_VERSION}.linux-${TARGETARCH}.tar.gz" \
        | tar -xz -C /usr/local \
    && mkdir -p "$GOPATH/bin" \
    && groupadd -f golang \
    && usermod -aG golang vscode \
    && chown -R vscode:golang "$GOPATH"

ENV PATH="$GOROOT/bin:$GOPATH/bin:$PATH"

# Install Go tools as vscode user (writes to $GOPATH/bin).
# `go telemetry off` writes $HOME/.config/go/telemetry/mode so both local
# collection and uploading are disabled for the vscode user.
USER vscode
RUN go telemetry off \
    && go install golang.org/x/tools/gopls@latest \
    && go install github.com/go-delve/delve/cmd/dlv@latest \
    && go install honnef.co/go/tools/cmd/staticcheck@latest \
    && go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest \
    && go install golang.org/x/tools/cmd/goimports@latest \
    && go install mvdan.cc/sh/v3/cmd/shfmt@latest \
    && rm -rf /home/vscode/.cache/go-build \
    && rm -rf "$GOPATH/pkg/mod/cache"
USER root

# =============================================================================
# .NET 9.0 SDK (via official install script - supports amd64 + arm64)
# https://learn.microsoft.com/en-us/dotnet/core/install/linux-scripted-manual
# =============================================================================
ENV DOTNET_ROOT=/usr/share/dotnet
ENV PATH="$PATH:$DOTNET_ROOT"

RUN curl -fsSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 9.0 --install-dir "$DOTNET_ROOT" \
    && ln -sf "$DOTNET_ROOT/dotnet" /usr/local/bin/dotnet

# =============================================================================
# go-sqlcmd (required by ci-start.sh health checks for SQL Server)
# Same logic as private/middleware/scripts/install-sqlcmd.sh
# =============================================================================
COPY install-sqlcmd.sh /tmp/install-sqlcmd.sh
RUN /tmp/install-sqlcmd.sh && rm /tmp/install-sqlcmd.sh

# =============================================================================
# Python packages + uv + kimi-cli
# =============================================================================
RUN pip install --no-cache-dir --break-system-packages pyyaml uv

USER vscode
RUN uv tool install kimi-cli
USER root

# =============================================================================
# Playwright system dependencies (browser binaries installed by postCreateCommand
# as vscode user, ensuring version matches the project's @playwright/test)
# =============================================================================
RUN npx playwright install-deps chromium

# =============================================================================
# Global npm tools
# =============================================================================
RUN npm install -g @openai/codex @google/gemini-cli \
    && npm cache clean --force

# glab — GitLab CLI (https://gitlab.com/gitlab-org/cli)
ARG GLAB_VERSION=1.90.0
RUN ARCH=$(dpkg --print-architecture) \
    && curl -fsSL -o /tmp/glab.deb "https://gitlab.com/gitlab-org/cli/-/releases/v${GLAB_VERSION}/downloads/glab_${GLAB_VERSION}_linux_${ARCH}.deb" \
    && dpkg -i /tmp/glab.deb \
    && rm /tmp/glab.deb

# bottom (btm) — system monitor (https://github.com/ClementTsang/bottom)
ARG BTM_VERSION=0.12.3
RUN curl -fsSL -o /tmp/bottom.deb "https://github.com/ClementTsang/bottom/releases/download/${BTM_VERSION}/bottom_${BTM_VERSION}-1_$(dpkg --print-architecture).deb" \
    && dpkg -i /tmp/bottom.deb \
    && rm /tmp/bottom.deb

# agent-browser — browser automation CLI (https://github.com/vercel-labs/agent-browser)
# Installed via npm so the package's postinstall picks the right native binary
# for the host arch; the standalone GitHub release binary is missing its
# daemon/playwright support files and cannot run on its own.
ARG AGENT_BROWSER_VERSION=0.26.0
RUN npm install -g agent-browser@${AGENT_BROWSER_VERSION} \
    && npm cache clean --force

# Pre-pull the matching chromium-headless-shell so the first `agent-browser
# open` in a fresh container doesn't stall on a ~113 MiB download. Runs as
# vscode so the cache lands in /home/vscode/.cache/ms-playwright/.
# Chrome for Testing (upstream) does not publish Linux ARM64 builds; skip the
# pre-pull on arm64 so the image still builds, and let the first invocation
# fall back to Playwright's bundled Chromium at runtime.
USER vscode
RUN if [ "$(dpkg --print-architecture)" = "amd64" ]; then \
        agent-browser install; \
    else \
        echo "Skipping agent-browser install on $(dpkg --print-architecture): Chrome for Testing has no Linux ARM64 builds"; \
    fi
USER root

# Claude Code (installs to ~/.local/bin for vscode user)
USER vscode
RUN curl -fsSL https://claude.ai/install.sh | bash
USER root

# =============================================================================
# VS Code Extensions (pre-installed from Open-VSX for fast startup)
# Works for both GitHub Codespaces and self-hosted OpenVSCode Server
# =============================================================================
ENV VSCODE_EXTENSIONS_DIR=/opt/vscode-extensions

COPY download-extensions.sh /tmp/
RUN chmod +x /tmp/download-extensions.sh \
    && /tmp/download-extensions.sh \
    && rm /tmp/download-extensions.sh

# =============================================================================
# OpenVSCode Server (for self-hosted HTTP browser access)
# https://github.com/gitpod-io/openvscode-server - MIT License
# =============================================================================
ARG OPENVSCODE_VERSION=1.106.3

RUN ARCH=$(dpkg --print-architecture) \
    && case "$ARCH" in amd64) OVSX_ARCH="x64" ;; arm64) OVSX_ARCH="arm64" ;; esac \
    && echo "Installing OpenVSCode Server v${OPENVSCODE_VERSION} for ${OVSX_ARCH}..." \
    && curl -fsSL "https://github.com/gitpod-io/openvscode-server/releases/download/openvscode-server-v${OPENVSCODE_VERSION}/openvscode-server-v${OPENVSCODE_VERSION}-linux-${OVSX_ARCH}.tar.gz" \
        | tar -xz -C /opt \
    && mv "/opt/openvscode-server-v${OPENVSCODE_VERSION}-linux-${OVSX_ARCH}" /opt/openvscode-server \
    && ln -sf /opt/openvscode-server/bin/openvscode-server /usr/local/bin/openvscode-server \
    # Pre-install extensions into OpenVSCode Server
    && echo "Installing extensions into OpenVSCode Server..." \
    && for vsix in "$VSCODE_EXTENSIONS_DIR"/*.vsix; do \
        [ -f "$vsix" ] && /opt/openvscode-server/bin/openvscode-server \
            --install-extension "$vsix" \
            --extensions-dir /opt/openvscode-server/extensions 2>/dev/null || true; \
    done \
    && chown -R vscode:vscode /opt/openvscode-server

# Bake default Machine + User settings to disable VS Code telemetry, crash
# reporting, auto-updates, and online-lookup features. Written before first
# boot so the settings apply from the initial session.
RUN mkdir -p /home/vscode/.openvscode-server/data/Machine \
             /home/vscode/.openvscode-server/data/User \
    && printf '%s\n' \
        '{' \
        '  "telemetry.telemetryLevel": "off",' \
        '  "telemetry.enableCrashReporter": false,' \
        '  "telemetry.enableTelemetry": false,' \
        '  "update.mode": "none",' \
        '  "extensions.autoUpdate": false,' \
        '  "extensions.autoCheckUpdates": false,' \
        '  "workbench.settings.enableNaturalLanguageSearch": false,' \
        '  "workbench.enableExperiments": false,' \
        '  "npm.fetchOnlinePackageInfo": false' \
        '}' \
        > /home/vscode/.openvscode-server/data/Machine/settings.json \
    && cp /home/vscode/.openvscode-server/data/Machine/settings.json \
          /home/vscode/.openvscode-server/data/User/settings.json \
    && chown -R vscode:vscode /home/vscode/.openvscode-server

# Desktop startup script (starts Xvfb + XFCE + x11vnc + noVNC)
COPY start-desktop.sh /usr/local/bin/start-desktop.sh
RUN chmod +x /usr/local/bin/start-desktop.sh

# ttyd web terminal (lightweight, static binary from official image)
COPY --from=tsl0922/ttyd:1.7.8-alpine /usr/bin/ttyd /usr/bin/ttyd

# ttyd startup script (starts ttyd with tmux session persistence)
COPY start-ttyd.sh /usr/local/bin/start-ttyd.sh
RUN chmod +x /usr/local/bin/start-ttyd.sh

# KVM startup script (starts libvirtd + default network if /dev/kvm exists)
COPY start-kvm.sh /usr/local/bin/start-kvm.sh
RUN chmod +x /usr/local/bin/start-kvm.sh

# Expose ports for self-hosted VS Code, ttyd terminal, and desktop access
EXPOSE 6080 7681 8080

# =============================================================================
# Environment setup
# =============================================================================
RUN sed -i 's|^PATH=.*|PATH="/home/vscode/.local/bin:/usr/local/share/nvm/current/bin:/usr/local/go/bin:/go/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"|' /etc/environment \
    && echo 'GOROOT="/usr/local/go"' >> /etc/environment \
    && echo 'GOPATH="/go"' >> /etc/environment \
    && echo 'NVM_DIR="/usr/local/share/nvm"' >> /etc/environment \
    && echo 'NVM_SYMLINK_CURRENT="true"' >> /etc/environment \
    && echo 'DOCKER_BUILDKIT="1"' >> /etc/environment \
    && echo 'DOTNET_ROOT="/usr/share/dotnet"' >> /etc/environment \
    && echo 'DOTNET_CLI_TELEMETRY_OPTOUT="1"' >> /etc/environment \
    && echo 'DO_NOT_TRACK="1"' >> /etc/environment \
    && echo 'DISABLE_TELEMETRY="1"' >> /etc/environment \
    && echo 'DISABLE_ERROR_REPORTING="1"' >> /etc/environment \
    && echo 'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC="1"' >> /etc/environment \
    && echo 'HOMEBREW_NO_ANALYTICS="1"' >> /etc/environment \
    && echo 'DISPLAY=":99"' >> /etc/environment

# OCI Labels
LABEL org.opencontainers.image.title="Rediacc Console Devcontainer" \
      org.opencontainers.image.description="Prebuilt development container for rediacc-console" \
      org.opencontainers.image.vendor="Rediacc" \
      org.opencontainers.image.source="https://github.com/rediacc/console"
