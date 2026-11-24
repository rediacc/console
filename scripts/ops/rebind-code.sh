#!/usr/bin/env bash
# The program REDIACC_IP_REBIND_CODE_COMMAND names for a bench config (rdc.sh exports it):
# prints the current bench-root authenticator code from the vault on stdout, nothing else.
# The logic and its refusals live in .ci/rediacc_ci/ops/rebind_code.py.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../.." && pwd -P)"
PYTHONPATH="$ROOT_DIR/.ci${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m rediacc_ci.ops.rebind_code "$@"
