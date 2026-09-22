"""Port of `.ci/scripts/test/gates/test-age-check.sh`, retired in W7 P5.

End-to-end tests for the suppression re-review clock: whether an allowlist / blocklist entry has outlived its age window, and whether a truncated git history can answer that question at all.

WHY THIS NO LONGER GOES THROUGH BASH. Until W7P5-c this file drove `.ci/scripts/lib/age-check.sh`, a delegating shim over `rediacc_ci.core.age`, because the shim's own seam (sourcing correctly, passing `$AGE_WARN_DAYS` / `$AGE_FAIL_DAYS`, translating the TAB-separated verdict line into an exit code) was the subject, not just the core it wrapped. That shim's only caller,
`.ci/scripts/quality/check-go-deps.sh`, was deleted in the same change, and the shim went with it -- nothing else sourced it. Its Python successor is `rediacc_ci.quality.go_deps.check_entry_age`, which composes `rediacc_ci.core.age.entry_age_days` and `.verdict` directly, in-process, with no shell in between. The cases below drive that composition and the core functions it calls,
on the same real git fixtures the twin used.

THE GIT FIXTURES ARE REAL REPOSITORIES WITH BACKDATED COMMITS, unchanged from the twin, because the subject reads `git log -S`. A fixture that is not a repository makes every case answer 0 for the same reason a broken one would, which is the "the control did not fire" shape rather than a finding.
"""

import pathlib

from rediacc_ci.core import age
from rediacc_ci.quality import go_deps
from rediacc_ci.tests.gates import harness

GIT_FIX = "install git; every case here needs a real repository with backdated commits"


def _git(gate, args: list[str], cwd) -> harness.RunResult:
    git = harness.require_tool("git", GIT_FIX)
    result = harness.run([git, *args], cwd=cwd)
    if result.rc != 0:
        gate.log_fail("git %s failed in %s: %s" % (" ".join(args), cwd, result.combined))
    return result


def make_fixture(gate, directory: pathlib.Path, age_days: int, content: str) -> None:
    """The twin's `make_fixture`: a repo whose single commit is `age_days` old."""
    directory.mkdir(parents=True, exist_ok=True)
    _git(gate, ["init", "-q"], directory)
    _git(gate, ["config", "user.email", "test@example.com"], directory)
    _git(gate, ["config", "user.name", "test"], directory)
    _git(gate, ["config", "commit.gpgsign", "false"], directory)
    (directory / "listfile").write_text(content + "\n", encoding="utf-8")
    _git(gate, ["add", "listfile"], directory)
    date = harness.require_tool("date", "install coreutils; the fixture backdates its commit")
    stamp = harness.run([date, "-u", "-d", "%d days ago" % age_days, "+%Y-%m-%dT%H:%M:%S"])
    if stamp.rc != 0:
        gate.log_fail("could not compute a backdate: %s" % stamp.combined)
    when = stamp.out.strip()
    git = harness.require_tool("git", GIT_FIX)
    commit = harness.run(
        [git, "commit", "-q", "-m", "fixture"],
        cwd=directory,
        env={"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when},
    )
    if commit.rc != 0:
        gate.log_fail("could not create the backdated commit: %s" % commit.combined)


def make_shallow_pair(gate, directory: pathlib.Path, age_days: int, content: str) -> None:
    """The twin's `make_shallow_pair`: one origin, one depth-1 clone, one full clone.

    The SECOND, recent commit is load-bearing. `--depth 1` cuts above whichever commit is newest, so without it the graft would land on the very commit that introduced the line and the shallow clone would still see it.
    """
    origin = directory / "origin"
    make_fixture(gate, origin, age_days, content)
    (origin / "other").write_text("later\n", encoding="utf-8")
    _git(gate, ["add", "other"], origin)
    _git(
        gate, ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "recent"], origin
    )
    _git(
        gate,
        ["clone", "-q", "--depth", "1", "file://%s" % origin, str(directory / "shallow")],
        directory,
    )
    _git(gate, ["clone", "-q", "file://%s" % origin, str(directory / "full")], directory)


def test_age_fresh_entry(gate, tmp_path):
    make_fixture(gate, tmp_path, 5, "ENTRY_FRESH")
    result = age.entry_age_days("listfile", "ENTRY_FRESH", root=tmp_path)
    # 5 days old -- may read as 4 or 5 depending on rounding; accept 4-6.
    if result < 4 or result > 6:
        gate.log_fail("expected ~5 day age, got %d" % result)
    gate.log_pass("fresh entry reports correct age")


def test_age_medium_entry_warns_only(gate, tmp_path):
    make_fixture(gate, tmp_path, 200, "ENTRY_WARN")
    failed = go_deps.check_entry_age("listfile", "ENTRY_WARN", "testid", root=tmp_path)
    gate.assert_eq(failed, False, "check_entry_age should pass (warn-only) on 200-day entry")
    gate.log_pass("200-day entry warns without failing")


def test_age_old_entry_hard_fails(gate, tmp_path):
    make_fixture(gate, tmp_path, 400, "ENTRY_OLD")
    result = age.entry_age_days("listfile", "ENTRY_OLD", root=tmp_path)
    if result < 399 or result > 401:
        gate.log_fail("expected ~400 day age, got %d" % result)
    failed = go_deps.check_entry_age("listfile", "ENTRY_OLD", "testid", root=tmp_path)
    if not failed:
        gate.log_fail("check_entry_age should fail on 400-day-old entry")
    gate.log_pass("400-day entry hard-fails")


def test_age_untracked_file_returns_zero(gate, tmp_path):
    (tmp_path / "floating-file").write_text("floating\n", encoding="utf-8")
    result = age.entry_age_days("floating-file", "floating", root=tmp_path)
    gate.assert_eq(result, 0, "untracked file returns 0 age")
    gate.log_pass("untracked file returns 0 age")


def test_age_truncated_history_cannot_verify(gate, tmp_path, monkeypatch):
    """A TRUNCATED history reports the graft's date, not the line's, so an old suppression looks new. Measured on the real repo before this was fixed: the github.com/docker/docker entry in .go-deps-upgrade-blocklist read 195 days on a full clone and 2 days on a truncated one, with AGE_WARN_DAYS at 180. The gate whose job is expiring stale suppressions expired nothing, in green.
    """
    make_shallow_pair(gate, tmp_path, 400, "ENTRY_OLD")

    # CONTROL FIRST: the same fixture with FULL history must measure the real age. Without this, -1 below could just mean "the fixture is broken".
    full_age = age.entry_age_days("listfile", "ENTRY_OLD", root=tmp_path / "full")
    if full_age < 390 or full_age > 410:
        gate.log_fail("CONTROL: full clone should measure ~400 days, got %d" % full_age)
    gate.log_pass("CONTROL: a full clone still measures the real age (~400 days)")

    graft = tmp_path / "shallow" / ".git" / "shallow"
    if not (graft.is_file() and graft.stat().st_size > 0):
        gate.log_fail("CONTROL: the shallow fixture carries no graft, so it proves nothing")
    shallow_age = age.entry_age_days("listfile", "ENTRY_OLD", root=tmp_path / "shallow")
    gate.assert_eq(shallow_age, -1, "a truncated history reports CANNOT VERIFY, not an age")
    gate.log_pass("a truncated history reports -1 rather than a young age")

    # And CANNOT VERIFY must not be silently swallowed: refuse in CI, warn out. `monkeypatch` is the whole reason this conversion is simpler than the bash twin's: it isolates and restores CI on its own, where the twin needed an
    # explicit `env_replace=True` because `harness.run`'s default OVERLAYS the
    # ambient environment and leaving a name out of `env` changes nothing -- the bug a GitHub runner caught in run 34970782616, read there.
    monkeypatch.setenv("CI", "true")
    in_ci_failed = go_deps.check_entry_age(
        "listfile", "ENTRY_OLD", "test-id", "fixture entry", root=tmp_path / "shallow"
    )
    gate.assert_eq(in_ci_failed, True, "CI refuses an unverifiable age")
    gate.log_pass("CI refuses an unverifiable age")

    monkeypatch.delenv("CI", raising=False)
    local_failed = go_deps.check_entry_age(
        "listfile", "ENTRY_OLD", "test-id", "fixture entry", root=tmp_path / "shallow"
    )
    gate.assert_eq(local_failed, False, "a local shallow clone warns rather than blocking")
    gate.log_pass("a local shallow clone warns rather than blocking")
