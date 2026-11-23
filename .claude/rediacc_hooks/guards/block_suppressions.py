"""Refuse an Edit, Write, MultiEdit or NotebookEdit that ADDS an inline lint or type suppression marker.

THE RULE, operator ruling 2026-10-08: "statements like '# noq[a]: B010' should be banned: a) with hooks to avoid future edits/inserts b) with CI, fix the existing ones." This is (a) for the edit tools; `block_suppressions_shell_write.py` is (a) for the shell, and `.ci/scripts/quality/check_inline_suppressions.py` is (b). All three call ONE scanner, `rediacc_ci.quality.inline_suppressions.count_markers`, so the keystroke and CI cannot drift apart.

NOTE: every banned token in THIS file is written with a trailing character class (`eslint-disabl[e]`, `noq[a]`) or assembled from halves, so the file never holds the literal token. That convention is not decoration: drafting a comment without it once got the repair of this guard refused by this guard.

WHAT CHANGED ON 2026-10-08, AND WHY "ANY MARKER IN THE NEW TEXT" WAS RETIRED. The guard used to refuse any TS/JS directive appearing anywhere in the new content. Widened to Python, Go, shell and Dockerfiles, that rule would refuse every unrelated edit to the ~640 files that already carry a marker, because a Write carries the whole file and an Edit's `new_string` routinely repeats a line it did not change. A ban that blocks the cleanup of the very files it is about gets deleted within a week. So the
question is now the gate's own: does the COUNT of (marker kind, code) in this file go UP? Keeping an existing marker passes, removing one passes, moving one passes, and only an addition is refused. The DEFECT below plants the retired rule, and the "keeping an existing marker" cases are what catch it.

HOW THE BEFORE AND AFTER ARE BUILT. A Write is compared with the file on disk (nothing, for a new file). An Edit or MultiEdit is applied to the file on disk in memory, and the whole file is compared before and after, which is what lets Python be read by `tokenize`: a marker named inside a DOCSTRING or a string literal is not a marker, and only a whole file tokenizes reliably. When the file is not on disk or an `old_string` is not found in it, the two fragments are compared instead. A NotebookEdit compares the cell it replaces.

TWO NARROWINGS, both paid for, both kept, now enforced by the shared scanner:

  1. CODE FILES ONLY. A marker in Markdown is an example, and an example is how the rule gets taught (measured 2026-08-27: the original refused `docs/style.md` writing the rule down).
  2. DIRECTIVE POSITION. In JS/TS a directive sits immediately after a comment opener; prose puts words in between. In Python the position is a COMMENT token. That is a property of the syntax, not a keyword list.

WHAT IT STILL OVER-COUNTS, said so the refusal is not a surprise: a JS/TS or Go STRING literal holding a directive at a comment opener (`'// @ts-ignor[e]'`). There is no JS tokenizer here, so a test fixture that needs one assembles it from halves, as this file does. The CI gate counts the same way, so the two agree.

IT FAILS OPEN, LOUDLY. If the scanner cannot be imported, the edit is allowed and stderr says it went UNEXAMINED; the CI gate is the backstop. `block_prose_style_edit.py` argues the same case.
"""

import importlib
import json
import os
import pathlib
import sys

from rediacc_hooks import hookio, syspath
from rediacc_hooks.guards import _cases

__getattr__ = _cases.lazy(
    "block_suppressions",
    "EDGE_CASES",
    "_ESLINT_DISABLE",
    "_NOLINT",
    "_NOQA",
    "_SHELLCHECK",
    "_TS_IGNORE",
    "_TYPE_IGNORE",
)

CHAIN = "pre-edit"
ORDER = 4

# The rule this guard retired on 2026-10-08: compare the new content against NOTHING, i.e. refuse any marker the new text carries. Planting it flips every "keeping an existing marker" case to a refusal.
DEFECT = (
    "grew = engine.growth(old_counts, new_counts)",
    "grew = engine.growth(type(new_counts)(), new_counts)",
)

UNEXAMINED = (
    "block-suppressions: the inline-suppression scanner could not be loaded (%s); this edit "
    "passed UNEXAMINED. CI (check:ci-inline-suppressions) still judges it."
)


HEADER = """BLOCKED: this edit ADDS an inline lint/type suppression marker. Inline suppressions are
banned (operator ruling 2026-10-08).

"""

FOOTER = """
Instead:
  * Fix the code the linter is pointing at. That is almost always the answer.
  * For a deliberate, project-wide exception, add a per-file entry to the linter's
    own config (pyproject.toml [tool.ruff.lint.per-file-ignores], biome.json
    overrides, .golangci.yml exclusions) carrying a BLOCKER: reason, per
    docs/agent-reference/suppressions.md.

Keeping, moving or removing an EXISTING marker is allowed; only a new one is refused.
A test fixture that must hold the token in a JS/TS or Go string assembles it from
halves ('@ts-ignor' + 'e'), the convention this guard's own source uses.
CI enforces the same rule: .ci/scripts/quality/check_inline_suppressions.py
"""


def _engine(root):
    """Import the shared scanner, restoring `sys.path` on the way out (the dispatcher runs every guard of the chain in one process; see block_prose_style_edit._engine)."""
    cipath = str(pathlib.Path(root) / ".ci")
    inserted = syspath.on_sys_path(cipath)
    try:
        module = importlib.import_module("rediacc_ci.quality.inline_suppressions")
    finally:
        if inserted and cipath in sys.path:
            sys.path.remove(cipath)
    return module


def _resolve(root, file_path, cwd):
    """The absolute path of an edit inside the repository, "" for no path, or None when the edit is outside the tree (a scratch file is not this repository's code)."""
    if not file_path:
        return ""
    path = file_path if os.path.isabs(file_path) else os.path.join(cwd or str(root), file_path)
    # Where the edit LANDS (review 3f53e99e.1 sweep): a directory link outside the tree that points into it was judged outside and allowed. `hookio.landing` is the one reading every pre-edit guard shares (9c6817f3.8). The path as typed still counts when it holds no `..`, so a link inside the tree pointing out of it is judged as before; with a `..` the typed text is not where the kernel writes (`esc/../f` behind a link lands outside), so only the landing counts. The landing is preferred, since its name decides the language.
    candidates = [hookio.landing(file_path, cwd or str(root), str(root))[0]]
    if ".." not in path.split("/"):
        candidates.append(os.path.normpath(path))
    for candidate in candidates:
        try:
            rel = os.path.relpath(candidate, str(root))
        except ValueError:
            continue
        if not rel.startswith(".."):
            return candidate
    return None


def _read(path):
    if not path:
        return None
    try:
        with open(path, encoding="utf-8", errors="surrogateescape") as handle:
            return handle.read()
    except OSError:
        return None


def _apply(text, edits):
    """`text` with each (old, new, all) applied in order, or None when an `old` is not in it."""
    for old, new, every in edits:
        if not old or old not in text:
            return None
        text = text.replace(old, new) if every else text.replace(old, new, 1)
    return text


def _notebook_cell(text, cell_id):
    try:
        cells = json.loads(text).get("cells", [])
    except (ValueError, AttributeError):
        return ""
    for cell in cells:
        if isinstance(cell, dict) and cell.get("id") == cell_id:
            source = cell.get("source", "")
            return "".join(source) if isinstance(source, list) else str(source)
    return ""


def _before_after(tool, path):
    """(old, new) texts to compare, from the payload's tool_input and the file on disk."""
    disk = _read(path)
    if "new_source" in tool:
        old = (
            _notebook_cell(disk or "", tool.get("cell_id"))
            if tool.get("edit_mode", "replace") == "replace"
            else ""
        )
        new = "" if tool.get("edit_mode") == "delete" else str(tool.get("new_source") or "")
        return old, new
    if "content" in tool:
        return disk or "", str(tool.get("content") or "")
    raw_edits = tool.get("edits") if isinstance(tool.get("edits"), list) else [tool]
    edits = [
        (str(e.get("old_string") or ""), str(e.get("new_string") or ""), bool(e.get("replace_all")))
        for e in raw_edits
        if isinstance(e, dict)
    ]
    if disk is not None:
        applied = _apply(disk, edits)
        if applied is not None:
            return disk, applied
    return "\n".join(e[0] for e in edits), "\n".join(e[1] for e in edits)


def run(ev):
    doc = ev.doc
    tool = doc.get("tool_input") if isinstance(doc, dict) else None
    if not isinstance(tool, dict):
        return hookio.ALLOW
    try:
        root = hookio.repo_root()
        engine = _engine(root)
    except (ImportError, OSError, RuntimeError, SyntaxError) as exc:
        ev.warn(UNEXAMINED % exc)
        return hookio.ALLOW

    file_path = ev.first(("tool_input", "file_path"), ("tool_input", "notebook_path"))
    path = _resolve(root, file_path, ev.default(("cwd",), str(root)))
    if path is None:
        return hookio.ALLOW
    old, new = _before_after(tool, path)
    if not new.strip():
        return hookio.ALLOW

    if file_path:
        # The language of the file the edit lands in: a `.txt` link to a Python file is Python.
        if path.endswith(".ipynb"):
            language = "py"
        else:
            head = (new if "content" in tool else (_read(path) or new)).split("\n", 1)[0]
            language = engine.language_for(path, head)
        if language is None:
            return hookio.ALLOW
        old_counts = engine.count_markers(old, language)
        new_counts = engine.count_markers(new, language)
    else:
        old_counts = engine.count_any_language(old)
        new_counts = engine.count_any_language(new)

    grew = engine.growth(old_counts, new_counts)
    if not grew:
        return hookio.ALLOW
    lines = [HEADER, "%s\n" % (file_path or "(no file path in the payload)")]
    for kind, code, before, after in grew:
        lines.append(
            "  %s  (%d -> %d in this file)\n" % (engine.render_marker(kind, code), before, after)
        )
    lines.append(FOOTER)
    ev.warn_raw("".join(lines))
    return hookio.DENY
