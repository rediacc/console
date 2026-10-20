"""block_turbo_early_push admits the `/pr-merge` pointer-bump push in the session's merge phase (#8aad9216).

`/pr-merge` step 2 pushes the console's submodule pointer bump, and the review records committed for it, to the PR branch. Under turbo with a Promoted plan open that push was refused, and only a borrowed `deadline:` reason got it through. The guard now admits it with no reason when the session's newest phase is `merge` for the checkout's branch and the unpushed range changes only gitlinks and `agent/reviews/` paths.

REAL REPOSITORIES built by the guard's own `world()` (turbo on, PLAN-fx-a open, so every case below would be refused without the admission), with `origin/1008-1` moved to the seeded work commit so the unpushed range holds only the commits each case adds. The phase lives in a store directory named by `WORKLIST_STORE_DIR`, in the shape `wl_store.phase_event` writes. Each payload runs through the real dispatcher in a subprocess, with `gh` stubbed on PATH.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import os
import pathlib
import subprocess
import sys

import pytest

HOOKS = pathlib.Path(__file__).resolve().parents[1]
GUARD = HOOKS / "guards" / "block_turbo_early_push.py"
DISPATCH = HOOKS / "dispatch.py"
STEM = "block_turbo_early_push"
SID = "cafe0000-1111-2222-3333-444455556666"
ME = SID[:8]
BRANCH = "1008-1"
PUSH = "git push origin %s" % BRANCH

_SPEC = importlib.util.spec_from_file_location("turbo_guard_merge_phase", GUARD)
if _SPEC is None or _SPEC.loader is None:
    raise SystemExit("cannot load %s" % GUARD)
G = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(G)


def _commit(repo, msg):
    G._git(repo, "commit", "-q", "-m", msg)


def _gitlink(repo, path="private/renet"):
    G._git(repo, "update-index", "--add", "--cacheinfo", "160000,%s,%s" % ("a" * 40, path))
    _commit(repo, "chore(submodules): bump pointers")


def _review(repo):
    f = repo / "agent" / "reviews" / BRANCH / "deadbeef.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("# review\n", encoding="utf-8")
    G._git(repo, "add", "--", str(f.relative_to(repo)))
    _commit(repo, "chore(reviews): record reviews")


def _other(repo):
    f = repo / "docs" / "note.md"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("a change\n", encoding="utf-8")
    G._git(repo, "add", "--", "docs/note.md")
    _commit(repo, "docs: a change")


@pytest.fixture
def world(tmp_path):
    repo = G.world(tmp_path / "repo")
    # Everything the fixture made is pushed; only what a case adds is in the range.
    G._git(repo, "update-ref", "refs/remotes/origin/%s" % BRANCH, "HEAD")
    gh = tmp_path / "bin"
    gh.mkdir()
    (gh / "gh").write_text(G.GH_NONE_BODY, encoding="utf-8")
    (gh / "gh").chmod(0o755)
    store = tmp_path / "store"
    store.mkdir()
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    return {"repo": repo, "gh": gh, "store": store, "tmp": tmp}


def _phase(w, mode, branch=BRANCH):
    row = {
        "ev": "phase",
        "at": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "by": ME,
        "o": ME,
        "mode": mode,
        "branch": branch,
        "pr": 599,
        "why": "operator",
    }
    (w["store"] / ("%s.jsonl" % ME)).write_text(json.dumps(row) + "\n", encoding="utf-8")


def _run(w, command=PUSH):
    env = dict(
        os.environ,
        CLAUDE_PROJECT_DIR=str(w["repo"]),
        PATH="%s:%s" % (w["gh"], os.environ["PATH"]),
        TMPDIR=str(w["tmp"]),
        WORKLIST_STORE_DIR=str(w["store"]),
    )
    env.pop("TURBO_PUSH_REASON", None)
    payload = json.dumps(
        {
            "tool_name": "Bash",
            "tool_input": {"command": command},
            "cwd": str(w["repo"]),
            "session_id": SID,
        }
    )
    proc = subprocess.run(
        [sys.executable, str(DISPATCH), STEM],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert proc.returncode in (0, 2), proc.stderr[-800:]
    return proc.returncode, proc.stderr


def _ledger(w):
    path = w["repo"] / G.LEDGER_REL
    if not path.is_file():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln]


def test_merge_phase_gitlink_only_is_admitted(world):
    _phase(world, "merge")
    _gitlink(world["repo"])
    rc, err = _run(world)
    assert rc == 0, err
    rows = _ledger(world)
    assert [r["kind"] for r in rows] == [G.MERGE_KIND]


def test_merge_phase_gitlink_and_reviews_is_admitted(world):
    _phase(world, "merge")
    _gitlink(world["repo"])
    _review(world["repo"])
    rc, err = _run(world)
    assert rc == 0, err
    assert [r["kind"] for r in _ledger(world)] == [G.MERGE_KIND]


def test_merge_phase_with_another_path_is_refused(world):
    _phase(world, "merge")
    _gitlink(world["repo"])
    _other(world["repo"])
    rc, err = _run(world)
    assert rc == 2
    assert "docs/note.md" in err
    assert "pointer bump needs no reason" in err
    assert _ledger(world) == []


def test_merge_phase_symlink_under_reviews_is_refused(world):
    _phase(world, "merge")
    _gitlink(world["repo"])
    link = world["repo"] / "agent" / "reviews" / BRANCH / "x.md"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to("../../../docs")
    G._git(world["repo"], "add", "--", str(link.relative_to(world["repo"])))
    _commit(world["repo"], "chore(reviews): a symlink, not a record")
    rc, err = _run(world)
    assert rc == 2
    assert "agent/reviews/%s/x.md" % BRANCH in err
    assert _ledger(world) == []


@pytest.mark.parametrize(
    "command",
    [
        "git push origin other:%s" % BRANCH,  # sends a ref the range check never read
        "git push origin +%s" % BRANCH,
        "git push --force origin %s" % BRANCH,
        "git push --force-with-lease=%s origin %s" % (BRANCH, BRANCH),
        "git push --tags origin %s" % BRANCH,
        "git push -f origin %s" % BRANCH,
        "git push --force-if-includes origin %s" % BRANCH,
        "git push --all origin",
        "git push --mirror origin",
        "git push origin",  # no explicit refspec
        "git push origin HEAD",  # HEAD with no destination names no branch
    ],
)
def test_merge_phase_refuses_a_push_that_is_not_exactly_head(world, command):
    _phase(world, "merge")
    _gitlink(world["repo"])
    G._git(world["repo"], "branch", "other")
    rc, _err = _run(world, command)
    assert rc == 2, command
    assert _ledger(world) == []


def test_a_delete_push_stays_out_of_scope_not_merge_admitted(world):
    # SCOPE: the guard never judges a delete push (the cleanup after a merge), so the merge phase has nothing to admit or ledger.
    _phase(world, "merge")
    _gitlink(world["repo"])
    rc, err = _run(world, "git push --delete origin %s" % BRANCH)
    assert rc == 0, err
    assert _ledger(world) == []


def test_merge_phase_admits_head_onto_the_branch(world):
    _phase(world, "merge")
    _gitlink(world["repo"])
    rc, err = _run(world, "git push origin HEAD:%s" % BRANCH)
    assert rc == 0, err


def test_an_unreadable_phase_store_fails_closed(world):
    (world["store"] / ("%s.jsonl" % ME)).write_text("{not json\n", encoding="utf-8")
    _gitlink(world["repo"])
    rc, _err = _run(world)
    assert rc == 2
    assert _ledger(world) == []


def test_build_phase_gitlink_only_is_refused(world):
    _phase(world, "build")
    _gitlink(world["repo"])
    rc, err = _run(world)
    assert rc == 2
    assert "BLOCKED: turbo is on" in err
    assert _ledger(world) == []


def test_no_phase_gitlink_only_is_refused(world):
    _gitlink(world["repo"])
    rc, _err = _run(world)
    assert rc == 2


def test_merge_phase_for_another_branch_is_refused(world):
    _phase(world, "merge", branch="1007-1")
    _gitlink(world["repo"])
    rc, _err = _run(world)
    assert rc == 2
    assert _ledger(world) == []


def test_merge_phase_push_to_another_destination_is_refused(world):
    _phase(world, "merge")
    _gitlink(world["repo"])
    rc, _err = _run(world, "git push origin HEAD:1009-1")
    assert rc == 2


def test_merge_phase_never_admits_gh_pr_create(world):
    _phase(world, "merge")
    _gitlink(world["repo"])
    rc, _err = _run(world, "gh pr create --draft -t x -b y")
    assert rc == 2
