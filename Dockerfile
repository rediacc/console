# Dockerfile for standalone Rediacc Console deployment
# This is for open-source users who want to run the console independently
#
# Multi-stage build:
# 1. cli-builder: Build web app, account SPA, and pack CLI
# 2. account-builder: Build account server (Hono API)
# 3. renet-builder: Cross-compile renet binaries
# 4. runtime: Node.js + Nginx with all assets
#
# Build: docker build -t rediacc/web:latest .
# Run: docker run -p 80:80 -p 443:443 rediacc/web:latest

# Base image ARGs must be declared before any FROM for multi-stage build
ARG NODE_IMAGE=node:22-alpine
ARG GO_IMAGE=golang:1.24-alpine

# =============================================================================
# Stage 1: CLI Builder (Node.js)
# Build web app, account SPA, and create CLI npm package
# =============================================================================
FROM ${NODE_IMAGE} AS cli-builder
ARG NODE_IMAGE
LABEL com.rediacc.stage="cli-builder"
LABEL com.rediacc.base-image="${NODE_IMAGE}"

# Set build type (can be overridden at build time)
ARG REDIACC_BUILD_TYPE=DEBUG
ARG VITE_APP_VERSION=latest

WORKDIR /app

# Install build dependencies for native modules (node-pty)
RUN apk add --no-cache python3 make g++

# Copy package files first for better caching
COPY package*.json ./
COPY packages ./packages

# Install dependencies (including dev dependencies for build) with npm cache
RUN --mount=type=cache,target=/root/.npm \
    npm ci

# Copy source code
COPY . .

# Set environment variables for build
ENV REDIACC_BUILD_TYPE=${REDIACC_BUILD_TYPE}
ENV VITE_APP_VERSION=${VITE_APP_VERSION}

# Build the web application with Vite cache
RUN --mount=type=cache,target=/app/node_modules/.cache \
    npm run build

# Build www and generate JSON configuration files
WORKDIR /app/packages/www
RUN npm run build

# Build account portal SPA
WORKDIR /app/private/account
RUN --mount=type=cache,target=/root/.npm \
    npm install
WORKDIR /app/private/account/web
RUN --mount=type=cache,target=/root/.npm \
    npm install
RUN npx vite build --outDir /app/dist/account-web

# Build and pack CLI
WORKDIR /app/packages/cli
RUN npm run build && npm run build:bundle

# Create npm package (.tgz)
RUN mkdir -p /app/dist/npm && npm pack --pack-destination /app/dist/npm

# Create latest symlink (in a way that works in Docker)
RUN cd /app/dist/npm && \
    CLI_PKG=$(ls rediacc-cli-*.tgz 2>/dev/null | head -1) && \
    if [ -n "$CLI_PKG" ]; then \
        cp "$CLI_PKG" rediacc-cli-latest.tgz; \
    fi

# =============================================================================
# Stage 2: Account Server Builder (Node.js)
# Build the account Hono API server bundle
# =============================================================================
FROM ${NODE_IMAGE} AS account-builder
ARG NODE_IMAGE
LABEL com.rediacc.stage="account-builder"
LABEL com.rediacc.base-image="${NODE_IMAGE}"

# Build shared package first (account depends on it)
WORKDIR /
COPY tsconfig.json /tsconfig.json
WORKDIR /packages/shared
COPY packages/shared/package.json packages/shared/tsconfig.json ./
COPY packages/shared/src ./src
RUN npm install --ignore-scripts && npm run build

# Build account server
WORKDIR /app
COPY private/account/package.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm install
COPY private/account/tsconfig.json ./
COPY private/account/src/ ./src/
RUN npm run build
# Bundle for Node.js ESM compatibility
RUN npx --yes esbuild dist/entry/node.js --bundle --platform=node --format=esm \
    --outfile=dist/bundle.js --external:@aws-sdk/* --external:@smithy/*

# =============================================================================
# Stage 3: Renet Builder (Go)
# Cross-compile renet for linux/amd64 and linux/arm64
# =============================================================================
FROM ${GO_IMAGE} AS renet-builder
ARG GO_IMAGE
LABEL com.rediacc.stage="renet-builder"
LABEL com.rediacc.base-image="${GO_IMAGE}"

ARG VITE_APP_VERSION=latest

WORKDIR /build

# Copy renet source
COPY private/renet/ .

# Build for linux/amd64 with Go module cache
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
    -ldflags="-s -w -X main.version=${VITE_APP_VERSION}" \
    -o /renet-linux-amd64 \
    ./cmd/renet

# Build for linux/arm64 with Go module cache
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build \
    -ldflags="-s -w -X main.version=${VITE_APP_VERSION}" \
    -o /renet-linux-arm64 \
    ./cmd/renet

# =============================================================================
# Stage 4: Runtime (Node.js + Nginx)
# Combine web, account, CLI, and renet into final image
# =============================================================================
FROM ${NODE_IMAGE}
ARG NODE_IMAGE
LABEL com.rediacc.stage="runtime"
LABEL com.rediacc.base-image="${NODE_IMAGE}"

# Install nginx and dependencies for entrypoint script
RUN apk add --no-cache nginx coreutils

# Copy www (public website) to root
COPY --from=cli-builder /app/packages/www/dist /usr/share/nginx/html

# Copy web (console app) to /console/ subdirectory
COPY --from=cli-builder /app/packages/web/dist /usr/share/nginx/html/console

# Copy account portal (SPA) to /account/ subdirectory
COPY --from=cli-builder /app/dist/account-web /usr/share/nginx/html/account

# Copy account server bundle and production dependencies
COPY --from=account-builder /app/dist/bundle.js /app/account/bundle.js
COPY --from=account-builder /app/package.json /app/account/package.json
WORKDIR /app/account
RUN --mount=type=cache,target=/root/.npm \
    npm install --omit=dev
WORKDIR /

# Copy CLI npm packages
COPY --from=cli-builder /app/dist/npm /usr/share/nginx/html/npm

# Copy renet binaries
COPY --from=renet-builder /renet-linux-amd64 /usr/share/nginx/html/bin/renet-linux-amd64
COPY --from=renet-builder /renet-linux-arm64 /usr/share/nginx/html/bin/renet-linux-arm64

# Create latest symlinks for renet
RUN cd /usr/share/nginx/html/bin && \
    cp renet-linux-amd64 renet-linux-amd64-latest && \
    cp renet-linux-arm64 renet-linux-arm64-latest

# Copy nginx configuration
COPY .ci/docker/web/nginx.conf /etc/nginx/http.d/default.conf
COPY .ci/docker/web/nginx-https.conf /etc/nginx/nginx-https.conf

# Copy entrypoint script
COPY .ci/docker/web/entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Create directory for SSL certificates (mounted at runtime)
RUN mkdir -p /etc/nginx/certs

# Expose ports (HTTP and HTTPS)
EXPOSE 80 443

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q --spider http://localhost/health || exit 1

# Labels
ARG VITE_APP_VERSION=latest
ARG REDIACC_BUILD_TYPE=DEBUG
LABEL org.opencontainers.image.title="Rediacc Console" \
      org.opencontainers.image.description="Open-source web console for Rediacc system management" \
      org.opencontainers.image.vendor="Rediacc" \
      org.opencontainers.image.source="https://github.com/rediacc/console" \
      org.opencontainers.image.version="${VITE_APP_VERSION}" \
      com.rediacc.build-type="${REDIACC_BUILD_TYPE}"

# Set entrypoint
ENTRYPOINT ["/docker-entrypoint.sh"]
