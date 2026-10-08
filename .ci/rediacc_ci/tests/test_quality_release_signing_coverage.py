"""`rediacc_ci.quality.release_signing_coverage` over the builder it reads.

THE BUILDER IS PYTHON NOW. This gate used to read the bash `build-linux-pkg.sh` with a `sed` BRE (the format list) and an eleven-line `awk` program (the per-format signing guard), and this file ran those two pipelines for real against the port's reimplementation of them, on every awkward input. When the bash builder was retired (PLAN-retire-bash-oracles B3) the gate was retargeted to its successor, `rediacc_ci.build.build_linux_pkg`, read through `ast`: the format list is the module's `FORMATS` tuple and the guard is a `raise` naming `RELEASE_SIGNING_REQUIRED` inside the format's own branch of `_report_unsigned`. The tables below are the same questions, one expected answer per awkward shape, and each shape is a property of the `ast` reading rather than of a shell pipeline.

The tally the gate prints its verdict through came from `.ci/scripts/lib/gate-controls.sh`, which has since been retired, so that half is compared against `goldens/gate-controls-tally/` rather than against a live library. They are NOT the whole gate: the whole gate is what the committed shadow ledger `.ci/shadow/w7p2-signing-coverage.observations.jsonl` compares over five distinct trees. This file covers the seams that ledger cannot isolate.
"""

import contextlib
import io

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import release_signing_coverage as rsc
from rediacc_ci.tests import differential as diff
from rediacc_ci.tests import frozen

# Every shape the format parse has to survive, as (builder source, expected formats). The comment on each line is the property it is there for; a case with no property is a case that will be deleted the first time someone tidies this file.
FORMAT_CASES = [
    (
        'FORMATS = ("deb", "rpm", "apk", "archlinux")\n',
        ["deb", "rpm", "apk", "archlinux"],
    ),  # the real shape
    ('FORMATS=("deb","rpm")\n', ["deb", "rpm"]),  # no spaces at all
    ('FORMATS = ["deb"]\n', ["deb"]),  # a list literal is a literal too
    ('FORMATS = ("deb",)\n', ["deb"]),  # one format
    ('FORMATS = ("a", "b")\nFORMATS = ("c", "d")\n', ["a", "b"]),  # the FIRST assignment wins
    ('FORMATS = ("", "deb")\n', ["deb"]),  # an EMPTY name must not survive as a format
    ('FORMATS = ("deb", 3)\n', []),  # a non-string element is not a literal list of names
    ("FORMATS = tuple(NAMES)\n", []),  # a computed value is not read
    ('OTHER = ("deb", "rpm")\n', []),  # a different name is not the format list
    ('def f():\n    FORMATS = ("deb",)\n', []),  # only a MODULE-LEVEL assignment counts
    ('FORMATS = ("deb", "rpm"\n', []),  # source that does not parse reads nothing
    ("print(1)\n", []),  # no assignment at all
    ("", []),  # the empty file
]


@pytest.mark.parametrize(("content", "expected"), FORMAT_CASES)
def test_formats_of_reads_the_formats_tuple(content: str, expected: list[str]) -> None:
    assert rsc.formats_of(content) == expected


def test_the_format_table_exercises_both_directions() -> None:
    """A table of only-matching cases would prove the parser cannot say no.

    Asserted rather than trusted: this is the control ON the table, and without it a later edit that dropped every negative case would leave the file green and vacuous.
    """
    parsed = [rsc.formats_of(content) for content, _expected in FORMAT_CASES]
    assert any(p for p in parsed), "no case parses; the table tests nothing"
    assert any(not p for p in parsed), "every case parses; the table has no negatives"


def _builder(chain: str, formats: str = '("deb", "rpm", "apk", "archlinux")') -> str:
    """A builder module with `FORMATS` and a `_report_unsigned` holding `chain` (indented four spaces after its first line)."""
    return "import os\n\nFORMATS = %s\n\n\ndef _report_unsigned(fmt):\n    %s\n" % (formats, chain)


GUARD_RAISE = (
    'if os.environ.get("RELEASE_SIGNING_REQUIRED", "0") == "1":\n'
    '            raise SystemExit("refusing")'
)

# Every shape the branch scan has to survive, as (builder text, format, expected, why).
GUARD_CASES = [
    (
        _builder('if fmt in ("rpm", "deb"):\n        %s\n    else:\n        pass' % GUARD_RAISE),
        "deb",
        "yes",
        "the guard inside the format's own branch",
    ),
    (
        _builder(
            'if fmt in ("rpm", "deb"):\n        %s\n    elif fmt == "apk":\n        pass'
            % GUARD_RAISE
        ),
        "apk",
        "no",
        "a LATER branch must not inherit an earlier branch's guard",
    ),
    (
        _builder('if fmt == "apk":\n        pass\n    else:\n        %s' % GUARD_RAISE),
        "archlinux",
        "yes",
        "the else branch covers every format no earlier branch named",
    ),
    (
        _builder('if fmt == "apk":\n        %s\n    else:\n        pass' % GUARD_RAISE),
        "archlinux",
        "no",
        "a guard in an EARLIER branch is not the else branch's",
    ),
    (
        _builder('if fmt == "deb":\n        %s' % GUARD_RAISE),
        "rpm",
        "no",
        "a format the chain never names is unguarded",
    ),
    (
        _builder('if fmt == "snap":\n        %s\n    else:\n        pass' % GUARD_RAISE),
        "snap",
        "yes",
        "the branch is read for the format it names, accepted or not",
    ),
    (
        _builder('if fmt == "deb":\n        print("RELEASE_SIGNING_REQUIRED is not set here")'),
        "deb",
        "no",
        "a message that merely MENTIONS the variable is not a guard",
    ),
    (
        _builder('if fmt == "deb":\n        os.environ.get("RELEASE_SIGNING_REQUIRED")'),
        "deb",
        "no",
        "reading the variable without refusing is not a guard",
    ),
    (
        _builder('if fmt == "deb":\n        raise SystemExit("unsigned")'),
        "deb",
        "no",
        "a refusal that never names the variable is not THE guard",
    ),
    (
        _builder('if fmt == "apk":\n        pass') + 'GUARD = "RELEASE_SIGNING_REQUIRED"\n',
        "apk",
        "no",
        "a guard outside the chain belongs to nobody",
    ),
    (
        "def other(fmt):\n    if fmt == 'deb':\n        raise SystemExit(os.environ.get('RELEASE_SIGNING_REQUIRED'))\n",
        "deb",
        "no",
        "only `_report_unsigned` is read",
    ),
    ("def _report_unsigned(fmt:\n", "deb", "no", "source that does not parse guards nothing"),
    ("", "deb", "no", "the empty file"),
]


@pytest.mark.parametrize(("content", "fmt", "expected", "why"), GUARD_CASES)
def test_guarded_in_reads_the_formats_own_branch(
    content: str, fmt: str, expected: str, why: str
) -> None:
    assert rsc.guarded_in(fmt, content) == expected, why


def test_the_guard_table_exercises_both_directions() -> None:
    answers = {rsc.guarded_in(fmt, content) for content, fmt, _expected, _why in GUARD_CASES}
    assert answers == {"yes", "no"}, "the guard table must contain both verdicts"


def test_the_real_builder_guards_rpm_and_deb_and_exempts_the_rest() -> None:
    """The gate's verdict on the tree it protects, by name: deb and rpm refuse to ship unsigned, apk and archlinux do not and are on the exemption list. A builder edit that moved a guard shows up here before it reaches a release."""
    text = (paths.repo_root() / rsc.BUILDER_REL).read_text(encoding="utf-8")
    assert rsc.formats_of(text) == ["deb", "rpm", "apk", "archlinux"]
    assert {fmt: rsc.guarded_in(fmt, text) for fmt in rsc.formats_of(text)} == {
        "deb": "yes",
        "rpm": "yes",
        "apk": "no",
        "archlinux": "no",
    }
    assert {fmt for fmt, _reason in rsc.UNSIGNED_ON_PURPOSE} == {"apk", "archlinux"}


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
