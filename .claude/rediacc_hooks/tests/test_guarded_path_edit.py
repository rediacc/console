"""block_guarded_path_edit still makes every refusal the three guards it merged made (PLAN-tooling-code-reduction CR5).

One test per retired guard, each through `dispatch.py <stem>` with its control beside it: the review record (once block_review_file_edit), the live-proof ledger (once block_live_proof_ledger_write) and the whole-file write over an existing round log (once block_roundlog_write). The full case sets and the plants are in `guards/test-block_guarded_path_edit.py`; the round log row is also judged by its golden. A last test holds `guards.RENAMED`, the map the fire ledger's old stems are folded through.
"""

import json

from rediacc_hooks import guards
from rediacc_hooks.tests import hookcases

KEY = "guards/block_guarded_path_edit.py"


def _answer(tool, path, **extra):
    payload = {"tool_name": tool, "tool_input": {"file_path": path, **extra}}
    return hookcases.run_guard(KEY, json.dumps(payload), want_stderr=True)


def test_a_review_record_edit_is_refused_and_a_plan_is_not():
    rc, err = _answer("Edit", "agent/reviews/1231-9/x.md", old_string="[high]", new_string="[low]")
    assert rc == 2, err
    assert "--review-mark" in err, err
    rc, err = _answer("Write", "agent/plans/PLAN-x.md", content="agent/reviews/")
    assert rc == 0, err


def test_a_live_proof_ledger_write_is_refused_and_a_non_ledger_beside_it_is_not():
    rc, err = _answer("Write", "agent/ledgers/live-proof.jsonl", content="{}\n")
    assert rc == 2, err
    assert "live_proof record" in err, err
    rc, err = _answer("Write", "agent/ledgers/feedback-snapshot.json", content="{}\n")
    assert rc == 0, err


def test_an_agent_store_write_is_refused_by_its_own_row():
    """Review finding 896a95d5.3: another `.jsonl` ledger, a reggate file and the worklist event log are the agent store row's, and its refusal (not the live-proof one) names them."""
    for path in (
        "agent/ledgers/effort-outcomes.jsonl",
        "agent/reggate/main.jsonl",
        "agent/worklist/d778be9d.jsonl",
    ):
        rc, err = _answer("Write", path, content="{}\n")
        assert rc == 2, (path, err)
        assert "append-only agent store" in err, (path, err)
        assert "live_proof record" not in err, (path, err)
    rc, err = _answer("Write", "agent/worklist/README.md", content="x\n")
    assert rc == 0, err


def test_a_whole_file_write_over_an_existing_round_log_is_refused_and_creating_one_is_not(
    tmp_path,
):
    log = tmp_path / "reports" / "pr-babysit-0831-1.md"
    log.parent.mkdir()
    log.write_text("# wave\n\n## STATUS (round 1, t)\n\nx\n", encoding="utf-8")
    rc, err = _answer("Write", str(log), content="x")
    assert rc == 2, err
    assert "worklist.py --roundlog" in err, err
    rc, err = _answer("Edit", str(log), old_string="x", new_string="y")
    assert rc == 0, err
    rc, err = _answer("Write", str(log.with_name("pr-babysit-never-written.md")), content="x")
    assert rc == 0, err


def test_every_renamed_stem_is_gone_and_its_target_is_on_disk():
    stems = set(guards.stems())
    assert guards.RENAMED, "an empty map would fold nothing and pass"
    for old, new in guards.RENAMED.items():
        assert old not in stems, "%s is mapped away but still on disk" % old
        assert new in stems, "%s maps to %s, which is not a guard" % (old, new)
