"""`rediacc_ci.quality.release_key_canonical` against its bash twin.

A bash child runs the REAL `.ci/scripts/quality/check-release-key-canonical.sh`
over a fixture with stdout and stderr captured SEPARATELY, and its bytes are
compared against the port's. The twin's own `RELEASE_KEY_ROOT` seam points both
implementations at the fixture; the twin is copied in anyway, because the
committed ledger (`.ci/shadow/w7p2-release-key.observations.jsonl`) records a tree
id that has to be a claim about BOTH implementations.

EACH SIDE GENERATES ITS OWN THROWAWAY KEY, so the two runs are NOT byte-identical
in general: the fingerprint differs. Every fixture below is therefore built so
that the controls naming a fingerprint PASS (and are printed as `  ok    ...`
without the value), and only the two `grep`-counting controls fail. That is what
makes a byte comparison meaningful here rather than merely noisy.

WHAT NO FIXTURE HERE EXERCISES, and why. Three of the twin's exits are REFUSALS
in `scripts/lib/shadow-gate.ts`'s vocabulary -- "nothing here was verified" (no
gpg), "so NOTHING was verified" (key generation failed) and "the battery is not
being executed as written" (short battery). A refusal suspends the comparison
rather than colouring it, so no ledger row can be recorded over one. They are
ported faithfully and are asserted here only through the message-shape test at
the bottom, which reads the strings without driving the state.

THE FIXTURES VARY build-linux-pkg.sh, not the key, because that file is the only
input a test can move without a secret. The twin cannot check the real
RELEASE_GPG_PRIVATE_KEY -- quality jobs do not have it and must not.
"""

import pathlib
import shutil

import pytest

from rediacc_ci.quality import release_key_canonical as gate
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/quality/check-release-key-canonical.sh"
CANON = ".ci/scripts/build/canonicalise-gpg-key.sh"
BUILD_PKG = ".ci/scripts/build/build-linux-pkg.sh"
MODULE = "release_key_canonical"

GUARD_LINE = 'canonicalise-gpg-key.sh "$K" "$P" || canon_rc=$?\n'
CALL_LINE = "echo running canonicalise-gpg-key.sh\n"
PROSE = "# The gate counts CODE, not prose: `|| canon_rc=$?` here must not count.\n"


def build(tmp_path: pathlib.Path, guards: int | None, calls: int) -> pathlib.Path:
    """A fixture root. `guards=None` omits build-linux-pkg.sh entirely."""
    src = pathlib.Path(diff.repo())
    root = tmp_path / "fixture"
    (root / ".ci" / "scripts" / "quality").mkdir(parents=True)
    (root / ".ci" / "scripts" / "build").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "quality").mkdir(parents=True)
    shutil.copytree(src / ".ci" / "scripts" / "lib", root / ".ci" / "scripts" / "lib")
    shutil.copy2(src / TWIN, root / TWIN)
    shutil.copy2(src / CANON, root / CANON)
    for name in ("__init__.py", "log.py", "paths.py", "controls.py"):
        shutil.copy2(src / ".ci" / "rediacc_ci" / name, root / ".ci" / "rediacc_ci" / name)
    for name in ("__init__.py", "%s.py" % MODULE):
        shutil.copy2(
            src / ".ci" / "rediacc_ci" / "quality" / name,
            root / ".ci" / "rediacc_ci" / "quality" / name,
        )
    if guards is not None:
        (root / BUILD_PKG).write_text(
            "#!/bin/bash\n" + PROSE + GUARD_LINE * guards + CALL_LINE * calls, encoding="utf-8"
        )
    return root


def run_both(root: pathlib.Path) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    env = diff.env_for(PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1", RELEASE_KEY_ROOT=str(root))
    old = diff.bash_streams("bash %s" % TWIN, env=env, cwd=str(root), timeout=180)
    new = diff.bash_streams(
        "python3 -m rediacc_ci.quality.%s" % MODULE, env=env, cwd=str(root), timeout=180
    )
    return old, new


@pytest.mark.parametrize(
    ("guards", "calls", "failures", "must_contain"),
    [
        # THE ASYMMETRY OVER A MISSING FILE. The guard control is a PIPELINE
        # whose second grep reads an empty stdin and prints "0"; the call control
        # is a DIRECT grep that never opens a stream and prints nothing. A port
        # that returned 0 for both would disagree on one compared line.
        pytest.param(None, 0, 2, "(got '' want '1')", id="no-build-script-at-all"),
        pytest.param(0, 1, 1, "guards that non-zero exit (got '0' want '1')", id="no-guard"),
        pytest.param(2, 0, 2, "guards that non-zero exit (got '2' want '1')", id="two-guards"),
        pytest.param(1, 1, 1, "calls the canonicaliser (got '2' want '1')", id="two-calls"),
        pytest.param(0, 0, 2, "calls the canonicaliser (got '0' want '1')", id="neither"),
    ],
)
def test_port_and_twin_agree(
    tmp_path: pathlib.Path, guards: int | None, calls: int, failures: int, must_contain: str
) -> None:
    root = build(tmp_path, guards, calls)
    (old_exit, old_out, old_err), (new_exit, new_out, new_err) = run_both(root)
    assert old_exit == 1
    assert new_exit == old_exit
    assert new_out == old_out, "the ok-tally on stdout is the gate's output contract"
    # stderr differs ONLY where the twin's grep writes its own "No such file"
    # warning, which is chatter to `scripts/lib/shadow-gate.ts` and is the one
    # documented residual divergence of this port.
    assert new_err.split("\n") == [
        x for x in old_err.split("\n") if not x.startswith(("grep:", "ugrep:"))
    ]
    assert "%d of 12 control(s) failed" % failures in old_err
    assert must_contain in old_err


def test_a_correct_build_script_is_green_on_both_sides(tmp_path: pathlib.Path) -> None:
    """The mirror the five cases above need, and the non-trivial-count evidence.

    Twelve controls, all of them green, on BOTH implementations. A gate that
    failed everything would satisfy every parametrized case.
    """
    root = build(tmp_path, 1, 0)
    (old_exit, old_out, _), (new_exit, new_out, _) = run_both(root)
    assert old_exit == 0
    assert new_exit == 0
    assert new_out == old_out
    assert "12 control(s) passed" in old_out
    assert "throwaway key" in old_out


def test_the_fingerprint_controls_pass_so_the_bytes_can_be_compared(
    tmp_path: pathlib.Path,
) -> None:
    """Each side mints its own key; the value only reaches stdout when it FAILS."""
    root = build(tmp_path, 1, 0)
    (_, old_out, _), (_, new_out, _) = run_both(root)
    assert "ok    ...and the repaired key is still the SAME key" in old_out
    assert new_out == old_out


def test_a_missing_canonicaliser_fails_on_both_sides(tmp_path: pathlib.Path) -> None:
    root = build(tmp_path, 1, 0)
    (root / CANON).unlink()
    (old_exit, _, old_err), (new_exit, _, new_err) = run_both(root)
    assert (old_exit, new_exit) == (1, 1)
    assert "the build depends on it" in old_err
    assert new_err == old_err


# ---------------------------------------------------------------------------
# The decision functions, driven directly. Both directions for every rule.
# ---------------------------------------------------------------------------

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
    # THE STRUCTURAL SIGNATURE: the body grew a longer line, which is what
    # RFC 4880's 64-column wrap forbids and Go's armor decoder rejects.
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
