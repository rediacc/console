"""Refuse an Edit, Write, MultiEdit or NotebookEdit that would leave a slash command or skill file disabling model invocation.

THE RULING (operator, 2026-10-09), verbatim: "no command or skill in this repo is user-only. Every slash command and skill must be invocable by the AI. This is enforced twice: a hook refuses the flag at write time, and a CI gate fails on it." This is the write-time half for the edit tools; `block_user_only_command_shell_write` is the same rule for Bash, and `check:ci-model-invocable-commands` is the CI half.

ONE PREDICATE. What counts as a command or skill file, and what counts as disabling model invocation (every spelling of the key, and an explicit `false` refused as well as a truthy value), is decided in `rediacc_hooks/model_invocation.py`, which the shell twin and the CI gate import too. Read that docstring for the definition and for why `false` is refused; this file only decides WHICH TEXT to judge.

IT JUDGES THE RESULTING DOCUMENT, NOT THE NEW TEXT (the `block_plan_without_depends` shape). A Write is judged on its content. An Edit or MultiEdit is APPLIED to the on-disk text (`old_string` -> `new_string`, honouring `replace_all`, edits in sequence) and the result is judged. So an Edit that REMOVES the key passes, an Edit that ADDS it is refused, and an unrelated Edit to a file that still carries it is refused too, because the file it leaves still disables model invocation. A NotebookEdit naming a command or skill path is judged on its `new_source`. An Edit the tool itself would reject (the file is missing, `old_string` is absent) has nothing to judge and passes.

SCOPE. `.md` under any `.claude/commands/` or `.claude/skills/` directory, nested `.claude` trees and a user-level `~/.claude` included: a command there is just as invocable from a session in this repo. Prose that only MENTIONS the key, in a body or in any other file, passes. `user-invocable:` in a skill's `SKILL.md` is a different key (the user's slash menu) and is not read.

THE EXCEPTION LIST, from the operator's amendment of 2026-10-09, verbatim:

    it seems that we need an exceptionlist. I forgot about handoff command. let's include it into the exception list for CI & hook(s)

`.ci/config/model-invocation-exceptions.json` is read through `model_invocation.exceptions_for`, the one loader the shell twin and the gate share, and `model_invocation.verdict` decides: a LISTED file may carry the key, and editing it is allowed while the key stays exactly as the list says. The list holds operator rulings only, never a BLOCKER entry, and this guard refuses ANY edit to the list itself: adding an exception is an operator decision, made with `!`. There is no token the AI can type to get past either refusal.

THIS GUARD HAS NO BASH TWIN (`OWN_SUITE = True`), so it is judged against `test-block_user_only_command.py` beside it and against its own DEFECT, never against a golden.
"""

import os
import pathlib

from rediacc_hooks import hookio, model_invocation

CHAIN = "pre-edit"
OWN_SUITE = True
ORDER = 15
# Read by check:ci-guard-mention-anchoring: this guard judges the RESULTING command file's frontmatter, so a sentence appended to a valid command file passes; only a frontmatter key line is refused.
ANCHORING = "structure: refuses a command or skill file whose resulting frontmatter declares disable-model-invocation, never a sentence naming it"

LIST_MESSAGE = (
    "BLOCKED: this %s edits the model-invocation exception list (%s).\n"
    "\n"
    "Every entry is an operator ruling that lets one command or skill stay user-only.\n"
    "The ruling: %s\n"
    "%s\n"
)

# The scope test is the whole guard: with it answering "out of scope", every command file may disable model invocation again.
DEFECT = ("if not model_invocation.in_scope(path.as_posix()):", "if True:")

MESSAGE = (
    "BLOCKED: this %s breaks the model-invocation rule for %s.\n"
    "\n"
    "%s\n"
    "\n"
    "The ruling: %s\n"
    "%s\n"
    "\n"
    "Delete the key line from the frontmatter instead (any value: `false` is refused too, because a\n"
    "present key is one word away from a user-only command). A file on the operator's exception list\n"
    "(.ci/config/model-invocation-exceptions.json) keeps the key exactly as listed.\n"
)

_C = ".claude/commands/x.md"
_FM = "---\ndescription: x\n%s---\n\nBody.\n"

EDGE_CASES = [
    (
        "a Write adding the key",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/r/" + _C,
                "content": _FM % "disable-model-invocation: true\n",
            },
        },
    ),
    (
        "a Write with an explicit false",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/r/.claude/skills/s/SKILL.md",
                "content": _FM % "disable-model-invocation: false\n",
            },
        },
    ),
    (
        "a Write with another spelling",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/r/" + _C,
                "content": _FM % "Disable_Model_Invocation : 'Yes'\n",
            },
        },
    ),
    (
        "a nested command tree",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/r/private/account/.claude/commands/t.md",
                "content": _FM % "disableModelInvocation: on\n",
            },
        },
    ),
    (
        "a NotebookEdit naming a command path",
        {
            "tool_name": "NotebookEdit",
            "tool_input": {
                "notebook_path": "/r/" + _C,
                "new_source": _FM % "disable-model-invocation: 1\n",
            },
        },
    ),
    (
        "a Write whose body only mentions the key",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/r/" + _C,
                "content": _FM % "" + "Never set `disable-model-invocation: true`.\n",
            },
        },
    ),
    (
        "a Write outside the command directories",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/r/docs/x.md",
                "content": _FM % "disable-model-invocation: true\n",
            },
        },
    ),
    (
        "a Write to a sub-agent definition",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/r/.claude/agents/x.md",
                "content": _FM % "disable-model-invocation: true\n",
            },
        },
    ),
    (
        "a commented-out key",
        {
            "tool_name": "Write",
            "tool_input": {
                "file_path": "/r/" + _C,
                "content": _FM % "# disable-model-invocation: true\n",
            },
        },
    ),
    (
        "an Edit of the exception list",
        {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "/r/.ci/config/model-invocation-exceptions.json",
                "old_string": "[",
                "new_string": "[{}",
            },
        },
    ),
    ("no path", {"tool_name": "Write", "tool_input": {"content": "x"}}),
]


def _result_text(doc, path):
    """The text the tool call would leave at `path`, or None when the call fails on its own and there is nothing to judge."""
    tin = doc.get("tool_input") or {}
    if not isinstance(tin, dict):
        return None
    if doc.get("tool_name") == "NotebookEdit":
        return str(tin.get("new_source") or "")
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


def run(ev):
    doc = ev.doc
    if not isinstance(doc, dict):
        return hookio.ALLOW
    file_path = ev.first(("tool_input", "file_path"), ("tool_input", "notebook_path"))
    if not file_path or file_path == "null":
        return hookio.ALLOW
    path = pathlib.Path(file_path)
    if not path.is_absolute():
        try:
            base = pathlib.Path(ev.default(("cwd",), str(hookio.repo_root())))
        except RuntimeError:
            base = pathlib.Path(ev.cwd)
        path = base / path
    # Judged where the write LANDS (review 3f53e99e.1): `.claude/x/../commands/new.md` and a directory symlink into `.claude/commands` were out of scope as typed and allowed, while `.claude/commands/../x/new.md` was in scope and refused. `realpath` resolves `.`, `..` and every symlink in the part of the path that exists.
    path = pathlib.Path(os.path.realpath(path))
    if model_invocation.is_exception_list(path.as_posix()):
        ev.warn_raw(
            LIST_MESSAGE
            % (
                ev.field("tool_name") or "write",
                file_path,
                model_invocation.RULING,
                model_invocation.OPERATOR_LINE,
            )
        )
        return hookio.DENY
    if not model_invocation.in_scope(path.as_posix()):
        return hookio.ALLOW
    text = _result_text(doc, path)
    if text is None:
        return hookio.ALLOW
    rel, exceptions = model_invocation.exceptions_for(path)
    found = model_invocation.verdict(rel, text, exceptions)
    if not found:
        return hookio.ALLOW
    ev.warn_raw(
        MESSAGE
        % (
            ev.field("tool_name") or "write",
            file_path,
            "\n".join("  " + f for f in found),
            model_invocation.RULING,
            model_invocation.OPERATOR_LINE,
        )
    )
    return hookio.DENY
