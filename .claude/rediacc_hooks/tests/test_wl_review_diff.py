"""The reviewed diff leaves out the review records that ride a commit (CLAUDE.md rule 1, Cadence).

A commit that carries `agent/reviews/<branch>/<sha>.md` beside its own change used to send those records to the reviewer, which then filed findings about the records themselves (eight such findings on branch 1008-1, each one closed by hand). `capped_diff` now drops every `agent/reviews/` section and keeps the rest; the control is the same commit's other file, still sent whole.
"""

from __future__ import annotations

import contextlib
import os
import subprocess

from rediacc_hooks.tests import wlfix

R = wlfix.import_wl("wl_review")

GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME="Fixture",
    GIT_AUTHOR_EMAIL="fixture@example.invalid",
    GIT_COMMITTER_NAME="Fixture",
    GIT_COMMITTER_EMAIL="fixture@example.invalid",
    GIT_CONFIG_GLOBAL="/dev/null",
    GIT_CONFIG_SYSTEM="/dev/null",
)


def _git(repo, *args):
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, env=GIT_ENV
    ).stdout.strip()


def _mixed_commit(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "--initial-branch=main")
    (repo / "README.md").write_text("base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    (repo / "tool.py").write_text("print('changed')\n")
    record = repo / "agent" / "reviews" / "1231-9" / ("a" * 40 + ".md")
    record.parent.mkdir(parents=True)
    record.write_text("# Review aaaaaaaa: a record riding this commit\n\nResolution: open\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: a change with a riding review record")
    return repo, _git(repo, "rev-parse", "HEAD")


def test_a_riding_review_record_is_left_out_of_the_reviewed_diff(tmp_path):
    repo, sha = _mixed_commit(tmp_path)
    diff, _total, files, cut = R.capped_diff(str(repo), sha, 100_000)
    assert "agent/reviews/" not in diff
    assert files == 1
    assert cut == []


def test_control_the_commits_own_change_is_still_sent_whole(tmp_path):
    repo, sha = _mixed_commit(tmp_path)
    diff, _total, _files, _cut = R.capped_diff(str(repo), sha, 100_000)
    assert "diff --git a/tool.py b/tool.py" in diff
    assert "print('changed')" in diff


def test_move_search_note_says_so_when_the_commits_cannot_be_counted(monkeypatch):
    """Review 21ac17b2.1: a failing `git rev-list --count` read as 0 commits, so the refusal omitted the cut-short sentence. CONTROL: a short counted range stays silent."""
    monkeypatch.setattr(R, "git", lambda *_a, **_k: (0, "3\n"))
    assert R.move_search_note("r", "b" * 12, "f" * 12) == ""
    monkeypatch.setattr(R, "git", lambda *_a, **_k: (128, ""))
    assert "could not count" in R.move_search_note("r", "b" * 12, "f" * 12)
    monkeypatch.setattr(R, "git", lambda *_a, **_k: (0, "many\n"))
    assert "could not count" in R.move_search_note("r", "b" * 12, "f" * 12)
    monkeypatch.setattr(R, "git", lambda *_a, **_k: (0, "%d\n" % (R.MOVE_MAX_COMMITS + 5)))
    assert "read only the newest" in R.move_search_note("r", "b" * 12, "f" * 12)


def _commit_files(tmp_path, name, files):
    """A repo whose last commit writes `files` ({path: text}) over a base commit; returns (repo, sha)."""
    repo = tmp_path / name
    repo.mkdir()
    _git(repo, "init", "-q", "--initial-branch=main")
    (repo / "README.md").write_text("base\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "change")
    return repo, _git(repo, "rev-parse", "HEAD")


def _cfg():
    """The console's real config: a scratch repo carries none of its own."""
    return R.load_config(R.CONSOLE_ROOT)


def test_control_a_code_only_commit_diff_is_unchanged(tmp_path):
    repo, sha = _commit_files(tmp_path, "c", {"a.py": "x = 1\n"})
    diff, _total, files, cut = R.capped_diff(str(repo), sha, 100_000)
    assert "diff --git a/a.py b/a.py" in diff
    assert files == 1
    assert cut == []


def test_a_queue_record_leaves_the_diff_and_the_code_stays(tmp_path):
    repo, sha = _commit_files(tmp_path, "q", {"a.py": "x = 1\n", "agent/plans/QUEUE.md": "queue\n"})
    diff, _total, files, _cut = R.capped_diff(str(repo), sha, 100_000)
    assert "a.py" in diff
    assert "QUEUE.md" not in diff
    assert files == 1


def test_the_other_skip_paths_leave_the_diff(tmp_path):
    repo, sha = _commit_files(
        tmp_path,
        "o",
        {
            "a.py": "x = 1\n",
            "agent/s1/STATE.md": "s\n",
            "agent/ledgers/census-x.jsonl": "{}\n",
            ".ci/config/plan-boxes.json": "{}\n",
            "agent/worklist/events.jsonl": "{}\n",
        },
    )
    diff, _total, files, _cut = R.capped_diff(str(repo), sha, 100_000)
    for gone in ("STATE.md", "ledgers", "plan-boxes", "worklist"):
        assert gone not in diff
    assert files == 1


def test_skip_globs_union_the_record_paths_read_at_runtime(tmp_path):
    (tmp_path / ".ci" / "policy").mkdir(parents=True)
    (tmp_path / ".ci" / "policy" / "record-paths.json").write_text(
        '{"records": [{"glob": "agent/worklist/*.jsonl", "except": []}]}'
    )
    skips = R.skip_globs(str(tmp_path), {"review_skip_globs": ["agent/ledgers/**"]})
    assert R.is_skipped_path("agent/worklist/e.jsonl", skips)
    assert R.is_skipped_path("agent/ledgers/a/b.jsonl", skips)
    assert R.is_skipped_path("agent/reviews/b/clean.jsonl", skips)
    assert not R.is_skipped_path("a.py", skips)
    assert not R.is_skipped_path("agent/worklist/sub/e.jsonl", skips)


def test_a_record_only_commit_is_skipped_without_a_model_call(tmp_path):
    repo, sha = _commit_files(
        tmp_path, "r", {"agent/plans/QUEUE.md": "queue\n", "agent/s1/STATE.md": "s\n"}
    )

    def no_model(*_a):
        raise AssertionError("a record-only commit reached the model")

    path = R.run_review(
        repo, "console", sha, "1110-1", reviewer=no_model, cfg=_cfg(), log=lambda _m: None
    )
    assert path is not None
    assert R.read_ledger(path)[0][0].verdict == "skipped (record-only)"


def test_control_a_mixed_commit_still_reaches_the_model_with_only_the_code(tmp_path):
    repo, sha = _commit_files(tmp_path, "m", {"a.py": "x = 1\n", "agent/plans/QUEUE.md": "queue\n"})
    seen = []

    def model(prompt, *_a):
        seen.append(prompt)
        return {"verdict": "clean", "findings": [], "labels": None}, ""

    R.run_review(repo, "console", sha, "1110-2", reviewer=model, cfg=_cfg(), log=lambda _m: None)
    assert len(seen) == 1
    assert "a.py" in seen[0]
    assert "QUEUE.md" not in seen[0]


def test_a_skip_glob_that_would_cover_code_is_refused(tmp_path):
    """Review 623c29ce.1: the skip list lives in files a commit can edit, so a glob reaching code is refused."""
    (tmp_path / ".ci" / "policy").mkdir(parents=True)
    (tmp_path / ".ci" / "policy" / "record-paths.json").write_text('{"records": []}')
    for bad in ("**", "agent/**", "*.py", ".ci/config/*.json", "packages/**", ".ci/policy/*.json"):
        skips = R.skip_globs(str(tmp_path), {"review_skip_globs": [bad]})
        for code in (
            "a.py",
            "agent/plans/PLAN-y.md",
            ".ci/config/commit-review.json",
            ".ci/policy/record-paths.json",
        ):
            assert not R.is_skipped_path(code, skips), (bad, code)
    # CONTROL: the real record globs stay admitted.
    for good in (
        "agent/plans/QUEUE.md",
        "agent/*/STATE.md",
        "agent/ledgers/plan-*.jsonl",
        ".ci/config/plan-boxes.json",
    ):
        assert R.admissible_skip_glob(good), good
    skips = R.skip_globs(str(tmp_path), {"review_skip_globs": ["agent/*/STATE.md"]})
    assert R.is_skipped_path("agent/s1/STATE.md", skips)


def test_a_commit_widening_the_skip_list_is_still_reviewed(tmp_path):
    """The commit that writes "**" into the skip list is itself reviewed, and the "**" is refused."""
    repo, sha = _commit_files(
        tmp_path, "w", {".ci/config/commit-review.json": '{"review_skip_globs": ["**"]}\n'}
    )
    seen = []

    def model(*a):
        seen.append(a)
        raise RuntimeError("stop after the call")

    with contextlib.suppress(RuntimeError):
        R.run_review(
            repo, "console", sha, "1110-1", reviewer=model, cfg=_cfg(), log=lambda _m: None
        )
    assert seen, "a commit that widens the skip list must reach the model"


def test_the_stat_honours_a_skip_globs_except_like_the_diff(tmp_path):
    """Review 623c29ce.2: a path a skip glob's `except` keeps is listed in the stat as in the diff, and a covered one leaves both."""
    (tmp_path / ".ci" / "policy").mkdir(parents=True)
    (tmp_path / ".ci" / "policy" / "record-paths.json").write_text(
        '{"records": [{"glob": "agent/worklist/*.jsonl", "except": ["agent/worklist/keep.jsonl"]}]}'
    )
    skips = R.skip_globs(str(tmp_path), {"review_skip_globs": []})
    paths = ["agent/worklist/e.jsonl", "agent/worklist/keep.jsonl", "a.py"]
    assert R.stat_paths(paths, skips) == ["agent/worklist/keep.jsonl", "a.py"]
    # CONTROL: with no skip covering them, every path stays.
    assert R.stat_paths(["a.py", "b.py"], skips) == ["a.py", "b.py"]
