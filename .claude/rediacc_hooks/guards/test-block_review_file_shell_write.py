#!/usr/bin/env python3
"""Control harness for block_review_file_shell_write: the shell half of "a review record is never edited by hand".

The cases and the runner live in `test-block_review_file_edit.py` beside this file, so the two halves are judged by one set of rules; this file runs the shell cases through dispatch.py in both directions, then plants the guard's DEFECT and requires the run to fail.

The cases below are this guard's own, added to the shared shell cases: the operand arms read the words as bash expands them (#f6334e52), the glob pre-filter reads only a glob that can spell the review directory as one (#a1852a9e), a redirect target and an in-place option are read as bash expands them (#4deea064), a copied script carries its source (#3ff3bb16), and a word the walk cannot expand is read by where its value comes from (#b53f586d). Each MUTANT plants the defect one of them fixed and must turn at least one row, so neither fix is pinned by a harness that cannot see it.

    test-block_review_file_shell_write.py
"""

import atexit
import importlib
import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile
import typing

SHARED = pathlib.Path(__file__).resolve().with_name("test-block_review_file_edit.py")
STEM = "block_review_file_shell_write"
# A line that writes a Python program opening a review file for writing (#3ff3bb16 rows).
_REVIEW_WRITER = "printf \"open('agent/reviews/x/y.md','w')\\n\" > /tmp/r87s.py"
# d218ebf3, verbatim: the command that rewrote a review record through a listing over `agent/`.
_LISTING_MEASURED = """python3 - <<'EOF'
import re,glob,subprocess
files=subprocess.run(['grep','-rlE','AKIA[A-Z0-9]{16}','agent/'],capture_output=True,text=True).stdout.split()
for f in files:
    s=open(f).read()
    n=re.sub(r'AKIA[A-Z0-9]{16}',lambda m:'AKIA…'+m.group(0)[-4:],s)
    if n!=s: open(f,'w').write(n); print('redacted',f)
EOF"""


# ffbd9211.2: a review directory whose name reads as a file, present only under a directory the run reaches by its own `cd`, never under the guard process's directory or the repository root.
_DOTTED = pathlib.Path(tempfile.mkdtemp(prefix="test-review-dotted-"))
atexit.register(shutil.rmtree, str(_DOTTED), True)
(_DOTTED / "agent" / "reviews" / "1104-1.v2").mkdir(parents=True)
_DOTTED_REVIEWS = str(_DOTTED / "agent" / "revi*s")
# A listing loop that leaves `f` naming a review file, for the ffbd9211.1 rows.
_LISTED = "import glob\nfor f in glob.glob('agent/**/*.md', recursive=True):\n    print(f)\n"


def _py(code):
    """`code` as a python3 heredoc, the shape the measured command took."""
    return "python3 - <<'EOF'\n%s\nEOF" % code


OWN_CASES = [
    # #f6334e52: each refusal was allowed (rc 0) at 5e00d0768, because the operand was read as typed (`$D/y.md`).
    ("tee through an assigned directory", "D=agent/reviews/x; tee $D/y.md", True),
    ("sudo tee through an assigned directory", "D=agent/reviews/x; sudo tee $D/y.md", True),
    ("timeout tee through an assigned directory", "D=agent/reviews/x; timeout 5 tee $D/y.md", True),
    ("tee through a quoted braced variable", 'D=agent/reviews/x; tee "${D}/y.md"', True),
    ("truncate through an assigned directory", "D=agent/reviews/x; truncate -s 0 $D/y.md", True),
    ("sed -i through an assigned directory", "D=agent/reviews/x; sed -i s/a/b/ $D/y.md", True),
    ("cp onto an assigned directory", "D=agent/reviews/x; cp /tmp/a.md $D/", True),
    ("tee through an assigned directory, elsewhere", "D=plain; tee $D/y.md", False),
    ("cat through an assigned directory", "D=agent/reviews/x; cat $D/y.md", False),
    ("tee through an unset variable", "tee $UNSET_REVIEW_DIR/y.md", False),
    # #a1852a9e: the first two were refused (rc 2) at 5e00d0768 for the `.*` inside the sed or perl expression.
    ("sed -i with .* then the script runs", "sed -i 's/a.*b/c/' x.py && python3 x.py", False),
    (
        "perl -pi with .* then the script runs",
        "perl -pi -e 's/a.*b/c/' x.py && python3 x.py",
        False,
    ),
    ("cp onto a glob that reads as the directory", "cp x agent/revi*s/", True),
    ("sed -i with .* on a globbed review file", "sed -i 's/a.*b/c/' agent/revi*s/x/y.md", True),
    ("tee onto a glob under cd agent", "cd agent && tee revi*s/y.md", True),
    ("xargs cp fed a glob under cd agent", "cd agent && echo revi*s/x | xargs cp a", True),
    # A glob in the directory the run executes in is read as one in its word is: this was allowed (rc 0) at 5e00d0768.
    ("tee under a globbed cd", "cd agen? && tee revi*s/x.md", True),
    ("tee under a globbed cd, a sibling directory", "cd agen? && tee reviews-old/x.md", False),
    # #4deea064: each refusal was allowed (rc 0) at 04b0ebdf9, because a redirect target and sed's options were read as typed. bash writes `agent/reviews/x/y.md` in each, and opens a group's redirect before its body runs.
    ("redirect through an assigned directory", "D=agent/reviews/x; echo hi > $D/y.md", True),
    ("append through a quoted assigned directory", 'D=agent/reviews/x; echo hi >> "$D/y.md"', True),
    (
        "redirect through an assigned directory under cd agent",
        "cd agent && D=reviews/x; echo hi > $D/y.md",
        True,
    ),
    (
        "group redirect expanded before its body",
        "D=agent/reviews; { D=plain; echo hi; } > $D/y.md",
        True,
    ),
    ("sed in place through an assigned option", "F=-i; sed $F s/a/b/ agent/reviews/x/y.md", True),
    (
        "group redirect, the value the body assigns",
        "D=plain; { D=agent/reviews/x; echo hi; } > $D/y.md",
        False,
    ),
    ("redirect bash refuses as ambiguous", 'D="agent/reviews/x y"; echo hi > $D', False),
    ("sed -n through an assigned option", "F=-n; sed $F p agent/reviews/x/y.md", False),
    # #3ff3bb16: a copy carries its source. The first was refused (rc 2) at 04b0ebdf9 as a script written from a source the hook cannot read, and the second allowed (rc 0), its directory landing never recorded; the last two stay refused.
    (
        "a copied script run in the same command",
        "cp .claude/rediacc_hooks/__init__.py /tmp/r87c.py && python3 /tmp/r87c.py --out reviews.txt",
        False,
    ),
    (
        "a script copied into a directory, then run",
        "%s && cp /tmp/r87s.py /var/tmp/ && python3 /var/tmp/r87s.py" % _REVIEW_WRITER,
        True,
    ),
    (
        "a copied script that writes a review file",
        "%s && cp /tmp/r87s.py /tmp/r87d.py && python3 /tmp/r87d.py" % _REVIEW_WRITER,
        True,
    ),
    (
        "a no-clobber copy stays unreadable",
        "cp -n .claude/rediacc_hooks/__init__.py /tmp/r87c.py && python3 /tmp/r87c.py --out reviews.txt",
        True,
    ),
    # Review 0600a464.1: a directory the same command makes is a directory (`/tmp/r92-made` is absent when the hook runs). The first two were allowed (rc 0) at 434eb6c5f: the copy was recorded as a file named `/tmp/r92-made` and `python3 /tmp/r92-made/r87s.py` read the disk, where nothing was; the third, a directory whose name the walk cannot expand, is unjudgeable and refused.
    (
        "a script copied into a directory the command makes, then run",
        "%s && mkdir -p /tmp/r92-made && cp /tmp/r87s.py /tmp/r92-made && python3 /tmp/r92-made/r87s.py"
        % _REVIEW_WRITER,
        True,
    ),
    (
        "a script copied into a directory install -d makes, then run",
        "%s && install -d /tmp/r92-made && cp /tmp/r87s.py /tmp/r92-made && python3 /tmp/r92-made/r87s.py"
        % _REVIEW_WRITER,
        True,
    ),
    (
        "a script copied where an unexpanded mkdir may make a directory",
        '%s && mkdir -p "$(echo /tmp/r92-made)" && cp /tmp/r87s.py /tmp/r92-made && python3 /tmp/r92-made/r87s.py'
        % _REVIEW_WRITER,
        True,
    ),
    # #97ed76a7: a group's redirect is on the runs inside it, joined to the `cd` in force (allowed, rc 0, at 434eb6c5f); a variable `for` or `read` assigned is not the stale value (refused, rc 2, at 434eb6c5f, while bash writes `plain/y.md`).
    ("a group redirect under a cd", "cd agent/reviews/x && { echo hi; } > y.md", True),
    ("an if redirect under a cd", "cd agent/reviews/x && if true; then echo hi; fi > y.md", True),
    ("a function body is walked", "function f { tee agent/reviews/x/y.md; }", True),
    (
        "a for loop reassigns the variable",
        "D=agent/reviews/x; for D in plain; do echo hi > $D/y.md; done",
        False,
    ),
    (
        "read reassigns the variable",
        "D=agent/reviews/x; read D <<< plain; echo hi > $D/y.md",
        False,
    ),
    # #b53f586d: a word the walk cannot expand is read by where its value comes from. Each refusal was allowed (rc 0) at af677c6a9 while bash 5.3 writes the review file; the controls were allowed there too and stay allowed.
    (
        "a for loop walks the review directory",
        "for D in agent/reviews/x; do echo hi > $D/y.md; done",
        True,
    ),
    (
        "tee through a loop over the review directory",
        "for D in agent/reviews/x; do tee $D/y.md; done",
        True,
    ),
    (
        "a loop word that globs the directory",
        "for D in agent/revi*s/x; do echo hi > $D/y.md; done",
        True,
    ),
    (
        "a trimmed loop value",
        "for f in agent/reviews/x/a.md; do cp /tmp/a ${f%.md}.txt; done",
        True,
    ),
    ("read takes the review directory", "read D <<< agent/reviews/x; echo hi > $D/y.md", True),
    (
        "printf -v assigns the review directory",
        "printf -v D %s agent/reviews/x; echo hi > $D/y.md",
        True,
    ),
    ("set -- assigns the review directory", "set -- agent/reviews/x; echo hi > $1/y.md", True),
    ("a substitution names the review directory", 'echo hi > "$(echo agent/reviews/x)/y.md"', True),
    ("a default assigns the review directory", "echo hi > ${D:=agent/reviews/x}/y.md", True),
    ("an unknown segment under cd agent", "cd agent && echo hi > $X/y.md", True),
    ("an unknown segment after agent/", "echo hi > agent/$X", True),
    ("a for loop elsewhere", "for D in plain; do echo hi > $D/y.md; done", False),
    ("an unknown target outside agent", "echo hi > $D/y.md", False),
    ("two unknown segments", 'cat agent/reviews/x/a.md > "$OUT/$NAME"', False),
    (
        "a mktemp target on a line reading a review",
        "T=$(mktemp); cat agent/reviews/x/a.md > $T",
        False,
    ),
    # #e85553f0: an absolute redirect target is opened where it names, not under the run's directory. The first three were refused (rc 2) at 62ba1d8d2 ("redirect into /dev/null"); the refusals were refused there too and stay refused.
    (
        "a stderr sink under cd into the review directory",
        "cd agent/reviews/1023-1 && for f in 0f6b5915 1ac184a8; do ls $f*.md 2>/dev/null; done",
        False,
    ),
    (
        "stdout into /dev/stderr under cd into the review directory",
        "cd agent/reviews/x && cat a.md >/dev/stderr",
        False,
    ),
    (
        "an absolute file outside under cd into the review directory",
        "cd agent/reviews/x && ls 2>/tmp/r85e.txt",
        False,
    ),
    (
        "a relative write beside a sink under the review directory",
        "cd agent/reviews/x && echo hi 2>/dev/null > y.md",
        True,
    ),
    ("an absolute review path", "echo hi > /home/u/console/agent/reviews/x/y.md", True),
    (
        "an absolute review path under cd elsewhere",
        "cd /tmp && echo hi > /home/u/console/agent/reviews/x/y.md",
        True,
    ),
    (
        "a trimmed loop value lands elsewhere",
        "for f in agent/reviews/x/a.md; do cp /tmp/a /tmp/${f##*/}; done",
        False,
    ),
    ("a loop that reads review files", 'for f in agent/reviews/x/*.md; do cat "$f"; done', False),
    ("set -- elsewhere", "set -- plain; cat agent/reviews/x/a.md > $1/y.md", False),
    # #b53f586d: a downloaded script names no review word and has no source on disk; it was allowed (rc 0) at af677c6a9.
    (
        "a downloaded script run in the same command",
        "curl -s https://example.invalid/x > /tmp/r97u.py && python3 /tmp/r97u.py",
        True,
    ),
    # #63109cf2: a script a tool writes through its own output option is written, with content this hook cannot read. The first three were allowed (rc 0) at 6ea3efd3a, the script read as absent; the control runs a script nothing in the line writes.
    (
        "curl -o then the script runs",
        "curl -so /tmp/r98u.py https://example.invalid/x && python3 /tmp/r98u.py",
        True,
    ),
    (
        "wget -O then the script runs",
        "wget -qO /tmp/r98u.py https://example.invalid/x && python3 /tmp/r98u.py",
        True,
    ),
    (
        "an extracted script runs",
        "tar -xf /tmp/r98u.tar -C /tmp/r98ux && python3 /tmp/r98ux/a.py",
        True,
    ),
    (
        "curl -o, then another script runs",
        "curl -so /tmp/r98u.py https://example.invalid/x && python3 /tmp/r98u-absent.py",
        False,
    ),
    # 8ef78586.1: `${!P}` is the value of the variable P names, not `$!`. The first three were allowed (rc 0) at 6ea3efd3a, read as `0/y.md`, while bash 5.3 writes `agent/reviews/x/y.md`; the controls were allowed there too and stay allowed.
    (
        "an indirect expansion through two known names",
        "P=D; D=agent/reviews/x; echo hi > ${!P}/y.md",
        True,
    ),
    ("tee through an indirect expansion", "P=D; D=agent/reviews/x; tee ${!P}/y.md", True),
    (
        "an indirect expansion through an unknown name",
        "D=agent/reviews/x; echo hi > ${!P}/y.md",
        True,
    ),
    ("an indirect expansion elsewhere", "P=D; D=plain; echo hi > ${!P}/y.md", False),
    ("an unknown indirect expansion outside agent", "echo hi > ${!P}/y.md", False),
    # 2026-10-20: `git archive <rev> -- <review path>` streams a tar to stdout and writes no file it names; it was refused (rc 2) as "git naming <path>". The tar extract into /tmp writes nothing under the directory; the last four land a file there.
    (
        "git archive of a review path, extracted into /tmp",
        "git archive HEAD -- agent/reviews/b/x.md | tar -x -C /tmp/r20x",
        False,
    ),
    (
        "git archive of a review directory, extracted into /tmp",
        "git archive HEAD~1 -- agent/reviews/b | tar -x -C /tmp/r20x",
        False,
    ),
    (
        "git archive of a plain path, extracted into /tmp",
        "git archive HEAD -- docs/a.md | tar -x -C /tmp/r20x",
        False,
    ),
    (
        "git archive extracted INTO the review directory",
        "git archive HEAD~1 -- agent/reviews/b | tar -x -C agent/reviews/b",
        True,
    ),
    ("git archive -o onto a review path", "git archive -o agent/reviews/b/x.tar HEAD", True),
    # review 58be8bbc.1: parse-options takes a unique long-option prefix and a short bundle ending in a value flag.
    (
        "git archive --outp (unique prefix) onto a review path",
        "git archive --outp agent/reviews/b/x.tar HEAD",
        True,
    ),
    (
        "git archive -vo (short bundle) onto a review path",
        "git archive -vo agent/reviews/b/x.tar HEAD",
        True,
    ),
    # review 5884f513.1/.2: the attached short form carries its own value; a path ending in `o` is not a bundle.
    (
        "git archive -oPATH (attached) onto a review path",
        "git archive -oagent/reviews/b/x.tar HEAD",
        True,
    ),
    (
        "git archive -o/tmp/logo (attached, ends in o) then a review pathspec",
        "git archive -o/tmp/logo HEAD -- agent/reviews/b/x.md",
        False,
    ),
    (
        "git archive -9o (compression level then o) onto a review path",
        "git archive -9o agent/reviews/b/x.tar HEAD",
        True,
    ),
    # `-oo` is `-o` with the attached value `o`, never a bundle that takes the next word.
    (
        "git archive -oo (attached value o) then a review pathspec, into /tmp",
        "git archive -oo HEAD -- agent/reviews/b/x.md | tar -x -C /tmp/r20x",
        False,
    ),
    (
        "git archive -v (no value) then a review pathspec, into /tmp",
        "git archive -v HEAD -- agent/reviews/b/x.md | tar -x -C /tmp/r20x",
        False,
    ),
    (
        "git archive --output= onto a review path",
        "git archive HEAD --output=agent/reviews/x.tar",
        True,
    ),
    (
        "git archive piped to tar -xf - into the directory",
        "git archive HEAD | tar -xf - -C agent/reviews/b",
        True,
    ),
    # d218ebf3: a write target bound to what a LISTING over an ancestor of the review directory returns. The measured command rewrote a review record on 2026-11-10 (rc 0 at a49d20475): its target `f` comes from `grep -rlE ... agent/`, so no review literal ever reaches it. Each refusal below was allowed (rc 0) there; every control was allowed there too and stays allowed.
    ("a listing over agent/ feeds the write target (measured)", _LISTING_MEASURED, True),
    (
        "glob.glob over agent/ feeds open for write",
        _py(
            "import glob\nfor f in glob.glob('agent/**/*.md', recursive=True):\n    open(f, 'w').write('x')"
        ),
        True,
    ),
    (
        "Path('agent').rglob feeds write_text",
        _py(
            "from pathlib import Path\nfor p in Path('agent').rglob('*.md'):\n"
            "    p.write_text(p.read_text().replace('a', 'b'))"
        ),
        True,
    ),
    (
        "os.walk('agent') feeds open for write",
        _py(
            "import os\nfor root, dirs, names in os.walk('agent'):\n    for n in names:\n"
            "        with open(os.path.join(root, n), 'w') as h:\n            h.write('x')"
        ),
        True,
    ),
    (
        "an indexed glob result under ./agent",
        _py("import glob\nfiles = glob.glob('./agent/*/*/*.md')\nopen(files[0], 'w').write('x')"),
        True,
    ),
    (
        "glob with root_dir agent, joined back",
        _py(
            "import glob, os\nfor f in glob.glob('**/*.md', root_dir='agent', recursive=True):\n"
            "    open(os.path.join('agent', f), 'w').write('x')"
        ),
        True,
    ),
    (
        "an absolute root ending in /agent",
        _py(
            "import os\nfor r, d, ns in os.walk('/home/developer/console/agent'):\n"
            "    for n in ns:\n        open(os.path.join(r, n), 'w').write('x')"
        ),
        True,
    ),
    (
        "an absolute walk of /x/agent feeds the target",
        _py(
            "import pathlib\nfor p in pathlib.Path('/srv/console/agent').glob('*/*/*.md'):\n"
            "    p.write_bytes(b'x')"
        ),
        True,
    ),
    (
        "find over agent through check_output, splitlines",
        _py(
            "import subprocess, pathlib\n"
            "out = subprocess.check_output(['find', 'agent', '-name', '*.md'], text=True)\n"
            "for f in out.splitlines():\n    pathlib.Path(f).write_text('x')"
        ),
        True,
    ),
    (
        "git ls-files agent, list() and a comprehension",
        _py(
            "import subprocess\nnames = list(subprocess.run('git ls-files agent', shell=True, "
            "capture_output=True, text=True).stdout.split())\n"
            "[open(n, 'a').write('x') for n in names]"
        ),
        True,
    ),
    (
        "a listing handed to sed -i through subprocess",
        _py(
            "import glob, subprocess\nfiles = glob.glob('agent/**/*.md', recursive=True)\n"
            "subprocess.run(['sed', '-i', 's/a/b/', *files])"
        ),
        True,
    ),
    (
        "a path derived from the listed one",
        _py(
            "from pathlib import Path\nfor p in Path('agent').rglob('*.md'):\n"
            "    p.with_suffix('.md').write_text('x')"
        ),
        True,
    ),
    (
        "a relative path under agent rebuilt from the listed one",
        _py(
            "import glob, os\nfor f in glob.glob('agent/**/*.md', recursive=True):\n"
            "    open('agent/' + os.path.relpath(f, 'agent'), 'w').write('x')"
        ),
        True,
    ),
    # The shell spellings of the same class: a listing's output reaches sed -i through xargs, a substitution or a read.
    (
        "grep -rl over agent/ piped to xargs sed -i",
        "grep -rl AKIA agent/ | xargs sed -i s/a/b/",
        True,
    ),
    (
        "find over agent piped to xargs -0 sed -i",
        "find agent -name '*.md' -print0 | xargs -0 sed -i s/a/b/",
        True,
    ),
    (
        "a for loop over a grep -rl of agent/",
        "for f in $(grep -rl AKIA agent/); do sed -i s/a/b/ $f; done",
        True,
    ),
    (
        "a read loop over a grep -rl of agent",
        'grep -rl AKIA agent | while read f; do sed -i s/a/b/ "$f"; done',
        True,
    ),
    (
        "a variable holding a git ls-files of agent",
        "F=$(git ls-files agent); sed -i s/a/b/ $F",
        True,
    ),
    # Controls: a listing that is only read, a write elsewhere, a root that is no ancestor, and the repository root (the accepted limit: a listing over the whole tree is too broad to judge, and refusing it would refuse every repo-wide rewrite).
    (
        "the measured grep -rl over agent/, results printed",
        _py(
            "import subprocess\nfiles = subprocess.run(['grep', '-rlE', 'AKIA[A-Z0-9]{16}', 'agent/'], "
            "capture_output=True, text=True).stdout.split()\nprint(files)"
        ),
        False,
    ),
    ("the measured grep in the shell", "grep -rlE 'AKIA[A-Z0-9]{16}' agent/", False),
    (
        "glob.glob over agent/ only read",
        _py(
            "import glob\nfor f in glob.glob('agent/**/*.md', recursive=True):\n    print(open(f).read())"
        ),
        False,
    ),
    (
        "Path('agent').rglob only read",
        _py(
            "from pathlib import Path\nfor p in Path('agent').rglob('*.md'):\n    print(p.read_text())"
        ),
        False,
    ),
    (
        "os.walk('agent') only read",
        _py(
            "import os\nfor root, dirs, names in os.walk('agent'):\n    for n in names:\n"
            "        print(open(os.path.join(root, n)).read())"
        ),
        False,
    ),
    (
        "a listing copied out to /tmp",
        _py(
            "import glob, os\nfor f in glob.glob('agent/**/*.md', recursive=True):\n"
            "    open('/tmp/out/' + os.path.basename(f), 'w').write(open(f).read())"
        ),
        False,
    ),
    (
        "a listing written as content of a scratch file",
        _py(
            "import glob\nout = open('/tmp/list.txt', 'w')\n"
            "out.write('\\n'.join(glob.glob('agent/**', recursive=True)))"
        ),
        False,
    ),
    (
        "a sibling root under agent that holds no reviews",
        _py(
            "from pathlib import Path\nfor p in Path('agent/plans').rglob('*.md'):\n    p.write_text('x')"
        ),
        False,
    ),
    (
        "a root whose name only starts with agent",
        _py(
            "import os\nfor r, d, ns in os.walk('agent-tools'):\n    open(os.path.join(r, ns[0]), 'w')"
        ),
        False,
    ),
    (
        "a listing over the repository root that writes (the accepted limit)",
        _py(
            "import glob\nfor f in glob.glob('**/*.md', recursive=True):\n"
            "    s = open(f).read()\n    open(f, 'w').write(s.replace('agent/plans/', 'agent/plans/_done/'))"
        ),
        False,
    ),
    (
        "grep -rl over . piped to xargs sed -i (the accepted limit)",
        "grep -rl AKIA . | xargs sed -i s/a/b/",
        False,
    ),
    ("grep -rl over agent/ piped to xargs cat", "grep -rl AKIA agent/ | xargs cat", False),
    (
        "a for loop over agent/plans",
        "for f in $(grep -rl x agent/plans); do sed -i s/a/b/ $f; done",
        False,
    ),
    # #6fdc7136: a substitution or a feed is lexed as text of its own, so the `cd` in force was lost. Each refusal was allowed (rc 0) at 00932b650 except the first, refused there only because any unknown value under `cd agent` completes `agent/<x>`; the controls were allowed there too and stay allowed.
    (
        "a for loop over a grep -rl of . under cd agent",
        'cd agent && for f in $(grep -rl x .); do sed -i s/a/b/ "$f"; done',
        True,
    ),
    (
        "a for loop over a grep -rl of .. under cd agent/plans",
        'cd agent/plans && for f in $(grep -rl x ..); do sed -i s/a/b/ "$f"; done',
        True,
    ),
    (
        "a substitution operand over .. under cd agent/plans",
        "cd agent/plans && sed -i s/a/b/ $(grep -rl x ..)",
        True,
    ),
    (
        "a variable holding a grep -rl of .. under cd agent/plans",
        "cd agent/plans && F=$(grep -rl x ..); sed -i s/a/b/ $F",
        True,
    ),
    (
        "grep -rl over . piped to xargs sed -i under cd agent",
        "cd agent && grep -rl x . | xargs sed -i s/a/b/",
        True,
    ),
    (
        "find over . piped to xargs sed -i under cd agent",
        "cd agent && find . -name '*.md' | xargs sed -i s/a/b/",
        True,
    ),
    (
        "grep -rl over .. piped to xargs sed -i under cd agent/plans",
        "cd agent/plans && grep -rl x .. | xargs sed -i s/a/b/",
        True,
    ),
    (
        "a for loop over a grep -rl of . under cd agent/plans",
        'cd agent/plans && for f in $(grep -rl x .); do sed -i s/a/b/ "$f"; done',
        False,
    ),
    (
        "grep -rl over . piped to xargs sed -i under cd agent/plans",
        "cd agent/plans && grep -rl x . | xargs sed -i s/a/b/",
        False,
    ),
    (
        "a listing under cd agent piped to xargs cat",
        "cd agent && grep -rl x . | xargs cat",
        False,
    ),
    (
        "a listing whose .. climbs out of agent",
        "cd agent/plans && grep -rl x ../.. | xargs sed -i s/a/b/",
        False,
    ),
    # 727fc4a4.1: allowed (rc 0) at 727fc4a419, where an anchored root holding `..` was read only at its `agent` segments; aafefb4b31 folds the `..`.
    (
        "grep -rl over agent/plans/../revi*s piped to xargs sed -i",
        "grep -rl x agent/plans/../revi*s | xargs sed -i s/a/b/",
        True,
    ),
    (
        "a python write over glob of agent/plans/../reviews",
        _py(
            "import glob\n"
            "for f in glob.glob('agent/plans/../reviews/**/*.md', recursive=True):\n"
            "    open(f, 'w')"
        ),
        True,
    ),
    (
        "grep -rl over agent/plans/../plans piped to xargs sed -i",
        "grep -rl x agent/plans/../plans | xargs sed -i s/a/b/",
        False,
    ),
    # 727fc4a4.2: rg over one file prints its lines, not names; the first two were refused (rc 2) at 727fc4a419, which read every rg run as a listing.
    (
        "python writes paths rg prints out of one review file",
        _py(
            "import subprocess\n"
            "out = subprocess.run(['rg', '-o', 'packages/[a-z/]+', "
            "'agent/reviews/1104-1/clean.jsonl'], capture_output=True, text=True).stdout\n"
            "for p in out.split():\n"
            "    open(p, 'w')"
        ),
        False,
    ),
    (
        "python writes paths rg prints out of one file under cwd agent/reviews",
        _py(
            "import subprocess\n"
            "out = subprocess.run(['rg', '-o', 'packages/[a-z/]+', 'clean.jsonl'], "
            "capture_output=True, text=True, cwd='agent/reviews/1104-1').stdout\n"
            "for p in out.split():\n"
            "    open(p, 'w')"
        ),
        False,
    ),
    (
        "rg over the agent directory piped to xargs sed -i",
        "rg -o x agent | xargs sed -i s/a/b/",
        True,
    ),
    (
        "rg -H over one review file cut to names and fed to sed -i",
        "rg -H x agent/plans/../revi*s/1104-1/clean.jsonl | cut -d: -f1 | xargs sed -i s/a/b/",
        True,
    ),
    (
        "rg over two roots under agent piped to xargs sed -i",
        "rg x agent/plans agent | xargs sed -i s/a/b/",
        True,
    ),
    # A search that prints lines crashed the guard (TypeError on the None roots, so it decided nothing), measured 2026-11-10.
    (
        "grep over one plan file piped to xargs sed -i",
        "grep x agent/plans/a.md | xargs sed -i s/a/b/",
        False,
    ),
    (
        "a line-printing grep before a review write",
        "grep x agent/plans/a.md | xargs echo; sed -i s/a/b/ agent/reviews/x/y.md",
        True,
    ),
    # 727fc4a4.3: the listing name is cleared by a later straight-line rebinding; the first two were refused (rc 2) at 727fc4a419.
    (
        "a listing loop name rebound to /tmp before a write",
        _py(
            "import glob\n"
            "for f in glob.glob('agent/**/*.md', recursive=True):\n"
            "    print(f)\n"
            "f = '/tmp/x'\n"
            "open(f, 'w')"
        ),
        False,
    ),
    (
        "a listing loop name rebound to /tmp inside the loop before a write",
        _py(
            "import glob\n"
            "for f in glob.glob('agent/**/*.md', recursive=True):\n"
            "    f = '/tmp/x'\n"
            "    open(f, 'w')"
        ),
        False,
    ),
    (
        "a listing loop name rebound to /tmp only after the write",
        _py(
            "import glob\n"
            "for f in glob.glob('agent/**/*.md', recursive=True):\n"
            "    open(f, 'w')\n"
            "    f = '/tmp/x'"
        ),
        True,
    ),
    (
        "a while loop that rebinds the name to a listing after the write",
        _py(
            "import glob\n"
            "f = '/tmp/x'\n"
            "while True:\n"
            "    open(f, 'w')\n"
            "    f = glob.glob('agent/**/*.md', recursive=True)[0]"
        ),
        True,
    ),
    (
        "a listing name rebound to /tmp in one branch only",
        _py(
            "import glob\n"
            "f = glob.glob('agent/**/*.md', recursive=True)[0]\n"
            "if f:\n"
            "    f = '/tmp/x'\n"
            "open(f, 'w')"
        ),
        True,
    ),
    (
        "a comprehension rebinding the name to a listing in the write",
        _py(
            "import glob\n"
            "files = glob.glob('agent/**/*.md', recursive=True)\n"
            "f = '/tmp/x'\n"
            "[open(f, 'w') for f in files]"
        ),
        True,
    ),
    (
        "a name rebound to another listing value before the write",
        _py(
            "import glob\n"
            "files = glob.glob('agent/**/*.md', recursive=True)\n"
            "f = '/tmp/x'\n"
            "f = files[0]\n"
            "open(f, 'w')"
        ),
        True,
    ),
    # ffbd9211.1: a write in a try's handler, else or finally block, or a match case, read the plain assignment before the whole statement; the four refusals were allowed (rc 0) at ffbd92113d.
    (
        "a try binding a listing, the write in its except handler",
        _py(
            "import glob\n"
            "f = '/tmp/x'\n"
            "try:\n"
            "    f = glob.glob('agent/**/*.md', recursive=True)[0]\n"
            "    raise ValueError\n"
            "except ValueError:\n"
            "    open(f, 'w')"
        ),
        True,
    ),
    (
        "a try binding a listing, the write in its else block",
        _py(
            "import glob\n"
            "f = '/tmp/x'\n"
            "try:\n"
            "    f = glob.glob('agent/**/*.md', recursive=True)[0]\n"
            "except ValueError:\n"
            "    pass\n"
            "else:\n"
            "    open(f, 'w')"
        ),
        True,
    ),
    (
        "a try binding a listing, the write in its finally block",
        _py(
            "import glob\n"
            "f = '/tmp/x'\n"
            "try:\n"
            "    f = glob.glob('agent/**/*.md', recursive=True)[0]\n"
            "finally:\n"
            "    open(f, 'w')"
        ),
        True,
    ),
    (
        "a match capturing a listing element, the write in its case",
        _py(
            "import glob\n"
            "f = '/tmp/x'\n"
            "match glob.glob('agent/**/*.md', recursive=True):\n"
            "    case [f, *_]:\n"
            "        open(f, 'w')"
        ),
        True,
    ),
    (
        "a listing name rebound to /tmp in the except handler before the write",
        _py(
            _LISTED + "try:\n"
            "    f = glob.glob('agent/**/*.md', recursive=True)[0]\n"
            "except ValueError:\n"
            "    f = '/tmp/x'\n"
            "    open(f, 'w')"
        ),
        False,
    ),
    (
        "a listing name rebound to /tmp in a try body before the write",
        _py(_LISTED + "try:\n    f = '/tmp/x'\n    open(f, 'w')\nexcept ValueError:\n    pass"),
        False,
    ),
    (
        "a match capturing a listing element, the write rebinds first",
        _py(
            "import glob\n"
            "match glob.glob('agent/**/*.md', recursive=True):\n"
            "    case [f, *_]:\n"
            "        f = '/tmp/x'\n"
            "        open(f, 'w')"
        ),
        False,
    ),
    # ffbd9211.2: the directory test read the guard process's directory, so a directory named like a file under the run's own cwd read as one file; the refusal was allowed (rc 0) at ffbd92113d.
    (
        "python writes paths rg prints out of a dotted review directory under cwd",
        _py(
            "import subprocess\n"
            "out = subprocess.run(['rg', '-o', 'packages/[a-z/]+', '1104-1.v2'], "
            "capture_output=True, text=True, cwd=%r).stdout\n"
            "for p in out.split():\n"
            "    open(p, 'w')" % _DOTTED_REVIEWS
        ),
        True,
    ),
    (
        "python writes paths rg prints out of a dotted review file under cwd",
        _py(
            "import subprocess\n"
            "out = subprocess.run(['rg', '-o', 'packages/[a-z/]+', '1104-1.v3'], "
            "capture_output=True, text=True, cwd=%r).stdout\n"
            "for p in out.split():\n"
            "    open(p, 'w')" % _DOTTED_REVIEWS
        ),
        False,
    ),
    # ffbd9211.3: grep -H and grep over two file roots print each line with its file; the three refusals were allowed (rc 0) at ffbd92113d.
    (
        "grep -H over one review file cut to names and fed to sed -i",
        "grep -H x agent/plans/../revi*s/1104-1/clean.jsonl | cut -d: -f1 | xargs sed -i s/a/b/",
        True,
    ),
    (
        "grep --with-filename over one review file cut to names and fed to sed -i",
        (
            "grep --with-filename x agent/plans/../revi*s/1104-1/clean.jsonl "
            "| cut -d: -f1 | xargs sed -i s/a/b/"
        ),
        True,
    ),
    (
        "grep over two file roots cut to names and fed to sed -i",
        (
            "grep x agent/plans/a.md agent/plans/../revi*s/1104-1/clean.jsonl "
            "| cut -d: -f1 | xargs sed -i s/a/b/"
        ),
        True,
    ),
    (
        "grep -r over one review file cut to names and fed to sed -i",
        "grep -r x agent/plans/../revi*s/1104-1/clean.jsonl | cut -d: -f1 | xargs sed -i s/a/b/",
        True,
    ),
    # The rows above hand grep, through a `cut`, to xargs: the stage that produces the input is read alone (`shellscan._Run.feed_stages`, #3661517d), so `cut -d: -f1` is no root of the grep. The two below hand grep its words alone through a program.
    (
        "python writes the files grep -H names in one review file",
        _py(
            "import subprocess\n"
            "out = subprocess.run(['grep', '-H', 'x', 'agent/reviews/1104-1/clean.jsonl'], "
            "capture_output=True, text=True).stdout\n"
            "for line in out.splitlines():\n"
            "    open(line.split(':')[0], 'w')"
        ),
        True,
    ),
    (
        "python writes the files grep --with-filename names in one review file",
        _py(
            "import subprocess\n"
            "out = subprocess.run(['grep', '--with-filename', 'x', "
            "'agent/reviews/1104-1/clean.jsonl'], capture_output=True, text=True).stdout\n"
            "for line in out.splitlines():\n"
            "    open(line.split(':')[0], 'w')"
        ),
        True,
    ),
    (
        "python writes paths grep prints out of one review file",
        _py(
            "import subprocess\n"
            "out = subprocess.run(['grep', '-o', 'packages/[a-z/]+', "
            "'agent/reviews/1104-1/clean.jsonl'], capture_output=True, text=True).stdout\n"
            "for p in out.split():\n"
            "    open(p, 'w')"
        ),
        False,
    ),
    (
        "grep -H over one plan file cut to names and fed to sed -i",
        "grep -H x agent/plans/a.md | cut -d: -f1 | xargs sed -i s/a/b/",
        False,
    ),
    # #3661517d: the feed was read as one bag of every stage's words, lexed as one command. The first allowed row was refused (rc 2) and the echo row allowed (rc 0) at 13f2459fb0, both measured 2026-11-10.
    ("a listing sorted and fed to sed -i", "grep -rl x agent/ | sort | xargs sed -i s/a/b/", True),
    (
        "grep -H over a review file cut to names and fed to sed -i",
        "grep -H x agent/reviews/b/c.jsonl | cut -d: -f1 | xargs sed -i s/a/b/",
        True,
    ),
    (
        "grep lines filtered by grep -v and fed to sed -i",
        "grep -o x README.md | grep -v agent | xargs sed -i s/a/b/",
        False,
    ),
    ("a file list fed to cat", "cat list.txt | xargs cat", False),
    (
        "a listing after an echo stage fed to sed -i",
        "echo README.md | grep -rl x agent/ | xargs sed -i s/a/b/",
        True,
    ),
    (
        "a listing in a subshell under cd fed to sed -i",
        "(cd agent && grep -rl x .) | xargs sed -i s/a/b/",
        True,
    ),
    (
        "a listing in a brace group fed to sed -i",
        "{ echo a; grep -rl x agent/; } | xargs sed -i s/a/b/",
        True,
    ),
    (
        "a listing through a loop's echo fed to sed -i",
        "grep -rl x agent/ | while read f; do echo $f | xargs sed -i s/a/b/; done",
        True,
    ),
    (
        "a listing piped to xargs that reads a here-string",
        "grep -rl x agent/ | xargs sed -i s/a/b/ <<< README.md",
        False,
    ),
    (
        "a listing piped into a grep over its own file, fed to sed -i",
        "grep -rl x agent/ | grep -o x README.md | xargs sed -i s/a/b/",
        False,
    ),
    (
        "a listing piped into a cat of its own file, fed to sed -i",
        "grep -rl x agent/ | cat list.txt | xargs sed -i s/a/b/",
        False,
    ),
    (
        "a listing through a process substitution fed to sed -i",
        "xargs sed -i s/a/b/ < <(grep -rl x agent/ | sort)",
        True,
    ),
]

MUTANTS = [
    (
        "operands read as typed only (#f6334e52)",
        (
            "what = _operand_write(run, name, list(words), where, base, cwd)",
            "what = _operand_write(run, name, argv, where, base, cwd)",
        ),
    ),
    (
        "any glob character sends the command on (#a1852a9e)",
        ("and not _globs_reviews(cmd, cwd)", 'and not any(ch in cmd for ch in "*?[{")'),
    ),
    (
        "the pre-filter blind to a glob word",
        ("        if any(spells(w, where) for w in words):", "        if False:"),
    ),
    (
        "a run's redirects read as typed (#4deea064)",
        (
            "for target in shellscan.redirect_targets(run):\n            if _is_review(target, where, base):",
            "for target in run.writes:\n            if _is_review(target, where, base):",
        ),
    ),
    (
        "the run directory joined as typed",
        (
            "for w in joined for form in _review_forms(w)",
            (
                "for w in joined[:1] for form in [*_review_forms(w), *("
                "str(cwd).rstrip('/') + '/' + f for f in _review_forms(w) if cwd)]"
            ),
        ),
    ),
    (
        "an unexpandable redirect read as typed only (#b53f586d)",
        (
            "for form, definite in _readings(target, run, cmd):",
            "for form, definite in []:",
        ),
    ),
    (
        "loop values not read (#b53f586d)",
        (
            '    if kind == "var" and name in loop:\n        return list(loop[name]), True\n',
            "",
        ),
    ),
    (
        "a variable's spelled source not read (#b53f586d)",
        (
            "source = _value_source(name, cmd, shellscan._CLOBBERED in str(value))",
            "source = None",
        ),
    ),
    (
        "unjudgeable programs judged by the review word alone (#b53f586d)",
        (
            "and not _programs_name_reviews(cmd, cwd)",
            'and not any("reviews" in t for t in shellscan.interpreter_scripts(cmd, cwd))',
        ),
    ),
    (
        "git archive positionals read as files it writes (2026-10-20)",
        ('    if verb == "archive":', "    if False:"),
    ),
    (
        "an absolute target joined to the run directory (#e85553f0)",
        (
            'if cwd and not word.startswith("/") else [word]',
            "if cwd else [word]",
        ),
    ),
    (
        "an indirect expansion read as $! (8ef78586.1)",
        ('elif body.startswith("!") and len(body) > 1:', "elif False:"),
    ),
    (
        "a Python target bound to a listing not read (d218ebf3)",
        (
            "if any(_listing_target(t, listed, calls, bound, review_names, parents) for t in targets):",
            "if False:",
        ),
    ),
    (
        "rglob read as a one-level glob (d218ebf3)",
        ('("/**/" if func.attr == "rglob" else "/")', '"/"'),
    ),
    (
        "a listing fed through xargs not read (d218ebf3)",
        ("        if _lists_under(stage.text, where):\n            return True\n", ""),
    ),
    (
        "the feed lexed as one bag of every stage (#3661517d)",
        (
            "    for stage in reversed(run.feed_stages):\n",
            "    for stage in [shellscan.FeedStage('data', run.feed or '')]:\n",
        ),
    ),
    (
        "a filter stage read as ending the walk (#3661517d)",
        (
            '        if stage.kind == "data" or _ignores_stdin(stage.text):\n',
            "        if True:\n",
        ),
    ),
    (
        "a data stage read as passing the pipe through (#3661517d)",
        (
            '        if stage.kind == "data" or _ignores_stdin(stage.text):\n',
            "        if _ignores_stdin(stage.text):\n",
        ),
    ),
    (
        "an echo of an expansion read as ignoring its stdin (#3661517d)",
        (
            '            if any("$" in a or "`" in a for a in argv):\n                return False\n',
            "            pass\n",
        ),
    ),
    (
        "a search with a file operand read as passing stdin through (#3661517d)",
        ('    return bool(operands) and "-" not in operands\n', "    return False\n"),
    ),
    (
        "a value's source read for the word reviews alone (d218ebf3)",
        (
            "return bool(_SPELLS_REVIEWS.search(text)) or _lists_under(text, where)",
            "return bool(_SPELLS_REVIEWS.search(text))",
        ),
    ),
    (
        "the repository root read as an ancestor (d218ebf3 limit)",
        ('        if i == 0 and seg in ("*", "**"):\n            return False\n', ""),
    ),
    (
        "a copy out to a literal directory refused (d218ebf3)",
        ('if head in ("", ".", "./") or _root_walks_reviews(head):', "if True:"),
    ),
    (
        "a listing read without the cd its output is used under (#6fdc7136)",
        (
            "return _text_lists_reviews(text) or bool(where and _text_lists_reviews(text, where))",
            "return _text_lists_reviews(text)",
        ),
    ),
    (
        "a listing root's .. not folded (#6fdc7136)",
        ("    return _root_walks_reviews(folded)\n", "    return False\n"),
    ),
    (
        "every rg run read as a listing (727fc4a4.2)",
        (
            "        lists = len(operands) != 1 or _names_a_directory(operands[0], where)\n",
            "        lists = True\n",
        ),
    ),
    (
        "rg over one directory read as one file (727fc4a4.2)",
        (
            "    return any(os.path.isdir(path) for path in _disk_readings(text, where))",
            "    return False",
        ),
    ),
    (
        "a search printing lines joined as roots (crash, 2026-11-10)",
        ("    if roots is None:\n        return None\n    where = ", "    where = "),
    ),
    (
        "a listing name kept past a straight-line rebinding (727fc4a4.3)",
        ("            if value is None or carries(value):\n", "            if True:\n"),
    ),
    (
        "any rebinding clears a listing name (727fc4a4.3)",
        ("            if value is None or carries(value):\n", "            if False:\n"),
    ),
    (
        "only a loop around the write keeps a listing name (ffbd9211.1)",
        (
            "        if _binds(parent, name):\n            return None\n        cur = parent\n",
            (
                "        if isinstance(parent, (ast.For, ast.While)) and _binds(parent, name):\n"
                "            return None\n        cur = parent\n"
            ),
        ),
    ),
    (
        "any binding around the write keeps a listing name (ffbd9211.1)",
        (
            "                    if isinstance(earlier, ast.Assign) and all(\n",
            "                    if False and all(\n",
        ),
    ),
    (
        "a match capture read as no binding (ffbd9211.1)",
        (
            "        if isinstance(n, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)) and n.name == name:\n",
            "        if isinstance(n, ast.ExceptHandler) and n.name == name:\n",
        ),
    ),
    (
        "a match subject not carried to its captures (ffbd9211.1)",
        (
            "            pairs.extend((case.pattern, node.subject) for case in node.cases)\n",
            "            pass\n",
        ),
    ),
    (
        "an rg root tested from the process directory only (ffbd9211.2)",
        (
            "        words.insert(0, os.path.join(os.path.expanduser(str(where)), text))\n",
            "        pass\n",
        ),
    ),
    (
        "grep -H read as printing no names (ffbd9211.3)",
        (
            '_SEARCH_LISTING_LETTERS = {"grep": frozenset("lLrRH"), "rg": frozenset("lH")}',
            '_SEARCH_LISTING_LETTERS = {"grep": frozenset("lLrR"), "rg": frozenset("lH")}',
        ),
    ),
    (
        "--with-filename read as printing no names (ffbd9211.3)",
        ('        "--with-filename",\n    )\n)\n', "    )\n)\n"),
    ),
    (
        "grep over two roots read as printing no names (ffbd9211.3)",
        (
            '    if family == "grep" and not lists:\n        lists = len(operands) > 1\n',
            "",
        ),
    ),
]


def _shared():
    spec = importlib.util.spec_from_file_location("review_file_harness", SHARED)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load %s" % SHARED)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _planted(shared, old, new):
    """The guard with `old` replaced by `new`, run in-process; None when `old` is not in the guard outside its DEFECT declaration."""
    shared._syspath.on_sys_path(str(shared.HERE.parents[2]))
    hookio = importlib.import_module("rediacc_hooks.hookio")
    good = importlib.import_module("rediacc_hooks.guards.%s" % STEM)
    src = pathlib.Path(str(good.__file__)).read_text(encoding="utf-8")
    if old not in shared._outside_defect(src):
        return None
    ns: dict[str, typing.Any] = {"__name__": "planted_" + STEM, "__file__": good.__file__}
    exec(compile(src.replace(old, new), str(good.__file__), "exec"), ns)

    def run(_stem, payload):
        event = hookio.Event(json.dumps(payload))
        # dispatch.py reports a guard that raises and lets the command through, so a planted crash (the errors a broken guard raises) reads as allowed.
        try:
            rc = ns["run"](event)
        except (TypeError, AttributeError, KeyError, IndexError, ValueError) as exc:
            return 0, "guard crashed: %r" % exc
        _rc, out, err = event.result(rc)
        return rc, out + err

    return run


def main():
    shared = _shared()
    shared.SHELL_CASES = [*shared.SHELL_CASES, *OWN_CASES]
    total = shared.main((STEM,))
    own = [(n, {"tool_name": "Bash", "tool_input": {"command": c}}, r) for n, c, r in OWN_CASES]
    fails = 0
    for label, (old, new) in MUTANTS:
        runner = _planted(shared, old, new)
        if runner is None:
            fails += 1
            print("plant %-52s *** FAIL *** it no longer applies to the guard" % label)
            continue
        turned = shared.run_cases(STEM, own, runner, quiet=True)
        fails += not turned
        print(
            "plant %-52s turns %d row(s) %s"
            % (label, turned, "ok" if turned else "*** FAIL *** the harness cannot see it")
        )
    print("MUTANT FAILURES: %d" % fails)
    return 1 if total or fails else 0


if __name__ == "__main__":
    sys.exit(main())
