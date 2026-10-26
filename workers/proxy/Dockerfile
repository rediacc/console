# The executor image: the rdc CLI, running as a server.
#
# It is deliberately the SAME artifact operators run locally. A separate
# server-only build would be a second implementation of vault building, policy
# evaluation, and the config crypto, and those are the last three things in this
# system that should ever be allowed to drift.
#
# NOTHING IS BUILT HERE. The image assembles the durable executor artifacts of one
# release (PLAN-proxy-cd-six-targets, Design item 8): `executor_artifacts fetch
# --version V --dest workers/proxy/stage/` for a deploy, or `executor_artifacts
# stage-local` for bench and local runs. workers/proxy/stage/ holds
#   cli-bundle.cjs, package.json, renet-linux-amd64, node-natives-linux-x64.tar, manifest.json
# and the image is the same bytes whatever machine builds it. Build context is the
# repo root:
#   docker build -f workers/proxy/Dockerfile .

# Pinned by digest (the multi-arch index of node:24-slim), so a rebuild of one
# release is the same base. `npm run pins -- bump image:proxy-node` moves the tag
# and the digest together.
FROM node:24-slim@sha256:55fb5f5a527ea2c5c4a95f963e48ef90aa38c7b346054fdc8ee9957a2b55d205

# The executor opens SSH itself (that is its entire job), and rsync backs the
# renet binary staging path.
RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-client rsync ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Bind-mounted, so the 200 MB renet lands in the image once, not once as a staged
# copy and again as the installed one. The manifest is the contract: every file it
# names must hash to its sha256, and a missing or extra-short stage fails by name
# rather than at run time. renet is a release binary (embedded assets, the
# production license key): outside a SEA the CLI runs the renet on PATH and uploads
# that same binary to a machine whose renet differs.
RUN --mount=type=bind,source=workers/proxy/stage,target=/stage \
    test -f /stage/manifest.json \
 || { echo "workers/proxy/stage/ has no manifest.json: run 'PYTHONPATH=.ci python3 -m rediacc_ci.deploy.executor_artifacts fetch --version V --dest workers/proxy/stage/' (or stage-local)" >&2; exit 1; }
RUN --mount=type=bind,source=workers/proxy/stage,target=/stage \
    node -e 'const m=require("/stage/manifest.json");for(const[n,e]of Object.entries(m.files))console.log(e.sha256+"  "+n)' > /tmp/stage.sha256 \
 && test -s /tmp/stage.sha256 \
 && (cd /stage && sha256sum -c /tmp/stage.sha256) \
 && cp /stage/cli-bundle.cjs /stage/package.json /app/ \
 && install -m 0755 /stage/renet-linux-amd64 /usr/local/bin/renet \
 && tar -xf /stage/node-natives-linux-x64.tar -C /app \
 && rm /tmp/stage.sha256

# Fails the build when the staged renet does not run on this base.
RUN renet version

# The container tier holds no key at rest: a client grants the config key per
# session over X25519, and it lives in memory only. There is nothing to persist,
# which is convenient, because container disks are ephemeral anyway.
ENV NODE_ENV=production
EXPOSE 8080

CMD ["node", "cli-bundle.cjs", "serve", "--mode", "container", "--port", "8080"]
