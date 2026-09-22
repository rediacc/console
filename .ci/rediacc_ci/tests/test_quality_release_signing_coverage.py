"""`rediacc_ci.quality.release_signing_coverage` against the shell it replaces.

WHY A DIFFERENTIAL AND NOT A TABLE OF EXPECTED STRINGS. Two of this gate's three moving parts are not readable: a `sed` BRE with a bracket expression containing a space and a pipe, and an eleven-line `awk` program with a stateful `inarm` flag. Their behaviour on the awkward inputs -- an arm with no space around the pipe, an arm that is only `)`, a guard sitting after the `esac`, a
second one-line case arm further down -- is decided by POSIX bracket-expression rules and by awk's `sub` semantics rather than by anything a reader could infer. A table of expected strings would be a table of what the PORT does, asserted against itself.

The bash fragments below are lifted from `.ci/scripts/quality/check-release-signing-coverage.sh` (the `formats_of` and `guarded_in` function bodies), with nothing changed but the substitution of their arguments. The tally the gate prints its verdict through came from `.ci/scripts/lib/gate-controls.sh`, which has since been retired, so that half is compared against
`goldens/gate-controls-tally/` rather than against a live library. They are NOT the whole gate: the whole gate is what the committed shadow ledger `.ci/shadow/w7p2-signing-coverage.observations.jsonl` compares over five distinct trees. This file covers the seams that ledger cannot isolate, because a ledger row can only say the two sides agreed on THAT tree.
"""

import contextlib
import io
import pathlib

import pytest

from rediacc_ci.quality import release_signing_coverage as rsc
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

# The `formats_of` pipeline, verbatim from the twin with `"$1"` replaced by the fixture path. Four stages; the comment on each is in the port's docstring.
_FORMATS_PIPELINE = (
    r"""sed -n 's/^[[:space:]]*\([a-z |]*\))[[:space:]]*;;[[:space:]]*$/\1/p' builder.sh |"""
    """ head -1 | tr -d ' ' | tr '|' '\\n' | grep -v '^$' || true"""
)

# The `guarded_in` awk program, verbatim. `-v fmt=` is how the twin passes the
# format name, so the quoting question the port has to get right is exercised here rather than assumed.
_GUARDED_AWK = r"""awk -v fmt="%s" '
        /^[[:space:]]*[a-z][a-z |]*\)[[:space:]]*$/ {
            arm = $0
            sub(/\)[[:space:]]*$/, "", arm)
            gsub(/[[:space:]]/, "", arm)
            inarm = 0
            m = split(arm, parts, "|")
            for (i = 1; i <= m; i++) if (parts[i] == fmt) inarm = 1
            next
        }
        /^[[:space:]]*;;[[:space:]]*$/ { inarm = 0; next }
        inarm && /RELEASE_SIGNING_REQUIRED/ { found = 1 }
        END { print (found ? "yes" : "no") }
    ' builder.sh"""

# Every shape the format parse has to survive. The comment on each line is the property it is there for; a case with no property is a case that will be deleted the first time someone tidies this file.
FORMAT_CASES = [
    "    deb | rpm | apk | archlinux) ;;\n",  # the real builder's line
    "    deb|rpm|apk|archlinux) ;;\n",  # no spaces at all
    "deb) ;;\n",  # no indent, one format
    "\tdeb | rpm) ;;\n",  # TAB indent: [[:space:]] matches, `tr -d ' '` does not
    "    a | b) ;;\n    c | d) ;;\n",  # head -1: the FIRST arm wins
    "    ) ;;\n",  # an EMPTY group, which must not yield one empty name
    "    deb | rpm) ;;  # trailing comment\n",  # the `$` anchor must reject this
    "    DEB | RPM) ;;\n",  # uppercase is outside [a-z]
    "    deb | rpm)\n",  # a multi-line arm header is NOT the validation case
    "    *) ;;\n",  # the default arm: `*` is outside the bracket expression
    "    deb | rpm) ;; \n",  # one trailing space before end of line
    "echo hi\n",  # no case at all
    "",  # the empty file
]


@pytest.mark.parametrize("content", FORMAT_CASES)
def test_formats_of_matches_the_sed_pipeline(tmp_path: pathlib.Path, content: str) -> None:
    """The four shell stages, run for real, against the port's reimplementation."""
    (tmp_path / "builder.sh").write_text(content, encoding="utf-8")
    code, out, err = diff.bash_streams(_FORMATS_PIPELINE, cwd=str(tmp_path))
    assert code == 0, err
    expected = [line for line in out.split("\n") if line != ""]
    assert rsc.formats_of(content) == expected


def test_the_format_table_exercises_both_directions() -> None:
    """A table of only-matching cases would prove the parser cannot say no.

    Asserted rather than trusted: this is the control ON the table, and without it a later edit that dropped every negative case would leave the file green and vacuous.
    """
    parsed = [rsc.formats_of(c) for c in FORMAT_CASES]
    assert any(p for p in parsed), "no case parses; the table tests nothing"
    assert any(not p for p in parsed), "every case parses; the table has no negatives"


# Every shape the arm scan has to survive, as (builder text, format, why).
GUARD_CASES = [
    (
        "    rpm | deb)\n        RELEASE_SIGNING_REQUIRED=1\n        ;;\n",
        "deb",
        "the guard inside the format's own arm",
    ),
    (
        "    rpm | deb)\n        RELEASE_SIGNING_REQUIRED=1\n        ;;\n    apk)\n        :\n        ;;\n",
        "apk",
        "a LATER arm must not inherit an earlier arm's guard",
    ),
    (
        "    apk)\n        :\n        ;;\nesac\nRELEASE_SIGNING_REQUIRED=1\n",
        "apk",
        "a guard after the esac belongs to nobody",
    ),
    (
        "    deb)\n        RELEASE_SIGNING_REQUIRED=1\n        ;;\n",
        "rpm",
        "a format the builder never names",
    ),
    (
        "    deb|rpm)\n        RELEASE_SIGNING_REQUIRED=1\n        ;;\n",
        "rpm",
        "no spaces around the pipe",
    ),
    (
        "\tdeb)\n\t\tRELEASE_SIGNING_REQUIRED=1\n\t\t;;\n",
        "deb",
        "TAB indentation throughout",
    ),
    (
        "    deb) ;;\n        RELEASE_SIGNING_REQUIRED=1\n",
        "deb",
        "a ONE-LINE arm is not an arm header, so nothing is in scope",
    ),
    (
        "    deb)\n        # RELEASE_SIGNING_REQUIRED is not set here\n        ;;\n",
        "deb",
        "a COMMENT mentioning the guard counts, and that is the twin's behaviour",
    ),
    (
        "    *)\n        RELEASE_SIGNING_REQUIRED=1\n        ;;\n",
        "deb",
        "the default arm never matches: the awk regex demands a leading [a-z]",
    ),
    ("", "deb", "the empty file"),
]


@pytest.mark.parametrize(("content", "fmt", "why"), GUARD_CASES)
def test_guarded_in_matches_the_awk(
    tmp_path: pathlib.Path, content: str, fmt: str, why: str
) -> None:
    (tmp_path / "builder.sh").write_text(content, encoding="utf-8")
    code, out, err = diff.bash_streams(_GUARDED_AWK % fmt, cwd=str(tmp_path))
    assert code == 0, err
    assert rsc.guarded_in(fmt, content) == out.strip(), why


def test_the_guard_table_exercises_both_directions() -> None:
    answers = {rsc.guarded_in(fmt, content) for content, fmt, _why in GUARD_CASES}
    assert answers == {"yes", "no"}, "the guard table must contain both verdicts"


# The tally cases, named by the arm they drive. The second value of each pair is what `gate_check` was given as `got`, so "mixed" runs one passing and one failing control and "green" runs two passing ones.
TALLY_SLUG = "gate-controls-tally"
TALLY_CASES: dict[str, tuple[str, int]] = {
    "floor-1": ("mixed", 1),
    "floor-2": ("mixed", 2),
    "floor-9": ("mixed", 9),
    "green-floor-1": ("green", 1),
    "green-floor-9": ("green", 9),
}
TALLY_ARMS = {"mixed": ("a", "b"), "green": ("a", "a")}


def _recorded_tally(case: str) -> tuple[int, str, str]:
    """One golden, split back into exit code, stdout and stderr."""
    body = frozen.read(TALLY_SLUG, case)
    head, rest = body.split("\n--- stdout ---\n", 1)
    out, err = rest.split("--- stderr ---\n", 1)
    return int(head[len("exit: ") :]), out, err


@pytest.mark.parametrize("case", sorted(TALLY_CASES))
def test_gate_tally_matches_the_twins_recorded_output(case: str) -> None:
    """The port's local copy of the tally, byte for byte against the original.

    THE TWIN HAS BEEN DELETED. While `.ci/scripts/lib/gate-controls.sh` existed this ran it and the port side by side; `goldens/gate-controls-tally/` now holds the bash library's OWN bytes, captured on its last day in the tree, and each golden's provenance header carries the blob sha so `git cat-file -p <sha>` still yields the program that printed them.

    BOTH STREAMS, SEPARATELY. `gate_check` writes passes to stdout and failures to stderr, and `gate_finish` splits its verdict the same way. Merging them would hide exactly the swap this comparison exists to catch.
    """
    arm, floor = TALLY_CASES[case]
    second_got, second_want = TALLY_ARMS[arm]
    code, out, err = _recorded_tally(case)

    tally = rsc.GateTally()
    py_out, py_err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(py_out), contextlib.redirect_stderr(py_err):
        tally.check("first", "a", "a")
        tally.check("second", second_got, second_want)
        green = tally.finish(floor, "subject line")

    assert py_out.getvalue() == out
    assert py_err.getvalue() == err
    # `gate_finish` returns 1 on failure and the script's exit status is that
    # return, so the boolean and the exit code must agree.
    assert green is (code == 0)


def test_the_tally_corpus_is_the_one_on_disk() -> None:
    """ANTI-VACUITY on the corpus: a case whose golden vanished would pass by never being compared, and a golden nothing reads is a recording of a case that stopped running."""
    frozen.assert_corpus(TALLY_SLUG, set(TALLY_CASES))


def test_the_recorded_tally_carries_both_verdicts() -> None:
    """A recording of failures only would agree with a port that never prints a green line, and the green line is the one the shadow comparator reads as a pass."""
    codes = {_recorded_tally(case)[0] for case in TALLY_CASES}
    assert codes == {0, 1}, "the recorded tally must hold a green and a red"


def test_the_floor_message_is_the_battery_wording_not_the_file_wording() -> None:
    """`controls.py` says "file", `gate-controls.sh` says "battery".

    Pinned because the two wordings are one word apart and a "unification" that reached for the existing class would change what the shadow comparator's refusal vocabulary matches on. See the port notes.
    """
    tally = rsc.GateTally()
    buf = io.StringIO()
    with contextlib.redirect_stderr(buf), contextlib.redirect_stdout(io.StringIO()):
        tally.finish(3, "subject")
    assert "the battery is not being executed as written" in buf.getvalue()


def test_the_exemption_order_is_bash_hash_order() -> None:
    """archlinux BEFORE apk, which is not the order a human would write.

    Measured on GNU bash 5.3.9 with
    `declare -A U=([archlinux]=x [apk]=y); for k in "${!U[@]}"; do echo $k; done`.
    Re-measured here against the real shell so the claim cannot rot silently.
    """
    code, out, err = diff.bash_streams(
        'declare -A U=([archlinux]=x [apk]=y); for k in "${!U[@]}"; do echo "$k"; done'
    )
    assert code == 0, err
    assert [k for k, _ in rsc.UNSIGNED_ON_PURPOSE] == out.split()


def test_every_exemption_reason_survives_the_length_control() -> None:
    """The reasons are load-bearing prose; a truncation must fail the gate.

    This is the mirror of the `carries a reason` control: it asserts the shipped reasons pass it, so a port that had silently dropped them to placeholders would be caught here rather than by a reader.
    """
    for fmt, reason in rsc.UNSIGNED_ON_PURPOSE:
        assert len(reason) > rsc.MIN_REASON_LEN, fmt


def test_the_archaeology_the_reasons_carry_is_still_present() -> None:
    """Driver contract 5c, applied to the two strings a ratio cannot see.

    The comment-byte ratio counts COMMENTS. These reasons are string literals, so every dated measurement and upstream reference in them is invisible to that audit and is asserted explicitly instead.
    """
    reasons = dict(rsc.UNSIGNED_ON_PURPOSE)
    assert "field signature not found in type nfpm.ArchLinux" in reasons["archlinux"]
    assert "goreleaser/nfpm#628" in reasons["archlinux"]
    assert "PR #1065" in reasons["archlinux"]
    assert "pacman.conf(5)" in reasons["archlinux"]
    assert "LocalFileSigLevel" in reasons["archlinux"]
    assert "VERIFIED 2026-09-06" in reasons["apk"]
    assert "APK_RSA_PRIVATE_KEY" in reasons["apk"]
    assert ".ci/config/bws-secret-map.json" in reasons["apk"]


def test_selftest_passes() -> None:
    """The gate's own plants and mirrors, driven from pytest.

    Cheap, and it is the only thing that fails when someone edits a plant into a shape that no longer fires.
    """
    assert rsc.selftest() == 0
