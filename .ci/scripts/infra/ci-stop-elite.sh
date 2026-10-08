#!/bin/bash
# Stop the elite on-premise services: a shim over rediacc_ci.infra.ci_stop_elite (path contract of the .ci/breakpoint tree).
set -euo pipefail
PYTHONPATH="$(dirname "${BASH_SOURCE[0]}")/../..${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m rediacc_ci.infra.ci_stop_elite "$@"
