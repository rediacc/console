"""wl_liveproof: the `worklist.py --live-proof` verb (agent/plans/PLAN-tested-on-bench.md, Design item "Agent verb").

Every run case drives `wl_liveproof.run` against a plan planted in a temporary root, with a FAKE recorder that records the argv it is handed and a FAKE tick that records its calls, so "the recorder never ran" and "the box was not ticked" are reads of a call log rather than an absence of errors. The Accept parser is the real `rediacc_ci.proof.live_tier.accept_of`, reached the way the verb reaches it. No case runs the real recorder.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from rediacc_hooks.tests import wlfix
from rediacc_hooks.wellknown import BENCH_ORIGIN

if TYPE_CHECKING:
    import pathlib

LP = wlfix.import_wl("wl_liveproof")
ROOT = wlfix.STOP_DIR.parents[2]
ME = "d778be9d"
ROW_ID = "lp-0123456789ab"
REL = "agent/plans/PLAN-lp-fixture.md"

PLAN = (
    """# Plan: fixture

Status: in-progress
Owns: packages/x/**

## Tasks

- [ ] T1 an ordinary code box. Accept: `grep -n x file` rc=0
- [ ] LP-bench [live] Fresh bench receipt.
  - Accept: `live-proof bench account-smoke`
- [ ] LP-hostinger [live] Fresh hostinger receipt on one machine.
  - Accept: `live-proof hostinger renet-live machine=eu-1`
- [ ] LP-www [live] A box whose Accept is not a live-proof form.
  - Accept: `curl -fsS %s/` rc=0
- [ ] LP-cli [live] A box with no Accept line at all.
- [ ] LP-region [live] A box whose Accept carries an argument the registry does not take.
  - Accept: `live-proof bench account-smoke region=eu`
- [x] LP-done [live] An already ticked box.
  - Accept: `live-proof bench account-smoke`
"""
    % BENCH_ORIGIN
)


def _sig(text: str, label: str) -> str:
    for _i, _line, body, sig in LP.R.open_boxes(text):
        if body.startswith(label + " "):
            return sig
    raise AssertionError("no open box %s in the fixture" % label)


def _line(text: str, label: str) -> int:
    for i, raw in enumerate(text.splitlines()):
        if re.search(r"\]\s+%s\s" % re.escape(label), raw):
            return i
    raise AssertionError(label)


class FakeRecorder:
    """Records each argv; on rc 0 with --write it appends a VERIFIED row for the requested plan/box and names it on stderr, the way the real recorder's log.info does."""

    def __init__(self, root: pathlib.Path, rc: int = 0, err: str = "", write_row: bool = True):
        self.root, self.rc, self.err, self.write_row = root, rc, err, write_row
        self.calls: list[list[str]] = []

    def __call__(self, argv, _root):
        argv = list(argv)
        self.calls.append(argv)
        if self.rc != 0:
            return self.rc, "", self.err
        if "--write" not in argv:
            return 0, "", "VERIFIED %s: dry run, nothing written (--write appends)\n" % ROW_ID
        if self.write_row:
            row = {
                "id": ROW_ID,
                "status": "VERIFIED",
                "plan": argv[argv.index("--plan") + 1],
                "box": argv[argv.index("--box") + 1],
                "target": argv[argv.index("--target") + 1],
                "check": {"id": argv[argv.index("--check") + 1], "rc": 0},
                "deploy": {"version_id": "4b9f3b44-58f9-4e59-a54e-b3e5434749f6"},
            }
            ledger = self.root / LP.LEDGER_REL
            ledger.parent.mkdir(parents=True, exist_ok=True)
            with ledger.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
        return 0, "", "VERIFIED %s: appended to agent/ledgers/live-proof.jsonl\n" % ROW_ID


class FakeTick:
    def __init__(self, rc: int = 0):
        self.rc = rc
        self.calls: list[tuple[str, str, str]] = []

    def __call__(self, rel, sig, evidence):
        self.calls.append((rel, sig, evidence))
        return self.rc


@pytest.fixture
def root(tmp_path):
    (tmp_path / "agent" / "plans").mkdir(parents=True)
    (tmp_path / REL).write_text(PLAN, encoding="utf-8")
    return tmp_path


def _run(root, *args, rec=None, tick=None, precheck=None):
    rec = rec or FakeRecorder(root)
    tick = tick or FakeTick()
    rc = LP.run(
        root,
        ME,
        list(args),
        tick=tick,
        recorder=rec,
        precheck=precheck or (lambda *_a: None),
    )
    return rc, rec, tick


# ---------------------------------------------------------------- Accept parsing


@pytest.mark.parametrize(
    ("label", "want"),
    [
        ("LP-bench", ("bench", "account-smoke", None)),
        ("LP-hostinger", ("hostinger", "renet-live", "eu-1")),
    ],
)
def test_accept_forms_parse(label, want):
    assert LP.parse_accept(PLAN, _line(PLAN, label)) == want


def test_every_live_proof_accept_line_in_the_tree_parses():
    """Read-only over the live plans: every `Accept: live-proof` sub-line under an LP box is a form the verb runs. Both forms in use today (bench account-smoke, hostinger renet-live) are reached here."""
    seen = set()
    for plan in sorted((ROOT / "agent" / "plans").glob("PLAN-*.md")):
        text = plan.read_text(encoding="utf-8", errors="replace")
        for i, _line, _body, _sig in LP.lp_boxes(text):
            raw = LP.accept_raw(text, i)
            if raw and raw.startswith("live-proof"):
                seen.add(LP.parse_accept(text, i))
    if not seen:
        pytest.skip("no open LP box with a live-proof Accept line in this tree")
    assert all(t and c for t, c, _m in seen), seen


def test_accept_not_a_live_proof_form_is_refused():
    with pytest.raises(LP.RefusedError, match="not a live-proof form"):
        LP.parse_accept(PLAN, _line(PLAN, "LP-www"))


def test_accept_inline_on_the_box_line_is_named_in_the_refusal():
    with pytest.raises(LP.RefusedError, match=r"`grep -n x file rc=0` is not a live-proof form"):
        LP.parse_accept(PLAN, _line(PLAN, "T1"))


def test_no_accept_line_is_refused():
    with pytest.raises(LP.RefusedError, match="carries no Accept line"):
        LP.parse_accept(PLAN, _line(PLAN, "LP-cli"))


def test_accept_with_an_unknown_argument_is_refused():
    with pytest.raises(LP.RefusedError, match="not a form the recorder runs"):
        LP.parse_accept(PLAN, _line(PLAN, "LP-region"))


def test_lp_boxes_are_open_lp_boxes_only():
    labels = {body.split()[0] for _i, _l, body, _s in LP.lp_boxes(PLAN)}
    assert labels == {"LP-bench", "LP-hostinger", "LP-www", "LP-cli", "LP-region"}


# ---------------------------------------------------------------- the run


def test_dry_run_calls_the_recorder_without_write_and_never_ticks(root):
    sig = _sig(PLAN, "LP-bench")
    rc, rec, tick = _run(root, REL, sig)
    assert rc == 0
    assert rec.calls == [
        [
            sys.executable,
            "-m",
            "rediacc_ci.ops.live_proof",
            "record",
            "--plan",
            REL,
            "--box",
            sig,
            "--target",
            "bench",
            "--check",
            "account-smoke",
            "--by",
            ME,
        ]
    ]
    assert tick.calls == []


def test_write_is_passed_through_and_no_tick_without_the_flag(root, capsys):
    sig = _sig(PLAN, "LP-bench")
    rc, rec, tick = _run(root, REL, sig, "--write")
    assert rc == 0
    assert rec.calls[0][-1] == "--write"
    assert tick.calls == []
    out = capsys.readouterr().out
    assert "worklist.py --plan-tick %s %s %s" % (ME, REL, sig) in out


def test_write_tick_ticks_once_with_the_receipt_evidence(root):
    sig = _sig(PLAN, "LP-bench")
    rc, rec, tick = _run(root, REL, sig, "--write", "--tick")
    assert rc == 0
    assert "--write" in rec.calls[0]
    assert tick.calls == [
        (
            REL,
            sig,
            "live-proof %s bench account-smoke rc=0 v=4b9f3b44-58f9-4e59-a54e-b3e5434749f6"
            % ROW_ID,
        )
    ]


def test_machine_argument_reaches_the_recorder(root):
    sig = _sig(PLAN, "LP-hostinger")
    _rc, rec, _tick = _run(root, REL, sig)
    argv = rec.calls[0]
    assert argv[argv.index("--target") + 1] == "hostinger"
    assert argv[argv.index("--check") + 1] == "renet-live"
    assert argv[argv.index("--machine") + 1] == "eu-1"


def test_recorder_failure_surfaces_rc_and_stderr_and_never_ticks(root, capsys):
    sig = _sig(PLAN, "LP-bench")
    rec = FakeRecorder(root, rc=1, err="NOT_VERIFIED not-live: the live version moved\n")
    rc, rec, tick = _run(root, REL, sig, "--write", "--tick", rec=rec)
    assert rc == 1
    assert tick.calls == []
    err = capsys.readouterr().err
    assert "rc=1" in err
    assert "NOT_VERIFIED not-live: the live version moved" in err


def test_recorder_usage_error_rc_is_kept(root):
    rec = FakeRecorder(root, rc=2, err="--plan x is finished\n")
    rc, _rec, tick = _run(root, REL, _sig(PLAN, "LP-bench"), "--write", "--tick", rec=rec)
    assert rc == 2
    assert tick.calls == []


def test_rc0_without_a_written_row_never_ticks(root, capsys):
    rec = FakeRecorder(root, write_row=False)
    rc, _rec, tick = _run(root, REL, _sig(PLAN, "LP-bench"), "--write", "--tick", rec=rec)
    assert rc == 1
    assert tick.calls == []
    assert "no VERIFIED row of this box" in capsys.readouterr().err


def test_a_refused_tick_names_the_plan_tick_command(root, capsys):
    sig = _sig(PLAN, "LP-bench")
    rc, _rec, tick = _run(root, REL, sig, "--write", "--tick", tick=FakeTick(rc=2))
    assert rc == 2
    assert len(tick.calls) == 1
    err = capsys.readouterr().err
    assert ROW_ID in err
    assert "worklist.py --plan-tick %s %s %s" % (ME, REL, sig) in err


def test_tick_without_write_is_refused_before_the_recorder(root):
    rc, rec, tick = _run(root, REL, _sig(PLAN, "LP-bench"), "--tick")
    assert rc == 2
    assert rec.calls == []
    assert tick.calls == []


def test_precheck_refusal_runs_no_recorder(root, capsys):
    rc, rec, tick = _run(
        root,
        REL,
        _sig(PLAN, "LP-bench"),
        "--write",
        "--tick",
        precheck=lambda *_a: "no investigation row",
    )
    assert rc == 2
    assert rec.calls == []
    assert tick.calls == []
    assert "no investigation row" in capsys.readouterr().err


def test_default_precheck_wants_an_investigation_row(root):
    msg = LP.tick_precheck(root, REL, _sig(PLAN, "LP-bench"), ME)
    assert msg
    assert "--plan-investigate" in msg


def test_precheck_passes_with_a_live_investigation_row_and_refuses_a_retro_one(root, monkeypatch):
    sig = _sig(PLAN, "LP-bench")
    monkeypatch.setattr(LP.R, "investigation_for", lambda _root, _rel, _sig: {"verdict": "absent"})
    assert LP.tick_precheck(root, REL, sig, ME) is None
    # Control: a retro row is not a live investigation, so the precheck refuses again.
    monkeypatch.setattr(
        LP.R, "investigation_for", lambda _root, _rel, _sig: {"verdict": "absent", "retro": True}
    )
    assert LP.tick_precheck(root, REL, sig, ME)


def test_evidence_reads_the_check_rc_from_the_row():
    row = {
        "id": "lp-1",
        "target": "bench",
        "check": {"id": "account-smoke", "rc": 3},
        "deploy": {"version_id": "v9"},
    }
    assert LP.evidence(row) == "live-proof lp-1 bench account-smoke rc=3 v=v9"
    for bad in ({"id": "account-smoke"}, {"id": "account-smoke", "rc": None}):
        row["check"] = bad
        assert LP.evidence(row) == "live-proof lp-1 bench account-smoke rc=unknown v=v9"


@pytest.mark.parametrize("bad_rc", [None, 0.0, "0", True])
def test_null_check_rc_is_never_a_pass_and_tick_refuses(root, capsys, bad_rc):
    class NullRc(FakeRecorder):
        def __call__(self, argv, _root):
            out = super().__call__(argv, _root)
            if "--write" in argv:
                ledger = self.root / LP.LEDGER_REL
                row = json.loads(ledger.read_text(encoding="utf-8").splitlines()[-1])
                row["check"]["rc"] = bad_rc
                ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")
            return out

    sig = _sig(PLAN, "LP-bench")
    rc, _rec, tick = _run(root, REL, sig, "--write", "--tick", rec=NullRc(root))
    assert rc == 1
    assert tick.calls == []
    err = capsys.readouterr().err
    assert "account-smoke" in err
    assert "rc=unknown" in err
    assert "rc=0 v=" not in err


def test_a_recorder_past_its_timeout_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(LP, "RECORDER_TIMEOUT_S", 1)
    rc, _out, err = LP.run_recorder([sys.executable, "-c", "import time; time.sleep(5)"], tmp_path)
    assert rc == 124
    assert "past 1 s" in err


@pytest.mark.parametrize(
    ("args", "needle"),
    [
        (("agent/plans/PLAN-absent.md", "deadbeef"), "unknown plan"),
        ((REL, "T1"), "is not an open LP box"),
        ((REL, "LP-done"), "is not an open LP box"),
        ((REL, "LP-www"), "not a live-proof form"),
        ((REL, "LP-cli"), "carries no Accept line"),
        ((REL, "LP-bench", "--force"), "unknown flag"),
        ((REL,), "pass a plan and one box"),
    ],
)
def test_refusals_run_no_recorder(root, capsys, args, needle):
    rc, rec, tick = _run(root, *args)
    assert rc == 2
    assert rec.calls == []
    assert tick.calls == []
    assert needle in capsys.readouterr().err


def test_a_plan_outside_the_live_folder_is_refused(root, capsys):
    done = root / "agent" / "plans" / "_done" / "PLAN-old.md"
    done.parent.mkdir()
    done.write_text(PLAN, encoding="utf-8")
    rc, rec, _tick = _run(root, "agent/plans/_done/PLAN-old.md", "LP-bench")
    assert rc == 2
    assert rec.calls == []
    assert "not a live plan" in capsys.readouterr().err


def test_bare_plan_name_resolves_under_agent_plans(root):
    rc, rec, _tick = _run(root, "PLAN-lp-fixture.md", "LP-bench")
    assert rc == 0
    assert rec.calls[0][rec.calls[0].index("--plan") + 1] == REL


# ---------------------------------------------------------------- the worklist.py arm


def test_cli_with_no_arguments_prints_usage_and_exits_nonzero():
    got = subprocess.run(
        [sys.executable, str(wlfix.STOP_DIR / "worklist.py"), "--live-proof"],
        capture_output=True,
        text=True,
        env=wlfix.scrubbed_environ(),
        stdin=subprocess.DEVNULL,
        check=False,
        timeout=60,
    )
    assert got.returncode == 2
    assert "usage: worklist.py --live-proof <me>" in got.stderr
    assert got.stdout == ""
