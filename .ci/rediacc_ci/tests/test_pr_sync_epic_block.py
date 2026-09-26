"""Differential: `rediacc_ci.pr.sync_epic_block` against its twin `.ci/scripts/pr/sync-epic-block.sh`.

A DISPOSABLE LOCAL GIT REPO (never GitHub), on the same strategy as `test_review_epic_context.py`: real commits, an `agent/pr/<branch>.md` snapshot the twin reads by convention, `git rev-parse --show-toplevel` resolving the fixture root rather than this checkout's.

A RECORDING FAKE `gh`, written as Python per ruling 7, seam is PATH. The seam matters here for a reason `ci-stop-elite`'s fake docker also proved: `gh pr edit` is NOT stdout/stderr-redirected by either subject, so a fake that stays silent on success would hide a port that swallowed that pass-through -- `test_gh_edit_stdout_is_not_swallowed` exists to catch exactly that class, after
it was confirmed present in a first draft of the port (both `stdout`
and `stderr` were passed `capture_output=True` for the edit call, silently
eating gh's own URL line; fixed to inherit both, matching the twin).

K=5 LEDGER: `.ci/shadow/w7p6-sync-epic-block.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile

from rediacc_ci import paths

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "pr" / "sync-epic-block.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "pr" / "sync_epic_block.py"

FAKE_GH = """#!/usr/bin/env python3
import os
import sys

LOG = os.environ["FAKE_GH_LOG"]
BODY = os.environ.get("FAKE_GH_BODY", "")
VIEW_RC = int(os.environ.get("FAKE_GH_VIEW_RC", "0"))
EDIT_RC = int(os.environ.get("FAKE_GH_EDIT_RC", "0"))
BODY_CAPTURE = os.environ.get("FAKE_GH_BODY_CAPTURE")

with open(LOG, "a", encoding="utf-8") as fh:
    fh.write("\\t".join(sys.argv[1:]) + "\\n")

argv = sys.argv[1:]
if argv[:2] == ["pr", "view"]:
    if VIEW_RC != 0:
        sys.stderr.write("gh: fake pr view failure\\n")
        sys.exit(VIEW_RC)
    sys.stdout.write(BODY)
    sys.exit(0)
if argv[:2] == ["pr", "edit"]:
    if EDIT_RC != 0:
        sys.stderr.write("gh: fake pr edit failure\\n")
        sys.exit(EDIT_RC)
    if BODY_CAPTURE:
        # `--body-file <path>` is always argv index 4 in this script's own
        # invocation shape; captured so a test can inspect the file's content
        # before the caller's `trap EXIT` deletes its temp dir.
        body_file = argv[4]
        with open(body_file, "r", encoding="utf-8") as src:
            content = src.read()
        with open(BODY_CAPTURE, "a", encoding="utf-8") as dst:
            dst.write(content)
            dst.write("\\x00")
    # REAL `gh pr edit` prints the PR URL to its own stdout on success, and
    # NEITHER subject redirects that call's streams -- reproduced here or a
    # port that silently captured (and dropped) it would agree with the twin
    # on every other assertion in this file.
    sys.stdout.write("https://github.com/example/repo/pull/" + argv[2] + "\\n")
    sys.exit(0)
sys.exit(1)
"""


def _git(cwd: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


def _repo(tmp_path: pathlib.Path) -> pathlib.Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    (repo / "agent" / "pr").mkdir(parents=True)
    (repo / "f.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _snapshot(repo: pathlib.Path, branch: str, text: str) -> None:
    slug = branch.replace("/", "-")
    (repo / "agent" / "pr" / f"{slug}.md").write_text(text, encoding="utf-8")


def _fake_gh_bin(where: pathlib.Path) -> pathlib.Path:
    where.mkdir(parents=True, exist_ok=True)
    fake = where / "gh"
    fake.write_text(FAKE_GH, encoding="utf-8")
    fake.chmod(0o755)
    return where


def _run(
    subject: pathlib.Path,
    cwd: pathlib.Path,
    *args: str,
    gh_env: dict[str, str] | None = None,
    path_override: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    runner = ["bash"] if subject.suffix == ".sh" else ["python3"]
    env = dict(os.environ)
    log = cwd.parent / f"ghlog-{subject.name}.txt"
    log.write_text("", encoding="utf-8")
    if gh_env is not None:
        env.update(gh_env)
        env["FAKE_GH_LOG"] = str(log)
        fake_bin = _fake_gh_bin(cwd.parent / f"fakebin-{subject.name}")
        env["PATH"] = f"{fake_bin}:{env.get('PATH', '')}"
    if path_override is not None:
        env["PATH"] = path_override
    proc = subprocess.run(
        [*runner, str(subject), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=30,
    )
    calls = (
        [line for line in log.read_text(encoding="utf-8").splitlines() if line]
        if gh_env is not None
        else []
    )
    return proc, calls


def run_both(repo: pathlib.Path, *args: str, gh_env: dict[str, str] | None = None):
    old, old_calls = _run(TWIN, repo, *args, gh_env=gh_env)
    new, new_calls = _run(PORT, repo, *args, gh_env=gh_env)
    return old, new, old_calls, new_calls


def _assert_agree(old, new, label: str) -> None:
    assert new.returncode == old.returncode, (
        f"{label}: exit diverged: {old.returncode!r} vs {new.returncode!r}"
    )
    assert new.stdout == old.stdout, (
        f"{label}: stdout diverged:\nold: {old.stdout!r}\nnew: {new.stdout!r}"
    )
    assert new.stderr == old.stderr, (
        f"{label}: stderr diverged:\nold: {old.stderr!r}\nnew: {new.stderr!r}"
    )


def _normalize_edit_call(calls: list[str]) -> list[str]:
    """The last token of the `pr edit` call is a per-run mktemp path, which necessarily differs between the two independent subprocess runs; every other token (the verb sequence and its fixed flags) must still match."""
    return [c.rsplit("\t", 1)[0] if c.startswith("pr\tedit") else c for c in calls]


def test_usage_with_zero_args(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    old, new, _, _ = run_both(repo)
    assert old.returncode == 2
    _assert_agree(old, new, "usage-0")


def test_usage_with_one_arg(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    old, new, _, _ = run_both(repo, "5")
    assert old.returncode == 2
    _assert_agree(old, new, "usage-1")


def test_not_a_git_repo(tmp_path: pathlib.Path) -> None:
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    old, new, _, _ = run_both(outside, "5", "branch", "--dry-run")
    assert old.returncode == 128
    _assert_agree(old, new, "not-a-git-repo")
    assert "not a git repository" in old.stderr


def test_no_snapshot(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    old, new, _, _ = run_both(repo, "5", "no-such-branch", "--dry-run")
    assert old.returncode == 1
    _assert_agree(old, new, "no-snapshot")
    assert "no snapshot at agent/pr/no-such-branch.md" in old.stderr


def test_dry_run_strips_generated_header_and_epic_heading(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    _snapshot(
        repo,
        "0906-1",
        "<!-- generated by worklist.py, do not hand-edit -->\n"
        "# Work in 0906-1\n\n"
        "- [x] item one (abc123)\n"
        "- [ ] item two (def456)\n",
    )
    old, new, _, _ = run_both(repo, "7", "0906-1", "--dry-run")
    assert old.returncode == 0
    _assert_agree(old, new, "dry-run")
    assert "<!-- worklist-epics:begin -->" in old.stdout
    assert "# Work in 0906-1" not in old.stdout
    assert "generated by worklist.py" not in old.stdout


def test_dry_run_slash_in_branch_name_maps_to_dash(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    _snapshot(repo, "feature/thing", "body text\n")
    old, new, _, _ = run_both(repo, "9", "feature/thing", "--dry-run")
    assert old.returncode == 0
    _assert_agree(old, new, "slash-branch")


def test_gh_pr_edit_replaces_existing_block_and_url_passes_through(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    _snapshot(repo, "0906-1", "- [x] a\n- [ ] b\n")
    gh_env = {
        "FAKE_GH_BODY": (
            "Some existing body text.\n\n"
            "<!-- worklist-epics:begin -->\nold stale block\n<!-- worklist-epics:end -->\n"
            "Trailer line.\n"
        )
    }
    old, new, old_calls, new_calls = run_both(repo, "5", "0906-1", gh_env=gh_env)
    assert old.returncode == 0
    _assert_agree(old, new, "gh-edit-replace")
    assert _normalize_edit_call(old_calls) == _normalize_edit_call(new_calls), (
        f"gh call sequence diverged:\n old: {old_calls}\n new: {new_calls}"
    )
    assert "old stale block" not in old.stdout
    assert "epic block synced into PR #5" in old.stdout


def test_gh_edit_stdout_is_not_swallowed(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY for the pass-through requirement. `gh pr edit`'s own stdout (the PR URL) must appear BEFORE the final checkmark line on both sides -- a port that captured and discarded it would still exit 0 and print the checkmark, passing every other assertion in this file."""
    repo = _repo(tmp_path)
    _snapshot(repo, "0906-1", "- [x] a\n")
    gh_env = {"FAKE_GH_BODY": "plain body\n"}
    old, _, _, _ = run_both(repo, "5", "0906-1", gh_env=gh_env)
    lines = old.stdout.splitlines()
    assert any("github.com" in line for line in lines), (
        f"gh's own stdout is missing: {old.stdout!r}"
    )
    assert lines[-1].startswith("✓"), f"the final line is not the checkmark: {lines[-1]!r}"
    url_line = next(line for line in lines if "github.com" in line)
    assert lines.index(url_line) < len(lines) - 1


def test_gh_pr_view_failure_propagates(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    _snapshot(repo, "0906-1", "body\n")
    gh_env = {"FAKE_GH_VIEW_RC": "17"}
    old, new, _, _ = run_both(repo, "5", "0906-1", gh_env=gh_env)
    assert old.returncode == 17
    _assert_agree(old, new, "gh-view-fails")


def test_gh_pr_edit_failure_propagates(tmp_path: pathlib.Path) -> None:
    repo = _repo(tmp_path)
    _snapshot(repo, "0906-1", "body\n")
    gh_env = {"FAKE_GH_EDIT_RC": "3", "FAKE_GH_BODY": "plain body\n"}
    old, new, _, _ = run_both(repo, "5", "0906-1", gh_env=gh_env)
    assert old.returncode == 3
    _assert_agree(old, new, "gh-edit-fails")


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY. Flip `line == BEGIN` to `line.startswith(BEGIN)` in the
    marker-strip helper -- a plausible-looking "more lenient" rewrite that breaks exact-line equality, which the twin's own header calls out explicitly ("exact-line equality on the markers (not a substring match)"). Driven red on a body whose begin marker has trailing content on the same line as real prose containing the marker text, then the source is restored byte-identical
    and re-verified green."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace(
        "if line == BEGIN:\n            skip = True",
        "if line.startswith(BEGIN):\n            skip = True",
    )
    assert mutated != original, "the line this plant targets is no longer present verbatim"

    repo = _repo(tmp_path)
    _snapshot(repo, "0906-1", "- [x] a\n")
    # The line STARTS WITH the exact begin marker but carries trailing junk,
    # so real awk's `$0==b` (exact equality) does NOT treat it as the marker
    # and passes it through unskipped; `.startswith(BEGIN)` wrongly does.
    body = "<!-- worklist-epics:begin --> plus trailing junk\nkeep me\n"

    with tempfile.TemporaryDirectory() as td:
        mutant_path = pathlib.Path(td) / "mutant.py"
        mutant_path.write_text(mutated, encoding="utf-8")

        # The rebuilt body is only ever WRITTEN to a file passed to `gh pr edit` in the non-dry-run path (never printed), and that file is deleted by the caller's own `trap EXIT` before this test could look at it -- the fake `gh` copies it out first.
        old_capture = pathlib.Path(td) / "old-body.txt"
        new_capture = pathlib.Path(td) / "new-body.txt"
        old_gh_env = {"FAKE_GH_BODY": body, "FAKE_GH_BODY_CAPTURE": str(old_capture)}
        new_gh_env = {"FAKE_GH_BODY": body, "FAKE_GH_BODY_CAPTURE": str(new_capture)}
        _old, _old_calls = _run(TWIN, repo, "5", "0906-1", gh_env=old_gh_env)
        _new, _new_calls = _run(mutant_path, repo, "5", "0906-1", gh_env=new_gh_env)

        old_body = old_capture.read_text(encoding="utf-8")
        new_body = new_capture.read_text(encoding="utf-8")
        assert "keep me" in old_body, "fixture line was stripped by the TWIN; plant is untested"
        assert "keep me" not in new_body, "the mutant did not over-strip; plant did not fire"
        assert new_body != old_body, "planted defect was not caught by the rebuilt-body comparison"

    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
