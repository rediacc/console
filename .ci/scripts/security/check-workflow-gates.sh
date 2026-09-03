#!/bin/bash
# Structural invariants over GitHub Actions workflow YAML that only a real
# parser can see. Four independent checks, one pyyaml bootstrap.
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
#   OBS_OTLP_CREDENTIALS="" and shipped no telemetry. Nothing caught it
#   because an empty secret is indistinguishable from a working one at the YAML
#   layer. So assert the contract in both directions:
#     a) a reusable workflow may not read a secret it does not declare
#     b) a caller must pass every required secret/input the callee declares
#     c) a caller may not pass a secret/input the callee never declares (dead
#        wiring: it looks like the value flows, and it does not)
#
# CHECK 3 -- ubuntu-slim jobs declare a timeout under the platform cap
#   ubuntu-slim has a HARD 15-minute job cap. Exceeding it marks the job
#   CANCELLED with no failed step, which reads as neither pass nor fail: it
#   poisons CI Complete and leaves the watchdog nothing to classify.
#   quality-security hit this twice in three runs. Requiring an explicit
#   timeout-minutes <= 14 turns that silent kill into an ordinary timeout
#   failure naming the step that hung.
#
# CHECK 4 -- external-caller contracts (.github/external-callers.yml)
#   CHECK 2 scans .github/workflows only, so it cannot see callers in OTHER
#   repositories -- and those are the only callers that can actually break,
#   because a same-repo caller moves with its callee in one commit while a
#   cross-repo one resolves `@main` at run time. `.github/external-callers.yml`
#   declares them; this runs CHECK 2's contract against each declaration,
#   re-checks the declaration against the caller's real file when the submodule
#   is checked out, and fails on any external caller that is not registered.
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

# Overridable so the gate test can drive all three checks against fixture trees.
WORKFLOWS_DIR="${WORKFLOWS_DIR:-$ROOT_DIR/.github/workflows}"

# Ceiling for CHECK 3. One minute under ubuntu-slim's hard 15-minute platform
# cap, so the job's own timeout wins the race and the failure says which step
# hung. Not lower: the watchdog generation budget (480s poll + ~25s AI + up to
# 5min force-cancel wait) is 13.4 min by design.
SLIM_TIMEOUT_MAX="${SLIM_TIMEOUT_MAX:-14}"

# Anti-vacuity for CHECK 3: a tree with no ubuntu-slim job at all means the check
# asserted nothing, which must not read as success -- that is how a renamed
# runner label turns a gate into a no-op. But the guard is scoped to the REAL
# workflow tree, because the OTHER checks' fixture trees legitimately contain no
# slim jobs and CHECK 3 must not fail their tests for them. The test drives this
# explicitly to cover the blind case.
if [[ -z "${SLIM_TIMEOUT_REQUIRE_COVERAGE:-}" ]]; then
    if [[ "$WORKFLOWS_DIR" == "$ROOT_DIR/.github/workflows" ]]; then
        SLIM_TIMEOUT_REQUIRE_COVERAGE=true
    else
        SLIM_TIMEOUT_REQUIRE_COVERAGE=false
    fi
fi

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

# --- Check 3 ---------------------------------------------------------------
log_info "Checking every ubuntu-slim job declares timeout-minutes <= $SLIM_TIMEOUT_MAX"

python3 - "$WORKFLOWS_DIR" "$SLIM_TIMEOUT_MAX" "$SLIM_TIMEOUT_REQUIRE_COVERAGE" <<'PYEOF'
# ubuntu-slim is a 1-vCPU runner with a HARD 15-minute job cap enforced by the
# platform, not by us. When a job hits it the run does not fail -- the job is
# marked CANCELLED with no failed step, which poisons CI Complete and gives the
# watchdog nothing to classify. quality-security hit this twice in three runs
# during the 0722-1 wave before it was moved to ubuntu-latest.
#
# So every slim job must declare its own timeout BELOW the cap. Then a hang
# fails as a timeout, in the job that owns it, with a message naming the step.
# 12 rather than 15 leaves room for the runner's own setup/teardown, which is
# outside the steps but inside the cap.
#
# A job that legitimately needs longer does not get a bigger number here: it
# gets ubuntu-latest. That is the whole point -- the number is not a dial, it is
# an assertion that this job fits on this runner.
import os
import sys
import yaml

workflows_dir, limit = sys.argv[1], int(sys.argv[2])
require_coverage = sys.argv[3] == 'true'
SLIM = 'ubuntu-slim'
offenders = []
checked = 0

names = sorted(
    f for f in os.listdir(workflows_dir)
    if f.endswith(('.yml', '.yaml'))
)
if not names:
    print(f'no workflow files under {workflows_dir}', file=sys.stderr)
    sys.exit(3)

for fname in names:
    with open(os.path.join(workflows_dir, fname)) as fh:
        try:
            doc = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            print(f'{fname}: unparseable YAML: {exc}', file=sys.stderr)
            sys.exit(3)
    if not isinstance(doc, dict):
        continue

    for jid, job in (doc.get('jobs') or {}).items():
        if not isinstance(job, dict):
            continue
        runs_on = job.get('runs-on')
        # Matrix-driven runners (`runs-on: ${{ matrix.runner }}`) are not
        # resolvable here; a literal slim label is.
        labels = runs_on if isinstance(runs_on, list) else [runs_on]
        if SLIM not in [x for x in labels if isinstance(x, str)]:
            continue

        checked += 1
        # Named `declared`, not `timeout`: check-commands.sh scans this file as
        # bash and has no heredoc scoping, so a Python line reading
        # `timeout = ...` is indistinguishable from the bash command invocation
        # `timeout = ...` actually is. That gate is RIGHT about bash and must not
        # be taught to skip heredoc bodies -- a `ssh host <<'EOF' ... timeout 5`
        # body is exactly the remote-minimal-environment case it exists to
        # catch. Avoiding the collision is the fix; widening the gate is not.
        declared = job.get('timeout-minutes')
        if declared is None:
            offenders.append(
                f"{fname}: job '{jid}' runs on {SLIM} without timeout-minutes -- "
                f"a hang rides to the platform's 15-minute cap and reports as "
                f"cancelled, not failed"
            )
        elif not isinstance(declared, int):
            offenders.append(
                f"{fname}: job '{jid}' has a non-literal timeout-minutes "
                f"({declared!r}); this gate cannot verify it stays under the cap"
            )
        elif declared > limit:
            offenders.append(
                f"{fname}: job '{jid}' declares timeout-minutes: {declared} on "
                f"{SLIM}, above the {limit}-minute ceiling -- move it to "
                f"ubuntu-latest instead of raising the number"
            )

if not checked and require_coverage:
    print(f'no {SLIM} jobs found under {workflows_dir} -- this check is blind',
          file=sys.stderr)
    sys.exit(3)

if offenders:
    for line in offenders:
        print(line, file=sys.stderr)
    sys.exit(1)

sys.exit(0)
PYEOF

RC=$?
if [[ $RC -eq 0 ]]; then
    log_success "Every ubuntu-slim job declares timeout-minutes <= $SLIM_TIMEOUT_MAX"
elif [[ $RC -eq 3 ]]; then
    log_error "Fix: point WORKFLOWS_DIR at a tree that contains ubuntu-slim jobs; a check with no input cannot pass."
    FAILED=1
else
    log_error "ubuntu-slim timeout violations (see above)."
    log_error "Fix: add 'timeout-minutes: $SLIM_TIMEOUT_MAX' (or less) to the job, or move it to ubuntu-latest if it genuinely needs longer."
    FAILED=1
fi

# --- Check 4 ---------------------------------------------------------------
# CHECK 2 above scans WORKFLOWS_DIR only, so it is structurally blind to callers
# that live in OTHER repositories -- which are the only callers that can suffer
# the breakage it exists to prevent. A same-repo caller moves with its callee in
# one commit; a cross-repo caller resolves `@main` at run time, so a callee edit
# merged here breaks the other repo's next run, an hour later, in a log nobody
# on this PR is reading.
#
# .github/external-callers.yml declares them. CHECK 4 runs CHECK 2's three-way
# contract against each declaration, verifies the declaration still matches the
# caller's real file when the submodule is checked out, and refuses to let an
# undeclared external caller exist.
EXTERNAL_CALLERS_ROOT="${EXTERNAL_CALLERS_ROOT:-$ROOT_DIR}"
if [[ -z "${EXTERNAL_CALLERS_FILE:-}" ]]; then
    if [[ "$WORKFLOWS_DIR" == "$ROOT_DIR/.github/workflows" ]]; then
        EXTERNAL_CALLERS_FILE="$ROOT_DIR/.github/external-callers.yml"
    else
        # A CHECK 1/2/3 fixture tree has no external callers to speak of. The
        # real tree always takes the branch above, so this is not an escape
        # hatch anyone can reach by accident.
        EXTERNAL_CALLERS_FILE=""
    fi
fi

if [[ -z "$EXTERNAL_CALLERS_FILE" ]]; then
    log_info "Skipping external-caller contract check (fixture tree: no registry)"
else
    log_info "Checking external-caller contracts against $(basename "$EXTERNAL_CALLERS_FILE")"

    python3 - "$WORKFLOWS_DIR" "$EXTERNAL_CALLERS_FILE" "$EXTERNAL_CALLERS_ROOT" <<'PYEOF'
import glob
import os
import sys
import yaml

workflows_dir, registry_file, scan_root = sys.argv[1], sys.argv[2], sys.argv[3]

offenders = []


def die_blind(msg):
    print(f"{msg} -- this check is blind", file=sys.stderr)
    sys.exit(3)


def load(path):
    with open(path) as fh:
        return yaml.safe_load(fh.read())


if not os.path.isfile(registry_file):
    die_blind(f"{registry_file}: no external-caller registry")

try:
    registry = load(registry_file)
except (yaml.YAMLError, OSError) as exc:
    print(f"{registry_file}: unreadable ({exc})", file=sys.stderr)
    sys.exit(1)

entries = (registry or {}).get('callers') or []
if not isinstance(entries, list) or not entries:
    die_blind(f"{registry_file}: declares no callers")


def workflow_call(doc):
    """on: is parsed as the boolean True by YAML 1.1, so look under both keys."""
    if not isinstance(doc, dict):
        return {}
    on = doc.get('on', doc.get(True)) or {}
    if not isinstance(on, dict):
        return {}
    wc = on.get('workflow_call') or {}
    return wc if isinstance(wc, dict) else {}


REQUIRED_FIELDS = ('caller', 'repo', 'pinned_at', 'calls', 'passes_inputs', 'passes_secrets')

# --- (a) the declared contract must hold against the callee's real signature
registered = set()
for i, entry in enumerate(entries):
    if not isinstance(entry, dict):
        offenders.append(f"{registry_file}: caller #{i} is not a mapping")
        continue
    missing = [f for f in REQUIRED_FIELDS if f not in entry]
    if missing:
        offenders.append(
            f"{registry_file}: caller #{i} is missing {', '.join(missing)}"
        )
        continue

    caller = entry['caller']
    calls = entry['calls']
    registered.add((caller, calls))

    callee_path = os.path.join(workflows_dir, os.path.basename(calls))
    if not os.path.isfile(callee_path):
        offenders.append(
            f"{caller} -> {calls}: the callee does not exist in this repo. "
            f"An external caller pinned at {entry['pinned_at']} will fail on its "
            f"next run; restore the workflow or update the caller first."
        )
        continue

    wc = workflow_call(load(callee_path))
    if not wc:
        offenders.append(
            f"{caller} -> {calls}: the callee declares no on.workflow_call block, "
            f"so it cannot be called from another repository at all"
        )
        continue

    dinp = wc.get('inputs') or {}
    dsec = wc.get('secrets') or {}
    got_inp = set(entry['passes_inputs'] or [])
    got_sec = entry['passes_secrets']
    inherits = got_sec == 'inherit'
    got_sec = set() if inherits else set(got_sec or [])

    for name in sorted({k for k, v in dinp.items() if isinstance(v, dict) and v.get('required')} - got_inp):
        offenders.append(f"{caller} -> {calls}: does not pass required input {name}")
    for name in sorted(got_inp - set(dinp)):
        offenders.append(
            f"{caller} -> {calls}: passes input {name}, which {os.path.basename(calls)} "
            f"never declares -- the value goes nowhere"
        )
    if not inherits:
        for name in sorted({k for k, v in dsec.items() if isinstance(v, dict) and v.get('required')} - got_sec):
            offenders.append(
                f"{caller} -> {calls}: does not pass required secret {name}. Making it "
                f"`required: false` in the callee is not a fix -- it ships \"\"."
            )
        for name in sorted(got_sec - set(dsec)):
            offenders.append(
                f"{caller} -> {calls}: passes secret {name}, which "
                f"{os.path.basename(calls)} never declares -- the value goes nowhere"
            )

# --- (b) the declaration must match the caller's real file, when we have it
CONSOLE_PREFIX = 'rediacc/console/'
verified = 0
for entry in entries:
    if not isinstance(entry, dict) or any(f not in entry for f in REQUIRED_FIELDS):
        continue
    caller = entry['caller']
    abs_caller = os.path.join(scan_root, caller)
    # The submodule holding this caller may simply not be checked out. That is
    # not a finding; a checked-out submodule that has LOST the file is.
    repo_tree = os.path.join(scan_root, caller.split('/.github/')[0], '.github', 'workflows')
    if not os.path.isfile(abs_caller):
        if os.path.isdir(repo_tree):
            offenders.append(
                f"{caller}: registered here but absent from a checked-out tree -- "
                f"delete the entry or restore the file"
            )
        continue

    try:
        doc = load(abs_caller)
    except (yaml.YAMLError, OSError) as exc:
        offenders.append(f"{caller}: unreadable ({exc})")
        continue

    want_uses_prefix = CONSOLE_PREFIX + entry['calls'] + '@'
    found = False
    for jid, job in ((doc or {}).get('jobs') or {}).items():
        if not isinstance(job, dict):
            continue
        uses = job.get('uses')
        if not isinstance(uses, str) or not uses.startswith(want_uses_prefix):
            continue
        found = True
        ref = uses.split('@', 1)[1]
        if ref != entry['pinned_at']:
            offenders.append(
                f"{caller}: job '{jid}' pins {entry['calls']}@{ref}, registry says "
                f"@{entry['pinned_at']}"
            )
        real_inp = set((job.get('with') or {}).keys())
        passed = job.get('secrets')
        real_sec = 'inherit' if passed == 'inherit' else set((passed or {}).keys())
        if real_inp != set(entry['passes_inputs'] or []):
            offenders.append(
                f"{caller}: job '{jid}' passes inputs {sorted(real_inp)}, registry "
                f"declares {sorted(entry['passes_inputs'] or [])}"
            )
        declared_sec = entry['passes_secrets']
        norm_declared = 'inherit' if declared_sec == 'inherit' else set(declared_sec or [])
        if real_sec != norm_declared:
            offenders.append(
                f"{caller}: job '{jid}' passes secrets "
                f"{real_sec if real_sec == 'inherit' else sorted(real_sec)}, registry "
                f"declares {norm_declared if norm_declared == 'inherit' else sorted(norm_declared)}"
            )
        verified += 1
    if not found:
        offenders.append(
            f"{caller}: no job calls {CONSOLE_PREFIX}{entry['calls']} -- the registry "
            f"entry describes a call that is not there"
        )

# --- (c) completeness: every external caller on disk must be registered
# A blind leg is reported only when there is nothing else to say. A concrete
# offender IS evidence the check ran, and burying it under "this check is blind"
# was how the first version of CHECK 4 reported a stale registry entry as a
# missing submodule.
blind = []
trees = sorted(glob.glob(os.path.join(scan_root, 'private', '*', '.github', 'workflows')))
if not trees:
    blind.append(
        f"no private/*/.github/workflows tree under {scan_root}: the completeness "
        f"scan cannot see whether an unregistered external caller exists"
    )

for tree in trees:
    for path in sorted(glob.glob(os.path.join(tree, '*.yml')) + glob.glob(os.path.join(tree, '*.yaml'))):
        rel = os.path.relpath(path, scan_root)
        try:
            doc = load(path)
        except (yaml.YAMLError, OSError):
            continue
        for jid, job in ((doc or {}).get('jobs') or {}).items():
            if not isinstance(job, dict):
                continue
            uses = job.get('uses')
            if not isinstance(uses, str) or not uses.startswith(CONSOLE_PREFIX):
                continue
            calls = uses[len(CONSOLE_PREFIX):].split('@', 1)[0]
            if (rel, calls) not in registered:
                offenders.append(
                    f"{rel}: job '{jid}' calls {calls} but is not declared in "
                    f"{os.path.basename(registry_file)} -- an unregistered external "
                    f"caller is exactly what this check exists to prevent"
                )

if not verified:
    blind.append(
        "no registered external caller could be checked against its real file "
        "(no submodule containing one is checked out)"
    )

if offenders:
    for line in offenders:
        print(line, file=sys.stderr)
    sys.exit(1)

if blind:
    die_blind('; '.join(blind))

print(f"info: {verified} external caller call-site(s) verified against their real files")
sys.exit(0)
PYEOF

    RC=$?
    if [[ $RC -eq 0 ]]; then
        log_success "External-caller contracts hold and every external caller is registered"
    elif [[ $RC -eq 3 ]]; then
        log_error "Fix: either .github/external-callers.yml declares no callers, or no"
        log_error "     submodule holding one is checked out (git submodule update --init"
        log_error "     private/account private/renet). A check with no input cannot pass."
        FAILED=1
    else
        log_error "External-caller contract violations (see above)."
        log_error "Fix: update .github/external-callers.yml AND the caller in the other repository together. Editing only this repo breaks their next run, not this PR."
        FAILED=1
    fi
fi

# =============================================================================
# CHECK 5: a job that fetches from Bitwarden must CHECK OUT the map it resolves with.
#
# ./.github/actions/bws-secrets translates NAMES to UUIDs out of
# .ci/config/bws-secret-map.json before it calls sm-action, because sm-action
# addresses secrets by UUID only and 197 raw UUIDs across 63 job blocks would be
# unreviewable. So the map is a RUNTIME input to the composite, not documentation.
#
# A sparse checkout that stops at `.github/actions` therefore produces a job that
# looks deliberately scoped and fails with "bws-secret-map.json not found at ..." --
# and it fails at the fetch step, in whatever job first needs a secret, which on the
# CD path is a production deploy. Found on 2026-09-02 in TWO jobs at once
# (backfill-release-sentinel `backfill`, cd-deploy-account `deploy`), both of which
# grew their `uses:` line long after their cone was written. Nothing connected the
# two edits, which is exactly what this check is for.
#
# The rule is deliberately narrow: it fires only when a sparse checkout EXISTS. A
# full checkout has everything, and demanding a `.ci/config` line there would be
# noise that teaches people to ignore the message.
# =============================================================================
log_info "Checking that every Bitwarden-fetching job checks out the secret map"

python3 - "$ROOT_DIR" <<'PYEOF'
import pathlib
import sys

import yaml

root = pathlib.Path(sys.argv[1])
MAP_DIR = ".ci/config"
files = sorted((root / ".github" / "workflows").glob("*.yml"))
files += sorted((root / ".ci" / "breakpoint" / "workflow").glob("*.yml"))

offenders = []
checked = 0
for path in files:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        print(f"error: {path.name} does not parse ({exc})", file=sys.stderr)
        sys.exit(1)
    if not isinstance(doc, dict):
        continue
    for job_id, job in (doc.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        steps = [s for s in (job.get("steps") or []) if isinstance(s, dict)]
        if not any("bws-secrets" in str(s.get("uses", "")) for s in steps):
            continue
        cones = [
            str((s.get("with") or {}).get("sparse-checkout"))
            for s in steps
            if "actions/checkout" in str(s.get("uses", ""))
            and (s.get("with") or {}).get("sparse-checkout")
        ]
        if not cones:
            continue
        checked += 1
        for cone in cones:
            if MAP_DIR not in cone:
                offenders.append(
                    f"{path.name}: job '{job_id}' fetches from Bitwarden but its sparse "
                    f"checkout does not include {MAP_DIR}. "
                    f"./.github/actions/bws-secrets reads {MAP_DIR}/bws-secret-map.json "
                    f"at run time and will fail with 'bws-secret-map.json not found'."
                )

# ANTI-VACUITY. This check can only fire on a job that BOTH fetches from Bitwarden
# and narrows its checkout, which is a small set by construction. If that set empties
# -- the composite is renamed, the cones are widened, the glob breaks -- the check
# passes for a reason indistinguishable from correctness, so say which it was.
if checked == 0:
    print(
        "info: no job both fetches from Bitwarden and narrows its checkout; "
        "CHECK 5 asserted nothing (this is the vacuous case, not a pass)"
    )

for line in offenders:
    print(f"error: {line}", file=sys.stderr)
if offenders:
    sys.exit(1)
print(f"info: {checked} sparse Bitwarden-fetching job(s) check out the map")
sys.exit(0)
PYEOF

if [[ $? -eq 0 ]]; then
    log_success "Every sparse Bitwarden-fetching job checks out .ci/config"
else
    log_error "Fix: add .ci/config to that job's sparse-checkout list. The cone must be a"
    log_error "     superset of what every local action in the job READS, not just where"
    log_error "     those actions live."
    FAILED=1
fi
# =============================================================================
# CHECK 6: nothing optional may run in front of the watchdog's monitor step.
#
# The watchdog is the thing that watches every other CI run. Its job therefore
# has an ordering property nothing else in this repo has: a step that can fail
# and that the monitor does not need is not merely noisy there, it silently
# disables the guard. On 2026-09-03 the shadow-secret compare -- a temporary
# migration scaffold that nothing consumes -- sat at step 7 of 7 ahead of the
# monitor, hit a real mismatch on ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN, and exited
# 1. Run 33704079162 reported "failure" having monitored NOTHING, and the only
# symptom was a red watchdog, which reads exactly like the watchdog working.
#
# The rule: a step BEFORE "Monitor jobs and cancel on failure" must either be one
# the monitor actually needs (the PREREQS allowlist, short on purpose) or be unable
# to cost the watch at all.
#
# "Unable to cost the watch" is not a name, it is two properties, and both are
# required because each alone leaves a door open:
#
#   continue-on-error: true  -- the step cannot FAIL the job, so the 2026-09-03
#                               shape (exit 1 at step 7 of 7, monitor never runs)
#                               is structurally impossible rather than promised.
#   timeout-minutes: <= 5    -- the step cannot HANG the job either. The monitor's
#                               own deadline is 480s inside a 14-minute slim cap,
#                               so a step that merely blocks kills the watch just
#                               as dead as one that exits 1, and continue-on-error
#                               says nothing about that.
#
# This is deliberately stricter than the name list it replaces: a name proves
# somebody once thought about a step, these two prove the step cannot take the
# watchdog down no matter what it does. PREREQS stays for the steps that must be
# allowed to fail, because the monitor cannot run correctly without them.
# =============================================================================
log_info "Checking that nothing optional precedes the watchdog's monitor step"

python3 - "$ROOT_DIR" <<'PYEOF'
import pathlib
import sys

import yaml

root = pathlib.Path(sys.argv[1])
WORKFLOW = root / ".github" / "workflows" / "watchdog-monitor.yml"
MONITOR = "Monitor jobs and cancel on failure"
# Steps the monitor genuinely depends on: the checkout that puts its scripts on
# disk, and the deterministic attempt cap, which must run first BECAUSE it writes
# the env var the monitor reads.
PREREQS = {"Attempt cap (deterministic backstop)"}
MAX_TIMEOUT_MINUTES = 5


def harmless(step):
    """Can this step neither fail nor hang the job?

    Both answers must come from a LITERAL, never an expression: `continue-on-error:
    ${{ ... }}` is decided at run time, and a rule that reads it as safe is trusting
    a value it cannot see.
    """
    if step.get("continue-on-error") is not True:
        return False
    t = step.get("timeout-minutes")
    return isinstance(t, int) and 0 < t <= MAX_TIMEOUT_MINUTES

if not WORKFLOW.exists():
    print(f"error: {WORKFLOW} is missing; CHECK 6 cannot report", file=sys.stderr)
    sys.exit(1)

doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
offenders = []
found_monitor = False
for job_id, job in (doc.get("jobs") or {}).items():
    steps = [s for s in (job.get("steps") or []) if isinstance(s, dict)]
    names = [s.get("name") or str(s.get("uses", "")) for s in steps]
    if MONITOR not in names:
        continue
    found_monitor = True
    cut = names.index(MONITOR)
    for name, step in zip(names[:cut], steps[:cut]):
        if name in PREREQS or "actions/checkout" in name or harmless(step):
            continue
        offenders.append(
            f"watchdog-monitor.yml: job '{job_id}' runs {name!r} BEFORE {MONITOR!r}, "
            f"and it can stop the watch: a failure there ends the job and the watchdog "
            f"monitors nothing while reporting a failure that looks like its own. "
            f"Three ways out, in order of preference: move it after the monitor with "
            f"`if: always()`; or, if the monitor genuinely needs its output, give it "
            f"BOTH `continue-on-error: true` and `timeout-minutes: <= "
            f"{MAX_TIMEOUT_MINUTES}` so it can neither fail nor hang the job; or add it "
            f"to PREREQS in CHECK 6 saying why it must be allowed to fail."
        )

# ANTI-VACUITY: a renamed monitor step would empty this check silently, and an
# ordering rule that stops finding its own anchor is the vacuous case.
if not found_monitor:
    print(
        f"error: no job in watchdog-monitor.yml has a {MONITOR!r} step. Either it was "
        f"renamed -- update CHECK 6 -- or the watchdog lost its monitor.",
        file=sys.stderr,
    )
    sys.exit(1)

for line in offenders:
    print(f"error: {line}", file=sys.stderr)
if offenders:
    sys.exit(1)
print("info: nothing optional precedes the watchdog's monitor step")
sys.exit(0)
PYEOF

if [[ $? -eq 0 ]]; then
    log_success "The watchdog monitors before anything optional can stop it"
else
    log_error "Fix: move the step after 'Monitor jobs and cancel on failure' and give it"
    log_error "     'if: always()', so a failure there still reports without costing the watch."
    FAILED=1
fi

exit "$FAILED"
