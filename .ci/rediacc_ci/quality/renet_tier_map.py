"""The renet licence tier map still covers every registered function.

Ported from `.ci/scripts/quality/check-renet-tier-map.sh`, which W7 P5 batch A2 retired once `.ci/shadow/w7p2-renet-tiermap.observations.jsonl` asserted equivalence over five distinct trees.

THE TWIN IS DECLARED `kind: local-only`, AND ITS BLOCKER IS ABOUT WIRING RATHER THAN ABOUT THE TIER MAP, so it stays with the bash file rather than moving here: "no CI step invokes this script; the seven tier-map tests it drives already run in CI inside rediacc_ci.private.run_renet test (ct-tests.yml job test-renet, step 'Run renet tests'), which resolves to that leaf and not this
one, so a step pointer would claim CI runs a script it never invokes". A port does not inherit a registration, so nothing here re-states it as a live suppression, and this module is deliberately NOT wired into anything either.

WHY THE TWIN EXISTS AT ALL, given CI already runs those tests. `npm run ci` had no leg for them, so a tier-map regression could only be found after a push. The CLI now DERIVES its licence-issuance class from this map through the generated contract (`packages/shared/src/renet-contract/data/license-tiers.generated.ts`, consumed by
`packages/cli/src/services/renet/renet-license-contract.ts`), which makes the map's completeness a console-side correctness property, not only a renet one.

THE THREE PHASES, AND WHY THE FIRST AND THIRD EXIST AT ALL. Phase 2 on its own -- run the tests, believe the exit code -- is the vacuous version of this gate, and both of the phases around it close a way it reports green while checking nothing:

    Phase 1  INSTRUMENT CHECK. `go test -run` exits 0 with "no tests to run"
             when its regex matches nothing. So the regex's selection is
             compared against a HAND-WRITTEN list of the seven test names
             before any green run of it is trusted. A rename is then a loud
             failure here instead of a silent selection of zero tests.
    Phase 2  RUN THEM, with `-count=1` so a stale green from a previous tier
             map cannot be replayed out of the test cache.
    Phase 3  ASSERT EACH ONE REPORTED PASS. A green exit is not enough: a build
             tag or a `t.Skip` retires a test silently, and the run still exits
             0 with that test selected and never executed.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE SUBMODULE GUARD IS A THREE-WAY BRANCH, NOT A TWO-WAY ONE. `require_submodule` answers "present", "absent under CI" (hard failure, exit 1, three lines naming the fix) and "absent locally" (warn, and the caller's `|| exit 0` makes it a skip). All three rungs are carried; see `rediacc_ci.quality.renet_types` for the same note and for common.sh's own reason ("a gate that silently
skips is worse than no gate at all").

`sort` IS BYTE ORDER HERE, AND THE PORT'S `sorted()` MATCHES IT. The twin sorts both lists with coreutils `sort`, whose result depends on the locale. Every
caller that matters -- CI, and the shadow differential -- pins `LC_ALL=C`, and
all seven names are ASCII, so `sorted()` on the Python side produces the same sequence. Under a collating locale the twin could order `TestTierMapGateCanFail` and `TestTierMapHasNoOrphans` differently from the port. Stated rather than hidden, because it is the kind of difference that surfaces once, on someone
else's machine.

A ZERO-TEST SELECTION ABORTS THE TWIN SILENTLY, and that is a defect this port
reproduces. `LISTED="$(... | grep '^Test' | sort)"` runs under `set -euo
pipefail`, so when `grep` matches nothing the pipeline fails, the assignment fails, and the script exits 1 having printed NOTHING beyond `go test`'s own output. The reader sees an exit code and no explanation, for the exact condition phase 1 was written to explain. The port exits with the same code at the same point; the defect is reported, not repaired, because repairing it would
change what the gate prints.

`2>&1` IS THE TWIN'S OWN MERGE AND IS NOT THIS PORT'S CHOICE. Phase 2 captures the test run with the two streams merged, then re-prints the whole thing on stderr when the run failed. `rediacc_ci.tests.differential` refuses to merge streams for exactly the reason the 2026-09-06 emit-advisory incident showed, and this is not that: the merge here is INSIDE the subject, part of what
the gate prints, so the port merges too and the gate's own two streams stay separate.
"""

import os
import pathlib
import re
import subprocess
import sys

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls, plant

RENET_REL = "private/renet"
MARKER = "go.mod"

# The tests this gate exists to run. NAMED INDIVIDUALLY rather than swept by a pattern so a RENAME is a loud failure here instead of a silent selection of zero tests.
EXPECTED_TESTS = (
    "TestTierMapCoversRegistry",
    "TestTierMapHasNoOrphans",
    "TestTierMapGateCanFail",
    "TestPendingBacklogIsReported",
    "TestTierMapDrivesDispatch",
    "TestOperateTierSurvivesExpiry",
    "TestTierProbeMatchesTheMap",
)

# The regex handed to `go test -list` and `go test -run`. Byte for byte from the twin: the two must select the same set or phase 1 verifies a different thing
# from the one phase 2 runs.
RUN_REGEX = (
    "^(TestTierMap.*|TestTierProbeMatchesTheMap|TestOperateTierSurvivesExpiry"
    "|TestPendingBacklogIsReported)$"
)

TEST_PACKAGE = "./pkg/functions/"

# `auto` so private/renet/go.mod's toolchain directive stays the single source of truth, matching every sibling renet script.
GOTOOLCHAIN_DEFAULT = "auto"


def wanted() -> list[str]:
    """`printf '%s\\n' "${EXPECTED_TESTS[@]}" | sort`."""
    return sorted(EXPECTED_TESTS)


def listed_from(output: str) -> list[str]:
    """`go test -list` output, filtered to `^Test` and sorted.

    The filter is not cosmetic: `go test -list` also prints the package result line (`ok <module>/pkg/functions 0.002s`), and without `grep '^Test'` that line would join the comparison and make phase 1 fail on every run.
    """
    lines = output.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return sorted(line for line in lines if line.startswith("Test"))


def missing_passes(output: str) -> list[str]:
    """Which expected tests never reported `--- PASS:`. Order is EXPECTED's.

    `grep -q -- "--- PASS: $test_name"` is a SUBSTRING test, not an anchored one, and the order of the result is the declaration order rather than the
    sorted one because the twin loops over `"${EXPECTED_TESTS[@]}"`. Both are
    carried: the list is interpolated into the failure message with `${MISSING[*]}`
    and a reviewer diffs the two implementations' stderr side by side.
    """
    return [name for name in EXPECTED_TESTS if ("--- PASS: %s" % name) not in output]


def _require_submodule(marker: pathlib.Path, label: str) -> bool:
    """`require_submodule` from `.ci/scripts/lib/common.sh`. True to proceed.

    Raises SystemExit(1) on the CI rung, exactly as the bash function's `exit 1` does. See this module's port notes for why all three rungs survive.
    """
    if marker.exists():
        return True
    if os.environ.get("CI", "false") == "true":
        log.error("%s is required in CI but missing: %s" % (label, marker))
        log.error("  A gate skipped here would report success while checking nothing.")
        log.error("  Fix the workflow checkout (submodules: true, or git submodule update --init).")
        raise SystemExit(1)
    log.warn("%s not available, skipping (this is a hard failure in CI)" % label)
    return False


def _go_env() -> dict[str, str]:
    """The child environment: the caller's, with GOTOOLCHAIN defaulted."""
    env = dict(os.environ)
    env["GOTOOLCHAIN"] = env.get("GOTOOLCHAIN", GOTOOLCHAIN_DEFAULT)
    return env


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 covered, 1 on drift or failure, 0 on a local skip.

    `--selftest` is intercepted BEFORE any real scan. The twin takes no arguments at all, so no caller can be passing this string today.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    renet_dir = pathlib.Path(os.environ.get("RENET_DIR") or (root / RENET_REL))

    # go.mod is the marker, NOT the directory: an uninitialised submodule leaves an EMPTY directory behind, and a gate that ran zero tests against it would report success while checking nothing.
    if not _require_submodule(renet_dir / MARKER, "Renet submodule"):
        return 0

    log.step("Checking the renet tier map covers the function registry...")

    # -- Phase 1: instrument check ------------------------------------------
    try:
        listing = subprocess.run(
            ["go", "test", "-list", RUN_REGEX, TEST_PACKAGE],
            cwd=str(renet_dir),
            capture_output=True,
            text=True,
            check=False,
            env=_go_env(),
        )
    except FileNotFoundError:
        # `go` absent: the twin dies with bash's own `command not found` and exit 127, a message it never wrote. Same code, own words. See `rediacc_ci.quality.renet_types` for the identical decision.
        log.error("go is not installed, so NOTHING was verified.")
        log.error("  Install the Go toolchain, or run this gate where one exists.")
        return 127
    sys.stderr.write(listing.stderr)
    listed = listed_from(listing.stdout)
    if listing.returncode != 0 or not listed:
        # THE SILENT ABORT, REPRODUCED. `set -euo pipefail` plus `grep`'s exit 1 on no match kills the twin here with no message of its own. See the port notes: the defect is reported, not repaired.
        return 1

    if listed != wanted():
        log.error("The tier-map test selection has drifted.")
        log.error("  wanted:")
        for name in wanted():
            print("    %s" % name, file=sys.stderr)
        log.error("  selected by %s:" % RUN_REGEX)
        # `${LISTED:-<none>}` -- an empty selection prints the literal marker
        # rather than a blank line, so the failure names the vacuity.
        for name in listed or ["<none>"]:
            print("    %s" % name, file=sys.stderr)
        log.error("  Update EXPECTED_TESTS/RUN_REGEX in this gate, or restore the test names.")
        return 1

    # -- Phase 2: run them --------------------------------------------------
    log.step("Running %d tier-map tests in %s..." % (len(EXPECTED_TESTS), TEST_PACKAGE))
    run = subprocess.run(
        ["go", "test", "-count=1", "-v", "-run", RUN_REGEX, TEST_PACKAGE],
        cwd=str(renet_dir),
        capture_output=True,
        text=True,
        check=False,
        env=_go_env(),
        # The twin's own `2>&1`. See the port notes: this merge is inside the subject, not a shortcut taken by the comparison.
        stdin=subprocess.DEVNULL,
    )
    # `$( ... 2>&1 )` -- merged, then trailing newlines stripped.
    output = (run.stdout + run.stderr).rstrip("\n")
    if run.returncode != 0:
        print(output, file=sys.stderr)
        log.error("Renet tier-map tests failed.")
        log.error("  A registered function with no tier entry means renet cannot decide whether")
        log.error("  it needs a licence, and the CLI's generated contract inherits that gap.")
        log.error("  Fix private/renet/pkg/license/tiermap.go, then regenerate:")
        log.error("    cd private/renet && go build -o bin/renet ./cmd/renet")
        log.error("    private/renet/bin/renet functions generate-types \\")
        log.error("      --output packages/shared/src/renet-contract/data --version dev")
        return 1

    # -- Phase 3: a green exit is not enough --------------------------------
    missing = missing_passes(output)
    if missing:
        print(output, file=sys.stderr)
        log.error("These tier-map tests never reported PASS: %s" % " ".join(missing))
        log.error("  They were selected but did not run (skipped, or excluded by a build tag).")
        return 1

    log.info("Renet tier map covers the registry (%d tests passed)" % len(EXPECTED_TESTS))
    return 0


# A `go test -v` transcript in which every expected test passes. The base every plant below mutates, and asserted CLEAN first: without that, each plant would "fire" against a transcript that was already failing.
_PASSING_RUN = (
    "\n".join("=== RUN   %s\n--- PASS: %s (0.00s)" % (name, name) for name in EXPECTED_TESTS)
    + "\nPASS\nok  \tgithub.com/rediacc/renet/pkg/functions\t0.004s\n"
)

# What `go test -list` prints: one name per line, then the package result line that `grep '^Test'` exists to drop.
_LISTING = "\n".join(EXPECTED_TESTS) + "\nok  \tgithub.com/rediacc/renet/pkg/functions\t0.002s\n"


def selftest() -> int:
    """Plant each violation, prove it reds; remove it, prove it greens.

    THE PURE HALF ONLY, AND THAT IS A DECISION. The end-to-end path compiles and runs a Go package, which needs a toolchain, the submodule, and tens of seconds; a selftest that silently degraded when any of those was missing would be the vacuity this package exists to refuse. The two functions that decide the verdict are pure, so they are driven directly here, and the whole gate is
    proven end to end by the committed shadow ledger `.ci/shadow/w7p2-renet-tiermap.observations.jsonl` over five distinct trees.
    """
    ctl = Controls("renet-tier-map", floor=18, verbose=True)

    # -- phase 1's comparison ----------------------------------------------
    ctl.check("CONTROL: the reference listing matches EXPECTED", listed_from(_LISTING), wanted())
    ctl.check(
        "CONTROL: the package result line is dropped, not compared",
        "ok" in listed_from(_LISTING),
        False,
    )
    ctl.check("VACUITY: an EMPTY listing selects nothing", listed_from(""), [])
    ctl.check(
        "VACUITY: a listing with only the result line selects nothing",
        listed_from("ok  \tm/pkg\t0.002s\n"),
        [],
    )
    ctl.check(
        "VACUITY: 'no tests to run' selects nothing, which is the whole hazard",
        listed_from("testing: warning: no tests to run\nPASS\nok  \tm/pkg\t0.001s\n"),
        [],
    )
    ctl.check(
        "PLANT: a RENAMED test is drift",
        listed_from(plant(_LISTING, "TestTierMapCoversRegistry", "TestTierMapCoversTheRegistry"))
        == wanted(),
        False,
    )
    ctl.check(
        "PLANT: an EXTRA selected test is drift",
        listed_from(_LISTING + "TestTierMapSomethingNew\n") == wanted(),
        False,
    )
    ctl.check(
        "PLANT: a MISSING test is drift",
        listed_from(plant(_LISTING, "TestTierProbeMatchesTheMap\n", "")) == wanted(),
        False,
    )
    ctl.check(
        "MIRROR: a different ORDER is not drift, because both sides sort",
        listed_from("\n".join(reversed(EXPECTED_TESTS)) + "\n"),
        wanted(),
    )
    ctl.check(
        "MIRROR: a name that does not start with Test is ignored",
        listed_from(_LISTING + "BenchmarkTierMap\n"),
        wanted(),
    )

    # -- phase 3's assertion -----------------------------------------------
    ctl.check("CONTROL: a fully passing run has nothing missing", missing_passes(_PASSING_RUN), [])
    ctl.check(
        "PLANT: a SKIPPED test never reported PASS",
        missing_passes(
            plant(
                _PASSING_RUN,
                "--- PASS: TestTierMapGateCanFail (0.00s)",
                "--- SKIP: TestTierMapGateCanFail (0.00s)",
            )
        ),
        ["TestTierMapGateCanFail"],
    )
    ctl.check(
        "PLANT: a FAILED test never reported PASS",
        missing_passes(
            plant(
                _PASSING_RUN,
                "--- PASS: TestTierMapHasNoOrphans (0.00s)",
                "--- FAIL: TestTierMapHasNoOrphans (0.00s)",
            )
        ),
        ["TestTierMapHasNoOrphans"],
    )
    ctl.check(
        "VACUITY: an EMPTY transcript means every test is missing",
        missing_passes(""),
        list(EXPECTED_TESTS),
    )
    ctl.check(
        "PLANT: the report order is EXPECTED's, not sorted",
        missing_passes(
            plant(
                plant(_PASSING_RUN, "--- PASS: TestTierMapHasNoOrphans", "x"),
                "--- PASS: TestTierMapCoversRegistry",
                "y",
            )
        ),
        ["TestTierMapCoversRegistry", "TestTierMapHasNoOrphans"],
    )
    ctl.check(
        "MIRROR: a SUBTEST's PASS line still satisfies its parent, as grep does",
        missing_passes(
            plant(
                _PASSING_RUN,
                "--- PASS: TestTierMapGateCanFail (0.00s)",
                "    --- PASS: TestTierMapGateCanFail/sub (0.00s)",
            )
        ),
        [],
    )

    # -- the regex and the list must agree ---------------------------------
    #
    # PHASE 1 IS ONLY MEANINGFUL IF THE REGEX CAN SELECT EXACTLY THESE SEVEN. A port that copied one and mistyped the other would fail every real run
    # for a reason that looks like drift in renet.
    compiled = re.compile(RUN_REGEX)
    ctl.check(
        "the regex selects every expected test",
        [name for name in EXPECTED_TESTS if not compiled.match(name)],
        [],
    )
    ctl.check(
        "and it does NOT select an unrelated test in the same package",
        compiled.match("TestSomethingElse"),
        None,
    )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
