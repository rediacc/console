"""`rediacc_ci.proxies.unit_tests` against its bash twin
`.ci/scripts/test/proxies/proxy-unit-tests.sh`, which is TWO registered gates
over one script: `check:test-provisioning` (`package.json:393`) and
`check:test-e2e-unit` (`package.json:394`).

Sibling of `test_proxies_linux_packages.py`; see that file for why the two
invocations are compared byte for byte rather than as a finding set.

TWO CASES DRIVE THE REAL WORKSPACES, one per registered gate, so a rename on
either side reds here. The rest use a fixture root with a stub
`node_modules/.bin/vitest` (the proxy requires it to EXIST and never invokes
it) and a workspace whose script prints a canned vitest summary -- which is
the only way to drive the mixed-summary defect, since a real suite cannot be
asked to print `Tests  1 failed | 10 passed (11)` on demand.

K=5 LEDGER: `.ci/shadow/w7p6-proxy-unit-tests.observations.jsonl`. Re-recorded
2026-09-10 after the ANSI/wrong-token fix (5 rows, 5 distinct trees, 4 distinct
finding sets): a clean suite, a COLOURED clean suite (the exact regression
this fix closes), a mixed pass/fail suite, a vacuous workspace, and a missing
vitest (77).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.proxies import unit_tests

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/test/proxies/proxy-unit-tests.sh"
PORT_REL = ".ci/rediacc_ci/proxies/unit_tests.py"
PORT_MODULE = "rediacc_ci.proxies.unit_tests"
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

GREEN_RUNNER = (
    '#!/bin/bash\necho " Test Files  2 passed (2)"\necho "      Tests  11 passed (11)"\nexit 0\n'
)
MIXED_RUNNER = (
    "#!/bin/bash\n"
    'echo " Test Files  1 failed | 1 passed (2)"\n'
    'echo "      Tests  1 failed | 10 passed (11)"\n'
    "exit 1\n"
)
EMPTY_RUNNER = (
    "#!/bin/bash\n"
    'echo " Test Files  no test files found"\n'
    'echo "      Tests  0 passed (0)"\n'
    "exit 0\n"
)
SILENT_RUNNER = "#!/bin/bash\necho 'nothing a reader can count'\nexit 0\n"

pytestmark = pytest.mark.skipif(
    shutil.which("npm") is None or shutil.which("node") is None,
    reason="node/npm absent; both sides would report 77, proving nothing",
)


def build_fixture(
    tmp_path: pathlib.Path,
    *,
    runner: str = GREEN_RUNNER,
    scripts: dict[str, str] | None = None,
    ws_name: str = "@scratch/sample",
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

    (fixture / "package.json").write_text(
        json.dumps(
            {"name": "scratch-root", "private": True, "workspaces": ["packages/*"]}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    binp = fixture / "node_modules" / ".bin"
    binp.mkdir(parents=True, exist_ok=True)
    (binp / "vitest").write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
    (binp / "vitest").chmod(0o755)

    ws = fixture / "packages" / "sample"
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "package.json").write_text(
        json.dumps(
            {
                "name": ws_name,
                "version": "1.0.0",
                "scripts": scripts if scripts is not None else {"test": "./run.sh"},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (ws / "run.sh").write_text(runner, encoding="utf-8")
    (ws / "run.sh").chmod(0o755)
    return fixture


def _env(fixture: pathlib.Path, path: str | None = None) -> dict[str, str]:
    home = fixture / ".home"
    home.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": path if path is not None else os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "npm_config_cache": str(home / ".npm"),
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
        "npm",
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


def _real_tree_env(no_color: bool = True) -> dict[str, str]:
    """NO_COLOR is set DELIBERATELY, and that is a finding rather than tidiness.

    See `test_the_summary_regex_cannot_see_a_coloured_vitest_line` below: the
    twin's summary regex cannot match vitest's coloured output, so whether this
    gate is green depends on whether something in the ambient environment
    happened to turn vitest's colour off. Pinning it here makes the green case
    reproducible; the red case gets its own test rather than being inherited
    from whatever shell the suite is run from.
    """
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C",
        "LANG": "C",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if no_color:
        env["NO_COLOR"] = "1"
    return env


# ---------------------------------------------------------------------------
# The real tree, once per registered gate
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


@pytest.mark.parametrize(
    ("workspace", "key", "gate"),
    [
        ("@rediacc/provisioning", "test", "check:test-provisioning"),
        ("@rediacc/e2e-tests", "test:unit", "check:test-e2e-unit"),
    ],
)
def test_real_tree_agrees_byte_for_byte(workspace: str, key: str, gate: str) -> None:
    kwargs = {"env": _real_tree_env(), "cwd": str(ROOT), "capture_output": True, "text": True}
    old = subprocess.run(  # type: ignore[call-overload]
        ["bash", str(TWIN), workspace, key], timeout=600, check=False, **kwargs
    )
    if old.returncode == 77:
        pytest.skip(f"{gate}: the twin reports cannot-run here: {old.stderr.strip()[:200]}")
    new = subprocess.run(  # type: ignore[call-overload]
        ["python3", "-m", PORT_MODULE, workspace, key], timeout=600, check=False, **kwargs
    )
    assert old.returncode == 0, old.stderr
    assert "4 check(s) passed, 4 requirement(s) present" in old.stdout
    assert (new.returncode, new.stdout, new.stderr) == (old.returncode, old.stdout, old.stderr)


def test_no_arguments_is_the_usage_refusal(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    old, new = run_both(fixture)
    assert old.returncode == 2
    assert old.stdout == ""
    assert old.stderr == "usage: proxy-unit-tests.sh <workspace> <npm script key>\n"
    assert_same(old, new)


def test_one_argument_is_also_the_usage_refusal(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    old, new = run_both(fixture, "@scratch/sample")
    assert old.returncode == 2
    assert_same(old, new)


# ---------------------------------------------------------------------------
# Fixture cases
# ---------------------------------------------------------------------------


def test_a_green_suite_reports_its_counts(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    old, new = run_both(fixture, "@scratch/sample", "test")
    assert old.returncode == 0, old.stderr
    assert "workspace @scratch/sample resolves to packages/sample" in old.stdout
    assert "11 test(s) across 2 file(s) in @scratch/sample" in old.stdout
    assert_same(old, new)


def test_an_unresolvable_workspace_is_the_vacuous_refusal(tmp_path: pathlib.Path) -> None:
    """The word VACUOUS is load-bearing: check:ci-enumeration-vacuity keys on it."""
    fixture = build_fixture(tmp_path)
    old, new = run_both(fixture, "@scratch/nowhere", "test")
    assert old.returncode == 1
    assert "VACUOUS: workspace '@scratch/nowhere' resolves to no package.json" in old.stderr
    assert_same(old, new)


def test_a_missing_script_key_is_loud_and_never_a_77(tmp_path: pathlib.Path) -> None:
    """`npm run <missing>` exits 1 with ZERO BYTES on both streams under --silent."""
    fixture = build_fixture(tmp_path, scripts={"build": "./run.sh"})
    old, new = run_both(fixture, "@scratch/sample", "test")
    assert old.returncode == 1
    assert "script key 'test' is NOT in packages/sample/package.json" in old.stderr
    assert "do not chase the empty failure" in old.stderr
    assert_same(old, new)


def test_zero_executed_tests_is_refused(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path, runner=EMPTY_RUNNER)
    old, new = run_both(fixture, "@scratch/sample", "test")
    assert old.returncode == 1
    assert "the runner executed 0 tests" in old.stderr
    assert_same(old, new)


def test_an_unreadable_summary_is_refused(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path, runner=SILENT_RUNNER)
    old, new = run_both(fixture, "@scratch/sample", "test")
    assert old.returncode == 1
    assert "no 'Tests N passed' summary in either stream" in old.stderr
    assert_same(old, new)


def test_a_missing_vitest_is_77_not_a_verdict(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    (fixture / "node_modules" / ".bin" / "vitest").unlink()
    old, new = run_both(fixture, "@scratch/sample", "test")
    assert old.returncode == 77
    assert "node_modules/.bin/vitest does not exist" in old.stderr
    assert_same(old, new)


def test_a_missing_npm_is_77_not_a_verdict(tmp_path: pathlib.Path) -> None:
    fixture = build_fixture(tmp_path)
    old, new = run_both(fixture, "@scratch/sample", "test", path=_bin_without(tmp_path, "npm"))
    assert old.returncode == 77
    assert "npm is not on PATH" in old.stderr
    assert_same(old, new)


# ---------------------------------------------------------------------------
# A SECOND, LIVE DEFECT: the summary regex cannot see a COLOURED vitest line
# ---------------------------------------------------------------------------


def test_the_summary_regex_cannot_see_a_coloured_vitest_line() -> None:
    """FIXED 2026-09-10. Measured on the REAL workspace, GitHub-Actions-shaped.

    vitest prints its summary as

        ESC[2m      Tests ESC[22m ESC[1mESC[32m11 passed ESC[39m...ESC[90m (11)ESC[39m

    and the escapes used to sit BETWEEN the word `Tests` and the number, so
    the OLD `grep -oE 'Tests +[0-9]+ (passed|failed)'` (`:124`) matched
    nothing and the proxy false-reded a passing suite. The fix strips ANSI
    SGR sequences before matching and reads the trailing "(N)" total, so this
    now goes GREEN in exactly the environment that used to expose the bug.

    WHEN COLOUR APPEARED, measured one variable at a time on this host (now
    irrelevant to the verdict, kept as a record of the failure class):

        (bare shell)                        -> coloured
        CI=true                             -> coloured
        CI=true GITHUB_ACTIONS=true         -> coloured
        TERM=dumb                           -> plain
        NO_COLOR=1                          -> plain
        CLAUDECODE=1                        -> plain

    So the false red only ever showed up in a CI-shaped environment; this
    sandbox's own `CLAUDECODE=1` accidentally hid it. Both gates are wired as
    real steps (`ci-quality.yml:1405` and `:1409`, job `quality-packages`).
    """
    coloured = _real_tree_env(no_color=False)
    coloured["CI"] = "true"
    coloured["GITHUB_ACTIONS"] = "true"
    coloured.pop("CLAUDECODE", None)
    kwargs = {"env": coloured, "cwd": str(ROOT), "capture_output": True, "text": True}
    old = subprocess.run(  # type: ignore[call-overload]
        ["bash", str(TWIN), "@rediacc/provisioning", "test"], timeout=600, check=False, **kwargs
    )
    if old.returncode == 77:
        pytest.skip(f"the twin reports cannot-run here: {old.stderr.strip()[:200]}")
    new = subprocess.run(  # type: ignore[call-overload]
        ["python3", "-m", PORT_MODULE, "@rediacc/provisioning", "test"],
        timeout=600,
        check=False,
        **kwargs,
    )
    assert old.returncode == 0, "the twin still reds on coloured output; re-triage this"
    assert "npm run test -w @rediacc/provisioning exited 0" in old.stdout
    assert "test(s) across" in old.stdout
    assert (new.returncode, new.stdout, new.stderr) == (old.returncode, old.stdout, old.stderr)


def test_the_escapes_really_sit_between_the_word_and_the_number() -> None:
    """The mechanism, isolated from the gate, so the reason is not inferred."""
    coloured = (
        "\x1b[2m      Tests \x1b[22m \x1b[1m\x1b[32m11 passed\x1b[39m\x1b[22m\x1b[90m (11)\x1b[39m"
    )
    assert unit_tests.summary_count(coloured) == "11", coloured
    assert unit_tests.summary_count("      Tests  11 passed (11)") == "11"


# ---------------------------------------------------------------------------
# FIXED: the summary reader used to take the FAILED count on a mixed line
# ---------------------------------------------------------------------------


def test_a_partly_failing_suite_reports_the_failed_count_on_both_sides(
    tmp_path: pathlib.Path,
) -> None:
    """vitest prints `Tests  1 failed | 10 passed (11)`.

    The OLD `grep -oE 'Tests +[0-9]+ (passed|failed)'` matched the FIRST token
    on that line -- the FAILURE count -- so a run of eleven was reported as
    one. FIXED 2026-09-10: the trailing "(11)" total is read instead, which is
    right regardless of which side of "|" wins. The verdict still goes red
    here -- `npm run` exited non-zero and `:115` already recorded a FAIL --
    but the PASS line under it now names the true count.
    """
    fixture = build_fixture(tmp_path, runner=MIXED_RUNNER)
    old, new = run_both(fixture, "@scratch/sample", "test")
    assert old.returncode == 1
    assert "PASS: 11 test(s) across 1 file(s) in @scratch/sample" in old.stdout
    assert_same(old, new)


# ---------------------------------------------------------------------------
# The planted defect: this differential must be able to go RED
# ---------------------------------------------------------------------------


def test_a_planted_defect_in_the_port_is_caught(tmp_path: pathlib.Path) -> None:
    """The plant reverts the fix: it takes the FIRST number after `Tests`
    instead of the trailing `(N)` total, which is exactly the class of bug
    this pair was just fixed for.
    """
    source = (ROOT / PORT_REL).read_text(encoding="utf-8")
    planted = source.replace(
        'SUMMARY_RE = re.compile(r"^[ \\t]*Tests[ \\t].*\\(([0-9]+)\\)", re.MULTILINE)',
        'SUMMARY_RE = re.compile(r"^[ \\t]*Tests[ \\t]+([0-9]+)", re.MULTILINE)',
        1,
    )
    assert planted != source, "SUMMARY_RE moved; re-aim the plant"

    good = build_fixture(tmp_path / "good", runner=MIXED_RUNNER)
    old_g, new_g = run_both(good, "@scratch/sample", "test")
    assert_same(old_g, new_g)

    bad = build_fixture(tmp_path / "bad", runner=MIXED_RUNNER, port_source=planted)
    old_b, new_b = run_both(bad, "@scratch/sample", "test")
    assert old_b.stdout != new_b.stdout, "THE PLANT DID NOT FIRE"
    assert "PASS: 11 test(s) across 1 file(s)" in old_b.stdout
    assert "PASS: 1 test(s) across 1 file(s)" in new_b.stdout


# ---------------------------------------------------------------------------
# The pure helpers
# ---------------------------------------------------------------------------


def test_summary_count_reads_the_trailing_total_on_a_mixed_line() -> None:
    assert unit_tests.summary_count("      Tests  1 failed | 10 passed (11)") == "11"
    assert unit_tests.summary_count("      Tests  11 passed (11)") == "11"
    assert unit_tests.summary_count("      Tests  0 passed (0)") == "0"
    assert unit_tests.summary_count("nothing") == ""


def test_summary_count_takes_the_last_summary_on_the_stream() -> None:
    both = "      Tests  3 passed (3)\nmore chatter\n      Tests  7 passed (7)"
    assert unit_tests.summary_count(both) == "7"


def test_files_count_needs_the_trailing_space_the_pattern_demands() -> None:
    assert unit_tests.files_count(" Test Files  2 passed (2)") == "2"
    # No trailing space after the number: `grep -oE 'Test Files +[0-9]+ '` misses it.
    assert unit_tests.files_count(" Test Files  2") == ""
    assert unit_tests.files_count("nothing") == ""


def test_resolve_workspace_finds_the_real_workspaces_and_refuses_a_stranger() -> None:
    assert unit_tests.resolve_workspace(ROOT, "@rediacc/provisioning") == "packages/provisioning"
    assert unit_tests.resolve_workspace(ROOT, "@rediacc/e2e-tests") == "packages/e2e-tests"
    assert unit_tests.resolve_workspace(ROOT, "@rediacc/not-a-package") == ""


def test_has_script_reads_the_keys_the_two_registered_gates_depend_on() -> None:
    """A corpus-derived floor: dropping either key reds HERE, not only in CI."""
    assert unit_tests.has_script(ROOT, "packages/provisioning", "test")
    assert unit_tests.has_script(ROOT, "packages/e2e-tests", "test:unit")
    assert not unit_tests.has_script(ROOT, "packages/provisioning", "no-such-key")
