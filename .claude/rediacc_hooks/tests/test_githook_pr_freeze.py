"""The PR freeze (PLAN-simple-two-tree-loop B1): real `git commit`s in a scratch repository with two trees bound by a landing record, whose shared commit-msg hook calls pr_freeze.check, against a `gh` stub on PATH answering the landing branch's open PRs and a worklist store (WORKLIST_STORE_DIR) holding the items focus-fix names.

Both directions on every rule: the landing tree refuses a feat while its PR is open, and the development tree, the same commit, lands it (the control); each admit row has a refusal beside it.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import types

import pytest

HOOKS = pathlib.Path(__file__).resolve().parents[1]
PR_FREEZE = HOOKS / "pr_freeze.py"
BRANCH = "1120-1"
DEV_BRANCH = "1120-2"
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

GH_STUB = """#!/bin/sh
d="$(dirname "$0")/.."
echo "$*" >> "$d/gh-calls.log"
cat "$d/gh-answer.json"
exit "$(cat "$d/gh-rc")"
"""


def _load():
    spec = importlib.util.spec_from_file_location("pr_freeze_under_test", PR_FREEZE)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
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


class World(types.SimpleNamespace):
    def gh(self, answer="[]", rc=0):
        """What the `gh` stub prints and exits with; the call log starts empty."""
        (self.tmp / "gh-answer.json").write_text(answer)
        (self.tmp / "gh-rc").write_text(str(rc))
        (self.tmp / "gh-calls.log").write_text("")

    def pr_open(self, number=605):
        self.gh(json.dumps([{"number": number}]))

    def gh_calls(self):
        return [ln for ln in (self.tmp / "gh-calls.log").read_text().splitlines() if ln]


@pytest.fixture
def world(tmp_path, monkeypatch):
    """`main` (the development tree, on DEV_BRANCH) and `landing` (a linked tree on BRANCH) bound by a landing record; the commit-msg hook in the common git dir serves both. The gh stub answers no open PR until a test says otherwise."""
    main = tmp_path / "main"
    subprocess.run(["git", "init", "-q", "-b", DEV_BRANCH, str(main)], check=True)
    _git(main, *IDENT, "commit", "-q", "--allow-empty", "-m", "base")
    (main / ".ci" / "policy").mkdir(parents=True)
    (main / ".ci" / "policy" / "record-paths.json").write_text(
        json.dumps({"version": 1, "records": [{"glob": "agent/reviews/**", "except": []}]})
    )
    _git(main, "add", ".ci")
    _git(main, *IDENT, "commit", "-q", "-m", "fix: policy")
    landing = tmp_path / "landing"
    _git(main, "worktree", "add", "-q", "-b", BRANCH, str(landing))
    landing = pathlib.Path(os.path.realpath(landing))
    PF.commit_policy().write_landing_record(str(main), str(landing), BRANCH)
    hook = main / ".git" / "hooks" / "commit-msg"
    hook.write_text(HOOK_SCRIPT % {"python": sys.executable, "module": str(PR_FREEZE)})
    hook.chmod(0o755)
    store = tmp_path / "store"
    store.mkdir()
    (tmp_path / "bin").mkdir()
    stub = tmp_path / "bin" / "gh"
    stub.write_text(GH_STUB)
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", "%s%s%s" % (tmp_path / "bin", os.pathsep, os.environ["PATH"]))
    monkeypatch.setenv("WORKLIST_STORE_DIR", str(store))
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    w = World(tmp=tmp_path, main=main, landing=landing, store=store)
    w.gh()
    return w


def _items(store, items=()):
    lines = []
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
def test_the_subject_decides_in_the_landing_tree_with_an_open_pr(world, subject, admitted):
    world.pr_open()
    r = _commit(world.landing, subject)
    assert (r.returncode == 0) is admitted, r.stderr
    if not admitted:
        assert "FROZEN" in r.stderr
        assert "PR #605" in r.stderr
        assert "landing --promote" in r.stderr
        assert "development tree" in r.stderr


def test_control_the_development_tree_lands_the_same_feat(world):
    """CONTROL: with the landing PR open, the same feat commit lands in the development tree, so the refusal above is the role's."""
    world.pr_open()
    assert _commit(world.landing, "feat(ci): in landing").returncode != 0
    r = _commit(world.main, "feat(ci): in development")
    assert r.returncode == 0, r.stderr
    assert world.gh_calls() == [
        "pr list --head %s --state open --json number --limit 5" % BRANCH
    ], "the development commit reads no PR; the landing one reads the record's branch"


def test_a_fix_lands_in_both_trees_and_reads_no_pr(world):
    world.pr_open()
    assert _commit(world.landing, "fix(ci): landing repair").returncode == 0
    assert _commit(world.main, "fix(ci): development repair").returncode == 0
    assert world.gh_calls() == [], "a fix commit is admitted before the PR read"


def test_no_open_pr_the_landing_tree_is_not_frozen(world):
    """After the merge (or before promote opens the next PR) the landing tree takes any commit: the hotfix on main, the idle tree."""
    world.gh("[]")
    r = _commit(world.landing, "feat(ci): nothing open")
    assert r.returncode == 0, r.stderr
    assert len(world.gh_calls()) == 1


@pytest.mark.parametrize(
    ("answer", "rc", "why"),
    [
        ("", 1, "exited 1"),
        ("not json", 0, "no JSON"),
        ('{"number": 605}', 0, "not a list"),
        ('[{"title": "x"}]', 0, "carry no number"),
    ],
)
def test_an_unknown_pr_state_refuses_a_feat_and_still_admits_a_fix(world, answer, rc, why):
    """Unknown is never "no PR": a gh that cannot answer refuses what only the PR state could admit, and names why."""
    world.gh(answer, rc)
    r = _commit(world.landing, "feat(ci): blind")
    assert r.returncode != 0
    assert "unknown" in r.stderr
    assert why in r.stderr
    assert _commit(world.landing, "fix(ci): blind but a fix", path="g.txt").returncode == 0


def test_a_record_paths_only_commit_is_admitted(world):
    world.pr_open()
    r = _commit(world.landing, "feat(ci): records only", path="agent/reviews/1120-1/clean.jsonl")
    assert r.returncode == 0, r.stderr
    assert world.gh_calls() == []
    r = _commit(world.landing, "feat(ci): code", path="code.py")
    assert r.returncode != 0, "CONTROL: a code path is refused"


def test_focus_fix_admits_an_open_item_of_any_session_carrying_the_landing_pr(world):
    items = [
        ("aaaa1111", "fix the thing pr:605/fix", " ", OWNER),
        ("bbbb2222", "fix the thing pr:605/fix", "x", OWNER),
        ("cccc3333", "fix the thing pr:605/fix", " ", "6c87d631"),
        ("dddd4444", "fix the thing pr:999/fix", " ", OWNER),
        ("eeee5555", "fix the thing pr:6050/fix", " ", OWNER),
    ]
    _items(world.store, items)
    world.pr_open()
    assert _commit(world.landing, "feat(ci): a", body="focus-fix:#aaaa1111").returncode == 0
    r = _commit(world.landing, "feat(ci): peer", path="g-peer.txt", body="focus-fix:#cccc3333")
    assert r.returncode == 0, "an item of another session admits: the freeze has no owner"
    for iid, why in (
        ("bbbb2222", "is not open"),
        ("dddd4444", "does not carry pr:605"),
        ("eeee5555", "does not carry pr:605"),
        ("ffff6666", "names no open item"),
    ):
        r = _commit(
            world.landing, "feat(ci): %s" % iid, path="g-%s.txt" % iid, body="focus-fix:#%s" % iid
        )
        assert r.returncode != 0, "%s must be refused" % iid
        assert why in r.stderr


def _submodule(world, tmp_path):
    """A submodule at private/sub of the landing tree, cloned from `origin` (a bare repository whose main holds one fix), added by a fix commit, its tree on BRANCH."""
    origin = tmp_path / "sub-origin.git"
    seed = tmp_path / "sub-seed"
    subprocess.run(["git", "init", "-q", "-b", "main", str(seed)], check=True)
    _git(seed, *IDENT, "commit", "-q", "--allow-empty", "-m", "fix(x): base")
    subprocess.run(["git", "clone", "-q", "--bare", str(seed), str(origin)], check=True)
    _git(
        world.landing,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(origin),
        "private/sub",
    )
    assert _git(world.landing, *IDENT, "commit", "-q", "-m", "fix(sub): add").returncode == 0
    inner = world.landing / "private" / "sub"
    _git(inner, "checkout", "-q", "-b", BRANCH)
    return inner


def test_a_gitlink_bump_is_judged_by_the_range_it_brings_in(world, tmp_path):
    inner = _submodule(world, tmp_path)
    world.pr_open()
    _git(inner, *IDENT, "commit", "-q", "--allow-empty", "-m", "fix(x): only fixes")
    _git(world.landing, "add", "private/sub")
    r = _git(world.landing, *IDENT, "commit", "-q", "-m", "chore(sub): bump", check=False)
    assert r.returncode == 0, r.stderr
    _git(inner, *IDENT, "commit", "-q", "--allow-empty", "-m", "feat(x): new work")
    _git(world.landing, "add", "private/sub")
    r = _git(world.landing, *IDENT, "commit", "-q", "-m", "chore(sub): bump again", check=False)
    assert r.returncode != 0, "a bump whose range holds a feat off origin/main must be refused"
    assert "feat(x): new work" in r.stderr


def test_the_merge_pointer_bump_lands_when_every_pointer_is_on_origin_main(world, tmp_path):
    """Rule 6: the submodule's feat reached its origin/main (its PR merged), so the console's bump to it lands in the landing tree, though its range holds a feat. The CONTROL is the same shape one commit ahead of origin/main, refused."""
    inner = _submodule(world, tmp_path)
    world.pr_open()
    _git(inner, *IDENT, "commit", "-q", "--allow-empty", "-m", "feat(x): merged work")
    _git(inner, "push", "-q", "origin", "HEAD:main")
    _git(inner, "fetch", "-q", "origin")
    _git(world.landing, "add", "private/sub")
    r = _git(world.landing, *IDENT, "commit", "-q", "-m", "chore(submodules): bump", check=False)
    assert r.returncode == 0, r.stderr
    _git(inner, *IDENT, "commit", "-q", "--allow-empty", "-m", "feat(x): unmerged work")
    _git(world.landing, "add", "private/sub")
    r = _git(world.landing, *IDENT, "commit", "-q", "-m", "chore(submodules): ahead", check=False)
    assert r.returncode != 0, "a pointer ahead of origin/main is not the merge pointer bump"
    assert "feat(x): unmerged work" in r.stderr


def test_gitlink_on_main_reads_unreadable_as_none(world, tmp_path):
    sub = tmp_path / "sub2"
    subprocess.run(["git", "init", "-q", "-b", BRANCH, str(sub)], check=True)
    _git(sub, *IDENT, "commit", "-q", "--allow-empty", "-m", "fix(x): base")
    sha = _git(sub, "rev-parse", "HEAD").stdout.strip()
    _git(world.landing, "update-index", "--add", "--cacheinfo", "160000,%s,private/ghost" % sha)
    assert PF.gitlink_on_main(world.landing, ["private/ghost"]) == {"private/ghost": None}
    assert PF.gitlink_on_main(world.landing, ["f.txt"]) == {}, "a path that is no gitlink is absent"


def test_verdict_rule_6_needs_every_pointer_on_main():
    freeze = {"branch": BRANCH, "pr": 605}
    ranges = {"private/a": ["feat(x): a"], "private/b": ["feat(x): b"]}
    both = {"private/a": True, "private/b": True}
    assert PF.verdict("chore(submodules): bump", list(ranges), ranges, freeze, {}, None, both)[0]
    for partial in (
        {"private/a": True, "private/b": False},
        {"private/a": True, "private/b": None},
    ):
        ok, reason = PF.verdict(
            "chore(submodules): bump", list(ranges), ranges, freeze, {}, None, partial
        )
        assert not ok, partial
        assert "not on the submodule's origin/main" in reason


def test_control_a_mutant_that_ignores_the_role_turns_the_development_row_red(world, monkeypatch):
    """CONTROL (the plan's mutant): `landing_branch` answering the record's branch for every tree refuses the development tree's feat, so the development-tree admit above is what the role check pins."""
    world.pr_open()
    assert PF.check(world.main, world.main, DEV_BRANCH, "feat(ci): dev", ["f.txt"]) == (True, "")
    monkeypatch.setattr(PF, "landing_branch", lambda _repo: BRANCH)
    assert PF.check(world.main, world.main, DEV_BRANCH, "feat(ci): dev", ["f.txt"])[0] is False


def test_control_a_verdict_that_always_admits_turns_the_feat_case_red(world, monkeypatch):
    """CONTROL: `verdict` replaced with (True, "") admits the feat commit the open landing PR must refuse, so the refusal assertions above are what this suite pins."""
    world.pr_open()
    assert PF.check(world.landing, world.landing, BRANCH, "feat(ci): x", ["f.txt"])[0] is False
    monkeypatch.setattr(PF, "verdict", lambda *_a, **_k: (True, ""))
    assert PF.check(world.landing, world.landing, BRANCH, "feat(ci): x", ["f.txt"])[0] is True


def test_landing_branch_follows_the_record(world):
    assert PF.landing_branch(world.landing) == BRANCH
    assert PF.landing_branch(world.main) == ""
    assert PF.landing_tree(world.landing) == str(world.landing)


def test_verdict_core_names_the_escape():
    ok, reason = PF.verdict("feat(x): y", ["a.py"], {}, {"branch": "b", "pr": 7}, {})
    assert not ok
    assert "landing --promote" in reason
    assert "--phase" not in reason
    assert PF.verdict("feat(x): y", ["a.py"], {}, None, {}) == (True, "")


def test_a_loader_error_fails_open_with_a_note(world, monkeypatch):
    world.pr_open()
    monkeypatch.setattr(
        PF, "record_res", lambda *_a: (_ for _ in ()).throw(OSError("policy unreadable"))
    )
    ok, reason = PF.check(world.landing, world.landing, BRANCH, "feat(x): y", ["a.py"])
    assert ok
    assert "could not judge" in reason


def _githooks():
    spec = importlib.util.spec_from_file_location(
        "githooks_pr_freeze_under_test", HOOKS / "git" / "githooks.py"
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_commit_msg_is_wired_to_the_freeze(world, monkeypatch, capsys):
    """githooks.pr_freeze_refusal refuses what pr_freeze refuses, and skips a lease."""
    gh = _githooks()
    fake = type("F", (), {"check": staticmethod(lambda *_a: (False, "FROZEN-BY-FAKE"))})
    monkeypatch.setattr(gh, "_load", lambda name, _path: fake if name == "pr_freeze" else None)
    assert gh.pr_freeze_refusal("feat(x): y", str(world.landing), BRANCH, ["f.txt"]) != 0
    assert "FROZEN-BY-FAKE" in capsys.readouterr().err
    monkeypatch.setattr(gh.cp, "lease_root", lambda _repo: "/lease")
    assert gh.pr_freeze_refusal("feat(x): y", str(world.landing), BRANCH, ["f.txt"]) == 0, (
        "a lease is judged when its commits land, not here"
    )


def test_a_missing_freeze_module_refuses(monkeypatch, capsys, tmp_path):
    """Review 9188027d.1: a deleted or broken pr_freeze.py must not silently admit every commit."""
    gh = _githooks()

    def missing(_name, path):
        raise FileNotFoundError(path)

    monkeypatch.setattr(gh, "_load", missing)
    monkeypatch.setattr(gh.cp, "lease_root", lambda _repo: "")
    assert gh.pr_freeze_refusal("fix(x): y", str(tmp_path), BRANCH, ["f.txt"]) != 0
    assert "cannot be loaded" in capsys.readouterr().err
    assert (
        gh.pr_freeze_refusal(
            "fix(hooks): restore the freeze", str(tmp_path), BRANCH, [gh.PR_FREEZE_REL]
        )
        == 0
    ), "the commit restoring the module must land (review 7d2c8fca.1)"
    mixed = gh.pr_freeze_refusal(
        "fix(hooks): restore", str(tmp_path), BRANCH, [gh.PR_FREEZE_REL, "src/feature.py"]
    )
    assert mixed != 0, (
        "other files beside the module must not ride the repair path (review 8d45a5c5.1)"
    )
    test_only = gh.pr_freeze_refusal(
        "fix(hooks): test only",
        str(tmp_path),
        BRANCH,
        [".claude/rediacc_hooks/tests/test_githook_pr_freeze.py"],
    )
    assert test_only != 0, "the repair path needs the module itself staged (review 46649b07.1)"


def test_commit_msg_reaches_the_freeze(world, monkeypatch, capsys):
    """Review 9188027d.2: commit_msg itself, not only pr_freeze_refusal, must refuse a frozen commit."""
    world.pr_open()
    repo = world.landing
    gh = _githooks()
    monkeypatch.chdir(repo)
    monkeypatch.setattr(gh, "_repo", lambda: str(repo))
    monkeypatch.setattr(gh, "CONSOLE_ROOT", repo)
    msg = repo / "MSG"
    msg.write_text("chore(ci): through commit_msg\n")
    (repo / "f.txt").write_text("x\n")
    _git(repo, "add", "f.txt")
    assert gh.commit_msg([str(msg)]) != 0
    assert "fix work only" in capsys.readouterr().err
    msg.write_text(
        "fix(ci): through commit_msg\n\nRelease-Note: none -- fixture commit of the freeze test\n"
    )
    assert gh.commit_msg([str(msg)]) == 0, "CONTROL: a fix passes the same path"


def test_an_unreadable_submodule_range_refuses_the_bump():
    """Review a29977aa.1: a range that cannot be read is not an empty range."""
    freeze = {"branch": BRANCH, "pr": 605}
    ok, reason = PF.verdict("chore(sub): bump", ["private/sub"], {"private/sub": None}, freeze, {})
    assert not ok
    assert "unreadable" in reason
    assert PF.verdict("chore(sub): bump", ["private/sub"], {"private/sub": []}, freeze, {})[0], (
        "CONTROL: a readable empty range admits"
    )


def test_a_failed_git_log_reads_as_unreadable(world, tmp_path):
    """Review 9188027d.4: a gitlink whose submodule is not checked out yields None, not an empty list."""
    sub = tmp_path / "sub2"
    subprocess.run(["git", "init", "-q", "-b", BRANCH, str(sub)], check=True)
    _git(sub, *IDENT, "commit", "-q", "--allow-empty", "-m", "fix(x): base")
    sha = _git(sub, "rev-parse", "HEAD").stdout.strip()
    _git(world.landing, "update-index", "--add", "--cacheinfo", "160000,%s,private/ghost" % sha)
    assert PF.gitlink_ranges(world.landing, ["private/ghost"]) == {"private/ghost": None}


def test_a_gitlink_with_an_unreadable_range_is_refused_not_failed_open(world, monkeypatch):
    """3a21f6bd.2: the focus-fix scan skips a None range, so the verdict (which refuses an unreadable range) is reached. A TypeError there would fail the whole check open with a `could not judge` note."""
    world.pr_open()
    repo = world.landing
    monkeypatch.setattr(PF, "gitlink_ranges", lambda *_a: {"private/sub": None})
    monkeypatch.setattr(PF, "gitlink_on_main", lambda *_a: {"private/sub": None})
    ok, reason = PF.check(repo, repo, BRANCH, "chore(sub): bump", ["private/sub"])
    assert ok is False
    assert "could not judge" not in reason
    # Control: a readable range of fixes is admitted by the same path.
    monkeypatch.setattr(PF, "gitlink_ranges", lambda *_a: {"private/sub": ["fix(x): ok"]})
    assert PF.check(repo, repo, BRANCH, "chore(sub): bump", ["private/sub"])[0] is True


def test_a_checked_commit_leaves_no_claude_worklist_directory(world, monkeypatch):
    """3a21f6bd.1: neither the commit-msg hook run nor an in-process check creates `<tmp>/claude-worklist` in a scratch TMPDIR."""
    world.pr_open()
    repo = world.landing
    tmp = world.tmp / "tmp"
    monkeypatch.setattr(tempfile, "tempdir", str(tmp))
    refused = _commit(repo, "feat(ci): frozen", body="focus-fix:#abcdef12")
    assert refused.returncode != 0
    assert PF.check(repo, repo, BRANCH, "feat(ci): frozen", ["f.txt"])[0] is False
    assert isinstance(PF.open_items(repo), dict)
    assert not (tmp / "claude-worklist").exists()
    # Control: the directory is read when it exists, so the guard of that read is not a blanket skip.
    (tmp / "claude-worklist").mkdir()
    assert PF._worklist(types.SimpleNamespace(worklist_for=lambda _r: "real"), repo) == "real"


def test_stop_modules_import_from_the_stop_directory_and_leave_sys_path_as_found(monkeypatch):
    """3a21f6bd.3: with the Stop-hook directory off sys.path and its modules unloaded, `_stop_modules` still imports them (on_sys_path inserted the directory) and removes the entry again."""
    stop = str(PF.STOP_DIR)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p != stop])
    for name in ("wl_core", "wl_store", "wl_review"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    mods = PF._stop_modules()
    assert [m.__name__ for m in mods] == ["wl_core", "wl_store"]
    assert "wl_review" in sys.modules
    assert stop not in sys.path


def _gh_answers(monkeypatch, answers):
    """Plants `subprocess.run` with the scripted (rc, stdout, stderr) answers, one per call, and the nap as a recorder; returns (argv calls, naps)."""
    calls: list = []
    naps: list = []

    def fake_run(argv, **_kw):
        calls.append(argv)
        rc, out, err = answers[min(len(calls), len(answers)) - 1]
        return subprocess.CompletedProcess(argv, rc, out, err)

    monkeypatch.setattr(PF.subprocess, "run", fake_run)
    monkeypatch.setattr(PF.time, "sleep", naps.append)
    return calls, naps


def test_open_pr_retries_a_5xx_once_after_the_two_second_pause(tmp_path, monkeypatch):
    calls, naps = _gh_answers(
        monkeypatch, [(1, "", "gh: Server Error (HTTP 502)"), (0, '[{"number": 7}]', "")]
    )
    assert PF.open_pr(tmp_path, BRANCH) == (7, "")
    assert (len(calls), naps) == (2, [2])


def test_open_pr_answers_a_4xx_at_once_without_a_retry(tmp_path, monkeypatch):
    calls, naps = _gh_answers(monkeypatch, [(1, "", "gh: Not Found (HTTP 404)"), (0, "[]", "")])
    number, why = PF.open_pr(tmp_path, BRANCH)
    assert number is None
    assert "exited 1" in why
    assert (len(calls), naps) == (1, [])


def test_open_pr_reports_a_spawn_failure_at_once_never_as_no_pr(tmp_path, monkeypatch):
    calls: list = []

    def broken(argv, **_kw):
        calls.append(argv)
        raise FileNotFoundError("gh")

    monkeypatch.setattr(PF.subprocess, "run", broken)
    monkeypatch.setattr(PF.time, "sleep", lambda _s: calls.append("nap"))
    number, why = PF.open_pr(tmp_path, BRANCH)
    assert number is None
    assert why.startswith("gh could not run")
    assert len(calls) == 1


def test_open_pr_control_no_open_pr_is_none_with_no_error(tmp_path, monkeypatch):
    _gh_answers(monkeypatch, [(0, "[]", "")])
    assert PF.open_pr(tmp_path, BRANCH) == (None, "")
