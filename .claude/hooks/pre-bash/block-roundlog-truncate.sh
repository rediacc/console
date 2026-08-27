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
# cp with the log as DESTINATION, i.e. the LAST argument of that segment. `cp <log>
# /backup/` names the log as a SOURCE, which is a pure read, and blocking it contradicted
# this file's own "reads are untouched" guarantee two paragraphs up. Backing the log up is
# the single most useful thing a session can do with it, and this refused it.
# `${RL}` braced, not `$RL`: a `[` directly after a bare name reads as an array subscript
# to shellcheck (SC1087, an error not a warning), and here the bracket opens a character
# class in the regex rather than an index.
echo "$CMD" | grep -qE "(^|[[:space:];|&])cp[[:space:]]${SEG}${RL}[[:space:]]*($|[;|&])" && TRUNCATING=1
# mv and truncate stay position-independent, and NOT by oversight: `mv <log> elsewhere`
# reads as a source too, but it REMOVES the log from its path, so unlike cp it is
# destructive in exactly the way this guard exists to catch.
echo "$CMD" | grep -qE "(^|[[:space:];|&])(mv|truncate)[[:space:]]$SEG$RL" && TRUNCATING=1
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
# Two ways this was wrong, both found in review, both reproduced before fixing:
#
#   1. `-[^[:space:]]*a` is not an option test, it is a substring test. It matched
#      `tee --output-error=warn <log>`, because `--output-error=wa` fits "a dash, some
#      non-space, an a". That command TRUNCATES, and the guard waved it through as if it
#      had said -a.
#   2. The test was unscoped, searching the WHOLE command for any `tee -a`. So
#      `tee -a other.txt | tee <log>` passed on the strength of a decoy append to an
#      unrelated file, while the second tee truncated the log.
#
# Both are fixed by scoping to the tee invocation that actually targets the log, and by
# requiring a real option TOKEN: `-a`, a short bundle containing a, or `--append`. The
# surrounding space/end anchors are what stop `--output-error=warn` matching again.
TEE_SEG=$(echo "$CMD" | grep -oE "(^|[[:space:];|&])tee[[:space:]]$SEG$RL" | tail -1)
if [ -n "$TEE_SEG" ]; then
    echo "$TEE_SEG" | grep -qE "[[:space:]](--append|-[A-Za-z]*a[A-Za-z]*)([[:space:]]|$)" || TRUNCATING=1
fi
# An in-process write from python or node. NOT anchorable the way the shell verbs
# are: the 2026-08-19 incident was a heredoc where the path sat on a DIFFERENT
# LINE from the write call, so demanding both inside one shell segment would miss
# precisely the shape this hook exists for.
# NAMED RESIDUAL: a script that writes some OTHER file while merely mentioning a
# round-log path is still blocked here. That is the one over-block left standing,
# and it is deliberate: this is the exact shape that destroyed the appendix.
# THE PYTHON ARM MUST TEST THE TARGET, NOT JUST THE IDIOM.
#
# This used to be an unconditional `grep write_text|open(...,'w') && TRUNCATING=1`.
# Reaching here already means a round-log NAME appears somewhere in the command
# (the gate above), but a name is not a target: a heredoc editing an unrelated
# file whose CONTENT quotes a round-log path matched every time. Measured
# 2026-08-27, refusing an edit to a scratchpad state-body file that could not
# have touched a round log.
#
# So resolve the write target the way python actually spells one -- assigned to a
# name, or handed to open()/Path() -- and fire only when it IS a round log.
# FAIL CLOSED when no target can be resolved: that unidentifiable shape is
# precisely `p.write_text(s[:i] + new)`, which is what destroyed the round
# history on 2026-08-19 and is the reason this guard exists.
# shutil/os MOVE AND COPY COUNT AS WRITES. Measured 2026-08-27: shutil.copy and
# os.replace onto a round log both returned 0 from this guard, because the arm
# below triggered only on write_text and open(...,"w"). Each of them overwrites
# the file completely. The shell half has covered `cp` and `mv` onto a round log
# from the start; these are their python spelling, and their absence made the
# guard read as thorough while a one-line rename walked through it.
if echo "$CMD" | grep -qE 'write_text|open\([^)]*["'\'']w|shutil\.(copy|copyfile|copy2|move)|os\.(replace|rename)'; then
    # Candidates come from an assignment/open()/Path() position AND from every
    # quoted path inside a copy/move call. A copy names a source and a
    # destination and only the destination truncates, but telling them apart by
    # position across copy/copyfile/copy2/move/replace/rename is fragile, and
    # taking both is strictly safer: a call with a round log on either side is
    # not something to wave through. Two innocent paths still pass, which is
    # what stops this becoming a blanket refusal.
    PYTARGET=$(
        {
            echo "$CMD" |
                grep -oE "(=|open\(|Path\()[[:space:]]*[\"'][^\"']+\.md" |
                grep -oE "[A-Za-z0-9_./-]+\.md"
            echo "$CMD" |
                grep -oE "(shutil\.(copy|copyfile|copy2|move)|os\.(replace|rename))\([^)]*" |
                grep -oE "[A-Za-z0-9_./-]+\.md"
        } | sort -u
    )
    if [ -z "$PYTARGET" ]; then
        TRUNCATING=1
    elif echo "$PYTARGET" | grep -qE "$RL"; then
        TRUNCATING=1
    fi
fi

[ "$TRUNCATING" = "1" ] || exit 0

echo "❌ BLOCKED: this Bash command can replace a pr-babysit round log wholesale. That is how the round history was destroyed on 2026-08-19: a python heredoc doing p.write_text(s[:i] + new), which replaces from the STATUS heading to END OF FILE and takes the entire appendix with it, silently, on a file with no backup. To refresh STATUS use the verb, which replaces ONLY that block and prints the bytes it kept above and below:  .claude/hooks/stop/worklist.py --roundlog <branch> <<'EOF' ... EOF   To add to the history appendix, append instead ('>>' and 'tee -a' are deliberately allowed, since they cannot truncate). To amend the wave header, use the Edit tool -- targeted edits are allowed for the same reason." >&2
exit 2
