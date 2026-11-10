"""K1 of agent/plans/PLAN-renet-down-before-kill.md (box K0): a repository's containers never stop unless its Rediaccfile `down()` has run and finished first, on every planned path. The rows assert the FIXED behaviour; on a renet without the stop hook the same drill records FAIL rows, which is the failing evidence (the plan's K1 CONTROL).

`vm_check.py` registers this module once, through `EXTRA_RENET_STEPS`, as the `K1` step of the renet phase; `--only K1` drags in P5. `ctx` is the running `VmCheck`: every VM action goes through its `./rdc.sh` helpers (`rdc`), its raw ssh recipe (`vm_ssh.ssh_argv` through `host_run`, the 192.168.111.* worker) and its ledger (`check`).

THE PROBE. Repository A is a grand of its own (autostart is refused on a fork), with autostart on; repository B is a fork of A (`A:<tag>`), with autostart off. Both carry the probe Rediaccfile: `up()` appends `up <epoch>` to `downproof.log` in the mount, and `down()` appends `down <epoch>` and then sleeps `DOWN_SLEEP_S` seconds. The line is written at the START of `down()`, so a `down` line at least `DOWN_SLEEP_S` before the daemon's next `ExecMainStartTimestamp` proves the stop waited for the whole `down()` (a stop that killed it part way restarts sooner). Every epoch comes from the worker's own clock: the probe's `date +%s`, `systemctl show` and `uptime -s` read through `date -d`.

THE ROWS. K1.0 A (autostart on) and B (autostart off) are up and each wrote an `up` line; K1.1 A's docker unit carries an `ExecStop` that runs `renet daemon stop-hook --network-id=<N>` and both `After=` lines (`rediacc-repo-shutdown.service` and the systemd-escaped mount unit); then the autostart-reconcile timer is paused until K1.7 (a tick recovers A, which runs no container, on every pass and rewrote its unit under K1.3; K1.4 and K1.6 run their own tick); K1.2 a raw `systemctl restart` of A's unit writes a `down` line at least `DOWN_SLEEP_S` before the new start; K1.3 A's unit loses its first `Environment=` line, `daemon-reload`, then `rdc repo up`: a `down` line before the restart and an `up` line after it; K1.4 the stop side drifts (ExecStop and TimeoutStopSec removed), one `renet repository reconcile` tick restores it and MainPID is unchanged; K1.5 A's runtime stamp is removed and `rdc machine converge` restarts A with a `down` line before the restart; K1.9 A's daemon is made SKEWED (its live socket renamed to the old-layout path, so it answers only there, as a daemon an older-layout renet started does), then `rdc machine converge` restarts it with a `down` line at least `DOWN_SLEEP_S` before the new start (down() through the old socket before the heal, renet b63746a), and the same again through `renet daemon restart` (the stop hook's old-socket fallback) with an `up` line after the restart; K1.10 A's unit loses its first `Environment=` line again, then the mount-only `rdc repo up --no-start` (renet's MountWithDocker): a `down` line before the restart and an `up` line after it; K1.6 the main-pointer renet is installed on the worker (`upgrade_converge.install_current_renet_script`), A is upped under it through a throwaway config, `rdc machine setup` installs the branch renet back, neither daemon restarts, and after one reconcile tick both units carry the new stop side; K1.8 `reboot.target`'s `JobTimeoutUSec` is 30 min or more; K1.7 `systemctl reboot`, then both A and B have a `down` line timestamped at least `DOWN_SLEEP_S` before `uptime -s`, and A is back up with an `up` line after the boot. K1.8 runs before K1.7 so a worker that does not come back still leaves its read.

TEARDOWN. B then A are deleted (A's autostart disabled first), the throwaway config files are removed, and a run that installed the main-pointer renet reverts the worker with `rdc machine setup`; anything that stays rides `ctx.sweep_leftovers`.

The CLI-free pieces (the probe text, the root scripts, the systemd path escape, and the parsers and verdicts of the log, the unit text, the daemon state and the job timeout) are pure functions, pinned by `tests/test_drills_down_before_kill.py` without a machine.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shlex
import shutil
import time
import types
import uuid
from typing import TYPE_CHECKING, Any

from rediacc_ci.core import local_common
from rediacc_ci.drills import lifecycle_privilege, upgrade_converge, vm_ssh
from rediacc_ci.well_known import DATASTORE_PATH, RUNTIME_DIR

if TYPE_CHECKING:
    from collections.abc import Callable

STEP_ID = "K1"

MOUNTS = DATASTORE_PATH + "/mounts"
LOG_FILE = "downproof.log"
REDIACCFILE = "Rediaccfile"
DOWN_SLEEP_S = 20
GRAND_SIZE = "1G"
SHUTDOWN_UNIT = "rediacc-repo-shutdown.service"
STOP_HOOK = "daemon stop-hook"
# Decision 7: the docker unit's TimeoutStopSec is the down cap (15 min) plus 2 min, the same in every unit.
STOP_TIMEOUT_S = 17 * 60
# Decision 7: the stop budget has to fit reboot.target's job timeout.
MIN_JOB_TIMEOUT_S = 30 * 60
# K1.7 waits out the whole stop budget plus a boot: a shutdown that uses its 17 minutes is not a failed reboot.
REBOOT_WAIT_S = STOP_TIMEOUT_S + 5 * 60
BACK_UP_WAIT_S = 600
POLL_S = 10
# The renet commit the console's main branch points at; K1.6 builds and installs it.
MAIN_POINTER = "origin/main:private/renet"


# --------------------------------------------------------------------------- probe and scripts


def probe_rediaccfile() -> str:
    """The probe Rediaccfile. `up()` appends `up <epoch>`; `down()` appends `down <epoch>` first and then sleeps, so the line's epoch is when `down()` started."""
    return (
        "#!/bin/bash\n"
        "up() {\n"
        '  echo "up $(date +%%s)" >> "$REDIACC_WORKING_DIR/%(log)s"\n'
        "}\n"
        "down() {\n"
        '  echo "down $(date +%%s)" >> "$REDIACC_WORKING_DIR/%(log)s"\n'
        "  sleep %(sleep)d\n"
        "}\n"
    ) % {"log": LOG_FILE, "sleep": DOWN_SLEEP_S}


def daemon_unit(network_id: int | str) -> str:
    """The systemd unit of a repository's Docker daemon."""
    return lifecycle_privilege.daemon_unit(network_id)


def mount_path(guid: str) -> str:
    """The host mount of a repository, `<datastore>/mounts/<guid>`."""
    return "%s/%s" % (MOUNTS, guid)


def systemd_escape_path(path: str) -> str:
    """`systemd-escape --path`: slashes collapsed and trimmed, each `/` turned into `-`, and every byte outside `[A-Za-z0-9:_.]` (and a leading `.`) written as `\\xNN`."""
    norm = "/".join(seg for seg in path.split("/") if seg)
    if not norm:
        return "-"
    out: list[str] = []
    for i, ch in enumerate(norm):
        if ch == "/":
            out.append("-")
        elif ch.isascii() and (ch.isalnum() or ch in ":_.") and not (i == 0 and ch == "."):
            out.append(ch)
        else:
            out.extend("\\x%02x" % b for b in ch.encode("utf-8"))
    return "".join(out)


def mount_unit(guid: str) -> str:
    """The mount unit systemd derives for a repository's mount path."""
    return systemd_escape_path(mount_path(guid)) + ".mount"


def state_script(network_id: int | str) -> str:
    """Root on the worker: the worker's clock (`NOW`), the unit's `MAINPID`, its `ExecMainStartTimestamp` as an epoch (`START`, 0 when it never started) and whether it is `ACTIVE`."""
    unit = shlex.quote(daemon_unit(network_id))
    return (
        "echo NOW=$(date +%%s); "
        "echo MAINPID=$(systemctl show -p MainPID --value %(u)s); "
        "ts=$(systemctl show -p ExecMainStartTimestamp --value %(u)s); "
        'if [ -n "$ts" ]; then echo START=$(date -d "$ts" +%%s); else echo START=0; fi; '
        "echo ACTIVE=$(systemctl is-active %(u)s)"
    ) % {"u": unit}


def unit_text_script(network_id: int | str) -> str:
    """Root on the worker: the docker unit's text as systemd reads it."""
    return "systemctl cat %s" % shlex.quote(daemon_unit(network_id))


def restart_script(network_id: int | str) -> str:
    """Root on the worker: the restart K1.2 makes, from outside renet."""
    return "systemctl restart %s" % shlex.quote(daemon_unit(network_id))


def _edit_unit_script(network_id: int | str, sed_expr: str) -> str:
    unit = shlex.quote(daemon_unit(network_id))
    return (
        "set -e; f=$(systemctl show -p FragmentPath --value %(u)s); "
        'test -n "$f"; b=$(mktemp); cp "$f" "$b"; sed -i %(expr)s "$f"; '
        # A sed that matches nothing exits 0, so the row would pass with the unit untouched.
        'if cmp -s "$f" "$b"; then rm -f "$b"; echo "UNCHANGED=$f"; exit 3; fi; rm -f "$b"; '
        "systemctl daemon-reload; echo EDITED=$f"
    ) % {"u": unit, "expr": shlex.quote(sed_expr)}


def drop_environment_script(network_id: int | str) -> str:
    """Root on the worker: the unit file loses its FIRST `Environment=` line (a start-side change), then `daemon-reload`. Nothing restarts here."""
    return _edit_unit_script(network_id, "0,/^Environment=/{/^Environment=/d}")


def drop_stop_side_script(network_id: int | str) -> str:
    """Root on the worker: the unit file loses its `ExecStop=` and `TimeoutStopSec=` lines (a stop-side-only drift), then `daemon-reload`."""
    return _edit_unit_script(network_id, "/^ExecStop=/d;/^TimeoutStopSec=/d")


def remove_stamp_script(network_id: int | str) -> str:
    """Root on the worker: remove the runtime stamp so the converge pass sees `no_stamp` for this network."""
    return "rm -f %s && echo REMOVED" % shlex.quote(upgrade_converge.runtime_stamp_path(network_id))


def current_socket(network_id: int | str) -> str:
    """The daemon's Docker socket of the current layout, `<runtime>/net-<N>/docker-<N>.sock` (runpaths.DockerSocket)."""
    n = int(network_id)
    return "%s/net-%d/docker-%d.sock" % (RUNTIME_DIR, n, n)


def legacy_socket(network_id: int | str) -> str:
    """The daemon's Docker socket of the layout before net-<N>/, `<runtime>/docker-<N>.sock` (daemon.LegacyDockerSocket)."""
    return "%s/docker-%d.sock" % (RUNTIME_DIR, int(network_id))


def plant_skew_script(network_id: int | str) -> str:
    """Root on the worker: make the running daemon a SKEWED one, as an older-layout renet left it. The live socket is renamed to the old-layout path: a listening unix socket keeps serving under its new name, so the daemon answers only on `legacy_socket` and nothing is at `current_socket`, which daemon.SupervisorSkewed reads as an active unit with the old layout's socket on disk."""
    return (
        "set -e; cur=%(cur)s; old=%(old)s; "
        'test -S "$cur"; mv "$cur" "$old"; test -S "$old"; test ! -e "$cur"; echo PLANTED=$old'
    ) % {
        "cur": shlex.quote(current_socket(network_id)),
        "old": shlex.quote(legacy_socket(network_id)),
    }


def daemon_restart_script(network_id: int | str) -> str:
    """Root on the worker: `renet daemon restart` of the network's daemon (its ExecStop hook runs down(), then up() runs after the restart)."""
    return "renet daemon restart --network-id=%d" % int(network_id)


def read_log_script(guid: str) -> str:
    """Root on the worker: the probe's log in the repository's mount (empty when it does not exist)."""
    return "cat %s 2>/dev/null || true" % shlex.quote("%s/%s" % (mount_path(guid), LOG_FILE))


RECONCILE_TIMER = "rediacc-autostart-reconcile.timer"
RECONCILE_SERVICE = "rediacc-autostart-reconcile.service"
PAUSE_WAIT_S = 900


def pause_reconcile_script() -> str:
    """Root on the worker: stop the autostart-reconcile timer and wait out a tick already running (`PAUSED` on success). A tick recovers an autostart repository that runs no container on every pass, rewriting its unit and restarting its daemon, so it races the rows that drift the unit and judge the restart; K1.4 and K1.6 run their own tick."""
    return (
        "systemctl stop %(t)s; i=0; while [ $i -lt %(n)d ]; do "
        "s=$(systemctl is-active %(s)s || true); "
        'case "$s" in active|activating|deactivating|reloading) sleep 1; i=$((i+1));; '
        '*) echo PAUSED; exit 0;; esac; done; echo "STILL=$s"; exit 1'
    ) % {"t": RECONCILE_TIMER, "s": RECONCILE_SERVICE, "n": PAUSE_WAIT_S}


def resume_reconcile_script() -> str:
    """Root on the worker: start the autostart-reconcile timer again."""
    return "systemctl start %s" % RECONCILE_TIMER


def reconcile_script() -> str:
    """Root on the worker: one reconcile tick, what the autostart-reconcile timer runs."""
    return lifecycle_privilege.reconcile_script(DATASTORE_PATH)


def boot_script() -> str:
    """Root on the worker: the boot time as an epoch (`BOOT`)."""
    return 'echo BOOT=$(date -d "$(uptime -s)" +%s)'


def reboot_script() -> str:
    """Root on the worker: the reboot K1.7 makes. The ssh session dies with it, so its exit status is not read."""
    return "systemctl reboot"


def job_timeout_script() -> str:
    """Root on the worker: reboot.target's job timeout."""
    return "systemctl show reboot.target -p JobTimeoutUSec --value"


def build_main_renet_script(src_dir: str, out_binary: str, commit: str) -> str:
    """The shell that builds the renet at `commit` the way `./rdc.sh` builds the branch one (`build.sh dev`, licence key from the environment) in a shared clone of private/renet, and installs the binary at `out_binary`. private/renet/bin is never touched."""
    src = shlex.quote(src_dir)
    return (
        "set -eu\n"
        "rm -rf %(src)s\n"
        "git clone --quiet --shared --no-checkout private/renet %(src)s\n"
        "git -C %(src)s -c advice.detachedHead=false checkout --quiet %(sha)s\n"
        "(cd %(src)s && ./build.sh dev)\n"
        "install -m 0755 %(src)s/bin/renet %(out)s\n"
        % {"src": src, "out": shlex.quote(out_binary), "sha": shlex.quote(commit)}
    )


# --------------------------------------------------------------------------- parsers


def parse_log(text: str) -> list[tuple[str, int]]:
    """The `up <epoch>` and `down <epoch>` lines of the probe's log, in file order; any other line is ignored."""
    found: list[tuple[str, int]] = []
    for line in text.splitlines():
        m = re.match(r"^(up|down) (\d+)\s*$", line.strip())
        if m:
            found.append((m.group(1), int(m.group(2))))
    return found


def parse_kv_ints(text: str) -> dict[str, int]:
    """The `KEY=<integer>` lines of a root script's output; a non-integer value is left out."""
    found: dict[str, int] = {}
    for line in text.splitlines():
        m = re.match(r"^([A-Z]+)=(-?\d+)\s*$", line.strip())
        if m:
            found[m.group(1)] = int(m.group(2))
    return found


def parse_state(text: str) -> dict[str, Any]:
    """The output of `state_script`: `now`, `pid` and `start` as integers (0 when missing) and `active` as a string."""
    ints = parse_kv_ints(text)
    active = ""
    for line in text.splitlines():
        if line.startswith("ACTIVE="):
            active = line.split("=", 1)[1].strip()
    return {
        "now": ints.get("NOW", 0),
        "pid": ints.get("MAINPID", 0),
        "start": ints.get("START", 0),
        "active": active,
    }


def parse_timespan(text: str) -> float | None:
    """Seconds in a systemd time span (`1020`, `17min`, `1h 30min`, `30min 5s`, `500ms`); `inf` for `infinity`; None when the text is not one."""
    value = text.strip()
    if value == "infinity":
        return float("inf")
    if re.fullmatch(r"\d+", value):
        return float(value)
    units = {
        "us": 1e-6,
        "ms": 1e-3,
        "s": 1.0,
        "sec": 1.0,
        "m": 60.0,
        "min": 60.0,
        "h": 3600.0,
        "hr": 3600.0,
        "d": 86400.0,
    }
    parts = re.findall(r"(\d+(?:\.\d+)?)\s*([a-z]+)", value)
    if not parts or re.sub(r"(\d+(?:\.\d+)?)\s*([a-z]+)", "", value).strip():
        return None
    total = 0.0
    for num, unit in parts:
        if unit not in units:
            return None
        total += float(num) * units[unit]
    return total


def parse_unit(text: str) -> dict[str, Any]:
    """The facts K1 reads from a unit's text: every `ExecStop=` value, the union of the `After=` units, the `TimeoutStopSec=` span in seconds (None when absent or unreadable) and the `Environment=` values. `systemctl cat` comment lines are skipped."""
    exec_stop: list[str] = []
    after: set[str] = set()
    env: list[str] = []
    timeout: float | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")) or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key == "ExecStop":
            if value:
                exec_stop.append(value)
            else:
                exec_stop.clear()  # systemd: an empty assignment resets the earlier ExecStop= list
        elif key == "After":
            after.update(value.split())
        elif key == "Environment":
            env.append(value)
        elif key == "TimeoutStopSec":
            timeout = parse_timespan(value)
    return {"exec_stop": exec_stop, "after": after, "timeout_stop_s": timeout, "environment": env}


def runs_stop_hook(command: str, network_id: int | str) -> bool:
    """True when an `ExecStop=` command runs `daemon stop-hook` for `network_id` (`--network-id=N` or `--network-id N`)."""
    if STOP_HOOK not in " ".join(command.split()):
        return False
    m = re.search(r"--network-id(?:=|\s+)(\d+)\b", command)
    return m is not None and m.group(1) == str(int(network_id))


# --------------------------------------------------------------------------- verdicts


def unit_order_verdict(unit: dict[str, Any], network_id: int | str, guid: str) -> tuple[bool, str]:
    """(ok, evidence) of K1.1: an `ExecStop=` runs the stop hook for this network, and `After=` names the shutdown unit and the repository's mount unit."""
    hook = any(runs_stop_hook(c, network_id) for c in unit["exec_stop"])
    want_mount = mount_unit(guid)
    shut = SHUTDOWN_UNIT in unit["after"]
    mnt = want_mount in unit["after"]
    return (
        hook and shut and mnt,
        "stop_hook=%s after_shutdown=%s after_mount=%s (%s) exec_stop=%s"
        % (
            hook,
            shut,
            mnt,
            want_mount,
            unit["exec_stop"] or "<none>",
        ),
    )


def stop_side_verdict(unit: dict[str, Any], network_id: int | str, guid: str) -> tuple[bool, str]:
    """(ok, evidence) of a complete stop side: K1.1's facts plus `TimeoutStopSec` at the down cap plus 2 min."""
    ok, why = unit_order_verdict(unit, network_id, guid)
    t = unit["timeout_stop_s"]
    t_ok = t is not None and t == STOP_TIMEOUT_S
    return ok and t_ok, "%s timeout_stop_s=%s (want %d)" % (why, t, STOP_TIMEOUT_S)


def restarted(issued: int, at: int, pids: tuple[int, int] | None = None) -> bool:
    """Whether the daemon restarted after the drill acted: its MainPID changed (both readings non-zero), or its start is after `issued`. Both clocks read whole seconds, so a restart within the second the drill acted shows only in the MainPID (vm:check run vmc-11060119-8cbbc0 K1.9 read one as "nothing restarted")."""
    if pids is not None and pids[0] and pids[1] and pids[0] != pids[1]:
        return True
    return at > issued


def down_before_verdict(
    events: list[tuple[str, int]],
    issued: int,
    at: int,
    gap: int = DOWN_SLEEP_S,
    pids: tuple[int, int] | None = None,
) -> tuple[bool, str]:
    """(ok, evidence): a `down` line written no earlier than `issued` (when the drill acted) and at least `gap` seconds before `at` (the daemon's new start, or the boot), and a restart or reboot after `issued` (`restarted`: a later start, or a MainPID change when `pids` = (before, after) is given). A log with no such line is a FAIL, which is the K1 CONTROL."""
    if not issued or not at:
        return False, "no reading: issued=%s at=%s" % (issued, at)
    if not restarted(issued, at, pids):
        tail = " and MainPID stayed %d" % pids[1] if pids is not None else ""
        return False, "nothing restarted: start %d is not after the action at %d%s" % (
            at,
            issued,
            tail,
        )
    downs = [ts for kind, ts in events if kind == "down" and ts >= issued]
    good = [ts for ts in downs if ts + gap <= at]
    if good:
        return True, "down at %d, %ds before %d (issued %d)" % (good[0], at - good[0], at, issued)
    if downs:
        return False, "down at %s is less than %ds before %d: down() did not finish first" % (
            downs,
            gap,
            at,
        )
    return False, "no down line between the action at %d and %d" % (issued, at)


def up_after_verdict(events: list[tuple[str, int]], at: int) -> tuple[bool, str]:
    """(ok, evidence): an `up` line written at or after `at` (the new start, or the boot)."""
    ups = [ts for kind, ts in events if kind == "up" and at and ts >= at]
    if ups:
        return True, "up at %d (start %d)" % (ups[0], at)
    return False, "no up line at or after %d" % at


def up_written_verdict(events: list[tuple[str, int]]) -> tuple[bool, str]:
    """(ok, evidence) of K1.0: the probe's `up()` ran at least once."""
    ups = [ts for kind, ts in events if kind == "up"]
    return bool(ups), "up lines %s" % (ups or "<none>")


def pid_unchanged_verdict(before: int, after: int) -> tuple[bool, str]:
    """(ok, evidence): the daemon's MainPID is the same non-zero pid before and after."""
    return bool(before) and before == after, "MainPID before=%s after=%s" % (before, after)


def job_timeout_verdict(text: str) -> tuple[bool, str]:
    """(ok, evidence) of K1.8: reboot.target's job timeout is at least `MIN_JOB_TIMEOUT_S` (`infinity` passes)."""
    secs = parse_timespan(text)
    if secs is None:
        return False, "unreadable JobTimeoutUSec %r" % text.strip()
    return secs >= MIN_JOB_TIMEOUT_S, "JobTimeoutUSec=%s (%ss, want >= %d)" % (
        text.strip(),
        secs,
        MIN_JOB_TIMEOUT_S,
    )


def repo_names(tags: tuple[str, str]) -> tuple[str, str]:
    """A's grand name and B's tag, from the run's fork tag: `k1-<stem>` and `k1b`. A grand is not a fork of the run's parent, so the stale-fork sweep never reads it."""
    stem = tags[0].removesuffix("-a")
    return "k1-%s" % stem, "k1b"


def config_name(run_id: str) -> str:
    """The throwaway config of K1.6, e.g. `k1-vmc-11051000-abcdef`."""
    return "k1-%s" % run_id


def _clip(text: str, limit: int = 200) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "..."


# --------------------------------------------------------------------------- live


def run(ctx: Any) -> None:
    """The live K1 step. Records K1 rows on `ctx`; deletes its repositories and config, reverts the worker's renet when K1.6 changed it, and appends any leftover to `ctx.sweep_leftovers`."""
    _LiveK1(ctx).execute()


# The registration entry vm_check's EXTRA_RENET_STEPS takes: (step id, the steps `--only` drags in, the live function). K1 builds its own grand, and P5 is the plan's stated dependency (the run's fleet and machine in hand).
STEP = (STEP_ID, ("P5",), run)


class _LiveK1:
    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self.grand, self.tag_b = repo_names(ctx.tags)
        self.ref_a = self.grand
        self.ref_b = "%s:%s" % (self.grand, self.tag_b)
        self.nids: dict[str, int] = {}
        self.guids: dict[str, str] = {}
        self.created_grand = False
        self.created_fork = False
        self.autostart_enabled = False
        self.cfg = config_name(ctx.run_id)
        self.created_cfg = False
        self.main_installed = False
        self.reconcile_paused = False
        self.tmp = pathlib.Path(ctx.work) / ("k1-%s" % ctx.run_id)
        self.sleep = time.sleep

    # -- helpers ---------------------------------------------------------------

    def check(
        self, desc: str, ok: bool, res: Any = None, evidence: str = "", *, log_path: str = ""
    ) -> bool:
        return self.ctx.check(STEP_ID, desc, ok, res, evidence, log_path=log_path)

    def root(self, command: str, timeout: float = 60.0) -> Any:
        """`command` as root on the worker, through the run's own ssh recipe."""
        argv = vm_ssh.ssh_argv(
            self.ctx.ssh_user,
            self.ctx.ssh_key,
            self.ctx.worker_ip,
            "sudo sh -c %s" % shlex.quote(command),
        )
        return self.ctx.host_run(argv, env=self.ctx.environ, timeout=timeout)

    def rdc(self, *args: str, timeout: float = 900, extra_env: dict[str, str] | None = None) -> Any:
        return self.ctx.rdc(*args, timeout=timeout, refuse=False, extra_env=extra_env)

    def state(self, ref: str) -> dict[str, Any]:
        return parse_state(self.root(state_script(self.nids[ref])).out)

    def events(self, ref: str) -> list[tuple[str, int]]:
        return parse_log(self.root(read_log_script(self.guids[ref])).out)

    def unit(self, ref: str) -> dict[str, Any]:
        return parse_unit(self.root(unit_text_script(self.nids[ref])).out)

    def config_path(self, name: str) -> pathlib.Path:
        return pathlib.Path.home() / ".config" / "rediacc" / ("%s.json" % name)

    # -- the run ---------------------------------------------------------------

    def execute(self) -> None:
        try:
            if not self.k1_0_bring_up():
                return
            self.k1_1_unit_order()
            if not self.pause_reconcile():
                return
            self.k1_2_raw_restart()
            self.k1_3_unit_rewrite()
            self.k1_4_stop_side_drift()
            self.k1_5_converge()
            self.k1_9_skewed_restart()
            self.k1_10_mount_restart()
            self.k1_6_rollout()
            self.k1_8_job_timeout()
            self.resume_reconcile()
            self.k1_7_reboot()
        finally:
            self.cleanup()

    def _ids(self) -> bool:
        listed, entries = self.ctx.repo_list()
        for item in entries:
            name = item.get("name")
            if name in (self.ref_a, self.ref_b):
                self.guids[str(name)] = str(item.get("guid", ""))
                nid = item.get("networkId", item.get("network_id"))
                if str(nid or "").isdigit():
                    self.nids[str(name)] = int(str(nid))
        return self.check(
            "K1.0 A and B listed with a guid and network id",
            all(self.guids.get(r) and self.nids.get(r) for r in (self.ref_a, self.ref_b)),
            listed,
            "guids %s network ids %s" % (self.guids, self.nids),
        )

    def _upload(self, ref: str) -> bool:
        up = self.tmp / "probe"
        up.mkdir(parents=True, exist_ok=True)
        (up / REDIACCFILE).write_text(probe_rediaccfile())
        sent = self.rdc("repo", "sync", "upload", ref, "--local", str(up) + "/")
        return self.check(
            "K1.0 the probe Rediaccfile is uploaded into %s" % ref,
            sent.rc == 0,
            sent,
            self.ctx.remote_evidence(sent) if sent.rc != 0 else "",
        )

    def k1_0_bring_up(self) -> bool:
        """A is a grand of its own (autostart is refused on a fork) and B a fork of it, made before A carries the probe so B's log starts empty."""
        # Flagged before the create: one that fails part way may still leave the grand, and teardown removes it either way.
        self.created_grand = True
        made = self.rdc("repo", "create", self.grand, "-m", self.ctx.machine, "--size", GRAND_SIZE)
        if not self.check("K1.0 the grand %s is created" % self.ref_a, made.rc == 0, made):
            return False
        self.created_fork = True
        # Up from the start, so its mount takes the upload; A carries no Rediaccfile yet, so nothing runs.
        forked = self.rdc("repo", "fork", self.grand, "--tag", self.tag_b, "--up", timeout=1800)
        if not self.check("K1.0 the fork %s is created" % self.ref_b, forked.rc == 0, forked):
            return False
        if not self._ids():
            return False
        for ref in (self.ref_a, self.ref_b):
            if not self._upload(ref):
                return False
        enabled = self.rdc("repo", "admin", "autostart", "enable", self.ref_a)
        self.autostart_enabled = enabled.rc == 0 or self.autostart_enabled
        if not self.check(
            "K1.0 autostart is enabled for %s" % self.ref_a, enabled.rc == 0, enabled
        ):
            return False
        ok_all = True
        for ref in (self.ref_a, self.ref_b):
            up = self.rdc("repo", "up", ref)
            ok, why = up_written_verdict(self.events(ref)) if up.rc == 0 else (False, "")
            st = self.state(ref) if up.rc == 0 else {"active": ""}
            ok_all = (
                self.check(
                    "K1.0 %s is up and its up() wrote a line" % ref,
                    up.rc == 0 and ok and st["active"] == "active",
                    up,
                    "rc=%d active=%s %s" % (up.rc, st["active"], why),
                )
                and ok_all
            )
        return ok_all

    def k1_1_unit_order(self) -> None:
        ok, why = unit_order_verdict(
            self.unit(self.ref_a), self.nids[self.ref_a], self.guids[self.ref_a]
        )
        self.check("K1.1 A's unit has the stop hook and both After= lines", ok, None, why)

    def _restart_row(
        self,
        desc: str,
        act: Any,
        *,
        want_up: bool,
        detail: Callable[[Any], str] | None = None,
    ) -> None:
        """Read A's state, `act()`, read it again, and judge the log: a finished down() before the new start (and an up() after it when `want_up`)."""
        before = self.state(self.ref_a)
        res = act()
        after = self.state(self.ref_a)
        events = self.events(self.ref_a)
        ok, why = down_before_verdict(
            events, before["now"], after["start"], pids=(before["pid"], after["pid"])
        )
        why = "%s (MainPID %s->%s)" % (why, before["pid"], after["pid"])
        if want_up:
            ok_up, why_up = up_after_verdict(events, after["start"])
            ok, why = ok and ok_up, "%s; %s" % (why, why_up)
        rc = getattr(res, "rc", 0)
        passed = rc == 0 and ok
        log_path = ""
        if detail is not None:
            # The detail is what names a failure's cause, so it leads: the row's evidence is clipped to EVIDENCE_MAX bytes and the verdict text alone fills them.
            extra = detail(res)
            why = "%s; %s" % (extra, why)
            if not passed and hasattr(res, "out"):
                log_path = self.ctx.keep_log(
                    STEP_ID,
                    desc.split(" ", 1)[0],
                    [desc],
                    types.SimpleNamespace(
                        rc=rc,
                        ms=getattr(res, "ms", 0),
                        out="%s\n--- detail\n%s" % (res.out, extra),
                        err=getattr(res, "err", ""),
                    ),
                )
        self.check(desc, passed, res, "rc=%d %s" % (rc, why), log_path=log_path)

    def k1_2_raw_restart(self) -> None:
        self._restart_row(
            "K1.2 a raw systemctl restart runs down() to the end before the daemon restarts",
            lambda: self.root(restart_script(self.nids[self.ref_a]), timeout=1200),
            want_up=False,
        )
        # The raw restart brings the daemon back without up(); the next rows start from a running repository.
        self.rdc("repo", "up", self.ref_a)

    def k1_3_unit_rewrite(self) -> None:
        edit = self.root(drop_environment_script(self.nids[self.ref_a]))
        if not self.check("K1.3 A's unit loses its Environment= line", edit.rc == 0, edit):
            return
        self._restart_row(
            "K1.3 repo up after a start-side change runs down() before the restart and up() after it",
            lambda: self.rdc("repo", "up", self.ref_a),
            want_up=True,
            detail=self._unit_rewrite_detail,
        )

    def _unit_rewrite_detail(self, up: Any) -> str:
        """What a no-restart K1.3 needs to name its cause: `repo up`'s stderr and the unit's `Environment=` lines as systemd reads them afterwards."""
        err = self.ctx.scrub(str(getattr(up, "err", "") or "")).strip()
        text = self.root(unit_text_script(self.nids[self.ref_a])).out
        env = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("Environment=")]
        return "unit Environment=: %s; repo up stderr: %s" % (
            " | ".join(env) or "<none>",
            err[-600:] or "<empty>",
        )

    def k1_4_stop_side_drift(self) -> None:
        nid, guid = self.nids[self.ref_a], self.guids[self.ref_a]
        before = self.state(self.ref_a)
        edit = self.root(drop_stop_side_script(nid))
        if not self.check("K1.4 A's unit loses its stop side", edit.rc == 0, edit):
            return
        tick = self.root(reconcile_script(), timeout=900)
        after = self.state(self.ref_a)
        ok_pid, why_pid = pid_unchanged_verdict(before["pid"], after["pid"])
        ok_unit, why_unit = stop_side_verdict(self.unit(self.ref_a), nid, guid)
        passed = tick.rc == 0 and ok_pid and ok_unit
        self.check(
            "K1.4 one reconcile tick restores the stop side without a restart",
            passed,
            tick,
            "reconcile rc=%d %s %s" % (tick.rc, why_pid, why_unit),
            log_path="" if passed else self.ctx.keep_log(STEP_ID, "K1.4", ["reconcile"], tick),
        )

    def k1_5_converge(self) -> None:
        gone = self.root(remove_stamp_script(self.nids[self.ref_a]))
        if not self.check("K1.5 A's runtime stamp is removed", gone.rc == 0, gone):
            return
        self._restart_row(
            "K1.5 machine converge runs down() before it restarts A",
            lambda: self.rdc("machine", "converge", self.ctx.machine, timeout=1800),
            want_up=False,
        )

    def _skewed_row(self, via: str, act: Any, *, want_up: bool) -> None:
        """Plant a skewed daemon for A, then judge `act()`'s restart like `_restart_row`: down() through the old socket finished before the new start (renet b63746a for converge, the stop hook's old-socket fallback for a restart)."""
        planted = self.root(plant_skew_script(self.nids[self.ref_a]))
        if not self.check(
            "K1.9 A's daemon is skewed (it answers only on the old-layout socket) before %s" % via,
            planted.rc == 0 and "PLANTED=" in planted.out,
            planted,
        ):
            return
        self._restart_row(
            "K1.9 %s of a skewed daemon runs down() to the end before the restart" % via,
            act,
            want_up=want_up,
        )

    def k1_9_skewed_restart(self) -> None:
        self._skewed_row(
            "machine converge",
            lambda: self.rdc("machine", "converge", self.ctx.machine, timeout=1800),
            want_up=False,
        )
        # Converge brings the daemon back on the current layout; the restart below starts from a running repository again.
        self.rdc("repo", "up", self.ref_a)
        self._skewed_row(
            "renet daemon restart",
            lambda: self.root(daemon_restart_script(self.nids[self.ref_a]), timeout=1200),
            want_up=True,
        )

    def k1_10_mount_restart(self) -> None:
        """A mount-only `repo up --no-start` reaches MountWithDocker; after a start-side change its restart runs down() first and, since renet's mount restart path brings the services back, up() after it."""
        edit = self.root(drop_environment_script(self.nids[self.ref_a]))
        if not self.check("K1.10 A's unit loses its Environment= line", edit.rc == 0, edit):
            return
        self._restart_row(
            "K1.10 repo up --no-start after a start-side change runs down() before the restart"
            " and up() after it",
            lambda: self.rdc("repo", "up", self.ref_a, "--no-start"),
            want_up=True,
        )

    # -- K1.6 ------------------------------------------------------------------

    def _main_binary(self) -> pathlib.Path | None:
        """The renet at the main pointer, built in a shared clone with the licence key `./rdc.sh` would bake."""
        self.tmp.mkdir(parents=True, exist_ok=True)
        sha = self.ctx.host_run(
            ["git", "rev-parse", MAIN_POINTER], env=self.ctx.environ, timeout=60
        )
        if not self.check(
            "K1.6 resolve the main-pointer renet (%s)" % MAIN_POINTER,
            sha.rc == 0 and bool(sha.out.strip()),
            sha,
        ):
            return None
        commit = sha.out.strip()
        env = dict(self.ctx.environ)
        try:
            env[local_common.ACCOUNT_KEY_NAME] = local_common.resolve_renet_account_key(
                str(pathlib.Path(self.ctx.root) / "private" / "renet"), env
            )
        except local_common.LocalCommonError as exc:
            self.check("K1.6 the renet licence key resolves", False, evidence=_clip(str(exc)))
            return None
        out = self.tmp / "renet-main"
        script = build_main_renet_script(str(self.tmp / "src-main"), str(out), commit)
        built = self.ctx.host_run(["bash", "-c", script], env=env, timeout=1800)
        if not self.check(
            "K1.6 build the main-pointer renet (%s)" % commit[:12], built.rc == 0, built
        ):
            return None
        return out

    def _install(self, binary: pathlib.Path) -> bool:
        staged = upgrade_converge.staged_renet_path(self.ctx.run_id, STEP_ID)
        ssh = vm_ssh.ssh_argv(
            self.ctx.ssh_user,
            self.ctx.ssh_key,
            self.ctx.worker_ip,
            "cat > %s" % shlex.quote(staged),
        )
        sent = self.ctx.host_run(
            upgrade_converge.with_stdin_from(str(binary), ssh), env=self.ctx.environ, timeout=900
        )
        if not self.check("K1.6 upload the main-pointer renet to the worker", sent.rc == 0, sent):
            return False
        script = upgrade_converge.install_current_renet_script(staged)
        res = self.ctx.host_run(
            vm_ssh.ssh_argv(
                self.ctx.ssh_user,
                self.ctx.ssh_key,
                self.ctx.worker_ip,
                "sh -c %s" % shlex.quote(script),
            ),
            env=self.ctx.environ,
            timeout=300,
        )
        self.main_installed = True
        want = upgrade_converge.file_sha256(binary)
        got = upgrade_converge.installed_sha(res.out)
        return self.check(
            "K1.6 the main-pointer renet is the worker's current renet",
            res.rc == 0 and bool(want) and got == want,
            res,
            "installed=%s built=%s" % (got[:12], want[:12]),
        )

    def _make_config(self, binary: pathlib.Path) -> bool:
        """A copy of the dev config with `renetPath` on the main-pointer build, so the CLI's provision verifies that binary instead of replacing it. Created 0600 from the first byte: it carries the repo credentials."""
        dev_json = self.config_path("dev")
        try:
            doc = json.loads(dev_json.read_text())
        except (OSError, ValueError) as exc:
            return self.check("K1.6 the dev config reads", False, evidence=type(exc).__name__)
        doc["renetPath"] = str(binary)
        doc["id"] = str(uuid.uuid4())
        target = self.config_path(self.cfg)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as handle:
            handle.write(json.dumps(doc, indent=2) + "\n")
        self.created_cfg = True
        return True

    def k1_6_rollout(self) -> None:
        binary = self._main_binary()
        if binary is None or not self._install(binary) or not self._make_config(binary):
            return
        up = self.rdc(
            "repo", "up", self.ref_a, extra_env={"REDIACC_CONFIG": self.cfg, "RDC_DEV": ""}
        )
        if not self.check("K1.6 repo up A under the main-pointer renet", up.rc == 0, up):
            return
        before = {r: self.state(r) for r in (self.ref_a, self.ref_b)}
        setup = self.rdc("machine", "setup", self.ctx.machine, timeout=1800)
        if setup.rc == 0:
            self.main_installed = False
        if not self.check("K1.6 rdc machine setup installs the branch renet", setup.rc == 0, setup):
            return
        tick = self.root(reconcile_script(), timeout=900)
        for ref in (self.ref_a, self.ref_b):
            after = self.state(ref)
            ok_pid, why_pid = pid_unchanged_verdict(before[ref]["pid"], after["pid"])
            ok_unit, why_unit = stop_side_verdict(self.unit(ref), self.nids[ref], self.guids[ref])
            self.check(
                "K1.6 %s: no restart across the rollout, and the new stop side after one tick"
                % ref,
                tick.rc == 0 and ok_pid and ok_unit,
                tick,
                "reconcile rc=%d %s %s" % (tick.rc, why_pid, why_unit),
            )

    # -- K1.7 and K1.8 ---------------------------------------------------------

    def k1_8_job_timeout(self) -> None:
        res = self.root(job_timeout_script())
        ok, why = job_timeout_verdict(res.out)
        self.check(
            "K1.8 reboot.target's job timeout fits the stop budget", res.rc == 0 and ok, res, why
        )

    def _boot(self) -> int:
        return parse_kv_ints(self.root(boot_script()).out).get("BOOT", 0)

    def _poll(self, attempts: int, probe: Any) -> Any:
        for _ in range(attempts):
            got = probe()
            if got:
                return got
            self.sleep(POLL_S)
        return probe()

    def k1_7_reboot(self) -> None:
        # B is brought up again: K1.3 and K1.5 restarted only A, but a run that got this far must see both down() calls.
        self.rdc("repo", "up", self.ref_b)
        issued = self.state(self.ref_a)["now"]
        boot_before = self._boot()
        if not self.check(
            "K1.7 the worker's clock and boot time read before the reboot",
            bool(issued) and bool(boot_before),
            evidence="now=%s boot=%s" % (issued, boot_before),
        ):
            return
        self.root(reboot_script(), timeout=120)

        def booted() -> int:
            b = self._boot()
            return b if b > boot_before else 0

        boot = self._poll(REBOOT_WAIT_S // POLL_S, booted)
        if not self.check(
            "K1.7 the worker comes back after systemctl reboot",
            bool(boot),
            evidence="boot before=%s after=%s" % (boot_before, boot),
        ):
            return

        def a_back() -> bool:
            st = self.state(self.ref_a)
            return st["active"] == "active" and up_after_verdict(self.events(self.ref_a), boot)[0]

        back = self._poll(BACK_UP_WAIT_S // POLL_S, a_back)
        ok, why = down_before_verdict(self.events(self.ref_a), issued, boot)
        self.check("K1.7 A's down() finished before the reboot", ok, None, why)
        mounted = self.rdc("repo", "up", self.ref_b, "--no-start")
        ok, why = down_before_verdict(self.events(self.ref_b), issued, boot)
        self.check(
            "K1.7 B's down() (autostart off) finished before the reboot",
            mounted.rc == 0 and ok,
            mounted,
            "mount rc=%d %s" % (mounted.rc, why),
        )
        ok, why = up_after_verdict(self.events(self.ref_a), boot)
        self.check("K1.7 A is back up after the boot", bool(back) and ok, None, why)

    # -- teardown --------------------------------------------------------------

    def pause_reconcile(self) -> bool:
        res = self.root(pause_reconcile_script(), timeout=PAUSE_WAIT_S + 60)
        self.reconcile_paused = res.rc == 0 or self.reconcile_paused
        return self.check(
            "K1 the autostart-reconcile timer is paused for the restart rows",
            res.rc == 0 and "PAUSED" in res.out,
            res,
        )

    def resume_reconcile(self) -> bool:
        if not self.reconcile_paused:
            return True
        res = self.root(resume_reconcile_script())
        self.reconcile_paused = res.rc != 0
        return res.rc == 0

    def cleanup(self) -> None:
        left: list[str] = []
        if not self.resume_reconcile():
            left.append("K1 %s still stopped (systemctl start failed)" % RECONCILE_TIMER)
        if self.main_installed:
            res = self.rdc("machine", "setup", self.ctx.machine, timeout=1800)
            if res.rc != 0:
                left.append(
                    "K1 worker still on the main-pointer renet (machine setup rc=%d)" % res.rc
                )
        if self.autostart_enabled:
            res = self.rdc("repo", "admin", "autostart", "disable", self.ref_a)
            if res.rc != 0:
                left.append("K1 autostart of %s (disable rc=%d)" % (self.ref_a, res.rc))
        if self.created_fork:
            res = self.rdc("repo", "delete", self.ref_b, "-y")
            if res.rc != 0:
                left.append("K1 fork %s (delete rc=%d)" % (self.ref_b, res.rc))
        if self.created_grand:
            res = self.rdc("repo", "delete", self.ref_a, "--archive-config", "-y")
            if res.rc != 0:
                left.append("K1 grand %s (delete rc=%d)" % (self.ref_a, res.rc))
        if self.created_cfg:
            for path in upgrade_converge.config_files(self.config_path(self.cfg), self.cfg):
                try:
                    path.unlink(missing_ok=True)
                except OSError as exc:
                    left.append("K1 config file %s not removed (%s)" % (path.name, exc))
        if self.tmp.exists():
            shutil.rmtree(self.tmp, ignore_errors=True)
        self.ctx.sweep_leftovers.extend(self.ctx.scrub(x) for x in left)


__all__ = [
    "DOWN_SLEEP_S",
    "LOG_FILE",
    "STEP",
    "STEP_ID",
    "boot_script",
    "build_main_renet_script",
    "config_name",
    "current_socket",
    "daemon_restart_script",
    "daemon_unit",
    "down_before_verdict",
    "drop_environment_script",
    "drop_stop_side_script",
    "job_timeout_script",
    "job_timeout_verdict",
    "legacy_socket",
    "mount_path",
    "mount_unit",
    "parse_kv_ints",
    "parse_log",
    "parse_state",
    "parse_timespan",
    "parse_unit",
    "pid_unchanged_verdict",
    "plant_skew_script",
    "probe_rediaccfile",
    "read_log_script",
    "reboot_script",
    "reconcile_script",
    "remove_stamp_script",
    "repo_names",
    "restart_script",
    "restarted",
    "run",
    "runs_stop_hook",
    "state_script",
    "stop_side_verdict",
    "systemd_escape_path",
    "unit_order_verdict",
    "unit_text_script",
    "up_after_verdict",
    "up_written_verdict",
]
