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
ARG GO_VERSION=1.26.6

# EVERY NETWORK FETCH RETRIES, because one upstream hiccup must not kill a ten-minute
# multi-arch build that gates every PR.
#
# MEASURED 2026-09-01: `Build (Docker) / Devcontainer (amd64)` died at
# `curl: (22) The requested URL returned error: 500` on the Go tarball. go.dev was briefly
# unwell; probed minutes later the same URL answered 302. Nothing was wrong with the image
# or the pin -- the build simply had no second attempt.
#
# The asymmetry was the real defect: the two apt steps each carry a hand-rolled
# `for i in 1 2 3 4 5` retry loop, while EIGHT other fetches -- Go, nvm, and six
# architecture-keyed tool downloads -- had none. Eight more copies of that loop would be
# eight more things to drift, so this uses curl's own retry instead, once, as a shared ARG.
#
# MEASURED, not assumed, against a local server that always answers 500: `--retry 3` makes
# curl hit it FOUR times (one attempt plus three retries), so a 5xx is already inside
# curl's transient set and plain `--retry` would have covered this outage. A first draft of
# this comment claimed `--retry-all-errors` was what made 500 retryable; the hit count says
# otherwise. It is kept because it widens cover to errors curl does not class as transient
# (a truncated body, a DNS hiccup mid-transfer), which cost nothing here. Requires curl
# >= 7.71; the base image is ubuntu-24.04, which ships 8.x.
ARG CURL_RETRY="--retry 5 --retry-delay 3 --retry-all-errors --retry-max-time 180"

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
#
# "EFFECTIVELY NEVER" RAN OUT ON 2026-08-19. azure.archive.ubuntu.com
# (20.106.104.242) refused connections on port 80 for over ninety minutes, and
# because EVERY source had been rewritten to that one host, all five retries
# hammered the same dead mirror: four consecutive CI attempts died, two by
# exhausting the retries and two by running past the 30-minute job timeout while
# doing so. Retrying a single point of failure five times is still a single point
# of failure.
#
# So the loop now FALLS BACK after the first failure: attempt 1 still uses the
# fast in-datacenter mirror, and attempts 2 to 5 revert to the canonical
# archive.ubuntu.com. This keeps the speed argument above intact for the normal
# case, which is the whole reason the rewrite exists, while removing the
# assumption that one host is always up.
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
                shellcheck \
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
        if [ "$i" = "1" ]; then \
            echo "azure mirror unreachable; falling back to archive.ubuntu.com" >&2; \
            find /etc/apt -name 'ubuntu.sources' -o -name 'sources.list' 2>/dev/null \
                | xargs -r sed -i \
                    -e 's|http://azure\.archive\.ubuntu\.com/ubuntu|http://archive.ubuntu.com/ubuntu|g'; \
        fi; \
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
    && curl -fsSL $CURL_RETRY https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
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
    && curl -fsSL $CURL_RETRY https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash \
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
# Never auto-download a different toolchain: tool installs below must build
# with the pinned GO_VERSION. Without this, a tool's `go` directive can pull
# a same-day toolchain whose sumdb entry is not published yet (gopls v0.22.0
# resolved the never-published go1.26.5 and 404'd the whole image build).
# THAT WAS TRUE WHEN WRITTEN AND IS NOT NOW: go1.26.5 and go1.26.6 are both
# published (checked 2026-08-27 with `curl -sL -I`, following the redirect --
# a bare -I returns 302 for EVERY version, published or not, so the obvious
# probe cannot answer this question and go1.26.4 is the control that proves
# the check works). Pinned to 1.26.6 because govulncheck reports SIX
# actionable standard-library vulnerabilities against 1.26.4 -- GO-2026-4970,
# 5026, 5856, 5942, 5972, 6088, including an Encrypted Client Hello privacy
# leak in crypto/tls and a Punycode label-rejection failure in net/http.
# net/http's fix lands in 1.26.6 specifically, so 1.26.5 is not enough.
ENV GOTOOLCHAIN=local
ARG TARGETARCH

# Checksums from go.dev's own index: curl -s 'https://go.dev/dl/?mode=json&include=all'
# | jq '.[]|select(.version=="go<V>")|.files[]|select(.os=="linux" and .kind=="archive")'
ARG GO_SHA256_AMD64=708effb774be8237570d0add163225abbdfaf4fca28b2611df167beba4feef89
ARG GO_SHA256_ARM64=d0507e9e9d7fe012aae570108cbd76c15de879e17130ab8cb90d4d7445cb1f2e
# Downloaded to a file rather than streamed into tar: a stream cannot be verified
# before it is extracted, which is the whole point of having a checksum.
RUN case "$TARGETARCH" in \
    amd64) GO_SHA="$GO_SHA256_AMD64" ;; \
    arm64) GO_SHA="$GO_SHA256_ARM64" ;; \
    *) echo "no pinned go checksum for $TARGETARCH" >&2; exit 1 ;; \
    esac \
    && curl -fsSL $CURL_RETRY -o /tmp/go.tgz "https://go.dev/dl/go${GO_VERSION}.linux-${TARGETARCH}.tar.gz" \
    && echo "${GO_SHA}  /tmp/go.tgz" | sha256sum -c - \
    && tar -xz -C /usr/local -f /tmp/go.tgz \
    && rm /tmp/go.tgz \
    && mkdir -p "$GOPATH/bin" \
    && groupadd -f golang \
    && usermod -aG golang vscode \
    && chown -R vscode:golang "$GOPATH"

ENV PATH="$GOROOT/bin:$GOPATH/bin:$PATH"

# Install Go tools as vscode user (writes to $GOPATH/bin).
# `go telemetry off` writes $HOME/.config/go/telemetry/mode so both local
# collection and uploading are disabled for the vscode user.
# THE GATE TOOLCHAIN PINS, as the image's own copy.
#
# This is the third reader of .devcontainer/toolchain.env (bash and GitHub
# Actions are the other two), and the reason that file lives in this directory:
# the build context IS .devcontainer/ (.github/workflows/ci-build-docker.yml:558),
# so COPY cannot reach outside it.
COPY toolchain.env /etc/rediacc/toolchain.env

USER vscode
# shfmt is PINNED, the rest stay @latest deliberately.
#
# shfmt decides a CI verdict, so an image that ships a different one than the
# host or the runner makes the same gate disagree with itself -- which is what
# `go install ...@latest` here plus an unpinned `curl webi.sh/shfmt | sh` in the
# workflow actually produced. The others (gopls, dlv, staticcheck,
# golangci-lint, goimports) are EDITOR tooling: nothing gates on their output,
# so pinning them would buy churn rather than consistency.
#
# The `: "${SHFMT_VERSION:?...}"` guard is not decoration: without it an empty
# build arg silently resolves to `@v`, which Go treats as a floating reference,
# and the image would quietly ship an unpinned shfmt again while looking pinned.
RUN . /etc/rediacc/toolchain.env \
    && : "${SHFMT_VERSION:?toolchain.env did not define SHFMT_VERSION}" \
    && go telemetry off \
    && go install golang.org/x/tools/gopls@latest \
    && go install github.com/go-delve/delve/cmd/dlv@latest \
    && go install honnef.co/go/tools/cmd/staticcheck@latest \
    && go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest \
    && go install golang.org/x/tools/cmd/goimports@latest \
    && go install "mvdan.cc/sh/v3/cmd/shfmt@v${SHFMT_VERSION}" \
    && rm -rf /home/vscode/.cache/go-build \
    && rm -rf "$GOPATH/pkg/mod/cache"
USER root

# =============================================================================
# Python packages + uv + kimi-cli
# =============================================================================
# PyYAML NEEDS ITS OWN INSTALL WITH --ignore-installed, and that is not
# carelessness. The base image already carries PyYAML 6.0.1 installed by DEBIAN
# (the python3-yaml apt package), which pip cannot uninstall -- a distro package
# has no RECORD file, so pinning it in the same command as everything else fails
# the whole layer with:
#
#     ERROR: Cannot uninstall PyYAML 6.0.1, RECORD file not found.
#            Hint: The package was installed by debian.
#
# Verified inside the running image before committing: --ignore-installed takes
# it 6.0.1 -> 6.0.2 and `import yaml` still works. It is a SEPARATE command so
# that flag applies to PyYAML alone; ruff and uv have no distro copy to shadow
# and must keep failing loudly if they collide with one.
#
# ruff and PyYAML at the PINNED versions, so check-python-lint.sh finds a real
# binary on PATH instead of falling through to `uvx ruff@X`, which needs the
# network on first use. PyYAML is pinned here for the same reason it is pinned
# in the workflow: two python gates import it.
RUN . /etc/rediacc/toolchain.env \
    && : "${RUFF_VERSION:?toolchain.env did not define RUFF_VERSION}" \
    && : "${PYYAML_VERSION:?toolchain.env did not define PYYAML_VERSION}" \
    && pip install --no-cache-dir --break-system-packages \
        uv "ruff==${RUFF_VERSION}" \
    && pip install --no-cache-dir --break-system-packages --ignore-installed \
        "pyyaml==${PYYAML_VERSION}"

USER vscode
RUN uv tool install kimi-cli
USER root

# =============================================================================
# Playwright system dependencies (browser binaries installed by postCreateCommand
# as vscode user, ensuring version matches the project's @playwright/test)
# =============================================================================
# `apt-get update` MUST be in the same layer as the install.
#
# install-deps shells out to apt, and apt uses whatever package index the last cached
# layer left behind. Ubuntu's pool only keeps the CURRENT version of each .deb, so once
# a point release lands (libasound2t64 1.2.11-1ubuntu0.3 -> .4), a stale index points at
# a file that no longer exists and apt dies on a 404 — which is exactly how the arm64
# devcontainer broke. It is not a flake: it will happen again on the next point release,
# and it fails ONLY on the arch whose layer cache happens to be older.
#
# Refreshing the index in the same RUN keeps the two in step, and the list is cleaned up
# so this does not bloat the image.
RUN apt-get update && \
    npx playwright install-deps chromium && \
    rm -rf /var/lib/apt/lists/*

# =============================================================================
# Global npm tools
# =============================================================================
RUN npm install -g @openai/codex @google/gemini-cli \
    && npm cache clean --force

# awscli — required by the R2 gates, and its absence made them unrunnable.
#
# WHY IT IS HERE. `npm run check:ci-release-state` exits 1 with "Required
# command 'aws' is not available" on the host AND, until this, inside the
# devbox. That gate guards the tag<->sentinel bijection and (since 2026-08-26)
# the channel-pointer relation -- i.e. exactly the release-correctness property
# whose failure let cli/edge/manifest.json advertise 1.3.1 with no v1.3.1 tag
# three times over. A release gate that cannot be run locally is a release gate
# that gets verified only in CI, which is where this one's blind spot lived.
#
# The bundled installer, not pip: the host has no pip at all (python3 carries no
# pip module), so a pip-based install would reproduce the same "works in CI,
# not here" gap one layer down.
RUN ARCH=$(dpkg --print-architecture) \
    && case "$ARCH" in \
    amd64) AWS_ARCH=x86_64 ;; \
    arm64) AWS_ARCH=aarch64 ;; \
    *) echo "unsupported arch for awscli: $ARCH" >&2; exit 1 ;; \
    esac \
    && curl -fsSL $CURL_RETRY -o /tmp/awscliv2.zip "https://awscli.amazonaws.com/awscli-exe-linux-${AWS_ARCH}.zip" \
    && unzip -q /tmp/awscliv2.zip -d /tmp \
    && /tmp/aws/install \
    && rm -rf /tmp/aws /tmp/awscliv2.zip \
    && aws --version

# glab — GitLab CLI (https://gitlab.com/gitlab-org/cli)
ARG GLAB_VERSION=1.90.0
# From the release's own checksums.txt:
#   curl -sL https://gitlab.com/gitlab-org/cli/-/releases/v<V>/downloads/checksums.txt
ARG GLAB_SHA256_AMD64=e487c07ed8e634bae1737e17d4dfe192d762f8acf5b64d7f1658a741aa1e4060
ARG GLAB_SHA256_ARM64=9ba8431991dc4b4ad78c3c6e0b6341076d0d7063ca81ed370bcd1378665a4370
RUN ARCH=$(dpkg --print-architecture) \
    && case "$ARCH" in \
    amd64) GLAB_SHA="$GLAB_SHA256_AMD64" ;; \
    arm64) GLAB_SHA="$GLAB_SHA256_ARM64" ;; \
    *) echo "no pinned glab checksum for $ARCH" >&2; exit 1 ;; \
    esac \
    && curl -fsSL $CURL_RETRY -o /tmp/glab.deb "https://gitlab.com/gitlab-org/cli/-/releases/v${GLAB_VERSION}/downloads/glab_${GLAB_VERSION}_linux_${ARCH}.deb" \
    && echo "${GLAB_SHA}  /tmp/glab.deb" | sha256sum -c - \
    && dpkg -i /tmp/glab.deb \
    && rm /tmp/glab.deb

# Bitwarden CLI (bw) — https://github.com/bitwarden/clients
#
# THE NATIVE ZIP, NOT npm, AND THE HASH IS PINNED. @bitwarden/cli@2026.4.0 was
# malicious on npm for ~90 minutes on 2026-04-22 (CVE-2026-42994): a compromised
# GitHub Action injected a credential harvester into the npm PACKAGING step only,
# leaving the GitHub release assets and the snap untouched. It took GitHub/npm
# tokens, SSH keys, env vars and shell history off CI runners -- this container's
# exact threat model. So the channel that was not compromised is the one used
# here, and it is pinned to a digest rather than to a moving tag.
#
# It costs nothing in toolchain either: the native build embeds its own Node
# runtime (pkg), so `ldd` wants only libc/libstdc++/libm/libgcc_s/libpthread/libdl
# -- glibc >= 2.28, which ubuntu-24.04 satisfies several times over. It does cost
# ~142 MB unpacked, which is the honest price of not using the 5 MB npm package.
#
# THE DIGESTS ARE THE `digest` FIELD ON EACH RELEASE ASSET. Bitwarden publishes no
# .sha256 sidecar files and no GPG/cosign signatures, and the docs' talk of
# "checksum files" means the sha256 GitHub renders beside each asset. Re-read both
# with, for version V:
#   curl -s https://api.github.com/repos/bitwarden/clients/releases/tags/cli-v$V \
#     | jq -r '.assets[]|select(.name|test("bw-linux(-arm64)?-"))|"\(.name) \(.digest)"'
# scripts/check-devcontainer-pin-freshness.ts watches this pin and rewrites all
# three ARGs together; the CLI lives in a MONOREPO, so that gate filters tags by
# the `cli-v` prefix rather than trusting /releases/latest.
ARG BW_VERSION=2026.8.0
ARG BW_SHA256_AMD64=367f618e9fcccaac4980ec12c7bafd01df739b5f3cb1af31bc9045cf75eea1d6
ARG BW_SHA256_ARM64=74d822a5dceda5896ed8fc07bc61925b29afd98d96a6a3e9e525ae556c3083a8
RUN ARCH=$(dpkg --print-architecture) \
    && case "$ARCH" in \
    amd64) BW_ASSET="bw-linux-${BW_VERSION}.zip";       BW_SHA="${BW_SHA256_AMD64}" ;; \
    arm64) BW_ASSET="bw-linux-arm64-${BW_VERSION}.zip"; BW_SHA="${BW_SHA256_ARM64}" ;; \
    *) echo "unsupported arch for bw: $ARCH" >&2; exit 1 ;; \
    esac \
    && curl -fsSL $CURL_RETRY -o /tmp/bw.zip \
        "https://github.com/bitwarden/clients/releases/download/cli-v${BW_VERSION}/${BW_ASSET}" \
    && echo "${BW_SHA}  /tmp/bw.zip" | sha256sum -c - \
    && unzip -o -q /tmp/bw.zip -d /usr/local/bin \
    && chmod +x /usr/local/bin/bw \
    && rm /tmp/bw.zip \
    # `status`, not just `--version`: it exercises the embedded Node runtime and
    # the first write to the appdata dir, which is where a broken pkg bundle
    # actually fails. Same reflex as `aws --version` above -- fail the BUILD
    # rather than ship a binary that cannot start.
    && bw --version \
    && bw status >/dev/null

# Bitwarden Secrets Manager CLI (bws) — https://github.com/bitwarden/sdk-sm
#
# A DIFFERENT PRODUCT from `bw` above: `bw` is the password-manager CLI (a
# person's vault, unlocked with BW_SESSION); `bws` is the Secrets Manager CLI
# (a machine account, authenticated with BWS_ACCESS_TOKEN). CI reads its
# credentials from Secrets Manager, and the consumers that run OUTSIDE GitHub
# Actions -- deploy-bench.sh, run.sh's preview builder, the drills,
# license-e2e.sh -- cannot use the sm-action, so they need this binary.
#
# Same discipline as bw: the native release zip, hash-pinned, never npm. Unlike
# bitwarden/clients, sdk-sm publishes a real checksums file per release
# (bws-sha256-checksums-<V>.txt) and these two digests come from it. Also
# unlike clients it is a plain repo, but its releases are still prefixed
# (`bws-v`), so the freshness watcher filters by that prefix.
#
# glibc build, not musl: the image is ubuntu-24.04 and the gnu build is the
# one Bitwarden tests against on it.
ARG BWS_VERSION=2.1.0
ARG BWS_SHA256_AMD64=ba8233c3a4aee5d43e3c73bbd04d99e9bc5aba13bbbfd06d89b073abe732b860
ARG BWS_SHA256_ARM64=18253757286e119d450133a87eb463bf8c1ce418ce24c834f4f250d60cba6f9e
RUN ARCH=$(dpkg --print-architecture) \
    && case "$ARCH" in \
    amd64) BWS_ASSET="bws-x86_64-unknown-linux-gnu-${BWS_VERSION}.zip";  BWS_SHA="${BWS_SHA256_AMD64}" ;; \
    arm64) BWS_ASSET="bws-aarch64-unknown-linux-gnu-${BWS_VERSION}.zip"; BWS_SHA="${BWS_SHA256_ARM64}" ;; \
    *) echo "unsupported arch for bws: $ARCH" >&2; exit 1 ;; \
    esac \
    && curl -fsSL $CURL_RETRY -o /tmp/bws.zip \
        "https://github.com/bitwarden/sdk-sm/releases/download/bws-v${BWS_VERSION}/${BWS_ASSET}" \
    && echo "${BWS_SHA}  /tmp/bws.zip" | sha256sum -c - \
    && unzip -o -q /tmp/bws.zip -d /usr/local/bin \
    && chmod +x /usr/local/bin/bws \
    && rm /tmp/bws.zip \
    && bws --version

# bottom (btm) — system monitor (https://github.com/ClementTsang/bottom)
ARG BTM_VERSION=0.12.3
# Digests from the release API's `digest` field, same source as the bw pins above.
ARG BTM_SHA256_AMD64=75dd4aa31eeb61087925c434627191062d9811b5da91c75ed28b83137a42ff27
ARG BTM_SHA256_ARM64=6247af81c0f5befe46d95f8e34444e8f1aae04a525c571565fce4e1a0d3682a0
RUN ARCH=$(dpkg --print-architecture) \
    && case "$ARCH" in \
    amd64) BTM_SHA="$BTM_SHA256_AMD64" ;; \
    arm64) BTM_SHA="$BTM_SHA256_ARM64" ;; \
    *) echo "no pinned bottom checksum for $ARCH" >&2; exit 1 ;; \
    esac \
    && curl -fsSL $CURL_RETRY -o /tmp/bottom.deb "https://github.com/ClementTsang/bottom/releases/download/${BTM_VERSION}/bottom_${BTM_VERSION}-1_${ARCH}.deb" \
    && echo "${BTM_SHA}  /tmp/bottom.deb" | sha256sum -c - \
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
RUN curl -fsSL $CURL_RETRY https://claude.ai/install.sh | bash
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
ARG OPENVSCODE_VERSION=1.109.5
# Digests from the release API's `digest` field.
ARG OPENVSCODE_SHA256_X64=b433bf4f0227321a7014d8460d10a8f958adc0f45aa79bd889e84e65e8f88363
ARG OPENVSCODE_SHA256_ARM64=36d9c14036489b63de84ebace837fcacf7e60e669a0dc715802c5443684ea4dc

RUN ARCH=$(dpkg --print-architecture) \
    && case "$ARCH" in amd64) OVSX_ARCH="x64" ;; arm64) OVSX_ARCH="arm64" ;; esac \
    && echo "Installing OpenVSCode Server v${OPENVSCODE_VERSION} for ${OVSX_ARCH}..." \
    && case "$OVSX_ARCH" in \
    x64) OVSX_SHA="$OPENVSCODE_SHA256_X64" ;; \
    arm64) OVSX_SHA="$OPENVSCODE_SHA256_ARM64" ;; \
    *) echo "no pinned openvscode checksum for $OVSX_ARCH" >&2; exit 1 ;; \
    esac \
    && curl -fsSL $CURL_RETRY -o /tmp/ovsx.tgz "https://github.com/gitpod-io/openvscode-server/releases/download/openvscode-server-v${OPENVSCODE_VERSION}/openvscode-server-v${OPENVSCODE_VERSION}-linux-${OVSX_ARCH}.tar.gz" \
    && echo "${OVSX_SHA}  /tmp/ovsx.tgz" | sha256sum -c - \
    && tar -xz -C /opt -f /tmp/ovsx.tgz \
    && rm /tmp/ovsx.tgz \
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
# Pinned by DIGEST, not by tag: a tag is mutable, so `1.7.8-alpine` can be
# repointed at a different image without the version string changing. The digest
# is the only form a rebuild cannot silently drift under. Comment keeps the
# human-readable version. Re-read with:
#   docker buildx imagetools inspect tsl0922/ttyd:1.7.8-alpine
COPY --from=tsl0922/ttyd@sha256:9355735b28a407fe7fb09597f6773d5550f2502259d22b350a2e2460125f9072 /usr/bin/ttyd /usr/bin/ttyd

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
