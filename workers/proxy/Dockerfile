# The executor image: the rdc CLI, running as a server.
#
# It is deliberately the SAME artifact operators run locally. A separate
# server-only build would be a second implementation of vault building, policy
# evaluation, and the config crypto, and those are the last three things in this
# system that should ever be allowed to drift.
#
# Build context is the repo root, because the bundle is produced from the
# workspace:
#   docker build -f workers/proxy/Dockerfile .

# The one npm (.devcontainer/toolchain.env NPM_VERSION, outside this build context;
# check:ci-lockfile asserts the two agree). node:22-slim bundles npm 10, which cannot
# resolve the npm-11 lockfile `npm ci` installs below.
ARG NPM_VERSION=11.20.0

FROM node:22-slim AS build
ARG NPM_VERSION
RUN npm install -g "npm@${NPM_VERSION}" --no-audit --no-fund

WORKDIR /build

# Workspace manifests first, so a dependency change is the only thing that
# invalidates the install layer. The root tsconfig comes along because every
# package tsconfig extends it; without it the compiler reports a cascade of
# missing-type errors that all trace back to one missing file.
COPY package.json package-lock.json .npmrc tsconfig.json ./
# @rediacc/locales is the single declaration of the site locale set. It is buildless
# (no dist, no scripts), but the CLI imports it, so both its manifest and its source
# have to be present or `npm ci` leaves the workspace unlinked and the bundle fails.
COPY packages/locales/package.json packages/locales/
COPY packages/shared/package.json packages/shared/
COPY packages/cli/package.json packages/cli/
# The CLI compiles against @rediacc/provisioning for the local-VM types. Those
# commands never run in a container, but tsc compiles the whole tree, so the
# package has to be present to build.
COPY packages/provisioning/package.json packages/provisioning/

# The repo pins ignore-scripts=true for supply-chain reasons, so the three
# packages that genuinely need to compile are rebuilt explicitly afterwards.
RUN npm ci --ignore-scripts && npm rebuild --ignore-scripts=false ssh2 cpu-features esbuild || true

COPY packages/locales packages/locales
COPY packages/shared packages/shared
COPY packages/provisioning packages/provisioning
COPY packages/cli packages/cli

# renet. Outside a SEA the CLI runs the renet it finds on PATH, and uploads that
# same binary to a machine whose renet differs, so the image must carry a
# release renet (with its embedded assets and the production license key), not
# one compiled here. deploy-proxy.sh builds it and stages it in workers/proxy/renet/;
# the directory itself is tracked so this COPY always has a source, and the
# check below names the missing file instead of failing later at run time.
COPY workers/proxy/renet/ /opt/rediacc-bin/
RUN test -x /opt/rediacc-bin/renet-linux-amd64 \
 || { echo "workers/proxy/renet/renet-linux-amd64 is missing: build it with .ci/scripts/deploy/deploy-proxy.sh (or copy a release renet-linux-amd64 there)" >&2; exit 1; }

# The shipped artifact is the esbuild BUNDLE, not the raw tsc output. The dist
# tree emits extensionless ESM imports that plain node cannot resolve; the bundle
# is what the installed `rdc` actually runs, so the executor runs it too. Same
# code, same resolution behavior, no third build path to keep in sync.
#
# The bundle takes its version FROM the staged renet, so the two can never
# disagree: the executor's rdc reports the version of the renet it ships.
RUN CLI_VERSION="$(/opt/rediacc-bin/renet-linux-amd64 version | awk '{print $3}')" \
 && test -n "$CLI_VERSION" \
 && export CLI_VERSION \
 && npm run build --workspace @rediacc/provisioning \
 && npm run build --workspace @rediacc/shared \
 && npm run build --workspace @rediacc/cli \
 && npm run build:bundle --workspace @rediacc/cli

# ---------------------------------------------------------------------------

FROM node:22-slim

# The executor opens SSH itself (that is its entire job), and rsync backs the
# renet binary staging path. renet itself is copied in below, from the build stage.
RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-client rsync ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Only the bundle and the native modules it dlopen's need to ship. Everything
# else (sources, tsc output, dev dependencies) stays in the build stage.
COPY --from=build /build/packages/cli/dist/cli-bundle.cjs ./cli-bundle.cjs
COPY --from=build /build/node_modules/ssh2 ./node_modules/ssh2
COPY --from=build /build/node_modules/cpu-features ./node_modules/cpu-features
COPY --from=build /opt/rediacc-bin/renet-linux-amd64 /usr/local/bin/renet
RUN renet version

# The container tier holds no key at rest: a client grants the config key per
# session over X25519, and it lives in memory only. There is nothing to persist,
# which is convenient, because container disks are ephemeral anyway.
ENV NODE_ENV=production
EXPOSE 8080

CMD ["node", "cli-bundle.cjs", "serve", "--mode", "container", "--port", "8080"]
