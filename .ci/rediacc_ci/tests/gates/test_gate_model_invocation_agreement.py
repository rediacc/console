"""The hook and the gate agree on what "a user-only command" is, over one set of planted fixtures.

THE RULING (operator, 2026-10-09): "no command or skill in this repo is user-only. Every slash command and skill must be invocable by the AI. This is enforced twice: a hook refuses the flag at write time, and a CI gate fails on it." Enforced twice means two implementations that can drift, so this file holds them together, amended the same day with one exception list read by both.

ONE PREDICATE, PROVEN SHARED, THEN PROVEN EQUAL. `test_one_predicate_and_one_loader` asserts the pre-edit guard, the pre-bash twin and the gate hold the SAME `rediacc_hooks.model_invocation` module object, so there is one definition of the key, one scope test, one list loader and one `verdict`. That alone does not prove the WIRING agrees (which text each side judges, how each finds the list), so `test_edit_guard_and_gate_agree` drives the real
guard through `dispatch.py` and the real gate through `check_tree` on the same fixture tree, case by case, and fails on any disagreement. Each case is planted in its own git repository holding a clean command, a clean skill, the exception list, and the one file the list admits (`.claude/commands/listed.md`, `disable-model-invocation: true`), so a LISTED file and an UNLISTED one are judged side by side.

THE SHELL TWIN IS HELD TO SOUNDNESS, NOT EQUALITY. `block_user_only_command_shell_write` reads command text, not a resulting file, and over-refuses by design (its docstring: a static read cannot tell a removal from an insertion). So `test_shell_twin_never_allows_what_the_gate_refuses` requires that the twin refuses every overwrite the gate would fail, and that the cases where it refuses MORE are exactly the documented `SHELL_OVER_REFUSES`; a new divergence in either direction is red.

THE COMPARISON CAN FAIL. `test_the_comparison_fires_on_a_planted_divergence` hands the comparison a hook stand-in that ignores the exception list (the plausible regression: a guard that judges `findings` instead of `verdict`) and requires it to report the listed-file case as a disagreement.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from typing import TYPE_CHECKING

from rediacc_ci import paths
from rediacc_ci.quality import model_invocable_commands as gate

if TYPE_CHECKING:
    import pathlib

DISPATCH = paths.from_root(".claude", "rediacc_hooks", "dispatch.py")
K = "disable-model-invocation"
CLEAN = "---\ndescription: a command\n---\n\nBody.\n"
FLAG = "---\ndescription: a command\n%s: %%s\n---\n\nBody.\n" % K
LISTED = ".claude/commands/listed.md"
LIST_TEXT = json.dumps(
    {
        "exceptions": [
            {
                "path": LISTED,
                "value": "true",
                "ruling": {
                    "date": "2026-10-09",
                    "quote": "a fixture ruling, quoted verbatim for this test",
                },
            }
        ]
    }
)
BASE = {
    ".claude/commands/clean.md": CLEAN,
    ".claude/skills/s/SKILL.md": CLEAN,
    LISTED: FLAG % "true",
    ".ci/config/model-invocation-exceptions.json": LIST_TEXT,
}

# (name, path planted, content) -- each planted over BASE in a repository of its own.
CASES = [
    ("unlisted truthy key", ".claude/commands/new.md", FLAG % "true"),
    ("unlisted explicit false", ".claude/commands/new.md", FLAG % "false"),
    (
        "unlisted other spelling",
        ".claude/skills/s/SKILL.md",
        FLAG.replace(K, "Disable_Model_Invocation") % "Yes",
    ),
    ("unlisted empty value", ".claude/commands/new.md", FLAG % ""),
    ("unlisted nested command tree", "private/x/.claude/commands/t.md", FLAG % "on"),
    ("unlisted namespaced command", ".claude/commands/ns/t.md", FLAG % "1"),
    ("a clean command", ".claude/commands/new.md", CLEAN),
    (
        "a body that only mentions the key",
        ".claude/commands/new.md",
        CLEAN + "Never set `%s: true`.\n" % K,
    ),
    (
        "a commented-out key",
        ".claude/commands/new.md",
        CLEAN.replace("---\n\n", "# %s: true\n---\n\n"),
    ),
    ("a sub-agent definition", ".claude/agents/a.md", FLAG % "true"),
    ("a non-Markdown file in the directory", ".claude/commands/notes.txt", FLAG % "true"),
    ("LISTED file keeping its key", LISTED, (FLAG % "true").replace("Body.", "New body.")),
    ("LISTED file with the key removed", LISTED, CLEAN),
    ("LISTED file flipped to false", LISTED, FLAG % "false"),
    (
        "LISTED file with a second key line",
        LISTED,
        (FLAG % "true").replace("---\n\n", "%s: true\n---\n\n" % K),
    ),
]

# The twin's documented over-refusals: it refuses a write whose TEXT carries the key with a value, wherever in the file and whatever the file type under a command directory, because it cannot read the resulting frontmatter the way the gate does.
SHELL_OVER_REFUSES = {"a body that only mentions the key", "a non-Markdown file in the directory"}


def _plant(root: pathlib.Path, rel: str, content: str) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    files = dict(BASE)
    files[rel] = content
    for path, text in files.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)


def _base_only(root: pathlib.Path) -> None:
    """The tree BEFORE the write a hook judges: BASE alone, so the hook sees the write and the gate sees its result."""
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for path, text in BASE.items():
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def gate_fails(root: pathlib.Path, rel: str, content: str) -> bool:
    _plant(root / "gate", rel, content)
    return gate.check_tree(root / "gate", gate.CONSOLE_ONLY).failed()


def _dispatch(stem: str, payload: dict) -> int:
    proc = subprocess.run(
        [sys.executable, str(DISPATCH), stem],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode in (0, 2), "guard %s crashed (rc %d): %s" % (
        stem,
        proc.returncode,
        proc.stderr[-400:],
    )
    return proc.returncode


def edit_guard_refuses(root: pathlib.Path, rel: str, content: str) -> bool:
    world = root / "hook"
    _base_only(world)
    payload = {
        "tool_name": "Write",
        "cwd": str(world),
        "tool_input": {"file_path": str(world / rel), "content": content},
    }
    return _dispatch("block_user_only_command", payload) == 2


def shell_twin_refuses(root: pathlib.Path, rel: str, content: str) -> bool:
    world = root / "shell"
    _base_only(world)
    command = "cat > %s <<'EOF'\n%sEOF" % (rel, content)
    payload = {"tool_name": "Bash", "cwd": str(world), "tool_input": {"command": command}}
    return _dispatch("block_user_only_command_shell_write", payload) == 2


def compare(tmp_path: pathlib.Path, hook) -> list[tuple[str, bool, bool]]:
    """(case, gate fails?, hook refuses?) for every case where the two disagree."""
    out = []
    for i, (name, rel, content) in enumerate(CASES):
        root = tmp_path / str(i)
        failed = gate_fails(root, rel, content)
        refused = hook(root, rel, content)
        if failed != refused:
            out.append((name, failed, refused))
    return out


def test_one_predicate_and_one_loader():
    shared = gate.predicate()
    assert shared is importlib.import_module("rediacc_hooks.model_invocation")
    for stem in ("block_user_only_command", "block_user_only_command_shell_write"):
        guard = importlib.import_module("rediacc_hooks.guards.%s" % stem)
        assert guard.model_invocation is shared, (
            "%s judges with a second copy of the predicate" % stem
        )


def test_the_fixtures_cover_both_directions_and_both_list_states(tmp_path):
    verdicts = {
        name: gate_fails(tmp_path / str(i), rel, content)
        for i, (name, rel, content) in enumerate(CASES)
    }
    assert sum(verdicts.values()) >= 6, verdicts
    assert len(verdicts) - sum(verdicts.values()) >= 5, verdicts
    assert verdicts["LISTED file keeping its key"] is False
    assert verdicts["unlisted truthy key"] is True
    assert verdicts["LISTED file with the key removed"] is True


def test_edit_guard_and_gate_agree(tmp_path):
    assert compare(tmp_path, edit_guard_refuses) == []


def test_shell_twin_never_allows_what_the_gate_refuses(tmp_path):
    diverged = compare(tmp_path, shell_twin_refuses)
    unsound = [d for d in diverged if d[1] and not d[2]]
    assert unsound == [], "the shell twin ALLOWS a write the gate fails: %s" % unsound
    assert {d[0] for d in diverged} == SHELL_OVER_REFUSES


def test_the_comparison_fires_on_a_planted_divergence(tmp_path):
    shared = gate.predicate()

    def ignores_the_list(_root, rel, content):
        # The planted regression: a hook judging `findings` (the bare predicate) instead of `verdict` (the predicate plus the exception list).
        return shared.in_scope(rel) and bool(shared.findings(content))

    diverged = {d[0] for d in compare(tmp_path, ignores_the_list)}
    assert "LISTED file keeping its key" in diverged
    assert "LISTED file with the key removed" in diverged
