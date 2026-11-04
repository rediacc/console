"""Legs b, c and d of `rediacc_ci.drills.backup` with REAL renet in the loop (`--renet`).

WHAT CHANGES. The host-only legs build their own cells in Python and talk to the control plane as a stand-in for a machine. With `--renet` the same three claims are proven by a machine: a real repository on the worker VM (LUKS image on btrfs, a licence issued by this run's own gateway) is snapshotted by `renet backup snapshot`, one cell of its image is rewritten and it is snapshotted again, and both snapshots are restored by `renet backup restore` into DIFFERENT repositories whose images are compared byte for byte with the source's. The proofs are the legs' own:

  b  the seed snapshot is stored, the manifest index lists it, and the quota ledger moved by exactly the bytes renet reports uploading.
  c  one rewritten cell transfers exactly one cell (`bytesUploaded == CELL_BYTES`), the ledger grew by that one cell, and the delta lists the seed as its parent.
  d  both snapshots restore into a fresh repository, and each restored image's sha256 equals the digest of the source image taken when that snapshot was cut. Control: the two digests differ, so identical inputs cannot pass.
  p  a swapped image is refused with nothing uploaded, by the journal and, with the journal gone, by the server's previous row; a wrong passphrase places nothing. Controls: the original image stores again, and the right passphrase restores it byte for byte.
  r  a chunk overwritten in the store is deleted by the account's repair route and put back by `renet backup repair` from the anchor, the lease is released, and the store pass is clean. Control: a hash no anchor holds is named as unrepairable, and the verb exits non-zero.

The transport, licence installation, repository creation, quiesce and byte comparison are `rediacc_ci.drills.backup_roundtrip`'s (`Roundtrip`), driven against THIS drill's gateway and subscription instead of a second account. Everything stays on the VM network: the gateway the drill started is addressed by the bridge host (the Host header names the universe, see that module), and the renet under test is the one already installed on the worker (never `./rdc.sh`, which rebuilds and redeploys it).

What the later legs inherit, so e, f, j, k and l keep their meaning: `stored_lineage` (the source repository's guid, the lineage the chunks live under), `snap_seed` and `snap_incr` (renet's snapshot ids), `seed_stored_bytes` (the seed upload, so leg e's `seed + one cell` equals the ledger), `seed_sha`, and `license_blob`/`machine_id` (the source repository's licence and the worker's machine id, which leg k presents to restore under a lapsed subscription).

NOT PROVEN HERE, said plainly: the worker must already hold a renet built from this tree (`vm:check` installs one), and the account gateway must be reachable from it (`rediacc_ci.drills.backup` binds the bridge address when the VM network exists, and `--renet` refuses itself when it does not).
"""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any

from rediacc_ci.drills import backup_roundtrip as rt

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable

# The byte rewritten into the source image between the two snapshots: cell 3, 4 KiB in, 32 bytes of the VM's own entropy.
MUTATION_CELL = 3
MUTATION_OFFSET_IN_CELL = 4096
MUTATION_BYTES = 32
# Where renet keeps a repository's journal (`<datastoreID>-<guid>.json`), and a name beside it this leg moves it to for the lost-journal case.
JOURNAL_DIR = "/var/lib/rediacc/backup-journal"
JOURNAL_ASIDE = ".drill-aside"
IMAGE_ASIDE = ".drill-original"
# A hash no fixture and no anchor holds.
UNHELD_HASH = "ab" * 32
# Leg t: the session lifetime the dev gateway is moved to, and how long one trickled cell takes (over two lifetimes). Leg u: how long the first run lives before the KILL.
SESSION_TTL_DRILL_MS = 4000
TRICKLE_SECONDS = 12
KILL_AFTER_SECONDS = 6


def mutation_command(datastore: str, guid: str, cell_bytes: int) -> str:
    """The shell that rewrites `MUTATION_BYTES` of cell `MUTATION_CELL` of the (unmounted) source image in place, so exactly that cell's hash changes."""
    offset = MUTATION_CELL * cell_bytes + MUTATION_OFFSET_IN_CELL
    return (
        "sudo -n sh -c 'head -c %d /dev/urandom | dd of=%s/repositories/%s bs=1 seek=%d "
        "conv=notrunc status=none && sync'" % (MUTATION_BYTES, datastore, guid, offset)
    )


def swap_image_command(datastore: str, guid: str) -> str:
    """The shell that moves the repository's image aside and puts a freshly formatted LUKS image of the same size under its name: a replaced image, with another UUID and key digest. Fast KDF settings, since this image is never opened."""
    image = "%s/repositories/%s" % (datastore, guid)
    return (
        "sudo -n sh -c 'set -e; size=$(stat -c %%s %(image)s); mv %(image)s %(image)s%(aside)s; "
        "truncate -s $size %(image)s; head -c 32 /dev/urandom | cryptsetup luksFormat --batch-mode "
        "--pbkdf pbkdf2 --pbkdf-force-iterations 1000 --key-file - %(image)s'"
        % {"image": image, "aside": IMAGE_ASIDE}
    )


def unswap_image_command(datastore: str, guid: str) -> str:
    image = "%s/repositories/%s" % (datastore, guid)
    return (
        "sudo -n sh -c 'if [ -e %(image)s%(aside)s ]; then mv -f %(image)s%(aside)s %(image)s; fi'"
        % {
            "image": image,
            "aside": IMAGE_ASIDE,
        }
    )


def journal_aside_command(guid: str) -> str:
    return """sudo -n sh -c 'for f in %s/*-%s.json; do mv "$f" "$f%s"; done'""" % (
        JOURNAL_DIR,
        guid,
        JOURNAL_ASIDE,
    )


def journal_back_command(guid: str) -> str:
    return (
        """sudo -n sh -c 'for f in %(dir)s/*-%(guid)s.json%(aside)s; do mv "$f" "${f%%%(aside)s}"; done'"""
        % {
            "dir": JOURNAL_DIR,
            "guid": guid,
            "aside": JOURNAL_ASIDE,
        }
    )


def repair_command(datastore: str, guid: str) -> str:
    return "sudo -n renet backup repair --datastore %s --repo %s --hashes-stdin" % (datastore, guid)


def snapshot_ok(doc: dict[str, Any]) -> bool:
    return doc.get("status") == "stored" and bool(doc.get("snapshotId"))


def uploaded(doc: dict[str, Any]) -> int:
    """`bytesUploaded` of a snapshot document, 0 when absent or not a number."""
    value = doc.get("bytesUploaded")
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return 0
    try:
        return int(value)
    except ValueError:
        return 0


class RenetLegs:
    """One run's real-renet legs. `backup` is the running `Backup`; `roundtrip` is the seam the tests replace."""

    def __init__(self, backup: Any, roundtrip: rt.Roundtrip) -> None:
        self.b = backup
        self.rt = roundtrip
        self.src = ""
        self.src_sha = ""
        self.incr_sha = ""
        self.seed_uploaded = 0
        self.incr_uploaded = 0

    @property
    def d(self) -> Any:
        return self.b.d

    def say(self, text: str) -> None:
        self.d.note(text)

    # ------------------------------------------------------------------ leg b

    def leg_b(self) -> None:
        d, r = self.d, self.rt
        d.step("Leg b (renet): a real repository is snapshotted by `renet backup snapshot`")
        self.src = str(uuid.uuid4())
        r.created.append(self.src)
        # The licence comes first: an enforcing renet refuses `repository create` for a guid with no installed licence.
        r.issue_license(self.src, self.src, "grand")
        blob = json.loads((r.work / "lic.json").read_text(encoding="utf-8"))
        machine_id = r.run_vm("sudo -n renet machine-id").stdout.strip("\r\n")
        r.create_source(self.src)
        d.last_cmd = "renet repository license-status"
        d.assert_equal(
            "valid", r.source_status(self.src), "the source repository's licence is valid"
        )

        r.run_vm("sudo -n renet repository down --name %s" % self.src, must=False)
        r.run_vm("sudo -n renet repository unmount --name %s" % self.src)
        self.src_sha = r.image_digest(self.src, quiesce=True)
        d.last_cmd = "sha256sum of the source image"
        d.assert_not_equal("", self.src_sha, "the source image is digested while quiesced")

        doc = r.snapshot(self.src)
        d.last_cmd = "renet backup snapshot (seed)"
        d.assert_equal("stored", str(doc.get("status", "")), "renet stores the seed snapshot")
        self.seed_uploaded = uploaded(doc)
        d.assert_not_equal("0", str(self.seed_uploaded), "and uploaded real bytes")
        snap = str(doc.get("snapshotId", ""))

        listed = self.b.lineage_snapshots(self.src)
        d.last_cmd = "GET /backups/manifests?lineage=<source repository>"
        d.assert_equal(snap, ",".join(listed), "the manifest index lists exactly the seed snapshot")
        d.assert_equal(
            str(self.seed_uploaded),
            str(self.b.stored_bytes()),
            "and the ledger moved by exactly the bytes renet uploaded",
        )

        self.b.snap_seed = snap
        self.b.seed_sha = self.src_sha
        self.b.stored_lineage = self.src
        self.b.license_blob = blob if isinstance(blob, dict) else {}
        self.b.machine_id = machine_id
        self.b.seed_stored_bytes = self.seed_uploaded

    # ------------------------------------------------------------------ leg c

    def leg_c(self) -> None:
        d, r = self.d, self.rt
        d.step("Leg c (renet): one rewritten cell moves one cell")
        cell_bytes = int(r.cell_bytes)
        r.run_vm(mutation_command(r.datastore, self.src, cell_bytes))
        self.incr_sha = r.image_digest(self.src, quiesce=True)
        d.last_cmd = "sha256sum of the source image after the rewrite"
        d.assert_not_equal(
            self.src_sha, self.incr_sha, "control: the rewrite really changed the source image"
        )

        doc = r.snapshot(self.src)
        d.last_cmd = "renet backup snapshot (incremental)"
        d.assert_equal(
            "stored", str(doc.get("status", "")), "renet stores the incremental snapshot"
        )
        self.incr_uploaded = uploaded(doc)
        d.assert_equal(
            str(cell_bytes),
            str(self.incr_uploaded),
            "exactly one cell transferred, not another whole image",
        )
        snap = str(doc.get("snapshotId", ""))
        d.assert_equal(
            f"{snap},{self.b.snap_seed}",
            ",".join(self.b.lineage_snapshots(self.src)),
            "the index lists the incremental snapshot over the seed, newest first",
        )
        d.assert_equal(
            str(self.seed_uploaded + self.incr_uploaded),
            str(self.b.stored_bytes()),
            "and the ledger grew by that one cell",
        )
        self.b.snap_incr = snap
        self.b.incr_sha = self.incr_sha

    # ------------------------------------------------------------------ leg d

    def leg_d(self) -> None:
        d, r = self.d, self.rt
        d.step("Leg d (renet): both snapshots restore byte-identically by `renet backup restore`")
        d.last_cmd = "the two source digests"
        d.assert_not_equal(
            self.src_sha,
            self.incr_sha,
            "control: the two snapshots hold different images (a compare of identical inputs proves nothing)",
        )
        for label, snap, want in (
            ("seed", self.b.snap_seed, self.src_sha),
            ("incremental", self.b.snap_incr, self.incr_sha),
        ):
            target = str(uuid.uuid4())
            r.created.append(target)
            # The restore target needs a licence of its own: without one the first installed licence is used, which may be another subscription's.
            r.issue_license(target, self.src, "fork")
            doc = r.restore(target, self.src, snap)
            d.last_cmd = "renet backup restore (%s)" % label
            d.assert_equal(
                "restored", str(doc.get("status", "")), "the %s snapshot restores" % label
            )
            d.last_cmd = "sha256sum of the restored %s image" % label
            d.assert_equal(
                want,
                r.image_digest(target),
                "and the %s restore is byte-identical to the source image cut with it" % label,
            )

    # ------------------------------------------------------------------ leg p

    def refused_swap(self, baseline: str, desc: str) -> None:
        """One snapshot of the swapped image: refused by name, nothing uploaded, nothing listed, nothing billed."""
        d, r = self.d, self.rt
        listed = self.b.lineage_snapshots(self.src)
        stored = self.b.stored_bytes()
        doc = r.snapshot(self.src)
        d.last_cmd = "renet backup snapshot (%s)" % desc
        d.assert_equal("identity-changed", str(doc.get("status", "")), "%s is refused" % desc)
        self.b.av(baseline in str(doc.get("reason", "")), True, "by the %s" % baseline)
        d.assert_equal("0", str(uploaded(doc)), "with nothing uploaded")
        d.assert_equal(
            ",".join(listed),
            ",".join(self.b.lineage_snapshots(self.src)),
            "and no snapshot listed",
        )
        d.assert_equal(str(stored), str(self.b.stored_bytes()), "and nothing billed")

    def leg_p(self) -> None:
        d, r = self.d, self.rt
        d.step("Leg p (renet): a swapped image and a wrong passphrase, on real renet")
        try:
            # Inside the try: a swap that fails after its mv leaves the original at the aside name, and only the finally puts it back.
            r.run_vm(swap_image_command(r.datastore, self.src))
            self.refused_swap("journal-anchor", "a replaced image")
            # The server's previous row is what survives a lost journal; without it this run would be a new baseline.
            r.run_vm(journal_aside_command(self.src))
            try:
                self.refused_swap("server-previous", "a replaced image with the journal lost")
            finally:
                r.run_vm(journal_back_command(self.src))
        finally:
            r.run_vm(unswap_image_command(r.datastore, self.src))

        # CONTROL: the original image under the same name is stored again, so the refusals were the image.
        doc = r.snapshot(self.src)
        d.last_cmd = "renet backup snapshot (the original image)"
        d.assert_equal("stored", str(doc.get("status", "")), "CONTROL: the original image stores")

        target = str(uuid.uuid4())
        r.created.append(target)
        r.issue_license(target, self.src, "fork")
        passphrase = r.passphrase()
        refused = r.restore(target, self.src, self.b.snap_seed, "not-" + passphrase)
        d.last_cmd = "renet backup restore (wrong passphrase)"
        d.assert_equal(
            "refused",
            str(refused.get("passphraseCheck", "")),
            "a wrong passphrase is refused by the test-open",
        )
        d.assert_not_equal(
            "restored", str(refused.get("status", "")), "and the restore does not report success"
        )
        self.b.av(r.image_present(target), False, "and places nothing at the target")

        doc = r.restore(target, self.src, self.b.snap_seed, passphrase)
        d.last_cmd = "renet backup restore (the right passphrase)"
        d.assert_equal(
            "restored", str(doc.get("status", "")), "CONTROL: the right passphrase restores"
        )
        d.assert_equal("opened", str(doc.get("passphraseCheck", "")), "and says the image opened")
        d.last_cmd = "sha256sum of the image restored with the passphrase"
        d.assert_equal(self.src_sha, r.image_digest(target), "byte-identically")

    # ------------------------------------------------------------------ leg r

    def leg_r(self) -> None:
        d, r = self.d, self.rt
        d.step("Leg r (renet): `renet backup repair` puts a deleted chunk back from the anchor")
        self.b.release_probe_leases()
        token = self.b.mint_restore_session() and self.b.restore_session_token
        digest = self.b.a_seed_digest(token) if token else ""
        d.last_cmd = "read a chunk hash of the seed manifest"
        d.assert_not_equal("", digest, "the seed snapshot names a chunk")
        cell_bytes = int(r.cell_bytes)
        d.assert_equal(
            "200",
            self.b.s3_put(self.b.chunk_url(self.src, digest), b"\xff" * cell_bytes),
            "that chunk is overwritten in the store",
        )
        text = self.b.repair(self.src, [digest], False)
        self.b.capture("POST /backups/chunks/repair (renet's lineage)", text)
        d.assert_equal("200", self.b.status, "the repair route answers")
        self.b.av(self.b.field("deleted"), [digest], "and deletes it")

        doc = r._json_result(
            r.run_vm(repair_command(r.datastore, self.src), digest + "\n", must=False)
        )
        d.last_cmd = "renet backup repair"
        d.assert_equal("repaired", str(doc.get("status", "")), "renet puts it back from the anchor")
        self.b.av(doc.get("uploaded"), [digest], "and names it")

        # A lease renet left behind would answer 409 here.
        text = self.b.repair(self.src, [digest], True)
        self.b.capture("POST /backups/chunks/repair (dry run, after renet's repair)", text)
        d.assert_equal("200", self.b.status, "renet released its lease, so a repair is admitted")
        self.b.av(self.b.field("stillGood"), [digest], "and the object is sound now")
        clean = self.b.store_pass(self.src)
        self.b.av(
            [clean["missing"], clean["corrupt"]],
            [[], []],
            "the store pass over the lineage is clean",
        )

        # CONTROL: the verb does not claim what it cannot do.
        result = r.run_vm(repair_command(r.datastore, self.src), UNHELD_HASH + "\n", must=False)
        doc = r._json_result(result)
        d.last_cmd = "renet backup repair (a hash no anchor holds)"
        d.assert_not_equal(
            "0", str(result.returncode), "CONTROL: a hash no anchor holds exits non-zero"
        )
        self.b.av(
            [str(x.get("hash")) for x in (doc.get("unrepairable") or [])],
            [UNHELD_HASH],
            "and is named as unrepairable",
        )

    # ------------------------------------------------------------------ leg t

    def set_session_ttl(self, ms: int | None) -> None:
        """Moves the dev gateway's session lifetime through its `/test/backup/session-ttl` seam (private/account setBackupSessionTtlForTest); None restores the 1 h constant."""
        text = self.b.api(
            "POST",
            "%s/test/backup/session-ttl" % self.d.api_base(),
            {"ms": ms},
        )
        self.b.capture("POST /test/backup/session-ttl (%s)" % ms, text)
        self.d.assert_equal("200", self.b.status, "the TTL seam answers (dev gateway only)")

    def leg_t(self) -> None:
        """A real renet snapshot crosses two session expiries and still commits, one cell moved and the ledger exact."""
        d, r = self.d, self.rt
        d.step("Leg t (renet): a snapshot that outlives two sessions re-mints and still commits")
        cell_bytes = int(r.cell_bytes)
        ttl_ms = SESSION_TTL_DRILL_MS
        # One cell at cell_bytes / TRICKLE_SECONDS bytes a second takes TRICKLE_SECONDS, which is over two lifetimes.
        trickle = max(cell_bytes // TRICKLE_SECONDS, 1)
        r.run_vm(mutation_command(r.datastore, self.src, cell_bytes))
        before = self.b.stored_bytes()
        try:
            self.set_session_ttl(ttl_ms)
            doc = r._json_result(
                r.run_vm(
                    "sudo -n renet backup snapshot --datastore %s --repo %s --cell-bytes %s --bwlimit %d"
                    % (r.datastore, self.src, r.cell_bytes, trickle),
                    must=False,
                )
            )
        finally:
            self.set_session_ttl(None)
        d.last_cmd = "renet backup snapshot (trickle over two session lifetimes)"
        d.assert_equal("stored", str(doc.get("status", "")), "the snapshot still commits")
        duration_ms = int(doc.get("durationMs") or 0)
        d.assert_equal(
            "True",
            str(duration_ms >= 2 * ttl_ms),
            "CONTROL: the run lasted at least two session lifetimes (%d ms vs %d ms each)"
            % (duration_ms, ttl_ms),
        )
        d.assert_equal(
            str(before + cell_bytes),
            str(self.b.stored_bytes()),
            "and the ledger grew by exactly the one cell",
        )

    # ------------------------------------------------------------------ leg u

    def leg_u(self) -> None:
        """A killed run, then a rerun, leaves the ledger reconciled against the store."""
        d, r = self.d, self.rt
        d.step(
            "Leg u (renet): a killed snapshot and its rerun leave `backup reconcile --check` clean"
        )
        cell_bytes = int(r.cell_bytes)
        r.run_vm(mutation_command(r.datastore, self.src, cell_bytes))
        slow = max(cell_bytes // (4 * KILL_AFTER_SECONDS), 1)
        killed = r.run_vm(
            "sudo -n timeout -s KILL %d renet backup snapshot --datastore %s --repo %s --cell-bytes %s --bwlimit %d"
            % (KILL_AFTER_SECONDS, r.datastore, self.src, r.cell_bytes, slow),
            must=False,
        )
        d.last_cmd = "renet backup snapshot killed after %d s" % KILL_AFTER_SECONDS
        d.assert_not_equal("0", str(killed.returncode), "the first run was killed before it ended")
        doc = r.snapshot(self.src)
        d.last_cmd = "renet backup snapshot (rerun)"
        d.assert_equal("stored", str(doc.get("status", "")), "the rerun stores the snapshot")
        self.b.release_probe_leases()
        text = self.b.api(
            "POST",
            "%s/reconcile" % self.b.backup_api(),
            {"lineageGuid": self.src, "dryRun": True},
            {"Authorization": "Bearer %s" % self.b.manage_token()},
        )
        self.b.capture(
            "POST /backups/reconcile (dry run: the wire of `rdc backup reconcile --check`)", text
        )
        d.assert_equal("200", self.b.status, "the reconcile route answers")
        lineages = self.b.field("lineages")
        judged = [
            row
            for row in (lineages if isinstance(lineages, list) else [])
            if isinstance(row, dict) and not row.get("skipped")
        ]
        d.assert_not_equal("0", str(len(judged)), "the lineage was judged, not skipped")
        drifted = [
            str(row.get("lineageGuid"))
            for row in judged
            if row.get("observedBytes") != row.get("ledgerBytesBefore")
            or row.get("observedChunks") != row.get("ledgerChunksBefore")
        ]
        d.assert_equal("[]", str(drifted), "no judged lineage drifted: --check would exit 0")

    def teardown(self) -> None:
        self.rt.teardown()


def build(
    backup: Any,
    *,
    user: str,
    key: str,
    vm_host: str,
    bridge: str,
    port: str,
    work: pathlib.Path,
    vm: Callable[[str, str | None], rt.VmResult] | None = None,
    say: Callable[[str], None] | None = None,
) -> RenetLegs:
    """The real wiring: ssh to the worker, this drill's gateway through the bridge address, this drill's token. `vm` replaces the ssh transport in tests."""
    api = rt.Api("http://%s:%s" % (bridge, port))
    api.token = backup.api_token

    def ssh(command: str, stdin_data: str | None = None) -> rt.VmResult:
        return rt.ssh_vm(user, key, vm_host, command, stdin_data)

    roundtrip = rt.Roundtrip(vm or ssh, api, work, say=say)
    return RenetLegs(backup, roundtrip)
