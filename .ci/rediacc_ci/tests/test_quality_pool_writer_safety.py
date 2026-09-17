"""`rediacc_ci.quality.pool_writer_safety` against its bash twin.

A bash child runs the REAL `.ci/scripts/quality/check-pool-writer-safety.sh` over a fixture with stdout and stderr captured SEPARATELY, and its bytes are compared against the port's. The twin has TWO environment seams of its own -- `POOL_SAFETY_GATES_DIR` and `POOL_SAFETY_LOCK` -- so the gate battery and the
registration are pointed at the fixture; the twin itself is copied in anyway,
because the committed ledger (`.ci/shadow/w7p2-pool-writer.observations.jsonl`) records a tree id that has to be a claim about BOTH implementations.

RETARGETED 2026-09-09 (W7P3-BAT) WITH ITS SUBJECT. The registration used to be the `WRITER_TESTS` / `WRITER_TESTS_FALLBACK` arrays in
`.ci/scripts/test/run-all.sh`; `battery.py` replaced that runner and classifies
from `scripts/ci-runner/gates.lock.json`'s `mutex: ["tree:..."]` declarations
instead, so the seam is now `POOL_SAFETY_LOCK` and the fixtures are JSON. The three defects below are unchanged and still pinned, because they are properties of the GATE and not of the file it reads.

THE THREE STACKED DEFECTS THIS GATE CARRIES ARE EACH PINNED HERE, because they are the reason the twin has the shape it has and every one of them was a green that meant nothing:

  1. `log_fail` did not exist in common.sh, so all THREE anti-vacuity refusals
     exited 127 instead of refusing. `test_a_lock_declaring_no_writers_refuses`
     and `test_a_missing_lock_refuses` drive two of them and assert the message,
     which is what a 127 cannot produce.
  2. W2.4b made WRITER_TESTS a DERIVED array, so the old `WRITER_TESTS=(`...`)`
     pattern parsed EMPTY and the gate would have passed everything. The retarget
     finishes that argument by reading the declaration itself;
     `test_registered_writers_reads_the_mutex_declaration` pins the new parse and
     `test_a_reads_declaration_is_not_a_writer_registration` pins the half that
     would silently re-open the same hole.
  3. With both fixed the gate named a real unregistered writer. That is the
     positive direction, and it is every parametrized case below.
"""

import json
import pathlib
import shutil

import pytest

from rediacc_ci.quality import pool_writer_safety as gate
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/quality/check-pool-writer-safety.sh"
MODULE = "pool_writer_safety"

WRITER = """#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
run_it() {
    local real="$REPO_ROOT/.ci/scripts/version/resolve-version.sh"
    printf 'stub\\n' >"$real"
}
"""

TEMPSAFE = """#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
FIXTURE="$(mktemp -d)"
ROOT="$FIXTURE/repo"
run_it() {
    mkdir -p "$ROOT/.ci"
    cp "$REPO_ROOT/.ci/scripts/lib/common.sh" "$ROOT/.ci/"
    printf 'seed\\n' >"$ROOT/seed.txt"
}
"""

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

    One non-gate-test entry is always present, because `run` is a command line in
    the general case and the parser has to pick the WORD that names the script; a
    fixture holding only gate tests could not catch a parser that took the whole string.
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


def build(
    tmp_path: pathlib.Path, gates: dict[str, str], lock: str
) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    """Returns (root, gates dir, lock path). The twin is copied in; see above."""
    src = pathlib.Path(diff.repo())
    root = tmp_path / "fixture"
    (root / ".ci" / "scripts" / "quality").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "quality").mkdir(parents=True)
    gates_dir = root / ".ci" / "scripts" / "test" / "gates"
    gates_dir.mkdir(parents=True)
    shutil.copytree(src / ".ci" / "scripts" / "lib", root / ".ci" / "scripts" / "lib")
    shutil.copy2(src / TWIN, root / TWIN)
    for name in ("__init__.py", "log.py", "paths.py", "controls.py"):
        shutil.copy2(src / ".ci" / "rediacc_ci" / name, root / ".ci" / "rediacc_ci" / name)
    for name in ("__init__.py", "%s.py" % MODULE):
        shutil.copy2(
            src / ".ci" / "rediacc_ci" / "quality" / name,
            root / ".ci" / "rediacc_ci" / "quality" / name,
        )
    for name, content in gates.items():
        (gates_dir / name).write_text(content, encoding="utf-8")
    lock_path = root / "scripts" / "ci-runner" / "gates.lock.json"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(lock, encoding="utf-8")
    return root, gates_dir, lock_path


def run_both(
    root: pathlib.Path, gates_dir: pathlib.Path, lock: pathlib.Path
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    env = diff.env_for(
        PYTHONPATH=".ci",
        PYTHONDONTWRITEBYTECODE="1",
        POOL_SAFETY_GATES_DIR=str(gates_dir),
        POOL_SAFETY_LOCK=str(lock),
    )
    old = diff.bash_streams("bash %s" % TWIN, env=env, cwd=str(root))
    new = diff.bash_streams("python3 -m rediacc_ci.quality.%s" % MODULE, env=env, cwd=str(root))
    return old, new


@pytest.mark.parametrize(
    ("gates", "registered", "violations"),
    [
        pytest.param(
            {"test-a.sh": WRITER, "test-reg.sh": WRITER, "test-safe.sh": TEMPSAFE},
            ("test-reg.sh",),
            1,
            id="one-unregistered-beside-a-registered-one",
        ),
        pytest.param(
            {"test-a.sh": WRITER, "test-b.sh": WRITER, "test-reg.sh": WRITER},
            ("test-reg.sh",),
            2,
            id="two-unregistered",
        ),
        pytest.param(
            {"test-a.sh": WRITER, "test-b.sh": WRITER, "test-c.sh": WRITER},
            # A NAME THAT IS NOT IN THE BATTERY, on purpose. An EMPTY tuple here would make the declared set empty and trip the anti-vacuity refusal instead, which is a different case (and is covered by `test_a_lock_declaring_no_writers_refuses`). The first draft of this parameter did exactly that and asserted three violations against a refusal.
            ("test-elsewhere.sh",),
            3,
            id="three-unregistered",
        ),
    ],
)
def test_port_and_twin_agree_byte_for_byte(
    tmp_path: pathlib.Path, gates: dict[str, str], registered: tuple[str, ...], violations: int
) -> None:
    root, gdir, lock = build(tmp_path, gates, lock_text(*registered))
    (old_exit, old_out, old_err), (new_exit, new_out, new_err) = run_both(root, gdir, lock)
    assert old_exit == 1
    assert new_exit == old_exit
    assert new_out == old_out
    assert new_err == old_err
    assert "%d unregistered real-tree writer(s)" % violations in old_err


def test_a_registered_writer_alone_is_green_on_both_sides(tmp_path: pathlib.Path) -> None:
    """The mirror: the rule is ONE-DIRECTIONAL and a declared writer is fine."""
    root, gdir, lock = build(
        tmp_path, {"test-reg.sh": WRITER, "test-safe.sh": TEMPSAFE}, lock_text("test-reg.sh")
    )
    (old_exit, old_out, old_err), (new_exit, new_out, new_err) = run_both(root, gdir, lock)
    assert old_exit == 0
    assert new_exit == 0
    assert new_out == old_out
    assert new_err == old_err
    # THE COUNT IS PRINTED IN THE GREEN LINE, so a reader can see the verdict was not trivial. BOTH counts: the battery scanned, and the set declared.
    assert "among 2 gate tests" in old_err
    assert "(1 declared" in old_err


def test_a_reads_declaration_is_not_a_writer_registration(tmp_path: pathlib.Path) -> None:
    """The half of the retarget that could silently re-open the old hole.

    `reads` releases a test to run BESIDE other scanners; only `mutex` puts it in
    the serial W chain. A parser that accepted either would look correct on every positive case above and would bless exactly the misclassification this gate exists for.
    """
    lock = json.dumps(
        [
            {
                "id": "gate-test:reg",
                "run": ".ci/scripts/test/gates/test-reg.sh",
                "reads": ["tree:repo"],
            },
            {
                "id": "gate-test:other",
                "run": ".ci/scripts/test/gates/test-other.sh",
                "mutex": ["tree:repo"],
            },
        ]
    )
    root, gdir, lock_path = build(tmp_path, {"test-reg.sh": WRITER}, lock)
    (old_exit, _, old_err), (new_exit, _, new_err) = run_both(root, gdir, lock_path)
    assert (old_exit, new_exit) == (1, 1)
    assert "1 unregistered real-tree writer(s)" in old_err
    assert new_err == old_err


def test_a_temp_only_writer_alone_is_green(tmp_path: pathlib.Path) -> None:
    """A scanner that flagged every file would pass every positive case above."""
    root, gdir, lock = build(tmp_path, {"test-safe.sh": TEMPSAFE}, lock_text("test-reg.sh"))
    (old_exit, _, old_err), (new_exit, _, new_err) = run_both(root, gdir, lock)
    assert (old_exit, new_exit) == (0, 0)
    assert "among 1 gate tests" in old_err
    assert new_err == old_err


def test_a_lock_declaring_no_writers_refuses(tmp_path: pathlib.Path) -> None:
    """Archaeology 1 and 2 together: the refusal that used to exit 127."""
    root, gdir, lock = build(tmp_path, {"test-a.sh": WRITER}, NO_WRITERS)
    (old_exit, _, old_err), (new_exit, _, new_err) = run_both(root, gdir, lock)
    assert (old_exit, new_exit) == (1, 1)
    assert "this gate would pass everything" in old_err
    assert new_err == old_err


def test_an_unparseable_lock_refuses(tmp_path: pathlib.Path) -> None:
    """A broken lock must not read as "nothing needs isolating"."""
    root, gdir, lock = build(tmp_path, {"test-a.sh": WRITER}, "{not json at all")
    (old_exit, _, old_err), (new_exit, _, new_err) = run_both(root, gdir, lock)
    assert (old_exit, new_exit) == (1, 1)
    assert "this gate would pass everything" in old_err
    assert new_err == old_err


def test_a_missing_lock_refuses(tmp_path: pathlib.Path) -> None:
    root, gdir, lock = build(tmp_path, {"test-a.sh": WRITER}, lock_text("x.sh"))
    lock.unlink()
    (old_exit, _, old_err), (new_exit, _, new_err) = run_both(root, gdir, lock)
    assert (old_exit, new_exit) == (1, 1)
    assert "refusing to pass while measuring nothing" in old_err
    assert new_err == old_err


def test_an_empty_gates_directory_refuses(tmp_path: pathlib.Path) -> None:
    """ZERO INPUTS IS A FAILURE, never a pass."""
    root, gdir, lock = build(tmp_path, {}, lock_text("test-reg.sh"))
    (old_exit, _, old_err), (new_exit, _, new_err) = run_both(root, gdir, lock)
    assert (old_exit, new_exit) == (1, 1)
    assert "refusing to report a clean battery over an empty set" in old_err
    assert new_err == old_err


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
