#!/usr/bin/env bash
# Require a PR-TASK trailer naming a REAL epic, so a per-epic review finds its work.
#
# WHY. The review now runs once per epic, and it selects an epic's commits with
# `git log --grep='^PR-TASK: <id>'`. A commit with no trailer belongs to no epic,
# so it is reviewed by nobody, silently. That is the same shape as the flat
# review's licence to leave areas unreviewed, moved one level down to where
# nothing reports it at all.
#
# ANCHORED TO LINE START, deliberately. The sibling guard block-commit-meta.sh
# states the rule this follows in its own header: a guard whose only failure mode
# is refusing CORRECT input teaches people to reword honest messages until it
# stops complaining. A commit whose prose merely mentions PR-TASK is not tagged;
# only a real trailer line is.
#
# THE `-F` BLIND SPOT WAS WIDER THAN IT NEEDED TO BE, and it mattered: measured
# 2026-08-27, `git commit -F -` was exempted outright, and that is the form
# every message longer than one line uses. Thirty-six consecutive commits in one
# session went through this guard without it ever looking at them. They happened
# to carry trailers; nothing checked.
#
# Two of the three unreadable shapes were never unreadable:
#   -F -  with a heredoc  -> the BODY is in the command string, right there
#   -F <file>             -> the file is on disk, and readable
# Only a piped stdin or a command-substituted message is genuinely opaque, and
# that case still ALLOWS rather than refusing a commit it cannot judge.
#
# A TYPO IS WORSE THAN A MISSING TRAILER, which is why shape is no longer
# enough. `PR-TASK: f2757831` (one character off) looks tagged, routes to an
# epic that does not exist, and no review pass ever reads it. The id is checked
# against agent/pr/<branch>.md -- the COMMITTED snapshot, not the worklist
# sidecar, because the sidecar lives in TMPDIR and was found empty on this very
# branch while 35 commits carried a live id.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)
[ -z "$CMD" ] && exit 0

source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"
SCAN=$(hook_scan_target "$CMD")

# Is this a commit at all? Command position, so prose about committing is not.
printf '%s' "$SCAN" | grep -qE '(^|[;&|(]|\$\(|`)[[:space:]]*git([[:space:]]+-[A-Za-z-]+([[:space:]]+[^ ;&|]+)?)*[[:space:]]+commit([[:space:]]|$)' || exit 0

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"

# THIS REPO IS NOT THE ONLY ONE ON THE MACHINE. A command that `cd`s into an
# independent sibling checkout (e.g. private/growth, private/generative -- real
# repos with their own origin, not a console submodule) and commits there was
# still judged against CLAUDE_PROJECT_DIR/agent/pr/<console-branch>.md: wrong
# branch name (this repo's HEAD, not the target's), wrong epic snapshot (one
# that cannot possibly name an epic for a repo it has never heard of), so every
# such commit was refused for a trailer no epic file could ever supply. Detect
# a `cd`/`git -C` into another repo anywhere on the line -- a cd applies to
# every later segment, so this is deliberately line-wide, matching
# hook_target_repo's convention in lib/command-scan.sh -- and if the git root
# THAT resolves to is a real repo distinct from this one, this guard has
# nothing to check: that repo's commits are not this repo's epics' business.
# THE RESOLUTION MOVED TO lib/command-scan.sh when a third guard needed it. Two siblings
# had the same defect -- block-unverified-push.sh refused a foreign repo's push against
# THIS tree's gate stamp (reproduced live), and warn-remote-drift.sh has the same shape
# latently -- so the walk this file pioneered is now shared rather than copied twice more.
if [ -n "$(hook_target_root "$SCAN" "$ROOT")" ]; then
    exit 0
fi

# ---- what message text can we actually see? --------------------------------
# Everything readable is concatenated; the trailer only has to appear once.
MSG=""

# 1. -m / --message: the raw command carries it.
printf '%s' "$CMD" | grep -qE '\-m([[:space:]]|=)|--message([[:space:]]|=)' && MSG="$CMD"

# 2. -F - with a heredoc: the body is in the command string. hook_scan_target
#    STRIPS heredocs (they are data, for its purposes), so this reads $CMD.
# The `<<` is required, not incidental: `-F -` ALONE means the message arrives
# on a pipe this hook cannot see, and treating the command text as the message
# then reads a trailer-less command line as a trailer-less COMMIT. Measured:
# `cat msg.txt | git commit -F -` was refused for a message it never saw.
if printf '%s' "$CMD" | grep -qE '(-F|--file)([[:space:]]|=)[[:space:]]*-([[:space:]]|$)' &&
    printf '%s' "$CMD" | grep -q '<<'; then
    MSG="$MSG
$CMD"
fi

# 3. -F <file> / --file=<file>: read it off disk.
while IFS= read -r f; do
    [ -n "$f" ] || continue
    [ "$f" = "-" ] && continue
    for cand in "$f" "$ROOT/$f"; do
        if [ -f "$cand" ]; then
            MSG="$MSG
$(cat "$cand" 2>/dev/null)"
            break
        fi
    done
done < <(printf '%s' "$CMD" | grep -oE '(-F|--file)([[:space:]]+|=)[^[:space:];|&]+' |
    sed -E 's/^(-F|--file)([[:space:]]+|=)//')

# Nothing readable -- a piped stdin or a command substitution. Allow, as the
# header says: this hook catches the common case cheaply; CI is the enforcement.
[ -z "${MSG//[[:space:]]/}" ] && exit 0

# ---- the epics that actually exist -----------------------------------------
# `rev-parse --abbrev-ref HEAD` PRINTS THE STRING "HEAD" WHEN DETACHED, and a
# detached HEAD is not exotic: it is every pull_request checkout and every
# halted rebase. The snapshot path then became agent/pr/HEAD.md, which does not
# exist, so KNOWN was empty and a TYPO'D id -- the case this guard was extended
# for -- sailed through. Measured 2026-08-27: the suite case asserting the typo
# is refused returned 0 in CI while passing on every developer machine.
#
# `git branch --show-current` prints EMPTY when detached rather than lying, and
# the CI environment names the branch outright. Same resolution order as
# scripts/check-pr-task-trailers.ts, so the gate and the guard agree about which
# branch they are judging.
BRANCH="${PR_HEAD_REF:-${GITHUB_HEAD_REF:-$(git -C "${ROOT:-.}" branch --show-current 2>/dev/null)}}"
# A HALTED REBASE IS THE DETACHED CASE THAT ACTUALLY MATTERS HERE. This repo
# has a rebase executor, so committing mid-rebase is a normal thing to do, and
# that is exactly when losing id validation would hurt. git remembers the
# branch it is rebasing in rebase-merge/head-name (rebase-apply/head-name for
# the am backend), so ask instead of guessing.
if [ -z "$BRANCH" ]; then
    for hn in rebase-merge/head-name rebase-apply/head-name; do
        hp=$(git -C "${ROOT:-.}" rev-parse --git-path "$hn" 2>/dev/null)
        if [ -n "$hp" ] && [ -f "$hp" ]; then
            BRANCH=$(sed -e 's#^refs/heads/##' "$hp" 2>/dev/null)
            break
        fi
    done
fi
# Still empty means a plain detached checkout, where there genuinely IS no
# branch and therefore no published epic set. The guard allows, as it does
# whenever it has nothing to judge against.
SNAP="$ROOT/agent/pr/${BRANCH//\//-}.md"
KNOWN=""
[ -f "$SNAP" ] && KNOWN=$(grep -oE '^`?PR-TASK:[[:space:]]*[0-9a-f]{6,32}`?$' "$SNAP" 2>/dev/null |
    grep -oE '[0-9a-f]{6,32}')

FOUND=$(printf '%s' "$MSG" | grep -oP '(^|\\n|\n)[[:space:]]*PR-TASK:[[:space:]]*\K[0-9a-f]{6,32}' | head -1)

epic_menu() {
    if [ -n "$KNOWN" ]; then
        echo "" >&2
        echo "Epics declared for this branch (agent/pr/${BRANCH//\//-}.md):" >&2
        while IFS= read -r id; do
            [ -n "$id" ] || continue
            title=$(grep -B4 -F "PR-TASK: $id" "$SNAP" 2>/dev/null | grep -E '^### ' | tail -1 | sed 's/^### //')
            printf '    %s  %s\n' "$id" "${title:-(untitled)}" >&2
        done <<<"$KNOWN"
    else
        echo "" >&2
        echo "No snapshot at agent/pr/${BRANCH//\//-}.md, so there is no epic to name yet:" >&2
        echo "    .claude/hooks/stop/worklist.py --epic <me> new \"<title>\"" >&2
        echo "    .claude/hooks/stop/worklist.py --publish <me> ${BRANCH:-<branch>}" >&2
    fi
}

if [ -z "$FOUND" ]; then
    cat >&2 <<'MSG'
BLOCKED: this commit carries no PR-TASK trailer.

The review runs once per epic and selects an epic's commits with
`git log --grep='^PR-TASK: <id>'`. An untagged commit belongs to no epic, so it
is reviewed by nobody and nothing reports the gap.

Add a trailer line naming the epic this change belongs to:

  git commit -m "feat(x): what changed

  PR-TASK: <epic-id>"
MSG
    epic_menu
    exit 2
fi

# A trailer whose id names no epic is WORSE than no trailer: it looks tagged.
# Only judge when a snapshot exists -- with none, there is no set to judge
# against, and refusing would block the very first commit of a new branch.
if [ -n "$KNOWN" ] && ! grep -qx -- "$FOUND" <<<"$KNOWN"; then
    cat >&2 <<MSG
BLOCKED: PR-TASK id '$FOUND' names no epic on this branch.

This is worse than a missing trailer, which is why it is refused. The commit
LOOKS tagged, so nothing downstream complains: \`git log --grep\` finds no epic
by that id, the per-epic review never selects the commit, and the gap is
reported by nobody. A single mistyped character does it.
MSG
    epic_menu
    exit 2
fi
exit 0
