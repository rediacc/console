"""A durable operator ruling silences one subject of one Stop check, in every session, until it is revoked (agent/plans/PLAN-stop-hook-rulings-campaign.md section 2).

The fixture is a REAL superproject with a REAL submodule whose worktree commit differs from the recorded gitlink, because `wl_ci.submodule_pointer_moves` reads `git submodule status --cached` and nothing short of a real gitlink produces its leading `+`. `WORKLIST_SUBMODULE_LATCH_MIN=0` switches the unchanged-subject window off, so every silence below is the RULING's and never the latch's; the
first case proves the window really is off by firing twice in a row.

Every silence has a paired firing: a different sha, a revocation, a rulings path that cannot be read.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys

import pytest

from rediacc_hooks.tests import wlfix

NEEDLE = "SUBMODULE POINTER MOVED"
NO_LATCH = {"WORKLIST_SUBMODULE_LATCH_MIN": "0"}
GATE = pathlib.Path(__file__).resolve().parents[3] / ".ci/scripts/quality/check_operator_rulings.py"


def _sh(*args: str, cwd: pathlib.Path | None = None) -> str:
    proc = subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, "git %s: %s" % (" ".join(args), proc.stderr[-400:])
    return proc.stdout.strip()


def moved_pointer(fix) -> str:
    """Turn the fixture project into a superproject whose `sub` gitlink has moved; returns the worktree sha's 9-character prefix, which is what the check names."""
    work = fix.base / "subrepo"
    _sh("init", "-q", "--bare", "-b", "main", str(work / "remote.git"))
    _sh("init", "-q", "-b", "main", str(work / "sub"))
    (work / "sub" / "f").write_text("one\n", encoding="utf-8")
    _sh("add", "f", cwd=work / "sub")
    _sh("commit", "-qm", "one", cwd=work / "sub")
    _sh("remote", "add", "origin", str(work / "remote.git"), cwd=work / "sub")
    _sh("push", "-q", "origin", "main", cwd=work / "sub")
    shutil.rmtree(fix.proj / ".git")
    _sh("init", "-q", "-b", "main", str(fix.proj))
    _sh(
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(work / "remote.git"),
        "sub",
        cwd=fix.proj,
    )
    _sh("add", ".gitmodules", "sub", cwd=fix.proj)
    _sh("commit", "-qm", "super", cwd=fix.proj)
    return advance(fix)


def advance(fix) -> str:
    """One more commit inside the submodule worktree: a NEW subject for the check."""
    sub = fix.proj / "sub"
    n = len(list(sub.glob("g*")))
    (sub / ("g%d" % n)).write_text("%d\n" % n, encoding="utf-8")
    _sh("add", "-A", cwd=sub)
    _sh("commit", "-qm", "g%d" % n, cwd=sub)
    return _sh("rev-parse", "HEAD", cwd=sub)[:9]


def world(fix) -> str:
    fix.brief_now()
    fix.hand_now()
    fix.say("answer\n\n## Remaining\n- #7 thing (pending)")
    fix.task(7, "pending", "thing")
    return moved_pointer(fix)


def quiet(fix, got: wlfix.Result, label: str) -> None:
    """The needle is absent AND the battery ran, so the silence is the check's verdict and never a hook that died first."""
    proof = "%s: no proof the battery ran: %s" % (label, got.err[-300:])
    assert got.battery_ran, proof
    assert got.rc == 0, proof
    assert NEEDLE not in got.out, fix.why(label, got.decision, got, NEEDLE)


def rule(fix, *args: str, prefix: str = wlfix.ME) -> wlfix.Result:
    return fix.cli("--rule", prefix, *args)


def test_a_moved_pointer_fires_on_every_stop_with_the_window_off(wl):
    """CONTROL for every silence below: with the latch at 0 nothing but a ruling can suppress."""
    sha = world(wl)
    first = wl.run(NO_LATCH)
    assert NEEDLE in first.out, wl.why("first stop", "block", first, NEEDLE)
    assert "sub@%s" % sha in first.out, "the fire names the exact --rule subject"
    again = wl.run(NO_LATCH)
    assert NEEDLE in again.out, wl.why("second stop, window off", "block", again, NEEDLE)


def test_a_ruling_silences_the_next_stop_and_renders_into_rules_md(wl):
    sha = world(wl)
    assert NEEDLE in wl.run(NO_LATCH).out
    got = rule(wl, "submodule", "sub@%s" % sha, "KEEP, a peer's checkout; never stage it")
    assert got.rc == 0, got.err
    assert "recorded" in got.out
    quiet(wl, wl.run(NO_LATCH), "ruled")
    rules_md = (wl.store_dir.parent / "RULES.md").read_text(encoding="utf-8")
    assert "sub@%s" % sha in rules_md
    assert "KEEP, a peer's checkout" in rules_md
    listing = rule(wl)
    assert listing.rc == 0
    assert "1 live" in listing.out
    assert sha in listing.out


def test_a_different_sha_fires_again(wl):
    """Keyed on the SUBJECT, not a global mute of the check."""
    sha = world(wl)
    assert rule(wl, "submodule", "sub@%s" % sha, "KEEP").rc == 0
    quiet(wl, wl.run(NO_LATCH), "ruled")
    newer = advance(wl)
    fired = wl.run(NO_LATCH)
    assert NEEDLE in fired.out, wl.why("new sha", "block", fired, NEEDLE)
    assert newer in fired.out, wl.why("new sha", "block", fired, NEEDLE)


def test_a_wholesale_state_rewrite_leaves_the_ruling_in_force(wl):
    sha = world(wl)
    assert rule(wl, "submodule", "sub@%s" % sha, "KEEP").rc == 0
    body = wlfix.STATE_BODY.replace("Round 23", "Round 24, rewritten from scratch")
    assert wl.cli("--state", wlfix.ME, stdin=body).rc == 0
    quiet(wl, wl.run(NO_LATCH), "after --state")


def test_a_fresh_session_inherits_the_ruling(wl):
    """The cross-session property the session-local latch lacked: a peer's first stop is silent."""
    sha = world(wl)
    peer = "cafef00d"
    fired = wl.run_as(peer, NO_LATCH)
    assert NEEDLE in fired.out, wl.why("peer, unruled", "block", fired, NEEDLE)
    assert rule(wl, "submodule", "sub@%s" % sha, "KEEP").rc == 0
    quiet(wl, wl.run_as("feedf00d", NO_LATCH), "fresh peer, ruled")


def test_a_revocation_fires_again_and_keeps_the_row(wl):
    sha = world(wl)
    assert rule(wl, "submodule", "sub@%s" % sha, "KEEP").rc == 0
    rid = json.loads(
        next((wl.store_dir.parent / "rulings").glob("*.jsonl")).read_text().splitlines()[0]
    )["id"]
    quiet(wl, wl.run(NO_LATCH), "ruled")
    got = rule(wl, "--revoke", rid, "the pointer belongs to this PR after all")
    assert got.rc == 0, got.err
    fired = wl.run(NO_LATCH)
    assert NEEDLE in fired.out, wl.why("revoked", "block", fired, NEEDLE)
    rows = [
        json.loads(line)
        for path in (wl.store_dir.parent / "rulings").glob("*.jsonl")
        for line in path.read_text().splitlines()
    ]
    assert [r["ev"] for r in rows] == ["rule", "revoke"], "nothing is ever deleted"
    assert "REVOKED" in (wl.store_dir.parent / "RULES.md").read_text(encoding="utf-8")
    again = rule(wl, "--revoke", rid, "twice")
    assert again.rc == 2
    assert "already revoked" in again.err


def test_an_unreadable_ruling_path_restores_the_firing(wl):
    """Any error in the lookup is None, which is today's behaviour: the check fires."""
    sha = world(wl)
    assert rule(wl, "submodule", "sub@%s" % sha, "KEEP").rc == 0
    rulings = wl.store_dir.parent / "rulings"
    shutil.rmtree(rulings)
    rulings.write_text("not a directory\n", encoding="utf-8")
    fired = wl.run(NO_LATCH)
    assert NEEDLE in fired.out, wl.why("unreadable rulings", "block", fired, NEEDLE)


def test_the_verb_refuses_what_would_bind_nothing(wl):
    wl.setup()
    unknown = rule(wl, "stale-local", "anything", "text")
    assert unknown.rc == 2
    assert "not a check that consults rulings" in unknown.err
    past = rule(wl, "submodule", "sub@abc", "text", "--until", "2001-01-01T00:00:00Z")
    assert past.rc == 2
    assert "--until" in past.err
    short = rule(wl, "submodule", "sub@abc")
    assert short.rc == 2
    assert not (wl.store_dir.parent / "rulings").exists(), "a refused call writes nothing"
    future = rule(wl, "submodule", "sub@abc", "text", "--until", "2999-01-01T00:00:00Z")
    assert future.rc == 0
    assert "until 2999-01-01T00:00:00Z" in (wl.store_dir.parent / "RULES.md").read_text(
        encoding="utf-8"
    )


def _gate(root: pathlib.Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_gate_agrees_with_the_verb_and_fails_on_a_planted_drift(wl, tmp_path):
    """check:ci-operator-rulings over what `--rule` wrote: green as written, red after one hand-appended row and after a hand edit of the block."""
    wl.setup()
    assert rule(wl, "submodule", "sub@abc123456", "KEEP, rides this PR").rc == 0
    tree = tmp_path / "tree"
    (tree / "agent").mkdir(parents=True)
    shutil.copytree(wl.store_dir.parent / "rulings", tree / "agent" / "rulings")
    shutil.copy(wl.store_dir.parent / "RULES.md", tree / "agent" / "RULES.md")
    green = _gate(tree)
    assert green.returncode == 0, green.stdout + green.stderr
    ledger = next((tree / "agent" / "rulings").glob("*.jsonl"))
    row = json.loads(ledger.read_text().splitlines()[0])
    row.update(id="0badc0de", subject="sub@fff000111")
    row["sig"] = wlfix.import_wl("wl_ruling").subject_sig(row["subject"])
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    drift = _gate(tree)
    assert drift.returncode == 1, drift.stdout + drift.stderr
    assert "O3" in drift.stderr, drift.stdout + drift.stderr
    shutil.copy(wl.store_dir.parent / "RULES.md", tree / "agent" / "RULES.md")
    ledger.write_text(ledger.read_text().splitlines()[0] + "\n", encoding="utf-8")
    md = tree / "agent" / "RULES.md"
    md.write_text(md.read_text().replace("KEEP, rides", "DROP, rides"), encoding="utf-8")
    edited = _gate(tree)
    assert edited.returncode == 1
    assert "O3" in edited.stderr


def test_record_refuses_a_malformed_row_before_writing_anything(tmp_path):
    """f8840f98.1: `rule_row` returns whatever it is given; `record`, the only door to the ledger, runs `row_problem` first. An empty text or an unlisted check writes no ledger file."""
    ru = wlfix.import_wl("wl_ruling")
    check = min(ru.RULABLE_CHECKS)
    for bad in (
        ru.rule_row("d778be9d", check, "subject", "   "),
        ru.rule_row("d778be9d", "no-such-check", "subject", "text"),
    ):
        with pytest.raises(ValueError, match="malformed"):
            ru.record(tmp_path, "d778be9d", bad)
    assert not list(ru.rulings_dir(tmp_path).glob("*.jsonl"))
    ru.record(tmp_path, "d778be9d", ru.rule_row("d778be9d", check, "subject", "text"))
    assert len(list(ru.rulings_dir(tmp_path).glob("*.jsonl"))) == 1
