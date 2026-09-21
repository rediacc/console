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
# Is this the repo's own workflow tree, or a gate test's fixture tree? Two
# checks need to know, so it is decided once here rather than compared twice.
# Overridable for the same reason SLIM_TIMEOUT_REQUIRE_COVERAGE is: the
# DECLARED_UNUSED_OK liveness sweep only runs on the real tree, so without a way
# to force it on a fixture it would have no both-ways test at all -- which is
# exactly how it shipped, and exactly how it broke two other gates' tests.
if [[ -z "${REAL_WORKFLOW_TREE:-}" ]]; then
    if [[ "$WORKFLOWS_DIR" == "$ROOT_DIR/.github/workflows" ]]; then
        REAL_WORKFLOW_TREE=true
    else
        REAL_WORKFLOW_TREE=false
    fi
fi

if [[ -z "${SLIM_TIMEOUT_REQUIRE_COVERAGE:-}" ]]; then
    SLIM_TIMEOUT_REQUIRE_COVERAGE="$REAL_WORKFLOW_TREE"
fi

# The external-caller registry. Resolved HERE, not next to CHECK 4, because two
# checks read it: CHECK 4 owns the caller/callee contract, and CHECK 2's arm (a3)
# asserts that every DECLARED_UNUSED_OK exemption is pinned alive by an entry in
# this file. One resolution, one rule, so a fixture tree cannot be real for one
# arm and synthetic for the other.
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

python3 - "$WORKFLOWS_DIR" "$REAL_WORKFLOW_TREE" "$EXTERNAL_CALLERS_FILE" "${WORKFLOW_GATES_EXTRA_EXEMPTIONS:-}" <<'PYEOF'
import os
import re
import sys
import yaml

workflows_dir = sys.argv[1]
real_tree = sys.argv[2] == 'true'
registry_file = sys.argv[3]
# TEST-ONLY seam: `_DECLARED_UNUSED_OK` below is drained to empty on the real
# tree by design (W8 P1b's "declared endgame"), which would otherwise leave the
# liveness sweep and arm (a3) with no positive case to prove they can fire at
# all. A fixture injects a synthetic pair here as "file:NAME" entries,
# comma-separated; production never sets this, so real runs are unaffected.
_EXTRA_EXEMPTIONS = [
    tuple(pair.split(':', 1)) for pair in sys.argv[4].split(',') if pair
]

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
        # COMMENTS ARE NOT USES. `texts` feeds USE_RE, which decides whether a workflow
        # "reads" a secret, and a raw read counted `# ... secrets.X ...` as a use. So a
        # comment RECORDING that some secrets.X was removed made the callee look like it
        # still consumed the name, and the contract check then demanded a declaration for
        # something nothing reads. Measured 2026-09-09 while retiring exactly such a
        # reference: two explanatory lines kept the declaration alive.
        #
        # This is the FIFTH gate in this tree found with the same blindness in one day --
        # check:ci-env-file-adoption, block_host_toolchain_run, check-secret-scope.ts and
        # check_secret_reachability.py were the others. The shared shape is a text scan
        # standing in for a semantic one, and the shared cost is pressure to delete the
        # explanation to get green.
        texts[fname] = "\n".join(
            "" if ln.lstrip().startswith("#") else ln for ln in text.split("\n")
        )
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

# (a2) a reusable workflow may not DECLARE a secret nothing in it reads.
#
# THE ARM THAT WAS MISSING, and its absence is measurable: 57 such declarations had
# accumulated by 2026-09-06, left behind when consumers moved to Bitwarden, and were
# removed in one sweep. (a) catches a read with no declaration; nothing caught a
# declaration with no read, so dead scaffolding grew quietly on the one surface
# where a stale secret name is most misleading -- a caller reads the declaration
# and passes a value that goes nowhere.
# A LIST, converted below, deliberately: `{...}` with its last member deleted is
# `{}`, which is an empty DICT, and the set arithmetic in arm (a3) then dies with
# a TypeError while `in` and `sorted()` above degrade to silently matching
# nothing. Draining this list to empty is the declared endgame (W8 P1b), so the
# empty form has to be the safe one. Found by planting exactly that drain.
_DECLARED_UNUSED_OK = [
    # DRAINED 2026-09-08, and the premise this entry rested on was FALSE.
    # It said the consumer "fetches this from Bitwarden now, so the passed value IS
    # unused". Measured: the fetch step is guarded on `github.repository ==
    # 'rediacc/console'`, and in a REUSABLE workflow `github.repository` is the
    # CALLER's repo -- so for rediacc/account and rediacc/renet that step never ran
    # and the token was EMPTY. The passed secret was unread not because their half of
    # the migration had landed but because it had never been written, and deleting the
    # declaration would have made a live outage permanent.
    # `claude-review-reusable.yml` now reads
    # `env.BWS_... || secrets.ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN`, which restores the
    # read for both callers, and that is what makes this exemption genuinely removable.
]
DECLARED_UNUSED_OK = set(_DECLARED_UNUSED_OK) | set(_EXTRA_EXEMPTIONS)
if len(DECLARED_UNUSED_OK) != len(_DECLARED_UNUSED_OK) + len(_EXTRA_EXEMPTIONS):
    print("DECLARED_UNUSED_OK contains a duplicate entry", file=sys.stderr)
    sys.exit(1)
for fname, doc in docs.items():
    wc = workflow_call(doc)
    if not wc:
        continue
    declared = set((wc.get('secrets') or {}).keys())
    used = set(USE_RE.findall(texts[fname])) - IMPLICIT
    for name in sorted(declared - used):
        if (fname, name) in DECLARED_UNUSED_OK:
            continue
        offenders.append(
            f"{fname}: declares secret {name} under workflow_call but never reads it -- "
            f"a caller passing it sends a value nowhere; delete the declaration"
        )
# An exemption naming a declaration that is gone, or one that IS read, excuses
# nothing and would sit forever looking like coverage.
#
# SCOPED TO THE REAL TREE, and that scoping is not a nicety. The exemptions name
# files in .github/workflows; a CHECK 1/CHECK 3 fixture tree contains two or
# three synthetic YAMLs and none of them. Sweeping there reported every
# exemption as dangling, which made this script exit 1 on EVERY fixture tree and
# turned two unrelated gate tests red for a file their fixtures were never meant
# to have -- test_gate_slim_timeout.py and test_gate_workflow_contracts.py, nightly run
# 34014201256. A liveness probe that cannot see the thing it probes for must
# stay silent, not condemn it.
if real_tree:
    for fname, name in sorted(DECLARED_UNUSED_OK):
        doc = docs.get(fname)
        if doc is None:
            offenders.append(f"DECLARED_UNUSED_OK names {fname}, which does not exist")
            continue
        declared = set((workflow_call(doc).get('secrets') or {}).keys())
        used = set(USE_RE.findall(texts[fname])) - IMPLICIT
        if name not in declared:
            offenders.append(f"DECLARED_UNUSED_OK: {fname} no longer declares {name}; drop the exemption")
        elif name in used:
            offenders.append(f"DECLARED_UNUSED_OK: {fname} now READS {name}; drop the exemption")

# (a3) every DECLARED_UNUSED_OK exemption must be PINNED ALIVE by a real entry in
# .github/external-callers.yml, and every pair that registry pins alive must be
# named by the exemption list. Set equality, both directions.
#
# WHY: the only legitimate reason to keep a declaration nothing reads is that a
# caller in ANOTHER repository still passes it, so deleting the declaration
# breaks their next run rather than this PR. Until now that justification lived
# in a COMMENT above the set. A comment cannot go stale loudly: retire the
# external caller and the exemption stays, looking like coverage, protecting a
# declaration nothing on earth passes any more.
#
# Scoped exactly like the liveness sweep above, and for the same reason: a
# CHECK 1/2/3 fixture tree has no registry, and an arm that cannot see the thing
# it probes for must stay silent rather than condemn it.
if real_tree and registry_file:
    reg_offenders = []
    try:
        with open(registry_file) as fh:
            registry = yaml.safe_load(fh.read())
    except (yaml.YAMLError, OSError) as exc:
        reg_offenders.append(
            f"arm (a3): {registry_file} unreadable ({exc}) -- the exemption list "
            f"cannot be justified against a registry that will not parse"
        )
        registry = None
    reg_entries = (registry or {}).get('callers') or []
    if not reg_offenders and (not isinstance(reg_entries, list) or not reg_entries):
        # Zero inputs is a failure, never a pass: with an empty registry every
        # exemption would look unjustified and an empty exemption list would look
        # perfect, and the arm would be asserting nothing either way.
        reg_offenders.append(
            f"arm (a3): {os.path.basename(registry_file)} declares no callers -- "
            f"nothing can pin an exemption alive, so this arm is blind"
        )
        reg_entries = []

    pinned_unused = set()
    for entry in reg_entries:
        if not isinstance(entry, dict) or 'calls' not in entry:
            continue  # CHECK 4 owns the shape of a registry entry
        callee = os.path.basename(entry['calls'])
        doc = docs.get(callee)
        if doc is None:
            continue  # CHECK 4 reports a registered call to a callee that is gone
        declared = set((workflow_call(doc).get('secrets') or {}).keys())
        used = set(USE_RE.findall(texts[callee])) - IMPLICIT
        passed = entry.get('passes_secrets')
        names = declared if passed == 'inherit' else set(passed or [])
        pinned_unused |= {(callee, n) for n in (names & declared) - used}

    for fname, name in sorted(DECLARED_UNUSED_OK - pinned_unused):
        reg_offenders.append(
            f"DECLARED_UNUSED_OK exempts {fname}/{name}, but no entry in "
            f"{os.path.basename(registry_file)} pins it alive -- nothing outside this "
            f"repo passes it, so delete the declaration and the exemption, not the check"
        )
    for fname, name in sorted(pinned_unused - DECLARED_UNUSED_OK):
        reg_offenders.append(
            f"{os.path.basename(registry_file)} pins {fname}/{name} alive (an external "
            f"caller passes a secret {fname} declares and never reads), but "
            f"DECLARED_UNUSED_OK does not name it -- reconcile the two, or delete the "
            f"declaration and the registry entry together"
        )

    offenders.extend(reg_offenders)
    if not reg_offenders:
        print(
            f"info: arm (a3): {len(DECLARED_UNUSED_OK)} declared-unused exemption(s) == "
            f"{len(pinned_unused)} pinned alive by {len(reg_entries)} external-caller "
            f"entr{'y' if len(reg_entries) == 1 else 'ies'}"
        )

# (b)/(c) caller <-> callee contract
for fname, doc in docs.items():
    # FIXED 2026-09-10, same class as CHECK 6's guard below and found while testing
    # it. `(doc or {})` covers an EMPTY workflow file (safe_load -> None) and nothing
    # else: a workflow whose YAML parses to a scalar or a list reached `.get` here and
    # died with `AttributeError: 'str' object has no attribute 'get'`, after which bash
    # printed "Reusable-workflow contract violations (see above)" about a crash. The
    # port already carried this isinstance guard (workflow_gates.py:571), so the two
    # sides disagreed on that input and the differential had no case covering it.
    jobs = (doc or {}).get('jobs') or {} if isinstance(doc, dict) else {}
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
# EXTERNAL_CALLERS_ROOT / EXTERNAL_CALLERS_FILE are resolved near the top of the
# file, because CHECK 2's arm (a3) needs the same registry and must resolve it
# the same way rather than growing a second copy of the rule.
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
    # And it FAILS, rather than announcing the vacuity and exiting 0 as it did
    # until 2026-09-09. "This is the vacuous case, not a pass" followed by a green
    # success line is a gate that has stopped meaning its own name: 10 jobs are in
    # this set today, so an empty one is a broken matcher, never a clean tree.
    print(
        "error: no job both fetches from Bitwarden and narrows its checkout, so "
        "CHECK 5 asserted nothing. Ten jobs were in this set on 2026-09-09; an "
        "empty set means the bws-secrets composite was renamed, the sparse-checkout "
        "key moved, or the workflow glob stopped matching. Fix the matcher above.",
        file=sys.stderr,
    )
    sys.exit(1)

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
#
# THE continue-on-error DOOR IS CURRENTLY CLOSED IN THIS REPO, and saying so here
# matters more than the door itself. check-workflows.sh bans the keyword outright
# ("Silently ignores step/job failures"), so no workflow can walk through it today
# -- as this session found by trying: the watchdog's Bitwarden fetch was moved ahead
# of the monitor with continue-on-error, this check accepted it on the property, and
# the banned-patterns gate refused it four minutes into CI. The move was reverted.
#
# The rule stays as written rather than being narrowed back to a name list, because
# the property is the thing that is actually true and the other gate's ban is a
# policy on top of it. If that ban is ever relaxed, this admits the case correctly
# and its test already proves both answers. Until then, PREREQS is the only way in.
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
PREREQS = {
    "Attempt cap (deterministic backstop)",
    # Added 2026-09-09. The monitor's two classifier tiers read credentials this step
    # exports; without them it does not degrade gracefully, it hands the retry decision to
    # an allowlist nobody reviewed -- which is the harm the workflow's own comment
    # describes. That is the PREREQS contract: allowed to fail BECAUSE the monitor cannot
    # run correctly without it. The org secrets it replaces were deleted 2026-09-05 to
    # force exactly this migration, and this workflow was the last consumer still reading
    # them.
    "Fetch secrets from Bitwarden",
}
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


def scalar(value):
    """A YAML scalar as the string GitHub would render, or None if it is not one.

    YAML hands back whatever was written, so `name: 5` is an int and `name: null`
    is None. Everything below goes through here rather than assuming str.
    """
    if isinstance(value, str):
        return value or None
    if isinstance(value, (bool, int, float)):
        return str(value)
    return None


def step_label(step):
    """What to call this step in a message, and what to match the monitor on.

    FIXED 2026-09-10. This was inlined as `s.get("name") or str(s.get("uses", ""))`,
    which returns a non-str for `name: 5` and then died on `"actions/checkout" in
    name` with `TypeError: argument of type 'int' is not a container or iterable`
    -- a traceback under which bash printed "move the step after the monitor",
    a fix for a crash that has nothing to do with ordering.
    """
    return scalar(step.get("name")) or scalar(step.get("uses")) or ""


def is_checkout(step):
    """A repository checkout, decided by `uses:` and NEVER by the display name.

    FIXED 2026-09-10. This used to ask `"actions/checkout" in <label>`, and the
    label only falls back to `uses:` when the step has no `name:`. So the exemption
    held for the 139 unnamed checkout steps under .github/workflows and was lost for
    the 5 named ones. One ordinary edit (`name: Checkout` on watchdog-monitor.yml's
    own checkout, which is unnamed today) would have turned this gate red on the one
    workflow it exists to guard, with a message telling the author to move the
    checkout AFTER the monitor and leave the monitor's scripts off disk.
    """
    uses = step.get("uses")
    return isinstance(uses, str) and uses.startswith("actions/checkout")

if not WORKFLOW.exists():
    print(f"error: {WORKFLOW} is missing; CHECK 6 cannot report", file=sys.stderr)
    sys.exit(1)

# FIXED 2026-09-10. THREE of the five ways the monitor anchor can go missing used
# to end in a traceback rather than in this check's own message: an EMPTY document
# and a NON-MAPPING document both reached `doc.get("jobs")` and raised
# `AttributeError`, and a SYNTAX ERROR raised `yaml.YAMLError` out of safe_load.
# Bash printed "move the step after the monitor" on top of each, telling the
# operator to reorder a step in a file that has no steps. All three are still
# failures -- the anti-vacuity rule below cannot be satisfied by a file that did
# not parse -- but each now names its cause.
try:
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
except yaml.YAMLError as exc:
    print(
        f"error: {WORKFLOW} is not parseable YAML ({exc}); CHECK 6 cannot report",
        file=sys.stderr,
    )
    sys.exit(1)
if not isinstance(doc, dict):
    print(
        f"error: {WORKFLOW} did not parse as a YAML mapping (got "
        f"{type(doc).__name__}); CHECK 6 cannot report",
        file=sys.stderr,
    )
    sys.exit(1)

offenders = []
found_monitor = False
jobs = doc.get("jobs")
for job_id, job in (jobs if isinstance(jobs, dict) else {}).items():
    if not isinstance(job, dict):
        continue
    steps = [s for s in (job.get("steps") or []) if isinstance(s, dict)]
    names = [step_label(s) for s in steps]
    if MONITOR not in names:
        continue
    found_monitor = True
    cut = names.index(MONITOR)
    for name, step in zip(names[:cut], steps[:cut]):
        if name in PREREQS or is_checkout(step) or harmless(step):
            continue
        offenders.append(
            f"watchdog-monitor.yml: job '{job_id}' runs {name!r} BEFORE {MONITOR!r}, "
            f"and it can stop the watch: a failure there ends the job and the watchdog "
            f"monitors nothing while reporting a failure that looks like its own. "
            f"TWO ways out. Move it after the monitor with `if: always()`; or add it to "
            f"PREREQS in CHECK 6 saying why it must be allowed to fail. "
            f"A THIRD ROUTE EXISTS IN THIS CHECK'S LOGIC AND IS CLOSED IN THIS REPO: "
            f"`continue-on-error: true` with `timeout-minutes: <= {MAX_TIMEOUT_MINUTES}` "
            f"satisfies the property here, but check-workflows.sh bans the keyword "
            f"outright, so CI refuses it minutes later. Two sessions have now spent effort "
            f"discovering that -- the second on 2026-09-09, because this message advertised "
            f"the route while only the comment above recorded the ban. It is named here "
            f"rather than hidden so the next reader does not rediscover it a third time."
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
