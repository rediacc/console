"""`rediacc_ci.core.gate_controls` against the bytes `gate-controls.sh` printed.

THE TWIN HAS BEEN DELETED. `.ci/scripts/lib/gate-controls.sh` carried the implementation until W7 P5 retired the staging-tag-guard, release-signing-coverage and release-key-canonical bash gates that sourced it, leaving it with no sourcer at all; `.ci/shadow/w7p5b-gate-controls.observations.jsonl` holds 5 rows of equivalence over 5 distinct trees, and the file was removed on the
strength of them.

`goldens/gate-controls/` holds the library's OWN recorded bytes, captured on its last day in the tree by driving it through the same `_drive` shell function this file used to run live, over the same seven cases. Each golden's provenance header carries the blob sha, so `git cat-file -p <sha>` still yields the program that printed them, and no byte here is a hand-written
expectation.

THE BASH DRIVER IS RECORDED IN THIS FILE and was never a script under `.ci/`. RULING 7 freezes the tracked `.sh` count, and a driver is exactly the kind of file that gets added without anyone deciding to. It is kept verbatim because a reader re-deriving a golden needs the program that produced it, not a description of one.

WHAT THE PLANTED CONTROL PROVES, AND WHY IT IS NOT THE SELFTEST. Every case below could pass against a port that was byte-identical to nothing at all if the comparison were misassembled -- a helper comparing a string to itself, a case list that is empty, a `diff` whose exit code is discarded. `test_the_comparison_can_fail` mutates ONE character of the port's output contract and
asserts the same comparison goes red. It runs the real Python against the real recording; only the expected bytes move.
"""

import textwrap

import pytest

from rediacc_ci.core import gate_controls as gc
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

TWIN = ".ci/scripts/lib/gate-controls.sh"
SLUG = "gate-controls"

# The driver the recording was taken through, kept verbatim. `IFS=$'\x1f'` and
# NOT `$'\t'`: tab is IFS WHITESPACE, so consecutive tabs collapse and an empty
# field vanishes, shifting every later field left. That cost a false STDOUT-DIFF on this differential's first run and is recorded at `rediacc_ci.core.gate_controls`'s SEP.
BASH_DRIVER = textwrap.dedent(
    """
    _drive() {
      source %s
      while IFS=$'\\x1f' read -r verb a b c; do
        [[ -n "$verb" ]] || continue
        case "$verb" in
          check) gate_check "$a" "$b" "$c" ;;
          finish) gate_finish "$a" "$b"; exit $? ;;
          *) exit 2 ;;
        esac
      done
      exit 2
    }
    """
    % TWIN
)

PY_DRIVER = "PYTHONPATH=.ci python3 -m rediacc_ci.core.gate_controls"

US = "\x1f"

# (id, program lines). Each line is already US-joined by `program()`.
CASES = [
    ("all-green", [("check", "one", "a", "a"), ("finish", "1", "all green")]),
    (
        "mixed",
        [
            ("check", "one", "a", "b"),
            ("check", "two", "x", "x"),
            ("finish", "2", "mixed"),
        ],
    ),
    (
        "short-battery",
        [
            ("check", "one", "a", "a"),
            ("check", "two", "b", "b"),
            ("finish", "5", "short battery"),
        ],
    ),
    # EMPTY FIELDS ARE A CASE, not an edge: `gate_check "" "" ""` is what a gate writes when the value it measured was itself empty, and it must PASS.
    (
        "empty-fields",
        [("check", "", "", ""), ("check", " ", "x", ""), ("finish", "1", "empty fields")],
    ),
    # A floor of zero with zero controls. The one shape where the floor cannot fire, kept so a future change that made the floor unconditional is caught.
    ("floor-zero", [("finish", "0", "nothing ran")]),
    # Quoting and globbing hostility, because every field crosses a shell.
    (
        "shell-hostile",
        [("check", "it's *", "a b", "a b"), ("finish", "1", "sub ject")],
    ),
    # A label with a colon and a value with an equals sign: the two characters most likely to be eaten by a naive split on either side.
    (
        "punctuation",
        [("check", "ratio: got=want", "3=4", "3=4"), ("finish", "1", "punct")],
    ),
]


def program(rows: list[tuple[str, ...]]) -> str:
    return "".join(US.join(row) + "\n" for row in rows)


def run_port(text: str) -> tuple[int, str, str]:
    """Feed the recorded bytes to the port's driver. Streams stay separate."""
    quoted = "printf '%%s' %s" % _shquote(text)
    return diff.bash_streams("%s | %s" % (quoted, PY_DRIVER))


def recorded(case_id: str) -> tuple[int, str, str]:
    """One golden, split back into exit code, stdout and stderr."""
    body = frozen.read(SLUG, case_id)
    head, rest = body.split("\n--- stdout ---\n", 1)
    out, err = rest.split("--- stderr ---\n", 1)
    return int(head[len("exit: ") :]), out, err


def _shquote(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


@pytest.mark.parametrize(("case_id", "rows"), CASES, ids=[c[0] for c in CASES])
def test_port_matches_the_twins_recorded_output(case_id: str, rows: list[tuple[str, ...]]) -> None:
    old = recorded(case_id)
    new = run_port(program(rows))
    assert old == new, "case %s: recorded %r vs python %r" % (case_id, old, new)


def test_the_corpus_is_not_empty() -> None:
    """Zero cases is a green that means nothing. The count is printed by -v."""
    assert len(CASES) >= 5, "the differential corpus collapsed to %d case(s)" % len(CASES)


def test_the_corpus_and_the_goldens_are_the_same_set() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(SLUG, {case_id for case_id, _rows in CASES})


def test_the_recording_carries_both_verdicts() -> None:
    """A recording of refusals only agrees with a port that prints no green line at all, and a recording of greens only leaves the floor unexercised."""
    codes = {recorded(case_id)[0] for case_id, _rows in CASES}
    assert codes == {0, 1}, "the recording must hold a green and a red"


def test_the_comparison_can_fail() -> None:
    """A one-character mutation of the port's contract must turn the comparison red.

    THE MUTATION IS APPLIED TO THE EXPECTED BYTES, not to the tree. Editing `gate_controls.py` on disk and restoring it is the other way to write this, and it leaves the tree broken if the test aborts between the two. Here the real recording and the real Python both stay unmodified and the ASSERTION is what moves, which proves the same thing: that these bytes are actually compared.
    """
    rows = dict(CASES)["all-green"]
    old = recorded("all-green")
    new = run_port(program(rows))
    assert old == new, "the case this control mutates does not agree to begin with"
    poisoned = (new[0], new[1].replace("ok    ", "ok   "), new[2])
    assert old != poisoned, (
        "the comparison did not notice a deleted space in `  ok    <label>`, so it "
        "is not comparing stdout at all"
    )
    poisoned_err = (new[0], new[1], new[2] + "x")
    assert old != poisoned_err, "the comparison is ignoring stderr"
    assert (new[0] + 1, new[1], new[2]) != old, "the comparison is ignoring the exit code"


# -- the helpers, exercised directly -----------------------------------------


def test_check_compares_strings_not_objects() -> None:
    """`[[ "$2" == "$3" ]]` has only strings, so 1 and "1" must agree."""
    tally = gc.GateTally()
    assert tally.check("int against str", 1, "1") is True
    assert tally.check("differs", 1, "2") is False
    assert tally.n == 2
    assert tally.fails == 1


def test_finish_is_not_idempotent_in_either_language() -> None:
    """Under the floor, a second `finish` adds a second failure. The twin too."""
    tally = gc.GateTally()
    tally.check("one", "a", "a")
    assert tally.finish(5, "s") == 1
    assert tally.fails == 1
    assert tally.finish(5, "s") == 1
    assert tally.fails == 2


def test_module_tally_is_process_wide_like_the_bash_globals() -> None:
    gc.reset()
    assert gc.gate_check("a", 1, 1) is True
    assert gc.MODULE_TALLY.n == 1
    gc.reset()
    assert gc.MODULE_TALLY.n == 0


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([], 2),
        ([("check", "a", "1", "1")], 2),
        ([("chekc", "a", "1", "1"), ("finish", "1", "s")], 2),
        ([("check", "a", "1")], 2),
        ([("finish", "notanumber", "s")], 2),
    ],
    ids=["empty", "no-finish", "typo-verb", "short-check", "non-numeric-floor"],
)
def test_a_broken_program_is_a_refusal_not_a_pass(rows, expected: int) -> None:
    """Anti-vacuity, in the entry point. Every one of these used to be a 0 or a 1.

    An empty program with no `finish` would otherwise exit 0 having asserted nothing, and a driver typo would surface as "the battery is not being executed as written" -- true, and naming the wrong cause.
    """
    assert gc.run_program([US.join(row) for row in rows]) == expected


def test_a_valid_program_is_not_refused() -> None:
    """The negative control for the five refusals above."""
    assert gc.run_program([US.join(("check", "a", "1", "1")), US.join(("finish", "1", "s"))]) == 0
