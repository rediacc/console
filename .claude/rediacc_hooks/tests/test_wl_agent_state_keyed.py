"""STATE.md freshness keyed to the ids it names (agent/plans/PLAN-stop-hook-retro-20261125.md R20261125.2, friction 2).

The lead's 14:09Z rewrite named 8 delegated item ids under `## Delegated` and none under `## Next action`, so `agent_state_state` fell back to the owned-item signature and every writer's tick or add staled it: 33 rewrites in 18.5 h. These worlds pin both halves of the fix: `## Delegated` ids count as named, and the unkeyed stale reason says how to key the document.

Each world is a real `agent/<me>/STATE.md` with a heading stamp 40 minutes old (past AGENT_STATE_STALE_MIN), judged with a moved signature (`cur_sig != saved_sig`), so only the named-ids branch can return ok.
"""

from __future__ import annotations

import datetime
import types

from rediacc_hooks.tests import wlfix

S = wlfix.import_wl("wl_store")
C = wlfix.import_wl("wl_core")
K = wlfix.import_wl("wl_checks")

ME = "cafe0125"
DELEGATED = [
    "f55c6a82",
    "3a102a4c",
    "e32de9b1",
    "c276a9df",
    "9b1e0a77",
    "5d0c3e21",
    "a1b2c3d4",
    "0f9e8d7c",
]
PAD = (
    "The plan-folders sweep landed; the retro plan is written and its four boxes are with writers. "
    * 3
)


def _body(next_ids=(), delegated=()):
    nxt = "Land each writer's report as it arrives and tick its box%s." % (
        (" (" + ", ".join("#" + i for i in next_ids) + ")") if next_ids else ""
    )
    lines = [PAD, "", "## Next action", nxt, ""]
    if delegated:
        lines += ["## Delegated"] + ["- #%s writer on its own lease" % i for i in delegated] + [""]
    lines += ["## Big pieces", "none: no plan carries an open box.", ""]
    return "\n".join(lines)


def _world(tmp_path, body):
    sdir = S.agent_session_dir(tmp_path, ME)
    sdir.mkdir(parents=True)
    stamp = (C.utcnow() - datetime.timedelta(minutes=40)).strftime("%Y-%m-%dT%H:%M:%SZ")
    (sdir / "STATE.md").write_text("## SESSION %s %s\n%s" % (ME, stamp, body), encoding="utf-8")
    return tmp_path


def _fold(states):
    return types.SimpleNamespace(
        items=[
            {"id": rid, "state": st, "owner": ME, "text": "item (%s)" % ME}
            for rid, st in states.items()
        ]
    )


def _verdict(root, fold):
    return S.agent_state_state(root, ME, cur_sig="moved", saved_sig="banked", fold=fold)[0]


def test_the_1409z_body_with_eight_open_delegated_ids_stays_ok(tmp_path):
    root = _world(tmp_path, _body(delegated=DELEGATED))
    fold = _fold(dict.fromkeys(DELEGATED, ">"))
    assert S.next_action_ids(_body(delegated=DELEGATED)) == DELEGATED
    assert _verdict(root, fold) == "ok"


def test_inverse_no_ids_anywhere_and_a_moved_signature_is_stale_with_the_new_sentence(tmp_path):
    body = _body()
    root = _world(tmp_path, body)
    assert S.next_action_ids(body) == []
    assert _verdict(root, _fold(dict.fromkeys(DELEGATED, ">"))) == "stale"
    because = K._agent_state_because("stale", 40, keyed=bool(S.next_action_ids(body)))
    assert "'## Next action' names no #id, so any owned-item change stales it" in because, because
    assert "name the ids of the next steps" in because, because
    assert "'## Delegated' count too" in because, because


def test_every_named_id_closed_is_stale_and_the_reason_says_so(tmp_path):
    body = _body(next_ids=DELEGATED[:2], delegated=DELEGATED[2:])
    root = _world(tmp_path, body)
    assert _verdict(root, _fold(dict.fromkeys(DELEGATED, "x"))) == "stale"
    because = K._agent_state_because("stale", 40, keyed=bool(S.next_action_ids(body)))
    assert "every #id its '## Next action' and '## Delegated' name has closed" in because, because
    assert "names no #id" not in because, because


def test_control_one_delegated_id_still_open_keeps_it_fresh(tmp_path):
    body = _body(delegated=DELEGATED)
    root = _world(tmp_path, body)
    states = dict.fromkeys(DELEGATED, "x")
    states[DELEGATED[-1]] = " "
    assert _verdict(root, _fold(states)) == "ok"


def test_control_an_unmoved_signature_with_no_ids_is_ok(tmp_path):
    root = _world(tmp_path, _body())
    verdict = S.agent_state_state(root, ME, cur_sig="same", saved_sig="same", fold=_fold({}))[0]
    assert verdict == "ok"


def test_ids_named_in_both_sections_are_listed_once_in_order():
    body = _body(next_ids=[DELEGATED[1], DELEGATED[0]], delegated=DELEGATED[:3])
    assert S.next_action_ids(body) == [DELEGATED[1], DELEGATED[0], DELEGATED[2]]


def test_next_action_ids_lists_next_action_first_then_delegated_whatever_the_document_order() -> (
    None
):
    """5be6080d.1: the ids come in heading-tuple order, not document order, once each."""
    body = "## Delegated\n- #aaaaaaaa one\n- #bbbbbbbb two\n\n## Next action\n- #cccccccc three\n- #aaaaaaaa again\n"
    assert S.next_action_ids(body) == ["cccccccc", "aaaaaaaa", "bbbbbbbb"]
    # control: the document order with Next action first gives the same list
    swapped = "## Next action\n- #cccccccc three\n- #aaaaaaaa again\n\n## Delegated\n- #aaaaaaaa one\n- #bbbbbbbb two\n"
    assert S.next_action_ids(swapped) == ["cccccccc", "aaaaaaaa", "bbbbbbbb"]
