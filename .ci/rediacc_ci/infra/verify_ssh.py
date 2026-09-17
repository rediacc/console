"""Port of `.ci/scripts/infra/verify-ssh.sh`.

Polls one or more hosts until SSH answers, or fails after N attempts, and
succeeds as soon as ANY target answers. `ops up` returns when libvirt has
started the domain; sshd comes up later, and every later step SSHes in, so
waiting here turns a confusing mid-suite connection refusal into one clear
timeout with an attempt count. A target is `host` or `host:port` (the
`localhost:2201` shape `ops` emits).

HOST-KEY CHECKING STAYS OFF, and the twin's reason is carried over verbatim
rather than "improved": these are ephemeral CI VMs whose keys are regenerated
on every provision, so `StrictHostKeyChecking=no` with
`UserKnownHostsFile=/dev/null` is the only thing that survives a second run.
A port that quietly hardened this would break every caller on provision two.

RELATIONSHIP TO `wait_for_vm_ssh.py`, which is the sibling port in this box.
The two twins were written independently and SHARE NO CODE, not even through
`common.sh`: they each open-code their own poll loop, their own attempt
counter, and their own ssh argument list. The duplication is real but it is
NOT identical, and the differences are behavioural rather than cosmetic, so
neither port factors a shared helper out (that would be a refactor of two live
scripts, not a port):

  * host keys       verify-ssh REFUSES to learn them (`no` + /dev/null);
                    wait-for-vm-ssh LEARNS them (`accept-new`, then an
                    explicit `ssh-keyscan` append into ~/.ssh/known_hosts).
  * identity        verify-ssh requires `SSH_KEY` and passes `-i`;
                    wait-for-vm-ssh passes no identity at all.
  * ports           verify-ssh parses `host:port`; wait-for-vm-ssh does not.
  * budget          verify-ssh's `ATTEMPTS` is env-tunable (default 15);
                    wait-for-vm-ssh hardcodes 36.
  * quantifier      verify-ssh succeeds when ANY one target answers;
                    wait-for-vm-ssh requires EVERY target to answer.
  * ssh stderr      verify-ssh lets it through; wait-for-vm-ssh sends it to
                    /dev/null.

Only the 5-second inter-attempt sleep and the "poll a host over ssh" shape are
genuinely common, and a helper carrying just that would be smaller than the
argument list each caller would have to hand it.

`sleep` AND `whoami` ARE EXECUTED AS PROGRAMS, NOT REPLACED WITH THE PYTHON
EQUIVALENT, and both choices are load-bearing rather than lazy.

  `sleep` -- the twin runs the external `sleep(1)`. Using `time.sleep` here
  would make the two implementations respond DIFFERENTLY to the same PATH, and
  PATH is exactly the seam the differential drives: a stub `sleep` that returns
  instantly turns a 36-attempt exhaustion case from three minutes into
  milliseconds for the bash side and changes nothing at all for a `time.sleep`
  port. The two would then be timed differently while claiming to be compared.

  `whoami` -- `getpass.getuser()` is NOT the same function. It consults
  LOGNAME, USER, LNAME and USERNAME from the environment before it falls back
  to the password database, while `whoami(1)` reports the effective uid's name
  and nothing else. Under `sudo -E`, or in a container where USER is exported
  for something else, those two disagree, and the disagreement would land in
  the ssh login name.

DIVERGENCES THAT ARE DELIBERATE, all three in refusal text nobody parses:

  1. `${SSH_KEY:?SSH_KEY is required}` is a bash DIAGNOSTIC carrying the twin's
     own path and LINE NUMBER (`verify-ssh.sh: line 33: SSH_KEY: SSH_KEY is
     required`). Reproducing a line number would pin this port to the twin's
     current layout, so the port names itself and the variable instead. Same
     stream (stderr), same exit code (1), same ordering relative to the
     `require_cmd ssh` check above it.
  2. The usage line interpolates `$0`, and the two files cannot have the same
     name. The text is otherwise identical.
  3. A non-integer `ATTEMPTS` is a bash ARITHMETIC error (`abc` reads as an
     unset variable name and trips `set -u`; `3x` is "value too great for
     base"). Both exit 1 before any ssh call, and so does this port, with one
     message that says which value was rejected.

THE DEFECT THIS PORT PRESERVES, reported rather than fixed. On the FINAL
attempt the twin still prints "retrying in 5s..." and still sleeps 5 seconds
before giving up. The message is false at that point and the sleep is pure
latency on the failure path (75s of a 15-attempt run's tail is not, but the
last 5s are). It is preserved here because the acceptance rule for this wave is
byte-equivalence with the live twin; fixing it means changing both files in one
edit, which is a behaviour change to a live CI script and belongs to whoever
owns the cutover.

K=5 LEDGER: `.ci/shadow/w7p6-verify-ssh.observations.jsonl`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from rediacc_ci import log

SELF = "verify-ssh.py"

# The twin's own default, kept as a named constant so the differential can cite it rather than repeat the literal.
DEFAULT_ATTEMPTS = 15

# Seconds between full passes over the target list. Hardcoded in the twin too;
# there is no env knob and this port does not invent one.
RETRY_SLEEP = "5"


def split_target(target: str) -> tuple[str, str]:
    """`host[:port]` the way the twin splits it, character for character.

    `${target%%:*}` is everything before the FIRST colon and `${target##*:}` is
    everything after the LAST one, so `a:b:c` yields host `a` and port `c`.
    That is not a sensible parse, and it is reproduced exactly: an IPv6 literal
    goes through both implementations equally wrong, which is the property a
    differential is allowed to assert. `partition`/`rpartition` are the direct
    translation of the two bash operators.
    """
    if ":" not in target:
        return target, "22"
    return target.partition(":")[0], target.rpartition(":")[2]


def parse_attempts(raw: str) -> int | None:
    """The `ATTEMPTS` env value as bash's `((i<=ATTEMPTS))` would read it.

    None means "bash would have failed here", which is exit 1 before the first
    ssh call. Bash arithmetic accepts a leading sign and C-style bases (`0x10`
    is 16, `010` is 8), and this reproduces that trio because a value written
    with a leading zero silently meaning octal is precisely the kind of thing
    a port must not quietly re-interpret as decimal.

    NOT REPRODUCED, and stated rather than discovered later: bash would also
    evaluate `2+3`, `$((n))` and a bare name as a nested variable reference.
    Nothing in this repo passes ATTEMPTS anything but a decimal literal, and a
    Python expression evaluator here would be a larger attack surface than the
    behaviour it matched.
    """
    text = raw.strip()
    if not text:
        return None
    sign = 1
    if text[0] in "+-":
        if text[0] == "-":
            sign = -1
        text = text[1:]
    try:
        if text[:2].lower() == "0x":
            return sign * int(text, 16)
        if len(text) > 1 and text[0] == "0":
            return sign * int(text[1:], 8)
        return sign * int(text, 10)
    except ValueError:
        return None


def main(argv: list[str]) -> int:
    # ORDER MATTERS AND IS THE TWIN'S. require_cmd runs before the SSH_KEY test, which runs before the argument-count test. A caller with no ssh, no key and no arguments must be told about ssh first, same as today.
    if shutil.which("ssh") is None:
        log.error("Required command 'ssh' is not available")
        return 1

    ssh_key = os.environ.get("SSH_KEY", "")
    if not ssh_key:
        # See divergence 1 in the module docstring.
        print(f"{SELF}: SSH_KEY: SSH_KEY is required", file=sys.stderr, flush=True)
        return 1

    if len(argv) < 1:
        log.error(f"Usage: {sys.argv[0]} <host[:port]> ...")
        return 1

    # `${ATTEMPTS:-15}`: an empty value takes the default, an unset one too.
    #
    # PARSED HERE, REFUSED LATER, and the order is the twin's rather than the tidy one. Bash assigns ATTEMPTS as a plain string and does not evaluate it arithmetically until the `for ((...))` header, which is AFTER the chown below has already run. A port that validated eagerly would skip a chown the twin performs, so the verdict is computed now and acted on at the loop.
    attempts_raw = os.environ.get("ATTEMPTS") or str(DEFAULT_ATTEMPTS)
    attempts = parse_attempts(attempts_raw)

    user_name = os.environ.get("SSH_USER") or ""
    if not user_name:
        # `$(whoami)` under `set -e`: a failing substitution in an assignment aborts the script with the substitution's status, so this returns it.
        who = subprocess.run(["whoami"], capture_output=True, text=True, check=False)
        if who.returncode != 0:
            sys.stderr.write(who.stderr)
            sys.stderr.flush()
            return who.returncode
        user_name = who.stdout.strip()

    chown_path = os.environ.get("CHOWN_PATH", "")
    if chown_path:
        # `ops` writes the key as root; the twin chowns it back before reading
        # it. Not captured: sudo's own prompt and diagnostics belong on this process's stderr exactly as they do for the twin.
        who = subprocess.run(["whoami"], capture_output=True, text=True, check=False)
        if who.returncode != 0:
            sys.stderr.write(who.stderr)
            sys.stderr.flush()
            return who.returncode
        chown = subprocess.run(["sudo", "chown", "-R", who.stdout.strip(), chown_path], check=False)
        if chown.returncode != 0:
            return chown.returncode

    if attempts is None:
        # See divergence 3: bash fails in the loop header, not before it.
        print(f"{SELF}: ATTEMPTS: {attempts_raw!r} is not a number", file=sys.stderr, flush=True)
        return 1

    for i in range(1, attempts + 1):
        for target in argv:
            host, port = split_target(target)
            # STREAMS ARE INHERITED, NOT CAPTURED. The twin does not redirect ssh at all, so its banner, its "Connection refused" and its `SSH OK` all reach this process's own stdout and stderr. A
            # `capture_output=True` here would silently swallow every one of
            # them and the two implementations would print different things
            # while agreeing on the exit code.
            result = subprocess.run(
                [
                    "ssh",
                    "-i",
                    ssh_key,
                    "-p",
                    port,
                    "-o",
                    "StrictHostKeyChecking=no",
                    "-o",
                    "UserKnownHostsFile=/dev/null",
                    "-o",
                    "ConnectTimeout=5",
                    f"{user_name}@{host}",
                    "echo 'SSH OK'",
                ],
                check=False,
            )
            if result.returncode == 0:
                log.info(f"SSH connection successful via {target} on attempt {i}")
                return 0
            log.info(f"Attempt {i} on {target} failed")
        # THE FALSE LINE AND THE WASTED SLEEP ARE THE TWIN'S, on the last pass as much as on the first. See the docstring.
        log.info(f"Attempt {i} failed for all targets, retrying in 5s...")
        subprocess.run(["sleep", RETRY_SLEEP], check=False)

    log.error(f"SSH connection failed for all targets after {attempts} attempts")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
