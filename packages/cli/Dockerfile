# Dockerfile for Rediacc CLI
# Minimal Node.js image with the CLI bundle
#
# Build: docker build -f packages/cli/Dockerfile -t rediacc/cli:latest .
# Run: docker run --rm rediacc/cli:latest --version

ARG NODE_IMAGE=node:22-alpine

# =============================================================================
# Stage 1: Builder
# =============================================================================
FROM ${NODE_IMAGE} AS builder

WORKDIR /app

# Install build dependencies for native modules
RUN apk add --no-cache python3 make g++

# Copy package files first for better caching
COPY package*.json ./
COPY packages ./packages

# Install dependencies
RUN --mount=type=cache,target=/root/.npm \
    npm ci

# Copy source code
COPY . .

# Build shared packages and CLI bundle
RUN npm run build && npm run build:bundle -w @rediacc/cli

# =============================================================================
# Stage 2: Runtime
# =============================================================================
FROM ${NODE_IMAGE}

WORKDIR /app

COPY --from=builder /app/packages/cli/dist/cli-bundle.cjs /app/rdc.cjs
COPY --from=builder /app/packages/cli/package.json /app/package.json

ENTRYPOINT ["node", "/app/rdc.cjs"]
