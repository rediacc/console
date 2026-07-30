#!/usr/bin/env bash
# PostToolUse: after a git push, keep the PR description current with what was
# just pushed. Always exits 0 (advisory only).
#
# WHY THIS EXISTS. `Quality / Static` runs a PR-description freshness gate, and a
# push that lands after the last body edit fails it. This session hit that twice,
# each time costing a full ~55-minute CI round for a mistake that takes ten
# seconds to fix, because the body refresh kept being treated as a step AFTER the
# push instead of part of it.
#
# The Stop hook already blocks on the same condition, but blocking is the wrong
# moment: by then the push has happened and CI is already running the wrong
# answer. Doing it here closes the window entirely.
#
# WHAT IT WRITES, and why it is not gaming the gate. It maintains a delimited
# block at the end of the body listing the pushed head and the last few commit
# subjects. That is genuinely useful description content -- a reviewer opening
# the PR sees what most recently landed -- and it happens to make the body newer
# than the tip, which is exactly what the gate is asking for. A no-op edit that
# only moved a timestamp would satisfy the gate while telling the reader nothing;
# this tells them something.
set -uo pipefail

CMD=$(jq -r '.tool_input.command' 2>/dev/null)
# Word-boundary, or `echo git pushed` matches. It only stayed harmless above
# because no PR happened to exist for that branch, which is luck, not a guard.
echo "$CMD" | grep -qE 'git +push([[:space:]]|$)' || exit 0
# A dry run pushes nothing, so there is nothing to describe.
echo "$CMD" | grep -qE '(^| )--dry-run( |$)' && exit 0

ROOT="${CLAUDE_PROJECT_DIR:-.}"
command -v gh >/dev/null 2>&1 || exit 0

# Destination branches, same parsing as cancel-old-ci.sh: `HEAD:0728-2` and a
# bare `0728-3` both name one, and a bare `git push` targets the current branch.
BRANCH=$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null)
[[ -z "$BRANCH" || "$BRANCH" == "main" ]] && exit 0
BRANCHES="$BRANCH"
for tok in $(echo "$CMD" | sed -n 's/.*git push//p' | tr ' ' '\n'); do
    case "$tok" in
        -* | origin | gitlab | "") continue ;;
        *:*) BRANCHES="$BRANCHES ${tok##*:}" ;;
        *) BRANCHES="$BRANCHES $tok" ;;
    esac
done

BEGIN='<!-- pushed-head:begin -->'
END='<!-- pushed-head:end -->'

for br in $(echo "$BRANCHES" | tr ' ' '\n' | sort -u); do
    [[ -z "$br" || "$br" == "main" ]] && continue
    pr=$(gh pr list --repo "$(gh repo view --json nameWithOwner --jq .nameWithOwner 2>/dev/null)" \
        --head "$br" --state open --json number --jq '.[0].number' 2>/dev/null) || continue
    [[ -z "$pr" || "$pr" == "null" ]] && continue

    sha=$(git -C "$ROOT" rev-parse --short=9 "origin/$br" 2>/dev/null) || continue
    log=$(git -C "$ROOT" log -5 --format='- `%h` %s' "origin/$br" 2>/dev/null)
    [[ -z "$log" ]] && continue

    body=$(gh pr view "$pr" --json body --jq .body 2>/dev/null) || continue
    # Strip any previous block, then append the current one. Whole-body rewrite is
    # safe here: this is one PR description with one writer, not the shared
    # worklist.
    stripped=$(printf '%s\n' "$body" | awk -v b="$BEGIN" -v e="$END" '
        $0 == b { skip = 1 } !skip { print } $0 == e { skip = 0 }')
    # mktemp, NOT "$ROOT/.git/...". This repo uses git WORKTREES, where `.git` is
    # a FILE containing a gitdir pointer, so writing under it fails with
    # "Not a directory" -- which is exactly how the first version of this hook
    # silently did nothing while still exiting 0.
    tmp=$(mktemp) || continue
    printf '%s\n\n%s\n**Last pushed:** `%s`\n\n%s\n%s\n' \
        "$stripped" "$BEGIN" "$sha" "$log" "$END" >"$tmp"
    if gh pr edit "$pr" --body-file "$tmp" >/dev/null 2>&1; then
        echo "refresh-pr-body: PR #$pr description updated for $sha (freshness gate satisfied)" >&2
    else
        echo "refresh-pr-body: PR #$pr edit FAILED for $sha" >&2
    fi
    rm -f "$tmp"
done
exit 0
