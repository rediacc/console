# Consolidated Dockerfile for the Rediacc server image.
#
# Builds two variants from the same source via --target:
#   --target cloud   -> ghcr.io/rediacc/elite/web    (internal cloud deployment)
#   --target onprem  -> ghcr.io/rediacc/server       (customer-facing self-hosted)
#
# The build CONTEXT must contain these pre-staged directories (CI populates
# them by downloading the matching artifacts from build-web, build-www,
# build-cli, and build-renet jobs; the local-dev wrapper at
# scripts/docker/build-server.sh stages them from local source builds):
#
#   ./web-assets/         packages/web/dist           (web console SPA)
#   ./www-assets/         packages/www/dist           (marketing site)
#   ./account-web-assets/ private/account/web/dist    (account portal SPA)
#   ./cli-npm/            packages/cli npm tarball    (CLI release artifact)
#   ./binaries/           renet-linux-{amd64,arm64}   (with embedded CRIU/rsync/rclone
#                                                      and ACCOUNT_ED25519_PUBLIC_KEY
#                                                      already baked in)
#
# Why renet binaries are pre-built and not built inside this Dockerfile:
# the renet binary embeds CRIU/rsync/rclone via go:embed assets/*. Those .gz
# files are extracted from the rediacc/bridge image by build-renet.sh, which
# requires running on a real Linux host with Docker available -- not possible
# inside an in-Docker `go build` step. The previous Dockerfiles all silently
# produced asset-less renet binaries that refused to operate at runtime.
#
# Build (CI / local with staged context):
#   docker buildx build --file Dockerfile --target cloud  --tag ... .
#   docker buildx build --file Dockerfile --target onprem --tag ... .
#
# Build (local with the wrapper):
#   scripts/docker/build-server.sh cloud
#   scripts/docker/build-server.sh onprem

ARG NODE_IMAGE=node:22-alpine
ARG ACCOUNT_ENTRY=node                # node | on-premise

# =============================================================================
# Stage 1: account-builder
# Build the account server bundle. Variant-specific via ACCOUNT_ENTRY.
# Bundles EVERYTHING via esbuild (no externals) so the runtime stage doesn't
# need any node_modules at all -- fully self-contained, fully reproducible.
# esbuild's tree-shaker eliminates unreached code paths automatically when
# bundling from the on-premise entry (no Stripe, no admin routes, no SES).
# =============================================================================
FROM ${NODE_IMAGE} AS account-builder
ARG ACCOUNT_ENTRY
WORKDIR /app
COPY package*.json ./
# Root tsconfig.json is needed because packages/shared/tsconfig.json extends
# ../../tsconfig.json. Without this, tsc silently falls back to defaults
# (no target, no lib, no paths) and the shared build fails with TS2802
# (RegExpStringIterator iteration) and TS1501 (regex flag) errors.
COPY tsconfig.json ./
COPY packages/shared/package*.json packages/shared/
COPY private/account/package*.json private/account/
# Install workspace deps (only packages listed in root workspaces).
# private/account is NOT a workspace member, so its deps must be installed
# separately below. --ignore-scripts skips postinstall hooks here to avoid
# running better-sqlite3 native rebuilds we don't need at this stage.
RUN npm ci --ignore-scripts
COPY packages/shared packages/shared
RUN npm run build -w @rediacc/shared
COPY private/account private/account
WORKDIR /app/private/account
# Install private/account's own deps (zod 3.x, hono, drizzle, etc).
# Without this, tsc would walk up to /app/node_modules and resolve `zod`
# to whatever bridge-tests pulled in (zod 4.x), which causes a cascade
# of TS2307/TS1259 errors in the type-only checks.
RUN npm install --ignore-scripts
RUN npm run build
# Use `npm exec esbuild` to ensure we run the workspace-pinned esbuild
# (matching dev/CI bundling behavior) instead of `npx --yes` which would
# transparently download an arbitrary version from the registry.
#
# The createRequire banner is needed because some bundled deps still rely on
# CJS-style require() at runtime even when the output format is ESM.
RUN npm exec --prefix /app -- esbuild dist/entry/${ACCOUNT_ENTRY}.js \
    --bundle --platform=node --format=esm \
    --outfile=dist/bundle.js \
    --banner:js="import { createRequire } from 'module'; const require = createRequire(import.meta.url);"

# =============================================================================
# Stage 2: runtime-base
# Shared between both final targets. Assembles nginx + the account server
# bundle + all pre-built static assets + renet binaries into the runtime
# image. No source compilation here -- purely a stitching layer.
# =============================================================================
FROM ${NODE_IMAGE} AS runtime-base

RUN apk add --no-cache nginx coreutils

# Marketing site (root)
COPY ./www-assets/         /usr/share/nginx/html/
# Web console SPA (/console/)
COPY ./web-assets/         /usr/share/nginx/html/console/
# Account portal SPA (/account/)
COPY ./account-web-assets/ /usr/share/nginx/html/account/

# Account server bundle (variant-specific, fully self-contained)
COPY --from=account-builder /app/private/account/dist/bundle.js /app/account/bundle.js

# CLI npm tarball + release manifest for the install script
COPY ./cli-npm/ /usr/share/nginx/html/npm/
ARG VITE_APP_VERSION=latest
RUN mkdir -p /usr/share/nginx/html/releases/cli/stable && \
    cp /usr/share/nginx/html/npm/rediacc-cli-latest.tgz \
       /usr/share/nginx/html/releases/cli/stable/rediacc-cli-latest.tgz && \
    echo "{\"version\":\"${VITE_APP_VERSION}\",\"npm\":true}" > \
       /usr/share/nginx/html/releases/cli/stable/latest.json

# Renet binaries (pre-built by ci-build-renet.yml with embedded CRIU/rsync/
# rclone assets and ACCOUNT_ED25519_PUBLIC_KEY baked in via -X main.Version
# / -X .../keys.ProductionPublicKey ldflags).
COPY ./binaries/renet-linux-amd64 /usr/share/nginx/html/bin/renet-linux-amd64
COPY ./binaries/renet-linux-arm64 /usr/share/nginx/html/bin/renet-linux-arm64
RUN cd /usr/share/nginx/html/bin && \
    cp renet-linux-amd64 renet-linux-amd64-latest && \
    cp renet-linux-arm64 renet-linux-arm64-latest

# nginx + entrypoint
COPY .ci/docker/web/nginx.conf       /etc/nginx/http.d/default.conf
COPY .ci/docker/web/nginx-https.conf /etc/nginx/nginx-https.conf
COPY .ci/docker/web/entrypoint.sh    /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh && mkdir -p /etc/nginx/certs

EXPOSE 80 443
# The Hono account server exposes /health at the root (see app.ts), and
# nginx is configured to proxy / to the upstream account server.
# wget --tries=1 prevents the healthcheck from hanging on cold-start nginx.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD wget --tries=1 --quiet --output-document=/dev/null http://localhost/health || exit 1
ENTRYPOINT ["/docker-entrypoint.sh"]

# =============================================================================
# Final target: cloud
# Internal cloud deployment, published to ghcr.io/rediacc/elite/web.
# =============================================================================
FROM runtime-base AS cloud
LABEL com.rediacc.variant=cloud
LABEL org.opencontainers.image.title="Rediacc Console (Cloud)"
LABEL org.opencontainers.image.description="Rediacc cloud console - account API, web console, CLI, and renet distribution"
LABEL org.opencontainers.image.source="https://github.com/rediacc/console"
LABEL org.opencontainers.image.version="${VITE_APP_VERSION}"

# =============================================================================
# Final target: onprem
# Customer-facing self-hosted deployment, published to ghcr.io/rediacc/server.
# Bakes the upstream master public key as a runtime default for
# UPSTREAM_PUBLIC_KEY (used by the on-prem account server to verify
# customer-uploaded fresh delegation certs).
# =============================================================================
FROM runtime-base AS onprem
LABEL com.rediacc.variant=onprem
LABEL org.opencontainers.image.title="Rediacc Server (Self-Hosted)"
LABEL org.opencontainers.image.description="Self-hosted Rediacc server - account API, web console, CLI, and renet binaries"
LABEL org.opencontainers.image.source="https://github.com/rediacc/console"
LABEL org.opencontainers.image.version="${VITE_APP_VERSION}"

ENV ON_PREMISE_MODE=true \
    EMAIL_TRANSPORT=smtp

# UPSTREAM_PUBLIC_KEY_DEFAULT is consumed by entrypoint.sh, which exports it
# as UPSTREAM_PUBLIC_KEY when the customer didn't supply one. This removes
# one config variable from the standard install -- the master public key is
# the same for every customer (single global root of trust).
ARG ACCOUNT_ED25519_PUBLIC_KEY=
ENV UPSTREAM_PUBLIC_KEY_DEFAULT=${ACCOUNT_ED25519_PUBLIC_KEY}
