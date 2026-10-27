#!/usr/bin/env python3
"""Start the LOCAL backup control plane for the chunk-store round-trip proof.

Ported from `programs/backup-storage/start-local-plane.sh` (PLAN-retire-bash-oracles B5, W10).

    PYTHONPATH=.ci python3 -m rediacc_ci.drills.backup_local_plane

Two processes, both local, neither touching anything remote:

  1. RustFS (already running for `./run.sh account dev` config blobs) gains a second bucket, `rediacc-backups-probe`. NEVER `rediacc-backups`: that is the production name, and a local bucket wearing it is one env-var typo away from a test writing where production backups live.
  2. The account dev gateway on :4800, bound 0.0.0.0 so the worker VMs can reach it, carrying ACCOUNT_BACKUP_S3_* so `createBackupPlane` selects the S3 presign minter (the minter the operator chose for production).

THE HOST HEADER IS LOAD-BEARING. `renewalUrlFor` (routes/license.ts:36) derives the licence's renewalUrl from `envConfig.baseUrl`, which is `env.PUBLIC_SITE_URL ?? \\`${url.protocol}//${url.host}\\`` (app.ts:534). renet derives the backup SESSION url from that renewalUrl by suffix swap (backup_snapshot.go:540). So a licence issued over http://localhost:4800 stamps a renewalUrl no VM can reach, and the snapshot fails at session mint. Every account API call in this program therefore uses 192.168.111.254:4800.

Same reasoning for ACCOUNT_BACKUP_S3_ENDPOINT: the presigned URLs the server signs are handed to renet ON THE VM, and SigV4 covers the Host header, so the endpoint must be spelled exactly as the VM will dial it.

The gateway needs the DEV crypto keys, which come from Bitwarden through the `backup-plane` profile (`.ci/config/secret-supply.json` `consumers`), and the committed non-secret constants from `private/account/dev.defaults.env`. Both follow the shell-wins rule (`rediacc_ci.core.env`), so the knobs below (GATEWAY_PORT, RUSTFS_PORT, BRIDGE_HOST, RUSTFS_KEY, RUSTFS_SECRET) mean what they say. The profile deliberately binds no ACCOUNT_BACKUP_S3_* name: those are set here and point the gateway at the local RustFS bucket.

The process is REPLACED by the gateway (`bws_env exec`), so its exit status is this program's.

DELIBERATE DELTA FROM THE BASH (Rule T), tested in `test_drills_backup_local_plane.py`:

  * A bucket creation that fails for any reason other than "it already exists" is reported on stderr. The bash sent the whole `docker run` to `/dev/null` with `|| true`, so a missing docker or an unreachable RustFS surfaced minutes later as a gateway that could not presign, with nothing pointing back here. The gateway still starts: an existing bucket is the normal case and a transient failure is not a reason to refuse.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

from rediacc_ci import paths, well_known
from rediacc_ci.core import bws_env, env

PRODUCTION_BUCKET = "rediacc-backups"
ALREADY_THERE = ("BucketAlreadyOwnedByYou", "BucketAlreadyExists")
PROFILE = "backup-plane"
GATEWAY_COMMAND = ["npx", "--no-install", "tsx", "src/entry/dev-gateway.ts"]


def knobs(environ: dict[str, str]) -> dict[str, str]:
    """The tunables, each overridable from the environment."""
    return {
        "BRIDGE_HOST": environ.get("BRIDGE_HOST") or "192.168.111.254",
        "GATEWAY_PORT": environ.get("GATEWAY_PORT") or str(well_known.ACCOUNT_DEV_PORT),
        "RUSTFS_PORT": environ.get("RUSTFS_PORT") or "9100",
        "RUSTFS_KEY": environ.get("RUSTFS_KEY") or "configadmin",
        "RUSTFS_SECRET": environ.get("RUSTFS_SECRET") or "configadmin",
        "PROBE_BUCKET": environ.get("PROBE_BUCKET") or "rediacc-backups-probe",
        "LOG_DIR": environ.get("LOG_DIR") or "/tmp/backup-roundtrip",
    }


def bucket_command(k: dict[str, str]) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--network",
        "host",
        # `-e NAME` with no value: docker copies NAME from its own environment (`bucket_environment`), so the keys are on no argv (worklist #3a8d1f46).
        "-e",
        "AWS_ACCESS_KEY_ID",
        "-e",
        "AWS_SECRET_ACCESS_KEY",
        "-e",
        "AWS_DEFAULT_REGION=us-east-1",
        "amazon/aws-cli",
        "s3api",
        "create-bucket",
        "--bucket",
        k["PROBE_BUCKET"],
        "--endpoint-url",
        "http://127.0.0.1:%s" % k["RUSTFS_PORT"],
    ]


def bucket_environment(k: dict[str, str]) -> dict[str, str]:
    """docker's environment for `bucket_command`: this process's, plus the two RustFS keys its `-e NAME` flags copy into the container."""
    return {
        **os.environ,
        "AWS_ACCESS_KEY_ID": k["RUSTFS_KEY"],
        "AWS_SECRET_ACCESS_KEY": k["RUSTFS_SECRET"],
    }


def create_bucket(k: dict[str, str]) -> str | None:
    """Create the probe bucket. None on success or when it exists; otherwise the first line of why not."""
    try:
        proc = subprocess.run(
            bucket_command(k),
            env=bucket_environment(k),
            capture_output=True,
            text=True,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except OSError as exc:
        return "cannot run docker: %s" % exc.strerror
    if proc.returncode == 0:
        return None
    text = (proc.stderr + proc.stdout).strip()
    if any(marker in text for marker in ALREADY_THERE):
        return None
    return text.splitlines()[0] if text else "docker exited %d" % proc.returncode


def gateway_environment(k: dict[str, str], environ: dict[str, str]) -> dict[str, str]:
    """The environment the gateway starts with: the shell, the committed defaults, then the forced bucket wiring."""
    child = dict(environ)
    env.apply(paths.repo_root() / "private" / "account" / "dev.defaults.env", child)
    child.update(
        {
            "GATEWAY_PORT": k["GATEWAY_PORT"],
            "ACCOUNT_BACKUP_S3_ENDPOINT": "http://%s:%s" % (k["BRIDGE_HOST"], k["RUSTFS_PORT"]),
            "ACCOUNT_BACKUP_S3_BUCKET": k["PROBE_BUCKET"],
            "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID": k["RUSTFS_KEY"],
            "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY": k["RUSTFS_SECRET"],
            "CONFIG_R2_ENDPOINT": "http://127.0.0.1:%s" % k["RUSTFS_PORT"],
            "CONFIG_R2_BUCKET": "rediacc-configs",
            "CONFIG_R2_ACCESS_KEY_ID": k["RUSTFS_KEY"],
            "CONFIG_R2_SECRET_ACCESS_KEY": k["RUSTFS_SECRET"],
            "TEST_MODE": "true",
        }
    )
    return child


def main(argv: list[str] | None = None) -> int:
    del argv  # no arguments: every knob is an environment variable
    k = knobs(dict(os.environ))
    if k["PROBE_BUCKET"] == PRODUCTION_BUCKET:
        # The drill carries the same guard for the same reason: a harness that CAN point at production eventually will.
        print("REFUSING bucket 'rediacc-backups': that is the production name.", file=sys.stderr)
        return 1
    pathlib.Path(k["LOG_DIR"]).mkdir(parents=True, exist_ok=True)

    print("==> RustFS bucket %s on :%s" % (k["PROBE_BUCKET"], k["RUSTFS_PORT"]))
    problem = create_bucket(k)
    if problem:
        print(
            "WARNING: could not create bucket %s (%s); the gateway will start anyway."
            % (k["PROBE_BUCKET"], problem),
            file=sys.stderr,
        )

    print(
        "==> account dev gateway on :%s (ACCOUNT_BACKUP_S3_* -> %s)"
        % (k["GATEWAY_PORT"], k["PROBE_BUCKET"])
    )
    os.chdir(paths.repo_root() / "private" / "account")
    os.environ.update(gateway_environment(k, dict(os.environ)))
    sys.stdout.flush()
    return bws_env.main(["exec", "--profile", PROFILE, "--", *GATEWAY_COMMAND])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
