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
        while IFS= read -r ref; do
            [[ -n "$ref" ]] && check_path "$ref" "$f ($sub)"
        done < <(grep -A 12 -E "^[[:space:]]*\"?${sub}\"?\)" "$f" 2>/dev/null |
            grep -oE 'scripts/[A-Za-z0-9_./-]+' | sort -u)
    done < <(ci_invoked_runsh_subcommands)
done

if ((${#violations[@]} > 0)); then
    echo "${RED}✗ ${#violations[@]} root scripts/ path(s) reachable from a gated job do not force full CI:${NC}" >&2
    printf '  %s\n' "${violations[@]}" >&2
    echo "" >&2
    echo "Each of these is executed by (or dispatched from) code that runs in a gated" >&2
    echo "job, so a delta touching only that file would skip the job that depends on" >&2
    echo "it. Add a carve-out rule in .ci/scripts/ci/scope-map.cjs ABOVE the" >&2
    echo "'scripts-gates' rule (first match wins), mirroring 'scripts-drills'." >&2
    exit 1
fi

echo "${GREEN}✓${NC} every root scripts/ path reachable from a gated job forces full CI"
