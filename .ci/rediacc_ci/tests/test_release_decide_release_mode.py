"""`rediacc_ci.release.decide_release_mode` against the bytes its bash twin printed.

THE TWIN HAS BEEN DELETED. `.ci/scripts/release/decide-release-mode.sh` had no call site outside its own usage header; the K=5 ledger `.ci/shadow/w7p5a-decide-release-mode.observations.jsonl` holds five rows of equivalence over five distinct trees (`npx tsx scripts/lib/shadow-gate.ts --pair w7p5a-decide-release-mode --assert --k 5` -> "equivalence holds over 5 distinct trees"),
and `goldens/decide-release-mode/` holds the twin's OWN recorded bytes, captured on its last day in the tree. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

THE `$GITHUB_OUTPUT` FILE IS RECORDED TOO, under its own marker. It is this script's real product -- the two `::notice::` lines are commentary, the key=value pairs are what the workflow reads -- so a recording that held only the streams would freeze the commentary and drop the contract. Sibling of
`test_deploy_resolve_account_deploy_config.py`; see that file for why `/dev/stdout` is not used as `$GITHUB_OUTPUT` and why the missing-env-var path is checked for exit code and substance, not bytes.

WHAT IS MASKED, AND IT IS ONLY THIS: the fixture root, which is a fresh `tmp_path` per run and appears in bash's own `${VAR:?}` diagnostic. Nothing else is touched, and both streams stay separate throughout.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

if TYPE_CHECKING:  # pathlib appears only in `tmp_path` annotations, never at runtime.
    import pathlib

TWIN = ".ci/scripts/release/decide-release-mode.sh"
MODULE = "decide_release_mode"
SLUG = "decide-release-mode"
OUT_MARK = "--- github-output ---\n"

# name -> the environment the case runs under. The recording was taken through this same table.
CASES: dict[str, dict[str, str]] = {
    "workers-only": {"DEPLOY_WORKERS_ONLY": "true", "RELEASE_MODE": "patch"},
    "retry-mode": {"DEPLOY_WORKERS_ONLY": "false", "RELEASE_MODE": "retry"},
    "patch-mode": {"DEPLOY_WORKERS_ONLY": "false", "RELEASE_MODE": "patch"},
    "missing-deploy-workers-only": {"RELEASE_MODE": "patch"},
}


def recorded(case: str) -> tuple[int, str, str, str]:
    """One golden, split back into exit code, stdout, stderr and the output file."""
    body, github_output = frozen.read(SLUG, case).split(OUT_MARK, 1)
    head, rest = body.split("\n--- stdout ---\n", 1)
    out, err = rest.split("--- stderr ---\n", 1)
    return int(head[len("exit: ") :]), out, err, github_output


def run_port(tmp_path: pathlib.Path, env_extra: dict[str, str]) -> tuple[int, str, str, str]:
    """The port, over one fixture, with the fixture root masked out of both streams."""
    written = tmp_path / "new-output.txt"
    env = diff.env_for(
        **env_extra,
        GITHUB_OUTPUT=str(written),
        PYTHONPATH=".ci",
        PYTHONDONTWRITEBYTECODE="1",
    )
    code, out, err = diff.bash_streams(
        "python3 -m rediacc_ci.release.%s" % MODULE, env=env, timeout=30
    )
    got = written.read_text(encoding="utf-8") if written.exists() else ""
    return code, frozen.mask_root(out, tmp_path), frozen.mask_root(err, tmp_path), got


def test_workers_only_short_circuits_before_release_mode(tmp_path: pathlib.Path) -> None:
    old = recorded("workers-only")
    new = run_port(tmp_path, CASES["workers-only"])
    assert old[0] == 0
    assert old[2] == ""
    assert (
        old[1] == "::notice::Workers-only mode -- deploy Workers without version bump or publish\n"
    )
    assert old[3] == "retry_mode=false\nworkers_only=true\n"
    assert new == old


def test_retry_mode(tmp_path: pathlib.Path) -> None:
    old = recorded("retry-mode")
    new = run_port(tmp_path, CASES["retry-mode"])
    assert old[0] == 0
    assert old[2] == ""
    assert old[1] == "::notice::Retry mode -- will re-deploy current version without bumping\n"
    assert old[3] == "workers_only=false\nretry_mode=true\n"
    assert new == old


def test_patch_mode(tmp_path: pathlib.Path) -> None:
    old = recorded("patch-mode")
    new = run_port(tmp_path, CASES["patch-mode"])
    assert old[0] == 0
    assert old[2] == ""
    assert old[1] == "::notice::Release mode: patch bump -- will create new release\n"
    assert old[3] == "workers_only=false\nretry_mode=false\n"
    assert new == old


def test_missing_deploy_workers_only_fails_the_same_way_reworded(tmp_path: pathlib.Path) -> None:
    """NOT BYTE-COMPARED, and the twin's recording says why: bash's own `${VAR:?msg}` diagnostic is line-numbered and names the shell, so the port has never matched it. What both sides owe is the exit code and the substance, and the recording is what proves the twin owed it too."""
    old = recorded("missing-deploy-workers-only")
    new = run_port(tmp_path, CASES["missing-deploy-workers-only"])
    assert old[0] == 1
    assert new[0] == 1
    for stream in (old[2], new[2]):
        assert "DEPLOY_WORKERS_ONLY" in stream
        assert "must be set" in stream


def test_the_corpus_and_the_goldens_are_the_same_set() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_the_recording_holds_both_verdicts_and_a_non_empty_product() -> None:
    """A recording of refusals only would agree with a port that writes no output file at all, which is this script's whole product."""
    codes = {recorded(case)[0] for case in CASES}
    assert codes == {0, 1}, "the recording must hold a green and a red"
    assert any(recorded(case)[3] for case in CASES), "no case recorded a $GITHUB_OUTPUT write"
