"""Port of `.ci/scripts/test/gates/test-go-deps-probe-failure.sh`, retired in W7 P5.

The probe-failure guard, driven against `.ci/scripts/quality/check-go-deps.sh`'s OWN RECORDED BYTES rather than against a live copy of it.

WHAT BROKE, ORIGINALLY. The gate gathered its data with

    go list -u -m -json all 2>/dev/null | jq ... 2>/dev/null || true

so ANY failure of either command produced an empty result set, which is byte-identical to a clean tree. The gate then printed "All Go direct dependencies are up-to-date" and exited 0. It was not reporting that deps were fine; it was reporting nothing at all, in the voice of success.

Observed 2026-07-27: a local `npm run ci` reported all-clean while CI failed on the SAME commit for an outdated csi-spec. The gate was not disagreeing with CI --
`go list` was exiting 1 locally (go.mod requires go >= 1.25, the toolchain on
PATH was 1.24) and the failure was being swallowed.

WHILE BOTH COPIES EXISTED this file drove the tracked `.ci/scripts/quality/check-go-deps.sh` directly, using a fake `go` on PATH (a real toolchain cannot easily produce the EMPTY-but-successful case) over the SAME five fixture shapes below, and compared its bytes against the Python port's. W7 P5 then deleted the twin, having recorded its output for each shape into
`goldens/w7p5-go-deps-probe-failure/`, captured from the tracked script on its last day in the tree. Every case below now compares the PORT against that recording. Nothing here is a hand-written expectation.

WHY A PATH SHIM survives the cutover unchanged: reproducing the original required a specific broken toolchain, and the fake `go` reproduces every failure mode deterministically -- fail, empty, garbage and clean/outdated -- on any runner, for either implementation.

STREAMS ARE MERGED IN THE RECORDING BUT NOT IN THE COMPARISON. The twin redirected `>"$FIXTURE/out.txt" 2>&1`, so `frozen.render` holds them under separate markers and this file concatenates them back with plain string addition before asserting, which is the same shape the differential used.

NO `xdist_group`. Every case runs inside its own temporary fixture tree, PATH is set per-subprocess, and nothing module-global moves.
"""

import os
import pathlib
import shutil
import stat
import subprocess

import pytest

from rediacc_ci import paths
from rediacc_ci.tests import frozen

SLUG = "w7p5-go-deps-probe-failure"
PORT = paths.from_root(".ci", "scripts", "quality", "check_go_deps.py")

# The five behaviours of the fake `go`, unchanged from the twin's own fixture: `clean` emits only the main module, which is what a real `go list -m` always emits at minimum; `empty` is the mode a genuinely broken toolchain cannot easily produce and is the subtlest of the five.
GO_SHIM = """#!/bin/bash
mode="%s"
case "$mode" in
    fail)      echo "go: go.mod requires go >= 1.25.0 (running go 1.24.0)" >&2; exit 1 ;;
    empty)     exit 0 ;;
    garbage)   echo "this is not json"; exit 0 ;;
    clean)     printf '%%s\\n' '{"Path":"example.com/fakemod","Version":"v1.0.0","Main":true}' ;;
    outdated)  printf '%%s\\n' \
'{"Path":"github.com/some/dep","Version":"v1.0.0",\
"Update":{"Version":"v1.1.0","Time":"2020-01-01T00:00:00Z"}}' ;;
esac
"""

CASES = [
    ("healthy-clean-tree-passes", "clean"),
    ("healthy-outdated-still-fails", "outdated"),
    ("probe-failure-is-not-up-to-date", "fail"),
    ("probe-failure-surfaces-the-real-error", "fail"),
    ("empty-output-is-a-failure-not-a-clean-tree", "empty"),
    ("unparsable-output-is-a-failure", "garbage"),
]


def build_fixture(root: pathlib.Path, mode: str) -> pathlib.Path:
    """The minimal tree the PORT reads: no bash libraries to mirror any more.

    `scripts/lib/release-age.ts` and `.npmrc` DO still have to be copied in, though: `ReleaseAge` resolves the delegate under `REDIACC_CI_ROOT`, and a fixture without it falls through to the fail-closed branch, which turns the 2020-dated "outdated" fixture into a DEFERRED one and the whole case into a false pass. Same trap `go_deps.selftest`'s own `build()` documents.
    """
    (root / "private" / "fakemod").mkdir(parents=True)
    (root / "private" / "fakemod" / "go.mod").write_text(
        "module example.com/fakemod\n\ngo 1.25\n", encoding="utf-8"
    )
    (root / ".ci" / "policy").mkdir(parents=True)
    (root / ".ci" / "policy" / ".go-deps-upgrade-blocklist").write_text("", encoding="utf-8")
    (root / "scripts" / "lib").mkdir(parents=True)
    shutil.copy2(paths.from_root("scripts", "lib", "release-age.ts"), root / "scripts" / "lib")
    shutil.copy2(paths.from_root(".npmrc"), root / ".npmrc")
    shim = root / "shim"
    shim.mkdir()
    target = shim / "go"
    target.write_text(GO_SHIM % mode, encoding="utf-8")
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return root


def run_port(root: pathlib.Path) -> tuple[int, str, str]:
    env = dict(os.environ)
    env["PATH"] = "%s%s%s" % (root / "shim", os.pathsep, os.environ.get("PATH", ""))
    env["REDIACC_CI_ROOT"] = str(root)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        ["python3", str(PORT)],
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return proc.returncode, proc.stdout, proc.stderr


@pytest.mark.parametrize(("case_id", "mode"), CASES, ids=[c[0] for c in CASES])
def test_port_matches_the_twins_recorded_output(tmp_path, case_id, mode):
    root = build_fixture(tmp_path, mode)
    returncode, stdout, stderr = run_port(root)
    stdout = frozen.mask_root(stdout, root)
    stderr = frozen.mask_root(stderr, root)
    want_rc, want_out, want_err = split_golden(frozen.read(SLUG, case_id))
    assert returncode == want_rc, "the twin exited %d, the port %d" % (want_rc, returncode)
    assert stdout == want_out, "stdout diverged from the twin's recorded bytes"
    assert stderr == want_err, "stderr diverged from the twin's recorded bytes"


def split_golden(text: str) -> tuple[int, str, str]:
    exit_line, rest = text.split("\n", 1)
    stdout, stderr = rest.split("--- stdout ---\n", 1)[1].split("--- stderr ---\n", 1)
    return int(exit_line.removeprefix("exit: ")), stdout, stderr


def test_every_case_has_a_golden_and_no_golden_is_orphaned() -> None:
    """ANTI-VACUITY on the corpus: see `frozen.assert_corpus`."""
    frozen.assert_corpus(SLUG, {c[0] for c in CASES})


def test_healthy_outdated_still_fails_says_so() -> None:
    """THE GATE'S ORIGINAL JOB must survive the fix, pinned on the recording.

    `log_warn`/`log_info` write to STDERR in this repo's logging convention; only the data lines (the module list itself) land on stdout.
    """
    _rc, _out, err = split_golden(frozen.read(SLUG, "healthy-outdated-still-fails"))
    assert "Outdated Go direct dependencies" in err

    _rc, _out, err = split_golden(frozen.read(SLUG, "healthy-clean-tree-passes"))
    assert "up-to-date" in err


def test_probe_failure_is_never_reported_as_up_to_date() -> None:
    """THE REGRESSION, pinned on all three probe-failure recordings at once."""
    for case_id in (
        "probe-failure-is-not-up-to-date",
        "empty-output-is-a-failure-not-a-clean-tree",
        "unparsable-output-is-a-failure",
    ):
        rc, out, err = split_golden(frozen.read(SLUG, case_id))
        assert rc == 1, "%s: a probe failure must fail the gate" % case_id
        combined = out + err
        assert "probe FAILED" in combined, "%s: named as a probe failure" % case_id
        assert "All Go direct dependencies are up-to-date" not in combined, (
            "%s: must NOT claim everything is up-to-date" % case_id
        )


def test_probe_failure_surfaces_the_real_error() -> None:
    """The diagnostic must name the underlying cause, or a dependency problem and a toolchain problem look identical to the reader."""
    _rc, out, err = split_golden(frozen.read(SLUG, "probe-failure-surfaces-the-real-error"))
    combined = out + err
    assert "go.mod requires go >= 1.25.0" in combined
    assert "exit=1" in combined


def test_the_port_never_swallows_the_probes_exit_status() -> None:
    """STRUCTURAL, not textual: the fix this whole file exists to guard is that the probe's exit status reaches the caller. `check=False` plus an explicit `proc.returncode` branch is the Python shape of that; `check=True` (which raises instead of reporting) or a bare `subprocess.run(...).stdout` (which discards the code) would both put the 2026-07-27 defect back."""
    source = paths.from_root(".ci", "rediacc_ci", "quality", "go_deps.py").read_text(
        encoding="utf-8"
    )
    assert "check=False" in source, "the probe must not raise on a non-zero exit"
    assert "proc.returncode != 0" in source, "the exit status must be read explicitly"
