"""`rediacc_ci.release.deployment_summary`, driven directly.

WHILE BOTH COPIES EXISTED every case below ran `.ci/scripts/release/deployment-summary.sh` over the same environment and compared its `$GITHUB_STEP_SUMMARY` bytes, its stdout and its stderr against the port's.
The K=5 ledger `.ci/shadow/w7p5a-deployment-summary.observations.jsonl` recorded that verdict over five distinct trees (`npx tsx scripts/lib/shadow-gate.ts --pair w7p5a-deployment-summary --assert --k 5`) and licensed the port; W7 P5 retired the twin and the cases that executed it went with it.

THE GOLDEN BLOCK BELOW IS THE TWIN'S, KEPT VERBATIM. The script has no branch at all, only string interpolation into a fixed template, so "these exact bytes" was the whole claim then and remains the whole claim now.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rediacc_ci.tests import differential as diff

if TYPE_CHECKING:  # pathlib appears only in `tmp_path` annotations, never at runtime.
    import pathlib

MODULE = "deployment_summary"

EXPECTED = (
    "\n---\n\n## Deployment Complete\n\n"
    "**Version:** v1.2.3\n"
    "**CI Run:** 42 (sha: abc123)\n"
    "**Pages URL:** https://www.rediacc.com\n\n"
    "**Docker images:**\n"
    "- ghcr.io/rediacc/renet:1.2.3 + :latest\n"
    "- ghcr.io/rediacc/rdc:1.2.3 + :latest\n"
    "- ghcr.io/rediacc/server:1.2.3 + :latest (on-prem)\n"
)


def run_port(summary: pathlib.Path, env_extra: dict[str, str]) -> tuple[int, str, str]:
    env = diff.env_for(
        **env_extra,
        GITHUB_STEP_SUMMARY=str(summary),
        PYTHONPATH=".ci",
        PYTHONDONTWRITEBYTECODE="1",
    )
    return diff.bash_streams("python3 -m rediacc_ci.release.%s" % MODULE, env=env, timeout=30)


def test_full_summary_is_the_pinned_template(tmp_path: pathlib.Path) -> None:
    summary = tmp_path / "summary.md"
    env = {"VERSION": "1.2.3", "CI_RUN_ID": "42", "CI_SHA": "abc123"}
    assert run_port(summary, env) == (0, "", "")
    assert summary.read_text(encoding="utf-8") == EXPECTED


def test_the_template_carries_its_inputs(tmp_path: pathlib.Path) -> None:
    """ANTI-VACUITY. A fixed template that ignored `VERSION`, `CI_RUN_ID` and `CI_SHA` would satisfy the case above and nothing else."""
    summary = tmp_path / "summary.md"
    env = {"VERSION": "9.9.9", "CI_RUN_ID": "7", "CI_SHA": "cafef00d"}
    assert run_port(summary, env) == (0, "", "")
    written = summary.read_text(encoding="utf-8")
    assert written != EXPECTED
    assert "**Version:** v9.9.9\n" in written
    assert "**CI Run:** 7 (sha: cafef00d)\n" in written


def test_appends_rather_than_overwrites(tmp_path: pathlib.Path) -> None:
    """`$GITHUB_STEP_SUMMARY` already carries other jobs' output by the time this step runs, so the write must be `>>`, never a truncation."""
    summary = tmp_path / "summary.md"
    summary.write_text("# earlier job output\n", encoding="utf-8")
    env = {"VERSION": "0.0.1", "CI_RUN_ID": "1", "CI_SHA": "deadbeef"}
    assert run_port(summary, env) == (0, "", "")
    written = summary.read_text(encoding="utf-8")
    assert written.startswith("# earlier job output\n")
    assert "## Deployment Complete" in written


def test_missing_ci_sha_is_refused_and_names_the_variable(tmp_path: pathlib.Path) -> None:
    summary = tmp_path / "summary.md"
    exit_code, _, err = run_port(summary, {"VERSION": "1.2.3", "CI_RUN_ID": "42"})
    assert exit_code == 1
    assert "CI_SHA" in err
    assert "must be set" in err
    assert not summary.exists() or summary.read_text(encoding="utf-8") == ""
