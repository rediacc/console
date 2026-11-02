"""The git-level `pre-push` check of the backup receipt (box J10 of agent/plans/PLAN-backup-program.md): `githooks.backup_receipt_refusal`, called from `githooks.pre_push`.

REAL GIT. Each case builds a console-shaped repository on `1008-1` with nested `private/renet` and `private/account` repos and hand-recorded gitlinks, feeds `pre_push` the stdin lines git would, and reads its exit code and stderr. The receipt is written by `backup_check_trigger.record`, the drill runner's own call, so no shape the module would refuse is planted.

BOTH DIRECTIONS. A backup-path push with no receipt and with a stale-gitlink receipt is refused; its twins (a VERIFIED receipt, a docs-only push, a commit a remote-tracking ref already holds, a delete, a well-formed escape) are admitted.

THE CONTROL. The refused case is run again with `backup_receipt_refusal` replaced by an always-allow stub, and must then pass: a case that passes against a hook that never asks proves nothing about the hook.
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
import types

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
HOOKS = REPO_ROOT / ".claude" / "rediacc_hooks" / "git"
ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}
ZERO = "0" * 40
CONSOLE_FILE = "packages/cli/src/services/backup/backup-schedule.ts"
ESCAPE = (
    "not-runtime: only comments in packages/cli/src/services/backup changed, no runtime code "
    "ASKED:2026-01-01T00:00Z"
)


def _load(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None, path
    assert spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


GH = _load("githooks_backup_receipt_under_test", HOOKS / "githooks.py")
# `syspath.import_from_ci` is the one scoped `.ci` loader the hooks share; it takes `.ci` off sys.path again after the import.
bct = _load(
    "_rediacc_syspath_backup_receipt", REPO_ROOT / ".claude" / "rediacc_hooks" / "syspath.py"
).import_from_ci("rediacc_ci.drills.backup_check_trigger")


def _git(cwd: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
        env={**ENV, "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": "/nonexistent"},
    ).stdout.strip()


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class World:
    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        root.mkdir()
        _git(root, "init", "-q", "-b", "main")
        _write(root, ".gitignore", ".ci/cache/\n")
        _write(root, CONSOLE_FILE, "export const a = 1;\n")
        self.subs = {}
        for sub in (bct.RENET_SUBMODULE, bct.ACCOUNT_SUBMODULE):
            path = root / sub
            path.mkdir(parents=True)
            _git(path, "init", "-q", "-b", "main")
            _write(path, "README.md", "x\n")
            _git(path, "add", "-A")
            _git(path, "commit", "-q", "-m", "seed")
            self.subs[sub] = path
        self.seed = self.commit("seed")
        _git(root, "update-ref", "refs/remotes/origin/main", self.seed)
        _git(root, "checkout", "-q", "-b", "1008-1")

    def commit(self, msg: str) -> str:
        _git(self.root, "add", "-A", "--", ".", ":!private")
        for sub, path in self.subs.items():
            head = _git(path, "rev-parse", "HEAD")
            _git(self.root, "update-index", "--add", "--cacheinfo", "160000,%s,%s" % (head, sub))
        _git(self.root, "commit", "-q", "--allow-empty", "-m", msg)
        return _git(self.root, "rev-parse", "HEAD")

    def record(self) -> None:
        bct.record(
            self.root,
            status=bct.VERIFIED,
            legs=bct.REQUIRED_LEGS,
            onprem=True,
            run_id="t-run",
            started_at="2026-01-01T00:00:00Z",
            finished_at="2026-01-01T00:05:00Z",
        )


def _touched(tmp_path: pathlib.Path) -> tuple[World, str]:
    w = World(tmp_path / "c")
    _write(w.root, CONSOLE_FILE, "export const a = 2;\n")
    return w, w.commit("work")


def _push(monkeypatch, capsys, world: World, tip: str, remote_oid: str = ZERO, ref: str = "1008-1"):
    monkeypatch.chdir(world.root)
    monkeypatch.delenv("COMMIT_POLICY_OK", raising=False)
    line = "refs/heads/%s %s refs/heads/%s %s\n" % (ref, tip, ref, remote_oid)
    rc = GH.pre_push(["origin", "https://github.com/fixture/console.git"], line)
    return rc, capsys.readouterr().err


def test_backup_path_without_a_receipt_is_refused(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(GH.BACKUP_REASON_ENV, raising=False)
    w, tip = _touched(tmp_path)
    rc, err = _push(monkeypatch, capsys, w, tip)
    assert rc == 1
    assert "[no-receipt]" in err
    assert CONSOLE_FILE in err
    assert GH.BACKUP_REASON_ENV in err


def test_control_a_hook_that_never_asks_admits_the_same_push(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(GH.BACKUP_REASON_ENV, raising=False)
    w, tip = _touched(tmp_path)
    monkeypatch.setattr(GH, "backup_receipt_refusal", lambda *_a: "")
    rc, _err = _push(monkeypatch, capsys, w, tip)
    assert rc == 0


def test_a_verified_receipt_admits(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(GH.BACKUP_REASON_ENV, raising=False)
    w, tip = _touched(tmp_path)
    w.record()
    rc, err = _push(monkeypatch, capsys, w, tip)
    assert (rc, err) == (0, "")


def test_a_stale_gitlink_is_refused(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(GH.BACKUP_REASON_ENV, raising=False)
    w, _tip = _touched(tmp_path)
    w.record()
    renet = w.subs[bct.RENET_SUBMODULE]
    _write(renet, "pkg/chunkstore/store.go", "package chunkstore\n")
    _git(renet, "add", "-A")
    _git(renet, "commit", "-q", "-m", "chunkstore")
    tip = w.commit("pointer")
    rc, err = _push(monkeypatch, capsys, w, tip)
    assert rc == 1
    assert "[stale-gitlink]" in err


def test_a_docs_only_push_is_admitted(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(GH.BACKUP_REASON_ENV, raising=False)
    w = World(tmp_path / "c")
    _write(w.root, "docs/x.md", "x\n")
    tip = w.commit("docs")
    assert _push(monkeypatch, capsys, w, tip)[0] == 0


def test_an_already_published_commit_is_not_judged_again(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(GH.BACKUP_REASON_ENV, raising=False)
    w, tip = _touched(tmp_path)
    _git(w.root, "update-ref", "refs/remotes/origin/1008-1", tip)
    assert _push(monkeypatch, capsys, w, tip)[0] == 0


def test_an_update_of_an_existing_branch_diffs_from_its_old_tip(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(GH.BACKUP_REASON_ENV, raising=False)
    w, old = _touched(tmp_path)
    _write(w.root, "docs/x.md", "x\n")
    tip = w.commit("docs after the backup change")
    # The old tip carried the backup change; the range old..tip is docs only.
    assert _push(monkeypatch, capsys, w, tip, remote_oid=old)[0] == 0


def test_a_delete_is_not_judged(tmp_path, monkeypatch):
    monkeypatch.delenv(GH.BACKUP_REASON_ENV, raising=False)
    w, tip = _touched(tmp_path)
    monkeypatch.chdir(w.root)
    line = "(delete) %s refs/heads/1007-1 %s\n" % (ZERO, tip)
    assert GH.pre_push(["origin", "u"], line) == 0


@pytest.mark.parametrize(
    ("reason", "want_rc"),
    [
        (ESCAPE, 0),
        ("not-runtime: short ASKED:2026-01-01T00:00Z", 1),
        (ESCAPE.replace(" ASKED:2026-01-01T00:00Z", ""), 1),
        (ESCAPE.replace("not-runtime", "because"), 1),
    ],
)
def test_the_escape_is_checked_for_shape(tmp_path, monkeypatch, capsys, reason, want_rc):
    w, tip = _touched(tmp_path)
    monkeypatch.setenv(GH.BACKUP_REASON_ENV, reason)
    assert _push(monkeypatch, capsys, w, tip)[0] == want_rc


def _drill(world: World) -> types.SimpleNamespace:
    """The `lib.Drill` facts `backup_check_trigger.record_drill` reads, for a clean, non-empty pass."""
    return types.SimpleNamespace(
        root=world.root, name="backup", selftest=False, count=30, failures=0, started_at=1767225600
    )


def test_the_two_drill_halves_together_admit_and_the_legs_alone_do_not(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.delenv(GH.BACKUP_REASON_ENV, raising=False)
    w, tip = _touched(tmp_path)
    bct.record_drill(_drill(w), bct.LEGS_HALF, 0, bct.REQUIRED_LEGS)
    assert "receipt NOT_VERIFIED" in capsys.readouterr().err
    rc, err = _push(monkeypatch, capsys, w, tip)
    assert rc == 1
    assert "[not-verified]" in err
    assert "legs-partial" in err
    bct.record_drill(_drill(w), bct.ONPREM_HALF, 0)
    assert "receipt VERIFIED" in capsys.readouterr().err
    assert _push(monkeypatch, capsys, w, tip) == (0, "")
