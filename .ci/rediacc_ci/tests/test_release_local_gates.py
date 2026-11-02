"""`rediacc_ci.release.local_gates`: every gate of a local release, against real temporary git repositories.

The ci:quick worlds are the push guard's own `FIXTURES`, so the receipt shapes judged here are the ones the guard's goldens freeze. The vm:check receipts come from the receipt module's test builder. The network and R2 readers are injected; git is real throughout.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci.release import local_gates as lg
from rediacc_ci.tests.test_proof_vm_tier import make as vm_receipt
from rediacc_ci.tests.test_proof_vm_tier import not_verified as vm_not_verified

if TYPE_CHECKING:
    import pathlib

GUARD = lg._push_guard()
SUB_FILE = "sub.txt"


def _env() -> dict[str, str]:
    return dict(
        os.environ,
        GIT_AUTHOR_NAME="Fixture",
        GIT_AUTHOR_EMAIL="fixture@example.invalid",
        GIT_COMMITTER_NAME="Fixture",
        GIT_COMMITTER_EMAIL="fixture@example.invalid",
        GIT_CONFIG_NOSYSTEM="1",
    )


def git(cwd: pathlib.Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-c", "protocol.file.allow=always", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env=_env(),
    )
    return proc.stdout.strip()


@pytest.fixture(autouse=True)
def isolated_git(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """A global git config of the test's own, so the host's config never reaches the clone gate."""
    config = tmp_path / "gitconfig"
    config.write_text("[init]\n\tdefaultBranch = main\n", encoding="utf-8")
    for key, value in _env().items():
        if key.startswith("GIT_"):
            monkeypatch.setenv(key, value)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    return config


def commit_all(repo: pathlib.Path, message: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def tree_of(repo: pathlib.Path) -> str:
    return git(repo, "rev-parse", "HEAD^{tree}")


def head_of(repo: pathlib.Path) -> str:
    return git(repo, "rev-parse", "HEAD")


def tagged_repo(tmp_path: pathlib.Path, after: dict[str, str] | None = None) -> pathlib.Path:
    """A repository tagged v1.0.0, then one commit writing `after` (path -> text)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "--initial-branch=main")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    commit_all(repo, "seed")
    git(repo, "tag", "v1.0.0")
    for rel, text in (after or {"notes.txt": "a later commit outside every trigger\n"}).items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    commit_all(repo, "after the tag")
    return repo


def with_submodule(tmp_path: pathlib.Path) -> pathlib.Path:
    """A repository with one submodule, `private/sub`, checked out at its pointer."""
    src = tmp_path / "subsrc"
    src.mkdir()
    git(src, "init", "-q", "--initial-branch=main")
    (src / SUB_FILE).write_text("sub\n", encoding="utf-8")
    commit_all(src, "sub seed")
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "--initial-branch=main")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    git(repo, "submodule", "add", "-q", str(src), "private/sub")
    commit_all(repo, "seed with a submodule")
    return repo


# --------------------------------------------------------------------------- (a) ci:quick


def guard_world(tmp_path: pathlib.Path, name: str) -> pathlib.Path:
    return GUARD.FIXTURES[name](tmp_path / name)


def test_ci_quick_admits_the_green_receipt(tmp_path: pathlib.Path) -> None:
    root = guard_world(tmp_path, "push-green")
    assert lg.ci_quick_refusal(root, tree_of(root)) is None


def test_ci_quick_no_receipt_refuses(tmp_path: pathlib.Path) -> None:
    root = guard_world(tmp_path, "push-no-receipt")
    got = lg.ci_quick_refusal(root, tree_of(root))
    assert got is not None
    assert got.code == "ci-quick"
    assert GUARD.NO_RECEIPT in got.message


def test_ci_quick_a_receipt_of_another_tree_refuses(tmp_path: pathlib.Path) -> None:
    root = guard_world(tmp_path, "push-wrong-tree")
    got = lg.ci_quick_refusal(root, tree_of(root))
    assert got is not None
    assert "different tree" in got.message


def test_ci_quick_prefers_the_per_tree_copy(tmp_path: pathlib.Path) -> None:
    root = guard_world(tmp_path, "push-wrong-tree")
    tree = tree_of(root)
    green = GUARD._v2_body({"headTree": tree, "whole": True, "exitCode": 0, "droppedTouched": []})
    archive = root / GUARD.RECEIPT_ARCHIVE_REL
    archive.mkdir(parents=True, exist_ok=True)
    (archive / ("%s.json" % tree)).write_text(json.dumps(green), encoding="utf-8")
    assert lg.ci_quick_refusal(root, tree) is None


def test_ci_quick_a_narrowed_run_refuses(tmp_path: pathlib.Path) -> None:
    root = guard_world(tmp_path, "push-narrowed")
    got = lg.ci_quick_refusal(root, tree_of(root))
    assert got is not None
    assert "NARROWED" in got.message


def test_ci_quick_a_red_receipt_not_carried_refuses(tmp_path: pathlib.Path) -> None:
    root = guard_world(tmp_path, "push-red-unnamed")
    got = lg.ci_quick_refusal(root, tree_of(root))
    assert got is not None
    assert "check:format" in got.message


def test_ci_quick_a_dropped_gate_not_verified_refuses(tmp_path: pathlib.Path) -> None:
    root = guard_world(tmp_path, "push-dropped-unverified")
    got = lg.ci_quick_refusal(root, tree_of(root))
    assert got is not None
    assert "check:ci-plan-record" in got.message


# --------------------------------------------------------------------------- (b) vm:check


TRIGGER = ".ci/rediacc_ci/drills/lib.py"
ACCOUNT_TRIGGER = ".ci/rediacc_ci/drills/license.py"


def write_vm_receipt(root: pathlib.Path, receipt: dict[str, Any]) -> None:
    folder = root / ".ci" / "cache" / "vm-check"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")


def test_vm_check_hits_without_a_receipt_refuse(tmp_path: pathlib.Path) -> None:
    root = tagged_repo(tmp_path, {TRIGGER: "x = 1\n"})
    got = lg.vm_check_refusal(root, tree_of(root), "v1.0.0")
    assert got is not None
    assert got.code == "vm-check"
    assert "[no-receipt]" in got.message
    assert TRIGGER in got.message
    assert "--base v1.0.0" in got.message


def test_vm_check_a_not_verified_receipt_refuses(tmp_path: pathlib.Path) -> None:
    root = tagged_repo(tmp_path, {TRIGGER: "x = 1\n"})
    write_vm_receipt(root, vm_not_verified(tree=tree_of(root)))
    got = lg.vm_check_refusal(root, tree_of(root), "v1.0.0")
    assert got is not None
    assert "[not-verified]" in got.message


def test_vm_check_an_account_mismatch_refuses(tmp_path: pathlib.Path) -> None:
    root = tagged_repo(tmp_path, {ACCOUNT_TRIGGER: "x = 1\n"})
    receipt = vm_receipt(
        tree=tree_of(root),
        phases={
            "renet": {"required": False, "ran": False},
            "account": {"required": True, "ran": True},
        },
    )
    receipt["submodules"]["private/account"]["checkout"] = "8" * 40
    write_vm_receipt(root, receipt)
    got = lg.vm_check_refusal(root, tree_of(root), "v1.0.0")
    assert got is not None
    assert "[checkout-mismatch]" in got.message


def test_vm_check_a_verified_receipt_admits(tmp_path: pathlib.Path) -> None:
    root = tagged_repo(tmp_path, {TRIGGER: "x = 1\n"})
    receipt = vm_receipt(
        tree=tree_of(root),
        phases={
            "renet": {"required": True, "ran": True},
            "account": {"required": True, "ran": True},
        },
    )
    write_vm_receipt(root, receipt)
    assert lg.vm_check_refusal(root, tree_of(root), "v1.0.0") is None


def test_vm_check_no_hits_is_not_required(tmp_path: pathlib.Path) -> None:
    root = tagged_repo(tmp_path)
    assert lg.vm_check_refusal(root, tree_of(root), "v1.0.0") is None


def test_backup_untouched_is_not_required(tmp_path: pathlib.Path) -> None:
    root = tagged_repo(tmp_path)
    assert lg.backup_refusal(root, "v1.0.0") is None


def test_the_previous_tag_is_the_newest_reachable_one(tmp_path: pathlib.Path) -> None:
    root = tagged_repo(tmp_path)
    git(root, "tag", "v1.0.1")
    git(root, "checkout", "-q", "v1.0.0")
    assert lg.previous_tag(root) == "v1.0.0"


def test_the_previous_tag_is_the_highest_version_not_the_nearest(tmp_path: pathlib.Path) -> None:
    """A lower tag on a merged side branch is nearer by commit distance, so `git describe` would answer it; the range starts at the real previous release."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "--initial-branch=main")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    commit_all(repo, "seed")
    git(repo, "branch", "side")
    (repo / "main.txt").write_text("release\n", encoding="utf-8")
    commit_all(repo, "release")
    git(repo, "tag", "v1.0.0")
    for n in range(5):
        (repo / "main.txt").write_text("main %d\n" % n, encoding="utf-8")
        commit_all(repo, "main %d" % n)
    git(repo, "checkout", "-q", "side")
    (repo / "side.txt").write_text("side\n", encoding="utf-8")
    commit_all(repo, "side")
    git(repo, "tag", "v0.9.9")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "-m", "merge side", "side")
    assert git(repo, "describe", "--tags", "--abbrev=0", "--match", "v*", "HEAD") == "v0.9.9"
    assert lg.previous_tag(repo) == "v1.0.0"


def test_no_reachable_tag_is_none(tmp_path: pathlib.Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "--initial-branch=main")
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    commit_all(repo, "seed")
    assert lg.previous_tag(repo) is None


# --------------------------------------------------------------------------- (d) the release clone


def test_a_clean_clone_with_its_submodule_admits(tmp_path: pathlib.Path) -> None:
    root = with_submodule(tmp_path)
    tree = tree_of(root)
    assert lg.clone_refusal(root, tree, head_of(root)) is None
    clone = root / lg.CLONE_REL / tree
    assert (clone / "private" / "sub" / SUB_FILE).read_text(encoding="utf-8") == "sub\n"


def test_the_clone_is_taken_afresh(tmp_path: pathlib.Path) -> None:
    root = with_submodule(tmp_path)
    tree = tree_of(root)
    stale = root / lg.CLONE_REL / tree
    stale.mkdir(parents=True)
    (stale / "left-over").write_text("x", encoding="utf-8")
    assert lg.clone_refusal(root, tree, head_of(root)) is None
    assert not (stale / "left-over").exists()


def test_a_declared_submodule_with_no_gitlink_refuses(tmp_path: pathlib.Path) -> None:
    root = with_submodule(tmp_path)
    with (root / ".gitmodules").open("a", encoding="utf-8") as fh:
        fh.write(
            '[submodule "ghost"]\n\tpath = private/ghost\n\turl = %s\n' % (tmp_path / "subsrc")
        )
    commit_all(root, "declare a submodule with no gitlink")
    # A local copy to clone from, so the refusal is the missing gitlink, not the missing source.
    git(root, "clone", "-q", str(tmp_path / "subsrc"), str(root / "private" / "ghost"))
    got = lg.clone_refusal(root, tree_of(root), head_of(root))
    assert got is not None
    assert got.code == "clone"
    assert "private/ghost" in got.message
    assert "no gitlink" in got.message


def test_a_dirty_clone_refuses(tmp_path: pathlib.Path, isolated_git: pathlib.Path) -> None:
    root = with_submodule(tmp_path)
    (root / ".gitattributes").write_text("seed.txt filter=rewrite\n", encoding="utf-8")
    commit_all(root, "a filter the host defines")
    # The host's clean filter rewrites the file, so the checkout no longer matches the tree: a clone that is not clean even though nothing was edited.
    with isolated_git.open("a", encoding="utf-8") as fh:
        fh.write('[filter "rewrite"]\n\tclean = tr s S\n')
    got = lg.clone_refusal(root, tree_of(root), head_of(root))
    assert got is not None
    assert got.code == "clone"
    assert "not clean" in got.message
    assert "seed.txt" in got.message


def test_a_submodule_out_of_place_refuses(tmp_path: pathlib.Path) -> None:
    root = with_submodule(tmp_path)
    missing = "1234567890abcdef1234567890abcdef12345678"
    git(root, "update-index", "--cacheinfo", "160000,%s,private/sub" % missing)
    git(root, "commit", "-q", "-m", "a pointer no copy has")
    got = lg.clone_refusal(root, tree_of(root), head_of(root))
    assert got is not None
    assert "submodule" in got.message


# --------------------------------------------------------------------------- (e) origin/main


def test_head_not_origin_main_refuses(tmp_path: pathlib.Path) -> None:
    root = tagged_repo(tmp_path)
    got = lg.origin_main_refusal(root, head_of(root), lambda _r: ("f" * 40, ""))
    assert got is not None
    assert "is not origin/main" in got.message


def test_a_failed_fetch_refuses(tmp_path: pathlib.Path) -> None:
    root = tagged_repo(tmp_path)
    got = lg.origin_main_refusal(root, head_of(root), lambda _r: (None, "could not resolve host"))
    assert got is not None
    assert "fetch of origin main failed" in got.message


def test_the_live_fetch_against_a_real_origin(tmp_path: pathlib.Path) -> None:
    root = tagged_repo(tmp_path)
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(root, "remote", "add", "origin", str(bare))
    git(root, "push", "-q", "origin", "main")
    assert lg.origin_main_refusal(root, head_of(root), lg.live_fetch) is None
    (root / "ahead.txt").write_text("not pushed\n", encoding="utf-8")
    commit_all(root, "ahead of origin")
    got = lg.origin_main_refusal(root, head_of(root), lg.live_fetch)
    assert got is not None
    assert "is not origin/main" in got.message


def test_the_live_fetch_with_no_origin_refuses(tmp_path: pathlib.Path) -> None:
    root = tagged_repo(tmp_path)
    got = lg.origin_main_refusal(root, head_of(root), lg.live_fetch)
    assert got is not None
    assert "fetch of origin main failed" in got.message


# --------------------------------------------------------------------------- (f) the release lock


def free(_root: pathlib.Path, _version: str) -> tuple[bool, str]:
    return True, "Version is available for publishing."


def test_a_present_sentinel_refuses(tmp_path: pathlib.Path) -> None:
    got = lg.lock_refusals(tmp_path, "1.0.1", lambda _v: True, free)
    assert [r.code for r in got] == ["lock"]
    assert "is taken" in got[0].message


def test_an_unknown_sentinel_refuses(tmp_path: pathlib.Path) -> None:
    got = lg.lock_refusals(tmp_path, "1.0.1", lambda _v: None, free)
    assert [r.code for r in got] == ["lock"]
    assert "UNKNOWN" in got[0].message


def test_check_existing_release_must_agree(tmp_path: pathlib.Path) -> None:
    got = lg.lock_refusals(
        tmp_path, "1.0.1", lambda _v: False, lambda _r, _v: (False, "tag exists")
    )
    assert [r.code for r in got] == ["lock"]
    assert "tag exists" in got[0].message


def test_a_free_lock_admits(tmp_path: pathlib.Path) -> None:
    assert lg.lock_refusals(tmp_path, "1.0.1", lambda _v: False, free) == []


def test_a_hung_check_existing_release_is_a_refusal_not_an_exception(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A timeout in the existing-release probe is a lock refusal, so every other gate's refusal still prints."""

    def hang(*args: Any, **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(args[0], kwargs.get("timeout", 0))

    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setattr(lg.subprocess, "run", hang)
    free_, said = lg.live_existing(tmp_path, "1.0.1")
    assert free_ is False
    assert "did not answer within %ds" % lg.FETCH_TIMEOUT_S in said


# --------------------------------------------------------------------------- stable


NOW = int(time.time())
ASKED = "ASKED:2026-10-27T06:37Z"


def stamp(days_ago: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - days_ago * 86400))


def stable(
    record: dict[str, Any] | None,
    *,
    force_asked: str | None = None,
    proven: bool = False,
    tag: str | None = "a" * 40,
    sealed: bool | None = True,
) -> list[lg.Refusal]:
    return lg.stable_refusals(
        version="1.0.0",
        tag_commit=lambda _t: tag,
        sentinel=lambda _v: sealed,
        record=lambda _k: (record, "") if record is not None else (None, "absent"),
        force_asked=force_asked,
        asked_proof=lambda _a: proven,
        now_epoch=NOW,
    )


def test_stable_with_no_edge_record_refuses() -> None:
    got = stable(None)
    assert len(got) == 1
    assert "release-records/v1.0.0/edge.json is absent" in got[0].message


def test_stable_inside_the_soak_window_without_force_refuses() -> None:
    got = stable({"smoke_rc": 0, "recorded_at": stamp(2)})
    assert len(got) == 1
    assert "has not soaked" in got[0].message
    assert "Edge needs 5 more day(s) of soak" in got[0].message


def test_stable_force_with_an_unproven_minute_refuses() -> None:
    got = stable({"smoke_rc": 0, "recorded_at": stamp(2)}, force_asked=ASKED, proven=False)
    messages = " ".join(r.message for r in got)
    assert "matches no AskUserQuestion answer" in messages
    assert "has not soaked" in messages


def test_stable_force_with_a_proven_minute_skips_the_age() -> None:
    assert stable({"smoke_rc": 0, "recorded_at": stamp(2)}, force_asked=ASKED, proven=True) == []


def test_stable_a_failed_edge_smoke_refuses() -> None:
    got = stable({"smoke_rc": 1, "recorded_at": stamp(9)})
    assert len(got) == 1
    assert "smoke_rc 1" in got[0].message


def test_stable_an_untagged_or_unsealed_version_refuses() -> None:
    got = stable({"smoke_rc": 0, "recorded_at": stamp(9)}, tag=None, sealed=None)
    messages = [r.message for r in got]
    assert any("tag v1.0.0 does not exist" in m for m in messages)
    assert any("UNKNOWN" in m for m in messages)


def test_stable_all_good_admits() -> None:
    assert stable({"smoke_rc": 0, "recorded_at": stamp(9)}) == []


def test_the_transcript_proof_without_a_transcript_proves_nothing() -> None:
    assert lg.transcript_proof(None)(ASKED) is False


# --------------------------------------------------------------------------- the whole check


def green_world(tmp_path: pathlib.Path) -> pathlib.Path:
    """The guard's push-green world, tagged at HEAD so nothing moved since the previous release."""
    root = guard_world(tmp_path, "push-green")
    git(root, "tag", "v1.0.0")
    return root


def test_check_admits_a_green_world(tmp_path: pathlib.Path) -> None:
    root = green_world(tmp_path)
    head = head_of(root)
    got = lg.check(
        root,
        "edge",
        fetch=lambda _r: (head, ""),
        sentinel=lambda _v: False,
        existing=free,
        next_version=lambda _r: "1.0.1",
    )
    assert got == []


def test_check_names_every_refusal(tmp_path: pathlib.Path) -> None:
    root = guard_world(tmp_path, "push-no-receipt")
    got = lg.check(
        root,
        "edge",
        fetch=lambda _r: (None, "offline"),
        sentinel=lambda _v: None,
        existing=free,
        next_version=lambda _r: "1.0.1",
    )
    assert [r.code for r in got] == ["ci-quick", "vm-check", "origin-main", "lock"]
    assert all(r.line().startswith("local-gates: ") and "\n" not in r.line() for r in got)


def test_check_stable_runs_the_stable_gate(tmp_path: pathlib.Path) -> None:
    root = green_world(tmp_path)
    head = head_of(root)
    got = lg.check(
        root,
        "stable",
        fetch=lambda _r: (head, ""),
        sentinel=lambda _v: True,
        version="1.0.0",
        tag_commit=lambda _t: head,
        record=lambda _k: (None, "absent"),
    )
    assert [r.code for r in got] == ["stable"]
