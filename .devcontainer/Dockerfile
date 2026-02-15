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

# =============================================================================
# System packages + GitHub CLI + Python 3 + XFCE Desktop + VNC stack
# =============================================================================
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
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
        # X11/Xvfb for E2E testing
        xvfb \
        libgtk-3-0 \
        libnotify4 \
        libnss3 \
        libxss1 \
        libxtst6 \
        libatspi2.0-0 \
        libsecret-1-0 \
        # XFCE desktop + VNC (browser-based desktop via noVNC)
        xfce4 \
        xfce4-terminal \
        x11vnc \
        novnc \
        websockify \
        dbus-x11 \
        netcat-openbsd \
        gnome-keyring \
        # KVM/libvirt for local VM provisioning (Standalone Run)
        qemu-kvm \
        libvirt-daemon-system \
        libvirt-clients \
        bridge-utils \
        virtinst \
        cloud-image-utils \
        genisoimage \
        dnsmasq-base \
        iputils-ping \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Allow vscode user to manage VMs via libvirt
RUN usermod -aG libvirt,kvm vscode

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
    && npm install -g npm@latest \
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

# Install Go tools as vscode user (writes to $GOPATH/bin)
USER vscode
RUN go install golang.org/x/tools/gopls@latest \
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
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1
ENV PATH="$PATH:$DOTNET_ROOT"

RUN curl -fsSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 9.0 --install-dir "$DOTNET_ROOT" \
    && ln -sf "$DOTNET_ROOT/dotnet" /usr/local/bin/dotnet

# =============================================================================
# go-sqlcmd (required by ci-start.sh health checks for SQL Server)
# Same logic as private/middleware/scripts/install-sqlcmd.sh
# =============================================================================
ARG SQLCMD_VERSION=1.9.0

RUN ARCH=$(dpkg --print-architecture) \
    && wget -qO- "https://github.com/microsoft/go-sqlcmd/releases/download/v${SQLCMD_VERSION}/sqlcmd-linux-${ARCH}.tar.bz2" \
        | tar -xj -C /usr/local/bin \
    && chmod +x /usr/local/bin/sqlcmd

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

# bottom (btm) — system monitor (https://github.com/ClementTsang/bottom)
ARG BTM_VERSION=0.12.3
RUN curl -fsSL -o /tmp/bottom.deb "https://github.com/ClementTsang/bottom/releases/download/${BTM_VERSION}/bottom_${BTM_VERSION}-1_$(dpkg --print-architecture).deb" \
    && dpkg -i /tmp/bottom.deb \
    && rm /tmp/bottom.deb

# agent-browser (https://github.com/vercel-labs/agent-browser)
ARG AGENT_BROWSER_VERSION=0.9.0
RUN ARCH=$(dpkg --print-architecture) \
    && case "$ARCH" in amd64) AB_ARCH="x64" ;; arm64) AB_ARCH="arm64" ;; esac \
    && curl -fsSL -o /usr/local/bin/agent-browser "https://github.com/vercel-labs/agent-browser/releases/download/v${AGENT_BROWSER_VERSION}/agent-browser-linux-${AB_ARCH}" \
    && chmod +x /usr/local/bin/agent-browser

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

# Desktop startup script (starts Xvfb + XFCE + x11vnc + noVNC)
COPY start-desktop.sh /usr/local/bin/start-desktop.sh
RUN chmod +x /usr/local/bin/start-desktop.sh

# KVM startup script (starts libvirtd + default network if /dev/kvm exists)
COPY start-kvm.sh /usr/local/bin/start-kvm.sh
RUN chmod +x /usr/local/bin/start-kvm.sh

# Expose ports for self-hosted VS Code and desktop access
EXPOSE 6080 8080

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
    && echo 'DISPLAY=":99"' >> /etc/environment

# OCI Labels
LABEL org.opencontainers.image.title="Rediacc Console Devcontainer" \
      org.opencontainers.image.description="Prebuilt development container for rediacc-console" \
      org.opencontainers.image.vendor="Rediacc" \
      org.opencontainers.image.source="https://github.com/rediacc/console"
