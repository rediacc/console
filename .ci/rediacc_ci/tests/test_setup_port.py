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
from rediacc_ci.setup.ctx import Result

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


# --------------------------------------------------------------------------- setup --check: the deps row and the timing ---------------------------------------------------------------------------


class _RecordingCtx(machine.Ctx):
    """A `Ctx` with no tools on PATH that records every line instead of printing it."""

    def __init__(self, root: pathlib.Path) -> None:
        super().__init__(root=root, env={}, stdin_tty=False)
        self.lines: list[str] = []

    def which(self, _name: str) -> str | None:
        return None

    def run(
        self,
        argv: list[str],
        *,
        timeout: int | None = None,
        stdin_text: str | None = None,
    ) -> Result:
        del argv, timeout, stdin_text
        return Result(1, "", "")

    def say(self, message: str = "") -> None:
        self.lines.append(message)

    def info(self, message: str) -> None:
        self.lines.append("INFO " + message)

    def warn(self, message: str) -> None:
        self.lines.append("WARN " + message)

    def step(self, message: str) -> None:
        self.lines.append("STEP " + message)


@pytest.mark.parametrize(
    ("current", "row", "counted"),
    [
        (True, "  deps        installed (stamp matches)", False),
        (False, "  deps        STALE (dependencies and native modules pending)", True),
    ],
)
def test_check_reports_deps_through_the_live_rule(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, current: bool, row: str, counted: bool
) -> None:
    asked: list[str] = []

    def fake_call(expr: str, *_args: object) -> int:
        asked.append(expr)
        if expr == "deps_are_current":
            return 0 if current else 1
        return 0

    monkeypatch.setattr(machine.bridge, "call", fake_call)
    monkeypatch.setattr(
        machine,
        "_devbox_facts",
        lambda *_a: {"worktree": str(tmp_path), "image": "1", "running": "1"},
    )
    monkeypatch.setattr(machine, "_port_block_row", lambda *_a: "  port block  1-10")
    monkeypatch.setattr(machine.githooks, "check_row", lambda _root: ("  git hooks   ok", 0))
    monkeypatch.setattr(machine.host, "_git_global", lambda *_a: "dev@example.com")

    ctx = _RecordingCtx(tmp_path)
    started = machine.time.monotonic()
    machine.check(ctx, {"DEVBOX_IMAGE": "img", "NODE_VERSION_MIN": "22"}, started)

    assert "deps_are_current" in asked, (
        "the row must ask the same rule ensure_deps uses, through the bridge"
    )
    assert row in ctx.lines
    # Between docker and image, where the checkpoint put it.
    docker = next(i for i, line in enumerate(ctx.lines) if line.startswith("  docker "))
    image = next(i for i, line in enumerate(ctx.lines) if line.startswith("  image "))
    assert docker < ctx.lines.index(row) < image
    closing = ctx.lines[-1]
    assert closing.endswith("(checked in 0s)"), closing
    # node, gh and the compiler are MISSING under this Ctx (3), docker is MISSING (1); STALE deps adds one.
    assert closing.startswith("WARN %d item(s)" % (4 + int(counted))), closing


class _OldNodeCtx(_RecordingCtx):
    """Only `node` is on PATH, at the version given."""

    def __init__(self, root: pathlib.Path, version: str) -> None:
        super().__init__(root)
        self.version = version

    def which(self, name: str) -> str | None:
        return "/usr/bin/node" if name == "node" else None

    def run(
        self,
        argv: list[str],
        *,
        timeout: int | None = None,
        stdin_text: str | None = None,
    ) -> Result:
        del timeout, stdin_text
        return Result(0, self.version + "\n", "") if argv[0] == "node" else Result(1, "", "")


@pytest.mark.parametrize(
    ("version", "row", "counted"),
    [
        ("v22.23.2", "  node        v22.23.2 OLDER than the floor 24.11.0", True),
        ("v24.11.0", "  node        v24.11.0", False),
        ("v24.21.0", "  node        v24.21.0", False),
    ],
)
def test_check_judges_a_present_node_against_the_floor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path, version: str, row: str, counted: bool
) -> None:
    """A present node under NODE_VERSION_MIN is pending work, because `./run.sh setup` refuses it."""
    monkeypatch.setattr(machine.bridge, "call", lambda *_a: 0)
    monkeypatch.setattr(
        machine,
        "_devbox_facts",
        lambda *_a: {"worktree": str(tmp_path), "image": "1", "running": "1"},
    )
    monkeypatch.setattr(machine, "_port_block_row", lambda *_a: "  port block  1-10")
    monkeypatch.setattr(machine.githooks, "check_row", lambda _root: ("  git hooks   ok", 0))
    monkeypatch.setattr(machine.host, "_git_global", lambda *_a: "dev@example.com")
    ctx = _OldNodeCtx(tmp_path, version)
    machine.check(ctx, {"DEVBOX_IMAGE": "img", "NODE_VERSION_MIN": "24.11.0"})
    assert row in ctx.lines, ctx.lines
    # gh, the compiler and docker are MISSING under this Ctx (3); an old node adds one.
    assert ctx.lines[-1].startswith("WARN %d item(s)" % (3 + int(counted))), ctx.lines[-1]


def test_check_without_a_start_time_prints_no_suffix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setattr(machine.bridge, "call", lambda *_a: 0)
    monkeypatch.setattr(
        machine,
        "_devbox_facts",
        lambda *_a: {"worktree": str(tmp_path), "image": "1", "running": "1"},
    )
    monkeypatch.setattr(machine, "_port_block_row", lambda *_a: "  port block  1-10")
    monkeypatch.setattr(machine.githooks, "check_row", lambda _root: ("  git hooks   ok", 0))
    monkeypatch.setattr(machine.host, "_git_global", lambda *_a: "dev@example.com")
    ctx = _RecordingCtx(tmp_path)
    machine.check(ctx, {"DEVBOX_IMAGE": "img"})
    assert "checked in" not in ctx.lines[-1]


class _NpmCtx(_RecordingCtx):
    """node 24.21.0 and an npm that reports `npm_version`; an install moves it to `installed` when it succeeds."""

    def __init__(
        self, root: pathlib.Path, npm_version: str, *, install_rc: int = 0, installed: str = ""
    ) -> None:
        super().__init__(root)
        self.env = {"NODE_VERSION_MIN": "24.11.0"}
        self.npm_version = npm_version
        self.install_rc = install_rc
        self.installed = installed
        self.calls: list[list[str]] = []
        self.errors: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def which(self, name: str) -> str | None:
        return "/usr/bin/" + name if name in {"node", "npm"} else None

    def run(
        self,
        argv: list[str],
        *,
        timeout: int | None = None,
        stdin_text: str | None = None,
    ) -> Result:
        del timeout, stdin_text
        self.calls.append(argv)
        if argv[0] == "node":
            return Result(0, "v24.21.0\n", "")
        if argv[:3] == ["npm", "install", "-g"]:
            if self.install_rc == 0 and self.installed:
                self.npm_version = self.installed
            return Result(self.install_rc, "", "EACCES" if self.install_rc else "")
        return Result(0, self.npm_version + "\n", "")


def _pin_npm(root: pathlib.Path, version: str) -> None:
    (root / ".devcontainer").mkdir()
    (root / ".devcontainer" / "toolchain.env").write_text("NPM_VERSION=%s\n" % version)


def test_check_reports_npm_drift_from_the_pin_as_pending(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    _pin_npm(tmp_path, "11.20.0")
    monkeypatch.setattr(machine.bridge, "call", lambda *_a: 0)
    monkeypatch.setattr(
        machine,
        "_devbox_facts",
        lambda *_a: {"worktree": str(tmp_path), "image": "1", "running": "1"},
    )
    monkeypatch.setattr(machine, "_port_block_row", lambda *_a: "  port block  1-10")
    monkeypatch.setattr(machine.githooks, "check_row", lambda _root: ("  git hooks   ok", 0))
    monkeypatch.setattr(machine.host, "_git_global", lambda *_a: "dev@example.com")
    ctx = _NpmCtx(tmp_path, "11.19.0")
    machine.check(ctx, {"DEVBOX_IMAGE": "img", "NODE_VERSION_MIN": "24.11.0"})
    assert "  npm         11.19.0 (pinned 11.20.0) STALE" in ctx.lines, ctx.lines
    # gh and the compiler are MISSING (2); the stale npm is one more.
    assert ctx.lines[-1].startswith("WARN 3 item(s)"), ctx.lines[-1]
    assert not [c for c in ctx.calls if c[:2] == ["npm", "install"]], ctx.calls


def test_setup_installs_the_pinned_npm_and_verifies_it(tmp_path: pathlib.Path) -> None:
    _pin_npm(tmp_path, "11.20.0")
    ctx = _NpmCtx(tmp_path, "11.19.0", installed="11.20.0")
    assert host.node_toolchain(ctx) == 0
    assert ["npm", "install", "-g", "npm@11.20.0", "--ignore-scripts"] in ctx.calls
    assert ctx.npm_version == "11.20.0"


def test_setup_leaves_an_npm_that_already_matches_the_pin(tmp_path: pathlib.Path) -> None:
    _pin_npm(tmp_path, "11.20.0")
    ctx = _NpmCtx(tmp_path, "11.20.0")
    assert host.node_toolchain(ctx) == 0
    assert not [c for c in ctx.calls if c[:2] == ["npm", "install"]], ctx.calls


def test_setup_fails_loudly_when_the_npm_install_fails(tmp_path: pathlib.Path) -> None:
    _pin_npm(tmp_path, "11.20.0")
    ctx = _NpmCtx(tmp_path, "11.19.0", install_rc=1)
    assert host.node_toolchain(ctx) == 1
    assert any("failed" in e for e in ctx.errors), ctx.errors


def test_setup_fails_loudly_when_npm_is_still_off_the_pin_after_installing(
    tmp_path: pathlib.Path,
) -> None:
    _pin_npm(tmp_path, "11.20.0")
    ctx = _NpmCtx(tmp_path, "11.19.0", installed="11.19.0")
    assert host.node_toolchain(ctx) == 1
    assert any("after installing" in e for e in ctx.errors), ctx.errors
