#!/bin/bash
# Pre-pull and authenticate GHCR images: a shim over rediacc_ci.infra.ci_pull_images (path contract of the .ci/breakpoint tree).
set -euo pipefail
PYTHONPATH="${BASH_SOURCE[0]%/*}/../..${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m rediacc_ci.infra.ci_pull_images "$@"
