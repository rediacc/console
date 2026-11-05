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

import base64
import hashlib
import json
import uuid
from typing import TYPE_CHECKING, Any

from rediacc_ci.drills import backup_roundtrip as rt
from rediacc_ci.well_known import RUNTIME_DIR

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


def journal_read_command(guid: str) -> str:
    return "sudo -n sh -c 'cat %s/*-%s.json'" % (JOURNAL_DIR, guid)


def journal_upload_snapshot(journal_text: str) -> str:
    """The snapshot id of the upload a journal holds in flight (`upload.snapshotId`), empty when it holds none or is unreadable."""
    try:
        doc = json.loads(journal_text)
    except ValueError:
        return ""
    upload = doc.get("upload") if isinstance(doc, dict) else None
    value = upload.get("snapshotId") if isinstance(upload, dict) else None
    return value if isinstance(value, str) else ""


def lineage_rows(lineages: object) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """A reconcile answer's lineage rows split into (judged, skipped). A skipped row's observed figures are 0 by construction, a skip marker and not a count."""
    rows = [
        row for row in (lineages if isinstance(lineages, list) else []) if isinstance(row, dict)
    ]
    return [r for r in rows if not r.get("skipped")], [r for r in rows if r.get("skipped")]


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


# Leg v: the hook drill's repository (own network id, beside leg b's source), its container, and the bounds. The deadman fires 2 x timeout + 30 s after the hook arms.
HOOK_NET_ID = "2944"
HOOK_TIMEOUT_SECONDS = 5
HOOK_DEADMAN_SECONDS = 2 * HOOK_TIMEOUT_SECONDS + 30
HOOK_WAIT_SECONDS = HOOK_DEADMAN_SECONDS + 60
HOOK_MARKER_DIR = "/run/rediacc/backup-hook"
HOOK_LOG = "hook-log"
HOOK_CONTAINER = "db"
# A prepare that holds the application and then hangs past any timeout; the sleep's odd length names it for the cleanup.
HOOK_HANG_SECONDS = 97
# Leg w: the tier cadence, and how many runs the rolling sample may take to reach the deleted chunk (16 chunks per run).
HEAL_TARGET = "5m"
HEAL_MAX_RUNS = 80
# Leg x: how many runs the chain holds, and the run restored (1-based).
RUN_CHAIN = 3
RUN_RESTORED = 2
REFLINK_SUFFIX = ".drill-run"


def hook_compose() -> str:
    """The drill's database stand-in: a container that appends a row every 200 ms unless `/data/frozen` exists, so a held application is visible as a row count that stops."""
    return (
        "services:\n"
        "  db:\n"
        "    image: busybox:1.36\n"
        "    container_name: %s\n"
        "    command:\n"
        '      - sh\n      - -c\n      - "mkdir -p /data; i=0; while true; do [ -f /data/frozen ] || echo $$i >> /data/rows; i=$$((i+1)); sleep 0.2; done"\n'
        % HOOK_CONTAINER
    )


def hook_rediaccfile(hang: bool, hooks: bool = True) -> str:
    """The drill's Rediaccfile. `hooks` False leaves `backup_prepare` and `backup_finish` out (the control: a run without them is crash-consistent). `hang` makes `backup_prepare` hold the application and then sleep past its timeout, the state a SIGKILLed renet leaves behind."""
    text = "#!/bin/bash\nup() { renet compose -- up -d; }\ndown() { renet compose -- down; }\n"
    if not hooks:
        return text
    hang_line = "  sleep %d\n" % HOOK_HANG_SECONDS if hang else ""
    return (
        text
        + "backup_prepare() {\n"
        + '  echo "prepare $(date +%%s%%N)" >> "$REDIACC_WORKING_DIR/%s"\n' % HOOK_LOG
        + "  docker exec %s touch /data/frozen\n" % HOOK_CONTAINER
        + hang_line
        + "}\n"
        + "backup_finish() {\n"
        + "  docker exec %s rm -f /data/frozen\n" % HOOK_CONTAINER
        + '  echo "finish $(date +%%s%%N)" >> "$REDIACC_WORKING_DIR/%s"\n' % HOOK_LOG
        + "}\n"
    )


def install_hook_files_command(datastore: str, guid: str, rediaccfile: str, compose: str) -> str:
    """Root on the worker: the Rediaccfile and compose file written into the repository's mount through base64, and a world-writable hook log (the hook runs as the repository's own user, not root)."""
    rf = base64.b64encode(rediaccfile.encode()).decode()
    dc = base64.b64encode(compose.encode()).decode()
    mount = "%s/mounts/%s" % (datastore, guid)
    return (
        "sudo -n sh -c 'printf %%s %(rf)s | base64 -d > %(m)s/Rediaccfile && "
        "printf %%s %(dc)s | base64 -d > %(m)s/docker-compose.yml && chmod 644 %(m)s/Rediaccfile %(m)s/docker-compose.yml && "
        ": > %(m)s/%(log)s && chmod 666 %(m)s/%(log)s'"
        % {"rf": rf, "dc": dc, "m": mount, "log": HOOK_LOG}
    )


def docker_exec_command(network_id: str, args: str) -> str:
    """Root on the worker: `docker <args>` against the repository's own daemon socket."""
    sock = "%s/net-%s/docker-%s.sock" % (RUNTIME_DIR, network_id, network_id)
    return "sudo -n env DOCKER_HOST=unix://%s docker %s" % (sock, args)


def hook_log_command(datastore: str, guid: str) -> str:
    return "sudo -n cat %s/mounts/%s/%s" % (datastore, guid, HOOK_LOG)


def hook_log_events(text: str) -> list[str]:
    """The event words of the hook log (`prepare`, `finish`), in the order written."""
    return [line.split()[0] for line in text.splitlines() if line.split()]


def killed_hook_command(datastore: str, guid: str, cell_bytes: str) -> str:
    """Root on the worker: a hot snapshot started in the background with a short hook timeout; its pid is left in a file so the drill can SIGKILL it once the hold marker stands."""
    return (
        "sudo -n sh -c 'nohup renet backup snapshot --datastore %s --repo %s --cell-bytes %s "
        "--hook-timeout %ds > /tmp/hook-kill.out 2>&1 & echo $! > /tmp/hook-kill.pid'"
        % (datastore, guid, cell_bytes, HOOK_TIMEOUT_SECONDS)
    )


def wait_marker_command(guid: str, present: bool, seconds: int) -> str:
    """Root on the worker: poll up to `seconds` for the hold marker to appear (`present`) or to be gone, exit 0 when it does."""
    test = "-e" if present else "! -e"
    return (
        "sudo -n sh -c 'i=0; while [ $i -lt %d ]; do if [ %s %s/%s ]; then exit 0; fi; i=$((i+1)); sleep 1; done; exit 1'"
        % (seconds, test, HOOK_MARKER_DIR, guid)
    )


def kill_pid_command() -> str:
    return "sudo -n sh -c 'kill -9 $(cat /tmp/hook-kill.pid)'"


def hook_cleanup_command(datastore: str, guid: str) -> str:
    """Root on the worker: stop the repository, end any leftover hanging prepare, and remove the drill's temp files. Every step tolerates absence."""
    return (
        'sudo -n sh -c \'renet repository down --name %s --datastore %s; pkill -f "[s]leep %d"; '
        "rm -f /tmp/hook-kill.pid /tmp/hook-kill.out; true'" % (guid, datastore, HOOK_HANG_SECONDS)
    )


def rows_command(network_id: str) -> str:
    return docker_exec_command(network_id, "exec %s wc -l /data/rows" % HOOK_CONTAINER)


def count_of(text: str) -> int:
    """The leading integer of a `wc -l` line, -1 when there is none."""
    words = text.split()
    return int(words[0]) if words and words[0].isdigit() else -1


def snapshot_target_command(datastore: str, guid: str, cell_bytes: str) -> str:
    """A tier-cadence run: `--target` makes an unchanged image commit nothing and sample the store instead."""
    return "sudo -n renet backup snapshot --datastore %s --repo %s --cell-bytes %s --target %s" % (
        datastore,
        guid,
        cell_bytes,
        HEAL_TARGET,
    )


def sample_found_missing(doc: dict[str, Any]) -> bool:
    """True when a run's rolling sample found the lost chunk: the record counts a missing sampled chunk."""
    value = doc.get("chunksSampleMissing")
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def reflink_command(datastore: str, guid: str, run: int) -> str:
    """Root on the worker: a reflink copy of the (unmounted) image, the reference one run's restore is compared with."""
    image = "%s/repositories/%s" % (datastore, guid)
    return "sudo -n sh -c 'sync; cp --reflink=always %s %s%s%d'" % (
        image,
        image,
        REFLINK_SUFFIX,
        run,
    )


def reflink_digest_command(datastore: str, guid: str, run: int) -> str:
    image = "%s/repositories/%s" % (datastore, guid)
    return "sudo -n sha256sum %s%s%d" % (image, REFLINK_SUFFIX, run)


def reflink_remove_command(datastore: str, guid: str) -> str:
    return "sudo -n sh -c 'rm -f %s/repositories/%s%s*'" % (datastore, guid, REFLINK_SUFFIX)


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
        killed_snapshot = journal_upload_snapshot(
            r.run_vm(journal_read_command(self.src), must=False).stdout
        )
        d.last_cmd = "the journal of the killed run"
        d.assert_not_equal("", killed_snapshot, "the killed run left an upload in its journal")
        doc = r.snapshot(self.src)
        d.last_cmd = "renet backup snapshot (rerun)"
        d.assert_equal("stored", str(doc.get("status", "")), "the rerun stores the snapshot")
        self.b.release_probe_leases()
        # The killed run's lease is the server's evidence that the run may still be alive: a rerun on the same machine inside the staleness window keeps it, and a live lease makes reconcile skip its lineage.
        judged, skipped = self.reconcile_dry_run()
        d.assert_equal(
            "leased",
            ",".join(str(row.get("skipped")) for row in skipped),
            "CONTROL: while the killed run's lease lives the lineage is skipped, not judged",
        )
        d.assert_equal("[]", str(judged), "and a skipped lineage is not counted as judged")
        self.expire_killed_lease(killed_snapshot)
        judged, _ = self.reconcile_dry_run()
        d.assert_not_equal("0", str(len(judged)), "the lineage was judged, not skipped")
        drifted = [
            str(row.get("lineageGuid"))
            for row in judged
            if row.get("observedBytes") != row.get("ledgerBytesBefore")
            or row.get("observedChunks") != row.get("ledgerChunksBefore")
        ]
        d.assert_equal("[]", str(drifted), "no judged lineage drifted: --check would exit 0")

    def reconcile_dry_run(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """POST /backups/reconcile as a dry run on the source lineage: the wire of `rdc backup reconcile --check`. Returns (judged, skipped) rows."""
        text = self.b.api(
            "POST",
            "%s/reconcile" % self.b.backup_api(),
            {"lineageGuid": self.src, "dryRun": True},
            {"Authorization": "Bearer %s" % self.b.manage_token()},
        )
        self.b.capture(
            "POST /backups/reconcile (dry run: the wire of `rdc backup reconcile --check`)", text
        )
        self.d.assert_equal("200", self.b.status, "the reconcile route answers")
        return lineage_rows(self.b.field("lineages"))

    def expire_killed_lease(self, snapshot_id: str) -> None:
        """Backdates the killed run's lease through the dev gateway's `/test/expire-lease` seam, the stand-in for waiting out its two-hour lifetime."""
        text = self.b.api(
            "POST",
            "%s/test/expire-lease" % self.d.api_base(),
            {"subscriptionId": self.b.subscription_id, "snapshotId": snapshot_id},
        )
        self.b.capture("POST /test/expire-lease (the killed run's snapshot)", text)
        self.d.assert_equal("200", self.b.status, "the lease seam answers (dev gateway only)")

    # ------------------------------------------------------------------ leg v

    def leg_v(self) -> None:
        """Hook order on a real repository with a running container, and a killed renet thawed by the deadman."""
        d, r = self.d, self.rt
        d.step("Leg v (renet): backup_prepare and backup_finish around the freeze, and the deadman")
        guid = str(uuid.uuid4())
        r.created.append(guid)
        saved_net = r.net_src
        r.net_src = HOOK_NET_ID
        try:
            r.issue_license(guid, guid, "grand")
            r.create_source(guid)
        finally:
            r.net_src = saved_net
        ds, nid = r.datastore, HOOK_NET_ID
        try:
            r.run_vm(install_hook_files_command(ds, guid, hook_rediaccfile(False), hook_compose()))
            r.run_vm(
                "sudo -n renet repository up --name %s --network-id %s --datastore %s"
                % (guid, nid, ds)
            )
            d.last_cmd = "docker exec db (the container runs)"
            before = count_of(r.run_vm(rows_command(nid), must=False).stdout)
            d.assert_not_equal("-1", str(before), "the database container is running and writing")

            # Order: one prepare, then one finish, and the copy says app-quiesced.
            doc = self.hook_snapshot(guid)
            d.assert_equal("stored", str(doc.get("status", "")), "the hooked snapshot stores")
            raw_hook = doc.get("hook")
            hook = raw_hook if isinstance(raw_hook, dict) else {}
            d.assert_equal("ok", str(hook.get("prepare", "")), "backup_prepare ran and succeeded")
            d.assert_equal("ok", str(hook.get("finish", "")), "backup_finish ran and succeeded")
            d.assert_equal(
                "app-quiesced", str(doc.get("consistency", "")), "and the copy claims app-quiesced"
            )
            d.last_cmd = "the hook log of the mount"
            log = hook_log_events(r.run_vm(hook_log_command(ds, guid)).stdout)
            d.assert_equal(
                "prepare,finish", ",".join(log), "the hooks ran once each, prepare first"
            )

            # CONTROL: without the two functions the same repository is crash-consistent, so the claim above was the hook.
            r.run_vm(
                install_hook_files_command(
                    ds, guid, hook_rediaccfile(False, hooks=False), hook_compose()
                )
            )
            control = self.hook_snapshot(guid)
            self.b.av(
                control.get("consistency") != "app-quiesced",
                True,
                "CONTROL: a repository with no hook is not claimed app-quiesced",
            )

            # The deadman: prepare holds the application, renet is SIGKILLed, and the timer thaws it.
            r.run_vm(install_hook_files_command(ds, guid, hook_rediaccfile(True), hook_compose()))
            r.run_vm(killed_hook_command(ds, guid, r.cell_bytes))
            armed = r.run_vm(wait_marker_command(guid, True, 60), must=False)
            d.last_cmd = "the hold marker under %s" % HOOK_MARKER_DIR
            d.assert_equal(
                "0", str(armed.returncode), "the run held the application (marker stands)"
            )
            r.run_vm(kill_pid_command())
            held = r.run_vm(
                docker_exec_command(nid, "exec %s test -f /data/frozen" % HOOK_CONTAINER),
                must=False,
            )
            d.last_cmd = "docker exec db test -f /data/frozen"
            d.assert_equal(
                "0",
                str(held.returncode),
                "CONTROL: right after the kill the application is still held",
            )
            frozen_rows = count_of(r.run_vm(rows_command(nid), must=False).stdout)
            thawed = r.run_vm(wait_marker_command(guid, False, HOOK_WAIT_SECONDS), must=False)
            d.last_cmd = "the hold marker after the deadman delay (%d s)" % HOOK_DEADMAN_SECONDS
            d.assert_equal(
                "0", str(thawed.returncode), "the deadman ended the hold within its bound"
            )
            free = r.run_vm(
                docker_exec_command(nid, "exec %s test ! -f /data/frozen" % HOOK_CONTAINER),
                must=False,
            )
            d.assert_equal("0", str(free.returncode), "and the application is thawed")
            after = count_of(r.run_vm(rows_command(nid), must=False).stdout)
            self.b.av(after > frozen_rows >= 0, True, "and its writes resumed")
            log = hook_log_events(r.run_vm(hook_log_command(ds, guid)).stdout)
            d.assert_equal(
                "finish", log[-1] if log else "", "backup_finish ran last, from the timer"
            )
        finally:
            r.run_vm(hook_cleanup_command(ds, guid), must=False)

    def hook_snapshot(self, guid: str) -> dict[str, Any]:
        r = self.rt
        return r._json_result(
            r.run_vm(
                "sudo -n renet backup snapshot --datastore %s --repo %s --cell-bytes %s --hook-timeout %ds"
                % (r.datastore, guid, r.cell_bytes, HOOK_TIMEOUT_SECONDS),
                must=False,
            )
        )

    # ------------------------------------------------------------------ leg w

    def leg_w(self) -> None:
        """Tier-cadence runs over an idle repository: a chunk deleted from the store is found by the rolling sample and put back."""
        d, r = self.d, self.rt
        d.step("Leg w (renet): a chunk lost from the store is healed by the rolling sample")
        self.b.release_probe_leases()
        token = self.b.mint_restore_session() and self.b.restore_session_token
        digest = self.b.a_seed_digest(token) if token else ""
        d.last_cmd = "read a chunk hash of the seed manifest"
        d.assert_not_equal("", digest, "the seed snapshot names a chunk")
        url = self.b.chunk_url(self.src, digest)
        # An image no cell of which changed since the last commit, so a target run is idle.
        first = r._json_result(
            r.run_vm(snapshot_target_command(r.datastore, self.src, r.cell_bytes), must=False)
        )
        d.last_cmd = "renet backup snapshot --target (idle)"
        d.assert_equal("unchanged", str(first.get("status", "")), "an idle run commits nothing")
        self.b.av(int(first.get("chunksSampled") or 0) > 0, True, "and samples chunks of the store")

        code, _ = self.b.s3_get(url)
        d.assert_equal("200", str(code), "the chunk is in the store before the loss")
        d.assert_equal("204", self.b.s3_delete(url), "the chunk is deleted from the store")
        gone, _ = self.b.s3_get(url)
        d.assert_equal("404", str(gone), "and the store no longer holds it")

        found: dict[str, Any] = {}
        idle_runs = 0
        for _ in range(HEAL_MAX_RUNS):
            doc = r._json_result(
                r.run_vm(snapshot_target_command(r.datastore, self.src, r.cell_bytes), must=False)
            )
            if sample_found_missing(doc):
                found = doc
                break
            # CONTROL, each run before the find: nothing uploaded, nothing committed.
            self.b.av(
                [str(doc.get("status", "")), uploaded(doc)],
                ["unchanged", 0],
                "run %d before the find is idle and uploads nothing" % (idle_runs + 1),
            )
            idle_runs += 1
        d.last_cmd = "renet backup snapshot --target x%d" % (idle_runs + 1)
        self.b.av(
            bool(found),
            True,
            "the rolling sample reached the lost chunk within %d runs" % HEAL_MAX_RUNS,
        )
        d.assert_equal(
            "stored", str(found.get("status", "")), "the finding run stores a full snapshot"
        )
        self.b.av(uploaded(found) >= int(r.cell_bytes), True, "and uploads the missing chunk")
        healed, body = self.b.s3_get(url)
        d.assert_equal("200", str(healed), "the chunk is back in the store")
        d.assert_equal(
            hashlib.sha256(body).hexdigest(),
            digest,
            "and its bytes hash to the name it was lost under",
        )

    # ------------------------------------------------------------------ leg x

    def leg_x(self) -> None:
        """A restore at a chosen run of a chain equals that run's reflink, whole image."""
        d, r = self.d, self.rt
        d.step("Leg x (renet): a restore at a chosen run equals that run's reflink, byte for byte")
        ds, src = r.datastore, self.src
        snaps: list[str] = []
        try:
            for run in range(1, RUN_CHAIN + 1):
                r.run_vm(mutation_command(ds, src, int(r.cell_bytes)))
                doc = r.snapshot(src)
                d.last_cmd = "renet backup snapshot (run %d)" % run
                d.assert_equal("stored", str(doc.get("status", "")), "run %d stores" % run)
                snaps.append(str(doc.get("snapshotId", "")))
                # The reflink is cut right after the run, before the next rewrite, so it is that run's image.
                r.run_vm(reflink_command(ds, src, run))
            digests = [
                r.run_vm(reflink_digest_command(ds, src, run)).stdout.split()[0]
                for run in range(1, RUN_CHAIN + 1)
            ]
            d.assert_equal(
                str(RUN_CHAIN),
                str(len(set(digests))),
                "CONTROL: every run's image differs from the others",
            )
            live = r.image_digest(src, quiesce=True)
            d.assert_not_equal(
                digests[RUN_RESTORED - 1],
                live,
                "CONTROL: the chosen run is not the live image, so a restore of the latest cannot pass",
            )
            target = str(uuid.uuid4())
            r.created.append(target)
            r.issue_license(target, src, "fork")
            doc = r.restore(target, src, snaps[RUN_RESTORED - 1])
            d.last_cmd = "renet backup restore (run %d)" % RUN_RESTORED
            d.assert_equal("restored", str(doc.get("status", "")), "the chosen run restores")
            d.assert_equal(
                digests[RUN_RESTORED - 1],
                r.image_digest(target),
                "and the restored image equals that run's reflink",
            )
        finally:
            r.run_vm(reflink_remove_command(ds, src), must=False)

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
