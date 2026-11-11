"""The backup refs at the git layer (Design G of agent/plans/PLAN-local-first-delivery.md): `githooks.backup_push` and its parts, called from `githooks.pre_push` (box G1).

REAL GIT. Each case builds a throwaway console repository on `1104-1` with `origin/main` at the seed, feeds `pre_push` the stdin lines git would, and reads its exit code and stderr. Secret shapes and session trailers are assembled at run time, so this file carries none of them.

BOTH DIRECTIONS, AND A CONTROL PER REFUSAL CLASS. The admitted shapes (a live create or fast-forward, the pre-rewrite pair, a daily create, a past-retention delete) sit beside their refused twins (non-fast-forward, a daily move, an in-retention delete, another remote, a mixed push, a session link, a secret). `refs/backup/x` to `origin` is also run with the backup dispatch switched off, which is today's hook, and must then pass: the refusal is the change, not the fixture. The incremental scan is proven by the same leaky range refused from a zero old oid and admitted from the old live tip.
"""

from __future__ import annotations

import datetime
import importlib.util
import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
HOOKS = REPO_ROOT / ".claude" / "rediacc_hooks" / "git"
ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "PATH": "/usr/bin:/bin:/usr/local/bin",
    "HOME": "/nonexistent",
}
ZERO = "0" * 40
CONSOLE_URL = "https://gitlab.rediacc.io/rediacc-org/github/console.git"
RENET_URL = "https://gitlab.rediacc.io/rediacc-org/github/renet.git"
ORIGIN_URL = "https://github.com/fixture/console.git"
LIVE = "refs/backup/1104-1/live"
# Assembled, never literal: this file is itself pushed through the scans it tests.
SECRET = "gh" + "p_" + "Q7" * 18
SESSION_LINE = "Claude" + "-Session: fixture"


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None, path
    assert spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


GH = _load("githooks_backup_ref_under_test", HOOKS / "githooks.py")


def _git(cwd: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True, env=ENV
    ).stdout.strip()


class World:
    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        root.mkdir(parents=True)
        _git(root, "init", "-q", "-b", "main")
        self.seed = self.commit("seed", "README.md", "seed\n")
        _git(root, "update-ref", "refs/remotes/origin/main", self.seed)
        _git(root, "checkout", "-q", "-b", "1104-1")

    def commit(self, msg: str, rel: str = "notes.txt", text: str | None = None) -> str:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text if text is not None else msg + "\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-q", "-m", msg)
        return _git(self.root, "rev-parse", "HEAD")


def _push(
    monkeypatch,
    capsys,
    cwd: pathlib.Path,
    lines: list[tuple[str, str, str]],
    url=CONSOLE_URL,
    remote="gitlab",
):
    """`lines` are `(new, remote_ref, old)`; the local ref is the commit itself, as `git push gitlab <sha>:<ref>` sends it."""
    monkeypatch.chdir(cwd)
    monkeypatch.delenv("COMMIT_POLICY_OK", raising=False)
    stdin = "".join(
        "%s %s %s %s\n" % (new if new != ZERO else "(delete)", new, ref, old)
        for new, ref, old in lines
    )
    rc = GH.pre_push([remote, url], stdin)
    return rc, capsys.readouterr().err


def _two(tmp_path) -> tuple[World, str, str]:
    w = World(tmp_path / "c")
    return w, w.commit("one"), w.commit("two")


# ------------------------------------------------------------------ live


def test_live_create_and_fast_forward_are_admitted(tmp_path, monkeypatch, capsys):
    w, one, two = _two(tmp_path)
    assert _push(monkeypatch, capsys, w.root, [(one, LIVE, ZERO)])[0] == 0
    rc, err = _push(monkeypatch, capsys, w.root, [(two, LIVE, one)])
    assert rc == 0, err


def test_live_non_fast_forward_is_refused(tmp_path, monkeypatch, capsys):
    w, one, _ = _two(tmp_path)
    _git(w.root, "reset", "-q", "--hard", w.seed)
    other = w.commit("beside")
    rc, err = _push(monkeypatch, capsys, w.root, [(other, LIVE, one)])
    assert rc == 1
    assert "no fast-forward" in err


def test_pre_rewrite_pair_is_admitted(tmp_path, monkeypatch, capsys):
    w, _, two = _two(tmp_path)
    pre = "refs/backup/1104-1/pre-rewrite-20261111T1200Z"
    rc, err = _push(monkeypatch, capsys, w.root, [(two, pre, ZERO), (ZERO, LIVE, two)])
    assert rc == 0, err


def test_live_delete_without_pre_rewrite_at_the_old_tip_is_refused(tmp_path, monkeypatch, capsys):
    w, one, two = _two(tmp_path)
    rc, err = _push(monkeypatch, capsys, w.root, [(ZERO, LIVE, two)])
    assert rc == 1
    assert "pre-rewrite" in err
    # A pre-rewrite at ANOTHER oid does not license the delete.
    pre = "refs/backup/1104-1/pre-rewrite-20261111T1200Z"
    rc, err = _push(monkeypatch, capsys, w.root, [(one, pre, ZERO), (ZERO, LIVE, two)])
    assert rc == 1


# ------------------------------------------------------------------ snapshots


def test_daily_create_is_admitted_and_a_move_refused(tmp_path, monkeypatch, capsys):
    w, one, two = _two(tmp_path)
    daily = "refs/backup/1104-1/daily-2026-11-11"
    assert _push(monkeypatch, capsys, w.root, [(one, daily, ZERO)])[0] == 0
    rc, err = _push(monkeypatch, capsys, w.root, [(two, daily, one)])
    assert rc == 1
    assert "never moved" in err


def test_snapshot_delete_follows_retention(tmp_path, monkeypatch, capsys):
    w, one, _ = _two(tmp_path)
    now = datetime.datetime(2026, 11, 11, 12, 0, tzinfo=datetime.UTC)
    monkeypatch.setattr(GH, "_utcnow", lambda: now)

    def day(n: int) -> str:
        return "refs/backup/1104-1/daily-%s" % (now - datetime.timedelta(days=n)).strftime(
            "%Y-%m-%d"
        )

    def pre(n: int) -> str:
        return "refs/backup/1104-1/pre-rewrite-%s" % (now - datetime.timedelta(days=n)).strftime(
            "%Y%m%dT%H%MZ"
        )

    rc, err = _push(monkeypatch, capsys, w.root, [(ZERO, day(89), one)])
    assert rc == 1
    assert "retention" in err
    assert _push(monkeypatch, capsys, w.root, [(ZERO, day(91), one)])[0] == 0
    assert _push(monkeypatch, capsys, w.root, [(ZERO, pre(29), one)])[0] == 1
    assert _push(monkeypatch, capsys, w.root, [(ZERO, pre(31), one)])[0] == 0


def test_unknown_leaf_is_refused(tmp_path, monkeypatch, capsys):
    w, one, _ = _two(tmp_path)
    assert _push(monkeypatch, capsys, w.root, [(one, "refs/backup/1104-1/other", ZERO)])[0] == 1
    assert _push(monkeypatch, capsys, w.root, [(one, "refs/backup/x", ZERO)])[0] == 1


# ------------------------------------------------------------------ where and with what


def test_backup_ref_to_origin_is_refused(tmp_path, monkeypatch, capsys):
    w, one, _ = _two(tmp_path)
    rc, err = _push(
        monkeypatch, capsys, w.root, [(one, "refs/backup/x", ZERO)], url=ORIGIN_URL, remote="origin"
    )
    assert rc == 1
    assert "pinned backup project" in err


def test_control_todays_hook_admits_a_backup_ref_to_origin(tmp_path, monkeypatch, capsys):
    w, one, _ = _two(tmp_path)
    monkeypatch.setattr(GH, "is_backup_push", lambda _lines: False)
    rc, _err = _push(
        monkeypatch, capsys, w.root, [(one, "refs/backup/x", ZERO)], url=ORIGIN_URL, remote="origin"
    )
    assert rc == 0


def test_a_mixed_push_is_refused(tmp_path, monkeypatch, capsys):
    w, one, _ = _two(tmp_path)
    rc, err = _push(monkeypatch, capsys, w.root, [(one, LIVE, ZERO), (one, "refs/heads/x", ZERO)])
    assert rc == 1
    assert "carries no other ref" in err
    assert "refs/heads/x" in err


def test_a_lookalike_url_is_refused(tmp_path, monkeypatch, capsys):
    w, one, _ = _two(tmp_path)
    rc, _err = _push(monkeypatch, capsys, w.root, [(one, LIVE, ZERO)], url=RENET_URL)
    assert rc == 1
    rc, _err = _push(
        monkeypatch, capsys, w.root, [(one, LIVE, ZERO)], url=str(tmp_path / "bare.git")
    )
    assert rc == 1


def test_a_submodule_pushes_only_to_its_own_pin(tmp_path, monkeypatch, capsys):
    w = World(tmp_path / "c")
    sub = w.root / "private" / "renet"
    sub.mkdir(parents=True)
    _git(sub, "init", "-q", "-b", "main")
    (sub / "f").write_text("x\n", encoding="utf-8")
    _git(sub, "add", "-A")
    _git(sub, "commit", "-q", "-m", "seed")
    head = _git(sub, "rev-parse", "HEAD")
    _git(w.root, "update-index", "--add", "--cacheinfo", "160000,%s,private/renet" % head)
    _git(w.root, "commit", "-q", "-m", "pin")
    assert GH.backup_repo_key(str(sub)) == "private/renet"
    rc, err = _push(monkeypatch, capsys, sub, [(head, LIVE, ZERO)], url=RENET_URL)
    assert rc == 0, err
    assert _push(monkeypatch, capsys, sub, [(head, LIVE, ZERO)], url=CONSOLE_URL)[0] == 1


# ------------------------------------------------------------------ the scans


def test_session_link_in_the_new_range_is_refused(tmp_path, monkeypatch, capsys):
    w = World(tmp_path / "c")
    tip = w.commit("work\n\n" + SESSION_LINE)
    rc, err = _push(monkeypatch, capsys, w.root, [(tip, LIVE, ZERO)])
    assert rc == 1
    assert "session link" in err


def test_secret_shape_in_the_new_range_is_refused_by_shape_not_value(tmp_path, monkeypatch, capsys):
    w = World(tmp_path / "c")
    tip = w.commit("add config", "cfg.txt", "token=%s\n" % SECRET)
    rc, err = _push(monkeypatch, capsys, w.root, [(tip, LIVE, ZERO)])
    assert rc == 1
    assert "secret shape" in err
    assert tip[:12] in err
    assert SECRET not in err


def test_a_removed_secret_line_is_not_an_added_one(tmp_path, monkeypatch, capsys):
    w = World(tmp_path / "c")
    leaked = w.commit("add", "cfg.txt", "token=%s\n" % SECRET)
    _git(w.root, "update-ref", "refs/remotes/origin/main", leaked)
    tip = w.commit("drop", "cfg.txt", "token=\n")
    rc, err = _push(monkeypatch, capsys, w.root, [(tip, LIVE, ZERO)])
    assert rc == 0, err


def test_a_second_sync_scans_only_commits_after_the_remote_old_tip(tmp_path, monkeypatch, capsys):
    w = World(tmp_path / "c")
    leaky = w.commit("work\n\n" + SESSION_LINE, "cfg.txt", "token=%s\n" % SECRET)
    tip = w.commit("clean")
    # Control: from a zero old oid the range holds the leaky commit and is refused.
    assert _push(monkeypatch, capsys, w.root, [(tip, LIVE, ZERO)])[0] == 1
    # From the old live tip the leaky commit is history the remote already holds.
    rc, err = _push(monkeypatch, capsys, w.root, [(tip, LIVE, leaky)])
    assert rc == 0, err


def test_the_scan_excludes_each_old_tip_and_never_a_remote_tracking_backup_ref(tmp_path):
    w, one, two = _two(tmp_path)
    assert GH.backup_exclusions(str(w.root), [[two, two, LIVE, one], ["x", ZERO, LIVE, ZERO]]) == [
        one
    ]
    assert GH.backup_exclusions(str(w.root), [[two, two, LIVE, "f" * 40]]) == []


def test_the_branch_rules_still_judge_a_heads_push(tmp_path, monkeypatch, capsys):
    """A plain branch push to origin never enters the backup path: creating a non-current remote branch is still refused."""
    w, one, _ = _two(tmp_path)
    rc, err = _push(
        monkeypatch,
        capsys,
        w.root,
        [(one, "refs/heads/9999-9", ZERO)],
        url=ORIGIN_URL,
        remote="origin",
    )
    assert rc == 1
    assert "creates the remote branch" in err
