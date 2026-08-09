#!/usr/bin/env bash
# Block a BLANKET `git add` -- `-A`/`--all` with no pathspec, a lone `.`, or `:/`.
#
# WHY. This checkout is routinely shared by several live sessions, so "stage
# everything" does not mean "stage my work", it means "stage whatever every
# other session happens to have uncommitted right now". The tree is the shared
# surface; the index is not a private scratchpad.
#
# Found live, twice, and the second one is why this exists as a HOOK rather
# than a paragraph:
#   - `.agent/TRAPS.md:146`: sweep cefa43ca7 sucked in another session's
#     check-solution-video-engine.ts, which then failed 273 of 273 on branch
#     0730-2 (run 30554973713, job 90913300683). The sweep looked clean; the
#     failure surfaced a full CI round later, on someone else's code.
#   - 2026-08-09: a peer's private/renet submodule pointer and three of its
#     deliberately-uncommitted gate scripts sat in the tree all afternoon
#     while an unrelated PR was being built around them. A single `git add -A`
#     would have shipped a submodule bump into a PR that never reviewed it.
#
# WHY A HOOK AND NOT A RULE. CLAUDE.md session default 1 and the memory
# feedback_shared_checkout_hygiene have both said "never blanket-add in a
# shared tree" for months. The repo's own record is that written rules do not
# hold: the 2026-08-04 wave logged nine instances of one documented trap, three
# authored by the person who had just written the entry about it. A rule
# protects only the session that reads it and remembers it at the right second.
#
# THE ESCAPE IS IN THE MESSAGE, deliberately. A session that genuinely wants
# everything under one directory says so with a pathspec:
#     git add -A -- packages/cli/src
# That is one edit away, it is reviewable, and it cannot reach a path its
# author did not name. Blocking without naming the escape is how a guard
# becomes something sessions route around instead of using.
#
# NO CROSS-TALK with block-worktree-add.sh: `git worktree add x` has `worktree`
# between `git` and `add`, so the pattern below cannot see it. Pinned by a case
# in test-hooks.sh, because two guards matching adjacent shapes is exactly where
# a regex change silently swallows the wrong one.
source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
[[ -z "$CMD" ]] && exit 0

SCAN=$(hook_scan_target "$CMD")

# Command position: line start, or after ; & | ( $( or a backtick. Flags
# between `git` and `add` (-C <path>, -c k=v) stay matched, since they change
# where the command runs, not what it stages.
GIT_ADD='(^|[;&|(]|\$\(|`)[[:space:]]*git([[:space:]]+-[A-Za-z-]+([[:space:]]+[^ ;&|]+)?)*[[:space:]]+add[[:space:]]+'

# What counts as "nothing followed it". End of line, another command, OR a
# REDIRECTION: `git add -A > /dev/null` and `git add -A 2>&1` stage the entire
# tree exactly like the bare form, and an earlier version of this guard let both
# through because `>` was not in the terminator set. Caught in review of PR #566
# and confirmed by running the guard: all three shapes exited 0.
END='[[:space:]]*($|[;&|<>]|[0-9]*>)'

# A trailing `--` with NO pathspec after it is also blanket. git treats
# `git add -A --` as no restriction at all, so the escape this guard advertises
# (name a pathspec) must actually contain one; an empty pathspec list is the
# bare form wearing the escape's clothes.
BARE_DDASH='([[:space:]]+--[[:space:]]*)?'

BLANKET_ALL="${GIT_ADD}(-A|--all)${BARE_DDASH}${END}"
BLANKET_DOT="${GIT_ADD}\\.${BARE_DDASH}${END}"
BLANKET_ROOT="${GIT_ADD}:/${BARE_DDASH}${END}"

for pat in "$BLANKET_ALL" "$BLANKET_DOT" "$BLANKET_ROOT"; do
    if printf '%s' "$SCAN" | grep -qE "$pat"; then
        echo '❌ BLOCKED: blanket `git add` stages every other live session'"'"'s uncommitted work, not just yours. This checkout is shared, and a sweep has already shipped a peer'"'"'s half-finished file into an unrelated PR once (it failed 273 of 273 a full CI round later, on code the author had never seen). NAME THE PATHSPEC instead -- `git add -A -- <dir>` and `git add <file>...` both pass this guard, are reviewable, and cannot reach a path you did not name. If you truly want the whole tree and know what is in it, say so explicitly with `git add -A -- .` and own that choice.' >&2
        exit 2
    fi
done
exit 0
