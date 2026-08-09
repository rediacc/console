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
#     [--remote origin] [--failed-jobs <file>] [--verdict-out <file>] [--dry-run]
#
# THE THREE OUTCOMES ARE ALL FIRST-CLASS. `push` stages and commits; `escalate`
# and `no-change` are ROUND RESULTS, not failures: the handoff was valid, the
# model reached a legitimate conclusion, and this script exits 0 having staged
# nothing. Exiting 1 on them (as this script did until 2026-08-09) made every
# escalating round paint the job red, which fired the generic failure latch and
# lost the model's reason -- the exact information the escalation exists to
# carry. What HAPPENS next (an escalation comment, the blocked label, a ledger
# line) belongs to the workflow's post-boundary steps, which read --verdict-out.
#
# --verdict-out <file> receives the VALIDATED verdict JSON (outcome, files,
# decisions, ruled_out, escalation) on every accepted handoff, push included.
# One file, one shape, so no caller has to re-parse handoff.json -- which is
# untrusted -- to learn what the round decided.
#
# SUBMODULES (03-v2-autonomy.md section 5), gated by AUTOPILOT_ALLOW_SUBMODULES.
# When the verdict carries submodules[], each one is committed and pushed on the
# CALLER'S BRANCH NAME before console stages anything, and the parent's gitlink
# is then verified in the index at exactly the SHA that was pushed. The branch
# is created at the submodule's CURRENT HEAD, never at origin/main, so the new
# commit is a descendant of the pointer the parent recorded -- section 5's
# anti-rollback rule is ancestry, and branching elsewhere would break it
# silently. --dry-run commits locally and pushes nothing, in the submodules
# exactly as in console.
#
# Env (all fail closed):
#   AUTOPILOT_ALLOW_PUSH        must be exactly "true" for a real push (absent=off)
#   AUTOPILOT_ALLOW_SUBMODULES  must be exactly "true" for submodules[] to be
#                               honoured at all; otherwise the round is refused
#   AUTOPILOT_GIT_NAME          committer identity (operator's noreply identity;
#   AUTOPILOT_GIT_EMAIL         03-v2-autonomy.md section 0 states the trade-off)
#
# Exit: 0 pushed, dry-run complete, or a validated escalate/no-change round;
#       1 rejected handoff or tripped tripwire (nothing staged, nothing
#       pushed); 2 usage.
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
VERDICT_OUT="${ARG_VERDICT_OUT:-}"
DRY_RUN="${ARG_DRY_RUN:-false}"

[[ -n "$ROOT" && -n "$HANDOFF" && -n "$BRANCH" ]] || {
    log_error "usage: autopilot-push.sh --root <checkout> --handoff <file> --branch <name> [--remote <name>] [--failed-jobs <file>] [--verdict-out <file>] [--dry-run]"
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
SUB_ALLOWED=false
[[ "${AUTOPILOT_ALLOW_SUBMODULES:-}" == "true" ]] && SUB_ALLOWED=true
if ! node "$SCRIPT_DIR/validate-handoff.cjs" \
    --handoff "$HANDOFF" \
    --root "$ROOT" \
    --base-head "$(git rev-parse HEAD)" \
    --allow-submodules "$SUB_ALLOWED" \
    --status "$workdir/status.z" >"$workdir/verdict.json"; then
    log_error "handoff rejected; escalating (nothing staged, nothing pushed)"
    exit 1
fi

# The verdict is published BEFORE any outcome branching, so the workflow's
# post-boundary steps see the same validated object on every accepted round.
if [[ -n "$VERDICT_OUT" ]]; then
    cat "$workdir/verdict.json" >"$VERDICT_OUT"
fi

outcome="$(jq -r '.outcome' "$workdir/verdict.json")"
case "$outcome" in
    push) ;;
    escalate | no-change)
        # Nothing staged, nothing committed, nothing pushed -- and NOT an
        # error. A no-change round with a dirty tree never reaches here: the
        # validator already refused it as undeclared-dirty.
        log_info "outcome-$outcome: validated round, nothing staged and nothing pushed; the post-boundary steps own the follow-up"
        exit 0
        ;;
    *)
        # Unreachable while the schema pins the enum; kept so a schema
        # widening cannot silently reach the staging code below.
        log_error "outcome-unknown: handoff outcome is '$outcome'; refusing to stage anything"
        exit 1
        ;;
esac

# ---------------------------------------------------------------------------
# SUBMODULES FIRST, then console (03-v2-autonomy.md section 5). The order is
# the design's: each submodule's branch is committed and pushed before the
# parent stages its gitlink, so the pointer console publishes always names a
# commit that already exists on the remote. The reverse order publishes a
# console commit pointing at a SHA nobody else can fetch, which is the shape
# that makes a submodule bump unreviewable.
# ---------------------------------------------------------------------------
: >"$workdir/sub-shas.txt"
sub_count="$(jq -r '(.submodules // []) | length' "$workdir/verdict.json")"

if ((sub_count > 0)); then
    # Belt and braces: the validator already refused submodules[] when the
    # flag is off. This is the same refusal at the write site, because the two
    # are separated by a process boundary and the one that stages bytes should
    # not depend on the other having run.
    if [[ "$SUB_ALLOWED" != "true" ]]; then
        log_error "stage-flag-disabled: AUTOPILOT_ALLOW_SUBMODULES is not 'true'; refusing ${sub_count} submodule change(s) (fail closed)"
        exit 1
    fi
fi

for ((i = 0; i < sub_count; i++)); do
    sub="$(jq -r ".submodules[$i].path" "$workdir/verdict.json")"
    subdir="$ROOT/$sub"

    # THE SUBMODULE MUST BE ITS OWN REPOSITORY, and `rev-parse --git-dir` is
    # the WRONG way to ask. Git walks UP from the directory, so inside an
    # uninitialized submodule it happily answers with the PARENT's git dir --
    # every command below would then run against console with a working
    # directory one level down, and `git add pkg/x.go` would stage
    # private/renet/pkg/x.go as ordinary console content. Comparing the
    # resolved toplevel is the question actually being asked.
    #
    # BELT AND BRACES, AND CURRENTLY UNREACHABLE -- said plainly so nobody
    # mistakes it for a live control or deletes it as dead code. Both routes to
    # an absent submodule are stopped earlier: an uninitialized one makes the
    # parent report NOTHING dirty at that path, so the handoff dies at
    # path-not-dirty; a broken `gitdir:` pointer makes the parent's own
    # `git status` fatal, so this script dies at the status capture above.
    # Measured on git 2.43, both directions. It stays because the outcome it
    # prevents (submodule content committed into console as ordinary files) is
    # severe and the check costs one comparison.
    if [[ ! -d "$subdir" ]]; then
        log_error "submodule-missing: '$sub' is not a directory in this checkout"
        exit 1
    fi
    sub_top="$(git -C "$subdir" rev-parse --show-toplevel 2>/dev/null || true)"
    if [[ -z "$sub_top" ]] || [[ "$(cd "$sub_top" && pwd -P)" != "$(cd "$subdir" && pwd -P)" ]]; then
        log_error "submodule-not-initialized: '$sub' is not its own git checkout here (toplevel resolves to '${sub_top:-<none>}'); refusing rather than committing submodule content into the parent"
        exit 1
    fi

    # Branch handling, and the base is deliberately CURRENT HEAD rather than
    # origin/main. Section 5's anti-rollback rule is ancestry: only a
    # descendant of the pointer the parent recorded may ever be committed.
    # Branching at the recorded pointer makes that true by construction;
    # branching at origin/main would silently rebase the round's work onto a
    # different base, which is precisely the "stale checkout" case the design
    # says must commit nothing.
    sub_branch="$(git -C "$subdir" rev-parse --abbrev-ref HEAD)"
    if [[ "$BRANCH" == "main" || "$BRANCH" == "master" || "$BRANCH" == HEAD ]]; then
        log_error "submodule-branch-forbidden: the autopilot never pushes '$BRANCH' in '$sub'"
        exit 1
    fi
    if [[ "$sub_branch" != "$BRANCH" ]]; then
        if git -C "$subdir" show-ref --verify --quiet "refs/heads/$BRANCH"; then
            # Checking it out would move HEAD across a tree the model has
            # already edited. Refuse rather than guess which side wins.
            log_error "submodule-branch-exists: '$sub' already has a local '$BRANCH' but HEAD is on '$sub_branch'; refusing to move HEAD across the round's edits"
            exit 1
        fi
        git -C "$subdir" checkout -q -b "$BRANCH"
    fi
    sub_base="$(git -C "$subdir" rev-parse HEAD)"

    # Stage exactly the declared files, one path at a time, then prove the
    # staged set equals the declared set -- the identical check the console
    # boundary applies, because a pathspec that expands is the same bug here.
    jq -r ".submodules[$i].files[]" "$workdir/verdict.json" >"$workdir/sub-files.txt"
    while IFS= read -r f; do
        [[ -z "$f" ]] && continue
        # A path git has never heard of AND that is not on disk is one `git
        # add` would die on with a bare `fatal: pathspec`. Naming the class
        # here keeps a mistyped path diagnosable. A DELETED file is still
        # known to git, so this does not reject a legitimate removal.
        if ! git -C "$subdir" ls-files --error-unmatch -- "$f" >/dev/null 2>&1 && [[ ! -e "$subdir/$f" ]]; then
            log_error "submodule-path-missing: '$sub/$f' is declared but is neither tracked in the submodule nor present on disk"
            exit 1
        fi
        git -C "$subdir" add -- "$f"
    done <"$workdir/sub-files.txt"
    git -C "$subdir" diff --cached --name-only | LC_ALL=C sort >"$workdir/sub-staged.txt"
    LC_ALL=C sort "$workdir/sub-files.txt" >"$workdir/sub-declared.txt"
    if ! diff -u "$workdir/sub-declared.txt" "$workdir/sub-staged.txt" >&2; then
        log_error "submodule-staged-set-mismatch: '$sub' staged set does not equal the validated files[]; refusing to commit"
        exit 1
    fi

    # Tripwire on the submodule's staged bytes, with the paths rewritten to be
    # PARENT-relative. Without the prefixes the tripwire would see `pkg/x.go`,
    # match no module prefix, and treat every byte as out of scope; with them
    # it sees `private/renet/pkg/x.go` and the same scope map that governs a
    # console fix governs this one.
    git -C "$subdir" diff --cached --src-prefix="a/$sub/" --dst-prefix="b/$sub/" >"$workdir/sub-staged.diff"
    if ! node "$SCRIPT_DIR/exfil-tripwire.cjs" --diff "$workdir/sub-staged.diff" \
        ${FAILED_JOBS:+--failed-jobs "$FAILED_JOBS"}; then
        log_error "tripwire tripped in submodule '$sub'; escalating (nothing committed there, nothing pushed)"
        exit 1
    fi

    jq -r ".submodules[$i].message" "$workdir/verdict.json" >"$workdir/sub-msg.txt"
    git -C "$subdir" -c "user.name=$AUTOPILOT_GIT_NAME" -c "user.email=$AUTOPILOT_GIT_EMAIL" \
        commit -F "$workdir/sub-msg.txt" --quiet
    sub_sha="$(git -C "$subdir" rev-parse HEAD)"

    # Ancestry, asserted rather than assumed. It holds by construction today;
    # it is checked so that a future change to the base above cannot quietly
    # publish a pointer that rolls the submodule backwards.
    if ! git -C "$subdir" merge-base --is-ancestor "$sub_base" "$sub_sha"; then
        log_error "submodule-pointer-rollback: '$sub' new commit $sub_sha is not a descendant of the recorded pointer $sub_base; refusing"
        exit 1
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "dry-run: would push $sub_sha to $REMOTE refs/heads/$BRANCH in '$sub'"
    else
        git -C "$subdir" push "$REMOTE" "$sub_sha:refs/heads/$BRANCH"
        log_info "pushed $sub_sha to $REMOTE refs/heads/$BRANCH in '$sub'"
    fi
    printf '%s %s\n' "$sub" "$sub_sha" >>"$workdir/sub-shas.txt"
done

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

# The pointer advance, verified in the INDEX rather than trusted. `git add` on
# a submodule path stages whatever the submodule's HEAD happens to be, so this
# is what proves the console commit about to be minted names exactly the SHA
# that was pushed a moment ago, at mode 160000 (a gitlink, not a directory of
# files someone flattened into the parent).
while read -r sub sub_sha; do
    [[ -z "$sub" ]] && continue
    entry="$(git ls-files -s -- "$sub")"
    staged_mode="$(awk '{print $1}' <<<"$entry")"
    staged_sha="$(awk '{print $2}' <<<"$entry")"
    if [[ "$staged_mode" != "160000" ]]; then
        log_error "gitlink-not-staged: '$sub' is staged as mode '${staged_mode:-<absent>}', not a 160000 gitlink; refusing to commit"
        exit 1
    fi
    if [[ "$staged_sha" != "$sub_sha" ]]; then
        log_error "gitlink-sha-mismatch: '$sub' is staged at $staged_sha but the harness pushed $sub_sha; refusing to commit a pointer to a different commit"
        exit 1
    fi
    log_info "gitlink verified: $sub -> $sub_sha"
done <"$workdir/sub-shas.txt"

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
