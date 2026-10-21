"""Start the backup plane a CI leg needs for the `rdc backup browse --at` end-to-end tier: RustFS with the probe bucket, and an account server that mints backup-capable tokens and presigns against that bucket.

    PYTHONPATH=.ci python3 -m rediacc_ci.testrun.start_backup_plane [--port <n>] [--worker <n>]

Four steps, each fatal on failure (the drill `drills.backup_local_plane` only warns on a bucket failure, since it starts a dev gateway that may reuse an existing bucket; a CI leg has nothing to reuse, so a missing bucket would surface minutes later as a presign error):

  1. RustFS on 127.0.0.1:9100 (`account_lifecycle.start_rustfs`) and the `rediacc-backups-probe` bucket. NEVER `rediacc-backups`, the production name.
  2. The bridge address of the VM network (`wire.bridge_host("192.168.111")`). It is the host in the published account server URL (the licence's renewalUrl is stamped from it) and in ACCOUNT_BACKUP_S3_ENDPOINT, since SigV4 signs the Host header and the presigned URLs are dialled from the VM.
  3. `start_account` with the backup scopes, `--advertise-host <bridge>` and the ACCOUNT_BACKUP_S3_* environment.
  4. A `/health` request from the worker VM over SSH to the advertised URL. No CI job had a VM call a service on the runner before, so an unreachable runner fails here instead of as a timeout inside a test.

The suite's S3 credentials are exported as E2E_BACKUP_S3_KEY and E2E_BACKUP_S3_SECRET: appended to `$GITHUB_ENV` (and masked) under Actions, otherwise only their names are printed. Their values are never printed.
"""

from __future__ import annotations

import os
import pathlib
import signal
import subprocess
import sys
from typing import TYPE_CHECKING

from rediacc_ci import log
from rediacc_ci.core import account, account_lifecycle
from rediacc_ci.drills import backup_local_plane, vm_ssh, wire
from rediacc_ci.testrun import start_account

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

NET_BASE = "192.168.111"
DEFAULT_PORT = "4900"
DEFAULT_WORKER = "11"
SCOPES = "license:read,license:activate,subscription:read,backup:read"
USAGE = "usage: PYTHONPATH=.ci python3 -m rediacc_ci.testrun.start_backup_plane [--port <n>] [--worker <n>]"
PROBE_TIMEOUT = 20


class PlaneError(Exception):
    """The backup plane cannot be brought up."""


def parse(argv: Sequence[str]) -> dict[str, str]:
    opts = {"port": os.environ.get("ACCOUNT_API_PORT") or DEFAULT_PORT, "worker": DEFAULT_WORKER}
    flags = {"--port": "port", "--worker": "worker"}
    i = 0
    while i < len(argv):
        flag = argv[i]
        if flag not in flags:
            raise ValueError(f"Unknown option: {flag}")
        if i + 1 >= len(argv) or argv[i + 1] == "":
            raise ValueError(f"{flag} needs a value")
        opts[flags[flag]] = argv[i + 1]
        i += 2
    return opts


def account_env(k: dict[str, str], bridge: str) -> dict[str, str]:
    """The environment that points the account server's backup plane at the local RustFS, spelled as the VM dials it."""
    return {
        "ACCOUNT_BACKUP_S3_ENDPOINT": f"http://{bridge}:{k['RUSTFS_PORT']}",
        "ACCOUNT_BACKUP_S3_BUCKET": k["PROBE_BUCKET"],
        "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID": k["RUSTFS_KEY"],
        "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY": k["RUSTFS_SECRET"],
    }


def start_storage(k: dict[str, str]) -> None:
    """RustFS plus the probe bucket; both must be there afterwards."""
    if k["PROBE_BUCKET"] == backup_local_plane.PRODUCTION_BUCKET:
        raise PlaneError(f"PROBE_BUCKET is the production bucket name {k['PROBE_BUCKET']!r}")
    account_lifecycle.start_rustfs()
    if not account.rustfs_alive(int(k["RUSTFS_PORT"])):
        raise PlaneError(f"RustFS does not answer on port {k['RUSTFS_PORT']} (is docker usable?)")
    failure = backup_local_plane.create_bucket(k)
    if failure is not None:
        raise PlaneError(f"could not create the bucket {k['PROBE_BUCKET']}: {failure}")
    log.info(f"backup bucket {k['PROBE_BUCKET']} ready")


def probe_from_vm(
    worker: str,
    url: str,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> None:
    """GET `<url>/health` from the worker VM; ssh's own failure (255) is told apart from the remote answer."""
    host = f"{NET_BASE}.{worker}"
    command = f"curl -fsS --max-time 10 {url}/health"
    argv = vm_ssh.ssh_argv(vm_ssh.default_user(), vm_ssh.default_key(), host, command)
    try:
        done = run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
            timeout=PROBE_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PlaneError(f"the probe from {host} did not complete: {exc}") from exc
    if done.returncode == vm_ssh.SSH_FAILED:
        raise PlaneError(f"cannot ssh to {host}: {(done.stderr or '').strip()}")
    if done.returncode != 0:
        raise PlaneError(
            f"{host} cannot reach {url}/health (curl rc={done.returncode}): {(done.stderr or '').strip()}"
        )
    log.info(f"{host} reaches {url}/health")


def export_credentials(k: dict[str, str]) -> None:
    """E2E_BACKUP_S3_KEY / E2E_BACKUP_S3_SECRET for the suite. Values go to `$GITHUB_ENV` only, masked; stdout carries names."""
    pairs = {"E2E_BACKUP_S3_KEY": k["RUSTFS_KEY"], "E2E_BACKUP_S3_SECRET": k["RUSTFS_SECRET"]}
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        for value in pairs.values():
            print(f"::add-mask::{value}")
        with open(github_env, "a", encoding="utf-8") as handle:
            for name, value in pairs.items():
                handle.write(f"{name}={value}\n")
        log.info("exported " + " and ".join(pairs) + " to $GITHUB_ENV")
        return
    for name in pairs:
        print(f"export {name}")
    log.info(
        "set the two names above to RUSTFS_KEY and RUSTFS_SECRET (dev default: docker-compose.yml)"
    )


def stop_account() -> None:
    """Stop the account server a failed probe leaves behind (its listener pid is recorded by start_account)."""
    pid_file = pathlib.Path(os.environ.get("RUNNER_TEMP") or "/tmp") / "account-for-e2e.pid"
    try:
        os.kill(int(pid_file.read_text().strip()), signal.SIGTERM)
    except (OSError, ValueError):
        return


def run(opts: dict[str, str]) -> int:
    k = backup_local_plane.knobs(os.environ)
    try:
        start_storage(k)
        bridge = wire.bridge_host(NET_BASE)
        if bridge is None:
            raise PlaneError(
                f"no interface on {NET_BASE}.0/24: the VM network is not up on this host"
            )
        os.environ.update(account_env(k, bridge))
        code = start_account.main(
            ["--port", opts["port"], "--scopes", SCOPES, "--advertise-host", bridge]
        )
        if code != 0:
            raise PlaneError(f"start_account exited {code}")
        try:
            probe_from_vm(opts["worker"], f"http://{bridge}:{opts['port']}")
        except PlaneError:
            stop_account()
            raise
        export_credentials(k)
    except PlaneError as exc:
        log.error(str(exc))
        return 1
    return 0


def main(argv: Sequence[str]) -> int:
    try:
        opts = parse(argv)
    except ValueError as exc:
        log.error(str(exc))
        print(USAGE, file=sys.stderr)
        return 2
    return run(opts)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
