"""The install table, asserted against the tree it claims to describe.

WHAT THESE TESTS ARE FOR, beyond re-running the module's own selftest. The selftest drives `audit` over SYNTHETIC tables, which proves the assertions fire and do not fire. It cannot prove that the SHIPPED table still describes this repository, because a synthetic corpus is not this repository. The tests below close that half: they read `.devcontainer/toolchain.env`,
`toolchain.TOOL_KEYS` and the tree's own bash enumerations, and require the table to agree with all three.

THE DIVISION IS DELIBERATE. If a pin is renamed, the selftest stays green and these go red, which is the correct split of blame: the assertions still work, the data no longer matches the world.
"""

from __future__ import annotations

import re
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.core import toolchain
from rediacc_ci.setup import tools

MODULE = "rediacc_ci.setup.tools"


def run_module(*args: str, root: str | None = None) -> subprocess.CompletedProcess[str]:
    """Drive the module as a program, with stdout and stderr kept SEPARATE.

    A subprocess and not a `main([])` call, because the exit code and the stream each line lands on are part of this gate's contract and neither survives an in-process call. `PYTHONDONTWRITEBYTECODE` matches how the shadow ledger runs the Python side, so a stray `__pycache__` never makes a fixture tree dirty.
    """
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "PYTHONPATH": str(paths.from_root(".ci")),
        "PYTHONDONTWRITEBYTECODE": "1",
        "HOME": "/tmp",
    }
    if root is not None:
        env[paths.ROOT_ENV] = root
    return subprocess.run(
        [sys.executable, "-m", MODULE, *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=180,
    )


# --------------------------------------------------------------------------- The table against the tree ---------------------------------------------------------------------------


def test_the_shipped_table_audits_clean() -> None:
    assert tools.audit() == []


def test_every_pinned_tool_has_a_row() -> None:
    """The corpus-derived direction: TOOL_KEYS -> table.

    Written as a set difference rather than a loop so the failure message names every missing tool at once. A loop reports the first and hides the rest, which turns one fix into several rounds.
    """
    named = {row.name for row in tools.TOOLS}
    assert set(toolchain.TOOL_KEYS) - named == set()


def test_every_pin_key_a_row_names_exists_in_the_pins_file() -> None:
    pins = toolchain.load_pins()
    dangling = {
        row.name: row.pin_key
        for row in tools.TOOLS
        if row.pin_key is not None and row.pin_key not in pins
    }
    assert dangling == {}


def test_the_pytest_row_exists_and_is_pinned_and_repo_provisioned() -> None:
    """The row the drafted enumeration omitted. driver contract section 5d.

    Three separate assertions rather than one compound, because each failure means something different: absent is the recorded gap reopening, a wrong pin is W6 inventing a version W1 already chose, and a missing `repo` arm is a table telling a developer to `pip install` on a host with no pip.
    """
    row = next((r for r in tools.TOOLS if r.name == "pytest"), None)
    assert row is not None
    assert row.pin_key == "PYTEST_VERSION"
    assert tools.REPO_MANAGER in row.install


def test_pytest_is_pinned_in_the_real_pins_file() -> None:
    """And the pin resolves to a value, not to an empty string.

    `toolchain.pin` raises on an empty value, which is the whole reason it has no
    `default=` parameter. Calling it here is what makes this test about the TREE
    rather than about the table's spelling.
    """
    assert re.match(r"^\d+(\.\d+)*$", toolchain.pin("PYTEST_VERSION"))


def test_every_row_has_both_a_linux_and_a_darwin_answer() -> None:
    holes = {
        row.name: sorted(row.install)
        for row in tools.TOOLS
        if not any(m in row.install for m in (*tools.LINUX_MANAGERS, tools.REPO_MANAGER))
        or not any(m in row.install for m in (*tools.DARWIN_MANAGERS, tools.REPO_MANAGER))
    }
    assert holes == {}


def test_every_manager_named_is_a_known_manager() -> None:
    unknown = {
        (row.name, manager)
        for row in tools.TOOLS
        for manager in row.install
        if manager not in tools.ALL_MANAGERS
    }
    assert unknown == set()


def test_row_names_are_unique() -> None:
    names = [row.name for row in tools.TOOLS]
    assert len(names) == len(set(names))


def test_no_row_writes_a_version_down() -> None:
    """A row names a KEY; it must never carry a value.

    The check is crude on purpose and errs toward refusing: any bare dotted number in an install line or a purpose is treated as a pinned version written in the wrong place. The exception list is EXPLICIT, so a new one has to be argued rather than absorbed.
    """
    allowed = {
        "22",  # the node major, which is part of the nodesource URL and the brew formula
        "3.13",  # the brew python formula name
        "8",  # the gitleaks go module major
        "3",  # python3 / nodejs:22 style names
    }
    offenders = [
        (row.name, number)
        for row in tools.TOOLS
        for command in row.install.values()
        for number in re.findall(r"(?<![\w.])\d+(?:\.\d+)+(?![\w.])", command)
        if number not in allowed
    ]
    assert offenders == []


# --------------------------------------------------------------------------- The table against the bash enumerations it consolidates ---------------------------------------------------------------------------


def test_the_table_covers_ensure_host_tools() -> None:
    """`.ci/lib/local-common.sh:590` names four tools; all four must be rows.

    Read from the FILE rather than restated here, so a tool added to the bash loop and not to the table is a red. That is the whole point of consolidating six enumerations: the table has to be a superset, provably.
    """
    text = paths.from_root(".ci", "lib", "local-common.sh").read_text(encoding="utf-8")
    match = re.search(r"for tool in ([a-z0-9 ]+); do", text)
    assert match is not None, "ensure_host_tools' loop has moved; re-derive this test"
    named = {row.name for row in tools.TOOLS}
    assert set(match.group(1).split()) - named == set()


def test_the_table_covers_the_toolchain_acquire_arms() -> None:
    """Every tool `toolchain_acquire` has a dedicated arm for must be a row."""
    text = paths.from_root(".ci", "scripts", "lib", "toolchain.sh").read_text(encoding="utf-8")
    arms = set(re.findall(r"^\s{8}(\w+)\) _toolchain_acquire_\w+ ", text, re.MULTILINE))
    assert arms, "toolchain_acquire's case arms have moved; re-derive this test"
    assert arms - {row.name for row in tools.TOOLS} == set()


# --------------------------------------------------------------------------- The program contract: exit codes and streams ---------------------------------------------------------------------------


def test_selftest_passes_and_prints_controls() -> None:
    """Exit 0 with ZERO control lines is a failure, so both are asserted.

    The count is compared against the module's own case list rather than a literal, for the reason the driver contract gives in section 6: a hand-typed count is re-typed the day a control is added, and a re-typed count is one nobody re-derives.
    """
    result = run_module("--selftest")
    assert result.returncode == 0
    passed = [line for line in result.stdout.splitlines() if line.startswith("ok    ")]
    assert len(passed) >= len(tools.TOOLS) // 2
    assert result.stdout.rstrip().endswith("control(s) passed")


def test_the_audit_prints_its_shape_on_success() -> None:
    """A green must carry the numbers a reader can watch collapse."""
    result = run_module()
    assert result.returncode == 0
    assert result.stderr == ""
    assert "%d row(s)" % len(tools.TOOLS) in result.stdout
    assert "pin(s) in .devcontainer/toolchain.env" in result.stdout


def test_an_unresolvable_root_is_77_and_never_a_verdict() -> None:
    """77 is CANNOT-RUN. It must not be 0 and it must not be 1."""
    result = run_module(root="/no/such/place")
    assert result.returncode == tools.EXIT_CANNOT_RUN
    assert result.stdout == ""
    assert "CANNOT RUN" in result.stderr


def test_install_plan_refuses_an_unknown_manager() -> None:
    result = run_module("--install-plan", "yum")
    assert result.returncode == tools.EXIT_FINDINGS
    assert "not a known manager" in result.stderr


def test_report_never_gates() -> None:
    """`--report` answers a question a developer asks before setup, so it is 0.

    Pinned by a test because the temptation to make it red when something is missing is real, and yielding to it would make the one command a person runs on a fresh machine look like a failure.
    """
    result = run_module("--report")
    assert result.returncode == 0
    assert "row(s)," in result.stdout


# --------------------------------------------------------------------------- The audit's own both-direction behaviour, driven from pytest ---------------------------------------------------------------------------


def _minimal(**kwargs: object) -> tools.Tool:
    base: dict[str, object] = {
        "name": "widget",
        "purpose": "a purpose",
        "pin_key": None,
        "install": {"apt": "a", "brew": "b"},
        "provenance": "x.sh:1",
    }
    base.update(kwargs)
    return tools.Tool(**base)  # type: ignore[arg-type]


FAKE_PINS = {"WIDGET_VERSION": "1.0", "PYTEST_VERSION": "9.1.1"}
FAKE_KEYS = {"widget": "WIDGET_VERSION", "pytest": "PYTEST_VERSION"}
GOOD_PYTEST = _minimal(
    name="pytest",
    pin_key="PYTEST_VERSION",
    install={"apt": "a", "brew": "b", "repo": "c"},
)
GOOD_WIDGET = _minimal(name="widget", pin_key="WIDGET_VERSION")


def test_an_empty_table_is_a_finding_never_a_pass() -> None:
    findings = tools.audit((), pins=FAKE_PINS, tool_keys=FAKE_KEYS)
    assert findings
    assert findings[0].startswith("A0.")


def test_an_empty_pin_corpus_is_a_finding_never_a_pass() -> None:
    findings = tools.audit((GOOD_WIDGET, GOOD_PYTEST), pins={}, tool_keys=FAKE_KEYS)
    assert findings
    assert findings[0].startswith("A0.")


def test_an_empty_tool_key_corpus_is_a_finding_never_a_pass() -> None:
    findings = tools.audit((GOOD_WIDGET, GOOD_PYTEST), pins=FAKE_PINS, tool_keys={})
    assert findings
    assert findings[0].startswith("A0.")


@pytest.mark.parametrize(
    ("label", "table", "want"),
    [
        ("clean", (GOOD_WIDGET, GOOD_PYTEST), None),
        ("duplicate name", (GOOD_WIDGET, GOOD_WIDGET, GOOD_PYTEST), "A1."),
        ("pinned tool with no row", (GOOD_PYTEST,), "A2."),
        (
            "pin_key disagrees with TOOL_KEYS",
            (_minimal(name="widget", pin_key="PYTEST_VERSION"), GOOD_PYTEST),
            "A2.",
        ),
        (
            "no darwin answer",
            (_minimal(name="widget", pin_key="WIDGET_VERSION", install={"apt": "a"}), GOOD_PYTEST),
            "A4.",
        ),
        (
            "no linux answer",
            (_minimal(name="widget", pin_key="WIDGET_VERSION", install={"brew": "b"}), GOOD_PYTEST),
            "A5.",
        ),
        ("pytest row absent", (GOOD_WIDGET,), "A6."),
        (
            "pytest row without a repo arm",
            (
                GOOD_WIDGET,
                _minimal(
                    name="pytest", pin_key="PYTEST_VERSION", install={"apt": "a", "brew": "b"}
                ),
            ),
            "A6.",
        ),
        (
            "no provenance",
            (_minimal(name="widget", pin_key="WIDGET_VERSION", provenance=" "), GOOD_PYTEST),
            "A7.",
        ),
    ],
)
def test_audit_fires_in_both_directions(
    label: str, table: tuple[tools.Tool, ...], want: str | None
) -> None:
    findings = tools.audit(table, pins=FAKE_PINS, tool_keys=FAKE_KEYS)
    if want is None:
        assert findings == [], label
    else:
        assert any(f.startswith(want) for f in findings), (label, findings)


def test_detect_manager_returns_a_known_name_or_nothing() -> None:
    assert tools.detect_manager() in (*tools.ALL_MANAGERS, "")


def test_probe_version_returns_none_rather_than_an_empty_string() -> None:
    """None, never "". Two empty strings compare equal and would read as agreement.

    The same argument `normalize_version` makes for raising instead of yielding "": vacuity inside the very comparison the value exists for.
    """
    absent = tools.Tool(
        name="definitely-not-a-real-binary-93bf",
        purpose="p",
        pin_key=None,
        install={"apt": "a", "brew": "b"},
        provenance="x:1",
        probe=("definitely-not-a-real-binary-93bf", "--version"),
    )
    assert tools.probe_version(absent) is None
    assert tools.present(absent) is None
