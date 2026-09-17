r"""`rediacc_ci.quality.drill_verdicts` against the harness it drives.

WHAT IS WORTH TESTING HERE. The shadow ledger `.ci/shadow/w7p2-drill-verdicts.observations.jsonl` drives the whole gate over five distinct trees, each carrying a differently-mutated `scripts/drills/lib.sh`. What a ledger row cannot isolate is the DRIVER: a `bash -c` subshell that sets eight variables, sources a library under `set +eu`, and hands back `<rc>|<stdout>`. If the driver
stops working, EVERY assertion in this gate either fails loudly (good) or, in the shape this repo keeps finding, passes vacuously.

So the cases below drive the REAL `scripts/drills/lib.sh` and assert on its real output, in both directions per verdict.

THE UNREACHABLE PROBE IS ASSERTED AS UNREACHABLE, not quietly ignored. The twin
checks `[[ "${probe%%|*}" == "97" ]]` against a capture that is EMPTY whenever
the subshell exits 97, so the branch cannot fire. That is a defect in the twin, carried by the port, and pinned here so it stays a known dead branch rather than becoming a surprise.
"""

import pathlib
import re

from rediacc_ci import paths
from rediacc_ci.quality import drill_verdicts as dv
from rediacc_ci.tests import differential as diff


def test_the_harness_exists() -> None:
    """ZERO INPUTS IS A FAILURE. Every case below is vacuous without it, and the
    gate's own first branch says so in two lines."""
    assert (paths.repo_root() / dv.DRILL_LIB).is_file(), (
        "%s moved; the gate refuses rather than passing, and so should this" % dv.DRILL_LIB
    )


def test_the_driver_returns_both_halves() -> None:
    """`<rc>|<stdout>`. Asserting only on the exit code is what let the original
    defect through, so the shape itself is asserted."""
    result = dv.run_summary(paths.repo_root(), "3", "0")
    assert "|" in result, result
    rc, _, out = result.partition("|")
    assert rc == "0", result
    assert "3 assertions" in out, out


def test_zero_assertions_says_skipped_and_never_passed() -> None:
    """THE 2026-08-05 DEFECT, driven against the live harness. Both halves: the
    right word present AND the wrong word absent."""
    rc, _, out = dv.run_summary(paths.repo_root(), "0", "0").partition("|")
    assert rc == "0", "a DECLARED skip keeps exit 0; it was the WORD that was wrong"
    assert "SKIPPED" in out, out
    assert "PASSED" not in out, out


def test_a_real_pass_still_says_passed() -> None:
    """THE CONTROL. Without it a harness hard-wired to SKIPPED would satisfy the
    case above, and the whole table would be satisfied by a constant."""
    rc, _, out = dv.run_summary(paths.repo_root(), "3", "0").partition("|")
    assert rc == "0"
    assert "PASSED" in out, out


def test_a_failure_is_loud_and_non_zero() -> None:
    rc, _, out = dv.run_summary(paths.repo_root(), "3", "1").partition("|")
    assert rc == "1"
    assert "FAILED" in out, out


def test_a_selftest_that_did_not_fire_refuses() -> None:
    rc, _, out = dv.run_summary(paths.repo_root(), "3", "0", "1").partition("|")
    assert rc == "1"
    assert "SELFTEST DID NOT FIRE" in out, out


def test_an_undrivable_harness_yields_an_empty_capture_not_97(tmp_path: pathlib.Path) -> None:
    """THE TWIN'S DEAD BRANCH, pinned.

    `declare -F drill_summary || exit 97` leaves the subshell before its
    `printf`, so the capture is "" and `${probe%%|*}` is "" -- never "97". The
    guard that actually catches this is `assert_verdict`'s empty-result branch.
    """
    (tmp_path / "scripts" / "drills").mkdir(parents=True)
    (tmp_path / dv.DRILL_LIB).write_text("#!/bin/bash\necho nothing\n", encoding="utf-8")
    result = dv.run_summary(tmp_path, "1", "0")
    assert result == "", result
    assert result.partition("|")[0] != dv.UNDRIVABLE
    assert dv.UNDRIVABLE == "97"


def test_the_bash_subshell_agrees_with_the_twins() -> None:
    """The port's runner against the twin's, over the same harness.

    Not "does the Python compute the right answer" but "does the same shell code run": the subject here IS bash, and a driver that diverged would test a different harness than the one the drills use.
    """
    root = str(paths.repo_root())
    twin = (
        '( set +eu; source "%s" >/dev/null 2>&1; declare -F drill_summary >/dev/null || exit 97; '
        'DRILL_NAME="gatecheck"; DRILL_STARTED_AT=$(date +%%s); DRILL_COUNT=0; '
        "DRILL_FAILURES=0; DRILL_SELFTEST=0; DRILL_ROWS=(); "
        'out="$(drill_summary 2>&1)"; rc=$?; printf \'%%s|%%s\' "$rc" "$out" )' % dv.DRILL_LIB
    )
    code, out, err = diff.bash_streams("source .ci/scripts/lib/common.sh; " + twin, cwd=root)
    assert (code, err) == (0, ""), err
    port = dv.run_summary(paths.repo_root(), "0", "0")

    # THE ELAPSED SECONDS ARE MASKED, and only those. Each side computes its own `now - DRILL_STARTED_AT` and renders it whole-seconds, so when the two runs straddle a second boundary the twin says `failed (1s)` and the port says `failed (0s)`. That is a clock tick, not a disagreement about behaviour. Observed in CI job 104616780062 after five clean runs, which is what a boundary
    # race looks like.
    #
    # Masked rather than pinned because the duration is environmental: the claim this case makes is "the same shell code runs", and how long it took is no
    # part of it. Same stance as the `cb=<digits>` cache-buster normalisation in
    # test_deploy_verify_edge_endpoints.py -- neither side can be made to agree and neither is supposed to.
    elapsed = re.compile(r"\(\d+s\)")
    assert elapsed.search(out), (
        "the twin printed no elapsed time, so the mask below would hide a real "
        "divergence rather than a clock tick: %r" % out
    )
    assert elapsed.search(port), "the port printed no elapsed time: %r" % port
    assert elapsed.sub("(<elapsed>)", port) == elapsed.sub("(<elapsed>)", out)


def test_the_byte_tail_matches_the_twins_pipeline() -> None:
    """`tr '\n' ' ' <<<"$out" | tail -c 200`, including the herestring's own
    trailing newline. Compared against the real tr and tail."""
    text = "line one\nline two\n" + "z" * 250
    # The text arrives through the ENVIRONMENT, not through the command string. An earlier version interpolated it and doubled its own `%%s`, so the comparison ran against the literal two characters `%s` and failed for a reason that had nothing to do with the tail.
    code, out, err = diff.bash_streams(
        "tr '\\n' ' ' <<<\"$T\" | tail -c 200",
        env=diff.env_for(T=text),
    )
    assert (code, err) == (0, ""), err
    assert dv.tail_summary(text) == out


def test_the_four_cases_are_the_twins_four() -> None:
    """The decision TABLE, asserted as a table. A fifth row appearing here
    without appearing in the twin is a divergence nobody would notice from the
    output, because every row prints the same shape of line."""
    assert [(c.count, c.fails, c.selftest, c.want_rc, c.want, c.forbid) for c in dv.CASES] == [
        ("0", "0", "0", "0", "SKIPPED", "PASSED"),
        ("3", "0", "0", "0", "PASSED", ""),
        ("3", "1", "0", "1", "FAILED", ""),
        ("3", "0", "1", "1", "SELFTEST DID NOT FIRE", ""),
    ]


def test_selftest_is_green() -> None:
    assert dv.selftest() == 0


def test_the_real_tree_passes() -> None:
    assert dv.main([]) == 0
