"""Ported from `.claude/hooks/stop/worklist-cases/26-migrate.sh`.

The tracked store and `--migrate`. Every case here names the defect it would catch, because the expensive direction of this feature is silent: a store that reads one file and misses the rest, or a migration that moves work out from under a session that is still doing it, both look like success.

EVERY CLI CALL GOES THROUGH THE FIXTURE ENVIRONMENT. The store has two halves, the tracked writer files under WORKLIST_STORE_DIR and everything resolved from the worklist path under TMPDIR, and a call that carries only the first reads its items from the fixture store while looking for `.lastevent-*` beside the operator's real one: it finds none, calls a live session idle, and
migrates it. Every case below depends on both halves travelling together, and case 203 is the control that proves they do.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
import time
from typing import TYPE_CHECKING

from rediacc_hooks.tests.wlfix import wl  # noqa: F401

if TYPE_CHECKING:
    import pathlib


def as_session(fix, prefix: str) -> dict:
    """The fixture environment with the bare prefix as the acting session id."""
    env = dict(fix.env)
    env["WORKLIST_SESSION_ID"] = prefix
    return env


def combined(result) -> str:
    return result.out + result.err


def age_store(fix, prefix: str, minutes: int = 180) -> None:
    """Age EVERY event in the store, and the peer's `.lastevent` with it.

    A case that leases or defers as the peer writes a FRESH event, which makes liveness say the session wrote to the store moments ago (correctly: that is a session still acting) and the migration is then refused. Re-aging after such a write models a peer that has since stopped.
    """
    stamp = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=minutes)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    for path in fix.store_dir.glob("*.jsonl"):
        lines = [
            json.dumps({**json.loads(line), "at": stamp}, separators=(",", ":"))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    marker = fix.stem(".lastevent-%s.json" % prefix[:8])
    marker.write_text("", encoding="utf-8")
    backdate(marker, minutes * 60)


def backdate(path: pathlib.Path, seconds: float) -> None:
    old = time.time() - seconds
    os.utime(path, (old, old))


def mig_peer(fix, prefix: str, text: str, minutes: int = 180) -> None:
    """A peer with remaining work, aged so no artifact says it is live.

    WHY AGED and not merely free of artifacts: the phantom check owns the never-stopped case and answers it with `--reassign`. `--migrate` is for a session that DID stop. Writing a `.lastevent` and backdating it is what tells the two apart, and getting this wrong makes every case below test the wrong feature.
    """
    fix.cli("--add", prefix, text, env=as_session(fix, prefix))
    age_store(fix, prefix, minutes)


def mig(fix, *argv: str) -> str:
    return combined(fix.cli("--migrate", "deadbeef", *argv, env=as_session(fix, "deadbeef")))


def item_id(fix, needle: str) -> str:
    """The id of the item whose text carries `needle`.

    BY THE ITEM'S OWN TEXT, not the first id in the listing: taking the first took whichever id happened to sort first, which is another session's item as often as the peer's, so the lease landed on the wrong thing and the migration then had nothing leased to carry.
    """
    for line in fix.cli("--list").out.splitlines():
        if needle in line:
            found = re.search(r"#([0-9a-f]{8,})", line)
            if found:
                return found.group(1)
    raise AssertionError("could not find the peer's item matching %r" % needle)


def test_190_the_store_is_a_directory_of_per_writer_files(wl):  # noqa: F811
    wl.say("done for now")
    wl.brief_now()
    wl.cli("--add", "deadbeef", "an item of my own")
    mine = wl.store_dir / "deadbeef.jsonl"
    assert mine.is_file(), "the add did not land in the tracked per-writer file: %s" % list(
        wl.store_dir.iterdir()
    )
    assert mine.stat().st_size > 0, (
        "the add did not land in the tracked per-writer file: %s" % list(wl.store_dir.iterdir())
    )
    assert not wl.events.is_file() or wl.events.stat().st_size == 0, (
        "the add landed in the legacy log instead of the tracked store"
    )
    # PLANT: a second writer must not touch the first's file. Two appenders on one path is exactly the merge conflict the layout exists to avoid.
    before = mine.read_text(encoding="utf-8")
    wl.cli("--add", "cafe1234", "a peer item", env=as_session(wl, "cafe1234"))
    peer = wl.store_dir / "cafe1234.jsonl"
    assert peer.is_file(), "the second writer got no file of its own"
    assert peer.stat().st_size > 0, "the second writer got no file of its own"
    assert mine.read_text(encoding="utf-8") == before, "writers are sharing a file"


def test_191_the_reader_unions_every_file_and_sorts_by_time(wl):  # noqa: F811
    """Name order is not time order.

    `zz` holds the older add and `aa` the newer tick. Concatenating in name order would fold the tick before the item exists and report the item as still open.
    """
    wl.say("done for now")
    wl.brief_now()
    now = datetime.datetime.now(datetime.UTC)
    older = (now - datetime.timedelta(minutes=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    newer = (now - datetime.timedelta(minutes=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    (wl.store_dir / "zz.jsonl").write_text(
        json.dumps(
            {
                "ev": "add",
                "id": "sortcase01",
                "at": older,
                "by": "deadbeef",
                "s": " ",
                "o": "deadbeef",
                "t": "(deadbeef) ordered by time, not by filename",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (wl.store_dir / "aa.jsonl").write_text(
        json.dumps(
            {
                "ev": "state",
                "id": "sortcase01",
                "at": newer,
                "by": "deadbeef",
                "s": "x",
                "note": "done, proven by run 123",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    listing = wl.cli("--list").out
    assert re.search(r"\[x\].*ordered by time", listing), (
        "the tick in the name-later file was folded before its add: %s" % listing[:300]
    )


def test_192_the_legacy_tmpdir_log_is_still_read(wl):  # noqa: F811
    """So nothing stopped blocking.

    PLANT: an open item that exists ONLY in the pre-move location. A reader that looked at the tracked store alone would let this session stop.
    """
    wl.say("done for now")
    wl.brief_now()
    stamp = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=5)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    with wl.events.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "ev": "add",
                    "id": "legacyopen1",
                    "at": stamp,
                    "by": "deadbeef",
                    "s": " ",
                    "o": "deadbeef",
                    "t": "(deadbeef) only in the legacy log",
                }
            )
            + "\n"
        )
    wl.check("block", "only in the legacy log", "an item only in the legacy log still blocks")


def test_193_migrate_refuses_a_session_that_is_live_here(wl):  # noqa: F811
    wl.say("done for now")
    wl.brief_now()
    mig_peer(wl, "livepeer1", "(livepeer1) work of a running session", 180)
    marker = wl.stem(".lastevent-livepeer.json")
    marker.write_text("", encoding="utf-8")  # fresh: written this second
    out = mig(wl, "livepeer1")
    assert "REFUSED" in out, "migrated a LIVE session: %s" % out[:300]
    assert "lastevent" in out, "the refusal does not name the artifact: %s" % out[:300]
    # CONTROL ON THE CONTROL: the same peer, artifact backdated, must migrate. Without it the assertion above would also pass if the verb refused everything.
    backdate(marker, 7200)
    out = mig(wl, "livepeer1")
    assert "migrated 1 item" in out, (
        "CONTROL: the refusal is unconditional, so the case above proves nothing: %s" % out[:300]
    )


def test_194_a_migrated_item_is_mine_and_the_original_is_closed(wl):  # noqa: F811
    """Case 195 rides here: the bash ran it with no `setup` of its own, so idempotence is asserted against the very store 194 just moved."""
    wl.say("done for now")
    wl.brief_now()
    mig_peer(wl, "oldsess1", "(oldsess1) the stranded work")
    mig(wl, "oldsess1")
    assert "the stranded work" in wl.cli("--list", "--open", "deadbeef").out, (
        "the migrated item is not owned by me, so the Stop hook would not block on it"
    )
    assert "migrated to #" in wl.cli("--list").out, (
        "the original was not closed, so the work is now double-counted"
    )
    # 195. Idempotent: a second run moves nothing.
    out = mig(wl, "oldsess1")
    assert "nothing left to migrate" in out, "re-migrating duplicated the work: %s" % out[:300]


def test_196_an_in_flight_item_arrives_open_with_its_dead_lease_reset(wl):  # noqa: F811
    wl.say("done for now")
    wl.brief_now()
    mig_peer(wl, "leasesess", "(leasesess) leased to a worker that died with its session")
    ident = item_id(wl, "leased to a worker")
    wl.cli(
        "--lease",
        "leasesess",
        ident,
        "+60",
        "worker:ghost1",
        "held",
        env=as_session(wl, "leasesess"),
    )
    # The lease above was a FRESH write; the peer must read as stopped.
    age_store(wl, "leasesess")
    mig(wl, "leasesess")
    listing = wl.cli("--list", "--open", "deadbeef").out
    assert re.search(r"\[ \].*leased to a worker", listing), (
        "the item arrived still leased to a worker on the other machine: %s" % listing[:300]
    )


def test_197_a_deferral_keeps_its_default_window(wl):  # noqa: F811
    """Rather than restarting it.

    The window is measured from `upd`. Carried, the item is already about 180 minutes old (the peer fixture aged it) and its default is due; restarted, it would read as fresh.
    """
    wl.say("done for now")
    wl.brief_now()
    mig_peer(wl, "defersess", "(defersess) a question for the operator")
    ident = item_id(wl, "a question for the operator")
    wl.cli(
        "--defer",
        "defersess",
        ident,
        "which branch? DEFAULT: use main WHY: it is the base HOW: rerun the gate",
        env=as_session(wl, "defersess"),
    )
    age_store(wl, "defersess")
    mig(wl, "defersess")
    assert "[?]" in wl.cli("--list", "--open", "deadbeef").out, "the [?] state was lost in the move"


def test_198_migrate_refuses_me_and_a_prefix_with_no_events(wl):  # noqa: F811
    wl.say("done for now")
    wl.brief_now()
    out = mig(wl, "deadbeef")
    assert "already yours" in out, "self-migration was allowed: %s" % out[:300]
    out = mig(wl, "nosuchse")
    assert "REFUSED" in out, "migrated from a session that never existed: %s" % out[:300]


def test_199_a_stopped_peers_work_is_reported_never_blocked_on(wl):  # noqa: F811
    wl.say("done for now")
    wl.brief_now()
    mig_peer(wl, "handoff1", "(handoff1) work its session left behind")
    wl.check(
        "allow",
        "HANDOFF CANDIDATES",
        "a stopped peer's work is reported",
        result=wl.run({"WORKLIST_REPORT_PER_STOP": "6"}),
    )


def test_199_control_a_live_peer_is_never_offered_for_handoff(wl):  # noqa: F811
    """CONTROL: a LIVE peer is not a handoff candidate, because its work is not this session's."""
    wl.say("done for now")
    wl.brief_now()
    mig_peer(wl, "handoff2", "(handoff2) work of a running session")
    wl.stem(".lastevent-handoff2.json").write_text("", encoding="utf-8")
    got = wl.run({"WORKLIST_REPORT_PER_STOP": "6"})
    assert got.out.strip(), "the hook produced no output, so the absence below means nothing"
    assert "HANDOFF CANDIDATES" not in got.out, "offered a live session's work for adoption"


def test_200_doctor_catches_what_a_tracked_file_makes_possible(wl):  # noqa: F811
    """Every plant is a shape that is SILENT by default: the reader skips unparseable lines by contract, so a conflict marker costs events and says nothing, and a secret in TMPDIR was private while a secret in a tracked file is pushed."""
    wl.say("done for now")
    wl.brief_now()
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    ghp_shaped = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"
    (wl.store_dir / "planted.jsonl").write_text(
        "<<<<<<< HEAD\n"
        + json.dumps(
            {
                "ev": "add",
                "id": "docok1",
                "at": stamp,
                "by": "deadbeef",
                "s": " ",
                "o": "deadbeef",
                "t": "fine",
            }
        )
        + "\nnot json at all\n"
        + json.dumps(
            {
                "ev": "add",
                "id": "docok2",
                "at": stamp,
                "by": "deadbeef",
                "s": " ",
                "o": "deadbeef",
                "t": "tok %s" % ghp_shaped,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    got = wl.cli("--doctor")
    out = combined(got)
    assert got.rc != 0, "--doctor passed a store with three planted defects"
    for needle in ("merge conflict marker", "unparseable", "secret-shaped"):
        assert needle in out, "--doctor missed %r (rc=%d): %s" % (needle, got.rc, out[:300])
    # The secret SHAPE is named and the value is not echoed back: printing it would be the leak this check exists to prevent.
    assert ghp_shaped not in out, "--doctor echoed the secret it was reporting"
    # CONTROL: without the PLANTS it must pass, or the case proves only that --doctor always fails. The store must still hold a VALID file: --doctor refuses an empty store outright (a check that scanned nothing is not a pass), so deleting the plant and leaving the directory bare would test that refusal instead of the clean-store path.
    (wl.store_dir / "planted.jsonl").unlink()
    (wl.store_dir / "clean.jsonl").write_text(
        json.dumps(
            {
                "ev": "add",
                "id": "docclean1",
                "at": stamp,
                "by": "deadbeef",
                "s": " ",
                "o": "deadbeef",
                "t": "a clean event",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    got = wl.cli("--doctor")
    assert got.rc == 0, "CONTROL: --doctor fails even on a clean store: %s" % combined(got)[:300]
    assert "store OK" in combined(got), (
        "CONTROL: --doctor fails even on a clean store: %s" % combined(got)[:300]
    )


def test_201_compaction_never_rewrites_a_file_a_live_peer_is_appending_to(wl):  # noqa: F811
    wl.say("done for now")
    wl.brief_now()
    wl.cli("--add", "deadbeef", "my own item")
    wl.cli("--add", "deadpeer", "a dead peer item", env=as_session(wl, "deadpeer"))
    wl.cli("--add", "livepeer", "a LIVE peer item", env=as_session(wl, "livepeer"))
    # deadpeer's events aged past WORKLIST_DEAD_HOURS; livepeer left fresh.
    dead = wl.store_dir / "deadpeer.jsonl"
    old = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=48)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    dead.write_text(
        "\n".join(
            json.dumps({**json.loads(line), "at": old}, separators=(",", ":"))
            for line in dead.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        + "\n",
        encoding="utf-8",
    )
    wl.stem(".lastevent-livepeer.json").write_text("", encoding="utf-8")
    out = combined(wl.cli("--compact"))
    assert (wl.store_dir / "livepeer.jsonl").is_file(), (
        "compaction rewrote a file a live session is still appending to"
    )
    assert "kept livepeer.jsonl" in out, "the reason was not printed: %s" % out[:300]
    assert not dead.is_file(), "nothing was compacted, so this case proves nothing"
    # THE PROPERTY THAT MATTERS: no item may be lost, whichever files moved.
    listing = wl.cli("--list").out
    found = sum(
        1
        for line in listing.splitlines()
        if "own item" in line or "dead peer item" in line or "LIVE peer item" in line
    )
    assert found == 3, "compaction lost items (found %d of 3)" % found


def test_202_the_tied_case_same_second_and_file_order_contradicts_write_order(wl):  # noqa: F811
    """`at` has SECOND resolution, so a judge reopen and a session tick inside one second TIE. Sorting on `at` alone left the tie to file-glob order, and a ticked item came back OPEN (case 150 caught it live). The nanosecond sequence is what restores real write order, and the file names below deliberately contradict it, so a sort that ignored `ns` would get this backwards."""
    wl.say("done for now")
    wl.brief_now()
    # ONE second for both events, on purpose, but DERIVED rather than a literal. What the case needs is that the two stamps are EQUAL, not that they name a fixed day, and a literal would age exactly as two other fixtures in this suite did (a retention window, then a fold order).
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    later = time.time_ns()
    (wl.store_dir / "zzz.jsonl").write_text(
        json.dumps(
            {
                "ev": "add",
                "id": "tiecase001",
                "at": stamp,
                "ns": later - 1000,
                "by": "deadbeef",
                "s": " ",
                "o": "deadbeef",
                "t": "(deadbeef) written first, in the name-LATER file",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (wl.store_dir / "aaa.jsonl").write_text(
        json.dumps(
            {
                "ev": "state",
                "id": "tiecase001",
                "at": stamp,
                "ns": later,
                "by": "judge",
                "s": "x",
                "note": "closed later in the same second",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert re.search(r"\[x\].*written first", wl.cli("--list").out), (
        "the tie was broken by filename, not by write order"
    )
    # CONTROL ON THE CONTROL: strip `ns` and the same two events must fold the OTHER way. Without it the case would pass just as well if `ns` did nothing.
    for name in ("aaa.jsonl", "zzz.jsonl"):
        path = wl.store_dir / name
        event = json.loads(path.read_text(encoding="utf-8"))
        event.pop("ns", None)
        path.write_text(json.dumps(event) + "\n", encoding="utf-8")
    assert re.search(r"\[ \].*written first", wl.cli("--list").out), (
        "CONTROL: ns is not the deciding field, so this case proves nothing"
    )


def test_203_the_fixture_owns_both_halves_of_the_store(wl):  # noqa: F811
    """So no call can straddle them.

    WHAT THIS CATCHES is not hypothetical: it happened to the operator's own worklist on 2026-09-04. The tracked writer files come from WORKLIST_STORE_DIR, while the legacy event log, the markdown mirror and the `.lastevent-*` liveness artifacts all resolve from the worklist path under TMPDIR. The bash `setup` exported only the first and left TMPDIR to a per-invocation prefix at
    seven call sites. One call without that prefix read items from the FIXTURE store and resolved the legacy half against the REAL temp directory, and since `compact()` folds both halves and rewrites the legacy file from the union, three fixture items were written into the operator's real worklist, where the Stop hook reported them as open work every round. Worse, they arrived
    owned by prefixes that never wrote under their own name, which put them beyond every sanctioned verb at once: `--tick` refuses another session's item, and `--reassign` refused the same item as having written no events at all.

    THE ASSERTION IS ON `--path`, DELIBERATELY. A first version asserted that a bare `--compact` wrote the fixture's legacy event log, and it FAILED for a reason that had nothing to do with the straddle: `compact()` returns early when that file does not exist yet, so the case tested an artifact the fix never produces, and its inverted control passed for the same empty reason.
    `--path` prints the resolved worklist, which is the one thing the straddle actually gets wrong.
    """
    out = wl.cli("--path").out.strip()
    assert out.startswith(str(wl.base)), (
        "a bare invocation resolved the worklist to %s, outside the fixture: it straddled" % out
    )
    # CONTROL ON THE CONTROL: the assertion above must be sensitive to TMPDIR, or it would pass just as well if TMPDIR did nothing here, which is precisely the false comfort that let the original leak through. Point one invocation at a THIRD directory and the resolved path must follow it.
    other = wl.base / "other"
    other.mkdir(parents=True, exist_ok=True)
    env = dict(wl.env)
    env["TMPDIR"] = str(other)
    out = wl.cli("--path", env=env).out.strip()
    assert out.startswith(str(other)), (
        "CONTROL: TMPDIR does not steer the worklist (%s), so this case proves nothing" % out
    )


FOLD_DUMP = """
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(sys.argv[1]).parent))
import wl_core as C
import wl_store as S

fold = S.load(C.worklist_for(C.project_start()), sync=False)
for rec in sorted(fold.items, key=lambda r: r["id"]):
    print(json.dumps({k: rec[k] for k in sorted(rec)}, sort_keys=True))
"""


def fold_dump(fix) -> str:
    """EVERY KEY OF EVERY RECORD, sorted, so the comparison cannot silently narrow to the fields this case's author thought of."""
    proc = subprocess.run(
        [sys.executable, "-c", FOLD_DUMP, str(fix.hook)],
        capture_output=True,
        text=True,
        env=dict(fix.env),
        check=False,
    )
    return proc.stdout


def test_204_compaction_is_lossless(wl):  # noqa: F811
    """The fold before equals the fold after.

    WHY THIS EXISTS, and why it is a property rather than another example. Compaction rewrites the whole log as a fresh snapshot, so every field the fold reads has to survive a round trip through `snapshot_events`. The suite tested compaction by its OUTPUTS (items consolidated, a live peer's file untouched, three items still present) and an output test only ever checks the fields
    the author happened to name. The field that went missing was the one nobody asserted: `by` is rewritten to "compact", which is deliberate, and `o` is the only thing left naming whose work an item is. Two readers scanned `by` and went blind on every compacted store, and the cost was an item that `--tick` refused as another session's while `--reassign` refused it as having
    written no events at all.

    So this case asserts the INVARIANT rather than a field: the fold of the store must equal the fold of the compacted store, across every key a record carries, for an item in every state the store can hold. A field added to the fold later is covered the day it is added, with no edit here, which is the property an example-based case cannot have.
    """
    ids = {}
    for label in ("an open item", "a done item", "a deferred item", "a leased item"):
        found = re.search(r"#([0-9a-f]+)", wl.cli("--add", "deadbeef", label).out)
        assert found, "--add produced no id for %r" % label
        ids[label] = found.group(1)
    wl.cli("--tick", "deadbeef", ids["a done item"], "closed at abc1234 with exit 0")
    wl.cli(
        "--defer",
        "deadbeef",
        ids["a deferred item"],
        "which way DEFAULT: do-it WHY: operator-call HOW: they-answer",
    )
    wl.cli("--lease", "deadbeef", ids["a leased item"], "+60", "worker:bg1", "note")

    before = fold_dump(wl)
    # ANTI-VACUITY: two empty dumps compare equal, and that is the shape this whole file exists to distrust. Four items were planted; fewer means the fixture, not the invariant, is what is being measured.
    planted = len([line for line in before.splitlines() if line.strip()])
    assert planted == 4, (
        "the fixture holds %d item(s), not 4, so the comparison below would be vacuous" % planted
    )
    wl.cli("--compact")
    after = fold_dump(wl)
    assert before == after, "compaction changed the fold"
    # CONTROL ON THE CONTROL: a passing comparison proves nothing unless a real loss makes it fail. Strip `o` from the compacted add events, the exact field whose absence caused the incident, and the same comparison must fire. Without it the case would pass just as well if the dump silently printed nothing, which is how a green assertion ends up guarding an empty set.
    for path in wl.store_dir.glob("*.jsonl"):
        out = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("ev") == "add":
                event.pop("o", None)
            out.append(json.dumps(event, separators=(",", ":")))
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
    lossy = fold_dump(wl)
    assert before != lossy, (
        "CONTROL: dropping the owner changed nothing, so this case proves nothing"
    )
