"""`rediacc_ci.quality.no_otlp_creds`, driven directly.

WHILE BOTH COPIES EXISTED a bash child ran the REAL `.ci/scripts/quality/check-no-otlp-creds.sh` over a fixture with stdout and stderr captured SEPARATELY, and its bytes were compared against the port's. THE TWIN HAD NO ENVIRONMENT SEAM -- it resolved the repo root from `get_repo_root`, i.e. from `.ci/scripts/lib/common.sh`'s own location -- so unlike
`test_quality_staging_tag_guard.py` the twin had to be COPIED into the fixture. That is the recipe the committed ledger uses (`.ci/shadow/w7p2-otlp-creds.observations.jsonl`), and it is what makes the tree id in those rows a claim about both implementations.

THE TWIN WAS RETIRED IN W7 P5 once that ledger licensed the port at K=5, and the cases that copied and ran it were retired with it: a fixture holding one implementation compares nothing. Two properties they carried are recorded here rather than lost silently. This gate writes everything through `log_*`, so every line lands on stderr and stdout stays empty, and the pair of
byte comparisons was what would have caught a stream swap. And `log_info` prefixes a SECOND success glyph onto a line that already carries one, a twin defect the port reproduces rather than tidies; the ledger's rows are the record of that agreement now.

The decision functions below are driven directly, both directions for every rule, and the gate's own selftest carries the controls.
"""

import os
import pathlib

import pytest

from rediacc_ci import paths
from rediacc_ci.quality import no_otlp_creds as gate

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
