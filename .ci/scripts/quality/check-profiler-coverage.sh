#!/bin/bash
# Every job that runs on a Linux runner must be profiled, and every job that is
# profiled must be configured correctly.
#
# WHY. Standard runners are free and unlimited on this public repo, which is
# exactly what makes oversizing invisible: a job that uses ~1 core on a 4-vCPU
# ubuntu-latest VM burns four cores' worth of the world's electricity to do one
# core's work, and no bill ever says so. The profiler action
# (.github/actions/profiler) turns runner sizing into a measurement. A
# measurement that covers 20 of 97 jobs measures nothing useful, and coverage
# maintained by habit decays the moment somebody adds a job in a hurry. This
# gate makes coverage an INVARIANT instead: a new Linux job is red until it is
# either profiled or written down here with a reason.
#
# TWO RELATIONS, because there are two ways the wiring is wrong:
#   (a) COVERAGE  -- a Linux job that does not use the action is invisible to
#                    the whole exercise.
#   (b) CONFIG    -- a job that uses the action with a bad `interval`, an
#                    undeclared input, or a `runner-label` that disagrees with
#                    its own `runs-on` produces a profile that LOOKS fine and
#                    is wrong. runner-label arms the HOST_LEAK check; a
#                    copy-pasted `runner-label: ubuntu-latest` on an
#                    ubuntu-slim job disarms it in the dangerous direction
#                    (4 cores / 16 GB read off a 1-core / 5 GB box).
#
# FAIL-CLOSED ON WHAT IT CANNOT RESOLVE. `runs-on: ${{ inputs.runner }}` cannot
# be resolved statically. An unresolvable runner counts as REQUIRING coverage,
# never as exempt: "we could not tell" must cost an allowlist line with a
# reason, because the alternative is a silent hole shaped exactly like the ones
# this repo keeps finding.
#
# COVERAGE IS DIRECT OR THROUGH A VERIFIED WRAPPER. A job is covered when its
# own steps use the action, or when they use a composite that carries it.
# Whether a JavaScript action's `post:` hook still fires when the action is
# nested inside a composite was the open question profiler-probe.yml existed to
# answer, and on 2026-08-08 it answered YES on real runners (run 31252148469:
# the panel appeared on ubuntu-slim and on ubuntu-latest through a composite
# wrapper). So ./.github/actions/setup-workspace is a wrapper from here on, and
# the ~26 jobs that already call it are covered without an edit each.
#
# A WRAPPER IS VERIFIED, NOT TRUSTED. Coverage for those jobs now hangs on one
# `uses:` line inside somebody else's file, and deleting that line would leave
# 26 jobs reporting as profiled while profiling nothing -- a fail-open of
# exactly the shape this gate exists to prevent. So each wrapper's own
# action.yml must be shown to reference the profiler before it counts, and a
# wrapper that stops doing so REFUSES rather than quietly covering nothing.
#
# ANTI-VACUITY. Every extractor self-tests against a planted sample before the
# sweep, and the sweep refuses on zero workflows, zero jobs, zero declared
# action inputs, or counts under the floors. An empty scan is a broken
# instrument, never a clean tree -- this repo has shipped gates that checked
# zero files for weeks.
#
# TEST SEAMS (all optional, used by .ci/scripts/test/gates/test-profiler-coverage.sh):
#   PROFILER_COVERAGE_WORKFLOW_DIR   directory of workflow YAML to scan
#   PROFILER_COVERAGE_ALLOWLIST      allowlist path
#   PROFILER_COVERAGE_ACTION_DIR     directory holding the profiler action.yml
#   PROFILER_COVERAGE_WRAPPER_DIRS   composite dirs that carry the profiler
#                                    (each is verified; empty means none)
#   PROFILER_COVERAGE_COVERING_ACTIONS  extra `uses:` refs that count as coverage
#   PROFILER_COVERAGE_MIN_WORKFLOWS  floor on workflow files parsed
#   PROFILER_COVERAGE_MIN_JOBS       floor on jobs parsed
#   PROFILER_COVERAGE_MIN_LINUX      floor on Linux jobs found
#
# Usage: check-profiler-coverage.sh
# Exits 0 when both relations hold, 1 on any gap or any refusal.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
# BLOCKER: log_info / log_error / get_repo_root are used throughout this gate
source "$SCRIPT_DIR/../lib/common.sh"
# shellcheck source=../lib/blocker-validator.sh
# BLOCKER: the coverage allowlist is a suppression list and is held to the same BLOCKER quality bar as every other allowlist in the repo
source "$SCRIPT_DIR/../lib/blocker-validator.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

WORKFLOW_DIR="${PROFILER_COVERAGE_WORKFLOW_DIR:-.github/workflows}"
ALLOWLIST="${PROFILER_COVERAGE_ALLOWLIST:-.profiler-coverage-allowlist}"
ACTION_DIR="${PROFILER_COVERAGE_ACTION_DIR:-.github/actions/profiler}"

# Composite actions that carry the profiler on behalf of every job calling them.
# Space-separated DIRECTORIES (not `uses:` refs): each one's action.yml is read
# below and must be shown to reference the profiler before the wrapper counts,
# which is what keeps this from being a one-line fail-open for ~26 jobs.
# `${VAR-default}` rather than `${VAR:-default}` on purpose: a test that sets it
# to the empty string means "no wrappers at all", which is the control for the
# wrapper path.
read -r -a WRAPPER_DIRS <<<"${PROFILER_COVERAGE_WRAPPER_DIRS-.github/actions/setup-workspace}"

# Extra `uses:` strings that count as coverage, taken on trust and NOT verified.
# Empty by default. This is the extension seam for a wrapper that lives outside
# this repo's action tree, and it is also what test-profiler-coverage.sh drives
# to prove the wrapper path is live code rather than a comment.
read -r -a EXTRA_COVERING_ACTIONS <<<"${PROFILER_COVERAGE_COVERING_ACTIONS:-}"

# Floors. The tree carries 28 workflows / 121 jobs / 97 Linux jobs; anything
# far under these numbers means the parse found a layout it does not
# understand, and "all covered" off three jobs is precisely the lie this gate
# exists to prevent.
MIN_WORKFLOWS="${PROFILER_COVERAGE_MIN_WORKFLOWS:-10}"
MIN_JOBS="${PROFILER_COVERAGE_MIN_JOBS:-60}"
MIN_LINUX="${PROFILER_COVERAGE_MIN_LINUX:-40}"

# ---------------------------------------------------------------------------
# Extractors. Each is self-tested below against a planted sample.
# ---------------------------------------------------------------------------

# job_keys <workflow> -> one top-level job id per line.
#
# Job keys are the only 2-space-indented bare keys inside the `jobs:` block;
# bodies sit at 4 spaces or deeper. Scoping to that block keeps `on:`,
# `permissions:` and `concurrency:` (also 2-space) out.
job_keys() {
    awk '
        /^jobs:[[:space:]]*$/ { in_jobs = 1; next }
        in_jobs && /^[^[:space:]#]/ { in_jobs = 0 }
        in_jobs && /^  [A-Za-z0-9_-]+:[[:space:]]*$/ {
            key = $0
            sub(/^  /, "", key)
            sub(/:[[:space:]]*$/, "", key)
            print key
        }
    ' "$1"
}

# job_block <workflow> <job> -> the body lines of that job.
#
# Anchored inside the `jobs:` block so a job named after a trigger (`push`)
# cannot accidentally match the `on:` section instead.
job_block() {
    awk -v want="$2" '
        /^jobs:[[:space:]]*$/ { in_jobs = 1; next }
        in_jobs && /^[^[:space:]#]/ { in_jobs = 0; in_job = 0 }
        !in_jobs { next }
        $0 ~ ("^  " want ":[[:space:]]*$") { in_job = 1; next }
        in_job && /^  [A-Za-z0-9_-]+:[[:space:]]*$/ { in_job = 0 }
        in_job { print }
    ' "$1"
}

# runs_on <block-file> -> the raw `runs-on:` value, trailing comment stripped.
# Empty when the job declares none (a reusable-workflow caller, or malformed).
runs_on() {
    awk '
        /^    runs-on:/ && !seen {
            seen = 1
            line = $0
            sub(/^    runs-on:[[:space:]]*/, "", line)
            sub(/[[:space:]]+#.*$/, "", line)
            sub(/[[:space:]]*$/, "", line)
            print line
        }
    ' "$1"
}

# is_caller <block-file> -> prints "yes" when the job is a reusable-workflow
# call. Such a job has no runner of its own: its steps are the called
# workflow's jobs, which this gate sees separately in that workflow's file.
is_caller() {
    if grep -qE '^    uses:[[:space:]]*\./\.github/workflows/' "$1"; then
        echo yes
    fi
}

# matrix_values <block-file> <key> -> every literal value the job's
# `strategy.matrix` gives <key>, across the `include:` form, the inline-list
# form (`os: [a, b]`) and the block-list form.
matrix_values() {
    awk -v key="$2" '
        /^    strategy:[[:space:]]*$/ { in_strategy = 1; next }
        in_strategy && /^    [A-Za-z0-9_-]+:/ { in_strategy = 0 }
        !in_strategy { next }
        {
            line = $0
            sub(/[[:space:]]+#.*$/, "", line)
        }
        # `key: value`, `- key: value`, `key: [a, b]`
        line ~ ("^[[:space:]]*(-[[:space:]]+)?" key ":") {
            v = line
            sub("^[[:space:]]*(-[[:space:]]+)?" key ":[[:space:]]*", "", v)
            gsub(/[][,]/, " ", v)
            gsub(/["'"'"']/, "", v)
            collecting = (v ~ /^[[:space:]]*$/)
            n = split(v, parts, /[[:space:]]+/)
            for (i = 1; i <= n; i++) if (parts[i] != "") print parts[i]
            next
        }
        # block-list continuation under a bare `key:`
        collecting && line ~ /^[[:space:]]*-[[:space:]]+[^[:space:]]/ {
            v = line
            sub(/^[[:space:]]*-[[:space:]]+/, "", v)
            gsub(/["'"'"']/, "", v)
            if (v != "") print v
            next
        }
        { collecting = 0 }
    ' "$1"
}

# covering_uses <block-file> <action-ref> -> count of steps in the job that use
# <action-ref> exactly (a trailing comment is allowed, a longer path is not, so
# `.../profiler/nest-probe` does not match `.../profiler`).
covering_uses() {
    local ref="$2"
    grep -cE "^[[:space:]]*(-[[:space:]]+)?uses:[[:space:]]*${ref//./\\.}[[:space:]]*(#.*)?$" "$1" || true
}

# malformed_refs <block-file> <action-ref> -> `uses:` lines that mention the
# profiler action but are not a legal local reference to it. `uses:
# .github/actions/profiler` (no leading ./) is not a local action reference at
# all: GitHub reads it as owner/repo and the job fails at parse time.
malformed_refs() {
    local ref="$2"
    awk -v ref="$ref" '
        /uses:/ && /actions\/profiler/ {
            line = $0
            sub(/[[:space:]]+#.*$/, "", line)
            sub(/[[:space:]]*$/, "", line)
            v = line
            sub(/^.*uses:[[:space:]]*/, "", v)
            if (v == ref) next
            if (v == ref "/nest-probe") next
            print line
        }
    ' "$1"
}

# step_inputs <block-file> <action-ref> -> `key=value` for every input passed
# to the profiler step's `with:` block.
#
# The `uses:` key column is the anchor: in `      - uses: X` and in the
# `        uses: X` of a named step, `uses:` starts at the same column as the
# sibling `with:`, and `with:`'s own keys sit two columns deeper. A non-blank
# line left of that column ends the step.
step_inputs() {
    local ref="$2"
    awk -v ref="$ref" '
        function keycol(s,   p) { p = index(s, "uses:"); return p - 1 }
        function indent(s) { match(s, /^[ ]*/); return RLENGTH }
        {
            line = $0
            sub(/[[:space:]]+#.*$/, "", line)
            sub(/[[:space:]]*$/, "", line)
        }
        state == 0 && line ~ /uses:/ {
            v = line
            sub(/^.*uses:[[:space:]]*/, "", v)
            if (v == ref) { base = keycol(line); state = 1; withcol = -1 }
            next
        }
        state == 0 { next }
        line == "" { next }
        indent(line) < base { state = 0; next }
        state == 1 && line ~ /^[ ]*with:[[:space:]]*$/ { withcol = indent(line); state = 2; next }
        state == 2 && indent(line) <= withcol { state = 1; next }
        state == 2 && indent(line) == withcol + 2 && line ~ /^[ ]*[A-Za-z0-9_-]+:/ {
            k = line; sub(/^[ ]*/, "", k); sub(/:.*$/, "", k)
            v = line; sub(/^[ ]*[A-Za-z0-9_-]+:[[:space:]]*/, "", v)
            gsub(/^["'"'"']|["'"'"']$/, "", v)
            print k "=" v
        }
    ' "$1"
}

# declared_inputs <action.yml> -> one declared input name per line.
declared_inputs() {
    awk '
        /^inputs:[[:space:]]*$/ { in_inputs = 1; next }
        in_inputs && /^[^[:space:]#]/ { in_inputs = 0 }
        in_inputs && /^  [A-Za-z0-9_-]+:[[:space:]]*$/ {
            key = $0
            sub(/^  /, "", key)
            sub(/:[[:space:]]*$/, "", key)
            print key
        }
    ' "$1"
}

# is_linux_label <label> -> 0 linux, 1 not linux, 2 unknown.
is_linux_label() {
    case "$1" in
        ubuntu-*) return 0 ;;
        macos-* | windows-*) return 1 ;;
        *) return 2 ;;
    esac
}

# ---------------------------------------------------------------------------
# Self-test. Every extractor must produce its known answer from a planted
# sample. An extractor that silently stops matching would under-report
# coverage, which reads exactly like a clean tree.
# ---------------------------------------------------------------------------
SELFTEST_DIR="$(mktemp -d)"
trap 'rm -rf "$SELFTEST_DIR"' EXIT

cat >"$SELFTEST_DIR/sample.yml" <<'YAML'
on:
  workflow_dispatch:
jobs:
  selftest-job:
    name: Selftest
    runs-on: ${{ matrix.runner }}  # trailing comment
    strategy:
      matrix:
        include:
          - runner: ubuntu-slim
    steps:
      - uses: ./.github/actions/profiler
        with:
          interval: '7'
          runner-label: ubuntu-slim
  selftest-caller:
    uses: ./.github/workflows/other.yml
YAML

selftest_fail() {
    log_error "SELF-TEST FAILED: extractor '$1' produced '${2:-<nothing>}', expected '$3'"
    log_error "The extractor is broken; the sweep below would silently under-report instead of failing."
    exit 1
}

got="$(job_keys "$SELFTEST_DIR/sample.yml" | tr '\n' ',')"
[ "$got" = "selftest-job,selftest-caller," ] || selftest_fail job_keys "$got" "selftest-job,selftest-caller,"

job_block "$SELFTEST_DIR/sample.yml" selftest-job >"$SELFTEST_DIR/block.txt"
job_block "$SELFTEST_DIR/sample.yml" selftest-caller >"$SELFTEST_DIR/caller.txt"

got="$(runs_on "$SELFTEST_DIR/block.txt")"
[ "$got" = '${{ matrix.runner }}' ] || selftest_fail runs_on "$got" '${{ matrix.runner }}'

got="$(is_caller "$SELFTEST_DIR/caller.txt")"
[ "$got" = "yes" ] || selftest_fail is_caller "$got" "yes"

got="$(is_caller "$SELFTEST_DIR/block.txt")"
[ -z "$got" ] || selftest_fail "is_caller(negative)" "$got" "<nothing>"

got="$(matrix_values "$SELFTEST_DIR/block.txt" runner | tr '\n' ',')"
[ "$got" = "ubuntu-slim," ] || selftest_fail matrix_values "$got" "ubuntu-slim,"

got="$(covering_uses "$SELFTEST_DIR/block.txt" "./.github/actions/profiler")"
[ "$got" = "1" ] || selftest_fail covering_uses "$got" "1"

got="$(covering_uses "$SELFTEST_DIR/caller.txt" "./.github/actions/profiler")"
[ "$got" = "0" ] || selftest_fail "covering_uses(negative)" "$got" "0"

got="$(step_inputs "$SELFTEST_DIR/block.txt" "./.github/actions/profiler" | sort | tr '\n' ',')"
[ "$got" = "interval=7,runner-label=ubuntu-slim," ] || selftest_fail step_inputs "$got" "interval=7,runner-label=ubuntu-slim,"

printf '%s\n' "      - uses: .github/actions/profiler" >"$SELFTEST_DIR/bad.txt"
got="$(malformed_refs "$SELFTEST_DIR/bad.txt" "./.github/actions/profiler")"
[ -n "$got" ] || selftest_fail malformed_refs "<nothing>" "the malformed uses line"

got="$(malformed_refs "$SELFTEST_DIR/block.txt" "./.github/actions/profiler")"
[ -z "$got" ] || selftest_fail "malformed_refs(negative)" "$got" "<nothing>"

# ---------------------------------------------------------------------------
# The action contract. Input names come from the real action.yml, never from a
# list hand-copied here that would drift the day an input is added.
# ---------------------------------------------------------------------------
ACTION_YML="$ACTION_DIR/action.yml"
if [ ! -f "$ACTION_YML" ]; then
    log_error "profiler action not found at $ACTION_YML"
    log_error "This gate derives the input contract from that file; without it, it can assert nothing. Fix the path, do not skip the check."
    exit 1
fi

ACTION_REF="./$ACTION_DIR"
DECLARED="$(declared_inputs "$ACTION_YML")"
DECLARED_COUNT=$(printf '%s\n' "$DECLARED" | sed '/^$/d' | wc -l)
if [ "$DECLARED_COUNT" -lt 1 ]; then
    log_error "parsed ZERO inputs from $ACTION_YML; the action declares some, so the parser is broken"
    exit 1
fi

# ---------------------------------------------------------------------------
# The wrapper contract. A composite counts as coverage only once it is SHOWN to
# reference the profiler, using the same matcher the job sweep uses, so the day
# somebody edits that line out this gate goes red instead of certifying ~26 jobs
# as profiled.
# ---------------------------------------------------------------------------
COVERING_ACTIONS=()
for wdir in ${WRAPPER_DIRS[@]+"${WRAPPER_DIRS[@]}"}; do
    [ -n "$wdir" ] || continue
    wdir="${wdir#./}"
    wyml="$wdir/action.yml"
    if [ ! -f "$wyml" ]; then
        log_error "covering wrapper '$wdir' has no action.yml at $wyml"
        log_error "Every job counted as covered through this wrapper would be counted off a file that does not exist. Fix the path, do not drop the check."
        exit 1
    fi
    if [ "$(covering_uses "$wyml" "$ACTION_REF")" -lt 1 ]; then
        log_error "covering wrapper '$wdir' does not use $ACTION_REF"
        log_error "It is treated as coverage for every job that calls it, so without that step those jobs are unprofiled while reporting as profiled -- the exact fail-open this gate exists to prevent."
        exit 1
    fi
    COVERING_ACTIONS+=("./$wdir")
done
COVERING_ACTIONS+=(${EXTRA_COVERING_ACTIONS[@]+"${EXTRA_COVERING_ACTIONS[@]}"})

# ---------------------------------------------------------------------------
# The allowlist
# ---------------------------------------------------------------------------
declare -A ALLOW_ENTRIES=()
declare -A ALLOW_REASONS=()
if [ -f "$ALLOWLIST" ]; then
    parse_blockered_list "$ALLOWLIST" ALLOW_ENTRIES ALLOW_REASONS
    if ! verify_all_blockers "$ALLOWLIST" ALLOW_REASONS; then
        log_error "An entry in $ALLOWLIST is a hole in the 'every Linux job is profiled' invariant."
        log_error "It must say WHY that job cannot carry the profiler, not that it does not yet."
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# The sweep
# ---------------------------------------------------------------------------
if [ ! -d "$WORKFLOW_DIR" ]; then
    log_error "workflow directory not found: $WORKFLOW_DIR"
    log_error "An unscannable surface is a broken instrument, not a clean tree."
    exit 1
fi

WORKFLOWS=()
while IFS= read -r f; do
    [ -n "$f" ] && WORKFLOWS+=("$f")
done < <(find "$WORKFLOW_DIR" -maxdepth 1 -type f \( -name '*.yml' -o -name '*.yaml' \) | sort)

if [ "${#WORKFLOWS[@]}" -eq 0 ]; then
    log_error "found ZERO workflow files under $WORKFLOW_DIR"
    log_error "This gate cannot report a clean tree off an empty scan. Fix the path, do not skip the check."
    exit 1
fi

if [ "${#WORKFLOWS[@]}" -lt "$MIN_WORKFLOWS" ]; then
    log_error "found only ${#WORKFLOWS[@]} workflow file(s) under $WORKFLOW_DIR (floor: $MIN_WORKFLOWS); the scan surface is wrong, not clean"
    exit 1
fi

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$SELFTEST_DIR" "$WORK_DIR"' EXIT

TOTAL_JOBS=0
LINUX_JOBS=0
COVERED_LINUX=0
CALLER_JOBS=0
FAILURES=0
declare -A REQUIRED_UNCOVERED=()
declare -A KNOWN_KEYS=()

for wf in "${WORKFLOWS[@]}"; do
    base="$(basename "$wf")"
    while IFS= read -r job; do
        [ -n "$job" ] || continue
        key="$base:$job"
        KNOWN_KEYS["$key"]=1
        TOTAL_JOBS=$((TOTAL_JOBS + 1))

        blk="$WORK_DIR/block.txt"
        job_block "$wf" "$job" >"$blk"

        # (b) CONFIGURATION -- checked for every job that uses the action, on
        # any OS, because a misconfigured profile is wrong wherever it runs.
        while IFS= read -r bad; do
            [ -n "$bad" ] || continue
            log_error "$key: malformed profiler reference: ${bad# }"
            log_error "  A local action must be referenced as '$ACTION_REF' (leading './' required); anything else is read as owner/repo and fails at workflow parse time."
            FAILURES=$((FAILURES + 1))
        done < <(malformed_refs "$blk" "$ACTION_REF")

        # Direct use drives the CONFIGURATION relation; direct use plus any
        # declared covering wrapper drives the COVERAGE relation.
        uses_count="$(covering_uses "$blk" "$ACTION_REF")"
        covered_count="$uses_count"
        for extra in ${COVERING_ACTIONS[@]+"${COVERING_ACTIONS[@]}"}; do
            covered_count=$((covered_count + $(covering_uses "$blk" "$extra")))
        done
        if [ "$uses_count" -gt 1 ]; then
            log_error "$key: uses the profiler $uses_count times; the post hook runs once per action instance and the panels would interleave"
            FAILURES=$((FAILURES + 1))
        fi

        declared_runs_on="$(runs_on "$blk")"

        if [ "$uses_count" -ge 1 ]; then
            seen_runner_label=""
            while IFS= read -r kv; do
                [ -n "$kv" ] || continue
                k="${kv%%=*}"
                v="${kv#*=}"
                if ! printf '%s\n' "$DECLARED" | grep -qx "$k"; then
                    log_error "$key: passes input '$k', which $ACTION_YML does not declare (declared: $(printf '%s' "$DECLARED" | tr '\n' ' '))"
                    FAILURES=$((FAILURES + 1))
                    continue
                fi
                case "$k" in
                    interval)
                        if ! printf '%s' "$v" | grep -qE '^[0-9]+$'; then
                            log_error "$key: interval '$v' is not an integer; the sampler sleeps for it, and a non-numeric value makes the sample loop spin or die"
                            FAILURES=$((FAILURES + 1))
                        elif [ "$v" -lt 1 ] || [ "$v" -gt 300 ]; then
                            log_error "$key: interval '$v' is outside 1..300s; below 1 the profiler perturbs the job it measures, above 300 a 15-minute slim job yields under three samples"
                            FAILURES=$((FAILURES + 1))
                        fi
                        ;;
                    strict)
                        case "$v" in
                            true | false) ;;
                            *)
                                log_error "$key: strict '$v' is neither 'true' nor 'false'; every other value is truthy to the action and silently arms hard failure"
                                FAILURES=$((FAILURES + 1))
                                ;;
                        esac
                        ;;
                    runner-label)
                        seen_runner_label="$v"
                        if [ -z "$v" ]; then
                            log_error "$key: runner-label is empty, which disarms the HOST_LEAK check the label exists to arm"
                            FAILURES=$((FAILURES + 1))
                        elif [ "${v#\$\{\{}" = "$v" ] && [ -n "$declared_runs_on" ] &&
                            [ "${declared_runs_on#\$\{\{}" = "$declared_runs_on" ] &&
                            [ "$v" != "$declared_runs_on" ]; then
                            log_error "$key: runner-label '$v' disagrees with runs-on '$declared_runs_on'; the sampler would size the job against the wrong runner and every conclusion drawn from it is wrong"
                            FAILURES=$((FAILURES + 1))
                        fi
                        ;;
                esac
            done < <(step_inputs "$blk" "$ACTION_REF")

            if [ -z "$seen_runner_label" ]; then
                log_error "$key: uses the profiler without runner-label. Unlabelled costs two things: HOST_LEAK cannot fire at all (sampler-linux.sh:209-222 arms it off the label), and at PROC_HOST tier the advisor goes MUTE rather than wrong (report.awk advise(): 'a VM cannot be told from a container'), so the job is profiled and yields no advice. At a cgroup tier the enforced quota substitutes for the label, so the loss there is only HOST_LEAK."
                FAILURES=$((FAILURES + 1))
            fi
        fi

        # (a) COVERAGE
        if [ -n "$(is_caller "$blk")" ]; then
            CALLER_JOBS=$((CALLER_JOBS + 1))
            KNOWN_KEYS["$key"]=caller
            continue
        fi

        if [ -z "$declared_runs_on" ]; then
            log_error "$key: has neither 'runs-on:' nor a reusable-workflow 'uses:'; this gate cannot classify it and refuses to guess"
            FAILURES=$((FAILURES + 1))
            continue
        fi

        # Resolve the runner label(s).
        labels=""
        unresolved=""
        case "$declared_runs_on" in
            '${{ matrix.'*)
                mkey="${declared_runs_on#*matrix.}"
                mkey="${mkey%%[^A-Za-z0-9_-]*}"
                labels="$(matrix_values "$blk" "$mkey")"
                [ -n "$labels" ] || unresolved="matrix.$mkey has no literal values in this job"
                ;;
            '${{'*)
                unresolved="runs-on is the expression '$declared_runs_on', which no static parse can resolve"
                ;;
            *)
                labels="$(printf '%s\n' "$declared_runs_on" | tr -d '[],' | tr ' ' '\n' | sed '/^$/d')"
                ;;
        esac

        required=""
        reason=""
        if [ -n "$unresolved" ]; then
            # Fail-closed: unresolvable means "we could not prove it is not
            # Linux", and that must cost a line in the allowlist.
            required=yes
            reason="$unresolved"
        else
            while IFS= read -r label; do
                [ -n "$label" ] || continue
                set +e
                is_linux_label "$label"
                verdict=$?
                set -e
                case "$verdict" in
                    0)
                        required=yes
                        reason="runs on $label"
                        ;;
                    2)
                        required=yes
                        reason="runner label '$label' is neither ubuntu-*, macos-* nor windows-*; add it to is_linux_label rather than letting an unknown runner go unprofiled"
                        ;;
                esac
            done <<<"$labels"
        fi

        if [ -z "$required" ]; then
            KNOWN_KEYS["$key"]=nonlinux
            continue
        fi

        LINUX_JOBS=$((LINUX_JOBS + 1))
        KNOWN_KEYS["$key"]=required

        if [ "$covered_count" -ge 1 ]; then
            COVERED_LINUX=$((COVERED_LINUX + 1))
            continue
        fi

        REQUIRED_UNCOVERED["$key"]="$reason"
    done < <(job_keys "$wf")
done

if [ "$TOTAL_JOBS" -eq 0 ]; then
    log_error "parsed ZERO jobs from ${#WORKFLOWS[@]} workflow file(s) under $WORKFLOW_DIR"
    log_error "Every workflow declares jobs, so the parser is broken. This is not a clean tree."
    exit 1
fi

if [ "$TOTAL_JOBS" -lt "$MIN_JOBS" ]; then
    log_error "parsed only $TOTAL_JOBS job(s) (floor: $MIN_JOBS); the job parser found a layout it does not understand"
    exit 1
fi

if [ "$LINUX_JOBS" -lt "$MIN_LINUX" ]; then
    log_error "classified only $LINUX_JOBS job(s) as needing a profile (floor: $MIN_LINUX); the runner classifier is broken, so 'all covered' would be vacuous"
    exit 1
fi

# ---------------------------------------------------------------------------
# Verdict (a): uncovered jobs, minus the allowlist.
# ---------------------------------------------------------------------------
UNCOVERED=0
if [ "${#REQUIRED_UNCOVERED[@]}" -gt 0 ]; then
    for key in $(printf '%s\n' "${!REQUIRED_UNCOVERED[@]}" | sort); do
        if [ -n "${ALLOW_ENTRIES[$key]:-}" ]; then
            continue
        fi
        log_error "$key: ${REQUIRED_UNCOVERED[$key]} but does not use $ACTION_REF"
        UNCOVERED=$((UNCOVERED + 1))
    done
fi

if [ "$UNCOVERED" -gt 0 ]; then
    log_error "$UNCOVERED Linux job(s) are unprofiled. Add a step to each:"
    log_error "      - uses: $ACTION_REF"
    log_error "        with:"
    log_error "          runner-label: <the job's runs-on label>"
    log_error "or add '<workflow>.yml:<job>' to $ALLOWLIST with a '# BLOCKER: <reason>' saying why it cannot carry one."
    FAILURES=$((FAILURES + UNCOVERED))
fi

# ---------------------------------------------------------------------------
# Verdict (a'): allowlist liveness. An entry is stale the moment its job
# disappears, becomes covered, or stops needing coverage -- so this list can
# only shrink, and the rollout cannot leave paid-down debt sitting in it.
# ---------------------------------------------------------------------------
STALE=0
if [ "${#ALLOW_ENTRIES[@]}" -gt 0 ]; then
    for key in $(printf '%s\n' "${!ALLOW_ENTRIES[@]}" | sort); do
        kind="${KNOWN_KEYS[$key]:-}"
        if [ -z "$kind" ]; then
            log_error "$ALLOWLIST: '$key' names no job in $WORKFLOW_DIR; it suppresses nothing"
            STALE=$((STALE + 1))
        elif [ "$kind" = caller ]; then
            log_error "$ALLOWLIST: '$key' is a reusable-workflow caller, which has no runner of its own and was never required; drop the entry"
            STALE=$((STALE + 1))
        elif [ "$kind" = nonlinux ]; then
            log_error "$ALLOWLIST: '$key' does not run on Linux, so it was never required; drop the entry"
            STALE=$((STALE + 1))
        elif [ -z "${REQUIRED_UNCOVERED[$key]:-}" ]; then
            log_error "$ALLOWLIST: '$key' IS profiled now; drop the entry (an exemption that exempts nothing hides the next real one)"
            STALE=$((STALE + 1))
        fi
    done
fi

if [ "$STALE" -gt 0 ]; then
    log_error "$STALE stale entr(ies) in $ALLOWLIST. Remove them; this list is only ever allowed to shrink."
    FAILURES=$((FAILURES + STALE))
fi

if [ "$FAILURES" -gt 0 ]; then
    exit 1
fi

log_info "profiler coverage: $COVERED_LINUX/$LINUX_JOBS Linux job(s) profiled, ${#ALLOW_ENTRIES[@]} allowlisted, across $TOTAL_JOBS job(s) in ${#WORKFLOWS[@]} workflow(s) ($CALLER_JOBS reusable-workflow caller(s) excluded)"
