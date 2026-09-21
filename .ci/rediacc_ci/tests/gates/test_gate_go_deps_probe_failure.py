"""Port of `.ci/scripts/test/gates/test-go-deps-probe-failure.sh`, retired in W7 P5.

The probe-failure guard in `.ci/scripts/quality/check-go-deps.sh`.

WHAT BROKE. The gate gathered its data with

    go list -u -m -json all 2>/dev/null | jq ... 2>/dev/null || true

so ANY failure of either command produced an empty result set, which is byte-identical to a clean tree. The gate then printed "All Go direct dependencies are up-to-date" and exited 0. It was not reporting that deps were fine; it was reporting nothing at all, in the voice of success.

Observed 2026-07-27: a local `npm run ci` reported all-clean while CI failed on the SAME commit for an outdated csi-spec. The gate was not disagreeing with CI --
`go list` was exiting 1 locally (go.mod requires go >= 1.25, the toolchain on
PATH was 1.24) and the failure was being swallowed.

WHY A PATH SHIM. Reproducing the original required a specific broken toolchain on the machine. A fake `go` on PATH reproduces every failure mode deterministically and on any runner, including the one a real toolchain cannot easily produce (valid-but-empty output).

WHAT THE PORT REIMPLEMENTS, AND WHY THE TWO AGREE. The twin builds its fixture
with `mkdir -p` / `cp` and installs its shim by writing a heredoc; this does the
same with `pathlib` and `shutil`, file for file, including the two copies that are load-bearing and were each added after a silent-pass was found:

  * `scripts/lib/release-age.ts`. `release-age.sh` stopped being self-contained
    on 2026-09-06 and is now a SHIM over that TypeScript module, so copying only
    `.ci/scripts/lib` leaves the delegate unreachable, `is_release_deferred`
    fails closed, and the OUTDATED case is silently deferred rather than
    reported. The gate would pass while asserting nothing.
  * `REDIACC_CI_ROOT` pointed at the REAL repository. The fixture mirrors
    `.ci/scripts` only, and `age-check.sh` became a shim over
    `rediacc_ci.core.age`, so without it every case failed at source time with
    "cannot find rediacc_ci" -- including the healthy baseline -- and the
    probe-failure assertions were passing for the wrong reason. The package is
    pure Python and reads no fixture state, so borrowing the real one changes
    nothing under test.

STREAMS ARE MERGED HERE ON PURPOSE, and it is one of the few ports where that is right rather than lazy: the twin redirects `>"$FIXTURE/out.txt" 2>&1` and asserts over the merged text, because the thing being asserted is that go's STDERR reaches the operator at all. Splitting them would change what is claimed.

NO `xdist_group`. Every case runs inside its own temporary fixture tree, PATH is set per-subprocess rather than on this process, and nothing module-global moves.
"""

import os
import pathlib
import shutil
import stat

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

REAL_GATE = paths.from_root(".ci", "scripts", "quality", "check-go-deps.sh")

# The five behaviours of the fake `go`, lifted from the twin's heredoc verbatim so a reader can diff the two. `clean` emits only the main module, which is what a real `go list -m` always emits at minimum; `empty` is the mode a genuinely broken toolchain cannot easily produce and is the subtlest of the five.
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


class Fixture:
    """The mirrored tree the gate runs against, plus the shim it resolves `go` in."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self.gate = root / ".ci" / "scripts" / "quality" / "check-go-deps.sh"
        self.shim = root / "shim"

    def install_fake_go(self, mode: str) -> None:
        target = self.shim / "go"
        target.write_text(GO_SHIM % mode, encoding="utf-8")
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    def run_gate(self) -> harness.RunResult:
        return harness.run(
            ["bash", str(self.gate)],
            cwd=self.root,
            env={
                "PATH": "%s:%s" % (self.shim, os.environ.get("PATH", "")),
                "REDIACC_CI_ROOT": str(paths.repo_root()),
            },
        )


def build_fixture(gate, root: pathlib.Path) -> Fixture:
    """Mirror the layout `get_repo_root()` resolves from the gate's own path."""
    for sub in (
        ".ci/scripts/quality",
        ".ci/scripts/lib",
        ".ci/policy",
        "private/fakemod",
        "scripts/lib",
        "shim",
    ):
        (root / sub).mkdir(parents=True, exist_ok=True)
    if not REAL_GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(REAL_GATE))
    shutil.copy2(REAL_GATE, root / ".ci" / "scripts" / "quality")
    libs = sorted(paths.from_root(".ci", "scripts", "lib").glob("*.sh"))
    if not libs:
        gate.log_fail(
            ".ci/scripts/lib holds no *.sh, so the fixture would be missing every helper "
            "the gate sources and the run below would fail for a reason that has nothing "
            "to do with the probe."
        )
    for lib in libs:
        shutil.copy2(lib, root / ".ci" / "scripts" / "lib")
    shutil.copy2(paths.from_root("scripts", "lib", "release-age.ts"), root / "scripts" / "lib")
    (root / "private" / "fakemod" / "go.mod").write_text(
        "module example.com/fakemod\n\ngo 1.25\n", encoding="utf-8"
    )
    (root / ".ci" / "policy" / ".go-deps-upgrade-blocklist").write_text("", encoding="utf-8")
    return Fixture(root)


def test_healthy_clean_tree_passes(gate):
    gate.log_test("baseline: a clean module list must pass")
    # Without this the failure cases could pass for the wrong reason, e.g. the gate erroring on the fixture itself.
    with harness.temp_dir() as root:
        fixture = build_fixture(gate, root)
        fixture.install_fake_go("clean")
        result = fixture.run_gate()
        gate.assert_exit_code(0, result.rc, "a clean module list must pass")
        gate.assert_contains(result.combined, "up-to-date", "and say so")
    gate.log_pass("a healthy probe with no updates passes")


def test_healthy_outdated_still_fails(gate):
    gate.log_test("the gate's ORIGINAL job must survive the fix")
    with harness.temp_dir() as root:
        fixture = build_fixture(gate, root)
        fixture.install_fake_go("outdated")
        result = fixture.run_gate()
        gate.assert_exit_code(1, result.rc, "a genuinely outdated direct dep must still fail")
        gate.assert_contains(
            result.combined, "Outdated Go direct dependencies", "with the original diagnostic"
        )
    gate.log_pass("a real outdated dependency still fails the gate")


def test_probe_failure_is_not_up_to_date(gate):
    gate.log_test("THE REGRESSION: a failing probe returned 0 and said up-to-date")
    with harness.temp_dir() as root:
        fixture = build_fixture(gate, root)
        fixture.install_fake_go("fail")
        result = fixture.run_gate()
        gate.assert_exit_code(1, result.rc, "a failing go-list must fail the gate, not pass it")
        gate.assert_contains(
            result.combined, "probe FAILED", "the failure is named as a probe failure"
        )
        gate.assert_not_contains(
            result.combined,
            "All Go direct dependencies are up-to-date",
            "it must NOT claim everything is up-to-date",
        )
    gate.log_pass("a failing probe fails loudly instead of reporting all-clean")


def test_probe_failure_surfaces_the_real_error(gate):
    gate.log_test("the diagnostic must name the underlying cause")
    # A diagnostic that does not name it sends the reader hunting through their own tree for a dependency problem that is really a toolchain problem.
    with harness.temp_dir() as root:
        fixture = build_fixture(gate, root)
        fixture.install_fake_go("fail")
        result = fixture.run_gate()
        gate.assert_contains(
            result.combined, "go.mod requires go >= 1.25.0", "the actual go error is surfaced"
        )
        gate.assert_contains(result.combined, "exit=1", "the exit status is surfaced")
    gate.log_pass("the probe failure carries go's own error text")


def test_empty_output_is_a_failure_not_a_clean_tree(gate):
    gate.log_test("exit 0 with empty stdout looked exactly like success")
    # `go list -m` on a real module always emits at least the main module, so zero modules means the probe returned nothing usable.
    with harness.temp_dir() as root:
        fixture = build_fixture(gate, root)
        fixture.install_fake_go("empty")
        result = fixture.run_gate()
        gate.assert_exit_code(1, result.rc, "an empty module list must fail")
        gate.assert_contains(result.combined, "no modules at all", "and say why")
    gate.log_pass("a successful-but-empty probe is treated as broken, not clean")


def test_unparsable_output_is_a_failure(gate):
    gate.log_test("unparsable probe output must not read as clean")
    with harness.temp_dir() as root:
        fixture = build_fixture(gate, root)
        fixture.install_fake_go("garbage")
        result = fixture.run_gate()
        gate.assert_exit_code(1, result.rc, "unparsable go-list output must fail")
        gate.assert_contains(result.combined, "probe FAILED", "reported as a probe failure")
    gate.log_pass("unparsable probe output fails instead of reading as clean")


def test_real_gate_has_no_swallowing_redirects(gate):
    gate.log_test("the fix is worthless if the swallowing shape comes back")
    # The twin runs `grep -A2 'go list -u -m -json all'` over the REAL gate. This is the same window in Python: the matching line plus the two after it. Read
    # from the real file and not the fixture copy on purpose, since the fixture
    # copy is what the cases above already exercised behaviourally.
    source = REAL_GATE.read_text(encoding="utf-8").splitlines()
    window: list[str] = []
    for index, line in enumerate(source):
        if "go list -u -m -json all" in line:
            window.extend(source[index : index + 3])
    if not window:
        gate.log_fail(
            "no line in %s contains `go list -u -m -json all`, so the two refusals below "
            "would be asserting over an empty string, which every not-contains test passes "
            "against by accident. The probe was renamed or removed."
            % paths.relative_to_root(REAL_GATE)
        )
    text = "\n".join(window)
    gate.assert_not_contains(text, "2>/dev/null", "the probe must not discard go's stderr")
    gate.assert_not_contains(text, "|| true", "the probe must not swallow a non-zero exit")
    gate.log_pass("the real gate still captures the probe's stderr and exit status")
