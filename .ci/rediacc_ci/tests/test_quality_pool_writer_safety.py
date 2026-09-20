"""`rediacc_ci.quality.pool_writer_safety`, driven directly.

WHILE BOTH COPIES EXISTED a bash child ran the REAL `.ci/scripts/quality/check-pool-writer-safety.sh` over a fixture with stdout and stderr captured SEPARATELY, and its bytes were compared against the port's. The twin had TWO environment seams of its own -- `POOL_SAFETY_GATES_DIR` and `POOL_SAFETY_LOCK` -- so the gate battery and the registration were pointed at the
fixture; the twin itself was copied in anyway, because the committed ledger (`.ci/shadow/w7p2-pool-writer.observations.jsonl`) records a tree id that has to be a claim about BOTH implementations. That ledger licensed the port at K=5 and the twin was retired in W7 P5, so the whole-gate cases were retired with it.

RETARGETED 2026-09-09 (W7P3-BAT) WITH ITS SUBJECT. The registration used to be the `WRITER_TESTS` / `WRITER_TESTS_FALLBACK` arrays in `.ci/scripts/test/run-all.sh`; `battery.py` replaced that runner and classifies
from `scripts/ci-runner/gates.lock.json`'s `mutex: ["tree:..."]` declarations
instead, so the seam is now `POOL_SAFETY_LOCK` and the fixtures are JSON. The three defects below are unchanged and still pinned, because they are properties of the GATE and not of the file it reads.

THE THREE STACKED DEFECTS THIS GATE CARRIES ARE EACH ON THE RECORD, because they are the reason it has the shape it has and every one of them was a green that meant nothing:

  1. `log_fail` did not exist in common.sh, so all THREE anti-vacuity refusals
     exited 127 instead of refusing. The refusals are the port's now and its
     selftest drives them; the cases that proved a message a 127 cannot produce
     ran the twin and were retired with it.
  2. W2.4b made WRITER_TESTS a DERIVED array, so the old `WRITER_TESTS=(`...`)`
     pattern parsed EMPTY and the gate would have passed everything. The retarget
     finishes that argument by reading the declaration itself;
     `test_registered_writers_reads_the_mutex_declaration` pins the new parse and
     `test_registered_writers_ignores_reads_and_non_tree_mutexes` pins the half
     that would silently re-open the same hole.
  3. With both fixed the gate named a real unregistered writer. That direction is
     what `test_scan_text` and the plant controls below carry.
"""

import json
import pathlib

import pytest

from rediacc_ci.quality import pool_writer_safety as gate
from rediacc_ci.tests import differential as diff

# A lock that names gate tests and declares NO mutex tree: resource on any of them. This is the retarget's equivalent of the derived-assignment shape: the file parses, the entries are real, and the registered set comes out EMPTY -- exactly the state the refusal exists to catch.
NO_WRITERS = json.dumps(
    [
        {"id": "gate-test:a", "run": ".ci/scripts/test/gates/test-a.sh"},
        {
            "id": "gate-test:b",
            "run": ".ci/scripts/test/gates/test-b.sh",
            "reads": ["tree:repo"],
        },
    ]
)


def lock_text(*registered: str) -> str:
    """A lock declaring `mutex: ["tree:repo"]` on each named gate test.

    One non-gate-test entry is always present, because `run` is a command line in the general case and the parser has to pick the WORD that names the script; a fixture holding only gate tests could not catch a parser that took the whole string.
    """
    entries: list[dict[str, object]] = [
        {
            "id": "check:elsewhere",
            "run": "npx tsx scripts/gates/check-elsewhere.ts",
            "mutex": ["tree:repo"],
        }
    ]
    entries.extend(
        {
            "id": "gate-test:%s" % name.removeprefix("test-").removesuffix(".sh"),
            "run": ".ci/scripts/test/gates/%s" % name,
            "mutex": ["tree:repo"],
        }
        for name in registered
    )
    return json.dumps(entries, indent=2)


# --------------------------------------------------------------------------- The scanner, driven directly. Both directions for every rule. ---------------------------------------------------------------------------

_SEED = 'REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"\n'
_TEMP = 'TMP="$(mktemp -d)"\n'


@pytest.mark.parametrize(
    ("text", "hits"),
    [
        pytest.param(_SEED + 'echo x >"$REPO_ROOT/f"\n', 1, id="redirect"),
        pytest.param(_SEED + 'echo x >>"$REPO_ROOT/f"\n', 1, id="append"),
        pytest.param(_SEED + 'cp "$SRC" "$REPO_ROOT/f"\n', 1, id="cp-last-arg"),
        pytest.param(_SEED + 'sed -i "s/a/b/" "$REPO_ROOT/f"\n', 1, id="sed-i"),
        pytest.param(_SEED + 'rm -rf "$TMP" "$REPO_ROOT/f"\n', 1, id="rm-every-non-flag-arg"),
        pytest.param(_SEED + 'echo x 2>&1 >"$T"\n', 0, id="fd-duplication"),
        pytest.param(_SEED + 'echo "($b -> $REPO_ROOT)"\n', 0, id="an-ascii-arrow-in-a-log-line"),
        pytest.param(_SEED + 'read -r x <"$REPO_ROOT/f"\n', 0, id="input-redirection"),
        pytest.param(_SEED + '# echo x >"$REPO_ROOT/f"\n', 0, id="a-comment"),
        pytest.param(
            _SEED + "cat <<'EOF'\necho x >\"$REPO_ROOT/f\"\nEOF\n", 0, id="a-heredoc-body"
        ),
        pytest.param(_TEMP + 'cp "$SRC" "$TMP/f"\n', 0, id="a-temp-target"),
        pytest.param(_TEMP + 'ROOT="$TMP/repo"\nprintf x >"$ROOT/f"\n', 0, id="temp-beats-repo"),
        pytest.param("", 0, id="empty"),
    ],
)
def test_scan_text(text: str, hits: int) -> None:
    assert len(gate.scan_text(text, "t.sh")) == hits


def test_safe_beats_taint_when_one_target_names_both() -> None:
    """The propagation ORDER, which no single-variable case can pin.

    Measured 2026-09-06: planting the swap left all the other controls and all five recorded shadow rows green, because every one of them references exactly one kind of variable. A control that cannot fail is not a control.
    """
    both = _TEMP + _SEED + 'cp "$SRC" "$TMP/${REPO_ROOT}.log"\n'
    assert gate.scan_text(both, "t.sh") == []
    only_taint = _SEED + 'cp "$SRC" "$X/${REPO_ROOT}.log"\n'
    assert len(gate.scan_text(only_taint, "t.sh")) == 1


def test_the_two_passes_catch_a_write_above_its_assignment() -> None:
    """A function body can textually precede the global it uses; hence pass 1."""
    text = 'run() { printf x >"$REPO_ROOT/f"; }\n' + _SEED
    assert len(gate.scan_text(text, "t.sh")) == 1


def test_registered_writers_reads_the_mutex_declaration() -> None:
    assert gate.registered_writers(lock_text("test-a.sh", "test-b.sh")) == [
        "test-a.sh",
        "test-b.sh",
    ]


def test_registered_writers_takes_the_script_word_out_of_a_command_line() -> None:
    """`run` is a command line in the general case, not a bare path."""
    assert gate.registered_writers(
        '[{"run": "bash -x .ci/scripts/test/gates/test-x.sh --flag", "mutex": ["tree:repo"]}]'
    ) == ["test-x.sh"]


def test_registered_writers_ignores_reads_and_non_tree_mutexes() -> None:
    assert (
        gate.registered_writers(
            '[{"run": ".ci/scripts/test/gates/test-r.sh", "reads": ["tree:repo"]},'
            ' {"run": ".ci/scripts/test/gates/test-n.sh", "mutex": ["npm:install"]}]'
        )
        == []
    )


def test_a_lock_that_declares_nothing_parses_empty() -> None:
    """The state the refusal exists for, in each of its three shapes."""
    assert gate.registered_writers(NO_WRITERS) == []
    assert gate.registered_writers("") == []
    assert gate.registered_writers("{not json") == []
    assert gate.registered_writers("{}") == []


def test_the_live_lock_still_declares_the_historical_writers() -> None:
    """Every fixture above is synthetic. This one reads the REAL declaration.

    A parser that agreed with all of them while reading the live lock as empty would look perfect here and refuse on every real run, and the retarget is exactly the change that could have caused it.
    """
    live = pathlib.Path(diff.repo()) / "scripts" / "ci-runner" / "gates.lock.json"
    declared = set(gate.registered_writers(live.read_text(encoding="utf-8")))
    assert declared >= {
        "test-docs-gen.sh",
        "test-gate-anti-vacuity.sh",
        "test-gate-paths-exist.sh",
        "test-generate-tag-inputs.sh",
    }


def test_the_planted_controls_land_in_both_directions() -> None:
    """The gate refuses to judge the real battery unless BOTH of these hold."""
    assert len(gate.scan_text(gate.PLANTED_WRITER, "test-planted-writer.sh")) == 1
    assert gate.scan_text(gate.PLANTED_TEMPSAFE, "test-planted-tempsafe.sh") == []


def test_selftest_passes_and_is_not_vacuous(capsys) -> None:
    assert gate.selftest() == 0
    out = capsys.readouterr().out
    assert "control(s) passed" in out
    assert int(out.strip().split("\n")[-1].split()[0]) >= 24
