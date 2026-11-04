"""Walkers stay out of lease trees (PLAN-worktree-lease W3): a root-anchored walk run in the live tree does not read `.claude/worktrees/<id>/`.

Each fixture plants a marker at `.claude/worktrees/x/marker` beside a real file, then drives the surveyed entries over it. A raw `os.walk` control reports the marker, so the instrument can fail; `paths.walk_tree` and the three entries the survey moved or patched do not. The TS entry (`importersOf` in `scripts/lib/pins/drivers/npm.ts`) cannot be imported from Python: its ignore list is read out of the source and handed to the same `glob` package, with the entry removed as a control.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import subprocess

import pytest

from rediacc_ci import paths

QUALITY_SCRIPTS = paths.CI_DIR / "scripts" / "quality"
NPM_DRIVER = paths.CI_DIR.parent / "scripts" / "lib" / "pins" / "drivers" / "npm.ts"
LEASE_ENTRY = ".claude/worktrees/x"
LEASE_IGNORE = ".claude/worktrees/**"
GLOB_PROBE = """
const { globSync } = require('glob');
const ignore = JSON.parse(process.argv[2]);
const found = globSync(['**/*.{ts,js}'], { cwd: process.argv[1], posix: true, dot: true, ignore });
process.stdout.write(JSON.stringify(found));
"""


@pytest.fixture
def tree(tmp_path):
    """A plain (non-git) root with one real file and a marker inside a lease directory."""
    for rel in (
        "docs/real.py",
        "docs/real.ts",
        f"{LEASE_ENTRY}/marker",
        f"{LEASE_ENTRY}/marker.py",
    ):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x = 1\n", encoding="utf-8")
    (tmp_path / LEASE_ENTRY / "marker.ts").write_text("export {};\n", encoding="utf-8")
    return tmp_path


def reports_marker(found):
    return any("marker" in str(item) for item in found)


def load_entry(monkeypatch, name):
    monkeypatch.syspath_prepend(str(QUALITY_SCRIPTS))
    return importlib.import_module(name)


def test_walkers_control_raw_os_walk_reports_the_marker(tree):
    raw = [os.path.join(d, f) for d, _dirs, files in os.walk(tree) for f in files]
    assert reports_marker(raw)


def test_walkers_walk_tree_does_not_report_the_marker(tree):
    pruned = [os.path.join(d, f) for d, _dirs, files in paths.walk_tree(tree) for f in files]
    assert not reports_marker(pruned)
    assert any(item.endswith("real.py") for item in pruned)


def test_walkers_walk_tree_goes_red_without_the_prune_entry(tree, monkeypatch):
    """The instrument can fail: with the `(.claude, worktrees)` pair removed the helper reports the marker."""
    monkeypatch.setattr(paths, "PRUNED_DIR_PAIRS", ((".ci", "cache"),))
    unpruned = [os.path.join(d, f) for d, _dirs, files in paths.walk_tree(tree) for f in files]
    assert reports_marker(unpruned)


def test_walkers_policy_inventory_fallback_walk_skips_the_lease(tree, monkeypatch):
    entry = load_entry(monkeypatch, "check_policy_inventory")
    found, how = entry.source_files(tree)
    assert how == "filesystem walk"
    assert not reports_marker(found)
    assert "docs/real.py" in found


def test_walkers_plan_deps_fallback_walk_skips_the_lease(tree, monkeypatch):
    entry = load_entry(monkeypatch, "check_plan_deps")
    found = entry._repo_files(tree)
    assert not reports_marker(found)
    assert "docs/real.py" in found


def ignore_list_from_source():
    """The `ignore: [...]` array of `importersOf`, as a list of strings."""
    text = NPM_DRIVER.read_text(encoding="utf-8")
    body = text.split("function importersOf", 1)[1]
    block = re.search(r"ignore: \[(.*?)\]", body, re.DOTALL).group(1)
    return re.findall(r"'([^']+)'", block)


def glob_found(tree, ignore):
    done = subprocess.run(
        ["node", "-e", GLOB_PROBE, str(tree), json.dumps(ignore)],
        cwd=paths.CI_DIR.parent,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return json.loads(done.stdout)


def test_walkers_ts_importers_ignore_list_skips_the_lease(tree):
    ignore = ignore_list_from_source()
    assert LEASE_IGNORE in ignore
    found = glob_found(tree, ignore)
    assert not reports_marker(found)
    assert "docs/real.ts" in found


def test_walkers_ts_importers_control_without_the_entry_reports_the_marker(tree):
    ignore = [entry for entry in ignore_list_from_source() if entry != LEASE_IGNORE]
    assert reports_marker(glob_found(tree, ignore))
