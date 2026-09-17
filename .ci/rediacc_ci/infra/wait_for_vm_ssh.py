"""Port of `.ci/scripts/infra/wait-for-vm-ssh.sh`.

Blocks until EVERY named VM accepts SSH, then trusts its host key. `ops up`
returns once libvirt has started the domains, but the guest is still booting,
and every later step SSHes in, so waiting here turns a confusing mid-suite
connection refusal into one clear timeout.

`ssh-keyscan` RUNS ONLY AFTER A VM ANSWERS, which is the twin's whole ordering
argument and is preserved exactly: scanning a half-booted guest writes a key
that is about to be regenerated into `~/.ssh/known_hosts`, and every later
connection then fails host-key verification for a reason nobody can see.

36 attempts, 5 seconds apart, 180 seconds per VM. The twin's own header
explains the number (raised from 150s because this repo has a documented
incident where a DIFFERENT subsystem's 150s healthcheck budget was insufficient
on a downclocked host, and nested-KVM boot under contention is the same
physical phenomenon). The budget is hardcoded there, so it is hardcoded here:
inventing an env knob would be a new feature wearing a port's clothes, and the
first thing a knob does is get set to 1 in a test that then proves nothing
about the real timeout.

SIBLING, NOT DUPLICATE, of `verify_ssh.py`. Read that module's docstring for
the six-way behavioural comparison (host keys, identity, ports, budget, ANY vs
EVERY, and where ssh's stderr goes). The short version: the two twins share the
SHAPE of a poll loop and nothing else, they disagree on host-key policy in
opposite directions, and a shared helper would be smaller than the argument
list each caller would have to hand it. Neither port factors one out, because
factoring two live bash scripts together is a refactor, not a port.

EXTERNAL PROGRAMS ARE EXECUTED, NOT REIMPLEMENTED: `sleep`, `ssh`,
`ssh-keyscan`, `cut` and `nproc`. `sleep` in particular is why the differential
for the 36-attempt exhaustion path costs milliseconds instead of three minutes
-- both implementations resolve it through PATH, so one stub serves both. Using
`time.sleep` would leave the bash side stubbed and the Python side sleeping for
real, and a comparison timed differently on the two sides is not a comparison.
`cut`/`nproc` matter for a smaller reason: the failure line's exact text
(including `unavailable` / `unknown` when /proc or the binary is missing) is
what a human reads out of a CI log, and reading /proc/loadavg in Python would
reproduce it only until the day the two formats disagreed.

TWO HAZARDS IN THE TWIN, PRESERVED AND REPORTED, not repaired here:

  1. `SSH_AS="${SSH_USER:-$USER}"` under `set -u`. With neither SSH_USER nor
     USER exported the script dies with `USER: unbound variable` and exit 1,
     BEFORE printing anything of its own. That is a real environment: a
     `docker run` without `-e USER`, a systemd unit, a cron job. The clear
     message this script exists to produce is exactly what is missing there.
  2. `ssh-keyscan "$vm" >>~/.ssh/known_hosts 2>/dev/null` is the last command
     in the success branch and is NOT guarded, so under `set -e` a non-zero
     ssh-keyscan aborts the whole script -- after it has already announced "VM
     <vm> is SSH-ready", with a bare exit code and no message, and without
     waiting for any remaining VM. This port reproduces that, including the
     exit code.

Fixing either means editing a live CI script, which is the cutover box's call,
not this one's: the acceptance rule for this wave is that the port and the twin
agree.

A NOTE ON THE FAILURE LINE'S VOLATILITY, for whoever reads the differential.
`load average (1m 5m 15m): ...` reports live kernel data, so two runs a second
apart can legitimately differ. The differential masks that field rather than
asserting on it, and asserts the SHAPE (the label, three fields or the literal
`unavailable`, and a core count) instead. Asserting the numbers would produce a
test that fails on a busy machine for no reason, which is how a test gets
deleted.

K=5 LEDGER: `.ci/shadow/w7p6-wait-for-vm-ssh.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

from rediacc_ci import log

SELF = "wait-for-vm-ssh.py"

# The twin's hardcoded budget: 36 attempts x 5s = 180s per VM. Named so the
# failure message and the loop cannot drift apart the way they would if 36 and "180s" were two independent literals.
ATTEMPTS = 36
RETRY_SLEEP = "5"
BUDGET_LABEL = "180s"


def default_targets(net_base: str) -> list[str]:
    """`.1` and `.11` off VM_NET_BASE, the twin's two-host default.

    Deliberately not a range and not derived from anything: those are the two
    addresses `ops` assigns (the host and the first guest), and a port that
    generalised the list would wait for machines that do not exist.
    """
    return [f"{net_base}.1", f"{net_base}.11"]


def _load_line() -> str:
    """The twin's `load average ...` line, built from the same two programs.

    `cut -d' ' -f1-3 /proc/loadavg 2>/dev/null || echo unavailable` and
    `nproc 2>/dev/null || echo unknown`, both with stderr discarded and both
    falling back to a literal. A missing binary is `FileNotFoundError` in
    Python where bash gives 127, so it is caught and folded into the same
    fallback the twin's `||` produces.
    """

    def _sub(argv: list[str], fallback: str) -> str:
        try:
            # stdout=PIPE plus stderr=DEVNULL, never capture_output: the two
            # cannot be combined (subprocess raises), and the twin's `2>/dev/null` is a DISCARD rather than a capture.
            proc = subprocess.run(
                argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                check=False,
            )
        except (FileNotFoundError, PermissionError):
            return fallback
        if proc.returncode != 0:
            return fallback
        # Command substitution strips trailing newlines; `cut` emits one line.
        return proc.stdout.rstrip("\n")

    load = _sub(["cut", "-d ", "-f1-3", "/proc/loadavg"], "unavailable")
    cores = _sub(["nproc"], "unknown")
    return f"load average (1m 5m 15m): {load}, cores: {cores}"


def main(argv: list[str]) -> int:
    # The twin's order: both binaries first, then the target list, then $USER.
    for command in ("ssh", "ssh-keyscan"):
        if shutil.which(command) is None:
            log.error(f"Required command '{command}' is not available")
            return 1

    targets = list(argv)
    if not targets:
        net_base = os.environ.get("VM_NET_BASE", "")
        if not net_base:
            # `${VM_NET_BASE:?...}`: a bash diagnostic carrying the twin's path
            # and line number. Same stream, same exit, same position in the
            # sequence; the prefix names this file instead. See verify_ssh.py's
            # docstring, divergence 1, for why a line number is not reproduced.
            print(
                f"{SELF}: VM_NET_BASE: pass VM addresses as arguments, or set VM_NET_BASE",
                file=sys.stderr,
                flush=True,
            )
            return 1
        targets = default_targets(net_base)

    ssh_as = os.environ.get("SSH_USER") or ""
    if not ssh_as:
        # HAZARD 1, reproduced. `${SSH_USER:-$USER}` under `set -u` aborts when
        # USER is not exported either, and it aborts before any output.
        if "USER" not in os.environ:
            print(f"{SELF}: USER: unbound variable", file=sys.stderr, flush=True)
            return 1
        ssh_as = os.environ["USER"]

    # `mkdir -p ~/.ssh`. `expanduser` is `$HOME` with the same passwd fallback bash's tilde expansion uses.
    ssh_dir = pathlib.Path(os.path.expanduser("~")) / ".ssh"
    ssh_dir.mkdir(parents=True, exist_ok=True)
    known_hosts = ssh_dir / "known_hosts"

    for vm in targets:
        log.info(f"Waiting for {vm} as {ssh_as}...")
        ready = False
        for i in range(1, ATTEMPTS + 1):
            # `2>/dev/null` on the ssh call, stdout NOT redirected: the guest's `ready` reaches this process's stdout exactly as it does the twin's, and ssh's "Connection refused" chatter is dropped exactly as the twin drops it.
            probe = subprocess.run(
                [
                    "ssh",
                    "-o",
                    "StrictHostKeyChecking=accept-new",
                    "-o",
                    "ConnectTimeout=5",
                    f"{ssh_as}@{vm}",
                    "echo",
                    "ready",
                ],
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if probe.returncode == 0:
                log.info(f"VM {vm} is SSH-ready")
                with open(known_hosts, "ab") as fh:
                    scan = subprocess.run(
                        ["ssh-keyscan", vm],
                        stdout=fh,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                if scan.returncode != 0:
                    # HAZARD 2, reproduced: `set -e` kills the run here, after the "SSH-ready" line and before any remaining VM, with ssh-keyscan's own status and no message of its own.
                    return scan.returncode
                ready = True
                break
            log.info(f"Waiting for VM {vm} SSH... ({i}/{ATTEMPTS})")
            subprocess.run(["sleep", RETRY_SLEEP], check=False)
        if not ready:
            log.error(f"VM {vm} SSH not ready after {BUDGET_LABEL}")
            log.error(_load_line())
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
