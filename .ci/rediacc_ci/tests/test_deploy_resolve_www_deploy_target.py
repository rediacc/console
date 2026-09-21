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

if TYPE_CHECKING:  # pathlib appears only in `tmp_path` annotations, never at runtime.
    import pathlib

MODULE = "resolve_www_deploy_target"


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


def test_stable_target_selects_the_stable_worker(tmp_path: pathlib.Path) -> None:
    (exit_code, out, err), written = run_port(tmp_path, {"TARGET": "stable"})
    assert (exit_code, out, err) == (0, "", "")
    assert written == (
        "script=deploy-www.sh\nworker=rediacc-www\ndomain=www.rediacc.com\nsandbox=\n"
    )


def test_edge_target_selects_the_edge_worker_and_sandbox(tmp_path: pathlib.Path) -> None:
    (exit_code, out, err), written = run_port(tmp_path, {"TARGET": "edge"})
    assert (exit_code, out, err) == (0, "", "")
    assert written == (
        "script=deploy-edge.sh\nworker=edge-rediacc-www\ndomain=edge.rediacc.com\n"
        "sandbox=--sandbox\n"
    )


def test_the_two_targets_do_not_resolve_to_the_same_thing(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY. Two golden blocks prove nothing if the gate ignores `TARGET` and prints one of them either way."""
    _, stable = run_port(tmp_path / "a", {"TARGET": "stable"})
    _, edge = run_port(tmp_path / "b", {"TARGET": "edge"})
    assert stable != edge
    assert stable != ""


def test_missing_target_is_refused_and_names_the_variable(tmp_path: pathlib.Path) -> None:
    (exit_code, _, err), written = run_port(tmp_path, {})
    assert exit_code == 1
    assert "TARGET" in err
    assert "must be set" in err
    assert written == ""
