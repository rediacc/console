#!/usr/bin/env bash
# Deny WHOLE-FILE tool writes to a pr-babysit ROUND LOG. Targeted edits pass.
#
# WHY THIS EXISTS. The round log is three parts in a fixed order: an immutable
# wave header, a STATUS block overwritten in place every round, and the round
# history appended below it forever. Refreshing STATUS is therefore a SPLICE,
# and the obvious splice is wrong in a way that looks right:
#
#     text[:i] + new        # i = index of "## STATUS"
#
# That replaces from the STATUS heading to END OF FILE, taking the entire
# history appendix with it. On 2026-08-19 a heartbeat tick whose whole purpose
# was keeping the log current did exactly this, and there was no backup of that
# file anywhere. The loss was silent: the write succeeded, the new STATUS looked
# perfect, and nothing said the appendix had gone.
#
# `worklist.py --roundlog` cannot express that splice. It parses the document
# into (head, status, tail), replaces only the middle, and prints the byte count
# of what it kept on either side, so a truncation can never again pass for a
# routine update. It also stamps the time itself, which matters more than it
# sounds: STATUS's timestamp is the signal a watchdog reads to decide whether
# the loop is wedged, and a hand-typed stamp can be copied forward from the
# previous round without anything noticing.
#
# WHY ONLY WHOLE-FILE WRITES, AND NOT EVERY EDIT. This is the one place this
# guard deliberately differs from block-agent-state-shape.sh next door. STATE.md
# has MERGE semantics across concurrent sessions, so every direct write to it is
# unsafe and the CLI is its only writer. The round log has a single owner, and
# two of its three parts are meant to be written by hand: the history appendix
# is appended to forever, and the wave header takes dated addenda. Denying those
# would leave legitimate work with no path at all, which is how a guard teaches
# people to route around it.
#
# The failure being prevented is specifically SILENT TRUNCATION, and only a
# whole-file replacement can do that silently. A targeted Edit carries an exact
# old_string: it either matches what is there or it fails loudly, and it cannot
# quietly swallow a 5 KB appendix it never mentioned. So Write and NotebookEdit
# are denied, Edit and MultiEdit are allowed through.
#
# SCOPED TO ROUND LOGS, NOT BRIEFINGS. `pr-babysit-<branch>-briefing.md` is a
# different artifact with a different contract (immutable once the babysitter is
# running; superseded by a NEW file, never rewritten). The verb does not handle
# briefings, so they are left to their own rule rather than blocked here with
# nothing offered in return.
#
# FAILS OPEN by design, like its neighbour: anything this pattern does not
# recognise is allowed through rather than blocked on a guess.
IN=$(cat)
FILE=$(jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' <<<"$IN" 2>/dev/null)
TOOL=$(jq -r '.tool_name // empty' <<<"$IN" 2>/dev/null)

# Targeted edits cannot silently truncate; only whole-file writes can.
case "$TOOL" in
    Edit | MultiEdit) exit 0 ;;
esac
case "$FILE" in
    *-briefing.md) exit 0 ;;
esac
[[ "$FILE" =~ (^|/)reports/pr-babysit-[^/]+\.md$ ]] || exit 0

echo "❌ BLOCKED: a whole-file write to a pr-babysit round log. Its STATUS block is spliced in place, and the obvious splice (text[:i] + new) deletes the entire round history below it -- which is what happened on 2026-08-19, silently, to a file with no backup. To refresh STATUS use the verb, which replaces ONLY that block and reports the bytes it kept above and below:  .claude/hooks/stop/worklist.py --roundlog <branch> <<'EOF' ... EOF   The tool writes the '## STATUS (round N, <utc>)' heading itself: the round auto-increments, and the stamp is machine-written because a watchdog reads it to decide whether this loop is wedged. To append to the history or amend the wave header, use Edit -- targeted edits are deliberately allowed, because they cannot swallow an appendix they never named." >&2
exit 2
