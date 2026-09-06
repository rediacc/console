#!/usr/bin/env bash
# Block a `git commit` that names no pathspec, because it commits the INDEX.
#
# WHY, and it is not the reason people expect. `git add -- <exact paths>` is
# correct and is NOT enough: a bare `git commit` afterwards writes whatever the
# index holds, including everything a CONCURRENT SESSION staged before you got
# there. The staging decision is scoped by intent and unscoped in execution.
#
# Found live, twice in one session, 2026-09-06:
#   - `git add -- <six named paths>` then `git commit` also landed fifteen
#     `git mv` renames a peer agent had staged, moving every policy allow/block
#     list into `.ci/policy/` WITHOUT any of their readers. HEAD then had the
#     files at their new paths while scripts/lib/policy-paths.ts still read
#     `const POLICY_DIR = '';` -- the exact half-landed state that seam exists
#     to refuse, reached from outside it.
#   - One hour later, and after the author had written the TRAPS.md entry about
#     it: `git add -- <three directories>` then `git commit` swept three other
#     agents' in-flight ports, landing 108 files where 33 were intended and
#     committing one ledger mid-record.
#
# WHY A HOOK. See block-blanket-git-add.sh's own header: this repo's record is
# that a written rule protects only the session that reads it and remembers it
# at the right second. The second instance above happened AFTER the rule was
# written down, by the session that wrote it.
#
# `-a` IS BLOCKED TOO, for the same reason and more directly: it stages every
# modified tracked file in a tree that routinely holds three other sessions'
# work.
#
# THE ESCAPE IS IN THE MESSAGE, deliberately:
#     git commit -F <message-file> -- <path> <path> ...
# Options come BEFORE the `--`, or git reads `-F` as a pathspec and refuses with
# "pathspec '-F' did not match any file(s)", which is a confusing way to learn
# the argument order.
#
# NOT BLOCKED: `--amend` (it rewrites a commit whose content is already chosen),
# and any commit that already carries a `--` pathspec.
source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"

INPUT=$(cat)
CMD=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null)
[[ -z "$CMD" ]] && exit 0

SCAN=$(hook_scan_target "$CMD")

# Command position: line start, or after ; & | ( $( or a backtick.
GIT_COMMIT='(^|[;&|(]|\$\(|`)[[:space:]]*git([[:space:]]+-[A-Za-z-]+([[:space:]]+[^ ;&|]+)?)*[[:space:]]+commit([[:space:]]|$)'

printf '%s' "$SCAN" | grep -qE "$GIT_COMMIT" || exit 0

# THROWAWAY FIXTURE REPOS ARE EXEMPT, and this was a defect in the guard's first
# hour rather than a concession. The shadow-differential recipe every port agent
# follows REQUIRES `git init` plus a sealing commit inside a disposable repo under
# the session scratchpad, because a ledger row records `HEAD^{tree}` and a dirty
# tree is refused. Blocking that would have stopped the wave this guard was
# written during. Measured: the guard refused `git init ... && git commit -qm seed`
# in a scratch directory five minutes after it landed.
#
# THE MARKERS ARE STRUCTURAL, not a name allowlist: a command that creates a
# repository, or that reaches into one under /tmp, is not committing to this
# checkout. The real checkout is never under /tmp.
#
# THE LIMIT, stated rather than hidden: a `cd` into /tmp followed by a `cd` back
# would slip through. This guard defends against the accident it was written for,
# which is a correctly-scoped `git add` followed by an unscoped commit in the
# working checkout; it is not an adversarial control, and pretending otherwise
# would be the "check that cannot fail" this repo keeps a trap file about.
if printf '%s' "$SCAN" | grep -qE '(^|[;&|(]|\$\(|`)[[:space:]]*git[[:space:]]+init([[:space:]]|$)'; then
    exit 0
fi
if printf '%s' "$SCAN" | grep -qE '(^|[;&|(]|\$\(|`)[[:space:]]*cd[[:space:]]+["'"'"']?/tmp/'; then
    exit 0
fi
if printf '%s' "$SCAN" | grep -qE 'git[[:space:]]+-C[[:space:]]+["'"'"']?/tmp/'; then
    exit 0
fi

# An amend is choosing nothing new, so it is not this guard's business.
printf '%s' "$SCAN" | grep -qE '(^|[[:space:]])--amend([[:space:]]|$)' && exit 0

# A `--` with a real pathspec after it is the shape this guard is asking for.
# `git commit --` with nothing after it is the bare form wearing the escape's
# clothes, exactly as in block-blanket-git-add.sh.
if printf '%s' "$SCAN" | grep -qE '(^|[[:space:]])--[[:space:]]+[^[:space:];&|<>]'; then
    exit 0
fi

echo '❌ BLOCKED: `git commit` with no pathspec commits the INDEX, not the paths you just added. This checkout is shared: a peer session'"'"'s staged work rides your commit. That has happened twice, and the second time was an hour after the trap was written down -- fifteen policy renames landed without their readers, then 108 files landed where 33 were intended. NAME WHAT YOU ARE COMMITTING: `git commit -F <message-file> -- <path> <path>`. Options go BEFORE the `--`, or git reads `-F` as a pathspec. `--amend` is not blocked. `-a` is: it stages every modified tracked file in a tree that holds other sessions'"'"' work.' >&2
exit 2
