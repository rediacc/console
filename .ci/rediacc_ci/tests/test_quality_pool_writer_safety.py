"""`rediacc_ci.quality.pool_writer_safety` against its bash twin.

A bash child runs the REAL `.ci/scripts/quality/check-pool-writer-safety.sh` over
a fixture with stdout and stderr captured SEPARATELY, and its bytes are compared
against the port's. The twin has TWO environment seams of its own --
`POOL_SAFETY_GATES_DIR` and `POOL_SAFETY_RUNNER` -- so the gate battery and the
runner are pointed at the fixture; the twin itself is copied in anyway, because
the committed ledger
(`.ci/shadow/w7p2-pool-writer.observations.jsonl`) records a tree id that has to
be a claim about BOTH implementations.

THE THREE STACKED DEFECTS THIS GATE CARRIES ARE EACH PINNED HERE, because they
are the reason the twin has the shape it has and every one of them was a green
that meant nothing:

  1. `log_fail` did not exist in common.sh, so all THREE anti-vacuity refusals
     exited 127 instead of refusing. `test_an_empty_writer_array_refuses` and
     `test_a_missing_runner_refuses` drive two of them and assert the message,
     which is what a 127 cannot produce.
  2. W2.4b made WRITER_TESTS a DERIVED array, so the old `WRITER_TESTS=(`...`)`
     pattern parsed EMPTY and the gate would have passed everything.
     `test_registered_writers_unions_both_arrays` pins the union.
  3. With both fixed the gate named a real unregistered writer. That is the
     positive direction, and it is every parametrized case below.
"""

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

# The DERIVED assignment holds no test names, which is exactly the shape that
# parsed empty before the 2026-09-06 re-key.
DERIVED_ONLY = "#!/bin/bash\nWRITER_TESTS=($RUN_ALL_WRITERS)\n)\n"


def runner_text(*registered: str) -> str:
    body = "#!/bin/bash\nWRITER_TESTS=($RUN_ALL_WRITERS)\n)\nWRITER_TESTS_FALLBACK=(\n"
    for name in registered:
        body += "    # %s swaps a real file and restores it\n    %s\n" % (name, name)
    return body + ")\n"


def build(
    tmp_path: pathlib.Path, gates: dict[str, str], runner: str
) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    """Returns (root, gates dir, runner path). The twin is copied in; see above."""
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
    runner_path = root / ".ci" / "scripts" / "test" / "run-all.sh"
    runner_path.write_text(runner, encoding="utf-8")
    return root, gates_dir, runner_path


def run_both(
    root: pathlib.Path, gates_dir: pathlib.Path, runner: pathlib.Path
) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    env = diff.env_for(
        PYTHONPATH=".ci",
        PYTHONDONTWRITEBYTECODE="1",
        POOL_SAFETY_GATES_DIR=str(gates_dir),
        POOL_SAFETY_RUNNER=str(runner),
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
            # A NAME THAT IS NOT IN THE BATTERY, on purpose. An EMPTY tuple here
            # would make the fallback array empty and trip the anti-vacuity
            # refusal instead, which is a different case (and is covered by
            # `test_an_empty_writer_array_refuses`). The first draft of this
            # parameter did exactly that and asserted three violations against a
            # refusal.
            ("test-elsewhere.sh",),
            3,
            id="three-unregistered",
        ),
    ],
)
def test_port_and_twin_agree_byte_for_byte(
    tmp_path: pathlib.Path, gates: dict[str, str], registered: tuple[str, ...], violations: int
) -> None:
    root, gdir, runner = build(tmp_path, gates, runner_text(*registered))
    (old_exit, old_out, old_err), (new_exit, new_out, new_err) = run_both(root, gdir, runner)
    assert old_exit == 1
    assert new_exit == old_exit
    assert new_out == old_out
    assert new_err == old_err
    assert "%d unregistered real-tree writer(s)" % violations in old_err


def test_a_registered_writer_alone_is_green_on_both_sides(tmp_path: pathlib.Path) -> None:
    """The mirror: the rule is ONE-DIRECTIONAL and a declared writer is fine."""
    root, gdir, runner = build(
        tmp_path, {"test-reg.sh": WRITER, "test-safe.sh": TEMPSAFE}, runner_text("test-reg.sh")
    )
    (old_exit, old_out, old_err), (new_exit, new_out, new_err) = run_both(root, gdir, runner)
    assert old_exit == 0
    assert new_exit == 0
    assert new_out == old_out
    assert new_err == old_err
    # THE COUNT IS PRINTED IN THE GREEN LINE, so a reader can see the verdict was
    # not trivial.
    assert "among 2 gate tests" in old_err


def test_a_temp_only_writer_alone_is_green(tmp_path: pathlib.Path) -> None:
    """A scanner that flagged every file would pass every positive case above."""
    root, gdir, runner = build(tmp_path, {"test-safe.sh": TEMPSAFE}, runner_text())
    (old_exit, _, old_err), (new_exit, _, new_err) = run_both(root, gdir, runner)
    assert (old_exit, new_exit) == (1, 1)
    # An empty fallback array is the EMPTY-parse refusal, not a clean battery,
    # which is the anti-vacuity half of this gate rather than a finding about
    # test-safe.sh.
    assert "parsed an EMPTY WRITER_TESTS" in old_err
    assert new_err == old_err


def test_an_empty_writer_array_refuses(tmp_path: pathlib.Path) -> None:
    """Archaeology 1 and 2 together: the refusal that used to exit 127."""
    root, gdir, runner = build(tmp_path, {"test-a.sh": WRITER}, DERIVED_ONLY)
    (old_exit, _, old_err), (new_exit, _, new_err) = run_both(root, gdir, runner)
    assert (old_exit, new_exit) == (1, 1)
    assert "this gate would pass everything" in old_err
    assert new_err == old_err


def test_a_missing_runner_refuses(tmp_path: pathlib.Path) -> None:
    root, gdir, runner = build(tmp_path, {"test-a.sh": WRITER}, runner_text("x.sh"))
    runner.unlink()
    (old_exit, _, old_err), (new_exit, _, new_err) = run_both(root, gdir, runner)
    assert (old_exit, new_exit) == (1, 1)
    assert "refusing to pass while measuring nothing" in old_err
    assert new_err == old_err


def test_an_empty_gates_directory_refuses(tmp_path: pathlib.Path) -> None:
    """ZERO INPUTS IS A FAILURE, never a pass."""
    root, gdir, runner = build(tmp_path, {}, runner_text("test-reg.sh"))
    (old_exit, _, old_err), (new_exit, _, new_err) = run_both(root, gdir, runner)
    assert (old_exit, new_exit) == (1, 1)
    assert "refusing to report a clean battery over an empty set" in old_err
    assert new_err == old_err


# ---------------------------------------------------------------------------
# The scanner, driven directly. Both directions for every rule.
# ---------------------------------------------------------------------------

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

    Measured 2026-09-06: planting the swap left all the other controls and all
    five recorded shadow rows green, because every one of them references exactly
    one kind of variable. A control that cannot fail is not a control.
    """
    both = _TEMP + _SEED + 'cp "$SRC" "$TMP/${REPO_ROOT}.log"\n'
    assert gate.scan_text(both, "t.sh") == []
    only_taint = _SEED + 'cp "$SRC" "$X/${REPO_ROOT}.log"\n'
    assert len(gate.scan_text(only_taint, "t.sh")) == 1


def test_the_two_passes_catch_a_write_above_its_assignment() -> None:
    """A function body can textually precede the global it uses; hence pass 1."""
    text = 'run() { printf x >"$REPO_ROOT/f"; }\n' + _SEED
    assert len(gate.scan_text(text, "t.sh")) == 1


def test_registered_writers_unions_both_arrays() -> None:
    assert gate.registered_writers(
        runner_text("test-a.sh", "test-b.sh") + "WRITER_TESTS=(\n    test-c.sh\n)\n"
    ) == ["test-a.sh", "test-b.sh", "test-c.sh"]


def test_registered_writers_drops_comment_lines_inside_the_array() -> None:
    assert gate.registered_writers(
        "WRITER_TESTS=(\n    # test-only-a-comment.sh\n    test-real.sh\n)\n"
    ) == ["test-real.sh"]


def test_the_derived_assignment_alone_parses_empty() -> None:
    """The state the refusal exists for, and could not report before 2026-09-06."""
    assert gate.registered_writers(DERIVED_ONLY) == []


def test_the_planted_controls_land_in_both_directions() -> None:
    """The gate refuses to judge the real battery unless BOTH of these hold."""
    assert len(gate.scan_text(gate.PLANTED_WRITER, "test-planted-writer.sh")) == 1
    assert gate.scan_text(gate.PLANTED_TEMPSAFE, "test-planted-tempsafe.sh") == []


def test_selftest_passes_and_is_not_vacuous(capsys) -> None:
    assert gate.selftest() == 0
    out = capsys.readouterr().out
    assert "control(s) passed" in out
    assert int(out.strip().split("\n")[-1].split()[0]) >= 24
