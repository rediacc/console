"""`rediacc_ci.proxies.rdc_update` against its bash twin
`.ci/scripts/test/proxies/proxy-rdc-update.sh` (gate `check:ci-proxy-rdc-update`,
`package.json:386`).

Sibling of `test_proxies_linux_packages.py`; see that file for why the two
invocations are compared byte for byte rather than as a finding set.

ONE CASE DRIVES THE REAL SUBJECT (five scenarios, a Python fixture server per
scenario, ~7 s on this host). The rest use a stub subject with the same
dispatch SHAPE, which is the only way to drive the drift and zero-scenario
branches: the real dispatch cannot be asked to grow an eighth arm.

K=5 LEDGER: `.ci/shadow/w7p6-proxy-rdc-update.observations.jsonl` (5 rows, 5
distinct trees, 5 distinct finding sets).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.proxies import rdc_update

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/test/proxies/proxy-rdc-update.sh"
PORT_REL = ".ci/rediacc_ci/proxies/rdc_update.py"
PORT_MODULE = "rediacc_ci.proxies.rdc_update"
TWIN = ROOT / TWIN_REL

FIXTURE_FILES = (
    TWIN_REL,
    ".ci/scripts/test/proxies/proxy-lib.sh",
    ".ci/rediacc_ci/__init__.py",
    ".ci/rediacc_ci/core/__init__.py",
    ".ci/rediacc_ci/core/proxyx.py",
    ".ci/rediacc_ci/proxies/__init__.py",
    PORT_REL,
)

SCENARIOS = (
    "check-only",
    "sha256-mismatch",
    "rollback-empty",
    "channel-switch",
    "reinstall",
    "happy",
    "rollback",
)

# A stub SUBJECT with the real one's dispatch SHAPE: `        <name>) scenario_`
# at EXACTLY eight spaces, which is what `:73`'s anchored grep reads. `%s` is
# the stream each scenario writes its `PASS:` line to.
_ARMS = "\n".join(f"        {name}) scenario_run {name} ;;" for name in SCENARIOS)
STUB_SUBJECT = f"""#!/usr/bin/env bash
set -uo pipefail
scenario_run() {{
    echo "PASS: $1" %s
}}
for s in "$@"; do
    case "$s" in
{_ARMS}
        *) echo "unknown scenario $s" >&2 ; exit 2 ;;
    esac
done
"""


def build_fixture(
    tmp_path: pathlib.Path,
    *,
    subject: str | None = None,
    install_sh: bool = True,
    port_source: str | None = None,
) -> pathlib.Path:
    fixture = tmp_path / "fixture"
    for rel in FIXTURE_FILES:
        dst = fixture / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((ROOT / rel).read_bytes())
    (fixture / TWIN_REL).chmod(0o755)
    if port_source is not None:
        (fixture / PORT_REL).write_text(port_source, encoding="utf-8")

    subj = fixture / ".ci" / "scripts" / "test" / "test-rdc-update.sh"
    subj.parent.mkdir(parents=True, exist_ok=True)
    subj.write_text(subject if subject is not None else STUB_SUBJECT % ("",), encoding="utf-8")
    subj.chmod(0o755)

    binary = fixture / "packages" / "cli" / "dist" / "cli-bundle.cjs"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)

    if install_sh:
        inst = fixture / "packages" / "www" / "public" / "install.sh"
        inst.parent.mkdir(parents=True, exist_ok=True)
        inst.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
        inst.chmod(0o755)
    return fixture


def _env(fixture: pathlib.Path, path: str | None = None) -> dict[str, str]:
    return {
        "PATH": path if path is not None else os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(fixture / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def run_both(
    fixture: pathlib.Path, *args: str, path: str | None = None
) -> tuple[subprocess.CompletedProcess[str], subprocess.CompletedProcess[str]]:
    env = _env(fixture, path)
    kwargs = {"env": env, "cwd": str(fixture), "capture_output": True, "text": True}
    old = subprocess.run(  # type: ignore[call-overload]
        ["bash", str(fixture / TWIN_REL), *args], timeout=300, check=False, **kwargs
    )
    new = subprocess.run(  # type: ignore[call-overload]
        ["python3", "-m", PORT_MODULE, *args], timeout=300, check=False, **kwargs
    )
    return old, new


def assert_same(
    old: subprocess.CompletedProcess[str], new: subprocess.CompletedProcess[str]
) -> None:
    assert new.returncode == old.returncode, "exit: twin %s, port %s (%r)" % (
        old.returncode,
        new.returncode,
        old.stderr,
    )
    assert new.stdout == old.stdout
    assert new.stderr == old.stderr


def _bin_without(tmp_path: pathlib.Path, drop: str) -> str:
    d = tmp_path / f"bin-no-{drop}"
    d.mkdir(exist_ok=True)
    for tool in (
        "bash",
        "sh",
        "env",
        "python3",
        "node",
        "sed",
        "cat",
        "mktemp",
        "rm",
        "mkdir",
        "chmod",
        "dirname",
        "grep",
        "head",
        "tail",
        "printf",
        "cut",
        "tr",
        "sort",
        "wc",
    ):
        if tool == drop:
            continue
        src = shutil.which(tool)
        if src and not (d / tool).exists():
            (d / tool).symlink_to(src)
    return str(d)


def _real_tree_env() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


# ---------------------------------------------------------------------------
# The real tree
# ---------------------------------------------------------------------------


def test_selftest_is_byte_identical() -> None:
    kwargs = {"env": _real_tree_env(), "cwd": str(ROOT), "capture_output": True, "text": True}
    old = subprocess.run(  # type: ignore[call-overload]
        ["bash", str(TWIN), "--selftest"], timeout=180, check=False, **kwargs
    )
    new = subprocess.run(  # type: ignore[call-overload]
        ["python3", "-m", PORT_MODULE, "--selftest"], timeout=180, check=False, **kwargs
    )
    assert old.returncode == 0, old.stderr
    assert "proxy-lib selftest: 4 case(s) passed" in old.stdout
    assert (new.returncode, new.stdout, new.stderr) == (old.returncode, old.stdout, old.stderr)


def test_real_tree_agrees_byte_for_byte() -> None:
    """The only case that boots the real fixture server, and it boots it twice."""
    kwargs = {"env": _real_tree_env(), "cwd": str(ROOT), "capture_output": True, "text": True}
    old = subprocess.run(  # type: ignore[call-overload]
        ["bash", str(TWIN)], timeout=600, check=False, **kwargs
    )
    if old.returncode == 77:
        # Cannot-run is NOT a verdict, and 77 == 77 would prove nothing here.
        pytest.skip(f"the twin reports cannot-run on this host: {old.stderr.strip()[:200]}")
    new = subprocess.run(  # type: ignore[call-overload]
        ["python3", "-m", PORT_MODULE], timeout=600, check=False, **kwargs
    )
    assert old.returncode == 0, old.stderr
    assert "3 check(s) passed, 5 requirement(s) present" in old.stdout
    assert "NOT EXERCISED HERE: happy rollback" in old.stdout
    assert (new.returncode, new.stdout, new.stderr) == (old.returncode, old.stdout, old.stderr)


# ---------------------------------------------------------------------------
# Fixture cases
# ---------------------------------------------------------------------------


def test_the_stub_dispatch_is_read_and_the_partition_holds(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    old, new = run_both(fixture)
    assert old.returncode == 0, old.stderr
    assert "partition covers all 7 scenarios the subject declares" in old.stdout
    assert "one PASS: line per scenario (5 of 5)" in old.stdout
    assert_same(old, new)


def test_scenario_drift_message_keeps_the_trailing_space(tmp_path: pathlib.Path) -> None:
    """`:85` pipes through `tr '\\n' ' '`, and `$( )` strips only NEWLINES.

    So the trailing space `tr` produced survives into the message. A port
    written with `" ".join(...)` would differ by two bytes on the one path
    nobody runs, which is exactly the kind of divergence a differential is for.
    """
    subject = STUB_SUBJECT % ("",)
    subject = subject.replace(
        "        check-only) scenario_run check-only ;;",
        "        extra) scenario_run extra ;;\n        check-only) scenario_run check-only ;;",
        1,
    )
    fixture = build_fixture(tmp_path, subject=subject)
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert (
        "scenario drift: the subject declares [channel-switch check-only extra happy "
        "reinstall rollback rollback-empty sha256-mismatch ] but this proxy partitions "
        "[channel-switch check-only happy reinstall rollback rollback-empty "
        "sha256-mismatch ]" in old.stderr
    )
    assert_same(old, new)


def test_a_reindented_dispatch_reads_zero_scenarios_and_refuses(tmp_path: pathlib.Path) -> None:
    subject = STUB_SUBJECT % ("",)
    subject = subject.replace("\n        ", "\n    ")
    fixture = build_fixture(tmp_path, subject=subject)
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "read ZERO scenarios out of the subject's dispatch" in old.stderr
    assert "would then be vacuous" in old.stderr
    assert_same(old, new)


def test_a_missing_installer_is_77_not_a_verdict(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path, install_sh=False)
    old, new = run_both(fixture)
    assert old.returncode == 77
    assert "CANNOT RUN" in old.stderr
    assert "install.sh does not exist" in old.stderr
    assert_same(old, new)


def test_a_missing_node_is_77_not_a_verdict(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    old, new = run_both(fixture, path=_bin_without(tmp_path, "node"))
    assert old.returncode == 77
    assert "node is not on PATH" in old.stderr
    assert_same(old, new)


def test_a_scenario_that_asserts_nothing_is_reported(tmp_path: pathlib.Path) -> None:
    """One `PASS:` line per scenario is the subject's contract (`:117-124`)."""
    subject = (STUB_SUBJECT % ("",)).replace('echo "PASS: $1"', 'echo "ran $1"')
    fixture = build_fixture(tmp_path, subject=subject)
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "the subject emitted 0 PASS: line(s) for 5 scenario(s)" in old.stderr
    assert_same(old, new)


def test_pass_lines_on_stderr_are_not_counted_on_either_side(tmp_path: pathlib.Path) -> None:
    """`:119` reads the STDOUT FILE alone, unlike the linux-packages proxy.

    A subject that moved its `PASS:` lines to stderr therefore reports "at
    least one asserted nothing" while every scenario really passed. That is
    the RIGHT direction to fail -- loud, red, and it names the shape -- so it
    is reproduced as written rather than widened to both streams.
    """
    fixture = build_fixture(tmp_path, subject=STUB_SUBJECT % (">&2",))
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "5 scenario(s) passed" in old.stdout
    assert "the subject emitted 0 PASS: line(s) for 5 scenario(s)" in old.stderr
    assert_same(old, new)


# ---------------------------------------------------------------------------
# The planted defect: this differential must be able to go RED
# ---------------------------------------------------------------------------


def test_a_planted_defect_in_the_port_is_caught(tmp_path: pathlib.Path) -> None:
    """The plant drops the trailing space from `joined`, two bytes per list."""
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    planted = source.replace('return "".join(f"{n} " for n in names)', 'return " ".join(names)', 1)
    assert planted != source, "`joined` moved; re-aim the plant"

    subject = (STUB_SUBJECT % ("",)).replace(
        "        check-only) scenario_run check-only ;;",
        "        extra) scenario_run extra ;;\n        check-only) scenario_run check-only ;;",
        1,
    )
    good = build_fixture(tmp_path / "good", subject=subject)
    old_g, new_g = run_both(good)
    assert_same(old_g, new_g)

    bad = build_fixture(tmp_path / "bad", subject=subject, port_source=planted)
    old_b, new_b = run_both(bad)
    assert old_b.stderr != new_b.stderr, "THE PLANT DID NOT FIRE"
    assert "sha256-mismatch ] but" in old_b.stderr
    assert "sha256-mismatch] but" in new_b.stderr


# ---------------------------------------------------------------------------
# The pure helpers
# ---------------------------------------------------------------------------


def test_parse_declared_is_anchored_at_eight_spaces() -> None:
    assert rdc_update.parse_declared("        b) scenario_b\n        a) scenario_a\n") == ["a", "b"]
    assert rdc_update.parse_declared("    a) scenario_a\n") == []
    assert rdc_update.parse_declared("         a) scenario_a\n") == []
    assert rdc_update.parse_declared("") == []


def test_parse_declared_ignores_a_name_outside_the_character_class() -> None:
    """`[a-z0-9-]+` only: an underscore or a capital is simply not a match."""
    assert rdc_update.parse_declared("        a_b) scenario_a_b\n") == []
    assert rdc_update.parse_declared("        Ab) scenario_ab\n") == []


def test_joined_keeps_the_trailing_space() -> None:
    assert rdc_update.joined(["a", "b"]) == "a b "
    assert rdc_update.joined([]) == ""


def test_the_real_subject_still_declares_exactly_the_partitioned_seven() -> None:
    """A corpus-derived floor, so a scenario added upstream reds HERE too."""
    subject = (ROOT / ".ci/scripts/test/test-rdc-update.sh").read_text(encoding="utf-8")
    assert rdc_update.parse_declared(subject) == sorted(rdc_update.SEA_FREE + rdc_update.SEA_ONLY)
