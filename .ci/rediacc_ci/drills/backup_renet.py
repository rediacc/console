"""Legs b, c and d of `rediacc_ci.drills.backup` with REAL renet in the loop (`--renet`).

WHAT CHANGES. The host-only legs build their own cells in Python and talk to the control plane as a stand-in for a machine. With `--renet` the same three claims are proven by a machine: a real repository on the worker VM (LUKS image on btrfs, a licence issued by this run's own gateway) is snapshotted by `renet backup snapshot`, one cell of its image is rewritten and it is snapshotted again, and both snapshots are restored by `renet backup restore` into DIFFERENT repositories whose images are compared byte for byte with the source's. The proofs are the legs' own:

  b  the seed snapshot is stored, the manifest index lists it, and the quota ledger moved by exactly the bytes renet reports uploading.
  c  one rewritten cell transfers exactly one cell (`bytesUploaded == CELL_BYTES`), the ledger grew by that one cell, and the delta lists the seed as its parent.
  d  both snapshots restore into a fresh repository, and each restored image's sha256 equals the digest of the source image taken when that snapshot was cut. Control: the two digests differ, so identical inputs cannot pass.
  p  a swapped image is refused with nothing uploaded, by the journal and, with the journal gone, by the server's previous row; a wrong passphrase places nothing. Controls: the original image stores again, and the right passphrase restores it byte for byte. Then, on a repository of its own, a wrong-password mount of the mounted repository leaves its TOC key as it was. Controls: with the key moved aside the wrong password installs nothing and the right one installs the same key.
  r  a chunk overwritten in the store is deleted by the account's repair route and put back by `renet backup repair` from the anchor, the lease is released, and the store pass is clean. Control: a hash no anchor holds is named as unrepairable, and the verb exits non-zero. Then spot and deep verify, under the backup_verify function's prefix, run in a transient scope whose cpu.max is one core. Control: the same deep run without the prefix is in no transient scope.
  w  (opt-in) tier-cadence runs heal a chunk lost from the store; then a run past its `--deadline` ends `deadline-exceeded` at that deadline with nothing committed and nothing left alive, two repositories take the machine's slot in turn with the wait recorded, and a systemd unit at a 1-minute target fires twice about a minute apart. Controls: a rerun with time to spare stores, a slot held from outside skips a run at its deadline, and the unit runs nothing before its timer.

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


# Leg p's TOC half (integrity box P1): its own repository, so the source's key and passphrase stay as legs b-d left them.
TOC_NET_ID = "3072"


def toc_status_command(datastore: str, guid: str) -> str:
    return "sudo -n renet backup toc-key status --datastore %s --repo %s" % (datastore, guid)


def mount_password_command(datastore: str, guid: str) -> str:
    """Mount with the password on stdin: on an already-mounted repository this proves no password, which is the case the TOC key must survive."""
    return "sudo -n renet repository mount --name %s --datastore %s --password-stdin" % (
        guid,
        datastore,
    )


def toc_key_path(datastore: str, guid: str) -> str:
    """renet's credentials.TOCPublicKeyPath."""
    return "%s/.credentials/toc/%s.pub" % (datastore, guid)


def toc_aside_command(datastore: str, guid: str) -> str:
    path = toc_key_path(datastore, guid)
    return "sudo -n mv %s %s%s" % (path, path, IMAGE_ASIDE)


def toc_back_command(datastore: str, guid: str) -> str:
    """Puts the moved key back unless a key stands under the name again. Tolerates absence."""
    path = toc_key_path(datastore, guid)
    return (
        "sudo -n sh -c 'if [ -e %(p)s%(a)s ]; then if [ -e %(p)s ]; then rm -f %(p)s%(a)s; else mv %(p)s%(a)s %(p)s; fi; fi'"
        % {
            "p": path,
            "a": IMAGE_ASIDE,
        }
    )


# Leg r's scope half (integrity box P1): the prefix `backgroundReadPrefix` (private/renet/pkg/functions/commands/backup.go) puts in front of `renet backup verify` on a systemd machine: a snapshot's priority and one core.
VERIFY_SCOPE_PREFIX = "nice -n 10 ionice -c 2 -n 7 systemd-run --scope --quiet -p CPUQuota=100%"
# cgroup v2's cpu.max for CPUQuota=100% at systemd's default period: one core.
ONE_CORE_CPU_MAX = "100000 100000"
# The full level's read cap in the drill, so the deep run lives long enough to be looked at (bytes a second).
DEEP_READ_BWLIMIT = 1048576


def verify_probe_command(datastore: str, guid: str, level: str, scoped: bool) -> str:
    """Root on the worker, one ssh call: start `renet backup verify` (inside the function's scope prefix when `scoped`), wait until the process is renet itself (the prefix execs in place), print its cgroup and that cgroup's cpu.max, then wait for it and print its exit code and its record. One call, so the process never outlives the session that started it."""
    prefix = VERIFY_SCOPE_PREFIX + " " if scoped else ""
    cap = " --read-bwlimit %d" % DEEP_READ_BWLIMIT if level == "full" else ""
    return (
        "sudo -n sh -c '%(prefix)srenet backup verify --datastore %(ds)s --repo %(g)s --level %(level)s%(cap)s "
        "> /tmp/verify-probe.out 2>/tmp/verify-probe.err & p=$!; i=0; "
        'while [ $i -lt 200 ]; do [ "$(cat /proc/$p/comm 2>/dev/null)" = renet ] && break; i=$((i+1)); sleep 0.05; done; '
        "c=$(cut -d: -f3 /proc/$p/cgroup 2>/dev/null | tail -n1); "
        'echo "cgroup $c"; echo "cpumax $(cat /sys/fs/cgroup$c/cpu.max 2>/dev/null)"; '
        'wait $p; echo "rc $?"; cat /tmp/verify-probe.out; rm -f /tmp/verify-probe.out /tmp/verify-probe.err\''
        % {"prefix": prefix, "ds": datastore, "g": guid, "level": level, "cap": cap}
    )


def probe_fields(text: str) -> dict[str, Any]:
    """The probe's `cgroup`, `cpumax` and `rc` lines, and the verify record (the first JSON object line). Absent fields are empty, rc -1."""
    out: dict[str, Any] = {"cgroup": "", "cpumax": "", "rc": -1, "record": {}}
    for line in text.splitlines():
        word, _, rest = line.partition(" ")
        if word in ("cgroup", "cpumax") and not out[word]:
            out[word] = rest.strip()
        elif word == "rc" and rest.strip().lstrip("-").isdigit():
            out["rc"] = int(rest.strip())
        elif line.startswith("{") and not out["record"]:
            try:
                doc = json.loads(line)
            except ValueError:
                continue
            if isinstance(doc, dict):
                out["record"] = doc
    return out


def transient_scope(cgroup: str) -> bool:
    """True for a systemd-run transient scope (`.../run-<id>.scope`), false for a login session's scope or anything else."""
    leaf = cgroup.rstrip("/").rsplit("/", 1)[-1]
    return leaf.startswith("run-") and leaf.endswith(".scope")


# Leg w's target half (critical-tier box Y1). The CLI refuses an rpo under 5 minutes (packages/shared/src/backup/duration.ts RPO_MIN_SECONDS), so a 1-minute target exists only as the drill's own unit, rendered as the CLI's generator renders a target unit.
TIER_TARGET = "1m"
TIER_TARGET_SECONDS = 60
TIER_SLOT = "/run/rediacc/backup-tier.lock"
# A run past its deadline: one cell trickled over DEADLINE_TRICKLE_SECONDS against a DEADLINE_SECONDS deadline; it must end within the slack after it.
DEADLINE_SECONDS = 8
DEADLINE_TRICKLE_SECONDS = 40
DEADLINE_SLACK_SECONDS = 30
# Two repositories and one slot: run A trickles one cell for SLOT_HOLD_SECONDS while run B waits; the control holds the slot past B's short deadline.
SLOT_NET_ID = "3008"
SLOT_HOLD_SECONDS = 12
SLOT_DEADLINE = "2m"
SLOT_WAITED_MS = 1000
SLOT_REFUSE_DEADLINE_SECONDS = 3
SLOT_HOLDER_SECONDS = 31
SLOT_WAIT_RUN_SECONDS = 150
# The unit: the CLI's figures for a 60 s target (backup-schedule-unit-generator.ts): deadline clamp(3T, 10 min, 2 h), TimeoutStartSec 2 x deadline + 10 min, RandomizedDelaySec min(T/5, 60 s), OnCalendar from rpoCron(60) through cronToOnCalendar.
UNIT_PREFIX = "rediacc-drill-tier-"
UNIT_DEADLINE = "10m"
UNIT_START_TIMEOUT_SECONDS = 1800
UNIT_JITTER_SECONDS = 12
UNIT_ON_CALENDAR = "*-*-* *:00/1:00"
UNIT_RUNS = 2
UNIT_WAIT_SECONDS = 200
UNIT_GAP_SECONDS = (45, 75)


def target_args(datastore: str, guid: str, cell_bytes: str, deadline: str, bwlimit: int = 0) -> str:
    """`renet backup snapshot` on the drill's target (no sudo: callers run it as root)."""
    limit = " --bwlimit %d" % bwlimit if bwlimit else ""
    return (
        "renet backup snapshot --datastore %s --repo %s --cell-bytes %s --target %s --deadline %s%s"
        % (
            datastore,
            guid,
            cell_bytes,
            TIER_TARGET,
            deadline,
            limit,
        )
    )


def timed_command(args: str) -> str:
    """Root on the worker: `args` with its wall time in whole seconds on stderr (`elapsed N`), its stdout and exit code untouched."""
    return (
        "sudo -n sh -c 's=$(date +%%s); %s; rc=$?; echo \"elapsed $(( $(date +%%s) - s ))\" >&2; exit $rc'"
        % args
    )


def elapsed_of(stderr: str) -> int:
    for line in reversed(stderr.splitlines()):
        words = line.split()
        if len(words) == 2 and words[0] == "elapsed" and words[1].isdigit():
            return int(words[1])
    return -1


def background_command(args: str, tag: str) -> str:
    """Root on the worker: `args` in the background, its stdout and pid under /tmp/tier-<tag>.*."""
    return (
        "sudo -n sh -c 'nohup %s > /tmp/tier-%s.out 2>/tmp/tier-%s.err & echo $! > /tmp/tier-%s.pid'"
        % (args, tag, tag, tag)
    )


def wait_pid_command(tag: str, seconds: int) -> str:
    return (
        "sudo -n sh -c 'i=0; while [ $i -lt %d ]; do kill -0 $(cat /tmp/tier-%s.pid) 2>/dev/null || exit 0; "
        "i=$((i+1)); sleep 1; done; exit 1'" % (seconds, tag)
    )


def read_out_command(tag: str) -> str:
    return "sudo -n cat /tmp/tier-%s.out" % tag


def slot_busy_command(seconds: int) -> str:
    """Root on the worker: poll up to `seconds` until someone holds the machine's slot (a non-blocking flock fails), exit 0 when it does."""
    return (
        "sudo -n sh -c 'i=0; while [ $i -lt %d ]; do flock -n %s true || exit 0; i=$((i+1)); sleep 0.2; done; exit 1'"
        % (seconds * 5, TIER_SLOT)
    )


def hold_slot_command() -> str:
    """Root on the worker: hold the machine's slot in the background for SLOT_HOLDER_SECONDS; -o keeps the lock out of the sleeping child, so ending flock frees it."""
    return "sudo -n sh -c 'nohup flock -o %s sleep %d > /dev/null 2>&1 &'" % (
        TIER_SLOT,
        SLOT_HOLDER_SECONDS,
    )


def tier_cleanup_command() -> str:
    """Root on the worker: end the slot holder and any drill run still alive, and remove the drill's temp files. Every step tolerates absence."""
    return (
        'sudo -n sh -c \'pkill -f "[f]lock -o %s"; pkill -f "[s]leep %d"; '
        'for f in /tmp/tier-*.pid; do [ -e "$f" ] && kill -9 $(cat "$f") 2>/dev/null; done; rm -f /tmp/tier-*; true\''
        % (TIER_SLOT, SLOT_HOLDER_SECONDS)
    )


def snapshot_alive_command(guid: str) -> str:
    """Exit 0 when a `renet backup snapshot` of `guid` is still running on the worker, 1 when none is, 3 when sudo itself is refused."""
    return 'sudo -n true || exit 3; sudo -n pgrep -f "[r]enet backup snapshot .*--repo %s"' % guid


def tier_service_unit(datastore: str, guid: str, cell_bytes: str) -> str:
    """The service of a 1-minute target unit, as the CLI's generateServiceUnit renders a target (licence renewal and the spot verify left out: neither is under test here)."""
    return (
        "[Unit]\nDescription=Rediacc drill tier unit (%(t)s)\nAfter=network-online.target\n\n"
        "[Service]\nType=oneshot\nNice=10\nIOSchedulingClass=best-effort\nIOSchedulingPriority=7\n"
        "TimeoutStartSec=%(timeout)d\nTimeoutStopSec=90\n"
        "ExecStart=/usr/bin/env renet backup snapshot --datastore %(ds)s --repo %(g)s --cell-bytes %(cb)s --target %(t)s --deadline %(dl)s\n"
        % {
            "t": TIER_TARGET,
            "timeout": UNIT_START_TIMEOUT_SECONDS,
            "ds": datastore,
            "g": guid,
            "cb": cell_bytes,
            "dl": UNIT_DEADLINE,
        }
    )


def tier_timer_unit() -> str:
    """The timer of a 1-minute target unit, as the CLI's generateTimerUnit renders a target."""
    return (
        "[Unit]\nDescription=Rediacc drill tier timer (%s)\n\n[Timer]\nOnCalendar=%s\n"
        "RandomizedDelaySec=%ds\nFixedRandomDelay=true\nAccuracySec=1s\nPersistent=true\n"
        % (TIER_TARGET, UNIT_ON_CALENDAR, UNIT_JITTER_SECONDS)
    )


def install_unit_command(name: str, service: str, timer: str) -> str:
    """Root on the worker: both unit files written through base64, systemd reloaded, and the timer started."""
    sv = base64.b64encode(service.encode()).decode()
    tm = base64.b64encode(timer.encode()).decode()
    unit = "/etc/systemd/system/%s" % name
    return (
        "sudo -n sh -c 'printf %%s %(sv)s | base64 -d > %(u)s.service && printf %%s %(tm)s | base64 -d > %(u)s.timer && "
        "systemctl daemon-reload && systemctl start %(n)s.timer'"
        % {"sv": sv, "tm": tm, "u": unit, "n": name}
    )


def unit_journal_command(name: str) -> str:
    return "sudo -n journalctl -u %s.service -o json --no-pager" % name


def wait_unit_runs_command(name: str, guid: str, runs: int, seconds: int) -> str:
    """Root on the worker: poll up to `seconds` until the unit's journal holds `runs` records of `guid`, exit 0 when it does."""
    return (
        'sudo -n sh -c \'i=0; while [ $i -lt %d ]; do n=$(journalctl -u %s.service -o cat --no-pager | grep -c "\\"guid\\":\\"%s\\""); '
        '[ "$n" -ge %d ] && exit 0; i=$((i+1)); sleep 1; done; exit 1\''
        % (seconds, name, guid, runs)
    )


def unit_cleanup_command(name: str) -> str:
    return (
        "sudo -n sh -c 'systemctl stop %(n)s.timer %(n)s.service; rm -f /etc/systemd/system/%(n)s.service "
        "/etc/systemd/system/%(n)s.timer; systemctl daemon-reload; systemctl reset-failed %(n)s.service %(n)s.timer; true'"
        % {"n": name}
    )


def unit_records(text: str, guid: str) -> list[tuple[int, dict[str, Any]]]:
    """(realtime in microseconds, record) for each snapshot record of `guid` in a `journalctl -o json` dump, in journal order."""
    out: list[tuple[int, dict[str, Any]]] = []
    for line in text.splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        message = entry.get("MESSAGE") if isinstance(entry, dict) else None
        if not isinstance(message, str) or not message.startswith("{"):
            continue
        try:
            doc = json.loads(message)
        except ValueError:
            continue
        stamp = str(entry.get("__REALTIME_TIMESTAMP", ""))
        if (
            isinstance(doc, dict)
            and doc.get("guid") == guid
            and "status" in doc
            and stamp.isdigit()
        ):
            out.append((int(stamp), doc))
    return out


def number(doc: dict[str, Any], key: str) -> int:
    """An integer field of a record, -1 when absent or not a number."""
    value = doc.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return -1
    return int(value)


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
        self.toc_key_on_mount()

    def own_repo(self, net_id: str) -> tuple[str, str]:
        """A repository of the leg's own on `net_id`, created mounted with its licence. Returns (guid, passphrase); the source's passphrase file is left as it was."""
        r = self.rt
        guid = str(uuid.uuid4())
        r.created.append(guid)
        luks = r.work / "luks.txt"
        saved = luks.read_text(encoding="utf-8") if luks.exists() else None
        saved_net = r.net_src
        r.net_src = net_id
        try:
            r.issue_license(guid, guid, "grand")
            r.create_source(guid)
            passphrase = r.passphrase()
        finally:
            r.net_src = saved_net
            if saved is not None:
                luks.write_text(saved, encoding="utf-8")
        return guid, passphrase

    def toc_status(self, guid: str) -> dict[str, Any]:
        return self.rt._json_result(
            self.rt.run_vm(toc_status_command(self.rt.datastore, guid), must=False)
        )

    def toc_key_on_mount(self) -> None:
        """Integrity box P1: on real cryptsetup a mount with a wrong password, on a repository that is already mounted, leaves its TOC key as it was. Controls: with the key gone the wrong password installs nothing, and the right one installs the same key again."""
        d, r = self.d, self.rt
        d.step("Leg p (renet): a mounted repository keeps its TOC key through a wrong password")
        guid, passphrase = self.own_repo(TOC_NET_ID)
        ds = r.datastore
        try:
            first = self.toc_status(guid)
            d.last_cmd = "renet backup toc-key status (after create)"
            d.assert_equal(
                "present",
                str(first.get("outcome", "")),
                "creating the repository installed its TOC key",
            )
            key = str(first.get("publicKey", ""))
            d.assert_not_equal("", key, "and the status names the key")

            wrong = r.run_vm(
                mount_password_command(ds, guid), "not-" + passphrase + "\n", must=False
            )
            self.say(
                "a wrong-password mount of the mounted repository exited %d (a mounted repository proves no password)"
                % wrong.returncode
            )
            after = self.toc_status(guid)
            d.last_cmd = "renet backup toc-key status (after a wrong-password mount)"
            d.assert_equal("present", str(after.get("outcome", "")), "the key is still there")
            d.assert_equal(key, str(after.get("publicKey", "")), "and it is the same key")

            # CONTROL: the mount does act on the password. With no key stored, the wrong one writes nothing and the right one writes this very key.
            r.run_vm(toc_aside_command(ds, guid))
            r.run_vm(mount_password_command(ds, guid), "not-" + passphrase + "\n", must=False)
            gone = self.toc_status(guid)
            d.last_cmd = "renet backup toc-key status (key moved aside, wrong-password mount)"
            d.assert_equal(
                "absent",
                str(gone.get("outcome", "")),
                "CONTROL: with the key gone a wrong password installs nothing",
            )
            r.run_vm(mount_password_command(ds, guid), passphrase + "\n", must=False)
            back = self.toc_status(guid)
            d.last_cmd = "renet backup toc-key status (key moved aside, right-password mount)"
            d.assert_equal(
                "present",
                str(back.get("outcome", "")),
                "CONTROL: the right password installs a key",
            )
            d.assert_equal(key, str(back.get("publicKey", "")), "and it is the key it had")
        finally:
            r.run_vm(toc_back_command(ds, guid), must=False)

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
        self.verify_in_scope()

    def verify_in_scope(self) -> None:
        """Integrity box P1: spot and deep verify, under the prefix the backup_verify function builds, run inside a transient scope held to one core, and verify the source. Control: the same deep run without the prefix is in no such scope."""
        d, r = self.d, self.rt
        d.step("Leg r (renet): spot and deep verify run inside a one-core scope")
        checked: dict[str, int] = {}
        for level, label in (("spot", "spot"), ("full", "deep")):
            probe = probe_fields(
                r.run_vm(
                    verify_probe_command(r.datastore, self.src, level, True), must=False
                ).stdout
            )
            rec = probe["record"]
            d.last_cmd = "renet backup verify --level %s (scoped)" % level
            self.say("cgroup %s, cpu.max %s" % (probe["cgroup"], probe["cpumax"]))
            self.b.av(
                transient_scope(probe["cgroup"]),
                True,
                "the %s verify ran inside a transient scope" % label,
            )
            d.assert_equal(ONE_CORE_CPU_MAX, probe["cpumax"], "held to one core")
            d.assert_equal("0", str(probe["rc"]), "the %s verify exits 0" % label)
            d.assert_equal("verified", str(rec.get("status", "")), "and verifies the source")
            d.assert_equal(level, str(rec.get("level", "")), "at the %s level" % level)
            checked[level] = number(rec, "checkedCells")
        self.b.av(
            checked["full"] > checked["spot"] > 0,
            True,
            "the deep pass checked more cells than the spot pass (%d vs %d)"
            % (checked["full"], checked["spot"]),
        )
        control = probe_fields(
            r.run_vm(verify_probe_command(r.datastore, self.src, "full", False), must=False).stdout
        )
        d.last_cmd = "renet backup verify --level full (no prefix)"
        self.say("cgroup %s, cpu.max %s" % (control["cgroup"], control["cpumax"]))
        d.assert_not_equal("", control["cgroup"], "CONTROL: the unprefixed run's cgroup was read")
        self.b.av(
            transient_scope(control["cgroup"]),
            False,
            "CONTROL: without the prefix the same run is in no transient scope",
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
        # CONTROL: before the rerun the killed run's lease is live, so its lineage is skipped as leased; without it the clean read after the rerun could be a run that never leased.
        _, leased = self.reconcile_dry_run()
        d.last_cmd = "reconcile dry run before the rerun"
        self.b.av(
            any(row.get("skipped") == "leased" for row in leased),
            True,
            "CONTROL: before the rerun the killed run's lease lives and its lineage is skipped",
        )
        doc = r.snapshot(self.src)
        d.last_cmd = "renet backup snapshot (rerun)"
        d.assert_equal("stored", str(doc.get("status", "")), "the rerun stores the snapshot")
        self.b.release_probe_leases()
        # The rerun's commit expires every other live lease on its own stream (private/account 1717250, measured on bench 2026-11-05: a kept lease left 53 chunks unbilled), so the lineage is judged at once, with no lease to wait out.
        judged, skipped = self.reconcile_dry_run()
        d.assert_equal(
            "",
            ",".join(str(row.get("skipped")) for row in skipped),
            "the killed run's lease ended with the rerun's commit: nothing is skipped",
        )
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
            # A control snapshot that failed (no status, no consistency field) proves nothing: it must have stored and named a consistency other than app-quiesced.
            self.b.av(
                control.get("status") == "stored"
                and str(control.get("consistency") or "") not in ("", "app-quiesced"),
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
            thawed = r.run_vm(wait_marker_command(guid, False, HOOK_DEADMAN_SECONDS), must=False)
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
        self.target_halves()

    def target_halves(self) -> None:
        """The rest of leg w (critical-tier box Y1): the deadline, the shared slot and the 1-minute unit, in that order, on the source the heal left trusted."""
        try:
            self.tier_deadline()
            self.tier_slot()
            self.tier_unit()
        finally:
            self.rt.run_vm(tier_cleanup_command(), must=False)

    def target_run(
        self, guid: str, deadline: str, bwlimit: int = 0
    ) -> tuple[dict[str, Any], rt.VmResult]:
        r = self.rt
        result = r.run_vm(
            timed_command(target_args(r.datastore, guid, r.cell_bytes, deadline, bwlimit)),
            must=False,
        )
        return r._json_result(result), result

    def tier_deadline(self) -> None:
        """Critical-tier box Y1: a run that cannot finish is ended by renet at its deadline, commits nothing, and leaves the slot free. Control: the same change with time to spare stores."""
        d, r = self.d, self.rt
        d.step("Leg w (renet): a hung target run is killed at its deadline")
        cell_bytes = int(r.cell_bytes)
        r.run_vm(mutation_command(r.datastore, self.src, cell_bytes))
        listed = self.b.lineage_snapshots(self.src)
        trickle = max(cell_bytes // DEADLINE_TRICKLE_SECONDS, 1)
        doc, result = self.target_run(self.src, "%ds" % DEADLINE_SECONDS, trickle)
        elapsed = elapsed_of(result.stderr)
        d.last_cmd = "renet backup snapshot --target %s --deadline %ds (one cell over %d s)" % (
            TIER_TARGET,
            DEADLINE_SECONDS,
            DEADLINE_TRICKLE_SECONDS,
        )
        d.assert_equal(
            "deadline-exceeded", str(doc.get("status", "")), "the run ends deadline-exceeded"
        )
        d.assert_not_equal("0", str(result.returncode), "and exits non-zero")
        self.b.av(doc.get("targetMet") is False, True, "and says the target was not met")
        self.b.av(
            DEADLINE_SECONDS - 1 <= elapsed <= DEADLINE_SECONDS + DEADLINE_SLACK_SECONDS,
            True,
            "it ended at its deadline, not before and not long after (%d s for a %d s deadline)"
            % (elapsed, DEADLINE_SECONDS),
        )
        alive = r.run_vm(snapshot_alive_command(self.src), must=False)
        # pgrep exits 1 for "no match"; a sudo refusal or a pgrep error is another code (or sudo's own 1, which the command's `sudo -n true` guard turns into 3).
        d.assert_equal("1", str(alive.returncode), "no part of the run is left alive")
        d.assert_equal(
            ",".join(listed),
            ",".join(self.b.lineage_snapshots(self.src)),
            "and nothing was committed",
        )
        # CONTROL: the same change with time to spare stores, and finds the slot free.
        again, _ = self.target_run(self.src, UNIT_DEADLINE)
        d.last_cmd = "renet backup snapshot --target %s --deadline %s" % (
            TIER_TARGET,
            UNIT_DEADLINE,
        )
        d.assert_equal(
            "stored", str(again.get("status", "")), "CONTROL: with time to spare it stores"
        )
        self.b.av(
            max(number(again, "slotWaitMs"), 0) < SLOT_WAITED_MS,
            True,
            "and the killed run left the slot free",
        )

    def tier_slot(self) -> None:
        """Critical-tier box Y1: two repositories on one machine take the slot in turn, the second's wait recorded as lateness. Control: a slot held past a short deadline skips the run, bounded by that deadline."""
        d, r = self.d, self.rt
        d.step("Leg w (renet): two repositories share the machine's slot")
        other, _ = self.own_repo(SLOT_NET_ID)
        ds, cell_bytes = r.datastore, int(r.cell_bytes)
        r.run_vm("sudo -n renet repository down --name %s" % other, must=False)
        r.run_vm("sudo -n renet repository unmount --name %s" % other)
        seed = r.snapshot(other)
        d.last_cmd = "renet backup snapshot (the second repository's seed)"
        d.assert_equal("stored", str(seed.get("status", "")), "the second repository is seeded")

        r.run_vm(mutation_command(ds, self.src, cell_bytes))
        r.run_vm(mutation_command(ds, other, cell_bytes))
        slow = max(cell_bytes // SLOT_HOLD_SECONDS, 1)
        r.run_vm(
            background_command(target_args(ds, self.src, r.cell_bytes, SLOT_DEADLINE, slow), "a")
        )
        held = r.run_vm(slot_busy_command(30), must=False)
        d.last_cmd = "flock -n %s" % TIER_SLOT
        d.assert_equal("0", str(held.returncode), "the first repository's run holds the slot")
        second, _ = self.target_run(other, SLOT_DEADLINE)
        d.last_cmd = "renet backup snapshot --target (the second repository, slot busy)"
        d.assert_equal(
            "stored", str(second.get("status", "")), "the second repository's run stores"
        )
        self.b.av(
            number(second, "slotWaitMs") >= SLOT_WAITED_MS,
            True,
            "after waiting for the slot (%d ms recorded)" % number(second, "slotWaitMs"),
        )
        done = r.run_vm(wait_pid_command("a", SLOT_WAIT_RUN_SECONDS), must=False)
        d.assert_equal("0", str(done.returncode), "the first run ended")
        first = r._json_result(r.run_vm(read_out_command("a"), must=False))
        d.last_cmd = "renet backup snapshot --target (the first repository, in the background)"
        d.assert_equal("stored", str(first.get("status", "")), "the first repository's run stored")
        self.b.av(
            max(number(first, "slotWaitMs"), 0) < SLOT_WAITED_MS,
            True,
            "and it had not waited",
        )

        # CONTROL: a slot nobody releases ends the run as skipped at its deadline, not a run that never returns.
        r.run_vm(hold_slot_command())
        try:
            held = r.run_vm(slot_busy_command(30), must=False)
            d.assert_equal("0", str(held.returncode), "CONTROL: the slot is held from outside")
            refused, result = self.target_run(other, "%ds" % SLOT_REFUSE_DEADLINE_SECONDS)
        finally:
            # The holder goes before the unit half, whose runs take the same slot.
            r.run_vm(tier_cleanup_command(), must=False)
        d.last_cmd = (
            "renet backup snapshot --target --deadline %ds (slot held)"
            % SLOT_REFUSE_DEADLINE_SECONDS
        )
        d.assert_equal(
            "skipped",
            str(refused.get("status", "")),
            "CONTROL: a run the slot never frees for is skipped",
        )
        self.b.av(
            number(refused, "slotWaitMs") >= (SLOT_REFUSE_DEADLINE_SECONDS - 1) * 1000
            and elapsed_of(result.stderr) <= SLOT_REFUSE_DEADLINE_SECONDS + DEADLINE_SLACK_SECONDS,
            True,
            "after waiting out its deadline and no longer (%d ms, %d s)"
            % (number(refused, "slotWaitMs"), elapsed_of(result.stderr)),
        )

    def tier_unit(self) -> None:
        """Critical-tier box Y1: a systemd unit at a 1-minute target fires on its timer, twice, about a minute apart, and each run meets the target. Control: before the timer starts the unit has run nothing."""
        d, r = self.d, self.rt
        d.step("Leg w (renet): a real unit at a %s target fires on its timer" % TIER_TARGET)
        name = UNIT_PREFIX + self.src[:8]
        try:
            before = unit_records(r.run_vm(unit_journal_command(name), must=False).stdout, self.src)
            d.last_cmd = "journalctl -u %s.service (before the timer)" % name
            d.assert_equal(
                "0", str(len(before)), "CONTROL: the unit has run nothing before its timer"
            )
            r.run_vm(
                install_unit_command(
                    name, tier_service_unit(r.datastore, self.src, r.cell_bytes), tier_timer_unit()
                )
            )
            fired = r.run_vm(
                wait_unit_runs_command(name, self.src, UNIT_RUNS, UNIT_WAIT_SECONDS), must=False
            )
            d.last_cmd = "journalctl -u %s.service (waiting %d s)" % (name, UNIT_WAIT_SECONDS)
            d.assert_equal(
                "0",
                str(fired.returncode),
                "the timer fired %d runs within %d s" % (UNIT_RUNS, UNIT_WAIT_SECONDS),
            )
            records = unit_records(
                r.run_vm(unit_journal_command(name), must=False).stdout, self.src
            )
            runs = records[:UNIT_RUNS]
            self.b.av(len(runs), UNIT_RUNS, "the unit's journal holds its runs' records")
            for index, (_, rec) in enumerate(runs, start=1):
                self.b.av(
                    [
                        str(rec.get("status", "")) in ("stored", "unchanged"),
                        number(rec, "targetSeconds"),
                        rec.get("targetMet"),
                    ],
                    [True, TIER_TARGET_SECONDS, True],
                    "run %d succeeded on a %d s target and met it" % (index, TIER_TARGET_SECONDS),
                )
            if len(runs) == UNIT_RUNS:
                gap = (runs[1][0] - runs[0][0]) // 1_000_000
                low, high = UNIT_GAP_SECONDS
                self.b.av(
                    low <= gap <= high, True, "the two runs fired a target apart (%d s)" % gap
                )
        finally:
            r.run_vm(unit_cleanup_command(name), must=False)

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
