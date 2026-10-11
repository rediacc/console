"""Deny TRUNCATING Bash writes to a pr-babysit round log. Appends and reads pass.

WHY A SECOND GUARD. block-roundlog-write.sh (pre-edit) stops the Write tool, which is what an agent reaches for first. It cannot see Bash. Its neighbour block-agent-state-shape.sh names that residual honestly and leaves it open: "a Bash heredoc straight onto the path, which no PreToolUse hook can see".

For STATE.md that residual is theoretical. For the round log it is the ACTUAL incident: on 2026-08-19 the appendix was destroyed by

    python3 - <<'PY' ... p.write_text(s[:i] + new) ... PY

run through Bash, by a session that had a perfectly good reason to be editing the file and no idea it was about to truncate it. A pre-edit-only guard would have watched that go past.

WHAT IS DENIED, AND WHY NOT EVERYTHING. The failure is silent truncation, so the guard targets operations that can REPLACE the file wholesale:

    >  redirection      sed -i      tee (without -a)      truncate
    cp/mv onto it       dd of=      python write_text / open(...,'w')

Appends are deliberately allowed: `>>` and `tee -a` cannot delete a history appendix, and appending to it is a normal, sanctioned thing to do. Reads are untouched. So is `worklist.py --roundlog` itself, which is the whole point of having somewhere to send people.

JUDGED ON WHAT RUNS, NOT ON THE TEXT (worklist #0c331972). Every verb arm used to be a regex over the raw command, anchored to `(^|[;|&])`, so a separator or a `|` INSIDE a quoted sentence was a command position: `echo 'echo x | tee --output-error=warn agent/pr-babysit-0831-1.md'` was refused as a truncation. The arms now read the shell's own walk: the redirects bash performs with their operator (`>` truncates, `>>` appends), the verbs it runs (`tee`, `cp`, `mv`, `truncate`, `dd`, `sed -i`, each read off its argv, behind `sudo`, `xargs`, `sh -c` or `find -exec`), and the program texts it hands an interpreter (`block_worktree_add.interpreter_programs`). The `--roundlog` carve-out is gone with the text matching: the verb is a `worklist.py` run that writes nothing the walk can see, so it passes on its own, and the whole-line glob that exempted it also exempted `worklist.py --roundlog x; mv <log> /tmp/` (rc 0 at HEAD 306285231), a truncation riding on the verb's name.

FAILS OPEN. This matches on a path shape plus a write verb; anything it does not recognise runs. A guard that blocked on suspicion would be routed around, and being routed around is worse than a named residual.

NAMED RESIDUAL, not pretended away: a write whose path is ASSEMBLED at runtime is partly invisible here. A verb's operand set by an earlier statement of the same command (`F=<log>; mv $F /tmp/`) is read as bash expands it; a REDIRECT onto such a variable (`> $F`), a value from the environment, and a shell glob that expands to the log are not, because the walk keeps a redirect target unexpanded. The verb's own success line is the backstop for that case: it reports the bytes kept above and below STATUS, so a session that used the verb can SEE
the appendix survived, and a session that bypassed it has no such line to point at.

=============================================================================
PORT NOTES, and the bash's own two are worth keeping because they are about what a naive reader would write instead.
=============================================================================

`grep -q ... | grep -qv ...` IS NOT THE CHECK IT READS AS, and the tee arm used to be written that way: `-q` suppresses stdout, so the downstream grep always sees empty input and its exit status says nothing whatever about the first pattern. Measured in the bash: the pipeline returns 0 on a match AND on a miss. It happened not to set the flag in practice, which is worse than
failing loudly, because it made the line look tested when the controls were passing for an unrelated reason. In Python the two tests are simply two calls, so the trap cannot recur; the record of it is here because the NEXT person to "simplify" this arm is the reader this paragraph is for.

`${RL}` BRACED, NOT `$RL`, in the bash: a `[` directly after a bare name reads
as an array subscript to shellcheck (SC1087, an error not a warning), and here the bracket opens a character class in the regex rather than an index. Python has no such ambiguity, which is why the braces are gone and the reason is not.
"""

import os
import re

from rediacc_hooks import hookio, shellscan
from rediacc_hooks.guards import block_worktree_add as WT

CHAIN = "pre-bash"
ORDER = 31

# THE APPEND EXEMPTION. `>>` cannot truncate, and appending to the history is the sanctioned way to add to it; planting `>>` among the truncating operators refuses every append, which is the over-block the module docstring says gets a guard routed around.
DEFECT = (
    'TRUNCATING_OPS = frozenset((">", ">|", "&>", ">&"))',
    'TRUNCATING_OPS = frozenset((">", ">|", "&>", ">&", ">>"))',
)

# The redirect operators that open their target from byte zero. `>>`, `&>>` and `<>` keep what is there.
TRUNCATING_OPS = frozenset((">", ">|", "&>", ">&"))

# A round-log path. A target is a round log when its BASENAME is one and not a briefing (`_is_log`), which is the 2026-08 anchoring finding this file records twice carried to the walk: the verb and the path are one run, never two words on a line.
RL = r"pr-babysit-[A-Za-z0-9._-]+\.md"
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
    # #0c331972: text no shell runs is a sentence, and every write that runs is still one.
    (
        "an echo quoting a truncating tee",
        "echo 'echo x | tee --output-error=warn agent/pr-babysit-0831-1.md'",
    ),
    (
        "a commit message quoting a mv",
        "git commit -m 'never mv agent/pr-babysit-0831-1.md' -- a.md",
    ),
    (
        "the verb's own heredoc may name the log and a redirect",
        ".claude/hooks/stop/worklist.py --roundlog 0831-1 <<'EOF'\nsee > agent/pr-babysit-0831-1.md\nEOF",
    ),
    ("a truncating redirect inside sh -c", "sh -c 'echo x > agent/pr-babysit-0831-1.md'"),
    ("sudo tee truncates", "echo x | sudo tee agent/pr-babysit-0831-1.md"),
    ("xargs truncate", "echo agent/pr-babysit-0831-1.md | xargs truncate -s 0"),
    (
        "a briefing beside a log write is no exemption",
        "cat agent/pr-babysit-0831-1-briefing.md > agent/pr-babysit-0831-1.md",
    ),
    ("a verb operand set by an earlier statement", "F=agent/pr-babysit-0831-1.md; mv $F /tmp/"),
    ("cp -t a backup directory is a read", "cp -t /backup agent/pr-babysit-0831-1.md"),
    # Review 0bbd6471.3: xargs appends the log as cp's destination.
    (
        "xargs feeds the log to cp as its destination",
        "echo agent/pr-babysit-0831-1.md | xargs cp /tmp/bak.md",
    ),
    ("xargs feeds the log to sed -i", "echo agent/pr-babysit-0831-1.md | xargs sed -i s/a/b/"),
    ("xargs feeds the log to tee", "echo agent/pr-babysit-0831-1.md | xargs tee"),
    ("a cp destination set by an earlier statement", "F=agent/pr-babysit-0831-1.md; cp /tmp/x $F"),
    ("a copy back into agent/ lands on the log", "cp /tmp/pr-babysit-0831-1.md agent/"),
    (
        "xargs feeds the log to cp -t a backup directory",
        "echo agent/pr-babysit-0831-1.md | xargs cp -t /backup",
    ),
    ("a here-string python write", "python3 <<< \"open('agent/pr-babysit-0831-1.md', 'w')\""),
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


def _is_log(path):
    """A round-log path, by its basename; a briefing has its own contract."""
    base = path.rsplit("/", 1)[-1]
    return re.fullmatch(RL, base) is not None and re.fullmatch(BRIEFING, base) is None


def _copy_writes_log(run_, cwd):
    """Does this `cp` put a file at a round-log path? Where the copy lands is `shellscan.copy_landings`' reading, over the words as bash expands them, the xargs feed included (review 0bbd6471.3: `echo <log> | xargs cp /tmp/bak.md` copies onto the log).

    A copy INTO a directory lands under the source's own name, so `cp <log> /backup/` writes `/backup/<log name>`: a backup, which this guard has always read as a read. Such a landing counts only where a round log lives (a directory named `agent`) or where one already exists, which is the restore-over-the-log shape (`cp /tmp/<log name> agent/`).
    """
    for path, into in shellscan.copy_landings(run_, cwd, ("cp",), run_.xargv):
        if not _is_log(path):
            continue
        if not into or os.path.exists(path) or os.path.basename(os.path.dirname(path)) == "agent":
            return True
    return False


def _appends(args):
    """`tee -a`, `--append`, or a bundle holding `a` (`-ia`). `--output-error=warn` is not one: the arm was once fooled by the `a` in `warn`."""
    return any(
        a == "--append" or re.fullmatch(r"-[A-Za-z]*a[A-Za-z]*", a) is not None for a in args
    )


def _verb_truncates(run_, cwd):
    """Does this run's verb replace a round log wholesale? `mv` and `truncate` on any operand, `cp` onto where `_copy_writes_log` lands it, `dd of=`, `sed -i`, and `tee` without an append flag. xargs appends its input as operands, so the fed words count as operands in every arm."""
    base = run_.name.rsplit("/", 1)[-1]
    # The words as bash hands them over (`_Run.xargv`): `F=<log>; mv $F /tmp/` names the log through a variable an earlier statement set.
    args = list(run_.argv if run_.xargv is None else run_.xargv)
    operands = [a for a in args if not (a.startswith("-") and len(a) > 1)]
    if "xargs" in run_.via and run_.feed:
        operands += run_.feed.split()
    if base in ("mv", "truncate"):
        hits = operands
    elif base == "cp":
        return _copy_writes_log(run_, cwd)
    elif base == "dd":
        hits = [a[3:] for a in args if a.startswith("of=")]
    elif base == "sed":
        in_place = any(
            a.startswith("--in-place")
            or (not a.startswith("--") and a.startswith("-") and "i" in a[1:])
            for a in args
        )
        hits = operands if in_place else []
    elif base == "tee":
        hits = [] if _appends(args) else operands
    else:
        hits = []
    return any(_is_log(h) for h in hits)


def _program_truncates(code):
    """Does an interpreter program write a round log, or write a target it never names?

    THE PYTHON ARM MUST TEST THE TARGET, NOT JUST THE IDIOM. A heredoc editing an unrelated file whose CONTENT quotes a round-log path matched every time when this was an unconditional idiom test (measured 2026-08-27, refusing an edit to a scratchpad state-body file). So the write target is resolved the way python spells one -- assigned to a name, or handed to open()/Path() -- and every quoted path inside a copy/move call counts too, since only the destination truncates and telling the two apart by position across copy/copyfile/copy2/move/replace/rename is fragile. FAIL CLOSED when no target resolves: that unidentifiable shape is `p.write_text(s[:i] + new)`, which destroyed the round history on 2026-08-19.

    shutil/os MOVE AND COPY COUNT AS WRITES. Measured 2026-08-27: shutil.copy and os.replace onto a round log both returned 0 from this guard, because the arm triggered only on write_text and open(...,"w"). Each of them overwrites the file completely.
    """
    if not hookio.grep_q_line(
        r"write_text|open\([^)]*[\"']w|shutil\.(copy|copyfile|copy2|move)|os\.(replace|rename)",
        code,
    ):
        return False
    candidates = []
    for match in hookio.grep_o(
        r"(=|open\(|Path\()[" + hookio.BLANK + r"]*[\"'][^\"']+\.md", hookio._here_string(code)
    ):
        candidates.extend(hookio.grep_o(r"[A-Za-z0-9_./-]+\.md", match))
    for match in hookio.grep_o(
        r"(shutil\.(copy|copyfile|copy2|move)|os\.(replace|rename))\([^)]*",
        hookio._here_string(code),
    ):
        candidates.extend(hookio.grep_o(r"[A-Za-z0-9_./-]+\.md", match))
    return not candidates or any(_is_log(c) for c in candidates)


def run(ev):
    cmd = ev.field("tool_input", "command")

    # A round-log path must appear at all, which is also what keeps the walk below off every command that cannot touch one.
    if not hookio.grep_q_line(RL, cmd):
        return hookio.ALLOW

    # The redirects bash performs, with their operator: `>` truncates, `>>` appends (`2>&1`-style descriptor plumbing names no file).
    truncating = any(
        op in TRUNCATING_OPS and _is_log(target) and not re.fullmatch(r"\d+|-", target)
        for op, target in shellscan._analyse(cmd).writes
    )
    # The verbs it runs, behind any prefix, xargs, sh -c or find -exec.
    cwd = ev.field("cwd") or str(hookio.repo_root())
    truncating = truncating or any(_verb_truncates(r, cwd) for r in shellscan.every_run(cmd))
    # An in-process write from python, node, perl or ruby. NOT anchorable the way the shell verbs are: the 2026-08-19 incident was a heredoc where the path sat on a DIFFERENT LINE from the write call. NAMED RESIDUAL: a program that writes an UNNAMED target while the command merely mentions a round-log path elsewhere is still refused; that is the one over-block left standing, and it is deliberate, because it is the exact shape that destroyed the appendix.
    truncating = truncating or any(
        _program_truncates(code) for _family, code in WT.interpreter_programs(cmd)
    )

    if not truncating:
        return hookio.ALLOW

    ev.warn(MESSAGE)
    return hookio.DENY
