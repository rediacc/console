"""`rediacc_ci.quality.release_key_canonical`, driven directly.

WHILE BOTH COPIES EXISTED a bash child ran the REAL `.ci/scripts/quality/check-release-key-canonical.sh` over a fixture with stdout and stderr captured SEPARATELY, and its bytes were compared against the port's. The twin's own `RELEASE_KEY_ROOT` seam pointed both implementations at the fixture; the twin was copied in anyway, because the committed ledger
(`.ci/shadow/w7p2-release-key.observations.jsonl`) records a tree id that has to be a claim about BOTH implementations. That ledger licensed the port at K=5 and the twin was retired in W7 P5, so the fixture cases were retired with it.

WHAT THOSE CASES ESTABLISHED, recorded rather than dropped without trace. Each side generated its OWN throwaway key, so the two runs were not byte-identical in general: the fingerprint differed. Every fixture was therefore built so that the controls naming a fingerprint PASSED (printed as ` ok ...` without the value) and only the two `grep`-counting controls failed, which
is what made a byte comparison meaningful rather than merely noisy. The one residual divergence was the twin's own `grep: ... No such file` warning on stderr, chatter to `scripts/lib/shadow-gate.ts`. The fixtures varied build-linux-pkg.sh and never the key, because that file is the only input a test can move without a secret: quality jobs do not have
RELEASE_GPG_PRIVATE_KEY and must not.

THREE OF THIS GATE'S EXITS ARE REFUSALS in `scripts/lib/shadow-gate.ts`'s vocabulary -- "nothing here was verified" (no gpg), "so NOTHING was verified" (key generation failed) and "the battery is not being executed as written" (short battery). A refusal suspends the comparison rather than colouring it, so no ledger row could ever be recorded over one. They are asserted below
through the message-shape case, which reads the strings without driving the state, and by the port's own selftest.
"""

import pathlib

import pytest

from rediacc_ci.quality import release_key_canonical as gate
from rediacc_ci.tests import differential as diff

MODULE = "release_key_canonical"

GUARD_LINE = 'canonicalise-gpg-key.sh "$K" "$P" || canon_rc=$?\n'
CALL_LINE = "echo running canonicalise-gpg-key.sh\n"


# --------------------------------------------------------------------------- The decision functions, driven directly. Both directions for every rule. ---------------------------------------------------------------------------

_ARMOR = (
    "-----BEGIN PGP PRIVATE KEY BLOCK-----\n\nAAAA\nBBBB\nCCCC\n"
    "-----END PGP PRIVATE KEY BLOCK-----\n"
)


@pytest.mark.parametrize(
    ("text", "longest"),
    [
        pytest.param(_ARMOR, 4, id="a-short-body"),
        pytest.param(
            "-----BEGIN A VERY LONG DELIMITER INDEED-----\nAB\n", 2, id="delimiters-excluded"
        ),
        pytest.param("", 0, id="nothing-measures-zero-not-blank"),
        pytest.param("-----B-----\n-----E-----\n", 0, id="delimiters-only"),
    ],
)
def test_longest_body_line(text: str, longest: int) -> None:
    assert gate.longest_body_line(text) == longest


def test_the_welder_joins_exactly_one_pair_and_keeps_the_content() -> None:
    welded = gate.weld(_ARMOR)
    assert welded == (
        "-----BEGIN PGP PRIVATE KEY BLOCK-----\n\nAAAA\nBBBBCCCC\n"
        "-----END PGP PRIVATE KEY BLOCK-----\n"
    )
    # THE STRUCTURAL SIGNATURE: the body grew a longer line, which is what RFC 4880's 64-column wrap forbids and Go's armor decoder rejects.
    assert gate.longest_body_line(welded) > gate.longest_body_line(_ARMOR)
    assert welded.replace("\n", "") == _ARMOR.replace("\n", "")


def test_the_welder_stops_after_the_first_weld() -> None:
    assert gate.weld("-----B-----\n\nA\nB\nC\nD\n-----E-----\n") == (
        "-----B-----\n\nA\nBC\nD\n-----E-----\n"
    )


@pytest.mark.parametrize(
    ("text", "count"),
    [
        pytest.param('canon.sh "$K" || canon_rc=$?\n', 1, id="one-real-guard"),
        pytest.param(
            "# `|| canon_rc=$?` explains it\ncanon.sh || canon_rc=$?\n", 1, id="prose-not-counted"
        ),
        pytest.param("    # || canon_rc=$?\n", 0, id="an-indented-comment-is-a-comment"),
        pytest.param("canon.sh || canon_rc=$?  # note\n", 1, id="a-trailing-comment-still-counts"),
        pytest.param("", 0, id="empty"),
    ],
)
def test_guard_count(text: str, count: int) -> None:
    assert gate.guard_count(text) == count


def test_literal_count_counts_lines_not_occurrences() -> None:
    assert gate.literal_count("a canonicalise-gpg-key.sh b\n", gate.CANON_LITERAL) == 1
    assert (
        gate.literal_count("canonicalise-gpg-key.sh canonicalise-gpg-key.sh\n", gate.CANON_LITERAL)
        == 1
    )
    assert (
        gate.literal_count("canonicalise-gpg-key.sh\ncanonicalise-gpg-key.sh\n", gate.CANON_LITERAL)
        == 2
    )


def test_the_missing_file_asymmetry_is_reproduced(tmp_path: pathlib.Path) -> None:
    """`grep -v ... | grep -c` prints "0"; a direct `grep -c` prints NOTHING."""
    absent = tmp_path / "not-here.sh"
    assert gate.guard_count_field(absent) == "0"
    assert gate.call_count_field(absent) == ""
    present = tmp_path / "here.sh"
    present.write_text(GUARD_LINE + CALL_LINE, encoding="utf-8")
    assert gate.guard_count_field(present) == "1"
    assert gate.call_count_field(present) == "2"


def test_the_refusal_wording_is_carried_verbatim() -> None:
    """Three exits are REFUSALS to the comparator; their words are the contract."""
    source = pathlib.Path(diff.repo()) / (".ci/rediacc_ci/quality/%s.py" % MODULE)
    text = source.read_text(encoding="utf-8")
    assert "nothing here was verified" in text
    assert "so NOTHING was verified" in text
    assert "the battery is not being executed as written" in text


def test_selftest_passes_and_is_not_vacuous(capsys) -> None:
    assert gate.selftest() == 0
    out = capsys.readouterr().out
    assert "control(s) passed" in out
    assert int(out.strip().split("\n")[-1].split()[0]) >= 18
