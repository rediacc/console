"""Both writers of the stable history record share one concurrency group.

cd-release-stable.yml's promote (promote_r2_to_stable) and cd-release-edge.yml's hotfix steps (promote_r2_to_stable_hotfix) read-modify-write the same record, so a hotfix publish must queue in the stable workflow's group (review 2786d8d0.4).
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows"


def _load(name: str) -> dict:
    return yaml.safe_load((WF / name).read_text(encoding="utf-8"))


def test_the_stable_workflow_holds_the_named_group() -> None:
    assert _load("cd-release-stable.yml")["concurrency"]["group"] == "cd-release-stable"


def test_a_hotfix_publish_joins_the_stable_group() -> None:
    publish = _load("cd-release-edge.yml")["jobs"]["publish"]
    group = publish["concurrency"]["group"]
    assert "inputs.publish_stable == true && 'cd-release-stable'" in group
    assert publish["concurrency"]["cancel-in-progress"] is False
    steps = [s.get("run", "") for s in publish["steps"]]
    assert any("promote_r2_to_stable_hotfix" in run for run in steps), (
        "the hotfix step moved out of the publish job"
    )
