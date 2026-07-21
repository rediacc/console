#!/bin/bash
# Hotfix promotion: retag the published :edge Docker images as :stable.
#
# WHY: this is the emergency lane used by `Release` with publish_stable=true,
# skipping the normal 7-day soak. `buildx imagetools create` copies the manifest
# list, so multi-arch images are promoted without pulling or rebuilding anything.
#
# The on-prem server image lives at ghcr.io/rediacc/server (outside elite/), so
# it is handled separately from the renet/rdc loop.
#
# Usage:
#   .ci/scripts/deploy/promote-docker-to-stable-hotfix.sh
#
# Requires a docker daemon already authenticated to ghcr.io (the workflow does
# this with docker/login-action before calling).
#
# NOTE: this MUTATES the production :stable tags. Do not run it locally against
# a real GHCR login.
#
# Shell options: the workflow block ran under plain `bash -e`. `-u`/`pipefail`
# are added here; there are no variables beyond the loop index and no pipelines,
# so neither can change the outcome.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd docker

for image in renet rdc; do
    echo "Promoting ${image}: edge -> stable"
    docker buildx imagetools create \
        -t "ghcr.io/rediacc/${image}:stable" \
        "ghcr.io/rediacc/${image}:edge"
done
# On-prem server image lives at ghcr.io/rediacc/server (outside elite/).
echo "Promoting server: edge -> stable"
docker buildx imagetools create \
    -t "ghcr.io/rediacc/server:stable" \
    "ghcr.io/rediacc/server:edge"
echo "Docker promoted to stable"
