#!/bin/bash
# block-untagged-commit.sh must know WHICH BRANCH it is judging, including when
# HEAD is detached.
#
# WHY THIS EXISTS. The guard validates a PR-TASK id against
# agent/pr/<branch>.md, and it resolved <branch> with
# `git rev-parse --abbrev-ref HEAD`. That prints the literal string "HEAD" when
# detached, so the snapshot path became agent/pr/HEAD.md, nothing was found, and
# a TYPO'D id -- the case the guard was extended for -- sailed straight through.
#
# Detached is not exotic. It is EVERY pull_request checkout (actions/checkout
# lands on refs/pull/N/merge) and every halted rebase. Measured 2026-08-27: the
# suite case asserting a typo is refused returned 0 in CI while passing on every
# developer machine, for exactly this reason.
#
# Lives here rather than in test-hooks.sh because every case needs a REAL repo
# in a specific HEAD state, and that suite's `check` helper drives the guard
# against the live tree with no env or cwd control.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GUARD="${GUARD:-$REPO_ROOT/.claude/hooks/pre-bash/block-untagged-commit.sh}"
REAL="f2757830"
TYPO="f2757831"

log_test "block-untagged-commit resolves its branch in every HEAD state"

D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT

g() { git -C "$D" "$@"; }

g init -q -b 0827-1
g config user.email fixture@example.invalid
g config user.name 'branch-fixture'
mkdir -p "$D/agent/pr"
printf '### Enforcement layer\n\n`PR-TASK: %s`\n' "$REAL" >"$D/agent/pr/0827-1.md"
printf 'base\n' >"$D/f.txt"
g add -A
g commit -qm base
BASE_SHA="$(g rev-parse HEAD)"

# Drive the guard the way the Bash tool does: JSON on stdin, cwd inside the
# fixture, CLAUDE_PROJECT_DIR naming it. PR_HEAD_REF/GITHUB_HEAD_REF are cleared
# per call so a real CI run's own environment cannot decide these cases for us.
run_guard() {
    local id="$1" env_k="${2:-}" env_v="${3:-}" json rc=0
    json=$(printf '{"tool_input":{"command":%s}}' \
        "$(jq -Rn --arg c "$(printf 'git commit -m "feat: x\n\nPR-TASK: %s"' "$id")" '$c')")
    if [[ -n "$env_k" ]]; then
        printf '%s' "$json" | (cd "$D" && env -u PR_HEAD_REF -u GITHUB_HEAD_REF \
            CLAUDE_PROJECT_DIR="$D" "$env_k=$env_v" bash "$GUARD" >/dev/null 2>&1) || rc=$?
    else
        printf '%s' "$json" | (cd "$D" && env -u PR_HEAD_REF -u GITHUB_HEAD_REF \
            CLAUDE_PROJECT_DIR="$D" bash "$GUARD" >/dev/null 2>&1) || rc=$?
    fi
    printf '%s' "$rc"
}

expect() {
    local want="$1" got="$2" label="$3"
    if [[ "$want" == "$got" ]]; then
        log_pass "$label"
    else
        log_fail "$label (wanted exit $want, got $got)"
    fi
}

# --- on a branch: the baseline the whole guard rests on ---------------------
expect 2 "$(run_guard "$TYPO")" "on a branch: a typo'd id is refused"
expect 0 "$(run_guard "$REAL")" "on a branch CONTROL: the real id passes"

# --- plain detached checkout ------------------------------------------------
# There is genuinely no branch here and therefore no published epic set, so the
# guard ALLOWS -- the same stance it takes for any message it cannot judge. The
# control below proves the fixture really is detached, because a case that
# expects 0 would also pass if the detach silently failed.
g checkout -q --detach "$BASE_SHA"
expect 0 "$(run_guard "$TYPO")" "plain detach: no branch exists, so it allows rather than refusing blind"
expect 0 "$(run_guard "$REAL")" "plain detach CONTROL: the real id still passes"
ABBREV="$(g rev-parse --abbrev-ref HEAD)"
if [[ "$ABBREV" == "HEAD" ]]; then
    log_pass "fixture precondition: abbrev-ref really does print the string HEAD when detached"
else
    log_fail "fixture precondition: abbrev-ref printed '$ABBREV', so nothing above was detached"
fi

# --- detached under CI, where the environment names the branch ---------------
expect 2 "$(run_guard "$TYPO" GITHUB_HEAD_REF 0827-1)" \
    "detached + GITHUB_HEAD_REF: the typo is refused -- the CI case that was red"
expect 2 "$(run_guard "$TYPO" PR_HEAD_REF 0827-1)" \
    "detached + PR_HEAD_REF: same, via the variable the gate step sets"
expect 0 "$(run_guard "$TYPO" GITHUB_HEAD_REF no-such-branch)" \
    "CONTROL: a branch with NO snapshot has no set to judge, so it allows"

# --- halted rebase: the detached case that actually happens here -------------
# This repo has a rebase executor, so committing mid-rebase is normal, and that
# is precisely when losing id validation would hurt. git remembers the branch in
# rebase-merge/head-name.
g checkout -q 0827-1
printf 'mine\n' >"$D/f.txt"
g commit -qam mine
g checkout -q -b other "$BASE_SHA"
printf 'theirs\n' >"$D/f.txt"
g commit -qam theirs
g checkout -q 0827-1
GIT_EDITOR=true g rebase other >/dev/null 2>&1 || true

# ANTI-VACUITY: a rebase that did not halt leaves HEAD on the branch, where the
# ordinary resolution works and the case below would pass having proven nothing.
# `--git-path` prints a path relative to the repo, so it is joined explicitly --
# resolving it against this script's cwd is how the first draft of this control
# reported "not halted" for a rebase that was.
MID=no
for d in rebase-merge rebase-apply; do
    p="$D/$(g rev-parse --git-path "$d")"
    [[ -d "$p" ]] && MID=yes && break
done
if [[ "$MID" == yes ]]; then
    log_pass "fixture precondition: the rebase really is halted mid-list"
else
    log_fail "fixture precondition: the rebase did not halt, so the cases below prove nothing"
fi

expect 2 "$(run_guard "$TYPO")" "mid-rebase: the branch is recovered from head-name, so the typo is refused"
expect 0 "$(run_guard "$REAL")" "mid-rebase CONTROL: the real id passes"

log_pass "all HEAD-state cases for block-untagged-commit"
