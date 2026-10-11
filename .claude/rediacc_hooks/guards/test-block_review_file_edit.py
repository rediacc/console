#!/usr/bin/env python3
"""Control harness for block_review_file_edit and block_review_file_shell_write, the two halves of "a review record is never edited by hand".

This file runs the Edit half; `test-block_review_file_shell_write.py` beside it runs the shell half through the same code, so each guard has the dedicated `test-<stem>.py` check-hook-integrity credits. Both directions for each half, because a one-sided control is satisfiable by a broken hook: one that always refuses passes the refusal cases, one that never refuses passes the allowed ones. Then each guard's declared DEFECT is planted in-process and the run MUST fail, which is the proof the cases can.

    test-block_review_file_edit.py        run every Edit case through dispatch.py, then the DEFECT run
"""

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
R = "agent/reviews/0930-1/" + "a" * 40 + ".md"
# The clean ledger (PLAN-clean-review-ledger): a clean verdict is a line of this file, protected exactly as a `.md` record is.
L = "agent/reviews/0930-1/clean.jsonl"
# Scripts run BY PATH (#c4542b69), untracked in the system temp directory: one writes a review record, one only reads it. Written before any case runs and removed at exit.
_SCRIPTS = pathlib.Path(tempfile.mkdtemp(prefix="test-review-file-scripts-"))
atexit.register(shutil.rmtree, str(_SCRIPTS), True)
WRITER = _SCRIPTS / "writer.py"
WRITER.write_text("import pathlib\npathlib.Path(%r).write_text('x')\n" % R, encoding="utf-8")
READER = _SCRIPTS / "reader.py"
READER.write_text("import pathlib\nprint(pathlib.Path(%r).read_text())\n" % R, encoding="utf-8")

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
    ("cp onto the directory", "cp /tmp/x.md agent/reviews/0930-1/", True),
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
    ("after cd", "cd agent/reviews/0930-1 && echo x > a.md", True),
    ("inside sh -c", "sh -c 'echo x > %s'" % R, True),
    ("cat reads one", "cat %s" % R, False),
    ("grep the directory", "grep -rn high agent/reviews/", False),
    ("echo the path", "echo 'agent/reviews/0930-1/'", False),
    ("commit carrying them", "git commit -F /tmp/m.txt -- agent/reviews/0930-1/", False),
    ("git add", "git add -- %s" % R, False),
    (
        "the mark verb",
        ".claude/hooks/stop/worklist.py --review-mark abcd1234 aaaaaaaa.1 fixed %s" % ("b" * 40),
        False,
    ),
    ("the reviewer", "python3 .claude/hooks/stop/wl_review.py --run abc --branch 0930-1", False),
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
    ("cp -t into the directory", "cp -t agent/reviews/0930-1 /tmp/x.md", True),
    ("mv --target-directory=", "mv --target-directory=agent/reviews/0930-1 /tmp/x.md", True),
    ("a value option after the operands", "cp /tmp/x.md %s -S .bak" % R, True),
    ("xargs appends the destination", "echo agent/reviews/0930-1/ | xargs cp /tmp/x.md", True),
    ("cp -t out of the directory", "cp -t /tmp %s" % R, False),
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
    # The interpreter's own options, parsed as it parses them (review 63ee61e3.1): each refusal was allowed (rc 0) before.
    ("python -E then the script", "python3 -E %s" % WRITER, True),
    ("python -W takes its own value", "python3 -W ignore %s" % WRITER, True),
    ("a -c after the script is the script's argument", "python3 %s -c x" % WRITER, True),
    (
        "a script that cannot be read fails open",
        "python3 %s" % (WRITER.parent / "absent-agent-reviews.py"),
        False,
    ),
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
    import ast  # noqa: PLC0415 -- only the planted-defect controls need it

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
    exec(compile(src.replace(old, new), str(good.__file__), "exec"), ns)  # noqa: S102

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
