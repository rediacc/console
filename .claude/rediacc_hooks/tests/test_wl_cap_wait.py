"""The cap-saturated wait: agent/plans/PLAN-stop-hook-cap-saturated-wait.md.

Operator order, 2026-09-24: "the stop hook should not be invoked (or should skip the order) when writer slots are full! There could be exceptions like 2% compaction etc." With every writer slot verified live and nothing this session could start, the work orders (the judge, the quiet ladder, report shape, hygiene) stand down and the stop allows with one line naming the writers. Only wl_standdown.CAP_WAIT's keeps still block.

EVERY EXCEPTION CASE HAS ITS ALLOW TWIN, differing by one planted fact: a fifth open item, a dead fourth writer, the late context band with a missing STATE.md, an expired DEFAULT. The allow case is the incident itself: four live writers, three queue leases 95 minutes old, and a judge that would have said "continue".
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil

from rediacc_hooks import syspath
from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_judge_fixset_scope import capturing_judge
from rediacc_hooks.tests.test_wl_roster import (
    W1,
    W2,
    W3,
    W4,
    linked,
    mk_sub,
    plant_lease,
    stamp,
    until,
    verdict,
    write_plan,
)
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

SAID = "all four writer slots are live; the rest is queued\n\n## Remaining\n- queued behind the writer cap"
CONTINUE = {"verdict": "continue", "reason": "do the next action", "next_action": "sweep the class"}


def band_env(fix, band: int) -> dict:
    """A context-band marker for this session (ctx_budget.state_file), in a scratch directory."""
    d = fix.base / "ctxband"
    d.mkdir(exist_ok=True)
    (d / (wlfix.ME + ".json")).write_text(json.dumps({"epoch": 1, "band": band}), encoding="utf-8")
    return {"CTX_BAND_STATE_DIR": str(d)}


def saturated(fix, live: int = 4, queued: int = 3, queue_age_min: float = 95) -> None:
    """`live` leased writers (of W1..W4) plus `queued` queue leases, the incident's shape."""
    fix.brief_now()
    fix.hand_now()
    for i, aid in enumerate((W1, W2, W3, W4)):
        if i >= live:
            continue  # a free slot: no agent, no lease (a lease on a finished agent is c4's case)
        mk_sub(fix, aid, "general-purpose", 0)
        plant_lease(fix, "cap%d" % i, aid)
    for i in range(queued):
        plant_lease(fix, "q%d" % i, "queue", lease_age_min=queue_age_min)


def all_events(fix) -> list[dict]:
    """Every store event: the legacy file the fixtures plant into plus the per-writer files the hook appends to."""
    paths = [fix.events, *sorted(fix.store_dir.glob("*.jsonl"))]
    out: list[dict] = []
    for p in paths:
        if p.is_file():
            out.extend(
                json.loads(line)
                for line in p.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
    return out


def stop(fix, extra: dict | None = None):
    # The EARLY band unless the case planted its own: writing band 0 unconditionally would overwrite a planted late band (the same file).
    env = dict(extra) if extra and "CTX_BAND_STATE_DIR" in extra else band_env(fix, 0)
    env.update(extra or {})
    fix.say(SAID)
    return fix.runj(env)


def test_c1_saturated_plus_queued_allows_and_the_judge_is_never_called(wl):  # noqa: F811
    saturated(wl)
    capturing_judge(wl, CONTINUE)
    got = stop(wl)
    assert got.decision == "allow", wl.why("c1", "allow", got, "CAP-SATURATED WAIT")
    assert "CAP-SATURATED WAIT: 4/4 writer slots live" in got.out, got.out[:800]
    assert "3 item(s) queued" in got.out, got.out[:800]
    for needle in ("GONE QUIET", "Do the next action", "QUEUED WORK AND A FREE WRITER SLOT"):
        assert needle not in got.out, "c1: %r still pushed: %s" % (needle, got.out[:800])
    assert not (wl.base / "prompt.txt").exists(), (
        "c1: the judge was consulted in a cap-saturated wait"
    )


def test_c1_control_three_live_writers_block_on_the_free_slot(wl):  # noqa: F811
    saturated(wl, live=3)
    capturing_judge(wl, CONTINUE)
    got = stop(wl)
    assert got.decision == "block", wl.why("c1-control", "block", got, "free slot")
    assert "QUEUED WORK AND A FREE WRITER SLOT" in got.out, got.out[:800]
    assert "CAP-SATURATED WAIT" not in got.out, got.out[:800]


def test_c2_an_open_item_breaks_the_wait(wl):  # noqa: F811
    saturated(wl)
    wl.add_item("- [ ] (deadbeef) a plain open item the lead could do now")
    got = stop(wl)
    assert got.decision == "block", wl.why("c2", "block", got, "open item")
    assert "CAP-SATURATED WAIT" not in got.out, got.out[:800]


def test_c3_the_late_band_with_no_state_doc_keeps_the_state_demand(wl):  # noqa: F811
    saturated(wl)
    doc = wl.proj / "agent" / wlfix.ME / "STATE.md"
    if doc.exists():
        doc.unlink()
    late = stop(wl, band_env(wl, 1))
    assert late.decision == "block", wl.why("c3", "block", late, "STATE.md near compaction")
    assert "last band before auto-compact" in late.out, late.out[:900]
    # TWIN: the same missing document in the EARLY band stands down.
    wl.newturn()
    early = stop(wl, band_env(wl, 0))
    assert "last band before auto-compact" not in early.out, early.out[:900]
    assert early.decision == "allow", wl.why("c3-early", "allow", early, "CAP-SATURATED WAIT")


def test_c4_a_lease_on_a_finished_worker_still_blocks(wl):  # noqa: F811
    saturated(wl)
    mk_sub(wl, "a1000000000000009", "general-purpose", 30, last="end_turn", running=False)
    plant_lease(wl, "dead1", "a1000000000000009")
    got = stop(wl)
    assert got.decision == "block", wl.why("c4", "block", got, "LEASED TO A FINISHED WORKER")
    assert "LEASED TO A FINISHED WORKER" in got.out, got.out[:900]


def test_c5_an_expired_default_still_executes(wl):  # noqa: F811
    saturated(wl)
    with wl.events.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ev": "add",
                    "id": "dq1",
                    "at": stamp(130),
                    "by": wlfix.ME,
                    "s": "?",
                    "o": wlfix.ME,
                    "t": "(deadbeef) ship it? DEFAULT: ship it",
                }
            )
            + "\n"
        )
    got = stop(wl)
    assert got.decision == "block", wl.why("c5", "block", got, "expired DEFAULT")
    assert "DEFAULT" in got.out, got.out[:900]


def test_c7_queue_leases_renew_only_while_the_cap_is_full(wl):  # noqa: F811
    """A queue lease near expiry is renewed at 4/4 and left alone at 3/4 (where queue-slot names it)."""
    saturated(wl, queued=0)
    with wl.events.open("a", encoding="utf-8") as fh:
        for ev in (
            {
                "ev": "add",
                "id": "qx",
                "at": stamp(100),
                "by": wlfix.ME,
                "s": " ",
                "o": wlfix.ME,
                "t": "(deadbeef) queued",
            },
            {
                "ev": "lease",
                "id": "qx",
                "at": stamp(99),
                "by": wlfix.ME,
                "until": until(10),
                "worker": "queue",
                "note": "",
                "worker_verified": False,
            },
        ):
            fh.write(json.dumps(ev) + "\n")
    stop(wl)
    leases = [e for e in all_events(wl) if e.get("id") == "qx"]
    renewed = [e for e in leases if e.get("ev") == "lease" and "auto-renew" in e.get("note", "")]
    assert renewed, "c7: the queue lease was not renewed at 4/4: %s" % leases
    assert renewed[-1]["until"] > until(100), renewed[-1]


def test_c7_control_no_renewal_below_the_cap(wl):  # noqa: F811
    saturated(wl, live=3, queued=0)
    with wl.events.open("a", encoding="utf-8") as fh:
        for ev in (
            {
                "ev": "add",
                "id": "qx",
                "at": stamp(100),
                "by": wlfix.ME,
                "s": " ",
                "o": wlfix.ME,
                "t": "(deadbeef) queued",
            },
            {
                "ev": "lease",
                "id": "qx",
                "at": stamp(99),
                "by": wlfix.ME,
                "until": until(10),
                "worker": "queue",
                "note": "",
                "worker_verified": False,
            },
        ):
            fh.write(json.dumps(ev) + "\n")
    stop(wl)
    renewed = [
        e for e in all_events(wl) if e.get("id") == "qx" and "auto-renew" in str(e.get("note", ""))
    ]
    assert not renewed, "c7-control: a queue lease was renewed with a free slot: %s" % renewed


def test_c8_the_quiet_ladder_never_fires_on_a_queue_lease(wl):  # noqa: F811
    """Below the cap too: a queue lease has no worker that can go quiet (step 1)."""
    saturated(wl, live=3, queued=1, queue_age_min=95)
    got = stop(wl)
    assert "GONE QUIET" not in got.out, got.out[:900]
    assert "worker:queue is NOT in the harness" not in got.out, got.out[:900]


def load_standdown():
    """wl_standdown loaded from the real stop directory."""
    stop_dir = wlfix.STOP_DIR
    spec = importlib.util.spec_from_file_location("_wl_standdown_c9", stop_dir / "wl_standdown.py")
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    syspath.on_sys_path(stop_dir)
    spec.loader.exec_module(mod)
    return mod


def producer_source() -> str:
    """Every stop module but the keep-lists' own, so a key named only in wl_standdown.py counts as having no producer."""
    return "".join(
        p.read_text(encoding="utf-8")
        for p in sorted(wlfix.STOP_DIR.glob("wl_*.py"))
        if p.name != "wl_standdown.py"
    )


def test_c9_every_kept_key_has_a_producer():
    """A keep-list entry nothing produces is a typo that silently stands a real check down. Iterates every profile."""
    mod = load_standdown()
    src = producer_source()
    missing: list[str] = []
    for prof in mod.PROFILES:
        missing.extend(
            "%s:%s" % (prof.name, k)
            for k in sorted(prof.keeps | prof.always_keeps | prof.compaction_keys)
            if not re.search(r"""["']%s["']""" % re.escape(k), src)
        )
        missing.extend(
            "%s:%s*" % (prof.name, pre)
            for pre in prof.prefixes
            if not re.search(r"""["']%s""" % re.escape(pre), src)
        )
    assert not missing, "keep-list keys with no producer: %s" % missing


def test_c10_the_verdict_counts_four_live_writers(wl):  # noqa: F811
    saturated(wl)
    v = verdict(wl)
    assert len(v["writers"]) == 4, v["writers"]


# ---- mutation controls: each exception removed in a PRIVATE COPY makes its case stop detecting it ----


def mutated_hook(fix, filename: str, old: str, new: str) -> None:
    """Copy the stop and context directories into the fixture (wl_retro finds the context module at parents[1]/context), mutate one file, and drive the copy."""
    hooks = fix.base / "hooks"
    shutil.copytree(wlfix.STOP_DIR, hooks / "stop", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(
        wlfix.STOP_DIR.parent / "context",
        hooks / "context",
        ignore=shutil.ignore_patterns("__pycache__", "state"),
    )
    path = hooks / "stop" / filename
    src = path.read_text(encoding="utf-8")
    assert src.count(old) == 1, "MUTATION FIXTURE BROKEN: %r occurs %d times in %s" % (
        old,
        src.count(old),
        filename,
    )
    path.write_text(src.replace(old, new), encoding="utf-8")
    fix.hook = hooks / "stop" / "worklist.py"
    # The judge launcher needs .ci/rediacc_ci/proc.py, which wl_proc finds at the copy's parents[2]; link the real one there.
    ci = hooks.parents[1] / ".ci"
    if not ci.exists():
        ci.symlink_to(wlfix.STOP_DIR.parents[2] / ".ci")


def test_m1_without_roster_dead_in_the_keep_list_a_dead_lease_stands_down(wl):  # noqa: F811
    saturated(wl)
    mk_sub(wl, "a1000000000000009", "general-purpose", 30, last="end_turn", running=False)
    plant_lease(wl, "dead1", "a1000000000000009")
    mutated_hook(wl, "wl_standdown.py", '        "roster-dead",\n', "")
    got = stop(wl)
    assert "LEASED TO A FINISHED WORKER" not in got.out, (
        "m1: the c4 case does not depend on the keep-list entry"
    )
    assert got.decision == "allow", "m1: expected the mutated wait to allow: %s" % got.out[:400]


def test_m2_without_defer_expired_in_the_keep_list_an_expired_default_stands_down(wl):  # noqa: F811
    saturated(wl)
    with wl.events.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ev": "add",
                    "id": "dq1",
                    "at": stamp(130),
                    "by": wlfix.ME,
                    "s": "?",
                    "o": wlfix.ME,
                    "t": "(deadbeef) ship it? DEFAULT: ship it",
                }
            )
            + "\n"
        )
    mutated_hook(wl, "wl_standdown.py", '        "defer-expired",\n', "")
    got = stop(wl)
    assert got.decision == "allow", (
        "m2: the c5 case does not depend on the keep-list entry: %s" % got.out[:400]
    )


def test_m3_without_the_late_band_read_the_compaction_case_stands_down(wl):  # noqa: F811
    saturated(wl)
    (wl.proj / "agent" / wlfix.ME / "STATE.md").unlink()
    mutated_hook(
        wl, "wl_checks.py", '        return band >= names.index("late")\n', "        return False\n"
    )
    got = stop(wl, band_env(wl, 1))
    assert "last band before auto-compact" not in got.out, (
        "m3: the c3 case does not depend on the band read"
    )
    assert got.decision == "allow", "m3: expected the mutated wait to allow: %s" % got.out[:400]


def test_m4_without_the_open_items_term_an_open_item_stands_down(wl):  # noqa: F811
    saturated(wl)
    wl.add_item("- [ ] (deadbeef) a plain open item the lead could do now")
    mutated_hook(
        wl,
        "wl_roster.py",
        '    if not verdict or verdict.get("blind") or open_items or actionable_tasks:\n',
        '    if not verdict or verdict.get("blind") or actionable_tasks:\n',
    )
    got = stop(wl)
    assert got.decision == "allow", (
        "m4: the c2 case does not depend on the open-items term: %s" % got.out[:400]
    )


def test_m5_with_an_unreachable_cap_the_saturated_case_is_judged_again(wl):  # noqa: F811
    saturated(wl)
    capturing_judge(wl, CONTINUE)
    mutated_hook(
        wl,
        "wl_roster.py",
        '    return len(verdict.get("writers") or ()) >= WRITER_CAP or concurrency_saturated(verdict)\n',
        '    return len(verdict.get("writers") or ()) >= 99 or concurrency_saturated(verdict)\n',
    )
    got = stop(wl)
    assert "CAP-SATURATED WAIT" not in got.out, "m5: the allow did not depend on the cap term"
    assert (wl.base / "prompt.txt").exists(), (
        "m5: with the wait off, the judge should have been consulted"
    )


# ---- the concurrency-saturated wait (agent/plans/PLAN-plan-priority-concurrency.md section 5c) ----


def held_queue(fix, unheld: bool = False) -> None:
    """One live writer of EXCLUSIVE plan E and two queue leases on plan F, which E's mutex holds: three slots free and nothing startable. `unheld` adds a queue lease on E itself, which the mutex does not hold."""
    fix.brief_now()
    fix.hand_now()
    e = write_plan(fix, "e", conc="exclusive -- regenerates every golden file")
    f = write_plan(fix, "f")
    mk_sub(fix, W1, "general-purpose", 0, prompt="Plan: %s" % e)
    plant_lease(fix, "e2000001", W1, text=linked(e, "regenerate goldens"))
    for i in range(2):
        plant_lease(fix, "f200000%d" % i, "queue", lease_age_min=30, text=linked(f, "held %d" % i))
    if unheld:
        plant_lease(fix, "e2000002", "queue", lease_age_min=20, text=linked(e, "startable"))


def test_c11_every_queued_item_held_is_a_concurrency_saturated_wait(wl):  # noqa: F811
    held_queue(wl)
    capturing_judge(wl, CONTINUE)
    got = stop(wl)
    assert got.decision == "allow", wl.why("c11", "allow", got, "CONCURRENCY-SATURATED WAIT")
    assert "CONCURRENCY-SATURATED WAIT: 1/4 writer slots live" in got.out, got.out[:900]
    assert "all 2 queued item(s) are held by a live plan (PLAN-e.md)" in got.out, got.out[:900]
    assert "QUEUED WORK AND A FREE WRITER SLOT" not in got.out, got.out[:900]
    assert not (wl.base / "prompt.txt").exists(), "c11: the judge was consulted in the wait"


def test_c11_control_one_unheld_queued_item_blocks_on_the_free_slot(wl):  # noqa: F811
    held_queue(wl, unheld=True)
    capturing_judge(wl, CONTINUE)
    got = stop(wl)
    assert got.decision == "block", wl.why("c11-control", "block", got, "free slot")
    assert "QUEUED WORK AND A FREE WRITER SLOT" in got.out, got.out[:900]
    assert "start #e2000002." in got.out, got.out[:900]
    assert "held back: #f2000000" in got.out, got.out[:1500]
    assert "CONCURRENCY-SATURATED WAIT" not in got.out, got.out[:900]


def test_c11_the_verdict_says_every_queued_item_is_held(wl):  # noqa: F811
    held_queue(wl)
    v = verdict(wl)
    assert [i for i, _why in v["queue_conc_held"]] == ["f2000000", "f2000001"], v
    assert v["queue_start"] == [], v
    assert v["queued"] == 2, v


def test_m6_without_the_concurrency_term_the_held_queue_is_judged_again(wl):  # noqa: F811
    held_queue(wl)
    capturing_judge(wl, CONTINUE)
    mutated_hook(
        wl,
        "wl_roster.py",
        '    return len(verdict.get("writers") or ()) >= WRITER_CAP or concurrency_saturated(verdict)\n',
        '    return len(verdict.get("writers") or ()) >= WRITER_CAP\n',
    )
    got = stop(wl)
    assert "CONCURRENCY-SATURATED WAIT" not in got.out, "m6: c11 does not depend on the term"
    assert (wl.base / "prompt.txt").exists(), "m6: with the wait off, the judge should be consulted"


def test_c12_a_held_queue_lease_renews_beside_a_free_slot(wl):  # noqa: F811
    """It waits on the holder, not on the lead: letting it expire into an open item would demand a start the spawn guard refuses."""
    held_queue(wl)
    near = until(10)
    with wl.events.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ev": "lease",
                    "id": "f2000000",
                    "at": stamp(1),
                    "by": wlfix.ME,
                    "until": near,
                    "worker": "queue",
                    "note": "",
                }
            )
            + "\n"
        )
    stop(wl)
    renewals = [
        e
        for e in all_events(wl)
        if e.get("ev") == "lease"
        and e.get("id") == "f2000000"
        and e.get("until") != near
        and "held by a live plan" in str(e.get("note") or "")
    ]
    assert renewals, "c12: the held queue lease was not renewed"
