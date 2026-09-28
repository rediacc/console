"""Collect per-VM KVM diagnostics after a failed E2E job.

A job that fails because a VM stopped answering SSH otherwise uploads only the harness's own reports, so the guest's side of the story is lost when the runner is recycled.
This collector reads, for every libvirt domain whose name starts with the prefix (default `rediacc`), the host-side record and, when SSH still answers, the guest-side record, and writes them under one directory that the job's failure artifact already uploads.

HOST SIDE (always, through `sudo -n virsh`, the same `sudo virsh` renet itself drives):
  domstate.txt   `virsh domstate --reason` and `virsh dominfo`.
  domain.xml     `virsh dumpxml`, which also names the console device.
  qemu.log       the tail of `/var/log/libvirt/qemu/<domain>.log`, where QEMU writes its own errors (KVM internal errors, guest panics, a killed process).
  console-log.txt  the tail of any `<log file=...>` configured on a serial or console device.
  console-live.txt  a bounded read of the console pty, when the console is a pty.

renet defines the console as `--console pty` with no log file (private/renet/pkg/infra/vm/kvm/driver.go), so libvirt keeps no history of the serial output.
console-live.txt is therefore only what the guest prints during the read window, and console-log.txt starts appearing on its own once the domain definition gains a `log.file`.

GUEST SIDE (only when an SSH probe succeeds): `journalctl -b --no-pager`, `cloud-init status --long` and `last -x`.

READ-ONLY: nothing is written to a domain, a pty or a guest.
BOUNDED: every command carries its own timeout, each VM has an overall deadline, VMs are collected in parallel, and every file is capped to its last MAX_FILE_BYTES.
SECRET-SAFE: every captured text passes through `redact()` before it is written, and stdout carries only names, states and sizes.
ALWAYS EXITS 0: it runs in a step attached to an already-failed job, where a non-zero exit would bury the real failure.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import getpass
import ipaddress
import os
import pathlib
import re
import signal
import subprocess
import sys
import tempfile
import time

MAX_FILE_BYTES = 4 * 1024 * 1024
DEFAULT_PREFIX = "rediacc"
# Every failure class the collection can raise; each is reported and swallowed, never propagated as a job failure.
_COLLECTOR_ERRORS = (
    OSError,
    ValueError,
    RuntimeError,
    UnicodeError,
    concurrent.futures.TimeoutError,
    subprocess.SubprocessError,
)

_SSH_OPTS = [
    "-o",
    "BatchMode=yes",
    "-o",
    "ConnectTimeout=10",
    "-o",
    "StrictHostKeyChecking=no",
    "-o",
    "UserKnownHostsFile=/dev/null",
    "-o",
    "LogLevel=ERROR",
]

_GUEST_COMMANDS = [
    ("guest-journal.txt", "sudo -n journalctl -b --no-pager 2>&1 || journalctl -b --no-pager 2>&1"),
    (
        "guest-cloud-init.txt",
        "sudo -n cloud-init status --long 2>&1 || cloud-init status --long 2>&1",
    ),
    ("guest-last.txt", "last -x 2>&1"),
]

_REDACTIONS = [
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL
        ),
        "[REDACTED PRIVATE KEY]",
    ),
    (re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"), "[REDACTED]"),
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 [REDACTED]"),
    (
        re.compile(
            r"(?i)((?:password|passwd|passphrase|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|authorization)[\"']?\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|\S+)"
        ),
        r"\1[REDACTED]",
    ),
    (re.compile(r"(?i)(://[^/\s:@]+:)[^@\s/]+@"), r"\1[REDACTED]@"),
]


def redact(text: str) -> str:
    """Mask credential-shaped values; the diagnostics never need them."""
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    return text


def _sudo() -> list[str]:
    return [] if os.geteuid() == 0 else ["sudo", "-n"]


def _run(argv: list[str], timeout: float) -> tuple[int | None, str]:
    """Run a command, returning (rc, combined output); rc is None on timeout or when it cannot start."""
    if timeout < 1:
        return None, "(skipped: per-VM deadline reached)\n"
    # coreutils `timeout` runs INSIDE sudo, so a root-owned child is killed by root.
    # A timeout enforced only from this unprivileged process cannot signal it, and its open pipe would then block the collector.
    cut = len(_sudo()) if argv[: len(_sudo())] == _sudo() else 0
    wrapped = [*argv[:cut], "timeout", "-k", "3", str(int(timeout)), *argv[cut:]]
    try:
        proc = subprocess.Popen(
            wrapped,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as exc:
        return None, f"(could not run {argv[0]}: {exc})\n"
    try:
        out, _ = proc.communicate(timeout=timeout + 10)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            os.killpg(proc.pid, signal.SIGKILL)
        try:
            out, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            out = b""
        return None, out.decode("utf-8", "replace") + f"\n(timed out after {timeout:.0f}s)\n"
    if proc.returncode in (124, 137) and argv[cut : cut + 1] != ["timeout"]:
        return None, out.decode("utf-8", "replace") + f"\n(timed out after {timeout:.0f}s)\n"
    return proc.returncode, out.decode("utf-8", "replace")


def _write(dest: pathlib.Path, text: str) -> None:
    data = redact(text).encode("utf-8", "replace")
    if len(data) > MAX_FILE_BYTES:
        data = b"(truncated to the last %d bytes)\n" % MAX_FILE_BYTES + data[-MAX_FILE_BYTES:]
    with contextlib.suppress(OSError):
        dest.write_bytes(data)


class _Deadline:
    def __init__(self, seconds: float) -> None:
        self.end = time.monotonic() + seconds

    def left(self, cap: float) -> float:
        return max(0.0, min(cap, self.end - time.monotonic()))


def list_domains(prefix: str) -> list[str]:
    rc, out = _run([*_sudo(), "virsh", "list", "--all", "--name"], 30)
    if rc != 0:
        return []
    return sorted(n.strip() for n in out.splitlines() if n.strip().startswith(prefix))


def _console_devices(xml_text: str) -> tuple[list[str], list[str]]:
    """(log files, pty paths) named by the domain's serial and console devices.

    Matched with regular expressions over `virsh dumpxml` output rather than an XML parser, since only two attributes of two element kinds are read.
    """
    logs: list[str] = []
    ptys: list[str] = []
    for match in re.finditer(r"<(serial|console)\b([^>]*)>(.*?)</\1>", xml_text, re.DOTALL):
        attrs, body = match.group(2), match.group(3)
        log = re.search(r"<log\b[^>]*\bfile=['\"]([^'\"]+)['\"]", body)
        if log and log.group(1) not in logs:
            logs.append(log.group(1))
        src = re.search(r"<source\b[^>]*\bpath=['\"]([^'\"]+)['\"]", body)
        if re.search(r"\btype=['\"]pty['\"]", attrs) and src and src.group(1) not in ptys:
            ptys.append(src.group(1))
    return logs, ptys


def _guest_ip(domain: str, xml_text: str, deadline: _Deadline) -> str | None:
    for source in ("arp", "lease"):
        _rc, out = _run(
            [*_sudo(), "virsh", "domifaddr", domain, "--source", source], deadline.left(15)
        )
        match = re.search(r"ipv4\s+(\d+\.\d+\.\d+\.\d+)/", out)
        if match:
            return match.group(1)
    # Fallback: renet's static addressing, <network base>.<VM_NET_OFFSET + id>, with the base read from the domain's own libvirt network.
    id_match = re.search(r"(\d+)$", domain)
    net_match = re.search(r"<source network=['\"]([^'\"]+)['\"]", xml_text)
    if not (id_match and net_match):
        return None
    _rc, net_xml = _run([*_sudo(), "virsh", "net-dumpxml", net_match.group(1)], deadline.left(15))
    ip_match = re.search(r"<ip address=['\"](\d+\.\d+\.\d+)\.\d+['\"]", net_xml)
    if not ip_match:
        return None
    try:
        host = int(os.environ.get("VM_NET_OFFSET") or 0) + int(id_match.group(1))
        return str(ipaddress.IPv4Address(f"{ip_match.group(1)}.{host}"))
    except ValueError:
        return None


def _ssh_base(ip: str) -> list[str]:
    # The same order as renet's resolveDataDir (private/renet/pkg/infra/opsconfig/config.go).
    data_dir = os.environ.get("RENET_DATA_DIR")
    if not data_dir and os.environ.get("CI") == "true":
        data_dir = str(pathlib.Path(os.environ.get("RUNNER_TEMP") or "/tmp") / "renet")
    if not data_dir:
        data_dir = str(pathlib.Path.home() / ".renet")
    key = pathlib.Path(data_dir) / "staging" / ".ssh" / "id_rsa"
    # The account renet's InitVM names as the VM user; an empty USER (a `docker exec` shell) still has an account.
    user = (
        os.environ.get("SSH_USER")
        or os.environ.get("SUDO_USER")
        or os.environ.get("USER")
        or getpass.getuser()
    )
    argv = ["ssh", *_SSH_OPTS]
    if key.is_file():
        argv += ["-i", str(key)]
        if not os.access(key, os.R_OK):
            argv = [*_sudo(), *argv]
    return [*argv, f"{user}@{ip}"]


def collect_vm(
    domain: str, out_dir: pathlib.Path, per_vm_timeout: float, console_seconds: float
) -> dict[str, str]:
    deadline = _Deadline(per_vm_timeout)
    dest = out_dir / domain
    dest.mkdir(parents=True, exist_ok=True)
    result = {"domain": domain}

    _rc, state = _run([*_sudo(), "virsh", "domstate", domain, "--reason"], deadline.left(15))
    _rc, info = _run([*_sudo(), "virsh", "dominfo", domain], deadline.left(15))
    _write(dest / "domstate.txt", state + "\n" + info)
    result["state"] = state.strip().splitlines()[0] if state.strip() else "unknown"

    _rc, xml_text = _run([*_sudo(), "virsh", "dumpxml", domain], deadline.left(15))
    _write(dest / "domain.xml", xml_text)

    tail = str(MAX_FILE_BYTES)
    _rc, qemu_log = _run(
        [*_sudo(), "tail", "-c", tail, f"/var/log/libvirt/qemu/{domain}.log"], deadline.left(15)
    )
    _write(dest / "qemu.log", qemu_log)

    logs, ptys = _console_devices(xml_text)
    if logs:
        parts = []
        for path in logs:
            _rc, text = _run([*_sudo(), "tail", "-c", tail, path], deadline.left(15))
            parts.append(f"==> {path} <==\n{text}")
        _write(dest / "console-log.txt", "\n".join(parts))
    if ptys and console_seconds > 0:
        parts = []
        for path in ptys:
            # `timeout` ends the read; its rc 124 is the expected outcome, not an error.
            _rc, text = _run(
                [*_sudo(), "timeout", str(int(console_seconds)), "cat", path],
                deadline.left(console_seconds + 5),
            )
            parts.append(
                f"==> {path} ({int(console_seconds)}s read window; renet keeps no console history) <==\n{text}"
            )
        _write(dest / "console-live.txt", "\n".join(parts))

    ip = _guest_ip(domain, xml_text, deadline)
    result["ip"] = ip or "unknown"
    if ip is None:
        result["ssh"] = "no address"
        return result
    base = _ssh_base(ip)
    rc, probe = _run([*base, "true"], deadline.left(20))
    if rc != 0:
        result["ssh"] = "unreachable"
        _write(dest / "ssh-probe.txt", f"ssh probe to {ip}: rc={rc}\n{probe}")
        return result
    result["ssh"] = "ok"
    for name, command in _GUEST_COMMANDS:
        _rc, text = _run([*base, command], deadline.left(60))
        _write(dest / name, text)
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", help="output directory (default: $RUNNER_TEMP/vm-diagnostics)")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX, help="libvirt domain name prefix")
    parser.add_argument(
        "--per-vm-timeout", type=float, default=120.0, help="overall seconds per VM"
    )
    parser.add_argument(
        "--console-seconds", type=float, default=5.0, help="console pty read window; 0 disables"
    )
    args = parser.parse_args(argv)

    if args.out:
        out_dir = pathlib.Path(args.out)
    else:
        runner_temp = os.environ.get("RUNNER_TEMP")
        out_dir = (
            pathlib.Path(runner_temp) if runner_temp else pathlib.Path(tempfile.mkdtemp())
        ) / "vm-diagnostics"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"vm diagnostics: cannot create {out_dir}: {exc}")
        return 0

    _rc, listing = _run([*_sudo(), "virsh", "list", "--all"], 30)
    _write(out_dir / "virsh-list.txt", listing)
    domains = list_domains(args.prefix)
    if not domains:
        print(f"vm diagnostics: no libvirt domain named {args.prefix}* (nothing collected)")
        return 0

    results: list[dict[str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(domains))) as pool:
        futures = {
            pool.submit(collect_vm, d, out_dir, args.per_vm_timeout, args.console_seconds): d
            for d in domains
        }
        for future, domain in futures.items():
            try:
                results.append(future.result(timeout=args.per_vm_timeout + 60))
            except (
                _COLLECTOR_ERRORS
            ) as exc:  # best-effort: one VM's failure must not stop the others
                results.append(
                    {"domain": domain, "state": f"collector error: {type(exc).__name__}"}
                )

    lines = [
        f"{r['domain']}: state={r.get('state', '?')} ip={r.get('ip', '?')} ssh={r.get('ssh', '?')}"
        for r in results
    ]
    _write(out_dir / "summary.txt", "\n".join(lines) + "\n")
    print(f"vm diagnostics: {len(results)} domain(s) under {out_dir}")
    for line in lines:
        print(f"  {line}")
    for path in sorted(out_dir.rglob("*")):
        if path.is_file():
            print(f"  {path.stat().st_size:>10} bytes  {path.relative_to(out_dir)}")
    return 0


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except SystemExit:
        pass
    except _COLLECTOR_ERRORS as exc:  # always exit 0, see the module docstring
        print(f"vm diagnostics: collector failed ({type(exc).__name__}); nothing further collected")
    raise SystemExit(0)
