"""The local-batch judge paragraph is told which open boxes are local work (agent/plans/PLAN-stop-hook-retro-20261110.md R20261110.1, R20261110.2).

In the 2026-11-09/10 window JUDGE_LOCAL_BATCH ended with "the next action advances the batch's open boxes locally" on every judge call, and 55 continues ordered box work that did not exist: every open box needed a live system, a CI run, the operator or a push. Two halves fix it:

  R20261110.1  `--plan-investigate ... partial` requires `--owed <kind>` and stores it on the row, so what a partial box still owes is a field and not a free-text note.
  R20261110.2  `wl_checks._batch_box_facts` classes each open box of the batch `non-writer` (by tag), `owed:<kind>` (newest partial row) or `local`; the prompt names them, and with no local box a continue that only orders batch work is read as stop (`wl_judge.settle_batch_no_local`).

Every case has its inverse, differing by one planted fact.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import types

import pytest

from rediacc_hooks.tests import wlfix

J = wlfix.import_wl("wl_judge")
R = wlfix.import_wl("wl_planrec")
M = wlfix.import_wl("worklist_messages")

REL = "agent/plans/PLAN-batch-fixture.md"
NOTE = "the parser half of this box is in the tree; the rest is a live step on the fleet"

# The 04:13:18 state, in miniature: every open box of the batch waits on something no local edit supplies. Tagged boxes are non-writer; the untagged ones (A1a, A4d, J6, ... carried no tag in PLAN-backup-program.md) carry a partial row with what they owe.
TAGGED = [
    "H3 [hostinger] restore drill on hostinger",
    "L2 [bench] bench round-trip",
    "LP-1 [live] live proof of the backup plane",
    "Q2 [operator] operator window for the key rotation",
    "K10 [post-merge] nightly after the merge",
]
OWED = {
    "A1a a PR preview of the docs page": "post-push",
    "A4d CI run ids recorded for the gate": "ci",
    "J6 suite runs in CI nightly": "ci",
    "J9 the second CI leg is green": "ci",
    "I3 elite live round-trip": "live",
    "P15 the receipts for the batch": "operator",
}


def plan_text(extra=()):
    lines = ["- [ ] %s" % b for b in (*TAGGED, *OWED, *extra)]
    return "# PLAN: batch fixture\nStatus: ready\nUpdated: 2026-11-10\n\n## Tasks\n\n%s\n" % (
        "\n".join(lines)
    )


def sig_of(text, prefix):
    return next(sig for _i, _raw, body, sig in R.open_boxes(text) if body.startswith(prefix))


def write_rows(root, rows):
    ledger = root.joinpath(*R.INVESTIGATION_REL)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


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


# ---- R20261110.2: the prompt and the settle, through a canned claude ----------------------------


@pytest.fixture
def judge(tmp_path, monkeypatch):
    """A canned `claude` that records its argv and answers `answer(...)`."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    seen = tmp_path / "argv.json"
    reply = tmp_path / "reply.json"
    script = bindir / "claude"
    script.write_text(
        "#!/usr/bin/env python3\nimport json, sys\n"
        "a = sys.argv[1:]; a.insert(a.index('-p') + 1, sys.stdin.read())  # the real CLI reads the prompt from stdin\n"
        "open(%r, 'w').write(json.dumps(a))\n"
        "print(open(%r).read())\n" % (str(seen), str(reply)),
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", "%s:%s:/usr/bin:/bin" % (bindir, os.path.dirname(sys.executable)))
    monkeypatch.setenv("TMPDIR", str(tmp_path))

    def answer(out):
        reply.write_text(json.dumps({"is_error": False, "structured_output": out}), "utf-8")

    def prompt():
        got = json.loads(seen.read_text(encoding="utf-8"))
        return got[got.index("-p") + 1]

    return types.SimpleNamespace(answer=answer, prompt=prompt)


# The order the judge gave at 04:17:30, 04:19:22 and 04:21:17.
BATCH_CONTINUE = {
    "verdict": "continue",
    "reason": "0/3 plans finished and the batch's open boxes are never checked.",
    "next_action": "Advance the batch's open boxes locally.",
}


def ask(local_batch, tracked=None):
    return J.run_judge(
        ["[ ] (deadbeef) an open item"],
        0,
        "The 22 open boxes wait on live steps.",
        0,
        "none declared",
        local_batch=local_batch,
        with_riders=False,
        facts={"tracked": tracked or [], "missing_ids": []} if tracked is not None else None,
    )


def test_control_without_box_rows_the_prompt_names_no_boxes_and_nothing_settles(judge):
    judge.answer(dict(BATCH_CONTINUE))
    verdict, err = ask({"finished": 0, "batch": 3})
    assert err is None, err
    prompt = judge.prompt()
    assert "TURBO LOCAL BATCH" in prompt
    assert "BATCH BOXES" not in prompt
    assert verdict["verdict"] == "continue", verdict


def test_settle_batch_no_local_alone():
    lb = {"rows": [("P.md", "H3", "12345678", "non-writer")], "local": 0, "open": 1}
    assert J.settle_batch_no_local(dict(BATCH_CONTINUE), lb)["verdict"] == "stop"
    assert J.settle_batch_no_local(dict(BATCH_CONTINUE), dict(lb, local=1))["verdict"] == (
        "continue"
    )
    assert J.settle_batch_no_local(dict(BATCH_CONTINUE), None)["verdict"] == "continue"
    stop = dict(BATCH_CONTINUE, verdict="stop")
    assert J.settle_batch_no_local(stop, lb) == stop


# ---- recount residue, lesson a6d0391f: a box box-audit reads live-owed is not local ------------
# PLAN-backup-program.md J9 ("Accept: CI run id.") had landed code and a newest `partial` row written before `--owed` existed. D1 classed it local, box-audit read it live-owed, and the judge ordered a writer for it.

LIVE_BODY = "J9 the second CI leg runs on every renet change. Accept: CI run id."
ABSENT_BODY = "Z9 a local thing with no row and nothing landed"
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


def live_owed_world(tmp_path, monkeypatch, landed=True):
    """A git repo on a live branch past `main`: J9 with (when `landed`) a commit whose Plan-Box trailer names it and an old partial row taken on that commit, and Z9 with nothing."""
    for key, value in GIT_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))
    monkeypatch.setenv("WORKLIST_REPORTS_DIR", str(tmp_path / "reports"))
    (tmp_path / "tmp").mkdir()
    root = (tmp_path / "proj").resolve()
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    _git(root, "add", "--", "base.txt")
    _git(root, "commit", "-q", "--no-gpg-sign", "-m", "base")
    _git(root, "switch", "-q", "-c", "0101-1")
    text = (
        "# PLAN: live-owed fixture\nStatus: ready\nUpdated: 2026-11-10\n\n## Tasks\n\n"
        "- [ ] %s\n- [ ] %s\n" % (LIVE_BODY, ABSENT_BODY)
    )
    (root / REL).parent.mkdir(parents=True, exist_ok=True)
    (root / REL).write_text(text, encoding="utf-8")
    sig = sig_of(text, "J9 ")
    if landed:
        (root / "j9.txt").write_text("j9\n", encoding="utf-8")
        _git(root, "add", "--", "j9.txt")
        _git(
            root,
            "commit",
            "-q",
            "--no-gpg-sign",
            "-m",
            "feat: j9 code half\n\nPlan-Box: PLAN-batch-fixture.md#%s clauses=all\n" % sig,
        )
        # D1: the newest row is partial with no `owed`, taken on the landed code.
        head = _git(root, "rev-parse", "HEAD")
        write_rows(root, [{"plan": REL, "sig": sig, "verdict": "partial", "head": head}])
    return root, types.SimpleNamespace(plans=(REL,))


def test_live_owed_boxes_is_empty_when_the_audit_fails(tmp_path, monkeypatch):
    """The audit itself raises on a real git fixture: head and stamp work before it, so the empty result is the audit's exception being caught."""
    root, _state = live_owed_world(tmp_path, monkeypatch)
    ba = wlfix.import_wl("wl_boxaudit")
    assert ba.head_of(root)
    assert ba.inputs_stamp(root) is not None
    calls = []

    def boom(*a, **_k):
        calls.append(a)
        raise OSError("unreadable")

    monkeypatch.setattr(ba, "audit", boom)
    assert J.live_owed_boxes(root) == {}
    assert len(calls) == 1, "the audit was never reached, so the empty result proves nothing"


def test_live_owed_boxes_control_the_same_world_reads_j9_live_owed(tmp_path, monkeypatch):
    """CONTROL: with the audit untouched the fixture is not empty, so the failure test's {} is the caught exception."""
    root, _state = live_owed_world(tmp_path, monkeypatch)
    got = J.live_owed_boxes(root)
    assert [p for p, _s in got] == ["PLAN-batch-fixture.md"], got
