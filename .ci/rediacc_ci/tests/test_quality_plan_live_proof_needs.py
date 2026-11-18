"""`check:ci-plan-live-proof` judges the `Needs:` box sub-line as LP8 (agent/plans/PLAN-push-decoupling.md N1, D3.1, D3.2).

The grammar lives in `wl_plandeps.box_github_wait`, and the gate reads it through `github_wait_findings`, the reading the pre-edit guard shares. These cases go through the gate's own `github_wait_judged` with the committed proof map, so a gate that stopped calling the shared reading, or a map whose runner ids drift from `RUNNER_NEEDS`, fails here and not only in the hook's controls.

EVERY REFUSAL HAS A PASSING TWIN built from the same box with one fact changed.
"""

import importlib.util
import json
import pathlib
import sys

import pytest
import wl_plandeps as D

from rediacc_ci import paths

GATE_PATH = paths.repo_root() / ".ci" / "scripts" / "quality" / "check_plan_live_proof.py"
MAP_PATH = paths.repo_root() / ".ci" / "config" / "proof-tiers.json"
BOX = "- [ ] N9 [writer] the parser change\n"
WAIT = "- [ ] T9 the edge check after the merge\n"
WHY = " -- only the CD pipeline deploys the edge channel"


@pytest.fixture(scope="module")
def gate():
    assert GATE_PATH.is_file(), "the gate moved: %s" % GATE_PATH
    paths.on_sys_path(pathlib.Path(GATE_PATH).parent)
    spec = importlib.util.spec_from_file_location("check_plan_live_proof_needs", GATE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves the gate's string annotations through sys.modules, so the module is registered before it runs.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def judged(gate):
    view = gate.map_view(json.loads(MAP_PATH.read_text(encoding="utf-8")))
    assert view.github_waits, "the committed map lost tiers.live.github_waits"

    def run(boxes: str) -> list[str]:
        plan = gate._fixture(owns="docs/x.md", proof=None, boxes=boxes)
        found, notes, count = gate.github_wait_judged([plan], view, True)
        assert notes == []
        assert count == len(found)
        return [f.message for f in found]

    return run


@pytest.mark.parametrize("value", D.NEEDS_VALUES)
def test_each_value_on_a_sub_line_passes(judged, value):
    assert judged(BOX + "    Needs: %s\n" % value) == []


def test_an_unknown_value_is_lp8(judged):
    found = judged(BOX + "    Needs: after-review\n")
    assert len(found) == 1
    assert "not one of none|bench-deploy|verified-vmcheck|pushed-head" in found[0]


def test_a_value_on_the_box_line_is_lp8_and_prose_naming_the_tag_is_not(judged):
    found = judged("- [ ] N9 [writer] the parser change Needs: none\n")
    assert len(found) == 1
    assert "box line" in found[0]
    # TWIN: the tag named in prose with no value after it.
    assert judged("- [ ] N9 [writer] parse and derive `Needs:` beside the tags\n") == []


def test_the_value_is_not_searched_for_a_phrase():
    # `pushed-head` is made a phrase here, so only the scrub keeps the value from matching.
    assert D.box_github_wait(BOX + "    Needs: pushed-head\n", ["pushed-head"]).phrases == ()
    assert D.box_github_wait(BOX + "    on the pushed-head\n", ["pushed-head"]).phrases == (
        "pushed-head",
    )


def test_a_value_that_contradicts_a_valid_tag_is_lp8(judged):
    tagged = WAIT + "  (corrected 2026-11-18) GitHub-only: CD" + WHY + "\n"
    found = judged(tagged + "    Needs: none\n")
    assert len(found) == 1
    assert "contradicts" in found[0]
    # TWIN: the value the tag derives.
    assert judged(tagged + "    Needs: pushed-head\n") == []


def test_a_route_value_must_match_its_runner_class(judged):
    routed = WAIT + "  (corrected 2026-11-18) Local-route: deploy-bench" + WHY + "\n"
    assert len(judged(routed + "    Needs: verified-vmcheck\n")) == 1
    assert judged(routed + "    Needs: bench-deploy\n") == []


def test_a_later_corrected_line_supersedes(judged):
    box = BOX + "    Needs: later\n  (corrected 2026-11-18) Needs: none)\n"
    assert judged(box) == []
    # TWIN: the order reversed, so the malformed value is the last word.
    assert len(judged(BOX + "  (corrected 2026-11-18) Needs: none)\n    Needs: later\n")) == 1


def test_a_ticked_box_is_not_judged(judged):
    assert judged(BOX.replace("[ ]", "[x]") + "    Needs: later\n") == []


def test_every_committed_runner_has_a_class():
    live = json.loads(MAP_PATH.read_text(encoding="utf-8"))["tiers"]["live"]
    assert sorted(D.RUNNER_NEEDS) == sorted(live["local_runners"])
