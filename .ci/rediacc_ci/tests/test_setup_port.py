"""`rediacc_ci.setup` against the bash it replaces, at the seams the ledger cannot see.

WHAT THIS IS NOT. It is not the proof that the port is faithful; that is
`.ci/shadow/e1-setup.observations.jsonl`, which compares 116 to 120 observations
over five distinct clean trees and was recorded by
`scripts/lib/shadow-gate.ts --record`. A differential over whole runs cannot
isolate a helper, and a unit test over a helper cannot notice a phase that
stopped running. This file covers the first half.

WHY THE BASH IS RUN RATHER THAN DESCRIBED. Every case below that could be
written as "the port returns X" is instead written as "the port and the bash
return the same thing", for the reason `test_quality_npmrc.py` gives: a table of
expected strings is a table of what the port does, asserted against itself. The
awkward inputs here are decided by `sort -V`, by `cut -d'v' -f2`, by
`${suggested%% <*}` and by two `python3 -c` heredocs with a shell variable
interpolated INTO them, and none of those is inferable by reading.

THE ONE PLACE A LITERAL IS RIGHT is the phase table, because there is no bash
expression to compare it against: the order lives in `setup()`'s control flow.
`test_phase_order_matches_the_bash` reads it out of the bash and compares, which
is the same comparison `check:ci-setup-port-parity` makes on every run and is
repeated here so a `pytest -k setup_port` run says so too.
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
TWIN = ROOT / ".ci" / "lib" / "setup.sh"
BODY = ROOT.joinpath(*phases.SETUP_BODY_FILE)

# Skipped rather than failed when the bash is gone: after the flip these cases
# have no second implementation to compare against, and a red here would be the
# migration succeeding. `check:ci-setup-port-parity` A5 is what still holds then.
needs_bash = pytest.mark.skipif(
    not TWIN.is_file() or not BODY.is_file(),
    reason="the bash twin has been deleted; the ledger is the surviving evidence",
)


def bash(body: str) -> tuple[int, str]:
    """One `bash -c` with `.ci/lib/setup.sh` in scope. `(rc, stdout)`."""
    script = 'ROOT_DIR=%s\nset -euo pipefail\nsource "$ROOT_DIR/.ci/lib/setup.sh"\n%s' % (
        _quote(str(ROOT)),
        body,
    )
    proc = subprocess.run(
        ["bash", "-c", script],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout


def _quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


# ---------------------------------------------------------------------------
# the phase order
# ---------------------------------------------------------------------------


@needs_bash
def test_phase_order_matches_the_bash() -> None:
    """`phases.PHASE_KEYS` and the bash `setup()` agree, in order and both ways."""
    assert phases.from_source(ROOT) == list(phases.PHASE_KEYS)


def test_phase_order_matches_run_setup() -> None:
    """The table and the code path that executes it agree, in order.

    This is the clause that survives the flip, and it is the one that catches
    the drift that actually happens: `run_setup` is a straight line, and a
    straight line is edited by hand.
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

    `setup_docker_probe` is defined at `.ci/lib/setup.sh:575` and called by no
    file in the repository. Both halves are asserted, because carrying the port
    without excluding it from `PHASES` would silently ADD a phase the bash never
    ran, and excluding it without porting it would lose the code.
    """
    assert "setup_docker_probe" in phases.DEFINED_BUT_UNCALLED
    assert "setup_docker_probe" not in phases.PHASE_KEYS
    assert callable(host.docker_probe)


# ---------------------------------------------------------------------------
# node_pick_lts, against the heredoc it replaces
# ---------------------------------------------------------------------------

# Each row is a property, not a sample. A row with no property is a row that
# will be deleted the first time someone tidies this file.
NODE_INDEX = json.dumps(
    [
        {"version": "v23.1.0", "lts": False},  # newer major, no LTS flag
        {"version": "v22.20.0", "lts": False},  # newest on 22, but NOT lts
        {"version": "v22.13.0", "lts": "Jod"},  # the LTS the fallback must skip past
        {"version": "v22.9.0", "lts": "Jod"},  # an older LTS on the same major
        {"version": "v20.18.0", "lts": "Iron"},
        {"version": "v19.9.0", "lts": False},  # a major with LTS-less releases only
    ]
)


@needs_bash
@pytest.mark.parametrize("major", ["22", "20", "23", "19", "18", "2"])
def test_node_pick_lts_agrees_with_bash(major: str) -> None:
    """The Python and the `python3 -c` heredoc pick the same release.

    `"2"` is in the list on purpose: the bash builds its prefix as `v${major}.`,
    so `2` must NOT match `v22.13.0`. A port that compared on `startswith("v2")`
    would pass every other row here.
    """
    rc, out = bash("printf '%%s' %s | node_pick_lts %s" % (_quote(NODE_INDEX), major))
    mine = host.node_pick_lts(NODE_INDEX, major)
    assert (out.strip() or None) == mine
    assert (rc == 0) == (mine is not None)


def test_node_pick_lts_survives_garbage() -> None:
    """Unparseable input is None, never an exception.

    The bash wraps its `json.load` in `try/except: sys.exit(1)` and sends stderr
    to /dev/null, so a truncated download is a silent empty answer there. The
    port answers the same way rather than raising into a caller that has no
    handler for it.
    """
    assert host.node_pick_lts("{not json", "22") is None
    assert host.node_pick_lts('{"version": "v22.0.0"}', "22") is None  # an object, not a list
    assert host.node_pick_lts("[]", "22") is None


# ---------------------------------------------------------------------------
# go_pick_sha
# ---------------------------------------------------------------------------

GO_INDEX = json.dumps(
    [
        {
            "version": "go1.26.6",
            "files": [
                {"filename": "go1.26.6.linux-amd64.tar.gz", "sha256": "a" * 64},
                # An EMPTY sha256 must not be returned: the bash's condition is
                # `and f.get('sha256')`, so a published-but-unhashed row is a
                # miss and not an empty answer that reaches a comparison.
                {"filename": "go1.26.6.src.tar.gz", "sha256": ""},
            ],
        },
        {"version": "go1.25.0", "files": [{"filename": "x.tar.gz", "sha256": "c" * 64}]},
    ]
)


@needs_bash
@pytest.mark.parametrize(
    "filename",
    ["go1.26.6.linux-amd64.tar.gz", "go1.26.6.src.tar.gz", "x.tar.gz", "absent.tar.gz"],
)
def test_go_pick_sha_agrees_with_bash(filename: str) -> None:
    rc, out = bash("printf '%%s' %s | go_pick_sha %s" % (_quote(GO_INDEX), filename))
    mine = host.go_pick_sha(GO_INDEX, filename)
    assert (out.strip() or None) == mine
    assert (rc == 0) == (mine is not None)


# ---------------------------------------------------------------------------
# the identity helpers
# ---------------------------------------------------------------------------


@needs_bash
@pytest.mark.parametrize(
    "suggested",
    [
        "Ada Lovelace <ada@example.com>",
        "Two <Angle> Brackets <t@example.com>",  # `%% <*` cuts at the FIRST " <"
        "NoAngles",  # neither strip has anything to do
        "<only@example.com>",  # an empty name
    ],
)
def test_split_identity_agrees_with_bash(suggested: str) -> None:
    """`${suggested%% <*}` and `sed 's/.*<//; s/>.*//'`, as one Python call.

    The second bash expression is a GREEDY `.*<`, so the LAST `<` wins for the
    email while the FIRST " <" wins for the name. Those two disagree on the
    bracket case above, which is exactly why it is here.
    """
    rc, out = bash(
        "SUG=%s\nprintf '%%s|%%s' \"${SUG%%%% <*}\" "
        "\"$(printf '%%s' \"$SUG\" | sed 's/.*<//; s/>.*//')\"" % _quote(suggested)
    )
    assert rc == 0
    want_name, want_email = out.split("|", 1)
    assert host.split_identity(suggested) == (want_name, want_email)


@needs_bash
def test_dominant_author_agrees_with_bash() -> None:
    """The most frequent non-bot author of the last 200 commits.

    RUN AGAINST THE REAL LOG, because the tie-break is unspecified on both sides
    (`sort -rn` is not stable) and a synthetic corpus with a tie would compare
    two arbitrary choices. The real history has a clear winner, which is the
    only case either implementation is asked about in anger.
    """
    log = subprocess.run(
        ["git", "log", "-200", "--format=%an <%ae>"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    rc, out = bash(
        "printf '%%s' %s | grep -v '\\[bot\\]' | sort | uniq -c | sort -rn | head -1 "
        "| sed 's/^ *[0-9]* //'" % _quote(log)
    )
    assert rc == 0
    assert host.dominant_author(log) == out.strip()


def test_dominant_author_excludes_bots() -> None:
    log = "bot [bot] <b@x>\nbot [bot] <b@x>\nbot [bot] <b@x>\nAda <a@x>\n"
    assert host.dominant_author(log) == "Ada <a@x>"
    assert host.dominant_author("") == ""


# ---------------------------------------------------------------------------
# the flag grammar
# ---------------------------------------------------------------------------


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


@needs_bash
def test_help_text_is_byte_identical() -> None:
    """`machine.HELP` and the heredoc in `setup()` are the same bytes.

    Not "equivalent": a person who has memorised the old output should see no
    diff, and this is the cheapest place to keep that true while both exist.
    """
    body = phases.function_body(BODY.read_text(encoding="utf-8"), "setup")
    start = body.index("Usage: ./run.sh setup [OPTIONS]")
    end = body.index("EOF", start)
    assert body[start:end].rstrip("\n") == machine.HELP


# ---------------------------------------------------------------------------
# the extractor this package shares with a quality gate
# ---------------------------------------------------------------------------


def test_function_body_matches_the_gates_extractor() -> None:
    """`phases.function_body` and `setup_idempotency.function_body` agree.

    THE COPY IS DELIBERATE and this is the check that keeps it honest.
    `phases.py` reimplements the extractor rather than importing it, because
    importing a quality gate from a runtime module makes the gate a dependency
    of the thing it judges. That decision is only safe while the two agree.
    """
    text = BODY.read_text(encoding="utf-8") if BODY.is_file() else "f() {\n  x\n}\n"
    for name in ("setup", "setup_check", "does_not_exist"):
        assert phases.function_body(text, name) == setup_idempotency.function_body(text, name)


def test_function_body_python_ends_at_the_dedent() -> None:
    source = "def a():\n    x = 1\n\n    y = 2\n\n\ndef b():\n    z = 3\n"
    assert phases.function_body_python(source, "a") == "def a():\n    x = 1\n\n    y = 2\n\n"
    assert phases.function_body_python(source, "b") == "def b():\n    z = 3\n"
    assert phases.function_body_python(source, "c") == ""


# ---------------------------------------------------------------------------
# the ledger this port stands on
# ---------------------------------------------------------------------------


def test_ledger_carries_five_equivalent_trees() -> None:
    """The evidence file is present, parses, and has not shrunk.

    A test and not only a gate clause, because a `pytest -k setup_port` run is
    what a person does while editing this package, and the ledger is the thing
    an edit here silently invalidates.
    """
    trees, why = port_parity.ledger_trees(ROOT)
    assert why == "", why
    assert trees >= port_parity.LEDGER_K


def test_ledger_rows_name_both_implementations() -> None:
    """Every row's commands name the Python driver AND the bash twin.

    `.ci/rediacc_ci/quality/dead_python.py:317` reads exactly these two fields to
    decide whether a pre-cutover port is alive. A ledger recorded with a command
    that names neither admits nothing, and the port would read as dead code the
    day it landed.
    """
    path = ROOT / port_parity.LEDGER
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert rows
    for row in rows:
        assert "shadow_driver.py" in row["new"]["cmd"]
        assert ".ci/lib/setup.sh" in row["old"]["cmd"]


def test_shadow_driver_refuses_without_its_twin(tmp_path: pathlib.Path) -> None:
    """A missing bash twin is exit 77 and NOT an empty observation set.

    The anti-vacuity clause of the differential itself: after the flip both
    sides must refuse, because two silent sides compare as equal.
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
