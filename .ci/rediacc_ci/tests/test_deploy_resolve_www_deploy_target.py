"""`rediacc_ci.deploy.resolve_www_deploy_target`, driven directly.

WHILE BOTH COPIES EXISTED every case below ran `.ci/scripts/deploy/resolve-www-deploy-target.sh` over the same environment and compared its `$GITHUB_OUTPUT` bytes, its stdout and its stderr against the port's. The K=5 ledger
`.ci/shadow/w7p5a-resolve-www-deploy-target.observations.jsonl` recorded that verdict over five distinct trees (`npx tsx scripts/lib/shadow-gate.ts --pair w7p5a-resolve-www-deploy-target --assert --k 5` -> "equivalence holds over 5 distinct trees") and licensed the port; W7 P5 retired the twin and the cases that executed it went with it.

THE GOLDEN BYTES BELOW ARE THE TWIN'S, KEPT VERBATIM. Both valid paths were byte-identical on purpose -- pure computation, four `key=value` lines to
`$GITHUB_OUTPUT`, nothing on stdout or stderr -- so the literals that were once
the twin's observed output are now the port's pinned contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff
from rediacc_ci.well_known import SITE_ORIGIN

SITE_HOST = SITE_ORIGIN.removeprefix("https://")

if TYPE_CHECKING:  # pathlib appears only in `tmp_path` annotations, never at runtime.
    import pathlib

MODULE = "resolve_www_deploy_target"

# ONE www Worker, deployed by one script (PLAN-product-domain-rename): the edge Worker and its `--sandbox` flag are gone.
EXPECTED = "script=deploy_www\nworker=www\ndomain=" + SITE_HOST + "\nsandbox=\n"


def run_port(tmp_path: pathlib.Path, env_extra: dict[str, str]) -> tuple[tuple[int, str, str], str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    out = tmp_path / "output.txt"
    env = diff.env_for(
        **env_extra,
        GITHUB_OUTPUT=str(out),
        PYTHONPATH=".ci",
        PYTHONDONTWRITEBYTECODE="1",
    )
    result = diff.bash_streams("python3 -m rediacc_ci.deploy.%s" % MODULE, env=env, timeout=30)
    written = out.read_text(encoding="utf-8") if out.exists() else ""
    return result, written


def test_the_one_www_worker_is_resolved(tmp_path: pathlib.Path) -> None:
    (exit_code, out, err), written = run_port(tmp_path, {})
    assert (exit_code, out, err) == (0, "", "")
    assert written == EXPECTED


def test_a_target_variable_no_longer_changes_the_answer(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY. The old `TARGET=edge` answer named the edge Worker and `--sandbox`; with no edge Worker it must resolve exactly like `stable` and like no target at all, and none of the retired names may appear."""
    answers = {
        target: run_port(tmp_path / target, {"TARGET": target})[1] for target in ("stable", "edge")
    }
    assert answers["stable"] == answers["edge"] == EXPECTED
    for retired in ("deploy_edge", "edge-rediacc-www", "rediacc-www", "--sandbox"):
        assert retired not in answers["edge"]


def test_a_missing_github_output_is_refused_and_names_the_variable() -> None:
    env = diff.env_for(PYTHONPATH=".ci", PYTHONDONTWRITEBYTECODE="1")
    exit_code, _out, err = diff.bash_streams(
        "python3 -m rediacc_ci.deploy.%s" % MODULE, env=env, timeout=30
    )
    assert exit_code == 1
    assert "GITHUB_OUTPUT" in err
    assert "must be set" in err
