#!/bin/bash
# Structural invariants over GitHub Actions workflow YAML that only a real
# parser can see. Two independent checks, one pyyaml bootstrap.
#
# CHECK 1 -- job-level if: needs always()
#   Audit JOB-LEVEL if: blocks that reference needs.*.result. Prevents the
#   transitive-skip propagation bug (finding J): a downstream job whose if:
#   references needs.X.result == 'success' without an always() / !cancelled() /
#   !failure() prefix will silently skip whenever any upstream in X's transitive
#   needs: chain skipped, even if X itself concluded as success.
#
#   Only job-level if: blocks are audited. Step-level if: runs inside an
#   already-running job, so the transitive-skip concern doesn't apply.
#
#   Tolerated overrides (any one is enough to force evaluation):
#     always()      -- canonical GHA idiom
#     !cancelled()  -- common variant; matches success+failure+skipped
#     failure()     -- runs only on failure; implicitly overrides
#     success()     -- evaluates unconditionally (implicit default, but listing it here keeps us permissive)
#
# CHECK 2 -- reusable-workflow call contract
#   Inside a reusable workflow, `secrets.FOO` for a secret that is NOT declared
#   under on.workflow_call.secrets evaluates to the EMPTY STRING. No warning, no
#   failure -- the deploy just ships a blank credential. That is exactly how
#   OTLP_CLIENT_CREDENTIALS_{EU,US,ASIA} came to be read by cd-deploy-account.yml
#   while being declared by nobody, so every deployed account Worker ran with
#   OTLP_CLIENT_CREDENTIALS="" and shipped no telemetry. Nothing caught it
#   because an empty secret is indistinguishable from a working one at the YAML
#   layer. So assert the contract in both directions:
#     a) a reusable workflow may not read a secret it does not declare
#     b) a caller must pass every required secret/input the callee declares
#     c) a caller may not pass a secret/input the callee never declares (dead
#        wiring: it looks like the value flows, and it does not)
#
# Exit 1 on any offender, 2 on setup error.

set -uo pipefail

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

# Overridable so the gate test can drive both checks against fixture trees.
WORKFLOWS_DIR="${WORKFLOWS_DIR:-$ROOT_DIR/.github/workflows}"

# Anti-vacuity: a missing directory used to `exit 0` here, which meant a moved
# or renamed workflow tree turned this gate into a no-op that still reported
# success. Nothing to check is a failure, not a pass.
if [[ ! -d "$WORKFLOWS_DIR" ]]; then
    log_error "No workflows directory at $WORKFLOWS_DIR -- this check is blind"
    exit 1
fi

# pyyaml is absent from ubuntu-slim by default; install locally if missing.
python3 -c "import yaml" 2>/dev/null || pip install --user --quiet pyyaml >/dev/null 2>&1 || pip3 install --user --quiet pyyaml >/dev/null 2>&1 || {
    log_error "Unable to install pyyaml (needed for workflow parsing)"
    exit 2
}

FAILED=0

# --- Check 1 ---------------------------------------------------------------
log_info "Checking job-level if: blocks for always()/!cancelled() on needs.*.result references"

python3 - "$WORKFLOWS_DIR" <<'PYEOF'
import os
import re
import sys
import yaml

workflows_dir = sys.argv[1]
offenders = []
parsed = 0

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
        parsed += 1
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

if parsed == 0:
    print(f"{workflows_dir}: no workflow YAML parsed -- this check is blind", file=sys.stderr)
    sys.exit(3)

if offenders:
    for path, job_name, expr in offenders:
        rel = os.path.relpath(path, os.path.dirname(os.path.dirname(workflows_dir)))
        print(f"{rel}: job '{job_name}' has if: without always()/!cancelled()", file=sys.stderr)
        print(f"    expr: {expr}", file=sys.stderr)
    sys.exit(1)

sys.exit(0)
PYEOF

RC=$?
if [[ $RC -eq 0 ]]; then
    log_success "All job-level if: blocks using needs.*.result include an always()/!cancelled() override"
elif [[ $RC -eq 3 ]]; then
    log_error "Fix: point WORKFLOWS_DIR at a tree that contains workflow YAML; a check with no input cannot pass."
    FAILED=1
else
    log_error "Workflow gate audit found offenders (see above)."
    log_error "Fix: prefix the offending if: with 'always() &&' so transitive skip propagation cannot silently disable the job."
    FAILED=1
fi

# --- Check 2 ---------------------------------------------------------------
log_info "Checking reusable-workflow secret/input contracts"

python3 - "$WORKFLOWS_DIR" <<'PYEOF'
import os
import re
import sys
import yaml

workflows_dir = sys.argv[1]

# `secrets.X`, but not when it is part of a path or filename -- otherwise
# "set-account-worker-secrets.sh" reads as a reference to a secret named `sh`.
USE_RE = re.compile(r'(?<![\w./-])secrets\.([A-Za-z_][A-Za-z0-9_]*)')

# Always available inside a workflow; never declared under workflow_call.
IMPLICIT = {'GITHUB_TOKEN'}

docs = {}
texts = {}
for fname in sorted(os.listdir(workflows_dir)):
    if not (fname.endswith('.yml') or fname.endswith('.yaml')):
        continue
    path = os.path.join(workflows_dir, fname)
    try:
        with open(path) as f:
            text = f.read()
        docs[fname] = yaml.safe_load(text)
        texts[fname] = text
    except (yaml.YAMLError, OSError) as e:
        print(f"{fname}: unreadable ({e})", file=sys.stderr)
        sys.exit(1)

if not docs:
    print(f"{workflows_dir}: no workflow YAML parsed -- this check is blind", file=sys.stderr)
    sys.exit(3)


def workflow_call(doc):
    """on: is parsed as the boolean True by YAML 1.1, so look under both keys."""
    if not isinstance(doc, dict):
        return {}
    on = doc.get('on', doc.get(True)) or {}
    if not isinstance(on, dict):
        return {}
    wc = on.get('workflow_call') or {}
    return wc if isinstance(wc, dict) else {}


offenders = []

# (a) a reusable workflow may not read a secret it does not declare
for fname, doc in docs.items():
    wc = workflow_call(doc)
    if not wc:
        continue
    declared = set((wc.get('secrets') or {}).keys())
    used = set(USE_RE.findall(texts[fname])) - IMPLICIT
    for name in sorted(used - declared):
        offenders.append(
            f"{fname}: reads secrets.{name} but does not declare it under "
            f"on.workflow_call.secrets -- it will silently evaluate to \"\""
        )

# (b)/(c) caller <-> callee contract
for fname, doc in docs.items():
    jobs = (doc or {}).get('jobs') or {}
    if not isinstance(jobs, dict):
        continue
    for jid, job in jobs.items():
        if not isinstance(job, dict):
            continue
        uses = job.get('uses', '')
        if not isinstance(uses, str) or not uses.startswith('./.github/workflows/'):
            continue
        callee = os.path.basename(uses)
        if callee not in docs:
            offenders.append(f"{fname}: job '{jid}' calls {uses}, which does not exist")
            continue
        wc = workflow_call(docs[callee])
        dsec = wc.get('secrets') or {}
        dinp = wc.get('inputs') or {}

        passed = job.get('secrets')
        if passed != 'inherit':
            got = set((passed or {}).keys())
            required = {k for k, v in dsec.items() if isinstance(v, dict) and v.get('required')}
            for name in sorted(required - got):
                offenders.append(
                    f"{fname}: job '{jid}' -> {callee}: does not pass required secret {name}"
                )
            for name in sorted(got - set(dsec)):
                offenders.append(
                    f"{fname}: job '{jid}' -> {callee}: passes secret {name}, which {callee} "
                    f"never declares -- the value goes nowhere"
                )

        got = set((job.get('with') or {}).keys())
        required = {k for k, v in dinp.items() if isinstance(v, dict) and v.get('required')}
        for name in sorted(required - got):
            offenders.append(
                f"{fname}: job '{jid}' -> {callee}: does not pass required input {name}"
            )
        for name in sorted(got - set(dinp)):
            offenders.append(
                f"{fname}: job '{jid}' -> {callee}: passes input {name}, which {callee} "
                f"never declares -- the value goes nowhere"
            )

if offenders:
    for line in offenders:
        print(line, file=sys.stderr)
    sys.exit(1)

sys.exit(0)
PYEOF

RC=$?
if [[ $RC -eq 0 ]]; then
    log_success "Reusable-workflow secret/input contracts hold in both directions"
elif [[ $RC -eq 3 ]]; then
    log_error "Fix: point WORKFLOWS_DIR at a tree that contains workflow YAML; a check with no input cannot pass."
    FAILED=1
else
    log_error "Reusable-workflow contract violations (see above)."
    log_error "Fix: declare the secret under on.workflow_call.secrets in the callee AND pass it from every caller. An undeclared secret reads as \"\" with no error."
    FAILED=1
fi

exit "$FAILED"
