"""The concurrency-saturated wait: agent/plans/PLAN-stop-hook-cap-saturated-wait.md, narrowed to file-clash queues by agent/plans/PLAN-unlimited-writers.md.

The operator's order of 2026-09-24 stood the battery down while nothing could start, with "exceptions like 2% compaction". With no writer limit any more (agent/plans/PLAN-unlimited-writers.md), the one wait left is the queue a live plan holds: every queued item refused by block_plan_concurrency (a live plan's mutex or Owns) and nothing this session could start. The work orders (the judge, the quiet ladder, report shape, hygiene) stand down and the stop allows with one line naming the writers and the holder. Only wl_standdown.CONC_WAIT's keeps still block.

EVERY EXCEPTION CASE HAS ITS ALLOW TWIN, differing by one planted fact: an open item, a dead writer, the late context band with a missing STATE.md, an expired DEFAULT, one queued item no plan holds. The allow case: one live writer of EXCLUSIVE plan E, and queue leases on plan F, whose Owns overlap E's, 95 minutes old, with a judge that would have said "continue".
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
    linked,
    mk_sub,
    plant_lease,
    stamp,
    until,
    verdict,
    write_plan,
)

SAID = (
    "every queued item waits on PLAN-e.md\n\n## Remaining\n- queued behind the live exclusive plan"
)
CONTINUE = {"verdict": "continue", "reason": "do the next action", "next_action": "sweep the class"}


def band_env(fix, band: int) -> dict:
    """A context-band marker for this session (ctx_budget.state_file), in a scratch directory."""
    d = fix.base / "ctxband"
    d.mkdir(exist_ok=True)
    (d / (wlfix.ME + ".json")).write_text(json.dumps({"epoch": 1, "band": band}), encoding="utf-8")
    return {"CTX_BAND_STATE_DIR": str(d)}


def saturated(
    fix,
    queued: int = 3,
    queue_age_min: float = 95,
    unheld: bool = False,
    f_owns: str = "src/e/golden/**",
) -> None:
    """One live writer of EXCLUSIVE plan E and `queued` queue leases on plan F, which E's mutex holds: nothing startable. `unheld` adds a queue lease on E itself, which the mutex does not hold.

    F's Owns overlap E's by default: an exclusive plan is a mutex over ITS files (711841c55, operator ruling 2026-10-28), so only an overlapping F is held, and `f_owns` sets a disjoint one for the twin."""
    fix.brief_now()
    fix.hand_now()
    e = write_plan(fix, "e", conc="exclusive -- regenerates every golden file")
    f = write_plan(fix, "f", owns=f_owns)
    mk_sub(fix, W1, "general-purpose", 0, prompt="Plan: %s" % e)
    plant_lease(fix, "e2000001", W1, text=linked(e, "regenerate goldens"))
    for i in range(queued):
        plant_lease(
            fix,
            "f200000%d" % i,
            "queue",
            lease_age_min=queue_age_min,
            text=linked(f, "held %d" % i),
        )
    if unheld:
        plant_lease(fix, "e2000002", "queue", lease_age_min=20, text=linked(e, "startable"))


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


def test_c1_every_queued_item_held_allows_and_the_judge_is_never_called(wl):
    saturated(wl)
    capturing_judge(wl, CONTINUE)
    got = stop(wl)
    assert got.decision == "allow", wl.why("c1", "allow", got, "CONCURRENCY-SATURATED WAIT")
    assert "CONCURRENCY-SATURATED WAIT: 1 writer(s) live" in got.out, got.out[:900]
    assert "all 3 queued item(s) are held by a live plan (PLAN-e.md)" in got.out, got.out[:900]
    for needle in ("GONE QUIET", "Do the next action", "QUEUED WORK NOTHING HOLDS"):
        assert needle not in got.out, "c1: %r still pushed: %s" % (needle, got.out[:900])
    assert not (wl.base / "prompt.txt").exists(), "c1: the judge was consulted in the wait"


def test_c1_control_one_unheld_queued_item_blocks_and_names_it(wl):
    saturated(wl, unheld=True)
    capturing_judge(wl, CONTINUE)
    got = stop(wl)
    assert got.decision == "block", wl.why("c1-control", "block", got, "QUEUED WORK NOTHING HOLDS")
    assert "QUEUED WORK NOTHING HOLDS" in got.out, got.out[:900]
    assert "start #e2000002." in got.out, got.out[:900]
    assert "held back: #f2000000" in got.out, got.out[:1500]
    assert "CONCURRENCY-SATURATED WAIT" not in got.out, got.out[:900]


def test_c2_an_open_item_breaks_the_wait(wl):
    saturated(wl)
    wl.add_item("- [ ] (deadbeef) a plain open item the lead could do now")
    got = stop(wl)
    assert got.decision == "block", wl.why("c2", "block", got, "open item")
    assert "CONCURRENCY-SATURATED WAIT" not in got.out, got.out[:800]


def test_c3_the_late_band_with_no_state_doc_keeps_the_state_demand(wl):
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
    assert early.decision == "allow", wl.why(
        "c3-early", "allow", early, "CONCURRENCY-SATURATED WAIT"
    )


def test_c4_a_lease_on_a_finished_worker_still_blocks(wl):
    saturated(wl)
    mk_sub(wl, "a1000000000000009", "general-purpose", 30, last="end_turn", running=False)
    plant_lease(wl, "dead1", "a1000000000000009")
    got = stop(wl)
    assert got.decision == "block", wl.why("c4", "block", got, "LEASED TO A FINISHED WORKER")
    assert "LEASED TO A FINISHED WORKER" in got.out, got.out[:900]


def test_c5_an_expired_default_still_executes(wl):
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


def test_c7_control_a_queue_lease_no_plan_holds_is_not_renewed(wl):
    """The twin of c12: a queue lease near expiry on an item of plan F, disjoint from the live exclusive E, is held by nothing and left to expire (queue-slot names it instead). A planless item would be held: E's mutex refuses a planless writer."""
    saturated(wl, queued=0, f_owns="src/f/**")
    with wl.events.open("a", encoding="utf-8") as fh:
        for ev in (
            {
                "ev": "add",
                "id": "qx",
                "at": stamp(100),
                "by": wlfix.ME,
                "s": " ",
                "o": wlfix.ME,
                "t": linked("PLAN-f.md", "queued"),
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
    assert verdict(wl)["queue_start"] == ["qx"], "c7-control: qx is not the unheld queue item"
    stop(wl)
    renewed = [
        e for e in all_events(wl) if e.get("id") == "qx" and "auto-renew" in str(e.get("note", ""))
    ]
    assert not renewed, "c7-control: a queue lease no plan holds was renewed: %s" % renewed


def test_c8_the_quiet_ladder_never_fires_on_a_queue_lease(wl):
    """Unheld too: a queue lease has no worker that can go quiet (step 1)."""
    saturated(wl, queued=1, queue_age_min=95, unheld=True)
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
    # wl_prscope reaches plan_gate and commit_policy at its copy's parents[2] / "rediacc_hooks"; link the real package there, or the loop state fails to resolve in the copy and every mutated stop runs off the loop.
    pkg = hooks.parent / "rediacc_hooks"
    if not pkg.exists():
        pkg.symlink_to(wlfix.STOP_DIR.parents[1] / "rediacc_hooks")


def test_m1_without_roster_dead_in_the_keep_list_a_dead_lease_stands_down(wl):
    saturated(wl)
    mk_sub(wl, "a1000000000000009", "general-purpose", 30, last="end_turn", running=False)
    plant_lease(wl, "dead1", "a1000000000000009")
    mutated_hook(wl, "wl_standdown.py", '        "roster-dead",\n', "")
    got = stop(wl)
    assert "LEASED TO A FINISHED WORKER" not in got.out, (
        "m1: the c4 case does not depend on the keep-list entry"
    )
    assert got.decision == "allow", "m1: expected the mutated wait to allow: %s" % got.out[:400]


def test_m2_without_defer_expired_in_the_keep_list_an_expired_default_stands_down(wl):
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
    mutated_hook(wl, "wl_standdown.py", "        _DEFER_EXPIRED,\n", "")
    got = stop(wl)
    assert got.decision == "allow", (
        "m2: the c5 case does not depend on the keep-list entry: %s" % got.out[:400]
    )


def test_m3_without_the_late_band_read_the_compaction_case_stands_down(wl):
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


def test_m4_without_the_open_items_term_an_open_item_stands_down(wl):
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


def test_c11_control_a_disjoint_plan_is_not_held_and_its_queue_is_named(wl):
    """The overlap rule's twin of c1 (711841c55): F disjoint from the live exclusive E holds nothing, so the queue is startable."""
    saturated(wl, queued=2, queue_age_min=30, f_owns="src/f/**")
    v = verdict(wl)
    assert v["queue_conc_held"] == [], v["queue_conc_held"]
    assert v["queue_start"] == ["f2000000", "f2000001"], v["queue_start"]


def test_c11_the_verdict_says_every_queued_item_is_held(wl):
    saturated(wl, queued=2, queue_age_min=30)
    v = verdict(wl)
    assert [i for i, _why in v["queue_conc_held"]] == ["f2000000", "f2000001"], v
    assert v["queue_start"] == [], v
    assert v["queued"] == 2, v


def test_m6_without_the_concurrency_term_the_held_queue_is_judged_again(wl):
    saturated(wl)
    # The world's plans carry open boxes, so the STATE.md must name a big piece or the `bigpieces` drift check blocks before the judge is reached (agent/plans/PLAN-stop-hook-rulings-campaign.md section 5).
    body = wlfix.STATE_BODY.replace(
        "none: the fixture project carries no plan with an open box.", "- PLAN-e.md"
    )
    assert wl.cli("--state", wlfix.ME, stdin=body).rc == 0
    capturing_judge(wl, CONTINUE)
    mutated_hook(
        wl,
        "wl_roster.py",
        "    return concurrency_saturated(verdict)\n",
        "    return False\n",
    )
    got = stop(wl)
    assert "CONCURRENCY-SATURATED WAIT" not in got.out, "m6: c1 does not depend on the term"
    assert (wl.base / "prompt.txt").exists(), "m6: with the wait off, the judge should be consulted"


def test_c12_a_held_queue_lease_renews(wl):
    """It waits on the holder, not on the lead: letting it expire into an open item would demand a start the spawn guard refuses."""
    saturated(wl, queued=2, queue_age_min=30)
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
