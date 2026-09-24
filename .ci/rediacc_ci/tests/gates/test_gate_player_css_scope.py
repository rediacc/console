r"""`scripts/gates/check-player-css-scope.ts`, its eight plants, and TWO MUTANTS of it.

WHY THIS EXISTS RATHER THAN TRUSTING THE GATE'S OWN SELFTEST. That selftest builds its own corpora, so it proves the scanner reads what the selftest wrote. It cannot prove the thing that actually matters about a negative assertion: that the gate would still fire if its DETECTION were wrong rather than its arithmetic.
Two edits make the gate green over a corpus it should refuse, and neither touches a line the selftest reads. Widening the marker list makes a NON-player stylesheet count as the player's, which over-reports and would have had the fix chasing pages that were never offenders. Deleting F6 makes "no page links the player sheet" satisfiable by deleting plyr outright.
The gate's own plants are what catch both, so this file's job is to prove those plants can FAIL.

THE PLAN NAMED THE TWO ASSERTIONS AND THIS FILE KEEPS ITS WORDS: widening the markers must red the selftest NAMING P4, and deleting F6 must red it NAMING P6. The plant numbers are therefore a contract between two files, and the gate's own header says so where a renumbering would happen.

WHY IT IS PYTHON AND NOT THE `.sh` THE PLAN ASKED FOR. Ruling 7 freezes `.ci/` and `.claude/` against new tracked shell: `check_language_policy.py` sets `COVERED_ROOTS = (".ci", ".claude")` and refuses an addition to its path set. The two mutants and the written-outside-the-repo requirement carry over from the plan unchanged; only the language does not.

WHERE THE MUTANTS LIVE. Outside the repo, with `node_modules` and `scripts/lib` SYMLINKED in, which is what `check:ci-pool-writer-safety` requires and what the client-bundle-budget port already does.
The symlink for `lib` is not decoration: the gate imports `../lib/repo-root.js`, and node resolves a symlinked module to its REAL path, so `REPO_ROOT` inside the mutant still walks to this repository rather than to a temp directory.
A mutant that threw on import would exit non-zero for a reason that has nothing to do with the plant, and the case asserting a red would go green on it.

NO `xdist_group`. Each case runs `tsx` in a subprocess against its own `tmp_path`, and the real-dist arm only reads.
"""

import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root("scripts", "gates", "check-player-css-scope.ts")
DIST = paths.from_root("packages", "www", "dist")

# MUTANT 1. `.tvp-root` is the marker the gate's header records as MEASURED-AND-REJECTED: it appears in a non-player bundle too, so admitting it makes `a/other.css` a player stylesheet and `over.html` an offender. P4 is the plant that says it must not be.
MARKERS_FIXED = "const MARKERS = ['.plyr__control', '.tvp-caption-word'];"
MARKERS_WIDE = "const MARKERS = ['.plyr__control', '.tvp-caption-word', '.tvp-root'];"

# MUTANT 2. F6 is the positive half of the assertion; with its condition dead, a build in which nothing loads the player's stylesheet reports a clean tree. P6 is the plant that says it must refuse.
F6_FIXED = "if (unreferenced.length === r.playerCss.length) {"
F6_DEAD = "if (false) {"

# The eight plants the plan specifies, by the label each prints. Asserted as a SET so dropping one reds here rather than quietly shrinking the control surface, which is the failure the box this file closes was opened for: the gate had six floors and four checks.
PLANTS = (
    "P1 PLANT",
    "P2 PLANT",
    "P3 PLANT",
    "P4 CONTROL",
    "P5 PLANT",
    "P6 PLANT",
    "P7 PLANT",
    "P8 PLANT",
)


def run_tsx(gate, script: pathlib.Path) -> harness.RunResult:
    """Drive the gate, or a mutant of it, through the workspace `npx tsx` from the repo root.

    The existence refusal is not decoration: one caller hands this a file written a moment earlier, and a mutant that failed to be written would make `tsx` exit non-zero for a reason that has nothing to do with the plant.
    """
    if not script.is_file():
        gate.log_fail(
            "there is nothing to run at %s, so this case could not exercise the subject at all -- which is a FAILURE and not a pass"
            % script
        )
    npx = harness.require_tool(
        "npx", "install node; the subject is a TypeScript program driven through tsx"
    )
    return harness.run([npx, "tsx", str(script)], cwd=paths.repo_root())


def write_mutant(gate, tmp_path: pathlib.Path, fixed: str, mutated: str) -> pathlib.Path:
    """A one-edit copy of the gate, in a tree where its relative import still resolves."""
    source = GATE.read_text(encoding="utf-8")
    if fixed not in source:
        # THE VACUITY GUARD. A replacement that stopped matching leaves the mutant byte-identical to the gate, and a case asserting "this must go red" would then be asserting it about the UNMUTATED gate, which is exactly the shape a mutant exists to refute.
        gate.log_fail(
            "the mutation target %r is no longer in %s, so this control would have run the unmutated gate and called its green a caught defect"
            % (fixed, paths.relative_to_root(GATE))
        )
    (tmp_path / "node_modules").symlink_to(paths.from_root("node_modules"))
    (tmp_path / "lib").symlink_to(paths.from_root("scripts", "lib"))
    (tmp_path / "gates").mkdir()
    target = tmp_path / "gates" / "mutant.ts"
    target.write_text(source.replace(fixed, mutated), encoding="utf-8")
    return target


def controls(text: str) -> dict[str, str]:
    """`{label: PASS|FAIL}` for every control line the gate printed.

    PARSED RATHER THAN GREPPED FOR `PASS`, because counting the word answers the wrong question. A run in which P4 flipped to FAIL still contains eleven PASSes, and a run whose selftest never executed contains none of either -- which a `not in` assertion reads as identical to a clean one.
    """
    out = {}
    for line in text.splitlines():
        stripped = line.strip()
        for verdict in ("PASS", "FAIL"):
            if stripped.startswith(verdict + "  "):
                out[stripped[len(verdict) + 2 :].strip()] = verdict
    return out


def verdict_for(gate, seen: dict[str, str], plant: str) -> str:
    """The verdict of the one control whose label starts with `plant`, refusing on zero or many."""
    matches = [(label, verdict) for label, verdict in seen.items() if label.startswith(plant)]
    if len(matches) != 1:
        gate.log_fail(
            "expected exactly one control labelled %r, found %d (%s). The plant numbering is a contract between this file and the gate's selftest; renumbering one side silently un-checks the other."
            % (plant, len(matches), sorted(label for label, _ in matches))
        )
    return matches[0][1]


def test_the_gate_runs_all_eight_plants_and_every_one_passes(gate):
    """Box 1's contract, made executable from outside the gate."""
    gate.log_test("the gate's selftest carries eight plants and a clean counterpart, and all pass")
    if not GATE.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(GATE))
    result = run_tsx(gate, GATE)
    seen = controls(result.combined)
    if not seen:
        gate.log_fail(
            "the gate printed no control line at all (rc=%s). Its selftest did not run, so nothing below could have been checked"
            % harness.describe_exit(result.rc),
            result,
        )
    for plant in PLANTS:
        gate.assert_eq(
            verdict_for(gate, seen, plant), "PASS", "%s must pass on the tree as it stands" % plant
        )
    failed = sorted(label for label, verdict in seen.items() if verdict == "FAIL")
    gate.assert_eq(failed, [], "no control may fail")
    gate.log_pass("all eight plants and %d control(s) in total ran and passed" % len(seen))


def test_mutant_widening_the_marker_list_reds_p4(gate, tmp_path):
    """THE FIRST MUTANT. Over-matching the stylesheet must be caught by P4, not tolerated."""
    gate.log_test(
        "CONTROL: admitting .tvp-root as a player marker must red the selftest, naming P4"
    )
    mutant = write_mutant(gate, tmp_path, MARKERS_FIXED, MARKERS_WIDE)
    result = run_tsx(gate, mutant)
    gate.assert_exit(2, result, "a failed instrument control must refuse before any verdict")
    seen = controls(result.combined)
    gate.assert_eq(
        verdict_for(gate, seen, "P4 CONTROL"),
        "FAIL",
        "P4 is the plant that catches an over-matching marker list",
    )
    gate.assert_contains(
        result.combined,
        "instrument control failed",
        "and the gate must say so rather than report on the real tree",
    )
    # The other direction in the same run: a mutation that reddened EVERYTHING would satisfy the assertion above while proving nothing about P4 in particular.
    gate.assert_eq(
        verdict_for(gate, seen, "P1 PLANT"),
        "PASS",
        "the plant for the verdict itself is unaffected by the marker list",
    )
    gate.assert_eq(verdict_for(gate, seen, "P6 PLANT"), "PASS", "and so is F6's")
    gate.log_pass("CONTROL: P4 detects the exact over-match, rather than passing beside it")


def test_mutant_deleting_f6_reds_p6(gate, tmp_path):
    """THE SECOND MUTANT. Without F6, deleting plyr outright would pass this gate."""
    gate.log_test("CONTROL: killing F6's condition must red the selftest, naming P6")
    mutant = write_mutant(gate, tmp_path, F6_FIXED, F6_DEAD)
    result = run_tsx(gate, mutant)
    gate.assert_exit(2, result, "a failed instrument control must refuse before any verdict")
    seen = controls(result.combined)
    gate.assert_eq(
        verdict_for(gate, seen, "P6 PLANT"), "FAIL", "P6 is the plant that catches a dead F6"
    )
    gate.assert_eq(
        verdict_for(gate, seen, "P4 CONTROL"),
        "PASS",
        "and F6 is the only thing this mutant touches",
    )
    gate.assert_eq(
        verdict_for(gate, seen, "P1 PLANT"), "PASS", "the verdict's own plant is unaffected"
    )
    gate.log_pass("CONTROL: P6 detects a dead F6 specifically, not a general unhappiness")


def test_the_real_dist_verdict_is_clean_and_not_vacuous(gate):
    """The gate's real subject, and the floors it reports on the way.

    A LOUD SKIP AND NOT A FAILURE when `dist` is absent, which is the one place this directory's "unknown is a failure" rule is deliberately not applied: the arm asks a question about a BUILD ARTIFACT, and a tree that has not been built has no answer rather than an unknown one. The gate itself refuses in that case (F1), which is the behaviour the case above already covers.
    """
    gate.log_test("the real build must report zero offenders over a corpus that is really there")
    if not DIST.is_dir():
        gate.log_pass(
            "SKIP (loudly): %s absent, so the real-build arm asserted NOTHING"
            % paths.relative_to_root(DIST)
        )
        return
    result = run_tsx(gate, GATE)
    gate.assert_exit(0, result, "the tree is fixed, so the gate must be green over the real dist")
    gate.assert_contains(
        result.out, "page(s),", "and it must print the shape it scanned, not merely a verdict"
    )
    gate.assert_contains(
        result.out, "with a mount; no page links", "naming what it found linked without a mount"
    )
    gate.log_pass("the real dist reports no offender, with its page, link and mount counts printed")
