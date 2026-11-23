#!/usr/bin/env python3
"""Control harness for block_protected_files_edit, the edit-tool half of block_protected_files.

Both directions, because a one-sided control is satisfiable by a broken hook: one that always refuses passes the refusal cases, one that never refuses passes the allowed ones. The world is two throwaway git checkouts holding both protected files, one with `.claude/settings.json` edited after its commit (so a write of its HEAD text is a restore) and one clean (so the same write changes nothing). Then the guard's declared DEFECT is planted in-process and the run MUST fail, which is the proof the cases can.

    test-block_protected_files_edit.py
"""

import atexit
import importlib
import importlib.util
import pathlib
import shutil
import subprocess
import sys
import tempfile

import _hookpath

from rediacc_hooks.guards import _edit_suite
from rediacc_hooks.tests.fixtures.guards.loader import load_table

HERE = pathlib.Path(__file__).resolve()
# The canonical sys.path hop, through rediacc_hooks/syspath.py loaded by file (the pattern test-block_review_file_edit.py uses).
_SYSPATH = importlib.util.spec_from_file_location(
    "rediacc_hooks_syspath", HERE.parent.parent / "syspath.py"
)
if _SYSPATH is None or _SYSPATH.loader is None:
    raise SystemExit("%s: rediacc_hooks/syspath.py is missing" % __file__)
_syspath = importlib.util.module_from_spec(_SYSPATH)
_SYSPATH.loader.exec_module(_syspath)
STEM = "block_protected_files_edit"
NEEDLE = "protected hook file"

SETTINGS = ".claude/settings.json"
PRE_COMMIT = "scripts/pre-commit-check.sh"
HEAD_SETTINGS = '{\n  "hooks": {"Stop": []}\n}\n'
EDITED_SETTINGS = '{\n  "hooks": {"Stop": [], "PreToolUse": []}\n}\n'
HEAD_SCRIPT = "#!/usr/bin/env bash\nexit 0\n"

_WORLD = pathlib.Path(tempfile.mkdtemp(prefix="test-protected-files-edit-"))
atexit.register(shutil.rmtree, str(_WORLD), True)


def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
    )


def _checkout(name, edited):
    repo = _WORLD / name
    (repo / ".claude").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "docs").mkdir()
    (repo / SETTINGS).write_text(HEAD_SETTINGS, encoding="utf-8")
    (repo / PRE_COMMIT).write_text(HEAD_SCRIPT, encoding="utf-8")
    (repo / "docs" / "x.md").write_text("notes\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "seed")
    if edited:
        (repo / SETTINGS).write_text(EDITED_SETTINGS, encoding="utf-8")
    return repo


DIRTY = _checkout("dirty", edited=True)
CLEAN = _checkout("clean", edited=False)
BLANK = _checkout("blank", edited=False)
(BLANK / SETTINGS).write_text("", encoding="utf-8")


def _write(path, content, cwd=None):
    payload: dict = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(path), "content": content},
    }
    if cwd is not None:
        payload["cwd"] = str(cwd)
    return payload


def _edit(path, old, new, replace_all=False):
    return {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(path),
            "old_string": old,
            "new_string": new,
            "replace_all": replace_all,
        },
    }


# One case is data (CR5), the payload with no path, a row in tests/fixtures/guards/block_protected_files_edit.json read by that directory's one loader. Every other case names a file in the scratch checkouts above and stays code.
CASES = [
    # (name, payload, refused?)
    *load_table("block_protected_files_edit", "CASES"),
    ("Write of an empty settings file", _write(DIRTY / SETTINGS, ""), True),
    ("Write of a blank pre-commit script", _write(CLEAN / PRE_COMMIT, " \n\n"), True),
    (
        "Write of the settings file's HEAD text over an edit",
        _write(DIRTY / SETTINGS, HEAD_SETTINGS),
        True,
    ),
    (
        "Edit reverting the uncommitted change",
        _edit(DIRTY / SETTINGS, ', "PreToolUse": []', ""),
        True,
    ),
    (
        "MultiEdit that leaves the settings file blank",
        {
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": str(DIRTY / SETTINGS),
                "edits": [{"old_string": EDITED_SETTINGS, "new_string": "\n"}],
            },
        },
        True,
    ),
    (
        "NotebookEdit naming the settings file",
        {
            "tool_name": "NotebookEdit",
            "tool_input": {"notebook_path": str(DIRTY / SETTINGS), "new_source": "x"},
        },
        True,
    ),
    ("a relative path judged from the call's cwd", _write(SETTINGS, "", cwd=DIRTY), True),
    (
        "a path through .. that lands on the file",
        _write(DIRTY / "docs" / ".." / SETTINGS, ""),
        True,
    ),
    # --- allowed: the file changes, or the write is not to a protected file ---
    (
        "Edit adding a hook to the settings file",
        _edit(DIRTY / SETTINGS, '"Stop": []', '"Stop": [], "Notification": []'),
        False,
    ),
    (
        "Write of HEAD text over a file already at HEAD",
        _write(CLEAN / SETTINGS, HEAD_SETTINGS),
        False,
    ),
    (
        "Write of a new pre-commit script",
        _write(CLEAN / PRE_COMMIT, HEAD_SCRIPT + "echo ok\n"),
        False,
    ),
    ("Write of an empty ordinary file", _write(DIRTY / "docs" / "x.md", ""), False),
    # Review 7359200f.1: blank over a file that is already blank changes nothing.
    ("Write of an empty settings file already blank", _write(BLANK / SETTINGS, ""), False),
    (
        "Write of an empty local settings file",
        _write(DIRTY / ".claude" / "settings.local.json", ""),
        False,
    ),
    ("Edit whose old_string is absent", _edit(DIRTY / SETTINGS, "no such text", ""), False),
    (
        "NotebookEdit of an ordinary notebook",
        {
            "tool_name": "NotebookEdit",
            "tool_input": {"notebook_path": str(DIRTY / "docs" / "n.ipynb"), "new_source": "x"},
        },
        False,
    ),
]


# The runner is `_edit_suite`'s, shared by the four edit/shell twin suites (CR5); this suite judges one guard and prints no header.
STYLE = _edit_suite.Style(says=NEEDLE, width=52)


def main():
    return _edit_suite.finish(_edit_suite.judge(STEM, CASES, STYLE, header=False))


if __name__ == "__main__":
    sys.exit(main())
