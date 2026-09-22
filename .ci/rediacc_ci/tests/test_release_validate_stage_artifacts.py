"""`rediacc_ci.release.validate_stage_artifacts` against the bytes its bash twin printed.

THE TWIN HAS BEEN DELETED. `.ci/scripts/release/validate-stage-artifacts.sh` had no call site outside its own usage header; the K=5 ledger `.ci/shadow/w7p5a-validate-stage-artifacts.observations.jsonl` holds five rows of equivalence over five distinct trees, and `goldens/validate-stage-artifacts/` holds the twin's OWN recorded bytes, captured on its last day in the tree. Each
golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them.

THE `$GITHUB_STEP_SUMMARY` FILE IS RECORDED TOO, under its own marker. It is this script's real product -- the streams carry only the `::error::` lines -- so a recording that held the streams alone would freeze the complaints and drop the report.

EVERY CASE HERE RUNS AGAINST AN ISOLATED `dist/` FIXTURE, never against this checkout's own `dist/` (which does not exist in a fresh checkout, and must not be created as a side effect of running a test suite). The recording was taken the same way. The fixture still carries a REAL copy of `.ci/scripts/lib/common.sh`, because the bash twin's `get_repo_root()` derived the root from
`common.sh`'s OWN file location (`${BASH_SOURCE[0]}`) and the recording depends on it having landed there; the Python port asks `rediacc_ci.paths.repo_root()`, which honours `$REDIACC_CI_ROOT`, so the new side just sets that env var and copies nothing.

`du` PRODUCES REAL, HOST-DEPENDENT BYTES (block-size rounding), so the recorded `| Pages bundle |` cell carries `<du-size>` wherever the twin printed a real measurement. `N/A` is NOT masked: it is a verdict both sides compute without touching `du` at all, and erasing the difference between a measurement and its absence would gut the case that exists to show it. The fixture root is
masked for the same reason it always is, and nothing else is touched.
"""

from __future__ import annotations

import os
import re
import shutil
from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

if TYPE_CHECKING:  # pathlib appears only in `tmp_path` annotations, never at runtime.
    import pathlib

TWIN_REL = ".ci/scripts/release/validate-stage-artifacts.sh"
COMMON_REL = ".ci/scripts/lib/common.sh"
MODULE = "validate_stage_artifacts"
SLUG = "validate-stage-artifacts"
SUM_MARK = "--- step-summary ---\n"

# ONLY a real `du` size is masked; the leading digit is what distinguishes a measurement from the `N/A` verdict beside it.
SIZE_RE = re.compile(r"(\| Pages bundle \| )[0-9][^|]*(\|)")

CASES = ("an-empty-dist", "a-full-dist-with-a-channel", "missing-event-name")


def _build_fixture(root: pathlib.Path, twin_root: str) -> None:
    """Copy just enough of the real tree for the recording's own root resolution to have landed on `root` instead of this checkout."""
    (root / ".ci" / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    (root / ".ci" / "scripts" / "release").mkdir(parents=True, exist_ok=True)
    shutil.copy2(os.path.join(twin_root, COMMON_REL), root / COMMON_REL)


def _full_dist(root: pathlib.Path) -> None:
    """One CLI binary, eight Linux packages across four formats, a pages bundle and both repo trees."""
    dist = root / "dist"
    (dist / "cli").mkdir(parents=True)
    (dist / "cli" / "rdc-linux-x64").write_bytes(b"x")
    pkg = dist / "packages"
    pkg.mkdir(parents=True)
    for name in (
        "a.deb",
        "b.deb",
        "a.rpm",
        "b.rpm",
        "a.apk",
        "b.apk",
        "a.pkg.tar.zst",
        "b.pkg.tar.zst",
    ):
        (pkg / name).write_bytes(b"x")
    (dist / "pages").mkdir(parents=True)
    (dist / "pages" / "index.html").write_bytes(b"x" * 1024)
    (dist / "repos" / "apt" / "dists").mkdir(parents=True)
    (dist / "repos" / "apt" / "dists" / "Release").write_bytes(b"x")
    (dist / "repos" / "rpm" / "repodata").mkdir(parents=True)
    (dist / "repos" / "rpm" / "repodata" / "repomd.xml").write_bytes(b"x")


def recorded(case: str) -> tuple[int, str, str, str]:
    """One golden, split back into exit code, stdout, stderr and the step summary."""
    body, summary = frozen.read(SLUG, case).split(SUM_MARK, 1)
    head, rest = body.split("\n--- stdout ---\n", 1)
    out, err = rest.split("--- stderr ---\n", 1)
    return int(head[len("exit: ") :]), out, err, summary


def run_port(root: pathlib.Path, env_extra: dict[str, str]) -> tuple[int, str, str, str]:
    """The port, over one fixture, masked the way the recording was masked."""
    summary = root / "new-summary.md"
    written = root / "new-output.txt"
    env = diff.env_for(
        **env_extra,
        GITHUB_STEP_SUMMARY=str(summary),
        GITHUB_OUTPUT=str(written),
        PYTHONPATH=os.path.join(diff.repo(), ".ci"),
        PYTHONDONTWRITEBYTECODE="1",
        REDIACC_CI_ROOT=str(root),
    )
    code, out, err = diff.bash_streams(
        "python3 -m rediacc_ci.release.%s" % MODULE, env=env, cwd=str(root), timeout=30
    )
    text = summary.read_text(encoding="utf-8") if summary.exists() else ""
    return (
        code,
        frozen.mask_root(out, root),
        frozen.mask_root(err, root),
        SIZE_RE.sub(r"\1<du-size> \2", frozen.mask_root(text, root)),
    )


def test_empty_dist_fails_with_the_vacuity_errors(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "fixture"
    _build_fixture(root, diff.repo())
    old = recorded("an-empty-dist")
    new = run_port(root, {"EVENT_NAME": "schedule", "NEXT_VERSION": "9.9.9", "CHANNEL": ""})
    assert old[0] == 1
    assert old[2] == ""
    assert "VACUOUS: No CLI artifacts found under dist/cli" in old[1]
    assert "Channel is empty for event 'schedule'" in old[1]
    assert "| CLI artifacts | 0 files |" in old[3]
    assert "| Pages bundle | N/A |" in old[3], "no dist/pages, so `du` was never reached"
    assert "Validation FAILED" in old[3]
    assert new == old


def test_full_dist_with_channel_passes(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "fixture"
    _build_fixture(root, diff.repo())
    _full_dist(root)
    old = recorded("a-full-dist-with-a-channel")
    new = run_port(root, {"EVENT_NAME": "push", "NEXT_VERSION": "1.2.3", "CHANNEL": "edge"})
    assert old[:3] == (0, "", "")
    assert "| CLI artifacts | 1 files |" in old[3]
    assert "| Linux packages | 8 files (deb:2 rpm:2 apk:2 arch:2) |" in old[3]
    assert "| Pages bundle | <du-size> |" in old[3], "dist/pages exists, so `du` produced a size"
    assert "N/A" not in old[3]
    assert "All validation passed. Ready for publish." in old[3]
    assert new == old


def test_missing_event_name_fails_the_same_way_reworded(tmp_path: pathlib.Path) -> None:
    """NOT BYTE-COMPARED, and the twin's recording says why: bash's own `${VAR:?msg}` diagnostic is line-numbered and names the shell, so the port has never matched it. `$GITHUB_STEP_SUMMARY` and `$GITHUB_OUTPUT` are always supplied (both point at real temp files), so the first genuinely-missing required var is `EVENT_NAME`."""
    root = tmp_path / "fixture"
    _build_fixture(root, diff.repo())
    old = recorded("missing-event-name")
    new = run_port(root, {})
    assert old[0] == 1
    assert new[0] == 1
    for stream in (old[2], new[2]):
        assert "EVENT_NAME" in stream
        assert "must be set" in stream


def test_the_corpus_and_the_goldens_are_the_same_set() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, set(CASES))


def test_the_recording_holds_both_verdicts_and_a_non_empty_report() -> None:
    """A recording of refusals only would agree with a port that never writes a step summary, which is this script's whole product."""
    codes = {recorded(case)[0] for case in CASES}
    assert codes == {0, 1}, "the recording must hold a green and a red"
    assert any(recorded(case)[3] for case in CASES), "no case recorded a step summary"
