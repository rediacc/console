"""The PR freeze (PLAN-two-track-merge-dev F1): real `git commit`s in a scratch repository whose commit-msg hook calls pr_freeze.check, against a worklist store (WORKLIST_STORE_DIR) holding a planted phase event."""

from __future__ import annotations

import datetime
import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

HOOKS = pathlib.Path(__file__).resolve().parents[1]
PR_FREEZE = HOOKS / "pr_freeze.py"
BRANCH = "1120-1"
OWNER = "d778be9d"
IDENT = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]

HOOK_SCRIPT = """#!%(python)s
import pathlib, subprocess, sys
import importlib.util
spec = importlib.util.spec_from_file_location("pr_freeze_hook", %(module)r)
pf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pf)
msg = pathlib.Path(sys.argv[1]).read_text()
repo = pathlib.Path.cwd()
branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True).stdout.strip()
paths = [p for p in subprocess.run(["git", "diff", "--cached", "--name-only"], capture_output=True, text=True).stdout.split("\\n") if p]
ok, reason = pf.check(repo, repo, branch, msg, paths)
if not ok:
    sys.stderr.write("FROZEN: " + reason + "\\n")
    sys.exit(1)
"""


def _load():
    spec = importlib.util.spec_from_file_location("pr_freeze_under_test", PR_FREEZE)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


PF = _load()


def _git(cwd, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=check
    )


def _now(hours_ago=0.0):
    return (datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=hours_ago)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _event(**kw):
    base = {"at": _now(), "by": OWNER, "o": OWNER, "h": "0", "br": BRANCH, "ns": 1}
    base.update(kw)
    return json.dumps(base)


@pytest.fixture
def world(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", BRANCH, str(repo)], check=True)
    _git(repo, *IDENT, "commit", "-q", "--allow-empty", "-m", "base")
    (repo / ".ci" / "policy").mkdir(parents=True)
    (repo / ".ci" / "policy" / "record-paths.json").write_text(
        json.dumps({"version": 1, "records": [{"glob": "agent/reviews/**", "except": []}]})
    )
    hook = repo / ".git" / "hooks" / "commit-msg"
    hook.write_text(HOOK_SCRIPT % {"python": sys.executable, "module": str(PR_FREEZE)})
    hook.chmod(0o755)
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setenv("WORKLIST_STORE_DIR", str(store))
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    return repo, store


def _phase(store, mode="babysit", branch=BRANCH, hours_ago=0.0, pr=605, items=()):
    lines = [
        _event(ev="phase", mode=mode, branch=branch, pr=pr, why="test", at=_now(hours_ago), ns=2)
    ]
    for i, (iid, text, state, owner) in enumerate(items):
        lines.append(_event(ev="add", id=iid, s=" ", o=owner, t=text, ns=10 + i))
        if state != " ":
            lines.append(_event(ev="state", id=iid, s=state, note="done", ns=100 + i))
    (store / ("%s.jsonl" % OWNER)).write_text("\n".join(lines) + "\n")


def _commit(repo, subject, path="f.txt", body=""):
    p = repo / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(subject + "\n")
    _git(repo, "add", path)
    return _git(
        repo, *IDENT, "commit", "-q", "-m", subject + ("\n\n" + body if body else ""), check=False
    )


@pytest.mark.parametrize(
    ("subject", "admitted"),
    [
        ("feat(ci): a new thing", False),
        ("chore(pins): bump npm", False),
        ("perf(plans): faster", False),
        ("fix(ci): a fix", True),
        ("test(ci): a test", True),
        ("chore(reviews): records", True),
        ("chore(state): resume point", True),
        ("chore(plans): tick a box", True),
    ],
)
def test_the_subject_decides_under_a_babysit_phase(world, subject, admitted):
    repo, store = world
    _phase(store)
    r = _commit(repo, subject)
    assert (r.returncode == 0) is admitted, r.stderr
    if not admitted:
        assert "FROZEN" in r.stderr
        assert "--phase <me> build" in r.stderr


def test_a_record_paths_only_commit_is_admitted(world):
    repo, store = world
    _phase(store)
    r = _commit(repo, "feat(ci): records only", path="agent/reviews/1120-1/clean.jsonl")
    assert r.returncode == 0, r.stderr


def test_focus_fix_admits_only_an_open_item_of_the_owner_with_the_pr(world):
    repo, store = world
    items = [
        ("aaaa1111", "fix the thing pr:605/fix", " ", OWNER),
        ("bbbb2222", "fix the thing pr:605/fix", "x", OWNER),
        ("cccc3333", "fix the thing pr:605/fix", " ", "6c87d631"),
        ("dddd4444", "fix the thing pr:999/fix", " ", OWNER),
    ]
    _phase(store, items=items)
    assert _commit(repo, "feat(ci): a", body="focus-fix:#aaaa1111").returncode == 0
    for iid, why in (("bbbb2222", "closed"), ("cccc3333", "a peer"), ("dddd4444", "another pr")):
        r = _commit(repo, "feat(ci): %s" % why, path="g-%s.txt" % iid, body="focus-fix:#%s" % iid)
        assert r.returncode != 0, "%s must be refused" % why


def test_a_phase_on_another_branch_does_not_freeze(world):
    repo, store = world
    _phase(store, branch="1119-9")
    assert _commit(repo, "feat(ci): free here").returncode == 0


def test_an_expired_phase_does_not_freeze(world):
    repo, store = world
    _phase(store, hours_ago=30)
    assert _commit(repo, "feat(ci): the phase lapsed").returncode == 0


def test_a_build_phase_does_not_freeze(world):
    repo, store = world
    _phase(store, mode="build")
    assert _commit(repo, "feat(ci): building").returncode == 0


def test_a_gitlink_bump_is_judged_by_the_range_it_brings_in(world, tmp_path):
    repo, store = world
    sub = tmp_path / "sub"
    subprocess.run(["git", "init", "-q", "-b", BRANCH, str(sub)], check=True)
    _git(sub, *IDENT, "commit", "-q", "--allow-empty", "-m", "fix(x): base")
    _git(
        repo, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(sub), "private/sub"
    )
    _git(repo, *IDENT, "commit", "-q", "-m", "fix(sub): add the submodule")
    _phase(store)
    inner = repo / "private" / "sub"
    _git(inner, *IDENT, "commit", "-q", "--allow-empty", "-m", "fix(x): only fixes")
    _git(repo, "add", "private/sub")
    assert _git(repo, *IDENT, "commit", "-q", "-m", "chore(sub): bump", check=False).returncode == 0
    _git(inner, *IDENT, "commit", "-q", "--allow-empty", "-m", "feat(x): new work")
    _git(repo, "add", "private/sub")
    r = _git(repo, *IDENT, "commit", "-q", "-m", "chore(sub): bump again", check=False)
    assert r.returncode != 0, "a bump whose range holds a feat must be refused"
    assert "feat(x): new work" in r.stderr


def test_control_with_no_phase_the_same_commit_lands(world):
    """CONTROL: with no phase the same feat commit lands, so the refusals above come from the freeze and not from the harness."""
    repo, _store = world
    assert _commit(repo, "feat(ci): no phase at all").returncode == 0


def test_control_a_verdict_that_always_admits_turns_the_feat_case_red(world, monkeypatch):
    """CONTROL (the plan's mutant): `verdict` replaced with (True, "") admits the feat commit the babysit phase must refuse, so the refusal assertions above are what this suite pins. check:ci-guard-mutations mutates CLI TypeScript only, so the mutant is driven here."""
    repo, store = world
    _phase(store)
    assert PF.check(repo, repo, BRANCH, "feat(ci): a new thing", ["f.txt"])[0] is False
    monkeypatch.setattr(PF, "verdict", lambda *_a, **_k: (True, ""))
    assert PF.check(repo, repo, BRANCH, "feat(ci): a new thing", ["f.txt"])[0] is True


def test_verdict_core_names_the_escape():
    ok, reason = PF.verdict(
        "feat(x): y", ["a.py"], {}, {"mode": "babysit", "branch": "b", "pr": 7, "o": OWNER}, {}
    )
    assert not ok
    assert "worklist.py --phase <me> build" in reason
    assert PF.verdict("feat(x): y", ["a.py"], {}, None, {}) == (True, "")


def test_a_loader_error_fails_open_with_a_note(world, monkeypatch):
    repo, _store = world
    monkeypatch.setattr(
        PF, "active_phase", lambda *_a: (_ for _ in ()).throw(OSError("store unreadable"))
    )
    ok, reason = PF.check(repo, repo, BRANCH, "feat(x): y", ["a.py"])
    assert ok
    assert "could not judge" in reason


def _githooks():
    spec = importlib.util.spec_from_file_location(
        "githooks_pr_freeze_under_test", HOOKS / "git" / "githooks.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_commit_msg_is_wired_to_the_freeze(world, monkeypatch, capsys):
    """githooks.pr_freeze_refusal refuses what pr_freeze refuses, and skips a lease."""
    repo, _store = world
    gh = _githooks()
    fake = type("F", (), {"check": staticmethod(lambda *_a: (False, "FROZEN-BY-FAKE"))})
    monkeypatch.setattr(gh, "_load", lambda name, _path: fake if name == "pr_freeze" else None)
    assert gh.pr_freeze_refusal("feat(x): y", str(repo), BRANCH, ["f.txt"]) != 0
    assert "FROZEN-BY-FAKE" in capsys.readouterr().err
    monkeypatch.setattr(gh.cp, "lease_root", lambda _repo: "/lease")
    assert gh.pr_freeze_refusal("feat(x): y", str(repo), BRANCH, ["f.txt"]) == 0, (
        "a lease is judged when its commits land, not here"
    )


def test_an_unreadable_submodule_range_refuses_the_bump():
    """Review a29977aa.1: a range that cannot be read is not an empty range."""
    phase = {"mode": "babysit", "branch": BRANCH, "pr": 605, "o": OWNER}
    ok, reason = PF.verdict("chore(sub): bump", ["private/sub"], {"private/sub": None}, phase, {})
    assert not ok
    assert "unreadable" in reason
    assert PF.verdict("chore(sub): bump", ["private/sub"], {"private/sub": []}, phase, {})[0], (
        "CONTROL: a readable empty range admits"
    )


def test_a_missing_freeze_module_fails_open(monkeypatch, capsys, tmp_path):
    gh = _githooks()

    def missing(_name, path):
        raise FileNotFoundError(path)

    monkeypatch.setattr(gh, "_load", missing)
    monkeypatch.setattr(gh.cp, "lease_root", lambda _repo: "")
    assert gh.pr_freeze_refusal("feat(x): y", str(tmp_path), BRANCH, ["f.txt"]) == 0
    assert "not loaded" in capsys.readouterr().err
