# The web image: Astro build/dev plus agent-browser and its Chrome.
#
# WHY IT IS SEPARATE FROM THE RENDER IMAGE. Both carry a browser, and merging them looks
# tempting. They are split because their browsers are DIFFERENT and neither substitutes
# for the other: the render image uses Remotion's own pinned chrome-headless-shell (the
# version is part of render determinism), while this one uses agent-browser's Chrome for
# Testing, which is chosen by the agent-browser version. One image with two Chromes is
# larger than two images with one each, and it makes a render's browser version depend on
# a measurement tool's release cadence.
#
# THREE INSTALL GOTCHAS, ALL HIT LIVE ON 2026-08-27, all encoded below rather than left in
# a README nobody reads when the build breaks:
#   1. This repo's .npmrc sets ignore-scripts=true, so a plain `npm i -g agent-browser`
#      installs the package and NEVER links the binary. It needs --allow-scripts.
#   2. agent-browser declares engines.node >= 24 against our 22. Cosmetic: the bin symlink
#      points at a prebuilt native binary and the JS shim never runs. npm still warns.
#   3. Chrome needs system libs. `agent-browser install --with-deps` wants root for the
#      libs; running the BROWSER download as root puts it under /root where the runtime
#      user cannot reach it. So: libs as root, browser as the runtime user, separately.
FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl \
      libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
      libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
      libgbm1 libasound2 libpango-1.0-0 libcairo2 libxss1 \
      fontconfig fonts-inter fonts-jetbrains-mono fonts-dejavu-core \
    && fc-cache -f \
    && rm -rf /var/lib/apt/lists/*

# Gotcha 1 and 2. --allow-scripts is what links the binary; the engine warning is expected.
RUN npm install -g --allow-scripts=agent-browser agent-browser@latest \
    && agent-browser --version

# Gotcha 3: the browser is fetched as the RUNTIME user, into a path it owns.
ENV AGENT_BROWSER_HOME=/browsers
RUN mkdir -p /browsers && chmod 0777 /browsers

# Prove the binary is actually reachable, rather than trusting that npm said "added".
RUN command -v agent-browser >/dev/null || { echo "FATAL: agent-browser not on PATH"; exit 1; }

WORKDIR /work
