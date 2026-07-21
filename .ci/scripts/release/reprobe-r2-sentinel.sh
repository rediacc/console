#!/bin/bash
# Re-read R2 after a sentinel write and assert the sentinel is really there.
#
# WHY: the writer short-circuits when a sentinel already exists and swallows a
# number of "nothing to do" cases. Trusting its exit code alone would let a
# backfill report success while the drift the operator ran it for is still
# there. This probes the live bucket instead.
#
# Usage:
#   .ci/scripts/release/reprobe-r2-sentinel.sh
#
# Required env:
#   VERSION               version tag with leading v, e.g. v1.1.2
#   R2_ACCESS_KEY_ID      exported to the validator as AWS_ACCESS_KEY_ID
#   R2_SECRET_ACCESS_KEY  exported to the validator as AWS_SECRET_ACCESS_KEY
#   R2_ENDPOINT           read directly by release-state-validator.sh
#
# Run locally (read-only, needs R2 credentials):
#   VERSION=v1.1.2 R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... R2_ENDPOINT=... \
#     .ci/scripts/release/reprobe-r2-sentinel.sh
#
# Shell options: the workflow block already ran under `set -euo pipefail`;
# kept identical here.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../lib/release-state-validator.sh"

require_cmd aws
: "${VERSION:?reprobe-r2-sentinel.sh: VERSION must be set}"
: "${R2_ACCESS_KEY_ID:?reprobe-r2-sentinel.sh: R2_ACCESS_KEY_ID must be set}"
: "${R2_SECRET_ACCESS_KEY:?reprobe-r2-sentinel.sh: R2_SECRET_ACCESS_KEY must be set}"
: "${R2_ENDPOINT:?reprobe-r2-sentinel.sh: R2_ENDPOINT must be set}"

export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION=auto
missing=0
# BLOCKER: the single-element list is deliberate and moved verbatim out of backfill-release-sentinel.yml -- cli is the only product with `.released` sentinels today, and keeping the loop shape means adding the next one is a one-word edit rather than a restructure
# shellcheck disable=SC2043
for product in cli; do
    if rsv_sentinel_exists "$product" "$VERSION"; then
        echo "✓ $product/$VERSION/.released present in R2"
    else
        echo "::error::$product/$VERSION/.released NOT present after write"
        missing=1
    fi
done
[[ $missing -eq 0 ]]
