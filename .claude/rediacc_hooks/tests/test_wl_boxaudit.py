"""Tests for `wl_boxaudit.py`, box T9 of agent/plans/PLAN-tick-tracking.md (`worklist.py --box-audit`).

One fixture repository holds a plan with one box per verdict, a live branch past `main`, a lease commit landed with `cherry-pick -x` that carries no trailer, a report store whose TICK line names that lease commit, and the three ledgers. Each verdict is asserted on its own box.

THE CONTROL is the report store pointed at an empty directory: the box linked only by its report reads `untouched`, which proves report linkage is what finds work that carries no trailer.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from rediacc_hooks.tests import wlfix

BA = wlfix.import_wl("wl_boxaudit")
R = wlfix.import_wl("wl_planrec")
ME = "deadbeef"
BODIES = {
    "tick": "T1 the tickable box of the fixture plan",
    "stale": "T2 the stale box of the fixture plan",
    "live": "T3 the live-owed box of the fixture plan",
    "untouched": "T4 the untouched box of the fixture plan",
    "linked": "T5 the linked box of the fixture plan",
    "lp": "LP-bench [live] T6 the proved live box of the fixture plan",
}
SIG = {k: R.box_sig(v) for k, v in BODIES.items()}
PLAN = "PLAN-fx.md"
REL = "agent/plans/" + PLAN
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
}


def _git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _commit(root, name, message):
    (root / name).write_text(name + "\n", encoding="utf-8")
    _git(root, "add", "--", name)
    _git(root, "commit", "-q", "--no-gpg-sign", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


class World:
    def __init__(self, root, reports, shas):
        self.root = root
        self.reports = reports
        self.shas = shas


@pytest.fixture
def world(tmp_path, monkeypatch):
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    root = (tmp_path / "proj").resolve()
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    plan = root / "agent" / "plans" / PLAN
    plan.parent.mkdir(parents=True)
    plan.write_text(
        "# PLAN: fx\n\nStatus: approved\nOwner: %s\n\n## Tasks\n\n" % ME
        + "".join("- [ ] %s\n" % b for b in BODIES.values()),
        encoding="utf-8",
    )
    base = _commit(root, "base.txt", "base")
    # A commit no branch keeps: the stale row's head.
    _git(root, "switch", "-q", "-c", "gone")
    gone = _commit(root, "gone.txt", "chore: a commit a rebase dropped")
    _git(root, "switch", "-q", "main")
    _git(root, "branch", "-q", "-D", "gone")
    # The lease commit, on a side line, picked onto the live branch with -x and no trailer.
    _git(root, "switch", "-q", "-c", "lease")
    lease = _commit(root, "lease.txt", "feat: the live-owed code half\n\nPR-TASK: 1d805023\n")
    _git(root, "switch", "-q", "-c", "0101-1", "main")
    tick = _commit(
        root, "t1.txt", "feat: t1\n\nPlan-Box: %s#%s clauses=all\n" % (PLAN, SIG["tick"])
    )
    stale = _commit(
        root, "t2.txt", "feat: t2\n\nPlan-Box: %s#%s clauses=all\n" % (PLAN, SIG["stale"])
    )
    linked = _commit(
        root, "t5.txt", "feat: t5\n\nPlan-Box: %s#%s clauses=C1\n" % (PLAN, SIG["linked"])
    )
    lp_code = _commit(
        root, "t6.txt", "feat: t6\n\nPlan-Box: %s#%s clauses=all\n" % (PLAN, SIG["lp"])
    )
    _git(root, "cherry-pick", "-x", lease)
    picked = _git(root, "rev-parse", "HEAD")
    head = picked
    _jsonl(
        root / "agent" / "ledgers" / "plan-investigation.jsonl",
        [
            {"plan": REL, "sig": SIG["tick"], "verdict": "absent", "head": base},
            {"plan": REL, "sig": SIG["stale"], "verdict": "absent", "head": gone},
            {"plan": REL, "sig": SIG["linked"], "verdict": "absent", "head": base},
            {"plan": REL, "sig": SIG["lp"], "verdict": "absent", "head": base},
        ],
    )
    _jsonl(
        root / "agent" / "ledgers" / "plan-box-progress.jsonl",
        [
            {
                "kind": "define",
                "plan": REL,
                "sig": SIG["linked"],
                "clauses": [
                    {"id": "C1", "half": "code", "text": "one code half"},
                    {"id": "C2", "half": "code", "text": "another code half"},
                ],
            }
        ],
    )
    _jsonl(
        root / "agent" / "ledgers" / "live-proof.jsonl",
        [
            {
                "id": "lp-000000000001",
                "plan": REL,
                "box": SIG["lp"],
                "status": "VERIFIED",
                "head": head,
                "target": "bench",
                "check": {"id": "c", "rc": 0},
            },
            {
                "id": "lp-000000000002",
                "plan": REL,
                "box": SIG["live"],
                "status": "VERIFIED",
                "head": base,
                "target": "bench",
                "check": {"id": "c", "rc": 0},
            },
        ],
    )
    reports = tmp_path / "reports"
    body = (
        "Done with the code half.\n\n"
        "TICK %s#%s partial commits=%s landed=all owed=C2:live\n"
        "  close: worklist.py --live-proof %s %s %s --write\n"
        % (PLAN, SIG["live"], lease[:9], ME, REL, SIG["live"])
    )
    (reports / "0101-1").mkdir(parents=True)
    (reports / "0101-1" / "w.md").write_text("---\nagent_id: a1\n---\n\n" + body, encoding="utf-8")
    _jsonl(
        reports / "index.jsonl",
        [
            {
                "ev": "report",
                "id": "rep000000001",
                "at": "2099-01-01T00:00:00Z",
                "body": "0101-1/w.md",
            }
        ],
    )
    monkeypatch.setenv("WORKLIST_REPORTS_DIR", str(reports))
    shas = {
        "tick": tick,
        "stale": stale,
        "linked": linked,
        "lp": lp_code,
        "live": picked,
        "lease": lease,
    }
    return World(root, reports, shas)


def _by_sig(rows):
    return {a.sig: a for a in rows}


def test_one_verdict_per_box(world):
    rows, _head, _base = BA.audit(world.root, ME)
    got = {k: _by_sig(rows)[SIG[k]].verdict for k in BODIES}
    assert got == {
        "tick": "tickable-now",
        "stale": "stale-investigation",
        "live": "live-owed",
        "untouched": "untouched",
        "linked": "linked",
        "lp": "tickable-now",
    }


def test_tickable_now_prints_the_ready_plan_tick_line(world):
    a = _by_sig(BA.audit(world.root, ME)[0])[SIG["tick"]]
    assert a.tick == "worklist.py --plan-tick %s %s %s 'commit:%s landed for box %s' --write" % (
        ME,
        REL,
        SIG["tick"],
        world.shas["tick"][:12],
        SIG["tick"],
    )


def test_a_verified_receipt_on_the_landed_code_proves_the_lp_box(world):
    a = _by_sig(BA.audit(world.root, ME)[0])[SIG["lp"]]
    assert "live-proof lp-000000000001" in a.tick


def test_live_owed_box_is_linked_by_its_report_through_the_x_line(world):
    a = _by_sig(BA.audit(world.root, ME)[0])[SIG["live"]]
    assert [s for s, _src in a.landed] == [world.shas["live"]]
    assert a.owed == [("C2", "live")]
    assert a.lp == [], "a receipt taken before the landed code proves nothing"
    assert "--plan-investigate" in a.investigate
    assert world.shas["lease"][:12] not in a.investigate


def test_stale_investigation_names_the_unreachable_head(world):
    a = _by_sig(BA.audit(world.root, ME)[0])[SIG["stale"]]
    assert "unreachable from HEAD with no rebase successor" in a.why


def test_render_sha_names_each_landed_sha_against_its_box(world):
    rows, head, base = BA.audit(world.root, ME)
    text, rc = BA.render(rows, head, base, shas=[world.shas["live"][:9], "0000000"])
    assert rc == 0
    assert "%s -> live-owed" % world.shas["live"][:9] in text
    assert "0000000 untouched" in text


def test_mixed_unsplit_lists_landed_boxes_with_no_map_and_exits_1(world):
    rows, head, base = BA.audit(world.root, ME)
    text, rc = BA.render(rows, head, base, mixed=True)
    assert rc == 1
    for k in ("tick", "stale", "live", "lp"):
        assert "#%s" % SIG[k] in text
    assert "#%s" % SIG["linked"] not in text


def test_live_owed_filter_lists_only_the_live_owed_box(world):
    rows, head, base = BA.audit(world.root, ME)
    text, _rc = BA.render(rows, head, base, live_owed=True)
    assert "#%s" % SIG["live"] in text
    assert "#%s" % SIG["tick"] not in text


def test_control_an_empty_report_store_leaves_the_report_linked_box_untouched(world, monkeypatch):
    empty = world.reports.parent / "empty"
    empty.mkdir()
    monkeypatch.setenv("WORKLIST_REPORTS_DIR", str(empty))
    # The old receipt of the live box is dropped too: with no landed commit it would prove the box on its own, and the control is about the report alone.
    ledger = world.root / "agent" / "ledgers" / "live-proof.jsonl"
    ledger.write_text(ledger.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    rows, head, base = BA.audit(world.root, ME)
    assert _by_sig(rows)[SIG["live"]].verdict == "untouched"
    text, _ = BA.render(rows, head, base, shas=[world.shas["live"][:9]])
    assert "%s untouched" % world.shas["live"][:9] in text


def test_cli_box_audit_runs_from_the_project(world):
    done = subprocess.run(
        ["python3", str(wlfix.HOOK), "--box-audit", ME, "--mixed-unsplit"],
        cwd=str(world.root),
        env={
            **wlfix.scrubbed_environ(),
            "CLAUDE_PROJECT_DIR": str(world.root),
            "WORKLIST_SESSION_ID": wlfix.SID,
            "WORKLIST_REPORTS_DIR": str(world.reports),
            **GIT_ENV,
            "TMPDIR": str(world.root.parent / "tmp"),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 1, done.stderr
    assert "open box(es) with landed work and no clause map" in done.stdout
    assert pathlib.Path(world.root / "agent" / "plans" / PLAN).is_file()


# ---- T11: live-owed on release ------------------------------------------------------------


def test_release_of_an_item_naming_a_landed_box_appends_live_owed_and_lists_it(world):
    pb = wlfix.import_wl("wl_planbox")
    rows = BA.release_live_owed(world.root, "finish the box %s" % SIG["live"], ME, "abcd1234")
    assert [(r["sig"], r["clause"], r["state"], r["ref"]) for r in rows] == [
        (SIG["live"], "all", "live-owed", "released #abcd1234")
    ]
    assert pb.box_state(world.root, REL, SIG["live"])["all"][0] == "live-owed"
    again = BA.release_live_owed(world.root, "finish the box %s" % SIG["live"], ME, "abcd1234")
    assert again == []
    audit, head, base = BA.audit(world.root, ME)
    text, _rc = BA.render(audit, head, base, live_owed=True)
    assert "#%s" % SIG["live"] in text


def test_release_control_a_box_with_no_landed_work_appends_nothing(world):
    ledger = world.root / "agent" / "ledgers" / "plan-box-progress.jsonl"
    before = ledger.read_bytes()
    assert BA.release_live_owed(world.root, "box %s" % SIG["untouched"], ME, "abcd1234") == []
    assert BA.release_live_owed(world.root, "no box named here", ME, "abcd1234") == []
    assert ledger.read_bytes() == before


def test_release_control_the_message_stays_byte_identical(wl):
    added = wl.cli("--add", wlfix.ME, "release probe for box 0123abcd")
    item = added.out.split("#", 1)[1].split()[0].rstrip(":.,")
    assert wl.cli("--lease", wlfix.ME, item, "+30", "worker:relbg").rc == 0
    got = wl.cli("--lease", wlfix.ME, item, "release")
    assert got.rc == 0, got.err
    assert got.out == (
        "released #%s back to open; it is ordinary open work again, claimed by no worker\n" % item
    )


def test_release_writes_and_lists_the_live_owed_row_through_the_cli_helper(world, capsys):
    """Review 0e0808a5.1, CONTROL half: the helper the `--lease ... release` branch calls writes the row and lists it, rc 0."""
    wl = wlfix.import_wl("worklist")
    assert wl._release_live_owed(world.root, "box %s" % SIG["live"], ME, "beef0001") == 0
    got = capsys.readouterr()
    assert "live-owed %s#%s clause all" % (PLAN, SIG["live"]) in got.out
    assert got.err == ""


def test_release_names_a_failed_live_owed_write_and_exits_1(world, capsys, monkeypatch):
    """Review 0e0808a5.1: an audit or ledger failure was swallowed by `contextlib.suppress(Exception)`, so the release read as complete with the half unscheduled. It is said now, with the command that lists what is owed."""
    wl = wlfix.import_wl("worklist")

    def broken(*_a, **_k):
        raise OSError("ledger is read-only")

    monkeypatch.setattr(BA, "release_live_owed", broken)
    assert wl._release_live_owed(world.root, "box %s" % SIG["live"], ME, "beef0002") == 1
    err = capsys.readouterr().err
    assert "live-owed: NOT WRITTEN for #beef0002 (OSError: ledger is read-only)" in err
    assert "--box-audit %s --live-owed" % ME in err


def test_state_owed_demand_reads_the_cached_audit(world, capsys):
    """Review a94cd7a7.2: the `--state` wiring hands `agent_state_shape` exactly what the cached audit answers, silently."""
    wl = wlfix.import_wl("worklist")
    assert wl._owed_for_state(world.root, ME) == BA.owned_owed_cached(world.root, ME)
    assert capsys.readouterr().err == ""


def test_state_owed_demand_says_when_the_audit_cannot_run(world, capsys, monkeypatch):
    """Review a94cd7a7.2: a failing audit demands nothing (the document is never locked), and says the demand went unchecked rather than reading as nothing owed."""
    wl = wlfix.import_wl("worklist")

    def broken(*_a, **_k):
        raise ValueError("bad ledger row")

    monkeypatch.setattr(BA, "owned_owed_cached", broken)
    assert wl._owed_for_state(world.root, ME) is None
    assert "owed ticks: UNCHECKED" in capsys.readouterr().err


@pytest.mark.parametrize("cached", ["uninvestigated_cached", "owned_owed_cached"])
def test_the_audit_cache_misses_on_every_input_it_reads(world, monkeypatch, tmp_path, cached):
    """Review 82fd346d.1 and ec1efb0e.2: at one HEAD a plan edit, a live-proof row or a captured report changes a verdict, so each must miss the cache. CONTROL: an unchanged world hits it."""
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    fn = getattr(BA, cached)
    fn(world.root, ME)
    calls = []
    real = BA.audit

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(BA, "audit", counting)
    fn(world.root, ME)
    assert calls == [], "an unchanged world missed the cache"
    plan = world.root / "agent" / "plans" / PLAN
    ledger = world.root / "agent" / "ledgers" / "live-proof.jsonl"
    for path in (plan, ledger):
        before = path.read_bytes()
        try:
            path.write_bytes(before + b"\n")
            fn(world.root, ME)
        finally:
            path.write_bytes(before)
        assert calls, "a change to %s hit the stale cache" % path.name
        calls.clear()
        fn(world.root, ME)
        calls.clear()


# ---- T10: the blocking check plan-box-owed -----------------------------------------------


def test_stopcheck_quiet_for_two_stops_blocks_on_the_third_and_the_row_silences_it(world):
    memo = None
    key = "%s#%s" % (PLAN, SIG["live"])
    for stop in (1, 2, 3):
        rows, _h, _b = BA.audit(world.root, ME)
        memo, blocking = BA.stop_check(memo, BA.uninvestigated(rows))
        keys = [k for k, _l, _c in blocking]
        if stop < 3:
            assert keys == []
        else:
            assert keys == [key]
            assert "--plan-investigate" in blocking[0][2]
            assert "live-owed" in blocking[0][1]
    inv = world.root / "agent" / "ledgers" / "plan-investigation.jsonl"
    row = {"plan": REL, "sig": SIG["live"], "verdict": "partial", "head": world.shas["live"]}
    with inv.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    rows, _h, _b = BA.audit(world.root, ME)
    memo, blocking = BA.stop_check(memo, BA.uninvestigated(rows))
    assert blocking == []
    assert key not in memo


def test_stopcheck_the_key_is_in_the_effort_table_and_off_at_quiet():
    effort = wlfix.import_wl("wl_effort")
    blocking, _advisory = effort.produced_keys()
    assert "plan-box-owed" in blocking
    assert effort.verdict("plan-box-owed", "quiet") == "off"
    assert effort.verdict("plan-box-owed", "low") != "block"
    assert effort.verdict("plan-box-owed", "smart") == "block"
