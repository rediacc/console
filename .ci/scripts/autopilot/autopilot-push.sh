#!/bin/bash
# THE SECURITY BOUNDARY of the autopilot (03-v2-autonomy.md section 0). The
# model never holds a write token; this script, run AFTER the model exits, is
# the only path from a handoff file to a commit and a push. It is deliberately
# tiny and boring: validate, stage exactly the declared set, tripwire, commit
# from a file, push by explicit SHA to a hardcoded-checked branch. Review any
# change to this file as a change to the security boundary itself.
#
# Wholesale staging (add with -A, --all, or a bare dot) is banned; staging is
# per validated path only, and the harness test sweeps this directory for it.
#
# Usage:
#   autopilot-push.sh --root <checkout> --handoff <file> --branch <name> \
#     [--remote origin] [--failed-jobs <file>] [--dry-run]
#
# Env (all fail closed):
#   AUTOPILOT_ALLOW_PUSH   must be exactly "true" for a real push (absent=off)
#   AUTOPILOT_GIT_NAME     committer identity (operator's noreply identity;
#   AUTOPILOT_GIT_EMAIL    03-v2-autonomy.md section 0 states the trade-off)
#
# Exit: 0 pushed (or dry-run complete), 1 escalate (nothing pushed), 2 usage.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"
ROOT="${ARG_ROOT:-}"
HANDOFF="${ARG_HANDOFF:-}"
BRANCH="${ARG_BRANCH:-}"
REMOTE="${ARG_REMOTE:-origin}"
FAILED_JOBS="${ARG_FAILED_JOBS:-}"
DRY_RUN="${ARG_DRY_RUN:-false}"

[[ -n "$ROOT" && -n "$HANDOFF" && -n "$BRANCH" ]] || {
    log_error "usage: autopilot-push.sh --root <checkout> --handoff <file> --branch <name> [--remote <name>] [--failed-jobs <file>] [--dry-run]"
    exit 2
}
require_dir "$ROOT"
cd "$ROOT"

# Stage flag, fail closed: absent means off, and only the exact string "true"
# arms the push. A dry-run needs no flag because it never writes the remote.
if [[ "$DRY_RUN" != "true" && "${AUTOPILOT_ALLOW_PUSH:-}" != "true" ]]; then
    log_error "stage-flag-disabled: AUTOPILOT_ALLOW_PUSH is not 'true'; refusing to push (fail closed)"
    exit 1
fi
require_var AUTOPILOT_GIT_NAME
require_var AUTOPILOT_GIT_EMAIL

# Hardcoded branch checks. The current branch must be exactly the one the
# caller named, and main/master are refused unconditionally: even a harness
# bug upstream must not be able to aim this script at a default branch
# (renet/account/elite have no rulesets, so this check is their only guard).
actual_branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$actual_branch" != "$BRANCH" ]]; then
    log_error "branch-mismatch: checkout is on '$actual_branch', caller named '$BRANCH'; refusing"
    exit 1
fi
if [[ "$BRANCH" == "main" || "$BRANCH" == "master" || "$BRANCH" == HEAD ]]; then
    log_error "branch-forbidden: the autopilot never pushes '$BRANCH'"
    exit 1
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

# Validate the handoff against the tree as it actually is. The status capture
# is taken here, by the harness, so the validator judges reality rather than
# anything the model asserted.
git status --porcelain=v1 -z >"$workdir/status.z"
if ! node "$SCRIPT_DIR/validate-handoff.cjs" \
    --handoff "$HANDOFF" \
    --root "$ROOT" \
    --base-head "$(git rev-parse HEAD)" \
    --status "$workdir/status.z" >"$workdir/verdict.json"; then
    log_error "handoff rejected; escalating (nothing staged, nothing pushed)"
    exit 1
fi

outcome="$(jq -r '.outcome' "$workdir/verdict.json")"
if [[ "$outcome" != "push" ]]; then
    log_error "outcome-not-push: handoff outcome is '$outcome'; this script only serves push rounds"
    exit 1
fi

# Stage exactly the validated files, one path at a time.
jq -r '.files[]' "$workdir/verdict.json" >"$workdir/files.txt"
while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    git add -- "$f"
done <"$workdir/files.txt"

# Staged-set equality: what git staged must be byte-for-byte the declared
# list. Any divergence (a pathspec that expanded, an index surprise) aborts.
git diff --cached --name-only | LC_ALL=C sort >"$workdir/staged.txt"
LC_ALL=C sort "$workdir/files.txt" >"$workdir/declared.txt"
if ! diff -u "$workdir/declared.txt" "$workdir/staged.txt" >&2; then
    log_error "staged-set-mismatch: the staged set does not equal the validated files[]; refusing to commit"
    exit 1
fi

# Tripwire on the exact bytes about to be committed, BEFORE the commit exists.
git diff --cached >"$workdir/staged.diff"
if ! node "$SCRIPT_DIR/exfil-tripwire.cjs" --diff "$workdir/staged.diff" \
    ${FAILED_JOBS:+--failed-jobs "$FAILED_JOBS"}; then
    log_error "tripwire tripped; escalating (nothing committed, nothing pushed)"
    exit 1
fi

# Commit message via -F from a file: no shell interpolation of model text.
jq -r '.commit_message' "$workdir/verdict.json" >"$workdir/msg.txt"
git -c "user.name=$AUTOPILOT_GIT_NAME" -c "user.email=$AUTOPILOT_GIT_EMAIL" \
    commit -F "$workdir/msg.txt" --quiet

sha="$(git rev-parse HEAD)"
if [[ "$DRY_RUN" == "true" ]]; then
    log_info "dry-run: would push $sha to $REMOTE refs/heads/$BRANCH"
    echo "$sha"
    exit 0
fi

# Push by explicit SHA, never a bare branch name: the ref that leaves this
# machine is exactly the commit minted above.
git push "$REMOTE" "$sha:refs/heads/$BRANCH"
log_info "pushed $sha to $REMOTE refs/heads/$BRANCH"
echo "$sha"
