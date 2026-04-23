#!/bin/bash
# Audit GitHub Actions workflows for missing always() on JOB-LEVEL if:
# blocks that reference needs.*.result. Prevents the transitive-skip
# propagation bug (finding J): a downstream job whose if: references
# needs.X.result == 'success' without an always() / !cancelled() /
# !failure() prefix will silently skip whenever any upstream in X's
# transitive needs: chain skipped, even if X itself concluded as success.
#
# Only job-level if: blocks are audited. Step-level if: runs inside an
# already-running job, so the transitive-skip concern doesn't apply.
#
# Tolerated overrides (any one is enough to force evaluation):
#   always()      -- canonical GHA idiom
#   !cancelled()  -- common variant; matches success+failure+skipped
#   failure()     -- runs only on failure; implicitly overrides
#   success()     -- evaluates unconditionally (implicit default, but listing it here keeps us permissive)
#
# Exit 1 on any offender.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

if [[ "${CI:-}" == "true" ]]; then
    RED="" GREEN="" YELLOW="" NC=""
else
    RED='\033[0;31m' GREEN='\033[0;32m' YELLOW='\033[1;33m' NC='\033[0m'
fi

log_error() { echo -e "${RED}error: $1${NC}" >&2; }
log_success() { echo -e "${GREEN}success: $1${NC}"; }
log_warn() { echo -e "${YELLOW}warn: $1${NC}"; }
log_info() { echo "info: $1"; }

WORKFLOWS_DIR="$ROOT_DIR/.github/workflows"
if [[ ! -d "$WORKFLOWS_DIR" ]]; then
    log_warn "No workflows directory at $WORKFLOWS_DIR; nothing to check"
    exit 0
fi

log_info "Checking job-level if: blocks for always()/!cancelled() on needs.*.result references"

python3 - "$WORKFLOWS_DIR" <<'PYEOF'
import os
import re
import sys
import yaml

workflows_dir = sys.argv[1]
offenders = []

OVERRIDE_RE = re.compile(r'(always\(\)|!\s*cancelled\(\)|failure\(\)|success\(\))')
NEEDS_RESULT_RE = re.compile(r'needs\.[A-Za-z0-9_-]+\.result')


def check_if_expr(path, job_name, expr):
    if not isinstance(expr, str):
        return
    if not NEEDS_RESULT_RE.search(expr):
        return
    if OVERRIDE_RE.search(expr):
        return
    offenders.append((path, job_name, expr.strip()[:160]))


for root, _dirs, files in os.walk(workflows_dir):
    for fname in sorted(files):
        if not (fname.endswith('.yml') or fname.endswith('.yaml')):
            continue
        path = os.path.join(root, fname)
        try:
            with open(path) as f:
                doc = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(f"{path}: YAML parse error: {e}", file=sys.stderr)
            offenders.append((path, '<yaml-error>', str(e)))
            continue
        if not isinstance(doc, dict):
            continue
        jobs = doc.get('jobs') or {}
        if not isinstance(jobs, dict):
            continue
        for job_name, job_spec in jobs.items():
            if not isinstance(job_spec, dict):
                continue
            if 'if' in job_spec:
                check_if_expr(path, job_name, job_spec['if'])

if offenders:
    for path, job_name, expr in offenders:
        rel = os.path.relpath(path, os.path.dirname(os.path.dirname(workflows_dir)))
        print(f"{rel}: job '{job_name}' has if: without always()/!cancelled()", file=sys.stderr)
        print(f"    expr: {expr}", file=sys.stderr)
    sys.exit(1)

sys.exit(0)
PYEOF

case "$?" in
    0)
        log_success "All job-level if: blocks using needs.*.result include an always()/!cancelled() override"
        ;;
    *)
        log_error "Workflow gate audit found offenders (see above)."
        log_error "Fix: prefix the offending if: with 'always() &&' so transitive skip propagation cannot silently disable the job."
        exit 1
        ;;
esac
