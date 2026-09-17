"""`rediacc_ci.quality.no_otlp_creds` against its bash twin.

A bash child runs the REAL `.ci/scripts/quality/check-no-otlp-creds.sh` over a fixture with stdout and stderr captured SEPARATELY, and its bytes are compared against the port's. THE TWIN HAS NO ENVIRONMENT SEAM -- it resolves the repo root
from `get_repo_root`, i.e. from `.ci/scripts/lib/common.sh`'s own location -- so
unlike `test_quality_staging_tag_guard.py` the twin has to be COPIED into the fixture. That is the same recipe the committed ledger uses (`.ci/shadow/w7p2-otlp-creds.observations.jsonl`), and it is what makes the tree id in those rows a claim about both implementations rather than about one.

BOTH STREAMS ARE COMPARED BYTE FOR BYTE HERE. This gate writes everything through
`log_*`, so every line is on stderr and stdout is empty; asserting on both is what
would catch a stream swap, which is the 2026-09-06 incident `rediacc_ci.tests.differential` was shaped by.

THE FIXTURES ARE ALL NON-CLEAN ON PURPOSE. A clean tree makes this gate print `✓` lines only, and two implementations that both print nothing have proved nothing about each other. Every case below produces at least one warning or one error on both sides.
"""

import os
import pathlib
import shutil

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import no_otlp_creds as gate
from rediacc_ci.tests import differential as diff

TWIN = ".ci/scripts/quality/check-no-otlp-creds.sh"
MODULE = "no_otlp_creds"

LEAK = 'const h = "Basic QUJDREVGR0hJSktMTU5PUFFSU1RVVg==";\n'
RUNTIME = "const h = `Basic ${this.authToken}`;\n"


def build(tmp_path: pathlib.Path, files: dict[str, str]) -> pathlib.Path:
    """A specimen repo holding BOTH implementations plus `files`.

    The bash library goes in whole because the twin sources `common.sh`; the
    Python package goes in by named module rather than wholesale so a sibling agent's half-written file cannot change what this test runs.
    """
    src = pathlib.Path(diff.repo())
    root = tmp_path / "fixture"
    (root / ".ci" / "scripts" / "quality").mkdir(parents=True)
    (root / ".ci" / "rediacc_ci" / "quality").mkdir(parents=True)
    shutil.copytree(src / ".ci" / "scripts" / "lib", root / ".ci" / "scripts" / "lib")
    shutil.copy2(src / TWIN, root / TWIN)
    for name in ("__init__.py", "log.py", "paths.py", "controls.py"):
        shutil.copy2(src / ".ci" / "rediacc_ci" / name, root / ".ci" / "rediacc_ci" / name)
    for name in ("__init__.py", "%s.py" % MODULE):
        shutil.copy2(
            src / ".ci" / "rediacc_ci" / "quality" / name,
            root / ".ci" / "rediacc_ci" / "quality" / name,
        )
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def run_both(root: pathlib.Path) -> tuple[tuple[int, str, str], tuple[int, str, str]]:
    env = diff.env_for(PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1")
    old = diff.bash_streams("bash %s" % TWIN, env=env, cwd=str(root))
    new = diff.bash_streams("python3 -m rediacc_ci.quality.%s" % MODULE, env=env, cwd=str(root))
    return old, new


@pytest.mark.parametrize(
    ("files", "want_exit", "must_contain"),
    [
        pytest.param({}, 0, "skipping renet checks", id="nothing-built-is-two-warnings"),
        pytest.param(
            {"packages/cli/dist/cli-bundle.cjs": RUNTIME},
            0,
            "no literal credentials",
            id="a-runtime-header-is-not-a-leak",
        ),
        pytest.param(
            {"packages/cli/dist/cli-bundle.cjs": LEAK},
            1,
            "literal 'Basic <token>' header",
            id="a-baked-header-is-a-leak",
        ),
        pytest.param(
            {"private/renet/bin/renet": "not a go binary\n"},
            1,
            "'go version -m' failed",
            id="an-unreadable-binary-is-an-ERROR-not-a-pass",
        ),
        pytest.param(
            {
                "private/renet/bin/renet": "not a go binary\n",
                "private/bin/renet-linux-amd64": "nor is this\n",
            },
            1,
            "cannot inspect for baked credentials",
            id="two-unreadable-binaries-are-two-errors",
        ),
    ],
)
def test_port_and_twin_agree_byte_for_byte(
    tmp_path: pathlib.Path, files: dict[str, str], want_exit: int, must_contain: str
) -> None:
    root = build(tmp_path, files)
    (old_exit, old_out, old_err), (new_exit, new_out, new_err) = run_both(root)
    assert old_exit == want_exit
    assert new_exit == old_exit
    assert new_out == old_out
    assert new_err == old_err
    assert must_contain in old_err
    # ANTI-VACUITY FOR THE TEST ITSELF: two silent implementations agree about nothing, so every case must have produced output on the compared stream.
    assert old_err.strip() != ""


def test_the_failing_and_passing_cases_do_not_look_alike(tmp_path: pathlib.Path) -> None:
    """A differential that cannot tell red from green is not a differential."""
    clean = run_both(build(tmp_path / "a", {"packages/cli/dist/cli-bundle.cjs": RUNTIME}))
    leak = run_both(build(tmp_path / "b", {"packages/cli/dist/cli-bundle.cjs": LEAK}))
    assert clean[0][2] != leak[0][2]
    assert clean[0][0] == 0
    assert leak[0][0] == 1


def test_the_twin_prints_a_doubled_glyph_and_the_port_reproduces_it(
    tmp_path: pathlib.Path,
) -> None:
    """`log_info "✓ ..."` prefixes a SECOND ✓. A twin defect, carried not fixed.

    Pinned so nobody "tidies" the port into printing one glyph, which would be a compared-line difference against the twin for a purely cosmetic gain.
    """
    root = build(tmp_path, {"packages/cli/dist/cli-bundle.cjs": RUNTIME})
    (_, _, old_err), (_, _, new_err) = run_both(root)
    assert "✓ ✓ CLI bundle: no literal credentials" in old_err
    assert "✓ ✓ CLI bundle: no literal credentials" in new_err


# --------------------------------------------------------------------------- The decision functions, driven directly. Both directions for every rule. ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("buildinfo", "count"),
    [
        pytest.param("\tpath\tgithub.com/rediacc/renet\n", 0, id="ordinary"),
        pytest.param("-X telemetry.otlpUser=a\n", 1, id="user"),
        pytest.param("-X telemetry.otlpPass=b\n", 1, id="pass"),
        pytest.param("telemetry.otlpUser telemetry.otlpPass\n", 2, id="both"),
        pytest.param("telemetryXotlpUser\n", 0, id="the-dot-is-escaped"),
        pytest.param("", 0, id="empty"),
    ],
)
def test_buildinfo_findings(buildinfo: str, count: int) -> None:
    assert len(gate.buildinfo_findings("b", buildinfo)) == count


@pytest.mark.parametrize(
    ("text", "fires"),
    [
        pytest.param("otlpUser\nQUJDREVGR0hJSktMTU5PUFFSUw==\n", True, id="after"),
        pytest.param("QUJDREVGR0hJSktMTU5PUFFSUw==\notlpPass\n", True, id="before"),
        pytest.param("otlpUser\nfiller\nQUJDREVGR0hJSktMTU5PUFFSUw==\n", False, id="two-away"),
        pytest.param("otlpUser\nQUJD\n", False, id="too-short"),
        pytest.param("otlpUser\nk=QUJDREVGR0hJSktMTU5PUFFSUw== x\n", False, id="not-anchored"),
        pytest.param("QUJDREVGR0hJSktMTU5PUFFSUw==\n", False, id="no-symbol"),
        pytest.param("", False, id="empty"),
    ],
)
def test_base64_near_symbol(text: str, fires: bool) -> None:
    assert gate.base64_near_symbol(text) is fires


def test_renet_binaries_finds_both_locations(tmp_path: pathlib.Path) -> None:
    (tmp_path / "private" / "renet" / "bin").mkdir(parents=True)
    (tmp_path / "private" / "renet" / "bin" / "renet").write_text("x", encoding="utf-8")
    (tmp_path / "private" / "bin").mkdir(parents=True)
    (tmp_path / "private" / "bin" / "renet-linux-amd64").write_text("x", encoding="utf-8")
    # MIRROR: `-name 'renet-*'` is a glob on the basename, so a neighbour with a different prefix is not a renet binary.
    (tmp_path / "private" / "bin" / "middleware").write_text("x", encoding="utf-8")
    names = sorted(p.name for p in gate.renet_binaries(tmp_path))
    assert names == ["renet", "renet-linux-amd64"]


def test_renet_binaries_is_empty_when_nothing_is_built(tmp_path: pathlib.Path) -> None:
    assert gate.renet_binaries(tmp_path) == []


def test_selftest_passes_and_is_not_vacuous(capsys) -> None:
    """`--selftest` must be green AND must have run a non-trivial number of controls."""
    assert gate.selftest() == 0
    out = capsys.readouterr().out
    assert "control(s) passed" in out
    assert int(out.strip().split("\n")[-1].split()[0]) >= 16


def test_the_module_reads_the_root_the_package_agrees_on(tmp_path: pathlib.Path) -> None:
    """The port honours $REDIACC_CI_ROOT, which is how a harness moves it."""
    saved = os.environ.get(paths.ROOT_ENV)
    os.environ[paths.ROOT_ENV] = str(tmp_path)
    try:
        assert gate.main([]) == 0  # nothing built: two warnings and a clean exit
    finally:
        if saved is None:
            del os.environ[paths.ROOT_ENV]
        else:
            os.environ[paths.ROOT_ENV] = saved
