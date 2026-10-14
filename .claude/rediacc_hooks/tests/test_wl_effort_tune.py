"""The effort tuner (agent/plans/PLAN-stop-hook-effort-tuning.md T2-T6).

T2 the `--effort-propose` verb refuses evidence that cites no outcome row and appends one that does. T3 on a fixture ledger the core proposes the planted demotion and promotion, flags the planted dead key, and the replay names the emissions that change. T4 the near-compaction request fires once per context through the real Stop hook, and a fixture run writes the patch and evidence. T5 a promotion applies with a report line, a demotion waits for one /ask whose answer is recorded and not asked again, the FLOOR is never tuned, and a demoted key quiet before a miss is promoted back. T6 three re-raised finished items yield one proposed judge rule whose test passes.

Every write goes to a scratch project holding a copy of the real effort.json; the real table is only read.
"""

from __future__ import annotations

import datetime
import json
import shutil
import subprocess
import sys

import pytest

from rediacc_hooks.tests import wlfix

T = wlfix.import_wl("wl_effort_tune")
OUT = wlfix.import_wl("wl_outcomes")
E = wlfix.import_wl("wl_effort")
FLOOR = wlfix.import_wl("wl_floor")
REPO = wlfix.STOP_DIR.parents[2]
NOW = datetime.datetime(2026, 10, 14, 12, 0, tzinfo=datetime.UTC)
ME = wlfix.ME

DEMOTE_KEY = "plan-drift"  # blocks at high: planted to block 10 times with 1 led to work
PROMOTE_KEY = "no-remaining"  # advises at smart: planted to advise 8 times with 6 led to work
DEAD_KEY = "plan-unimplemented"  # planted with no row at all


def stamp(minutes_ago):
    return (NOW - datetime.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def row(n, key, verdict, level, outcome, **extra):
    return {
        "id": "eo-%08x" % n,
        "kind": "outcome",
        "key": key,
        "verdict": verdict,
        "level": level,
        "outcome": outcome,
        "why": extra.pop("why", ""),
        "session": ME,
        "epoch": 1,
        "stop": n,
        "at": stamp(600 - n),
        "decided": stamp(590 - n),
        "subjects": extra.pop("subjects", {"items": [], "plans": [], "paths": [], "tokens": []}),
        "strong": False,
        "miss": extra.pop("miss", False),
        "text": extra.pop("text", "%s fired" % key),
        **extra,
    }


def fixture_ledger():
    rows = []
    n = 0
    for i in range(10):
        n += 1
        rows.append(row(n, DEMOTE_KEY, "block", "high", "work" if i == 0 else "paperwork"))
    for i in range(8):
        n += 1
        rows.append(row(n, PROMOTE_KEY, "advise", "smart", "work" if i < 6 else "expired"))
    for _ in range(4):
        n += 1
        rows.append(row(n, "open-items", "block", "smart", "work"))
    for _ in range(6):  # a FLOOR key that never leads to work is still never tuned
        n += 1
        rows.append(row(n, "ci-red", "block", "smart", "expired"))
    return rows


@pytest.fixture
def wl(tmp_path):
    """One hook sandbox per test (wlfix.Fixture)."""
    fixture = wlfix.Fixture(tmp_path / "hookfix")
    fixture.setup()
    return fixture


@pytest.fixture
def proj(tmp_path):
    """A scratch project: a copy of the real effort.json and the fixture ledger."""
    root = tmp_path / "proj"
    (root / ".claude" / "config").mkdir(parents=True)
    shutil.copy(REPO / E.TABLE_REL, root / E.TABLE_REL)
    OUT.append_rows(OUT.ledger_path(root), fixture_ledger())
    yield root
    E._CACHE.clear()


def table_of(root):
    return json.loads((root / E.TABLE_REL).read_text(encoding="utf-8"))


# ---- T3: the core --------------------------------------------------------------------------------


def test_t3_the_planted_demotion_and_promotion_and_nothing_on_the_floor(proj):
    table = table_of(proj)
    st = T.stats(fixture_ledger(), NOW)
    assert T.precision(st[DEMOTE_KEY]["block"]) == pytest.approx(0.1)
    changes = {c["key"]: c for c in T.candidates(table, st, NOW)}
    assert set(changes) == {DEMOTE_KEY, PROMOTE_KEY}, changes
    dem, pro = changes[DEMOTE_KEY], changes[PROMOTE_KEY]
    assert (dem["direction"], dem["from"], dem["to"]) == (
        "demote",
        {"block": "high", "advise": "smart"},
        {"block": "ultra", "advise": "smart"},
    )
    assert (pro["direction"], pro["to"]) == ("promote", {"block": "smart", "advise": "smart"})
    assert dem["ids"][0] == "eo-00000001"
    assert "ci-red" not in changes, "the FLOOR is never tuned"


def test_t3_the_planted_dead_key_is_flagged_and_a_thin_window_flags_nothing(proj):
    table = table_of(proj)
    rows = fixture_ledger()
    dead = T.dead_keys(table, rows, NOW)
    assert DEAD_KEY in dead
    assert DEMOTE_KEY not in dead
    assert not set(dead) & FLOOR.FLOOR
    assert T.dead_keys(table, rows[:10], NOW) == [], "ten stops are too few to call a key dead"


def test_t3_the_replay_names_the_emissions_that_change(proj):
    table = table_of(proj)
    rows = fixture_ledger()
    new = T.apply_changes(table, T.candidates(table, T.stats(rows, NOW, table=table), NOW), NOW)
    moved = T.replay(rows, table, new)
    by_key: dict[str, set] = {}
    for r in moved:
        by_key.setdefault(r[3], set()).add((r[4], r[5], r[6]))
    assert by_key == {
        DEMOTE_KEY: {("high", "block", "advise")},
        PROMOTE_KEY: {("smart", "advise", "block")},
    }
    assert len(moved) == 18
    assert moved[0][:4] == (ME, 1, 1, DEMOTE_KEY)


def test_t3_the_window_drops_old_rows():
    rows = [dict(r, decided="2026-09-01T00:00:00Z") for r in fixture_ledger()]
    assert T.stats(rows, NOW) == {}


def test_t3_the_diff_applies_with_git(proj, tmp_path):
    table = table_of(proj)
    old = (proj / E.TABLE_REL).read_text(encoding="utf-8")
    new = T.apply_changes(
        table, T.candidates(table, T.stats(fixture_ledger(), NOW, table=table), NOW), NOW
    )
    patch = tmp_path / "p.patch"
    patch.write_text(T.diff(old, T.render(new)), encoding="utf-8")
    got = subprocess.run(
        ["git", "apply", "--check", "--directory=", str(patch)],
        cwd=str(proj),
        capture_output=True,
        text=True,
        check=False,
    )
    assert got.returncode == 0, got.stderr
    assert T.diff(old, old) == ""


# ---- T4: the run, the brief and the request ----------------------------------------------------


def test_t4_a_fixture_run_writes_the_patch_and_the_evidence(proj):
    doc = T.run(proj, ME, 1, now=NOW)
    out = T.run_dir(proj, ME, 1)
    patch = (out / "effort.json.patch").read_text(encoding="utf-8")
    assert '-      "block": "high",' in patch
    assert '+      "block": "ultra",' in patch
    evidence = (out / "evidence.md").read_text(encoding="utf-8")
    assert "| %s | 10 (w1 p9 o0 e0) 0.10 |" % DEMOTE_KEY in evidence
    assert "demote %s" % DEMOTE_KEY in evidence
    assert "- %s" % DEAD_KEY in evidence
    assert doc["gate"] == [], doc["gate"]
    assert json.loads((out / "run.json").read_text(encoding="utf-8"))["changes"] == doc["changes"]
    assert (proj / E.TABLE_REL).read_text(encoding="utf-8") == (REPO / E.TABLE_REL).read_text(
        encoding="utf-8"
    ), "a run proposes; it never edits the table"


def test_t4_the_brief_hands_over_this_contexts_rows(proj):
    OUT.append_rows(
        OUT.ledger_path(proj), [dict(row(99, "open-items", "block", "smart", "work"), epoch=7)]
    )
    text = T.brief(proj, ME, 7)
    out = T.run_dir(proj, ME, 7)
    rows = [json.loads(x) for x in (out / "context-rows.jsonl").read_text().splitlines()]
    assert [r["id"] for r in rows] == ["eo-00000063"]
    assert (out / "observations.md").is_file()
    assert "effort-tuner" in text
    assert "1 outcome row(s)" in text


@pytest.fixture
def band(tmp_path, monkeypatch):
    d = tmp_path / "ctxband"
    d.mkdir()
    monkeypatch.setenv("CTX_BAND_STATE_DIR", str(d))

    def plant(epoch, usage, threshold=1_000_000):
        (d / ("%s.json" % ME)).write_text(
            json.dumps({"epoch": epoch, "band": 0, "usage": usage, "threshold": threshold}),
            encoding="utf-8",
        )

    return plant


def test_t4_the_request_is_due_once_per_context_past_85_percent(proj, band):
    band(1, 840_000)
    assert T.request_due(proj, wlfix.SID) is None, "84% is not yet due"
    band(1, 860_000)
    due = T.request_due(proj, wlfix.SID)
    assert due is not None
    text, epoch, frac = due
    assert (epoch, round(frac, 2)) == (1, 0.86)
    assert "brief %s" % ME in text
    assert "agent/%s/effort-tune/e1" % ME in text
    T.mark_requested(proj, wlfix.SID, epoch, frac)
    band(1, 950_000)
    assert T.request_due(proj, wlfix.SID) is None, "once per context"
    band(2, 870_000)
    assert T.request_due(proj, wlfix.SID) is not None, "a new context earns its own request"


def test_t4_the_dedupe_key_is_the_slug_the_request_stored(proj, tmp_path, monkeypatch):
    """request_due compares against `session_slug`, so mark_requested must store the same spelling for an id the slug rewrites (fb45d045.3)."""
    odd = "ab cdefg-hij"
    slug = T._ctx().session_slug(odd)
    assert slug != odd[:8]
    d = tmp_path / "slugband"
    d.mkdir()
    monkeypatch.setenv("CTX_BAND_STATE_DIR", str(d))
    (d / ("%s.json" % slug)).write_text(
        json.dumps({"epoch": 1, "band": 0, "usage": 900_000, "threshold": 1_000_000}),
        encoding="utf-8",
    )
    due = T.request_due(proj, odd)
    assert due is not None
    T.mark_requested(proj, odd, due[1], due[2])
    assert T.request_due(proj, odd) is None, "once per context, whatever the id's spelling"


def test_t4_the_stop_hook_asks_exactly_once_per_context(wl):
    d = wl.base / "ctxband"
    d.mkdir()
    env = {"CTX_BAND_STATE_DIR": str(d)}

    def plant(epoch, usage):
        (d / ("%s.json" % ME)).write_text(
            json.dumps({"epoch": epoch, "band": 0, "usage": usage, "threshold": 1_000_000}),
            encoding="utf-8",
        )

    def requests():
        return [
            r
            for r in OUT.read_rows(OUT.proposals_path(wl.proj))
            if r.get("kind") == "tuner-request"
        ]

    wl.settings(effort="smart")
    plant(1, 500_000)
    wl.say("working")
    wl.run(env)
    assert requests() == []
    plant(1, 870_000)
    shown = []
    for _ in range(3):
        wl.say("still working")
        shown.append(wl.run(env).out)
    assert [(r["session"], r["epoch"]) for r in requests()] == [(ME, 1)]
    assert sum("EFFORT TUNER DUE" in s for s in shown) == 1, shown
    plant(2, 880_000)
    wl.say("after a compaction")
    assert "EFFORT TUNER DUE" in wl.run(env).out
    assert [(r["session"], r["epoch"]) for r in requests()] == [(ME, 1), (ME, 2)]


def test_t4_a_blocked_stop_still_delivers_the_request(wl):
    """A session that keeps blocking near compaction gets the request on the block itself: it is queued above every block exit, and the block digest delivers a one-line advisory."""
    d = wl.base / "ctxband"
    d.mkdir()
    (d / ("%s.json" % ME)).write_text(
        json.dumps({"epoch": 3, "band": 0, "usage": 870_000, "threshold": 1_000_000}),
        encoding="utf-8",
    )
    assert wl.cli("--add", ME, "(%s) do the thing" % ME).rc == 0
    wl.settings(effort="smart")
    wl.say("still going")
    got = wl.run({"CTX_BAND_STATE_DIR": str(d)})
    assert got.decision == "block", got.out[:400]
    assert "EFFORT TUNER DUE" in got.out, got.out[-1500:]


# ---- T5: trust ----------------------------------------------------------------------------------


def test_t5_promotions_apply_with_a_report_and_demotions_wait_for_one_ask(proj):
    T.run(proj, ME, 1, now=NOW)
    out = T.run_dir(proj, ME, 1)
    report, payload = T.apply(proj, ME, out, now=NOW)
    table = table_of(proj)
    assert table["checks"][PROMOTE_KEY] == {"block": "smart", "advise": "smart"}
    assert table["checks"][DEMOTE_KEY] == {"block": "high", "advise": "smart"}, (
        "not without the operator"
    )
    tuned = table["tuned"][PROMOTE_KEY]
    assert (tuned["direction"], tuned["tuned_at"], tuned["review_after"]) == (
        "promote",
        "2026-10-14T12:00:00Z",
        "2026-10-28T12:00:00Z",
    )
    assert any(line.startswith("effort-tune: promoted %s" % PROMOTE_KEY) for line in report)
    [question] = payload["questions"]
    assert question["options"][0]["label"] == "Demote %s" % DEMOTE_KEY
    assert '+      "block": "ultra",' in question["options"][0]["preview"]
    assert json.loads((out / "ask.json").read_text(encoding="utf-8")) == payload
    assert T.tuned_problems(table) == []


def test_t5_demotions_past_the_one_ask_are_reported_as_unasked_not_as_waiting(proj):
    """The one /ask holds ASK_QUESTIONS x ASK_OPTIONS options; the report may not claim more wait than the payload carries (fb45d045.2)."""
    T.run(proj, ME, 1, now=NOW)
    out = T.run_dir(proj, ME, 1)
    run_file = out / "run.json"
    doc = json.loads(run_file.read_text(encoding="utf-8"))
    base = next(c for c in doc["changes"] if c["direction"] == "demote")
    capacity = T.ASK_OPTIONS * T.ASK_QUESTIONS
    table = table_of(proj)
    keys = [
        k
        for k in sorted(table["checks"])
        if T.tunable(k, table) and k not in {DEMOTE_KEY, PROMOTE_KEY}
    ][: capacity + 2]
    assert len(keys) == capacity + 2, "the real table must hold enough tunable rows for the plant"
    doc["changes"] = [base] + [{**base, "key": k, "ids": ["eo-x"]} for k in keys]
    run_file.write_text(json.dumps(doc), encoding="utf-8")
    report, payload = T.apply(proj, ME, out, now=NOW)
    asked = sum(len(q["options"]) for q in payload["questions"])
    assert asked == capacity
    waiting = next(line for line in report if "wait for the operator" in line)
    assert "%d demotion(s) wait" % capacity in waiting, waiting
    over = len(doc["changes"]) - capacity
    assert any("%d more demotion(s) did not fit" % over in line for line in report), report
    pending = [r for r in T.proposal_rows(proj) if r.get("kind") == "demotion-pending"]
    assert len(pending) == capacity


def test_t5_an_accepted_answer_applies_and_is_never_asked_again(proj):
    T.run(proj, ME, 1, now=NOW)
    out = T.run_dir(proj, ME, 1)
    T.apply(proj, ME, out, now=NOW)
    line = T.answer(proj, ME, DEMOTE_KEY, "accept", "operator said yes", now=NOW)
    assert "accept of the demotion of %s" % DEMOTE_KEY in line
    table = table_of(proj)
    assert table["checks"][DEMOTE_KEY] == {"block": "ultra", "advise": "smart"}
    assert table["tuned"][DEMOTE_KEY]["direction"] == "demote"
    # The same evidence a second time asks nothing.
    E._CACHE.clear()
    T.run(proj, ME, 2, now=NOW)
    report, payload = T.apply(proj, ME, T.run_dir(proj, ME, 2), now=NOW)
    assert payload is None
    assert not any("demotion" in line and "wait" in line for line in report), report


def test_t5_a_recorded_rejection_suppresses_the_repeat_question(proj):
    T.run(proj, ME, 1, now=NOW)
    T.apply(proj, ME, T.run_dir(proj, ME, 1), now=NOW)
    T.answer(proj, ME, DEMOTE_KEY, "reject", now=NOW)
    assert table_of(proj)["checks"][DEMOTE_KEY] == {"block": "high", "advise": "smart"}
    T.run(proj, ME, 2, now=NOW)
    report, payload = T.apply(proj, ME, T.run_dir(proj, ME, 2), now=NOW)
    assert payload is None
    assert "effort-tune: demotion of %s already answered; not asked again" % DEMOTE_KEY in report
    with pytest.raises(ValueError, match="already answered"):
        T.answer(proj, ME, DEMOTE_KEY, "accept", now=NOW)


def test_t5_the_floor_is_never_tuned(proj):
    floor_key = min(FLOOR.FLOOR)
    with pytest.raises(ValueError, match="FLOOR"):
        T.answer(proj, ME, floor_key, "accept")
    with pytest.raises(ValueError, match="FLOOR"):
        T.apply_changes(
            table_of(proj),
            [
                {
                    "key": floor_key,
                    "direction": "demote",
                    "from": "floor",
                    "to": {"block": "high", "advise": "low"},
                    "ids": [],
                }
            ],
        )
    planted = table_of(proj)
    planted["tuned"] = {
        floor_key: {
            "direction": "demote",
            "tuned_at": "2026-10-14T00:00:00Z",
            "review_after": "2026-10-28T00:00:00Z",
        }
    }
    assert T.tuned_problems(planted) == [
        "tuned: %s is a FLOOR key (wl_floor.FLOOR); the tuner never touches the FLOOR" % floor_key
    ]


def test_t5_the_effort_table_gate_refuses_a_tuned_floor_key(proj, tmp_path):
    gate = REPO / ".ci" / "scripts" / "quality" / "check_plan_record.py"
    planted = table_of(proj)
    path = tmp_path / "effort.json"
    path.write_text(T.render(planted), encoding="utf-8")
    clean = subprocess.run(
        [sys.executable, str(gate), "--effort-table", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert clean.returncode == 0, clean.stderr
    floor_key = min(FLOOR.FLOOR)
    planted["tuned"] = {
        floor_key: {
            "direction": "demote",
            "tuned_at": "2026-10-14T00:00:00Z",
            "review_after": "2026-10-28T00:00:00Z",
        }
    }
    path.write_text(T.render(planted), encoding="utf-8")
    red = subprocess.run(
        [sys.executable, str(gate), "--effort-table", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert red.returncode == 1
    assert "tuned: %s is a FLOOR key" % floor_key in red.stderr


def test_t5_tuned_rows_need_their_stamps():
    table = {
        "checks": {"plan-drift": {"block": "high", "advise": "smart"}},
        "tuned": {
            "plan-drift": {
                "direction": "sideways",
                "tuned_at": "2026-10-14T00:00:00Z",
                "review_after": "2026-10-01T00:00:00Z",
            },
            "nope": {},
        },
    }
    got = T.tuned_problems(table)
    assert "tuned: nope is not a row of checks" in got
    assert "tuned: plan-drift: review_after is not after tuned_at" in got
    assert "tuned: plan-drift: direction must be promote or demote" in got


def test_t5_a_demoted_key_quiet_before_a_miss_is_promoted_back(proj):
    table = table_of(proj)
    before = dict(table["checks"][DEMOTE_KEY])
    table["checks"][DEMOTE_KEY] = {"block": "ultra", "advise": "smart"}
    table["tuned"] = {
        DEMOTE_KEY: {
            "direction": "demote",
            "from": before,
            "tuned_at": "2026-10-01T00:00:00Z",
            "review_after": "2026-10-15T00:00:00Z",
        }
    }
    rows = [row(1, DEMOTE_KEY, "advise", "high", "expired", miss=True)]
    [ch] = T.candidates(table, T.stats(rows, NOW, table=table), NOW)
    assert (ch["key"], ch["direction"], ch["to"]) == (DEMOTE_KEY, "promote", before)
    assert "re-promotion" in ch["reason"]
    # CONTROL: the same quiet row without the miss changes nothing.
    assert (
        T.candidates(table, T.stats([row(1, DEMOTE_KEY, "advise", "high", "expired")], NOW), NOW)
        == []
    )
    assert T.review_due(table, datetime.datetime(2026, 10, 16, tzinfo=datetime.UTC)) == [DEMOTE_KEY]


# ---- T2: proposals ------------------------------------------------------------------------------


def test_t2_a_proposal_without_row_citations_is_refused_and_one_with_them_appends(wl):
    OUT.append_rows(OUT.ledger_path(wl.proj), fixture_ledger())
    bare = wl.cli("--effort-propose", ME, DEMOTE_KEY, "advise@high", "it", "feels", "noisy")
    assert bare.rc == 1, (bare.rc, bare.out, bare.err)
    assert "cites no outcome row" in bare.err
    uncounted = wl.cli("--effort-propose", ME, DEMOTE_KEY, "advise@high", "rows", "eo-00000002")
    assert uncounted.rc == 1
    assert "gives no count" in uncounted.err
    foreign = wl.cli("--effort-propose", ME, DEMOTE_KEY, "advise@high", "1/10", "eo-00000011")
    assert foreign.rc == 1
    assert "are not outcome rows of %s" % DEMOTE_KEY in foreign.err
    floor = wl.cli("--effort-propose", ME, "ci-red", "off@smart", "0/6", "eo-00000017")
    assert floor.rc == 1
    assert "FLOOR" in floor.err
    assert not OUT.proposals_path(wl.proj).exists(), "a refusal writes nothing"
    good = wl.cli(
        "--effort-propose",
        ME,
        DEMOTE_KEY,
        "advise@high",
        "1/10",
        "led",
        "to",
        "work:",
        "eo-00000001",
        "eo-00000002",
    )
    assert good.rc == 0, good.err
    [prop] = OUT.read_rows(OUT.proposals_path(wl.proj))
    assert (prop["kind"], prop["key"], prop["to"], prop["cites"]) == (
        "proposal",
        DEMOTE_KEY,
        {"verdict": "advise", "level": "high"},
        ["eo-00000001", "eo-00000002"],
    )
    listing = wl.cli("--effort-propose", ME)
    assert listing.rc == 0
    assert "effort proposals: 1 recorded" in listing.out


# ---- T6: judge-error shapes --------------------------------------------------------------------


def test_t6_three_reraised_finished_items_yield_one_rule_and_its_test(tmp_path):
    rows = [
        row(
            40 + i,
            "judge",
            "block",
            "smart",
            "overruled",
            why="refuted: #%s already closed" % rid,
            subjects={"items": [rid], "plans": [], "paths": [], "tokens": []},
            text="Finish #%s before stopping." % rid,
        )
        for i, rid in enumerate(("aaaa1111", "bbbb2222", "cccc3333"))
    ]
    rows.append(row(50, "judge", "block", "smart", "work", text="Fix the failing gate."))
    [rule] = T.judge_shapes(rows)
    assert rule["shape"] == "reraised-finished"
    assert rule["ids"] == ["eo-00000028", "eo-00000029", "eo-0000002a"]
    test = tmp_path / "test_rule.py"
    test.write_text(rule["test"], encoding="utf-8")
    got = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(test)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(tmp_path),
    )
    assert got.returncode == 0, got.stdout + got.stderr
    assert "2 passed" in got.stdout
    assert T.judge_shapes(rows[:2]) == [], "two rows are not yet a shape"


# Review fb45d045.1: the status-table and rule-breaking sources were rendered as `re.compile(r%r)`, so the raw prefix on repr's escaped text turned `\b` into a literal backslash and `b`, and the generated rule matched nothing.
POSITIVES = {
    "reraised-finished": ("Finish #0badc0de first.", ("0badc0de",)),
    "status-table": ("List every open item by id with its state.", ()),
    "rule-breaking": ("First ask the operator whether to proceed.", ()),
}


@pytest.mark.parametrize("shape", sorted(POSITIVES))
def test_each_generated_judge_rule_matches_its_shape_and_not_its_control(shape):
    spec = next(s for s in T.JUDGE_SHAPES if s["shape"] == shape)
    ns: dict = {}
    exec(compile(spec["source"], "<rule:%s>" % shape, "exec"), ns)
    assert ns["matches"](*POSITIVES[shape]) is True
    assert ns["matches"](*spec["control"]) is False
