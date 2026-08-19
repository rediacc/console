#!/usr/bin/env bash
# Deny TRUNCATING Bash writes to a pr-babysit round log. Appends and reads pass.
#
# WHY A SECOND GUARD. block-roundlog-write.sh (pre-edit) stops the Write tool,
# which is what an agent reaches for first. It cannot see Bash. Its neighbour
# block-agent-state-shape.sh names that residual honestly and leaves it open:
# "a Bash heredoc straight onto the path, which no PreToolUse hook can see".
#
# For STATE.md that residual is theoretical. For the round log it is the ACTUAL
# incident: on 2026-08-19 the appendix was destroyed by
#
#     python3 - <<'PY' ... p.write_text(s[:i] + new) ... PY
#
# run through Bash, by a session that had a perfectly good reason to be editing
# the file and no idea it was about to truncate it. A pre-edit-only guard would
# have watched that go past.
#
# WHAT IS DENIED, AND WHY NOT EVERYTHING. The failure is silent truncation, so
# the guard targets operations that can REPLACE the file wholesale:
#
#     >  redirection      sed -i      tee (without -a)      truncate
#     cp/mv onto it       dd of=      python write_text / open(...,'w')
#
# Appends are deliberately allowed: `>>` and `tee -a` cannot delete a history
# appendix, and appending to it is a normal, sanctioned thing to do. Reads are
# untouched. So is `worklist.py --roundlog` itself, which is the whole point of
# having somewhere to send people.
#
# FAILS OPEN. This matches on a path shape plus a write verb; anything it does
# not recognise runs. A guard that blocked on suspicion would be routed around,
# and being routed around is worse than a named residual.
#
# NAMED RESIDUAL, not pretended away: a write whose path is ASSEMBLED at runtime
# (a variable holding the filename, a shell glob that expands to it) is invisible
# here, exactly as it is to every other command-text guard in this directory.
# The verb's own success line is the backstop for that case: it reports the bytes
# kept above and below STATUS, so a session that used the verb can SEE the
# appendix survived, and a session that bypassed it has no such line to point at.
CMD=$(jq -r '.tool_input.command // empty' 2>/dev/null)

# The verb is the sanctioned path; never block it.
case "$CMD" in
    *--roundlog*) exit 0 ;;
esac

# A round-log path must appear at all. Briefings have their own contract and are
# not this hook's business.
echo "$CMD" | grep -qE 'pr-babysit-[A-Za-z0-9._-]+\.md' || exit 0
echo "$CMD" | grep -qE 'pr-babysit-[A-Za-z0-9._-]+-briefing\.md' && exit 0

# Appends first: `>>` and `tee -a` cannot truncate, so if the only write shape
# present is an append, let it through.
# EVERY shell verb below is ANCHORED TO THE LOG: the verb, then the path, with no
# `;` `&&` `||` or `|` between them, so the two are genuinely one command.
#
# THE UNANCHORED FORM WAS A REAL DEFECT, caught in review and then reproduced
# twice against this very hook within minutes. `truncate` matched this script's
# OWN filename, so `ls .../block-roundlog-trunc*.sh` next to a round-log read was
# blocked; and a bare `cp`/`mv` matched a copy of unrelated files that merely
# shared a command line with a round-log READ. A guard that blocks `cat <log>` is
# not strict, it is broken, and its own header argues that a guard which blocks
# legitimate work teaches people to route around it.
RL='pr-babysit-[A-Za-z0-9._-]+\.md'
SEG='[^;|&]*'
TRUNCATING=0
# `>` that is not `>>` and not `2>&1`-style fd plumbing, aimed at the log.
echo "$CMD" | grep -qE "[^>&2]>[[:space:]]*[^>|&[:space:]]*$RL" && TRUNCATING=1
# cp / mv / truncate naming the log as an argument of THAT command.
echo "$CMD" | grep -qE "(^|[[:space:];|&])(cp|mv|truncate)[[:space:]]$SEG$RL" && TRUNCATING=1
echo "$CMD" | grep -qE "(^|[[:space:];|&])dd[[:space:]]${SEG}of=$SEG$RL" && TRUNCATING=1
# sed -i on the log, with any flags before the -i.
echo "$CMD" | grep -qE "sed[[:space:]]+(-[^[:space:]]+[[:space:]]+)*-i$SEG$RL" && TRUNCATING=1
# tee onto the log WITHOUT -a.
#
# Written as an if with an explicit second test rather than
# `grep -q ... | grep -qv ...`, which is NOT the check it reads as: `-q`
# suppresses stdout, so the downstream grep always sees empty input and its exit
# status says nothing whatever about the first pattern. Measured here: the
# pipeline returns 0 on a match AND on a miss. It happened not to set the flag in
# practice, which is worse than failing loudly, because it made the line look
# tested when the controls were passing for an unrelated reason.
if echo "$CMD" | grep -qE "(^|[[:space:];|&])tee[[:space:]]$SEG$RL"; then
    echo "$CMD" | grep -qE "(^|[[:space:];|&])tee[[:space:]]+-[^[:space:]]*a" || TRUNCATING=1
fi
# An in-process write from python or node. NOT anchorable the way the shell verbs
# are: the 2026-08-19 incident was a heredoc where the path sat on a DIFFERENT
# LINE from the write call, so demanding both inside one shell segment would miss
# precisely the shape this hook exists for.
# NAMED RESIDUAL: a script that writes some OTHER file while merely mentioning a
# round-log path is still blocked here. That is the one over-block left standing,
# and it is deliberate: this is the exact shape that destroyed the appendix.
echo "$CMD" | grep -qE 'write_text|open\([^)]*["'\'']w' && TRUNCATING=1

[ "$TRUNCATING" = "1" ] || exit 0

echo "❌ BLOCKED: this Bash command can replace a pr-babysit round log wholesale. That is how the round history was destroyed on 2026-08-19: a python heredoc doing p.write_text(s[:i] + new), which replaces from the STATUS heading to END OF FILE and takes the entire appendix with it, silently, on a file with no backup. To refresh STATUS use the verb, which replaces ONLY that block and prints the bytes it kept above and below:  .claude/hooks/stop/worklist.py --roundlog <branch> <<'EOF' ... EOF   To add to the history appendix, append instead ('>>' and 'tee -a' are deliberately allowed, since they cannot truncate). To amend the wave header, use the Edit tool -- targeted edits are allowed for the same reason." >&2
exit 2
