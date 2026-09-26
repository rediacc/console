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

from rediacc_hooks.tests.wlfix import import_wl, wl  # noqa: F401

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
        result=wl.run(),
    )


def test_199_control_a_live_peer_is_never_offered_for_handoff(wl):  # noqa: F811
    """CONTROL: a LIVE peer is not a handoff candidate, because its work is not this session's."""
    wl.say("done for now")
    wl.brief_now()
    mig_peer(wl, "handoff2", "(handoff2) work of a running session")
    wl.stem(".lastevent-handoff2.json").write_text("", encoding="utf-8")
    # This session's own deferred item, so the allow is loud (its guide) and the absence below is absence from a real report.
    wl.add_item("- [?] (deadbeef) keep the flag? DEFAULT: keep it")
    got = wl.run()
    assert got.out.strip(), "the hook produced no output, so the absence below means nothing"
    assert "HANDOFF CANDIDATES" not in got.out, "offered a live session's work for adoption"


def test_200_doctor_catches_what_a_tracked_file_makes_possible(wl):  # noqa: F811
    """Every plant is a shape that is SILENT by default: the reader skips unparseable lines by contract, so a conflict marker costs events and says nothing, and a secret in TMPDIR was private while a secret in a tracked file is pushed."""
    wl.say("done for now")
    wl.brief_now()
    stamp = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Assembled at runtime so the tracked source holds no token-shaped literal for check:ci-tracked-credentials to flag; the planted value is identical.
    ghp_shaped = "ghp" + "_abcdefghijklmnopqrstuvwxyz0123456789"
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


# ---- plan-document discovery -----------------------------------------------
#
# THE DEFECT THESE GUARD, measured live on 2026-09-17: `migrate_candidates` built its candidate set from the worklist store alone, so a committed `agent/plans/PLAN-*.md` carrying open boxes whose declared owner had stopped was named by NOTHING.
# 96 plans on disk, 15 carrying open boxes, 151 open boxes, and 99 of those belonged to a plan whose owner the same listing printed as `idle`. `--candidates` returned four bare prefixes and not one plan path.
#
# The two per-stop plan mechanisms cannot cover this and must not: `wl_checks.plan_drift_rows` and `wl_planfile.plan_rows` are both gated on `C.owned_by_me`, so they answer "does THIS session's own plan need attention", never "what undone design is nobody driving". Discovery is the only layer that may read both stores, which is why the cases live in the migrate suite.

PLAN_HEADER = (
    "# %s\n"
    "\n"
    "Status: %s\n"
    "First-Seen: 2026-09-01\n"
    "Owner: %s\n"
    "Updated: 2026-09-01\n"
    "\n"
    "One body line, so the file is more than a header.\n"
    "\n"
    "## Tasks\n"
    "\n"
)


def plant_plan(fix, slug, owner, status="ready", open_boxes=2, ticked=1):
    """One committed-looking plan under `agent/plans/`, returned as its path.

    The box bodies carry the slug because `wl_planfid.plan_tasks` de-duplicates on the first 120 normalised characters: two plans with identically-worded boxes would fold into one task and the census would then under-count the second.
    """
    directory = fix.proj / "agent" / "plans"
    directory.mkdir(parents=True, exist_ok=True)
    body = "".join("- [ ] open box %d of the %s design\n" % (i, slug) for i in range(open_boxes))
    body += "".join("- [x] ticked box %d of the %s design\n" % (i, slug) for i in range(ticked))
    path = directory / ("PLAN-%s.md" % slug)
    path.write_text(PLAN_HEADER % (slug, status, owner) + body, encoding="utf-8")
    return path


def spent_peer(fix, prefix, minutes=180):
    """A peer that TICKED everything and stopped: real aged events, zero open items.

    This is the shape the plan pass exists for and the shape every other helper here misses. `mig_peer` leaves an open item, which puts the prefix in `by_owner` and makes it a candidate for a reason that has nothing to do with plans -- a plan assertion built on it would pass with the plan pass deleted.
    """
    text = "an item this peer finished before it stopped"
    fix.cli("--add", prefix, text, env=as_session(fix, prefix))
    fix.cli(
        "--tick", prefix, item_id(fix, text), "suite green, exit 0", env=as_session(fix, prefix)
    )
    age_store(fix, prefix, minutes)


def candidates_json(fix):
    """`--candidates --json` parsed, LOUDLY on anything that is not a list."""
    raw = fix.cli(
        "--migrate", "deadbeef", "--candidates", "--json", env=as_session(fix, "deadbeef")
    )
    try:
        return json.loads(raw.out)
    except ValueError as exc:
        raise AssertionError(
            "--candidates --json printed no parseable JSON (%s)\n  out: %s\n  err: %s"
            % (exc, raw.out[:400], raw.err[:400])
        ) from exc


def plans_of(cands, prefix):
    """The plan rows one candidate carries, asserting the prefix appears EXACTLY once.

    Once is the assertion, not at-least-once: the third pass enriches an owner already in the list, and an owner appended twice would still satisfy every "the plan is named" check while giving the operator two rows for one session.
    """
    rows = [c for c in cands if c["prefix"] == prefix]
    assert len(rows) == 1, "%s appears %d time(s) in the listing, want exactly 1: %s" % (
        prefix,
        len(rows),
        [c["prefix"] for c in cands],
    )
    return rows[0].get("plans") or []


def test_205_a_plan_with_open_boxes_and_a_stopped_owner_is_a_candidate(wl):  # noqa: F811
    """And a finished or box-free plan is not.

    All three states of one plan, in one case, because the interesting failure is not "no plan is ever listed" -- it is a filter that lists EVERY plan. A `Status: done` plan and a plan whose last box is ticked are the two ways a plan clears itself, and a discovery surface that keeps naming them teaches the operator to ignore it.
    """
    mig_peer(wl, "cafe1234", "a peer item so the listing is never empty")
    plant_plan(wl, "open-design", "cafe1234", status="ready", open_boxes=2)
    named = [p["rel"] for p in plans_of(candidates_json(wl), "cafe1234")]
    assert named == ["agent/plans/PLAN-open-design.md"], (
        "the open plan was not named under its stopped owner: %s" % named
    )

    # A FINISHED plan is not work. `FINISHED_STATES`, never `in_scope_status`: the latter also drops `draft`, which is this repo's default header on a plan under active execution, and would hide most of what this exists to surface.
    plant_plan(wl, "open-design", "cafe1234", status="done", open_boxes=2)
    assert plans_of(candidates_json(wl), "cafe1234") == [], (
        "a Status: done plan is still being offered for adoption"
    )

    # And a plan whose boxes are all ticked has nothing left to hand over.
    plant_plan(wl, "open-design", "cafe1234", status="ready", open_boxes=0, ticked=3)
    assert plans_of(candidates_json(wl), "cafe1234") == [], (
        "a plan with zero open boxes is still being offered for adoption"
    )


def test_206_a_live_sessions_plan_is_never_offered(wl):  # noqa: F811
    """Listing is not adopting, but a live peer's plan is still not on the menu.

    The rule is the same one the item path already obeys and for the same reason: `--plan` rewrites a committed document, and offering a running session's design is how two sessions end up executing one plan. The idle peer beside it is the anti-vacuity half -- without it an empty listing would satisfy this assertion for the wrong reason.
    """
    mig_peer(wl, "cafe1234", "an idle peer item")
    plant_plan(wl, "idle-owned", "cafe1234")
    plant_plan(wl, "live-owned", "beef0001")
    wl.brief_other("beef0001")

    cands = candidates_json(wl)
    every = [p["rel"] for c in cands for p in (c.get("plans") or [])]
    assert "agent/plans/PLAN-idle-owned.md" in every, (
        "the idle owner's plan is missing, so the absence below proves nothing: %s" % every
    )
    assert "agent/plans/PLAN-live-owned.md" not in every, (
        "a LIVE session's plan was offered for adoption: %s" % every
    )
    assert [c["prefix"] for c in cands].count("beef0001") == 0, (
        "a live session was listed as a handoff candidate: %s" % [c["prefix"] for c in cands]
    )


def test_207_an_owner_with_items_is_enriched_not_duplicated(wl):  # noqa: F811
    """One row per prefix, carrying both its items and its plans.

    The third pass runs after two that may already have added the owner, so "append a candidate" is the wrong default: it would print one session twice, once with its items and once with its plans, and the operator would have to know they were the same session.
    """
    mig_peer(wl, "cafe1234", "a real worklist item")
    plant_plan(wl, "same-owner", "cafe1234")
    cands = candidates_json(wl)
    row = [c for c in cands if c["prefix"] == "cafe1234"]
    assert len(row) == 1, "cafe1234 appears %d time(s): %s" % (
        len(row),
        [c["prefix"] for c in cands],
    )
    assert row[0]["counts"]["open"] == 1, "the item half of the enriched row was lost: %s" % row[0]
    assert [p["rel"] for p in row[0]["plans"]] == ["agent/plans/PLAN-same-owner.md"], (
        "the plan half of the enriched row was lost: %s" % row[0]
    )

    # AND THE HUMAN-READABLE RENDERER SAYS BOTH. The JSON above is what /migrate reads; this is what the operator reads, and it had its own item_desc branch to get wrong.
    out = mig(wl, "--candidates")
    assert out.count("  cafe1234  ") == 1, "the prefix is printed twice:\n%s" % out
    assert "PLAN agent/plans/PLAN-same-owner.md  [ready]  2 open / 1 ticked" in out, (
        "the renderer named no plan line:\n%s" % out
    )


def test_208_control_a_peer_with_nothing_but_a_plan_is_still_a_candidate(wl):  # noqa: F811
    """Zero items, no STATE.md Next action, one `Status: ready` plan. Nothing else.

    THE CASE THE WHOLE CHANGE EXISTS FOR, and the only one that fails if the third pass is deleted: every other case here has an item or a handoff note propping the prefix up. Live on 2026-09-17 this was `8f55d4f0` and `PLAN-tooling-transformation.md`, 13 open boxes and 141 ticked, named by no surface in the repo.
    """
    spent_peer(wl, "cafe1234")
    assert not (wl.proj / "agent" / "cafe1234").exists(), (
        "the fixture wrote a STATE.md for the peer, so the STATE.md pass could carry this case"
    )
    plant_plan(wl, "nothing-but-a-plan", "cafe1234", status="ready", open_boxes=3, ticked=7)

    cands = candidates_json(wl)
    row = [c for c in cands if c["prefix"] == "cafe1234"]
    assert len(row) == 1, "the plan-only peer is not a candidate at all: %s" % [
        c["prefix"] for c in cands
    ]
    assert row[0]["counts"] == {"open": 0, "inflight": 0, "deferred": 0}, (
        "a plan-only candidate must carry zeroed counts: %s" % row[0]["counts"]
    )
    assert row[0]["plans"] == [
        {
            "rel": "agent/plans/PLAN-nothing-but-a-plan.md",
            "status": "ready",
            "open": 3,
            "ticked": 7,
        }
    ], "the plan row is wrong: %s" % row[0]["plans"]

    out = mig(wl, "--candidates")
    assert "0 worklist item(s), but 1 committed plan(s) with 3 open box(es)" in out, (
        "the zero-item line still reads as a STATE.md candidate:\n%s" % out
    )

    # THE NEGATIVE CONTROL, and without it the assertions above would pass just as well against a listing that names every plan in the tree. A plan this session already owns is not a handoff candidate, and neither is one that declares itself unowned -- `owned_by_me(None)` is True, so the per-stop advisory already shows it to everybody.
    plant_plan(wl, "already-mine", "deadbeef")
    plant_plan(wl, "no-owner-at-all", "unowned")
    every = [p["rel"] for c in candidates_json(wl) for p in (c.get("plans") or [])]
    assert "agent/plans/PLAN-already-mine.md" not in every, (
        "this session's own plan was offered back to it: %s" % every
    )
    assert "agent/plans/PLAN-no-owner-at-all.md" not in every, (
        "an unowned plan was duplicated into the handoff listing: %s" % every
    )


def test_209_migrate_prints_the_plan_command_and_plan_adopts(wl):  # noqa: F811
    """A store migration never rewrites a committed document; `--plan` does, when named.

    The split is the point. Moving items is a store operation and takes no argument beyond a prefix, so folding plan adoption into it would rewrite a peer's committed file as a side effect of a verb whose whole contract is the worklist. The move prints the command instead, and the command names every path it will touch.
    """
    mig_peer(wl, "cafe1234", "an item to migrate")
    plan = plant_plan(wl, "handed-over", "cafe1234", status="ready", open_boxes=2, ticked=1)
    before = plan.read_text(encoding="utf-8")

    moved = mig(wl, "cafe1234")
    assert "cafe1234 also owns 1 open plan(s), not moved by this command" in moved, (
        "the move said nothing about the peer's plan:\n%s" % moved
    )
    assert (
        "adopt one:  worklist.py --migrate deadbeef --plan agent/plans/PLAN-handed-over.md" in moved
    ), "the move printed no runnable adopt command:\n%s" % moved
    assert plan.read_text(encoding="utf-8") == before, (
        "the store migration rewrote a committed plan file"
    )

    adopted = mig(wl, "--plan", "agent/plans/PLAN-handed-over.md")
    assert "adopted agent/plans/PLAN-handed-over.md (was cafe1234, 2 open box(es))" in adopted, (
        "the adoption did not report itself:\n%s" % adopted
    )
    # THE CENSUS IS KEYED ON BYTE SIZE, so an adoption that does not say this leaves a loud staleness banner on the next SessionStart with no command attached to it.
    assert "npm run check:ci-plan-record -- --update" in adopted, (
        "the adoption printed no census-regeneration command:\n%s" % adopted
    )

    after = plan.read_text(encoding="utf-8")
    head = after.splitlines()[:10]
    assert any(line.startswith("Owner: deadbeef (adopted from cafe1234 ") for line in head), (
        "the Owner: line was not re-stamped inside the header: %s" % head
    )
    # SESSION-SHAPED TOKEN FIRST: `PLAN_OWNER_ID_RE` takes the first 8-hex word on the line, so writing the predecessor first would hand the plan straight back.
    owner = import_wl("wl_checks").plan_owner(str(wl.proj), "agent/plans/PLAN-handed-over.md")
    assert owner == "deadbeef", "the header still resolves to %r after adoption" % owner
    assert len(after.splitlines()) == len(before.splitlines()), (
        "adoption changed the line count, so the header may have been pushed past line 10"
    )
    assert [ln for ln in after.splitlines() if ln.startswith(("- [ ]", "- [x]"))] == [
        ln for ln in before.splitlines() if ln.startswith(("- [ ]", "- [x]"))
    ], "adoption touched a box line, which would re-sign it for check:ci-plan-boxes A0"

    # Twice is a no-op, not a second re-stamp naming this session as its own predecessor.
    again = mig(wl, "--plan", "agent/plans/PLAN-handed-over.md")
    assert "already belongs to deadbeef; nothing changed" in again, (
        "a second adoption did not recognise itself:\n%s" % again
    )
    assert plan.read_text(encoding="utf-8") == after, "a second adoption rewrote the file"


def test_210_plan_adoption_refuses_a_finished_or_box_free_plan(wl):  # noqa: F811
    """The two refusals, byte-checked, because a refusal that still writes is worse than no refusal."""
    done = plant_plan(wl, "finished-design", "cafe1234", status="done", open_boxes=2)
    empty = plant_plan(wl, "drained-design", "cafe1234", status="ready", open_boxes=0, ticked=2)
    before = {p: p.read_text(encoding="utf-8") for p in (done, empty)}

    out = mig(
        wl, "--plan", "agent/plans/PLAN-finished-design.md", "agent/plans/PLAN-drained-design.md"
    )
    assert "refused: agent/plans/PLAN-finished-design.md is Status: done (finished)" in out, (
        "a finished plan was not refused:\n%s" % out
    )
    assert "refused: agent/plans/PLAN-drained-design.md has no open boxes" in out, (
        "a plan with nothing left open was not refused:\n%s" % out
    )
    assert "npm run check:ci-plan-record" not in out, (
        "a run that wrote nothing still asked for a census regeneration:\n%s" % out
    )
    for path, text in before.items():
        assert path.read_text(encoding="utf-8") == text, "%s was rewritten despite the refusal" % (
            path.name
        )
