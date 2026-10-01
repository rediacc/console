"""Port of `scripts/drills/backup.sh` (1505 lines): the live chunk-store battery.

    PYTHONPATH=.ci python3 -m rediacc_ci.drills.backup [--legs a,b,c,d,e,f,g,h,j,k] [--selftest] [--no-restart] [--keep-work] [--vm <ip>] [--ssh-user <u>] [--ssh-key <p>]

WHAT IT IS FOR. The backup-storage program replaces whole-image pushes with a content-addressed chunk store: a fixed cell grid over the LUKS image, SHA-256 of the ciphertext cell as object key and dedup key, a manifest per snapshot, and a control plane that mints sessions, answers which of a set of hashes are already held, mints delete-free write grants under a byte quota and commits manifests. This drill drives the whole path with real bytes over a real wire.

COST. No virtual machines for the default legs. It runs against `./run.sh account dev` (restarted by the drill) and the RustFS that script starts on :9100, and uploads a few hundred kilobytes. Leg i (`rdc backup verify` on a real repo) is opt-in and refuses itself by name when no machine is there.

LEGS, one claim each. a: a session mints from a license blob alone (with a tampered-blob control). b: seed upload, real PUTs through presigned URLs, a ledger that moved by exactly the bytes that moved. c: incremental upload, one changed cell transfers. d: both snapshots restore byte-identically through a read grant. e: the quota refuses at mint time, with the control that one byte of headroom lets the same request through. f: `rdc backup usage` and `rdc backup manifests` against the live server. g: the real `renet repository prune --output json` through the real CLI parser. h: the shapes renet's session client sends, against the live server. i: opt-in machine leg. j: a write session cannot read and a read session cannot write. k: a lapsed subscription still restores inside the retention window.

NOT PROVEN HERE, said plainly: no machine runs `renet backup snapshot` or `renet backup restore` in this host-only drill (the FIEMAP/anchor half is renet's btrfs tier, restore is e2e suite 26). Legs b-d produce their own cells.

THE OFFLINE CONTROL is `private/account/tests/integration/backup-lifecycle.test.ts`, the VM-less twin: if a leg fails here and its twin passes there, the difference is the environment.

TIER B: `DRILL_STORE_ENDPOINT` plus `DRILL_STORE_BUCKET`/`DRILL_STORE_KEY`/`DRILL_STORE_SECRET` points the whole drill at a real S3/R2 bucket. A run deletes under its own tenant prefix, so a bucket not named *probe*/*test*/*scratch*/*bench* (and the bare `rediacc-backups`) is refused.

RULE T: WHERE THIS DELIBERATELY DIFFERS FROM THE BASH (each pinned by a test in `tests/test_drills_backup_license.py`).

  1. NO `curl`, `node`, `uuidgen`, `awk` AND NO `--aws-sigv4` PRECONDITION. HTTP is `urllib`, the fixture image and its cell arithmetic are Python (`make_image`, `plan_of`, `assemble`) pinned to the node helper's exact bytes and hashes by a differential, and the one store request the drill signs itself (the bucket create, and the manifest fallback) is signed in-process (`wire.sigv4_headers`). The bash refused to start on a curl older than 7.75.
  2. THE GATEWAY GETS THE STORE ENVIRONMENT AND NOT THE SANDBOX. The bash exported the chunk-store variables and the throwaway `XDG_CONFIG_HOME` into its own environment before restarting the gateway, so the gateway inherited both (the sandbox half is the defect fixed in `rediacc_ci.drills.lib`). Here the store variables reach the gateway through `BackupDrill.gateway_env` and the sandbox reaches only the `rdc` commands under test.
  3. A TRANSPORT FAILURE ENDS THE DRILL WITH ITS CAUSE. In the bash a failed `curl` inside `$(...)` killed the shell under `set -e` with no message when the failure was an assignment, and was swallowed when it was a pipeline stage. Here every transport failure raises `OSError` naming the method and URL, and the drill exits 1 reporting it.
  4. AN EMPTY LEG ITEM IS REFUSED BY NAME. `--legs a,,b` ran silently as `a,b` in the bash (its `${LEGS//,/ }` split dropped the empty item); the unknown-leg refusal now covers it.
"""

from __future__ import annotations

import base64
import contextlib
import getpass
import hashlib
import http.cookiejar
import json
import os
import pathlib
import re
import secrets
import shutil
import subprocess
import sys
import time
import uuid
from typing import TYPE_CHECKING

from rediacc_ci import log
from rediacc_ci.drills import lib, wire

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

KNOWN_LEGS = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k"]
DEFAULT_LEGS = "a,b,c,d,e,f,g,h,j,k"
CELL_BYTES = 65536
CELLS = 8
# Cell 2 and cell 6 are holes: all-zero, elided from the manifest as "" the way FIEMAP-driven ZERO detection elides an unwritten extent.
HOLES = frozenset({2, 6})
USAGE = (
    "Usage: ./run.sh drill backup [--legs a,b,c,d,e,f,g,h,i,j,k] [--selftest] "
    "[--no-restart] [--keep-work] [--vm <ip>] [--ssh-user <u>] [--ssh-key <p>]"
)
DRILL_PASSWORD = "DrillBackup123!"  # noqa: S105 -- a throwaway dev-gateway login
CONFIG_NAME = "drill-backup"
S3_REGION = "us-east-1"


# ---------------------------------------------------------------------- the fixture image


def make_image(path: str | os.PathLike, version: str) -> None:
    """Write the fixture image: 8 cells, two of them holes (version 2 rewrites cell 3)."""
    image = bytearray(CELLS * CELL_BYTES)
    for cell in range(CELLS):
        if cell in HOLES:
            continue
        seed = 99 if cell == 3 and version == "2" else cell + 1
        base = cell * CELL_BYTES
        image[base : base + CELL_BYTES] = bytes(
            (seed * 31 + i * 7) % 251 for i in range(CELL_BYTES)
        )
    pathlib.Path(path).write_bytes(bytes(image))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def plan_of(path: str | os.PathLike) -> dict:
    """`{cellBytes, imageBytes, cells:[hash|""], unique:[]}` for an image, in the node helper's key order."""
    image = pathlib.Path(path).read_bytes()
    cells = []
    for cell in range(len(image) // CELL_BYTES):
        chunk = image[cell * CELL_BYTES : (cell + 1) * CELL_BYTES]
        cells.append("" if cell in HOLES else sha256_hex(chunk))
    unique = list(dict.fromkeys(c for c in cells if c != ""))
    return {"cellBytes": CELL_BYTES, "imageBytes": len(image), "cells": cells, "unique": unique}


def slice_cell(path: str | os.PathLike, index: int) -> bytes:
    return pathlib.Path(path).read_bytes()[index * CELL_BYTES : (index + 1) * CELL_BYTES]


def assemble(cells: list[str], chunk_dir: pathlib.Path, out: pathlib.Path) -> None:
    """Rebuild an image from cell hashes: a hole stays a hole, and a chunk of the wrong size is an error."""
    image = bytearray(len(cells) * CELL_BYTES)
    for index, digest in enumerate(cells):
        if digest == "":
            continue
        chunk = (chunk_dir / digest).read_bytes()
        if len(chunk) != CELL_BYTES:
            raise ValueError("cell %d: %d bytes, want %d" % (index, len(chunk), CELL_BYTES))
        image[index * CELL_BYTES : (index + 1) * CELL_BYTES] = chunk
    out.write_bytes(bytes(image))


def manifest_body(
    snapshot: str, plan: dict, lineage: str, parent: str = "", parent_plan: dict | None = None
) -> str:
    """The shapes renet actually writes (pkg/chunkstore/manifest.go): a full manifest carries `cells` with "" for a hole; a delta carries `parent` + `changedCells`."""
    base = {
        "version": 1,
        "snapshotId": snapshot,
        "repositoryGuid": lineage,
        "lineage": lineage,
        "cellBytes": CELL_BYTES,
        "imageBytes": plan["imageBytes"],
        "createdAt": wire.iso_now(),
    }
    if parent:
        assert parent_plan is not None  # noqa: S101
        changed = {str(i): h for i, h in enumerate(plan["cells"]) if parent_plan["cells"][i] != h}
        return wire.compact({**base, "parent": parent, "changedCells": changed})
    return wire.compact({**base, "cells": plan["cells"]})


# ---------------------------------------------------------------------- the drill


class BackupDrill(lib.Drill):
    """`lib.Drill` plus the environment only the dev gateway receives (Rule T 2)."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self.gateway_extra: dict[str, str] = {}

    def gateway_env(self) -> dict[str, str]:
        env = super().gateway_env()
        env.update(self.gateway_extra)
        return env


class Options:
    def __init__(self) -> None:
        self.restart_gateway = True
        self.legs = DEFAULT_LEGS
        self.net_base = os.environ.get("VM_NET_BASE") or "192.168.111"
        self.vm_ip = self.net_base + ".11"
        self.ssh_user = os.environ.get("SSH_USER") or os.environ.get("USER") or getpass.getuser()
        renet_data = os.environ.get("RENET_DATA_DIR") or os.path.join(
            os.environ.get("HOME", "~"), ".renet"
        )
        self.ssh_key = os.environ.get("SSH_KEY") or os.path.join(
            renet_data, "staging", ".ssh", "id_rsa"
        )
        self.store_endpoint = os.environ.get("DRILL_STORE_ENDPOINT", "")
        self.store_bucket = os.environ.get("DRILL_STORE_BUCKET", "")
        self.store_key = os.environ.get("DRILL_STORE_KEY", "")
        self.store_secret = os.environ.get("DRILL_STORE_SECRET", "")
        self.store_region = os.environ.get("DRILL_STORE_REGION") or "auto"
        self.rustfs_port = os.environ.get("RUSTFS_PORT") or "9100"
        self.rustfs_key = os.environ.get("CONFIG_R2_ACCESS_KEY_ID") or "configadmin"
        self.rustfs_secret = os.environ.get("CONFIG_R2_SECRET_ACCESS_KEY") or "configadmin"
        self.bucket = os.environ.get("BACKUP_BUCKET_NAME") or "rediacc-backups"

    def leg_set(self) -> list[str]:
        return self.legs.split(",")

    def enabled(self, leg: str) -> bool:
        return leg in self.leg_set()

    def needs_plane(self) -> bool:
        """Any leg that talks to the control plane needs BOTH the dev gateway and a reachable chunk store (g and i do not)."""
        return any(self.enabled(leg) for leg in "abcdefhjk")

    def using_real_store(self) -> bool:
        return bool(self.store_endpoint)


def parse_args(argv: list[str], opts: Options) -> int | None:
    """None to continue, otherwise the exit code (an unknown option exits 2)."""
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--no-restart":
            opts.restart_gateway = False
        elif arg in ("--legs", "--vm", "--ssh-user", "--ssh-key"):
            i += 1
            value = argv[i] if i < len(argv) else ""
            if arg == "--legs":
                opts.legs = value
            elif arg == "--vm":
                opts.vm_ip = value
            elif arg == "--ssh-user":
                opts.ssh_user = value
            else:
                opts.ssh_key = value
        else:
            log.error("Unknown option: %s" % arg)
            print(USAGE, file=sys.stderr)
            return 2
        i += 1
    return None


def validate_legs(opts: Options) -> bool:
    """Refuse an unknown or empty leg by name: a typo must never run a narrower battery and print PASSED."""
    if not opts.legs.replace(",", ""):
        log.error("--legs was given an empty list; nothing would run.")
        return False
    for leg in opts.leg_set():
        if leg not in KNOWN_LEGS:
            log.error("Unknown leg '%s' in --legs %s" % (leg, opts.legs))
            log.error("Known legs: %s" % ", ".join(KNOWN_LEGS))
            return False
    return True


def disposable_store_error(opts: Options) -> list[str]:
    """The refusal lines for a tier-B bucket that is not marked disposable (empty when fine)."""
    if not opts.using_real_store():
        return []
    if opts.store_bucket == "rediacc-backups":
        return [
            "refusing the bare production bucket name 'rediacc-backups': this drill writes and deletes."
        ]
    if not re.search(r"(probe|test|scratch|bench)", opts.store_bucket):
        return [
            "refusing bucket '%s': the name does not mark it disposable." % opts.store_bucket,
            "Use a bucket named *probe*/*test*/*scratch*/*bench*.",
        ]
    return []


@contextlib.contextmanager
def _cwd(path: pathlib.Path) -> Iterator[None]:
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class Backup:
    def __init__(self, drill: BackupDrill, opts: Options) -> None:
        self.d = drill
        self.o = opts
        self.rdc = str(drill.root / "rdc.sh")
        self.renet_bin = os.environ.get("DRILL_RENET_BIN") or str(
            drill.root / "private" / "renet" / "bin" / "renet"
        )
        stamp = int(time.time())
        self.email = "drill-backup-%d@rediacc.io" % stamp
        self.snap_seed = "snap-seed-%d" % stamp
        self.snap_incr = "snap-incr-%d" % stamp
        self.bucket = opts.bucket
        self.api_token = ""
        self.subscription_id = ""
        self.admin_jar: http.cookiejar.CookieJar | None = None
        self.session_token = ""
        self.session_mint_url = ""
        self.session_base_url = ""
        self.stream_id = ""
        self.lineage = ""
        self.seed_stored_bytes = 0
        self.quota_lowered = False
        self.lapsed_subscription = False
        self.license_blob: dict = {}
        self.machine_id = ""
        self.restore_session_token = ""
        self.seed_plan: dict = {}
        self.incr_plan: dict = {}
        self.grant: dict = {}
        self.status = "none"

    # ------------------------------------------------------------------ small helpers

    @property
    def work(self) -> pathlib.Path:
        assert self.d.work is not None  # noqa: S101
        return self.d.work

    def store_url(self) -> str:
        if self.o.using_real_store():
            return self.o.store_endpoint.rstrip("/")
        return "http://%s:%s" % (self.d.host, self.o.rustfs_port)

    def backup_api(self) -> str:
        return "%s/backups" % self.d.api_base()

    def api(
        self, method: str, url: str, body: object = None, headers: dict[str, str] | None = None
    ) -> str:
        """One call: returns the body and keeps the HTTP status in `self.status`. A transport failure raises `OSError`; an HTTP error is not an error here, the assertions read it."""
        payload = (
            None
            if body is None or body == ""
            else (body if isinstance(body, str) else wire.compact(body))
        )
        code, text = wire.http_call(method, url, payload, headers)
        self.status = str(code)
        return text

    def session_api(self, method: str, path: str, body: object = None) -> str:
        return self.api(
            method, self.backup_api() + path, body, {"X-Backup-Session": self.session_token}
        )

    def bearer(self) -> dict[str, str]:
        return {"Authorization": "Bearer %s" % self.api_token}

    def capture(self, description: str, body: str) -> None:
        """Stage a captured HTTP body as if `run` had produced it, so the JSON assertions and the failure dump work unchanged."""
        self.d.last_cmd = description
        if self.d.stdout_file is None or self.d.stderr_file is None:
            raise RuntimeError("Drill.init() must run first")
        self.d.stdout_file.write_text(body)
        self.d.stderr_file.write_text("")
        self.d.code = 0

    def run_fn(self, description: str, fn: Callable[[], bool]) -> None:
        """The bash `drill_run <function>`: the function's own outcome becomes the exit code, its output stays out of the way."""
        self.d.last_cmd = description
        if self.d.stdout_file is None or self.d.stderr_file is None:
            raise RuntimeError("Drill.init() must run first")
        self.d.stdout_file.write_text("")
        self.d.stderr_file.write_text("")
        try:
            self.d.code = 0 if fn() else 1
        except (OSError, ValueError, KeyError) as exc:
            self.d.stderr_file.write_text("%s\n" % exc)
            self.d.code = 1

    def aj(self, path: str, expected: object, desc: str) -> None:
        self.d.assert_equal(wire.jstr(expected), lib.json_get(self.d.stdout_text(), path), desc)

    def at(self, path: str, expected_type: str, desc: str) -> None:
        actual = wire.typeof(wire.lookup(wire.parse(self.d.stdout_text()), path))
        self.d.assert_equal(expected_type, actual, desc)

    def av(self, value: object, expected: object, desc: str) -> None:
        """Assert on a value computed from the captured body (the bash's JS expression)."""
        self.d.assert_equal(wire.jstr(expected), wire.jstr(value), desc)

    def stdout_json(self) -> object:
        return wire.parse(self.d.stdout_text())

    def field(self, path: str, body: str | None = None) -> object:
        parsed = wire.parse(self.d.stdout_text() if body is None else body)
        return wire.lookup(parsed, path)

    def patch_subscription(self, patch: dict) -> None:
        assert self.admin_jar is not None  # noqa: S101
        self.d.account_patch_subscription(self.admin_jar, self.subscription_id, patch)

    # ------------------------------------------------------------------ preflight

    def announce_cost(self) -> None:
        port = self.o.rustfs_port
        self.d.out.write(
            "\n  This drill runs against ./run.sh account dev and the RustFS it starts on\n"
            "  :%s. It provisions NOTHING and needs NO virtual machines.\n\n"
            "    legs a,b,c,d,e,f,h,j,k  the dev gateway (restarted by this drill) + Docker for\n"
            "                        the RustFS chunk store. A few hundred KB uploaded into\n"
            "                        bucket %s, under this run's own tenant prefix.\n"
            "    leg  g              the LOCAL renet binary and a throwaway datastore\n"
            "                        directory in the work dir. No server, no store.\n"
            "    leg  i              OPT-IN, needs a machine with a repo (./rdc.sh ops up --basic\n"
            "                        plus a licensed repo). Not selected by default.\n\n"
            "  Selected legs: %s\n\n" % (port, self.bucket, self.o.legs)
        )
        self.d.out.flush()

    def preflight_tools(self) -> None:
        d, o = self.d, self.o
        d.step("Preflight: tools")
        ok = True
        if o.needs_plane() and not _docker_ok():
            log.error("Docker is not available, so ./run.sh account dev cannot start RustFS.")
            log.error("Legs a,b,c,d,e,f,h,j,k all need the chunk store; only leg g can run here:")
            log.error("    ./run.sh drill backup --legs g")
            ok = False
        if o.enabled("g"):
            if not (os.path.isfile(self.renet_bin) and os.access(self.renet_bin, os.X_OK)):
                log.error("Leg g needs the renet binary at %s, which is missing." % self.renet_bin)
                log.error(
                    "Build it:  (cd private/renet && ./build.sh dev)   — or run any ./rdc.sh command."
                )
                log.error("Or drop the leg:  ./run.sh drill backup --legs a,b,c,d,e,f,h,j,k")
                ok = False
            if not shutil.which("npx"):
                log.error("Leg g runs the CLI's own parser through tsx and needs npx on PATH.")
                ok = False
        if o.enabled("i") and not os.path.isfile(o.ssh_key):
            log.error(
                "Leg i (machine) needs an SSH key at %s (override with --ssh-key)." % o.ssh_key
            )
            ok = False
        if not ok:
            raise SystemExit(1)
        d.note("python %s" % sys.version.split()[0])

    def preflight_machines(self) -> None:
        """Leg i is the only machine-dependent leg, and it refuses itself BY NAME rather than failing nine assertions deep on an empty box."""
        d, o = self.d, self.o
        if not o.enabled("i"):
            return
        d.step("Preflight: machine availability (leg i)")
        proc = subprocess.run(
            [self.rdc, "ops", "status", "-o", "json"],
            capture_output=True,
            text=True,
            env=d.cli_env(),
            check=False,
        )
        if proc.returncode != 0:
            log.error("Could not read ops status, and leg i needs a machine.")
            log.error("Provision one:  ./rdc.sh ops up --basic     Or drop the leg.")
            raise SystemExit(1)
        running = running_ips(proc.stdout)
        d.note("running VMs: %s" % (" ".join(running) or "<none>"))
        if o.vm_ip not in running:
            log.error("Leg i needs the worker VM %s, which is not running." % o.vm_ip)
            log.error("Provision it:  ./rdc.sh ops up --basic")
            log.error(
                "Or run the machine-less legs:  ./run.sh drill backup --legs a,b,c,d,e,f,g,h,j,k"
            )
            raise SystemExit(1)

    def announce_unrunnable(self) -> None:
        d = self.d
        d.step("Not covered by this run, and why (read this before trusting a green)")
        for line in (
            "renet-driven backup: the verb EXISTS (renet backup snapshot), but this",
            "  host-only drill does not run it: that needs a machine with a real",
            "  btrfs/LUKS repo and a licence. Legs b-d therefore produce their own cells;",
            "  the FIEMAP/anchor half is covered by renet's btrfs tier, not by this drill.",
            "machine-side restore: legs d/j/k now read through a READ GRANT, as a machine",
            "  does, but no machine RUNS renet backup restore here; that is e2e suite 26.",
            "cross-machine restore: byte-identity across two machines is suite 26's",
            "  RESTORE tier, which needs a two-worker fleet this host-only drill has not.",
        ):
            d.note(line)

    # ------------------------------------------------------------------ setup

    def setup_sandbox(self) -> None:
        d = self.d
        d.step("Setup: isolated config directory")
        config_home = self.work / "xdg"
        (config_home / "rediacc").mkdir(parents=True, exist_ok=True)
        d.extra_env["XDG_CONFIG_HOME"] = str(config_home)
        d.extra_env["REDIACC_CONFIG"] = CONFIG_NAME
        # Unpinned, a drill measures the json surface while describing the human one, because its stdout is never a TTY.
        d.extra_env["REDIACC_DEFAULT_OUTPUT"] = "table"
        # This drill targets only the disposable local ops VMs, so a renet built from a dirty private/renet tree may be uploaded to them.
        d.extra_env["REDIACC_ALLOW_DIRTY_RENET"] = "1"

    def setup_store_env(self) -> None:
        """Point the dev gateway at a chunk store BEFORE it starts: a stock dev gateway exports CONFIG_R2_* only, so its backup plane is absent and every backup route answers 503 BACKUP_NOT_CONFIGURED.

        ONE host value for the whole run: the account server presigns store URLs against its configured endpoint and an API token binds to the first host it is used with.
        """
        d, o = self.d, self.o
        if not o.needs_plane():
            return
        d.step("Setup: chunk-store environment for the dev gateway")
        host = wire.bridge_host(o.net_base)
        if host:
            d.host = host
            d.note("using the VM-network address %s (reachable from machines too)" % d.host)
        else:
            d.note(
                "no %s.0/24 interface; using %s for every URL in this run" % (o.net_base, d.host)
            )
        extra = d.gateway_extra
        if o.using_real_store():
            self.bucket = o.store_bucket
            extra["ACCOUNT_BACKUP_S3_ENDPOINT"] = o.store_endpoint.rstrip("/")
            extra["ACCOUNT_BACKUP_S3_BUCKET"] = o.store_bucket
            extra["ACCOUNT_BACKUP_S3_ACCESS_KEY_ID"] = o.store_key
            extra["ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY"] = o.store_secret
            d.note("TIER-B: real object store, bucket %s" % o.store_bucket)
        else:
            extra["ACCOUNT_BACKUP_S3_ENDPOINT"] = "http://%s:%s" % (d.host, o.rustfs_port)
            extra["ACCOUNT_BACKUP_S3_BUCKET"] = self.bucket
            extra["ACCOUNT_BACKUP_S3_ACCESS_KEY_ID"] = o.rustfs_key
            extra["ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY"] = o.rustfs_secret
        # The maintenance timer would run GC underneath the drill's own objects.
        extra["BACKUP_MAINTENANCE_INTERVAL_MS"] = "0"
        d.note(
            "chunk store: %s/%s"
            % (extra["ACCOUNT_BACKUP_S3_ENDPOINT"], extra["ACCOUNT_BACKUP_S3_BUCKET"])
        )

    def setup_gateway(self) -> None:
        d, o = self.d, self.o
        if not o.needs_plane():
            return
        if o.restart_gateway:
            d.restart_gateway()
        else:
            d.step("Reusing the running dev gateway (--no-restart)")
            if not d.gateway_alive():
                log.error("No healthy dev gateway. Start one: ./run.sh account dev")
                raise SystemExit(1)
            d.note("NOTE: a gateway this drill did not start may have no backup plane")
            d.note("configured, in which case every backup route answers 503.")
            d.gateway_port_cached = d.gateway_port()
        d.note("account server: %s" % d.server_url())

    def s3_put(self, url: str, payload: bytes = b"") -> str:
        o = self.o
        if o.using_real_store():
            headers = wire.sigv4_headers(
                "PUT", url, payload, o.store_region, o.store_key, o.store_secret
            )
        else:
            headers = wire.sigv4_headers(
                "PUT", url, payload, S3_REGION, o.rustfs_key, o.rustfs_secret
            )
        code, _ = wire.http_call("PUT", url, payload, headers, json_body=False)
        return str(code)

    def setup_store_bucket(self) -> None:
        d = self.d
        if not self.o.needs_plane():
            return
        d.step("Setup: the chunk-store bucket")
        waited = 0
        answered = False
        while True:
            # RustFS answers 403 to an unsigned root GET, which is a healthy store: any answer at all proves the port is serving.
            try:
                wire.http_call("GET", self.store_url() + "/", timeout=2)
                answered = True
                break
            except OSError:
                pass
            if waited >= 60:
                break
            time.sleep(2)
            waited += 2
        if not answered:
            port = self.o.rustfs_port
            log.error("No S3 store answering on %s after %ds." % (self.store_url(), waited))
            log.error("./run.sh account dev starts RustFS there when Docker is available, and it")
            log.error("FAILS OPEN: the gateway comes up healthy with no config store and no backup")
            log.error("plane, so this check is the only thing that notices. Look in")
            log.error(".account-logs/rustfs.log first.")
            log.error("")
            log.error("The failure seen on 2026-08-14 was the ghost-container state account.sh")
            log.error("documents: compose insists on recreating a container id the daemon does not")
            log.error('have ("No such container: <id>"), and account_docker_ghost_clean does not')
            log.error("clear it. The documented way out, which this drill then reuses:")
            log.error("    docker rm -f <the ghost container>")
            log.error("    docker run -d --name rediacc-config-rustfs-dev -p %s:9000 \\" % port)
            log.error("      -e RUSTFS_VOLUMES=/data -e RUSTFS_ADDRESS=0.0.0.0:9000 \\")
            log.error(
                "      -e RUSTFS_ACCESS_KEY=%s -e RUSTFS_SECRET_KEY=%s \\"
                % (self.o.rustfs_key, self.o.rustfs_secret)
            )
            log.error("      rustfs/rustfs:latest")
            raise SystemExit(1)
        # Create-bucket is idempotent here: this RustFS answers 200 to a re-create rather than 409, so nothing keys on the status. A failure to create is not fatal either, the first leg proves the store.
        with contextlib.suppress(OSError):
            self.s3_put("%s/%s" % (self.store_url(), self.bucket))
        d.note("bucket ready: %s/%s" % (self.store_url(), self.bucket))

    def setup_account(self) -> None:
        d = self.d
        if not self.o.needs_plane():
            return
        d.step("Setup: dev subscription and API token")
        d.account_ensure_login(self.email, DRILL_PASSWORD)
        d.account_ensure_subscription(self.email, "PROFESSIONAL")
        jar = http.cookiejar.MozillaCookieJar(str(self.work / "cookies.txt"))
        if not d.account_session(self.email, DRILL_PASSWORD, jar):
            raise SystemExit(1)
        self.subscription_id = d.account_subscription_id(jar)
        self.api_token = d.account_mint_token(
            jar,
            self.subscription_id,
            "drill-backup",
            ["license:read", "license:activate", "subscription:read", "backup:read"],
        )
        d.note("subscription %s" % self.subscription_id)
        # Leg e lowers the storage quota, which is an admin-route edit.
        self.admin_jar = http.cookiejar.MozillaCookieJar(str(self.work / "admin-cookies.txt"))
        if not d.account_admin_session(self.email, DRILL_PASSWORD, self.admin_jar):
            raise SystemExit(1)

    def teardown_hook(self) -> None:
        """Restore what the drill changed on the SUBSCRIPTION, because those edits outlive the work directory: a low quota or a suspended subscription left behind fails the NEXT run for a reason nothing explains. A failed restore is reported (Rule T), not swallowed."""
        if self.admin_jar is None or not self.subscription_id:
            return
        for flag, patch in (
            (self.quota_lowered, {"storageQuotaBytes": None}),
            (self.lapsed_subscription, {"status": "active"}),
        ):
            if flag:
                try:
                    self.patch_subscription(patch)
                except OSError as exc:
                    log.warn("teardown: restoring the subscription (%s) failed: %s" % (patch, exc))

    # ------------------------------------------------------------------ leg a

    def leg_a_session_mint(self) -> None:
        d = self.d
        d.step("Leg a: the license blob is the credential")
        self.machine_id = secrets.token_hex(32)
        self.lineage = str(uuid.uuid4())
        blob_response = self.api(
            "POST",
            "%s/licenses/activate-repo" % d.api_base(),
            {
                "machineId": self.machine_id,
                "clientMachineId": self.machine_id,
                "repositoryGuid": self.lineage,
                "kind": "grand",
                "requestedSizeGb": 1,
            },
            self.bearer(),
        )
        self.capture("POST /licenses/activate-repo", blob_response)
        d.assert_equal("200", self.status, "a repo license is issued for a fresh machine")
        self.at("license.payload", "string", "the blob carries a signed payload")

        blob = self.field("license", blob_response)
        # Retained for the restore-intent sessions legs d, j and k mint later: the blob is both credential and address book, and re-issuing one per leg would test a different machine than the one that wrote the chunks.
        self.license_blob = blob if isinstance(blob, dict) else {}
        self.session_mint_url = "%s/session" % self.backup_api()
        session = self.api(
            "POST",
            self.session_mint_url,
            {"license": self.license_blob, "machineId": self.machine_id},
        )
        self.capture("POST /backups/session", session)
        d.assert_equal(
            "200", self.status, "the blob alone mints a storage session (no API token presented)"
        )
        token = self.field("token")
        self.av(
            isinstance(token, str) and token.startswith("rbs_"),
            True,
            "the session token carries its own prefix",
        )
        self.aj("subscriptionId", self.subscription_id, "and is scoped to this subscription")
        self.aj(
            "grantKind",
            "presigned-s3",
            "the server reports a configured data plane (presigned S3 over the local store)",
        )
        # dataPlaneUrl is where CHUNK BYTES go and is NOT an API root; renet says so at session.go:43-47 after mistaking it for one cost a 100% mint failure.
        self.aj(
            "dataPlaneUrl",
            self.store_url(),
            "dataPlaneUrl names the STORE (chunk bytes), not the control-plane root",
        )
        self.session_token = wire.jstr(token)
        self.session_base_url = wire.jstr(self.field("dataPlaneUrl"))

        # CONTROL. Without this, every assertion above could be passing on a server that mints a session for anything at all.
        forged_license = json.loads(json.dumps(self.license_blob))
        raw = json.loads(base64.b64decode(forged_license["payload"]).decode())
        raw["subscriptionId"] = str(uuid.uuid4())
        forged_license["payload"] = base64.b64encode(wire.compact(raw).encode()).decode()
        forged = self.api(
            "POST",
            "%s/session" % self.backup_api(),
            {"license": forged_license, "machineId": self.machine_id},
        )
        self.capture("POST /backups/session (tampered blob — planted control)", forged)
        d.assert_equal(
            "403",
            self.status,
            "planted control: a tampered blob is REFUSED, so the check above can fail",
        )
        self.aj("code", "INVALID_LICENSE_SIGNATURE", "and the refusal names the signature")
        self.at("token", "undefined", "no session token leaks with the refusal")

    # ------------------------------------------------------------------ leg b

    def upload_cells(self, plan: dict, image: pathlib.Path, missing: list[str]) -> int:
        """PUT one object per MISSING hash through the grant's presigned URLs; content addressing means one PUT per unique hash. Returns the failure count."""
        failures = 0
        put_urls = (self.grant.get("grant") or {}).get("putUrls") or {}
        for digest in missing:
            index = plan["cells"].index(digest)
            data = slice_cell(image, index)
            # BARE HASH, not the object key: the DTO documents putUrls as "hash -> presigned PUT URL" and renet indexes it that way (pkg/chunkstore/grants.go:181).
            url = put_urls.get(digest) or ""
            if not url:
                failures += 1
                continue
            # If-None-Match is MANDATORY: the account presigns these URLs with IfNoneMatch, SigV4 signs the headers a request carries, and dropping it answers 403 SignatureDoesNotMatch. This drill IS the machine's stand-in, so it sends exactly what pkg/chunkstore/grants.go sends.
            code, _ = wire.http_call("PUT", url, data, {"If-None-Match": "*"}, json_body=False)
            if code != 200:
                failures += 1
        return failures

    def put_manifest(self, snapshot: str, body: str) -> str:
        """The manifest object, written THE WAY A MACHINE WRITES IT: through the manifestPutUrl the grant carries. The signed fallback exists only for a backend that mints no manifest URL, and is announced when it fires."""
        (self.work / "manifest.json").write_text(body)
        url = (self.grant.get("grant") or {}).get("manifestPutUrl") or ""
        if url:
            code, _ = wire.http_call(
                "PUT", url, body.encode(), {"If-None-Match": "*"}, json_body=False
            )
            return str(code)
        self.d.note("no manifestPutUrl in the grant: signing the manifest write with the")
        self.d.note("store's own credentials, which a machine cannot do (see assertion 20)")
        return self.s3_put(
            "%s/%s/t/%s/l/%s/m/%s"
            % (self.store_url(), self.bucket, self.subscription_id, self.lineage, snapshot),
            body.encode(),
        )

    def leg_b_seed_upload(self) -> None:
        d = self.d
        d.step("Leg b: the seed upload, with real bytes in the store")
        image = self.work / "image-v1.bin"
        make_image(image, "1")
        self.seed_plan = plan_of(image)
        lineage = self.lineage

        stream = self.session_api(
            "POST", "/streams", {"repositoryGuid": lineage, "lineageGuid": lineage}
        )
        self.capture("POST /backups/streams", stream)
        d.assert_equal("200", self.status, "the server mints a stream id for this repo and machine")
        self.aj("created", True, "and reports it as newly created")
        self.stream_id = wire.jstr(self.field("streamId"))

        unique = self.seed_plan["unique"]
        exists = self.session_api("POST", "/exists", {"lineageGuid": lineage, "hashes": unique})
        self.capture("POST /backups/exists (virgin lineage)", exists)
        d.assert_equal(
            "200", self.status, "exists-batch answers for a lineage the store has never seen"
        )
        self.av(len(_as_list(self.field("existing"))), 0, "and holds none of these hashes yet")
        self.aj("pinExpiresAt", "", "so there is nothing to pin (null, not a stale promise)")

        missing = unique
        declared = len(missing) * CELL_BYTES
        grant_text = self.session_api(
            "POST",
            "/grants",
            {
                "snapshotId": self.snap_seed,
                "lineageGuid": lineage,
                "declaredBytes": declared,
                "hashes": missing,
            },
        )
        self.grant = _as_dict(grant_text)
        self.capture("POST /backups/grants", grant_text)
        d.assert_equal(
            "200",
            self.status,
            "a write grant is minted (the quota is checked here, before any I/O)",
        )
        self.aj("grant.kind", "presigned-s3", "the grant is the presigned-S3 kind")
        put_urls = self.field("grant.putUrls")
        urls = put_urls if isinstance(put_urls, dict) else {}
        self.av(
            len(urls),
            len(missing),
            "one PUT URL per missing hash — the wire contract renet treats a gap in as fatal",
        )
        self.av(
            all("X-Amz-Signature=" in u and "/c/" in u for u in urls.values()),
            True,
            "every URL is actually signed, and points into the lineage's chunk prefix",
        )
        # The KEY shape, not just the value: renet indexes this map by bare hash and the DTO documents it as "hash -> presigned PUT URL". Keyed by full object key instead, every lookup misses and the run uploads nothing while looking healthy.
        self.av(
            all(re.fullmatch(r"[0-9a-f]{64}", k) for k in urls),
            True,
            "putUrls is keyed by BARE HASH, the way the machine indexes it",
        )
        self.at(
            "grant.manifestPutUrl",
            "string",
            "the grant carries a manifest PUT URL (commit HEADs that object; a machine has no other way to write it)",
        )

        failures = self.upload_cells(self.seed_plan, image, missing)
        d.last_cmd = "PUT each missing cell through its presigned URL"
        d.assert_equal("0", str(failures), "every cell PUT into the store returns 200")

        recheck = self.session_api("POST", "/exists", {"lineageGuid": lineage, "hashes": unique})
        self.capture("POST /backups/exists (after the uploads)", recheck)
        self.av(
            len(_as_list(self.field("existing"))),
            len(unique),
            "the server now HEADs every one of them in the store: the bytes really landed",
        )

        manifest = manifest_body(self.snap_seed, self.seed_plan, lineage)
        status = self.put_manifest(self.snap_seed, manifest)
        d.last_cmd = "PUT the manifest object through the grant's manifestPutUrl"
        d.assert_equal(
            "200",
            status,
            "the manifest object reaches the bucket through the GRANT, as a machine would",
        )

        self.seed_stored_bytes = declared
        commit_body = {
            "snapshotId": self.snap_seed,
            "lineageGuid": lineage,
            "streamId": self.stream_id,
            "cellSizeBytes": CELL_BYTES,
            "totalBytes": self.seed_plan["imageBytes"],
            "addedBytes": declared,
            "addedChunkCount": len(missing),
        }
        commit = self.session_api("POST", "/commit", commit_body)
        self.capture("POST /backups/commit (seed)", commit)
        d.assert_equal("200", self.status, "the snapshot commits")
        self.aj("idempotent", False, "as a first commit, not a replay")
        self.aj("storedBytes", declared, "and the ledger moved by exactly the bytes uploaded")

        replay = self.session_api("POST", "/commit", commit_body)
        self.capture("POST /backups/commit (replayed)", replay)
        self.aj("idempotent", True, "a replayed commit is idempotent")
        self.aj("storedBytes", declared, "and bills nothing twice")

    # ------------------------------------------------------------------ leg c

    def leg_c_incremental_upload(self) -> None:
        d = self.d
        d.step("Leg c: the second run moves only what changed")
        image = self.work / "image-v2.bin"
        make_image(image, "2")
        self.incr_plan = plan_of(image)
        lineage = self.lineage

        unique = self.incr_plan["unique"]
        exists = self.session_api("POST", "/exists", {"lineageGuid": lineage, "hashes": unique})
        self.capture("POST /backups/exists (second run)", exists)
        d.assert_equal("200", self.status, "exists-batch answers for the changed image")
        existing = _as_list(self.field("existing"))
        self.av(
            len(existing),
            len(unique) - 1,
            "every unchanged cell is already held: exactly one hash is new",
        )
        # An exists ANSWER is a promise to skip those chunks, so it must pin them for 24h; without the pin, GC can delete a skipped chunk between the answer and the commit that references it.
        self.at("pinExpiresAt", "string", "the skip promise is pinned")

        held = set(existing)
        missing = [h for h in unique if h not in held]
        d.last_cmd = "the missing set of the incremental run"
        d.assert_equal("1", str(len(missing)), "one cell changed, so exactly one cell transfers")

        declared = CELL_BYTES
        grant_text = self.session_api(
            "POST",
            "/grants",
            {
                "snapshotId": self.snap_incr,
                "lineageGuid": lineage,
                "declaredBytes": declared,
                "hashes": missing,
            },
        )
        self.grant = _as_dict(grant_text)
        self.capture("POST /backups/grants (incremental)", grant_text)
        d.assert_equal("200", self.status, "a grant is minted for the delta only")

        failures = self.upload_cells(self.incr_plan, image, missing)
        d.last_cmd = "PUT the single changed cell"
        d.assert_equal("0", str(failures), "the changed cell uploads")

        manifest = manifest_body(
            self.snap_incr, self.incr_plan, lineage, self.snap_seed, self.seed_plan
        )
        status = self.put_manifest(self.snap_incr, manifest)
        d.last_cmd = "PUT the DELTA manifest object"
        d.assert_equal("200", status, "the delta manifest reaches the bucket")

        commit = self.session_api(
            "POST",
            "/commit",
            {
                "snapshotId": self.snap_incr,
                "lineageGuid": lineage,
                "streamId": self.stream_id,
                "parentSnapshotId": self.snap_seed,
                "cellSizeBytes": CELL_BYTES,
                "totalBytes": self.incr_plan["imageBytes"],
                "addedBytes": declared,
                "addedChunkCount": 1,
            },
        )
        self.capture("POST /backups/commit (incremental)", commit)
        d.assert_equal("200", self.status, "the incremental snapshot commits")
        self.aj(
            "storedBytes",
            self.seed_stored_bytes + CELL_BYTES,
            "the ledger grew by ONE cell, not by another whole image",
        )

    # ------------------------------------------------------------------ leg d

    def mint_restore_session(self) -> bool:
        """A RESTORE-intent session for the drill's license: not interchangeable with the backup-intent one (a restore session cannot write, and it is the only intent a lapsed-but-retained subscription can obtain)."""
        response = self.api(
            "POST",
            self.session_mint_url,
            {"license": self.license_blob, "machineId": self.machine_id, "intent": "restore"},
        )
        self.restore_session_token = wire.jstr(self.field("token", response))
        return bool(self.restore_session_token)

    def read_grant(self, snapshot: str, hashes: list[str] | None = None) -> str:
        return self.api(
            "POST",
            "%s/read-grants" % self.backup_api(),
            {"lineageGuid": self.lineage, "snapshotId": snapshot, "hashes": hashes or []},
            {"X-Backup-Session": self.restore_session_token},
        )

    def restore_snapshot(self, snapshot: str, out: pathlib.Path) -> bool:
        """Restore AS A MACHINE DOES IT: through a read grant, never with the store's own credentials.

        Two grants per restore, and that is the protocol: the first is minted with NO hashes to learn `manifestChain` (which the machine cannot derive), and the second presigns the chunks once the composed inventory says which are wanted.
        """
        directory = self.work / ("restore-%s" % snapshot)
        (directory / "chunks").mkdir(parents=True, exist_ok=True)

        chain_grant = self.read_grant(snapshot)
        chain = self.field("manifestChain", chain_grant)
        if not isinstance(chain, list) or not chain:
            return False
        get_urls = self.field("manifestGetUrls", chain_grant)
        if not isinstance(get_urls, dict):
            return False
        # Fetch every manifest the server named, FULL ROOT FIRST, and compose the chain one hop at a time: the chain is of unbounded depth.
        cells: list[str] | None = None
        for ident in chain:
            url = get_urls.get(ident) or ""
            if not url:
                return False
            code, raw = wire.http_bytes("GET", url)
            if code >= 400:
                return False
            manifest = json.loads(raw.decode())
            if cells is None:
                if manifest.get("parent"):
                    raise ValueError("chain root %s is a delta" % manifest.get("snapshotId"))
                cells = list(manifest["cells"])
            else:
                for index, digest in (manifest.get("changedCells") or {}).items():
                    cells[int(index)] = digest
        if cells is None:
            return False
        wanted = list(dict.fromkeys(h for h in cells if h != ""))
        chunk_grant = self.read_grant(snapshot, wanted)
        get_chunk = self.field("getUrls", chunk_grant)
        for digest in wanted:
            # Keyed by BARE HASH, never by object key: the write path already paid for the other choice and every lookup missed.
            url = (get_chunk if isinstance(get_chunk, dict) else {}).get(digest) or ""
            if not url:
                return False
            code, raw = wire.http_bytes("GET", url)
            if code >= 400:
                return False
            (directory / "chunks" / digest).write_bytes(raw)
        assemble(cells, directory / "chunks", out)
        return True

    def leg_d_point_in_time_restore(self) -> None:
        d = self.d
        d.step("Leg d: both snapshots restore byte-identically, THROUGH A READ GRANT")
        self.run_fn("restore_session_token", self.mint_restore_session)
        d.assert_exit(0, "a restore-intent session is minted from the same license blob")

        seed_sha = sha256_hex((self.work / "image-v1.bin").read_bytes())
        incr_sha = sha256_hex((self.work / "image-v2.bin").read_bytes())
        d.last_cmd = "sha256 of the two source images"
        d.assert_not_equal(
            seed_sha,
            incr_sha,
            "control: the two source images really differ (a compare of identical inputs proves nothing)",
        )

        restored_v1 = self.work / "restored-v1.bin"
        self.run_fn(
            "restore_snapshot %s %s" % (self.snap_seed, restored_v1),
            lambda: self.restore_snapshot(self.snap_seed, restored_v1),
        )
        d.assert_exit(0, "the seed snapshot is fetched and reassembled")
        d.last_cmd = "sha256 of the restored seed image"
        d.assert_equal(
            seed_sha,
            _sha_file(restored_v1),
            "POINT IN TIME: the OLD snapshot still restores to the OLD bytes after the newer one landed",
        )

        restored_v2 = self.work / "restored-v2.bin"
        self.run_fn(
            "restore_snapshot %s %s" % (self.snap_incr, restored_v2),
            lambda: self.restore_snapshot(self.snap_incr, restored_v2),
        )
        d.assert_exit(0, "the incremental snapshot is fetched and materialized over its parent")
        d.last_cmd = "sha256 of the restored incremental image"
        d.assert_equal(incr_sha, _sha_file(restored_v2), "and reassembles byte-identically too")

    # ------------------------------------------------------------------ leg e

    def leg_e_quota_refusal(self) -> None:
        d = self.d
        d.step("Leg e: past the quota, the grant is refused before any I/O")
        usage = self.api("GET", "%s/usage" % self.backup_api(), None, self.bearer())
        self.capture("GET /backups/usage", usage)
        d.assert_equal("200", self.status, "usage is readable with the backup:read scope")
        used = wire.jstr(self.field("storedBytes"))
        d.assert_equal(
            str(self.seed_stored_bytes + CELL_BYTES),
            used,
            "and reports exactly the bytes this drill stored",
        )

        # Pin the quota to what is already stored: the next byte cannot fit.
        self.patch_subscription({"storageQuotaBytes": _as_number(used)})
        self.quota_lowered = True
        d.note("storage quota pinned to the stored bytes (%s)" % used)

        probe = {
            "snapshotId": "snap-over-quota",
            "lineageGuid": self.lineage,
            "declaredBytes": 1,
            "hashes": [],
        }
        refused = self.session_api("POST", "/grants", probe)
        self.capture("POST /backups/grants (one byte over the quota)", refused)
        d.assert_equal("403", self.status, "one byte over the quota is refused")
        self.aj("code", "BACKUP_QUOTA_EXCEEDED", "with the exact refusal code")
        retry = self.field("retryAfter")
        self.av(
            isinstance(retry, (int, float)) and not isinstance(retry, bool) and retry > 0,
            True,
            "carrying a retry hint the client can back off on",
        )
        self.aj("quotaBytes", used, "and the quota it measured against")

        # CONTROL: the same request, one byte of headroom later, must succeed: otherwise the refusal above could be any old rejection.
        self.patch_subscription({"storageQuotaBytes": _as_number(used) + 1})
        allowed = self.session_api("POST", "/grants", probe)
        self.capture("POST /backups/grants (with one byte of headroom — planted control)", allowed)
        d.assert_equal(
            "200",
            self.status,
            "planted control: with one byte of room the SAME request is granted, so the refusal was the quota",
        )

        self.patch_subscription({"storageQuotaBytes": None})
        self.quota_lowered = False

    # ------------------------------------------------------------------ leg f

    def setup_cli_config(self) -> None:
        d = self.d
        d.step("Setup: an rdc config pointed at this gateway")
        server = d.server_url()
        d.setup_run([self.rdc, "config", "init", CONFIG_NAME, "--server", server])
        d.setup_run([self.rdc, "config", "current", "-o", "json"])
        d.setup_run(
            [self.rdc, "subscription", "login", "--token", self.api_token, "--server", server]
        )

    def leg_f_cli_reads(self) -> None:
        d = self.d
        d.step("Leg f: rdc backup usage / manifests against the live server")
        self.setup_cli_config()

        # The CLI wraps every -o json payload in its {success, data} envelope, so the fields live one level down.
        d.run([self.rdc, "backup", "usage", "-o", "json"])
        d.assert_exit(0, "rdc backup usage exits 0")
        self.aj(
            "data.storedBytes",
            self.seed_stored_bytes + CELL_BYTES,
            "and reports the same stored bytes the ledger holds",
        )
        lineages = self.field("data.lineages")
        self.av(
            any(
                isinstance(x, dict) and x.get("lineageGuid") == self.lineage
                for x in (lineages if isinstance(lineages, list) else [])
            ),
            True,
            "with this repo's lineage in the per-repo breakdown",
        )

        d.run([self.rdc, "backup", "manifests", "-o", "json"])
        d.assert_exit(0, "rdc backup manifests exits 0")
        found = self.field("data.manifests")
        manifests = [m for m in (found if isinstance(found, list) else []) if isinstance(m, dict)]
        self.av(
            any(m.get("snapshotId") == self.snap_seed for m in manifests),
            True,
            "the seed snapshot is listed",
        )
        self.av(
            any(
                m.get("snapshotId") == self.snap_incr
                and m.get("parentSnapshotId") == self.snap_seed
                for m in manifests
            ),
            True,
            "and the incremental one, carrying its parent",
        )

        # Stream placement: the human progress line must not land on stdout, or every `-o json` consumer downstream parses garbage.
        d.run([self.rdc, "backup", "usage", "-o", "json"])
        d.assert_stdout_not_contains("Fetching", "the progress line stays off stdout in json mode")

    # ------------------------------------------------------------------ leg g

    def leg_g_prune_json_contract(self) -> None:
        d = self.d
        d.step("Leg g: real renet prune JSON through the real CLI parser")
        ds = self.work / "ds"
        dead = "11111111-2222-3333-4444-555555555555"
        staging = "66666666-7777-8888-9999-aaaaaaaaaaaa"
        live = "22222222-3333-4444-5555-666666666666"
        for sub in ("repositories", "mounts", ".chunk-anchors"):
            (ds / sub).mkdir(parents=True, exist_ok=True)
        # An anchor whose repo image is gone: reclaimable.
        (ds / ".chunk-anchors" / dead).write_text("anchor\n")
        # Staging left by a killed run, with no lock held: reclaimable.
        (ds / ".chunk-anchors" / ("%s.new" % staging)).write_text("staging\n")
        # An anchor whose repo image EXISTS: the over-eager control. Deleting it would silently degrade the next backup to a full local rehash.
        (ds / ".chunk-anchors" / live).write_text("anchor\n")
        (ds / "repositories" / live).write_text("image\n")

        d.run(
            [
                self.renet_bin,
                "repository",
                "prune",
                "--datastore",
                str(ds),
                "--dry-run",
                "--output",
                "json",
            ]
        )
        d.assert_exit(0, "renet repository prune --output json exits 0 on a datastore directory")
        parsed = self.stdout_json()
        anchors = wire.lookup(parsed, "stale_backup_anchors")
        anchor_list = anchors if isinstance(anchors, list) else []
        self.av(
            dead in anchor_list,
            True,
            "the anchor whose repo is gone is reported (stale_backup_anchors)",
        )
        self.av(("%s.new" % staging) in anchor_list, True, "and so is the abandoned .new staging")
        self.av(
            live in anchor_list,
            False,
            "over-eager control: the anchor of a LIVE repo is NOT reported",
        )
        keys = parsed if isinstance(parsed, dict) else {}
        self.av(
            "stale_backup_journals" in keys,
            True,
            "the journal key is present in the contract (empty here: the journal dir is machine-local)",
        )
        self.av(
            "stale_pull_staging" in keys and "stale_churn_probe_bases" in keys,
            True,
            "together with wave 0's two keys",
        )

        # The other half of the contract: the CLI's parser turns THIS output into preview rows. Reading the struct tags cannot catch a parser that never sees real output.
        assert d.stdout_file is not None  # noqa: S101
        shutil.copyfile(d.stdout_file, self.work / "prune.json")
        script = self.work / "parse-prune.ts"
        script.write_text(
            "import { readFileSync } from 'node:fs';\n"
            "import {\n"
            "  buildPrunePreviewRows,\n"
            "  parseDatastorePruneOutput,\n"
            "  type DatastorePrunableResources,\n"
            "} from '%s/packages/cli/src/commands/datastore-prune-parser.js';\n\n"
            "const parsed = parseDatastorePruneOutput(\n"
            "  readFileSync(process.argv[2], 'utf8')\n"
            ") as DatastorePrunableResources;\n"
            "process.stdout.write(JSON.stringify({ rows: buildPrunePreviewRows(parsed) }));\n"
            % d.root
        )
        # tsx is resolved from the CLI package, where its devDependency and tsconfig live: the cwd moves only for this command.
        with _cwd(d.root / "packages" / "cli"):
            d.run(["npx", "tsx", str(script), str(self.work / "prune.json")])
        d.assert_exit(0, "the CLI parser consumes renet's real output")
        found = self.field("rows")
        rows = [r for r in (found if isinstance(found, list) else []) if isinstance(r, dict)]
        self.av(
            sum(1 for r in rows if r.get("type") == "backup-anchor"),
            2,
            "and renders both reclaimable anchors as backup-anchor rows",
        )

    # ------------------------------------------------------------------ leg h

    def leg_h_machine_wire_conformance(self) -> None:
        d = self.d
        d.step("Leg h: the shapes renet's session client sends, against the live server")
        lineage = self.lineage
        header = {"X-Backup-Session": self.session_token}

        # 1. The API root: the client derives it as the mint URL minus its /session suffix (session.go:134).
        derived = self.session_mint_url.removesuffix("/session")
        d.last_cmd = "derive the API root the way session.go:134 does"
        d.assert_equal(
            self.backup_api(),
            derived,
            "the mint URL minus /session IS the control-plane root (session.go:134)",
        )

        # 2. exists: path, header and body, exactly as ExistsBatch sends them (session.go:256-261). The header is X-Backup-Session, never a bearer.
        exists = self.api(
            "POST",
            "%s/exists" % self.backup_api(),
            {"lineageGuid": lineage, "hashes": ["a" * 64]},
            header,
        )
        self.capture("POST /exists as ExistsBatch sends it (session.go:256-261)", exists)
        d.assert_equal("200", self.status, "renet's exists call is accepted verbatim")
        # The client computes the MISSING set as the complement of `existing` (session.go:266-289): a missing key would be a silent zero-chunk backup.
        self.av(
            isinstance(self.field("existing"), list),
            True,
            "the answer carries an 'existing' array (a missing key = a silent zero-chunk backup)",
        )

        # 3. grants: the body MintGrant sends (session.go:293-299).
        grant = self.api(
            "POST",
            "%s/grants" % self.backup_api(),
            {
                "snapshotId": "wire-probe-%d" % os.getpid(),
                "lineageGuid": lineage,
                "declaredBytes": 0,
                "hashes": [],
            },
            header,
        )
        self.capture("POST /grants as MintGrant sends it (session.go:293-299)", grant)
        d.assert_equal("200", self.status, "renet's grant body satisfies the route's schema")
        self.at("grant.kind", "string", "the response nests the grant under 'grant', with a kind")
        self.at("leaseId", "string", "and carries the leaseId the client stamps")

        # 4. commit: the FIELD SET CommitManifest sends (session.go:341-352).
        commit = self.api(
            "POST",
            "%s/commit" % self.backup_api(),
            {
                "snapshotId": self.snap_incr,
                "lineageGuid": lineage,
                "streamId": self.stream_id,
                "cellSizeBytes": CELL_BYTES,
                "totalBytes": 0,
                "addedBytes": 0,
                "addedChunkCount": 0,
            },
            header,
        )
        self.capture("POST /commit as CommitManifest sends it (session.go:341-352)", commit)
        d.assert_equal("200", self.status, "renet's commit field set is accepted")
        self.aj(
            "idempotent",
            True,
            "and replaying leg c's snapshot is idempotent, so this probe bills nothing",
        )

        # 5. streams: GetOrCreateStream's body (session.go:148-151).
        stream = self.api(
            "POST",
            "%s/streams" % self.backup_api(),
            {"repositoryGuid": lineage, "lineageGuid": lineage},
            header,
        )
        self.capture("POST /streams as GetOrCreateStream sends it (session.go:148-151)", stream)
        d.assert_equal("200", self.status, "renet's stream call is accepted")
        self.aj(
            "streamId",
            self.stream_id,
            "and resolves to the SAME stream leg b opened (identity is per repo and machine)",
        )

        # 6. The control: a body the server must REFUSE.
        refused = self.api(
            "POST", "%s/grants" % self.backup_api(), {"lineage": lineage, "hashes": []}, header
        )
        self.capture(
            "POST /grants with the client's OLD body {lineage, hashes} — planted control", refused
        )
        d.assert_equal(
            "400",
            self.status,
            "planted control: the pre-fix body is still refused, so the acceptances above mean something",
        )

    # ------------------------------------------------------------------ leg i

    def leg_i_machine_verify(self) -> None:
        d = self.d
        d.step("Leg i: rdc backup verify on a real machine")
        d.note("this leg needs a repo on %s that this drill did not create" % self.o.vm_ip)
        ref = os.environ.get("DRILL_REPO_REF") or "drill-repo"
        d.run([self.rdc, "backup", "verify", ref, "-o", "json"])
        d.assert_exit(
            0, "rdc backup verify exits 0 on a repo with no backup yet (no-backup is not a failure)"
        )
        d.assert_stdout_contains("no-backup", "and says so by name rather than inventing a verdict")

    # ------------------------------------------------------------------ leg j

    def leg_j_write_grant_cannot_read(self) -> None:
        d = self.d
        d.step("Leg j: a write session cannot read, and a read session cannot write")
        # The backup-intent session leg a minted is still in hand. It must be refused at /read-grants.
        refused = self.session_api(
            "POST", "/read-grants", {"lineageGuid": self.lineage, "snapshotId": self.snap_seed}
        )
        self.capture("POST /backups/read-grants on a BACKUP-intent session", refused)
        d.assert_not_equal(
            "200",
            self.status,
            "a backup-intent session is REFUSED a read grant (else leg d proves only that someone can read)",
        )

        # And the mirror: a read credential that can also write is a ransomware path, not a restore path.
        self.run_fn("restore_session_token", self.mint_restore_session)
        d.assert_exit(
            0,
            "control: a restore-intent session still mints (the refusal above is about INTENT, not a dead token)",
        )
        # declaredBytes, NOT totalBytes: the wrong field name dies in schema validation with a 400 and never reaches the intent check.
        write_refused = self.api(
            "POST",
            "%s/grants" % self.backup_api(),
            {
                "hashes": [],
                "declaredBytes": 1,
                "lineageGuid": self.lineage,
                "snapshotId": self.snap_seed,
            },
            {"X-Backup-Session": self.restore_session_token},
        )
        self.capture("POST /backups/grants on a RESTORE-intent session", write_refused)
        d.assert_equal("403", self.status, "a restore-intent session is REFUSED a write grant")
        self.aj(
            "code",
            "BACKUP_SESSION_READ_ONLY",
            "and it is refused BY NAME, not as a generic 403 that could be anything",
        )

    # ------------------------------------------------------------------ leg k

    def lapse_subscription(self) -> bool:
        """Move the drill subscription out of an entitled state through the admin PUT (there is no /test route for it). The restore flag lives in `teardown_hook`, because an admin edit outlives the work directory."""
        self.patch_subscription({"status": "suspended"})
        self.lapsed_subscription = True
        return True

    def leg_k_lapsed_restore(self) -> None:
        d = self.d
        d.step("Leg k: a LAPSED subscription can still restore inside the retention window")
        # Control first, and it is the load-bearing one: a BACKUP intent against the same lapsed subscription must be refused.
        self.run_fn("lapse_subscription", self.lapse_subscription)
        d.assert_exit(0, "the drill subscription is moved to a lapsed state")

        backup_refused = self.api(
            "POST",
            self.session_mint_url,
            {"license": self.license_blob, "machineId": self.machine_id},
        )
        self.capture("POST /backups/session (backup intent, lapsed)", backup_refused)
        d.assert_not_equal(
            "200",
            self.status,
            "CONTROL: a backup-intent session is refused once the subscription lapses",
        )

        restore_ok = self.api(
            "POST",
            self.session_mint_url,
            {"license": self.license_blob, "machineId": self.machine_id, "intent": "restore"},
        )
        self.capture("POST /backups/session (restore intent, lapsed but retained)", restore_ok)
        d.assert_equal(
            "200",
            self.status,
            "but a RESTORE-intent session is granted: this is the 60-day promise",
        )
        self.restore_session_token = wire.jstr(self.field("token", restore_ok))

        restored = self.work / "restored-lapsed.bin"
        self.run_fn(
            "restore_snapshot %s %s" % (self.snap_seed, restored),
            lambda: self.restore_snapshot(self.snap_seed, restored),
        )
        d.assert_exit(0, "and the data actually comes back through it")
        want = _sha_file(self.work / "image-v1.bin")
        got = _sha_file(restored)
        d.last_cmd = "sha256 of the image restored on a lapsed subscription"
        d.assert_equal(
            want, got, "byte-identically — retained data is USABLE data, not just stored data"
        )

    # ------------------------------------------------------------------ main

    def run_all(self) -> int:
        o, d = self.o, self.d
        self.announce_cost()
        d.selftest_probe()
        if d.selftest:
            d.note("selftest mode: stopping before any server or store work")
            return d.summary()

        self.preflight_tools()
        self.preflight_machines()
        self.announce_unrunnable()

        self.setup_sandbox()
        self.setup_store_env()
        self.setup_gateway()
        self.setup_store_bucket()
        self.setup_account()

        # Legs b-f, h, j and k all operate on the session and lineage leg a opens. Selecting them without leg a would produce a pile of 401s that read like defects.
        if o.needs_plane() and not o.enabled("a"):
            log.error(
                "Legs b-f, h, j and k all run inside the session leg a mints, and there is no"
            )
            log.error("session on disk to inherit. Include leg a:  --legs a,%s" % o.legs)
            raise SystemExit(1)

        for leg, fn in (
            ("a", self.leg_a_session_mint),
            ("b", self.leg_b_seed_upload),
            ("c", self.leg_c_incremental_upload),
            ("d", self.leg_d_point_in_time_restore),
            ("e", self.leg_e_quota_refusal),
            ("f", self.leg_f_cli_reads),
            ("g", self.leg_g_prune_json_contract),
            ("h", self.leg_h_machine_wire_conformance),
            ("i", self.leg_i_machine_verify),
            ("j", self.leg_j_write_grant_cannot_read),
            ("k", self.leg_k_lapsed_restore),
        ):
            if o.enabled(leg):
                fn()
        return d.summary()


# ---------------------------------------------------------------------- small utilities


def _docker_ok() -> bool:
    if not shutil.which("docker"):
        return False
    return subprocess.run(["docker", "info"], capture_output=True, check=False).returncode == 0


def running_ips(status_json: str) -> list[str]:
    """The `ip` of every VM whose status is `running` in `rdc ops status -o json` (the CLI envelope puts the array at `data.vms`; the bare renet shape is accepted too). `ops status` lists every CONFIGURED VM including absent ones, so the gate is on each entry's status, never on the array's length."""
    parsed = wire.parse(status_json)
    vms = wire.lookup(parsed, "data.vms")
    if not isinstance(vms, list):
        vms = wire.lookup(parsed, "vms")
    if not isinstance(vms, list):
        return []
    return [str(v.get("ip")) for v in vms if isinstance(v, dict) and v.get("status") == "running"]


def _sha_file(path: pathlib.Path) -> str:
    return sha256_hex(path.read_bytes()) if path.is_file() else ""


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _as_dict(text: str) -> dict:
    parsed = wire.parse(text)
    return parsed if isinstance(parsed, dict) else {}


def _as_number(text: str) -> int:
    try:
        return int(text)
    except ValueError:
        return 0


def main(argv: list[str]) -> int:
    selftest, keep_work, rest = lib.parse_common_args(argv)
    opts = Options()
    code = parse_args(rest, opts)
    if code is not None:
        return code
    # Before ANYTHING else, including --selftest: a mistyped leg must be refused whether or not the run would have reached a server.
    if not validate_legs(opts):
        return 1
    problems = disposable_store_error(opts)
    if problems:
        for line in problems:
            log.error(line)
        return 1
    drill = BackupDrill("backup", selftest=selftest, keep_work=keep_work)
    drill.init()
    backup = Backup(drill, opts)
    rc = 1
    try:
        rc = backup.run_all()
    except SystemExit as exc:
        rc = int(exc.code) if isinstance(exc.code, int) else 1
    except (lib.GatewayError, OSError) as exc:
        log.error(str(exc))
        rc = 1
    finally:
        with contextlib.suppress(Exception):
            backup.teardown_hook()
        drill.teardown()
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
