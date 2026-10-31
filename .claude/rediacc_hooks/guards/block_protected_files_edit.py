"""Refuse an Edit, Write or MultiEdit that empties or restores a protected hook file, and any NotebookEdit of one: the edit-tool half of `block_protected_files`.

WHY (worklist #6378e10e). `block_protected_files` refuses `rm`, `git restore` and `git checkout` of `.claude/settings.json` and `scripts/pre-commit-check.sh`, and it is a pre-bash guard, so the edit tools reached the same two outcomes unrefused: a Write of an empty `.claude/settings.json` unwires every hook as surely as an `rm` (rc 0 through the pre-edit chain at c72518af1), and a Write of the file's HEAD text
discards every uncommitted change to it, which is what `git restore` does and why it is refused.

THE SAME ACTS, NOT EVERY EDIT. The shell half refuses deleting and restoring, never changing: `sed -i` on `.claude/settings.json` passes it, and so does a hook-wiring Edit here. Hook wiring is ordinary work (18 commits touched `.claude/settings.json` between 2026-09-01 and 2026-10-14), and the operator chose a warning over a refusal for hook changes on 2026-08-25 (`warn_hook_change`). So the result of the call is judged, the way `block_user_only_command` judges it:
  - EMPTIED. A Write, Edit or MultiEdit that leaves the file blank (whitespace only) is the edit-tool `rm`.
  - RESTORED. One that leaves the file byte-equal to its HEAD blob while the working copy differs from HEAD is the edit-tool `git restore`. A file already at HEAD is left alone, so rewriting it unchanged passes.
  - A NotebookEdit naming either path can only replace it with a notebook cell, so it is refused outright.
An Edit the tool itself would reject (the file is missing, `old_string` is absent) changes nothing and passes. The protected set is `block_protected_files.PROTECTED_PATHS`, matched by the path the write LANDS on (`hookio.landing`) the way that guard's walked runs match it: the file at the end of the path, in this checkout or any other.

THIS GUARD HAS NO BASH TWIN (`OWN_SUITE = True`), so it is judged against `test-block_protected_files_edit.py` beside it and against its own DEFECT, never against a golden.
"""

import pathlib
import subprocess

from rediacc_hooks import hookio
from rediacc_hooks.guards import block_protected_files as PF

CHAIN = "pre-edit"
OWN_SUITE = True
ORDER = 16

# The path test is the whole guard: with it gone no protected file is recognised, so an empty Write over `.claude/settings.json` passes.
DEFECT = ("if not PF._is_protected(absolute):", "if True:")

MESSAGE = (
    "BLOCKED: this %s would %s %s, a protected hook file.\n"
    "\n"
    "Emptying `.claude/settings.json` unwires every hook, and writing back its HEAD text discards\n"
    "every uncommitted change to it, including other sessions' wiring. The shell half,\n"
    "block_protected_files, refuses the same acts as `rm` and `git restore`. An edit that changes\n"
    "the file is allowed; to undo a change, edit the value back. If the file genuinely has to be\n"
    "emptied or restored, hand the exact command to the operator to run with the `!` prefix.\n"
)

# The cases that need no world on disk; the restore cases need a checkout and live in the harness.
EDGE_CASES = [
    (
        "a Write emptying the settings file",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "/r/.claude/settings.json", "content": ""},
        },
    ),
    (
        "a Write blanking the pre-commit script",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "/r/scripts/pre-commit-check.sh", "content": "\n \n"},
        },
    ),
    (
        "a NotebookEdit naming the settings file",
        {
            "tool_name": "NotebookEdit",
            "tool_input": {"notebook_path": "/r/.claude/settings.json", "new_source": "x"},
        },
    ),
    (
        "a Write of new settings text",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "/r/.claude/settings.json", "content": '{"hooks": {}}\n'},
        },
    ),
    (
        "a Write emptying an ordinary file",
        {"tool_name": "Write", "tool_input": {"file_path": "/r/docs/x.md", "content": ""}},
    ),
    (
        "a Write emptying the local settings file",
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "/r/.claude/settings.local.json", "content": ""},
        },
    ),
    ("no path", {"tool_name": "Write", "tool_input": {"content": ""}}),
]


def _result_text(doc, path):
    """The text the call leaves at `path`, or None when the tool itself would fail and nothing changes (the `block_user_only_command` reading)."""
    tin = doc.get("tool_input") or {}
    if not isinstance(tin, dict):
        return None
    if "content" in tin:
        return str(tin.get("content") or "")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    edits = tin.get("edits")
    if not isinstance(edits, list):
        edits = [tin]
    for edit in edits:
        if not isinstance(edit, dict):
            return None
        old = str(edit.get("old_string") or "")
        new = str(edit.get("new_string") or "")
        if not old or old not in text:
            return None
        text = text.replace(old, new) if edit.get("replace_all") else text.replace(old, new, 1)
    return text


def _head_text(path):
    """The file's text at HEAD of the checkout holding it, or None (no checkout, untracked, unreadable)."""
    try:
        done = subprocess.run(
            ["git", "-C", str(path.parent), "show", "HEAD:./%s" % path.name],
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    return done.stdout.decode("utf-8", "replace")


def _current_text(path):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def run(ev):
    doc = ev.doc
    if not isinstance(doc, dict):
        return hookio.ALLOW
    given = ev.first(("tool_input", "file_path"), ("tool_input", "notebook_path"))
    if not given or given == "null":
        return hookio.ALLOW
    absolute, _judged, shown = hookio.landing(given, ev.field("cwd") or None)
    if not PF._is_protected(absolute):
        return hookio.ALLOW
    tool = ev.field("tool_name") or "edit"
    if tool == "NotebookEdit":
        ev.warn_raw(MESSAGE % (tool, "replace", shown))
        return hookio.DENY
    path = pathlib.Path(absolute)
    after = _result_text(doc, path)
    if after is None:
        return hookio.ALLOW
    if not after.strip():
        # A write that leaves a file blank which is already blank changes nothing, like the restore check's already-at-HEAD exemption (review 7359200f.1).
        current = _current_text(path)
        if current is not None and not current.strip():
            return hookio.ALLOW
        ev.warn_raw(MESSAGE % (tool, "empty", shown))
        return hookio.DENY
    head = _head_text(path)
    if head is not None and after == head and _current_text(path) != head:
        ev.warn_raw(MESSAGE % (tool, "restore to HEAD", shown))
        return hookio.DENY
    return hookio.ALLOW
