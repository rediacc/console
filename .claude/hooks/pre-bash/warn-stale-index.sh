#!/usr/bin/env bash
# WARN when a commit is about to capture a STALE staged version of a file.
#
# `git commit` commits THE INDEX, not the working tree. Stage a path, edit it
# afterwards, and the commit takes the version from `git add` time while the
# message you just wrote describes what is on disk. Nothing in git says so: the
# commit succeeds, the file list looks right, and the diff is quietly one
# revision behind.
#
# THIS COST TWO REAL DEFECTS IN A SINGLE SESSION (2026-08-28):
#
#   1. `git commit -F <file>` after `git add <paths>` swept in two files a PEER
#      session had staged, because -F commits the whole INDEX and not the paths
#      named on the preceding `git add`. They landed under someone else's
#      commit message.
#   2. worklist_messages.py was staged, THEN edited (ten DEFAULT placeholders
#      reworded), then committed. The commit message claimed the rewording; the
#      commit did not contain it. Caught only by grepping the commit afterwards.
#
# WHY WARN AND NOT BLOCK. Staging a deliberately partial version is legitimate
# (`git add -p` exists). The failure here is not that it is possible, it is that
# it is SILENT -- so the fix is to say it out loud, not to forbid it. A block
# would be wrong on a real workflow; a warning is right on every case.
#
# ROUTED THROUGH lib/command-scan.sh so prose quoting `git commit` is not
# matched -- a worklist note or a doc mentioning the command is not a commit.
CMD=$(jq -r '.tool_input.command' 2>/dev/null)

source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"
SCAN=$(hook_scan_target "$CMD")

# COMMAND POSITION, not mere mention. The first draft of this guard matched
# `git commit` after ANY whitespace, so `echo do not run git commit here` warned
# -- prose read as a command. That is the same mention-vs-target defect fixed in
# block-bash-write-to-running-script.sh and block-roundlog-truncate.sh on
# 2026-08-28, reintroduced here within the hour, which is why it is anchored
# rather than remembered. hook_scan_target strips QUOTED spans and extracts
# `sh -c` payloads; unquoted prose survives it, so the anchor is what separates
# a command from a sentence.
if ! printf '%s' "$SCAN" | grep -qE '(^|[;&|(]|&&|\|\|)[[:space:]]*git[[:space:]]+commit'; then
    exit 0
fi

# `git commit <pathspec>` and `-a` both take the WORKING TREE for those paths,
# so the staleness this guard is about cannot arise. Only the index-only forms
# are at risk.
if printf '%s' "$SCAN" | grep -qE 'git +commit[^|;&]*(-a[[:space:]]|--all\b)'; then
    exit 0
fi

# An unreadable probe is never a pass, but this is an ADVISORY: it must never
# fail a command because git was unavailable. Stay silent instead.
staged=$(git diff --cached --name-only 2>/dev/null) || exit 0
unstaged=$(git diff --name-only 2>/dev/null) || exit 0
[ -n "$staged" ] || exit 0
[ -n "$unstaged" ] || exit 0

stale=$(comm -12 <(printf '%s\n' "$staged" | sort -u) <(printf '%s\n' "$unstaged" | sort -u))
[ -n "$stale" ] || exit 0

n=$(printf '%s\n' "$stale" | grep -c .)
echo "⚠️  STALE INDEX: $n path(s) were staged and then EDITED. This commit takes the STAGED version, not what is on disk:" >&2
printf '%s\n' "$stale" | sed 's/^/      /' >&2
echo "   If the message describes the edits, re-stage first: git add -- <those paths>" >&2
echo "   (Verify afterwards against the COMMIT, not the tree: git show <sha>:<path>)" >&2
exit 0
