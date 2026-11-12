"""`python -m rediacc_ci.lab.airgap apply|remove|check --vm <ip>` (PLAN-enterprise-tenants box C12): cut an ops VM off from the internet for an air-gapped install drill.

    apply   iptables and ip6tables: OUTPUT policy DROP, with only `lo` and ESTABLISHED,RELATED allowed out, so ssh from the host gateway (.254) keeps answering; the same DROP in DOCKER-USER, so containers are cut off too. Nothing is persisted: a reboot clears it.
    remove  the policies go back to ACCEPT and the rules this module added are deleted.
    check   runs ON the VM: `curl -m5` to ghcr.io, registry-1.docker.io, archive.ubuntu.com and download.docker.com and a DNS query to 1.1.1.1 must all FAIL while ssh answers. The OUTPUT DROP counter is printed as evidence.

Ops network only: an address outside 192.168.111.0/24 is refused before any ssh. The ops VMs are disposable development machines; no other machine may be cut off by this tool. Commands go through `drills.vm_ssh`, the one way a drill reaches an ops VM.

EXIT CODES. 0 done / check passed; 1 failed or check failed; 2 usage or refused address.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence

from rediacc_ci.drills import vm_ssh

OPS_VM_NETWORK = "192.168.111"
TAG = "rediacc-airgap"
TOOLS = ("iptables", "ip6tables")
HOSTS = ("ghcr.io", "registry-1.docker.io", "archive.ubuntu.com", "download.docker.com")
DNS_SERVER = "1.1.1.1"
SSH_MARK = "SSH-ANSWERS"
USAGE = "usage: python -m rediacc_ci.lab.airgap apply|remove|check --vm <ip>"

# One shell command's transport: argv in, (exit code, stdout+stderr) out.
Transport = Callable[[Sequence[str]], tuple[int, str]]

# A DNS A query for example.com, sent to DNS_SERVER; exit 0 only when an answer comes back.
DNS_PROBE = (
    "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(5);"
    "q=bytes.fromhex('1a2b01000001000000000000076578616d706c6503636f6d0000010001');"
    "s.sendto(q,('%s',53));s.recv(512)" % DNS_SERVER
)


def is_ops_vm_ip(ip: str) -> bool:
    """True only for a dotted IPv4 literal inside the ops network: a hostname, an IPv6 form or a look-alike is not an ops VM."""
    parts = ip.split(".")
    if len(parts) != 4 or not all(p.isascii() and p.isdigit() and int(p) <= 255 for p in parts):
        return False
    return ".".join(parts[:3]) == OPS_VM_NETWORK


def apply_script() -> str:
    """Idempotent: the module's own rules are removed first, then added once."""
    lines = ["set -e", remove_script(), ""]
    for tool in TOOLS:
        lines += [
            "%s -N DOCKER-USER 2>/dev/null || true" % tool,
            "%s -I OUTPUT 1 -m conntrack --ctstate ESTABLISHED,RELATED -m comment --comment %s -j ACCEPT"
            % (tool, TAG),
            "%s -I OUTPUT 1 -o lo -m comment --comment %s -j ACCEPT" % (tool, TAG),
            "%s -P OUTPUT DROP" % tool,
            "%s -I DOCKER-USER 1 -m conntrack --ctstate ESTABLISHED,RELATED -m comment --comment %s -j ACCEPT"
            % (tool, TAG),
            "%s -I DOCKER-USER 2 -m comment --comment %s -j DROP" % (tool, TAG),
        ]
    return "\n".join(lines)


def remove_script() -> str:
    lines = []
    for tool in TOOLS:
        lines.append("%s -P OUTPUT ACCEPT" % tool)
        lines.extend(
            "%s -S %s 2>/dev/null | grep -- '--comment %s' | sed 's/^-A/-D/' | while read -r r; do %s $r; done || true"
            % (tool, chain, TAG, tool)
            for chain in ("OUTPUT", "DOCKER-USER")
        )
    return "\n".join(lines)


def check_script() -> str:
    lines = ["echo %s" % SSH_MARK]
    lines.extend(
        "if curl -sS -m5 -o /dev/null https://%s/ >/dev/null 2>&1; then echo 'PROBE %s reached'; else echo 'PROBE %s blocked'; fi"
        % (host, host, host)
        for host in HOSTS
    )
    lines.append(
        "if python3 -c %s >/dev/null 2>&1; then echo 'PROBE dns:%s reached'; else echo 'PROBE dns:%s blocked'; fi"
        % (shlex.quote(DNS_PROBE), DNS_SERVER, DNS_SERVER)
    )
    lines.append("iptables -L OUTPUT -v -n -x | head -1")
    return "\n".join(lines)


def remote(script: str) -> str:
    return "sudo sh -c %s" % shlex.quote(script)


def ssh_transport(argv: Sequence[str]) -> tuple[int, str]:
    proc = subprocess.run(list(argv), capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout + proc.stderr


def vm_argv(ip: str, script: str, environ: dict[str, str] | None = None) -> list[str]:
    env = os.environ if environ is None else environ
    return vm_ssh.ssh_argv(vm_ssh.default_user(env), vm_ssh.default_key(env), ip, remote(script))


def judge_check(rc: int, out: str) -> tuple[bool, list[str]]:
    """(passed, evidence lines). Passes only when ssh answered, every probe is blocked, and OUTPUT's policy is DROP."""
    if rc == vm_ssh.SSH_FAILED:
        return False, ["ssh did not answer (rc=255): %s" % out.strip()[:200]]
    if SSH_MARK not in out:
        return False, ["ssh ran but the check script did not (rc=%d): %s" % (rc, out.strip()[:200])]
    expected = [*HOSTS, "dns:%s" % DNS_SERVER]
    seen = dict(re.findall(r"^PROBE (\S+) (reached|blocked)$", out, re.MULTILINE))
    evidence = ["ssh answers"]
    ok = True
    for name in expected:
        state = seen.get(name)
        evidence.append("%s %s" % (name, state or "no result"))
        ok = ok and state == "blocked"
    counter = re.search(r"Chain OUTPUT \(policy (\w+) (\d+) packets, (\d+) bytes\)", out)
    if counter is None:
        evidence.append("OUTPUT counter unreadable")
        return False, evidence
    evidence.append("OUTPUT policy %s, dropped %s packets, %s bytes" % counter.groups())
    return ok and counter.group(1) == "DROP", evidence


def run(verb: str, ip: str, transport: Transport = ssh_transport) -> int:
    if not is_ops_vm_ip(ip):
        print(
            "refused: %r is not inside %s.0/24, the ops network" % (ip, OPS_VM_NETWORK),
            file=sys.stderr,
        )
        return 2
    if verb == "check":
        rc, out = transport(vm_argv(ip, check_script()))
        passed, evidence = judge_check(rc, out)
        for line in evidence:
            print(line)
        print("air-gap check %s" % ("PASSED" if passed else "FAILED"))
        return 0 if passed else 1
    script = apply_script() if verb == "apply" else remove_script()
    rc, out = transport(vm_argv(ip, script))
    if rc != 0:
        print("%s failed on %s (rc=%d): %s" % (verb, ip, rc, out.strip()[:300]), file=sys.stderr)
        return 1
    print("%s done on %s" % (verb, ip))
    return 0


def main(argv: Sequence[str], transport: Transport = ssh_transport) -> int:
    args = list(argv)
    if len(args) != 3 or args[0] not in ("apply", "remove", "check") or args[1] != "--vm":
        print(USAGE, file=sys.stderr)
        return 2
    return run(args[0], args[2], transport)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
