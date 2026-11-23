"""The test tables of `block_roundlog_truncate`, moved out of the guard so a hook call imports no test data (PLAN-tooling-code-reduction CR5); the guard forwards each name here through `guards._cases.lazy`."""

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
