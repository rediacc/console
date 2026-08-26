#!/usr/bin/env bash
# A feature branch is `MMDD-N`. No suffixes, no words, no decoration.
#
# WHY. `.claude/commands/pr-babysit.md` and `.claude/commands/pr-merge.md` both
# state the convention, and pr-merge's hand-back section warns that guessing a name
# produces stray refs the next `/pr-babysit` has to clean up. On 2026-08-26 a
# session created `0826-1-prerebase` in the console AND in a submodule, as
# safety copies before a rebase. Reasonable intent, wrong shape: the suffix
# makes the ref sort next to a wave branch while belonging to no wave, and
# nothing downstream -- not pr-babysit's branch listing, not the submodule
# same-name matching in branch-rebase.md's submodule step, not pr-merge's coordinated-PR
# lookup -- can tell the two apart.
#
# THE SUBMODULE POINT IS THE SHARP ONE. `/pr-merge` finds a submodule's PRs by
# matching the console branch name EXACTLY. A console branch carrying a suffix
# silently matches nothing, so a coordinated submodule PR is invisible to the
# merge path and gets left behind.
#
# ONLY CREATION IS CHECKED. `git branch -d`, `-r`, `--list`, `--show-current`
# and `--contains` read; they are none of this hook's business. Blocking a read
# would be the over-matching that gets a guard switched off.
#
# CITED BY HEADING, NOT LINE. Three of this file's original `:NNN` references
# rotted inside the same session that wrote them, because the files they point
# at were edited in the same working tree. block-blanket-git-add.sh adopted the
# heading convention for exactly this reason.
#
# `main` is allowed because it is not a feature branch. Nothing else is special
# cased: if a name is neither `main` nor `MMDD-N`, the convention does not
# describe it, and the operator is the one who decides to widen the convention.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
[ -z "$CMD" ] && exit 0

# A HEREDOC BODY IS DATA, NOT A COMMAND. This hook blocked its own commit
# message for saying so: the message described the slashed-name shape the guard
# refuses, and the guard read the description as the act. It then blocked the
# edit that would have fixed it, for the same reason -- the fix had to come
# through the Edit tool. That is the fifth mention-vs-execution false positive
# in one session, so this uses the SHARED stripper the rest of the pre-bash
# family already uses rather than inventing a fifth private one.
#
# Only heredoc BODIES are dropped, deliberately: hook_scan_target also strips
# quoted strings, and a branch name may legitimately be quoted, so using it
# would fail this open on `git branch "bad name"`.
source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"
CMD=$(printf '%s' "$CMD" | _hook_strip_heredocs)

# Cheap reject: no branch-creating verb anywhere.
printf '%s' "$CMD" | grep -qE 'git([[:space:]]+-[A-Za-z-]+([[:space:]]+[^ ;&|]+)?)*[[:space:]]+(branch|checkout|switch)([[:space:]]|$)' || exit 0

CANDIDATE=""
# -b/-B (checkout), -c/-C (switch): the new name is the next token.
#
# ANCHORED TO A COMMAND POSITION, and the anchor is not decoration. Without it
# the pattern matched a shell VARIABLE ASSIGNMENT whose value happened to hold
# the words -- `SLASH='git checkout -b some/name'` -- and refused a line that
# runs nothing. Requiring `git` after a command boundary is what makes this a
# guard on an act rather than on a vocabulary.
GIT_AT_CMD='(^|[;&|(]|\$\(|`)[[:space:]]*git([[:space:]]+-[A-Za-z-]+([[:space:]]+[^ ;&|]+)?)*[[:space:]]+'
NAME=$(printf '%s' "$CMD" |
    grep -oE "${GIT_AT_CMD}(checkout|switch)([[:space:]]+-[A-Za-z-]+)*[[:space:]]+-[bBcC][[:space:]]+[^[:space:];|&)]+" |
    grep -oE '[^[:space:]]+$' | head -1)
[ -n "$NAME" ] && CANDIDATE="$NAME"

# `git branch [-m|-M] ...`: the new name is the LAST positional, because the
# rename form is `-m <old> <new>` and the create form is `branch <new> [start]`.
# Handled separately so a rename INTO a legal name passes while a rename INTO a
# suffixed one does not -- which is exactly how this session fixed its own.
if [ -z "$CANDIDATE" ]; then
    BRANCH_ARGS=$(printf '%s' "$CMD" |
        grep -oE "${GIT_AT_CMD}branch[[:space:]]+[^;|&]*" |
        sed -E 's/.*[[:space:]]branch[[:space:]]+//' | head -1)
    # A read-only or delete invocation is not our business.
    if ! printf '%s' "$BRANCH_ARGS" | grep -qE '(^|[[:space:]])-(d|D|r|a|v|-list|-show-current|-contains|-merged|-no-merged|-delete|-remotes|-all|-verbose|-set-upstream-to|-unset-upstream|-edit-description)'; then
        read -ra TOKENS <<<"$BRANCH_ARGS"
        for tok in "${TOKENS[@]}"; do
            case "$tok" in
                -*) continue ;;
                *) CANDIDATE="$tok" ;;
            esac
        done
        # `git branch <new> <start-point>`: the START POINT is an existing ref,
        # not a name being created, so only the FIRST positional is judged --
        # unless this is a rename, where the new name is the SECOND.
        if ! printf '%s' "$BRANCH_ARGS" | grep -qE '(^|[[:space:]])-[mM]([[:space:]]|$)'; then
            for tok in "${TOKENS[@]}"; do
                case "$tok" in
                    -*) continue ;;
                    *) CANDIDATE="$tok"; break ;;
                esac
            done
        fi
    fi
fi

[ -z "$CANDIDATE" ] && exit 0
# Strip quotes the session happened to use.
CANDIDATE=$(printf '%s' "$CANDIDATE" | sed -E "s/^['\"]//; s/['\"]$//")

# `main` is not a feature branch. `MMDD-N` is the convention.
[ "$CANDIDATE" = "main" ] && exit 0
printf '%s' "$CANDIDATE" | grep -qE '^[0-9]{4}-[0-9]+$' && exit 0
# A SHA or a remote-tracking ref is a START POINT, not a name being created,
# so it is not this hook's call. NOTE the anchors: an earlier draft skipped any
# candidate containing a slash, which silently let `checkout -b feature/x`
# through -- the exact shape this hook exists to refuse. Caught by its own
# control, which is the argument for writing the controls first.
printf '%s' "$CANDIDATE" | grep -qE '^[0-9a-f]{7,40}$|^origin/|^refs/' && exit 0

cat >&2 <<MSG
BLOCKED: '${CANDIDATE}' is not a branch name this repo uses.

Feature branches are MMDD-N and carry NO suffix. pr-babysit.md and pr-merge.md
both say so, and pr-merge's hand-back section warns that invented names
leave stray refs for the next session to clean up.

A suffix is not cosmetic here. /pr-merge finds a submodule's coordinated PR by
matching the console branch name EXACTLY (branch-rebase.md's submodule step does
the same),
so a suffixed console branch matches no submodule branch and the submodule PR
is silently left out of the merge.

Pick MAX+1 for today. Compute MAX from PR HEADS, not from live remote branches:
a merged PR's branch is DELETED, so \`git branch -r\` cannot see the name it
consumed. That is exactly how 0826-1 got picked twice on 2026-08-26, the second
time after PR #576 had already merged it that morning.

  d=\$(date +%m%d)
  gh pr list --state all --limit 100 --json headRefName \\
    --jq '.[].headRefName' | grep "^\${d}-" | sed "s/^\${d}-//" | sort -n | tail -1

Then add one. If you need a throwaway safety ref before a rebase, take the next
MMDD-N rather than decorating an existing name -- or use a TAG, which carries no
branch convention at all:

  git tag prerebase-\$(date +%m%d) <branch>
MSG
exit 2
