"""The committed plan renders count only the plans git tracks (worklist #0b93d454).

`wl_store.agent_plan_files` globbed the working tree, so `check:ci-plan-record -- --update` run in a tree holding another session's untracked draft wrote `agent/INDEX.md` with one plan more than a clean CI checkout renders, and R8's equality then failed in CI. Measured three times on 2026-10-02: 180 plans written locally, 179 rendered in CI.

The committed renders pass `tracked_only=True` and see `git ls-files`, staged files included. The Stop hook's live view keeps the default and still sees a draft nobody has added yet. Outside a git checkout there is no tracked set to ask for, so the glob answers both.
"""

from __future__ import annotations

import pathlib
import subprocess

from rediacc_hooks.tests.wlfix import import_wl

S = import_wl("wl_store")
CK = import_wl("wl_checks")
PI = import_wl("wl_planindex")

PLAN = "# PLAN {name}\n\nStatus: draft\n\n- [ ] one open box\n"


def _git(root: pathlib.Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        env={"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1", "PATH": "/usr/bin:/bin"},
    )


def _plant(root: pathlib.Path) -> None:
    plans = root / "agent" / "plans"
    plans.mkdir(parents=True)
    for name in ("tracked", "staged", "untracked"):
        (plans / f"PLAN-{name}.md").write_text(PLAN.format(name=name), encoding="utf-8")


def _names(paths) -> set[str]:
    return {pathlib.Path(p).name for p in paths}


def _repo(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "repo"
    root.mkdir()
    _plant(root)
    _git(root, "init", "-q")
    _git(root, "add", "agent/plans/PLAN-tracked.md")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "seed")
    # STAGED, NOT COMMITTED: `git ls-files` reads the index, so a new plan that has been `git add`ed is part of the next commit and the committed render must count it.
    _git(root, "add", "agent/plans/PLAN-staged.md")
    return root


def test_committed_render_excludes_untracked_plan(tmp_path):
    root = _repo(tmp_path)
    want = {"PLAN-tracked.md", "PLAN-staged.md"}

    assert _names(S.agent_plan_files(root, tracked_only=True)) == want
    assert _names(r[0] for r in CK.plan_records(root, tracked_only=True)) == want
    rows = PI.census_rows(root, tracked_only=True)
    assert _names(r[0] for r in rows) == want
    assert "\n2 plan(s), 2 carrying boxes." in PI.render_census(rows)


def test_live_view_still_sees_untracked_draft(tmp_path):
    root = _repo(tmp_path)
    everything = {"PLAN-tracked.md", "PLAN-staged.md", "PLAN-untracked.md"}

    assert _names(S.agent_plan_files(root)) == everything
    assert _names(r[0] for r in CK.plan_records(root)) == everything
    assert _names(r[0] for r in PI.plan_stats(root)) == everything


def test_outside_git_checkout_falls_back_to_glob(tmp_path):
    root = tmp_path / "plain"
    root.mkdir()
    _plant(root)
    everything = {"PLAN-tracked.md", "PLAN-staged.md", "PLAN-untracked.md"}

    assert _names(S.agent_plan_files(root, tracked_only=True)) == everything


def test_subdirectory_of_checkout_falls_back_to_glob(tmp_path):
    # A fixture planted INSIDE some other checkout is not that checkout's root, so its tracked set says nothing about the fixture; the glob answers.
    outer = _repo(tmp_path)
    inner = outer / "fixture"
    inner.mkdir()
    _plant(inner)

    assert len(S.agent_plan_files(inner, tracked_only=True)) == 3
