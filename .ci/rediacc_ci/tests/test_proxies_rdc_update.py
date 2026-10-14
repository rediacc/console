"""`rediacc_ci.proxies.rdc_update` against its bash twin `.ci/scripts/test/proxies/proxy-rdc-update.sh` (gate `check:ci-proxy-rdc-update`, `package.json:386`).

Sibling of `test_proxies_linux_packages.py`; see that file for why the two invocations are compared byte for byte rather than as a finding set.

ONE CASE DRIVES THE REAL SUBJECT (five scenarios, a Python fixture server per scenario, ~7 s on this host). The rest use a stub subject with the same dispatch SHAPE, which is the only way to drive the drift and zero-scenario branches: the real dispatch cannot be asked to grow an eighth arm.

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
from rediacc_ci.tests import differential as diff

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

# A stub SUBJECT with the real one's SCENARIOS-tuple SHAPE: the tuple closed by a `)` in column 0, which is what the proxy reads. `%s` is the stream each scenario writes its `PASS:` line to.
_ARMS = "\n".join(f'    "{name}",' for name in SCENARIOS)
STUB_SUBJECT = f"""import sys

SCENARIOS = (
{_ARMS}
)
for s in sys.argv[1:]:
    if s not in SCENARIOS:
        print("unknown scenario " + s, file=sys.stderr)
        raise SystemExit(2)
    print("PASS: " + s, file=%s)
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
        if not (ROOT / rel).exists():
            continue  # the retired twin and its library: only a recording run copies them
        dst.write_bytes((ROOT / rel).read_bytes())
    if (fixture / TWIN_REL).exists():
        (fixture / TWIN_REL).chmod(0o755)
    if port_source is not None:
        (fixture / PORT_REL).write_text(port_source, encoding="utf-8")

    subj = fixture / rdc_update.SUBJECT_REL
    subj.parent.mkdir(parents=True, exist_ok=True)
    (subj.parent / "__init__.py").write_text("", encoding="utf-8")
    subj.write_text(
        subject if subject is not None else STUB_SUBJECT % ("sys.stdout",), encoding="utf-8"
    )

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
    kwargs: diff.RunKwargs = {"env": env, "cwd": str(fixture), "capture_output": True, "text": True}

    def port_side() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", "-m", PORT_MODULE, *args], timeout=300, check=False, **kwargs
        )

    def port_streams() -> tuple[int, str, str]:
        proc = port_side()
        return proc.returncode, proc.stdout, proc.stderr

    def retired_bash() -> tuple[int, str, str]:
        raise RuntimeError("proxy-rdc-update.sh is retired; only its golden answers")

    # The bash proxy is retired, so its answer comes from the golden. A case whose output names the subject was re-recorded from the port after the subject moved to the Python module (Rule T, PLAN-retire-bash-oracles).
    rc, out, err = diff.twin_call(
        TWIN_REL,
        [repr(["bash", str(fixture / TWIN_REL), *args])],
        retired_bash,
        port=port_streams,
        work=(fixture.parent,),
    )
    old = subprocess.CompletedProcess([], rc, out, err)
    return old, port_side()


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


# --------------------------------------------------------------------------- The real tree ---------------------------------------------------------------------------


def test_selftest_is_byte_identical() -> None:
    kwargs: diff.RunKwargs = {
        "env": _real_tree_env(),
        "cwd": str(ROOT),
        "capture_output": True,
        "text": True,
    }
    old = diff.twin_result(
        TWIN_REL,
        [repr(["bash", str(TWIN), "--selftest"])],
        lambda: subprocess.run(
            ["bash", str(TWIN), "--selftest"], timeout=180, check=False, **kwargs
        ),
        work=(),
    )
    new = subprocess.run(
        ["python3", "-m", PORT_MODULE, "--selftest"], timeout=180, check=False, **kwargs
    )
    assert old.returncode == 0, old.stderr
    assert "proxy-lib selftest: 4 case(s) passed" in old.stdout
    assert (new.returncode, new.stdout, new.stderr) == (old.returncode, old.stdout, old.stderr)


def test_real_tree_passes_through_the_port() -> None:
    """The only case that boots the real fixture server. The bash twin it was compared with is retired (PLAN-retire-bash-oracles B3)."""
    kwargs: diff.RunKwargs = {
        "env": _real_tree_env(),
        "cwd": str(ROOT),
        "capture_output": True,
        "text": True,
    }
    new = subprocess.run(["python3", "-m", PORT_MODULE], timeout=600, check=False, **kwargs)
    if new.returncode == 77:
        # Cannot-run is NOT a verdict, and 77 == 77 would prove nothing here.
        pytest.skip(f"the port reports cannot-run on this host: {new.stderr.strip()[:200]}")
    assert new.returncode == 0, new.stderr
    assert "3 check(s) passed, 5 requirement(s) present" in new.stdout
    assert "NOT EXERCISED HERE: happy rollback" in new.stdout


# --------------------------------------------------------------------------- Fixture cases ---------------------------------------------------------------------------


def test_the_stub_dispatch_is_read_and_the_partition_holds(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    old, new = run_both(fixture)
    assert old.returncode == 0, old.stderr
    assert "partition covers all 7 scenarios the subject declares" in old.stdout
    assert "one PASS: line per scenario (3 of 3)" in old.stdout
    assert_same(old, new)


def test_the_banner_names_the_python_subject_not_the_retired_bash_one(
    tmp_path: pathlib.Path,
) -> None:
    """RULE T: the proxy drives `rediacc_ci.testrun.rdc_update`, the module CI runs. The retired bash proxy announced `test-rdc-update.sh`, a file that no longer exists."""
    fixture = build_fixture(tmp_path)
    _old, new = run_both(fixture)
    assert (
        "proxy rdc-update: local stand-in for .ci/rediacc_ci/testrun/rdc_update.py\n" in new.stdout
    )
    assert "test-rdc-update.sh" not in new.stdout + new.stderr


def test_scenario_drift_message_keeps_the_trailing_space(tmp_path: pathlib.Path) -> None:
    """`:85` pipes through `tr '\\n' ' '`, and `$( )` strips only NEWLINES.

    So the trailing space `tr` produced survives into the message. A port written with `" ".join(...)` would differ by two bytes on the one path nobody runs, which is exactly the kind of divergence a differential is for.
    """
    subject = STUB_SUBJECT % ("sys.stdout",)
    subject = subject.replace(
        '    "check-only",',
        '    "extra",\n    "check-only",',
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
    subject = STUB_SUBJECT % ("sys.stdout",)
    subject = subject.replace("\n)", "\n    )")
    fixture = build_fixture(tmp_path, subject=subject)
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "read ZERO scenarios out of the subject's SCENARIOS tuple" in old.stderr
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
    subject = (STUB_SUBJECT % ("sys.stdout",)).replace('print("PASS: " + s', 'print("ran " + s')
    fixture = build_fixture(tmp_path, subject=subject)
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "the subject emitted 0 PASS: line(s) for 3 scenario(s)" in old.stderr
    assert_same(old, new)


def test_pass_lines_on_stderr_are_not_counted_on_either_side(tmp_path: pathlib.Path) -> None:
    """`:119` reads the STDOUT FILE alone, unlike the linux-packages proxy.

    A subject that moved its `PASS:` lines to stderr therefore reports "at least one asserted nothing" while every scenario really passed. That is the RIGHT direction to fail -- loud, red, and it names the shape -- so it is reproduced as written rather than widened to both streams.
    """
    fixture = build_fixture(tmp_path, subject=STUB_SUBJECT % ("sys.stderr",))
    old, new = run_both(fixture)
    assert old.returncode == 1
    assert "3 scenario(s) passed" in old.stdout
    assert "the subject emitted 0 PASS: line(s) for 3 scenario(s)" in old.stderr
    assert_same(old, new)


# --------------------------------------------------------------------------- The planted defect: this differential must be able to go RED ---------------------------------------------------------------------------


def test_a_planted_defect_in_the_port_is_caught(tmp_path: pathlib.Path) -> None:
    """The plant drops the trailing space from `joined`, two bytes per list."""
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    planted = source.replace('return "".join(f"{n} " for n in names)', 'return " ".join(names)', 1)
    assert planted != source, "`joined` moved; re-aim the plant"

    subject = (STUB_SUBJECT % ("sys.stdout",)).replace(
        '    "check-only",',
        '    "extra",\n    "check-only",',
        1,
    )
    good = build_fixture(tmp_path / "good", subject=subject)
    old_g, new_g = run_both(good)
    assert_same(old_g, new_g)

    bad = build_fixture(tmp_path / "bad", subject=subject, port_source=planted)
    # The expected answer is the unplanted one, already read above for the same subject and arguments.
    old_b = old_g
    new_b = subprocess.run(
        ["python3", "-m", PORT_MODULE],
        timeout=300,
        check=False,
        env=_env(bad),
        cwd=str(bad),
        capture_output=True,
        text=True,
    )
    assert old_b.stderr != new_b.stderr, "THE PLANT DID NOT FIRE"
    assert "sha256-mismatch ] but" in old_b.stderr
    assert "sha256-mismatch] but" in new_b.stderr


# --------------------------------------------------------------------------- The pure helpers ---------------------------------------------------------------------------


def test_parse_declared_reads_the_scenarios_tuple_closed_in_column_zero() -> None:
    assert rdc_update.parse_declared('SCENARIOS = (\n    "b",\n    "a",\n)\n') == ["a", "b"]
    # An indented closer or a renamed tuple matches nothing, which the proxy turns into a loud refusal.
    assert rdc_update.parse_declared('SCENARIOS = (\n    "a",\n    )\n') == []
    assert rdc_update.parse_declared('NAMES = (\n    "a",\n)\n') == []
    assert rdc_update.parse_declared("") == []


def test_parse_declared_ignores_a_name_outside_the_character_class() -> None:
    """`[a-z0-9-]+` only: an underscore or a capital is simply not a match."""
    assert rdc_update.parse_declared('SCENARIOS = (\n    "a_b",\n)\n') == []
    assert rdc_update.parse_declared('SCENARIOS = (\n    "Ab",\n)\n') == []


def test_joined_keeps_the_trailing_space() -> None:
    assert rdc_update.joined(["a", "b"]) == "a b "
    assert rdc_update.joined([]) == ""


def test_the_real_subject_still_declares_exactly_the_partitioned_seven() -> None:
    """A corpus-derived floor, so a scenario added upstream reds HERE too."""
    subject = (ROOT / rdc_update.SUBJECT_REL).read_text(encoding="utf-8")
    assert rdc_update.parse_declared(subject) == sorted(rdc_update.SEA_FREE + rdc_update.SEA_ONLY)
