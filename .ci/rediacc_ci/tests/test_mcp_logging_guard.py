"""`check:ci-mcp-logging-guard` (agent/plans/PLAN-rmcp-remote-worker.md RW-D1, Design 9), driven for real.

The gate's own `selftest()` carries one planted violation per rule. This file adds what a selftest cannot say about itself: that the controls really execute, that the real tree is green with a non-trivial scan, and that a violation planted into a copy of the REAL MCP Worker files reds, rule by rule, through the same entry CI runs.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

import pytest

from rediacc_ci import paths
from rediacc_ci.controls import fixture_git_env
from rediacc_ci.quality import mcp_logging_guard as gate
from rediacc_ci.well_known import MCP_US_HOST

ROOT = pathlib.Path(paths.repo_root())


def test_the_controls_run_and_pass() -> None:
    assert gate.selftest() is False, "a control failed; see the PASS/FAIL lines above"


def test_the_real_tree_is_green_and_was_seen() -> None:
    findings, stats = gate.run(ROOT)
    assert findings == [], findings
    assert stats["mcp_wranglers"] >= 7, stats
    assert stats["wranglers"] > stats["mcp_wranglers"], stats
    assert stats["non_test"] >= 10, stats


def test_the_module_entry_exits_zero_on_the_real_tree() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "rediacc_ci.quality.mcp_logging_guard"],
        cwd=ROOT,
        env={**fixture_git_env(), "PYTHONPATH": str(ROOT / ".ci")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    assert "non-test" in out.stderr, "the success line must print the scan's shape"


def test_an_unknown_argument_is_refused() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "rediacc_ci.quality.mcp_logging_guard", "--write-baseline"],
        cwd=ROOT,
        env={**fixture_git_env(), "PYTHONPATH": str(ROOT / ".ci")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode == 2, (out.returncode, out.stderr)


def _copy_of_real_tree(tmp: str) -> pathlib.Path:
    """A git repo holding the real `workers/mcp` wrangler files and sources plus one other Worker's wrangler file."""
    root = pathlib.Path(tmp)
    rels = [
        rel
        for rel in gate.tracked(ROOT)
        if rel.startswith((gate.MCP, gate.MCP_HOST))
        and rel.endswith((".toml", *gate.SOURCE_SUFFIXES))
    ]
    rels.append("workers/proxy/wrangler.template.toml")
    for rel in rels:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, root / rel)
    env = fixture_git_env()
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, env=env)
    subprocess.run(["git", "-C", str(root), "add", "-A", "-f", "."], check=True, env=env)
    return root


def _edit(root: pathlib.Path, rel: str, old: str, new: str) -> None:
    path = root / rel
    text = path.read_text(encoding="utf-8")
    assert old in text, "the plant's anchor %r left %s; update the plant" % (old, rel)
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


PLANTS = {
    "W1": (
        "workers/proxy/wrangler.template.toml",
        "[observability]",
        '[logpush_job]\ncustom_fields = ["authorization"]\n\n[observability]',
    ),
    "W2": ("workers/mcp/wrangler.eu.toml", "invocation_logs = false", "invocation_logs = true"),
    "W3": (
        "workers/mcp/wrangler.us.toml",
        'pattern = "%s"' % MCP_US_HOST,
        'pattern = "%s/*?token=*"' % MCP_US_HOST,
    ),
    "S1": ("workers/mcp/src/index.ts", "export {", "void getUnredacted;\nexport {"),
    "S2": (
        "packages/shared/src/mcp-host/oauth/index.ts",
        "url.searchParams.get('client_id')",
        "url.searchParams.get('access_token')",
    ),
}


def test_the_copied_real_tree_is_green_before_any_plant() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        assert gate.run(_copy_of_real_tree(tmp))[0] == []


@pytest.mark.parametrize("rule", sorted(PLANTS))
def test_one_plant_per_rule_reds_on_the_real_files(rule: str) -> None:
    rel, old, new = PLANTS[rule]
    with tempfile.TemporaryDirectory() as tmp:
        root = _copy_of_real_tree(tmp)
        _edit(root, rel, old, new)
        findings = gate.run(root)[0]
    assert [f for f in findings if f.startswith("%s %s" % (rule, rel))], findings
    assert all(f.startswith(rule) for f in findings), (
        "a %s plant must not fire another rule: %s" % (rule, findings)
    )


def test_getunredacted_in_the_shared_mcp_host_is_caught() -> None:
    rel = "packages/shared/src/mcp-host/handler.ts"
    with tempfile.TemporaryDirectory() as tmp:
        root = _copy_of_real_tree(tmp)
        _edit(root, rel, "export ", "void getUnredacted;\nexport ")
        findings = gate.run(root)[0]
    assert [f for f in findings if f.startswith("S1 %s" % rel)], findings
