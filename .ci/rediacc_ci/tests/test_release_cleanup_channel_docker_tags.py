"""Differential: `rediacc_ci.release.cleanup_channel_docker_tags` against its twin `.ci/scripts/release/cleanup-channel-docker-tags.sh`.

NEITHER SIDE RUNS IN THIS CHECKOUT. The twin resolves the deleter as `$SCRIPT_DIR/../docker/cleanup_staging.py` (agent/plans/PLAN-w7p4w-docker-cutover.md Stage 5 cut the twin's own call site from `cleanup-staging.sh` over to this Python entry point; the fixture below tracks that, not the pre-cutover name),
with no override hook, and that script talks to GHCR through `gh api --method
DELETE`. So every case builds a throwaway console tree per side at the real relative depths, drops a RECORDING STUB at `.ci/scripts/docker/cleanup_staging.py`, and runs the subject out of that tree. The real deleter is never on any path either side can reach.

THE STEP SUMMARY IS THE OBSERVABLE, not stdout. This script's whole product is a markdown block appended to `$GITHUB_STEP_SUMMARY`; stdout and stderr carry only whatever the deleter itself printed, inherited rather than captured. So every case compares the summary FILE byte for byte, and the deleter's own two streams as well, and the call log on top of that.

THE PRODUCTION PATH IS THE ONE THAT CALLS NOTHING, which is worth stating because it looks like a bug and is not. `cleanup-staging.sh` accepts only `staging-*` tags by design, so a stray call cannot delete a real tag, and `CHANNEL` is `edge` or `stable`. The guard therefore rejects it on EVERY release and the deleter is never invoked; the twin's header is emphatic that this is a
KNOWN GAP with its own summary wording, not the token-scope problem the header used to claim. `test_edge_takes_the_known_gap_branch_and_calls_ nothing` pins exactly that, call log included.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import typing

from rediacc_ci import paths

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN = ROOT / ".ci" / "scripts" / "release" / "cleanup-channel-docker-tags.sh"
PORT = ROOT / ".ci" / "rediacc_ci" / "release" / "cleanup_channel_docker_tags.py"
COMMON = ROOT / ".ci" / "scripts" / "lib" / "common.sh"
BASH = shutil.which("bash") or "/bin/bash"

# Records argv[1:] ONLY, never `$0`: the twin invokes the deleter through a path containing `/../` and the port through the normalised one, so a stub echoing its own name would manufacture a difference that is not one.
FAKE_CLEANUP_STAGING = """#!/usr/bin/python3
import os
import sys

with open(os.environ["FAKE_LOG"], "a") as fh:
    fh.write("call: cleanup_staging.py " + " ".join(sys.argv[1:]) + "\\n")

rc = int(os.environ.get("FAKE_CLEANUP_RC", "0"))
if rc == 0:
    sys.stdout.write("deleted 3 image tags\\n")
else:
    sys.stderr.write("gh: HTTP 403 (missing delete:packages)\\n")
sys.exit(rc)
"""

KNOWN_GAP_WHY = (
    "cleanup-staging.sh only deletes `staging-*` tags by design, so a channel tag can never "
    "be removed through it. This is a KNOWN GAP, not a token-scope problem, and it is "
    "non-critical: a channel tag left in GHCR is harmless."
)
FAILED_WHY = "The delete call failed; check that GH_TOKEN carries `delete:packages`."


def _fixture(tmp_path: pathlib.Path, side: str, *, with_deleter: bool = True) -> pathlib.Path:
    """One throwaway console tree holding both subjects at their real depths."""
    root = tmp_path / ("tree-%s" % side)
    for rel in (
        (".ci", "scripts", "release"),
        (".ci", "scripts", "lib"),
        (".ci", "scripts", "docker"),
        (".ci", "rediacc_ci", "release"),
    ):
        (root / os.path.join(*rel)).mkdir(parents=True, exist_ok=True)

    shutil.copy2(TWIN, root / ".ci" / "scripts" / "release" / TWIN.name)
    shutil.copy2(PORT, root / ".ci" / "rediacc_ci" / "release" / PORT.name)
    shutil.copy2(COMMON, root / ".ci" / "scripts" / "lib" / "common.sh")
    if with_deleter:
        deleter = root / ".ci" / "scripts" / "docker" / "cleanup_staging.py"
        deleter.write_text(FAKE_CLEANUP_STAGING, encoding="utf-8")
        deleter.chmod(0o755)
    return root


def _run(
    tmp_path: pathlib.Path,
    side: str,
    *,
    with_deleter: bool = True,
    seed_summary: str | None = None,
    no_summary_var: bool = False,
    **extra: str,
) -> tuple[int, str, str, list[str], str | None]:
    root = _fixture(tmp_path, side, with_deleter=with_deleter)
    call_log = tmp_path / ("%s-calls.log" % side)
    call_log.write_text("", encoding="utf-8")
    summary = root / "step-summary.md"
    if seed_summary is not None:
        summary.write_text(seed_summary, encoding="utf-8")

    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "TMPDIR": str(tmp_path),
        "LC_ALL": "C",
        "LANG": "C",
        "NO_COLOR": "1",
        "PYTHONPATH": str(root / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "FAKE_LOG": str(call_log),
    }
    if not no_summary_var:
        env["GITHUB_STEP_SUMMARY"] = str(summary)
    env.update(extra)
    for key, value in list(env.items()):
        if value is None:
            del env[key]

    if side == "old":
        subject = root / ".ci" / "scripts" / "release" / TWIN.name
        runner = [BASH]
    else:
        subject = root / ".ci" / "rediacc_ci" / "release" / PORT.name
        runner = [sys.executable]
    proc = subprocess.run(
        [*runner, str(subject)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )
    calls = [line for line in call_log.read_text(encoding="utf-8").splitlines() if line]
    written = summary.read_text(encoding="utf-8") if summary.exists() else None
    return proc.returncode, proc.stdout, proc.stderr, calls, written


def run_both(tmp_path: pathlib.Path, **kw) -> tuple[tuple, tuple]:
    return _run(tmp_path, "old", **kw), _run(tmp_path, "new", **kw)


def assert_agree(old: tuple, new: tuple, label: str, *, stderr: bool = True) -> None:
    o_rc, o_out, o_err, o_calls, o_sum = old
    n_rc, n_out, n_err, n_calls, n_sum = new
    assert n_rc == o_rc, "%s: exit diverged: %d vs %d (old %r, new %r)" % (
        label,
        o_rc,
        n_rc,
        o_err,
        n_err,
    )
    assert n_sum == o_sum, "%s: the step summary diverged:\nold: %r\nnew: %r" % (
        label,
        o_sum,
        n_sum,
    )
    assert n_out == o_out, "%s: stdout diverged:\nold: %r\nnew: %r" % (label, o_out, n_out)
    if stderr:
        assert n_err == o_err, "%s: stderr diverged:\nold: %r\nnew: %r" % (label, o_err, n_err)
    assert n_calls == o_calls, "%s: call sequence diverged:\nold: %s\nnew: %s" % (
        label,
        o_calls,
        n_calls,
    )


def _block(*lines: str) -> str:
    return "## Cleanup Channel Tags\n\n" + "".join(line + "\n" for line in lines)


# --------------------------------------------------------------------------- The controls on the harness ---------------------------------------------------------------------------


def test_the_fixture_carries_a_stub_deleter_not_the_real_one(tmp_path: pathlib.Path) -> None:
    """The control on the control: prove the real deleter is out of reach."""
    root = _fixture(tmp_path, "control")
    deleter = root / ".ci" / "scripts" / "docker" / "cleanup_staging.py"
    assert deleter.is_file()
    text = deleter.read_text(encoding="utf-8")
    assert "FAKE_LOG" in text, "the fixture deleter is not the stub"
    assert "gh api" not in text, "the real deleter reached the fixture tree"
    real = ROOT / ".ci" / "scripts" / "docker" / "cleanup_staging.py"
    assert real.is_file(), "the real deleter moved; the port's path constant needs re-deriving"


def test_both_subjects_exist() -> None:
    assert TWIN.is_file(), "the bash twin moved: %s" % TWIN
    assert PORT.is_file(), "the port moved: %s" % PORT


# --------------------------------------------------------------------------- The branch production actually takes ---------------------------------------------------------------------------


def test_edge_takes_the_known_gap_branch_and_calls_nothing(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, CHANNEL="edge")
    assert old[0] == 0, "the twin is non-critical by design and must still exit 0"
    assert old[4] == _block("**Channel tag NOT cleaned up:** edge", KNOWN_GAP_WHY)
    assert old[1] == ""
    assert old[2] == ""
    assert old[3] == [], "the deleter was invoked for a non-staging tag"
    assert_agree(old, new, "edge")


def test_stable_takes_the_same_branch(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, CHANNEL="stable")
    assert old[0] == 0
    assert "**Channel tag NOT cleaned up:** stable" in old[4]
    assert old[3] == []
    assert_agree(old, new, "stable")


def test_a_bare_staging_without_the_dash_is_still_rejected(tmp_path: pathlib.Path) -> None:
    """`^staging-` includes the hyphen. A prefix test that dropped it would let a tag literally named `staging` through to the deleter."""
    old, new = run_both(tmp_path, CHANNEL="staging")
    assert old[3] == []
    assert "**Channel tag NOT cleaned up:** staging" in old[4]
    assert_agree(old, new, "bare-staging")


def test_staging_must_be_a_prefix_not_a_substring(tmp_path: pathlib.Path) -> None:
    """`edge-staging-1` contains `staging-` but does not start with it."""
    old, new = run_both(tmp_path, CHANNEL="edge-staging-1")
    assert old[3] == [], "an unanchored match let a non-staging tag reach the deleter"
    assert "**Channel tag NOT cleaned up:** edge-staging-1" in old[4]
    assert_agree(old, new, "substring-staging")


# --------------------------------------------------------------------------- The two branches that do call the deleter ---------------------------------------------------------------------------


def test_a_staging_tag_is_deleted_and_reported(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, CHANNEL="staging-abc123", FAKE_CLEANUP_RC="0")
    assert old[0] == 0
    assert old[4] == _block("**Channel tag cleaned up:** staging-abc123")
    assert old[3] == ["call: cleanup_staging.py --tag staging-abc123"]
    assert old[1] == "deleted 3 image tags\n", "the deleter's stdout is inherited, not swallowed"
    assert_agree(old, new, "staging-ok")


def test_a_failed_delete_is_reported_and_still_exits_zero(tmp_path: pathlib.Path) -> None:
    """Non-critical by design: the failure lands in the summary, not the exit code."""
    old, new = run_both(tmp_path, CHANNEL="staging-abc123", FAKE_CLEANUP_RC="1")
    assert old[0] == 0
    assert old[4] == _block("**Failed to clean up channel tag:** staging-abc123", FAILED_WHY)
    assert old[3] == ["call: cleanup_staging.py --tag staging-abc123"]
    assert old[2] == "gh: HTTP 403 (missing delete:packages)\n"
    assert_agree(old, new, "staging-failed")


def test_a_nonzero_exit_other_than_one_is_still_a_failure(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, CHANNEL="staging-abc123", FAKE_CLEANUP_RC="7")
    assert old[0] == 0
    assert "**Failed to clean up channel tag:**" in old[4]
    assert_agree(old, new, "staging-rc7")


def test_a_missing_deleter_falls_through_to_the_failure_block(tmp_path: pathlib.Path) -> None:
    """`command not found` is a non-zero status like any other.

    STDERR IS EXCLUDED FROM THIS ONE COMPARISON, and only this one: bash says `line 62: <path>: No such file or directory` while the port says `<path>: No such file or directory`. The summary block, the exit code and the empty call log all agree, which is what a reader of the step summary sees. A port that let `FileNotFoundError` escape would instead abort with a traceback BEFORE
    writing the failure block, so this case is the one that proves it does not.
    """
    old, new = run_both(tmp_path, with_deleter=False, CHANNEL="staging-abc123", FAKE_CLEANUP_RC="0")
    assert old[0] == 0
    assert old[4] == _block("**Failed to clean up channel tag:** staging-abc123", FAILED_WHY)
    assert "No such file or directory" in old[2]
    assert "No such file or directory" in new[2]
    assert "Traceback" not in new[2]
    assert_agree(old, new, "missing-deleter", stderr=False)


# --------------------------------------------------------------------------- The summary file itself ---------------------------------------------------------------------------


def test_the_block_is_appended_to_an_existing_summary(tmp_path: pathlib.Path) -> None:
    """`>>`, not `>`. A port that truncated would erase every earlier step."""
    seed = "## Earlier Step\n\nsomething a previous step wrote\n"
    old, new = run_both(tmp_path, seed_summary=seed, CHANNEL="edge")
    assert old[4].startswith(seed), "the twin truncated the summary"
    assert old[4] == seed + _block("**Channel tag NOT cleaned up:** edge", KNOWN_GAP_WHY)
    assert_agree(old, new, "append")


def test_a_missing_summary_file_is_created(tmp_path: pathlib.Path) -> None:
    """`>>` creates. The workflow always pre-creates it; a hand run does not."""
    old, new = run_both(tmp_path, CHANNEL="edge")
    assert old[4] is not None
    assert_agree(old, new, "create")


# --------------------------------------------------------------------------- Refusals, before the summary is touched ---------------------------------------------------------------------------


def test_missing_channel_refuses_and_writes_nothing(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, CHANNEL=None)
    assert old[0] == 1
    assert old[4] is None, "the twin wrote a heading before refusing"
    assert new[0] == 1
    assert new[4] is None, "the port wrote a heading before refusing"
    assert "CHANNEL" in old[2]
    assert "must be set" in old[2]
    assert "CHANNEL" in new[2]
    assert "must be set" in new[2]
    assert old[3] == []
    assert new[3] == []


def test_empty_channel_refuses_like_an_unset_one(tmp_path: pathlib.Path) -> None:
    """`${CHANNEL:?}` is the colon form: empty refuses too."""
    old, new = run_both(tmp_path, CHANNEL="")
    assert old[0] == 1
    assert new[0] == 1
    assert old[4] is None
    assert new[4] is None
    assert "CHANNEL" in old[2]
    assert "CHANNEL" in new[2]


def test_missing_step_summary_refuses(tmp_path: pathlib.Path) -> None:
    old, new = run_both(tmp_path, no_summary_var=True, CHANNEL="edge")
    assert old[0] == 1
    assert new[0] == 1
    assert "GITHUB_STEP_SUMMARY" in old[2]
    assert "must be set" in old[2]
    assert "GITHUB_STEP_SUMMARY" in new[2]
    assert "must be set" in new[2]
    assert old[3] == []
    assert new[3] == []


def test_channel_is_validated_before_the_summary_path(tmp_path: pathlib.Path) -> None:
    """Order matters: with both absent, both sides must name CHANNEL first."""
    old, new = run_both(tmp_path, no_summary_var=True, CHANNEL=None)
    assert "CHANNEL" in old[2]
    assert "GITHUB_STEP_SUMMARY" not in old[2]
    assert "CHANNEL" in new[2]
    assert "GITHUB_STEP_SUMMARY" not in new[2]
    assert old[0] == new[0] == 1


# --------------------------------------------------------------------------- Anti-vacuity ---------------------------------------------------------------------------


def test_the_harness_actually_compared_something(tmp_path: pathlib.Path) -> None:
    """A stub that never ran, or a summary never written, would pass everything above."""
    old, new = run_both(tmp_path, CHANNEL="staging-abc123", FAKE_CLEANUP_RC="0")
    assert len(old[3]) == 1, "the deleter stub never ran"
    assert len(new[3]) == 1, "the deleter stub never ran"
    assert old[4], "no step summary was written by either side"
    assert new[4], "no step summary was written by either side"
    assert len(old[4].splitlines()) == 3
