"""Runs .claude/hooks/stop/test-rebase-consistency.py (PLAN-two-track-merge-dev RB1) under pytest, so check:ci-pytest carries its controls."""

import subprocess
import sys

from rediacc_ci import paths


def test_rebase_consistency_controls_pass():
    script = paths.from_root(".claude", "hooks", "stop", "test-rebase-consistency.py")
    r = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, timeout=600, check=False
    )
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "control(s) passed" in r.stdout, r.stdout[-500:]
