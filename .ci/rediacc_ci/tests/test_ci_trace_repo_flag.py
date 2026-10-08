"""ci-trace.py --repo OWNER/NAME retargets every gh read at that repository; without it the console repo is read (finding #0023db1e: a submodule PR such as rediacc/account#91 had no sanctioned CI reader)."""

import importlib.util
import json
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.well_known import ACCOUNT_REPO, GH_ORIGIN, GH_REPO, RENET_REPO

TRACE = paths.from_root(".ci", "scripts", "ci", "ci-trace.py")


@pytest.fixture
def ct():
    spec = importlib.util.spec_from_file_location("ci_trace_repo_flag_under_test", TRACE)
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Done:
    returncode = 0
    stdout = json.dumps({"status": "completed", "conclusion": "success", "jobs": []})
    stderr = ""


def _record_gh(ct, monkeypatch):
    calls = []

    def fake_run(cmd, **_kw):
        calls.append(list(cmd))
        # tmp_path is not a git checkout: git answers like one, so --repo keeps the cwd as its root.
        if cmd[0] == "git":
            return subprocess.CompletedProcess(cmd, 128, "", "fatal: not a git repository")
        return _Done()

    monkeypatch.setattr(ct.subprocess, "run", fake_run)
    return calls


def test_repo_flag_targets_run_view_and_fetcher(ct, monkeypatch, tmp_path):
    calls = _record_gh(ct, monkeypatch)
    monkeypatch.chdir(tmp_path)
    ct.main(["--repo", ACCOUNT_REPO, "--run", "7"])
    view = [c for c in calls if c[:3] == ["gh", "run", "view"]]
    assert view
    assert view[0][view[0].index("--repo") + 1] == ACCOUNT_REPO
    assert ct._fetcher(tmp_path).repo == ACCOUNT_REPO


def test_repo_flag_reaches_the_rollup(ct, monkeypatch, tmp_path):
    seen = {}

    def fake_rollup(_root, _ref, repo=None, **_kw):
        seen["repo"] = repo
        return "no-pr", "x"

    monkeypatch.setattr(ct.wl_ci, "ci_rollup", fake_rollup)
    monkeypatch.chdir(tmp_path)
    ct.main(["--repo", ACCOUNT_REPO, "--ref", "1004-2"])
    assert seen["repo"] == ACCOUNT_REPO


def test_default_is_the_console_repo(ct, monkeypatch, tmp_path):
    calls = _record_gh(ct, monkeypatch)
    monkeypatch.chdir(tmp_path)
    ct.main(["--run", "7"])
    view = [c for c in calls if c[:3] == ["gh", "run", "view"]]
    assert view[0][view[0].index("--repo") + 1] == ct.GH_REPO
    assert ct._fetcher(tmp_path).repo == ct.GH_REPO
    assert ct.GH_REPO != ACCOUNT_REPO


def test_bad_repo_is_refused(ct):
    with pytest.raises(SystemExit):
        ct.main(["--repo", "nonsense", "--run", "7"])


def _zero_info(pushed_at):
    return {
        "owner": "rediacc",
        "name": "account",
        "source": "pr",
        "pr": 91,
        "sha": "050e15cb" + "0" * 32,
        "rollup": "EXPECTED",
        "total": 0,
        "contexts": [],
        "truncated": False,
        "has_rollup": False,
        "foreign": 0,
        "pushed_at": pushed_at,
    }


def _zero_verdict(ct, monkeypatch, pushed_at, runs):
    monkeypatch.setattr(ct.wl_ci, "ci_rollup", lambda *_a, **_k: ("ok", _zero_info(pushed_at)))
    monkeypatch.setattr(ct.wl_ci, "commit_ci_runs", lambda *_a, **_k: (runs, ""))
    monkeypatch.setattr(ct.wl_ci, "nearest_checked_ancestor", lambda *_a, **_k: ("", ""))
    payload, err = ct._snapshot(ct.pathlib.Path("."), "b", {}, seen={})
    assert err is None
    return payload


def test_zero_context_pr_settles_to_no_ci(ct, monkeypatch, capsys):
    payload = _zero_verdict(ct, monkeypatch, "2020-01-01T00:00:00Z", [])
    assert payload["verdict"] == "no-ci"
    ct._emit(payload, False)
    out = capsys.readouterr().out
    assert out.startswith("NO-CI  PR #91 @ 050e15cb: zero check contexts on this head")


def test_zero_context_pr_inside_grace_stays_running(ct, monkeypatch):
    now = ct.datetime.datetime.now(ct.datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert _zero_verdict(ct, monkeypatch, now, [])["verdict"] == "running"


def test_zero_context_pr_with_a_pending_run_stays_running(ct, monkeypatch):
    runs = [(1, "Console CI", "push", "in_progress", 1, "", "")]
    assert _zero_verdict(ct, monkeypatch, "2020-01-01T00:00:00Z", runs)["verdict"] == "running"


def _git(*args):
    subprocess.run(["git", *args], check=True, capture_output=True)


def _checkout(path, origin):
    _git("init", "-q", str(path))
    _git("-C", str(path), "remote", "add", "origin", origin)


def test_checkout_for_repo_finds_the_submodule_whose_origin_matches(ct, tmp_path):
    # 2026-10-08: --repo rediacc/account from the console root compared account#95's head with the CONSOLE's origin/1007-1 and gave no verdict.
    top = tmp_path / "console"
    _checkout(top, "git@github.com:%s.git" % GH_REPO)
    _checkout(top / "private" / "account", "%s/%s.git" % (GH_ORIGIN, ACCOUNT_REPO))
    (top / ".gitmodules").write_text(
        '[submodule "private/account"]\n\tpath = private/account\n\turl = x\n'
    )
    assert ct._checkout_for_repo(top, ACCOUNT_REPO) == top / "private" / "account"
    assert ct._checkout_for_repo(top, GH_REPO) == top
    assert ct._checkout_for_repo(top, RENET_REPO) is None


def test_repo_flag_without_a_matching_checkout_is_refused(ct, monkeypatch, tmp_path):
    top = tmp_path / "console"
    _checkout(top, "git@github.com:%s.git" % GH_REPO)
    monkeypatch.chdir(top)
    with pytest.raises(SystemExit):
        ct.main(["--repo", ACCOUNT_REPO, "--run", "7"])
