"""`rediacc_ci.setup` against the bash it replaces, at the seams the ledger cannot see.

WHAT THIS IS NOT. It is not the proof that the port is faithful; that is `.ci/shadow/e1-setup.observations.jsonl`, which compares 116 to 120 observations over five distinct clean trees and was recorded by `scripts/lib/shadow-gate.ts --record`. A differential over whole runs cannot isolate a helper, and a unit test over a helper cannot notice a phase that stopped running. This file
covers the first half.

THE BASH IS GONE, AND SO ARE THE CASES THAT RAN IT. `.ci/lib/setup.sh` was deleted by `1ae84c3e3`; six differential cases (17 with their parameters) were left behind guarded by `skipif(not TWIN.is_file())`, which is permanently true. They were removed 2026-09-15 rather than left skipping, and the reasoning is worth keeping because the original choice was deliberate and still wrong:

    skipping was chosen so that "a red here would be the migration succeeding"

That is a good instinct about pytest's exit code and a bad one about the gate
above it. `check:ci-pytest` refuses `passed != collected` on purpose -- a skipped
test is not a passing one, and the difference is invisible in the exit code -- so 17 permanent skips did not read as "migration succeeded", they read as a gate that could never go green again. It stayed invisible for six days because that gate is slow (deferred from every `--quick` receipt) and its lane was cancelled in every CI run of the wave. A test kept alive as a permanent
skip is dead code
with a heartbeat monitor attached.

WHAT STILL COVERS THE DELETED CASES. `check:ci-setup-port-parity`, which reports `FLIPPED (bash gone)` and `5 EQUIVALENT tree(s) in the ledger` -- verified passing before the deletion, not assumed -- plus `.ci/shadow/e1-setup.observations.jsonl` itself. The ledger is the surviving evidence, which is exactly what the skip reason said it would be.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import setup_idempotency
from rediacc_ci.setup import host, machine, phases, port_parity

if TYPE_CHECKING:  # pragma: no cover - `pathlib` is only ever an annotation here
    import pathlib

ROOT = paths.repo_root()
BODY = ROOT.joinpath(*phases.SETUP_BODY_FILE)

# --------------------------------------------------------------------------- the phase order ---------------------------------------------------------------------------


def test_phase_order_matches_run_setup() -> None:
    """The table and the code path that executes it agree, in order.

    This is the clause that survives the flip, and it is the one that catches the drift that actually happens: `run_setup` is a straight line, and a straight line is edited by hand.
    """
    source = (ROOT / ".ci" / "rediacc_ci" / "setup" / "machine.py").read_text(encoding="utf-8")
    assert port_parity.run_setup_order(source, phases.PHASE_KEYS) == list(phases.PHASE_KEYS)


def test_no_start_drops_exactly_devbox_up() -> None:
    """`--no-start` removes one phase and moves none of the others."""
    full = phases.plan(ROOT, {}, start=True)
    short = phases.plan(ROOT, {}, start=False)
    assert short == [k for k in full if k != "devbox_up"]
    assert "devbox_up" in full


def test_docker_probe_is_ported_but_not_a_phase() -> None:
    """The dead bash function has a port and is NOT in the phase table.

    `setup_docker_probe` is defined at `.ci/lib/setup.sh:575` and called by no file in the repository. Both halves are asserted, because carrying the port without excluding it from `PHASES` would silently ADD a phase the bash never ran, and excluding it without porting it would lose the code.
    """
    assert "setup_docker_probe" in phases.DEFINED_BUT_UNCALLED
    assert "setup_docker_probe" not in phases.PHASE_KEYS
    assert callable(host.docker_probe)


# --------------------------------------------------------------------------- node_pick_lts, against the heredoc it replaces ---------------------------------------------------------------------------

# Each row is a property, not a sample. A row with no property is a row that will be deleted the first time someone tidies this file.


def test_node_pick_lts_survives_garbage() -> None:
    """Unparseable input is None, never an exception.

    The bash wraps its `json.load` in `try/except: sys.exit(1)` and sends stderr to /dev/null, so a truncated download is a silent empty answer there. The port answers the same way rather than raising into a caller that has no handler for it.
    """
    assert host.node_pick_lts("{not json", "22") is None
    assert host.node_pick_lts('{"version": "v22.0.0"}', "22") is None  # an object, not a list
    assert host.node_pick_lts("[]", "22") is None


# --------------------------------------------------------------------------- go_pick_sha ---------------------------------------------------------------------------


# --------------------------------------------------------------------------- the identity helpers ---------------------------------------------------------------------------


def test_dominant_author_excludes_bots() -> None:
    log = "bot [bot] <b@x>\nbot [bot] <b@x>\nbot [bot] <b@x>\nAda <a@x>\n"
    assert host.dominant_author(log) == "Ada <a@x>"
    assert host.dominant_author("") == ""


# --------------------------------------------------------------------------- the flag grammar ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "want"),
    [
        ([], machine.Options()),
        (["--check"], machine.Options(check=True)),
        (["--pull"], machine.Options(pull=True)),
        (["--no-start"], machine.Options(start=False)),
        # ORDER-INSENSITIVE and REPEAT-TOLERANT, like the `while` loop it ports.
        (["--pull", "--check"], machine.Options(check=True, pull=True)),
        (["--check", "--pull"], machine.Options(check=True, pull=True)),
        (["--check", "--check"], machine.Options(check=True)),
        # `--help` returns IMMEDIATELY, so a later bad flag never reports.
        (["--help"], machine.Options(help=True)),
        (["--check", "--help", "--bogus"], machine.Options(check=True, help=True)),
        (["--bogus"], machine.Options(error="--bogus")),
        (["--check", "--bogus"], machine.Options(error="--bogus")),
    ],
)
def test_parse_args(argv: list[str], want: machine.Options) -> None:
    assert machine.parse_args(argv) == want


# --------------------------------------------------------------------------- the extractor this package shares with a quality gate ---------------------------------------------------------------------------


def test_function_body_matches_the_gates_extractor() -> None:
    """`phases.function_body` and `setup_idempotency.function_body` agree.

    THE COPY IS DELIBERATE and this is the check that keeps it honest. `phases.py` reimplements the extractor rather than importing it, because importing a quality gate from a runtime module makes the gate a dependency of the thing it judges. That decision is only safe while the two agree.
    """
    text = BODY.read_text(encoding="utf-8") if BODY.is_file() else "f() {\n  x\n}\n"
    for name in ("setup", "setup_check", "does_not_exist"):
        assert phases.function_body(text, name) == setup_idempotency.function_body(text, name)


def test_function_body_python_ends_at_the_dedent() -> None:
    source = "def a():\n    x = 1\n\n    y = 2\n\n\ndef b():\n    z = 3\n"
    assert phases.function_body_python(source, "a") == "def a():\n    x = 1\n\n    y = 2\n\n"
    assert phases.function_body_python(source, "b") == "def b():\n    z = 3\n"
    assert phases.function_body_python(source, "c") == ""


# --------------------------------------------------------------------------- the ledger this port stands on ---------------------------------------------------------------------------


def test_ledger_carries_five_equivalent_trees() -> None:
    """The evidence file is present, parses, and has not shrunk.

    A test and not only a gate clause, because a `pytest -k setup_port` run is what a person does while editing this package, and the ledger is the thing an edit here silently invalidates.
    """
    trees, why = port_parity.ledger_trees(ROOT)
    assert why == "", why
    assert trees >= port_parity.LEDGER_K


def test_ledger_rows_name_both_implementations() -> None:
    """Every row's commands name the Python driver AND the bash twin.

    `.ci/rediacc_ci/quality/dead_python.py:317` reads exactly these two fields to decide whether a pre-cutover port is alive. A ledger recorded with a command that names neither admits nothing, and the port would read as dead code the day it landed.
    """
    path = ROOT / port_parity.LEDGER
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert rows
    for row in rows:
        assert "shadow_driver.py" in row["new"]["cmd"]
        assert ".ci/lib/setup.sh" in row["old"]["cmd"]


def test_shadow_driver_refuses_without_its_twin(tmp_path: pathlib.Path) -> None:
    """A missing bash twin is exit 77 and NOT an empty observation set.

    The anti-vacuity clause of the differential itself: after the flip both sides must refuse, because two silent sides compare as equal.
    """
    driver = ROOT / ".ci" / "rediacc_ci" / "setup" / "shadow_driver.py"
    proc = subprocess.run(
        ["python3", str(driver), "--side", "old", "--root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 77
    assert proc.stdout == ""
    assert "CANNOT RUN" in proc.stderr
