"""The post-edit check for the Stop-hook modules (agent/plans/PLAN-stop-hook-continuity.md P2.6).

Every case drives the member THROUGH THE WIRING: it is looked up in `lifecycle.PATTERNS["post-tool"]` and run by `lifecycle.run_pattern`, so a hook file that exists but is not wired fails here rather than passing as a unit. The planted defects live in a private copy of the stop directory; the live tree is never touched.
"""

from __future__ import annotations

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
