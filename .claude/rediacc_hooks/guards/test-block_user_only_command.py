#!/usr/bin/env python3
"""Control harness for block_user_only_command and block_user_only_command_shell_write, the two write-time halves of "no command or skill is user-only" (operator ruling 2026-10-09).

This file runs the Edit half; `test-block_user_only_command_shell_write.py` beside it runs the shell half through the same code, so each guard has the dedicated `test-<stem>.py` check-hook-integrity credits. Both directions for each half, because a one-sided control is satisfiable by a broken hook: one that always refuses passes the refusal cases, one that never refuses passes the allowed ones. Then each guard's declared DEFECT is planted in-process and the run MUST fail, which is the proof the cases can.

The Edit, MultiEdit and copy cases need a file on disk, so every case runs against a scratch tree (`world()`) holding a clean command, a command that still carries the key, and copy sources with and without it; the payload's `cwd` points there.

    test-block_user_only_command.py        run every Edit case through dispatch.py, then the DEFECT run
"""

import json
import pathlib
import subprocess
import sys
import tempfile

import _hookpath

from rediacc_hooks.guards import _edit_suite
from rediacc_hooks.tests.fixtures.guards.loader import load_table

HERE = pathlib.Path(__file__).resolve()
NEEDLE = "a user-only command is an operator decision: the operator edits it with !"

K = "disable-model-invocation"
CLEAN = "---\ndescription: a command\nallowed-tools: Bash(ls:*)\n---\n\nBody.\n"
FLAGGED = "---\ndescription: a command\n%s: true\n---\n\nBody.\n" % K
C = ".claude/commands/clean.md"
F = ".claude/commands/flagged.md"
S = ".claude/skills/s/SKILL.md"
# The scratch tree's own exception list: one LISTED command keeps the key as `true`.
LISTED = ".claude/commands/listed.md"
LIST = ".ci/config/model-invocation-exceptions.json"
LIST_TEXT = json.dumps(
    {
        "exceptions": [
            {
                "path": LISTED,
                "value": "true",
                "ruling": {
                    "date": "2026-10-09",
                    "quote": "a scratch ruling, quoted verbatim for the harness",
                },
            }
        ]
    }
)


def world(root: pathlib.Path) -> None:
    """The scratch tree every case runs in."""
    for rel, text in (
        (C, CLEAN),
        (F, FLAGGED),
        (S, CLEAN),
        ("src/flagged.md", FLAGGED),
        ("src/clean.md", CLEAN),
        ("srcdir/a.md", FLAGGED),
        (LISTED, FLAGGED),
        (LIST, LIST_TEXT),
        # Scripts run BY PATH (#c4542b69); the scratch tree is no git checkout, so none is tracked.
        (
            "tools/key_writer.py",
            "import pathlib\npathlib.Path(%r).write_text('---\\n%s: true\\n---\\n')\n" % (C, K),
        ),
        ("tools/list_writer.py", "open(%r, 'w').write('{}')\n" % LIST),
        ("tools/reader.py", "print(open(%r).read())\n" % LIST),
    ):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    # Review b922f15c.3-.4, built once: a git repo whose committed scripts write the key (one edited after the commit), a script past the old 1 MiB cap, and one past the read budget.
    key_writer = (root / "tools" / "key_writer.py").read_text(encoding="utf-8")
    repo = root / "repo"
    if not (repo / ".git").is_dir():
        repo.mkdir(exist_ok=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        # No detached maintenance after a commit (the world is removed at exit): maintenance.auto=false and gc.auto=0: the detached `git maintenance` child holds .git/objects/maintenance.lock past `commit` and races the fixture's removal (see .claude/rediacc_hooks/tests/test_wl_scratch.py).
        for key, val in (("maintenance.auto", "false"), ("gc.auto", "0")):
            subprocess.run(["git", "-C", str(repo), "config", key, val], check=True)
        (repo / "unchanged.py").write_text(key_writer, encoding="utf-8")
        (repo / "edited.py").write_text("print('reviewed')\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "-c",
                "user.name=t",
                "-c",
                "user.email=t@t",
                "commit",
                "-qm",
                "x",
            ],
            check=True,
        )
        (repo / "edited.py").write_text(key_writer, encoding="utf-8")
    padded = root / "tools" / "padded.py"
    if not padded.is_file():
        padded.write_text("#" * (2 << 20) + "\n" + key_writer, encoding="utf-8")
    huge = root / "tools" / "huge-commands.py"
    if not huge.is_file():
        huge.write_text("#" * (17 << 20) + "\n", encoding="utf-8")
    # A directory symlink inside the tree that lands in the command directory (review 3f53e99e.1).
    (root / ".claude" / "x").mkdir(parents=True, exist_ok=True)
    link = root / "cmdlink"
    if not link.is_symlink():
        link.symlink_to(root / ".claude" / "commands", target_is_directory=True)
    # A link then `..` (review 9c6817f3.1-.4 sweep): the kernel follows the link first. `out/l` points INTO the guarded directory, `esc` points OUT of it.
    (root / ".claude" / "commands" / "sub").mkdir(exist_ok=True)
    (root / "out").mkdir(exist_ok=True)
    if not (root / "out" / "l").is_symlink():
        (root / "out" / "l").symlink_to(
            root / ".claude" / "commands" / "sub", target_is_directory=True
        )
        (root / ".claude" / "commands" / "esc").symlink_to(root / "out", target_is_directory=True)


# The cases are data (CR5): `(name, payload or command, refused?)` rows in tests/fixtures/guards/block_user_only_command.json (EDIT_CASES) and block_user_only_command_shell_write.json (SHELL_CASES), read by that directory's one loader. None names the scratch tree, which `_style` hands each payload as its cwd, so every row moved; this file keeps the world they run in.
EDIT_CASES = load_table("block_user_only_command", "EDIT_CASES")
SHELL_CASES = load_table("block_user_only_command_shell_write", "SHELL_CASES")


# The runner is `_edit_suite`'s, shared by the four edit/shell twin suites (CR5). Every case runs in a fresh `world(root)`, with the payload's cwd there.
via_dispatch = _edit_suite.via_dispatch
_outside_defect = _edit_suite.outside_defect


def _style(root):
    def prepare(raw):
        world(root)
        return dict(raw, cwd=str(root))

    return _edit_suite.Style(says=NEEDLE, width=50, shown=200, prepare=prepare)


def run_cases(stem, cases, runner, root, quiet=False):
    return _edit_suite.run_cases(stem, cases, runner, _style(root), quiet)


def main(stems=("block_user_only_command",)):
    shell = [(n, {"tool_name": "Bash", "tool_input": {"command": c}}, r) for n, c, r in SHELL_CASES]
    suites = {"block_user_only_command": EDIT_CASES, "block_user_only_command_shell_write": shell}
    with tempfile.TemporaryDirectory(prefix="uo-guard-") as tmp:
        style = _style(pathlib.Path(tmp) / "world")
        total = sum(_edit_suite.judge(stem, suites[stem], style) for stem in stems)
    return _edit_suite.finish(total)


if __name__ == "__main__":
    sys.exit(main())
