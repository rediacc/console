"""Run private/elite/scripts/s3-conformance-probe.sh against the object store the elite job just started.

WHY. The probe checks the surface the backup data plane depends on (presigned PUT/GET, create-only PUT with
If-None-Match: *, HeadObject, DeleteObjects, multipart) and nothing in CI called it, so the pinned RustFS
image could regress on the load-bearing 412 with every job green (PLAN-backup-program A4d).

  python3 -m rediacc_ci.infra.elite_s3_probe             live: find the rustfs container, probe it, exit with the probe's status
  python3 -m rediacc_ci.infra.elite_s3_probe --selftest  controls: a conformant stub must pass, a stub that ignores
                                                         If-None-Match must FAIL the probe on create-only-conflict

ANTI-VACUITY. A missing container, an empty IP, missing credentials or a missing probe script is a loud failure
with the cause, never a skipped green. The credentials travel in the environment of the probe process only.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STUB = Path(__file__).resolve().with_name("elite_s3_probe_stub.py")
PREFIX = "elite_s3_probe"


class ProbeError(Exception):
    pass


def _die(msg: str) -> int:
    print(f"{PREFIX}: {msg}", file=sys.stderr)
    return 1


def _docker(*args: str) -> str:
    try:
        r = subprocess.run(["docker", *args], capture_output=True, text=True, check=False)
    except OSError as e:
        raise ProbeError(f"docker could not be run: {e}") from e
    if r.returncode != 0:
        raise ProbeError(r.stderr.strip())
    return r.stdout.strip()


def _run_probe(probe: Path, env_extra: dict[str, str], out=None) -> int:
    env = {**os.environ, **env_extra}
    return subprocess.run(
        ["bash", str(probe)],
        env=env,
        stdout=out,
        stderr=subprocess.STDOUT if out else None,
        check=False,
    ).returncode


def _start_stub(tmp: Path, *flags: str) -> tuple[subprocess.Popen[bytes], int]:
    ready, err = tmp / "ready", tmp / "stub.err"
    with ready.open("wb") as o, err.open("wb") as e:
        proc = subprocess.Popen([sys.executable, "-I", str(STUB), *flags], stdout=o, stderr=e)
    for _ in range(50):
        if ready.read_text().startswith("READY "):
            break
        time.sleep(0.1)
    first = ready.read_text().split()
    if len(first) < 2 or first[0] != "READY":
        proc.kill()
        raise ProbeError(f"stub store did not start: {err.read_text().strip()}")
    return proc, int(first[1])


def _stop(proc: subprocess.Popen[bytes]) -> None:
    proc.kill()
    proc.wait()


def _probe_stub(probe: Path, port: int, tmp: Path) -> tuple[int, str]:
    out = tmp / "probe.out"
    env = {
        "S3_ENDPOINT": f"http://127.0.0.1:{port}",
        "S3_BUCKET": "stub",
        "S3_ACCESS_KEY_ID": "stub",
        "S3_SECRET_ACCESS_KEY": "stub",
    }
    with out.open("wb") as f:
        rc = _run_probe(probe, env, f)
    return rc, out.read_text()


def selftest(probe: Path) -> int:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        proc, port = _start_stub(tmp)
        try:
            rc, text = _probe_stub(probe, port, tmp)
        finally:
            _stop(proc)
        if rc != 0:
            print(text, end="")
            return _die("CONTROL failed: the probe rejected the conformant stub")
        if "create-only-conflict" not in text:
            return _die("CONTROL failed: the probe never reached the create-only step")
        print("  PASS  conformant stub passes all probes")

        proc, port = _start_stub(tmp, "--ignore-if-none-match")
        try:
            rc, text = _probe_stub(probe, port, tmp)
        finally:
            _stop(proc)
        if rc == 0:
            print(text, end="")
            return _die("the probe PASSED a store that ignores If-None-Match")
        if "FAIL create-only-conflict" not in text:
            print(text, end="")
            return _die("the probe failed, but not on create-only-conflict")
        print(
            "  PASS  a non-conformant stub (ignores If-None-Match) is red on create-only-conflict"
        )
    print(f"{PREFIX}: selftest ok")
    return 0


def live(probe: Path) -> int:
    container = f"{os.environ.get('INSTANCE_NAME') or 'rediacc'}-rustfs"
    try:
        running = _docker("inspect", "-f", "{{.State.Running}}", container)
    except ProbeError as e:
        if str(e).startswith("docker could not be run"):
            raise
        running = ""
    if running != "true":
        return _die(
            f"container {container} is not running; the elite stack did not start its object store"
        )
    ips = _docker(
        "inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}", container
    ).split()
    if not ips:
        return _die(f"container {container} has no network address")
    ip = ips[0]
    try:
        access = _docker("exec", container, "printenv", "RUSTFS_ACCESS_KEY")
    except ProbeError:
        return _die(f"cannot read the store's access key from {container}")
    try:
        secret = _docker("exec", container, "printenv", "RUSTFS_SECRET_KEY")
    except ProbeError:
        return _die(f"cannot read the store's secret key from {container}")
    if not access or not secret:
        return _die(f"the store's credentials are empty in {container}")
    rc = _run_probe(
        probe,
        {
            "S3_ENDPOINT": f"http://{ip}:9000",
            "S3_BUCKET": os.environ.get("ELITE_S3_PROBE_BUCKET") or "rediacc-backups",
            "S3_ACCESS_KEY_ID": access,
            "S3_SECRET_ACCESS_KEY": secret,
        },
    )
    print(f"{PREFIX}: probe against {container} ({ip}) exited {rc}")
    return rc


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    probe = Path(
        os.environ.get("ELITE_S3_PROBE_SCRIPT")
        or ROOT / "private/elite/scripts/s3-conformance-probe.sh"
    )
    if not probe.is_file():
        return _die(
            f"probe script not found at {probe} (is the private/elite submodule checked out?)"
        )
    try:
        return selftest(probe) if args[:1] == ["--selftest"] else live(probe)
    except ProbeError as e:
        return _die(str(e))


if __name__ == "__main__":
    sys.exit(main())
