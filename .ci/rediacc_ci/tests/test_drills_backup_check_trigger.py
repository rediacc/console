"""`rediacc_ci.drills.backup_check_trigger`: the backup path tables, the receipt schema, the admission rule and the git-level `check` command (box J4 and J10 of agent/plans/PLAN-backup-program.md).

Fixture repositories are real: a console repo with `private/renet` and `private/account` gitlinks over real nested repos. One test reads the live tree, and only to prove every path-table entry still matches a tracked file (an entry matching nothing is a trigger that can never fire).
"""

from __future__ import annotations

import fnmatch
import pathlib
import subprocess
import sys
import types
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.drills import backup, backup_onprem
from rediacc_ci.drills import backup_check_trigger as bct

if TYPE_CHECKING:
    from collections.abc import Sequence

REPO = pathlib.Path(__file__).resolve().parents[3]
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
CONSOLE_FILE = "packages/cli/src/services/backup/backup-schedule.ts"
RENET_FILE = "pkg/chunkstore/store.go"


def _git(cwd: pathlib.Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True, env=ENV
    ).stdout.strip()


def _write(root: pathlib.Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class World:
    """A console repo on `main` with both submodules as nested repos and their gitlinks recorded by hand; `refs/remotes/origin/main` is the seed."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        root.mkdir()
        _git(root, "init", "-q", "-b", "main")
        _write(root, ".gitignore", ".ci/cache/\n")
        _write(root, "README.md", "x\n")
        _write(root, CONSOLE_FILE, "export const a = 1;\n")
        self.subs = {}
        for sub, seed in (
            (bct.RENET_SUBMODULE, "cmd/renet/other.go"),
            (bct.ACCOUNT_SUBMODULE, "src/index.ts"),
        ):
            path = root / sub
            path.mkdir(parents=True)
            _git(path, "init", "-q", "-b", "main")
            _write(path, seed, "x\n")
            _git(path, "add", "-A")
            _git(path, "commit", "-q", "-m", "seed")
            self.subs[sub] = path
        self.seed = self.commit("seed")
        _git(root, "update-ref", "refs/remotes/origin/main", self.seed)

    def sub_commit(self, sub: str, files: dict[str, str]) -> str:
        path = self.subs[sub]
        for rel, text in files.items():
            _write(path, rel, text)
        _git(path, "add", "-A")
        _git(path, "commit", "-q", "-m", "work")
        return _git(path, "rev-parse", "HEAD")

    def commit(self, msg: str) -> str:
        _git(self.root, "add", "-A", "--", ".", ":!private")
        for sub, path in self.subs.items():
            head = _git(path, "rev-parse", "HEAD")
            _git(self.root, "update-index", "--add", "--cacheinfo", "160000,%s,%s" % (head, sub))
        _git(self.root, "commit", "-q", "--allow-empty", "-m", msg)
        return _git(self.root, "rev-parse", "HEAD")

    def tree(self, rev: str = "HEAD") -> str:
        return _git(self.root, "rev-parse", "%s^{tree}" % rev)


def _record(
    world: World, legs: Sequence[str] = bct.REQUIRED_LEGS, onprem: bool = True
) -> pathlib.Path:
    return bct.record(
        world.root,
        status=bct.VERIFIED,
        legs=legs,
        onprem=onprem,
        run_id="t-run",
        started_at="2026-01-01T00:00:00Z",
        finished_at="2026-01-01T00:05:00Z",
    )


def _admit(world: World, rev: str = "HEAD") -> bct.Verdict:
    tree = world.tree(rev)
    return bct.admit(
        world.root,
        tree,
        bct.inputs_of_tree(world.root, tree),
        bct.pointers_of_tree(world.root, tree),
    )


# --------------------------------------------------------------------------- the path tables


@pytest.mark.parametrize(
    ("hit", "path", "want"),
    [
        (bct.console_hit, "packages/cli/src/commands/backup-ops.ts", True),
        (bct.console_hit, "packages/cli/src/commands/backup.ts", True),
        (bct.console_hit, "packages/cli/src/commands/repo-backup-list.ts", True),
        (bct.console_hit, "packages/cli/src/services/backup/dr-nudge.ts", True),
        (bct.console_hit, ".ci/rediacc_ci/drills/backup.py", True),
        (bct.console_hit, "packages/cli/src/commands/__tests__/backup-storage.test.ts", False),
        (bct.console_hit, "packages/cli/src/commands/repo-create-delete.ts", False),
        (bct.console_hit, ".ci/rediacc_ci/drills/backup_check_trigger.py", False),
        (bct.renet_hit, "cmd/renet/backup_push.go", True),
        (bct.renet_hit, "cmd/renet/backup.go", True),
        (bct.renet_hit, "cmd/renet/datastore_init.go", True),
        (bct.renet_hit, "pkg/chunkstore/toccrypt/toc.go", True),
        (bct.renet_hit, "go.mod", True),
        (bct.renet_hit, "pkg/chunkstore/store_test.go", False),
        (bct.renet_hit, "pkg/license/x.go", False),
        (bct.renet_hit, "cmd/renet/sandbox_exec.go", False),
        (bct.account_hit, "src/services/backup-gc.service.ts", True),
        (bct.account_hit, "src/entry/on-premise.ts", True),
        (bct.account_hit, "drizzle/0049_backup_storage.sql", True),
        (bct.account_hit, "src/routes/licenses.ts", False),
        (bct.account_hit, "tests/integration/backup-lifecycle.test.ts", False),
    ],
)
def test_path_tables_select_backup_code_and_nothing_else(hit, path, want):
    assert hit(path) is want


def _tracked(cwd: pathlib.Path) -> list[str] | None:
    proc = subprocess.run(
        ["git", "-C", str(cwd), "ls-files"], capture_output=True, text=True, check=False
    )
    return proc.stdout.splitlines() if proc.returncode == 0 and proc.stdout else None


def _matches(pattern: str, files: list[str]) -> bool:
    if pattern.endswith("/"):
        return any(f.startswith(pattern) for f in files)
    return any(fnmatch.fnmatchcase(f, pattern) for f in files)


def test_every_console_entry_matches_a_tracked_file():
    """An entry matching no tracked file is a trigger that can never fire, the `scripts/**/*.js` shape."""
    files = _tracked(REPO)
    assert files, "git ls-files returned nothing for the console checkout"
    dead = [p for p in bct.CONSOLE_PATHS if not _matches(p, files)]
    assert not dead, "CONSOLE_PATHS entries matching no tracked file: %s" % dead


@pytest.mark.parametrize(
    ("sub", "table"),
    [
        (bct.RENET_SUBMODULE, bct.RENET_PATHS),
        (bct.ACCOUNT_SUBMODULE, bct.ACCOUNT_PATHS),
    ],
)
def test_every_submodule_entry_matches_a_tracked_file(sub, table):
    files = _tracked(REPO / sub) if (REPO / sub / ".git").exists() else None
    if files is None:
        pytest.skip("%s is not checked out here; its table is judged where it is" % sub)
        return
    dead = [p for p in table if not _matches(p, files)]
    assert not dead, "%s entries matching no tracked file: %s" % (sub, dead)


# --------------------------------------------------------------------------- the range


def test_changed_paths_reads_console_and_submodule_hits(tmp_path):
    w = World(tmp_path / "c")
    _write(w.root, CONSOLE_FILE, "export const a = 2;\n")
    w.sub_commit(bct.RENET_SUBMODULE, {RENET_FILE: "package chunkstore\n", "pkg/x/y.go": "x\n"})
    tip = w.commit("work")
    changed = bct.changed_paths(w.root, w.seed, "push", tip)
    assert changed.hits == (CONSOLE_FILE, "private/renet/%s" % RENET_FILE)
    assert changed.touched


def test_changed_paths_ignores_tests_and_unrelated_files(tmp_path):
    w = World(tmp_path / "c")
    w.sub_commit(bct.RENET_SUBMODULE, {"pkg/chunkstore/store_test.go": "x\n"})
    _write(w.root, "docs/x.md", "x\n")
    tip = w.commit("work")
    assert not bct.changed_paths(w.root, w.seed, "push", tip).touched


def test_changed_paths_names_an_uncomputable_range(tmp_path):
    w = World(tmp_path / "c")
    fake = "0123456789abcdef0123456789abcdef01234567"
    _git(w.root, "update-index", "--cacheinfo", "160000,%s,%s" % (fake, bct.RENET_SUBMODULE))
    _git(w.root, "commit", "-q", "-m", "fake old")
    old = _git(w.root, "rev-parse", "HEAD")
    tip = w.commit("real again")
    changed = bct.changed_paths(w.root, old, "push", tip)
    assert changed.touched
    assert changed.unknown
    assert changed.unknown[0].startswith("private/renet %s" % fake)


# --------------------------------------------------------------------------- the receipt


def test_record_writes_a_verified_receipt_that_admits_its_tree(tmp_path):
    w = World(tmp_path / "c")
    path = _record(w)
    assert path == w.root / bct.CACHE_DIR / bct.LATEST
    assert (w.root / bct.CACHE_DIR / ("%s.json" % w.tree())).is_file()
    verdict = _admit(w)
    assert (verdict.ok, verdict.code) == (True, "ok")


def test_record_downgrades_a_partial_run_to_not_verified(tmp_path):
    w = World(tmp_path / "c")
    _record(w, legs=[leg for leg in bct.REQUIRED_LEGS if leg != "l"])
    latest = bct.read_latest(w.root)
    assert latest is not None
    assert latest["status"] == bct.NOT_VERIFIED
    assert latest["reason"]["class"] == "legs-partial"
    assert "l" in latest["reason"]["detail"]
    assert _admit(w).code == "not-verified"


def test_record_refuses_to_vouch_for_head_after_uncommitted_trigger_edits(tmp_path):
    w = World(tmp_path / "c")
    _write(w.root, CONSOLE_FILE, "an uncommitted change the drill ran\n")
    _record(w)
    latest = bct.read_latest(w.root)
    assert latest is not None
    assert latest["status"] == bct.NOT_VERIFIED
    assert latest["reason"]["class"] == "dirty-inputs"
    assert _admit(w).code == "not-verified"


def test_record_without_the_onprem_variant_is_not_verified(tmp_path):
    w = World(tmp_path / "c")
    _record(w, onprem=False)
    assert _admit(w).code == "not-verified"


def test_validate_refuses_a_verified_receipt_short_of_a_leg(tmp_path):
    w = World(tmp_path / "c")
    _record(w)
    latest = bct.read_latest(w.root)
    assert latest is not None
    latest["legs"] = ["a"]
    assert any("required leg" in e for e in bct.validate(latest))
    with pytest.raises(ValueError, match="required leg"):
        bct.write(w.root, latest)


def test_no_receipt(tmp_path):
    assert _admit(World(tmp_path / "c")).code == "no-receipt"


def test_a_docs_commit_after_the_run_keeps_the_key(tmp_path):
    w = World(tmp_path / "c")
    _record(w)
    _write(w.root, "docs/later.md", "x\n")
    w.commit("docs")
    assert _admit(w).ok


def test_a_console_trigger_edit_after_the_run_is_other_inputs(tmp_path):
    w = World(tmp_path / "c")
    _record(w)
    _write(w.root, CONSOLE_FILE, "export const a = 3;\n")
    w.commit("edit")
    assert _admit(w).code == "other-inputs"


def test_a_renet_move_after_the_run_is_a_stale_gitlink(tmp_path):
    w = World(tmp_path / "c")
    _record(w)
    w.sub_commit(bct.RENET_SUBMODULE, {"README.md": "unrelated\n"})
    w.commit("pointer")
    verdict = _admit(w)
    assert verdict.code == "stale-gitlink"
    assert "private/renet" in verdict.message


def test_an_account_move_after_the_run_is_a_stale_gitlink(tmp_path):
    w = World(tmp_path / "c")
    _record(w)
    w.sub_commit(bct.ACCOUNT_SUBMODULE, {"README.md": "unrelated\n"})
    w.commit("pointer")
    assert _admit(w).code == "stale-gitlink"


def test_a_checkout_off_the_pointer_is_refused(tmp_path):
    w = World(tmp_path / "c")
    w.sub_commit(bct.RENET_SUBMODULE, {"README.md": "ahead\n"})
    # The console still points at the seed renet while the drill ran the newer checkout.
    _record(w)
    assert _admit(w).code == "checkout-mismatch"


def test_a_modified_checkout_is_refused(tmp_path):
    w = World(tmp_path / "c")
    _write(w.subs[bct.RENET_SUBMODULE], RENET_FILE, "package chunkstore // dirty\n")
    _record(w)
    assert _admit(w).code == "modified-checkout"


def test_an_unrelated_dirty_file_in_a_submodule_is_not_modified(tmp_path):
    w = World(tmp_path / "c")
    _write(w.subs[bct.RENET_SUBMODULE], "docs/notes.md", "dirty\n")
    _record(w)
    assert _admit(w).ok


# --------------------------------------------------------------------------- the git-level check


def _cli(world: World, tip: str, base: str = "") -> subprocess.CompletedProcess[str]:
    argv = [
        sys.executable,
        "-m",
        "rediacc_ci.drills.backup_check_trigger",
        "check",
        "--root",
        str(world.root),
        "--tip",
        tip,
    ]
    if base:
        argv += ["--base", base]
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        check=False,
        env={**ENV, "PYTHONPATH": str(REPO / ".ci")},
    )


def test_check_command_untouched_admitted_and_refused(tmp_path):
    w = World(tmp_path / "c")
    _write(w.root, "docs/x.md", "x\n")
    docs = w.commit("docs")
    quiet = _cli(w, docs)
    assert (quiet.returncode, "touches no backup path" in quiet.stdout) == (0, True)

    _write(w.root, CONSOLE_FILE, "export const a = 2;\n")
    tip = w.commit("work")
    refused = _cli(w, tip)
    assert refused.returncode == 1
    assert "[no-receipt]" in refused.stderr
    assert CONSOLE_FILE in refused.stderr

    _record(w)
    admitted = _cli(w, tip)
    assert admitted.returncode == 0, admitted.stderr
    assert "VERIFIED receipt t-run" in admitted.stdout


def test_check_command_with_no_base_is_unjudged(tmp_path):
    w = World(tmp_path / "c")
    _git(w.root, "update-ref", "-d", "refs/remotes/origin/main")
    done = _cli(w, "HEAD")
    assert done.returncode == 2
    assert "cannot be judged" in done.stderr


# --------------------------------------------------------------------------- the drill runners' call


def _drill(world: World, *, count: int = 30, failures: int = 0, selftest: bool = False):
    """The four `lib.Drill` facts `record_drill` reads, over the fixture world."""
    return types.SimpleNamespace(
        root=world.root,
        name="backup",
        selftest=selftest,
        count=count,
        failures=failures,
        started_at=1767225600,
    )


def _latest(world: World) -> dict:
    latest = bct.read_latest(world.root)
    assert latest is not None
    return latest


def test_a_passing_legs_run_and_a_passing_onprem_run_write_one_verified_receipt(tmp_path):
    w = World(tmp_path / "c")
    path = bct.record_drill(_drill(w), bct.LEGS_HALF, 0, bct.REQUIRED_LEGS)
    assert path == w.root / bct.CACHE_DIR / bct.LATEST
    half = _latest(w)
    assert (half["status"], half["reason"]["class"], half["onprem"]) == (
        bct.NOT_VERIFIED,
        "legs-partial",
        False,
    )
    assert _admit(w).code == "not-verified"

    bct.record_drill(_drill(w), bct.ONPREM_HALF, 0)
    whole = _latest(w)
    assert (whole["status"], whole["onprem"], whole["legs"]) == (
        bct.VERIFIED,
        True,
        sorted(bct.REQUIRED_LEGS),
    )
    assert whole["tree"] == w.tree()
    assert _admit(w).ok


def test_the_halves_combine_in_either_order(tmp_path):
    w = World(tmp_path / "c")
    bct.record_drill(_drill(w), bct.ONPREM_HALF, 0)
    assert _latest(w)["reason"]["class"] == "legs-partial"
    bct.record_drill(_drill(w), bct.LEGS_HALF, 0, bct.REQUIRED_LEGS)
    assert _admit(w).ok


def test_a_legs_subset_never_completes_the_receipt(tmp_path):
    w = World(tmp_path / "c")
    bct.record_drill(_drill(w), bct.ONPREM_HALF, 0)
    bct.record_drill(_drill(w), bct.LEGS_HALF, 0, ["a", "g"])
    latest = _latest(w)
    assert latest["status"] == bct.NOT_VERIFIED
    assert "l" in latest["reason"]["detail"]
    assert _admit(w).code == "not-verified"


def test_a_failed_rerun_withdraws_its_half_and_keeps_the_other(tmp_path):
    w = World(tmp_path / "c")
    bct.record_drill(_drill(w), bct.LEGS_HALF, 0, bct.REQUIRED_LEGS)
    bct.record_drill(_drill(w), bct.ONPREM_HALF, 0)
    assert _admit(w).ok

    bct.record_drill(_drill(w, failures=2), bct.ONPREM_HALF, 1)
    failed = _latest(w)
    assert (failed["status"], failed["reason"]["class"], failed["onprem"]) == (
        bct.FAILED,
        "assertions-failed",
        False,
    )
    assert failed["legs"] == sorted(bct.REQUIRED_LEGS)
    assert _admit(w).code == "failed"

    bct.record_drill(_drill(w), bct.ONPREM_HALF, 0)
    assert _admit(w).ok


def test_a_half_from_another_tree_is_never_carried(tmp_path):
    w = World(tmp_path / "c")
    bct.record_drill(_drill(w), bct.LEGS_HALF, 0, bct.REQUIRED_LEGS)
    _write(w.root, CONSOLE_FILE, "export const a = 4;\n")
    w.commit("edit after the legs run")
    bct.record_drill(_drill(w), bct.ONPREM_HALF, 0)
    latest = _latest(w)
    assert (latest["status"], latest["legs"]) == (bct.NOT_VERIFIED, [])
    assert _admit(w).code == "not-verified"


def test_a_half_from_another_renet_checkout_is_never_carried(tmp_path):
    w = World(tmp_path / "c")
    bct.record_drill(_drill(w), bct.LEGS_HALF, 0, bct.REQUIRED_LEGS)
    # The same console tree, but renet moved under it between the two runs.
    w.sub_commit(bct.RENET_SUBMODULE, {RENET_FILE: "package chunkstore\n"})
    bct.record_drill(_drill(w), bct.ONPREM_HALF, 0)
    assert _latest(w)["legs"] == []


def test_legs_run_over_uncommitted_edits_are_never_carried(tmp_path):
    w = World(tmp_path / "c")
    _write(w.root, CONSOLE_FILE, "an uncommitted change the legs ran\n")
    bct.record_drill(_drill(w), bct.LEGS_HALF, 0, bct.REQUIRED_LEGS)
    dirty = _latest(w)
    assert dirty["legs"] == sorted(bct.REQUIRED_LEGS)
    assert dirty["inputs"] != bct.inputs_of_tree(w.root, w.tree())
    # The edit is reverted, so the tree is clean again, but those legs ran other code.
    _write(w.root, CONSOLE_FILE, "export const a = 1;\n")
    bct.record_drill(_drill(w), bct.ONPREM_HALF, 0)
    assert _latest(w)["legs"] == []
    assert _admit(w).code == "not-verified"


def test_a_stale_verified_receipt_refuses_the_next_backup_change(tmp_path):
    w = World(tmp_path / "c")
    bct.record_drill(_drill(w), bct.LEGS_HALF, 0, bct.REQUIRED_LEGS)
    bct.record_drill(_drill(w), bct.ONPREM_HALF, 0)
    assert _admit(w).ok
    _write(w.root, CONSOLE_FILE, "export const a = 5;\n")
    w.commit("a backup change after the drills")
    assert _admit(w).code == "other-inputs"
    w.sub_commit(bct.RENET_SUBMODULE, {RENET_FILE: "package chunkstore\n"})
    w.commit("and a renet move")
    assert _admit(w).code == "stale-gitlink"


@pytest.mark.parametrize(
    ("rc", "count", "failures", "status", "klass"),
    [
        (0, 30, 0, bct.VERIFIED, None),
        (1, 30, 2, bct.FAILED, "assertions-failed"),
        (0, 0, 0, bct.NOT_VERIFIED, "skipped"),
        (1, 0, 0, bct.NOT_VERIFIED, "drill-unavailable"),
    ],
)
def test_drill_outcome_maps_every_exit(rc, count, failures, status, klass):
    got, reason = bct.drill_outcome(rc=rc, count=count, failures=failures)
    assert got == status
    assert (reason or {}).get("class") == klass


def test_a_selftest_run_records_nothing(tmp_path):
    w = World(tmp_path / "c")
    assert bct.record_drill(_drill(w, selftest=True), bct.LEGS_HALF, 1, bct.REQUIRED_LEGS) is None
    assert bct.read_latest(w.root) is None


def test_record_half_refuses_an_unknown_half(tmp_path):
    w = World(tmp_path / "c")
    with pytest.raises(ValueError, match="half"):
        bct.record_half(
            w.root, half="both", status=bct.VERIFIED, run_id="r", started_at="", finished_at=""
        )


def _passing_run_all(self) -> int:
    self.d.assert_equal("1", "1", "a fixture assertion")
    return self.d.summary()


def test_the_backup_runner_records_the_legs_half_it_ran(monkeypatch):
    calls = []
    monkeypatch.setattr(backup.Backup, "run_all", _passing_run_all)
    monkeypatch.setattr(backup.Backup, "teardown_hook", lambda _self: None)
    monkeypatch.setattr(
        bct, "record_drill", lambda _drill, half, rc, legs=(): calls.append((half, rc, list(legs)))
    )
    assert backup.main(["--legs", "a,g"]) == 0
    assert calls == [(bct.LEGS_HALF, 0, ["a", "g"])]


def test_the_onprem_runner_records_the_onprem_half(monkeypatch):
    calls = []
    monkeypatch.setattr(
        backup_onprem.OnPrem, "__init__", lambda self, drill: setattr(self, "d", drill)
    )
    monkeypatch.setattr(backup_onprem.OnPrem, "run_all", _passing_run_all)
    monkeypatch.setattr(
        bct, "record_drill", lambda _drill, half, rc, legs=(): calls.append((half, rc, list(legs)))
    )
    assert backup_onprem.main([]) == 0
    assert calls == [(bct.ONPREM_HALF, 0, [])]
