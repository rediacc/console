"""rediacc_ci.feedback.critical, .plangen and Stages 4 and 5 of .triage (no network, no real worklist): each R8 trigger (a) to (e) on its fixture with a control one short of it, the regression-only and enterprise-only fixtures that never fire, the deferral the worklist's own parser accepts with DEFAULT: and a 6 h window, the filed-once state, the plan check_plan_record.py accepts, and the reproduction verb."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta

import pytest

from rediacc_ci import paths
from rediacc_ci.feedback import classify, client, critical, plangen, triage

NOW = datetime(2026, 11, 19, 5, 0, tzinfo=UTC)
FP = "e" * 64
FP2 = "f" * 64


def _iso(delta: timedelta) -> str:
    return (NOW - delta).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _item(fp=FP, status="screening", **extra):
    base = {
        "fingerprint": fp,
        "status": status,
        "kind": "bug",
        "commandPath": "backup push",
        "argv": "rdc backup push mail <machine>",
        "exitCode": 1,
        "errorCode": "BACKUP_PUSH_FAILED",
        "errorMessage": "upload stalled after the first chunk set",
        "stderrTail": "",
        "message": "",
        "os": "linux",
        "arch": "x64",
        "agent": False,
        "ci": False,
        "versions": ["0.8.3"],
        "reportCount": 1,
        "occurrenceCount": 1,
        "distinctReporters": 1,
        "distinctOrgs": 1,
        "firstSeenAt": _iso(timedelta(days=3)),
        "lastSeenAt": _iso(timedelta(hours=2)),
        "category": None,
        "triageNote": None,
        "planRef": None,
    }
    base.update(extra)
    return base


class _ExportStub:
    """GET export answers the given items; nothing else is called."""

    def __init__(self, items):
        self.items = items

    def get(self, _route):
        return 200, {"items": self.items}


def _cls(**over):
    doc = {
        "meaningful": True,
        "safe_to_reproduce": True,
        "suspicious": False,
        "category": "backup",
        "core_path": True,
        "summary": "backup push stalls on the first upload",
    }
    doc.update(over)
    return classify.parse_reply(json.dumps(doc))


def _codes(triggers):
    return [t.code for t in triggers]


# ---- (a) -----------------------------------------------------------------------------------------


def _fresh(**extra):
    return _item(
        firstSeenAt=_iso(timedelta(hours=20)), lastSeenAt=_iso(timedelta(hours=1)), **extra
    )


def test_a_fires_on_five_reporters_within_24h():
    assert _codes(critical.evaluate(_fresh(distinctReporters=5), NOW)) == ["a"]


def test_a_control_four_reporters_do_not_fire():
    assert critical.evaluate(_fresh(distinctReporters=4, distinctOrgs=2), NOW) == []


def test_a_fires_on_three_orgs_and_not_on_two():
    assert _codes(critical.evaluate(_fresh(distinctReporters=3, distinctOrgs=3), NOW)) == ["a"]
    assert critical.evaluate(_fresh(distinctReporters=3, distinctOrgs=2), NOW) == []


def test_a_reads_the_24h_counts_when_the_export_carries_them():
    old = _item(distinctReporters=40, distinctReporters24h=5, distinctOrgs24h=0)
    assert _codes(critical.evaluate(old, NOW)) == ["a"]
    quiet = _item(distinctReporters=40, distinctReporters24h=4, distinctOrgs24h=2)
    assert critical.evaluate(quiet, NOW) == []
    assert _codes(critical.evaluate(_item(distinctReporters24h=1, distinctOrgs24h=3), NOW)) == ["a"]


def test_a_prefers_the_24h_counts_over_a_fresh_window():
    # First and last report inside 24 h would let the totals stand in; the account's own 24 h counts say only one reporter is recent.
    fresh = _fresh(distinctReporters=9, distinctOrgs=9, distinctReporters24h=1, distinctOrgs24h=1)
    assert critical.evaluate(fresh, NOW) == []
    # Control: the same item without the pair falls back to the totals and fires.
    assert _codes(critical.evaluate(_fresh(distinctReporters=9, distinctOrgs=9), NOW)) == ["a"]


def test_a_half_24h_pair_is_ignored_and_the_window_reading_stands():
    """Review dcb11131.1: `export` refuses half pairs, so only a caller that skips it reaches this: one 24 h key alone never stands in for the pair, the first/last-seen window decides."""
    fresh = _fresh(distinctReporters=9, distinctOrgs=9, distinctReporters24h=1)
    assert _codes(critical.evaluate(fresh, NOW)) == ["a"]
    spread = _item(distinctReporters=9, distinctOrgs=9, distinctReporters24h=9)
    assert critical.evaluate(spread, NOW) == []
    # Control: the full pair is read as given.
    assert _codes(critical.evaluate(_item(distinctReporters24h=9, distinctOrgs24h=0), NOW)) == ["a"]


def test_a_reads_the_24h_counts_from_a_parsed_export():
    # First report 3 days ago: without the pair the window reading counts nothing.
    item = _item(distinctReporters=8, distinctOrgs=2, distinctReporters24h=6, distinctOrgs24h=1)
    parsed = client.export(_ExportStub([item]))
    assert _codes(critical.evaluate(parsed[0], NOW)) == ["a"]


def test_a_control_totals_spread_past_24h_do_not_count():
    assert critical.evaluate(_item(distinctReporters=9, distinctOrgs=9), NOW) == []


# ---- (b) -----------------------------------------------------------------------------------------


def test_b_fires_on_a_reproduced_core_path_with_no_workaround():
    assert _codes(critical.evaluate(_item(), NOW, repro="reproduced", category="backup")) == ["b"]


def test_b_controls():
    assert (
        critical.evaluate(_item(), NOW, repro="reproduced", workaround=True, category="backup")
        == []
    )
    assert critical.evaluate(_item(), NOW, repro="reproduced", category="config") == []
    assert critical.evaluate(_item(), NOW, repro="inconclusive", category="backup") == []
    assert critical.evaluate(_item(), NOW, category="backup") == []


# ---- (c) -----------------------------------------------------------------------------------------


def test_c_fires_when_the_classifier_quarantined_the_report():
    suspicious = classify.outcome_for(_item(), json.dumps({**_cls().as_dict(), "suspicious": True}))
    assert _codes(critical.evaluate(_item(), NOW, outcome=suspicious)) == ["c"]
    broken = classify.outcome_for(_item(), "not json")
    triggers = critical.evaluate(_item(), NOW, outcome=broken)
    assert _codes(triggers) == ["c"]
    assert "schema" in triggers[0].evidence


def test_c_control_a_stage1_quarantine_alone_is_not_critical():
    item = _item(
        status="quarantined", triageNote="stage1 quarantine: rule url matched field message"
    )
    assert critical.evaluate(item, NOW) == []


def test_c_control_a_clean_classification_is_not_critical():
    clean = classify.outcome_for(_item(), json.dumps(_cls().as_dict()))
    assert critical.evaluate(_item(), NOW, outcome=clean) == []


def test_c_fires_when_a_clean_reproduction_disagrees_with_a_high_count():
    assert _codes(critical.evaluate(_item(distinctReporters=3), NOW, repro="clean")) == ["c"]
    assert _codes(critical.evaluate(_item(occurrenceCount=10), NOW, repro="clean")) == ["c"]


def test_c_control_one_short_of_high_count():
    assert (
        critical.evaluate(_item(distinctReporters=2, occurrenceCount=9), NOW, repro="clean") == []
    )


# ---- (d) -----------------------------------------------------------------------------------------


def test_d_fires_past_14_days_while_still_growing():
    item = _item(firstSeenAt=_iso(timedelta(days=15)))
    triggers = critical.evaluate(item, NOW)
    assert _codes(triggers) == ["d"]
    assert triggers[0].default == critical.DEFAULT_RAISE


def test_d_controls():
    assert critical.evaluate(_item(firstSeenAt=_iso(timedelta(days=13))), NOW) == []
    stale_quiet = _item(firstSeenAt=_iso(timedelta(days=15)), lastSeenAt=_iso(timedelta(days=2)))
    assert critical.evaluate(stale_quiet, NOW) == []
    fixed = _item(status="fixed", firstSeenAt=_iso(timedelta(days=15)))
    assert critical.evaluate(fixed, NOW) == []


# ---- (e) -----------------------------------------------------------------------------------------


def test_e_fires_on_a_confirmed_docs_report():
    docs = _item(kind="docs")
    assert _codes(critical.evaluate(docs, NOW, repro="reproduced", category="docs")) == ["e"]


def test_e_controls():
    assert critical.evaluate(_item(kind="docs"), NOW, repro="inconclusive", category="docs") == []
    assert critical.evaluate(_item(), NOW, repro="reproduced", category="config") == []


# ---- not critical by itself ----------------------------------------------------------------------


def test_regression_only_fixture_does_not_fire():
    regression = _item(versions=["0.8.1", "0.8.2", "0.8.3", "0.9.0"], occurrenceCount=6)
    assert critical.evaluate(regression, NOW) == []


def test_enterprise_only_fixture_does_not_fire():
    enterprise = _item(enterprise=True, ownerKind="user", channel="stable", distinctOrgs=1)
    assert critical.evaluate(enterprise, NOW) == []


def test_unknown_repro_result_is_refused():
    with pytest.raises(ValueError, match="repro"):
        critical.evaluate(_item(), NOW, repro="maybe")


# ---- the deferral --------------------------------------------------------------------------------


def _wl_core():
    paths.on_sys_path(paths.hooks_stop_dir())
    return importlib.import_module("wl_core")


def test_defer_argv_carries_default_and_a_6h_window_the_worklist_accepts():
    now = datetime.now(UTC)
    (trigger,) = critical.evaluate(_item(kind="docs"), now, repro="reproduced", category="docs")
    argv = critical.defer_argv(trigger, "ab12cd34", "deadbeef", now)
    assert argv[2:5] == ["--defer", "ab12cd34", "deadbeef"]
    assert len(argv) == 6
    assert argv[1].endswith(".claude/hooks/stop/worklist.py")
    text = argv[-1]
    core = _wl_core()
    assert core.DEFAULT_TOKEN.search(text)
    just = core.parse_justification(text)
    assert just.get("why")
    assert just.get("how")
    assert core.VAGUE_WHY_RE.search(just["why"]) is None
    (hold,) = core.NOT_BEFORE.findall(text)
    assert hold == (now + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%MZ")
    assert core.not_before_problem(text) == ""
    assert "DEFAULT: %s." % critical.DEFAULT_PLAN in text


def test_defer_text_carries_no_report_field():
    (trigger,) = critical.evaluate(_item(), NOW, repro="reproduced", category="backup")
    text = critical.defer_text(trigger, NOW) + critical.item_text(trigger, "ab12cd34")
    for key in ("argv", "errorMessage", "commandPath"):
        assert _item()[key] not in text


def test_file_triggers_adds_then_defers_and_stops_on_a_refused_add():
    calls = []

    def capture(argv):
        calls.append(list(argv))
        if argv[2] == "--add":
            return 0, "added #1a2b3c4d: whatever\n"
        return 0, "deferred"

    triggers = critical.evaluate(_item(kind="docs"), NOW, repro="reproduced", category="docs")
    (filed,) = critical.file_triggers(triggers, "ab12cd34", NOW, capture)
    assert filed.ok
    assert filed.item_id == "1a2b3c4d"
    assert [c[2] for c in calls] == ["--add", "--defer"]
    assert calls[1][4] == "1a2b3c4d"

    calls.clear()
    (refused,) = critical.file_triggers(
        triggers, "ab12cd34", NOW, lambda a: (calls.append(a), (2, ""))[1]
    )
    assert not refused.ok
    assert len(calls) == 1


# ---- plans ---------------------------------------------------------------------------------------


def _plan_record():
    gate = paths.from_root(".ci", "scripts", "quality", "check_plan_record.py")
    paths.on_sys_path(gate.parent)
    spec = importlib.util.spec_from_file_location("check_plan_record_for_feedback", gate)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_plangen_writes_a_plan_check_plan_record_accepts(tmp_path):
    written = plangen.write(tmp_path, _item(), _cls(), NOW, owner="ab12cd34")
    assert written.created
    assert written.name == "PLAN-feedback-backup-backup-push-stalls-on-the-first-upload.md"
    text = (tmp_path / written.rel).read_text()
    gate = _plan_record()
    assert gate.boxless_verdict(written.rel, text) == ("", "")
    assert gate.finished_verdict(written.rel, text) == ("", "")
    assert gate.header_xref_problems(tmp_path, written.rel, text) == []
    plan = gate.PL.parse_plan(written.rel, text)
    assert plan.status == "draft"
    open_boxes, done = gate.PF.plan_boxes(text)
    assert len(open_boxes) == 1
    assert done == []
    assert "\nFeedback: %s\n" % FP[:12] in text
    for key in ("argv", "errorMessage"):
        assert _item()[key] not in text


def test_plan_record_control_a_started_plan_without_a_box_is_refused(tmp_path):
    written = plangen.write(tmp_path, _item(), _cls(), NOW)
    text = (tmp_path / written.rel).read_text()
    broken = text.replace("Status: draft", "Status: approved").split("## Boxes")[0]
    kind, _msg = _plan_record().boxless_verdict(written.rel, broken)
    assert kind == "refuse"


def test_plangen_keeps_its_own_plan_and_steps_around_a_foreign_one(tmp_path):
    first = plangen.write(tmp_path, _item(), _cls(), NOW)
    again = plangen.write(tmp_path, _item(), _cls(), NOW)
    assert again == plangen.Written(first.rel, first.name, created=False)
    other = plangen.write(tmp_path, _item(FP2), _cls(), NOW)
    assert other.created
    assert other.name.endswith("-%s.md" % FP2[:8])


def test_plangen_dry_run_writes_nothing(tmp_path):
    written = plangen.write(tmp_path, _item(), _cls(), NOW, dry_run=True)
    assert written.created
    assert not (tmp_path / written.rel).exists()


def test_plangen_refuses_an_owner_that_is_not_a_prefix(tmp_path):
    with pytest.raises(plangen.PlanError):
        plangen.write(tmp_path, _item(), _cls(), NOW, owner="bad owner")


def test_plangen_keeps_a_free_text_command_path_out(tmp_path):
    written = plangen.write(tmp_path, _item(commandPath="backup push; rm"), _cls(), NOW)
    text = (tmp_path / written.rel).read_text()
    assert "rm" not in text.split("## Context")[1].split("## Boxes")[0].replace("form", "")
    assert "an unnamed command" in text


# ---- the run: Stages 4 and 5 wired ---------------------------------------------------------------


class Server:
    def __init__(self, items):
        self.items = items
        self.posts = []

    def get(self, _route):
        return 200, {"items": self.items}

    def post(self, route, body):
        self.posts.append((route, body))
        n = len(body["verdicts"])
        return 200, {"fingerprints": n, "reports": n, "missing": []}


class Worklist:
    def __init__(self):
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        if argv[2] == "--add":
            return 0, "added #%08x: x\n" % len(self.calls)
        return 0, "deferred"


def _deps(server, worklist=None, lines=None):
    return triage.Deps(
        open_region=lambda _r, _w: server,
        now=lambda: NOW,
        out=(lines if lines is not None else []).append,
        complete=lambda _p: "{}",
        env={},
        capture=worklist or Worklist(),
    )


def _opts(tmp_path, me=None, dry_run=False):
    return triage.Options(
        ("eu",),
        dry_run=dry_run,
        cursor=tmp_path / "cursor.json",
        classify=False,
        me=me,
        plans_root=tmp_path,
        orders=tmp_path / "orders.json",
        critical_state=tmp_path / "critical.json",
    )


def test_stage4_files_a_trigger_once_under_me(tmp_path):
    server = Server([_fresh(distinctReporters=6)])
    worklist = Worklist()
    rc, results = triage.run(_opts(tmp_path, me="ab12cd34"), _deps(server, worklist))
    assert rc == 0
    assert [f.trigger.code for f in results[0].filed] == ["a"]
    assert [c[2] for c in worklist.calls] == ["--add", "--defer"]
    rc, results = triage.run(_opts(tmp_path, me="ab12cd34"), _deps(server, worklist))
    assert results[0].filed == []
    assert len(worklist.calls) == 2


class RefusingDefer(Worklist):
    """`--add` succeeds and `--defer` is refused."""

    def __call__(self, argv):
        rc, out = super().__call__(argv)
        return (3, "") if argv[2] == "--defer" else (rc, out)


class RefusingAdd(Worklist):
    def __call__(self, argv):
        self.calls.append(list(argv))
        return 4, ""


def test_stage4_a_refused_defer_is_still_filed_once(tmp_path):
    """Review 23cc895b.4: an --add that landed with its --defer refused was left out of the state, so every later run added the item again."""
    server = Server([_fresh(distinctReporters=6)])
    worklist = RefusingDefer()
    rc, results = triage.run(_opts(tmp_path, me="ab12cd34"), _deps(server, worklist))
    assert rc == 1
    (filed,) = results[0].filed
    assert not filed.ok
    assert filed.item_id
    assert "open without its deferral" in filed.note
    rc, results = triage.run(_opts(tmp_path, me="ab12cd34"), _deps(server, worklist))
    assert results[0].filed == []
    assert [c[2] for c in worklist.calls] == ["--add", "--defer"]


def test_stage4_control_a_refused_add_is_retried(tmp_path):
    server = Server([_fresh(distinctReporters=6)])
    worklist = RefusingAdd()
    rc, _results = triage.run(_opts(tmp_path, me="ab12cd34"), _deps(server, worklist))
    assert rc == 1
    triage.run(_opts(tmp_path, me="ab12cd34"), _deps(server, worklist))
    assert [c[2] for c in worklist.calls] == ["--add", "--add"]


def test_stage4_control_without_me_names_the_trigger_and_files_nothing(tmp_path):
    server = Server([_fresh(distinctReporters=6)])
    worklist = Worklist()
    lines = []
    triage.run(_opts(tmp_path), _deps(server, worklist, lines))
    assert worklist.calls == []
    assert any("critical R8 (a) not filed (no --me)" in line for line in lines)
    assert not (tmp_path / "critical.json").exists()


def _confirmed():
    cls = _cls()
    return _item(
        status="confirmed", category="backup", triageNote=classify.note_for(cls, "repro reproduced")
    )


def test_stage5_plans_a_confirmed_fingerprint(tmp_path):
    server = Server([_confirmed()])
    rc, results = triage.run(_opts(tmp_path), _deps(server))
    assert rc == 0
    (written,) = results[0].plans
    assert (tmp_path / written.rel).is_file()
    ((_route, body),) = server.posts
    assert body["verdicts"] == [{"fingerprint": FP, "status": "planned", "planRef": written.name}]


def test_stage5_controls_a_planned_or_unclassified_fingerprint_gets_no_plan(tmp_path):
    server = Server(
        [{**_confirmed(), "planRef": "PLAN-feedback-x.md"}, _item(FP2, status="confirmed")]
    )
    _rc, results = triage.run(_opts(tmp_path), _deps(server))
    assert results[0].plans == []
    assert not (tmp_path / "agent").exists()


def _hold_both_plan_names(root):
    """Two foreign plans under both names the confirmed fingerprint could take."""
    cls = _cls()
    for fp in ("1" * 64, "2" * 64):
        plangen.write(root, _item(fp), cls, NOW)
    base = plangen.slug_for(cls)
    plans = root / "agent" / "plans"
    first = plans / plangen.plan_name(base)
    second = plans / plangen.plan_name("%s-%s" % (base, FP[:8]))
    second.write_text(first.read_text())
    return first, second


def test_plangen_refuses_when_both_names_are_foreign(tmp_path):
    """Review 23cc895b.8: the double collision had no committed test."""
    _hold_both_plan_names(tmp_path)
    with pytest.raises(plangen.PlanError, match="both plan names"):
        plangen.write(tmp_path, _item(), _cls(), NOW)


def test_stage5_a_plan_error_fails_the_run(tmp_path):
    """Review 23cc895b.6: a confirmed fingerprint left with no plan logged a warning and the run exited 0."""
    _hold_both_plan_names(tmp_path)
    lines = []
    server = Server([_confirmed()])
    rc, results = triage.run(_opts(tmp_path), _deps(server, lines=lines))
    assert rc == 1
    assert results[0].plan_errors == [FP]
    assert results[0].plans == []
    assert any("1 confirmed fingerprint(s) with no plan" in line for line in lines)
    assert server.posts == []  # nothing changed, so no verdict moves it to planned
    # Review 5e6d8c31.1: the cursor stays put, so the next run exports the fingerprint again and retries its plan.
    assert not (tmp_path / "cursor.json").exists()
    assert any("cursor held" in line for line in lines)


def test_stage5_control_a_free_name_plans_and_exits_0(tmp_path):
    server = Server([_confirmed()])
    rc, results = triage.run(_opts(tmp_path), _deps(server))
    assert rc == 0
    assert results[0].plan_errors == []
    assert (tmp_path / "cursor.json").exists(), "control: a planned run advances the cursor"


def test_stage5_dry_run_writes_no_plan(tmp_path):
    server = Server([_confirmed()])
    _rc, results = triage.run(_opts(tmp_path, dry_run=True), _deps(server))
    assert len(results[0].plans) == 1
    assert not (tmp_path / "agent").exists()
    assert server.posts == []


# ---- repro ---------------------------------------------------------------------------------------


def _screened(**extra):
    return _item(category="backup", triageNote=classify.note_for(_cls()), **extra)


def _repro(tmp_path, items, result, me=None, dry_run=False, workaround=False):
    server = Server(items)
    worklist = Worklist()
    opts = triage.ReproOptions(
        "eu",
        FP,
        result,
        workaround=workaround,
        dry_run=dry_run,
        me=me,
        plans_root=tmp_path,
        critical_state=tmp_path / "critical.json",
    )
    rc, res = triage.repro(opts, _deps(server, worklist))
    return rc, res, server, worklist


def test_repro_reproduced_confirms_plans_and_files_b(tmp_path):
    rc, res, server, worklist = _repro(tmp_path, [_screened()], "reproduced", me="ab12cd34")
    assert rc == 0
    ((_route, body),) = server.posts
    (verdict,) = body["verdicts"]
    assert verdict["status"] == "planned"
    assert verdict["planRef"].startswith("PLAN-feedback-")
    assert verdict["triageNote"].endswith("| repro reproduced")
    assert (tmp_path / "agent" / "plans" / verdict["planRef"]).is_file()
    assert [f.trigger.code for f in res.filed] == ["b"]
    assert worklist.calls


def test_repro_clean_low_count_rejects(tmp_path):
    _rc, res, server, _w = _repro(tmp_path, [_screened()], "clean")
    (verdict,) = server.posts[0][1]["verdicts"]
    assert verdict["status"] == "rejected"
    assert res.triggers == []


def test_repro_clean_high_count_stays_and_raises_c(tmp_path):
    _rc, res, server, _w = _repro(tmp_path, [_screened(distinctReporters=4)], "clean")
    (verdict,) = server.posts[0][1]["verdicts"]
    assert verdict["status"] == "screening"
    assert [t.code for t in res.triggers] == ["c"]


def test_repro_refuses_a_quarantined_or_unclassified_fingerprint(tmp_path):
    rc, _res, server, _w = _repro(tmp_path, [_item(status="quarantined")], "reproduced")
    assert rc == 2
    assert server.posts == []
    rc, _res, server, _w = _repro(tmp_path, [_item()], "reproduced")
    assert rc == 2
    assert server.posts == []


def _order(fp):
    return {
        "fingerprint": fp,
        "where": "local",
        "commandPath": "backup push",
        "category": "backup",
        "start": "x",
    }


def test_write_orders_keeps_an_earlier_unreproduced_order(tmp_path):
    """Review 23cc895b.5: each run rewrote the orders file with its own orders only, losing the earlier ones."""
    path = tmp_path / "orders.json"
    triage.write_orders(path, "eu", [_order(FP)], "2026-11-19T04:00:00.000Z")
    triage.write_orders(path, "eu", [_order(FP2)], "2026-11-19T05:00:00.000Z")
    assert [o["fingerprint"] for o in triage.read_orders(path, "eu")] == [FP, FP2]


def test_write_orders_control_a_new_order_replaces_its_own_fingerprint(tmp_path):
    path = tmp_path / "orders.json"
    triage.write_orders(path, "eu", [_order(FP)], "2026-11-19T04:00:00.000Z")
    triage.write_orders(path, "eu", [{**_order(FP), "start": "y"}], "2026-11-19T05:00:00.000Z")
    assert [o["start"] for o in triage.read_orders(path, "eu")] == ["y"]
    assert triage.read_orders(path, "us") == []


def test_repro_consumes_its_order_and_keeps_the_others(tmp_path):
    path = tmp_path / "orders.json"
    triage.write_orders(path, "eu", [_order(FP), _order(FP2)], "2026-11-19T04:00:00.000Z")
    server = Server([_screened()])
    opts = triage.ReproOptions(
        "eu",
        FP,
        "clean",
        plans_root=tmp_path,
        critical_state=tmp_path / "critical.json",
        orders=path,
    )
    rc, _res = triage.repro(opts, _deps(server))
    assert rc == 0
    assert [o["fingerprint"] for o in triage.read_orders(path, "eu")] == [FP2]


def test_repro_dry_run_control_keeps_the_order(tmp_path):
    path = tmp_path / "orders.json"
    triage.write_orders(path, "eu", [_order(FP)], "2026-11-19T04:00:00.000Z")
    opts = triage.ReproOptions(
        "eu",
        FP,
        "clean",
        dry_run=True,
        plans_root=tmp_path,
        critical_state=tmp_path / "critical.json",
        orders=path,
    )
    triage.repro(opts, _deps(Server([_screened()])))
    assert [o["fingerprint"] for o in triage.read_orders(path, "eu")] == [FP]


def test_repro_dry_run_writes_nothing(tmp_path):
    rc, _res, server, worklist = _repro(
        tmp_path, [_screened()], "reproduced", me="ab12cd34", dry_run=True
    )
    assert rc == 0
    assert server.posts == []
    assert worklist.calls == []
    assert not (tmp_path / "agent").exists()


def test_parse_any_reads_the_repro_verb():
    opts = triage.parse_any(
        ["repro", "--region", "eu", "--fingerprint", FP, "--result", "clean", "--me", "ab12cd34"]
    )
    assert isinstance(opts, triage.ReproOptions)
    assert opts.result == "clean"
    for bad in (
        ["repro", "--region", "eu", "--fingerprint", "xyz", "--result", "clean"],
        ["repro", "--region", "eu", "--fingerprint", FP, "--result", "maybe"],
        ["run", "--me", "bad me"],
        ["run", "--no-classify", "--replies", "/tmp/x"],
    ):
        with pytest.raises(client.FeedbackError):
            triage.parse_any(bad)
