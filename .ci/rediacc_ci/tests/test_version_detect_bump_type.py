"""Differential: `rediacc_ci.version.detect_bump_type` against its twin `.ci/scripts/version/detect-bump-type.sh`.

REAL GIT REPOSITORIES, NOT A STUBBED `git`. Every case builds an actual repository in `tmp_path` -- commits, tags, a branch that is not an ancestor of HEAD -- and both subjects run against it with the same cwd. Stubbing `git` would mean the two sides agreeing about a fake, and the interesting inputs here
are exactly the ones a fake gets wrong: `--sort=-v:refname` is git's own version
collation (`v0.9.0` before `v0.10.0`), and `merge-base --is-ancestor` is a real question about the object graph.

`gh` IS FAKED, because the ONLY thing it does here is answer `commits/<sha>/pulls`, and reaching the network would make the suite depend on a repository nobody controls. The fake is a router over per-SHA fixture files that applies the CALLER's own `--jq` through the real `jq`, the shape `.ci/rediacc_ci/tests/gates/test_gate_detect_bump_type.py` established, so both sides parse
the fixture
with one jq rather than two opinions about it.

THE CALL LOG IS COMPARED IN EVERY CASE, and for this script that is the whole point rather than a refinement. `patch` is both the correct answer for a release with no labels AND the output of all nine fallback paths, so a port that never called the API at all would agree with the twin on the printed word in most cases. The predecessor of this script was green for weeks doing
exactly that. Comparing which commits were looked up is what distinguishes a verdict
from a shrug.

BOTH DIRECTIONS ON THE LABEL MATCH: `bump-major` fires, `bump-majority` and `xbump-major` do not, and an OPEN PR carrying `bump-major` does not either.

K=5 LEDGER: `.ci/shadow/w7p6-detect-bump-type.observations.jsonl` -- five
distinct trees, `--assert --k 5` prints "equivalence holds over 5 distinct trees". Recorded in a disposable scratch repo outside this checkout (`--record` refuses a dirty tree), one scenario per tree.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.version import detect_bump_type as port

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "version" / "detect-bump-type.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "version" / "detect_bump_type.py"
BASH = shutil.which("bash") or "/bin/bash"

FAKE_GH = """#!/usr/bin/python3
import os
import subprocess
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as fh:
    fh.write("\\t".join(argv) + "\\n")

if os.environ.get("FAKE_GH_FAIL_ALL"):
    sys.stderr.write("fake gh: forced API failure\\n")
    sys.exit(1)

path = ""
jq_expr = ""
skip = False
for index, arg in enumerate(argv):
    if skip:
        skip = False
        continue
    if arg == "--jq":
        jq_expr = argv[index + 1]
        skip = True
    elif arg == "api" or arg.startswith("-"):
        continue
    elif not path:
        path = arg

if not path.endswith("/pulls") or "/commits/" not in path:
    sys.stderr.write("fake gh: unrouted path: %s\\n" % path)
    sys.exit(3)

sha = path.split("/commits/", 1)[1][: -len("/pulls")]
if sha in os.environ.get("FAKE_GH_FAIL_SHAS", "").split(","):
    sys.stderr.write("fake gh: forced failure for %s\\n" % sha)
    sys.exit(1)

fixtures = os.environ["FAKE_GH_FIXTURES"]
target = os.path.join(fixtures, "pulls-%s.json" % sha)
if not os.path.isfile(target):
    target = os.path.join(fixtures, "pulls-default.json")

proc = subprocess.run(["jq", "-r", jq_expr, target], check=False)
sys.exit(proc.returncode)
"""

# Driven, not guessed. common.sh needs `dirname`/`uname` at source time; the twin's own pipelines need `head`, `sed`, `wc` and `grep`; `git` and `jq` are the two real tools both sides depend on.
PATH_MINIMUM = ("dirname", "uname", "tr", "git", "jq", "head", "sed", "wc", "grep")


def merged_pr(number: int, labels: str = "") -> dict:
    return {
        "number": number,
        "merged_at": "2026-08-01T00:00:00Z",
        "state": "closed",
        "labels": [{"name": name} for name in labels.split(",") if labels],
    }


def open_pr(number: int, labels: str = "") -> dict:
    """Contains the commit, but nothing has been released from it, so its label describes a release that has not happened."""
    return {
        "number": number,
        "merged_at": None,
        "state": "open",
        "labels": [{"name": name} for name in labels.split(",") if labels],
    }


class World:
    """A real git repository, a fixture directory, and a call log per side."""

    def __init__(self, tmp_path: pathlib.Path) -> None:
        self.tmp = tmp_path
        self.repo = tmp_path / "repo"
        self.fixtures = tmp_path / "fixtures"
        self.repo.mkdir(parents=True, exist_ok=True)
        self.fixtures.mkdir(parents=True, exist_ok=True)
        (self.fixtures / "pulls-default.json").write_text("[]\n", encoding="utf-8")
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "differential@example.invalid")
        self.git("config", "user.name", "Differential")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args: str) -> str:
        proc = subprocess.run(
            ["git", "-C", str(self.repo), *args],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"},
        )
        assert proc.returncode == 0, f"git {args} failed: {proc.stderr}"
        return proc.stdout.strip()

    def commit(self, subject: str) -> str:
        with open(self.repo / "file.txt", "a", encoding="utf-8") as fh:
            fh.write(subject + "\n")
        self.git("add", "file.txt")
        self.git("commit", "-q", "-m", subject)
        return self.git("rev-parse", "HEAD")

    def pulls_for(self, sha: str, *prs: dict) -> None:
        (self.fixtures / ("pulls-%s.json" % sha)).write_text(
            json.dumps(list(prs)), encoding="utf-8"
        )

    def _bin(self, side: str, *, with_gh: bool) -> str:
        stub = self.tmp / f"{side}-bin"
        stub.mkdir(exist_ok=True)
        for name in PATH_MINIMUM:
            real = shutil.which(name)
            assert real is not None, f"{name} is missing from this machine"
            link = stub / name
            if not link.exists():
                link.symlink_to(real)
        if with_gh:
            fake = stub / "gh"
            fake.write_text(FAKE_GH, encoding="utf-8")
            fake.chmod(0o755)
        else:
            assert shutil.which("gh", path=str(stub)) is None, "gh leaked into the stub PATH"
        return str(stub)

    def run(
        self,
        subject: pathlib.Path,
        args: list[str],
        *,
        with_gh: bool = True,
        cwd: pathlib.Path | None = None,
        **env_overrides: str,
    ):
        side = "old" if subject.suffix == ".sh" else "new"
        call_log = self.tmp / f"{side}-gh-calls.log"
        call_log.write_text("", encoding="utf-8")
        env = {
            "PATH": self._bin(side, with_gh=with_gh),
            "HOME": str(self.tmp),
            "LC_ALL": "C",
            "LANG": "C",
            "PYTHONPATH": str(ROOT / ".ci"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "FAKE_GH_LOG": str(call_log),
            "FAKE_GH_FIXTURES": str(self.fixtures),
            "GITHUB_REPOSITORY": "acme/widget",
            "GH_TOKEN": "fake-token",
        }
        for key, value in env_overrides.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
        runner = [BASH] if subject.suffix == ".sh" else [sys.executable]
        proc = subprocess.run(
            [*runner, str(subject), *args],
            cwd=str(cwd or self.repo),
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=90,
        )
        calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
        return proc, calls

    def both(self, args: list[str] | None = None, **kwargs):
        args = ["--verbose"] if args is None else args
        old, old_calls = self.run(TWIN, args, **kwargs)
        new, new_calls = self.run(PORT, args, **kwargs)
        return old, new, old_calls, new_calls


def _assert_agree(old, new, label: str, old_calls=None, new_calls=None) -> None:
    assert new.returncode == old.returncode, (
        f"{label}: exit diverged: {old.returncode!r} vs {new.returncode!r}"
    )
    assert new.stdout == old.stdout, (
        f"{label}: stdout diverged:\nold: {old.stdout!r}\nnew: {new.stdout!r}"
    )
    assert new.stderr == old.stderr, (
        f"{label}: stderr diverged:\nold: {old.stderr!r}\nnew: {new.stderr!r}"
    )
    if old_calls is not None:
        assert new_calls == old_calls, (
            f"{label}: gh call sequence diverged:\nold: {old_calls}\nnew: {new_calls}"
        )


def _pulls_call(sha: str) -> str:
    return (
        f"api\trepos/acme/widget/commits/{sha}/pulls\t--jq\t"
        '.[] | select(.merged_at != null) | "\\(.number) \\((.labels // []) | '
        'map(.name) | join(","))"'
    )


def test_no_github_repository_is_a_fallback_without_touching_the_api(
    tmp_path: pathlib.Path,
) -> None:
    world = World(tmp_path)
    world.commit("work")
    old, new, old_calls, new_calls = world.both(GITHUB_REPOSITORY=None)
    assert old.returncode == 0
    assert old.stdout == "patch\n"
    assert "⚠ [detect-bump] Falling back to patch: GITHUB_REPOSITORY not set" in old.stderr
    assert old_calls == []
    _assert_agree(old, new, "no-repo", old_calls, new_calls)


def test_no_token_is_a_fallback(tmp_path: pathlib.Path) -> None:
    world = World(tmp_path)
    world.commit("work")
    old, new, old_calls, new_calls = world.both(GH_TOKEN=None)
    assert old.stdout == "patch\n"
    assert "GH_TOKEN not set" in old.stderr
    assert old_calls == []
    _assert_agree(old, new, "no-token", old_calls, new_calls)


def test_a_missing_gh_binary_is_a_fallback(tmp_path: pathlib.Path) -> None:
    world = World(tmp_path)
    world.commit("work")
    old, new, old_calls, new_calls = world.both(with_gh=False)
    assert old.stdout == "patch\n"
    assert "gh CLI not available" in old.stderr
    _assert_agree(old, new, "no-gh", old_calls, new_calls)


def test_without_verbose_the_only_output_is_the_word(tmp_path: pathlib.Path) -> None:
    """THE CONTRACT WITH THE CALLER: one word on stdout, and stderr silent, so `$(detect-bump-type.sh)` is safe to interpolate into a version calculation."""
    world = World(tmp_path)
    world.commit("work")
    old, new, old_calls, new_calls = world.both(args=[], GITHUB_REPOSITORY=None)
    assert old.stdout == "patch\n"
    assert old.stderr == "", f"the twin was noisy without --verbose: {old.stderr!r}"
    _assert_agree(old, new, "quiet", old_calls, new_calls)


def test_an_empty_repository_cannot_resolve_head(tmp_path: pathlib.Path) -> None:
    world = World(tmp_path)
    old, new, old_calls, new_calls = world.both()
    assert old.stdout == "patch\n"
    assert "cannot resolve HEAD" in old.stderr
    assert old_calls == []
    _assert_agree(old, new, "empty-repo", old_calls, new_calls)


def test_outside_a_git_repository_is_also_a_fallback(tmp_path: pathlib.Path) -> None:
    world = World(tmp_path)
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    old, new, old_calls, new_calls = world.both(cwd=outside)
    assert old.stdout == "patch\n"
    assert "cannot resolve HEAD" in old.stderr
    _assert_agree(old, new, "outside-repo", old_calls, new_calls)


def test_no_tag_scans_head_alone_and_a_minor_label_wins(tmp_path: pathlib.Path) -> None:
    world = World(tmp_path)
    first = world.commit("older work")
    head = world.commit("head work")
    world.pulls_for(head, merged_pr(556, "bump-minor"))
    world.pulls_for(first, merged_pr(555, "bump-major"))
    old, new, old_calls, new_calls = world.both()
    assert old.stdout == "minor\n"
    assert "HEAD alone (no usable version tag in this checkout)" in old.stderr
    assert old_calls == [_pulls_call(head)], (
        "an untagged checkout looked past HEAD, which would re-read consumed PRs"
    )
    _assert_agree(old, new, "head-alone", old_calls, new_calls)


def test_the_range_starts_after_the_latest_tag(tmp_path: pathlib.Path) -> None:
    """COMMITS BEFORE THE TAG ARE OUT OF RANGE ON PURPOSE: their labels were consumed by the release that tagged them, and re-reading them would escalate a version twice. The only evidence is the call log."""
    world = World(tmp_path)
    released = world.commit("released work")
    world.git("tag", "v1.0.0", released)
    after = world.commit("new work")
    world.pulls_for(released, merged_pr(1, "bump-major"))
    world.pulls_for(after, merged_pr(2, "bump-minor"))
    old, new, old_calls, new_calls = world.both()
    assert old.stdout == "minor\n"
    assert old_calls == [_pulls_call(after)], "a pre-tag commit was re-read"
    assert "Scanning 1 commit(s) in v1.0.0..HEAD" in old.stderr
    _assert_agree(old, new, "after-tag", old_calls, new_calls)


def test_an_empty_range_is_patch_not_a_wider_search(tmp_path: pathlib.Path) -> None:
    world = World(tmp_path)
    released = world.commit("released work")
    world.git("tag", "v1.0.0", released)
    world.pulls_for(released, merged_pr(1, "bump-major"))
    old, new, old_calls, new_calls = world.both()
    assert old.stdout == "patch\n"
    assert "no commits between v1.0.0 and HEAD" in old.stderr
    assert old_calls == []
    _assert_agree(old, new, "empty-range", old_calls, new_calls)


def test_a_tag_that_is_not_an_ancestor_falls_back_to_head_alone(
    tmp_path: pathlib.Path,
) -> None:
    """`git merge-base --is-ancestor` is a real question about the object graph, which is why this fixture is a real repository: the tag sits on a branch HEAD cannot reach."""
    world = World(tmp_path)
    base = world.commit("base")
    world.git("checkout", "-q", "-b", "side")
    side = world.commit("side work")
    world.git("tag", "v9.9.9", side)
    world.git("checkout", "-q", "main")
    head = world.commit("main work")
    world.pulls_for(head, merged_pr(3, "bump-minor"))
    assert base != side
    old, new, old_calls, new_calls = world.both()
    assert old.stdout == "minor\n"
    assert "HEAD alone (no usable version tag in this checkout)" in old.stderr
    _assert_agree(old, new, "unreachable-tag", old_calls, new_calls)


def test_git_version_collation_picks_the_highest_tag(tmp_path: pathlib.Path) -> None:
    """`--sort=-v:refname` is git's own version ordering: `v0.10.0` is newer
    than `v0.9.0`, which a byte sort gets backwards. The range description in the verbose log names the tag that was chosen."""
    world = World(tmp_path)
    old_release = world.commit("v0.9.0 work")
    world.git("tag", "v0.9.0", old_release)
    new_release = world.commit("v0.10.0 work")
    world.git("tag", "v0.10.0", new_release)
    head = world.commit("unreleased work")
    world.pulls_for(head, merged_pr(4, ""))
    old, new, old_calls, new_calls = world.both()
    assert "Scanning 1 commit(s) in v0.10.0..HEAD" in old.stderr
    assert old_calls == [_pulls_call(head)]
    _assert_agree(old, new, "version-collation", old_calls, new_calls)


def test_major_short_circuits_the_scan(tmp_path: pathlib.Path) -> None:
    """Priority is major > minor > patch, and the scan STOPS at the first major: the commits below it are never looked up. Only the call log shows it -- the printed word would be `major` either way."""
    world = World(tmp_path)
    released = world.commit("released")
    world.git("tag", "v1.0.0", released)
    older = world.commit("older")
    newer = world.commit("newer")
    world.pulls_for(newer, merged_pr(10, "bump-major"))
    world.pulls_for(older, merged_pr(11, "bump-minor"))
    old, new, old_calls, new_calls = world.both()
    assert old.stdout == "major\n"
    assert "major is the highest priority; short-circuiting the scan" in old.stderr
    assert old_calls == [_pulls_call(newer)], "the scan continued past a bump-major"
    _assert_agree(old, new, "short-circuit", old_calls, new_calls)


def test_an_open_pr_label_does_not_count(tmp_path: pathlib.Path) -> None:
    """`merged_at != null`. An open PR can contain the commit, and its label
    describes a release that has not happened. The API WAS reached, which is what separates this `patch` from a fallback."""
    world = World(tmp_path)
    head = world.commit("work")
    world.pulls_for(head, open_pr(20, "bump-major"))
    old, new, old_calls, new_calls = world.both()
    assert old.stdout == "patch\n"
    assert "no merged PRs found in HEAD alone" in old.stderr
    assert "Falling back to patch" not in old.stderr, "a reached API was reported as a fallback"
    assert old_calls == [_pulls_call(head)]
    _assert_agree(old, new, "open-pr", old_calls, new_calls)


def test_a_near_miss_label_does_not_count(tmp_path: pathlib.Path) -> None:
    """BOTH DIRECTIONS ON THE MATCH: `grep -qx` is whole-segment, so `bump-majority` and `xbump-minor` are not bumps."""
    world = World(tmp_path)
    head = world.commit("work")
    world.pulls_for(head, merged_pr(30, "bump-majority,xbump-minor,documentation"))
    old, new, old_calls, new_calls = world.both()
    assert old.stdout == "patch\n"
    assert "PR #30 labels: bump-majority,xbump-minor,documentation" in old.stderr
    _assert_agree(old, new, "near-miss-label", old_calls, new_calls)


def test_a_label_in_the_middle_of_the_list_still_counts(tmp_path: pathlib.Path) -> None:
    world = World(tmp_path)
    head = world.commit("work")
    world.pulls_for(head, merged_pr(31, "documentation,bump-minor,size/L"))
    old, new, old_calls, new_calls = world.both()
    assert old.stdout == "minor\n"
    _assert_agree(old, new, "middle-label", old_calls, new_calls)


def test_an_unlabelled_pr_reports_none(tmp_path: pathlib.Path) -> None:
    world = World(tmp_path)
    head = world.commit("work")
    world.pulls_for(head, merged_pr(32))
    old, new, old_calls, new_calls = world.both()
    assert "PR #32 labels: <none>" in old.stderr
    assert old.stdout == "patch\n"
    _assert_agree(old, new, "no-labels", old_calls, new_calls)


def test_the_same_pr_across_two_commits_is_logged_once(tmp_path: pathlib.Path) -> None:
    world = World(tmp_path)
    released = world.commit("released")
    world.git("tag", "v1.0.0", released)
    first = world.commit("first")
    second = world.commit("second")
    world.pulls_for(first, merged_pr(40, "bump-minor"))
    world.pulls_for(second, merged_pr(40, "bump-minor"))
    old, new, old_calls, new_calls = world.both()
    assert old.stdout == "minor\n"
    assert old.stderr.count("PR #40 labels:") == 1, "the dedupe stopped working"
    assert len(old_calls) == 2, "both commits are still looked up; only the PR is deduped"
    _assert_agree(old, new, "dedupe", old_calls, new_calls)


def test_one_failed_lookup_is_skipped_and_the_others_still_answer(
    tmp_path: pathlib.Path,
) -> None:
    world = World(tmp_path)
    released = world.commit("released")
    world.git("tag", "v1.0.0", released)
    first = world.commit("first")
    second = world.commit("second")
    world.pulls_for(first, merged_pr(50, "bump-minor"))
    old, new, old_calls, new_calls = world.both(FAKE_GH_FAIL_SHAS=second)
    assert old.stdout == "minor\n"
    assert "pulls failed, skipping" in old.stderr
    assert len(old_calls) == 2
    _assert_agree(old, new, "one-lookup-fails", old_calls, new_calls)


def test_every_lookup_failing_is_reported_as_a_fallback(tmp_path: pathlib.Path) -> None:
    """THE UNKNOWN-IS-NOT-FINE CASE. Nothing was checked, so the `patch` is labelled as a fallback rather than presented as a verdict."""
    world = World(tmp_path)
    world.commit("work")
    old, new, old_calls, new_calls = world.both(FAKE_GH_FAIL_ALL="1")
    assert old.stdout == "patch\n"
    assert "Falling back to patch: every commits/<sha>/pulls lookup failed" in old.stderr
    assert len(old_calls) == 1
    _assert_agree(old, new, "all-lookups-fail", old_calls, new_calls)


def test_max_commits_caps_the_range(tmp_path: pathlib.Path) -> None:
    """DETECT_BUMP_MAX_COMMITS is a bound on what a long release window costs in API calls, and it is applied by `git log -n`, so the CAPPED-OUT commit is never even a candidate."""
    world = World(tmp_path)
    released = world.commit("released")
    world.git("tag", "v1.0.0", released)
    oldest = world.commit("one")
    middle = world.commit("two")
    newest = world.commit("three")
    world.pulls_for(oldest, merged_pr(60, "bump-major"))
    old, new, old_calls, new_calls = world.both(DETECT_BUMP_MAX_COMMITS="2")
    assert old.stdout == "patch\n"
    assert "Scanning 2 commit(s) in v1.0.0..HEAD" in old.stderr
    assert old_calls == [_pulls_call(newest), _pulls_call(middle)]
    assert not any(oldest in call for call in old_calls), "the cap did not apply"
    _assert_agree(old, new, "max-commits", old_calls, new_calls)


def test_an_unknown_flag_is_ignored(tmp_path: pathlib.Path) -> None:
    """`for arg in "$@"` matches only `--verbose`; anything else is silently ignored, so a typo does not fail a release step."""
    world = World(tmp_path)
    world.commit("work")
    old, new, old_calls, new_calls = world.both(args=["--wat"], GITHUB_REPOSITORY=None)
    assert old.returncode == 0
    assert old.stdout == "patch\n"
    assert old.stderr == ""
    _assert_agree(old, new, "unknown-flag", old_calls, new_calls)


def test_pure_helpers() -> None:
    assert port.split_row("556 bump-minor,size/S") == ("556", "bump-minor,size/S")
    assert port.split_row("556") == ("556", "")
    assert port.split_row("556  two spaces") == ("556", " two spaces")
    assert port.has_label("a,bump-major,b", "bump-major")
    assert not port.has_label("bump-majority", "bump-major")
    assert not port.has_label("xbump-major", "bump-major")
    assert not port.has_label("", "bump-major")
    assert port.seen(" 1 2", "1")
    assert not port.seen(" 1 2", "12")
    assert not port.seen("", "1")
    assert port.pulls_path("a/b", "deadbeef") == "repos/a/b/commits/deadbeef/pulls"


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on the range selection -- the exact defect that made the PREVIOUS implementation of this script useless. The mutant scans HEAD alone even when a tag is usable, which still prints a plausible word and only shows up in the call log and the range description. Driven red, then the source is confirmed byte-identical and green."""
    world = World(tmp_path)
    released = world.commit("released")
    world.git("tag", "v1.0.0", released)
    first = world.commit("first")
    head = world.commit("head")
    world.pulls_for(first, merged_pr(70, "bump-minor"))
    world.pulls_for(head, merged_pr(71, ""))

    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace(
        '        if latest_tag and _git(["merge-base", "--is-ancestor", latest_tag, "HEAD"]).returncode == 0:',
        "        if False:",
    )
    assert mutated != original, "the line this plant targets is no longer present verbatim"
    mutant = tmp_path / "mutant.py"
    mutant.write_text(mutated, encoding="utf-8")

    old, old_calls = world.run(TWIN, ["--verbose"])
    bad, bad_calls = world.run(mutant, ["--verbose"])
    assert old.stdout == "minor\n", "the TWIN did not find the label; the plant is untested"
    assert len(old_calls) == 2
    assert bad.stdout == "patch\n", "the mutant still found the labelled PR"
    assert bad_calls == [_pulls_call(head)], "the mutant did not narrow the range"

    good, good_calls = world.run(PORT, ["--verbose"])
    assert good_calls == old_calls, "restored port no longer agrees with the twin"
    assert good.stdout == old.stdout
    assert good.stderr == old.stderr
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
