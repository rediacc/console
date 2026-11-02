"""I2: a repository's teardown ends its terminal and VS Code sessions on purpose, and a bare `repo down` leaves them alone.

Since renet 8e5ecd2 a sandbox session's PID-namespace init lingers after the shell exits, until its last process is gone, so a nohup job or a VS Code server outlives its ssh channel. Every one of those processes sits in the shared exec cgroup `rediacc.slice/renet-exec-<N>`. `repo down --unmount` (and delete, takeover, autostart stop) reaches renet's SafeShutdown, which now ends them first through `ebpf.EndExecSessions` (SIGTERM, then cgroup.kill) and records the `sessions_end` step, which the CLI prints as `Sessions ended: N sessions (M processes)`; before that only a racy SIGKILL net inside the LUKS close caught them, and a slow one failed the down.

`vm_check.py` registers this module once, through `EXTRA_RENET_STEPS`, as the `I2` step of the renet phase, after I1; `--only I2` drags in V1.2 (and with it P5 and V1.1), so fork A exists and is up when `run(ctx)` is called. `ctx` is the running `VmCheck`, driven the way tenant_isolation.py drives it: `./rdc.sh` through `rdc` and `shell`, root probes through `vm_ssh.ssh_argv` and `host_run`, rows through `check` and `record`. Every row records under `I2` and asserts the FIXED behaviour; a defect is a FAIL row.

THE ROWS. I2.1 a nohup sleep started in A's session is alive after the channel closed, and renet-exec-<N>/cgroup.procs is not empty; I2.2 a held-open `rdc term connect -c 'sleep N'` runs (and returns once A goes down); I2.3 `rdc repo down <A> --unmount` exits 0; I2.4 its output carries the "Sessions ended: N sessions (M processes)" step line with N >= 1; I2.5 a root probe finds neither sleep alive, the exec cgroup unpopulated or gone, and /dev/mapper/<guid> absent; I2.6 `rdc repo up <A>` exits 0 and a fresh session works; I2.7 a bare `rdc repo down <A>` leaves a fresh nohup job alive, then `rdc repo up <A>` again.

TEARDOWN. Every `sleep` this step started is killed by root at the end; one still running, or an ssh failure that proves nothing, rides `ctx.sweep_leftovers`, so the run cannot reach VERIFIED over it. A that is left down is brought up again (best effort; the run's teardown deletes the fork either way).
"""

from __future__ import annotations

import re
import shlex
import threading
from typing import Any

from rediacc_ci.drills import vm_ssh
from rediacc_ci.drills.tenant_isolation import alive_script, exec_cgroup, sleep_seconds

STEP_ID = "I2"

# Salts for sleep_seconds that I1 does not use (it takes 1 and 2), one per background job.
SALT_NOHUP, SALT_HELD, SALT_BARE = 21, 22, 23
# The held-open connect's process timeout: long enough to outlive the down, short enough that a down which never ends it still frees the run.
HOLD_TIMEOUT_S = 900
# How long, after the down returned, the held-open connect gets to notice its channel is gone.
HOLD_JOIN_S = 60
REPO_VERB_TIMEOUT_S = 900
# The CLI's rendering of renet's sessions_end step: the label is hard-coded in packages/cli/src/utils/timeline.ts doneLabels, the counts come from renet's English orchestration.sessions_ended_detail text: "✔ Sessions ended: 2 sessions (3 processes) (40ms)".
ENDED_RE = re.compile(r"Sessions ended: (\d+) sessions \((\d+) processes\)")
FRESH_MARK = "VMC-I2-FRESH"


# --------------------------------------------------------------------------- pure helpers


def sessions_ended(text: str) -> tuple[int, int] | None:
    """(sessions, processes) of the last "Sessions ended: N sessions (M processes)" step line in `text`, or None when no such line printed."""
    found = ENDED_RE.findall(text)
    if not found:
        return None
    sessions, processes = found[-1]
    return int(sessions), int(processes)


def procs_script(network_id: int | str) -> str:
    """Root on the worker: PROCS=<count of pids in renet-exec-<N>/cgroup.procs>, or NOCG (exit 3) when the cgroup does not exist."""
    procs = shlex.quote(exec_cgroup(network_id) + "/cgroup.procs")
    return "test -f %(p)s || { echo NOCG; exit 3; }; echo PROCS=$(grep -c . %(p)s)" % {"p": procs}


def procs_count(text: str) -> int | None:
    """The count procs_script printed, or None (NOCG, or no marker)."""
    found = re.findall(r"^PROCS=(\d+)\s*$", text, re.MULTILINE)
    return int(found[-1]) if found else None


def wait_alive_script(seconds: int, tries: int = 30) -> str:
    """Root on the worker: ALIVE once a `sleep <seconds>` process exists, polled once a second for `tries` seconds; GONE (exit 1) when it never appears."""
    pat = shlex.quote("^sleep %d$" % seconds)
    return (
        "for i in $(seq %(tries)d); do pgrep -f %(pat)s >/dev/null && { echo ALIVE; exit 0; }; "
        "sleep 1; done; echo GONE; exit 1" % {"pat": pat, "tries": tries}
    )


def teardown_probe_script(network_id: int | str, guid: str, seconds: list[int]) -> str:
    """Root on the worker after the down: one `SLEEP <n> ALIVE|GONE` line per job, `CGROUP ABSENT` or `CGROUP <cgroup.events populated line>`, and `MAPPER PRESENT|ABSENT` for /dev/mapper/<guid>."""
    events = shlex.quote(exec_cgroup(network_id) + "/cgroup.events")
    mapper = shlex.quote("/dev/mapper/%s" % guid)
    lines = [
        "pgrep -f %s >/dev/null && echo 'SLEEP %d ALIVE' || echo 'SLEEP %d GONE'"
        % (shlex.quote("^sleep %d$" % s), s, s)
        for s in seconds
    ]
    lines.append(
        "if test -f %(e)s; then echo \"CGROUP $(grep '^populated' %(e)s)\"; else echo 'CGROUP ABSENT'; fi"
        % {"e": events}
    )
    lines.append("test -e %s && echo 'MAPPER PRESENT' || echo 'MAPPER ABSENT'" % mapper)
    return "\n".join(lines) + "\n"


def teardown_verdict(text: str, seconds: list[int]) -> tuple[bool, str]:
    """(ok, evidence) of teardown_probe_script's output: every job GONE, the cgroup ABSENT or `populated 0`, the mapper ABSENT. A line that never printed is a failure, not a pass."""
    why = []
    for s in seconds:
        if "SLEEP %d GONE" % s in text:
            continue
        why.append("sleep %d %s" % (s, "alive" if "SLEEP %d ALIVE" % s in text else "unread"))
    cg = re.findall(r"^CGROUP (.*?)\s*$", text, re.MULTILINE)
    if not cg:
        why.append("cgroup unread")
    elif cg[-1] not in ("ABSENT", "populated 0"):
        why.append("cgroup %s" % cg[-1])
    if "MAPPER ABSENT" not in text:
        why.append("mapper %s" % ("present" if "MAPPER PRESENT" in text else "unread"))
    ev = "; ".join(ln.strip() for ln in text.splitlines() if ln.strip()) or "no output"
    return (not why), ("; ".join(why) + " (%s)" % ev) if why else ev


def nohup_script(seconds: int) -> str:
    """A session's shell: start a nohup `sleep <seconds>` and print STARTED once pgrep sees it."""
    return "nohup sleep %d >/dev/null 2>&1 & sleep 1; pgrep -f %s >/dev/null && echo STARTED" % (
        seconds,
        shlex.quote("^sleep %d$" % seconds),
    )


def kill_script(seconds: list[int]) -> str:
    """Root on the worker: kill every listed `sleep`, then exit 0 only when none is left."""
    pattern = shlex.quote("^sleep (%s)$" % "|".join(str(s) for s in seconds))
    return "pkill -f %s; sleep 1; ! pgrep -f %s" % (pattern, pattern)


# --------------------------------------------------------------------------- live


def run(ctx: Any) -> None:
    """The live I2 step: records I2 rows on `ctx` and kills what it started."""
    _LiveI2(ctx).execute()


STEP = (STEP_ID, ("V1.2",), run)


class _LiveI2:
    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self.tag_a = ctx.tags[0]
        self.ref_a = ctx.ref(self.tag_a)
        self.nid = 0
        self.guid = ""
        self.sleep_nohup = sleep_seconds(ctx.run_id, SALT_NOHUP)
        self.sleep_held = sleep_seconds(ctx.run_id, SALT_HELD)
        self.sleep_bare = sleep_seconds(ctx.run_id, SALT_BARE)
        self.sleeps_started = False
        # True between a down this step ran and the up that follows it.
        self.a_down = False
        self.held: threading.Thread | None = None
        self.held_res: Any = None
        self.down: Any = None

    # -- helpers ---------------------------------------------------------------

    def check(self, desc: str, ok: bool, res: Any = None, evidence: str = "") -> bool:
        return self.ctx.check(STEP_ID, desc, ok, res, evidence)

    def root(self, command: str, timeout: float = 60.0) -> Any:
        """`command` as root on the worker, through the run's own ssh recipe."""
        argv = vm_ssh.ssh_argv(
            self.ctx.ssh_user,
            self.ctx.ssh_key,
            self.ctx.worker_ip,
            "sudo sh -c %s" % shlex.quote(command),
        )
        return self.ctx.host_run(argv, env=self.ctx.environ, timeout=timeout)

    def ev(self, res: Any) -> str:
        return self.ctx.remote_evidence(res)

    def repo(self, verb: str, *extra: str) -> Any:
        return self.ctx.rdc("repo", verb, self.ref_a, *extra, timeout=REPO_VERB_TIMEOUT_S)

    # -- the run ---------------------------------------------------------------

    def execute(self) -> None:
        try:
            if not self._preconditions():
                return
            self.i2_1_nohup_job()
            self.i2_2_held_connect()
            if self.i2_3_down_unmount():
                self.i2_4_ended_line()
            self._join_held()
            self.i2_5_all_gone()
            if self.i2_6_up_again():
                self.i2_7_bare_down_keeps_sessions()
        finally:
            self._cleanup()

    def _preconditions(self) -> bool:
        nid = self.ctx.network_ids.get(self.tag_a)
        if str(nid or "").isdigit():
            self.nid = int(nid)
        self.guid = self.ctx.guids.get(self.tag_a, "")
        return self.check(
            "fork A has a network id and guid (from V1.1)",
            bool(self.nid and self.guid),
            evidence="network id %s guid %s" % (self.nid or "-", self.guid or "-"),
        )

    def i2_1_nohup_job(self) -> None:
        secs = self.sleep_nohup
        self.sleeps_started = True
        started = self.ctx.shell(self.ref_a, nohup_script(secs))
        if not self.check(
            "I2.1 A: a nohup sleep starts in a session",
            started.rc == 0 and "STARTED" in started.out,
            started,
            "" if started.rc == 0 else self.ev(started),
        ):
            return
        alive = self.root(alive_script(secs))
        self.check(
            "I2.1 the nohup sleep is alive after its session's channel closed",
            alive.rc == 0 and "ALIVE" in alive.out,
            alive,
            alive.text(),
        )
        procs = self.root(procs_script(self.nid))
        count = procs_count(procs.out)
        self.check(
            "I2.1 renet-exec-%d/cgroup.procs is not empty" % self.nid,
            procs.rc == 0 and bool(count),
            procs,
            "procs %s; %s" % (count, procs.text()),
        )

    def i2_2_held_connect(self) -> None:
        secs = self.sleep_held
        self.sleeps_started = True

        def hold() -> None:
            self.held_res = self.ctx.rdc(
                "term",
                "connect",
                self.ref_a,
                "-c",
                "sleep %d" % secs,
                timeout=HOLD_TIMEOUT_S,
                refuse=False,
            )

        self.held = threading.Thread(target=hold, name="vmc-i2-held", daemon=True)
        self.held.start()
        alive = self.root(wait_alive_script(secs), timeout=120)
        self.check(
            "I2.2 a held-open rdc term connect -c 'sleep %d' runs on the worker" % secs,
            alive.rc == 0 and "ALIVE" in alive.out,
            alive,
            alive.text()
            if alive.rc == 0
            else "%s; held connect %s" % (alive.text(), self._held_state()),
        )

    def _held_state(self) -> str:
        if self.held is not None and self.held.is_alive():
            return "still running"
        res = self.held_res
        return "returned rc=%s" % (res.rc if res is not None else "?")

    def i2_3_down_unmount(self) -> bool:
        self.down = self.repo("down", "--unmount")
        self.a_down = self.down.rc == 0
        return self.check(
            "I2.3 rdc repo down %s --unmount exits 0" % self.ref_a,
            self.down.rc == 0,
            self.down,
            "" if self.down.rc == 0 else self.ev(self.down),
        )

    def i2_4_ended_line(self) -> None:
        got = sessions_ended(self.down.text())
        self.check(
            "I2.4 the down's output says it ended at least one session",
            got is not None and got[0] >= 1,
            self.down,
            (
                "Sessions ended: %d sessions (%d processes)" % got
                if got
                else "no 'Sessions ended: N sessions' step line; %s" % self.ev(self.down)
            ),
        )

    def _join_held(self) -> None:
        if self.held is None:
            return
        self.held.join(HOLD_JOIN_S)
        if not self.a_down:
            return
        self.check(
            "I2.2 the held-open connect returned once A went down",
            not self.held.is_alive(),
            self.held_res,
            "held connect %s" % self._held_state(),
        )

    def i2_5_all_gone(self) -> None:
        if not self.a_down:
            return
        secs = [self.sleep_nohup, self.sleep_held]
        probe = self.root(teardown_probe_script(self.nid, self.guid, secs))
        ok, why = teardown_verdict(probe.out, secs)
        self.check(
            "I2.5 after the down no session sleep is alive, renet-exec-%d is empty and /dev/mapper/%s is gone"
            % (self.nid, self.guid),
            probe.rc == 0 and ok,
            probe,
            why if probe.rc == 0 else "%s; %s" % (why, probe.text()),
        )

    def i2_6_up_again(self) -> bool:
        up = self.repo("up")
        if up.rc == 0:
            self.a_down = False
        if not self.check(
            "I2.6 rdc repo up %s exits 0" % self.ref_a,
            up.rc == 0,
            up,
            "" if up.rc == 0 else self.ev(up),
        ):
            return False
        fresh = self.ctx.shell(self.ref_a, "echo %s" % FRESH_MARK)
        return self.check(
            "I2.6 a fresh session on A works",
            fresh.rc == 0 and FRESH_MARK in fresh.out,
            fresh,
            "" if fresh.rc == 0 else self.ev(fresh),
        )

    def i2_7_bare_down_keeps_sessions(self) -> None:
        secs = self.sleep_bare
        self.sleeps_started = True
        started = self.ctx.shell(self.ref_a, nohup_script(secs))
        if not self.check(
            "I2.7 A: a fresh nohup sleep starts in a session",
            started.rc == 0 and "STARTED" in started.out,
            started,
            "" if started.rc == 0 else self.ev(started),
        ):
            return
        down = self.repo("down")
        self.a_down = down.rc == 0
        if not self.check(
            "I2.7 a bare rdc repo down %s exits 0" % self.ref_a,
            down.rc == 0,
            down,
            "" if down.rc == 0 else self.ev(down),
        ):
            return
        alive = self.root(alive_script(secs))
        self.check(
            "I2.7 the nohup sleep is still alive after a bare down",
            alive.rc == 0 and "ALIVE" in alive.out,
            alive,
            alive.text(),
        )
        up = self.repo("up")
        if up.rc == 0:
            self.a_down = False
        self.check(
            "I2.7 rdc repo up %s exits 0 after the bare down" % self.ref_a,
            up.rc == 0,
            up,
            "" if up.rc == 0 else self.ev(up),
        )

    # -- teardown --------------------------------------------------------------

    def _cleanup(self) -> None:
        left: list[str] = []
        if self.sleeps_started:
            secs = [self.sleep_nohup, self.sleep_held, self.sleep_bare]
            res = self.root(kill_script(secs))
            # An ssh failure proves nothing was killed, so it is a leftover like a surviving process.
            if res.rc == vm_ssh.SSH_FAILED:
                left.append(
                    "I2 background sleep processes (%s) not checked: the root ssh probe failed (rc=%d)"
                    % (secs, res.rc)
                )
            elif res.rc != 0:
                left.append("I2 background sleep processes still running on the worker (%s)" % secs)
        if self.held is not None:
            self.held.join(HOLD_JOIN_S)
            if self.held.is_alive():
                left.append("I2 held-open rdc term connect to %s still running" % self.ref_a)
        if self.a_down:
            # The run's teardown deletes A either way; bringing it back keeps a later step from finding it down.
            self.ctx.rdc("repo", "up", self.ref_a, timeout=REPO_VERB_TIMEOUT_S, refuse=False)
        self.ctx.sweep_leftovers.extend(self.ctx.scrub(x) for x in left)


__all__ = [
    "STEP",
    "STEP_ID",
    "kill_script",
    "nohup_script",
    "procs_count",
    "procs_script",
    "run",
    "sessions_ended",
    "teardown_probe_script",
    "teardown_verdict",
    "wait_alive_script",
]
