"""Port of `.ci/scripts/test/gates/test-trap-registry.sh`.

Behavioural test for `.ci/scripts/quality/check-trap-registry.sh`, and for the
corpus parser it shares with the Stop hook (`.claude/hooks/stop/wl_store.py`).

WHAT IT GUARDS. `docs/agent-reference/TRAPS.md` is a REGISTRY, not prose: every
`## ` entry names the instrument that enforces it, and the gate proves that
pointer RESOLVES (F4) and is LIVE (F5). Presence alone would be worse than
nothing, because the cheapest thing to name under a coverage gate is a check that
cannot fire, and a gate demanding a name manufactures those at one per trap while
reporting full coverage.

THE SUBJECT IS CONTROL-FIRST, so the thing most worth testing is that its own
controls are not decorative. It plants every one of its assertions against a
fixture, requires each to red WITH THE MATCHING MESSAGE, requires two clean
fixtures to stay green, and refuses to judge the real tree if any of them
misbehaves. Two of those controls found real bugs in the gate while it was being
written (an empty `Residue` collapsing because TAB is IFS whitespace in bash, and
a manifest block scan that could not see a single-line entry), which is the
argument for keeping them in front of every run rather than behind a flag.

THE PLANTS BELOW GO INTO A COPY OF THE REAL CORPUS, never the tracked file. A
killed test must not strand a mutated TRAPS.md in a shared checkout, and this tree
routinely holds other sessions' uncommitted work.

WHY THIS MODULE OPTS IN TO THE REAL-TREE GROUP. `test_real_tree_is_green_and_the_controls_fired`
runs the subject seam-free, and every `--scan-only` case leaves the manifest, the
dispatcher, the hook suite and `.claude/settings.json` REAL so a planted corpus is
judged against live resolution sources. A battery step rewriting any of those
mid-scan is a divergence that would be blamed on this port. `REAL_TREE_TWIN = True`
buys the serialisation, and it is honoured only because this module declares no
`XDIST_GROUP` of its own; see `real_tree_admission` in `test_twin_parity.py`.

NO `TWIN_TIMEOUT` DECLARED. Measured 2026-09-08: the twin takes 63s and this
module takes comparable time, both far inside the 600s default. A declared
timeout that nothing needs is a number that will be believed later.

TRAP_FLOOR IS READ, NEVER TYPED. The subject prints `N entries (floor F)` and the
added shape case parses BOTH out of that one line. A copy of the floor here would
be a third place it lives (it is already in `check-trap-registry.sh` and
`.ci/rediacc_ci/quality/trap_registry.py`, whose agreement
`.ci/rediacc_ci/tests/test_quality_trap_registry.py` asserts), and a third copy is
the one that goes stale.

TWO TWIN CASES ARE REWRITTEN RATHER THAN LIFTED, and both go the same way. The
twin's two `wl_store` cases run a python heredoc that prints `PASS `/`FAIL ` lines
and then asserts the merged text contains no `FAIL`. This port runs the same
functions in the same nested interpreter and prints their RESULTS as JSON, so each
of the twin's seven checks becomes an assertion with its own message. The
difference matters: `assert_not_contains(out, "FAIL")` is also satisfied by an
interpreter that printed nothing at all, so the port asserts the subprocess's exit
code first and then compares values.
"""

import json
import os
import re

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

BASH_TWIN = ".ci/scripts/test/gates/test-trap-registry.sh"

# The real-tree case runs the subject seam-free, and every scan resolves pointers
# against the live manifest, dispatcher, hook suite and settings. See the docstring.
REAL_TREE_TWIN = True

GATE_REL = ".ci/scripts/quality/check-trap-registry.sh"
GATE = paths.from_root(*GATE_REL.split("/"))
CORPUS_REL = "docs/agent-reference/TRAPS.md"
CORPUS = paths.from_root(*CORPUS_REL.split("/"))
STOP_DIR = paths.hooks_stop_dir()

# `trap registry OK: 78 entries (floor 78), 12 JUDGMENT-ONLY, ...`
SHAPE_RE = re.compile(r"(\d+) entries \(floor (\d+)\)")

# The subject reads the whole tree per scan, and the seam-free run also drives ~20
# fixture controls. Comfortably over the 63s measured on 2026-09-08, and well under
# the parity driver's 600s ceiling for the module as a whole.
GATE_TIMEOUT = 300


def require_gate(gate) -> str:
    """The subject and its corpus, proved present before anything is claimed.

    The twin asserts `-x` on the gate rather than `-f`, and that is the stronger
    claim: a subject that lost its executable bit still reads fine and still runs
    under an explicit `bash`, so a port checking only existence would pass a state
    the twin refuses.
    """
    if not GATE.is_file():
        gate.log_fail("gate not found: %s" % GATE_REL)
    if not os.access(GATE, os.X_OK):
        gate.log_fail("gate not executable: %s" % GATE_REL)
    if not CORPUS.is_file():
        gate.log_fail("corpus missing: %s" % CORPUS_REL)
    return harness.require_tool("bash", "install bash; the subject IS a bash script")


def corpus_text(gate) -> str:
    """The real corpus, with ANTI-VACUITY on the read itself.

    Every plant below is a transformation of this text, and a transformation of an
    empty string produces a fixture that is also empty -- which the subject would
    red on for the WRONG reason (the population floor), while each case's
    message-matching assertion quietly failed to be about anything.
    """
    require_gate(gate)
    text = CORPUS.read_text(encoding="utf-8")
    if not text.strip():
        gate.log_fail(
            "%s read as empty, so every plant below would be a transformation of "
            "nothing and their reds would say nothing about the gate." % CORPUS_REL
        )
    return text


def scan_corpus(gate, path) -> harness.RunResult:
    """`scan_corpus` from the twin: one corpus, every OTHER source left real.

    `--scan-only` skips the subject's own control suite, which is what makes a
    per-case scan affordable. Pointers still resolve against the live manifest,
    package.json, dispatcher, hook suite and settings, so a plant is judged against
    the tree as it actually is.
    """
    bash = require_gate(gate)
    return harness.run(
        [bash, os.fspath(GATE), "--scan-only"],
        cwd=paths.repo_root(),
        env={"TRAP_CORPUS": os.fspath(path)},
        timeout=GATE_TIMEOUT,
    )


def plant(gate, destination, transform) -> None:
    """Write `transform(real corpus)` to `destination`, refusing a no-op.

    THE CONTROL ON THE CONTROL, and the twin has it for a reason: a plant that did
    not land leaves an unmodified corpus, the gate correctly stays green, and the
    case reads as "the gate failed to catch it". `cmp -s` in the twin; a text
    comparison here. Either way the message says the PLANT did not land, so the
    reader looks at the anchor rather than at the subject.
    """
    original = corpus_text(gate)
    mutated = transform(original)
    if mutated == original:
        gate.log_fail("the plant did not land: the corpus is unchanged")
    destination.write_text(mutated, encoding="utf-8")


def run_stop_hook_probe(gate, code: str, *args: str) -> dict:
    """Run `code` in a nested python3 with the Stop hook directory importable.

    The twin's shape exactly -- `python3 - "$STOP_DIR" "$d"` from the repo root --
    and a nested interpreter rather than an in-process import on purpose:
    `wl_store` is the live Stop hook's module, and importing it into the pytest
    process would put its module-level state beside every other test in the
    session for the rest of the run.

    THE EXIT CODE IS ASSERTED BEFORE THE OUTPUT IS READ. The twin's
    `assert_not_contains "$out" "FAIL"` is also satisfied by an interpreter that
    died before printing anything, and a crash that reads as a pass is the shape
    this directory exists to refuse.
    """
    python3 = harness.require_tool(
        "python3", "install python3; the Stop hook's parser IS a python module"
    )
    result = harness.run(
        [python3, "-", os.fspath(STOP_DIR), *args],
        cwd=paths.repo_root(),
        stdin=code,
        timeout=GATE_TIMEOUT,
    )
    if result.rc != 0:
        gate.log_fail(
            "the wl_store probe exited %d rather than running its checks, so nothing "
            "was compared. stdout: %s stderr: %s" % (result.rc, result.out, result.err)
        )
    try:
        return json.loads(result.out)
    except ValueError:
        gate.log_fail(
            'the wl_store probe printed something that is not JSON: "%s" (stderr: "%s")'
            % (result.out, result.err)
        )
        raise  # unreachable; log_fail raises


HEADINGS_PROBE = """
import json
import sys

sys.path.insert(0, sys.argv[1])
import wl_store as S  # noqa: E402

base = sys.argv[2]
print(
    json.dumps(
        {
            "fenced": S.trap_headings(base + "/fence"),
            "plain": S.trap_headings(base + "/plain"),
        }
    )
)
"""

PROMPT_PROBE = """
import json
import sys

sys.path.insert(0, sys.argv[1])
import wl_store as S  # noqa: E402

print(json.dumps({"got": S.trap_prompt_lines(sys.argv[2] + "/filter")}))
"""


# ---------------------------------------------------------------------------


def test_real_tree_is_green_and_the_controls_fired(gate):
    """Seam-free: the real invocation, real corpus, real everything.

    The three message assertions are the point. "the tree is clean" from a gate
    whose own controls silently stopped firing is exactly the green this estate
    refuses, so the verdict must state that the planted defects went red, that the
    clean fixtures stayed green, and what the population actually was.
    """
    bash = require_gate(gate)
    result = harness.run([bash, os.fspath(GATE)], cwd=paths.repo_root(), timeout=GATE_TIMEOUT)
    gate.assert_exit_code(
        0,
        result.rc,
        "the real corpus must pass the registry gate (output: %s)" % result.combined,
    )
    gate.assert_contains(
        result.combined,
        "planted defects red",
        "the verdict must state that its controls fired, not merely that the tree is clean",
    )
    gate.assert_contains(
        result.combined,
        "clean fixtures green",
        "the controls must include the converse direction",
    )
    gate.assert_contains(
        result.combined,
        "entries (floor",
        "the verdict must print the SHAPE, so a reader can see the population did not collapse",
    )
    gate.log_pass("real corpus green, controls fired in both directions, shape printed")


def _drop_lines(text: str, exact: str) -> str:
    """The twin's `sed '/^<exact>$/d'`: drop every line EQUAL to `exact`.

    A whole-line match, not a substring one. `Trap-Id: x` is a prefix of
    `Trap-Id: x-and-more`, so a substring delete could take a second entry's
    identity with it and the case would red for a reason it never claimed.
    """
    lines = text.split("\n")
    return "\n".join(line for line in lines if line != exact)


def test_a_missing_trap_id_is_caught(gate):
    """F2: identity. An entry with no Trap-Id cannot be pointed at, deduplicated or
    tracked, so the registry stops being a registry one entry at a time."""
    with harness.temp_dir() as d:
        plant(
            gate,
            d / "p.md",
            lambda text: _drop_lines(text, "Trap-Id: cancelled-run-not-passed"),
        )
        result = scan_corpus(gate, d / "p.md")
        gate.assert_exit_code(1, result.rc, "an entry with no Trap-Id must red (F2)")
        gate.assert_contains(
            result.combined, "has no Trap-Id", "the finding must name the missing field"
        )
        gate.log_pass("F2: a stripped Trap-Id reds, and the message names it")


def test_a_dangling_gate_pointer_is_caught(gate):
    """F4: the pointer must RESOLVE, against the live manifest rather than against a
    fixture's idea of one."""
    with harness.temp_dir() as d:
        plant(
            gate,
            d / "p.md",
            lambda text: text.replace(
                "Enforced-By: gate:check:ci-go-module-sync",
                "Enforced-By: gate:check:does-not-exist",
            ),
        )
        result = scan_corpus(gate, d / "p.md")
        gate.assert_exit_code(1, result.rc, "a gate: pointer at a non-existent id must red (F4)")
        gate.assert_contains(
            result.combined,
            "check:does-not-exist",
            "the finding must name the pointer that does not resolve",
        )
        gate.log_pass("F4: a dangling gate: pointer reds against the live manifest")


def test_a_scheduled_but_unrun_gate_is_caught(gate):
    """F5: the pointer must be LIVE.

    `build:packages` is a REAL manifest entry that is deliberately `gate: false` --
    a prerequisite node that validates nothing. Naming it would be the cheapest way
    to look covered, which is exactly what F5 exists to refuse.
    """
    with harness.temp_dir() as d:
        plant(
            gate,
            d / "p.md",
            lambda text: text.replace(
                "Enforced-By: gate:check:ci-go-module-sync",
                "Enforced-By: gate:build:packages",
            ),
        )
        result = scan_corpus(gate, d / "p.md")
        gate.assert_exit_code(
            1, result.rc, "a pointer at a manifest entry with gate:false must red (F5)"
        )
        gate.assert_contains(
            result.combined,
            "never schedules it",
            "the finding must say the gate is not run, not merely that it exists",
        )
        gate.log_pass("F5: a real-but-unscheduled gate id reds")


def _drop_entry(text: str, marker: str) -> str:
    """The twin's awk: drop every line of the `## ` section whose heading holds
    `marker`, and keep everything else. Skipping resets at the next `## `, which is
    what stops the deletion running to the end of the file."""
    out = []
    skip = False
    for line in text.split("\n"):
        if line.startswith("## "):
            skip = marker in line
        if not skip:
            out.append(line)
    return "\n".join(out)


def test_a_deleted_entry_is_caught(gate):
    """F1: the population floor. A corpus that is emptied, truncated or relocated
    reds instead of passing vacuously -- which is the only signal an unratcheted
    floor ever gives, and the reason the subject's own comment records the two
    occasions it was left behind."""
    with harness.temp_dir() as d:
        plant(gate, d / "p.md", lambda text: _drop_entry(text, "git branch --merged"))
        result = scan_corpus(gate, d / "p.md")
        gate.assert_exit_code(1, result.rc, "a shrinking corpus must red (F1)")
        gate.assert_contains(result.combined, "below the floor", "the finding must name the floor")
        gate.log_pass("F1: deleting an entry drops below the floor and reds")


def test_an_unchanged_copy_is_green(gate):
    """THE CONVERSE. Without it every assertion above is satisfied by a gate that
    reds on everything, including a correct corpus."""
    with harness.temp_dir() as d:
        (d / "clean.md").write_text(corpus_text(gate), encoding="utf-8")
        result = scan_corpus(gate, d / "clean.md")
        gate.assert_exit_code(
            0,
            result.rc,
            "an unmodified copy of the corpus must stay green (output: %s)" % result.combined,
        )
        gate.log_pass("CONTROL: an unmodified copy of the corpus is green")


# ---------------------------------------------------------------------------
# The stop hook's parser. wl_store.trap_headings was a bare startswith("## ")
# with no fence state: latent while no trap body carried a fenced heading, and
# activated the moment the registry required an id per entry.
# ---------------------------------------------------------------------------


def test_stop_hook_parser_ignores_fenced_headings(gate):
    with harness.temp_dir() as d:
        for flavour in ("fence", "plain"):
            (d / flavour / "docs" / "agent-reference").mkdir(parents=True)
        (d / "fence" / "docs" / "agent-reference" / "TRAPS.md").write_text(
            "# Traps\n"
            "\n"
            "## A real entry\n"
            "Trap-Id: a-real-entry\n"
            "Enforced-By: JUDGMENT-ONLY\n"
            "Residue: the residue sentence.\n"
            "\n"
            "```markdown\n"
            "## Not A Trap\n"
            "```\n"
            "\n"
            "~~~\n"
            "## Also Not A Trap\n"
            "~~~\n",
            encoding="utf-8",
        )
        # The SAME line unfenced must be seen, or the case above proves only that
        # the parser ignores things.
        (d / "plain" / "docs" / "agent-reference" / "TRAPS.md").write_text(
            "# Traps\n"
            "\n"
            "## A real entry\n"
            "Trap-Id: a-real-entry\n"
            "Enforced-By: JUDGMENT-ONLY\n"
            "Residue: the residue sentence.\n"
            "\n"
            "## Not A Trap\n",
            encoding="utf-8",
        )
        got = run_stop_hook_probe(gate, HEADINGS_PROBE, os.fspath(d))
        gate.assert_eq(
            got["fenced"],
            ["A real entry"],
            "fenced-headings-are-not-entries",
        )
        gate.assert_eq(
            got["plain"],
            ["A real entry", "Not A Trap"],
            "CONTROL-the-same-line-unfenced-is-an-entry",
        )
        gate.log_pass(
            "wl_store.trap_headings skips fenced ## examples and still sees unfenced ones"
        )


def test_prompt_filter_keeps_only_the_residue(gate):
    with harness.temp_dir() as d:
        (d / "filter" / "docs" / "agent-reference").mkdir(parents=True)
        (d / "filter" / "docs" / "agent-reference" / "TRAPS.md").write_text(
            "# Traps\n"
            "\n"
            "## Fully mechanized\n"
            "Trap-Id: fully-mechanized\n"
            "Enforced-By: gate:check:ci-breakpoint-drift\n"
            "Residue:\n"
            "\n"
            "body\n"
            "\n"
            "## Mechanized with residue\n"
            "Trap-Id: mechanized-with-residue\n"
            "Enforced-By: gate:check:ci-breakpoint-drift\n"
            "Residue: the part the gate does not reach.\n"
            "\n"
            "body\n"
            "\n"
            "## Judgment only\n"
            "Trap-Id: judgment-only-entry\n"
            "Enforced-By: JUDGMENT-ONLY\n"
            "Residue: nothing watches this.\n"
            "\n"
            "body\n"
            "\n"
            "## Unclassified legacy entry\n"
            "\n"
            "body\n",
            encoding="utf-8",
        )
        got = run_stop_hook_probe(gate, PROMPT_PROBE, os.fspath(d))["got"]
        # A trap something already watches leaves the prompt entirely.
        gate.assert_not_contains("\n".join(got), "Fully mechanized", "mechanized-entry-is-dropped")
        # Residue is what costs attention, and it renders as the SENTENCE.
        gate.assert_contains("\n".join(got), "the part the gate does not reach.", "residue-is-kept")
        gate.assert_contains("\n".join(got), "nothing watches this.", "judgment-only-is-kept")
        # Unknown is never folded into fine.
        gate.assert_contains(
            "\n".join(got), "Unclassified legacy entry", "unclassified-entry-is-kept"
        )
        gate.assert_eq(len(got), 3, "nothing-else-leaked")
        gate.log_pass(
            "prompt filter keeps residue and judgment-only, drops mechanized, keeps unclassified"
        )


def test_the_real_corpus_is_over_its_own_floor(gate):
    """ADDED BY THE PORT: read the SHAPE out of the real verdict, do not just look
    for the words.

    `test_real_tree_is_green_and_the_controls_fired` asserts the substring
    `entries (floor`, which a gate printing `0 entries (floor 0)` would satisfy. The
    numbers are parsed here instead, and both are DERIVED from the subject's own
    output rather than typed: `TRAP_FLOOR` already lives in two files whose
    agreement is asserted elsewhere, and a third copy here is the one that would go
    stale.

    The floor is a RATCHET, so `entries == floor` is the normal, healthy state on
    the day an entry is added and the number is bumped with it. What is refused is a
    corpus that has fallen UNDER its own floor while the gate still reported green,
    and a floor of zero, which would make the population claim vacuous.
    """
    bash = require_gate(gate)
    result = harness.run([bash, os.fspath(GATE)], cwd=paths.repo_root(), timeout=GATE_TIMEOUT)
    gate.assert_exit_code(0, result.rc, "the real run must pass before its shape means anything")
    match = SHAPE_RE.search(result.combined)
    if not match:
        gate.log_fail(
            "the real run exited 0 without printing its population and floor, so nobody "
            'can see a collapse. Output: "%s"' % result.combined
        )
    entries, floor = int(match.group(1)), int(match.group(2))
    if floor <= 0:
        gate.log_fail(
            "the subject reports a floor of %d, which makes its population claim "
            "vacuous: every corpus clears a floor of zero." % floor
        )
    if entries < floor:
        gate.log_fail(
            "%s holds %d entr(ies) against a floor of %d and the gate still reported "
            "green." % (CORPUS_REL, entries, floor)
        )
    gate.log_pass(
        "%s holds %d entr(ies) against its own floor of %d" % (CORPUS_REL, entries, floor)
    )
