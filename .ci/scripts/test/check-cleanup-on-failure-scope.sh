#!/bin/bash
# Guard cd-v2.yml's cleanup-on-failure job against scope regression.
#
# Finding K: the pre-WIP `if:` checked only `needs.publish.result == 'failure'`.
# Any post-publish failure (deploy-marketing-edge, deploy-account-edge,
# smoke-test) would leave versioned R2 bytes stranded because cleanup
# never fired. The WIP fix expanded both `needs:` and the `if:` to cover
# those jobs. This script enforces the expanded scope so a future narrowing
# regression is caught on the PR that introduces it, not after a Release
# failure strands bytes again.
#
# Why static, not runtime: inducing a real deploy-marketing-edge failure
# requires production infrastructure and would be hard to gate safely.
# A structural check catches the most likely regression (editing the
# needs/if of this job).
#
# Usage: check-cleanup-on-failure-scope.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
CD_V2="$ROOT_DIR/.github/workflows/cd-v2.yml"

require_file "$CD_V2"
require_cmd python3

# pyyaml is absent from ubuntu-slim by default; install locally if missing.
python3 -c "import yaml" 2>/dev/null || pip install --user --quiet pyyaml >/dev/null 2>&1 || pip3 install --user --quiet pyyaml >/dev/null 2>&1 || {
    log_error "Unable to install pyyaml (needed for workflow parsing)"
    exit 2
}

python3 - "$CD_V2" <<'PYEOF'
import sys
import yaml

path = sys.argv[1]
with open(path) as f:
    doc = yaml.safe_load(f)

jobs = doc.get('jobs', {})
job = jobs.get('cleanup-on-failure')
if not job:
    print(f"error: {path}: cleanup-on-failure job is missing", file=sys.stderr)
    sys.exit(1)

required_needs = {'publish', 'deploy-marketing-edge', 'deploy-account-edge', 'smoke-test'}
needs = set(job.get('needs') or [])
missing_needs = required_needs - needs
if missing_needs:
    print(f"error: {path}: cleanup-on-failure.needs missing: {sorted(missing_needs)}", file=sys.stderr)
    print(f"       current: {sorted(needs)}", file=sys.stderr)
    print("       Finding K requires all four deploy stages in needs so cleanup sees their results.", file=sys.stderr)
    sys.exit(1)

if_expr = job.get('if') or ''
if not isinstance(if_expr, str):
    print(f"error: {path}: cleanup-on-failure.if is not a string", file=sys.stderr)
    sys.exit(1)
# Must reference each .result by job id to fire on any one's failure
required_refs = [
    'needs.publish.result',
    'needs.deploy-marketing-edge.result',
    'needs.deploy-account-edge.result',
    'needs.smoke-test.result',
]
missing_refs = [r for r in required_refs if r not in if_expr]
if missing_refs:
    print(f"error: {path}: cleanup-on-failure.if does not reference: {missing_refs}", file=sys.stderr)
    print(f"       expr: {if_expr.strip()[:160]}", file=sys.stderr)
    print("       Finding K: narrow scope let post-publish failures strand R2 bytes; the if: must check all four.", file=sys.stderr)
    sys.exit(1)

# Must use always() so transitive skip propagation doesn't kill the job
if 'always()' not in if_expr:
    print(f"error: {path}: cleanup-on-failure.if missing always() prefix", file=sys.stderr)
    sys.exit(1)

print("ok")
PYEOF

log_info "cd-v2.yml cleanup-on-failure scope is intact (covers publish + 3 deploys + smoke-test)"
