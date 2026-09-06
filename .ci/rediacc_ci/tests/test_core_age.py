"""`rediacc_ci.core.age` against real git fixtures, and against its bash shim.

WHY THE FIXTURES ARE REAL REPOSITORIES WITH BACKDATED COMMITS. The subject is
"how long ago was this line added", and there is no way to ask that of a mock
that would also catch the defect the module exists for. `.ci/scripts/test/gates/
test-age-check.sh` -- which still passes UNCHANGED against the port, and is the
end-to-end proof -- builds fixtures exactly this way; these cases add the parts
a bash harness cannot reach cheaply: the verdict table as a pure function, the
shim's TAB-separated contract, and the shim's fail-closed behaviour.

THE ONE DEFECT EVERY CASE HERE IS ABOUT, restated because it is easy to lose.
Measured 2026-09-03: `git log --diff-filter=A` on a TRUNCATED history attributes
every line at the graft boundary to the boundary commit. The real entry
github.com/docker/docker in .go-deps-upgrade-blocklist read 195 days on a full
clone (added 2026-02-20) and 2 days on a truncated one (added 2026-09-01). With
AGE_WARN_DAYS at 180 that entry silently stopped warning, and at
AGE_FAIL_DAYS=365 it could never fail. So `test_truncated_history_cannot_verify`
below is not an edge case, it is the whole point, and it carries its control:
the SAME fixture cloned fully must still measure the real age, or a -1 would
only mean the fixture was broken.
"""

import subprocess
import textwrap
import time

import pytest

from rediacc_ci import paths
from rediacc_ci.core import age
from rediacc_ci.tests import differential as diff

SHIM = ".ci/scripts/lib/age-check.sh"

# Ambient git configuration is switched OFF, not merely overridden: /dev/null is
# a valid empty config file to git. Without this the fixture inherits the
# developer's init.defaultBranch, commit template and gpg signing, and passes or
# fails per machine.
ISOLATED = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
}


def _git(args, cwd, extra_env=None):
    env = diff.env_for(**ISOLATED)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )


def _fixture(path, age_days: int, content: str, extra_commit: bool = False):
    """A repository whose `listfile` line was added `age_days` ago."""
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q"], path)
    (path / "listfile").write_text(content + "\n")
    _git(["add", "listfile"], path)
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - age_days * 86400))
    _git(
        ["commit", "-q", "-m", "fixture"],
        path,
        {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp},
    )
    if extra_commit:
        # A RECENT second commit, so `clone --depth 1` grafts above the commit
        # that added the line. Without it the shallow clone still contains it
        # and the truncation case proves nothing.
        (path / "other").write_text("later\n")
        _git(["add", "other"], path)
        _git(["commit", "-q", "-m", "recent"], path)
    return path


def test_fresh_entry_reports_a_small_age(tmp_path) -> None:
    repo = _fixture(tmp_path / "fresh", 5, "ENTRY_FRESH")
    assert 4 <= age.entry_age_days("listfile", "ENTRY_FRESH", root=repo) <= 6


def test_old_entry_reports_its_real_age(tmp_path) -> None:
    repo = _fixture(tmp_path / "old", 400, "ENTRY_OLD")
    assert 399 <= age.entry_age_days("listfile", "ENTRY_OLD", root=repo) <= 401


def test_untracked_file_on_a_complete_history_is_age_zero(tmp_path) -> None:
    """0, not -1: on a COMPLETE history a line git has never seen is genuinely new.

    The distinction is the whole reason -1 exists. Collapsing the two would
    either expire brand-new suppressions or excuse ancient ones.
    """
    repo = _fixture(tmp_path / "untracked", 5, "ENTRY")
    (repo / "floating").write_text("floating\n")
    assert age.entry_age_days("floating", "floating", root=repo) == 0


def test_truncated_history_cannot_verify(tmp_path) -> None:
    """A graft must yield CANNOT_VERIFY, and the control proves the fixture works."""
    origin = _fixture(tmp_path / "origin", 400, "ENTRY_OLD", extra_commit=True)
    shallow = tmp_path / "shallow"
    full = tmp_path / "full"
    _git(["clone", "-q", "--depth", "1", f"file://{origin}", str(shallow)], tmp_path)
    _git(["clone", "-q", f"file://{origin}", str(full)], tmp_path)

    # CONTROL FIRST: without it, -1 below could just mean the fixture is broken.
    assert 390 <= age.entry_age_days("listfile", "ENTRY_OLD", root=full) <= 410
    assert age.grafts_file(root=full) is None

    assert age.grafts_file(root=shallow) is not None
    assert age.entry_age_days("listfile", "ENTRY_OLD", root=shallow) == age.CANNOT_VERIFY


@pytest.mark.parametrize(
    ("days", "ci", "level"),
    [
        (0, False, "ok"),
        (180, False, "ok"),
        (181, False, "warn"),
        # 365 is WARN, not ok: the bash was `if ((age > FAIL)) ... elif ((age >
        # WARN))`, so the fail threshold does not cancel the warn one. Writing
        # "ok" here was the first draft's mistake and the table caught it.
        (365, False, "warn"),
        (366, False, "error"),
        (-1, False, "warn"),
        (-1, True, "error"),
        (366, True, "error"),
    ],
)
def test_verdict_boundaries(days: int, ci: bool, level: str) -> None:
    """The thresholds are `>`, not `>=`, on both rungs, and CI only moves -1.

    Written as a table because the two off-by-one boundaries (180/181 and
    365/366) are the values a rewrite gets wrong, and a case that only tests 200
    and 400 cannot see it.
    """
    assert age.verdict(days, ci=ci).level == level


def test_verdict_wording_carries_the_actionable_remedy() -> None:
    """The strings are read by a human staring at a red job, so they are pinned."""
    v = age.verdict(age.CANNOT_VERIFY, ci=True)
    assert v.level == "error"
    assert "fetch-depth: 0" in v.remedy
    assert "filter: blob:none" in v.remedy
    assert v.failed is True
    assert age.verdict(200).failed is False


def test_shim_verdict_line_is_tab_separated_and_carries_the_exit_code(
    tmp_path,
) -> None:
    """The shim reads three TAB fields and returns the exit code. Both, together.

    A change that kept the fields and dropped the exit code would leave
    `check_entry_age` emitting an error and returning 0 -- a gate that prints
    its own failure and passes.
    """
    repo = _fixture(tmp_path / "old", 400, "ENTRY_OLD")
    script = textwrap.dedent(f"""
        cd {_q(str(repo))}
        PYTHONPATH={_q(str(paths.ci_dir()))} python3 -m rediacc_ci.core.age \\
            verdict listfile ENTRY_OLD 180 365 ''
    """)
    rc, out, err = diff.bash_streams(script, env=diff.env_for())
    assert rc == 1, err
    level, message, remedy = out.rstrip("\n").split("\t")
    assert level == "error"
    assert "yearly re-review required" in message
    assert "BLOCKER" in remedy


def test_shim_emits_through_emit_advisory_and_returns_one(tmp_path) -> None:
    """End to end through the real bash entry point, on a real fixture."""
    repo = _fixture(tmp_path / "old", 400, "ENTRY_OLD")
    shim = str(paths.from_root(SHIM))
    rc, out, err = diff.bash_streams(
        f"cd {_q(str(repo))}; source {_q(shim)}; check_entry_age listfile ENTRY_OLD test-id 'name'",
        env=diff.env_for(),
    )
    assert rc == 1
    assert "400 days old" in out + err


def test_shim_control_a_fresh_entry_emits_nothing_and_returns_zero(tmp_path) -> None:
    """CONTROL for the case above: an emitter that always emits passes that one."""
    repo = _fixture(tmp_path / "fresh", 5, "ENTRY_FRESH")
    shim = str(paths.from_root(SHIM))
    rc, out, err = diff.bash_streams(
        f"cd {_q(str(repo))}; source {_q(shim)}; check_entry_age listfile ENTRY_FRESH test-id 'name'",
        env=diff.env_for(),
    )
    assert rc == 0, err
    assert out.strip() == ""


def test_shim_fails_closed_when_the_package_is_unreachable(tmp_path) -> None:
    """No package, no answer. See the ports shim for why there is no fallback."""
    shim = str(paths.from_root(SHIM))
    rc, out, err = diff.bash_streams(
        f"source {_q(shim)}; entry_age_days listfile ENTRY",
        env=diff.env_for(REDIACC_CI_ROOT=str(tmp_path)),
    )
    assert rc != 0
    assert out.strip() == ""
    assert "cannot find rediacc_ci" in err


def _q(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"
