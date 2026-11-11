"""`rediacc_ci.dev.backup_ref sync` against a real local bare remote (box G2 of agent/plans/PLAN-local-first-delivery.md).

REAL GIT, NO HOOKS. A work repository on `1104-1` with `gitlab` pointing at a bare repository under tmp_path; `GIT_CONFIG_GLOBAL=/dev/null` keeps this machine's `core.hooksPath` out, so the pushes meet only git. The pre-push rules are `test_githook_backup_ref.py`'s.

EVERY CASE ALSO PROVES THE TWO INVARIANTS: `for-each-ref refs/remotes` is byte-identical before and after (a backup ref in `refs/remotes/*` would read as published to every "is it pushed" check), and no argv the worker ran is a forced shape. The forced-shape checker has its own control below, with a planted `--force` that must be caught, so a checker that never fires cannot pass these cases.
"""

from __future__ import annotations

import datetime
import importlib.util
import io
import os
import pathlib
import subprocess
import sys

import pytest

from rediacc_ci import __main__ as entry
from rediacc_ci.dev import backup_ref as br

ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}
DAY = datetime.datetime(2026, 11, 11, 10, 30, tzinfo=datetime.UTC)


def _git(cwd: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, **ENV},
    ).stdout.strip()


@pytest.fixture
def world(tmp_path, monkeypatch):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(br, "_utcnow", lambda: DAY)
    br.RAN.clear()
    bare = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", str(bare))
    work = tmp_path / "work"
    _git(tmp_path, "init", "-q", "-b", "main", str(work))
    (work / "a").write_text("seed\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "seed")
    _git(work, "remote", "add", "gitlab", str(bare))
    # A remote-tracking ref the worker must leave exactly as it is.
    _git(work, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(work, "checkout", "-q", "-b", "1104-1")
    before = _git(work, "for-each-ref", "refs/remotes")
    yield work, bare
    assert _git(work, "for-each-ref", "refs/remotes") == before
    assert not [argv for argv in br.RAN if br.forced(argv)], br.RAN


def _commit(work: pathlib.Path, msg: str) -> str:
    (work / "a").write_text(msg + "\n", encoding="utf-8")
    _git(work, "commit", "-q", "-am", msg)
    return _git(work, "rev-parse", "HEAD")


def _backup(bare: pathlib.Path) -> dict[str, str]:
    out = _git(bare, "for-each-ref", "--format=%(refname) %(objectname)", "refs/backup/")
    return {
        line.split()[0].removeprefix("refs/backup/1104-1/"): line.split()[1]
        for line in out.splitlines()
    }


def test_two_commits_leave_live_at_the_tip(world):
    work, bare = world
    _commit(work, "one")
    assert br.sync(work) == 0
    tip = _commit(work, "two")
    assert br.sync(work) == 0
    refs = _backup(bare)
    assert refs["live"] == tip
    assert refs["daily-2026-11-11"] != tip  # the day's snapshot stays where the first sync put it
    assert set(refs) == {"live", "daily-2026-11-11"}


def test_an_amend_keeps_the_old_tip_as_pre_rewrite(world):
    work, bare = world
    old = _commit(work, "one")
    assert br.sync(work) == 0
    _git(work, "commit", "-q", "--amend", "-m", "one, reworded")
    new = _git(work, "rev-parse", "HEAD")
    assert br.sync(work) == 0
    refs = _backup(bare)
    assert refs["live"] == new
    assert refs["pre-rewrite-20261111T1030Z"] == old
    assert [
        "push",
        "--atomic",
        "gitlab",
        "%s:refs/backup/1104-1/pre-rewrite-20261111T1030Z" % old,
        ":refs/backup/1104-1/live",
    ] in br.RAN


def test_a_rewrite_whose_old_tip_is_not_here_fetches_it_without_a_remote_ref(world, tmp_path):
    work, bare = world
    other = tmp_path / "other"
    _git(tmp_path, "clone", "-q", str(bare), str(other))
    _git(other, "checkout", "-q", "-b", "1104-1")
    (other / "b").write_text("elsewhere\n", encoding="utf-8")
    _git(other, "add", "-A")
    _git(other, "commit", "-q", "-m", "elsewhere")
    away = _git(other, "rev-parse", "HEAD")
    _git(other, "push", "-q", "origin", "HEAD:refs/backup/1104-1/live")
    tip = _commit(work, "here")
    assert br.sync(work) == 0
    refs = _backup(bare)
    assert refs["pre-rewrite-20261111T1030Z"] == away
    assert refs["live"] == tip
    assert any(argv[:3] == ["fetch", "--no-tags", "--refmap="] for argv in br.RAN)


def test_a_second_same_day_sync_creates_no_second_daily(world):
    work, bare = world
    first = _commit(work, "one")
    assert br.sync(work) == 0
    _commit(work, "two")
    assert br.sync(work) == 0
    assert _backup(bare)["daily-2026-11-11"] == first
    assert [k for k in _backup(bare) if k.startswith("daily-")] == ["daily-2026-11-11"]


def test_the_next_day_adds_its_own_daily(world, monkeypatch):
    work, bare = world
    _commit(work, "one")
    assert br.sync(work) == 0
    monkeypatch.setattr(br, "_utcnow", lambda: DAY + datetime.timedelta(days=1))
    tip = _commit(work, "two")
    assert br.sync(work) == 0
    assert _backup(bare)["daily-2026-11-12"] == tip


def test_an_up_to_date_sync_pushes_nothing(world):
    work, _bare = world
    _commit(work, "one")
    assert br.sync(work) == 0
    br.RAN.clear()
    assert br.sync(work) == 0
    assert not [argv for argv in br.RAN if argv[0] == "push"]


def test_main_and_a_detached_head_are_not_backed_up(world):
    work, bare = world
    _git(work, "checkout", "-q", "main")
    assert br.sync(work) == 0
    _git(work, "checkout", "-q", "--detach")
    assert br.sync(work) == 0
    assert _backup(bare) == {}


def test_a_failed_push_is_logged_and_the_next_sync_catches_up(world):
    work, bare = world
    _git(work, "remote", "set-url", "gitlab", str(bare) + "-missing")
    _commit(work, "one")
    assert br.sync(work) == 1
    log = (
        pathlib.Path(_git(work, "rev-parse", "--absolute-git-dir")) / "rediacc-backup" / "log"
    ).read_text()
    assert "FAILED" in log
    _git(work, "remote", "set-url", "gitlab", str(bare))
    tip = _commit(work, "two")
    assert br.sync(work) == 0
    assert _backup(bare)["live"] == tip


def test_hook_environment_does_not_redirect_the_worker(world, monkeypatch, tmp_path):
    """A git hook exports GIT_DIR and GIT_INDEX_FILE; the worker must still act on the repository it was given."""
    work, bare = world
    tip = _commit(work, "one")
    decoy = tmp_path / "decoy"
    _git(tmp_path, "init", "-q", str(decoy))
    monkeypatch.setenv("GIT_DIR", str(decoy / ".git"))
    monkeypatch.setenv("GIT_INDEX_FILE", str(decoy / ".git" / "index"))
    assert br.sync(work) == 0
    monkeypatch.delenv("GIT_DIR")
    monkeypatch.delenv("GIT_INDEX_FILE")
    assert _backup(bare)["live"] == tip


def test_a_lease_tree_never_pushes(tmp_path):
    tree = tmp_path / "m" / ".claude" / "worktrees" / "x"
    tree.mkdir(parents=True)
    br.RAN.clear()
    assert br.sync(tree) == 0
    assert br.RAN == []


# ------------------------------------------------------------------ the forced-shape checker, and its control


@pytest.mark.parametrize(
    "argv",
    [
        ["push", "--force", "gitlab", "a:b"],
        ["push", "--force-with-lease", "gitlab", "a:b"],
        ["push", "-f", "gitlab", "a:b"],
        ["push", "-qf", "gitlab", "a:b"],
        ["push", "gitlab", "+a:refs/backup/x/live"],
        ["fetch", "gitlab", "+refs/backup/*:refs/backup/*"],
    ],
)
def test_control_a_planted_forced_argv_is_caught_and_refused(argv, tmp_path):
    assert br.forced(argv)
    with pytest.raises(br.ForcedArgvError):
        br._git(tmp_path, argv)


def test_control_a_planted_force_in_the_worker_fails_the_invariant(world, monkeypatch):
    """A worker whose push grows a `--force` is refused before git runs, and the refusal is logged; with the refusal removed, the fixture's no-forced-argv assertion over `RAN` would fail instead."""
    work, _bare = world
    real = br._git

    def planting(repo, argv, check=True):
        if argv and argv[0] == "push":
            argv = [argv[0], "--force", *argv[1:]]
        return real(repo, argv, check)

    monkeypatch.setattr(br, "_git", planting)
    _commit(work, "one")
    assert br.sync(work) == 1  # refused before it ran, and logged as a failure
    assert (
        "forced"
        in (
            pathlib.Path(_git(work, "rev-parse", "--absolute-git-dir")) / "rediacc-backup" / "log"
        ).read_text()
    )


def test_plain_argvs_are_not_forced():
    assert not br.forced(
        ["push", "--atomic", "gitlab", "a:refs/backup/x/live", ":refs/backup/x/live"]
    )
    assert not br.forced(["fetch", "--no-tags", "--refmap=", "gitlab", "refs/backup/x/live"])
    assert not br.forced(["ls-remote", "gitlab", "refs/backup/x/*"])


def test_the_verb_is_registered():
    assert "backup-ref" in entry.names()
    assert br.main(["--help"]) == 0
    assert br.main(["nope"]) == 2


def test_two_rewrites_in_one_minute_keep_both_tips_without_a_move(world):
    """The clock is frozen, so both rewrites carry one minute stamp; the second pre-rewrite ref must take the next free name, since an existing one is create-only (e7710698.1)."""
    work, bare = world
    first = _commit(work, "one")
    assert br.sync(work) == 0
    _git(work, "commit", "-q", "--amend", "-m", "one, rewritten")
    second = _git(work, "rev-parse", "HEAD")
    assert br.sync(work) == 0
    _git(work, "commit", "-q", "--amend", "-m", "one, rewritten again")
    third = _git(work, "rev-parse", "HEAD")
    assert br.sync(work) == 0
    refs = _backup(bare)
    assert refs["pre-rewrite-20261111T1030Z"] == first
    assert refs["pre-rewrite-20261111T1031Z"] == second
    assert refs["live"] == third


def test_a_repository_with_no_remote_is_nothing_to_do_not_a_failure(world):
    """`--all` must not exit nonzero because one listed repository has no `gitlab` remote (e7710698.2)."""
    work, _bare = world
    _commit(work, "one")
    _git(work, "remote", "remove", "gitlab")
    assert br.sync(work) == 0


def test_an_unwritable_state_directory_is_a_logged_failure_not_a_traceback(world, capsys):
    """`state.mkdir` failing returns 1 so a later repository of an `--all` run still syncs (e7710698.3)."""
    work, _bare = world
    _commit(work, "one")
    git_dir = pathlib.Path(_git(work, "rev-parse", "--absolute-git-dir"))
    (git_dir / "rediacc-backup").write_text("in the way\n", encoding="utf-8")
    assert br.sync(work) == 1
    assert "cannot create" in capsys.readouterr().err


# ---- G6: list, restore, prune, status -------------------------------------------------------


def _seed(work: pathlib.Path, *leaves: str) -> str:
    """Creates each `refs/backup/1104-1/<leaf>` on the remote at HEAD, with plain git (no worker)."""
    tip = _git(work, "rev-parse", "HEAD")
    for leaf in leaves:
        _git(work, "push", "-q", "gitlab", "HEAD:refs/backup/1104-1/%s" % leaf)
    return tip


def _heads(work: pathlib.Path) -> str:
    return _git(work, "for-each-ref", "--format=%(refname) %(objectname)", "refs/heads")


def test_list_prints_kind_and_age_per_ref(world, capsys):
    work, _bare = world
    _commit(work, "one")
    _seed(work, "live", "daily-2026-11-01", "pre-rewrite-20261101T0900Z")
    assert br.list_refs(work, "gitlab", sys.stdout) == 0
    rows = {
        line.split("\t")[0]: line.split("\t")[1:] for line in capsys.readouterr().out.splitlines()
    }
    assert rows["1104-1/live"][:2] == ["live", "-"]
    assert rows["1104-1/daily-2026-11-01"][:2] == ["daily", "10d"]
    assert rows["1104-1/pre-rewrite-20261101T0900Z"][:2] == ["pre-rewrite", "10d"]


def test_restore_writes_only_the_restored_namespace(world, capsys):
    work, _bare = world
    old = _commit(work, "one")
    assert br.sync(work) == 0
    _git(work, "commit", "-q", "--amend", "-m", "one, reworded")
    assert br.sync(work) == 0
    heads, remotes = _heads(work), _git(work, "for-each-ref", "refs/remotes")
    before = set(_git(work, "for-each-ref", "--format=%(refname)").splitlines())
    name = "pre-rewrite-20261111T1030Z"
    assert br.restore(work, "gitlab", "1104-1/" + name, sys.stdout) == 0
    out = capsys.readouterr().out
    assert _git(work, "rev-parse", "refs/backup-restored/1104-1/" + name) == old
    assert "git worktree add --detach" in out
    assert out.strip().endswith("refs/backup-restored/1104-1/" + name)
    assert _heads(work) == heads
    assert _git(work, "for-each-ref", "refs/remotes") == remotes
    after = set(_git(work, "for-each-ref", "--format=%(refname)").splitlines())
    assert after - before == {"refs/backup-restored/1104-1/" + name}
    assert before - after == set()


def test_restore_accepts_the_full_ref_and_refuses_a_bare_leaf(world):
    work, _bare = world
    _commit(work, "one")
    assert br.sync(work) == 0
    assert br.restore(work, "gitlab", "refs/backup/1104-1/live", io.StringIO()) == 0
    assert _git(work, "rev-parse", "--verify", "refs/backup-restored/1104-1/live")
    with pytest.raises(br.StepError):
        br.restore(work, "gitlab", "live", io.StringIO())


def test_prune_deletes_past_retention_and_keeps_the_rest(world):
    work, bare = world
    _commit(work, "one")
    keep = ["live", "daily-2026-08-14", "pre-rewrite-20261020T1030Z", "daily-2026-11-11"]
    gone = ["daily-2026-08-12", "pre-rewrite-20261011T1030Z"]  # 91 and 31 days before DAY
    _seed(work, *keep, *gone)
    # The listing is not a deletion.
    assert br.prune(work, "gitlab", False, io.StringIO()) == 0
    assert set(_backup(bare)) == set(keep + gone)
    assert br.prune(work, "gitlab", True, io.StringIO()) == 0
    assert set(_backup(bare)) == set(keep)  # the 89-day daily and the 21-day pre-rewrite stay
    assert br.prune(work, "gitlab", True, io.StringIO()) == 0  # second run: nothing left


def test_prune_never_deletes_live_or_a_name_it_cannot_date(world):
    work, bare = world
    _commit(work, "one")
    _seed(work, "live", "odd-name")
    far = br._utcnow() + datetime.timedelta(days=999)
    assert br.expired(br.all_remote_refs(work, "gitlab"), far) == []
    assert br.prune(work, "gitlab", True, io.StringIO()) == 0
    assert set(_backup(bare)) == {"live", "odd-name"}


def test_prune_boundary_matches_the_hook():
    """Exactly 90 days (a daily) and exactly 30 days (a pre-rewrite) are still inside retention, as in the pre-push hook."""
    rows = [("b", "daily-2026-08-13", "x"), ("b", "pre-rewrite-20261012T0000Z", "x")]
    midnight = DAY.replace(hour=0, minute=0)
    assert br.expired(rows, midnight) == []
    assert br.expired(rows, midnight + datetime.timedelta(days=1)) == rows


def _ahead(work: pathlib.Path, n: int) -> None:
    for i in range(n):
        _git(work, "commit", "-q", "--allow-empty", "-m", "c%d" % i)


def test_status_exits_1_at_51_commits_behind_and_0_at_50(world):
    work, _bare = world
    _commit(work, "one")
    assert br.sync(work) == 0
    _ahead(work, 50)
    out = io.StringIO()
    assert br.status(work, "gitlab", False, out) == 0
    assert "50 commits" in out.getvalue()
    _ahead(work, 1)
    out = io.StringIO()
    assert br.status(work, "gitlab", False, out) == 1
    assert "51 commits" in out.getvalue()
    # The cached form (the Stop hook's) judges the oid the last sync recorded.
    assert br.status(work, "gitlab", True, io.StringIO()) == 1
    assert br.sync(work) == 0
    assert br.status(work, "gitlab", True, io.StringIO()) == 0
    assert br.status(work, "gitlab", False, io.StringIO()) == 0


def test_status_has_nothing_to_judge_on_main_or_without_a_remote(world):
    work, _bare = world
    _ahead(work, 51)
    _git(work, "remote", "remove", "gitlab")
    assert br.status(work, "gitlab", False, io.StringIO()) == 0
    _git(work, "checkout", "-q", "main")
    assert br.status(work, "gitlab", True, io.StringIO()) == 0


def test_main_dispatches_the_new_verbs(world, monkeypatch, capsys):
    work, _bare = world
    _commit(work, "one")
    assert br.sync(work) == 0
    monkeypatch.chdir(work)
    assert br.main(["status"]) == 0
    assert br.main(["prune"]) == 0
    assert br.main(["list"]) == 0
    assert "1104-1/live" in capsys.readouterr().out
    assert br.main(["restore", "nonsense"]) == 1
    assert br.main(["bogus"]) == 2


def test_prune_agrees_with_the_pre_push_hook_on_every_boundary(monkeypatch):
    """Whatever `prune` deletes, `backup_ref_refusal` admits; whatever it keeps inside retention, the hook refuses to delete (so the two never drift)."""
    root = pathlib.Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(
        "githooks_prune_parity", root / ".claude" / "rediacc_hooks" / "git" / "githooks.py"
    )
    assert spec is not None
    assert spec.loader is not None
    gh = importlib.util.module_from_spec(spec)
    sys.modules["githooks_prune_parity"] = gh
    spec.loader.exec_module(gh)
    assert br.RETENTION_DAYS == gh.BACKUP_RETENTION_DAYS
    monkey_now = DAY
    monkeypatch.setattr(gh, "_utcnow", lambda: monkey_now)
    repo = str(pathlib.Path(__file__).resolve().parents[3])
    url = "https://gitlab.rediacc.io" + gh.BACKUP_PATHS[""]
    oid = "a" * 40
    for leaf in (
        "daily-2026-08-12",
        "daily-2026-08-13",
        "daily-2026-08-14",
        "pre-rewrite-20261011T1030Z",
        "pre-rewrite-20261012T1030Z",
        "pre-rewrite-20261020T1030Z",
    ):
        line = ["", gh.cp.ZERO_OID, "refs/backup/1104-1/" + leaf, oid]
        refused = gh.backup_ref_refusal(repo, url, [line])
        pruned = bool(br.expired([("1104-1", leaf, oid)], DAY))
        assert pruned == (refused == ""), (leaf, refused)
