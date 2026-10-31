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

FAILS OPEN, WITH ONE EXCEPTION. This matches on a path shape plus a write verb; anything it does not recognise runs. A guard that blocked on suspicion would be routed around, and being routed around is worse than a named residual.

THE EXCEPTION IS AN INTERPRETER PROGRAM WITH A LOG IN PLAY, and there the burden is the program's. A log is IN PLAY for a python, node, perl or ruby run when the command line hands it one (an argument, an environment value, its stdin) or when the program's own text could spell one (the `pr-babysit` stem, or a string literal glob that meets the round-log pattern in a program that is not provably inert, `_program_inert`). Such a program must be one this guard can FOLLOW: made only of reads, pure calls, and writes to literal paths that are not a log. A dynamic import or dispatch, a shell-out, a write whose target is not a literal, a method on a value the reader cannot type, or simply a call it does not know, and the program is refused. THE BOUNDARY: a program that is handed no log and whose text cannot spell one is not read at all, however it is written, which is what keeps this strictness off every ordinary script.

NAMED RESIDUAL, not pretended away: a write whose path is ASSEMBLED at runtime is partly invisible here. A verb's operand set by an earlier statement of the same command (`F=<log>; mv $F /tmp/`) is read as bash expands it; a value from the environment, and a shell glob that expands to the log are not, because the walk cannot know them. A REDIRECT onto a variable the command assigned (`L=<log>; echo x > $L`) is read as bash expands it too (#7b3f34ae). The verb's own success line is the backstop for that case: it reports the bytes kept above and below STATUS, so a session that used the verb can SEE
the appendix survived, and a session that bypassed it has no such line to point at.

=============================================================================
PORT NOTES, and the bash's own two are worth keeping because they are about what a naive reader would write instead.
=============================================================================

`grep -q ... | grep -qv ...` IS NOT THE CHECK IT READS AS, and the tee arm used to be written that way: `-q` suppresses stdout, so the downstream grep always sees empty input and its exit status says nothing whatever about the first pattern. Measured in the bash: the pipeline returns 0 on a match AND on a miss. It happened not to set the flag in practice, which is worse than
failing loudly, because it made the line look tested when the controls were passing for an unrelated reason. In Python the two tests are simply two calls, so the trap cannot recur; the record of it is here because the NEXT person to "simplify" this arm is the reader this paragraph is for.

`${RL}` BRACED, NOT `$RL`, in the bash: a `[` directly after a bare name reads
as an array subscript to shellcheck (SC1087, an error not a warning), and here the bracket opens a character class in the regex rather than an index. Python has no such ambiguity, which is why the braces are gone and the reason is not.
"""

import ast
import builtins
import fnmatch
import functools
import os
import re
import textwrap
import types
from typing import NamedTuple

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
    # #cad8d610, two live false positives on 2026-10-14: a JSDoc opener and closer held as string literals (the opener's basename is a bare double star) put a log in play, and a node program the reader cannot follow was refused though it writes only a TypeScript file. A star in a literal names files only through something that EXPANDS it, a glob or match call, a shell-out or a dynamic construct; text with none of those spells no path, however it reads.
    (
        "a node program printing a JSDoc header into a TypeScript file",
        "node -e \"const x = require('./node_modules/acorn-jsx/xhtml.js'); const lines = ['/**', ' * Entities.', ' */']; for (const k of Object.keys(x)) lines.push(k); console.log(lines.join('\\n'));\" > scripts/lib/jsx-entities.ts",
    ),
    (
        "a node program writing a JSDoc header to a literal TypeScript path",
        "node -e \"const x = require('./node_modules/acorn-jsx/xhtml.js'); const lines = ['/**', ' * Entities.', ' */']; for (const k of Object.keys(x)) lines.push(k); const out = lines.join('\\n'); require('fs').writeFileSync('scripts/lib/jsx-entities.ts', out);\"",
    ),
    # Their twins, refused: the same shapes really reach a round log, through the redirect, a literal write, a glob call, or a shell-out the walk cannot follow.
    (
        "the JSDoc printer redirected onto a log",
        "node -e \"const x = require('./node_modules/acorn-jsx/xhtml.js'); const lines = ['/**', ' * Entities.', ' */']; for (const k of Object.keys(x)) lines.push(k); console.log(lines.join('\\n'));\" > agent/pr-babysit-0831-1.md",
    ),
    (
        "the JSDoc writer onto a literal log path",
        "node -e \"const x = require('./node_modules/acorn-jsx/xhtml.js'); const lines = ['/**', ' * Entities.', ' */']; for (const k of Object.keys(x)) lines.push(k); const out = lines.join('\\n'); require('fs').writeFileSync('agent/pr-babysit-0831-1.md', out);\"",
    ),
    (
        "the JSDoc writer onto what an md glob call returns",
        "node -e \"const lines = ['/**', ' * Entities.', ' */']; const out = lines.join('\\n'); require('fs').writeFileSync(require('fs').globSync('agent/*.md')[0], out);\"",
    ),
    (
        "the JSDoc writer shelling out with an md glob",
        "node -e \"const lines = ['/**', ' * Entities.', ' */']; require('child_process').execSync('cp /dev/null agent/*.md');\"",
    ),
    # Review db54423c.1: an allowlist of expanders misses every library that expands a glob or runs a shell (shelljs, Open3, python `sh`, zx, execa, globby), and every directory listing filtered by a pattern. Each of these was refused before 81822af65, passed at it, and is refused again: only a program provably inert lets a glob literal pass.
    ("shelljs rm on an md glob", "node -e \"require('shelljs').rm('agent/*.md')\""),
    ("shelljs cp onto an md glob", "node -e \"require('shelljs').cp('/dev/null', 'agent/*.md')\""),
    (
        "ruby Open3 running a shell on an md glob",
        "ruby -e \"require 'open3'; Open3.capture2('sh', '-c', 'cp /dev/null agent/*.md')\"",
    ),
    (
        "python sh running bash on an md glob",
        "python3 -c \"import sh; sh.bash('-c', 'cp /dev/null agent/*.md')\"",
    ),
    (
        "a directory listing filtered by a log-meeting pattern",
        "python3 -c \"import os, re; [open('agent/' + n, 'w') for n in os.listdir('agent') if re.search('pr-*.md', n)]\"",
    ),
    # Review 0c516466.1 and .2: a listing or a shell-out the word lists missed. `os.fwalk` is a walk under a prefix, so `walk` is matched anywhere in a word; perl's `readpipe` is backticks as a function.
    (
        "a python fwalk filtered by a log-meeting pattern",
        "python3 -c \"import os, re; [open(os.path.join(d, n), 'w') for d, _s, fs, _fd in os.fwalk('agent') for n in fs if re.search('pr-*.md', n)]\"",
    ),
    ("perl readpipe on an md glob", "perl -e 'readpipe(\"cp /dev/null agent/*.md\")'"),
    # The inert side, both directions: a program importing only `fs` that writes an md pattern list to the file its command line names writes that file, and the same program handed a log is refused by the handed arm.
    (
        "an inert program writing an md pattern list to the file it is handed",
        "node -e \"const fs = require('fs'); fs.writeFileSync(process.argv[1], JSON.stringify(['*.md']))\" out.json",
    ),
    (
        "the same inert program handed a log",
        "node -e \"const fs = require('fs'); fs.writeFileSync(process.argv[1], JSON.stringify(['*.md']))\" agent/pr-babysit-0831-1.md",
    ),
    (
        "the same program importing an unknown module",
        "node -e \"const fs = require('fs-extra'); fs.writeFileSync(process.argv[1], JSON.stringify(['*.md']))\" out.json",
    ),
    (
        "a JSDoc opener handed to a shelljs call",
        "node -e \"const lines = ['/**', ' */']; require('shelljs').cp('/dev/null', '/**');\"",
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
    # Review 4b3f59b5.1, judged per write: every row of the first block was allowed at d15fe3f5b with the log handed. The first three name another file somewhere (that used to clear the whole program); the rest write, remove or truncate through a spelling the write test did not know, or hand the log where the handed words were not read.
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
    # Review 8b651626.1: perl's `open` puts the HANDLE first, and the handle was read as the path, so every perl write to a named file was refused beside a handed log. The first six rows were refused at f087a1b96 or pin the perl read and append beside them; the rest are the controls of the two residuals closed below.
    (
        "perl writing a named file beside the handed log",
        'perl -e \'open(my $f, ">", "out.txt"); print $f 1\' agent/pr-babysit-0831-1.md',
    ),
    (
        "perl copying the handed log into a named file",
        'perl -e \'open(my $in, "<", $ARGV[0]); open(my $f, ">", "out.txt"); print $f <$in>\' agent/pr-babysit-0831-1.md',
    ),
    (
        "perl two-argument open onto a named file",
        "perl -e 'open(F, \">out.txt\"); print F 1' agent/pr-babysit-0831-1.md",
    ),
    (
        "perl open without parentheses onto a named file",
        'perl -e \'open my $f, ">", "out.txt"; print $f 1\' agent/pr-babysit-0831-1.md',
    ),
    (
        "perl appending to the handed log",
        "perl -e 'open(my $f, \">>\", $ARGV[0]); print $f 1' agent/pr-babysit-0831-1.md",
    ),
    (
        "perl two-argument read of a named file",
        "perl -e 'open(IN, \"notes.txt\"); print <IN>' agent/pr-babysit-0831-1.md",
    ),
    (
        "str.replace on text read through a Path of the handed log",
        "python3 -c \"import sys,pathlib; s=pathlib.Path(sys.argv[1]).read_text(); print(s.replace('a','b'))\" agent/pr-babysit-0831-1.md",
    ),
    (
        "Path.replace between two named files while the handed log is read",
        "python3 -c \"import sys,pathlib; p=pathlib.Path('x.txt'); p.replace('y.txt'); print(open(sys.argv[1]).read())\" agent/pr-babysit-0831-1.md",
    ),
    (
        "getattr and __import__ are not followed, even where they reach no writer",
        "python3 -c \"import sys,os; print(getattr(os,'sep'), __import__('json').dumps(open(sys.argv[1]).read()))\" agent/pr-babysit-0831-1.md",
    ),
    (
        "a Python open on an upper-case name bound to a named file",
        "python3 -c \"import sys; F='out.txt'; open(F, 'w').write(open(sys.argv[1]).read())\" agent/pr-babysit-0831-1.md",
    ),
    # The perl forms that DO reach the log, and two residuals of the previous round taken one step: `Path.replace` and `Path.rename` on a receiver that is provably a path (their argument is replaced too), and a writer reached through a literal name (`__import__('os')`, `getattr(os, 'rem' + 'ove')`). Every python row here was allowed at f087a1b96.
    (
        "perl three-argument open onto the log by name",
        'perl -e \'open(my $f, ">", "agent/pr-babysit-0831-1.md")\'',
    ),
    (
        "perl two-argument open onto the log by name",
        "perl -e 'open(F, \">agent/pr-babysit-0831-1.md\")'",
    ),
    (
        "perl two-argument open interpolating argv",
        "perl -e 'open(F, \">$ARGV[0]\")' agent/pr-babysit-0831-1.md",
    ),
    (
        "perl open without parentheses onto argv",
        "perl -e 'open my $f, \">\", $ARGV[0]; close $f' agent/pr-babysit-0831-1.md",
    ),
    (
        "perl pipe open naming argv",
        'perl -e \'open(my $f, "|-", "tee $ARGV[0]")\' agent/pr-babysit-0831-1.md',
    ),
    (
        "Path.replace on a name bound to a Path of argv",
        "python3 -c \"import sys,pathlib; p=pathlib.Path(sys.argv[1]); p.replace('/tmp/x')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "Path.replace called on Path(argv) itself",
        "python3 -c \"import sys; from pathlib import Path; Path(sys.argv[1]).replace('/tmp/x')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "Path.replace of a named file onto argv",
        "python3 -c \"import sys,pathlib; pathlib.Path('x.txt').replace(sys.argv[1])\" agent/pr-babysit-0831-1.md",
    ),
    (
        "Path.rename of a named file onto argv",
        "python3 -c \"import sys,pathlib; pathlib.Path('x.txt').rename(sys.argv[1])\" agent/pr-babysit-0831-1.md",
    ),
    (
        "__import__('os').remove on argv",
        "python3 -c \"import sys; __import__('os').remove(sys.argv[1])\" agent/pr-babysit-0831-1.md",
    ),
    (
        "import_module('shutil').rmtree on argv",
        "python3 -c \"import sys,importlib; importlib.import_module('shutil').rmtree(sys.argv[1])\" agent/pr-babysit-0831-1.md",
    ),
    (
        "getattr on os with a concatenated literal name",
        "python3 -c \"import sys,os; getattr(os,'rem'+'ove')(sys.argv[1])\" agent/pr-babysit-0831-1.md",
    ),
    (
        "getattr on os with a name that is not a literal",
        "python3 -c \"import sys,os; n='remove'; getattr(os, n)(sys.argv[1])\" agent/pr-babysit-0831-1.md",
    ),
    (
        "a Python open on an upper-case name bound to argv",
        "python3 -c \"import sys; F=sys.argv[1]; open(F, 'w').write('')\" agent/pr-babysit-0831-1.md",
    ),
    # Round 12, the burden inverted (reviews 97a72d29.1/.2): with a log in play a program must be one this guard can FOLLOW. The first three rows are the two reviewed shapes, allowed at ca2f75c43; every python row after them was allowed there too unless its neighbour in rounds 10 and 11 says otherwise, and the `getattr`/`__import__` row above this block is the one allow row the rule turned into a refusal.
    (
        "a name bound to a string and then to a Path of argv",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys\nfrom pathlib import Path\np = 'x'\np = Path(sys.argv[1])\np.replace('/tmp/x')\nPY",
    ),
    (
        "__import__ with a concatenated module name",
        "python3 -c \"import sys; __import__('o' + 's').remove(sys.argv[1])\" agent/pr-babysit-0831-1.md",
    ),
    (
        "import_module with a concatenated module name",
        "python3 -c \"import sys,importlib; importlib.import_module('o'+'s').remove(sys.argv[1])\" agent/pr-babysit-0831-1.md",
    ),
    (
        "a Path of argv on one branch of a name",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys\nfrom pathlib import Path\np = Path('x.txt')\nif sys.argv[2:]:\n    p = Path(sys.argv[1])\np.unlink()\nPY",
    ),
    (
        "a Path class imported under another name",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys\nfrom pathlib import Path as P\nP(sys.argv[1]).replace('/tmp/x')\nPY",
    ),
    (
        "a Path of argv appended to a list and indexed back",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys, pathlib\nxs = []\nxs.append(pathlib.Path(sys.argv[1]))\nxs[0].unlink()\nPY",
    ),
    (
        "a Path of argv stored under a key and read back",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys, pathlib\nd = {}\nd['p'] = pathlib.Path(sys.argv[1])\nd['p'].write_text('')\nPY",
    ),
    (
        "a Path of argv returned by a local function",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys\nfrom pathlib import Path\ndef target():\n    return Path(sys.argv[1])\ntarget().write_text('')\nPY",
    ),
    (
        "a class built from the type of a path",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys\nfrom pathlib import Path\np = Path('x.txt')\ntype(p)(sys.argv[1]).unlink()\nPY",
    ),
    (
        "vars() subscripted for a writer",
        "python3 -c \"import sys,os; vars(os)['remove'](sys.argv[1])\" agent/pr-babysit-0831-1.md",
    ),
    (
        "globals() subscripted for a module",
        "python3 -c \"import sys,os; globals()['os'].remove(sys.argv[1])\" agent/pr-babysit-0831-1.md",
    ),
    (
        "exec of a string",
        "python3 -c \"import sys; exec('import os; os.remove(sys.argv[1])')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "compile, with nothing run",
        "python3 -c \"import sys; compile('1','x','eval')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "setattr on a module",
        "python3 -c \"import sys,os; setattr(os,'x',1)\" agent/pr-babysit-0831-1.md",
    ),
    (
        "getattr that reaches no writer",
        "python3 -c \"import sys,os; print(getattr(os.stat(sys.argv[1]),'st_size'))\" agent/pr-babysit-0831-1.md",
    ),
    (
        "os.popen",
        "python3 -c \"import sys,os; os.popen('rm ' + sys.argv[1])\" agent/pr-babysit-0831-1.md",
    ),
    (
        "os.execvp",
        "python3 -c \"import sys,os; os.execvp('rm', ['rm', sys.argv[1]])\" agent/pr-babysit-0831-1.md",
    ),
    (
        "sys.modules subscripted",
        "python3 -c \"import sys; sys.modules['os'].remove(sys.argv[1])\" agent/pr-babysit-0831-1.md",
    ),
    (
        "a subclass walk from a tuple",
        "python3 -c \"import sys; ().__class__.__base__.__subclasses__()[0](sys.argv[1], 'w')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "functools.partial of a writer",
        'python3 -c "import sys,functools,os; functools.partial(os.remove, sys.argv[1])()" agent/pr-babysit-0831-1.md',
    ),
    (
        "a writer picked out of a dict",
        "python3 -c \"import sys,os; d = {'f': os.remove}; d['f'](sys.argv[1])\" agent/pr-babysit-0831-1.md",
    ),
    (
        "a writer handed to a lambda",
        'python3 -c "import sys,os; (lambda g: g(sys.argv[1]))(os.remove)" agent/pr-babysit-0831-1.md',
    ),
    (
        "a writer chosen by a conditional",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys, os\nrm = os.remove if sys.argv[2:] else print\nrm(sys.argv[1])\nPY",
    ),
    (
        "a module this reader does not know",
        "python3 -c \"import sys, zipfile; zipfile.ZipFile(sys.argv[1], 'w')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "argparse.FileType in write mode",
        "python3 -c \"import sys, argparse; a = argparse.ArgumentParser(); a.add_argument('f', type=argparse.FileType('w')); a.parse_args()\" agent/pr-babysit-0831-1.md",
    ),
    (
        "a class",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys\nclass W:\n    def go(self, p):\n        open(p, 'w')\nW().go(sys.argv[1])\nPY",
    ),
    (
        "a star import",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys\nfrom os import *\nremove(sys.argv[1])\nPY",
    ),
    (
        "text that is not python 3",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys\nprint 'python 2', sys.argv[1]\nPY",
    ),
    (
        "a write mode defaulted in a local function",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys\ndef w(p, m='w'):\n    return open(p, m)\nw(sys.argv[1])\nPY",
    ),
    (
        "shutil.move of argv to a named file",
        "python3 -c \"import sys,shutil; shutil.move(sys.argv[1], 'gone.txt')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "a target joined onto a literal directory",
        "python3 -c \"import sys,os; open(os.path.join('agent', sys.argv[1]), 'w')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "a log name joined from literals",
        "python3 -c \"import os; open(os.path.join('agent', 'pr-babysit-0831-1.md'), 'w')\"",
    ),
    (
        "a log name concatenated onto a directory",
        "python3 -c \"n = 'pr-babysit-0831-1.md'; open('agent/' + n, 'w')\"",
    ),
    (
        "os.ftruncate on a descriptor of argv",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys, os\nfd = os.open(sys.argv[1], os.O_RDWR)\nos.ftruncate(fd, 0)\nPY",
    ),
    (
        "node: a computed member call",
        "node -e \"const fs=require('fs'); fs['rm'+'Sync'](process.argv[1])\" agent/pr-babysit-0831-1.md",
    ),
    (
        "node: a writer held in a name",
        "node -e \"const w=require('fs').writeFileSync; w(process.argv[1],'')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "node: a writer destructured under another name",
        "node -e \"const {writeFileSync: w}=require('fs'); w(process.argv[1],'')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "node: require of a name that is not a literal",
        'node -e "require(process.argv[2]).rmSync(process.argv[1])" agent/pr-babysit-0831-1.md fs',
    ),
    (
        "node: a module held under a second name",
        "node -e \"const g=require('fs'); const h=g; h.rmSync(process.argv[1])\" agent/pr-babysit-0831-1.md",
    ),
    (
        "node: a writer passed as a callback",
        "node -e \"const fs=require('fs'); [process.argv[1]].forEach(fs.unlinkSync)\" agent/pr-babysit-0831-1.md",
    ),
    ("node: new Function", "node -e \"new Function('return 1')()\" agent/pr-babysit-0831-1.md"),
    ("ruby: send", 'ruby -e "File.send(:delete, ARGV[0])" agent/pr-babysit-0831-1.md'),
    (
        "ruby: a constant held in a name",
        "ruby -e \"x = IO; x.write(ARGV[0], '')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "ruby: a method object",
        'ruby -e "ARGV.each(&File.method(:delete))" agent/pr-babysit-0831-1.md',
    ),
    (
        "ruby: a library this reader does not know",
        "ruby -e \"require 'fileutils'; FileUtils.rm(ARGV[0])\" agent/pr-babysit-0831-1.md",
    ),
    (
        "ruby: -i edits the handed file in place",
        "ruby -i -pe '$_.upcase!' agent/pr-babysit-0831-1.md",
    ),
    (
        "ruby: -i bundled with other switches",
        "ruby -pi.bak -e '$_.upcase!' agent/pr-babysit-0831-1.md",
    ),
    (
        "perl: a call through a name",
        "perl -e 'my $f = \"unlink\"; &$f($ARGV[0])' agent/pr-babysit-0831-1.md",
    ),
    (
        "perl: a call through a reference",
        "perl -e 'my $c = \\&CORE::unlink; $c->($ARGV[0])' agent/pr-babysit-0831-1.md",
    ),
    (
        "perl: a substitution that evaluates code",
        "perl -e 's/x/unlink $ARGV[0]/e for \"x\"' agent/pr-babysit-0831-1.md",
    ),
    (
        "perl: the in-place variable",
        "perl -e '$^I = \"\"; while (<>) { print uc }' agent/pr-babysit-0831-1.md",
    ),
    (
        "perl: a module this reader does not know",
        "perl -e 'use File::Copy; move($ARGV[0], \"/tmp/x\")' agent/pr-babysit-0831-1.md",
    ),
    # Allowed. The BOUNDARY rows are the same unfollowable programs with no log in play: handed another file, or beside a log that is only read by `cat`. The rest are followed with the log handed: reads, pure calls, and writes to literal paths that are not a log.
    (
        "BOUNDARY: a concatenated __import__ handed another file",
        "python3 -c \"import sys; __import__('o' + 's').remove(sys.argv[1])\" notes.txt",
    ),
    (
        "BOUNDARY: a mixed-binding Path handed another file",
        "python3 - notes.txt <<'PY'\nimport sys\nfrom pathlib import Path\np = 'x'\np = Path(sys.argv[1])\np.replace('/tmp/x')\nPY",
    ),
    (
        "BOUNDARY: a subprocess handed another file",
        "python3 -c \"import sys,subprocess; subprocess.run(['rm', sys.argv[1]])\" notes.txt",
    ),
    (
        "BOUNDARY: a class, exec and getattr handed another file",
        "python3 - notes.txt <<'PY'\nimport sys\nclass W:\n    pass\nexec('1')\ngetattr(sys, 'argv')\nPY",
    ),
    (
        "BOUNDARY: node child_process handed another file",
        "node -e \"require('child_process').execSync('ls')\" notes.txt",
    ),
    (
        "BOUNDARY: a subprocess beside a cat of the log",
        "cat agent/pr-babysit-0831-1.md; python3 -c \"import subprocess; subprocess.run(['ls'])\"",
    ),
    ("BOUNDARY: ruby -i on another file", "ruby -i -pe '$_.upcase!' notes.txt"),
    (
        "a regex search over the handed log",
        "python3 -c \"import sys,re; print(re.findall(r'round \\d+', open(sys.argv[1]).read()))\" agent/pr-babysit-0831-1.md",
    ),
    (
        "shutil.copy of the handed log to a named file",
        "python3 -c \"import sys,shutil; shutil.copy(sys.argv[1], 'backup.txt')\" agent/pr-babysit-0831-1.md",
    ),
    (
        "a Counter over the handed log",
        'python3 -c "import sys,collections; c=collections.Counter(open(sys.argv[1]).read().split()); print(c.most_common(3))" agent/pr-babysit-0831-1.md',
    ),
    (
        "a hash of the handed log",
        "python3 -c \"import sys,hashlib; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())\" agent/pr-babysit-0831-1.md",
    ),
    (
        "a with block enumerating the handed log",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys\nwith open(sys.argv[1]) as f:\n    for i, line in enumerate(f):\n        if line.startswith('## '):\n            print(i, line.strip())\nPY",
    ),
    (
        "a local function reading the path it is given",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys\ndef head(path, n=5):\n    with open(path) as f:\n        return [next(f) for _ in range(n)]\nprint(''.join(head(sys.argv[1])))\nPY",
    ),
    (
        "a sort by a lambda written to a named file",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys, datetime\nlines = open(sys.argv[1]).read().splitlines()\nrows = sorted(lines, key=lambda l: l.lower())\nout = open('sorted.txt', 'w')\nout.write('\\n'.join(rows))\nout.close()\nprint(datetime.datetime.now().isoformat(), len(rows))\nPY",
    ),
    (
        "a copy to a path joined from literals",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys, os\nname = os.path.join('out', 'copy.txt')\nos.makedirs('out', exist_ok=True)\nwith open(sys.argv[1]) as src, open(name, 'w') as dst:\n    dst.write(src.read())\nPY",
    ),
    (
        "a Path joined from literals written from the handed log",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys\nfrom pathlib import Path\nout = Path('out') / 'copy.txt'\nout.write_text(Path(sys.argv[1]).read_text())\nPY",
    ),
    (
        "argparse reading the handed log",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport argparse\np = argparse.ArgumentParser()\np.add_argument('log')\na = p.parse_args()\nprint(open(a.log).read().count('\\n'))\nPY",
    ),
    (
        "a read-only descriptor of the handed log",
        "python3 - agent/pr-babysit-0831-1.md <<'PY'\nimport sys, os\nfd = os.open(sys.argv[1], os.O_RDONLY)\nprint(os.read(fd, 100))\nos.close(fd)\nPY",
    ),
    (
        "node: an arrow filter over the handed log",
        "node -e \"const fs=require('fs'); const t=fs.readFileSync(process.argv[1],'utf8').split('\\n').filter(l => l.startsWith('#')); console.log(t.length)\" agent/pr-babysit-0831-1.md",
    ),
    (
        "node: a destructured reader",
        "node -e \"const {readFileSync}=require('fs'); console.log(readFileSync(process.argv[1],'utf8').length)\" agent/pr-babysit-0831-1.md",
    ),
    (
        "ruby: gsub with a pattern over the handed log",
        "ruby -e \"s = File.read(ARGV[0]); puts s.gsub(/a/, 'b').lines.first\" agent/pr-babysit-0831-1.md",
    ),
    (
        "ruby: a block writing a named file from the handed log",
        "ruby -e \"File.open('out.txt', 'w') { |f| f.write(File.read(ARGV[0])) }\" agent/pr-babysit-0831-1.md",
    ),
    (
        "ruby: an option before the program that is not -i",
        "ruby -I lib -e 'puts File.read(ARGV[0])' agent/pr-babysit-0831-1.md",
    ),
    ("perl: -ne with a pattern", "perl -ne 'print if /round/' agent/pr-babysit-0831-1.md"),
    ("perl: -pe with a substitution to stdout", "perl -pe 's/a/b/g' agent/pr-babysit-0831-1.md"),
    (
        "perl: slurping the handed log into an array",
        'perl -e \'open(my $f, "<", $ARGV[0]) or die; my @l = <$f>; print scalar(@l), "\\n"\' agent/pr-babysit-0831-1.md',
    ),
    (
        "perl: the >| mode onto a named file is not a pipe",
        'perl -e \'open(my $f, ">|", "out.txt"); print $f 1\' agent/pr-babysit-0831-1.md',
    ),
    (
        "perl: a two-argument open of a file named w is a read",
        "perl -e 'open(FH, \"w\"); print <FH>' agent/pr-babysit-0831-1.md",
    ),
    # Reviews 801bbb46.1/.2: a quote or a `#` that is not a string or a comment in the language must not blank what follows it. Every row was allowed at ba0bd0df9, the unlink or delete hidden behind the shape its label names (`_extent_unknown`).
    (
        "perl: the list separator variable is not a string opener",
        'perl -e \'local $" = ","; my $c = \\&CORE::unlink; $c->($ARGV[0])\' agent/pr-babysit-0831-1.md',
    ),
    (
        "perl: a quote-like operator on a # delimiter is not a comment",
        "perl -e 'my @x = qw#a#; my $c = \\&CORE::unlink; $c->($ARGV[0])' agent/pr-babysit-0831-1.md",
    ),
    (
        "perl: the postmatch variable is not a string opener",
        "perl -e \"my \\$p = \\$'; my \\$c = \\\\&CORE::unlink; \\$c->(\\$ARGV[0]); print ''\" agent/pr-babysit-0831-1.md",
    ),
    (
        "perl: the old package separator is not a string opener",
        "perl -e \"\\$main'x = 1; my \\$c = \\\\&CORE::unlink; \\$c->(\\$ARGV[0]); print ''\" agent/pr-babysit-0831-1.md",
    ),
    (
        "perl: a pattern holding a quote",
        'perl -e \'print if /"/; my $c = \\&CORE::unlink; $c->($ARGV[0]); print ""\' agent/pr-babysit-0831-1.md',
    ),
    (
        "perl: a heredoc body holding a quote",
        'perl -e \'print <<EOT;\nA"\nEOT\nmy $c = \\&CORE::unlink; $c->($ARGV[0]); print ""\' agent/pr-babysit-0831-1.md',
    ),
    (
        "ruby: a character literal is not a string opener",
        'ruby -e \'x = ?"; File.send(:delete, ARGV[0]); y = ""\' agent/pr-babysit-0831-1.md',
    ),
    (
        "ruby: a percent literal holding a quote",
        'ruby -e \'x = %(1"); File.send(:delete, ARGV[0]); y = ""\' agent/pr-babysit-0831-1.md',
    ),
    (
        "ruby: the loaded-features variable is not a string opener",
        'ruby -e \'x = $"; File.send(:delete, ARGV[0]); y = ""\' agent/pr-babysit-0831-1.md',
    ),
    (
        "ruby: a pattern holding a quote",
        'ruby -e \'x = ARGV[0].split(/"/); File.send(:delete, ARGV[0]); y = ""\' agent/pr-babysit-0831-1.md',
    ),
    (
        "node: a pattern holding a quote",
        "node -e \"const t='a'.split(/'/); new Function(process.argv[1])(); const u=''\" agent/pr-babysit-0831-1.md",
    ),
    # Their controls: the plain reads stay followed.
    (
        "perl: a plain read of the handed log",
        "perl -e 'open(my $f, \"<\", $ARGV[0]) or die; print <$f>' agent/pr-babysit-0831-1.md",
    ),
    (
        "ruby: a plain read of the handed log",
        'ruby -e "puts File.read(ARGV[0])" agent/pr-babysit-0831-1.md',
    ),
    # Reviews 012e1b7b.1/.2/.3: `_extent_unknown` was a delimiter LIST with holes. It is the rule now (any non-word, non-space delimiter after a quote-like word; `<<` then optional space then a quote or identifier). The first three rows are the reviewed holes, allowed at cc5dbd0a3; the rest are siblings.
    (
        "ruby: percent on a dash delimiter",
        'ruby -e \'x = %-"-; y = File.send(:delete, ARGV[0]); z = ""\' agent/pr-babysit-0831-1.md',
    ),
    (
        "perl: qw on a comma delimiter",
        'perl -e \'my @q = qw,",; my $c = \\&CORE::unlink; $c->($ARGV[0]); print ""\' agent/pr-babysit-0831-1.md',
    ),
    (
        "perl: heredoc with a space before the quoted tag",
        'perl -e \'print << "EOT";\nA"\nEOT\nmy $c = \\&CORE::unlink; $c->($ARGV[0]); print ""\' agent/pr-babysit-0831-1.md',
    ),
    (
        "ruby: percent on an equals delimiter",
        'ruby -e \'x = %="=; y = File.send(:delete, ARGV[0]); z = ""\' agent/pr-babysit-0831-1.md',
    ),
    (
        "ruby: a typed percent on a dash delimiter",
        'ruby -e \'x = %Q-"-; y = File.send(:delete, ARGV[0]); z = ""\' agent/pr-babysit-0831-1.md',
    ),
    (
        "perl: m on a comma delimiter holding a quote",
        'perl -e \'print 1 if m,",; my $c = \\&CORE::unlink; $c->($ARGV[0]); print ""\' agent/pr-babysit-0831-1.md',
    ),
    (
        "perl: s on an equals delimiter holding a quote",
        'perl -e \'my $x="z"; $x =~ s=z="=; my $c = \\&CORE::unlink; $c->($ARGV[0]); print ""\' agent/pr-babysit-0831-1.md',
    ),
    (
        "ruby: a tilde heredoc body holding a quote",
        'ruby -e \'x = <<~EOS\n  a"\nEOS\nFile.send(:delete, ARGV[0]); y = ""\' agent/pr-babysit-0831-1.md',
    ),
    # Their controls are the two plain reads listed above (a52292e4.3).
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


# A PROGRAM IS INERT ONLY WHEN IT IS PROVABLY SO (review db54423c.1). The first version of this arm (81822af65) listed the things that EXPAND a glob literal and let a program holding none of them pass, and every library it did not list became a bypass: shelljs `rm('agent/*.md')`, ruby `Open3`, python `sh`, zx, execa, globby, and a directory listing filtered by the literal as a pattern. The direction is now the other one: a glob literal puts a log in play UNLESS every module the program imports is on a short inert list and its text holds none of the constructs below.
# The modules whose import alone cannot expand a glob or run a shell: what they offer that could (`os.system`, `fs.globSync`, `Path.glob`, `os.listdir`) is named by a construct below, so the call still makes the program live.
_INERT_MODULES = {
    "python": frozenset(
        (
            "sys",
            "os",
            "os.path",
            "posixpath",
            "json",
            "re",
            "io",
            "string",
            "textwrap",
            "math",
            "collections",
            "itertools",
            "functools",
            "datetime",
            "time",
            "typing",
            "pathlib",
        )
    ),
    "js": frozenset(("fs", "node:fs", "path", "node:path", "os", "node:os", "util", "node:util")),
    "ruby": frozenset(("json", "set", "date", "time")),
    "perl": frozenset(("strict", "warnings", "utf8", "feature")),
}
# What makes a program LIVE whatever it imports, matched anywhere in its text, inside literals too, so a mention over-counts life: a shell-out (`system`, `exec*`, `spawn*`, `popen`, a backtick, perl `qx` and `readpipe`, ruby `%x`), a computed name (`eval`, `getattr`, `__import__`, `Function`, `send`, `const_get`, perl `&{...}` and `->$name`), a glob or match call (`glob`, `fnmatch`, `match`), and a directory listing a pattern can filter (`listdir`, `scandir`, `walk` with every prefixed form such as `os.fwalk` and `walkSync`, `iterdir`, `readdir`, `opendir`, ruby `Dir`, `children`).
_SHELL_OR_NAME = (
    r"system|exec|spawn|popen|subprocess|child_process|`|\bqx\b|%x|readpipe|"
    r"eval|getattr|setattr|__import__|importlib|\bvars\b|locals|\bcompile\b|\bFunction\b|"
    r"\bsend\b|const_get|instance_|\bmethod\b|&\s*[{$]|->\s*\$"
)
_GLOB_CALL = r"glob|fnmatch|match"
_LISTING = r"listdir|scandir|walk|iterdir|readdir|opendir|\bDir\b|children|each_child|\bFind\b"
_LIVE = re.compile(f"{_SHELL_OR_NAME}|{_GLOB_CALL}|{_LISTING}")
# Perl and ruby open a PIPE through a mode or a leading or trailing `|` in a string (`open(F, "ls *.md |")`), and perl's `<*.md>` is a glob with no call at all.
_LIVE_PERL_RUBY = re.compile(r"['\"]\s*-?\||\|-?\s*['\"]|<[^<>\n]*[*?\[{][^<>\n]*>")
_IMPORT_WORDS = {
    "js": re.compile(r"\b(?:require|import)\b"),
    "ruby": re.compile(r"\b(?:require|require_relative|load|autoload)\b"),
    "perl": re.compile(r"\b(?:use|require|no|do)\b"),
}
_IMPORT_FORMS = {
    "js": re.compile(
        r"\brequire\s*\(\s*(['\"])([^'\"]+)\1\s*\)|\bimport\s+(?:[\w$*{}\s,]+?\s+from\s+)?(['\"])([^'\"]+)\3"
    ),
    "ruby": re.compile(r"\brequire\s*\(?\s*(['\"])([^'\"]+)\1"),
    "perl": re.compile(r"\buse\s+()([\w:]+)"),
}


def _imports_inert(code, family):
    """Does every import of the program name an inert module (`_INERT_MODULES`)? Python is read by its syntax tree (a relative import, or text that does not parse, is not inert); the other languages by their import words, each of which must be one plain import of a listed module. A language with no list is never inert."""
    if family == "python":
        try:
            tree = ast.parse(code)
        except (SyntaxError, ValueError):
            return False
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level or node.module is None:
                    return False
                names = [node.module]
            else:
                continue
            if any(name not in _INERT_MODULES["python"] for name in names):
                return False
        return True
    lang = "js" if family in _JS_FAMILIES else family
    if lang not in _IMPORT_FORMS:
        return False
    forms = list(_IMPORT_FORMS[lang].finditer(code))
    if len(forms) != len(_IMPORT_WORDS[lang].findall(code)):
        return False
    return all((m.group(2) or m.group(4)) in _INERT_MODULES[lang] for m in forms)


def _program_inert(code, family):
    """Is the program provably unable to turn a glob literal into file names? Its imports are all inert, and its text holds nothing in `_LIVE` (nor, for perl and ruby, a pipe open or a `<...>` glob)."""
    if _LIVE.search(code):
        return False
    if family in ("perl", "ruby") and _LIVE_PERL_RUBY.search(code):
        return False
    return _imports_inert(code, family)


# A COMMENT DELIMITER HELD AS TEXT (#cad8d610). A generator that prints a JSDoc header holds `'/` `**'` and `' */'` as strings; the opener's basename is a bare double star, which meets the round-log pattern. Such a literal is text, not a glob, when it is EXACTLY a delimiter, sits only inside list brackets or the arguments of a print, log or append call, and the program holds no shell-out, computed name or glob call that could take it as a pattern.
_DELIMITERS = frozenset(("/**", "/*", "*/", " */", " * ", " *"))
_TEXT_CALLS = frozenset(
    (
        "print",
        "log",
        "info",
        "warn",
        "error",
        "debug",
        "puts",
        "say",
        "printf",
        "write",
        "push",
        "append",
    )
)
_NOT_TEXT = re.compile(f"{_SHELL_OR_NAME}|{_GLOB_CALL}")
_LEXEME = re.compile(r"'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"|`(?:[^`\\]|\\.)*`|[()\[\]{}]")


def _delimiter_as_text(code, start):
    """Is the literal at `start` placed where it can only be text: every parenthesis around it the argument list of a `_TEXT_CALLS` call, and the innermost bracket a list or such a call? A top-level binding (`p = '/` `**'`) is not, since the name can be handed anywhere."""
    stack: list[tuple[str, str]] = []
    for m in _LEXEME.finditer(code, 0, start):
        lexeme = m.group(0)
        if lexeme in "([{":
            callee = (
                re.search(r"([A-Za-z_$][\w$]*)\s*$", code[: m.start()]) if lexeme == "(" else None
            )
            stack.append((lexeme, callee.group(1) if callee else ""))
        elif lexeme in ")]}" and stack:
            stack.pop()
    if not stack or stack[-1][0] == "{":
        return False
    return all(opener != "(" or callee in _TEXT_CALLS for opener, callee in stack)


# A GLOB LITERAL PUTS A LOG IN PLAY ONLY WHERE IT CAN REACH THE LOG'S DIRECTORY (#63109cf2). A round log is `agent/pr-babysit-<branch>.md` (`reports/` for the pre-edit guard's copy), and every glob made only of classes and stars meets its name: the regex `[A-Za-z_][A-Za-z0-9_]*` in a python heredoc that edits a guard, or a test script that slices and
# writes an unrelated file, was refused as a round-log truncation (rc 2) with no log anywhere near it. A glob literal now counts when one of its words has a directory part whose last segment can be a log directory (`agent/*.md`, `*/x.md`, any `**`), or has none (or `.`/`..`) and either holds a fixed character of its own (`*.md`, `pr-*`: a file name's shape, not a regex's) or the program or the command around it spells a log directory as a whole path word (`os.listdir('agent')`, `cd agent`), or the run's own directory is one.
_LOG_DIRS = ("agent", "reports")
_SPELLS_LOG_DIR = re.compile(r"(?<![\w.-])(?:agent|reports)/?(?=['\"`\s;)&|,]|\Z)")


def _recursive_reaches_log_dir(alt, context=""):
    """Can a `**` glob descend into a round-log directory? A `.` or `..` segment ANYWHERE in the glob counts (it climbs out of the fixed tree, even after the `**`). Otherwise only from where its fixed directory prefix (the whole segments before the first glob character) leaves the log directories reachable: no prefix, an absolute or `~` one, one holding `.` or `..`, one whose first segment can be a log directory (`agent/**`, `reports/**`), or any prefix in a program or command that changes directory with `chdir` (`os.chdir('/')` then `home/u/console/**`).

    #3df07b02: a python heredoc that only printed a call holding `workers/account/src/telemetry/**` as a declared-ownership string was refused as a round-log truncation (rc 2); `**` under a fixed relative directory that is not a log directory walks only that tree. NAMED RESIDUAL: a directory named `agent` nested inside such a tree, and a shell `cd` to an ancestor of the repository before the program runs.
    """
    if alt.startswith(("/", "~")) or re.search(r"chdir", context):
        return True
    # A `.` or `..` segment ANYWHERE climbs out of the fixed tree, including one after the `**` (`workers/**/../../agent/pr-*.md`), so only the prefix check below would miss it.
    if any(s in (".", "..") for s in alt.split("/")):
        return True
    head = re.split(r"[*?\[{]", alt, maxsplit=1)[0]
    fixed = [s for s in head.split("/")[:-1] if s]
    if not fixed or any(s in (".", "..") for s in fixed):
        return True
    return any(fnmatch.fnmatchcase(d, fixed[0]) for d in _LOG_DIRS)


def _glob_reaches_log_dir(literal, context):
    """Can the glob `literal` name a file in a round-log directory? `context` is the text a bare glob's directory is read from: the program, the command around it and the run's directory (the comment above)."""
    for token in literal.split():
        for alt in shellscan._brace_alternatives(token):
            base = alt.rsplit("/", 1)[-1]
            if not (any(ch in base for ch in _GLOB) and _glob_meets_log(base)) and not re.search(
                RL, alt
            ):
                continue
            if "**" in alt:
                if _recursive_reaches_log_dir(alt, context):
                    return True
                continue
            parent = alt.rsplit("/", 1)[0] if "/" in alt else "."
            segment = parent.rsplit("/", 1)[-1]
            if segment in (".", ".."):
                # A bare glob that holds a character of its own (`*.md`, `pr-*`) is a file name's shape; one made only of classes and stars (`[A-Za-z_][A-Za-z0-9_]*`) is a regex's, and reaches a log only where a log directory is spelled.
                literal = any(e is not None and len(e) == 1 for e in _glob_elements(base))
                if literal or _SPELLS_LOG_DIR.search(context):
                    return True
            elif any(fnmatch.fnmatchcase(d, segment) for d in _LOG_DIRS):
                return True
    return False


def _program_could_name_log(code, family="python", context=None):
    """Could an interpreter program's own text spell a round-log path? It names the round-log stem (`pr-babysit`, in a literal or an f-string alike), or one of its STRING LITERALS is a glob or brace that can meet the round-log pattern (`glob.glob('agent/*.md')`) in a program that is not provably inert (`_program_inert`). Code outside a literal is never read for globs: `3 * 4`, `from os import *` and `r']*'` are Python, not paths (#e5b0540a's false positive, reported live by w2).

    INERT IS PROVEN, NEVER PRESUMED (review db54423c.1). A glob literal names files only through something that expands it, and the set of things that can is open: a library (shelljs, Open3, python `sh`, zx, execa, globby), a shell-out, a computed name, a directory listing the literal filters. So a glob literal counts unless every import is on a short inert list and the text holds none of those constructs; an unknown module is enough to keep the log in play, and the program is then read by `_follow`, which refuses what it cannot follow.

    ONE NARROW EXEMPTION, for #cad8d610: a literal that is exactly a comment delimiter, held as list text or printed, in a program with no shell-out, computed name or glob call (`_delimiter_as_text`). The two live generators it was found on require a module from `node_modules` and so are not inert; they pass on this exemption alone. NAMED RESIDUAL: a delimiter placed in a list and later read back out of it as a pattern by a library this text does not name, a glob ASSEMBLED at runtime, and a module name assembled at runtime.
    """
    if _LOG_STEM in code:
        return True
    # Every single- or double-quoted string literal, escapes kept (Python, shell and JS alike): an EXTRACTOR over program text the walk already chose, so it is local here rather than a module pattern a sentence could be probed against.
    meeting = [
        m
        for m in re.finditer(r"'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"", code)
        if _word_could_name_log(m.group(0)[1:-1])
        and _glob_reaches_log_dir(m.group(0)[1:-1], code + "\n" + (context or ""))
        and not (
            m.group(0)[1:-1] in _DELIMITERS
            and not _NOT_TEXT.search(code)
            and _delimiter_as_text(code, m.start())
        )
    ]
    return bool(meeting) and not _program_inert(code, family)


_redirects = shellscan.analysis_redirects


def _shell_words(cmd):
    """The shell words a truncating arm judges: every redirect target, and the words (with what xargs appends) of each `mv`, `truncate`, `cp`, `dd`, `tee` and in-place editor bash runs. For an interpreter run, its arguments other than the inline program, and its stdin feed. Interpreter PROGRAM TEXT is not among them."""
    words = [target for _op, target in _redirects(shellscan._analyse(cmd))]
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


def _log_context(cmd, cwd):
    """The text a bare glob's directory is read from beside the program's own (`_glob_reaches_log_dir`): the command, and the last segment of the directory it runs in."""
    return "%s\n%s" % (cmd, os.path.basename(str(cwd or "").rstrip("/")))


def _could_name_log(cmd, cwd=None):
    """The prefilter. A command passes when it names the round-log stem at all (`pr-babysit`), when one of its SHELL WORDS that a truncating arm judges holds a glob or brace that could spell a log (`_shell_words`, `_word_could_name_log`), or when an interpreter program's text could spell one (`_program_could_name_log`). A glob is put to the round-log pattern's automaton, never to the disk.

    SHELL WORDS, NEVER PROGRAM TEXT (#e5b0540a, live false positive reported by w2). The first version tokenised the whole command, so a lone `*` anywhere (`3 * 4` in a Python heredoc) met the pattern, the program's write through a variable then failed closed, and every Python heredoc that wrote a file and multiplied was refused.
    """
    if _LOG_STEM in cmd:
        return True
    if not any(ch in cmd for ch in "*?[{"):
        return False
    if any(_word_could_name_log(w) for w in _shell_words(cmd)):
        return True
    return any(
        _program_could_name_log(code, family, _log_context(cmd, cwd))
        for family, code in WT.interpreter_programs(cmd)
    )


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
# TWO READERS, ONE RULE. A program with a log in play (see the header) is refused unless it can be FOLLOWED. A python program is parsed and walked (`_PythonReader`); a node, perl or ruby one has its write sites read by the patterns below and every other word checked against what that language's reader knows (`_follow_words`).
#
# STILL NOT READ, and named rather than pretended away: a DIRECTORY handed in place of the log (`os.listdir(sys.argv[1])` over `agent`, then a write to a literal name inside it is still a literal that is not a log; a write through the listed names is unresolved and refused), a log name assembled from pieces when no log is handed and the stem is never whole in the text (the prefilter never opens such a command), and a path the program reads out of a file when no log is in play.
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
        # Methods that replace or remove the path they are called ON. `rename` also replaces the path it is GIVEN, so its arguments are sites too.
        method=re.compile(r"\.(?:write_text|write_bytes|unlink|truncate|rmdir|touch|rename)\("),
        # perl's `open` written without parentheses: a handle, a comma, a quoted mode.
        bare_open=re.compile(r"(?<![\w$.])open\s+(?=(?:(?:my|local|our)\s+)?[$*]?\w+\s*,\s*['\"])"),
        # No readable target at all: a raw descriptor flag, a command handed to a shell, code built at run time, the perl and ruby calls written without parentheses, and a writer passed around as a value rather than called.
        blind=re.compile(
            r"O_TRUNC|\bos\.system\(|\bsubprocess\.|\bexecSync\(|\bchild_process\b|\bspawnSync\(|\bsystem\(|`[^`\n]*`|\bexec\(|\beval\(|(?<![\w.$])(?:unlink|rename|truncate)\s+[$@'\"]|\bFile\.(?:write|delete|truncate|unlink|open)\s+[^\s(=]|\b(?:os\.(?:remove|unlink|truncate|rename|replace)|shutil\.(?:copy|copyfile|copy2|move|rmtree))\b(?!\s*\()|[=(,]\s*open\s*[,);\n]"
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


def _perl_open(args):
    """The write sites of a perl `open`, or None when its arguments cannot be read. Perl puts the HANDLE first (review 8b651626.1: the handle was read as the path, so `open(my $f, ">", "out.txt")` was an unresolved write and was refused beside a handed log). The path is the third argument, or the rest of the second in the two-argument form (`open(F, ">out.txt")`). A read (`<`, or no mode at all: `open(FH, "w")` reads a file named `w`, review 97a72d29.5) and an append (`>>`) are no site; a pipe is a command, with no readable target. `>|` is not a pipe (review 97a72d29.3): it is read as the write to the named file it looks like."""
    if len(args) < 2 or not _grammar().string.fullmatch(args[1]):
        return None
    if not re.fullmatch(r"(?:(?:my|local|our)\s+)?[$*]\w+|[A-Z][A-Z0-9_]*", args[0]):
        return None
    body = _string_body(args[1])[1].strip()
    if body.startswith(("|", "-|")) or (body.endswith("|") and body[:1] not in "<>+"):
        return [None]
    mode = re.match(r"\+?[<>]{1,2}\|?", body)
    if mode is None:
        return []
    if mode.group(0).startswith(">>") or not (">" in mode.group(0) or "+" in mode.group(0)):
        return []
    interpolating = args[1].startswith('"')
    if len(args) >= 3:
        target = args[2]
        if (
            _grammar().string.fullmatch(target)
            and target.startswith('"')
            and re.search(r"[$@]", target)
        ):
            return [None]
        return [target]
    rest = body[mode.end() :].strip()
    if not rest or re.search(r"['\\]", rest) or (interpolating and re.search(r"[$@]", rest)):
        return [None]
    return ["'%s'" % rest]


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


def _write_sites(code, family):
    """`(sites, spans)` for a node, perl or ruby program: every expression it writes THROUGH (None for a site whose target this reading cannot lift out), and where in `code` the callee of each call it read sits, so the word check that follows does not meet it again."""
    grammar = _grammar()
    sites: list[str | None] = [None for _ in grammar.blind.finditer(code)]
    spans: list[tuple[int, int]] = []
    for match in grammar.opener.finditer(code):
        args = _call_args(code, match.end() - 1)
        before = code[: match.start()]
        on = None
        start = match.start()
        if before.endswith("."):
            found = grammar.receiver.search(before)
            on = found.group(1) if found else ""
            if found and on in _OPEN_MODULES:
                start = found.start(1)
        spans.append((start, match.end() - 1))
        if args is None:
            sites.append(None)
        elif family == "perl":
            perl = _perl_open(args) if on is None else None
            sites.extend([None] if perl is None else perl)
        elif on is None or on in _OPEN_MODULES:
            target = _keyword(args, "file") or _positional(args, 0)
            # A ruby `open("|cmd")` runs a command.
            piped = target is not None and target.strip("'\"").startswith("|")
            if piped:
                sites.append(None)
            elif _mode_writes(_keyword(args, "mode") or _positional(args, 1), code):
                sites.append(target)
        elif _mode_writes(_keyword(args, "mode") or _positional(args, 0), code):
            sites.append(on or None)
    for match in grammar.first.finditer(code):
        args = _call_args(code, match.end() - 1)
        sites.append(args[0] if args else None)
        spans.append((match.start(), match.end() - 1))
    for match in grammar.every.finditer(code):
        args = _call_args(code, match.end() - 1)
        # Every path the call names is one it may replace; a call with none readable is one unresolved site.
        sites.extend(args or [None])
        spans.append((match.start(), match.end() - 1))
    for match in grammar.bare_open.finditer(code):
        # The statement's own words, up to where perl ends it.
        words = re.split(r";|\n|\bor\b|\|\|", code[match.end() :], maxsplit=1)[0]
        args = _call_args("(%s)" % words, 0)
        perl = _perl_open(args) if args else None
        sites.extend([None] if perl is None else perl)
        spans.append((match.start(), match.start() + 4))
    for match in grammar.method.finditer(code):
        found = grammar.receiver.search(code[: match.start() + 1])
        sites.append(found.group(1) if found else None)
        sites.extend(_call_args(code, match.end() - 1) or [None])
        spans.append((match.start(), match.end() - 1))
    return sites, spans


def _site_targets(code, family):
    """`(literals, unresolved, spans)` over every write site of a node, perl or ruby program: the path literals its writes provably go to, whether any write goes through something this reading cannot resolve, and the spans of the callees read."""
    literals: list[str] = []
    unresolved = False
    sites, spans = _write_sites(code, family)
    for target in sites:
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
    return literals, unresolved, spans


# --------------------------------------------------------------------------- a python program, FOLLOWED ---------------------------------------------------------------------------
#
# THE BURDEN IS ON THE PROGRAM (reviews 97a72d29.1/.2, coordinator ruling round 12). Rounds 10 and 11 listed write idioms and the reviewer kept finding the next spelling (`__import__('o' + 's')`, a name bound twice). A python program in play is now PARSED (`ast`) and walked with a small set of value kinds, and it passes only when every call in it is one this reader knows: a read, a pure function, or a write whose target is a string this reader can spell. Anything else (a call it does not know, a method on a value it cannot type, a class, a decorator, a star import, text that does not parse) is NOT FOLLOWED, and a program that is not followed is refused while a log is in play.
#
# VALUE KINDS. `data` is a string, a number, or a container or parsed document of them: no method of a data value replaces a file, so `s.replace('a', 'b')` and `xs.remove(x)` are free. `path` is a `pathlib` object and `handle` an open file: both carry the literal strings they may name, or None when that is not known. `func` and `module` are a callable or module under its canonical dotted name, so `w = open` and `from os import remove` are followed to what they call. `unk` is everything else. A NAME HOLDS THE JOIN OF EVERY BINDING IT EVER GETS, anywhere in the program: bound once to a string and once to a path it is `unk`, and a method on `unk` is not followed.
def _words(text: str) -> frozenset[str]:
    """A word table, written as one line of words."""
    return frozenset(text.split())


class _V(NamedTuple):
    kind: str
    lits: frozenset[str] | None = None


_DATA = _V("data")
_UNK = _V("unk")
_MAX_LITS = 16


def _vjoin(a: _V | None, b: _V | None) -> _V | None:
    """The least value both could be. None is "no binding seen yet" and joins as nothing."""
    if a is None or b is None:
        return b if a is None else a
    if a.kind != b.kind:
        return _UNK
    if a.kind in ("func", "module"):
        return a if a.lits == b.lits else _UNK
    if a.lits is None or b.lits is None:
        return _V(a.kind)
    lits = a.lits | b.lits
    return _V(a.kind, lits if len(lits) <= _MAX_LITS else None)


def _named(kind: str, name: str) -> _V:
    return _V(kind, frozenset((name,)))


# Modules a bare name is taken to be when the program never imports it (a heredoc fragment), and what `import` binds.
_PY_SUBMODULES = frozenset(("os.path", "urllib.parse", "xml.etree", "xml.etree.ElementTree"))
# Every function of these returns data and replaces no file.
_PY_PURE_MODULES = _words(
    "json re math time datetime string textwrap hashlib base64 binascii difflib fnmatch statistics pprint html urllib.parse unicodedata os.path posixpath struct getopt shlex glob tomllib keyword calendar decimal fractions uuid traceback csv platform locale warnings zlib secrets numbers array"
)
# Functions of these hand back what they were given (a container, an iterator, a copy), so a path that goes in comes out.
_PY_FLOW_MODULES = _words(
    "itertools collections copy functools heapq random contextlib typing bisect"
)
_PY_PURE_FUNCS = _words(
    "yaml.safe_load yaml.safe_load_all yaml.safe_dump sys.exit sys.getsizeof sys.getdefaultencoding sys.intern sys.exc_info sys.getrecursionlimit sys.setrecursionlimit codecs.encode codecs.decode io.StringIO io.BytesIO io.TextIOWrapper argparse.ArgumentParser argparse.Namespace shutil.which shutil.get_terminal_size shutil.disk_usage os.listdir os.scandir os.walk os.stat os.lstat os.getcwd os.getenv os.getpid os.cpu_count os.fspath os.access os.readlink os.makedirs os.mkdir os.close os.read os.write os.isatty os.get_terminal_size os.urandom os.fsync os.strerror os.getuid os.uname os.fstat os.lseek os.fsencode os.fsdecode"
)
_PY_SCALAR_BUILTINS = _words(
    "print len str repr int float bool bytes bytearray range dir sum any all abs round ord chr hex oct bin isinstance issubclass hasattr callable format hash id divmod pow exit quit input ascii slice"
)
_PY_FLOW_BUILTINS = _words(
    "list tuple set frozenset dict sorted reversed iter next enumerate zip filter map min max type"
)
_PY_TYPES = _words("str bytes list dict set tuple int float bool frozenset")
# Module attributes that are values, not calls.
_PY_HANDLES = {"sys.stdin": "<stdin>", "sys.stdout": "<stdout>", "sys.stderr": "<stderr>"}
_PY_DATA_ATTRS = _words(
    "sys.argv sys.platform sys.version sys.version_info sys.path sys.maxsize sys.executable os.environ os.sep os.linesep os.name os.pathsep os.curdir os.pardir os.extsep"
)
_PY_PATH_CTORS = _words(
    "pathlib.Path pathlib.PurePath pathlib.PosixPath pathlib.PurePosixPath pathlib.WindowsPath"
)
_PY_OPENERS = frozenset(("open", "io.open", "codecs.open", "builtins.open"))
# Calls that replace or remove a file, with the positions of the arguments they destroy. A copy destroys only where it lands; a move or a rename also removes where it came from.
_PY_WRITERS = {
    "os.remove": (0,),
    "os.unlink": (0,),
    "os.truncate": (0,),
    "os.ftruncate": (0,),
    "os.rmdir": (0,),
    "os.removedirs": (0,),
    "shutil.rmtree": (0,),
    "os.rename": (0, 1),
    "os.renames": (0, 1),
    "os.replace": (0, 1),
    "shutil.move": (0, 1),
    "shutil.copy": (1,),
    "shutil.copyfile": (1,),
    "shutil.copy2": (1,),
    "shutil.copytree": (1,),
    "os.link": (1,),
    "os.symlink": (1,),
}
_PY_PATH_SAME = frozenset(("resolve", "absolute", "expanduser"))
_PY_PATH_DERIVED = _words("with_suffix with_name with_stem joinpath relative_to iterdir glob rglob")
_PY_PATH_READS = _words(
    "read_text read_bytes exists is_file is_dir is_symlink is_absolute stat lstat as_posix as_uri match samefile mkdir"
)
_PY_PATH_WRITES = _words("write_text write_bytes unlink touch rmdir symlink_to hardlink_to link_to")
_PY_HANDLE_METHODS = _words(
    "read readline readlines close seek tell fileno flush write writelines isatty readable writable seekable detach reconfigure peek readinto __enter__ __exit__"
)
_PY_MUTATORS = _words("append extend insert add update setdefault appendleft extendleft put push")
_PY_IMPLICIT_MODULES = _words(
    "os sys shutil pathlib json re io glob math time datetime collections itertools functools string textwrap subprocess codecs csv argparse"
)


def _is_exception(name: str) -> bool:
    """A builtin exception class: constructing one is pure."""
    cls = getattr(builtins, name, None)
    return isinstance(cls, type) and issubclass(cls, BaseException)


def _mode_replaces(mode: str) -> bool:
    """Does one literal `open` mode replace content? `w`, `x` and `+` do; a read and an append do not."""
    return any(ch in mode for ch in "wx+")


class _PythonReader:
    """One walk of a parsed python program. `sites` are the targets of its writes (the literal strings each may name, or None), `lost` is why it could not be followed."""

    def __init__(self, tree: ast.AST) -> None:
        self.tree = tree
        self.env: dict[str, _V] = {}
        self.defs: dict[str, ast.FunctionDef | ast.Lambda] = {}
        self.rets: dict[str, _V] = {}
        self.changed = False
        self.final = False
        self.sites: list[frozenset[str] | None] = []
        self.lost: list[str] = []

    # ---- driving ----
    def read(self) -> None:
        """Walk to a fixed point twice: first with an unbound name as "nothing yet" (so a use above its binding does not poison it), then with what is still unbound as `unk`."""
        for final in (False, True):
            self.final = final
            for _ in range(24):
                self.changed = False
                self.sites, self.lost = [], []
                self.block(getattr(self.tree, "body", []))
                if self.lost:
                    # What is lost stays lost: bindings only ever widen, so a later walk cannot follow it after all.
                    return
                if not self.changed:
                    break
            else:
                self.lost.append("the walk did not settle")

    def bind(self, name: str, value: _V | None) -> None:
        new = _vjoin(self.env.get(name), value)
        if new is not None and new != self.env.get(name):
            self.env[name] = new
            self.changed = True

    def get(self, node: ast.AST | None) -> _V | None:
        """`ev`, with "nothing yet" read as `unk` once the first walk has settled."""
        value = None if node is None else self.ev(node)
        return _UNK if value is None and self.final else value

    def site(self, value: _V | None) -> None:
        known = value is not None and value.kind in ("data", "path", "handle") and value.lits
        self.sites.append(value.lits if value is not None and known else None)

    # ---- statements ----
    def block(self, body: list[ast.stmt]) -> None:
        for stmt in body:
            self.stmt(stmt)

    def stmt(self, node: ast.stmt) -> None:
        if isinstance(node, ast.Expr):
            self.get(node.value)
        elif isinstance(node, ast.Assign):
            value = self.get(node.value)
            for target in node.targets:
                self.store(target, value)
        elif isinstance(node, ast.AnnAssign):
            if node.value is not None:
                self.store(node.target, self.get(node.value))
        elif isinstance(node, ast.AugAssign):
            value = _vjoin(self.get(node.target), self.get(node.value))
            self.store(node.target, None if value is None else _V(value.kind))
        elif isinstance(node, (ast.For, ast.While, ast.If)):
            if isinstance(node, ast.For):
                self.store(node.target, self.elem(self.get(node.iter)))
            else:
                self.get(node.test)
            self.block(node.body)
            self.block(node.orelse)
        elif isinstance(node, ast.With):
            for item in node.items:
                value = self.get(item.context_expr)
                if item.optional_vars is not None:
                    self.store(item.optional_vars, value)
            self.block(node.body)
        elif isinstance(node, ast.FunctionDef):
            self.function(node)
        elif isinstance(node, ast.Return):
            # Statements are walked with the enclosing function's name on `self.scope`.
            self.returned(self.get(node.value) if node.value is not None else _DATA)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name if alias.asname else alias.name.split(".")[0]
                self.bind(alias.asname or top, _named("module", top))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*" or node.level:
                    self.lost.append("a star or relative import")
                    continue
                self.bind(alias.asname or alias.name, self.member(node.module or "", alias.name))
        elif isinstance(node, ast.Try):
            self.block(node.body)
            for handler in node.handlers:
                if handler.type is not None:
                    self.get(handler.type)
                if handler.name:
                    self.bind(handler.name, _DATA)
                self.block(handler.body)
            self.block(node.orelse)
            self.block(node.finalbody)
        elif isinstance(node, (ast.Raise, ast.Assert)):
            for child in ast.iter_child_nodes(node):
                self.get(child)
        elif isinstance(node, ast.Delete):
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    self.get(target)
        elif not isinstance(node, (ast.Pass, ast.Break, ast.Continue, ast.Global, ast.Nonlocal)):
            self.lost.append("a %s statement" % type(node).__name__)

    scope: str | None = None

    def returned(self, value: _V | None) -> None:
        key = self.scope or ""
        new = _vjoin(self.rets.get(key), value)
        if new is not None and new != self.rets.get(key):
            self.rets[key] = new
            self.changed = True

    def function(self, node: ast.FunctionDef) -> None:
        if node.decorator_list:
            self.lost.append("a decorator")
        self.defs[node.name] = node
        self.bind(node.name, _named("func", "local:" + node.name))
        args = node.args
        named = [*args.posonlyargs, *args.args]
        for arg, default in zip(
            named[len(named) - len(args.defaults) :], args.defaults, strict=True
        ):
            self.bind(arg.arg, self.get(default))
        for arg, kw_default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
            if kw_default is not None:
                self.bind(arg.arg, self.get(kw_default))
        for star in (args.vararg, args.kwarg):
            if star is not None:
                self.bind(star.arg, _UNK)
        outer, self.scope = self.scope, node.name
        self.block(node.body)
        self.scope = outer

    def root(self, node: ast.AST) -> str | None:
        while isinstance(node, (ast.Subscript, ast.Attribute, ast.Starred)):
            node = node.value
        return node.id if isinstance(node, ast.Name) else None

    def store(self, target: ast.AST, value: _V | None) -> None:
        if isinstance(target, ast.Name):
            self.bind(target.id, value)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self.store(elt, self.elem(value))
        elif isinstance(target, ast.Starred):
            self.store(target.value, value)
        elif isinstance(target, ast.Subscript):
            self.get(target.slice)
            name = self.root(target)
            if name is None:
                self.lost.append("a store into something unnamed")
            else:
                # What goes into a container is what comes out of it.
                self.bind(name, value)
        else:
            self.lost.append("a store into an attribute")

    # ---- values ----
    def elem(self, value: _V | None) -> _V | None:
        """What iterating or indexing `value` yields."""
        if value is None or value.kind in ("data", "path"):
            return value
        return _DATA if value.kind == "handle" else _UNK

    def flow(self, values: list[_V | None]) -> _V | None:
        """What a pure container function hands back: data, unless something that is not data went in."""
        out: _V | None = None
        for value in values:
            # A function value is not carried along: `callbacks` has already taken it as called.
            if value is not None and value.kind not in ("data", "func"):
                out = _vjoin(out, value)
        return _DATA if out is None else out

    def member(self, module: str, attr: str) -> _V:
        """`module.attr` as a value."""
        canon = "%s.%s" % (module, attr) if module else attr
        if canon in _PY_SUBMODULES:
            return _named("module", canon)
        if canon in _PY_HANDLES:
            return _named("handle", _PY_HANDLES[canon])
        if canon == "os.devnull":
            return _V("data", frozenset(("/dev/null",)))
        if canon in _PY_DATA_ATTRS or canon.startswith("os.O_"):
            return _DATA
        if module in _PY_PURE_MODULES and not self.callable_named(canon):
            return _DATA
        return _named("func", canon)

    def callable_named(self, canon: str) -> bool:
        return canon in _PY_WRITERS or canon in _PY_OPENERS or canon in _PY_PATH_CTORS

    def name(self, ident: str) -> _V | None:
        if ident in self.env:
            return self.env[ident]
        if ident in _PY_IMPLICIT_MODULES:
            return _named("module", ident)
        if ident in ("__name__", "__file__", "__doc__"):
            return _DATA
        if ident in self.defs:
            return _named("func", "local:" + ident)
        if (
            ident in _PY_SCALAR_BUILTINS
            or ident in _PY_FLOW_BUILTINS
            or ident in _PY_OPENERS
            or ident in dir(builtins)
        ):
            return _named("func", ident)
        return None

    def ev(self, node: ast.AST) -> _V | None:
        if isinstance(node, ast.Constant):
            return _V("data", frozenset((node.value,)) if isinstance(node.value, str) else None)
        if isinstance(node, ast.Name):
            return self.name(node.id)
        if isinstance(node, ast.Call):
            return self.call(node)
        if isinstance(node, ast.Attribute):
            base = self.get(node.value)
            if node.attr.startswith("_"):
                # `().__class__.__base__.__subclasses__()` reaches every class there is from a plain tuple.
                self.lost.append("an underscore attribute")
                return _UNK
            if base is None:
                return None
            if base.kind in ("module", "func") and base.lits:
                return self.member(next(iter(base.lits)), node.attr)
            if base.kind == "data":
                return _DATA
            if base.kind == "path":
                return _V("path") if node.attr in ("parent", "parents") else _DATA
            if base.kind == "handle":
                return base if node.attr == "buffer" else _DATA
            return _UNK
        if isinstance(node, ast.Subscript):
            self.get(node.slice)
            value = self.get(node.value)
            return _UNK if value is not None and value.kind == "handle" else self.elem(value)
        if isinstance(node, ast.BinOp):
            left, right = self.get(node.left), self.get(node.right)
            if left is None or right is None:
                return None
            if left.kind == "path" or right.kind == "path":
                if not isinstance(node.op, ast.Div):
                    return _UNK
                if left.lits and right.lits and len(left.lits) * len(right.lits) <= _MAX_LITS:
                    return _V(
                        "path", frozenset(os.path.join(a, b) for a in left.lits for b in right.lits)
                    )
                return _V("path")
            if left.kind != "data" or right.kind != "data":
                return _UNK
            if isinstance(node.op, ast.Add) and left.lits and right.lits:
                joined = frozenset(a + b for a in left.lits for b in right.lits)
                if len(joined) <= _MAX_LITS and all(len(s) <= 512 for s in joined):
                    return _V("data", joined)
            return _DATA
        if isinstance(node, (ast.BoolOp, ast.IfExp)):
            parts = node.values if isinstance(node, ast.BoolOp) else [node.body, node.orelse]
            if isinstance(node, ast.IfExp):
                self.get(node.test)
            out: _V | None = None
            for part in parts:
                out = _vjoin(out, self.get(part))
            return out
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            values = [self.get(e.value if isinstance(e, ast.Starred) else e) for e in node.elts]
            return self.display(values)
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if key is not None:
                    self.get(key)
            return self.display([self.get(v) for v in node.values])
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            for gen in node.generators:
                self.store(gen.target, self.elem(self.get(gen.iter)))
                for cond in gen.ifs:
                    self.get(cond)
            if isinstance(node, ast.DictComp):
                self.get(node.key)
                return self.display([self.get(node.value)])
            return self.display([self.get(node.elt)])
        if isinstance(node, ast.NamedExpr):
            value = self.get(node.value)
            self.store(node.target, value)
            return value
        if isinstance(node, ast.Lambda):
            label = "lambda:%d:%d" % (node.lineno, node.col_offset)
            self.defs[label[len("lambda:") :]] = node
            outer, self.scope = self.scope, label
            self.returned(self.get(node.body))
            self.scope = outer
            return _named("func", label)
        if isinstance(node, ast.JoinedStr):
            for part in node.values:
                if isinstance(part, ast.FormattedValue):
                    self.get(part.value)
            return _DATA
        if isinstance(node, (ast.Compare, ast.UnaryOp)):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.expr):
                    self.get(child)
            return _DATA
        if isinstance(node, ast.Slice):
            for bound in (node.lower, node.upper, node.step):
                self.get(bound)
            return _DATA
        if isinstance(node, ast.Starred):
            return self.get(node.value)
        self.lost.append("a %s expression" % type(node).__name__)
        return _UNK

    def display(self, values: list[_V | None]) -> _V | None:
        """A list, tuple, set or dict display: the join of what it holds (an empty one is data)."""
        out: _V | None = None
        for value in values:
            out = _vjoin(out, value)
        if out is None and not values:
            return _DATA
        return out

    # ---- calls ----
    def call(self, node: ast.Call) -> _V | None:
        pos: list[_V | None] = []
        dynamic = False
        for arg in node.args:
            if isinstance(arg, ast.Starred):
                dynamic = True
                self.get(arg.value)
            else:
                pos.append(self.get(arg))
        kw: dict[str, _V | None] = {}
        for keyword in node.keywords:
            value = self.get(keyword.value)
            if keyword.arg is None:
                dynamic = True
            else:
                kw[keyword.arg] = value
        func = node.func
        if isinstance(func, ast.Attribute):
            base = self.get(func.value)
            if func.attr.startswith("_"):
                self.lost.append("an underscore method")
                return _UNK
            if base is None:
                return None
            if base.kind in ("module", "func") and base.lits:
                canon = "%s.%s" % (next(iter(base.lits)), func.attr)
                return self.dispatch(canon, node, pos, kw, dynamic)
            return self.method(base, func, pos, kw)
        callee = self.get(func)
        if callee is None:
            return None
        if callee.kind == "func" and callee.lits:
            return self.dispatch(next(iter(callee.lits)), node, pos, kw, dynamic)
        if callee.kind == "data":
            # A class or function of a pure module held in a name (`loads = json.loads`).
            self.callbacks([*pos, *kw.values()])
            return self.flow([*pos, *kw.values()])
        self.lost.append("a call of something this reader cannot name")
        return _UNK

    def invoke(self, func: _V, given: _V | None) -> _V | None:
        """Call a function VALUE this reader was only handed (`map(os.remove, xs)`, a `key=`): its arguments are not known one by one, so a local one gets `given` for every parameter and any other is called with unknown arguments."""
        if not func.lits:
            self.lost.append("a callable this reader cannot name")
            return _UNK
        canon = next(iter(func.lits))
        local = self.defs.get(canon.split(":", 1)[1]) if ":" in canon else None
        if local is not None:
            args = local.args
            for arg in (*args.posonlyargs, *args.args, *args.kwonlyargs):
                self.bind(arg.arg, given)
            return self.rets.get(canon if canon.startswith("lambda:") else canon[6:])
        return self.dispatch(canon, None, [], {}, True)

    def callbacks(self, values: list[_V | None]) -> _V | None:
        """Every function value among a call's arguments is taken as called by it, on what the other arguments hold."""
        funcs = [v for v in values if v is not None and v.kind == "func"]
        if not funcs:
            return None
        given = self.flow([self.elem(v) for v in values if v is not None and v.kind != "func"])
        out: _V | None = None
        for func in funcs:
            out = _vjoin(out, self.invoke(func, given))
        return out

    def local(self, canon: str, pos, kw, dynamic) -> _V | None:
        key = canon.split(":", 1)[1]
        fn = self.defs.get(key)
        if fn is None:
            return None
        args = fn.args
        named = [*args.posonlyargs, *args.args]
        for index, arg in enumerate(named):
            if dynamic:
                self.bind(arg.arg, _UNK)
            elif index < len(pos):
                self.bind(arg.arg, pos[index])
        for arg in (*named, *args.kwonlyargs):
            if arg.arg in kw:
                self.bind(arg.arg, kw[arg.arg])
            elif dynamic:
                self.bind(arg.arg, _UNK)
        return self.rets.get(canon if canon.startswith("lambda:") else key)

    def opened(self, target: _V | None, mode: _V | None, has_mode: bool, dynamic: bool) -> _V:
        """An `open`: a handle on `target`, and a write site when its mode replaces content or cannot be read."""
        if dynamic:
            self.sites.append(None)
            return _V("handle")
        known = target is not None and target.kind in ("data", "path", "handle")
        handle = _V("handle", target.lits if target is not None and known else None)
        if has_mode:
            literal = mode is not None and mode.kind == "data" and mode.lits
            if not literal or any(_mode_replaces(m) for m in (mode.lits if mode else ()) or ()):
                self.site(target)
        return handle

    def dispatch(self, canon: str, node: ast.Call | None, pos, kw, dynamic) -> _V | None:
        values = [*pos, *kw.values()]
        if canon.startswith(("local:", "lambda:")):
            return self.local(canon, pos, kw, dynamic)
        called = self.callbacks(values)
        if canon in _PY_PATH_CTORS:
            if dynamic or kw or len(pos) != 1:
                return _V("path", frozenset((".",)) if not pos and not dynamic else None)
            only = pos[0]
            known = only is not None and only.kind in ("data", "path") and only.lits
            return _V("path", only.lits if only is not None and known else None)
        if canon in ("pathlib.Path.cwd", "pathlib.Path.home"):
            return _V("path")
        if canon in _PY_OPENERS:
            target = kw.get("file", pos[0] if pos else None)
            has_mode = "mode" in kw or len(pos) > 1
            return self.opened(
                target, kw.get("mode", pos[1] if len(pos) > 1 else None), has_mode, dynamic
            )
        if canon == "os.open":
            flags = node.args[1] if node is not None and len(node.args) > 1 else None
            read_only = isinstance(flags, ast.Attribute) and flags.attr == "O_RDONLY"
            if not read_only:
                self.site(pos[0] if pos and not dynamic else None)
            target = pos[0] if pos else None
            known = target is not None and target.kind in ("data", "path") and target.lits
            return _V("handle", target.lits if target is not None and known else None)
        if canon in _PY_WRITERS:
            for index in _PY_WRITERS[canon]:
                self.site(pos[index] if index < len(pos) and not dynamic and not kw else None)
            return _DATA
        module = canon.rpartition(".")[0]
        if canon in ("str", "os.fspath") and len(pos) == 1 and pos[0] is not None:
            return _V("data", pos[0].lits if pos[0].kind in ("data", "path") else None)
        if canon == "os.path.join" and not dynamic and not kw and pos:
            parts = [p.lits if p is not None and p.kind == "data" else None for p in pos]
            if all(p is not None and len(p) == 1 for p in parts):
                return _V("data", frozenset((os.path.join(*(next(iter(p)) for p in parts if p)),)))
            return _DATA
        if (
            canon in _PY_SCALAR_BUILTINS
            or canon in _PY_PURE_FUNCS
            or (module in _PY_PURE_MODULES and canon != "argparse.FileType")
            or module in _PY_TYPES
            or _is_exception(canon)
        ):
            return _DATA
        if canon in _PY_FLOW_BUILTINS or module in _PY_FLOW_MODULES:
            return _vjoin(self.flow(values), called)
        self.lost.append("a call of %s" % canon)
        return _UNK

    def method(self, base: _V, func: ast.Attribute, pos, kw) -> _V | None:
        name = func.attr
        values = [*pos, *kw.values()]
        self.callbacks(values)
        if base.kind == "data":
            other = self.flow(values)
            if other is None or other.kind == "data":
                return _DATA
            if name in _PY_MUTATORS:
                # Something that is not data went into a container: the container now holds it.
                held = self.root(func.value)
                if held is None:
                    self.lost.append("a non-data value put into something unnamed")
                else:
                    self.bind(held, _UNK)
            return _UNK
        if base.kind == "path":
            if name == "open":
                has_mode = "mode" in kw or bool(pos)
                return self.opened(base, kw.get("mode", pos[0] if pos else None), has_mode, False)
            if name in _PY_PATH_SAME:
                return base
            if name in _PY_PATH_DERIVED:
                return _V("path")
            if name in _PY_PATH_READS:
                return _DATA
            if name in _PY_PATH_WRITES:
                self.site(base)
                return _DATA
            if name in ("rename", "replace"):
                # The path it is called on is removed and the one it is given is replaced.
                self.site(base)
                self.site(pos[0] if pos else None)
                return _V("path")
        elif base.kind == "handle":
            if name == "truncate":
                self.site(base)
                return _DATA
            if name in _PY_HANDLE_METHODS:
                return _DATA
        self.lost.append("a .%s() on a value this reader cannot type" % name)
        return _UNK


def _follow_python(code):
    """`(literals, lost)` for a python program: every literal string its writes may land on, and whether anything in it could not be followed (an unresolved write target included)."""
    try:
        tree = ast.parse(textwrap.dedent(code))
    except (SyntaxError, ValueError, RecursionError):
        return [], True
    reader = _PythonReader(tree)
    try:
        reader.read()
    except RecursionError:
        return [], True
    literals = sorted({text for site in reader.sites if site for text in site})
    return literals, bool(reader.lost) or any(not site for site in reader.sites)


# --------------------------------------------------------------------------- a node, perl or ruby program, FOLLOWED ---------------------------------------------------------------------------
#
# NO PARSER, SO EVERY WORD MUST BE KNOWN. The write sites are read as before (`_site_targets`); then the strings, comments and pattern literals are blanked, the callee of each site that was read is blanked, and every word left must be a keyword, a read or pure construct of that language, or a name the program itself declares. An unread writer (`const w = fs.writeFileSync`, `File.write ARGV[0], ''`), a module this reader does not know (`require('child_process')`) and a dynamic call (`fs['rm' + 'Sync'](x)`, `$f->()`, `send`) all leave a word or a shape behind, and the program is not followed.
_KNOWN_WORDS = {
    "js": _words(
        "const let var function return if else for while do of in new typeof instanceof try catch finally throw true false null undefined async await break continue switch case default void delete console log error warn info process argv env exit stdout stderr stdin write end on require fs path os util promises then JSON parse stringify Object keys values entries Array isArray from String Number Boolean parseInt parseFloat isNaN Math floor ceil round max min abs trunc Date now Set Map has get set add size split join map filter forEach reduce trim trimEnd trimStart toString slice substring substr replace replaceAll match matchAll test length push pop shift unshift includes startsWith endsWith indexOf lastIndexOf concat sort reverse find findIndex some every flat flatMap padStart padEnd toUpperCase toLowerCase charAt at localeCompare repeat readFileSync readFile readdirSync readdir existsSync statSync lstatSync accessSync mkdirSync appendFileSync readlinkSync realpathSync basename dirname extname resolve relative normalize sep isFile isDirectory mtime mtimeMs utf8 RegExp Error message"
    ),
    "perl": _words(
        "my our local use strict warnings utf8 print printf say chomp chop die warn exit if elsif else unless while until for foreach last next return sub split join map grep sort reverse keys values each exists defined length substr index rindex lc uc lcfirst ucfirst sprintf scalar push pop shift unshift splice close eof binmode readline opendir readdir closedir mkdir and or not eq ne lt gt le ge cmp x qw undef wantarray ref abs int"
    ),
    "ruby": _words(
        "if else elsif end do while unless until for in def return then begin rescue ensure nil true false and or not puts print p pp require json set date time ARGV ENV STDIN STDOUT STDERR ARGF each each_line each_with_index each_char map select reject lines split strip chomp chop gsub sub length size to_s to_i to_f to_a to_h to_sym to_json first last include start_with end_with empty join sort sort_by uniq count sum min max reverse keys values each_pair fetch dig push pop shift format printf sprintf exit abort upcase downcase capitalize scan match tr read readlines gets close flush lambda proc yield block_given next break redo self inspect freeze dup is_a nil key value times upto downto step abs round floor ceil zero any all none find detect inject reduce flat_map compact flatten zip take drop slice concat prepend center ljust rjust"
    ),
}
_JS_FAMILIES = frozenset(("node", "deno", "bun", "tsx"))
_JS_MODULES = frozenset(
    ("fs", "path", "os", "util", "node:fs", "node:path", "node:os", "node:util")
)


def _blanked(code, family, spans):
    """`(text, lost)`: `code` with string bodies, comments and the read sites' callees turned to spaces, and whether a string carries code this reader does not read (an interpolation, a template)."""
    out = list(code)
    lost = False
    for start, end in spans:
        out[start:end] = " " * (end - start)
    i, n = 0, len(code)
    while i < n:
        ch = code[i]
        if ch in "'\"":
            j = i + 1
            while j < n and code[j] != ch:
                j += 2 if code[j] == "\\" else 1
            body = code[i + 1 : j]
            if ch == '"' and family != "js" and re.search(r"#\{|[@$]\{", body):
                lost = True
            out[i + 1 : j] = " " * (min(j, n) - i - 1)
            i = j + 1
        elif ch == "`":
            lost = True
            i += 1
        elif family == "js" and code.startswith("//", i):
            j = code.find("\n", i)
            j = n if j < 0 else j
            out[i:j] = " " * (j - i)
            i = j
        elif family == "js" and code.startswith("/*", i):
            j = code.find("*/", i)
            j = n if j < 0 else j + 2
            out[i:j] = " " * (j - i)
            i = j
        elif family != "js" and ch == "#" and (i == 0 or code[i - 1] != "$"):
            j = code.find("\n", i)
            j = n if j < 0 else j
            out[i:j] = " " * (j - i)
            i = j
        else:
            i += 1
    return "".join(out), lost


def _extent_unknown(code, family):
    """Does `code` hold a construct whose EXTENT `_blanked` does not know?

    `_blanked` reads three things: a quoted string, a comment, a slash-delimited pattern. Anywhere a quote or a `#` is NOT one of those, it would blank from there on and hide live code from the word check (reviews 801bbb46.1/.2: perl's `$"`, and `qw#a#`). The shapes below are refused, not taught to it. Each is the RULE itself, never a list of delimiters (reviews 012e1b7b.1/.2/.3: every enumerated delimiter list had a hole):

    - a punctuation variable (`$`, perl `@`, or ruby `$`-globals followed by a quote, a backtick or a `#`, among them `$"` `$'` `` $` `` `$#`);
    - a quote-like operator word (perl `q qq qw qr m s tr y`, ruby `%`-forms) on ANY non-word, non-space delimiter, the one exception being the plain `/.../ ` pattern the pattern reader already handles and only when it holds no quote;
    - a bare ruby `%` that is not plainly the modulo operator between two spaced operands;
    - a heredoc (`<<` then optional space, optional `~` or `-`, then a quote or an identifier);
    - a ruby character literal (`?` then a quote); a data or pod section; perl's old `'` package separator.
    When it is ambiguous whether one of these is present, it is refused: a log is in play.
    """
    quote = r"""["'`#]"""
    # The plain slash pattern `_blanked` DOES read: a `/` where a pattern may stand, no quote-like word before it.
    plain_slash = r"(?:^|[(,=~!&|{;:?]|\b(?:if|unless|and|or|not|split|grep|while|return|when|until|match|scan|gsub|sub))\s*/(?![*/])"
    shapes = [
        # a plain slash pattern that itself holds a quote or `#` before the `/` that closes it
        plain_slash + r"(?:\\.|[^/\n\\])*" + quote,
    ]
    if family != "js":
        # A variable name whose next character is a quote or `#`: perl `$" $' $\` $#`, ruby `$" $'`. A legitimate `$#array` is refused too, and that is correct: `_blanked` cannot tell it from `$#`.
        shapes += [
            r"[$@]" + quote,
            r"<<\s*[~-]?\s*[\"'`]",
            r"<<[~-]?[A-Za-z_]",
            r"^__(?:END|DATA)__",
            r"^=[a-z]",
        ]
    if family == "perl":
        # A quote-like word on ANY delimiter that is not a word or space; a plain `/` touching the word is the pattern reader's and is handled above, so it is the one delimiter excluded here. A `/` after a space is not the pattern reader's (a52292e4.2) and is refused.
        # What may stand before the word and make it a name (a52292e4.1): a word character, the sigils `$` and `@`, which are never operators, and the method arrow. `%`, `&` and `>` are operators too (`1 %q#a#`, `&&q#a#`, `1>q#a#`), so a word after one of them is refused, a hash named `%s` and a call spelled `&s` with it.
        name = r"(?<![\w$@])(?<!->)"
        shapes += [
            name + r"(?:q|qq|qw|qr|m)\s*[^\w\s/]",
            name + r"(?:q|qq|qw|qr|m)/(?![*/])(?:\\.|[^/\n\\])*" + quote,
            name + r"(?:s|tr|y)\s*[^\w\s/]",
            name + r"(?:q|qq|qw|qr|m|s|tr|y)\s+/",
            r"\w'[A-Za-z_]",
        ]
        # A substitution on `/` (the pattern reader's own delimiter) whose body holds a quote or `#`.
        if any(
            re.search(quote, m.group(0))
            for m in re.finditer(r"\b(?:s|tr|y)/(?:\\.|[^/\n\\])*/(?:\\.|[^/\n\\])*/", code)
        ):
            return True
    if family == "ruby":
        # A `%`-literal on ANY delimiter: `%`, an optional single type letter, then any non-word, non-space character. A bare `%` with punctuation after it is one too, UNLESS it is plainly the modulo operator (a space, then `%`, then a space).
        shapes += [
            r"%[a-zA-Z]?[^\w\s]",
            r"\?" + quote,
        ]
        if re.search(r"(?<![ \t])%[^\w\s=]", code):
            return True
    return any(re.search(shape, code, re.MULTILINE) for shape in shapes)


def _follow_words(code, family):
    """`(literals, lost)` for a node, perl or ruby program."""
    literals, unresolved, spans = _site_targets(code, family)
    text, lost = _blanked(code, family, spans)
    lost = lost or unresolved or _extent_unknown(code, family)

    def blank(pattern, keep=0):
        """Blank what `pattern` matches, keeping its first `keep` groups."""
        nonlocal text
        text = re.sub(
            pattern,
            lambda m: (
                "".join(m.group(g) for g in range(1, keep + 1))
                + " " * (len(m.group(0)) - sum(len(m.group(g)) for g in range(1, keep + 1)))
            ),
            text,
        )

    # A substitution whose replacement is CODE (`s/x/.../e`) is not read.
    if family == "perl":
        for match in re.finditer(
            r"\b(?:s|tr|y)([/|!,])(?:\\.|(?!\1).)*\1(?:\\.|(?!\1).)*\1([a-z]*)", text
        ):
            lost = lost or "e" in match.group(2)
        blank(r"\b(?:s|tr|y)([/|!,])(?:\\.|(?!\1).)*\1(?:\\.|(?!\1).)*\1[a-z]*")
        # A file test (`-e $f`) and a bareword hash key (`$h{name}`).
        blank(r"(?<![\w$])-[a-zA-Z]\b(?=\s*[$\"'])")
        blank(r"\{\w+\}")
    # A pattern literal, where a pattern can stand: after an operator, an opening bracket, or a word that takes one.
    blank(
        r"(^|[(,=~!&|{;:?]|\b(?:if|unless|and|or|not|split|grep|while|return|when|until|match|scan|gsub|sub)\b)(\s*)(?:m|qr)?/(?:\\.|[^/\n\\])+/[a-z]*",
        2,
    )
    if re.search(r"\(\?\{|@\{\[", text):
        lost = True
    declared: set[str] = set()
    if family == "js":
        for names in re.findall(r"\b(?:const|let|var)\s+\{([^}]*)\}", text):
            # A destructured member is a MEMBER first (`{writeFileSync: w}`): only the name after the colon is the program's own, and the member itself must be one this reader knows.
            declared.update(re.findall(r":\s*([A-Za-z_]\w*)", names))
        declared.update(
            re.findall(r"\b(?:const|let|var|function|catch\s*\()\s*([A-Za-z_]\w*)", text)
        )
        declared.update(re.findall(r"\b([A-Za-z_]\w*)\s*=>", text))
        for names in re.findall(r"\(([\w\s,]*)\)\s*=>", text) + re.findall(
            r"\bfunction\s*\w*\s*\(([^)]*)\)", text
        ):
            declared.update(re.findall(r"[A-Za-z_]\w*", names))
        # A module is used only through a dot: `fs.readFileSync(...)`. Held any other way (passed, indexed, spread) its members are out of sight.
        aliases = {"fs", "path", "os", "util"} | set(
            re.findall(r"\b(?:const|let|var)\s+(\w+)\s*=\s*require\(", text)
        )
        for match in re.finditer(r"\brequire\b(?:\(\s*(['\"])([^'\"]*)\1\s*\))?", code):
            after = code[match.end() :].lstrip()[:1]
            if match.group(2) not in _JS_MODULES or after not in (".", ";", ",", "", "\n"):
                lost = True
        for alias in aliases:
            if re.search(
                r"(?<![\w$.])%s\b(?!\s*(?:\.[A-Za-z_]|=\s*require\())" % re.escape(alias), text
            ):
                lost = True
        if re.search(r"\]\s*\(|\{\s*\[|\[\s*['\"]", text):
            lost = True
    elif family == "perl":
        declared.update(re.findall(r"\bsub\s+([A-Za-z_]\w*)", text))
        # A call through a reference or a name, and `$^I`, which turns the `<>` loop into an in-place edit of the files handed.
        if re.search(r"->\s*\(|&\s*[${]|\\&|\$\^I", text):
            lost = True
    elif family == "ruby":
        # A constant is read only in the pairs below; held bare (`x = IO`) its writers are out of sight.
        blank(
            r"\b(?:File\.(?:read|readlines|foreach|exist\?|file\?|directory\?|size|basename|dirname|extname|join|expand_path|readable\?)|IO\.(?:read|readlines|foreach)|JSON\.(?:parse|generate|pretty_generate))(?![\w?!])"
        )
        blank(r"\$?(?:stdout|stderr|stdin|STDOUT|STDERR)\.(?:write|puts|print|flush|read)\b")
        blank(r"(?<=[a-z0-9_)\]])\.write\b")
        declared.update(
            re.findall(r"(?<![\w.:$@])([a-z_]\w*)\s*(?:[-+*/|&]|\|\||&&)?=(?![=~>])", text)
        )
        for names in re.findall(r"\|([\w\s,]*)\|", text) + re.findall(
            r"\bdef\s+\w+\s*\(([^)]*)\)", text
        ):
            declared.update(re.findall(r"[a-z_]\w*", names))
        declared.update(re.findall(r"\b(?:def|for)\s+([a-z_]\w*)", text))
        # A keyword label (`encoding: 'utf-8'`) and a symbol; a symbol turned into a call (`&:delete`) is a dynamic one.
        if re.search(r"&\s*:|\.\s*\(|%x|\$-i", text):
            lost = True
        # `require` runs a file: only the standard readers pass.
        for match in re.finditer(r"\brequire\b(?:\s*\(?\s*(['\"])([^'\"]*)\1)?", code):
            if match.group(2) not in ("json", "set", "date", "time", "csv", "optparse"):
                lost = True
        blank(r"\b\w+:(?!:)")
        blank(r"(?<!:):[a-z_]\w*[?!]?")
    else:
        return literals, True
    for match in re.finditer(r"(?<![\w$@%])[A-Za-z_]\w*", text):
        word = match.group(0)
        if word in _KNOWN_WORDS[family] or word in declared:
            continue
        if family == "perl" and word.isupper():
            continue
        lost = True
    return literals, lost


def _follow(code, family):
    """`(literals, lost)` by the reader for the program's language; a language with no reader is not followed."""
    if family == "python":
        return _follow_python(code)
    words = "js" if family in _JS_FAMILIES else family
    if words in _KNOWN_WORDS:
        return _follow_words(code, words)
    return [], True


def _literal_names_log(text):
    """Does a path literal name a round log, or spell one through a glob, a brace or the stem (an f-string's fixed text)?"""
    return _is_log(text) or _LOG_STEM in text or _word_could_name_log(text)


def _program_truncates(code, handed=False, family="python", context=None):
    """Does an interpreter program replace or remove a round log, or leave that open?

    ONLY A PROGRAM WITH A LOG IN PLAY IS READ: one the run was HANDED a log (`handed`: an argument, an environment value, its stdin), or whose own text could spell one (`_program_could_name_log`, the 2026-08-19 `p.write_text(s[:i] + new)` shape). Any other program is left alone, whatever it does.

    A program in play must be FOLLOWED (`_follow`): it is refused when a write lands on a literal that names a log, and equally when anything in it could not be followed, an unresolved write target included. A program whose every call is known, and whose every write goes to a named path that is not a log, writes those files and no other, whatever it reads.
    """
    if not handed and not _program_could_name_log(code, family, context):
        return False
    literals, lost = _follow(code, family)
    return lost or any(_literal_names_log(text) for text in literals)


def _ruby_in_place(run_):
    """Does this ruby run carry `-i` (edit the files it is handed in place)? Its option words are read as ruby bundles them, up to the script or the first operand: a letter that takes an attached or a following value ends its word (`-I lib`, `-e CODE`, and an option may follow the program), and `i` in any other place is the in-place switch (`-i`, `-pi.bak`, `-ni`)."""
    args = list(run_.argv if run_.xargv is None else run_.xargv)
    index = 0
    while index < len(args):
        word = args[index]
        if not word.startswith("-") or word in ("-", "--") or word.startswith("--"):
            return False
        for at, letter in enumerate(word[1:], 1):
            if letter == "i":
                return True
            if letter in "xFKTW0":
                break
            if letter in "eIrCE":
                if at == len(word) - 1:
                    index += 1
                break
        index += 1
    return False


def run(ev):
    cmd = ev.field("tool_input", "command")

    # A round-log path must appear at all, literally or as a glob or brace that could spell one (#e5b0540a: `echo pr-babysit-*.md | xargs cp /tmp/x.md` was allowed here before the walk ran), which is also what keeps the walk below off every command that cannot touch one.
    if not _could_name_log(cmd, ev.field("cwd")):
        return hookio.ALLOW

    # The redirects bash performs, with their operator: `>` truncates, `>>` appends (`2>&1`-style descriptor plumbing names no file).
    # A redirect target is expanded by bash too (`> agent/pr-babysit-*.md` truncates the one log it matches), and its run's directory is not on the write record, so a glob there is read by its shape.
    truncating = any(
        op in TRUNCATING_OPS and _names_log(target) and not re.fullmatch(r"\d+|-", target)
        for op, target in _redirects(shellscan._analyse(cmd))
    )
    # The verbs it runs, behind any prefix, xargs, sh -c or find -exec.
    cwd = ev.field("cwd") or str(hookio.repo_root())
    truncating = truncating or any(_verb_truncates(r, cwd) for r in shellscan.every_run(cmd))
    # An in-process write from python, node, perl or ruby. NOT anchorable the way the shell verbs are: the 2026-08-19 incident was a heredoc where the path sat on a DIFFERENT LINE from the write call. A program that writes an UNNAMED target is refused when its OWN text could spell a round-log path (`_program_could_name_log`: the `pr-babysit` stem, or a string literal glob that meets the pattern in a program not provably inert), because that is the exact shape that destroyed the appendix; one whose text cannot spell a log writes some other file and passes, whatever else the command mentions (#e5b0540a).
    truncating = truncating or any(
        _program_truncates(code, False, family, _log_context(cmd, cwd))
        for family, code in WT.interpreter_programs(cmd)
    )
    # The same question of each interpreter run with what the command line HANDS it (review 1d4e1754.1): a program that takes its target from argv, the environment or stdin names no path in its text.
    if not truncating:
        for run_ in shellscan.every_run(cmd):
            code, kind = shellscan.interpreter_program(run_, cmd, cwd)
            family = WT._interpreter_name(run_.name)
            # `ruby -i` rewrites every file it is handed, whatever the program says (measured allowed at ca2f75c43: `ruby -i -pe '$_.upcase!' <log>`). perl's `-i` is `shellscan.in_place_edit`'s, read with the verbs above.
            if family == "ruby" and _ruby_in_place(run_) and _handed_a_log(run_, code, kind, cwd):
                truncating = True
                break
            if code is None and kind != "unjudgeable":
                continue
            # A script this walk cannot read (an earlier clause wrote it from a source it cannot follow) is every program at once: handed a log, it is refused.
            if _handed_a_log(run_, code, kind, cwd) and (
                code is None or _program_truncates(code, True, family, _log_context(cmd, cwd))
            ):
                truncating = True
                break

    if not truncating:
        return hookio.ALLOW

    ev.warn(MESSAGE)
    return hookio.DENY
