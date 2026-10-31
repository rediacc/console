#!/usr/bin/env python3
"""Control harness for block_review_file_edit and block_review_file_shell_write, the two halves of "a review record is never edited by hand".

This file runs the Edit half; `test-block_review_file_shell_write.py` beside it runs the shell half through the same code, so each guard has the dedicated `test-<stem>.py` check-hook-integrity credits. Both directions for each half, because a one-sided control is satisfiable by a broken hook: one that always refuses passes the refusal cases, one that never refuses passes the allowed ones. Then each guard's declared DEFECT is planted in-process and the run MUST fail, which is the proof the cases can.

    test-block_review_file_edit.py        run every Edit case through dispatch.py, then the DEFECT run
"""

import ast
import atexit
import importlib
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import typing

HERE = pathlib.Path(__file__).resolve()
# The canonical sys.path hop, through rediacc_hooks/syspath.py loaded by file (the pattern test-block_commit_on_main.py uses).
_SYSPATH = importlib.util.spec_from_file_location(
    "rediacc_hooks_syspath", HERE.parent.parent / "syspath.py"
)
if _SYSPATH is None or _SYSPATH.loader is None:
    raise SystemExit("%s: rediacc_hooks/syspath.py is missing" % __file__)
_syspath = importlib.util.module_from_spec(_SYSPATH)
_SYSPATH.loader.exec_module(_syspath)
DISPATCH = str(HERE.parents[1] / "dispatch.py")
R = "agent/reviews/1231-9/" + "a" * 40 + ".md"
# The clean ledger (PLAN-clean-review-ledger): a clean verdict is a line of this file, protected exactly as a `.md` record is.
L = "agent/reviews/1231-9/clean.jsonl"
# Scripts run BY PATH (#c4542b69), untracked in the system temp directory: one writes a review record, one only reads it. Written before any case runs and removed at exit.
_SCRIPTS = pathlib.Path(tempfile.mkdtemp(prefix="test-review-file-scripts-"))
atexit.register(shutil.rmtree, str(_SCRIPTS), True)
WRITER = _SCRIPTS / "writer.py"
WRITER.write_text("import pathlib\npathlib.Path(%r).write_text('x')\n" % R, encoding="utf-8")
# The same writer run DIRECTLY by its shebang (review 05c4df4d.2): no interpreter word in the command.
DIRECT_WRITER = _SCRIPTS / "direct_writer.py"
DIRECT_WRITER.write_text(
    "#!/usr/bin/env python3\n" + WRITER.read_text(encoding="utf-8"), encoding="utf-8"
)
DIRECT_WRITER.chmod(0o755)
READER = _SCRIPTS / "reader.py"
READER.write_text("import pathlib\nprint(pathlib.Path(%r).read_text())\n" % R, encoding="utf-8")
# A directory symlink whose target is a review directory (review 3f53e99e.1 sweep).
(_SCRIPTS / "agent" / "reviews" / "1231-9").mkdir(parents=True)
(_SCRIPTS / "rl").symlink_to(_SCRIPTS / "agent" / "reviews" / "1231-9", target_is_directory=True)
# A link then `..` (review 9c6817f3.1-.4 sweep): `out/l` points INTO the review directory, `esc` points OUT of it.
(_SCRIPTS / "agent" / "reviews" / "1231-9" / "sub").mkdir()
(_SCRIPTS / "out").mkdir()
(_SCRIPTS / "out" / "l").symlink_to(
    _SCRIPTS / "agent" / "reviews" / "1231-9" / "sub", target_is_directory=True
)
(_SCRIPTS / "agent" / "reviews" / "1231-9" / "esc").symlink_to(
    _SCRIPTS / "out", target_is_directory=True
)
# Review b922f15c.3: a TRACKED script is exempt only while it matches HEAD. Both scripts are committed writing a review file; one is then edited after the commit.
_REPO = _SCRIPTS / "repo"
_REPO.mkdir()
subprocess.run(["git", "init", "-q", str(_REPO)], check=True)
(_REPO / "unchanged.py").write_text(WRITER.read_text(), encoding="utf-8")
(_REPO / "edited.py").write_text("print('reviewed')\n", encoding="utf-8")
subprocess.run(["git", "-C", str(_REPO), "add", "."], check=True)
subprocess.run(
    ["git", "-C", str(_REPO), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x"],
    check=True,
)
(_REPO / "edited.py").write_text(WRITER.read_text(), encoding="utf-8")
# Review b922f15c.4: size never switches the read off. Past the old 1 MiB cap it is read whole; past the budget it is unjudgeable.
PADDED = _SCRIPTS / "padded.py"
PADDED.write_text("#" * (2 << 20) + "\n" + WRITER.read_text(), encoding="utf-8")
HUGE = _SCRIPTS / "huge-agent-reviews.py"
HUGE.write_text("#" * (17 << 20) + "\n", encoding="utf-8")

EDIT_CASES = [
    # (name, payload, refused?)
    (
        "Write over a review file",
        {"tool_name": "Write", "tool_input": {"file_path": "/r/" + R, "content": "x"}},
        True,
    ),
    (
        "Edit downgrading a severity",
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": R, "old_string": "[high]", "new_string": "[low]"},
        },
        True,
    ),
    (
        "MultiEdit of a review file",
        {"tool_name": "MultiEdit", "tool_input": {"file_path": R, "edits": []}},
        True,
    ),
    (
        "NotebookEdit naming one",
        {"tool_name": "NotebookEdit", "tool_input": {"notebook_path": R}},
        True,
    ),
    (
        "Edit of the clean ledger",
        {
            "tool_name": "Edit",
            "tool_input": {"file_path": L, "old_string": '"clean"', "new_string": '"x"'},
        },
        True,
    ),
    (
        "Write over the clean ledger",
        {"tool_name": "Write", "tool_input": {"file_path": "/r/" + L, "content": ""}},
        True,
    ),
    (
        "a plan naming the directory",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "agent/plans/PLAN-x.md", "content": "agent/reviews/"},
        },
        False,
    ),
    (
        "a sibling directory",
        {"tool_name": "Write", "tool_input": {"file_path": "agent/reviews-old/x.md"}},
        False,
    ),
    (
        "an ordinary source file",
        {"tool_name": "Edit", "tool_input": {"file_path": "packages/cli/src/a.ts"}},
        False,
    ),
    ("no path", {"tool_name": "Write", "tool_input": {"content": "x"}}, False),
    # Judged where the write LANDS (review 3f53e99e.1 sweep): each refusal was allowed (rc 0) before, and the control was refused.
    (
        "a .. detour into the directory",
        {"tool_name": "Write", "tool_input": {"file_path": "agent/x/../reviews/1231-9/a.md"}},
        True,
    ),
    (
        "a symlink into the directory",
        {"tool_name": "Write", "tool_input": {"file_path": str(_SCRIPTS / "rl" / "a.md")}},
        True,
    ),
    (
        "a link into the directory, then ..",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": str(_SCRIPTS / "out" / "l") + "/../a.md"},
        },
        True,
    ),
    (
        "a link out of the directory, then ..",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(_SCRIPTS / "agent" / "reviews" / "1231-9" / "esc") + "/../a.md"
            },
        },
        False,
    ),
    (
        "a .. detour out of the directory",
        {"tool_name": "Write", "tool_input": {"file_path": "agent/reviews/../notes/a.md"}},
        False,
    ),
]

SHELL_CASES = [
    ("redirect", "printf 'Resolution: fixed' > %s" % R, True),
    ("append", "echo x >> %s" % R, True),
    ("append to the clean ledger", "echo '{}' >> %s" % L, True),
    ("sed -i on the clean ledger", "sed -i '1d' %s" % L, True),
    ("python appending to the clean ledger", "python3 -c \"open('%s','a').write('x')\"" % L, True),
    ("reading the clean ledger", "cat %s" % L, False),
    ("cat heredoc", "cat > %s <<'EOF'\n# Review\nEOF" % R, True),
    ("tee", "echo x | tee %s" % R, True),
    ("sed -i", "sed -i 's/high/low/' %s" % R, True),
    # In place is sed's and perl's own option parse (review 3f53e99e.2 sweep): each refusal was allowed (rc 0) before.
    ("sed -Ei", "sed -Ei 's/high/low/' %s" % R, True),
    ("perl -pi -e", "perl -pi -e 's/high/low/' %s" % R, True),
    ("sed -E without -i prints, never writes", "sed -E 's/high/low/' %s" % R, False),
    ("cp onto the directory", "cp /tmp/x.md agent/reviews/1231-9/", True),
    ("mv onto a file", "mv /tmp/x.md %s" % R, True),
    ("truncate", "truncate -s 0 %s" % R, True),
    ("python -c write", "python3 -c \"open('%s','w').write('x')\"" % R, True),
    (
        "python heredoc write_text",
        "python3 - <<'EOF'\nimport pathlib\npathlib.Path('%s').write_text('x')\nEOF" % R,
        True,
    ),
    (
        "python heredoc via a variable",
        "python3 - <<'EOF'\np = '%s'\nopen(p, 'w').write('x')\nEOF" % R,
        True,
    ),
    # #78afdc0b: a heredoc inside a payload is read from the payload's own text. Its offsets were applied to the command line, so this program read as a fragment of it (rc 0 at c72518af1).
    (
        "python heredoc inside sh -c",
        "sh -c \"python3 - <<'E'\nimport pathlib\npathlib.Path('%s').write_text('x')\nE\"" % R,
        True,
    ),
    ("after cd", "cd agent/reviews/1231-9 && echo x > a.md", True),
    ("inside sh -c", "sh -c 'echo x > %s'" % R, True),
    ("cat reads one", "cat %s" % R, False),
    ("grep the directory", "grep -rn high agent/reviews/", False),
    ("echo the path", "echo 'agent/reviews/1231-9/'", False),
    ("commit carrying them", "git commit -F /tmp/m.txt -- agent/reviews/1231-9/", False),
    ("git add", "git add -- %s" % R, False),
    (
        "the mark verb",
        ".claude/hooks/stop/worklist.py --review-mark abcd1234 aaaaaaaa.1 fixed %s" % ("b" * 40),
        False,
    ),
    ("the reviewer", "python3 .claude/hooks/stop/wl_review.py --run abc --branch 1231-9", False),
    ("copy out of the directory", "cp %s /tmp/x.md" % R, False),
    ("python read", "python3 -c \"print(open('%s').read())\"" % R, False),
    # The false positive found on this guard's first live run: a python heredoc patching another module whose new text only MENTIONS the directory.
    (
        "python patching a module that mentions the path",
        "python3 - <<'EOF'\nimport pathlib\np = pathlib.Path('w.py')\ns = '# keyed agent/reviews/<branch>/'\np.write_text(s)\nEOF",
        False,
    ),
    (
        "a script written by cat, then run",
        "cat > /tmp/f.py <<'EOF'\nx = 'agent/reviews/'\nEOF\npython3 /tmp/f.py",
        False,
    ),
    # The false positive of 2026-10-03: a python heredoc rewriting a test whose GitHub link names the directory. A URL is a web page, not a file on disk.
    (
        "python rewriting a URL that names the path",
        (
            "python3 - <<'EOF'\nimport pathlib\np = pathlib.Path('t.py')\n"
            "p.write_text(p.read_text().replace('\"https://github.com/o/r/blob/h/agent/reviews/b/x.md\"', 'U'))\nEOF"
        ),
        False,
    ),
    (
        "python heredoc write to an absolute review path",
        "python3 - <<'EOF'\nimport pathlib\npathlib.Path('/home/u/c/%s').write_text('x')\nEOF" % R,
        True,
    ),
    ("unrelated redirect", "echo x > /tmp/out.txt", False),
    # A copy's destination is getopt's answer (review cac47d16.1 sweep): each refusal was allowed (rc 0) before.
    ("cp -t into the directory", "cp -t agent/reviews/1231-9 /tmp/x.md", True),
    ("mv --target-directory=", "mv --target-directory=agent/reviews/1231-9 /tmp/x.md", True),
    ("a value option after the operands", "cp /tmp/x.md %s -S .bak" % R, True),
    ("xargs appends the destination", "echo agent/reviews/1231-9/ | xargs cp /tmp/x.md", True),
    ("cp -t out of the directory", "cp -t /tmp %s" % R, False),
    # A glob or brace spells the directory without the word (#7094b75e): each refusal was allowed (rc 0) before, the first two by the text prefilter.
    ("a fed glob under cd", "cd agent && echo revi*s/1231-9/x.md | xargs cp /tmp/a.md", True),
    ("a ? glob under cd", "cd agent && cp /tmp/a.md revi?ws/1231-9/", True),
    ("a bracket glob", "cp /tmp/a.md agent/revie[w]s/1231-9/", True),
    ("a brace", "cp /tmp/a.md agent/{reviews,x}/1231-9/", True),
    ("a redirect through two globs", "echo x > ag*/rev*/1231-9/new.md", True),
    # The reading of a deep glob is not lost to a cap on combinations (review c6dc18ec.1): five `a*t` segments read as `agent` or as themselves, so 2^7 combinations precede the one where `ag*` and `revi*s` spell the directory, and a cap of 64 never reached it.
    (
        "a deep glob past the old combination cap",
        "echo x > ag*/revi*s/a*t/a*t/a*t/a*t/a*t/f.md",
        True,
    ),
    ("a deep glob of stars", "echo x > */*/*/*/*/*/*/f.md", True),
    ("the same deep glob read out", "cat ag*/revi*s/a*t/a*t/a*t/a*t/a*t/f.md > /tmp/x", False),
    (
        "a deep glob that cannot spell the directory",
        "echo x > docs/ab*/cd*/ef*/gh*/ij*/kl*/f.md",
        False,
    ),
    ("a glob read out", "cat agent/revi*s/1231-9/clean.jsonl > /tmp/x", False),
    ("a glob in arithmetic text", "echo 3*4 > /tmp/x", False),
    ("a brace elsewhere", "cp /tmp/a.md /tmp/{a,b}/c.md", False),
    # Every way Python fills a template (review 6dcf79c7.1-.2): each refusal was allowed (rc 0) before.
    (
        "str.format with a keyword field",
        "python3 - <<'EOF'\nimport os\nos.system('echo x > {p}'.format(p='%s'))\nEOF" % R,
        True,
    ),
    (
        "str.format with numbered fields out of order",
        "python3 - <<'EOF'\nimport os\nos.system('{1} > {0}'.format('%s', 'echo x'))\nEOF" % R,
        True,
    ),
    (
        "str.format_map over a dict",
        "python3 - <<'EOF'\nimport os\nos.system('echo x > {p}'.format_map({'p': '%s'}))\nEOF" % R,
        True,
    ),
    (
        "a star width takes its own argument",
        "python3 - <<'EOF'\nimport os\nos.system('echo x > %%*s' %% (0, '%s'))\nEOF" % R,
        True,
    ),
    (
        "a percent mapping key",
        "python3 - <<'EOF'\nimport os\nos.system('echo x > %%(p)s' %% {'p': '%s'})\nEOF" % R,
        True,
    ),
    (
        "str.format putting the path in echoed text",
        "python3 - <<'EOF'\nimport os\nos.system('echo {p} > /tmp/x'.format(p='%s'))\nEOF" % R,
        False,
    ),
    (
        "a star width before echoed text",
        "python3 - <<'EOF'\nimport os\nos.system('echo %%*s > /tmp/x' %% (3, '%s'))\nEOF" % R,
        False,
    ),  # A program read from a FILE is read like one from a heredoc (#c4542b69): each refusal was allowed (rc 0) before.
    ("a python script by path writing a review file", "python3 %s" % WRITER, True),
    (
        "a python script by path after a cd",
        "cd %s && python3 -u %s" % (WRITER.parent, WRITER.name),
        True,
    ),
    ("a python script by path that only reads", "python3 %s" % READER, False),
    ("a script run directly by its shebang writing a review file", str(DIRECT_WRITER), True),
    ("the same script behind timeout", "timeout 5 %s" % DIRECT_WRITER, True),
    # The interpreter's own options, parsed as it parses them (review 63ee61e3.1): each refusal was allowed (rc 0) before.
    ("python -E then the script", "python3 -E %s" % WRITER, True),
    ("python -W takes its own value", "python3 -W ignore %s" % WRITER, True),
    ("a -c after the script is the script's argument", "python3 %s -c x" % WRITER, True),
    (
        "a script that cannot be read fails open",
        "python3 %s" % (WRITER.parent / "absent-agent-reviews.py"),
        False,
    ),
    # Review b922f15c.1-.4: each refusal was allowed (rc 0) before.
    (
        "a script written and run in one command",
        "cat > %s/later.py <<'EOF'\n%sEOF\npython3 %s/later.py"
        % (_SCRIPTS, WRITER.read_text(), _SCRIPTS),
        True,
    ),
    # #7ab88f34: the same scripts run DIRECTLY by the shebang their writer put on the first line. The file does not exist when the hook runs, so its first line was read from the disk, named nothing, and the program ran unread (rc 0, against rc 2 for the interpreter-word form).
    (
        "a script written and run directly by its shebang in one command",
        "cat > %s/later_direct.py <<'EOF'\n#!/usr/bin/env python3\n%sEOF\nchmod +x %s/later_direct.py; %s/later_direct.py"
        % (_SCRIPTS, WRITER.read_text(), _SCRIPTS, _SCRIPTS),
        True,
    ),
    (
        "a script printed and run directly by its shebang in one command",
        'printf \'#!/usr/bin/env python3\\nopen("%s", "w").write("x")\\n\' > %s/printed.py; chmod +x %s/printed.py; %s/printed.py'
        % (L, _SCRIPTS, _SCRIPTS, _SCRIPTS),
        True,
    ),
    (
        "a script written and run directly by its shebang that only reads",
        "cat > %s/later_direct_reader.py <<'EOF'\n#!/usr/bin/env python3\n%sEOF\nchmod +x %s/later_direct_reader.py; %s/later_direct_reader.py"
        % (_SCRIPTS, READER.read_text(), _SCRIPTS, _SCRIPTS),
        False,
    ),
    (
        "a script written and run in one command that only reads",
        "cat > %s/later_reader.py <<'EOF'\n%sEOF\npython3 %s/later_reader.py"
        % (_SCRIPTS, READER.read_text(), _SCRIPTS),
        False,
    ),
    (
        "a script copied in and run, the command naming the directory",
        "cp /tmp/nowhere.py %s/agent-reviews-tool.py && python3 %s/agent-reviews-tool.py"
        % (_SCRIPTS, _SCRIPTS),
        True,
    ),
    (
        "a script copied in and run, the command naming nothing",
        "cp /tmp/nowhere.py %s/tool.py && python3 %s/tool.py" % (_SCRIPTS, _SCRIPTS),
        False,
    ),
    ("a tracked script edited after its commit", "python3 %s" % (_REPO / "edited.py"), True),
    ("a tracked script unchanged since its commit", "python3 %s" % (_REPO / "unchanged.py"), False),
    ("a script past the old 1 MiB cap is read whole", "python3 %s" % PADDED, True),
    ("a script past the read budget is unjudgeable", "python3 %s" % HUGE, True),
    # Review fc3f376a.2: a script written from a variable is judged by what bash expands it to. Each refusal was allowed (rc 0) before.
    (
        "a script echoed from a variable and run",
        "P=%s; echo \"import pathlib; pathlib.Path('$P').write_text('x')\" > %s/echoed && python3 %s/echoed"
        % (R, _SCRIPTS, _SCRIPTS),
        True,
    ),
    (
        "a script echoed from an unknown source and run",
        'echo "$(cat /tmp/nowhere)" > %s/agent-reviews-tool && python3 %s/agent-reviews-tool'
        % (_SCRIPTS, _SCRIPTS),
        True,
    ),
    (
        "a script echoed from a variable that only reads",
        "P=%s; echo \"import pathlib; print(pathlib.Path('$P').read_text())\" > %s/echoed_reader && python3 %s/echoed_reader"
        % (R, _SCRIPTS, _SCRIPTS),
        False,
    ),
    # Worklist item ff3ab826: a tool's own output option is a write, and a command the reader table does not list is read as writing any word it names (`shellscan.output_landings`). Each refusal was allowed (rc 0) before.
    ("sort -o", "sort -o %s /tmp/a" % R, True),
    ("sort --output=", "sort --output=%s /tmp/a" % R, True),
    ("sort with the value in a bundle", "sort -uo%s /tmp/a" % R, True),
    ("sort --out, a unique prefix", "sort --out %s /tmp/a" % R, True),
    ("sort -o after the operands", "sort /tmp/a -o %s" % R, True),
    ("curl -o", "curl -o %s https://e.x/a" % R, True),
    ("wget -O", "wget -O %s https://e.x/a" % R, True),
    ("tar -cf", "tar -cf %s /tmp/a" % R, True),
    ("tar -C into the directory", "tar -xf /tmp/a.tar -C agent/reviews/1231-9", True),
    ("openssl -out", "openssl enc -in /tmp/a -out %s" % R, True),
    ("git diff --output=", "git diff --output=%s HEAD~1" % R, True),
    ("git format-patch -o", "git format-patch -o agent/reviews/1231-9 -1", True),
    ("pandoc -o", "pandoc /tmp/a.md -o %s" % R, True),
    ("xargs appends the value of sort -o", "echo %s | xargs sort /tmp/a -o" % R, True),
    (
        "xargs -I puts the file in --output=",
        "echo %s | xargs -I{} sort --output={} /tmp/a" % R,
        True,
    ),
    (
        "a launched sort -o onto what find names",
        r"find agent/reviews -name '*.md' -exec sort -o {} /tmp/a \;",
        True,
    ),
    ("find -fprint", "find /tmp -name a -fprint %s" % R, True),
    ("sed's w command", "sed -n 'w %s' /tmp/a" % R, True),
    ("an awk redirect", "awk '{print > \"%s\"}' /tmp/a" % R, True),
    ("uniq's output operand", "uniq /tmp/a %s" % R, True),
    ("touch", "touch %s" % R, True),
    ("prettier --write", "prettier --write %s" % R, True),
    ("a variable holding the file", "F=%s; sort -o $F /tmp/a" % R, True),
    ("a shell function handed the file", 'f() { touch "$1"; }; f %s' % R, True),
    ("sort reads one", "sort %s" % R, False),
    ("sort -o elsewhere", "sort -o /tmp/out %s" % R, False),
    ("wc reads one", "wc -l %s" % R, False),
    ("head reads one", "head -5 %s" % R, False),
    ("git log over the directory", "git log --oneline -- agent/reviews/", False),
    ("git diff --stat over the directory", "git diff --stat agent/reviews/", False),
    ("git diff --output= elsewhere", "git diff --output=/tmp/d -- agent/reviews/", False),
    ("diff reads one", "diff %s /tmp/b" % R, False),
    ("jq reads the clean ledger", "jq . %s" % L, False),
    (
        "curl -o elsewhere, a URL naming the path",
        "curl -o /tmp/out https://e.x/agent/reviews/a",
        False,
    ),
    ("xargs feeds a review file to sort", "echo %s | xargs sort" % R, False),
    ("echo spelling a sort -o", "echo sort -o %s /tmp/a" % R, False),
    ("sed substituting the path away", "sed 's|agent/reviews/||' /tmp/list", False),
    ("rm keeps its verdict", "rm %s" % R, False),
    ("git checkout keeps its verdict", "git checkout -- %s" % R, False),
    # The reads the review workflow itself runs.
    ("grep -n over the records", "grep -n Resolution agent/reviews/1008-1/*.md", False),
    ("sed -n prints a range", "sed -n 1,20p %s" % R, False),
    ("git add of the directory", "git add -- agent/reviews/1008-1/", False),
    (
        "git commit of the directory",
        "git commit -F /tmp/m -- agent/reviews/1008-1/",
        False,
    ),
    ("ls of the directory", "ls agent/reviews/1008-1/", False),
    ("tail of the clean ledger", "tail -1 %s" % L, False),
    (
        "the mark verb with evidence naming a record",
        (
            "python3 .claude/hooks/stop/worklist.py --review-mark d778be9d ab12cd34.1 not-a-bug "
            "'x agent/reviews/1008-1/x.md:3'"
        ),
        False,
    ),
    # Review 906a4d56.1 and .2: an awk option's value placed where gawk does not place it hid the program. Each refusal was allowed (rc 0) before; `-o` pretty-prints without running the program, and is refused with the rest because the reading no longer rests on which word that is.
    ("gawk -p, then a program that redirects", "gawk -p '{print > \"%s\"}' /tmp/a" % R, True),
    ("gawk -d, then a program that redirects", "gawk -d '{print > \"%s\"}' /tmp/a" % R, True),
    ("gawk -o, then a program that redirects", "gawk -o '{print > \"%s\"}' /tmp/a" % R, True),
    (
        "gawk --profile, then a program that redirects",
        "gawk --profile '{print > \"%s\"}' /tmp/a" % R,
        True,
    ),
    ("gawk -W, then a program that redirects", "gawk -W lint '{print > \"%s\"}' /tmp/a" % R, True),
    (
        "mawk -W, then a program that redirects",
        "mawk -W interactive '{print > \"%s\"}' /tmp/a" % R,
        True,
    ),
    ("gawk -W dump-variables=", "gawk -W dump-variables=%s '{print}' /tmp/a" % R, True),
    # The sweep of the class: xxd's options are whole words, tree hands `-o` a later word, and an awk writes beside its input through FILENAME.
    ("xxd -ps, then its output operand", "xxd -ps /tmp/in %s" % R, True),
    ("tree -Lo hands -o the second word", "tree -Lo 2 %s agent" % R, True),
    ("awk writing beside FILENAME", "awk '{print > (FILENAME \".bak\")}' %s" % R, True),
    ("gawk reads one", "gawk '{print $1}' %s" % R, False),
    ("gawk -W lint reads one", "gawk -W lint '{print $1}' %s" % R, False),
    ("gawk -d reads one", "gawk -d '{print $1}' %s" % R, False),
    ("gawk -p with its file attached reads one", "gawk -p/tmp/prof '{print $1}' %s" % R, False),
    ("awk splitting on a pipe reads one", "awk -F'|' '{print $2}' %s" % R, False),
    ("awk comparing reads one", "awk '$3 > 0' %s" % R, False),
    ("xxd -ps reads one", "xxd -ps %s" % R, False),
    ("xxd -s -l reads one", "xxd -s 4 -l 16 %s" % R, False),
    ("tree without -o", "tree -L 2 agent/reviews", False),
    # A read this session ran for real: a program with a regex alternation and its own assignments, from inside the directory. A draft of this fix read what follows the program's `=` as a file and refused it.
    (
        "awk filtering findings from inside the directory",
        "cd agent/reviews/1008-1 && awk '/^### /{p=0} /^### (0b8baf43.1|599bfb94.1)/{p=1} p' x.md",
        False,
    ),
    # Review fd4eda1a.1: whether an awk program may redirect is a rule over its text that follows nothing, so a redirect into a literal elsewhere is refused while the program reads a review file, and allowed over any other file.
    ("awk redirecting elsewhere while it reads one", "awk '{print > \"x\"}' %s" % R, True),
    (
        "the same awk program over another file",
        "awk '{print > \"x\"}' /tmp/agent-reviews-list.txt",
        False,
    ),
    # Review fd4eda1a.3: the rule is lexical, and this refusal is its stated over-read. The program prints nothing.
    ("over-read: an awk regex spelling print beside a pipe", "awk '/print|x/' %s" % R, True),
    ("an awk regex with an alternation and no print", "awk '/prin|x/' %s" % R, False),
    (
        "a loop reading the records after a cd",
        "cd agent/reviews/1008-1 && grep -l open *.md | while read f; do head -1 $f; done",
        False,
    ),
    # A git ref verb's positional words are refs, refspecs and patterns, never a file it writes: two adjacent `*` segments in a glob refspec are not `agent/reviews`. Each allowance was refused (rc 2) before.
    ("push of a glob refspec", "git push --dry-run . 'refs/heads/*/*:refs/heads/q/*/*'", False),
    ("fetch of a glob refspec", "git fetch . 'refs/heads/*/*:refs/x/*/*'", False),
    ("pull of a glob refspec", "git pull . 'refs/heads/*/*'", False),
    ("ls-remote of a glob pattern", "git ls-remote . 'refs/*/*'", False),
    ("branch --list of a glob", "git branch --list '*/*'", False),
    ("tag -l of a glob", "git tag -l '*/*'", False),
    ("for-each-ref of a glob", "git for-each-ref 'refs/*/*'", False),
    ("log over a glob pathspec", "git log -- '*/*/x'", False),
    ("push under -C of a glob refspec", "git -C /tmp push . 'refs/*/*:refs/*/*'", False),
    # The other direction: an option of the same verb, a path remote, and a verb that writes a path it names stay refused.
    ("push whose remote is the directory", "git push agent/reviews/1231-9 main", True),
    ("push --receive-pack naming the directory", "git push --receive-pack=%s o" % R, True),
    ("push --receive-pack value after the remote", "git push origin --receive-pack %s" % R, True),
    ("fetch --upload-pack value after the remote", "git fetch origin --upload-pack %s" % R, True),
    ("push -o value before the remote", "git push -o %s origin main" % R, True),
    (
        "push --force then a glob refspec",
        "git push origin --force 'refs/heads/*/*:refs/heads/q/*/*'",
        False,
    ),
    # A ref verb's separate-form option value is a message or a ref, not a program or path: it is dropped with the positionals, where a remote verb's is judged.
    ("update-ref -m message that is a glob", "git update-ref -m '*/*' refs/heads/q HEAD", False),
    ("tag -m message that is a glob", "git tag -m '*/*' v1", False),
    ("push -o value that is a glob, a remote verb", "git push -o '*/*' origin main", True),
    (
        "update-ref -m naming the directory is still an option",
        "git update-ref -m=%s refs/x HEAD" % R,
        True,
    ),
    ("clone into a glob that reads as the directory", "git clone . '*/*'", True),
    ("worktree add at a glob that reads as the directory", "git worktree add '*/*'", True),
]


def via_dispatch(stem, payload):
    p = subprocess.run(
        [sys.executable, DISPATCH, stem],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    return p.returncode, p.stdout + p.stderr


def _outside_defect(src: str, *names: str) -> str:
    """`src` with every top-level `DEFECT` (or named) assignment removed, so a needle search cannot be satisfied by the declaration that names it.

    `old in src` alone stays true after the guarded line is deleted, because the declaration itself contains the text it plants (measured 2026-10-05).
    """
    wanted = names or ("DEFECT",)
    cut = [
        n
        for n in ast.parse(src).body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id in wanted for t in n.targets)
    ]
    return "\n".join(
        line
        for i, line in enumerate(src.split("\n"), 1)
        if not any(n.lineno <= i <= (n.end_lineno or n.lineno) for n in cut)
    )


def defect_runner(stem):
    """The guard with its declared DEFECT planted, run in-process."""
    _syspath.on_sys_path(str(HERE.parents[2]))
    hookio = importlib.import_module("rediacc_hooks.hookio")
    good = importlib.import_module("rediacc_hooks.guards.%s" % stem)
    old, new = good.DEFECT
    src = pathlib.Path(str(good.__file__)).read_text(encoding="utf-8")
    if old not in _outside_defect(src):
        raise SystemExit("the DEFECT no longer applies to %s outside its own declaration" % stem)
    ns: dict[str, typing.Any] = {"__name__": "broken_" + stem, "__file__": good.__file__}
    exec(compile(src.replace(old, new), str(good.__file__), "exec"), ns)

    def run(_stem, payload):
        event = hookio.Event(json.dumps(payload))
        rc = ns["run"](event)
        _rc, out, err = event.result(rc)
        return rc, out + err

    return run


def run_cases(stem, cases, runner, quiet=False):
    fails = 0
    for name, payload, refused in cases:
        rc, text = runner(stem, payload)
        blocked = rc != 0
        ok = blocked == refused and (not refused or "--review-mark" in text)
        fails += not ok
        if not quiet:
            print(
                "%-46s want=%-8s %s"
                % (
                    name,
                    "BLOCKED" if refused else "allowed",
                    "ok" if ok else "*** FAIL *** " + text[:160],
                )
            )
    return fails


def main(stems=("block_review_file_edit",)):
    shell = [(n, {"tool_name": "Bash", "tool_input": {"command": c}}, r) for n, c, r in SHELL_CASES]
    suites = {"block_review_file_edit": EDIT_CASES, "block_review_file_shell_write": shell}
    total = 0
    for stem in stems:
        cases = suites[stem]
        print("== %s" % stem)
        total += run_cases(stem, cases, via_dispatch)
        refusals = sum(1 for c in cases if c[2])
        if refusals < 4 or len(cases) - refusals < 4:
            print("FLOOR: at least 4 cases of each direction")
            total += 1
        planted = run_cases(stem, cases, defect_runner(stem), quiet=True)
        print(
            "DEFECT planted in %s: %d case(s) fail%s"
            % (stem, planted, "" if planted else "  *** the suite cannot fail ***")
        )
        total += planted == 0
    print("FAILURES: %d" % total)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
