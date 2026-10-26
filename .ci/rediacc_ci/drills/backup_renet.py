"""Legs b, c and d of `rediacc_ci.drills.backup` with REAL renet in the loop (`--renet`).

WHAT CHANGES. The host-only legs build their own cells in Python and talk to the control plane as a stand-in for a machine. With `--renet` the same three claims are proven by a machine: a real repository on the worker VM (LUKS image on btrfs, a licence issued by this run's own gateway) is snapshotted by `renet backup snapshot`, one cell of its image is rewritten and it is snapshotted again, and both snapshots are restored by `renet backup restore` into DIFFERENT repositories whose images are compared byte for byte with the source's. The proofs are the legs' own:

  b  the seed snapshot is stored, the manifest index lists it, and the quota ledger moved by exactly the bytes renet reports uploading.
  c  one rewritten cell transfers exactly one cell (`bytesUploaded == CELL_BYTES`), the ledger grew by that one cell, and the delta lists the seed as its parent.
  d  both snapshots restore into a fresh repository, and each restored image's sha256 equals the digest of the source image taken when that snapshot was cut. Control: the two digests differ, so identical inputs cannot pass.

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


def mutation_command(datastore: str, guid: str, cell_bytes: int) -> str:
    """The shell that rewrites `MUTATION_BYTES` of cell `MUTATION_CELL` of the (unmounted) source image in place, so exactly that cell's hash changes."""
    offset = MUTATION_CELL * cell_bytes + MUTATION_OFFSET_IN_CELL
    return (
        "sudo -n sh -c 'head -c %d /dev/urandom | dd of=%s/repositories/%s bs=1 seek=%d "
        "conv=notrunc status=none && sync'" % (MUTATION_BYTES, datastore, guid, offset)
    )


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
