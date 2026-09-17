"""Port of `.ci/scripts/test/gates/test-age-check.sh`.

Unit tests for `.ci/scripts/lib/age-check.sh`, the library that decides whether a suppression entry has outlived its re-review window.

WHY THE PORT STILL GOES THROUGH BASH. The subject is a bash library today, and it is a DELEGATING SHIM over `rediacc_ci.core.age`. A port that imported the Python core directly would be testing the half that is already Python and would go green on a tree where the shim had stopped loading, stopped passing `$AGE_WARN_DAYS`, or stopped translating the verdict line. The twin's whole
subject is that seam, so
every case here drives `bash -c 'source age-check.sh; <call>'` exactly as the twin
does, and the Python core is exercised THROUGH it.

WHY EACH CALL IS ITS OWN `bash -c`, the same argument `test_gate_verify_version` makes: the twin sources the library once into its own shell and every case shares that state. A Python port has no shell to source into, so the library is re-sourced per call. Slower, and strictly more honest -- no case can leave a variable behind
for the next one, which matters here because the library marks
`AGE_WARN_DAYS` / `AGE_FAIL_DAYS` `readonly`.

THE GIT FIXTURES ARE REAL REPOSITORIES WITH BACKDATED COMMITS, unchanged from the twin, because the subject reads `git log -S`. A fixture that is not a repository makes every case answer 0 for the same reason a broken one would, which is the "the control did not fire" shape rather than a finding.
"""

import os
import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-age-check.sh"

LIB = paths.from_root(".ci", "scripts", "lib", "age-check.sh")

GIT_FIX = "install git; every case here needs a real repository with backdated commits"


def _git(gate, args: list[str], cwd) -> harness.RunResult:
    git = harness.require_tool("git", GIT_FIX)
    result = harness.run([git, *args], cwd=cwd)
    if result.rc != 0:
        gate.log_fail("git %s failed in %s: %s" % (" ".join(args), cwd, result.combined))
    return result


def source_and_run(
    gate, snippet: str, cwd, env: dict[str, str] | None = None, env_replace: bool = False
):
    """`source age-check.sh` then run `snippet`, in a fresh shell, at `cwd`.

    A missing subject is a LOUD failure and never a skip: the twin's `source` would abort the whole file, and a port that quietly reported nothing would be the vacuous green this directory refuses.

    `env_replace` IS FORWARDED because an OVERLAY CANNOT UNSET A VARIABLE. `harness.run` builds `dict(os.environ)` and then `.update(env)`, so handing it a dict with a name left OUT changes nothing at all -- the ambient value survives. That is only invisible on a host where the name was already unset. See the `CI` case in test_age_truncated_history_cannot_verify.
    """
    if not LIB.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(LIB))
    bash = harness.require_tool("bash", "install bash; the subject IS a bash library")
    return harness.run(
        [bash, "-c", 'source "%s"\n%s' % (os.fspath(LIB), snippet)],
        cwd=cwd,
        env=env,
        env_replace=env_replace,
    )


def entry_age_days(gate, cwd, path: str, pattern: str) -> int:
    result = source_and_run(gate, 'entry_age_days "%s" "%s"' % (path, pattern), cwd)
    text = result.out.strip()
    if not text.lstrip("-").isdigit():
        gate.log_fail(
            "entry_age_days printed %r (rc=%d, stderr=%r) instead of an integer; the "
            "shim is not reaching rediacc_ci.core.age" % (text, result.rc, result.err)
        )
    return int(text)


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
    age = entry_age_days(gate, tmp_path, "listfile", "ENTRY_FRESH")
    # 5 days old -- may read as 4 or 5 depending on rounding; accept 4-6.
    if age < 4 or age > 6:
        gate.log_fail("expected ~5 day age, got %d" % age)
    gate.log_pass("fresh entry reports correct age")


def test_age_medium_entry_warns_only(gate, tmp_path):
    make_fixture(gate, tmp_path, 200, "ENTRY_WARN")
    result = source_and_run(
        gate, "check_entry_age listfile ENTRY_WARN testid >/dev/null 2>&1", tmp_path
    )
    gate.assert_exit_code(0, result.rc, "check_entry_age should pass (warn-only) on 200-day entry")
    gate.log_pass("200-day entry warns without failing")


def test_age_old_entry_hard_fails(gate, tmp_path):
    make_fixture(gate, tmp_path, 400, "ENTRY_OLD")
    age = entry_age_days(gate, tmp_path, "listfile", "ENTRY_OLD")
    if age < 399 or age > 401:
        gate.log_fail("expected ~400 day age, got %d" % age)
    result = source_and_run(
        gate, "check_entry_age listfile ENTRY_OLD testid >/dev/null 2>&1", tmp_path
    )
    if result.rc == 0:
        gate.log_fail("check_entry_age should fail on 400-day-old entry")
    gate.log_pass("400-day entry hard-fails")


def test_age_untracked_file_returns_zero(gate, tmp_path):
    (tmp_path / "floating-file").write_text("floating\n", encoding="utf-8")
    result = source_and_run(
        gate, "entry_age_days floating-file floating 2>/dev/null || echo 0", tmp_path
    )
    gate.assert_eq(result.out.strip(), "0", "untracked file returns 0 age")
    gate.log_pass("untracked file returns 0 age")


def test_age_truncated_history_cannot_verify(gate, tmp_path):
    """A TRUNCATED history reports the graft's date, not the line's, so an old
    suppression looks new. Measured on the real repo before this was fixed: the github.com/docker/docker entry in .go-deps-upgrade-blocklist read 195 days on a full clone and 2 days on a truncated one, with AGE_WARN_DAYS at 180. The gate whose job is expiring stale suppressions expired nothing, in green.
    """
    make_shallow_pair(gate, tmp_path, 400, "ENTRY_OLD")

    # CONTROL FIRST: the same fixture with FULL history must measure the real age. Without this, -1 below could just mean "the fixture is broken".
    full_age = entry_age_days(gate, tmp_path / "full", "listfile", "ENTRY_OLD")
    if full_age < 390 or full_age > 410:
        gate.log_fail("CONTROL: full clone should measure ~400 days, got %d" % full_age)
    gate.log_pass("CONTROL: a full clone still measures the real age (~400 days)")

    graft = tmp_path / "shallow" / ".git" / "shallow"
    if not (graft.is_file() and graft.stat().st_size > 0):
        gate.log_fail("CONTROL: the shallow fixture carries no graft, so it proves nothing")
    shallow_age = entry_age_days(gate, tmp_path / "shallow", "listfile", "ENTRY_OLD")
    gate.assert_eq(shallow_age, -1, "a truncated history reports CANNOT VERIFY, not an age")
    gate.log_pass("a truncated history reports -1 rather than a young age")

    # And CANNOT VERIFY must not be silently swallowed: refuse in CI, warn out.
    in_ci = source_and_run(
        gate,
        "check_entry_age listfile ENTRY_OLD test-id 'fixture entry' >/dev/null 2>&1",
        tmp_path / "shallow",
        env={"CI": "true"},
    )
    gate.assert_eq(in_ci.rc, 1, "CI refuses an unverifiable age")
    gate.log_pass("CI refuses an unverifiable age")

    # `env -i` is the WRONG tool for unsetting one name: the subject needs PATH to find python3 and git. So the whole environment is copied and CI dropped
    # from the copy -- and it is passed with `env_replace=True`, which is the
    # part this case got wrong for as long as it existed.
    #
    # `harness.run`'s default OVERLAYS: `dict(os.environ)` then `.update(env)`. Leaving a name out of `env` therefore removes nothing, and the ambient value survives. On a developer machine `CI` is unset anyway, so the case passed for a reason that had nothing to do with the code. A GitHub runner
    # exports `CI=true`, the subject saw it (`[[ "${CI:-}" == "true" ]]`, the
    # literal value and nothing else), refused instead of warning, and this assertion read `expected '0', got '1'` in run 34970782616.
    #
    # env_replace=True is the documented way to hand over a WHOLE environment,
    # PATH included, which is exactly what local_env is.
    local_env = {k: v for k, v in os.environ.items() if k != "CI"}
    local = source_and_run(
        gate,
        "check_entry_age listfile ENTRY_OLD test-id 'fixture entry' >/dev/null 2>&1",
        tmp_path / "shallow",
        env=local_env,
        env_replace=True,
    )
    gate.assert_eq(local.rc, 0, "a local shallow clone warns rather than blocking")
    gate.log_pass("a local shallow clone warns rather than blocking")
