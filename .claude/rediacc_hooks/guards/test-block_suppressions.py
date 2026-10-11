#!/usr/bin/env python3
"""Control harness for block_suppressions and block_suppressions_shell_write, the two halves of "no NEW inline suppression marker" (operator ruling 2026-10-08).

This file runs the edit half; `test-block_suppressions_shell_write.py` beside it runs the shell half through the same code, so each guard has the dedicated `test-<stem>.py` check-hook-integrity credits. Both directions for each half, because a one-sided control is satisfiable by a broken hook. Then each guard's declared DEFECT is planted in-process and the run MUST fail, which is the proof the cases can.

THE DISK CASES are the ones the payload-only EDGE_CASES cannot carry: an edit to a file that ALREADY holds a marker. They run in a scratch directory under the repository (the guards ignore paths outside it), which is created fresh and removed on exit. One of them is the control for the whole-file comparison: an Edit whose `new_string` alone would tokenize as a comment, but which lands inside a DOCSTRING of the real file and is therefore prose.

Marker fixtures are assembled from halves, so this file never holds a literal marker.

    test-block_suppressions.py            the edit half, then its DEFECT run
"""

import ast
import atexit
import importlib
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import typing

HERE = pathlib.Path(__file__).resolve()
_SYSPATH = importlib.util.spec_from_file_location(
    "rediacc_hooks_syspath", HERE.parent.parent / "syspath.py"
)
if _SYSPATH is None or _SYSPATH.loader is None:
    raise SystemExit("%s: rediacc_hooks/syspath.py is missing" % __file__)
_syspath = importlib.util.module_from_spec(_SYSPATH)
_SYSPATH.loader.exec_module(_syspath)
DISPATCH = str(HERE.parents[1] / "dispatch.py")
REPO = HERE.parents[3]

NQ = "# noq" + "a"
TI = "# type: ignor" + "e"
TSI = "@ts-ignor" + "e"

SCRATCH = pathlib.Path(
    tempfile.mkdtemp(prefix="test-block-suppressions-", dir=str(REPO / ".ci" / "cache"))
)
atexit.register(shutil.rmtree, str(SCRATCH), True)
KEPT = SCRATCH / "kept.py"
KEPT_TEXT = 'import os  %s: F401\n\n\ndef f():\n    """doc"""\n    return os.sep\n' % NQ
OUTSIDE = pathlib.Path(tempfile.gettempdir()) / "test-block-suppressions-outside.py"
# Scripts run BY PATH (#f3f36655): untracked (the scratch directory is under the gitignored `.ci/cache`), one writing a marker in each language family, one writing none.
MARKER_SCRIPT = SCRATCH / "marker_writer.py"
MARKER_PROGRAM = "import pathlib\npathlib.Path(%r).write_text('y = 1  %s: B010\\n')\n" % (
    str(KEPT),
    NQ,
)
MARKER_JS = SCRATCH / "marker_writer.js"
CLEAN_SCRIPT = SCRATCH / "clean_writer.py"
ABSENT_SCRIPT = SCRATCH / "absent.py"
# Symlinks (review 3f53e99e.1 sweep): a directory link OUTSIDE the tree pointing at the scratch directory inside it, and a `.txt` link to a Python file.
OUTSIDE_LINK = pathlib.Path(tempfile.mkdtemp(prefix="test-block-suppressions-link-")) / "into-repo"
atexit.register(shutil.rmtree, str(OUTSIDE_LINK.parent), True)
TXT_LINK = SCRATCH / "notes.txt"
# Review b922f15c.1-.4 fixtures: a git repo outside the tree whose committed scripts write a marker (one edited after the commit), a script past the old 1 MiB cap, and one past the read budget whose NAME carries the marker token, which is what lets the pre-filter match.
TRACK_REPO = pathlib.Path(tempfile.mkdtemp(prefix="test-block-suppressions-repo-"))
atexit.register(shutil.rmtree, str(TRACK_REPO), True)
PADDED = SCRATCH / "padded.py"
HUGE = SCRATCH / ("huge_noq" + "a_tool.py")
# A TRACKED script that carries markers in its own source and writes files: running it adds nothing the tree does not already hold.
TRACKED_SCRIPT = REPO / ".claude" / "hooks" / "stop" / "worklist.py"


def _world():
    SCRATCH.mkdir(parents=True, exist_ok=True)
    KEPT.write_text(KEPT_TEXT, encoding="utf-8")
    OUTSIDE.write_text("x = 1\n", encoding="utf-8")
    MARKER_SCRIPT.write_text(MARKER_PROGRAM, encoding="utf-8")
    MARKER_JS.write_text(
        "require('fs').writeFileSync('/tmp/x.ts', '// %s\\nlet x = 1\\n')\n" % TSI,
        encoding="utf-8",
    )
    CLEAN_SCRIPT.write_text(
        "import pathlib\npathlib.Path(%r).write_text('y = 1\\n')\n" % str(OUTSIDE), encoding="utf-8"
    )
    if not OUTSIDE_LINK.is_symlink():
        OUTSIDE_LINK.symlink_to(SCRATCH, target_is_directory=True)
    if not TXT_LINK.is_symlink():
        TXT_LINK.symlink_to(KEPT)
    if not (TRACK_REPO / ".git").is_dir():
        subprocess.run(["git", "init", "-q", str(TRACK_REPO)], check=True)
        (TRACK_REPO / "unchanged.py").write_text(MARKER_PROGRAM, encoding="utf-8")
        (TRACK_REPO / "edited.py").write_text("print('reviewed')\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(TRACK_REPO), "add", "."], check=True)
        subprocess.run(
            [
                *("git", "-C", str(TRACK_REPO), "-c", "user.name=t", "-c", "user.email=t@t"),
                "commit",
                "-qm",
                "x",
            ],
            check=True,
        )
        (TRACK_REPO / "edited.py").write_text(MARKER_PROGRAM, encoding="utf-8")
    if not PADDED.is_file():
        PADDED.write_text("#" * (2 << 20) + "\n" + MARKER_PROGRAM, encoding="utf-8")
    if not HUGE.is_file():
        HUGE.write_text("#" * (17 << 20) + "\n", encoding="utf-8")


def _edit(path, old, new):
    return {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(path), "old_string": old, "new_string": new},
    }


EDIT_CASES = [
    # (name, payload, refused?)
    (
        "Edit adding a coded marker",
        _edit("src/a.py", "m.x = 1", "setattr(m, 'x', 1)  %s: B010" % NQ),
        True,
    ),
    (
        "Write of a new file with a type ignore",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "src/n.py", "content": "x = f()  %s\n" % TI},
        },
        True,
    ),
    ("Edit adding a TS directive", _edit("src/a.ts", "x;", "// %s\nx;" % TSI), True),
    (
        "Edit adding a second code to a marker on disk",
        _edit(KEPT, "import os  %s: F401" % NQ, "import os  %s: F401, E402" % NQ),
        True,
    ),
    (
        "Write appending a marker to a file on disk",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": str(KEPT), "content": KEPT_TEXT + "y = 1  %s: B010\n" % NQ},
        },
        True,
    ),
    (
        "MultiEdit whose second edit adds one",
        {
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": str(KEPT),
                "edits": [
                    {"old_string": "doc", "new_string": "Doc."},
                    {"old_string": "return os.sep", "new_string": "return os.sep  %s: RET504" % NQ},
                ],
            },
        },
        True,
    ),
    # CONTROLS.
    (
        "Edit elsewhere in a file that keeps its marker",
        _edit(KEPT, "return os.sep", "return os.sep + '/'"),
        False,
    ),
    (
        "Write re-saving a file with its marker unchanged",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": str(KEPT), "content": KEPT_TEXT + "y = 1\n"},
        },
        False,
    ),
    ("Edit removing the marker", _edit(KEPT, "import os  %s: F401" % NQ, "import os"), False),
    # The whole-file control: `new_string` alone tokenizes as a comment, but in the file it is inside a docstring.
    (
        "Edit inside a docstring that names the marker",
        _edit(KEPT, "doc", "Never write %s: B010 here." % NQ),
        False,
    ),
    ("a file outside the repository", _edit(OUTSIDE, "x = 1", "x = 1  %s: B010" % NQ), False),
    # Judged where the edit LANDS (review 3f53e99e.1 sweep): each refusal was allowed (rc 0) before.
    (
        "a directory link outside the tree into it",
        _edit(OUTSIDE_LINK / KEPT.name, "return os.sep", "return os.sep  %s: B010" % NQ),
        True,
    ),
    (
        "a .txt link to a Python file",
        _edit(TXT_LINK, "return os.sep", "return os.sep  %s: B010" % NQ),
        True,
    ),
    ("Markdown teaching the rule", _edit("docs/a.md", "x", "Never write `%s: B010`." % NQ), False),
    ("an ordinary edit", _edit("src/a.ts", "x", "y"), False),
]

SHELL_CASES = [
    (
        "cat heredoc adding a marker to a file on disk",
        "cat > %s <<'EOF'\n%sy = 1  %s: B010\nEOF" % (KEPT, KEPT_TEXT, NQ),
        True,
    ),
    ("append to a file on disk", "echo 'y = 1  %s: F401' >> %s" % (NQ, KEPT), True),
    (
        "sed -i adding one",
        "sed -i 's/return os.sep/return os.sep  %s: RET504/' %s" % (NQ, KEPT),
        True,
    ),
    # In place is sed's and perl's own option parse (review 3f53e99e.2 sweep): each refusal was allowed (rc 0) before.
    (
        "sed -Ei adding one",
        "sed -Ei 's/return os.sep/return os.sep  %s: RET504/' %s" % (NQ, KEPT),
        True,
    ),
    (
        "perl -pi -e adding one",
        "perl -pi -e 's/return os.sep/return os.sep  %s: RET504/' %s" % (NQ, KEPT),
        True,
    ),
    (
        "python heredoc writing one",
        "python3 - <<'EOF'\nimport pathlib\npathlib.Path('a.py').write_text('x  %s: B010')\nEOF"
        % NQ,
        True,
    ),
    ("tee into a TS file", "printf '// %s\\n' | tee src/a.ts" % TSI, True),
    # CONTROLS.
    (
        "cat heredoc re-writing the file with its marker unchanged",
        "cat > %s <<'EOF'\n%sEOF" % (KEPT, KEPT_TEXT),
        False,
    ),
    ("sed -i removing the marker", "sed -i 's/  %s: F401//' %s" % (NQ, KEPT), False),
    (
        "a commit message naming the marker",
        "git commit -F - <<'EOF'\nfix: drop the %s: B010 swaps\nEOF" % NQ,
        False,
    ),
    ("grep for markers", "grep -rn '%s' .ci" % NQ, False),
    ("echo to the terminal", "echo '%s: B010'" % NQ, False),
    # A program read from a FILE is read like one read from a heredoc (#f3f36655): each refusal was allowed (rc 0) before.
    ("a python script by path writing a marker", "python3 %s" % MARKER_SCRIPT, True),
    ("a python script by path after options", "python3 -u -B %s --flag" % MARKER_SCRIPT, True),
    ("a node script by path writing a marker", "node %s" % MARKER_JS, True),
    ("a python script by path writing none", "python3 %s" % CLEAN_SCRIPT, False),
    (
        "a tracked script whose own source carries markers",
        "python3 %s --list --open x" % TRACKED_SCRIPT,
        False,
    ),
    ("a script that does not exist yet fails open", "python3 %s" % ABSENT_SCRIPT, False),
    ("python -m names a module, not a file", "python3 -m %s" % MARKER_SCRIPT.stem, False),
    # Review b922f15c.1-.4: each refusal was allowed (rc 0) before.
    (
        "a script written and run in one command",
        "cat > %s/later <<'EOF'\n%sEOF\npython3 %s/later" % (SCRATCH, MARKER_PROGRAM, SCRATCH),
        True,
    ),
    (
        "a script copied in and run, the command naming a marker",
        "cp /tmp/nowhere.py %s/x_noq%s_tool.py && python3 %s/x_noq%s_tool.py"
        % (SCRATCH, "a", SCRATCH, "a"),
        True,
    ),
    (
        "a script copied in and run, the command naming nothing",
        "cp /tmp/nowhere.py %s/tool.py && python3 %s/tool.py" % (SCRATCH, SCRATCH),
        False,
    ),
    ("a tracked script edited after its commit", "python3 %s" % (TRACK_REPO / "edited.py"), True),
    (
        "a tracked script unchanged since its commit",
        "python3 %s" % (TRACK_REPO / "unchanged.py"),
        False,
    ),
    ("a script past the old 1 MiB cap is read whole", "python3 %s" % PADDED, True),
    ("a script past the read budget is unjudgeable", "python3 %s" % HUGE, True),
    # The interpreter's own options, parsed as it parses them (review 63ee61e3.1): each refusal was allowed (rc 0) before.
    ("python -E is a flag, not an inline program", "python3 -E %s" % MARKER_SCRIPT, True),
    ("python -I then the script", "python3 -I %s" % MARKER_SCRIPT, True),
    ("python -X takes its own value", "python3 -X dev %s" % MARKER_SCRIPT, True),
    ("a -c after the script is the script's argument", "python3 %s -c x" % MARKER_SCRIPT, True),
    ("node -r takes its own value", "node -r %s %s" % (CLEAN_SCRIPT, MARKER_JS), True),
    ("perl -E is perl's inline program", "perl -E 'print 1'", False),
]


def via_dispatch(stem, payload):
    proc = subprocess.run(
        [sys.executable, DISPATCH, stem],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


def _outside_defect(src):
    """`src` without its top-level `DEFECT` assignment, so the needle search cannot be satisfied by the declaration itself."""
    cut = [
        n
        for n in ast.parse(src).body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "DEFECT" for t in n.targets)
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
    # The mutant is LOADED FROM A FILE rather than exec'd from a string: the same module semantics, and nothing for a security lint to flag.
    mutant = SCRATCH / ("broken_%s.py" % stem)
    mutant.write_text(src.replace(old, new), encoding="utf-8")
    spec = importlib.util.spec_from_file_location("broken_" + stem, mutant)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load the planted copy of %s" % stem)
    broken = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(broken)
    ns: dict[str, typing.Any] = vars(broken)

    def run(_stem, payload):
        event = hookio.Event(json.dumps(payload))
        rc = ns["run"](event)
        _rc, out, err = event.result(rc)
        return rc, out + err

    return run


def run_cases(stem, cases, runner, quiet=False):
    fails = 0
    for name, payload, refused in cases:
        _world()
        rc, text = runner(stem, payload)
        blocked = rc != 0
        ok = blocked == refused and (not refused or "operator ruling 2026-10-08" in text)
        fails += not ok
        if not quiet:
            print(
                "%-58s want=%-8s %s"
                % (
                    name,
                    "BLOCKED" if refused else "allowed",
                    "ok" if ok else "*** FAIL *** " + text[:200],
                )
            )
    return fails


def main(stems=("block_suppressions",)):
    shell = [(n, {"tool_name": "Bash", "tool_input": {"command": c}}, r) for n, c, r in SHELL_CASES]
    suites = {"block_suppressions": EDIT_CASES, "block_suppressions_shell_write": shell}
    total = 0
    try:
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
            # The world must be what the cases assumed: a run that edited the scratch file for real would make later cases lie.
            if KEPT.read_text(encoding="utf-8") != KEPT_TEXT:
                print(
                    "*** FAIL *** a case modified %s; the guard ran a command it should only have judged"
                    % KEPT
                )
                total += 1
    finally:
        OUTSIDE.unlink(missing_ok=True)
        shutil.rmtree(str(SCRATCH), ignore_errors=True)
    print("FAILURES: %d" % total)
    return 1 if total else 0


if __name__ == "__main__":
    os.environ.pop("CLAUDE_PROJECT_DIR", None)
    sys.exit(main())
