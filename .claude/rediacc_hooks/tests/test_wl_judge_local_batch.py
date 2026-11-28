"""`--plan-investigate ... partial` carries what the box still owes (agent/plans/PLAN-stop-hook-retro-20261110.md R20261110.1).

R20261110.1  `--plan-investigate ... partial` requires `--owed <kind>` and stores it on the row, so what a partial box still owes is a field and not a free-text note.

The judge's local-batch paragraph (R20261110.2: JUDGE_LOCAL_BATCH, `local_batch_boxes`, `settle_batch_no_local`, `live_owed_boxes`) left with the local batch it described (agent/plans/PLAN-simple-two-tree-loop.md B4, B5); `test_the_local_batch_judge_surface_is_gone` keeps it gone. Every case has its inverse, differing by one planted fact.
"""

from __future__ import annotations

import inspect
import json

import pytest

from rediacc_hooks.tests import wlfix

J = wlfix.import_wl("wl_judge")
R = wlfix.import_wl("wl_planrec")
M = wlfix.import_wl("worklist_messages")

REL = "agent/plans/PLAN-batch-fixture.md"
NOTE = "the parser half of this box is in the tree; the rest is a live step on the fleet"


def test_the_local_batch_judge_surface_is_gone():
    """B5: no caller passes `local_batch` since B4 deleted the local batch, so the parameter, its paragraph, its settle and its sanitiser arm are deleted with it."""
    params = inspect.signature(J.run_judge).parameters
    assert "local_batch" not in params
    assert "receipt_run" in params  # CONTROL: the sibling paragraph the same block carried stays
    for name in ("settle_batch_no_local", "local_batch_boxes", "live_owed_boxes", "BATCH_WORDS"):
        assert not hasattr(J, name), name
    for name in ("JUDGE_LOCAL_BATCH", "V_JUDGE_BATCH_ORDER_REJECTED", "N_BACKUP_PUSH"):
        assert not hasattr(M, name), name
    assert hasattr(M, "JUDGE_RECEIPT_IN_FLIGHT")


# ---- R20261110.1: --owed on a partial investigation ---------------------------------------------


@pytest.fixture
def wl(tmp_path):
    fixture = wlfix.Fixture(tmp_path / "hookfix")
    fixture.setup()
    return fixture


def plant_plan(fix):
    body = "B1 the one open box this row investigates"
    (fix.proj / "agent" / "plans").mkdir(parents=True, exist_ok=True)
    (fix.proj / REL).write_text(
        "# PLAN: owed fixture\nStatus: ready\nOwner: %s\nUpdated: 2026-11-10\n\n"
        "## Tasks\n\n- [ ] %s\n" % (fix.sid, body),
        encoding="utf-8",
    )
    (fix.proj / "seed.txt").write_text("seed line\n", encoding="utf-8")
    return R.box_sig(body)


def investigate(fix, sig, verdict, *flags):
    return fix.cli(
        "--plan-investigate",
        wlfix.ME,
        REL,
        sig,
        verdict,
        *flags,
        "fileline:seed.txt:1",
        "plan:%s" % REL,
        "--",
        NOTE,
        "--write",
    )


def ledger_rows(fix):
    path = fix.proj.joinpath(*R.INVESTIGATION_REL)
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_a_partial_without_owed_is_refused_and_the_refusal_names_the_flag(wl):
    sig = plant_plan(wl)
    got = investigate(wl, sig, "partial")
    assert got.rc == 2, (got.rc, got.out, got.err)
    assert "--owed" in got.err, got.err
    assert ledger_rows(wl) == []


def test_a_partial_with_owed_writes_the_kind_on_the_row(wl):
    sig = plant_plan(wl)
    got = investigate(wl, sig, "partial", "--owed", "live")
    assert got.rc == 0, (got.rc, got.out, got.err)
    [row] = ledger_rows(wl)
    assert row["verdict"] == "partial"
    assert row["owed"] == "live"


def test_control_an_absent_verdict_needs_no_owed_and_carries_none(wl):
    sig = plant_plan(wl)
    got = investigate(wl, sig, "absent")
    assert got.rc == 0, (got.rc, got.out, got.err)
    [row] = ledger_rows(wl)
    assert "owed" not in row


@pytest.mark.parametrize(
    ("verdict", "kind", "needle"),
    [("absent", "live", "belongs to a `partial`"), ("partial", "soon", "is not one of")],
)
def test_owed_on_another_verdict_or_an_unknown_kind_is_refused(wl, verdict, kind, needle):
    sig = plant_plan(wl)
    got = investigate(wl, sig, verdict, "--owed", kind)
    assert got.rc == 2, (got.rc, got.out, got.err)
    assert needle in got.err, got.err
    assert ledger_rows(wl) == []


def test_owed_with_no_kind_is_a_usage_error(wl):
    sig = plant_plan(wl)
    got = wl.cli(
        "--plan-investigate", wlfix.ME, REL, sig, "partial", "fileline:seed.txt:1", "--owed"
    )
    assert got.rc == 2, (got.rc, got.out, got.err)
    assert "--owed takes a kind" in got.err, got.err
