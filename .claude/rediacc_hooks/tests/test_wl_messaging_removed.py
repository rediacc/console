"""Cross-session messaging is GONE, and nothing of it survives as a half-working path.

Operator ruling, 2026-09-24: "The stop hook system has a messaging system between claude sessions (not for sub-agents). Let's remove it completely since we drive the sessions usually with only one terminal now." The request log, the inbox poll and its silent fast path, the inbox waiter and every Stop check built on them were deleted as a clean break, with no shims and no dual paths.

What this file pins, each positive assertion beside a control that proves the instrument can see:
  * the seven verbs are unknown verbs now, refused with exit 2 and never run as a Stop event;
  * `--help` no longer advertises them;
  * old history (a `.requests` sidecar, request events in the store, a leftover poll marker) folds cleanly and buys nothing;
  * no hook still wires the waiter;
  * the canonical cron shape is ONE work cron.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest

from rediacc_hooks import lifecycle
from rediacc_hooks.tests import wlfix
from rediacc_hooks.tests.wlfix import wl  # noqa: F401

REMOVED_VERBS = ("--ask", "--answer", "--decline", "--ack", "--requests", "--poll", "--wait")

FOLD_PROBE = r"""
import json, pathlib, sys
sys.path.insert(0, sys.argv[1])
import wl_store as S
f = S.load(pathlib.Path(sys.argv[2]), sync=True)
print(json.dumps(sorted([r["text"], r["state"], r["owner"] or ""] for r in f.items)))
"""


def fold_of(fix) -> list:
    """The folded store as sorted (text, state, owner) rows. Text, not id: two setups of one world must compare equal."""
    proc = subprocess.run(
        [sys.executable, "-c", FOLD_PROBE, str(wlfix.STOP_DIR), str(fix.wl)],
        capture_output=True,
        text=True,
        env=dict(fix.env),
        check=False,
    )
    assert proc.returncode == 0, "fold probe failed: %s" % proc.stderr[-400:]
    return json.loads(proc.stdout)


def stamp(minutes_ago: float = 0.0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - minutes_ago * 60))


def world(fix) -> None:
    """One ordinary world: a brief, a fresh STATE.md, one deferred item with a DEFAULT, and a message that reports it."""
    fix.brief_now()
    fix.hand_now()
    fix.brief_other("cafe1234")
    fix.add_item("- [?] (deadbeef) keep the flag? DEFAULT: keep it")
    fix.say("answer\n\n## Remaining\n- the flag decision, deferred with a default")


def plant_old_history(fix) -> bytes:
    """Everything the removed layers ever left on disk. Returns the `.requests` bytes, so a caller can prove nothing appended to it."""
    at = stamp(300)
    requests = [
        {
            "ev": "ask",
            "id": "aaaa1111",
            "from": "cafe1234",
            "to": "deadbeef",
            "at": at,
            "body": "an old ask to me",
        },
        {
            "ev": "ask",
            "id": "bbbb2222",
            "from": "deadbeef",
            "to": "cafe1234",
            "at": at,
            "body": "an old ask from me",
        },
        {"ev": "answer", "id": "bbbb2222", "by": "cafe1234", "at": at, "body": "an old answer"},
        {"ev": "escalate", "id": "aaaa1111", "at": at},
        {"ev": "reassign", "id": "aaaa1111", "at": at, "by": "deadbeef", "to": "deadbeef"},
    ]
    path = fix.stem(".requests")
    path.write_text("".join(json.dumps(r) + "\n" for r in requests), encoding="utf-8")
    # (b) request-shaped events inside the store's own logs, both halves: the legacy log and the tracked writer file.
    foreign = [
        {
            "ev": "ask",
            "id": "cccc3333",
            "from": "cafe1234",
            "to": "deadbeef",
            "at": at,
            "body": "x",
        },
        {"ev": "answer", "id": "cccc3333", "by": "deadbeef", "at": at, "body": "y"},
        {"ev": "ack", "id": "cccc3333", "by": "cafe1234", "at": at},
    ]
    lines = "".join(json.dumps(e) + "\n" for e in foreign)
    with fix.events.open("a", encoding="utf-8") as handle:
        handle.write(lines)
    fix.store_dir.mkdir(parents=True, exist_ok=True)
    with (fix.store_dir / "deadbeef.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(lines)
    return path.read_bytes()


def plant_poll_marker(fix) -> None:
    """(c) a fresh `.pollmark-` and a `.pollbase-` banked against this very world: under the removed fast path this pair bought a SILENT stop that skipped the battery and never wrote `.lastevent-`."""
    probe = (
        "import pathlib, sys\n"
        "sys.path.insert(0, %r)\n"
        "import wl_core as C, wl_store as S\n"
        "wl = pathlib.Path(%r)\n"
        "print(S.world_sig(C.project_root(%r), wl, %r, transcript_path=%r))\n"
    ) % (str(wlfix.STOP_DIR), str(fix.wl), str(fix.proj), fix.sid, str(fix.transcript))
    sig = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        env=dict(fix.env),
        check=False,
    ).stdout.strip()
    fix.stem(".pollmark-deadbeef").write_text(stamp(), encoding="utf-8")
    fix.stem(".pollbase-deadbeef").write_text(
        json.dumps({"sig": sig, "at": stamp(), "clsig": "da39a3ee5e6b4b0d", "cl_live": 0}),
        encoding="utf-8",
    )


def test_removed_verbs_are_unknown(wl):  # noqa: F811
    """Each removed verb falls into the unknown-verb refusal: exit 2, named, and no verdict. Before the removal `--poll` exited 0 on an empty inbox, so rc 2 here is the removal, not a verb that was always broken."""
    for verb in REMOVED_VERBS:
        got = wl.cli(verb, wlfix.ME, "x")
        both = got.out + got.err
        assert got.rc == 2, "%s: rc=%d %r" % (verb, got.rc, both[:200])
        assert "unknown verb '%s'" % verb in got.err, "%s: %r" % (verb, got.err[:200])
        assert '"decision"' not in both, "%s emitted a Stop verdict: %r" % (verb, both[:200])

    # It must not hang either, with stdin a pipe that STAYS OPEN (the 163x shape): a verb that fell through to the Stop path would block in json.load forever.
    read_fd, write_fd = os.pipe()
    env = dict(wl.env)
    env["CLAUDE_PROJECT_DIR"] = str(wl.proj)
    proc = subprocess.Popen(
        [sys.executable, str(wl.hook), "--poll", wlfix.ME],
        stdin=read_fd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    os.close(read_fd)
    hung = False
    try:
        rc = proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        hung = True
        proc.kill()
        proc.wait()
        rc = None
    finally:
        os.close(write_fd)
    assert not hung, "--poll hangs reading stdin"
    assert rc == 2, "--poll with an open stdin: rc=%r" % rc

    # CONTROL: the harness can succeed, so the rc 2 above is not vacuous.
    assert wl.cli("--list").rc == 0, "CONTROL: --list failed"
    got = wl.cli_as("cafe1234", "--brief", "cafe1234", "t")
    assert "brief recorded" in got.out, (
        "CONTROL: --brief as a peer failed: %r" % (got.out + got.err)[:200]
    )


def test_help_no_longer_advertises_messaging(wl):  # noqa: F811
    got = wl.cli("--help")
    text = got.out + got.err
    for needle in (*REMOVED_VERBS, "Cross-session messaging", "wl_wait"):
        assert needle not in text, "--help still advertises %r" % needle
    # CONTROL: the help is really printed and still lists the surviving verbs.
    assert "--add" in text, text[:300]
    assert "--reassign" in text, text[:300]


def test_old_request_history_folds_cleanly(wl):  # noqa: F811
    """Old history is ignored, not scrubbed: the fold skips an unknown `ev` and nothing opens `.requests` any more. The CONTROL is the same world with no history planted."""
    world(wl)
    control = wl.run()
    control_fold = fold_of(wl)
    assert control_fold, "CONTROL: the world folded to nothing, so an equal fold proves nothing"

    wl.setup()
    world(wl)
    before = plant_old_history(wl)
    got = wl.run()
    assert fold_of(wl) == control_fold, "old request history changed the fold"
    assert got.decision == control.decision, (
        "old request history changed the decision: %r vs %r"
        % (
            got.decision,
            control.decision,
        )
    )
    for needle in ("REQUEST", "INBOX", "ANSWERED"):
        assert needle not in got.out, "old history still surfaces %r: %s" % (needle, got.out[:300])
    assert wl.stem(".requests").read_bytes() == before, (
        "the stop read-modified the .requests sidecar"
    )


def test_a_leftover_poll_marker_buys_no_silent_stop(wl):  # noqa: F811
    """A clean world plus a fresh poll marker and a baseline banked against that very world. Under the removed fast path this stop exited with zero bytes and skipped the battery, so `.lastevent-` was never written. Now the battery runs: `.lastevent-` is written, which is the proof."""
    wl.brief_now()
    wl.hand_now()
    wl.say("all done")
    lastevent = wl.stem(".lastevent-deadbeef.json")
    # CONTROL: the ordinary stop writes the file this test reads.
    wl.run()
    assert lastevent.is_file(), (
        "CONTROL: an ordinary stop wrote no .lastevent-, so its absence below would prove nothing"
    )
    lastevent.unlink()

    plant_poll_marker(wl)
    wl.newturn()
    wl.say("all done")
    got = wl.run()
    assert got.rc == 0, got.err[:200]
    assert lastevent.is_file(), (
        "a leftover poll marker still bought a silent stop that skipped the battery"
    )


def test_no_hook_still_wires_the_waiter():
    commands = [m["command"] for m in lifecycle.flat_commands("post-tool")]
    assert not [c for c in commands if "wl_wait" in c], commands
    # 15 (band-notice) + 60 (onboard), the members that remain.
    assert lifecycle.entry_timeout("post-tool") == 75, lifecycle.entry_timeout("post-tool")
    # CONTROL: the reader sees the chain at all.
    assert any("band-notice.py" in c for c in commands), commands
    assert any("onboard.py" in c for c in commands), commands


def test_one_work_cron_is_the_shape_and_a_second_one_fires(wl):  # noqa: F811
    """The deleted `no-poll`/`many-poll-crons`/`many-waiters` coverage becomes a shape assertion. DEFAULT_CRONS holds one work cron, and a clean stop allows; a `*/5` second cron is now a second WORK cron and `many-work-crons` fires."""
    assert len(wlfix.DEFAULT_CRONS) == 1, wlfix.DEFAULT_CRONS
    wl.brief_now()
    wl.hand_now()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.task(7, "pending", "thing")
    wl.check("allow", "", "one work cron is the canonical shape")

    wl.crons = json.dumps([*wlfix.DEFAULT_CRONS, {"id": "p", "schedule": "*/5 * * * *"}])
    wl.newturn()
    wl.say("answer\n\n## Remaining\n- #7 thing (pending)")
    wl.check("block", "2 work crons are live", "a second cron is a second work cron now")


def test_check_quiet_accepts_a_proven_silent_stop_and_still_refuses_a_dead_hook(wl):  # noqa: F811
    """With the poll-backoff advisory gone, a clean stop is a zero-byte allow, so `wlfix.check_quiet` accepts silence when the battery provably ran (exit 0 and a rewritten `.lastevent-`). The FIRE leg keeps the anti-vacuity guard honest: a hook that no-ops before the battery (GITHUB_ACTIONS=true) is also silent, and must still be refused."""
    wl.brief_now()
    wl.hand_now()
    wl.say("all done")
    clean = wl.run()
    assert not clean.out.strip(), "premise: the clean stop was not silent: %r" % clean.out[:200]
    assert clean.battery_ran, "premise: the clean stop left no proof the battery ran"
    wl.check_quiet("NEEDLE-THAT-IS-NOT-THERE", "a proven silent stop", result=clean)

    wl.gha = "true"
    wl.newturn()
    dead = wl.run()
    assert not dead.out.strip(), "premise: the no-op stop printed something: %r" % dead.out[:200]
    assert not dead.battery_ran, "a no-op stop was credited with running the battery"
    with pytest.raises(AssertionError, match="no proof the battery ran"):
        wl.check_quiet("NEEDLE-THAT-IS-NOT-THERE", "a dead hook", result=dead)
