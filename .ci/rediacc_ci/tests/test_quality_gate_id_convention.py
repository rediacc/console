"""`rediacc_ci.quality.gate_id_convention` against the twin's own embedded program.

WHAT IS WORTH TESTING HERE. The shadow ledger
`.ci/shadow/w7p2-gate-id-convention.observations.jsonl` drives the whole gate over
five distinct trees: a direct gates/ script under the wrong id, the 2026-08-08
alias shape, a missing lock, a missing corpus directory, and a reader seeing less
than the corpus. What a ledger row cannot isolate is that this gate's ENTIRE
logic already existed as Python, inside a heredoc, and a port of it can drift in
exactly the way the thing it replaced drifted: silently, in the narrowing
direction, while the green line still reads healthy.

So the twin's heredoc is EXTRACTED from its source and run as a subprocess over
the same inputs, and the two are compared line for line. That is a stronger check
than any hand-written expectation, because it fails when either side changes.

The alias resolver is also driven directly on the shapes the header argues about:
the one-hop unwind that must resolve, the `ci: { test: ... }` mention that must
NOT, and the two-hop chain the #557 review accepted as out of scope.
"""

import json
import pathlib
import subprocess
import sys

from rediacc_ci import paths
from rediacc_ci.quality import gate_id_convention as gi

TWIN = paths.from_root(".ci", "scripts", "quality", "check-gate-id-convention.sh")


def twin_program() -> str:
    """The `evaluate` heredoc, lifted out of the twin.

    Read rather than copied: the point of a differential port is that a change
    to the twin reds this test instead of drifting past it.
    """
    body = TWIN.read_text(encoding="utf-8")
    start = body.index('    python3 - "$1" "$2" "$3" <<\'PY\'\n')
    start = body.index("\n", start) + 1
    end = body.index("\nPY\n", start)
    return body[start:end]


def _twin_evaluate(lock: str, pkg: str, gates_dir: str) -> tuple[list[str], list[str]]:
    """Run the twin's own program. Returns (stdout lines, stderr lines)."""
    proc = subprocess.run(
        [sys.executable, "-", lock, pkg, gates_dir],
        input=twin_program().encode("utf-8"),
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8")
    out = [line for line in proc.stdout.decode("utf-8").split("\n") if line != ""]
    err = [line for line in proc.stderr.decode("utf-8").split("\n") if line != ""]
    return out, err


SCRIPTS = {
    "check:ci-alias": ".ci/scripts/test/gates/test-alias.sh",
    "check:ci-other": "tsx scripts/check-other.ts",
}

CONFORMING = [
    {"id": "gate-test:%s" % n, "run": ".ci/scripts/test/gates/test-%s.sh" % n}
    for n in ("a", "b", "c")
]


def _fixture(tmp_path: pathlib.Path, entries, scripts) -> tuple[str, str, str]:
    gates_dir = tmp_path / "gates"
    gates_dir.mkdir(exist_ok=True)
    for name in ("test-a.sh", "test-b.sh", "test-c.sh"):
        (gates_dir / name).write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    lock = tmp_path / "lock.json"
    pkg = tmp_path / "package.json"
    lock.write_text(json.dumps(entries), encoding="utf-8")
    pkg.write_text(json.dumps({"scripts": scripts}), encoding="utf-8")
    return str(lock), str(pkg), str(gates_dir)


CASES = (
    ("clean", CONFORMING, SCRIPTS),
    (
        "direct under a check id",
        [*CONFORMING, {"id": "check:ci-d", "run": ".ci/scripts/test/gates/test-d.sh"}],
        SCRIPTS,
    ),
    (
        "the 2026-08-08 alias",
        [*CONFORMING, {"id": "check:ci-alias", "run": "npm run check:ci-alias"}],
        SCRIPTS,
    ),
    (
        "a silent alias",
        [*CONFORMING, {"id": "check:ci-alias", "run": "npm run --silent check:ci-alias"}],
        SCRIPTS,
    ),
    (
        "a conforming alias",
        [*CONFORMING, {"id": "gate-test:alias", "run": "npm run check:ci-alias"}],
        SCRIPTS,
    ),
    (
        "a non-gate alias",
        [*CONFORMING, {"id": "check:ci-other", "run": "npm run check:ci-other"}],
        SCRIPTS,
    ),
    (
        "a mere mention",
        [*CONFORMING, {"id": "check:ci-m", "run": "tsx x.ts .ci/scripts/test/gates/test-a.sh"}],
        SCRIPTS,
    ),
    ("a collapsed reader", CONFORMING[:2], SCRIPTS),
    ("entries missing id or run", [*CONFORMING, {"id": "x"}, {"run": "y"}], SCRIPTS),
)


def test_evaluate_matches_the_twins_program_on_every_case(tmp_path: pathlib.Path) -> None:
    """Nine locks, both streams, against the heredoc lifted from the twin."""
    for label, entries, scripts in CASES:
        lock, pkg, gates_dir = _fixture(tmp_path, entries, scripts)
        assert gi.evaluate(lock, pkg, gates_dir) == _twin_evaluate(lock, pkg, gates_dir), label


def test_evaluate_matches_the_twin_on_an_empty_corpus(tmp_path: pathlib.Path) -> None:
    """An empty gates/ directory must REFUSE on both sides, not pass quietly."""
    lock, pkg, _gates = _fixture(tmp_path, CONFORMING, SCRIPTS)
    empty = tmp_path / "empty"
    empty.mkdir()
    got = gi.evaluate(lock, pkg, str(empty))
    assert got == _twin_evaluate(lock, pkg, str(empty))
    assert got[0][0].startswith("FLOOR: no test-*.sh")


def test_evaluate_matches_the_twin_on_unreadable_inputs(tmp_path: pathlib.Path) -> None:
    """PARSE branches, which are the only paths that print no scope line."""
    lock, pkg, gates_dir = _fixture(tmp_path, CONFORMING, SCRIPTS)
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    obj = tmp_path / "object.json"
    obj.write_text('{"a": 1}', encoding="utf-8")

    for bad_lock, bad_pkg in ((str(broken), pkg), (lock, str(broken)), (str(obj), pkg)):
        got = gi.evaluate(bad_lock, bad_pkg, gates_dir)
        want = _twin_evaluate(bad_lock, bad_pkg, gates_dir)
        # The exception TEXT differs between two json module versions only if they disagree, and they do not: both sides are the same interpreter.
        assert got == want, (bad_lock, bad_pkg)
        assert got[1] == []


def test_the_planted_control_entry_still_fires_against_the_real_lock(
    tmp_path: pathlib.Path,
) -> None:
    """CONTROL 1's plant, run against the REAL lock and the REAL package.json.

    This is the control the gate itself runs on every invocation; asserting it
    here means a change to either real file that made the plant stop firing is a
    test failure rather than a gate that quietly cannot detect its own defect.
    """
    root = paths.repo_root()
    entries = json.loads((root / gi.LOCK_REL).read_text(encoding="utf-8"))
    entries.append(gi.PLANTED_ENTRY)
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps(entries), encoding="utf-8")

    manifest = json.loads((root / gi.PKG_REL).read_text(encoding="utf-8"))
    manifest.setdefault("scripts", {})[gi.PLANTED_ID] = gi.PLANTED_SCRIPT
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps(manifest), encoding="utf-8")

    out, _err = gi.evaluate(str(lock), str(pkg), str(root / gi.GATES_DIR_REL))
    assert any(line.startswith("CONVENTION:") for line in out), out[:3]
    assert out == _twin_evaluate(str(lock), str(pkg), str(root / gi.GATES_DIR_REL))[0]


def test_the_corpus_floor_fires_on_a_five_entry_lock(tmp_path: pathlib.Path) -> None:
    """CONTROL 2, against the real lock truncated the way the gate truncates it."""
    root = paths.repo_root()
    short = json.loads((root / gi.LOCK_REL).read_text(encoding="utf-8"))[:5]
    lock = tmp_path / "short.json"
    lock.write_text(json.dumps(short), encoding="utf-8")
    out, _err = gi.evaluate(str(lock), str(root / gi.PKG_REL), str(root / gi.GATES_DIR_REL))
    assert any(line.startswith("FLOOR:") for line in out), out


def test_selftest_runs_and_meets_its_floor() -> None:
    """The gate's own both-direction controls, over locks written by construction."""
    assert gi.selftest() == 0
