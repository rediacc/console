"""Start the backup plane a CI leg needs for the `rdc backup browse --at` end-to-end tier: RustFS with the probe bucket, and an account server that mints backup-capable tokens and presigns against that bucket.

    PYTHONPATH=.ci python3 -m rediacc_ci.testrun.start_backup_plane [--port <n>] [--worker <n>] [--rebuild-renet | --no-rebuild-renet]
    PYTHONPATH=.ci python3 -m rediacc_ci.testrun.start_backup_plane [options] -- <command> [args...]

Five steps, each fatal on failure (the drill `drills.backup_local_plane` only warns on a bucket failure, since it starts a dev gateway that may reuse an existing bucket; a CI leg has nothing to reuse, so a missing bucket would surface minutes later as a presign error):

  1. RustFS on port 9100 (`account_lifecycle.start_rustfs`, published on every interface, so the bridge address below reaches it) and the `rediacc-backups-probe` bucket. NEVER `rediacc-backups`, the production name.
  2. The bridge address of the VM network (`wire.bridge_host("192.168.111")`). It is the host in the published account server URL (the licence's renewalUrl is stamped from it) and in ACCOUNT_BACKUP_S3_ENDPOINT, since SigV4 signs the Host header and the presigned URLs are dialled from the VM.
  3. ONE ED25519 signing pair, generated here (`start_account.generate_keys`) and handed to the account server through ACCOUNT_ED25519_PRIVATE_KEY / ACCOUNT_ED25519_PUBLIC_KEY. `rdc repo create` files the licence blob under the SIGNER's fingerprint (`/var/lib/rediacc/license/repos/<guid>/<fingerprint>.json`) and renet's license-status, snapshot and restore verbs look up the fingerprint of the key the build BAKED (private/renet/pkg/license/preferred.go), so a server with a throwaway key of its own signs licences no renet build can find. With `--rebuild-renet` (the default off Actions; in CI the workflow rebuilds after this step) renet is rebuilt with the public half exported, and the staged binaries are COPIED into a directory only this run uses (`pin_renet`), checked there to bake it (`--verify-renet`, below), and exported as RENET_BINARY_PATH, so a rebuild of `private/renet/bin` by another job cannot swap the key under the suite.
  4. `start_account` with the backup scopes, `--advertise-host <bridge>` and the ACCOUNT_BACKUP_S3_* environment. It publishes the public half as ACCOUNT_ED25519_PUBLIC_KEY (in `$GITHUB_ENV` under Actions, where the rebuild step reads it). The private half is never printed or written.
  5. Two requests from the worker VM over SSH: `/health` on the advertised URL, and any HTTP answer from ACCOUNT_BACKUP_S3_ENDPOINT (RustFS answers 403 to an anonymous GET). No CI job had a VM call a service on the runner before, so an unreachable account server or RustFS fails here instead of as a timeout inside a test.

The suite's S3 credentials are exported as E2E_BACKUP_S3_KEY and E2E_BACKUP_S3_SECRET: appended to `$GITHUB_ENV` (and masked, only when `GITHUB_ACTIONS` is true) when `$GITHUB_ENV` is set, otherwise only their names are printed. Their values are never printed. A local run exports nothing to a shell, so a chained command cannot see them: put it after `--` and it is exec'd with the full environment (account server, token, public key, S3 credentials, RENET_BINARY_PATH) once the plane is up, e.g. `start_backup_plane -- npm run e2e -- --test 31-backup-large-repo`. The GITHUB_ENV writes are unchanged.

`--verify-renet <binary>` does nothing but the preflight: it reads the key baked into each binary from its build info (`go version -m`, the `-X .../keys.ProductionPublicKey=` ldflag) and refuses, naming both fingerprints, when it is not ACCOUNT_ED25519_PUBLIC_KEY. The workflow runs it after its rebuild.
"""

from __future__ import annotations

import dataclasses
import os
import pathlib
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING

from rediacc_ci import log, paths
from rediacc_ci.core import account, account_lifecycle
from rediacc_ci.drills import backup_local_plane, vm_ssh, wire
from rediacc_ci.release import renet_key_gate
from rediacc_ci.testrun import start_account

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

NET_BASE = "192.168.111"
DEFAULT_PORT = "4900"
DEFAULT_WORKER = "11"
SCOPES = "license:read,license:activate,subscription:read,backup:read,backup:manage"
USAGE = (
    "usage: PYTHONPATH=.ci python3 -m rediacc_ci.testrun.start_backup_plane [--port <n>] [--worker <n>] [--rebuild-renet | --no-rebuild-renet]\n"
    "       PYTHONPATH=.ci python3 -m rediacc_ci.testrun.start_backup_plane --verify-renet <binary> [--verify-renet <binary> ...]\n"
    "       PYTHONPATH=.ci python3 -m rediacc_ci.testrun.start_backup_plane [options] -- <command> [args...]"
)
PROBE_TIMEOUT = 20
PUBLIC_KEY_ENV = "ACCOUNT_ED25519_PUBLIC_KEY"
PRIVATE_KEY_ENV = "ACCOUNT_ED25519_PRIVATE_KEY"
# The binaries a local rebuild stages: the host one and the two the CLI pushes to a machine of either architecture.
STAGED_RENETS = ("renet", "renet-linux-amd64", "renet-linux-arm64")
# The build-info reader is shared with the release gate (`rediacc_ci.release.renet_key_gate`).
SPKI_ED25519_HEADER = renet_key_gate.SPKI_ED25519_HEADER


class PlaneError(Exception):
    """The backup plane cannot be brought up."""


@dataclasses.dataclass
class Options:
    port: str
    worker: str
    rebuild_renet: bool
    verify: list[str] = dataclasses.field(default_factory=list)
    command: list[str] = dataclasses.field(default_factory=list)


def parse(argv: Sequence[str]) -> Options:
    # Everything after a bare `--` is the follow-on command (`--exec`-style): run with the plane's environment once the plane is up.
    command: list[str] = []
    if "--" in argv:
        split = list(argv).index("--")
        command = list(argv[split + 1 :])
        argv = argv[:split]
        if not command:
            raise ValueError("-- needs a command to run")
    values = {"port": os.environ.get("ACCOUNT_API_PORT") or DEFAULT_PORT, "worker": DEFAULT_WORKER}
    flags = {"--port": "port", "--worker": "worker"}
    # In CI the workflow rebuilds renet after this step (it needs renet to bring the VMs up first), so the rebuild here is a local default.
    rebuild = os.environ.get("GITHUB_ACTIONS") != "true"
    verify: list[str] = []
    i = 0
    while i < len(argv):
        flag = argv[i]
        if flag in ("--rebuild-renet", "--no-rebuild-renet"):
            rebuild = flag == "--rebuild-renet"
            i += 1
            continue
        if flag not in flags and flag != "--verify-renet":
            raise ValueError(f"Unknown option: {flag}")
        if i + 1 >= len(argv) or argv[i + 1] == "":
            raise ValueError(f"{flag} needs a value")
        if flag == "--verify-renet":
            verify.append(argv[i + 1])
        else:
            values[flags[flag]] = argv[i + 1]
        i += 2
    for name, value in values.items():
        if not (value.isascii() and value.isdigit()):
            raise ValueError(f"--{name} must be a number, got {value!r}")
    return Options(values["port"], values["worker"], rebuild, verify, command)


def key_fingerprint(public_key: str) -> str:
    """renet's publicKeyId, through the shared reader in `renet_key_gate`."""
    try:
        return renet_key_gate.key_fingerprint(public_key)
    except renet_key_gate.KeyGateError as exc:
        raise PlaneError(str(exc)) from exc


def baked_public_key(
    binary: str, run: Callable[..., subprocess.CompletedProcess] = subprocess.run
) -> str:
    """The key `-X .../keys.ProductionPublicKey=` baked into `binary`, read from its build info by the shared reader."""
    try:
        return renet_key_gate.baked_public_key(binary, run)
    except renet_key_gate.KeyGateError as exc:
        raise PlaneError(str(exc)) from exc


def verify_renet(
    binary: str,
    expected: str,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> None:
    """Refuse a renet whose baked key is not the account server's signing key, naming both fingerprints."""
    want = key_fingerprint(expected)
    have = key_fingerprint(baked_public_key(binary, run))
    if have != want:
        raise PlaneError(
            f"{binary} bakes key {have}, but the account server signs with {want}: "
            f"every licence it issues is filed as /var/lib/rediacc/license/repos/<guid>/{want}.json and this renet looks up {have}.json. "
            f"Rebuild renet with {PUBLIC_KEY_ENV} exported (PYTHONPATH=.ci python3 -m rediacc_ci.infra.build_renet)."
        )
    log.info(f"{binary} bakes the signing key {want}")


def signing_pair() -> tuple[str, str]:
    """ONE throwaway ED25519 pair (private, public) for the account server and the renet build."""
    try:
        keys = start_account.generate_keys()
    except start_account.LegError as exc:
        raise PlaneError(str(exc)) from exc
    return keys["edPriv"], keys["edPub"]


def rebuild_renet(
    public_key: str, run: Callable[..., subprocess.CompletedProcess] = subprocess.run
) -> None:
    """`build_renet` with the signing key's public half exported. The private half is kept out of the build's environment."""
    root = paths.repo_root()
    env = {k: v for k, v in os.environ.items() if k != PRIVATE_KEY_ENV}
    env[PUBLIC_KEY_ENV] = public_key
    env["PYTHONPATH"] = str(root / ".ci")
    log.step(f"Rebuilding renet with the signing key {key_fingerprint(public_key)}...")
    try:
        done = run(
            [sys.executable, "-m", "rediacc_ci.infra.build_renet"],
            cwd=str(root),
            env=env,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise PlaneError(f"could not run build_renet: {exc}") from exc
    if done.returncode != 0:
        raise PlaneError(f"build_renet exited {done.returncode}")


def staged_renets() -> list[str]:
    """The staged renet binaries that exist after a rebuild."""
    bin_dir = paths.repo_root() / "private" / "renet" / "bin"
    return [str(bin_dir / name) for name in STAGED_RENETS if (bin_dir / name).is_file()]


def pin_renet(
    binaries: Sequence[str],
    public_key: str,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> str:
    """Copy the rebuilt renet binaries into a directory only this run uses, verify the COPIES bake `public_key`, and return the host binary's path.

    `private/renet/bin` is shared: any `npm run ci`, `vm:check` or build in the same checkout rebuilds it WITHOUT the plane's key, and the CLI then syncs that binary to the workers, so every licence the plane signed is filed under a fingerprint the machine does not look up (`LICENSE_REQUIRED: missing: no license data` right after `License activated`; measured 2026-11-05, suite 26 K4). The CLI picks `renet-linux-<arch>` from the directory of the host binary (`renet-provisioner.ts`), so the three staged names travel together. A mismatch raises before anything is exported."""
    by_name = {os.path.basename(b): b for b in binaries}
    if "renet" not in by_name:
        raise PlaneError("the renet rebuild staged no host `renet` binary to pin")
    pinned = tempfile.mkdtemp(prefix="renet-backup-plane-")
    for name, source in by_name.items():
        shutil.copy2(source, os.path.join(pinned, name))
    for name in by_name:
        verify_renet(os.path.join(pinned, name), public_key, run)
    return os.path.join(pinned, "renet")


def export_renet_path(path: str) -> None:
    """RENET_BINARY_PATH for the suite: appended to `$GITHUB_ENV` when set, else printed as an `export` line (a path is not a secret)."""
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a", encoding="utf-8") as handle:
            handle.write(f"RENET_BINARY_PATH={path}\n")
        log.info("exported RENET_BINARY_PATH to $GITHUB_ENV")
        return
    print(f"export RENET_BINARY_PATH={path}")


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
    *,
    http_ok: bool = True,
) -> None:
    """GET `url` from the worker VM; ssh's own failure (255) is told apart from the remote answer. With `http_ok` false any HTTP status passes, so only reachability is tested."""
    host = f"{NET_BASE}.{worker}"
    flags = "-fsS" if http_ok else "-sS -o /dev/null"
    command = f"curl {flags} --max-time 10 {shlex.quote(url)}"
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
            f"{host} cannot reach {url} (curl rc={done.returncode}): {(done.stderr or '').strip()}"
        )
    log.info(f"{host} reaches {url}")


def export_credentials(k: dict[str, str]) -> None:
    """E2E_BACKUP_S3_KEY / E2E_BACKUP_S3_SECRET for the suite. Values go to `$GITHUB_ENV` only, masked on Actions and never printed anywhere else; stdout carries names."""
    pairs = {"E2E_BACKUP_S3_KEY": k["RUSTFS_KEY"], "E2E_BACKUP_S3_SECRET": k["RUSTFS_SECRET"]}
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        # A `::add-mask::<value>` line is a workflow command only the Actions runner consumes; anywhere else it is the secret in plain text in a terminal or a captured log.
        if os.environ.get("GITHUB_ACTIONS") == "true":
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


def exec_follow_on(
    command: Sequence[str],
    k: dict[str, str],
    execvpe: Callable[..., object] = os.execvpe,
) -> None:
    """Replace this process with `command`, run with the plane's environment: what a local run cannot get from `$GITHUB_ENV`.

    The environment already holds the account and S3 variables, the signing pair's public half and RENET_BINARY_PATH (set in-process by `run` and `start_account.publish`); the suite's two S3 credentials are added here. Nothing is printed. The account server runs in its own session, so it outlives the exec."""
    env = dict(os.environ)
    env["E2E_BACKUP_S3_KEY"] = k["RUSTFS_KEY"]
    env["E2E_BACKUP_S3_SECRET"] = k["RUSTFS_SECRET"]
    execvpe(command[0], list(command), env)


def stop_account() -> None:
    """Stop the account server a failed probe leaves behind (its listener pid is recorded by start_account)."""
    pid_file = pathlib.Path(os.environ.get("RUNNER_TEMP") or "/tmp") / "account-for-e2e.pid"
    try:
        os.kill(int(pid_file.read_text().strip()), signal.SIGTERM)
    except (OSError, ValueError):
        return


def verify_only(binaries: Sequence[str]) -> int:
    """The `--verify-renet` mode: the preflight alone, against ACCOUNT_ED25519_PUBLIC_KEY."""
    expected = os.environ.get(PUBLIC_KEY_ENV, "")
    try:
        if not expected:
            raise PlaneError(
                f"{PUBLIC_KEY_ENV} is not set: nothing to verify the renet build against (start_backup_plane publishes it)"
            )
        for binary in binaries:
            verify_renet(binary, expected)
    except PlaneError as exc:
        log.error(str(exc))
        return 1
    return 0


def run(opts: Options) -> int:
    if opts.verify:
        return verify_only(opts.verify)
    k = backup_local_plane.knobs(dict(os.environ))
    pinned: str | None = None
    try:
        start_storage(k)
        bridge = wire.bridge_host(NET_BASE)
        if bridge is None:
            raise PlaneError(
                f"no interface on {NET_BASE}.0/24: the VM network is not up on this host"
            )
        private_key, public_key = signing_pair()
        os.environ[PRIVATE_KEY_ENV] = private_key
        os.environ[PUBLIC_KEY_ENV] = public_key
        if opts.rebuild_renet:
            rebuild_renet(public_key)
            binaries = staged_renets()
            if not binaries:
                raise PlaneError("the renet rebuild staged no binary under private/renet/bin")
            pinned = pin_renet(binaries, public_key)
            os.environ["RENET_BINARY_PATH"] = pinned
        else:
            log.info(
                f"renet not rebuilt here; the caller rebuilds it with {PUBLIC_KEY_ENV} and runs --verify-renet"
            )
        s3_env = account_env(k, bridge)
        os.environ.update(s3_env)
        code = start_account.main(
            ["--port", opts.port, "--scopes", SCOPES, "--advertise-host", bridge]
        )
        if code != 0:
            raise PlaneError(f"start_account exited {code}")
        try:
            probe_from_vm(opts.worker, f"http://{bridge}:{opts.port}/health")
            probe_from_vm(opts.worker, s3_env["ACCOUNT_BACKUP_S3_ENDPOINT"] + "/", http_ok=False)
        except PlaneError:
            stop_account()
            raise
        export_credentials(k)
        if pinned:
            export_renet_path(pinned)
    except PlaneError as exc:
        log.error(str(exc))
        return 1
    if opts.command:
        try:
            exec_follow_on(opts.command, k)
        except OSError as exc:
            log.error(f"could not run {opts.command[0]}: {exc}")
            return 127
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
