"""Differential: `rediacc_ci.release.advance_contract_floor` against its twin `.ci/scripts/release/advance-contract-floor.sh`.

A FIXTURE ROOT, NOT THIS CHECKOUT, AND THAT IS NOT OPTIONAL. On an advance the twin runs `git add`, `git commit` and `git push origin HEAD:main` in whatever `get_repo_root` resolves to -- and `get_repo_root` derives from COMMON.SH's own location, so running the twin out of this tree would target this tree. Every
case therefore copies both subjects into a temporary root whose layout gives the
two the SAME answer:

    <fix>/.ci/scripts/release/advance-contract-floor.sh   ../../.. -> <fix>
    <fix>/.ci/rediacc_ci/release/advance_contract_floor.py  parents[3] -> <fix>

`git` and `aws` are both RECORDING FAKES on a scratch PATH. Nothing reaches R2 and nothing reaches a git remote; the assertions are on the recorded argv, the streams, the exit code and the bytes left in the floor file.

THE FLOOR FILE IS RESET BETWEEN THE TWO SIDES. The twin MUTATES it on an advance, so running the port afterwards against the twin's output would compare an advance to a no-op and call it a divergence. `run_both` restores the input state before the second side, and asserts the two sides left identical bytes behind -- which is the only place the write itself is observable.

BOTH DEFECTS ARE PINNED. `test_defect_a_failed_aws_probe_is_reported_as_an_empty_bucket` drives an `aws` that exits 255 and asserts the twin says "no cli sentinels on R2" and exits 0; `test_defect_the_floor_file_is_written_before_git_runs` drives a failing `git` and asserts the tree is left modified. Reproduced because the acceptance rule for this wave is agreement with the live
twin; if either is repaired, the test goes red and names the port that must follow.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths
from rediacc_ci.release import advance_contract_floor as port
from rediacc_ci.release import local
from rediacc_ci.tests import differential as diff

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/release/advance-contract-floor.sh"
TWIN = ROOT / TWIN_REL
PORT = ROOT / ".ci" / "rediacc_ci" / "release" / "advance_contract_floor.py"
BASH = shutil.which("bash") or "/bin/bash"

# The smallest import closure the port needs, copied rather than reached through an absolute PYTHONPATH. `console_root()` resolves `__file__`, so a symlinked
# package would resolve back into the real checkout and the fixture would be a
# fiction. Verified by `test_the_fixture_root_is_not_this_checkout`.
PACKAGE_FILES = (
    "__init__.py",
    "log.py",
    "paths.py",
    "well_known.py",
    "core/__init__.py",
    "core/awscli.py",
    "core/common.py",
    "core/release_state_validator.py",
    "core/toolchain.py",
    "release/__init__.py",
    "release/advance_contract_floor.py",
)

FAKE_AWS = """#!/usr/bin/python3
import os
import sys

with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("aws\\t" + "\\t".join(sys.argv[1:]) + "\\n")

rc = int(os.environ.get("FAKE_AWS_RC", "0"))
if rc:
    sys.stderr.write(os.environ.get("FAKE_AWS_ERR", "Unable to locate credentials\\n"))
    sys.exit(rc)
sys.stdout.write(os.environ.get("FAKE_AWS_OUT", ""))
sys.exit(0)
"""

FAKE_GIT = """#!/usr/bin/python3
import os
import sys

argv = sys.argv[1:]
with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("git\\t" + "\\t".join(argv) + "\\n")

fail_on = os.environ.get("FAKE_GIT_FAIL_ON", "")
if fail_on and argv[:1] == [fail_on]:
    sys.stderr.write("fake git: %s refused\\n" % fail_on)
    sys.exit(int(os.environ.get("FAKE_GIT_RC", "3")))
sys.exit(0)
"""

# common.sh needs `dirname` and `uname` at source time; the twin uses `grep`, `head`, `sort` and `tail` (`printf` is a builtin), and release-state-validator.sh adds `tr` and `sed`. All of them must be reachable or the twin fails for a reason that has nothing to do with the subject -- `tail` was missing on the first run of this file and the twin died `line 61: tail: command not
# found`
# with rc=127, which is exactly the shape of a harness bug wearing a gate
# failure's clothes.
PATH_MINIMUM = ("dirname", "uname", "tr", "sed", "grep", "head", "sort", "tail")


def _fixture(tmp_path: pathlib.Path, floor_text: str | None) -> pathlib.Path:
    """A root both subjects resolve to, holding both subjects and the config."""
    fix = tmp_path / "fixture"
    (fix / ".ci" / "scripts" / "release").mkdir(parents=True, exist_ok=True)
    (fix / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    (fix / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    recording = diff.regolden_mode(TWIN_REL) == "bash"
    if recording:
        shutil.copy2(TWIN, fix / ".ci" / "scripts" / "release" / TWIN.name)
    shutil.copy2(
        ROOT / ".ci" / "config" / "well-known.env", fix / ".ci" / "config" / "well-known.env"
    )
    shutil.copy2(
        ROOT / ".ci" / "config" / "well-known.generated.sh",
        fix / ".ci" / "config" / "well-known.generated.sh",
    )
    for lib in ("common.sh", "release-state-validator.sh") if recording else ():
        shutil.copy2(ROOT / ".ci" / "scripts" / "lib" / lib, fix / ".ci" / "scripts" / "lib" / lib)
    for rel in PACKAGE_FILES:
        dst = fix / ".ci" / "rediacc_ci" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / ".ci" / "rediacc_ci" / rel, dst)
    floor = fix / ".ci" / "config" / "release-contract-floor.txt"
    if floor_text is None:
        floor.unlink(missing_ok=True)
    else:
        floor.write_text(floor_text, encoding="utf-8")
    return fix


def _bin(tmp_path: pathlib.Path, name: str, *, tools: bool = True) -> str:
    stub = tmp_path / name
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        link = stub / real_name
        if not link.exists():
            link.symlink_to(real)
    for tool, body in (("aws", FAKE_AWS), ("git", FAKE_GIT)):
        target = stub / tool
        if tools:
            target.write_text(body, encoding="utf-8")
            target.chmod(0o755)
        else:
            assert shutil.which(tool, path=str(stub)) is None, f"{tool} leaked into the stub PATH"
    return str(stub)


def _run(
    fix: pathlib.Path,
    tmp_path: pathlib.Path,
    side: str,
    *,
    tools: bool = True,
    drop_env: tuple[str, ...] = (),
    **extra: str,
):
    subject = (
        fix / ".ci" / "scripts" / "release" / TWIN.name
        if side == "old"
        else fix / ".ci" / "rediacc_ci" / "release" / PORT.name
    )
    call_log = tmp_path / f"{side}-calls.log"
    call_log.write_text("", encoding="utf-8")
    env = {
        "PATH": _bin(tmp_path, f"{side}-bin", tools=tools),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(fix / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_CALL_LOG": str(call_log),
        # A fixture endpoint and bucket. Even a bypassed fake would not name R2.
        "CLOUDFLARE_R2_ENDPOINT": "https://r2.invalid",
        "CLOUDFLARE_R2_ACCESS_KEY_ID": "AKIAFIXTURE",
        "CLOUDFLARE_R2_SECRET_ACCESS_KEY": "SECRETFIXTURE",
        "RELEASES_BUCKET": "widget-releases",
        "GIT_BOT_NAME": "Fixture Bot",
        "GIT_BOT_EMAIL": "bot@example.invalid",
    }
    env.update(extra)
    for name in drop_env:
        env.pop(name, None)
    runner = [BASH] if side == "old" else [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject)],
        # cwd is deliberately NOT the fixture: the twin `cd`s to the root it derives, and a port that relied on the caller's cwd would pass here only if the test handed it the answer.
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )
    calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
    return proc, calls


def _floor(fix: pathlib.Path) -> str | None:
    p = fix / ".ci" / "config" / "release-contract-floor.txt"
    return p.read_text(encoding="utf-8") if p.exists() else None


def _run_old(fix: pathlib.Path, tmp_path: pathlib.Path, **kw):
    """The twin's answer, from its golden (PLAN-retire-bash-oracles B3): streams, `git`/`aws` call log and the floor file it leaves, which is written back so the caller reads it exactly as it did when bash ran."""

    def bash():
        proc, calls = _run(fix, tmp_path, "old", **kw)
        return proc.returncode, proc.stdout, proc.stderr, calls, _floor(fix)

    rc, out, err, calls, floor = diff.twin_tuple(
        TWIN_REL, [repr(sorted(kw.items()))], bash, work=(tmp_path,)
    )
    path = fix / ".ci" / "config" / "release-contract-floor.txt"
    if floor is None:
        path.unlink(missing_ok=True)
    else:
        path.write_text(floor, encoding="utf-8")
    return subprocess.CompletedProcess([], rc, out, err), calls


def run_both(tmp_path: pathlib.Path, floor_text: str | None, **kw):
    """Drive both sides from the SAME input state and return both outcomes.

    The floor file is restored between the two runs because the twin mutates it on an advance; without the reset the port would be handed the twin's output as its input and every advance case would read as a divergence.
    """
    fix = _fixture(tmp_path, floor_text)
    old, old_calls = _run_old(fix, tmp_path, **kw)
    old_floor = _floor(fix)

    _fixture(tmp_path, floor_text)
    new, new_calls = _run(fix, tmp_path, "new", **kw)
    new_floor = _floor(fix)

    assert new_floor == old_floor, (
        f"the floor file diverged:\nold: {old_floor!r}\nnew: {new_floor!r}"
    )
    return old, new, old_calls, new_calls, old_floor


def run_new(tmp_path: pathlib.Path, floor_text: str | None, **kw):
    """The port alone, for the cases whose behavior deliberately left the twin: an advance no longer commits or pushes, so its goldens (which record the git calls) no longer apply. Returns `(proc, calls, floor)`."""
    fix = _fixture(tmp_path, floor_text)
    proc, calls = _run(fix, tmp_path, "new", **kw)
    return proc, calls, _floor(fix)


def _assert_no_git(calls: list[str]) -> None:
    """THE ACCEPTANCE: no git argv at all, so nothing can push console `main`."""
    assert not any(c.startswith("git\t") for c in calls), "the port ran git: %s" % calls
    assert not any("push" in c.split("\t") for c in calls), "the port pushed: %s" % calls


WROTE = "::notice::wrote .ci/config/release-contract-floor.txt in the working tree; commit it with the next PR\n"


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
            f"{label}: call sequence diverged:\nold: {old_calls}\nnew: {new_calls}"
        )


LIST_CALL = (
    "aws\ts3api\tlist-objects-v2\t--bucket\twidget-releases\t--prefix\tcli/v"
    "\t--endpoint-url\thttps://r2.invalid"
    "\t--query\tContents[?ends_with(Key, `/.released`)].Key\t--output\ttext"
)


def sentinels(*versions: str) -> str:
    """`aws --output text` packs an array onto ONE tab-joined line."""
    return "\t".join("cli/%s/.released" % v for v in versions) + "\n"


def test_the_ratchet_advances_in_the_working_tree_and_runs_no_git(
    tmp_path: pathlib.Path,
) -> None:
    proc, calls, floor = run_new(tmp_path, "v1.2.21\n", FAKE_AWS_OUT=sentinels("v1.3.0", "v1.4.0"))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout == "::notice::advancing ratchet v1.2.21 -> v1.3.0\n" + WROTE
    assert floor == "v1.3.0\n", "the new floor was not written"
    assert calls == [LIST_CALL]
    _assert_no_git(calls)


def test_the_oldest_sentinel_wins_not_the_first_key_listed(tmp_path: pathlib.Path) -> None:
    """`sort -uV | head -1`. R2 returns keys in lexical order, where `v1.10.0` precedes `v1.9.0`; the floor must be the VERSION-oldest, not the first key."""
    proc, calls, floor = run_new(
        tmp_path, "v1.0.0\n", FAKE_AWS_OUT=sentinels("v1.10.0", "v1.9.0", "v1.11.0")
    )
    assert proc.returncode == 0
    assert floor == "v1.9.0\n", "lexical order was used instead of version order"
    assert "advancing ratchet v1.0.0 -> v1.9.0" in proc.stdout
    _assert_no_git(calls)


def test_an_equal_observation_is_a_no_op_with_no_git_at_all(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls, floor = run_both(
        tmp_path, "v1.2.21\n", FAKE_AWS_OUT=sentinels("v1.2.21", "v1.3.0")
    )
    assert old.returncode == 0
    assert old.stdout == "::notice::ratchet already at v1.2.21 (>= observed v1.2.21); no change\n"
    assert floor == "v1.2.21\n", "a no-op run modified the tree"
    assert old_calls == [LIST_CALL], "a no-op run reached git"
    _assert_agree(old, new, "equal", old_calls, new_calls)


def test_an_older_observation_never_walks_the_ratchet_backwards(
    tmp_path: pathlib.Path,
) -> None:
    """THE SAFETY PROPERTY. A scrub that left only an old sentinel must NOT be able to lower the floor -- that is the whole reason the value is committed rather than re-derived."""
    old, new, old_calls, new_calls, floor = run_both(
        tmp_path, "v1.5.0\n", FAKE_AWS_OUT=sentinels("v1.2.0")
    )
    assert old.returncode == 0
    assert "ratchet already at v1.5.0 (>= observed v1.2.0); no change" in old.stdout
    assert floor == "v1.5.0\n"
    assert old_calls == [LIST_CALL]
    _assert_agree(old, new, "backwards", old_calls, new_calls)


def test_no_sentinels_at_all_is_a_skip(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls, floor = run_both(tmp_path, "v1.2.21\n", FAKE_AWS_OUT="\n")
    assert old.returncode == 0
    assert old.stdout == "::notice::no cli sentinels on R2; skipping ratchet advance\n"
    assert floor == "v1.2.21\n"
    _assert_agree(old, new, "no-sentinels", old_calls, new_calls)


def test_a_missing_floor_file_is_a_warning_and_a_clean_exit(tmp_path: pathlib.Path) -> None:
    old, new, old_calls, new_calls, floor = run_both(tmp_path, None)
    assert old.returncode == 0
    assert old.stdout == (
        "::warning::.ci/config/release-contract-floor.txt not present; skipping ratchet advance\n"
    )
    assert floor is None, "the missing file was created"
    assert old_calls == [], "R2 was consulted with no floor file to compare against"
    _assert_agree(old, new, "missing-floor", old_calls, new_calls)


def test_a_floor_file_with_no_semver_line_reads_as_unset(tmp_path: pathlib.Path) -> None:
    """`grep -E '^v[0-9]+\\.[0-9]+\\.[0-9]+$' | head -1` finds nothing, and the message then prints `<unset>` while COMPARING against `v0.0.0`. Two different defaults for one empty value, kept from the twin."""
    proc, calls, floor = run_new(
        tmp_path,
        "# the floor is not recorded yet\n\nv1.2.3-rc.1\n",
        FAKE_AWS_OUT=sentinels("v1.3.0"),
    )
    assert proc.returncode == 0
    assert proc.stdout == "::notice::advancing ratchet <unset> -> v1.3.0\n" + WROTE
    assert floor == "v1.3.0\n"
    _assert_no_git(calls)


def test_a_prerelease_sentinel_is_not_a_floor_candidate(tmp_path: pathlib.Path) -> None:
    """The sentinel filter is STRICT semver, so `v1.3.0-rc.1` is invisible and the floor is the oldest RELEASE sentinel."""
    proc, calls, floor = run_new(
        tmp_path, "v1.0.0\n", FAKE_AWS_OUT=sentinels("v1.3.0-rc.1", "v1.4.0")
    )
    assert proc.returncode == 0
    assert floor == "v1.4.0\n"
    _assert_no_git(calls)


def test_a_non_sentinel_key_under_the_prefix_is_ignored(tmp_path: pathlib.Path) -> None:
    proc, calls, floor = run_new(
        tmp_path,
        "v1.0.0\n",
        FAKE_AWS_OUT="cli/v1.2.0/rdc-linux-x64\tcli/v1.5.0/.released\n",
    )
    assert proc.returncode == 0
    assert floor == "v1.5.0\n", "a binary key was mistaken for a sentinel"
    _assert_no_git(calls)


def test_defect_a_failed_aws_probe_is_reported_as_an_empty_bucket(
    tmp_path: pathlib.Path,
) -> None:
    """THE VACUITY DEFECT, PINNED. `rsv_list_sentinels` sends aws's stderr to
    /dev/null and wraps its pipeline in `{ ... } || true`, so an expired
    credential, a DNS fault and a genuinely scrubbed bucket all produce

        ::notice::no cli sentinels on R2; skipping ratchet advance

    and exit 0 -- on the script whose entire reason for existing is to defend a high-water mark against a scrub. Reproduced because agreement with the live twin is the deliverable; repaired, this test goes red and names the port that must follow.
    """
    old, new, old_calls, new_calls, floor = run_both(
        tmp_path,
        "v1.2.21\n",
        FAKE_AWS_RC="255",
        FAKE_AWS_ERR="Unable to locate credentials\n",
    )
    assert old.returncode == 0, "the twin now fails on an unreachable bucket"
    assert old.stdout == "::notice::no cli sentinels on R2; skipping ratchet advance\n"
    assert old.stderr == "", "the twin now surfaces aws's own diagnostic"
    assert floor == "v1.2.21\n"
    assert port.PROBE_FAILURE_READS_AS_EMPTY_BUCKET
    _assert_agree(old, new, "aws-fails", old_calls, new_calls)


def test_a_git_that_would_refuse_everything_is_never_asked(tmp_path: pathlib.Path) -> None:
    """The old half-applied-ratchet defect (file written, then a failing `git commit` leaving the tree modified) cannot happen: no git runs, so a `git` that refuses every verb changes neither the exit code nor the call log."""
    proc, calls, floor = run_new(
        tmp_path,
        "v1.0.0\n",
        FAKE_AWS_OUT=sentinels("v1.6.0"),
        FAKE_GIT_FAIL_ON="commit",
        FAKE_GIT_RC="3",
    )
    assert proc.returncode == 0
    assert floor == "v1.6.0\n"
    assert proc.stderr == ""
    _assert_no_git(calls)


def test_a_no_op_run_runs_no_git_either(tmp_path: pathlib.Path) -> None:
    """The no-advance paths ran no git in the twin; they still run none. Together with the advance cases, no argv of the fake `git` exists in any case, so none can push `main`."""
    for floor_text, out in (("v1.5.0\n", sentinels("v1.2.0")), ("v1.5.0\n", "\n")):
        proc, calls, floor = run_new(tmp_path, floor_text, FAKE_AWS_OUT=out)
        assert proc.returncode == 0
        assert floor == floor_text
        _assert_no_git(calls)


def test_missing_aws_is_refused_before_missing_git(tmp_path: pathlib.Path) -> None:
    fix = _fixture(tmp_path, "v1.0.0\n")
    old, old_calls = _run_old(fix, tmp_path, tools=False)
    new, new_calls = _run(fix, tmp_path, "new", tools=False)
    assert old.returncode == 1
    assert old.stderr == "✗ Required command 'aws' is not available\n"
    assert "git" not in old.stderr, "the order of the two require_cmd calls changed"
    _assert_agree(old, new, "missing-aws", old_calls, new_calls)


def test_each_required_variable_is_demanded_in_order(tmp_path: pathlib.Path) -> None:
    """DIVERGENCE 1 IS ASSERTED, NOT ASSUMED. `${VAR:?msg}` is a bash diagnostic
    carrying the twin's path and line number; the port names itself instead. The stream, the exit code, the order and the absence of any aws or git call must all agree. The twin also demanded GIT_BOT_NAME and GIT_BOT_EMAIL; with no commit the port does not, which `test_the_git_identity_is_no_longer_demanded` pins."""
    for name in port.REQUIRED_ENV:
        fix = _fixture(tmp_path, "v1.0.0\n")
        old, old_calls = _run_old(fix, tmp_path, drop_env=(name,))
        new, new_calls = _run(fix, tmp_path, "new", drop_env=(name,))
        assert old.returncode == 1 == new.returncode, name
        assert old.stdout == "" == new.stdout, name
        assert name in old.stderr, name
        assert name in new.stderr, name
        assert "must be set" in old.stderr, name
        assert "must be set" in new.stderr, name
        assert old_calls == [] == new_calls, f"{name}: a tool ran without its input"
        assert new.stderr.startswith("rediacc_ci.release.advance_contract_floor: "), (
            f"{name}: the port stopped naming itself"
        )
        assert ": line " in old.stderr, (
            f"{name}: the twin no longer emits a bash line-numbered diagnostic; "
            "divergence 1 in the port's docstring needs re-checking"
        )


def test_the_git_identity_is_no_longer_demanded(tmp_path: pathlib.Path) -> None:
    assert "GIT_BOT_NAME" not in port.REQUIRED_ENV
    assert "GIT_BOT_EMAIL" not in port.REQUIRED_ENV
    proc, calls, floor = run_new(
        tmp_path,
        "v1.0.0\n",
        drop_env=("GIT_BOT_NAME", "GIT_BOT_EMAIL"),
        FAKE_AWS_OUT=sentinels("v1.2.0"),
    )
    assert proc.returncode == 0, proc.stderr
    assert floor == "v1.2.0\n"
    _assert_no_git(calls)


def test_the_floor_lags_the_oldest_sentinel_and_one_run_closes_it(
    tmp_path: pathlib.Path,
) -> None:
    """The lag `release.cd_preflight --checks c` warns about is closed by this module writing the file; a second run is then a no-op."""
    fix = _fixture(tmp_path, "v1.0.0\n")
    first, _ = _run(fix, tmp_path, "new", FAKE_AWS_OUT=sentinels("v1.2.0"))
    again, _ = _run(fix, tmp_path, "new", FAKE_AWS_OUT=sentinels("v1.2.0"))
    assert "advancing ratchet v1.0.0 -> v1.2.0" in first.stdout
    assert "no change" in again.stdout
    assert _floor(fix) == "v1.2.0\n"


def test_in_a_ci_job_the_discarded_write_is_a_warning_not_a_commit_order(
    tmp_path: pathlib.Path,
) -> None:
    """A CI runner's working tree dies with the job, so the run names main's floor as still lagging instead of telling the reader to commit a file that no longer exists."""
    proc, calls, floor = run_new(
        tmp_path, "v1.2.21\n", FAKE_AWS_OUT=sentinels("v1.3.0"), GITHUB_ACTIONS="true"
    )
    assert proc.returncode == 0, proc.stderr
    assert WROTE not in proc.stdout
    assert "::warning::" in proc.stdout
    assert "discards" in proc.stdout
    assert "stays v1.2.21 until a PR commits v1.3.0" in proc.stdout
    assert floor == "v1.3.0\n"
    _assert_no_git(calls)


def test_the_local_release_runs_the_floor_in_this_checkout() -> None:
    """The release clone is rebuilt every run, so a floor written there would be lost like a CI runner's."""
    (row,) = [s for s in local.STEPS if s.id == "contract-floor"]
    assert row.cwd == "root"


def test_an_empty_variable_is_refused_like_an_unset_one(tmp_path: pathlib.Path) -> None:
    """`${VAR:?}` fires on set-but-EMPTY, which is what an unfilled workflow
    input actually looks like."""
    proc, calls, _floor_text = run_new(tmp_path, "v1.0.0\n", CLOUDFLARE_R2_ENDPOINT="")
    assert proc.returncode == 1
    assert "CLOUDFLARE_R2_ENDPOINT" in proc.stderr
    assert calls == []


def test_the_fixture_root_is_not_this_checkout(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY ON THE HARNESS ITSELF. Every case above asserts on a floor file and on git calls; if the port resolved its root back to this checkout, those assertions would be about the real tree and it would have run `git push origin HEAD:main` against it. The port is asked where it thinks the root is, out of band. (The twin's half of this check went with the twin: its answers are frozen in a golden that was recorded from this fixture.)"""
    fix = _fixture(tmp_path, "v1.0.0\n")
    port_root = subprocess.run(
        [
            sys.executable,
            "-c",
            "import rediacc_ci.release.advance_contract_floor as m; print(m.console_root())",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
        env={
            "PYTHONPATH": str(fix / ".ci"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
        },
    ).stdout.strip()

    assert port_root == str(fix), f"the port resolved to {port_root}, not the fixture"
    assert port_root != str(ROOT), "the port would have committed to this checkout"


def test_pure_helpers() -> None:
    assert port.read_floor("v1.2.3\n") == "v1.2.3"
    assert port.read_floor("# note\nv1.2.3\nv1.9.9\n") == "v1.2.3"
    assert port.read_floor("") == ""
    assert port.read_floor("v1.2.3-rc.1\n") == ""
    assert port.read_floor("1.2.3\n") == ""

    assert port.newer_of("v1.2.21", "v1.3.0") == "v1.3.0"
    assert port.newer_of("v1.3.0", "v1.2.21") == "v1.3.0"
    assert port.newer_of("v1.9.0", "v1.10.0") == "v1.10.0", "lexical order leaked in"
    assert port.newer_of("v1.2.3", "v1.2.3") == "v1.2.3"
    assert port.newer_of("v0.0.0", "v0.0.1") == "v0.0.1"


def test_decide_is_the_ratchet_rule() -> None:
    assert port.decide("v1.0.0", "") == (
        False,
        "::notice::no cli sentinels on R2; skipping ratchet advance",
    )
    assert port.decide("v1.0.0", "v1.0.0") == (
        False,
        "::notice::ratchet already at v1.0.0 (>= observed v1.0.0); no change",
    )
    assert port.decide("v1.5.0", "v1.2.0") == (
        False,
        "::notice::ratchet already at v1.5.0 (>= observed v1.2.0); no change",
    )
    assert port.decide("v1.0.0", "v1.1.0") == (
        True,
        "::notice::advancing ratchet v1.0.0 -> v1.1.0",
    )
    # The empty floor compares as v0.0.0 and PRINTS as <unset>.
    assert port.decide("", "v0.0.1") == (True, "::notice::advancing ratchet <unset> -> v0.0.1")
    assert port.decide("", "v0.0.0") == (
        False,
        "::notice::ratchet already at <unset> (>= observed v0.0.0); no change",
    )


def test_planted_defect_is_caught(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY, planted on the monotonicity test itself -- the one line whose removal turns a ratchet into a follower. The mutant advances the floor DOWNWARD to an older observation, which is exactly the scrub this file exists to survive, and it does it while printing a perfectly plausible ::notice:: line. Driven red, then the source is confirmed byte-identical and green."""
    original = PORT.read_text(encoding="utf-8")
    mutated = original.replace(
        "    if newer_of(compare_to, oldest) == compare_to:\n",
        "    if False:\n",
    )
    assert mutated != original, "the line this plant targets is no longer present verbatim"

    fix = _fixture(tmp_path, "v1.5.0\n")
    (fix / ".ci" / "rediacc_ci" / "release" / PORT.name).write_text(mutated, encoding="utf-8")
    bad, _bad_calls = _run(fix, tmp_path, "new", FAKE_AWS_OUT=sentinels("v1.2.0"))
    assert _floor(fix) == "v1.2.0\n", "the mutant did not walk the ratchet backwards"
    assert WROTE in bad.stdout, "the mutant did not reach the write"
    assert bad.returncode == 0, "the plant is invisible in the exit code, as intended"

    fix = _fixture(tmp_path, "v1.5.0\n")
    old, old_calls = _run_old(fix, tmp_path, FAKE_AWS_OUT=sentinels("v1.2.0"))
    assert _floor(fix) == "v1.5.0\n", "the TWIN advanced backwards; the plant is untested"
    assert old_calls == [LIST_CALL]
    assert bad.stdout != old.stdout

    fix = _fixture(tmp_path, "v1.5.0\n")
    good, good_calls = _run(fix, tmp_path, "new", FAKE_AWS_OUT=sentinels("v1.2.0"))
    assert good_calls == old_calls, "restored port no longer agrees with the twin"
    assert good.stdout == old.stdout
    assert _floor(fix) == "v1.5.0\n"
    assert PORT.read_text(encoding="utf-8") == original, (
        "port source must be restored byte-identical"
    )
