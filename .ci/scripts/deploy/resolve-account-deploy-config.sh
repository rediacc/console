#!/bin/bash
# Pick the Worker name / domain / sandbox flag for one region of an account
# deploy, and emit them as step outputs.
#
# WHY: every region ships twice, once to stable and once to edge, and each
# channel has its own Worker name and hostname in regions.json. Resolving that
# fan-out once, into named outputs, keeps the later deploy / secret / webhook
# steps from re-deriving it (and drifting apart while doing so).
#
# Usage:
#   .ci/scripts/deploy/resolve-account-deploy-config.sh
#
# Required env:
#   TARGET                    deploy channel: stable | edge
#   MATRIX_ID                 region id from regions.json, e.g. eu
#   MATRIX_SECRET_SUFFIX      region suffix used for secret indirection, e.g. EU
#   MATRIX_WORKER_NAME        stable Worker name
#   MATRIX_DOMAIN             stable hostname
#   MATRIX_EDGE_WORKER_NAME   edge Worker name
#   MATRIX_EDGE_DOMAIN        edge hostname
#   GITHUB_OUTPUT             step-output file to append the resolved values to
#
# Outputs: region, suffix, worker, domain, sandbox
#
# Run locally (read-only):
#   TARGET=edge MATRIX_ID=eu MATRIX_SECRET_SUFFIX=EU \
#     MATRIX_WORKER_NAME=w MATRIX_DOMAIN=d \
#     MATRIX_EDGE_WORKER_NAME=ew MATRIX_EDGE_DOMAIN=ed \
#     GITHUB_OUTPUT=/dev/stdout \
#     .ci/scripts/deploy/resolve-account-deploy-config.sh
#
# Shell options: the workflow block ran under plain `bash -e`; `-uo pipefail`
# are added here. Neither can change the outcome: every variable read is
# guarded above, and the script contains no pipeline.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

: "${TARGET:?resolve-account-deploy-config.sh: TARGET must be set}"
: "${MATRIX_ID:?resolve-account-deploy-config.sh: MATRIX_ID must be set}"
: "${MATRIX_SECRET_SUFFIX:?resolve-account-deploy-config.sh: MATRIX_SECRET_SUFFIX must be set}"
: "${GITHUB_OUTPUT:?resolve-account-deploy-config.sh: GITHUB_OUTPUT must be set}"

REGION="$MATRIX_ID"
SUFFIX="$MATRIX_SECRET_SUFFIX"
if [[ "$TARGET" == "stable" ]]; then
    WORKER="${MATRIX_WORKER_NAME:-}"
    DOMAIN="${MATRIX_DOMAIN:-}"
    SANDBOX=""
else
    WORKER="${MATRIX_EDGE_WORKER_NAME:-}"
    DOMAIN="${MATRIX_EDGE_DOMAIN:-}"
    SANDBOX="--sandbox"
fi
echo "region=$REGION" >>"$GITHUB_OUTPUT"
echo "suffix=$SUFFIX" >>"$GITHUB_OUTPUT"
echo "worker=$WORKER" >>"$GITHUB_OUTPUT"
echo "domain=$DOMAIN" >>"$GITHUB_OUTPUT"
echo "sandbox=$SANDBOX" >>"$GITHUB_OUTPUT"
