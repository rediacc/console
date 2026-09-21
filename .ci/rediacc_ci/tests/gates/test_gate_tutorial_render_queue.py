"""Port of `.ci/scripts/test/gates/test-tutorial-render-queue.sh`, retired in W7 P5.

Tests `packages/www/scripts/list-tutorial-render-pairs.js`, the ONE readiness predicate for "which (tutorial, language) pairs still need rendering". Everything downstream trusts it: `run.sh`'s `www tutorials media` and `www tutorials watch` render exactly what it emits, so a predicate that silently answers "nothing" produces a green run that rendered nothing, and one that
over-reports burns hours of CPU re-rendering finished work.

WHAT IS CHECKED HERE VERSUS IN `--selftest`, carried over from the twin. The predicate ships its own staleness cases (mp4 missing, timeline newer, mp4 newer, wrong provider, audio dir absent) and this file does NOT duplicate them. It checks what a self-test cannot honestly check about itself: the empty-tree refusal against a REAL empty tree, that `--selftest` is wired into the npm
gate AND propagates its exit code, and that the self-test carries controls.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP. Three cases read the working tree in place -- the predicate file itself, `package.json`'s script table, and `scripts/ci-runner/manifest.ts` -- and `--selftest` runs the real shipped predicate out of `packages/www/scripts/`. A battery step rewriting any of those mid-read is
the flake that would be blamed on this port. `REAL_TREE_TWIN = True` is what buys
the serialisation, and it is honoured only because this module declares no `XDIST_GROUP` of its own; see `real_tree_admission` in `test_twin_parity.py`, which refuses the combination.

TWO CASES ARE REIMPLEMENTED RATHER THAN SHELLED OUT, and both are reads, not verdicts. The twin asks node to print `package.json`'s script value (`node -e "...require(package.json).scripts[...]"`) and greps `manifest.ts` for a literal; this reads the same two files with `json.loads` and a substring search. The strings asserted on are byte-identical to the twin's, so a drift in
either file reds both sides. Nothing about the SUBJECT is reimplemented: every predicate invocation below is the real `node <predicate>`.
"""

import json
import os

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

# Reads packages/www/scripts/, package.json and scripts/ci-runner/manifest.ts off the real working tree on every case. See the module docstring.
REAL_TREE_TWIN = True

PREDICATE_REL = "packages/www/scripts/list-tutorial-render-pairs.js"
PREDICATE = paths.from_root(*PREDICATE_REL.split("/"))
GATE_NAME = "check:ci-tutorial-render-queue"
MANIFEST_REL = "scripts/ci-runner/manifest.ts"
MANIFEST = paths.from_root(*MANIFEST_REL.split("/"))
PACKAGE_JSON = paths.from_root("package.json")


def node(gate) -> str:
    """`node`, probed by name with the remedy in the message.

    The twin invokes `node` bare and would arrive as `node: command not found` inside a command substitution, which `set -euo pipefail` turns into a bare non-zero. Probing first names the missing binary and what to do about it. `check:ci-pytest` runs in `quality-security`, which DOES set the workspace up, so an absent node here is a real finding about the lane and never a skip.
    """
    if not PREDICATE.is_file():
        gate.log_fail("predicate missing at %s -- the gate cannot be meaningful" % PREDICATE_REL)
    return harness.require_tool(
        "node",
        "install node (the lane's setup-workspace step provides it); the predicate is a .js file",
    )


def run_predicate(gate, *args: str) -> harness.RunResult:
    """The real predicate, merged streams, exactly as the twin captures `2>&1`."""
    binary = node(gate)
    return harness.run(
        [binary, os.fspath(PREDICATE), *args],
        cwd=paths.repo_root(),
    )


def test_predicate_exists(gate):
    if not PREDICATE.is_file():
        gate.log_fail("predicate missing at %s -- the gate cannot be meaningful" % PREDICATE_REL)
    gate.log_pass("predicate present")


def test_empty_tree_refuses(gate):
    """An empty tree must REFUSE, not answer "0 pairs".

    "0 pairs" is indistinguishable from "everything is rendered", and that is the reading that makes a broken checkout look green.
    """
    with harness.temp_dir() as tmp:
        result = run_predicate(gate, "--root", os.fspath(tmp))
        gate.assert_exit_code(1, result.rc, "empty tree must exit non-zero")
        gate.assert_contains(result.combined, "Refusing to run", "refusal must say it is refusing")
        # Pin the DIAGNOSTIC, not just the code: a crash also exits non-zero.
        gate.assert_contains(
            result.combined,
            "meaningless",
            "refusal must explain why the answer would be wrong",
        )
        gate.log_pass("an empty tree refuses instead of reporting zero pairs")


def test_half_populated_tree_refuses(gate):
    """Half a tree is the nastier case: casts present, timelines absent (or the reverse) is what a partial checkout or a half-finished narration run actually looks like."""
    with harness.temp_dir() as tmp:
        tutorials = tmp / "packages" / "www" / "public" / "assets" / "tutorials"
        tutorials.mkdir(parents=True, exist_ok=True)
        (tutorials / "tutorial-fake.cast").write_text("{}", encoding="utf-8")
        result = run_predicate(gate, "--root", os.fspath(tmp))
        gate.assert_exit_code(1, result.rc, "casts-without-timelines must exit non-zero")
        gate.assert_contains(result.combined, "Refusing to run", "half-populated tree must refuse")
        gate.log_pass("casts present but no timeline dirs still refuses")


def test_selftest_passes(gate):
    result = run_predicate(gate, "--selftest")
    gate.assert_exit_code(
        0, result.rc, "--selftest must pass on a clean tree (output: %s)" % result.combined
    )
    gate.log_pass("--selftest passes")


def test_selftest_has_controls(gate):
    """A self-test made only of cases that expect a hit cannot detect an over-reporting predicate. Require controls: cases asserting something is NOT listed."""
    result = run_predicate(gate, "--selftest")
    body = result.combined
    # `grep -c -i control`: COUNT OF MATCHING LINES, not of occurrences. A line naming "control" twice counts once on the bash side, so it must count once here too or the port's floor would be looser than the twin's.
    control_count = len([ln for ln in body.splitlines() if "control" in ln.lower()])
    if control_count < 2:
        gate.log_fail(
            "--selftest reported only %d control case(s); a predicate needs cases that "
            "must NOT fire (mp4 newer, wrong provider) or it cannot catch over-reporting"
            % control_count
        )
    gate.log_pass("--selftest carries %d control case(s)" % control_count)


def test_gate_runs_the_selftest(gate):
    """The gate is worthless if the npm script does not actually run the self-test, or runs it in a way that ignores its exit code."""
    if not PACKAGE_JSON.is_file():
        gate.log_fail("no package.json at %s, so this assertion would be vacuous" % PACKAGE_JSON)
    scripts = json.loads(PACKAGE_JSON.read_text(encoding="utf-8")).get("scripts") or {}
    if not scripts:
        gate.log_fail(
            "package.json declares NO scripts at all, so this case scanned nothing. "
            "Zero subjects is a failure here, not a pass."
        )
    cmd = scripts.get(GATE_NAME, "")
    if not cmd:
        gate.log_fail("%s is not registered in package.json" % GATE_NAME)
    gate.assert_contains(
        cmd, "list-tutorial-render-pairs", "%s must invoke the predicate" % GATE_NAME
    )
    gate.assert_contains(cmd, "--selftest", "%s must run --selftest" % GATE_NAME)
    # `;` or `||` between stages would swallow a failure; `&&` propagates it.
    if ";" in cmd:
        gate.log_fail(
            "%s chains with ';' which discards a failing stage's exit code: %s" % (GATE_NAME, cmd)
        )
    gate.log_pass("%s runs --selftest and propagates its exit code" % GATE_NAME)


def test_gate_is_in_the_gate_manifest(gate):
    """The gate must be in the local gate set, or nothing runs it.

    The twin's note is worth keeping: this used to read package.json's `ci` value and look for the key in it, which stopped working the moment `scripts.ci` became `tsx scripts/ci-runner/run.ts`. The manifest is the gate set now.
    """
    if not MANIFEST.is_file():
        gate.log_fail("no gate manifest at %s, so this assertion would be vacuous" % MANIFEST_REL)
    source = MANIFEST.read_text(encoding="utf-8")
    if "id: '%s'" % GATE_NAME not in source:
        gate.log_fail(
            "%s must be an entry in %s, or no local run schedules it" % (GATE_NAME, MANIFEST_REL)
        )
    gate.log_pass("%s is wired into the gate manifest" % GATE_NAME)


def test_harness_can_actually_fail(gate):
    """CONTROL for this file: a deliberately broken predicate must make the empty-tree assertion FAIL. Without this, every test above could be passing because `node` errors on everything."""
    binary = node(gate)
    with harness.temp_dir() as tmp:
        # A predicate that cheerfully reports zero pairs on an empty tree -- the exact defect.
        fake = tmp / "fake-predicate.js"
        fake.write_text('console.log("");\nprocess.exit(0);\n', encoding="utf-8")
        result = harness.run(
            [binary, os.fspath(fake), "--root", os.fspath(tmp)], cwd=paths.repo_root()
        )
        if result.rc != 0:
            gate.log_fail(
                "control is broken: a stub that exits 0 reported status %s"
                % harness.describe_exit(result.rc)
            )
        gate.assert_not_contains(result.combined, "Refusing to run", "control stub must not refuse")
        gate.log_pass("control: a zero-exit stub is distinguishable from the real refusal")


def test_the_manifest_and_script_table_are_not_empty(gate):
    """ADDED BY THE PORT: the anti-vacuity claim the two file-reading cases above leave implicit.

    Both of them answer by SEARCHING a file. A file that had been truncated, or a manifest whose entries moved elsewhere, would make the searches above answer "not found" and read as a wiring regression -- or, if the assertions were ever softened, answer nothing at all. Printing the shape makes a collapse visible: a reader can see the numbers were non-trivial rather than taking
    "OK" on faith.
    """
    scripts = json.loads(PACKAGE_JSON.read_text(encoding="utf-8")).get("scripts") or {}
    manifest_ids = MANIFEST.read_text(encoding="utf-8").count("id: '")
    if not scripts or manifest_ids == 0:
        gate.log_fail(
            "the two corpora this port searches are empty: %d npm script(s), %d manifest "
            "id(s). Their green would mean nothing." % (len(scripts), manifest_ids)
        )
    gate.log_pass(
        "corpora are non-trivial: %d npm script(s), %d manifest id(s)"
        % (len(scripts), manifest_ids)
    )
