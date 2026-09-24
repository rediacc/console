"""Deny TRUNCATING Bash writes to a pr-babysit round log. Appends and reads pass.

WHY A SECOND GUARD. block-roundlog-write.sh (pre-edit) stops the Write tool, which is what an agent reaches for first. It cannot see Bash. Its neighbour block-agent-state-shape.sh names that residual honestly and leaves it open: "a Bash heredoc straight onto the path, which no PreToolUse hook can see".

For STATE.md that residual is theoretical. For the round log it is the ACTUAL incident: on 2026-08-19 the appendix was destroyed by

    python3 - <<'PY' ... p.write_text(s[:i] + new) ... PY

run through Bash, by a session that had a perfectly good reason to be editing the file and no idea it was about to truncate it. A pre-edit-only guard would have watched that go past.

WHAT IS DENIED, AND WHY NOT EVERYTHING. The failure is silent truncation, so the guard targets operations that can REPLACE the file wholesale:

    >  redirection      sed -i      tee (without -a)      truncate
    cp/mv onto it       dd of=      python write_text / open(...,'w')

Appends are deliberately allowed: `>>` and `tee -a` cannot delete a history appendix, and appending to it is a normal, sanctioned thing to do. Reads are untouched. So is `worklist.py --roundlog` itself, which is the whole point of having somewhere to send people.

FAILS OPEN. This matches on a path shape plus a write verb; anything it does not recognise runs. A guard that blocked on suspicion would be routed around, and being routed around is worse than a named residual.

NAMED RESIDUAL, not pretended away: a write whose path is ASSEMBLED at runtime (a variable holding the filename, a shell glob that expands to it) is invisible here, exactly as it is to every other command-text guard in this directory. The verb's own success line is the backstop for that case: it reports the bytes kept above and below STATUS, so a session that used the verb can SEE
the appendix survived, and a session that bypassed it has no such line to point at.

=============================================================================
PORT NOTES, and the bash's own two are worth keeping because they are about what a naive reader would write instead.
=============================================================================

`grep -q ... | grep -qv ...` IS NOT THE CHECK IT READS AS, and the tee arm used to be written that way: `-q` suppresses stdout, so the downstream grep always sees empty input and its exit status says nothing whatever about the first pattern. Measured in the bash: the pipeline returns 0 on a match AND on a miss. It happened not to set the flag in practice, which is worse than
failing loudly, because it made the line look tested when the controls were passing for an unrelated reason. In Python the two tests are simply two calls, so the trap cannot recur; the record of it is here because the NEXT person to "simplify" this arm is the reader this paragraph is for.

`${RL}` BRACED, NOT `$RL`, in the bash: a `[` directly after a bare name reads
as an array subscript to shellcheck (SC1087, an error not a warning), and here the bracket opens a character class in the regex rather than an index. Python has no such ambiguity, which is why the braces are gone and the reason is not.
"""

from rediacc_hooks import hookio

CHAIN = "pre-bash"
TWIN = "pre-bash/block-roundlog-truncate.sh"
ORDER = 31

# The `--roundlog` carve-out. The verb IS the sanctioned path, and without this line the guard refuses the one command it spends its message telling people to use, which is the shape its own header calls "a guard that gets routed around".
DEFECT = ('if hookio.case_glob(cmd, "*worklist.py*--roundlog*"):', "if False:")

# A round-log path. Anchored into every verb pattern below rather than tested separately, which is the 2026-08 finding this file records twice.
RL = r"pr-babysit-[A-Za-z0-9._-]+\.md"
SEG = r"[^;|&]*"
BRIEFING = r"pr-babysit-[A-Za-z0-9._-]+-briefing\.md"

MESSAGE = (
    "❌ BLOCKED: this Bash command can replace a pr-babysit round log wholesale. That is "
    "how the round history was destroyed on 2026-08-19: a python heredoc doing "
    "p.write_text(s[:i] + new), which replaces from the STATUS heading to END OF FILE and "
    "takes the entire appendix with it, silently, on a file with no backup. To refresh "
    "STATUS use the verb, which replaces ONLY that block and prints the bytes it kept "
    "above and below:  .claude/hooks/stop/worklist.py --roundlog <branch> <<'EOF' ... EOF   "
    "To add to the history appendix, append instead ('>>' and 'tee -a' are deliberately "
    "allowed, since they cannot truncate). To amend the wave header, use the Edit tool -- "
    "targeted edits are allowed for the same reason."
)

EDGE_CASES = [
    ("the sanctioned verb", ".claude/hooks/stop/worklist.py --roundlog 0831-1"),
    # THE CASE THAT FOUND THE BYPASS, kept with its verdict inverted. It used to be labelled "the carve-out is a substring match, so this truncation passes" and it DID pass, on both sides, because `*--roundlog*` matched the string anywhere on the line rather than the verb at a command position. The twin was narrowed on 2026-09-06 and this port followed it a day later; the case
    # stays because it is the only one in this corpus that can tell the narrow carve-out from the wide one.
    (
        "a refresh and an archive on one line",
        ".claude/hooks/stop/worklist.py --roundlog 0831-1; mv agent/pr-babysit-0831-1.md /tmp/bak.md",
    ),
    (
        "merely NAMING the flag in a payload no longer buys the exemption",
        'echo "see --roundlog" > agent/pr-babysit-0831-1.md',
    ),
    ("a briefing has its own contract", "cat > agent/pr-babysit-0831-1-briefing.md"),
    # Appends cannot truncate, so they pass.
    ("append redirection", "echo x >> agent/pr-babysit-0831-1.md"),
    ("tee -a", "echo x | tee -a agent/pr-babysit-0831-1.md"),
    ("tee --append", "echo x | tee --append agent/pr-babysit-0831-1.md"),
    # The two shapes the tee arm was fixed for, both reproduced in review.
    (
        "tee --output-error=warn TRUNCATES",
        "echo x | tee --output-error=warn agent/pr-babysit-0831-1.md",
    ),
    (
        "a decoy append to another file",
        "echo x | tee -a other.txt | tee agent/pr-babysit-0831-1.md",
    ),
    # Truncating shell verbs.
    ("truncating redirection", "echo x > agent/pr-babysit-0831-1.md"),
    ("sed -i", "sed -i 's/a/b/' agent/pr-babysit-0831-1.md"),
    ("dd of=", "dd if=/dev/null of=agent/pr-babysit-0831-1.md"),
    ("mv the log away", "mv agent/pr-babysit-0831-1.md /tmp/"),
    ("cp ONTO the log", "cp /tmp/x agent/pr-babysit-0831-1.md"),
    # The cp finding: the log as a SOURCE is a pure read, and backing it up is the single most useful thing a session can do with it.
    ("cp the log AWAY is a read", "cp agent/pr-babysit-0831-1.md /backup/"),
    ("reading the log", "cat agent/pr-babysit-0831-1.md"),
    # The unanchored-verb defect, reproduced twice against this very hook.
    (
        "listing this guard's own filename",
        "ls .claude/hooks/pre-bash/block-roundlog-trunc*.sh; cat agent/pr-babysit-0831-1.md",
    ),
    # The python arm.
    (
        "the 2026-08-19 shape: an unresolvable write target",
        "python3 - <<'PY'\np = open('agent/pr-babysit-0831-1.md')\np.write_text(s[:i] + new)\nPY",
    ),
    (
        "a resolvable write to another file",
        "python3 -c \"open('other.md','w').write(x)  # see agent/pr-babysit-0831-1.md\"",
    ),
    ("shutil.copy onto the log", "python3 -c \"shutil.copy('a.md','agent/pr-babysit-0831-1.md')\""),
    ("os.replace onto the log", "python3 -c \"os.replace('a.md','agent/pr-babysit-0831-1.md')\""),
]


def run(ev):
    cmd = ev.field("tool_input", "command")

    # The verb is the sanctioned path; never block it.
    #
    # NARROWED 2026-09-06 TO FOLLOW THE TWIN, which was itself narrowed that day
    # from `*--roundlog*` because a whole-command substring match is a bypass
    # rather than an exemption. The twin's own measurement:
    #
    # echo "see --roundlog" > agent/pr-babysit-0831-1.md -> ALLOWED echo hi > agent/pr-babysit-0831-1.md -> BLOCKED
    #
    # Both truncate the same file; the first differs only by naming the flag inside a string it is writing, which is the easiest thing in the world to do by accident when the payload is prose ABOUT the round-log workflow. The exemption now requires the flag to be an ARGUMENT TO worklist.py, in that order, which is what actually makes a command the sanctioned path.
    #
    # THIS PORT LAGGED THE TWIN BY A DAY and the differential is what caught it, not review: the old wide carve-out was documented here as deliberate ("the port's job is to agree with its twin"), which was true when written and false the moment the twin moved.
    if hookio.case_glob(cmd, "*worklist.py*--roundlog*"):
        return hookio.ALLOW

    # A round-log path must appear at all. Briefings have their own contract and are not this hook's business.
    if not hookio.grep_q_line(RL, cmd):
        return hookio.ALLOW
    if hookio.grep_q_line(BRIEFING, cmd):
        return hookio.ALLOW

    # Appends first: `>>` and `tee -a` cannot truncate, so if the only write shape present is an append, let it through. EVERY shell verb below is ANCHORED TO THE LOG: the verb, then the path, with no `;` `&&` `||` or `|` between them, so the two are genuinely one command.
    #
    # THE UNANCHORED FORM WAS A REAL DEFECT, caught in review and then reproduced twice against this very hook within minutes. `truncate` matched this script's OWN filename, so `ls .../block-roundlog-trunc*.sh` next to a round-log read was blocked; and a bare `cp`/`mv` matched a copy of unrelated files that merely shared a command line with a round-log READ. A guard that blocks
    # `cat <log>` is not strict, it is broken, and its own header argues that a guard which blocks legitimate work teaches people to route around it.
    truncating = False

    # `>` that is not `>>` and not `2>&1`-style fd plumbing, aimed at the log.
    if hookio.grep_q_line(hookio.rx(r"[^>&2]>[{B}]*[^>|&{B}]*") + RL, cmd):
        truncating = True
    # cp with the log as DESTINATION, i.e. the LAST argument of that segment. `cp <log> /backup/` names the log as a SOURCE, which is a pure read, and blocking it contradicted this file's own "reads are untouched" guarantee two paragraphs up. Backing the log up is the single most useful thing a session can do with it, and this refused it.
    if hookio.grep_q_line(
        hookio.rx(r"(^|[{B};|&])cp[{B}]") + SEG + RL + hookio.rx(r"[{B}]*($|[;|&])"),
        cmd,
    ):
        truncating = True
    # mv and truncate stay position-independent, and NOT by oversight: `mv <log> elsewhere` reads as a source too, but it REMOVES the log from its path, so unlike cp it is destructive in exactly the way this guard exists to catch.
    if hookio.grep_q_line(hookio.rx(r"(^|[{B};|&])(mv|truncate)[{B}]") + SEG + RL, cmd):
        truncating = True
    if hookio.grep_q_line(hookio.rx(r"(^|[{B};|&])dd[{B}]") + SEG + r"of=" + SEG + RL, cmd):
        truncating = True
    # sed -i on the log, with any flags before the -i.
    if hookio.grep_q_line(
        hookio.rx(r"sed[{B}]+(-[^{B}]+[{B}]+)*-i") + SEG + RL,
        cmd,
    ):
        truncating = True
    # tee onto the log WITHOUT -a. See the module docstring for the two ways this
    # was wrong: `-[^[:space:]]*a` matched `--output-error=warn`, and an unscoped
    # test passed on a decoy append to an unrelated file.
    tee_matches = hookio.grep_o(
        hookio.rx(r"(^|[{B};|&])tee[{B}]") + SEG + RL,
        hookio._here_string(cmd),
    )
    if tee_matches:
        tee_seg = tee_matches[-1]
        if not hookio.grep_q_line(
            hookio.rx(r"[{B}](--append|-[A-Za-z]*a[A-Za-z]*)([{B}]|$)"),
            tee_seg,
        ):
            truncating = True

    # An in-process write from python or node. NOT anchorable the way the shell verbs are: the 2026-08-19 incident was a heredoc where the path sat on a DIFFERENT LINE from the write call, so demanding both inside one shell segment would miss precisely the shape this hook exists for. NAMED RESIDUAL: a script that writes some OTHER file while merely mentioning a round-log path is
    # still blocked here. That is the one over-block left standing, and it is deliberate: this is the exact shape that destroyed the appendix.
    #
    # THE PYTHON ARM MUST TEST THE TARGET, NOT JUST THE IDIOM.
    #
    # This used to be an unconditional `grep write_text|open(...,'w') && TRUNCATING=1`.
    # Reaching here already means a round-log NAME appears somewhere in the command (the gate above), but a name is not a target: a heredoc editing an unrelated file whose CONTENT quotes a round-log path matched every time. Measured 2026-08-27, refusing an edit to a scratchpad state-body file that could not have touched a round log.
    #
    # So resolve the write target the way python actually spells one -- assigned to a name, or handed to open()/Path() -- and fire only when it IS a round log. FAIL CLOSED when no target can be resolved: that unidentifiable shape is precisely `p.write_text(s[:i] + new)`, which is what destroyed the round history on 2026-08-19 and is the reason this guard exists. shutil/os MOVE AND
    # COPY COUNT AS WRITES. Measured 2026-08-27: shutil.copy and os.replace onto a round log both returned 0 from this guard, because the arm below triggered only on write_text and open(...,"w"). Each of them overwrites the file completely. The shell half has covered `cp` and `mv` onto a round log
    # from the start; these are their python spelling, and their absence made the
    # guard read as thorough while a one-line rename walked through it.
    if hookio.grep_q_line(
        r"write_text|open\([^)]*[\"']w|shutil\.(copy|copyfile|copy2|move)|os\.(replace|rename)",
        cmd,
    ):
        # Candidates come from an assignment/open()/Path() position AND from every quoted path inside a copy/move call. A copy names a source and a destination and only the destination truncates, but telling them apart by position across copy/copyfile/copy2/move/replace/rename is fragile, and taking both is strictly safer: a call with a round log on either side is not something to
        # wave through. Two innocent paths still pass, which is what stops this becoming a blanket refusal.
        candidates = []
        for match in hookio.grep_o(
            r"(=|open\(|Path\()[" + hookio.BLANK + r"]*[\"'][^\"']+\.md", hookio._here_string(cmd)
        ):
            candidates.extend(hookio.grep_o(r"[A-Za-z0-9_./-]+\.md", match))
        for match in hookio.grep_o(
            r"(shutil\.(copy|copyfile|copy2|move)|os\.(replace|rename))\([^)]*",
            hookio._here_string(cmd),
        ):
            candidates.extend(hookio.grep_o(r"[A-Za-z0-9_./-]+\.md", match))
        # `| sort -u`: sorted AND deduplicated, then joined by newlines, and the command substitution around it drops the trailing newline.
        pytarget = hookio._command_substitution(hookio._grep_out(sorted(set(candidates))))
        if pytarget == "" or hookio.grep_q_line(RL, pytarget):
            truncating = True

    if not truncating:
        return hookio.ALLOW

    ev.warn(MESSAGE)
    return hookio.DENY
