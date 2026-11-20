"""PLAN-two-track-merge-dev P1: the run-to-run fact cache of check:ci-plan-implementation (rediacc_ci.quality.plan_impl_facts)."""

import json
import subprocess

import pytest
import wl_planrec
import wl_review

from rediacc_ci.quality import plan_impl_facts as PIF

IDENT = ["-c", "user.name=t", "-c", "user.email=t@example.invalid"]


def _git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _repo(tmp_path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _git(repo, *IDENT, "commit", "-q", "--allow-empty", "-m", "base")
    shas = []
    for name in ("a.txt", "b.txt", "c.txt"):
        (repo / name).write_text(name + "\n")
        _git(repo, "add", name)
        _git(repo, *IDENT, "commit", "-q", "-m", name)
        shas.append(_git(repo, "rev-parse", "HEAD"))
    (repo / "c.txt").rename(repo / "d.txt")
    _git(repo, "add", "-A")
    _git(repo, *IDENT, "commit", "-q", "-m", "move c to d")
    return repo, shas


def test_differential_cached_answers_equal_the_per_call_answers(tmp_path):
    repo, shas = _repo(tmp_path)
    cache = tmp_path / "facts.json"
    fresh = {s: wl_review.patch_id(repo, s) for s in shas}
    dates = {s: _git(repo, "log", "-1", "--format=%cI", s) for s in shas}
    follow = tuple(_git(repo, "log", "--follow", "--name-only", "--format=", "--", "d.txt").split())
    last = _git(repo, "rev-list", "-1", "HEAD", "--", "d.txt")
    for _pass in ("cold", "warm"):
        facts = PIF.Facts(repo, "closure-x", str(cache))
        got = facts.patch_ids(
            shas,
            lambda: wl_review.patch_ids(repo, "HEAD~4..HEAD"),
            lambda s: wl_review.patch_id(repo, s),
            batch_over=1,
        )
        assert got == fresh
        for s in shas:
            assert (
                facts.commit_date("date_c", s, lambda c: _git(repo, "log", "-1", "--format=%cI", c))
                == dates[s]
            )
        assert facts.follow("d.txt", last, lambda _rel: follow) == follow
        facts.save()
    warm = PIF.Facts(repo, "closure-x", str(cache))
    assert warm.get("patch", shas[0]) == fresh[shas[0]], "the second pass must read the saved cache"


def test_a_warm_cache_answers_without_computing(tmp_path):
    repo, shas = _repo(tmp_path)
    cache = tmp_path / "facts.json"
    facts = PIF.Facts(repo, "closure-x", str(cache))
    facts.patch_ids(
        shas,
        lambda: wl_review.patch_ids(repo, "HEAD~4..HEAD"),
        lambda s: wl_review.patch_id(repo, s),
        batch_over=1,
    )
    facts.save()

    def boom(*_a):
        raise AssertionError("a cached fact was computed again")

    warm = PIF.Facts(repo, "closure-x", str(cache))
    assert set(warm.patch_ids(shas, boom, boom)) == set(shas)


def test_stale_an_entry_under_another_closure_is_ignored(tmp_path):
    repo, shas = _repo(tmp_path)
    cache = tmp_path / "facts.json"
    cache.write_text(
        json.dumps(
            {
                "schema": PIF.SCHEMA,
                "closure": "old-code",
                "patch": {shas[0]: "f" * 40},
                "date_c": {},
                "date_a": {},
                "follow": {},
            }
        )
    )
    facts = PIF.Facts(repo, "new-code", str(cache))
    assert facts.get("patch", shas[0]) is None, (
        "a planted entry under a changed closure hash must be ignored"
    )
    assert PIF.closure_hash([__file__]) != PIF.closure_hash([__file__, str(cache)]), (
        "the closure covers every file"
    )


def test_rebase_reachability_is_never_cached(tmp_path):
    repo, shas = _repo(tmp_path)
    cache = tmp_path / "facts.json"
    facts = PIF.Facts(repo, "closure-x", str(cache))
    facts.commit_date("date_c", shas[-1], lambda c: _git(repo, "log", "-1", "--format=%cI", c))
    facts.save()
    with pytest.raises(KeyError, match="reachability"):
        facts.put("ancestor", shas[-1], "yes")
    _git(repo, "reset", "-q", "--hard", "HEAD~2")
    ok, why = wl_planrec.resolve(repo, "commit", shas[-1])
    assert not ok, (
        "a commit dropped from HEAD's ancestry reads unreachable despite a cached fact about it: %s"
        % why
    )


def test_a_damaged_cache_is_an_empty_cache(tmp_path):
    repo, _shas = _repo(tmp_path)
    cache = tmp_path / "facts.json"
    cache.write_text("{not json")
    assert PIF.Facts(repo, "closure-x", str(cache)).data == {k: {} for k in PIF.KINDS}


def test_a_commit_only_on_origin_main_resolves_and_dropping_origin_main_refuses_it(
    tmp_path, monkeypatch
):
    """The reachability half of D2: answered fresh from HEAD and origin/main every run. A commit reachable only from origin/main resolves; the mutant that drops origin/main from the refs asked goes red."""
    repo, _shas = _repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "side", "HEAD~1")
    _git(repo, *IDENT, "commit", "-q", "--allow-empty", "-m", "only on main")
    only_main = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", "refs/remotes/origin/main", only_main)
    _git(repo, "checkout", "-q", "main")
    assert wl_planrec.resolve(repo, "commit", only_main)[0]
    real = wl_planrec._git_ok
    monkeypatch.setattr(
        wl_planrec,
        "_git_ok",
        lambda root, *a: False if "refs/remotes/origin/main" in a else real(root, *a),
    )
    assert not wl_planrec.resolve(repo, "commit", only_main)[0], (
        "MUTANT: without origin/main the commit must read unreachable"
    )


def test_a_damaged_follow_value_is_a_miss(tmp_path):
    repo, _shas = _repo(tmp_path)
    cache = tmp_path / "facts.json"
    last = _git(repo, "rev-list", "-1", "HEAD", "--", "d.txt")
    cache.write_text(
        json.dumps(
            {
                "schema": PIF.SCHEMA,
                "closure": "c",
                "patch": {},
                "date_c": {},
                "date_a": {},
                "follow": {"d.txt@" + last: "c.txt"},
            }
        )
    )
    facts = PIF.Facts(repo, "c", str(cache))
    assert facts.follow("d.txt", last, lambda _rel: ("c.txt",)) == ("c.txt",), (
        "a string value must not read as one name per character"
    )


def test_a_ref_that_is_not_a_full_sha_is_memoized_for_the_run(tmp_path):
    repo, _shas = _repo(tmp_path)
    facts = PIF.Facts(repo, "c", str(tmp_path / "f.json"))
    calls = []

    def compute(ref):
        calls.append(ref)
        return "2026-11-20T00:00:00Z"

    facts.commit_date("date_c", "HEAD", compute)
    facts.commit_date("date_c", "HEAD", compute)
    assert calls == ["HEAD"]
    assert facts.data["date_c"] == {}, "a ref is never written to the run-to-run cache"


def test_an_unreadable_source_hashes_instead_of_raising(tmp_path):
    unreadable = tmp_path / "secret.py"
    unreadable.write_text("x")
    unreadable.chmod(0)
    try:
        assert PIF.closure_hash([unreadable]) != PIF.closure_hash([tmp_path / "missing.py"])
    finally:
        unreadable.chmod(0o600)
