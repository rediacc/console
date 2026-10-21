"""check_plan_citations' reachability test for cited blobs and trees, driven against real repositories.

A blob:none partial clone stands in for CI's checkout: a committed blob it has not fetched must still count as reachable, and the cited prefix must resolve without a lazy fetch. A listing that fails must not refuse a citation whose presence was already proven.
"""

import importlib.util
import pathlib
import subprocess

from rediacc_ci import paths

GATE = paths.repo_root() / ".ci" / "scripts" / "quality" / "check_plan_citations.py"


def _gate_module(monkeypatch):
    # The script imports its sibling `_cipath` (the hop to `.ci`), as it does when run directly.
    monkeypatch.syspath_prepend(str(GATE.parent))
    spec = importlib.util.spec_from_file_location("check_plan_citations_under_test", GATE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(cwd, *args):
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "-c",
            "protocol.file.allow=always",
            *args,
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    ).stdout.strip()


def test_an_unfetched_committed_blob_in_a_blob_none_clone_is_reachable(tmp_path, monkeypatch):
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(origin, "init", "-q", "-b", "main")
    _git(origin, "config", "uploadpack.allowFilter", "true")
    (origin / "kept.txt").write_text("a committed blob the clone never fetches\n")
    _git(origin, "add", "kept.txt")
    _git(origin, "commit", "-qm", "base")
    blob = _git(origin, "rev-parse", "HEAD:kept.txt")
    clone = tmp_path / "clone"
    _git(
        tmp_path,
        "clone",
        "-q",
        "--filter=blob:none",
        "--no-checkout",
        "file://%s" % origin,
        str(clone),
    )
    missing = subprocess.run(
        ["git", "-C", str(clone), "cat-file", "-e", blob],
        env={"GIT_NO_LAZY_FETCH": "1", "PATH": "/usr/bin:/bin"},
        capture_output=True,
        check=False,
    )
    assert missing.returncode != 0, (
        "the fixture must leave the blob unfetched, or it proves nothing"
    )
    mod = _gate_module(monkeypatch)
    assert mod.content_object_is_reachable(clone, blob[:12])
    assert not mod.content_object_is_reachable(clone, "0123456789ab")


def test_a_failed_listing_defers_to_the_callers_presence_check(tmp_path, monkeypatch):
    """When git cannot list objects the reachability answer is True by design, because `unresolved` asks only after proving presence; the caller still refuses an object that is not there."""
    mod = _gate_module(monkeypatch)
    not_a_repo = pathlib.Path(tmp_path)
    assert mod._reachable_objects(not_a_repo) is None
    assert mod.content_object_is_reachable(not_a_repo, "0123456789ab")
    bad, _why = mod.unresolved(not_a_repo, "object", "0123456789ab")
    assert bad, "an object that is not present is refused even when the listing failed"


def test_an_ambiguous_prefix_is_not_reachable(tmp_path, monkeypatch):
    mod = _gate_module(monkeypatch)
    monkeypatch.setattr(
        mod, "_reachable_objects", lambda _root: ["abcd1111" + "0" * 32, "abcd2222" + "0" * 32]
    )
    assert not mod.content_object_is_reachable(tmp_path, "abcd")
    assert mod.content_object_is_reachable(tmp_path, "abcd1111")
