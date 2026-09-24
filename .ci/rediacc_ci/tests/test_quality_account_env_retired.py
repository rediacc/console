"""`check:ci-account-env-retired` (agent/plans/PLAN-account-env-to-bws.md T19), driven for real.

The gate's own `selftest()` carries the planted defects the plan names (a `sed` of the file in a script, a `local:.env` rotation consumer, a re-added dotenv name, a token path under the repository). This file adds what a selftest cannot say about itself: that it runs green on the real tree, that the controls really execute, and that `--write-baseline` can only shrink.
"""

from __future__ import annotations

import json
import subprocess
import tempfile

from rediacc_ci.quality import account_env_retired as gate


def test_the_real_tree_is_green() -> None:
    findings, stats, _found, _spec = gate.run()
    assert findings == [], findings
    assert stats["files"] > 1000, "the scan saw only %d tracked file(s)" % stats["files"]


def test_the_controls_run_and_pass() -> None:
    assert gate.selftest() is False, "a control failed; see the PASS/FAIL lines above"


def test_the_baseline_only_shrinks() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = gate._fixture(
            tmp,
            {"docs/a.md": "private/account/.env\nprivate/account/.env\n"},
            baseline={"mentions": {"docs/a.md": 1}, "dotenv_names": 0},
        )
        assert gate.write_baseline(root) == 1, "a baseline that would GROW must be refused"
        (root / "docs" / "a.md").write_text("gone\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=True, capture_output=True)
        assert gate.write_baseline(root) == 0
        doc = json.loads((root / gate.BASELINE_REL).read_text(encoding="utf-8"))
        assert doc["mentions"] == {}, "the drained file must leave the baseline"


def test_the_exclusions_are_all_live_on_the_real_tree() -> None:
    files = gate.tracked(gate.paths.repo_root())
    assert gate.evaluate_exclusions(files, gate.paths.repo_root()) == []
