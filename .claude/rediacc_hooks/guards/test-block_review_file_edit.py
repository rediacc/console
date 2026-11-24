#!/usr/bin/env python3
"""Control harness for block_review_file_edit and block_review_file_shell_write, the two halves of "a review record is never edited by hand".

This file runs the Edit half; `test-block_review_file_shell_write.py` beside it runs the shell half through the same code, so each guard has the dedicated `test-<stem>.py` check-hook-integrity credits. Both directions for each half, because a one-sided control is satisfiable by a broken hook: one that always refuses passes the refusal cases, one that never refuses passes the allowed ones. Then each guard's declared DEFECT is planted in-process and the run MUST fail, which is the proof the cases can.

    test-block_review_file_edit.py        run every Edit case through dispatch.py, then the DEFECT run
"""

import atexit
import pathlib
import shutil
import subprocess
import sys
import tempfile

import _hookpath

from rediacc_hooks.guards import _edit_suite
from rediacc_hooks.tests.fixtures.guards.loader import load_table

HERE = pathlib.Path(__file__).resolve()
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

# The rows that are data (CR5) are `(name, payload or command, refused?)` rows in tests/fixtures/guards/block_review_file_edit.json (EDIT_CASES) and block_review_file_shell_write.json (SHELL_CASES), read by that directory's one loader. The rows below them stay code: each names a path this file builds at import, a script, a link or a repository under `_SCRIPTS`.
EDIT_CASES = [
    *load_table("block_review_file_edit", "EDIT_CASES"),
    # Judged where the write LANDS (review 3f53e99e.1 sweep): each refusal was allowed (rc 0) before, and the control was refused.
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
]

SHELL_CASES = [
    *load_table("block_review_file_shell_write", "SHELL_CASES"),
    # Every way Python fills a template (review 6dcf79c7.1-.2): each refusal was allowed (rc 0) before.
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
]


# The runner is `_edit_suite`'s, shared by the four edit/shell twin suites (CR5); a refusal must name the verb that closes a finding.
STYLE = _edit_suite.Style(says="--review-mark", width=46)
via_dispatch = _edit_suite.via_dispatch
_outside_defect = _edit_suite.outside_defect


def run_cases(stem, cases, runner, quiet=False):
    return _edit_suite.run_cases(stem, cases, runner, STYLE, quiet)


def main(stems=("block_review_file_edit",)):
    shell = [(n, {"tool_name": "Bash", "tool_input": {"command": c}}, r) for n, c, r in SHELL_CASES]
    suites = {"block_review_file_edit": EDIT_CASES, "block_review_file_shell_write": shell}
    return _edit_suite.finish(sum(_edit_suite.judge(stem, suites[stem], STYLE) for stem in stems))


if __name__ == "__main__":
    sys.exit(main())
