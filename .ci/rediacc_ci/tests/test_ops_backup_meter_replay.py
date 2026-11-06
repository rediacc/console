"""`rediacc_ci.ops.backup_meter_replay` against a fake store and a fake rdc: no network, no machine.

The world is one subscription in the bench bucket. A healthy world meters what the store holds (R1 and A1 in place); each control changes one thing (the meter bills only the rerun's own uploads, a lineage drifts, the store moves mid-read, the throttled run finishes early) and must come out red or no-verdict, so a green cannot come from a comparison that never ran.
"""

from __future__ import annotations

import datetime
import io
import json
import urllib.parse
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci.ops import backup_meter_replay as mod

if TYPE_CHECKING:
    from pathlib import Path

SECRET = "s3cr3t-value-that-must-never-print"
KEY_ID = "key-id-that-must-never-print"
ENV = {
    "ACCOUNT_BACKUP_S3_ENDPOINT": "https://acct.r2.cloudflarestorage.com",
    "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID": KEY_ID,
    "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY": SECRET,
}
SUB = "63284afd-0000-4000-8000-000000000001"
LIN = "03ee0999-0000-4000-8000-000000000002"
OTHER = "1b8e6a28-0000-4000-8000-000000000003"
CELL = 4 * 1024 * 1024
PAGE = 7  # small pages so every listing exercises the continuation token


def envelope(data: dict, success: bool = True) -> dict:
    """The shape `rdc -o json` really prints: the figures sit under `data` (live run 2026-11-05)."""
    return {"success": success, "command": "backup", "data": data, "errors": None, "warnings": []}


def test_rdc_json_unwraps_the_envelope_and_refuses_a_failed_one():
    calls = iter(
        [
            (0, json.dumps(envelope({"subscriptionId": SUB})), ""),
            (0, json.dumps(envelope({"subscriptionId": SUB}, success=False)), ""),
        ]
    )
    rdc = mod.Rdc("rdc", "eu-bench", mod.Deps(runner=lambda _argv, _timeout: next(calls)))
    assert rdc.json("backup", "usage") == {"subscriptionId": SUB}
    with pytest.raises(mod.NoVerdictError, match="no data object"):
        rdc.json("backup", "usage")


class World:
    """The store (key -> size) and what the account server answers about it."""

    def __init__(self, *, meter_all: bool = True, early_finish: bool = False):
        self.objects: dict[str, int] = {}
        self.meter_all = meter_all  # False: the pre-fix meter, billing only the rerun's own PUTs
        self.early_finish = early_finish
        self.billed: dict[str, int] = {}  # lineage -> chunks billed
        self.next_chunk = 0
        self.snapshot_running = False
        self.client_rc: int | None = None
        self.calls: list[list[str]] = []
        self.list_calls = 0
        self.move_on_list: int | None = None  # add a chunk on this listing call
        self.headers: list[dict] = []
        self.check_rc_override: int | None = None

    # -- store
    def add_chunks(self, lineage: str, n: int) -> None:
        for _ in range(n):
            self.objects["t/%s/l/%s/c/%064x" % (SUB, lineage, self.next_chunk)] = CELL
            self.next_chunk += 1

    def add_manifest(self, lineage: str, sid: str) -> None:
        self.objects["t/%s/l/%s/m/%s" % (SUB, lineage, sid)] = 1234

    def chunks(self, lineage: str) -> int:
        return sum(1 for k in self.objects if "/l/%s/c/" % lineage in k)

    def transport(self, method, url, _body, headers):
        assert method == "GET"
        self.headers.append(headers)
        self.list_calls += 1
        if self.move_on_list == self.list_calls:
            self.add_chunks(LIN, 1)
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        assert urllib.parse.urlsplit(url).path.startswith("/rediacc-backups-bench")
        keys = sorted(k for k in self.objects if k.startswith(q["prefix"]))
        start = int(q.get("continuation-token", "0"))
        page = keys[start : start + PAGE]
        more = start + PAGE < len(keys)
        xml = "<ListBucketResult><IsTruncated>%s</IsTruncated>" % ("true" if more else "false")
        for k in page:
            xml += "<Contents><Key>%s</Key><Size>%d</Size></Contents>" % (k, self.objects[k])
        if more:
            xml += "<NextContinuationToken>%d</NextContinuationToken>" % (start + PAGE)
        return 200, (xml + "</ListBucketResult>").encode()

    # -- account
    def lineage_rows(self) -> list[dict]:
        rows = []
        for lin in sorted({k.split("/")[3] for k in self.objects} | set(self.billed)):
            n = self.chunks(lin)
            rows.append(
                {
                    "lineageGuid": lin,
                    "ledgerBytesBefore": self.billed.get(lin, 0) * CELL,
                    "ledgerChunksBefore": self.billed.get(lin, 0),
                    "observedBytes": n * CELL,
                    "observedChunks": n,
                    "referencedBytes": n * CELL,
                    "referencedChunks": n,
                    "unreferencedBytes": 0,
                    "unreferencedChunks": 0,
                    "unreferencedPastGraceChunks": 0,
                    "applied": False,
                    "skipped": None,
                }
            )
        return rows

    def reconcile(self, dry_run: bool) -> dict:
        rows = self.lineage_rows()
        if not dry_run:
            for row in rows:
                self.billed[row["lineageGuid"]] = row["observedChunks"]
                row["applied"] = True
        ledger = sum(self.billed.values())
        return {
            "subscriptionId": SUB,
            "lineages": rows,
            "ledgerBytes": ledger * CELL,
            "ledgerChunkCount": ledger,
            "bucketChunkBytes": sum(self.objects[k] for k in self.objects if "/c/" in k),
            "bucketChunkCount": sum(1 for k in self.objects if "/c/" in k),
            "driftBytes": 0,
        }

    def usage(self) -> dict:
        total = sum(self.billed.values())
        return {
            "subscriptionId": SUB,
            "storedBytes": total * CELL,
            "chunkCount": total,
            "lineages": [
                {"lineageGuid": lin, "storedBytes": n * CELL, "chunkCount": n}
                for lin, n in sorted(self.billed.items())
            ],
        }

    def drift(self) -> bool:
        return any(
            self.billed.get(lin, 0) != self.chunks(lin)
            for lin in {k.split("/")[3] for k in self.objects}
        )

    # -- rdc
    def runner(self, argv, _timeout):
        args = list(argv[3:])  # drop rdc --config <name>
        self.calls.append(args)
        if args[:2] == ["term", "connect"]:
            cmd = args[4]
            if cmd == mod.RUNNING_COMMAND:
                return 0, "RUNNING\n" if self.snapshot_running else "IDLE\n", ""
            if cmd == mod.KILL_COMMAND:
                if self.snapshot_running:
                    self.snapshot_running = False
                    self.client_rc = 1
                return 0, "GONE\n", ""
            raise AssertionError(cmd)
        if "-o" in args:
            args = [a for a in args if a not in ("-o", "json")]
            json_out = True
        else:
            json_out = False
        if args[:2] == ["backup", "usage"]:
            return 0, "fetching\n" + json.dumps(envelope(self.usage()), indent=2), ""
        if args[:2] == ["backup", "reconcile"]:
            if "--check" in args:
                if self.check_rc_override is not None:
                    return self.check_rc_override, "", ""
                return (1 if self.drift() else 0), "", ""
            return 0, json.dumps(envelope(self.reconcile("--dry-run" in args))), ""
        if args[:2] == ["backup", "snapshot"] and json_out:
            # the rerun: uploads what is missing (10 chunks), commits, and the meter moves
            before = self.chunks(LIN)
            self.add_chunks(LIN, 10)
            self.add_manifest(LIN, "20261105T000000Z-rerun")
            if self.meter_all:
                self.billed[LIN] = self.chunks(LIN)
            else:
                self.billed[LIN] = self.billed.get(LIN, 0) + (self.chunks(LIN) - before)
            return (
                0,
                json.dumps(
                    {"snapshotId": "20261105T000000Z-rerun", "lineage": LIN, "chunksUploaded": 10}
                ),
                "",
            )
        raise AssertionError(args)

    def spawner(self, argv, _out_path, _err_path):
        assert "--bwlimit" in argv
        self.snapshot_running = True
        self.client_rc = None
        world = self

        class Proc:
            def poll(self):
                return world.client_rc

            def wait(self, timeout=None):
                assert timeout is None or timeout > 0
                return world.client_rc if world.client_rc is not None else 1

            def kill(self):
                world.snapshot_running = False

        return Proc()

    def sleep(self, _s):
        if self.snapshot_running:
            self.add_chunks(LIN, 20)
            if self.early_finish:
                self.add_manifest(LIN, "early")
                self.snapshot_running = False
                self.client_rc = 0


def deps(world: World, tmp_path: Path) -> mod.Deps:
    return mod.Deps(runner=world.runner, spawner=world.spawner, sleep=world.sleep, workdir=tmp_path)


def run(world: World, tmp_path: Path, *argv: str) -> tuple[int, str]:
    out = io.StringIO()
    rc = mod.main(
        [*list(argv), "--rdc", "rdc"],
        transport=world.transport,
        environ=dict(ENV),
        deps=deps(world, tmp_path),
        out=out,
    )
    text = out.getvalue()
    assert SECRET not in text
    assert KEY_ID not in text
    return rc, text


REPLAY = (
    "replay",
    "--config",
    "eu-bench",
    "--repo",
    "mautic",
    "--machine",
    "hostinger",
    "--poll",
    "0",
)


# Any, not World: the cases replace World methods with variants to plant one defect each.
def seeded(**kw) -> Any:
    w = World(**kw)
    w.add_chunks(LIN, 5)
    w.add_manifest(LIN, "old")
    w.add_chunks(OTHER, 3)
    w.billed = {LIN: 5, OTHER: 3}
    return w


def test_replay_metered_world_exits_0(tmp_path):
    w = seeded()
    rc, text = run(w, tmp_path, *REPLAY)
    assert rc == 0, text
    assert "PASS       lineage chunkCount" in text
    assert "meter 75, listing 75" in text  # 5 baseline + 60 killed-run uploads + 10 by the rerun
    assert ["term", "connect", "hostinger", "-c", mod.KILL_COMMAND] in w.calls
    assert ["backup", "reconcile", "mautic@hostinger", "--check"] in w.calls
    # the listing was signed
    assert all(h["Authorization"].startswith("AWS4-HMAC-SHA256") for h in w.headers)


def test_replay_control_pre_fix_meter_is_red(tmp_path):
    """The bug itself: the rerun bills only its own 10 uploads, not the killed run's 60."""
    w = seeded(meter_all=False)
    rc, text = run(w, tmp_path, *REPLAY)
    assert rc == 1, text
    assert "FAIL       lineage chunkCount" in text
    assert "meter 15, listing 75" in text


def test_replay_check_drift_alone_is_red(tmp_path):
    w = seeded()
    w.check_rc_override = 1
    rc, text = run(w, tmp_path, *REPLAY)
    assert rc == 1
    assert "FAIL       reconcile --check" in text


def test_replay_snapshot_finishing_early_is_no_verdict(tmp_path):
    w = seeded(early_finish=True)
    rc, text = run(w, tmp_path, *REPLAY, "--kill-after", "50")
    assert rc == 2, text
    assert "before 50" in text
    assert ["term", "connect", "hostinger", "-c", mod.KILL_COMMAND] not in w.calls


def test_replay_refuses_when_a_snapshot_already_runs(tmp_path):
    w = seeded()
    w.snapshot_running = True
    rc, text = run(w, tmp_path, *REPLAY)
    assert rc == 2
    assert "already runs" in text


def test_replay_moving_store_is_no_verdict(tmp_path):
    # A healthy run's last listing is the second verdict read; a chunk landing just before it moves the store.
    probe = seeded()
    assert run(probe, tmp_path, *REPLAY)[0] == 0
    w = seeded()
    w.move_on_list = probe.list_calls
    rc, text = run(w, tmp_path, *REPLAY)
    assert rc == 2
    assert "the store moved" in text


CENSUS = ("census", "--config", "eu-bench")


def _line(text: str, what: str) -> list[str]:
    """[verdict, detail] of the first report line naming `what`."""
    for line in text.splitlines():
        if what in line:
            verdict, rest = line.split(None, 1)
            return [verdict, rest.split(what, 1)[1].strip()]
    raise AssertionError("no line names %r in:\n%s" % (what, text))


def test_census_clean_exits_0(tmp_path):
    w = seeded()
    rc, text = run(w, tmp_path, *CENSUS)
    assert rc == 0, text
    assert _line(text, "total chunkCount") == ["PASS", "meter 8, listing 8"]


def test_census_control_drift_is_red_and_apply_repairs(tmp_path):
    w = seeded()
    w.add_chunks(LIN, 4)  # debris a killed run left, unbilled
    rc, text = run(w, tmp_path, *CENSUS)
    assert rc == 1, text
    assert _line(text, "total chunkCount") == ["FAIL", "meter 8, listing 12"]
    rc, text = run(w, tmp_path, *CENSUS, "--apply")
    assert rc == 0, text
    assert "1 lineage(s) applied" in text or "2 lineage(s) applied" in text


def test_census_refset_sum_mismatch_is_red(tmp_path):
    w = seeded()
    orig = w.reconcile

    def short(dry_run):
        doc = orig(dry_run)
        doc["lineages"][0]["referencedChunks"] -= 1
        return doc

    w.reconcile = short
    rc, text = run(w, tmp_path, *CENSUS)
    assert rc == 1
    assert "ref+unref chunks" in text


def test_census_skipped_lineage_is_no_verdict(tmp_path):
    w = seeded()
    orig = w.reconcile

    def skip(dry_run):
        doc = orig(dry_run)
        doc["lineages"][0]["skipped"] = "leased"
        return doc

    w.reconcile = skip
    rc, text = run(w, tmp_path, *CENSUS)
    assert rc == 2
    assert "skipped by the server (leased)" in text


def test_census_strict_referenced(tmp_path):
    w = seeded()
    orig = w.reconcile

    def unref(dry_run):
        doc = orig(dry_run)
        for row in doc["lineages"]:
            if row["lineageGuid"] == LIN:
                row["referencedChunks"] -= 2
                row["referencedBytes"] -= 2 * CELL
                row["unreferencedChunks"] += 2
                row["unreferencedBytes"] += 2 * CELL
        return doc

    w.reconcile = unref
    rc, text = run(w, tmp_path, *CENSUS)
    assert rc == 0, text  # unreferenced debris is billed, not a mismatch
    rc, text = run(w, tmp_path, *CENSUS, "--strict-referenced", LIN)
    assert rc == 1
    assert "stored=referenced" in text


def test_missing_credentials_exit_2(tmp_path):
    w = seeded()
    out = io.StringIO()
    rc = mod.main(
        [*list(CENSUS), "--rdc", "rdc"],
        transport=w.transport,
        environ={},
        deps=deps(w, tmp_path),
        out=out,
    )
    assert rc == 2
    assert w.calls == []


def test_listing_refused_is_no_verdict(tmp_path):
    w = seeded()
    w.transport = lambda *_a: (403, b"")
    rc, text = run(w, tmp_path, *CENSUS)
    assert rc == 2
    assert "HTTP 403" in text


@pytest.mark.parametrize(
    ("start", "end", "crosses"),
    [
        ("2026-11-05T02:50:00", "2026-11-05T03:10:00", True),
        ("2026-11-05T03:10:00", "2026-11-05T04:00:00", False),
        ("2026-11-05T23:00:00", "2026-11-06T03:00:00", True),
        ("2026-11-05T10:00:00", "2026-11-05T11:00:00", False),
    ],
)
def test_crosses_maintenance(start, end, crosses):
    s = datetime.datetime.fromisoformat(start).replace(tzinfo=datetime.UTC)
    e = datetime.datetime.fromisoformat(end).replace(tzinfo=datetime.UTC)
    assert mod.crosses_maintenance(s, e) is crosses


def test_parse_page_decodes_entities_and_token():
    xml = (
        "<IsTruncated>true</IsTruncated><Contents><Key>t/s/l/x/m/a&amp;b</Key><Size>3</Size></Contents>"
        "<NextContinuationToken>tok&amp;1</NextContinuationToken>"
    )
    objects, token = mod.parse_page(xml)
    assert objects == [("t/s/l/x/m/a&b", 3)]
    assert token == "tok&1"


def test_replay_unreadable_listing_mid_poll_kills_the_client_and_the_remote_run(tmp_path):
    w = seeded()
    base_transport = w.transport
    calls = {"n": 0}

    def flaky(method, url, body, headers):
        calls["n"] += 1
        # the baseline listing is call 1 (one page); the first poll listing fails
        if calls["n"] >= 2:
            return 500, b""
        return base_transport(method, url, body, headers)

    w.transport = flaky
    rc, text = run(w, tmp_path, *REPLAY)
    assert rc == 2, text
    assert ["term", "connect", "hostinger", "-c", mod.KILL_COMMAND] in w.calls
    assert w.snapshot_running is False


def test_real_runner_missing_binary_is_127_not_a_crash():
    rc, _out, err = mod.real_runner(["/nonexistent/rdc-binary", "x"], 5)
    assert rc == 127
    assert "/nonexistent/rdc-binary" in err
