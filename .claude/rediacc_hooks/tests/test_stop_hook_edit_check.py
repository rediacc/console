"""The post-edit check for the Stop-hook modules (agent/plans/PLAN-stop-hook-continuity.md P2.6).

Every case drives the member THROUGH THE WIRING: it is looked up in `lifecycle.PATTERNS["post-tool"]` and run by `lifecycle.run_pattern`, so a hook file that exists but is not wired fails here rather than passing as a unit. The planted defects live in a private copy of the stop directory; the live tree is never touched.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil

import pytest

from rediacc_hooks import lifecycle
from rediacc_hooks.tests import guardcorpus

ROOT = guardcorpus.repo_root()
STOP_DIR = ROOT / ".claude" / "hooks" / "stop"
SCRIPT = "hooks/context/stop-hook-edit-check.py"
PLANT = "\n\ndef _planted_by_the_p26_control():\n    return undefined_name_p26()\n"


def member():
    found = [m for m in lifecycle.flat_commands("post-tool") if SCRIPT in m["command"]]
    assert len(found) == 1, (
        "the post-edit check is not wired into the post-tool pattern exactly once: %s"
        % [m["command"] for m in lifecycle.flat_commands("post-tool")]
    )
    return found[0]


def drive(payload):
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(ROOT)
    return lifecycle.run_pattern("post-tool", json.dumps(payload), env=env, members=[member()])


def edit(path, tool="Edit"):
    return {"tool_name": tool, "tool_input": {"file_path": str(path)}, "tool_response": {}}


@pytest.fixture
def stop_copy(tmp_path):
    target = tmp_path / ".claude" / "hooks" / "stop"
    shutil.copytree(STOP_DIR, target, ignore=shutil.ignore_patterns("__pycache__"))
    return target


def context_of(out):
    assert out.strip(), "the check printed nothing"
    return json.loads(out)["hookSpecificOutput"]["additionalContext"]


def test_an_undefined_name_is_named_with_its_line(stop_copy):
    """CONTROL: an F821 planted in a copy. The warning names the file and the line, and the tool call is not blocked."""
    target = stop_copy / "wl_lkg.py"
    src = target.read_text(encoding="utf-8")
    target.write_text(src + PLANT, encoding="utf-8")
    line = (src + PLANT).splitlines().index("    return undefined_name_p26()") + 1

    rc, out, _err = drive(edit(target))
    assert rc == 0, "a warning hook must never block"
    text = context_of(out)
    assert "%s:%d:" % (target, line) in text, text
    assert "F821" in text, text
    assert "undefined_name_p26" in text, text


def test_an_import_time_failure_is_reported_by_the_smoke_test(stop_copy):
    """A sibling that raises on import is caught into worklist's `_BROKEN`, which the smoke test must read rather than trust the import."""
    target = stop_copy / "wl_hints.py"
    target.write_text(
        target.read_text(encoding="utf-8") + "\nraise RuntimeError('p26 import plant')\n",
        encoding="utf-8",
    )
    rc, out, _err = drive(edit(target, tool="Write"))
    assert rc == 0
    text = context_of(out)
    assert "sibling wl_hints did not import" in text, text
    assert "p26 import plant" in text, text


def test_a_clean_stop_module_produces_no_output(stop_copy):
    """INVERSE: a clean file is silent, or the notice is noise on every edit."""
    rc, out, err = drive(edit(stop_copy / "wl_lkg.py", tool="MultiEdit"))
    assert (rc, out, err) == (0, "", "")


def test_a_file_outside_the_stop_directory_is_ignored(tmp_path):
    """INVERSE: an undefined name elsewhere is not this hook's business."""
    other = tmp_path / "elsewhere.py"
    other.write_text("def f():\n    return nope()\n", encoding="utf-8")
    assert drive(edit(other)) == (0, "", "")


def test_a_non_edit_tool_is_ignored(stop_copy):
    target = stop_copy / "wl_lkg.py"
    target.write_text(target.read_text(encoding="utf-8") + PLANT, encoding="utf-8")
    assert drive({"tool_name": "Read", "tool_input": {"file_path": str(target)}}) == (0, "", "")


def test_settings_json_is_the_derived_hooks_block():
    """Every entry of `.claude/settings.json`'s `hooks`, timeouts included, is what `lifecycle.hooks_block()` derives.

    `test_settings_collapse` compares the COMMANDS a settings entry expands to, and `expand` discards the entry's own `timeout`, so a member budget added to the table without the settings sum (or a hand-edited sum) passed every test in the tree. This pins the whole block.
    """
    doc = json.loads(lifecycle.settings_path().read_text(encoding="utf-8"))
    assert doc.get("hooks") == lifecycle.hooks_block(), (
        "settings.json's hooks differ from `python3 .claude/rediacc_hooks/lifecycle.py --hooks`"
    )


# ---- every hook directory the lifecycle table runs (worklist #95918e15) ----------------------
#
# Until this, the check covered `.claude/hooks/stop/*.py` only, while lifecycle also ran hook code from `hooks/context`, `hooks/post-bash`, `hooks/trapguard`, `hooks/` itself and the `rediacc_hooks` package. The directory set is DERIVED from `lifecycle.PATTERNS` by the hook itself, and these cases derive it the same way, so a new hook directory gets a case with no edit here.

CLAUDE = ROOT / ".claude"
KNOWN_DIRS = {
    "hooks",
    "hooks/context",
    "hooks/post-bash",
    "hooks/trapguard",
    "hooks/stop",
    "rediacc_hooks",
    "rediacc_hooks/guards",
}
COPY_IGNORE = shutil.ignore_patterns("__pycache__", "state", "tests", "test-*.py", "*.pyc")


def edit_check_module():
    spec = importlib.util.spec_from_file_location("_edit_check_under_test", CLAUDE / SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def hook_dirs() -> list[str]:
    """Every directory the check covers, from the live lifecycle table: each script's own directory, and every non-test package directory under a script's package."""
    ec = edit_check_module()
    out = set()
    for script in ec.lifecycle_scripts(CLAUDE):
        top = ec.package_top(CLAUDE, script.parent)
        if top is None:
            out.add(script.parent.as_posix())
            continue
        for init in (CLAUDE / top).rglob("__init__.py"):
            rel = init.parent.relative_to(CLAUDE)
            if "tests" not in rel.parts:
                out.add(rel.as_posix())
    return sorted(out)


def plant_file(root, rel_dir):
    """The first non-dunder, non-test `.py` directly in the directory."""
    return next(
        p
        for p in sorted((root / rel_dir).glob("*.py"))
        if not p.name.startswith(("__", "test")) and p.is_file()
    )


@pytest.fixture
def claude_copy(tmp_path):
    root = tmp_path / ".claude"
    # `hookio.repo_root` finds the tree by `.claude` beside `.ci`, as every real checkout has it.
    (tmp_path / ".ci").mkdir()
    for sub in ("hooks", "rediacc_hooks"):
        shutil.copytree(CLAUDE / sub, root / sub, ignore=COPY_IGNORE)
    return root


def test_the_derived_directory_set_covers_every_known_hook_directory():
    """ANTI-VACUITY: a derivation that found nothing would parametrize zero cases and pass."""
    assert set(hook_dirs()) >= KNOWN_DIRS, hook_dirs()


@pytest.mark.parametrize("rel_dir", hook_dirs())
def test_an_import_time_failure_is_reported_in_every_hook_directory(claude_copy, rel_dir):
    """CONTROL: before #95918e15 every directory but hooks/stop was silent here."""
    target = plant_file(claude_copy, rel_dir)
    target.write_text(
        target.read_text(encoding="utf-8")
        + "\nraise RuntimeError('edit-check plant %s')\n" % rel_dir,
        encoding="utf-8",
    )
    rc, out, _err = drive(edit(target))
    assert rc == 0, "a warning hook must never block"
    text = context_of(out)
    assert "edit-check plant %s" % rel_dir in text, text
    assert str(target) in text, text


@pytest.mark.parametrize("rel_dir", hook_dirs())
def test_a_clean_edit_is_silent_in_every_hook_directory(claude_copy, rel_dir):
    """INVERSE: every covered directory imports cleanly from a copy, or the check would be noise on every edit there."""
    assert drive(edit(plant_file(claude_copy, rel_dir))) == (0, "", "")


def test_a_directory_newly_wired_into_lifecycle_is_covered_with_no_edit_to_the_check(claude_copy):
    """The set is derived: wiring a new directory into the copy's own lifecycle table is all it takes."""
    fresh = claude_copy / "hooks" / "fresh" / "fresh_hook.py"
    fresh.parent.mkdir()
    fresh.write_text(
        "def main():\n    return undefined_fresh_name()\n\n\nif __name__ == '__main__':\n    main()\n",
        encoding="utf-8",
    )
    assert drive(edit(fresh)) == (0, "", ""), "an unwired directory is not hook code"
    table = claude_copy / "rediacc_hooks" / "lifecycle.py"
    src = table.read_text(encoding="utf-8")
    anchor = '            "python3 " + _P % "hooks/context/onboard.py",\n'
    assert anchor in src
    table.write_text(
        src.replace(
            anchor, anchor + '            "python3 " + _P % "hooks/fresh/fresh_hook.py",\n', 1
        ),
        encoding="utf-8",
    )
    rc, out, _err = drive(edit(fresh))
    assert rc == 0
    text = context_of(out)
    assert "undefined_fresh_name" in text, text
    assert "F821" in text, text


def test_a_test_suite_beside_the_hooks_is_not_smoke_imported(stop_copy):
    """INVERSE: a `test-*.py` suite RUNS when imported, so smoke-importing it reported its own passing lines as a load failure (2026-09-25). Its F821 is not this hook's business either."""
    suite = stop_copy / "test-p26-suite.py"
    suite.write_text("print('case one   want=allowed got=allowed ok')\n" + PLANT, encoding="utf-8")
    assert drive(edit(suite)) == (0, "", "")
