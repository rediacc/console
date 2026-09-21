"""Port of `.ci/scripts/test/gates/test-positional-detector.sh`, retired in W7 P5.

Both-ways test for `scripts/lib/positional-cli-detector.ts`.

The detector decides which `rdc ...` examples in docs, help text and locale strings
teach the WRONG syntax. It backs four consumers: two ESLint rules
(i18n/no-positional-cli-syntax, custom/no-positional-cli-syntax-source), scripts/gen/validate-cli-examples.ts, and packages/www/scripts/validate-docs-cli-usage.js.

It has to be tested in BOTH directions, because it can fail in both:

  - Too quiet, and stale docs teach a command form that does not exist.
  - Too loud, and it forbids the CORRECT form. That is not hypothetical: its
    placeholder pass ran over EVERY command path instead of only parent commands
    (which is all its own docstring ever claimed), so once P4 gave leaves
    positional refs it flagged `rdc datastore create <name>` and told the author
    the command "accepts zero positional arguments", a statement that was simply
    false. A validator that reds on correct output blocks the work it exists to
    protect.

WHAT THE PORT CHANGES. The twin writes a driver that loops the whole table inside Node and prints ONE `PASS: positional detector: 12/12 cases` at the end, so a case that stopped being exercised is invisible in the output and only the total moves. Here the driver returns the flagged/not-flagged answer PER CASE as JSON and the Python side records one control each, which means the
transcript names every case and the count is derived from the table rather than typed into a message. The TABLE ITSELF IS UNCHANGED, case for case and reason for reason, because that table IS the specification the twin pinned.

`test_the_case_table_is_not_empty` is the refusal that makes the loop mean something: a driver that returned zero rows would satisfy "no mismatches" while comparing nothing.
"""

import json

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

DETECTOR = paths.from_root("scripts", "lib", "positional-cli-detector.ts")

# [example, must_flag, why] -- the twin's table, unchanged.
CASES: list[tuple[str, bool, str]] = [
    # MUST FLAG -- a command that takes no positional, handed one anyway.
    ("rdc machine list prod-1", True, "zero-positional leaf given a bare word"),
    ("rdc machine list <name>", True, "zero-positional leaf given a placeholder"),
    ("rdc repo <name>", True, "parent given a placeholder; a parent expects a SUBCOMMAND"),
    # MUST NOT FLAG -- the P4 ref grammar. These are the forms we now want taught, and the detector used to reject every one of them.
    ("rdc repo up <repo-ref>", False, "leaf whose primary name IS a positional ref"),
    ("rdc datastore create <name>", False, "leaf that really accepts <datastore>"),
    ("rdc repo replicate <ref>", False, "actionable parent that takes a positional"),
    # MUST NOT FLAG -- nothing positional is being taught at all.
    ("rdc repo secret list", False, "no token after the command path"),
    ("rdc machine list --name x", False, "a flag is not a positional"),
    # MUST NOT FLAG -- a PROSE WORD that ends the clause is not an argument. German splits separable verbs (ausfuehren -> "fuehren Sie ... aus"), so the particle lands AFTER the command and the detector read it as a positional. The German is correct German; the detector was wrong, and it un-translated real work to satisfy a parser bug. Dutch and the Nordic languages split verbs the
    # same way.
    (
        "Falls er bereits angehaengt ist, fuehren Sie rdc config reconcile aus.",
        False,
        "German separable-verb particle after the command is prose, not an argument",
    ),
    ("Voer daarna rdc config reconcile uit.", False, "Dutch separable-verb particle, same class"),
    (
        "Run rdc config reconcile, then retry.",
        False,
        "an English prose word ending the clause is not an argument either",
    ),
    # ...but the fix must not go too quiet: a real argument still flags even at the end of a sentence, because it is value-shaped rather than a bare prose word.
    (
        "Run rdc machine list prod-1.",
        True,
        "value-shaped token is a positional, sentence-final or not",
    ),
]

# THE TABLE TRAVELS IN AN ENVIRONMENT VARIABLE, not in argv. `tsx --eval` does not place a caller's trailing arguments where a plain `node --eval` does, so an argv index here is a number that is right on one runner and `undefined` on another -- and `JSON.parse(undefined)` throws inside Node, which arrives as a stack trace about JSON rather than as a finding about the detector.
DRIVER = """
import { scanText } from %(detector)s;
const CASES = JSON.parse(process.env.POSITIONAL_CASES);
const out = CASES.map((example) => ({
  example,
  flagged: scanText(example).length > 0,
}));
process.stdout.write('\\n@@RESULT@@' + JSON.stringify(out));
"""


def scan_all(gate) -> dict[str, bool]:
    """{example: flagged} from the REAL detector, one tsx process for the table."""
    if not DETECTOR.is_file():
        gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(DETECTOR))
    npx = harness.require_tool(
        "npx", "install node; the detector is a TypeScript module driven through tsx"
    )
    body = DRIVER % {"detector": json.dumps(str(DETECTOR))}
    result = harness.run(
        [npx, "tsx", "--eval", body],
        cwd=paths.repo_root(),
        env={"POSITIONAL_CASES": json.dumps([c[0] for c in CASES])},
    )
    marker = "@@RESULT@@"
    if result.rc != 0 or marker not in result.out:
        gate.log_fail(
            "the detector driver did not report (rc=%d).\n--- stdout ---\n%s\n--- stderr ---\n%s"
            % (result.rc, result.out, result.err)
        )
    rows = json.loads(result.out.split(marker, 1)[1].strip())
    return {row["example"]: bool(row["flagged"]) for row in rows}


def test_the_case_table_is_not_empty(gate):
    """PORT-ONLY anti-vacuity. A table that emptied, or a driver that returned no rows, makes `test_detector_both_ways` report "no mismatches" having compared nothing. Both halves are checked, because either one alone can go quiet."""
    if not CASES:
        gate.log_fail("the case table is EMPTY, so the both-ways case below compares nothing")
    flagging = [c for c in CASES if c[1]]
    clean = [c for c in CASES if not c[1]]
    # BOTH DIRECTIONS MUST BE REPRESENTED. A table of only must-flag cases would pass against a detector that flags literally everything.
    if not flagging or not clean:
        gate.log_fail(
            "the table has %d must-flag and %d must-not-flag case(s). A table with only "
            "one direction cannot catch a detector that is uniformly loud or uniformly "
            "quiet." % (len(flagging), len(clean))
        )
    gate.log_pass(
        "%d case(s) in the table: %d must flag, %d must not"
        % (len(CASES), len(flagging), len(clean))
    )


def test_detector_both_ways(gate):
    gate.log_test("positional detector flags wrong syntax and accepts the P4 ref grammar")
    answers = scan_all(gate)
    missing = [example for example, _, _ in CASES if example not in answers]
    if missing:
        gate.log_fail("the driver returned no answer for %d case(s): %s" % (len(missing), missing))
    mismatches = []
    for example, must_flag, why in CASES:
        flagged = answers[example]
        if flagged != must_flag:
            mismatches.append(
                '  MISMATCH: "%s" -> flagged=%s, expected=%s (%s)'
                % (example, str(flagged).lower(), str(must_flag).lower(), why)
            )
    if mismatches:
        gate.log_fail(
            "positional-cli-detector did not behave as expected\n%s\n%d case(s) wrong"
            % ("\n".join(mismatches), len(mismatches))
        )
    for example, must_flag, why in CASES:
        gate.ok("%s: %s (%s)" % ("FLAGGED" if must_flag else "clean  ", example, why))
    gate.tally_finish("positional detector")
    gate.log_pass("positional detector: %d/%d cases, both directions" % (len(CASES), len(CASES)))
