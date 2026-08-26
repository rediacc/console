#!/usr/bin/env bash
# Every ROOT scripts/ path reachable from non-quality CI code must classify FULL.
#
# WHY THIS EXISTS. On 2026-08-06 the blanket `scripts/` harness rule in
# .ci/scripts/ci/scope-map.cjs was narrowed: gate sources became a zero-job
# `gates` module so an attribution-URL check would stop running the ceph fork
# test. Two subsets were carved out to stay full because a GATED job genuinely
# executes them -- scripts/drills/ and scripts/generate-third-party-licenses.ts.
#
# That carve-out list was traced BY HAND, once, at one commit. Nothing stopped
# the next reachable file from being added and silently narrowed: a new
# scripts/foo.sh invoked from a build or deploy script would classify as `gates`,
# pull nothing into scope, and the job that depends on it would be skipped on the
# very delta that changed it. The failure is invisible -- CI goes green faster,
# and nobody looks for a job that was never scheduled.
#
# THE INVARIANT, and why it is drawn here. A root scripts/ path referenced from
# .github/workflows/ or from the BUILD/DEPLOY/SETUP/PRIVATE halves of .ci/scripts
# is reachable from a gated job, so it must force full. Paths referenced only
# from .ci/scripts/quality/ or .ci/scripts/test/ are quality-lane consumers, and
# narrowing those is the entire point of the split -- quality lanes carry no
# run_* gate at all (ci-quality.yml has zero `run_` references), so the engine
# cannot skip them however a path classifies.
#
# CONTROL-FIRST. Before judging real paths this plants a synthetic reachable path
# and asserts the checker calls it a violation. If the control cannot fire, the
# gate exits non-zero without looking at anything else: a checker that cannot
# fail would report "all reachable paths force full" on a tree where none do.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
NC=$'\033[0m'

# Directories whose code runs in gated jobs. Deliberately NOT .ci/scripts/quality
# or .ci/scripts/test: those are the quality lanes, which are unscopeable.
GATED_DIRS=(
    ".github/workflows"
    ".ci/scripts/build"
    ".ci/scripts/deploy"
    ".ci/scripts/setup"
    ".ci/scripts/private"
    ".ci/scripts/housekeeping"
)

# `run.sh` is the drill dispatcher (run.sh -> scripts/drills/*.sh) and is itself a
# ROOT_MANIFEST path, so editing it forces full on its own. It is scanned because
# what it DISPATCHES to must still be full.
GATED_FILES=("run.sh")

# Extract root scripts/ paths that are INVOKED, not merely mentioned.
#
# The distinction is the whole accuracy of this gate. Measured 2026-08-06: the
# first version flagged scripts/dev/scrub-sentinel.sh from two call sites, and
# BOTH were `log_error` strings printing remediation advice to a human
# (cleanup-versions.sh:1258, upload-to-r2.sh:223). Treating a mention as a
# dependency would have forced full CI on every scripts/dev edit forever, on
# evidence that was only ever a help message.
#
# So a reference counts only in COMMAND POSITION: at the start of a command, or
# directly after an interpreter / path prefix. Output statements are excluded
# outright, because a path inside a message is documentation.
#
# The leading class also rejects `.ci/scripts/` and `packages/www/scripts/`: a
# match must begin at a path boundary that is not itself a path segment.
extract_refs() {
    local target="$1"
    grep -rhE '(^|[^A-Za-z0-9_./-])(\./|"?\$[A-Za-z_]+/)?scripts/' "$target" 2>/dev/null |
        grep -vE '\b(log_error|log_warn|log_info|log_debug|echo|printf)\b' |
        grep -oE '(^|[[:space:]]|"|\x27|\$\(|`|&&|\|\||;)[[:space:]]*((bash|sh|source|node|python3)[[:space:]]+|npx[[:space:]]+tsx[[:space:]]+|\./|"?\$[A-Za-z_]+/)?scripts/[A-Za-z0-9_./-]+' |
        grep -oE 'scripts/[A-Za-z0-9_./-]+' |
        sed -E 's#[^A-Za-z0-9_./-]+$##' |
        grep -vE '\.(md|txt)$' |
        sort -u || true
}

# The same rule, one tree over. `.ci/scripts/**` is currently ALL harness
# (scope-map.cjs's `ci-harness`), so every reference below classifies `full`
# today and this scan is green. It exists for the day someone narrows part of
# `.ci/` -- the refinement scope-map.cjs's own comment anticipates -- because
# nothing else would notice a referenced path becoming narrowable.
#
# WHY THE OLD PREMISE WAS WRONG. This gate's header says paths referenced only
# from `.ci/scripts/quality/` or `.ci/scripts/test/` are "quality-lane consumers"
# and therefore unscopeable. That is false in the other direction: several
# `.ci/scripts/quality/` files are executed from NON-quality jobs --
# `.github/workflows/ci-build-renet.yml:131` runs check-no-otlp-creds.sh against
# the real release binaries, `ci.yml:834` runs check-release-state.sh, and
# `ci.yml:531,536,539` run three `.ci/scripts/test/gates/` tests in `run-sh-tests`.
# Those jobs happen to carry no `run_*` gate TODAY, which is luck rather than
# architecture. Scanning workflow-wide (not per-job) keeps that luck from being
# load-bearing, and matches how GATED_DIRS already treats `.github/workflows`.
extract_ci_refs() {
    local target="$1"
    grep -rhE '(^|[^A-Za-z0-9_./-])(\./)?\.ci/scripts/' "$target" 2>/dev/null |
        grep -vE '\b(log_error|log_warn|log_info|log_debug|echo|printf)\b' |
        grep -oE '(^|[[:space:]]|"|\x27|\$\(|`|&&|\|\||;)[[:space:]]*((bash|sh|source|node|python3)[[:space:]]+|npx[[:space:]]+tsx[[:space:]]+|\./)?\.ci/scripts/[A-Za-z0-9_./-]+' |
        grep -oE '\.ci/scripts/[A-Za-z0-9_./-]+' |
        sed -E 's#[^A-Za-z0-9_./-]+$##' |
        grep -vE '\.(md|txt)$' |
        sort -u || true
}

# run.sh dispatches many subcommands; only the ones a WORKFLOW actually invokes
# are reachable from a gated job. `./run.sh drill ...` appears in ct-tests.yml,
# `./run.sh worktree` does not, so scripts/dev/worktree.sh is legitimately
# narrowable even though run.sh names it.
ci_invoked_runsh_subcommands() {
    grep -rhoE '\./run\.sh[[:space:]]+[a-z][a-z0-9-]*' .github/workflows/ 2>/dev/null |
        awk '{print $2}' | sort -u || true
}

classify_mode() {
    node -e '
const {classify} = require(process.argv[1] + "/.ci/scripts/ci/scope-map.cjs");
process.stdout.write(classify([process.argv[2]], {}).mode);
' "$REPO_ROOT" "$1" 2>/dev/null || echo "ERROR"
}

violations=()
check_path() {
    local p="$1" src="$2"
    [[ -e "$p" ]] || return 0 # a reference to a path that does not exist is a
    # different bug; check-command-paths owns that.
    local mode
    mode="$(classify_mode "$p")"
    if [[ "$mode" != "full" ]]; then
        violations+=("$p (referenced from $src) classifies '$mode', expected 'full'")
    fi
}

# ---- CONTROL A: the EXTRACTOR must actually fire -----------------------------
#
# The controls below this used to be the whole control section, and they only
# ever called classify_mode on two real paths. Neither touched extract_refs. A
# regression that made the extractor return NOTHING would leave this gate
# printing its success line over an empty scan -- "I flagged nothing today"
# reported as "nothing is reachable". Found by review 2026-08-26, one round
# after the identical defect shipped in test-ci-compat-prose.sh.
#
# So: plant a synthetic file containing one command-position reference and one
# log_error mention, and require the extractor to return EXACTLY the first.
_ctl_dir="$(mktemp -d)"
trap 'rm -rf "$_ctl_dir"' EXIT
{
    printf 'bash scripts/synthetic-control-probe.sh\n'
    printf 'log_error "see scripts/not-a-dependency.sh for details"\n'
} >"$_ctl_dir/probe.sh"

_ctl_got="$(extract_refs "$_ctl_dir" | tr '\n' ' ' | sed 's/ $//')"
if [[ "$_ctl_got" != "scripts/synthetic-control-probe.sh" ]]; then
    echo "${RED}✗ CONTROL FAILED${NC}: the reference extractor did not return the planted path." >&2
    echo "  expected exactly 'scripts/synthetic-control-probe.sh', got: '${_ctl_got:-<nothing>}'" >&2
    echo "  A scanner that matches nothing reports every tree as clean, so this" >&2
    echo "  gate refuses to report a result." >&2
    exit 1
fi

{
    printf 'bash .ci/scripts/synthetic-ci-probe.sh\n'
    printf 'log_error "see .ci/scripts/not-a-dependency.sh for details"\n'
} >"$_ctl_dir/probe.sh"
_ctl_ci="$(extract_ci_refs "$_ctl_dir" | tr '\n' ' ' | sed 's/ $//')"
if [[ "$_ctl_ci" != ".ci/scripts/synthetic-ci-probe.sh" ]]; then
    echo "${RED}✗ CONTROL FAILED${NC}: the .ci extractor did not return the planted path." >&2
    echo "  expected exactly '.ci/scripts/synthetic-ci-probe.sh', got: '${_ctl_ci:-<nothing>}'" >&2
    exit 1
fi

# ---- CONTROL: a synthetic reachable path MUST be judged a violation ----------
control_mode="$(classify_mode "scripts/check-embed-credits.ts")"
if [[ "$control_mode" != "reduced" ]]; then
    echo "${RED}✗ CONTROL FAILED${NC}: a known gate source classified '$control_mode', not 'reduced'." >&2
    echo "  The checker cannot tell a narrowed path from a full one, so its verdict" >&2
    echo "  on real paths is meaningless. Refusing to report a result." >&2
    exit 1
fi
control_full="$(classify_mode "scripts/drills/lib.sh")"
if [[ "$control_full" != "full" ]]; then
    echo "${RED}✗ CONTROL FAILED${NC}: a known carve-out classified '$control_full', not 'full'." >&2
    echo "  The carve-outs this gate exists to protect are not in force." >&2
    exit 1
fi

# ---- the real scan -----------------------------------------------------------
for d in "${GATED_DIRS[@]}"; do
    [[ -d "$d" ]] || continue
    while IFS= read -r ref; do
        [[ -n "$ref" ]] && check_path "$ref" "$d"
    done < <(extract_refs "$d")
done
# run.sh: only the dispatch targets of CI-invoked subcommands count. The
# subcommand name is matched against the dispatch block that mentions it, so a
# new `./run.sh <sub>` in a workflow drags its target into the check
# automatically rather than needing this list edited.
for f in "${GATED_FILES[@]}"; do
    [[ -f "$f" ]] || continue
    while IFS= read -r sub; do
        [[ -n "$sub" ]] || continue
        subq="$sub"
        while IFS= read -r ref; do
            [[ -n "$ref" ]] && check_path "$ref" "$f ($sub)"
        done < <(awk -v subcmd="$subq" '
            # NEAREST PRECEDING TOP-LEVEL LABEL, not a block scan.
            #
            # This was `grep -A 12` and review found it one line short: run.sh
            # drill dispatches THREE targets and the window ended at :1994, so
            # scripts/drills/license.sh at :1995 was never checked. A scan that
            # stops early is exactly the under-match this gate exists to catch,
            # so a bigger magic number is the wrong fix -- 16 works today and
            # breaks on the fourth drill.
            #
            # Trying to read the arm to its closing `;;` was worse: run.sh nests
            # case statements and its arms terminate inline (`stop) account_stop
            # ;;`), so the block scan ran PAST `account)` and mis-attributed
            # scripts/dev/worktree.sh to it.
            #
            # Attribution by nearest preceding TOP-LEVEL label needs no
            # understanding of arm termination at all: every dispatch belongs to
            # the last subcommand label seen at the outermost indentation.
            /^        [A-Za-z0-9_"|-]+\)/ {
                lbl = $0
                gsub(/^[[:space:]]*"?/, "", lbl)
                gsub(/"?\).*$/, "", lbl)
                cur = lbl
            }
            cur == subcmd { print }
        ' "$f" 2>/dev/null | grep -oE 'scripts/[A-Za-z0-9_./-]+' | sort -u)
    done < <(ci_invoked_runsh_subcommands)
done

# ---- the .ci/scripts scan ----------------------------------------------------
ci_scanned=0
for d in "${GATED_DIRS[@]}"; do
    [[ -d "$d" ]] || continue
    while IFS= read -r ref; do
        [[ -n "$ref" ]] || continue
        ci_scanned=$((ci_scanned + 1))
        check_path "$ref" "$d"
    done < <(extract_ci_refs "$d")
done

# ANTI-VACUITY. The workflows genuinely invoke dozens of .ci/scripts paths; a
# scan that found almost none means the extractor broke, not that the tree got
# clean. The controls above prove it CAN fire on a planted file; this proves it
# fired on the REAL tree.
if [[ "$ci_scanned" -lt 20 ]]; then
    echo "${RED}✗ VACUOUS SCAN${NC}: only $ci_scanned .ci/scripts reference(s) found across ${#GATED_DIRS[@]} dirs." >&2
    echo "  The real tree invokes far more than that, so the enumeration broke." >&2
    exit 1
fi

if ((${#violations[@]} > 0)); then
    echo "${RED}✗ ${#violations[@]} path(s) reachable from a gated job do not force full CI:${NC}" >&2
    printf '  %s\n' "${violations[@]}" >&2
    echo "" >&2
    echo "Each of these is executed by (or dispatched from) code that runs in a gated" >&2
    echo "job, so a delta touching only that file would skip the job that depends on" >&2
    echo "it. Add a carve-out rule in .ci/scripts/ci/scope-map.cjs ABOVE the" >&2
    echo "'scripts-gates' rule (first match wins), mirroring 'scripts-drills'." >&2
    exit 1
fi

echo "${GREEN}✓${NC} every root scripts/ and .ci/scripts/ path reachable from a gated job forces full CI"
echo "  ($ci_scanned .ci/scripts reference(s) scanned; extractor controls fired, so this is not an empty pass)"
echo "  Blind spot: scanning is workflow-WIDE, not per-job. A path referenced from"
echo "  an ungated job is held to the same rule, which is conservative, and a"
echo "  second-level dependency (a script a scanned script calls) is not followed."
