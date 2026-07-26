#!/bin/bash
# Pinned third-party tool versions and their checksums.
#
# This replicates the idiom in .ci/config/constants.sh (readonly VERSION +
# readonly SHA256 per artifact, verified with `sha256sum -c` BEFORE the artifact
# is used) rather than sourcing it, because breakpoint must work in a repo that
# has no .ci/config/ at all.
#
# RULE, enforced by test-breakpoint-pins.sh: the `sha256sum -c` call must appear
# BEFORE the install/extract call in every installer. The deleted
# .ci/scripts/tunnel/start-cloudflare.sh did neither -- it curled
# `.../releases/latest/download/cloudflared-linux-amd64.deb` (unpinned, so the
# artifact changed under you) straight into `sudo dpkg -i`. Root-owned arbitrary
# code, in a job that also held release secrets.
#
# NEITHER PROJECT PUBLISHES A CHECKSUM FILE. These values were computed by
# downloading each artifact and hashing it on 2026-07-26. To update: bump the
# version, download the four artifacts, `sha256sum` them, paste, and re-run
# `check-breakpoint-drift.sh --write` in the canonical repo.
#
# Why the raw binaries and not the .deb: the .deb needs `sudo dpkg -i`. The raw
# binary needs `chmod +x`. Dropping sudo means this works in a container, on a
# self-hosted runner with no passwordless sudo, and on a laptop.

# shellcheck disable=SC2034  # every constant here is consumed by the installers

# =============================================================================
# cloudflared -- https://github.com/cloudflare/cloudflared
# =============================================================================
# 2026.7.3, published 2026-07-23. Deliberately not `latest`: `latest` means the
# artifact you verified yesterday is not the artifact you get today, which makes
# the checksum meaningless.
readonly BREAKPOINT_CLOUDFLARED_VERSION="2026.7.3"
readonly BREAKPOINT_CLOUDFLARED_SHA256_X64="9d71c677db00134c1bd4144b7783486b654ad281b1ea62b4972098d19f770f17"
readonly BREAKPOINT_CLOUDFLARED_SHA256_ARM64="65259e652a7bea08bf5df603233ab22b8bf3116af8df9f9206209af6a1b955c0"

# =============================================================================
# tmate -- https://github.com/tmate-io/tmate
# =============================================================================
# The static build, because the apt package is old and unpinnable. The deleted
# .github/actions/tmate/scripts/install-tmate.sh tried `apt-get install tmate`
# FIRST and only fell back to the pinned release, which meant the pinned path
# was dead code on every Ubuntu runner and the thing actually installed was
# whatever the distro happened to ship. No apt fallback here.
#
# Upstream's arch suffix is `arm64v8`, not `arm64`; the installer maps it.
# Tarball layout is a single directory containing the binary, so extraction
# uses --strip-components=1.
readonly BREAKPOINT_TMATE_VERSION="2.4.0"
readonly BREAKPOINT_TMATE_SHA256_X64="6e503a1a3b0f9117bce6ff7cc30cf61bdc79e9b32d074cf96deb0264e067a60d"
readonly BREAKPOINT_TMATE_SHA256_ARM64="9bb687cca974dcb711e07739d9eaa8ed124519c2531a4442a0c0d320a75d8584"

# =============================================================================
# caddy -- the gateway that multiplexes one tunnel hostname across the app,
# the noVNC desktop and (later) anything else. See docker/Caddyfile.
# =============================================================================
# PINNED BY DIGEST, not by tag. The deleted .ci/docker/ci/docker-compose.desktop.yml
# used a bare `caddy:alpine`, which is a moving target: the image you reviewed is
# not the image you run tomorrow. A digest is immutable, and docker verifies it
# on pull, so this is the container equivalent of the sha256sum checks above.
#
# Resolved 2026-07-26 from caddy:2.10-alpine (caddy v2.10.2). To update: pull the
# new tag, read `docker inspect --format '{{index .RepoDigests 0}}'`, paste both.
readonly BREAKPOINT_CADDY_VERSION="2.10-alpine"
readonly BREAKPOINT_CADDY_DIGEST="sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d"
readonly BREAKPOINT_CADDY_IMAGE="caddy@${BREAKPOINT_CADDY_DIGEST}"
