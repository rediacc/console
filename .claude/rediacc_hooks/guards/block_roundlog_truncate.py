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

import functools
import os
import re
import types

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
    # Review 126f2a9f.1: bash brace-expands the fed word before xargs reads it.
    (
        "a brace-expanded fed destination",
        "echo {/tmp/x,agent/pr-babysit-0831-1.md} | xargs cp /tmp/y.md",
    ),
    # #e5b0540a: a glob or brace that could spell a log reaches the walk, and every arm reads it expanded.
    (
        "a fed log glob in an unknown directory",
        'cd "$D" && echo pr-babysit-*.md | xargs cp /tmp/x.md',
    ),
    ("a fed glob that cannot spell a log", 'cd "$D" && echo notes-*.md | xargs cp /tmp/x.md'),
    ("mv a brace that spells the log", "mv agent/pr-babysit-{0831-1,x}.md /tmp/"),
    ("truncate a log glob", "truncate -s 0 agent/pr-babysit-*.md"),
    ("a redirect onto a log glob", "echo x > agent/pr-babysit-*.md"),
    ("cp onto a log glob", "cp /tmp/x agent/pr-babysit-*.md"),
    ("listing a log glob is a read", "ls agent/pr-babysit-*.md"),
    ("a log glob piped with no blank", 'cd "$D" && echo pr-babysit-*.md|xargs cp /tmp/x.md'),
    # Review 9ed30a8a.3: a glob that meets the round-log pattern in an unknown directory, whatever sample names it would miss.
    ("a bare md glob in an unknown directory", 'cd "$D" && truncate -s 0 *.md'),
    (
        "a glob that meets the log by a class",
        'cd "$D" && echo [p]r-babysit-1?08*.md | xargs cp /tmp/x.md',
    ),
    ("a txt glob in an unknown directory cannot be a log", 'cd "$D" && truncate -s 0 *.txt'),
    # #e5b0540a, live false positive (w2): a `*` in Python code is not a glob, and a program that cannot spell a log writes some other file.
    (
        "a heredoc that multiplies and writes through a variable",
        "python3 - <<'EOF'\nimport pathlib\np = pathlib.Path('notes.txt')\nn = 3 * 4\np.write_text(str(n))\nEOF",
    ),
    (
        "python -c repeating a string into a file",
        "python3 -c \"import pathlib,sys; t=pathlib.Path(sys.argv[1]); t.write_text('x' * 3)\" out.txt",
    ),
    (
        "a star import that writes",
        "python3 - <<'EOF'\nfrom os import *\nf = open(name, 'w')\nf.write('x')\nEOF",
    ),
    # ...and a program whose literals could spell a log still fails closed.
    (
        "a program globbing md files writes through a variable",
        "python3 - <<'PY'\nimport glob\nfor p in glob.glob('agent/*.md'):\n    open(p, 'w').write('')\nPY",
    ),
    (
        "a program building the log name in an f-string",
        "python3 - <<'PY'\nb = '0831-1'\nopen(f'agent/pr-babysit-{b}.md', 'w').write('')\nPY",
    ),
    (
        "a program globbing txt files cannot write a log",
        "python3 - <<'PY'\nimport glob\nfor p in glob.glob('docs/*.txt'):\n    open(p, 'w').write('')\nPY",
    ),
    # Review 1d4e1754.1: a program handed the log (an argument, the environment, stdin) writes it without naming it.
    (
        "a program opening argv for write, handed the log",
        "python3 -c \"import sys; open(sys.argv[1],'w').write('')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "the log through a prefix assignment",
        "F=agent/pr-babysit-0831-1.md python3 -c \"import os; open(os.environ['F'],'w').write('')\"",
    ),
    (
        "the log through an exported variable",
        "export F=agent/pr-babysit-0831-1.md; python3 -c \"import os; open(os.environ['F'],'w').write('')\"",
    ),
    (
        "the log on stdin",
        "echo agent/pr-babysit-0831-1.md | python3 -c \"import sys; open(sys.stdin.read().strip(),'w').write('')\"",
    ),
    (
        "a stdin program handed the log as its argument",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys\np = sys.argv[1]\nopen(p, 'w').write('')\nPY",
    ),
    (
        "an argv glob that could be a log",
        "cd \"$D\" && python3 -c \"import sys; open(sys.argv[1],'w').write('')\" *.md",
    ),
    (
        "a program that only reads the log it is handed",
        'python3 -c "import sys; print(open(sys.argv[1]).read())" agent/pr-babysit-0831-1.md',
    ),
    (
        "a program handed the log that writes a named other file",
        "python3 -c \"import sys; open('out.md','w').write(open(sys.argv[1]).read())\" agent/pr-babysit-0831-1.md",
    ),
    (
        "the same writer handed a txt file",
        "python3 -c \"import sys; open(sys.argv[1],'w').write('')\" notes.txt",
    ),
    (
        "a writer handed another file after the log was only read",
        "cat agent/pr-babysit-0831-1.md; python3 -c \"import sys; open(sys.argv[1],'w').write('')\" notes.txt",
    ),
    ("appending to a log glob", "echo x >> agent/pr-babysit-*.md"),
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
    # #6378e10e: perl edits in place too, and a script naming the log is not the file edited.
    ("perl -pi", "perl -pi -e 's/a/b/' agent/pr-babysit-0831-1.md"),
    ("perl -i -pe", "perl -i -pe 's/a/b/' agent/pr-babysit-0831-1.md"),
    ("perl -pe only prints", "perl -pe 's/a/b/' agent/pr-babysit-0831-1.md"),
    ("gsed -i", "gsed -i 's/a/b/' agent/pr-babysit-0831-1.md"),
    (
        "a sed script naming the log edits another file",
        "sed -i 's/pr-babysit-0831-1.md/x/' notes.md",
    ),
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
    # Review 4b3f59b5.1, judged per write: every row of the first block was allowed at 8abc48a14 with the log handed. The first three name another file somewhere (that used to clear the whole program); the rest write, remove or truncate through a spelling the write test did not know, or hand the log where the handed words were not read.
    (
        "a named md file read beside a write to argv",
        "python3 -c \"import sys; print(open('README.md').read()); open(sys.argv[1],'w').write('')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "a name bound to another md file beside a write to argv",
        "python3 -c \"import sys; n='notes.md'; open(sys.argv[1],'w').write(open(n).read())\" agent/pr-babysit-0831-1.md",
    ),
    (
        "a named copy beside a write to argv",
        "python3 -c \"import sys,shutil; shutil.copy('a.md','b.md'); open(sys.argv[1],'w').write('')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "a path object's own open('w') on argv",
        "python3 -c \"import sys,pathlib; pathlib.Path(sys.argv[1]).open('w').write('')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "an open( whose arguments span lines",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys\nf = open(\n    sys.argv[1],\n    'w',\n)\nf.write('')\nPY",
    ),
    (
        "os.truncate on argv",
        'python3 -c "import sys,os; os.truncate(sys.argv[1], 0)" agent/pr-babysit-0831-1.md',
    ),
    (
        "truncate() on a handle opened r+",
        "python3 -c \"import sys; f=open(sys.argv[1],'r+'); f.truncate()\" agent/pr-babysit-0831-1.md",
    ),
    (
        "os.remove on argv",
        'python3 -c "import sys,os; os.remove(sys.argv[1])" agent/pr-babysit-0831-1.md',
    ),
    (
        "an imported remove on argv",
        'python3 -c "import sys; from os import remove; remove(sys.argv[1])" agent/pr-babysit-0831-1.md',
    ),
    (
        "Path.unlink on argv",
        'python3 -c "import sys,pathlib; pathlib.Path(sys.argv[1]).unlink()" agent/pr-babysit-0831-1.md',
    ),
    (
        "O_TRUNC on argv",
        'python3 -c "import sys,os; os.open(sys.argv[1], os.O_WRONLY|os.O_TRUNC)" agent/pr-babysit-0831-1.md',
    ),
    (
        "a shell command built from argv",
        "python3 -c \"import sys,os; os.system('cp /dev/null ' + sys.argv[1])\" agent/pr-babysit-0831-1.md",
    ),
    (
        "a subprocess handed argv",
        "python3 -c \"import sys,subprocess; subprocess.run(['truncate','-s','0',sys.argv[1]])\" agent/pr-babysit-0831-1.md",
    ),
    (
        "code built at run time",
        "python3 -c \"import sys; eval('open(sys.argv[1],chr(119))')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "node truncateSync on argv",
        "node -e \"require('fs').truncateSync(process.argv[1])\" agent/pr-babysit-0831-1.md",
    ),
    ("ruby File.write on argv", "ruby -e \"File.write(ARGV[0], '')\" agent/pr-babysit-0831-1.md"),
    (
        "perl open in write mode on argv",
        "perl -e 'open(my $f, \">\", $ARGV[0]); close $f' agent/pr-babysit-0831-1.md",
    ),
    (
        "the log as an option's value",
        "python3 -c \"import sys; open(sys.argv[1].split('=')[1],'w').write('')\" --out=pr-babysit-0831-1.md",
    ),
    (
        "an md glob on the program's stdin",
        'cd "$D" && ls *.md | python3 -c "import sys; [open(l.strip(),\'w\') for l in sys.stdin]"',
    ),
    (
        "a write mode held in a variable",
        "python3 -c \"import sys; m='w'; open(sys.argv[1], m).write('')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "a write mode taken from argv",
        "python3 -c \"import sys; open(sys.argv[1], sys.argv[2]).write('')\" agent/pr-babysit-0831-1.md w",
    ),
    (
        "a remover passed to map, never called in the text",
        'python3 -c "import sys,os; list(map(os.remove, sys.argv[1:]))" agent/pr-babysit-0831-1.md',
    ),
    (
        "open under another name",
        "python3 -c \"import sys; w=open; w(sys.argv[1],'w')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "a literal-bound name a loop rebinds",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys\np = 'x.txt'\nfor p in sys.argv[1:]:\n    open(p, 'w').write('')\nPY",
    ),
    (
        "a literal-bound name a parameter shadows",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys\np = 'x.txt'\ndef w(p):\n    open(p, 'w').write('')\nw(sys.argv[1])\nPY",
    ),
    # Their controls, all allowed: every write goes to a named file that is not a log, or nothing replaces a file at all. The star row is review 4b3f59b5.2: inline program text is not a shell word, so `2*3` is not a glob.
    (
        "a named output written from the handed log",
        "python3 -c \"import sys; open('out.txt','w').write(open(sys.argv[1]).read())\" agent/pr-babysit-0831-1.md",
    ),
    (
        "a named md copy written while the handed log is printed",
        "python3 -c \"import sys; print(open(sys.argv[1]).read()); open('copy.md','w').write('x')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "a literal-bound name written from the handed log",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys\np = 'x.txt'\nopen(p, 'w').write(open(sys.argv[1]).read())\nPY",
    ),
    (
        "a read mode held in a variable",
        "python3 -c \"import sys; m='r'; print(open(sys.argv[1], m).read())\" agent/pr-babysit-0831-1.md",
    ),
    (
        "an append to the handed log",
        "python3 -c \"import sys; open(sys.argv[1], 'a').write('more')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "str.replace on what was read from the handed log",
        "python3 -c \"import sys; s=open(sys.argv[1]).read().replace('a','b'); open('out.txt','w').write(s)\" agent/pr-babysit-0831-1.md",
    ),
    (
        "an md glob on the stdin of a program that only prints",
        'cd "$D" && ls *.md | python3 -c "import sys; print(sys.stdin.read())"',
    ),
    (
        "a star in inline code beside a named write",
        "python3 -c \"p=2*3; open('n.txt','w').write(str(p))\"",
    ),
    (
        "perl reading the handed log",
        "perl -e 'open(my $f, \"<\", $ARGV[0]); print <$f>' agent/pr-babysit-0831-1.md",
    ),
    (
        "node writing a named file from the handed log",
        "node -e \"const fs=require('fs'); const o='out.json'; fs.writeFileSync(o, fs.readFileSync(process.argv[1]))\" agent/pr-babysit-0831-1.md",
    ),
]


def _is_log(path):
    """A round-log path, by its basename; a briefing has its own contract."""
    base = path.rsplit("/", 1)[-1]
    return re.fullmatch(RL, base) is not None and re.fullmatch(BRIEFING, base) is None


# The characters with which bash makes one word into other names: globs, braces, a leading tilde.
_EXPANDING = frozenset("*?[{~")
_GLOB = frozenset("*?[")
# Round-log names a glob is tried against by the prefilter: any pattern that matches one of these could spell a log.
_PRINTABLE = frozenset(chr(c) for c in range(32, 127))


def _char_class(body: str) -> frozenset[str]:
    """The characters a bracket body names (`A-Za-z0-9._-`), ranges expanded; a leading or trailing `-` is itself."""
    out: set[str] = set()
    k = 0
    while k < len(body):
        if k + 2 < len(body) and body[k + 1] == "-":
            out.update(chr(c) for c in range(ord(body[k]), ord(body[k + 2]) + 1))
            k += 3
        else:
            out.add(body[k])
            k += 1
    return frozenset(out)


def _log_automaton():
    """The round-log name as an automaton, read out of `RL` itself (review 9ed30a8a.3): `<prefix>[<class>]+<suffix>`. A change to RL that leaves that shape raises here, at import, rather than leaving the prefilter testing an old pattern."""
    m = re.fullmatch(r"([^\[\\]+)\[([^\]]+)\]\+((?:\\.|[^\\])+)", RL)
    if m is None:
        raise RuntimeError("RL no longer reads as <prefix>[<class>]+<suffix>: %r" % RL)
    prefix, body, suffix = m.group(1), _char_class(m.group(2)), re.sub(r"\\(.)", r"\1", m.group(3))
    # States 0..len(prefix) spell the prefix; "B" is one or more body characters; ("S", i) has matched i characters of the suffix after the body.
    edges: dict[object, list[tuple[frozenset[str], object]]] = {
        i: [(frozenset(prefix[i]), i + 1)] for i in range(len(prefix))
    }
    edges[len(prefix)] = [(body, "B")]
    edges["B"] = [(body, "B")]
    for i in range(len(suffix)):
        edges[("S", i)] = [(frozenset(suffix[i]), ("S", i + 1))]
    return edges, ("S", len(suffix))


_LOG_EDGES, _LOG_ACCEPT = _log_automaton()


def _closure(states):
    """`B` reaches the suffix's start without reading a character."""
    out = set(states)
    if "B" in out:
        out.add(("S", 0))
    return out


def _glob_elements(pattern: str) -> list[frozenset[str] | None]:
    """A glob as a list of character sets, `None` for `*`."""
    out: list[frozenset[str] | None] = []
    k = 0
    while k < len(pattern):
        ch = pattern[k]
        if ch == "*":
            out.append(None)
        elif ch == "?":
            out.append(_PRINTABLE)
        elif ch == "\\" and k + 1 < len(pattern):
            k += 1
            out.append(frozenset(pattern[k]))
        elif ch == "[" and "]" in pattern[k + 2 :]:
            close = pattern.index("]", k + 2)
            inner = pattern[k + 1 : close]
            negated = inner[:1] in ("!", "^")
            named = _char_class(inner[1:] if negated else inner)
            out.append(_PRINTABLE - named if negated else named)
            k = close
        else:
            out.append(frozenset(ch))
        k += 1
    return out


def _glob_meets_log(pattern):
    """Can the glob `pattern` (a basename) and the round-log name both match some one name? Read as the intersection of the two languages, so no sample name is involved: `*.md`, `pr-*`, `p?-babysit-*` and `[p]r-babysit-x.md` do, `notes-*.md` and `*.txt` do not."""
    states = _closure({0})
    for element in _glob_elements(pattern):
        if element is None:
            reached = set(states)
            frontier = list(states)
            while frontier:
                state = frontier.pop()
                for _chars, nxt in _LOG_EDGES.get(state, ()):
                    for n in _closure({nxt}):
                        if n not in reached:
                            reached.add(n)
                            frontier.append(n)
            states = reached
            continue
        states = _closure(
            {nxt for s in states for chars, nxt in _LOG_EDGES.get(s, ()) if chars & element}
        )
        if not states:
            return False
    return _LOG_ACCEPT in states


def _names_log(word, directory=None):
    """Could `word` name a round log once bash expands it? A literal name is read as it stands; a word bash brace-, tilde- or glob-expands is read through `shellscan._fed_candidates` (its matches on disk in `directory`, the run's own, when known) and, for a glob, through one name of its shape too (`shellscan._glob_shape`), so `pr-babysit-*.md` in a directory this walk cannot read still counts (#e5b0540a)."""
    if _is_log(word):
        return True
    if not any(ch in word for ch in _EXPANDING):
        return False
    forms = shellscan._fed_candidates([word], directory)
    forms += [
        shellscan._glob_shape(f) for f in forms if any(ch in f.rsplit("/", 1)[-1] for ch in _GLOB)
    ]
    if any(_is_log(f) for f in forms):
        return True
    # A RELATIVE glob in a directory this walk cannot read fails safe: any glob that could match a round-log name counts as one (`cd "$D" && truncate -s0 *.md`), since which names it meets is the disk's answer, not ours.
    if directory is None:
        return any(
            _glob_meets_log(alt.rsplit("/", 1)[-1])
            for alt in shellscan._brace_alternatives(word)
            if not alt.startswith("/") and any(ch in alt.rsplit("/", 1)[-1] for ch in _GLOB)
        )
    return False


# The verbs whose operands `_verb_truncates` judges; the prefilter reads their words, and nothing else of the command.
_TRUNCATING_VERBS = frozenset(("mv", "truncate", "cp", "dd", "tee"))


def _log_stem():
    """The fixed part every round-log name carries (`pr-babysit`), read from RL's own prefix; raises at import if RL stops starting with one."""
    m = re.match(r"[A-Za-z]+-[A-Za-z]+", RL)
    if m is None:
        raise RuntimeError("RL no longer starts with a <word>-<word> stem: %r" % RL)
    return m.group(0)


_LOG_STEM = _log_stem()


def _word_could_name_log(word):
    """Could one word, as bash or a program's glob call expands it, name a round log? Its brace alternatives spell one (`RL`), or a glob in its basename meets the round-log pattern (`_glob_meets_log`)."""
    if not any(ch in word for ch in "*?[{"):
        return False
    for alt in shellscan._brace_alternatives(word):
        if re.search(RL, alt):
            return True
        base = alt.rsplit("/", 1)[-1]
        if any(ch in base for ch in _GLOB) and _glob_meets_log(base):
            return True
    return False


def _program_could_name_log(code):
    """Could an interpreter program's own text spell a round-log path? It names the round-log stem (`pr-babysit`, in a literal or an f-string alike), or one of its STRING LITERALS is a glob or brace that can meet the round-log pattern (`glob.glob('agent/*.md')`). Code outside a literal is never read for globs: `3 * 4`, `from os import *` and `r']*'` are Python, not paths (#e5b0540a's false positive, reported live by w2)."""
    if _LOG_STEM in code:
        return True
    # Every single- or double-quoted string literal, escapes kept (Python, shell and JS alike): an EXTRACTOR over program text the walk already chose, so it is local here rather than a module pattern a sentence could be probed against.
    literals = re.findall(r"'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"", code)
    return any(_word_could_name_log(lit[1:-1]) for lit in literals)


def _shell_words(cmd):
    """The shell words a truncating arm judges: every redirect target, and the words (with what xargs appends) of each `mv`, `truncate`, `cp`, `dd`, `tee` and in-place editor bash runs. For an interpreter run, its arguments other than the inline program, and its stdin feed. Interpreter PROGRAM TEXT is not among them."""
    words = [target for _op, target in shellscan._analyse(cmd).writes]
    for run_ in shellscan.every_run(cmd):
        base = run_.name.rsplit("/", 1)[-1]
        # An interpreter's arguments are operands too (review 1d4e1754.1): `python3 -c "open(sys.argv[1], 'w')" agent/*.md`.
        if (
            base in _TRUNCATING_VERBS
            or shellscan.in_place_edit(run_) is not None
            or base.startswith(shellscan.INTERPRETER_NAMES)
        ):
            interpreter = base.startswith(shellscan.INTERPRETER_NAMES)
            # The inline program is not an operand (review 4b3f59b5.2): its text is the program arm's to read, literal by literal, and a `*` in code is not a glob.
            program = shellscan.interpreter_program(run_, cmd)[0] if interpreter else None
            words.extend(a for a in run_.argv if a != program)
            # xargs turns its feed into operands, and an interpreter reads its stdin (`ls *.md | python3 -c "... sys.stdin ..."`).
            if run_.feed and ("xargs" in run_.via or interpreter):
                words.extend(run_.feed.split())
    return words


def _could_name_log(cmd):
    """The prefilter. A command passes when it names the round-log stem at all (`pr-babysit`), when one of its SHELL WORDS that a truncating arm judges holds a glob or brace that could spell a log (`_shell_words`, `_word_could_name_log`), or when an interpreter program's text could spell one (`_program_could_name_log`). A glob is put to the round-log pattern's automaton, never to the disk.

    SHELL WORDS, NEVER PROGRAM TEXT (#e5b0540a, live false positive reported by w2). The first version tokenised the whole command, so a lone `*` anywhere (`3 * 4` in a Python heredoc) met the pattern, the program's write through a variable then failed closed, and every Python heredoc that wrote a file and multiplied was refused.
    """
    if _LOG_STEM in cmd:
        return True
    if not any(ch in cmd for ch in "*?[{"):
        return False
    if any(_word_could_name_log(w) for w in _shell_words(cmd)):
        return True
    return any(_program_could_name_log(code) for _family, code in WT.interpreter_programs(cmd))


def _copy_writes_log(run_, cwd):
    """Does this `cp` put a file at a round-log path? Where the copy lands is `shellscan.copy_landings`' reading, over the words as bash expands them, the xargs feed included (review 0bbd6471.3: `echo <log> | xargs cp /tmp/bak.md` copies onto the log).

    A copy INTO a directory lands under the source's own name, so `cp <log> /backup/` writes `/backup/<log name>`: a backup, which this guard has always read as a read. Such a landing counts only where a round log lives (a directory named `agent`) or where one already exists, which is the restore-over-the-log shape (`cp /tmp/<log name> agent/`).
    """
    for path, into in shellscan.copy_landings(run_, cwd, ("cp",)):
        # A landing is absolute, so a glob in it is matched on disk; its shape counts too (`_names_log`).
        if not _names_log(path):
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
    elif shellscan.in_place_edit(run_) is not None:
        # EVERY IN-PLACE EDITOR, by its own option parse (#6378e10e): sed, gsed and `perl -i`/`-pi` rewrite the files they name, and `perl -pi -e ... <log>` was allowed while only sed was asked. The files are `in_place_edit`'s, read over the words as bash expands them (an attached `-e` script is not a file, review 3f53e99e.2), plus what xargs appends.
        expanded = types.SimpleNamespace(name=run_.name, argv=args)
        edit = shellscan.in_place_edit(expanded) or shellscan.in_place_edit(run_)
        fed = run_.feed.split() if "xargs" in run_.via and run_.feed else []
        hits = [*edit[1], *fed]
    elif base == "tee":
        hits = [] if _appends(args) else operands
    else:
        hits = []
    # Each operand as bash expands it in the run's own directory: `mv agent/pr-babysit-{0831-1,x}.md /tmp/` and `truncate -s0 agent/pr-babysit-*.md` name the log (#e5b0540a).
    directory = shellscan._run_directory(run_, cwd)
    return any(_names_log(h, directory) for h in hits)


def _handed_words(run_, code, kind):
    """What the command line hands an interpreter run besides its program (review 1d4e1754.1): its arguments as bash expands them (the inline program itself left out), the values of the environment the command line gives it (`F=<log> python3 ...`, an earlier `export`), and the words on its stdin when the program did not come from there. A program reads any of them without naming a path in its own text (`sys.argv[1]`, `os.environ['F']`, `sys.stdin`)."""
    args = list(run_.argv if run_.xargv is None else run_.xargv)
    # EVERY word but the program itself. An option is an operand too: `--out=<log>` hands the log as its value, and a bare `-o` is harmless to keep (review 4b3f59b5.1: dropping option-shaped words dropped `--out=<log>` with them).
    words = []
    for arg in args:
        if arg == code:
            continue
        words.append(arg)
        if arg.startswith("-") and "=" in arg:
            words.append(arg.split("=", 1)[1])
    words += [v for v in run_.env.values() if isinstance(v, str)]
    if kind != "stdin" and run_.feed:
        words += run_.feed.split()
    return words


def _handed_a_log(run_, code, kind, cwd):
    """Is this interpreter run handed something that names, or could spell, a round log?"""
    directory = shellscan._run_directory(run_, cwd)
    return any(_names_log(w, directory) for w in _handed_words(run_, code, kind))


# --------------------------------------------------------------------------- what an interpreter program writes ---------------------------------------------------------------------------
#
# JUDGED PER WRITE (review 4b3f59b5.1). The program arm used to collect every quoted `.md` literal in a target position and, when it found one that was not a round log, clear the whole program: `print(open('README.md').read()); open(sys.argv[1], 'w')` handed the log was allowed because `README.md` was "the target". Each write SITE is now read on its own: the expression it writes through is a path literal (harmless unless it names a log), a name bound only to path literals (the same), or anything else, which is UNRESOLVED. One unresolved write keeps a handed or spellable log in play, whatever else the program names.
#
# A SITE IS ANY CALL THAT REPLACES OR REMOVES A FILE, not only `open(..., 'w')`. Each row below was allowed with the log handed in argv until the row's spelling was listed (measured 2026-10-12 at 8abc48a14): a path object's own `.open('w')`, an `open(` whose arguments span lines, `truncate`, `remove`/`unlink`, `O_TRUNC`, node's `fs` calls beyond `writeFileSync`, ruby's `File.write`, a perl `open` in `>` mode, and a program that hands a command to a shell.
#
# STILL NOT READ, each measured allowed with the log handed (2026-10-12) and named rather than pretended away: a writer reached dynamically (`getattr(os, 'rem' + 'ove')`, `__import__('os').remove`), `Path.replace` (the method name is `str.replace` in nearly every program), a DIRECTORY handed in place of the log (`os.listdir(sys.argv[1])` over `agent`), a log name assembled from pieces that never hold the stem whole, and a path the program reads out of a file.
@functools.lru_cache(maxsize=1)
def _grammar():
    """The compiled readers of PROGRAM TEXT, built once. Each is applied to an interpreter program the walk already chose and never to the command, so they are built here rather than held as module patterns."""
    string = r"""[rRbBuUfF]{0,2}(?:'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*")"""
    # What a method is called on: a dotted, subscripted name, with one trailing call (`pathlib.Path('x')`).
    receiver = (
        r"[A-Za-z_$@][\w$]*(?:\.[A-Za-z_]\w*|\[[^\]\n]*\])*(?:\((?:[^()'\"]|" + string + r")*\))?"
    )
    return types.SimpleNamespace(
        string=re.compile(string),
        receiver=re.compile(r"(" + receiver + r")\s*\.$"),
        # A path literal wrapped once: `Path('x')` with that one argument (a second one joins a run-time part on), or `open('x', ...)`, whose later arguments are a mode.
        wrap=re.compile(
            r"(?:pathlib\.)?(?:Path|PurePath|PosixPath)\(\s*(?P<p>"
            + string
            + r")\s*\)|open\(\s*(?P<o>"
            + string
            + r")\s*(?:,[^()]*)?\)"
        ),
        # `open(` in every dialect: the builtin, a module's (`io.open`, `File.open`, `fs.openSync`), a path object's own.
        opener=re.compile(r"(?<![\w$])open(?:Sync)?\("),
        # Calls that replace or remove the file named by their FIRST argument. The bare names are the same calls imported (`from os import remove`).
        first=re.compile(
            r"(?:\bos\.(?:truncate|remove|unlink|rmdir)|\bFile\.(?:write|delete|truncate|unlink)|\b(?:fs\.)?(?:writeFileSync|writeFile|truncateSync|rmSync|unlinkSync|rmdirSync|createWriteStream)|(?<![\w.$])(?:truncate|remove|unlink))\("
        ),
        # Calls that replace or remove a file named by ANY argument: the copy and move family, imported bare or not.
        every=re.compile(
            r"(?:\bshutil\.(?:copy|copyfile|copy2|move|rmtree)|\bos\.(?:replace|rename|renames)|\b(?:fs\.)?(?:renameSync|copyFileSync)|(?<![\w.$])(?:copy|copyfile|copy2|move|rmtree|rename|replace))\("
        ),
        # Methods that replace or remove the path they are called ON. `.replace(` is absent: it is `str.replace` in nearly every program, and `Path.replace` is a named residual.
        method=re.compile(r"\.(?:write_text|write_bytes|unlink|truncate|rmdir|touch|rename)\("),
        # No readable target at all: a raw descriptor flag, a command handed to a shell, code built at run time, the perl and ruby calls written without parentheses, and a writer passed around as a value rather than called (`map(os.remove, sys.argv[1:])`, `w = open`).
        blind=re.compile(
            r"O_TRUNC|\bos\.system\(|\bsubprocess\.|\bexecSync\(|\bchild_process\b|\bspawnSync\(|\bsystem\(|`[^`\n]*`|\bexec\(|\beval\(|\bopen\s+(?:my\s+)?[$A-Z]\w*\s*,\s*['\"]\+?>(?!>)|(?<![\w.$])(?:unlink|rename|truncate)\s+[$@'\"]|\bFile\.(?:write|delete|truncate|unlink|open)\s+[^\s(=]|\b(?:os\.(?:remove|unlink|truncate|rename|replace)|shutil\.(?:copy|copyfile|copy2|move|rmtree))\b(?!\s*\()|[=(,]\s*open\s*[,);\n]"
        ),
    )


# The receivers whose `.open(` takes the path as its first argument, as the builtin does; any other receiver IS the path (`Path(x).open('w')`).
_OPEN_MODULES = frozenset(("io", "codecs", "builtins", "__builtins__", "File", "IO", "fs", "os"))


def _call_args(code, at):
    """The arguments of the call whose `(` is `code[at]`, split at its top-level commas; None when the call never closes (a quote this reading lost track of)."""
    depth, quote, start, args, i = 0, None, at + 1, [], at
    while i < len(code):
        ch = code[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                args.append(code[start:i])
                return [a.strip() for a in args if a.strip()]
        elif ch == "," and depth == 1:
            args.append(code[start:i])
            start = i + 1
        i += 1
    return None


def _string_body(lit):
    """`(prefix, body)` of one string literal."""
    quote = min(i for i in (lit.find("'"), lit.find('"')) if i >= 0)
    return lit[:quote].lower(), lit[quote + 1 : -1]


def _literal_text(expr):
    """The path a target expression spells when it is ONE string literal, alone or wrapped in `Path(...)`/`open(...)`; None for anything built at run time. An f-string with a `{}` hole is built at run time unless its fixed text already holds the round-log stem."""
    grammar = _grammar()
    expr = expr.strip()
    wrapped = grammar.wrap.fullmatch(expr)
    if wrapped:
        lit = wrapped.group("p") or wrapped.group("o")
    elif grammar.string.fullmatch(expr):
        lit = expr
    else:
        return None
    prefix, body = _string_body(lit)
    if "f" in prefix and "{" in body and _LOG_STEM not in body:
        return None
    return body


def _bound_literals(name, code):
    """Every literal `name` is bound to in `code`, or None unless EVERY binding of it is a plain statement-level assignment of one literal. Not bound at all is None (`sys.argv`, a parameter), and so is a name bound any other way: a loop (`for p in sys.argv[1:]`), `with ... as p`, an import, a walrus, an augmented, tuple, chained or conditional one-line assignment, a function or lambda parameter, a `global`."""
    q = re.escape(name)
    plain = re.findall(
        r"(?:^|[;\n])[ \t]*(?:(?:const|let|var)[ \t]+)?"
        + q
        + r"[ \t]*(?::[^=\n]+)?=(?!=)[ \t]*([^;\n]+)",
        code,
    )
    if not plain:
        return None
    # Every `name =` anywhere, whatever precedes it: more of them than plain assignments means one sits where the plain reading does not look (`if c: p = sys.argv[1]`, `a = p = x`, `f(p=x)`).
    if len(re.findall(r"(?<![\w.$])" + q + r"\s*(?::[^=\n()]+)?=(?!=)", code)) != len(plain):
        return None
    other = (
        r"\bfor\s+[^:\n]*?\b" + q + r"\b[^:\n]*?\bin\b",
        r"\bas\s+\(?[\w, ]*\b" + q + r"\b",
        r"\b(?:global|nonlocal|import)\s+[^\n;]*\b" + q + r"\b",
        r"(?<![\w.$])" + q + r"\s*(?::=|[+\-*/%|&^@]=|<<=|>>=|,[^=\n;]*=(?!=))",
        r",\s*" + q + r"\s*=(?!=)",
        r"\bdef\s+\w+\s*\([^)]*\b" + q + r"\b",
        r"\blambda\b[^:\n]*\b" + q + r"\b",
    )
    if any(re.search(form, code) for form in other):
        return None
    out = []
    for rhs in plain:
        text = _literal_text(rhs)
        if text is None:
            return None
        out.append(text)
    return out


def _keyword(args, name):
    """The value of the `name=` argument among `args`, or None."""
    for arg in args:
        m = re.match(re.escape(name) + r"\s*=(?!=)\s*(.+)", arg, re.DOTALL)
        if m:
            return m.group(1).strip()
    return None


def _positional(args, index):
    """The `index`-th argument when it is positional, or None."""
    if index < len(args) and not re.match(r"[A-Za-z_]\w*\s*=(?!=)", args[index]):
        return args[index]
    return None


def _mode_writes(expr, code):
    """Does an `open` mode replace the file's content? A literal one does when it holds `w`, `x`, `+` or perl's `>` (an append, `a` or `>>`, and a read do not); no mode at all is a read; a mode this reading cannot resolve to literals is taken as a write (`m = sys.argv[2]; open(p, m)`)."""
    if expr is None:
        return False
    if _grammar().string.fullmatch(expr):
        modes = [_string_body(expr)[1]]
    elif re.fullmatch(r"[A-Za-z_]\w*", expr):
        modes = _bound_literals(expr, code)
    else:
        modes = None
    if modes is None:
        return True
    return any(not m.startswith(">>") and any(ch in m for ch in "wx+>") for m in modes)


def _write_sites(code):
    """Every expression `code` writes THROUGH, one per site; None for a site whose target this reading cannot lift out."""
    grammar = _grammar()
    sites: list[str | None] = [None for _ in grammar.blind.finditer(code)]
    for match in grammar.opener.finditer(code):
        args = _call_args(code, match.end() - 1)
        before = code[: match.start()]
        on = None
        if before.endswith("."):
            found = grammar.receiver.search(before)
            on = found.group(1) if found else ""
        if args is None:
            sites.append(None)
        elif on == "os":
            # `os.open(path, flags)`: a write unless the flags are exactly read-only.
            if len(args) < 2 or not re.fullmatch(r"(?:os\.)?O_RDONLY", args[1]):
                sites.append(args[0] if args else None)
        elif on is None or on in _OPEN_MODULES:
            if _mode_writes(_keyword(args, "mode") or _positional(args, 1), code):
                sites.append(_keyword(args, "file") or _positional(args, 0))
        elif _mode_writes(_keyword(args, "mode") or _positional(args, 0), code):
            sites.append(on or None)
    for match in grammar.first.finditer(code):
        args = _call_args(code, match.end() - 1)
        sites.append(args[0] if args else None)
    for match in grammar.every.finditer(code):
        args = _call_args(code, match.end() - 1)
        # Every path the call names is one it may replace; a call with none readable is one unresolved site.
        sites.extend(args or [None])
    for match in grammar.method.finditer(code):
        found = grammar.receiver.search(code[: match.start() + 1])
        sites.append(found.group(1) if found else None)
    return sites


def _site_targets(code):
    """`(literals, unresolved)` over every write site of `code`: the path literals its writes provably go to, and whether any write goes through something this reading cannot resolve."""
    literals: list[str] = []
    unresolved = False
    for target in _write_sites(code):
        text = None if target is None else _literal_text(target)
        if text is not None:
            literals.append(text)
            continue
        bound = None
        if target is not None and re.fullmatch(r"[A-Za-z_]\w*", target.strip()):
            bound = _bound_literals(target.strip(), code)
        if bound is None:
            unresolved = True
        else:
            literals.extend(bound)
    return literals, unresolved


def _literal_names_log(text):
    """Does a path literal name a round log, or spell one through a glob, a brace or the stem (an f-string's fixed text)?"""
    return _is_log(text) or _LOG_STEM in text or _word_could_name_log(text)


def _program_truncates(code, handed=False):
    """Does an interpreter program replace or remove a round log?

    Read per write site (`_site_targets`). A write to a path literal that names a log is one. A write through something UNRESOLVED (a variable bound at run time, `sys.argv[1]`, an environment value, a command handed to a shell) is one when the program could reach a log: its own text could spell one (`_program_could_name_log`, the 2026-08-19 `p.write_text(s[:i] + new)` shape), or the run was HANDED one (`handed`: an argument, an environment value, its stdin). A program whose every write goes to a named path that is not a log writes those files and no other, whatever it reads.

    shutil/os MOVE AND COPY COUNT AS WRITES on every path they name: only the destination is replaced, but telling the two apart by position across copy/copyfile/copy2/move/replace/rename is fragile (measured 2026-08-27: both returned 0 from this guard while only `write_text` and `open(..., "w")` were asked).
    """
    literals, unresolved = _site_targets(code)
    if any(_literal_names_log(text) for text in literals):
        return True
    if unresolved:
        return handed or _program_could_name_log(code)
    return False


def run(ev):
    cmd = ev.field("tool_input", "command")

    # A round-log path must appear at all, literally or as a glob or brace that could spell one (#e5b0540a: `echo pr-babysit-*.md | xargs cp /tmp/x.md` was allowed here before the walk ran), which is also what keeps the walk below off every command that cannot touch one.
    if not _could_name_log(cmd):
        return hookio.ALLOW

    # The redirects bash performs, with their operator: `>` truncates, `>>` appends (`2>&1`-style descriptor plumbing names no file).
    # A redirect target is expanded by bash too (`> agent/pr-babysit-*.md` truncates the one log it matches), and its run's directory is not on the write record, so a glob there is read by its shape.
    truncating = any(
        op in TRUNCATING_OPS and _names_log(target) and not re.fullmatch(r"\d+|-", target)
        for op, target in shellscan._analyse(cmd).writes
    )
    # The verbs it runs, behind any prefix, xargs, sh -c or find -exec.
    cwd = ev.field("cwd") or str(hookio.repo_root())
    truncating = truncating or any(_verb_truncates(r, cwd) for r in shellscan.every_run(cmd))
    # An in-process write from python, node, perl or ruby. NOT anchorable the way the shell verbs are: the 2026-08-19 incident was a heredoc where the path sat on a DIFFERENT LINE from the write call. A program that writes an UNNAMED target is refused when its OWN text could spell a round-log path (`_program_could_name_log`: the `pr-babysit` stem, or a string literal glob that meets the pattern), because that is the exact shape that destroyed the appendix; one whose text cannot spell a log writes some other file and passes, whatever else the command mentions (#e5b0540a).
    truncating = truncating or any(
        _program_truncates(code) for _family, code in WT.interpreter_programs(cmd)
    )
    # The same question of each interpreter run with what the command line HANDS it (review 1d4e1754.1): a program that takes its target from argv, the environment or stdin names no path in its text.
    if not truncating:
        for run_ in shellscan.every_run(cmd):
            code, kind = shellscan.interpreter_program(run_, cmd, cwd)
            if code is None and kind != "unjudgeable":
                continue
            # A script this walk cannot read (an earlier clause wrote it from a source it cannot follow) is every program at once: handed a log, it is refused.
            if _handed_a_log(run_, code, kind, cwd) and (
                code is None or _program_truncates(code, True)
            ):
                truncating = True
                break

    if not truncating:
        return hookio.ALLOW

    ev.warn(MESSAGE)
    return hookio.DENY
