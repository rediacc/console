"""Ported from `.claude/hooks/stop/worklist-cases/22-plan-fidelity.sh`.

Plan-drift binding, unknown-plan orientation, `--intent`, the brief work-gate, `--update` carry, the reggate probes, and Tier-2 plan fidelity.

THE 2026-08-19 INCIDENT drove the last group end to end through the real hook: an operator approved a plan with several discrete tasks and the session tracked it as two umbrella items ("www round 4 Wave A", "www round 4 Waves B-D"), which leaves the open-item gate unable to tell one task from twenty. Every case there carries its own control, and 220c is the one that matters most:
the shim still says "unfaithful" and the check must stay SILENT because no plan was ever approved. Without it, a passing 220 would only prove that a canned answer can be printed.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import tempfile
import time

from rediacc_ci import runtmp

from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

PLAN_EXECUTING = "# PLAN: the thing\nStatus: executing\n"
PLAN_DONE = "# PLAN: the thing\nStatus: done\n"

PLAN_MYSTERY = """# PLAN: the mystery subject

**Status (dated parenthetical): this shape does not parse**

The work lives in pkg/chunkstore/pipeline_linux.go and pkg/chunkstore/pipeline_linux.go
again, plus cmd/renet/backup_snapshot.go. A passing mention of docs/agent-reference/ci-gates.md.
"""

PLAN_MYSTERY_READABLE = """# PLAN: the mystery subject
Status: executing

The work lives in pkg/chunkstore/pipeline_linux.go.
"""

FIXTURE_PLAN = """# round 4: the page frame, the voice, and a docs surface

## Context

Round 3 shipped and is on the open PR. This round is the operator's next pass,
and the decisions below are locked by them.

## Waves

### Wave A: the page frame

- The nav container gains a 1280px max-width and 80px gutters.
- The footer background goes black, full bleed, matching the header container.
- Both menus are rebuilt on the native popover API, deleting the hover timers.
- One backdrop rule dims the page behind the popup and both menus.

### Wave B: the solution-page bottom

- Move the two download sections adjacent and pair them in one two-column row.
- The row must degrade to one column when the gated button is absent.
- New sources component: a native details element rendering the reference items.
- Callouts lose only their source line.

### Wave C: the voice

1. Rewrite English second person to imperative across the solution pages.
2. Regenerate the translation hashes and re-naturalize only the changed delta.
"""

DECOMPOSED_TASKS = (
    "r4-A1 nav container 1280px max-width and 80px gutters",
    "r4-A2 footer background black, full bleed, matching container",
    "r4-A3 rebuild both menus on the native popover API",
    "r4-A4 one backdrop rule dims the page behind popup and menus",
    "r4-B1 move the two download sections adjacent to each other",
    "r4-B2 the row degrades to one column when the gated button is absent",
    "r4-B3 new sources component using a native details element",
    "r4-B4 callouts lose only their source line",
    "r4-C1 rewrite English second person to imperative on solution pages",
    "r4-C2 regenerate hashes and re-naturalize only the changed delta",
)

PLAN_PAD = "Context paragraph that exists only so this fixture clears the minimum plan length and is read at all by the plan parser. "

ADOPTED_PLAN = """# PLAN: adopted work
Status: ready
Owner: deadbeef (adopted from cafe1234 2026-09-20)
Updated: 2026-09-20

%s

## Tasks

- [ ] Rewrite the alpha subsystem onto the shared helper in one commit
- [ ] Regenerate the beta baseline with the audited token
- [ ] Delete the gamma shim once nothing imports it
""" % (PLAN_PAD * 3)

OWNED_PLAN = ADOPTED_PLAN.replace(
    "Owner: deadbeef (adopted from cafe1234 2026-09-20)", "Owner: deadbeef"
).replace("# PLAN: adopted work", "# PLAN: owned work")


def added_id(result) -> str:
    found = re.search(r"added #([0-9a-f]+)", result.out)
    assert found, "--add produced no id: %s" % result.out[:200]
    return found.group(1)


def plan_file(fix, name: str, body: str, minutes_ago: float = 0) -> pathlib.Path:
    path = fix.proj / "agent" / ("PLAN-%s.md" % name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    if minutes_ago:
        old = time.time() - minutes_ago * 60
        os.utime(path, (old, old))
    return path


def tick_n(fix, count: int, plan: str, label: str = "work %d that outran the plan") -> None:
    """A TICKED item, deliberately.

    Each item NAMES ITS PLAN (`PLAN-<plan>.md`), because plan_drift_rows counts only this plan's work: a session driving several plans must not see each flagged by work on the others. The fixture predated that scoping and named no plan, so 215 and 216 could never fire and failed on every tree (found 2026-09-24; the poll-backoff advisory had been the only output of those stops).

    It stamps `upd` (which is what a session's own work moving reads) without leaving anything open, so plan-drift is the ONLY rotating check outstanding. The focused block surfaces exactly one of those, so an open item here would win the rotation and the case would score whichever check happened to be picked, which is how its first version passed its three controls while the
    thing they
    control for never fired at all.

    FOUR ticked items, not one: the check requires a THRESHOLD of moved work (PLAN_DRIFT_MIN_MOVES) rather than any movement at all, because a single tick is not a plan going stale, and treating it as one made the check unsatisfiable (update the plan, tick the next item, stale again immediately).
    """
    for index in range(1, count + 1):
        ident = added_id(fix.cli("--add", wlfix.ME, "PLAN-%s.md %s" % (plan, label % index)))
        fix.cli("--tick", wlfix.ME, ident, "landed, suite green, exit 0")


def test_215_a_plan_the_work_has_moved_past_is_flagged(wl):  # noqa: F811
    """PLAN DRIFT: the session is bound to its own committed design record.

    The gap the operator named: plans were surfaced at SessionStart and PostCompact and NOWHERE else, so a session could work all day while the committed plan describing that work went stale. `plan_records()` existed; nothing on the stop path called it. The plan is backdated and the work moved after it, because the trigger is the work and never the clock: a plan a week old on a
    branch where nothing moved is accurate.
    """
    wl.say("answer\n\n## Remaining\n- stuff")
    wl.brief_now()
    wl.hand_now()
    plan_file(wl, "thing", PLAN_EXECUTING, minutes_ago=120)
    tick_n(wl, 4, "thing")
    wl.check("block", "PLAN-thing.md", "215: a plan the work has moved past is flagged")


def test_215a_one_tick_is_not_a_plan_going_stale(wl):  # noqa: F811
    """CONTROL, and the three arms chain because each rewrites the plan the one before it left.

    215a: the threshold is what makes the exit real. Without this control the check could go back to firing on any movement, which is the unsatisfiable version. 215b: without it the check could be firing on the mere existence of a plan file, which would make it noise within a day. 215c: demanding edits to history is how a check earns its way into being ignored.
    """
    wl.say("answer\n\n## Remaining\n- stuff")
    wl.brief_now()
    wl.hand_now()
    path = plan_file(wl, "thing", PLAN_EXECUTING, minutes_ago=120)
    ident = added_id(wl.cli("--add", wlfix.ME, "PLAN-thing.md one small thing"))
    wl.cli("--tick", wlfix.ME, ident, "landed, exit 0")
    assert "PLAN-thing.md" not in wl.run().out, "215a CONTROL: one tick flagged the plan"

    # 215b CONTROL: the same plan, touched AFTER the work, is silent.
    os.utime(path, None)
    wl.newturn()
    wl.say("still working\n\n## Remaining\n- stuff")
    assert "PLAN-thing.md" not in wl.run().out, "215b CONTROL: a fresh plan was still flagged"

    # 215c CONTROL: a DONE plan is history and is never flagged.
    plan_file(wl, "thing", PLAN_DONE, minutes_ago=120)
    wl.newturn()
    wl.say("still working\n\n## Remaining\n- stuff")
    assert "PLAN-thing.md" not in wl.run().out, "215c CONTROL: a done plan was flagged"


def test_215d_a_project_with_no_plan_directory_says_nothing(wl):  # noqa: F811
    wl.say("answer\n\n## Remaining\n- stuff")
    wl.brief_now()
    wl.hand_now()
    wl.add_item("- [ ] (deadbeef) work with no plan anywhere")
    assert "committed plan file" not in wl.run().out, (
        "215d CONTROL: complained about plans that do not exist"
    )


def test_216_an_unknown_plan_carries_a_description_and_file_pointers(wl):  # noqa: F811
    """An UNKNOWN status told the one reader who has no context precisely nothing: that the plan cannot be parsed, full stop. It now carries the plan's title and the files it keeps referring to, so a new or compacted session knows what to open first.

    216b CONTROL: a plan's own path is not a pointer to anywhere useful, and a file mentioned once is a passing reference rather than the subject. 216c CONTROL: the orientation is for UNKNOWN specifically, and on every row it would just be noise on plans whose state is already clear.
    """
    wl.say("answer\n\n## Remaining\n- stuff")
    wl.brief_now()
    wl.hand_now()
    plan_file(wl, "mystery", PLAN_MYSTERY, minutes_ago=120)
    tick_n(wl, 4, "mystery", "work %d")
    out = wl.run().out
    assert "the mystery subject" in out, "216: no orientation on an UNKNOWN plan: %s" % out[:320]
    assert "pkg/chunkstore/pipeline_linux.go" in out, out[:320]
    assert "PLAN-mystery.md; opens" not in out, "216b CONTROL: the plan listed itself"
    assert "opens: docs/agent-reference/ci-gates.md" not in out, (
        "216b CONTROL: a passing mention led the ranking"
    )

    plan_file(wl, "mystery", PLAN_MYSTERY_READABLE, minutes_ago=120)
    wl.newturn()
    wl.say("still working\n\n## Remaining\n- stuff")
    out = wl.run().out
    assert "PLAN-mystery.md" in out, "216c CONTROL: %s" % out[:320]
    assert "opens:" not in out, "216c CONTROL: a readable status got orientation noise"


def test_217_intent_answers_the_two_status_question_checks_and_nothing_else(wl):  # noqa: F811
    """An intent is a statement of PLAN. Its whole legitimate power is answering the checks whose entire content is what the session is doing (brief and agent-state) and reordering attention. It is never evidence.

    217b is decisive in the plan: an intent must NOT satisfy the TICK-EVIDENCE gate, because if an intent could close an item the ledger becomes a record of intentions. 217c: covered keys sort LAST but stay in `violations`, so the header count stays truthful.
    """
    wl.say("answer\n\n## Remaining\n- stuff")
    wl.hand_now()
    wl.brief_at(wlfix.ME, 200)
    wl.add_item("- [ ] (deadbeef) open thing")
    wl.check("block", "OPEN worklist item", "217: without an intent the stale brief is outstanding")
    wl.cli(
        "--intent",
        wlfix.ME,
        "driving the open thing to green",
        "--covers",
        "open-items",
        "--for",
        "60",
    )
    out = wl.run().out
    assert "session brief is stale" not in out, "217: brief still fired under a live intent"

    ident = added_id(wl.cli("--add", wlfix.ME, "needs real evidence"))
    got = wl.cli("--tick", wlfix.ME, ident, "I have an intent covering this")
    assert "REFUSED" in got.out + got.err, "217b C8: an intent satisfied the evidence gate"

    out = wl.run().out
    assert re.search(r"check\(s\) outstanding", out), (
        "217c: the outstanding count vanished under an intent"
    )


def test_217d_an_expired_intent_becomes_its_own_violation(wl):  # noqa: F811
    """This is what stops `--intent` being a mute button: going quiet has a horizon, and outliving it while the work is still open is itself the finding.

    NO open item on purpose. The focused block surfaces ONE rotating check, so an open item here would win the rotation and the case would score whichever check happened to be picked rather than the expiry.
    """
    wl.say("answer\n\n## Remaining\n- stuff")
    wl.brief_now()
    wl.hand_now()
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 90 * 60))
    wl.stem(".intents").write_text(
        json.dumps(
            {
                "at": old,
                "by": "deadbeef",
                "text": "said long ago",
                "covers": ["open-items"],
                "min": 30,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    wl.check(
        "block", "stated intent has EXPIRED", "217d: an expired intent blocks in its own right"
    )


def test_217e_an_expired_intent_covering_only_closed_work_stays_quiet(wl):  # noqa: F811
    """V_INTENT_EXPIRED tells the reader that what it covered is still outstanding, and until v18 the check never verified that. It fired live on an intent whose one covered item had been ticked WITH EVIDENCE, so the message asserted something demonstrably false. This is 217d's control: same expired intent, same horizon, and the ONLY difference is that the covered item is
    closed. 217d keeps firing because its `covers` names "open-items", which resolves to no record, and unresolvable is deliberately NOT treated as done."""
    wl.say("answer\n\n## Remaining\n- stuff")
    wl.brief_now()
    wl.hand_now()
    ident = added_id(wl.cli("--add", wlfix.ME, "the work the intent covered"))
    wl.cli("--tick", wlfix.ME, ident, "suite run green, exit 0")
    old = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 90 * 60))
    wl.stem(".intents").write_text(
        json.dumps(
            {"at": old, "by": "deadbeef", "text": "said long ago", "covers": [ident], "min": 30}
        )
        + "\n",
        encoding="utf-8",
    )
    wl.check_absent(
        "allow", "stated intent has EXPIRED", "217e: an expired intent over DONE work stays quiet"
    )


def test_210_an_old_brief_never_blocks_whether_or_not_the_world_moved(wl):  # noqa: F811
    """Rewritten 2026-09-24 when the `brief` check was deleted (agent/plans/PLAN-stop-hook-continuity.md P1.1): the hook stamps the brief itself, so neither an unchanged world nor a moved one can block on it. Before, 210b blocked with "session brief is stale" once the world moved."""
    wl.say("answer\n\n## Remaining\n- nothing open")
    wl.hand_now()
    wl.cli("--brief", wlfix.ME, "doing the thing")
    wl.brief_at(wlfix.ME, 200, "doing the thing")
    wl.check_absent("allow", "session brief", "an old brief on an unchanged world")
    wl.add_item("- [x] (deadbeef) a finished piece of work")
    wl.check_absent("allow", "session brief", "an old brief once the world has moved")


def test_218_update_on_a_deferral_carries_its_default_forward(wl):  # noqa: F811
    """The trap this pins: the rendered line carries only the MOST RECENT update, so an `--update` that omitted DEFAULT: made the deferral's default INVISIBLE, and the next stop blocked on a `[?]` that provably had one when it was written. Found live, by the session that wrote this.

    Refusing the update was the first fix and case 141 killed it: a refresh is the exit that is always available, and the aged-deferral rung tells a session to refresh. So the default is carried forward and the carry is ANNOUNCED. The defect was silence, not the exit.
    """
    ident = added_id(wl.cli("--add", wlfix.ME, "a thing needing an operator ruling"))
    wl.cli(
        "--defer",
        wlfix.ME,
        ident,
        "which way? DEFAULT: take the left fork WHY: only the operator picks HOW: they answer",
    )
    got = wl.cli("--update", wlfix.ME, ident, "made progress")
    assert got.rc == 0, "218: the refresh exit was removed (case 141 pins that it must stay)"
    assert "carried forward verbatim" in got.err, "218: the carry was silent: %s" % got.err[:200]
    assert "DEFAULT: take the left fork" in wl.cli("--list").out, "218: the default was lost"


def test_218b_an_open_item_is_untouched_by_the_deferral_default_rule(wl):  # noqa: F811
    """CONTROL: without it, 218 could pass because `--update` announces a carry for EVERYTHING. The only difference here is the item's state."""
    ident = added_id(wl.cli("--add", wlfix.ME, "ordinary open work"))
    got = wl.cli("--update", wlfix.ME, ident, "made progress")
    assert got.rc == 0, "218b: an ordinary update on an open item was rejected"
    assert "carried forward verbatim" not in got.err, (
        "218b: the [?] carry rule leaked onto an open item"
    )


def test_219_the_reggate_probe_sees_package_local_gates():
    """Nine real gates live under packages/*/scripts, because a gate about www content belongs beside www. The probe's globs once covered only scripts/gates/check-*.ts, so it answered that no new or changed check script was found at a session that had just written one under packages/www/scripts, wired its check:ci-* key and proven it with a planted defect. The only way to
    satisfy it was to move a www gate to the repo root, letting the probe dictate layout."""
    reggate = wlfix.import_wl("wl_reggate")
    assert "packages/*/scripts/check-*.ts" in reggate.CHECK_SCRIPT_GLOBS, reggate.CHECK_SCRIPT_GLOBS


def repo_root() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
    ).stdout.strip()


def test_219b_widening_the_globs_must_not_stampede_every_gate():
    """219 alone would pass on a probe that runs all 224 visible scripts at up to REGGATE_TIMEOUT_S each, a stop hook measured in tens of minutes. The probe only exercises gates the working tree TOUCHED; everything else is seeded. This control pins that discrimination, and errs toward running."""
    reggate = wlfix.import_wl("wl_reggate")
    root = repo_root()
    clean = subprocess.run(
        ["git", "ls-files", "--", "packages/www/scripts/check-tutorial-parity.ts"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert clean, "fixture missing: check-tutorial-parity.ts is not tracked"
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", clean],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert not dirty, "fixture moved: check-tutorial-parity.ts is modified in this tree"
    assert reggate._is_dirty(clean, root) is False, "an untouched gate was reported dirty"
    # And it must err toward RUNNING: a path git cannot report on is treated as touched.
    assert reggate._is_dirty(clean, "/nonexistent-repo-root") is True, (
        "a git failure must not skip a gate"
    )


def test_219c_the_reggate_accepts_a_case_on_a_surface_that_is_not_a_check_script():
    """ci.yml has six regression surfaces; the globs above see one. A fix whose home is an E2E case, an ops step, an install script or a unit test had NO acceptable answer: the only provable artifact was a static gate, which for a behavioural defect asserts that the source still looks right. The judge now names the surface and the path, and the probe checks THAT path, so a surface
    this machinery has never heard of still has a checkable answer.

    A DOTFILE PATH must resolve. The first spelling used `lstrip('./')`, which takes a character SET, so a `.claude/hooks/...` path arrived as `claude/hooks/...` and every hook-surface artifact was reported as nonexistent. The assertion is on RESOLUTION, not dirtiness: the first spelling of this control required the file to be dirty, which was true while it was being written and
    false the moment it was committed.
    """
    reggate = wlfix.import_wl("wl_reggate")
    root = repo_root()
    # A tracked, UNTOUCHED file proves nothing: the case has to have been written.
    clean = "packages/www/scripts/check-tutorial-parity.ts"
    ok, note = reggate.prove_named_artifact(root, clean)
    assert ok is False, "an untouched artifact was accepted as proof: %r" % (note,)
    assert "did not touch" in note, note
    # A path that does not exist proves nothing either.
    ok, note = reggate.prove_named_artifact(root, "packages/e2e-tests/tests/99-no-such.test.ts")
    assert ok is False, note
    assert "does not exist" in note, note
    # CONTROL: the escape hatches must not be reachable.
    for bad in ("", "   ", "../etc/passwd", "/etc/passwd"):
        ok, note = reggate.prove_named_artifact(root, bad)
        assert ok is False, "traversal or empty path accepted: %r" % (bad,)
    for spelling in (".claude/hooks/stop/wl_reggate.py", "./.claude/hooks/stop/wl_reggate.py"):
        ok, note = reggate.prove_named_artifact(root, spelling)
        assert "does not exist" not in note, "a dotfile path did not resolve: %r" % (note,)


def test_219g_a_docs_only_tick_is_banked_not_rediscovered_every_stop():
    """A real bug, found in review rather than by a control. `tick_touches_code` correctly kept a docs-only tick out of `ids` and `ticks` (so it is never asked about), but the id was then dropped ENTIRELY, never returned at all, so the caller's only bank site never saw it. A stop with only a docs-only tick and no new commit hit neither of the caller's two save branches, so
    nothing was written to disk, and the same tick was rediscovered and re-filtered on every future stop, forever."""
    reggate = wlfix.import_wl("wl_reggate")
    root = repo_root()
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()
    line = "- [x] fixed a typo in docs/agent-reference/TRAPS.md"
    items = [{"state": "x", "owner": None, "line": line, "lastnote": ""}]
    state = {"head": head, "seen_ticks": [], "fixsets": {}, "gate_runs": {}}
    _, ids, ticks, _, banked = reggate.fix_signals(root, items, "sess", state)
    assert ids == [], "a docs-only tick was asked about: %r" % (ids,)
    assert ticks == [], "a docs-only tick was asked about: %r" % (ticks,)
    tid = reggate._tick_id(line)
    assert banked == [tid], "the docs-only tick id was not banked: got %r, want [%r]" % (
        banked,
        tid,
    )
    # CONVERGENCE: once banked, the SAME tick must not reappear on the next pass.
    state["seen_ticks"] = banked
    _, _, _, _, banked2 = reggate.fix_signals(root, items, "sess", state)
    assert banked2 == [], "a banked docs-only tick was rediscovered: %r" % (banked2,)


def test_219f_a_settled_fixset_records_the_surface_it_was_routed_to():
    """Found by dogfooding, not review: sixteen settled fixsets carried no surface at all, because the judge produced one, the router used it, and the settle path dropped it. The only question worth asking of the routing, whether it is any good, was unanswerable from the record, and it had already misrouted a www DOM change to packages/e2e-tests."""
    source = (wlfix.STOP_DIR / "wl_checks.py").read_text(encoding="utf-8")
    assert '"surface": str(rg.get("surface", ""))' in source, (
        "219f: a settled fixset drops the routing, so the record cannot be audited"
    )
    assert '"artifact": str(rg.get("artifact", ""))' in source, (
        "219f: a settled fixset drops the artifact, so the record cannot be audited"
    )


def test_219e_one_fix_asked_per_stop_and_only_code_touching_ticks():
    """Every commit and every new tick of a stop used to be hashed into ONE fix-set, so a single verdict had to cover unrelated fixes. Asking per item is the operator's rule; asking about all of them at once would wall a busy stop in behind eight simultaneous demands, so the rest stay unbanked for later stops. The docs-only filter mirrors the one commits already face, and it
    FAILS TOWARD ASKING: no path is not evidence that nothing shipped."""
    reggate = wlfix.import_wl("wl_reggate")
    assert reggate.tick_touches_code("- [x] #a (me) packages/cli/src/foo.ts:12 exit 0") is True
    assert (
        reggate.tick_touches_code("- [x] #a (me) docs/agent-reference/TRAPS.md and README.md")
        is False
    )
    assert reggate.tick_touches_code("- [x] #a (me) no paths at all, exit 0") is True, (
        "a tick with no path was silently dropped"
    )
    assert (
        reggate.tick_touches_code("- [x] #a (me) docs/x.md plus packages/www/src/a.css") is True
    ), "a mixed tick was treated as docs-only"


def test_219d_a_static_gate_still_faces_the_stricter_probe():
    """CONTROL: 219c alone would pass on a machinery that let ANY touched file settle a finding, which would gut the wired-and-green requirement for check:ci-* keys. The named-artifact path is consulted only when the judge routed AWAY from `gates`; `gates` and `none` must still go through `prove_new_gate`."""
    reggate = wlfix.import_wl("wl_reggate")
    source = pathlib.Path(reggate.__file__).read_text(encoding="utf-8")
    assert "surface not in (" in source, "fence gone"
    assert "gates" in source, "fence gone"
    assert "none" in source, "fence gone"
    # The fence as ruff formats it, double quotes and all.
    assert "if surface and surface not in (" in source, (
        "the named-artifact shortcut is no longer fenced away from static gates"
    )


def shim_planfid(fix, plan_fidelity: str) -> None:
    """A canned `claude` that answers the PLAN-FIDELITY call.

    Every other call gets the ordinary `stop` verdict, because a case that turns the judge on must not make the main judge fail closed on an answer meant for someone else. Every invocation is COUNTED, which is what lets a case assert that the PREFILTER, and not the model, was the thing that stayed quiet.
    """
    script = fix.base / "binonly" / "claude"
    body = (
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        'prompt = " ".join(sys.argv[1:])\n'
        'if "DECOMPOSITION" in prompt:\n'
        '    open(%r, "a").write("call\\n")\n'
        '    out = {"is_error": False,\n'
        '           "structured_output": {"plan_fidelity": json.loads(%r)}}\n'
        "else:\n"
        '    out = {"is_error": False,\n'
        '           "structured_output": {"verdict": "stop", "reason": "ok", "next_action": "none"}}\n'
        "print(json.dumps(out))\n"
    ) % (str(fix.base / "planfid-calls"), plan_fidelity)
    script.write_text(body, encoding="utf-8")
    script.chmod(0o755)
    (fix.base / "planfid-calls").write_text("", encoding="utf-8")


def planfid_calls(fix) -> int:
    path = fix.base / "planfid-calls"
    if not path.is_file():
        return 0
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line])


def broken_judge(fix) -> None:
    """A claude that exits non-zero.

    `wl_judge` fails CLOSED on the stop verdict, and this check deliberately does not: a heuristic trigger must not become a wall when the model is unreachable. It must also not go quiet about it.
    """
    script = fix.base / "binonly" / "claude"
    script.write_text("#!/bin/bash\nexit 3\n", encoding="utf-8")
    script.chmod(0o755)


def plant_plan(fix) -> None:
    """Write the fixture plan and record its APPROVAL in the transcript."""
    path = fix.base / "plan.md"
    path.write_text(FIXTURE_PLAN, encoding="utf-8")
    fix.append_transcript(
        {
            "type": "attachment",
            "isSidechain": False,
            "attachment": {
                "type": "plan_mode_exit",
                "planFilePath": str(path),
                "planExists": True,
            },
        }
    )


def test_220_an_approved_plan_tracked_as_two_umbrella_items_blocks(wl):  # noqa: F811
    """220a rides here: the bash ran it with no `setup` of its own, so the deferral exit is asserted against the very token 220's block just printed."""
    wl.say("seeded the round")
    wl.brief_now()
    plant_plan(wl)
    first = added_id(wl.cli("--add", wlfix.ME, "www round 4 Wave A"))
    second = added_id(wl.cli("--add", wlfix.ME, "www round 4 Waves B-D"))
    # Both umbrella ids named, and ONE plan task quoted verbatim. Both kinds of evidence are verified against the artifacts before they can block; 220e is the case that proves the verification is load-bearing.
    shim_planfid(
        wl,
        json.dumps(
            {
                "faithful": False,
                "umbrella_ids": [first, second],
                "missing": ["Callouts lose only their source line."],
                "instruction": "split these into one item per plan task",
            }
        ),
    )
    out = wl.runj().out
    assert '"decision": "block"' in out, "220 FIRE: no plan-fidelity block: %s" % out[:300]
    assert "AN APPROVED PLAN IS NOT DECOMPOSED" in out, out[:300]
    for exit_name in ("DECOMPOSE", "REBUT", "DEFER"):
        assert exit_name in out, "220 FIRE: the block does not name the %s exit" % exit_name
    assert first in out, "220 the block names no real umbrella item"
    assert "Callouts lose only their source line" in out, "220 the block quotes no untracked task"
    token = re.search(r"planfid:[0-9a-f]{8}", out)
    assert token, "220 no planfid deferral token in the block"

    # 220a. The DEFERRAL exit settles it.
    wl.add_item(
        "- [?] (deadbeef) %s is this plan superseded? DEFAULT: decompose it WHY: the scope may have "
        "moved HOW: the operator answers" % token.group(0)
    )
    out = wl.runj().out
    assert "AN APPROVED PLAN IS NOT DECOMPOSED" not in out, (
        "220a CONTROL: the deferral exit did not settle it"
    )


def test_220b_faithful_true_settles_and_is_never_asked_again(wl):  # noqa: F811
    wl.say("seeded the round")
    wl.brief_now()
    plant_plan(wl)
    wl.cli("--add", wlfix.ME, "www round 4 Wave A")
    wl.cli("--add", wlfix.ME, "www round 4 Waves B-D")
    shim_planfid(
        wl,
        json.dumps(
            {"faithful": True, "umbrella_ids": [], "missing": [], "instruction": "nothing to do"}
        ),
    )
    out = wl.runj().out
    assert "AN APPROVED PLAN IS NOT DECOMPOSED" not in out, (
        "220b CONTROL A: a faithful verdict still blocked"
    )
    first = planfid_calls(wl)
    wl.runj()
    second = planfid_calls(wl)
    assert first >= 1, "220b CONTROL B: the model was never asked, so nothing was settled"
    assert second == first, "220b: the settled plan was re-judged (%d -> %d)" % (first, second)
    marker = pathlib.Path(str(wl.wl) + ".planfid-deadbeef.json")
    assert marker.is_file(), "220b no planfid marker at all"
    assert '"verdict": "faithful"' in marker.read_text(encoding="utf-8"), (
        "220b no faithful verdict in the marker"
    )


def test_220c_the_instrument_blind_no_approved_plan_same_accusing_shim(wl):  # noqa: F811
    """Deliberately NO plan. Same umbrella items, same shim that would accuse."""
    wl.say("seeded the round")
    wl.brief_now()
    wl.cli("--add", wlfix.ME, "www round 4 Wave A")
    wl.cli("--add", wlfix.ME, "www round 4 Waves B-D")
    shim_planfid(
        wl,
        json.dumps(
            {
                "faithful": False,
                "umbrella_ids": ["aaaa1111"],
                "missing": ["Callouts lose only their source line."],
                "instruction": "split them",
            }
        ),
    )
    out = wl.runj().out
    assert "AN APPROVED PLAN IS NOT DECOMPOSED" not in out, "220c: fired without a plan"
    assert planfid_calls(wl) == 0, "220c: a call was spent with no approved plan"


def test_220d_a_decomposed_worklist_never_reaches_the_model_at_all(wl):  # noqa: F811
    wl.say("seeded the round")
    wl.brief_now()
    plant_plan(wl)
    for task in DECOMPOSED_TASKS:
        wl.cli("--add", wlfix.ME, task)
    shim_planfid(
        wl,
        json.dumps(
            {
                "faithful": False,
                "umbrella_ids": ["aaaa1111"],
                "missing": ["Callouts lose only their source line."],
                "instruction": "split them",
            }
        ),
    )
    out = wl.runj().out
    assert "AN APPROVED PLAN IS NOT DECOMPOSED" not in out, (
        "220d CONTROL: false positive on a decomposed worklist"
    )
    assert planfid_calls(wl) == 0, "220d: a decomposed worklist still reached the model"


def test_220e_an_invented_item_id_cannot_manufacture_a_block(wl):  # noqa: F811
    """Both axes hallucinated at once: an id no item carries, and a plan task that appears nowhere in the plan. Neither survives verification, so no evidence is left and the check must not block on the model's word alone."""
    wl.say("seeded the round")
    wl.brief_now()
    plant_plan(wl)
    wl.cli("--add", wlfix.ME, "www round 4 Wave A")
    wl.cli("--add", wlfix.ME, "www round 4 Waves B-D")
    shim_planfid(
        wl,
        json.dumps(
            {
                "faithful": False,
                "umbrella_ids": ["9999zzzz"],
                "missing": ["rewrite the kernel scheduler in rust"],
                "instruction": "do it",
            }
        ),
    )
    out = wl.runj().out
    assert "AN APPROVED PLAN IS NOT DECOMPOSED" not in out, (
        "220e CONTROL: an unevidenced verdict blocked"
    )
    assert planfid_calls(wl) >= 1, "220e: the model was never asked, so nothing was refused"


def test_220f_a_broken_judge_degrades_it_does_not_wall_the_session_in(wl):  # noqa: F811
    wl.say("seeded the round")
    wl.brief_now()
    plant_plan(wl)
    wl.cli("--add", wlfix.ME, "www round 4 Wave A")
    wl.cli("--add", wlfix.ME, "www round 4 Waves B-D")
    broken_judge(wl)
    out = wl.runj().out
    assert "AN APPROVED PLAN IS NOT DECOMPOSED" not in out, (
        "220f CONTROL: a broken judge produced a plan-fidelity block"
    )
    queued = wl.stem(".state-deadbeef.json")
    assert queued.is_file(), "220f: a failed plan-fidelity run left no trace at all"
    assert "plan-fidelity check could not run" in queued.read_text(encoding="utf-8"), (
        "220f: the failure was swallowed rather than queued for the session"
    )


def test_220h_a_failed_tier_two_call_is_recorded_not_just_reported(wl):  # noqa: F811
    """The `wl_checks` call sites are INVISIBLE to `wl_planfid`'s own selftest, so this is their only coverage: delete either one and the module controls stay green. The error branch specifically, because a judge that could not be reached is exactly the outcome nobody currently counts."""
    wl.say("seeded the round")
    wl.brief_now()
    plant_plan(wl)
    wl.cli("--add", wlfix.ME, "www round 4 Wave A")
    wl.cli("--add", wlfix.ME, "www round 4 Waves B-D")
    broken_judge(wl)
    wl.runj()
    verdicts = pathlib.Path(str(wl.wl) + ".planfid-verdicts-deadbeef.jsonl")
    assert verdicts.is_file(), "220h no verdict log at all"
    assert '"branch": "error"' in verdicts.read_text(encoding="utf-8"), (
        "220h an unreachable judge left no error row in the verdict log"
    )


def build_drift_repo(dirty_docs: bool, extra_commits: int) -> str:
    # A git repository per call, three per run, outside pytest's tmp_path and so outside its retention policy; inside one pid-stamped run dir, removed at exit and swept by the next run when this one was killed first.
    root = tempfile.mkdtemp(dir=runtmp.shared("plan-fidelity-test-"))

    def sh(*args):
        subprocess.run(args, cwd=root, check=True, capture_output=True)

    sh("git", "init", "-q")
    sh("git", "config", "user.email", "p@x")
    sh("git", "config", "user.name", "p")
    docs = pathlib.Path(root, "docs/ci-overhaul")
    docs.mkdir(parents=True)
    (docs / "06-progress.md").write_text("start\n", encoding="utf-8")
    pathlib.Path(root, ".ci").mkdir()
    pathlib.Path(root, ".ci/a.sh").write_text("x\n", encoding="utf-8")
    sh("git", "add", "-A")
    sh("git", "commit", "-qm", "base")
    for index in range(extra_commits):
        pathlib.Path(root, ".ci/a.sh").write_text("x%d\n" % index, encoding="utf-8")
        sh("git", "add", "-A")
        sh("git", "commit", "-qm", "c%d" % index)
    if dirty_docs:
        (docs / "06-progress.md").write_text("start\nuncommitted update\n", encoding="utf-8")
    return root


def test_221_docs_drift_counts_an_uncommitted_doc_edit():
    """`docs_drift` measured the last COMMIT touching the design docs, and this repo's standing rule is that work stays uncommitted until the operator asks. So a session that DID update the docs was told they had drifted at every stop, and the only way to satisfy the check was to commit, the one action that rule forbids doing unilaterally. The middle assertion is the guard
    rail: a genuinely un-updated docs tree must STILL report drifted, or this fix has merely disarmed the check."""
    checks = wlfix.import_wl("wl_checks")
    over = checks.DOCS_DRIFT_MAX + 2
    assert checks.docs_drift(build_drift_repo(False, 0))[0] == "ok", "quiet-when-aligned"
    assert checks.docs_drift(build_drift_repo(False, over))[0] == "drifted", (
        "still-fires-when-ignored"
    )
    assert checks.docs_drift(build_drift_repo(True, over))[0] == "pending", (
        "uncommitted-edit-counts"
    )


def test_227_an_adopted_plan_with_untracked_boxes_blocks(wl):  # noqa: F811
    """An ADOPTED plan is an order: its untracked boxes block in the mission tier, while a plan the session merely owns stays an advisory."""
    wl.say("answer\n\n## Remaining\n- nothing")
    wl.brief_now()
    wl.hand_now()
    plan_file(wl, "adopted", ADOPTED_PLAN)
    wl.check("block", "WAS ADOPTED BY THIS SESSION", "227: an adopted plan's boxes are ordered")


def test_227b_the_same_plan_merely_owned_is_only_an_advisory(wl):  # noqa: F811
    """CONTROL: never a block."""
    wl.say("answer\n\n## Remaining\n- nothing")
    wl.brief_now()
    wl.hand_now()
    plan_file(wl, "owned", OWNED_PLAN)
    wl.check("allow", "", "227b: an owned, not adopted, plan does not block")
