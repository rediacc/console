"""Focus mode: agent/plans/PLAN-stop-hook-focus-mode.md section 9, the Stop-hook half.

THE SPAWN HALF IS GONE. block_focus_spawn, with its cases f3 and m5 and the spawn assertions of f4, f5 and m2, was deleted in PLAN-simple-two-tree-loop B1. This file stays because test_wl_loop_next, test_wl_pr_scope_stop and test_wl_turbo_ci_red import its fixtures (`world`, `stop`, `merged_nodes`, `focus_on`, `focus_off`, `CI_RED`, `PLAN_PAD`); it goes with `--phase` itself (B10), once those fixtures move.

Operator order, 2026-09-25 (spec Y), of which the Stop-hook part is pinned here: "Finish, don't start ... Tests: focus on silences a plan-box push, keeps a CI-red block, and refuses a spawn; focus off restores all three."

EVERY FIRE CASE HAS ITS INVERSE, differing by one planted fact (focus on or off, a PR token present or absent, the late band or the early one), and the mutation controls at the end remove one branch in a PRIVATE COPY of the hook (docs/agent-reference/TRAPS.md) and show the case stops detecting it.
"""

from __future__ import annotations

import datetime
import json
import re

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.test_wl_cap_wait import (
    CONTINUE,
    band_env,
    load_standdown,
    mutated_hook,
    producer_source,
    saturated,
)
from rediacc_hooks.tests.test_wl_cap_wait import stop as cap_stop
from rediacc_hooks.tests.test_wl_ci_status import (
    CI_FRESH_PAYLOAD,
    CI_JOB_PAYLOAD,
    ci_job,
    write_exec,
)
from rediacc_hooks.tests.test_wl_ci_status import ci_rollup as ci_status_rollup
from rediacc_hooks.tests.test_wl_judge_fixset_scope import capturing_judge

ME = wlfix.ME
SAID = "working the PR\n\n## Remaining\n- the PR"
ADOPTED = "WAS ADOPTED BY THIS SESSION"
CI_RED = "CI IS RED ON PR #543"

PLAN_PAD = "Context paragraph that exists only so this fixture clears the minimum plan length and is read at all by the plan parser. "
ADOPTED_PLAN = """# PLAN: focus fixture
Status: ready
Owner: deadbeef (adopted from cafe1234 2026-09-20)
Depends-On: no-dep

%s

## Tasks

- [ ] Rewrite the alpha subsystem onto the shared helper in one commit
- [ ] Regenerate the beta baseline with the audited token
""" % (PLAN_PAD * 3)

# The gh shim: the one PR read (wl_ci.pr_link, which focus_pr_end reads through) ahead of the rollup, both from files so a case can swap them.
GH_SHIM = """#!/bin/bash
for a in "$@"; do
    case "$a" in
        *lastEditedAt*) cat "%(base)s/ci-fresh.json"; exit 0 ;;
        *'states:[OPEN,MERGED,CLOSED]'*) cat "%(base)s/ci-merged.json"; exit 0 ;;
        query=*) cat "%(base)s/ci-rollup.json"; exit 0 ;;
    esac
done
case "$*" in
    *actions/jobs/*) cat "%(base)s/ci-job.json"; exit 0 ;;
esac
echo '{}'
"""


def stamp(minutes_ago: float = 0.0) -> str:
    t = datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=minutes_ago)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def merged_nodes(fix, nodes: list[dict]) -> None:
    body = {"data": {"repository": {"pullRequests": {"nodes": nodes}}}}
    (fix.base / "ci-merged.json").write_text(json.dumps(body) + "\n", encoding="utf-8")
    fix.stem(".prlink-%s" % ME).unlink(missing_ok=True)


def world(fix, ci: bool = False, red: bool = False) -> None:
    """The fixture: fresh brief and handover, the gh shim, and optionally a git repo whose origin/pub PR #543 has a red job."""
    if ci:
        fix.git("init", "-q", "-b", "main")
        fix.git("config", "user.email", "t@t")
        fix.git("config", "user.name", "t")
        fix.git("remote", "add", "origin", wlfix.FAKE_ORIGIN)
        (fix.proj / "a.txt").write_text("a\n", encoding="utf-8")
        fix.git("add", "-A")
        fix.git("commit", "-qm", "base")
        head = fix.git("rev-parse", "HEAD").stdout.strip()
        fix.git("update-ref", "refs/remotes/origin/pub", head)
    fix.brief_now()
    fix.hand_now()
    (fix.base / "ci-fresh.json").write_text(json.dumps(CI_FRESH_PAYLOAD) + "\n", encoding="utf-8")
    (fix.base / "ci-job.json").write_text(json.dumps(CI_JOB_PAYLOAD) + "\n", encoding="utf-8")
    merged_nodes(fix, [])
    write_exec(fix.base / "binonly" / "gh", GH_SHIM % {"base": fix.base})
    if red:
        ci_status_rollup(fix, "FAILURE", "[%s]" % ci_job("Quality / Static", "FAILURE"))
    elif ci:
        ci_status_rollup(fix, "SUCCESS", "[%s]" % ci_job("Quality / Static", "SUCCESS"))


def adopted_plan(fix) -> None:
    path = fix.proj / "agent" / "plans" / "PLAN-fx.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ADOPTED_PLAN, encoding="utf-8")


def focus_on(fix, mode: str = "babysit", pr: str | None = "543") -> wlfix.Result:
    argv = ["--phase", ME, mode, "--branch", "pub"] + (["--pr", pr] if pr else [])
    got = fix.cli(*argv)
    assert got.rc == 0, "--phase failed: %s %s" % (got.out, got.err)
    return got


def focus_off(fix) -> wlfix.Result:
    got = fix.cli("--phase", ME, "build")
    assert got.rc == 0, "--phase build failed: %s %s" % (got.out, got.err)
    return got


def stop(fix, extra: dict | None = None, judge: bool = False) -> wlfix.Result:
    """A Stop with the gh shim on PATH and WORKLIST_PUBLISH_REF UNSET: only focus can arm the CI read."""
    env = dict(extra) if extra and "CTX_BAND_STATE_DIR" in extra else band_env(fix, 0)
    env.update(extra or {})
    env["PATH"] = "%s:%s" % (fix.base / "binonly", fix.env.get("PATH", ""))
    fix.say(SAID)
    if judge:
        return fix.runj(env)
    return fix.run(env)


def added_id(result) -> str:
    found = re.search(r"added #([0-9a-f]+)", result.out)
    assert found, "--add produced no id: %s %s" % (result.out[:200], result.err[:200])
    return found.group(1)


def focus_events(fix) -> list[dict]:
    return [
        json.loads(line)
        for line in fix.wl_events().splitlines()
        if line.strip() and '"phase"' in line and json.loads(line).get("ev") == "phase"
    ]


def state_doc(fix) -> dict:
    path = fix.stem(".state-%s.json" % ME)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def write_state_doc(fix, doc: dict) -> None:
    fix.stem(".state-%s.json" % ME).write_text(json.dumps(doc), encoding="utf-8")


# ---- f1: a plan-box push ---------------------------------------------------------------


def test_f1_focus_silences_a_plan_box_push(wl):
    world(wl)
    adopted_plan(wl)
    focus_on(wl)
    got = stop(wl)
    assert got.decision == "allow", wl.why("f1", "allow", got, "PHASE ")
    assert "PHASE babysit (PR #543" in got.out, got.out[:800]
    assert ADOPTED not in got.out, got.out[:800]


def test_f1_control_no_focus_blocks(wl):
    world(wl)
    adopted_plan(wl)
    got = stop(wl)
    assert got.decision == "block", wl.why("f1-control", "block", got, ADOPTED)
    assert ADOPTED in got.out, got.out[:800]


# ---- f2: a CI-red block ----------------------------------------------------------------


def test_f2_focus_keeps_a_ci_red_block(wl):
    world(wl, ci=True, red=True)
    focus_on(wl)
    got = stop(wl)
    assert got.decision == "block", wl.why("f2", "block", got, CI_RED)
    assert CI_RED in got.out, got.out[:900]


def test_f2_control_no_focus_no_ref_is_silent(wl):
    world(wl, ci=True, red=True)
    got = stop(wl)
    assert "CI IS RED" not in got.out, got.out[:900]


# ---- f4: focus off restores both --------------------------------------------------


def test_f4_focus_off_restores_both(wl):
    world(wl, ci=True, red=True)
    adopted_plan(wl)
    focus_on(wl)
    focused = stop(wl)
    assert CI_RED in focused.out, focused.out[:900]
    assert ADOPTED not in focused.out, focused.out[:900]
    focus_off(wl)
    ci_status_rollup(wl, "FAILURE", "[%s]" % ci_job("Quality / Static", "FAILURE"))
    wl.newturn()
    got = stop(wl, {"WORKLIST_PUBLISH_REF": "pub"})
    assert got.decision == "block", wl.why("f4", "block", got, ADOPTED)
    assert ADOPTED in got.out, got.out[:1500]
    assert CI_RED in got.out, got.out[:1500]
    assert "PHASE ENDED (operator)" in got.out, got.out[-1500:]
    assert "plan-adopted" in got.out.split("PHASE ENDED (operator)", 1)[1], got.out[-1500:]


# ---- f5: the PR merging ends focus -----------------------------------------------------


def test_f5_merge_auto_ends_focus(wl):
    world(wl, ci=True)
    focus_on(wl)
    stop(wl)  # a focused stop records what it parked
    merged_nodes(
        wl, [{"number": 543, "state": "MERGED", "mergedAt": stamp(-1), "closedAt": stamp(-1)}]
    )
    wl.newturn()
    got = stop(wl)
    offs = [e for e in focus_events(wl) if e.get("mode") == "build"]
    assert offs, focus_events(wl)
    assert offs[-1].get("why") == "merged", focus_events(wl)
    assert "PHASE ENDED (merged)" in got.out, got.out[-1200:]


def test_f5_control_no_merge_focus_stays(wl):
    world(wl, ci=True)
    focus_on(wl)
    stop(wl)
    wl.newturn()
    got = stop(wl)
    assert not [e for e in focus_events(wl) if e.get("mode") == "build"], focus_events(wl)
    assert "PHASE " in got.out, got.out[:800]


# ---- f6: the judge is skipped ----------------------------------------------------------


def deferral_world(fix) -> None:
    """Something remains (a justified, young `[?]`) and no static check blocks, so only the judge could speak."""
    world(fix)
    ident = added_id(fix.cli("--add", ME, "keep the legacy flag"))
    got = fix.cli(
        "--defer",
        ME,
        ident,
        "keep the flag? DEFAULT: keep it WHY: an operator call on a public flag "
        "HOW: the operator answers yes or no",
    )
    assert got.rc == 0, got.err


def test_f6_judge_skipped(wl):
    deferral_world(wl)
    focus_on(wl)
    capturing_judge(wl, CONTINUE)
    got = stop(wl, judge=True)
    assert not (wl.base / "prompt.txt").exists(), "f6: the judge ran in focus: %s" % got.out[:600]
    assert got.decision == "allow", wl.why("f6", "allow", got, "PHASE ")


def test_f6_control_focus_off_judge_runs(wl):
    deferral_world(wl)
    capturing_judge(wl, CONTINUE)
    got = stop(wl, judge=True)
    assert (wl.base / "prompt.txt").exists(), "f6-control: judge not consulted: %s" % got.out[:600]


# ---- f7: advisories are batched --------------------------------------------------------


def plant_advisories(fix, batch_age_min: float | None) -> None:
    doc = state_doc(fix)
    q = doc.setdefault("outq", {"seq": 0, "items": [], "shown": {}})
    q.setdefault("items", [])
    q.setdefault("shown", {})
    for i in range(4):
        q["items"].append(
            {
                "key": "held-%d" % i,
                "prio": 2,
                "sticky": False,
                "sig": "s%d" % i,
                "text": "HELD ADVISORY %d" % i,
                "at": stamp(1),
                "seq": 100 + i,
            }
        )
    q["items"].append(
        {
            "key": "unread-reports",
            "prio": 1,
            "sticky": False,
            "sig": "u",
            "text": "UNREAD REPORT WAITING",
            "at": stamp(1),
            "seq": 110,
        }
    )
    if batch_age_min is not None:
        doc.setdefault("standdown", {})["batch_at"] = stamp(batch_age_min)
    write_state_doc(fix, doc)


def test_f7_advisories_batched(wl):
    world(wl)
    focus_on(wl)
    stop(wl)  # seeds the standdown doc and its batch clock
    plant_advisories(wl, None)
    wl.newturn()
    got = stop(wl)
    assert got.decision == "allow", wl.why("f7", "allow", got, "PHASE ")
    assert "UNREAD REPORT WAITING" in got.out, got.out[:900]
    assert "HELD ADVISORY" not in got.out, got.out[:900]
    assert "4 advisory(ies) held" in got.out, got.out[:900]
    # The batch comes due: every held advisory is named on one line each.
    doc = state_doc(wl)
    doc["standdown"]["batch_at"] = stamp(31)
    write_state_doc(wl, doc)
    wl.newturn()
    due = stop(wl)
    for i in range(4):
        assert "HELD ADVISORY %d" % i in due.out, due.out[:1200]


# ---- f8: the PR's own fix work still blocks --------------------------------------------


def test_f8_pr_linked_item_still_blocks(wl):
    world(wl)
    focus_on(wl)
    wl.cli("--add", ME, "fix the red static job pr:543/fix")
    got = stop(wl)
    assert got.decision == "block", wl.why("f8", "block", got, "fix the red static job")
    assert "fix the red static job" in got.out, got.out[:900]


def test_f8_control_unlinked_item_allows(wl):
    world(wl)
    focus_on(wl)
    wl.cli("--add", ME, "an unrelated plan box")
    got = stop(wl)
    assert got.decision == "allow", wl.why("f8-control", "allow", got, "PHASE ")
    assert "an unrelated plan box" not in got.out, got.out[:900]


# ---- f9: STATE.md near compaction ------------------------------------------------------


def test_f9_compaction_near_keeps_state_demand(wl):
    world(wl)
    focus_on(wl)
    wl.cli("--add", ME, "a parked plan box")  # STATE.md is demanded only while something remains
    wl.state_file().unlink()
    late = stop(wl, band_env(wl, 1))
    assert late.decision == "block", wl.why("f9", "block", late, "phase is on")
    assert "Kept although a wind-down phase is on" in late.out, late.out[:900]


def test_f9_control_early_band_allows(wl):
    world(wl)
    focus_on(wl)
    wl.cli("--add", ME, "a parked plan box")
    wl.state_file().unlink()
    early = stop(wl, band_env(wl, 0))
    assert early.decision == "allow", wl.why("f9-control", "allow", early, "PHASE ")


# ---- f10: compaction keeps an active focus ---------------------------------------------


def test_f10_compaction_keeps_active_focus(wl):
    world(wl)
    focus_on(wl)
    assert wl.cli("--compact").rc == 0
    got = wl.cli("--phase", ME)
    assert "phase: babysit, PR #543 on pub" in got.out, got.out
    focus_off(wl)
    assert wl.cli("--compact").rc == 0
    assert not focus_events(wl), "an ended focus was re-emitted: %s" % focus_events(wl)
    assert "no wind-down to end" in wl.cli("--phase", ME).out


# ---- f11: a queue lease under focus ----------------------------------------------------


def test_f11_queue_lease_accepted_in_focus(wl):
    world(wl)
    ident = added_id(wl.cli("--add", ME, "parked writer work"))
    refused = wl.cli("--lease", ME, ident, "+60", "worker:queue")
    assert refused.rc != 0, refused.out
    assert "worker:queue is only for" in refused.err, refused.err
    focus_on(wl)
    got = wl.cli("--lease", ME, ident, "+60", "worker:queue")
    assert got.rc == 0, got.err


# ---- f12: the 24-hour cap --------------------------------------------------------------


def test_f12_expiry_ends_focus(wl):
    world(wl)
    old = stamp(25 * 60)
    with wl.events.open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ev": "phase",
                    "at": old,
                    "by": ME,
                    "o": ME,
                    "mode": "babysit",
                    "branch": "pub",
                    "pr": 543,
                    "why": "operator",
                }
            )
            + "\n"
        )
    write_state_doc(
        wl,
        {"standdown": {"focus_at": old, "mode": "babysit", "pr": 543, "parked": {"open-items": 3}}},
    )
    got = stop(wl)
    assert "PHASE ENDED (expired)" in got.out, got.out[-900:]
    assert "open-items x3" in got.out, got.out[-900:]
    offs = [e for e in focus_events(wl) if e.get("mode") == "build"]
    assert offs, focus_events(wl)
    assert offs[-1]["why"] == "expired", focus_events(wl)


def test_f12_control_fresh_focus_stays(wl):
    world(wl)
    focus_on(wl)
    got = stop(wl)
    assert "PHASE ENDED" not in got.out, got.out[-900:]
    assert "PHASE " in got.out, got.out[:600]


# ---- f13: static -----------------------------------------------------------------------


def test_f13_profiles_keys_have_producers():
    """Every kept key in every profile has a producer outside wl_standdown.py, and every key's one-per-line set entry (the shape each mutation control removes) occurs exactly once in it."""
    mod = load_standdown()
    src = producer_source()
    own = (wlfix.STOP_DIR / "wl_standdown.py").read_text(encoding="utf-8")
    missing: list[str] = []
    repeated: list[str] = []
    for prof in mod.PROFILES:
        for k in sorted(prof.keeps | prof.always_keeps | prof.compaction_keys):
            if not re.search(r"""["']%s["']""" % re.escape(k), src):
                missing.append("%s:%s" % (prof.name, k))
            line = '        "%s",\n' % k
            # Two keys are kept by several profiles and named once through a constant instead: pr-finish (_PR_FINISH) and defer-expired (_DEFER_EXPIRED, whose one set-entry line is checked below).
            if k not in ("pr-finish", "defer-expired") and own.count(line) != 1:
                repeated.append("%s (x%d)" % (k, own.count(line)))
    assert not missing, "kept keys with no producer: %s" % missing
    assert not repeated, "key literals not exactly once in wl_standdown.py: %s" % sorted(
        set(repeated)
    )
    assert own.count('_DEFER_EXPIRED = "defer-expired"\n') == 1
    assert own.count("        _DEFER_EXPIRED,\n") == 1
    assert mod.FOCUS is not mod.CAP_WAIT
    assert mod.PR_LOOP in mod.PROFILES
    assert "defer-expired" in mod.PR_LOOP.keeps
    assert "defer-expired" in mod.CAP_WAIT.keeps
    assert "pr-finish" in mod.FOCUS.keeps
    assert "pr-finish" in mod.CAP_WAIT.always_keeps
    assert "pr-finish" not in mod.CAP_WAIT.keeps


def test_f13_standdown_is_pure():
    """Sealed and stdlib-only: no environment read, no sibling import."""
    src = (wlfix.STOP_DIR / "wl_standdown.py").read_text(encoding="utf-8")
    assert "os.environ" not in src
    assert "getenv" not in src
    imports = re.findall(r"^(?:import|from) (\w+)", src, re.MULTILINE)
    assert set(imports) <= {"datetime", "re", "typing"}, imports


# ---- f14: the cap wait keeps the pr-finish hook-bug branch -----------------------------


FORCE_PRF = ("        _prf_info = None\n", "        _prf_info = 1 / 0\n")


def test_f14_cap_wait_keeps_pr_finish_hook_bug(wl):
    saturated(wl)
    mutated_hook(wl, "wl_checks.py", *FORCE_PRF)
    got = cap_stop(wl)
    assert got.decision == "block", wl.why("f14", "block", got, "finish-line check failed")
    assert "the pr-babysit finish-line check failed" in got.out, got.out[:900]


# ---- mutation controls: each removed in a PRIVATE COPY makes its case stop detecting ----


def test_m1_without_ci_red_in_focus_a_red_pr_stands_down(wl):
    world(wl, ci=True, red=True)
    focus_on(wl)
    mutated_hook(wl, "wl_standdown.py", '        "ci-red",\n', "")
    got = stop(wl)
    assert CI_RED not in got.out, "m1: f2 does not depend on the keep entry"
    assert got.decision == "allow", "m1: expected the mutated focus to allow: %s" % got.out[:400]


def test_m2_without_the_store_read_focus_is_off(wl):
    world(wl)
    adopted_plan(wl)
    focus_on(wl)
    mutated_hook(
        wl,
        "wl_standdown.py",
        '    if best is None or best.get("mode") not in PHASE_MODES:\n',
        "    if True:\n",
    )
    got = stop(wl)
    assert got.decision == "block", "m2: f1 does not depend on the read: %s" % got.out[:400]
    assert ADOPTED in got.out, got.out[:800]


def test_m3_without_the_judge_skip_the_judge_runs(wl):
    deferral_world(wl)
    focus_on(wl)
    capturing_judge(wl, CONTINUE)
    # The live `if` line is read from the source, so the pin follows however `wl_judge.disabled(...)` is spelled at the site.
    live = next(
        ln + "\n"
        for ln in (wlfix.STOP_DIR / "wl_checks.py").read_text(encoding="utf-8").splitlines()
        if ln.startswith("    if (something_remains or reg_signals) and not wl_judge.disabled(")
        and ln.endswith(" and not _in_standdown:")
    )
    mutated_hook(wl, "wl_checks.py", live, live.replace(" and not _in_standdown", ""))
    stop(wl, judge=True)
    assert (wl.base / "prompt.txt").exists(), "m3: f6 does not depend on the judge-site skip"


def test_m4_without_the_drain_filter_every_advisory_shows(wl):
    world(wl)
    focus_on(wl)
    stop(wl)
    plant_advisories(wl, None)
    mutated_hook(wl, "wl_checks.py", ", only=_drain_only)", ")")
    wl.newturn()
    got = stop(wl)
    assert "HELD ADVISORY" in got.out, "m4: f7 does not depend on the drain filter"


def test_m6_without_the_merge_read_focus_does_not_end(wl):
    world(wl, ci=True)
    focus_on(wl)
    stop(wl)
    merged_nodes(
        wl, [{"number": 543, "state": "MERGED", "mergedAt": stamp(-1), "closedAt": stamp(-1)}]
    )
    mutated_hook(
        wl,
        "wl_ci.py",
        '    branch = str((focus or {}).get("branch") or "")\n    if not branch:\n        return "", ""\n',
        '    return "", ""\n',
    )
    wl.newturn()
    got = stop(wl)
    assert "PHASE ENDED" not in got.out, "m6: f5 does not depend on focus_pr_end"
    assert not [e for e in focus_events(wl) if e.get("mode") == "build"]


def test_m7_without_focus_pr_items_the_fix_work_parks(wl):
    world(wl)
    focus_on(wl)
    wl.cli("--add", ME, "fix the red static job pr:543/fix")
    mutated_hook(wl, "wl_standdown.py", '        "focus-pr-items",\n', "")
    got = stop(wl)
    assert got.decision == "allow", "m7: f8 does not depend on the keep entry: %s" % got.out[:400]


def test_m8_without_the_always_keep_the_cap_wait_hides_a_hook_bug(wl):
    """f14's inverse: the pre-fix cap wait (no always-tier keep) stood the HOOK BUG branch down."""
    saturated(wl)
    mutated_hook(wl, "wl_checks.py", *FORCE_PRF)
    std = wl.hook.parent / "wl_standdown.py"
    src = std.read_text(encoding="utf-8")
    old = '"cap-wait", CORE | _CAP_WAIT_ONLY, PREFIXES, frozenset({_PR_FINISH}), COMPACTION_KEYS'
    assert src.count(old) == 1, "MUTATION FIXTURE BROKEN"
    std.write_text(
        src.replace(
            old, '"cap-wait", CORE | _CAP_WAIT_ONLY, PREFIXES, frozenset(), COMPACTION_KEYS'
        ),
        encoding="utf-8",
    )
    got = cap_stop(wl)
    assert "finish-line check failed" not in got.out, "m8: f14 does not depend on always_keeps"
    assert got.decision == "allow", got.out[:400]
