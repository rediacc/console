#!/bin/bash
# Static invariants over .github/workflows/ci.yml.
#
#   channel-as-docker-tag   a job that passes the CHANNEL as a reusable
#                           workflow's `docker_tag` must also refuse to run
#                           with an empty channel.
#
# WHY THIS IS A SECURITY-SHAPED RULE AND NOT A STYLE ONE. `docker_tag` chooses
# which IMAGE gets validated. An empty channel does not disable the tag, it
# silently becomes `latest`: `.ci/config/constants.sh:27` runs
# `DOCKER_TAG="${DOCKER_TAG:-latest}"` at source time, and `latest` is the last
# RELEASED image. So a job wired this way stops testing the artifact the run
# just built and starts testing an old published one, while still asserting the
# NEW version number.
#
# MEASURED, not theorised. `assert-channel-for-event.sh:24-31` requires an empty
# channel on `schedule`, and ci.yml's `scope` step is gated on
# `github.event_name == 'pull_request'`, so its `run_install_methods` output is
# empty on a nightly and the `!= 'false'` guard admits the job. Nightlies
# 32323997586 and 32208001410 both died on:
#
#   ✓   Version: 1.2.27
#   latest: Pulling from rediacc/rdc
#   ✗ Version mismatch: expected '1.2.27', got '1.2.26'
#
# Deterministic, and `bump-none` merges widen the gap because they deliberately
# cut no release, so `latest` falls further behind main every time.
#
# WHY THE RULE IS SCOPED TO `docker_tag` AND NOT TO "uses the channel". The
# broader rule is FALSE and would break a correct job: `stage-artifacts` also
# consumes the channel and MUST run with an empty one, staging the nightly's
# artifacts while skipping only its two channel-scoped metadata assertions
# (see .ci/scripts/test/gates/test-stage-artifacts-channel.sh, which exists to
# prove that skip stayed narrow). Tag selection is the discriminating detail:
# an empty channel there resolves to a DIFFERENT IMAGE rather than to nothing.
#
# Env: WORKFLOW_FILE overrides the target so the gate test can drive the
# invariant against mutated copies. Exit 0 clean, 1 violation, 2 setup error.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

WORKFLOW_FILE="${WORKFLOW_FILE:-$ROOT_DIR/.github/workflows/ci.yml}"

# Anti-vacuity: a missing workflow means the gate checked nothing, and nothing
# checked must never read as green.
if [[ ! -f "$WORKFLOW_FILE" ]]; then
    log_error "INVARIANT-FAIL: workflow-missing: no file at $WORKFLOW_FILE (nothing to check cannot pass)"
    exit 1
fi

command -v python3 >/dev/null 2>&1 || {
    log_error "python3 is required to parse $WORKFLOW_FILE"
    exit 2
}

# The analysis reads the PARSED workflow rather than grepping text, so a
# reflowed `if:` block or a reordered `with:` map cannot make the invariant
# silently unenforceable.
findings="$(
    WORKFLOW_FILE="$WORKFLOW_FILE" python3 - <<'PY'
import io, os, sys
try:
    import yaml
except ImportError:
    sys.stderr.write("SETUP: PyYAML is not importable\n")
    sys.exit(2)

path = os.environ["WORKFLOW_FILE"]
try:
    doc = yaml.safe_load(io.open(path, encoding="utf-8"))
except Exception as exc:
    sys.stderr.write("SETUP: %s does not parse as YAML: %s\n" % (path, exc))
    sys.exit(2)

jobs = (doc or {}).get("jobs") or {}
if not isinstance(jobs, dict) or not jobs:
    print("no-jobs\t<none>")
    sys.exit(0)

candidates = 0
for name, job in jobs.items():
    if not isinstance(job, dict):
        continue
    tag = ((job.get("with") or {}) if isinstance(job.get("with"), dict) else {}).get("docker_tag")
    if not isinstance(tag, str) or "channel" not in tag:
        continue
    candidates += 1
    cond = job.get("if")
    cond = "" if cond is None else str(cond)
    # Accept any spelling that requires the channel to be non-empty.
    ok = ("channel != ''" in cond.replace('"', "'")) or ("channel!=''" in cond.replace('"', "").replace(" ", ""))
    if not ok:
        print("ungated\t%s" % name)

if candidates == 0:
    print("no-candidates\t<none>")
PY
)" || {
    rc=$?
    log_error "INVARIANT-FAIL: analysis of $WORKFLOW_FILE failed (exit $rc); an unparsed workflow cannot pass"
    exit 1
}

FAILED=0
while IFS=$'\t' read -r kind name; do
    [[ -n "$kind" ]] || continue
    case "$kind" in
        ungated)
            log_error "INVARIANT-FAIL: channel-as-docker-tag: job '$name' passes the channel as docker_tag but its \`if:\` does not require \`needs.initialize.outputs.channel != ''\`. With an empty channel (every schedule run) constants.sh:27 rewrites the tag to 'latest', so the job validates the last RELEASED image while asserting the next version."
            FAILED=1
            ;;
        no-jobs)
            log_error "INVARIANT-FAIL: no-jobs: $WORKFLOW_FILE declares no jobs (nothing to check cannot pass)"
            FAILED=1
            ;;
        no-candidates)
            # Vacuity guard. If nobody passes a channel-derived docker_tag any
            # more, this gate is asserting nothing and must say so rather than
            # printing a green nobody earned. Delete the gate deliberately, or
            # point it at the construct that replaced docker_tag.
            log_error "INVARIANT-FAIL: no-candidates: no job in $WORKFLOW_FILE passes a channel-derived \`docker_tag\`, so this gate verified nothing. Retarget or remove it deliberately."
            FAILED=1
            ;;
    esac
done <<<"$findings"

if ((FAILED != 0)); then
    log_error "ci workflow invariants FAILED"
    exit 1
fi
log_info "ci workflow invariants hold: every channel-derived docker_tag job refuses an empty channel"
