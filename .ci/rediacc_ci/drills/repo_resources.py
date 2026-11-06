"""K2 and K3 of agent/plans/PLAN-repo-resource-limits.md (box K0b): a repository's memory cap holds inside its own cgroup, and its RAM volume lives and dies in the order the plan's loss model states.

`vm_check.py` registers this module through `EXTRA_RENET_STEPS` as two steps of the renet phase, `K2` (limits) and `K3` (RAM volume), each depending on P5 so the run's parent grand exists. `ctx` is the running `VmCheck`: VM actions go through its `./rdc.sh` helper (`rdc`), its raw ssh recipe (`vm_ssh.ssh_argv` through `host_run`, as root on the worker) and its ledger (`check`, `record`).

K2 ROWS. Both forks fork an empty grand, so after the limits K2.0 starts holder containers: in C one under the `keep` service directory that fills 48 MiB of /dev/shm and one ad-hoc leaf, in D one under `keep`.
K2.0 fork C (`--memory-max 1G --cpu-max 1`) and fork D (no limits) are up; K2.1 rediacc-<C> has memory.max 1073741824 and cpu.max `100000 100000`, every container cgroup under it (the `keep` directory and the ad-hoc leaf, both made after the limits) has memory.oom.group 1, and rediacc-<D> has memory.max `max`; K2.2 an `alloc` container in C runs `head -c 2147483648 /dev/zero | tail`, after which C's memory.events oom_kill rose by at least 1, D's did not move, the host's /proc/vmstat oom_kill delta equals C's, C's other containers and every D container keep their StartedAt, and sshd answers; K2.3 `rdc repo policy set C --memory-max 1536M` changes memory.max with the daemon's MainPID and the container start times unchanged; K2.4 `--memory-max 16M` without `--force` is refused; K2.5 memory.max survives `systemctl daemon-reload`, a restart of an unrelated unit, and `systemctl restart rediacc-docker-<C>`; K2.6 a fork of C inherits memory.max.

K3 ROWS. K3.0 fork E is up with `--ram-volume 512M --memory-max 1536M` and the probe Rediaccfile; K3.1 the tmpfs exists, size 512M, before up() runs (the probe's up() logged it); K3.2 a container writes `marker` into `.ram/data` through a bind; K3.3 up() restored 200 MB into `.ram`, rediacc-<E>'s memory.stat shmem holds at least that, and renet-exec-<E> does not; K3.4 `systemctl restart rediacc-docker-<E>` keeps `marker`; K3.5 `rdc repo down E --unmount` logs a down() line while `.ram` is still mounted and leaves no `.ram` mount, and after `rdc repo up E` the marker is gone and `.rediacc-ram` has a new mounted_at; K3.6 (the reboot row) needs K1 VERIFIED on the same tree and is a skip row here.

Deviation: the plan's K3.0 names `--memory-max 1G` with a 512M volume, which Decision 13 refuses (memory.max must be at least the volume plus 1 GiB); the fork takes 1536M, the smallest cap Decision 13 admits.

TEARDOWN. Every fork joins `ctx.forks`, so the run's teardown deletes it and purges its licence state even when a step crashes; this module removes only its detached container.

The pure pieces (the readout scripts, the probe Rediaccfile, and the parsers and verdicts of memory.events, /proc/vmstat, memory.stat, findmnt, statfs, the probe logs and StartedAt listings) are pinned by `tests/test_drills_repo_resources.py` without a machine.
"""

from __future__ import annotations

import json
import re
import shlex
from typing import Any

from rediacc_ci.drills import vm_ssh
from rediacc_ci.well_known import DATASTORE_PATH, RUNTIME_DIR

K2_ID = "K2"
K3_ID = "K3"

GIB = 1 << 30
MIB = 1 << 20
C_MEMORY_MAX = GIB
C_MEMORY_RAISED = 1536 * MIB
CPU_ONE_CORE = "100000 100000"
ALLOC_BYTES = 2 * GIB
REFUSED_MEMORY = "16M"
RAM_SIZE = 512 * MIB
E_MEMORY_MAX = RAM_SIZE + GIB
RESTORE_BYTES = 200 * MIB
IMAGE = "busybox:1.36"
SLICE = "/sys/fs/cgroup/rediacc.slice"
MOUNTS = DATASTORE_PATH + "/mounts"
MARKER = "marker"
K3_6_NOTE = (
    "K3.6 reboot row not run here: it needs K1 VERIFIED on the same tree and a reboot of the worker"
)
SECTION = "== "
PROBE_UP_LOG = ".ram-probe-up.log"
PROBE_DOWN_LOG = ".ram-probe-down.log"
RAM_MARKER_FILE = ".rediacc-ram"
COMPOSE_FILE = "docker-compose.yml"
KEEP_SERVICE = "keep"
# C's holder fills this much of /dev/shm (docker's default shm is 64 MiB), so C's memory.current is well above REFUSED_MEMORY and K2.4's refusal has usage to protect. The forks fork an empty grand, so without it C used under 16 MiB and the refusal rightly refused nothing (vm:check run vmc-11060119-8cbbc0 K2.4).
HOLD_SHM_BYTES = 48 * MIB


def fork_tags(tags: tuple[str, str]) -> tuple[str, str, str, str]:
    """The four forks: C, D, the fork of C, and E, fork A's run tag with `-a` turned into `-g`..`-j`, so the stale-fork sweep (`vm_check.FORK_TAG`) still recognises them."""
    stem = tags[0].removesuffix("-a")
    return stem + "-g", stem + "-h", stem + "-i", stem + "-j"


# --------------------------------------------------------------------------- root scripts


def cgroup_dir(network_id: int) -> str:
    return "%s/rediacc-%d" % (SLICE, int(network_id))


def cgroup_readout_script(network_id: int) -> str:
    """Root on the worker: one `== <file>` section per resource file of rediacc-<N>, then `== oom.group <svc>` per service directory (skipping `@lifecycle`); `NO_CGROUP` when rediacc-<N> is missing."""
    d = cgroup_dir(network_id)
    files = ("memory.max", "memory.high", "cpu.max", "memory.events", "memory.stat")
    parts = ["d=%s; test -d $d || { echo NO_CGROUP; exit 0; }" % shlex.quote(d)]
    parts += ["echo '%s%s'; cat $d/%s 2>/dev/null" % (SECTION, f, f) for f in files]
    parts.append(
        'for s in $d/*/; do [ -d "$s" ] || continue; n=$(basename $s); case $n in @*) continue;; esac; '
        'echo "%soom.group $n"; cat $s/memory.oom.group 2>/dev/null; done' % SECTION
    )
    return "; ".join(parts)


def keep_command(name: str, cgroup_parent: str = "", shm_bytes: int = 0) -> str:
    """A detached container that stays up: under `cgroup_parent` when given (a service directory, as compose places one), else straight under rediacc-<N> (an ad-hoc `docker run`); with `shm_bytes` it first fills /dev/shm, which is charged to the repository, so the repository's memory.current stays above that."""
    inner = "exec sleep 86400"
    if shm_bytes:
        inner = "head -c %d /dev/zero > /dev/shm/hold && %s" % (shm_bytes, inner)
    parent = " --cgroup-parent %s" % shlex.quote(cgroup_parent) if cgroup_parent else ""
    return "docker run -d --name %s%s %s sh -c %s" % (name, parent, IMAGE, shlex.quote(inner))


def service_parent(network_id: int, service: str) -> str:
    """The cgroup parent compose gives a service: /rediacc.slice/rediacc-<N>/<service>."""
    return "/rediacc.slice/rediacc-%d/%s" % (int(network_id), service)


def compose_body() -> str:
    """K3's compose file: one service that stays up, so the probe's `renet compose -- up -d` has a file to start (vm:check run vmc-11060119-8cbbc0 K3.0 failed `renet compose up -d: no compose file found`, the grand being empty)."""
    return 'services:\n  %s:\n    image: %s\n    command: ["sleep", "86400"]\n' % (
        KEEP_SERVICE,
        IMAGE,
    )


def vmstat_script() -> str:
    return "grep '^oom_kill ' /proc/vmstat"


def exec_stat_script(network_id: int) -> str:
    """Root: renet-exec-<N>'s memory.stat (empty when it does not exist)."""
    return "cat %s/renet-exec-%d/memory.stat 2>/dev/null || true" % (SLICE, int(network_id))


def findmnt_script(mount: str) -> str:
    return "findmnt -rn -o TARGET,FSTYPE,OPTIONS %s || true" % shlex.quote(ram_dir(mount))


def main_pid_script(network_id: int) -> str:
    return "echo MAINPID=$(systemctl show -p MainPID --value rediacc-docker-%d)" % int(network_id)


def grant_show_script(network_id: int) -> str:
    return "renet daemon grant --network-id %d --show" % int(network_id)


def ram_dir(mount: str) -> str:
    return mount.rstrip("/") + "/.ram"


def started_at_command() -> str:
    """A repository shell's `/<name> <StartedAt>` of every running container."""
    return "docker ps -q | xargs -r docker inspect -f '{{.Name}} {{.State.StartedAt}}'"


def alloc_command(name: str) -> str:
    """A detached container that reads 2 GiB of /dev/zero into `tail`, which holds it all (no newline ever ends a line)."""
    return "docker run -d --name %s %s sh -c %s" % (
        name,
        IMAGE,
        shlex.quote("head -c %d /dev/zero | tail" % ALLOC_BYTES),
    )


def writer_command(mount: str, network_id: int) -> str:
    """A container of the fork that writes MARKER into `.ram/data` through a bind and reads it back.

    Run through the drill's root ssh against the fork's own Docker socket, not `rdc term connect -c`: in agent mode term connect refuses every file-write pattern (a redirect, then `tee`, vm:check runs of 2026-11-06), and a container writing a file is the whole point of K3.2.
    """
    inner = "echo %s > /data/%s && cat /data/%s" % (MARKER, MARKER, MARKER)
    return (
        "env DOCKER_HOST=unix://%s/net-%d/docker-%d.sock docker run --rm -v %s/data:/data %s sh -c %s"
        % (
            RUNTIME_DIR,
            int(network_id),
            int(network_id),
            ram_dir(mount),
            IMAGE,
            shlex.quote(inner),
        )
    )


def probe_rediaccfile() -> str:
    """K3's probe: up() logs the findmnt of `.ram` before anything, then restores RESTORE_BYTES into the volume when `.restored` is missing; down() logs whether `.ram` is still mounted, after the services stop."""
    fm = "findmnt -rn -o TARGET,FSTYPE,OPTIONS \"$REDIACC_WORKING_DIR/.ram\" | tr ' ' '|'"
    return (
        "#!/bin/bash\n"
        "up() {\n"
        '  echo "findmnt $(%(fm)s)" >> %(up)s\n'
        '  if [ -n "$REDIACC_RAM_DIR" ] && [ ! -e "$REDIACC_RAM_DIR/.restored" ]; then\n'
        '    head -c %(bytes)d /dev/urandom > "$REDIACC_RAM_DIR/restore.bin"\n'
        '    touch "$REDIACC_RAM_DIR/.restored"\n'
        '    echo "restored %(bytes)d" >> %(up)s\n'
        "  fi\n"
        "  renet compose -- up -d\n"
        "}\n"
        "down() {\n"
        "  renet compose -- down\n"
        '  echo "down findmnt $(%(fm)s)" >> %(down)s\n'
        "}\n"
    ) % {"fm": fm, "up": PROBE_UP_LOG, "down": PROBE_DOWN_LOG, "bytes": RESTORE_BYTES}


# --------------------------------------------------------------------------- parsers


def sections(text: str) -> dict[str, str]:
    """The `== <name>` sections of a readout."""
    out: dict[str, str] = {}
    name = None
    for line in text.splitlines():
        if line.startswith(SECTION):
            name = line[len(SECTION) :].strip()
            out[name] = ""
        elif name is not None:
            out[name] += line + "\n"
    return out


def flat_keyed(text: str) -> dict[str, int]:
    """A flat-keyed cgroup file (`oom_kill 3`) or /proc/vmstat as a dict; unparseable lines are skipped."""
    out: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("-").isdigit():
            out[parts[0]] = int(parts[1])
    return out


def oom_kills(memory_events: str) -> int | None:
    return flat_keyed(memory_events).get("oom_kill")


def vmstat_oom_kill(text: str) -> int | None:
    return flat_keyed(text).get("oom_kill")


def shmem(memory_stat: str) -> int | None:
    return flat_keyed(memory_stat).get("shmem")


def section_value(readout: str, name: str) -> str:
    return sections(readout).get(name, "").strip()


def oom_groups(readout: str) -> dict[str, str]:
    """Service directory -> its memory.oom.group value."""
    return {
        k.split(" ", 1)[1]: v.strip()
        for k, v in sections(readout).items()
        if k.startswith("oom.group ")
    }


def parse_findmnt(text: str) -> list[dict[str, str]]:
    """`findmnt -rn -o TARGET,FSTYPE,OPTIONS` lines; the probe's lines carry a `findmnt ` or `down findmnt ` prefix and `|` between fields."""
    rows = []
    for raw in text.splitlines():
        line = raw.strip().removeprefix("down ").removeprefix("findmnt").strip()
        fields = [f for f in re.split(r"[ |]+", line) if f]
        if len(fields) >= 2:
            rows.append(
                {"target": fields[0], "fstype": fields[1], "options": ",".join(fields[2:3])}
            )
    return rows


def tmpfs_size(options: str) -> int | None:
    """The size= of a tmpfs option string in bytes (`size=524288k`)."""
    m = re.search(r"(?:^|,)size=(\d+)([kmg]?)(?:,|$)", options)
    if not m:
        return None
    return int(m.group(1)) * {"": 1, "k": 1 << 10, "m": 1 << 20, "g": 1 << 30}[m.group(2)]


def ram_mounted(findmnt: str, target: str) -> tuple[bool, int | None]:
    """(a tmpfs is mounted at target, its size)."""
    for row in parse_findmnt(findmnt):
        if row["target"] == target and row["fstype"] == "tmpfs":
            return True, tmpfs_size(row["options"])
    return False, None


def parse_statfs(text: str) -> tuple[int, int] | None:
    """`stat -f -c '%b %f %S'` (blocks, free, block size) as (size, used) bytes."""
    parts = text.split()
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    blocks, free, bsize = (int(p) for p in parts)
    return blocks * bsize, (blocks - free) * bsize


def started_at(text: str) -> dict[str, str]:
    """`/<name> <StartedAt>` lines as name -> StartedAt."""
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].startswith("/"):
            out[parts[0][1:]] = parts[1]
    return out


def parse_main_pid(text: str) -> int | None:
    found = re.findall(r"^MAINPID=(\d+)\s*$", text, re.MULTILINE)
    pid = int(found[-1]) if found else 0
    return pid or None


def _json_doc(text: str) -> dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return {}
    try:
        doc = json.loads(text[start : end + 1])
    except ValueError:
        return {}
    return doc if isinstance(doc, dict) else {}


def grant_memory_max(text: str) -> int | None:
    value = (_json_doc(text).get("limits") or {}).get("memory_max")
    return value if isinstance(value, int) else None


def marker_mounted_at(text: str) -> str | None:
    value = _json_doc(text).get("mounted_at")
    return str(value) if value else None


# --------------------------------------------------------------------------- verdicts


CONTAINER_LEAF = re.compile(r"^[0-9a-f]{64}$")


def limits_verdict(readout: str, memory_max: int, cpu_max: str) -> tuple[bool, str]:
    """K2.1 for C: memory.max and cpu.max are the granted ones, and every container cgroup under rediacc-<C> has memory.oom.group 1: the KEEP_SERVICE directory and at least one ad-hoc container leaf (a 64-hex id), both made after the limits were applied."""
    mem, cpu, groups = (
        section_value(readout, "memory.max"),
        section_value(readout, "cpu.max"),
        oom_groups(readout),
    )
    ok = (
        mem == str(memory_max)
        and cpu == cpu_max
        and KEEP_SERVICE in groups
        and any(CONTAINER_LEAF.match(name) for name in groups)
        and all(v == "1" for v in groups.values())
    )
    return ok, "memory.max=%s cpu.max=%r oom.group=%s" % (mem, cpu, groups)


def uncapped_verdict(readout: str) -> tuple[bool, str]:
    mem = section_value(readout, "memory.max")
    return mem == "max", "memory.max=%s" % mem


def _delta(pair: tuple[int | None, int | None]) -> int | None:
    before, after = pair
    if before is None or after is None:
        return None
    return after - before


def oom_isolation_verdict(
    c: tuple[int | None, int | None],
    d: tuple[int | None, int | None],
    host: tuple[int | None, int | None],
) -> tuple[bool, str]:
    """K2.2: C's oom_kill rose by at least 1, D's did not move, and the host's /proc/vmstat delta equals C's (no kill outside C)."""
    why = "C %s->%s D %s->%s host %s->%s" % (c[0], c[1], d[0], d[1], host[0], host[1])
    dc, dd, dh = _delta(c), _delta(d), _delta(host)
    if dc is None or dd is None or dh is None:
        return False, "unreadable counter: " + why
    return dc >= 1 and dd == 0 and dh == dc, why


def kept_started_verdict(
    before: dict[str, str], after: dict[str, str], skip: str = ""
) -> tuple[bool, str]:
    """Every container of `before` except `skip` is still running with the same StartedAt; an empty `before` proves nothing and fails."""
    moved = sorted(n for n, t in before.items() if n != skip and after.get(n) != t)
    return bool(before) and not moved, "moved: %s" % (", ".join(moved) or "none")


def shmem_verdict(e_shmem: int | None, exec_shmem: int | None, least: int) -> tuple[bool, str]:
    """K3.3: rediacc-<E>'s shmem holds at least `least` and renet-exec-<E>'s does not (the restore was charged to the repository)."""
    why = "rediacc shmem %s, renet-exec shmem %s, want >= %d inside" % (e_shmem, exec_shmem, least)
    if e_shmem is None:
        return False, "unreadable shmem: " + why
    return e_shmem >= least and (exec_shmem or 0) < least, why


def unmounted_verdict(findmnt_after: str, target: str) -> tuple[bool, str]:
    """K3.5: no `.ram` mount is listed after `repo down --unmount`; a listing that still carries it is FAIL."""
    mounted, _ = ram_mounted(findmnt_after, target)
    return not mounted, ("%s still mounted" if mounted else "no mount at %s") % target


def down_line_verdict(down_log: str) -> tuple[bool, str]:
    """K3.5: down() logged a line while `.ram` was still a tmpfs."""
    lines = [line for line in down_log.splitlines() if line.startswith("down findmnt")]
    return any("tmpfs" in line for line in lines), lines[-1] if lines else "down() logged nothing"


def probe_up_verdict(up_log: str, target: str) -> tuple[bool, str]:
    """K3.1: up()'s first findmnt line shows the tmpfs at target, size RAM_SIZE."""
    first = next((line for line in up_log.splitlines() if line.startswith("findmnt")), "")
    mounted, size = ram_mounted(first, target)
    return mounted and size == RAM_SIZE, first or "up() logged no findmnt line"


# --------------------------------------------------------------------------- live


def run_k2(ctx: Any) -> None:
    """The live K2 step: records K2 rows on `ctx`."""
    _Live(ctx, K2_ID).k2()


def run_k3(ctx: Any) -> None:
    """The live K3 step: records K3 rows on `ctx`."""
    _Live(ctx, K3_ID).k3()


# The registration entries vm_check's EXTRA_RENET_STEPS takes: both fork the run's parent grand, so both need P5.
STEP_K2 = (K2_ID, ("P5",), run_k2)
STEP_K3 = (K3_ID, ("P5",), run_k3)


class _Live:
    def __init__(self, ctx: Any, step: str) -> None:
        self.ctx = ctx
        self.step = step
        self.tag_c, self.tag_d, self.tag_cf, self.tag_e = fork_tags(ctx.tags)
        self.nid: dict[str, int] = {}
        self.mount: dict[str, str] = {}
        self.alloc = "vmc-k2-alloc-%s" % ctx.run_id[-6:]
        self.keep = "vmc-k2-keep-%s" % ctx.run_id[-6:]
        self.adhoc = "vmc-k2-adhoc-%s" % ctx.run_id[-6:]

    # -- helpers ---------------------------------------------------------------

    def check(self, desc: str, ok: bool, res: Any = None, evidence: str = "") -> bool:
        return self.ctx.check(self.step, desc, ok, res, evidence)

    def root(self, command: str, timeout: float = 120.0) -> Any:
        argv = vm_ssh.ssh_argv(
            self.ctx.ssh_user,
            self.ctx.ssh_key,
            self.ctx.worker_ip,
            "sudo sh -c %s" % shlex.quote(command),
        )
        return self.ctx.host_run(argv, env=self.ctx.environ, timeout=timeout)

    def shell(self, tag: str, command: str) -> Any:
        return self.ctx.rdc("term", "connect", self.ctx.ref(tag), "-c", command, refuse=False)

    def policy(self, tag: str, *flags: str) -> Any:
        return self.ctx.rdc("repo", "policy", "set", self.ctx.ref(tag), *flags, refuse=False)

    def readout(self, tag: str) -> str:
        return self.root(cgroup_readout_script(self.nid[tag])).out

    def memory_max(self, tag: str) -> str:
        return section_value(self.readout(tag), "memory.max")

    def starts(self, tag: str) -> dict[str, str]:
        return started_at(self.shell(tag, started_at_command()).out)

    def fork(self, tag: str, source: str = "") -> bool:
        entry: dict[str, Any] = {"tag": tag, "guid": "", "created": True, "deleted": False}
        self.ctx.forks.append(entry)
        res = self.ctx.rdc(
            "repo", "fork", source or self.ctx.opts.parent, "--tag", tag, "--up", timeout=1800
        )
        if not self.check("%s fork %s --up" % (self.step, self.ctx.ref(tag)), res.rc == 0, res):
            return False
        listed, entries = self.ctx.repo_list()
        for e in entries:
            if e.get("name") == self.ctx.ref(tag):
                entry["guid"] = str(e.get("guid", ""))
                nid = e.get("networkId", e.get("network_id"))
                if str(nid or "").isdigit():
                    self.nid[tag] = int(nid)
        self.mount[tag] = "%s/%s" % (MOUNTS, entry["guid"])
        return self.check(
            "%s fork %s listed with a guid and network id" % (self.step, self.ctx.ref(tag)),
            bool(entry["guid"]) and tag in self.nid,
            listed,
        )

    def oom_counters(self) -> tuple[int | None, int | None, int | None]:
        c = oom_kills(sections(self.readout(self.tag_c)).get("memory.events", ""))
        d = oom_kills(sections(self.readout(self.tag_d)).get("memory.events", ""))
        return c, d, vmstat_oom_kill(self.root(vmstat_script()).out)

    # -- K2 --------------------------------------------------------------------

    def k2(self) -> None:
        if not (self.fork(self.tag_c) and self.fork(self.tag_d)):
            return
        ref_c = self.ctx.ref(self.tag_c)
        res = self.policy(self.tag_c, "--memory-max", "1G", "--cpu-max", "1")
        if not self.check(
            "K2.0 rdc repo policy set %s --memory-max 1G --cpu-max 1" % ref_c, res.rc == 0, res
        ):
            return
        try:
            # The containers come after the limits, so K2.1 sees cgroups made after Apply.
            if not self.k2_0_containers():
                return
            ok_c, why_c = limits_verdict(self.readout(self.tag_c), C_MEMORY_MAX, CPU_ONE_CORE)
            ok_d, why_d = uncapped_verdict(self.readout(self.tag_d))
            self.check(
                "K2.1 rediacc-%d capped (1G, one core, oom.group 1); rediacc-%d uncapped"
                % (self.nid[self.tag_c], self.nid[self.tag_d]),
                ok_c and ok_d,
                None,
                "C %s; D %s" % (why_c, why_d),
            )
            self.k2_2_oom()
            self.k2_3_raise()
            res = self.policy(self.tag_c, "--memory-max", REFUSED_MEMORY)
            self.check(
                "K2.4 --memory-max %s without --force is refused" % REFUSED_MEMORY, res.rc != 0, res
            )
            self.k2_5_survives()
            self.k2_6_fork_inherits()
        finally:
            gone = "docker rm -f %s %s %s >/dev/null 2>&1 || true"
            self.shell(self.tag_c, gone % (self.alloc, self.keep, self.adhoc))
            self.shell(self.tag_d, gone % (self.alloc, self.keep, self.adhoc))

    def k2_0_containers(self) -> bool:
        """C and D fork an empty grand, so neither runs a container of its own. C gets a service-directory holder that fills /dev/shm and an ad-hoc one, D a service-directory one: K2.1 reads their oom.group, K2.2 and K2.3 their StartedAt, and K2.4 needs C's usage (vm:check run vmc-11060119-8cbbc0: K2.1 read `{'*': ''}`, K2.2/K2.3 failed on an empty StartedAt baseline, K2.4 had under 16 MiB to protect)."""
        starts = (
            (
                self.tag_c,
                keep_command(
                    self.keep, service_parent(self.nid[self.tag_c], KEEP_SERVICE), HOLD_SHM_BYTES
                ),
            ),
            (self.tag_c, keep_command(self.adhoc)),
            (
                self.tag_d,
                keep_command(self.keep, service_parent(self.nid[self.tag_d], KEEP_SERVICE)),
            ),
        )
        failed = None
        for tag, command in starts:
            res = self.shell(tag, command)
            if res.rc != 0:
                failed = res
                break
        return self.check(
            "K2.0 the holder containers run in C (a service directory and an ad-hoc leaf) and D",
            failed is None,
            failed,
        )

    def k2_2_oom(self) -> None:
        c0, d0, h0 = self.oom_counters()
        before_c, before_d = self.starts(self.tag_c), self.starts(self.tag_d)
        start = self.shell(self.tag_c, alloc_command(self.alloc))
        self.shell(self.tag_c, "docker wait %s" % self.alloc)
        c1, d1, h1 = self.oom_counters()
        ok, why = oom_isolation_verdict((c0, c1), (d0, d1), (h0, h1))
        ok_c, why_c = kept_started_verdict(before_c, self.starts(self.tag_c), skip=self.alloc)
        ok_d, why_d = kept_started_verdict(before_d, self.starts(self.tag_d))
        ssh = self.ctx.probe("true")
        self.check(
            "K2.2 the alloc container is OOM-killed inside C only; other containers keep StartedAt; sshd answers",
            start.rc == 0 and ok and ok_c and ok_d and ssh.rc == 0,
            start,
            "%s; C %s; D %s; ssh rc=%d" % (why, why_c, why_d, ssh.rc),
        )

    def k2_3_raise(self) -> None:
        nid = self.nid[self.tag_c]
        pid0 = parse_main_pid(self.root(main_pid_script(nid)).out)
        before = self.starts(self.tag_c)
        res = self.policy(self.tag_c, "--memory-max", "1536M")
        mem = self.memory_max(self.tag_c)
        pid1 = parse_main_pid(self.root(main_pid_script(nid)).out)
        ok_c, why_c = kept_started_verdict(before, self.starts(self.tag_c))
        self.check(
            "K2.3 --memory-max 1536M applies live: memory.max %d, MainPID and start times unchanged"
            % C_MEMORY_RAISED,
            res.rc == 0
            and mem == str(C_MEMORY_RAISED)
            and pid0 is not None
            and pid0 == pid1
            and ok_c,
            res,
            "memory.max=%s MainPID %s->%s %s" % (mem, pid0, pid1, why_c),
        )

    def k2_5_survives(self) -> None:
        nid = self.nid[self.tag_c]
        reload = self.root("systemctl daemon-reload && systemctl restart systemd-journald")
        mem1 = self.memory_max(self.tag_c)
        restart = self.root("systemctl restart rediacc-docker-%d" % nid, timeout=300)
        mem2 = self.memory_max(self.tag_c)
        want = str(C_MEMORY_RAISED)
        self.check(
            "K2.5 memory.max survives daemon-reload, an unrelated restart and a restart of rediacc-docker-%d"
            % nid,
            reload.rc == 0 and restart.rc == 0 and mem1 == want and mem2 == want,
            restart if restart.rc else reload,
            "after reload %s, after the daemon restart %s" % (mem1, mem2),
        )

    def k2_6_fork_inherits(self) -> None:
        if not self.fork(self.tag_cf, self.ctx.ref(self.tag_c)):
            return
        grant = grant_memory_max(self.root(grant_show_script(self.nid[self.tag_cf])).out)
        mem = self.memory_max(self.tag_cf)
        self.check(
            "K2.6 a fork of C inherits memory.max",
            grant == C_MEMORY_RAISED and mem == str(C_MEMORY_RAISED),
            None,
            "grant memory_max=%s cgroup memory.max=%s" % (grant, mem),
        )

    # -- K3 --------------------------------------------------------------------

    def k3(self) -> None:
        e = self.tag_e
        if not self.fork(e) or not self.k3_0_setup(e):
            return
        target = ram_dir(self.mount[e])
        up_log = self.shell(e, "cat %s" % PROBE_UP_LOG).out
        ok, why = probe_up_verdict(up_log, target)
        self.check("K3.1 the tmpfs is at %s, size 512M, before up() runs" % target, ok, None, why)
        w = self.root(writer_command(self.mount[e], self.nid[e]))
        self.check(
            "K3.2 a container writes %s into .ram/data through a bind" % MARKER,
            w.rc == 0 and MARKER in w.out,
            w,
        )
        self.k3_3_charged(e, up_log)
        restart = self.root("systemctl restart rediacc-docker-%d" % self.nid[e], timeout=300)
        kept = self.root("cat %s/data/%s" % (target, MARKER))
        self.check(
            "K3.4 %s survives systemctl restart rediacc-docker-%d" % (MARKER, self.nid[e]),
            restart.rc == 0 and kept.rc == 0 and MARKER in kept.out,
            kept,
        )
        self.k3_5_unmount(e, target)
        # K3.6 (the reboot row) is not run here, and a recorded skip row would keep the renet phase from ever counting (vm_check.phase_ran requires every row ok), so it is a note, as vm_check prints its own not-run steps.
        self.ctx.say("  %-5s %-6s %s" % (K3_ID, "--", K3_6_NOTE))

    def k3_0_setup(self, e: str) -> bool:
        pol = self.policy(e, "--memory-max", "1536M", "--ram-volume", "512M")
        work = self.ctx.work / "k3-probe"
        work.mkdir(parents=True, exist_ok=True)
        (work / "Rediaccfile").write_text(probe_rediaccfile())
        (work / COMPOSE_FILE).write_text(compose_body())
        sent = self.ctx.rdc(
            "repo", "sync", "upload", self.ctx.ref(e), "--local", str(work) + "/", refuse=False
        )
        # The volume is mounted at the daemon's next start, so the repository goes down and up again.
        down = self.ctx.rdc("repo", "down", self.ctx.ref(e), "--unmount", timeout=900, refuse=False)
        up = self.ctx.rdc("repo", "up", self.ctx.ref(e), timeout=900, refuse=False)
        failed = next((r for r in (pol, sent, down, up) if r.rc != 0), None)
        return self.check(
            "K3.0 fork %s up with --ram-volume 512M --memory-max 1536M and the probe Rediaccfile"
            % self.ctx.ref(e),
            failed is None,
            failed or up,
        )

    def k3_3_charged(self, e: str, up_log: str) -> None:
        e_shmem = shmem(sections(self.readout(e)).get("memory.stat", ""))
        exec_shmem = shmem(self.root(exec_stat_script(self.nid[e])).out)
        restored = ("restored %d" % RESTORE_BYTES) in up_log
        ok, why = shmem_verdict(e_shmem, exec_shmem, RESTORE_BYTES)
        self.check(
            "K3.3 up() restored %d bytes into .ram, charged to rediacc-%d and not to renet-exec-%d"
            % (RESTORE_BYTES, self.nid[e], self.nid[e]),
            restored and ok,
            None,
            why,
        )

    def k3_5_unmount(self, e: str, target: str) -> None:
        before = marker_mounted_at(self.root("cat %s/%s" % (target, RAM_MARKER_FILE)).out)
        down = self.ctx.rdc("repo", "down", self.ctx.ref(e), "--unmount", timeout=900, refuse=False)
        ok_u, why_u = unmounted_verdict(self.root(findmnt_script(self.mount[e])).out, target)
        up = self.ctx.rdc("repo", "up", self.ctx.ref(e), timeout=900, refuse=False)
        ok_d, why_d = down_line_verdict(self.shell(e, "cat %s" % PROBE_DOWN_LOG).out)
        gone = self.root("test ! -e %s/data/%s" % (target, MARKER))
        now = marker_mounted_at(self.root("cat %s/%s" % (target, RAM_MARKER_FILE)).out)
        self.check(
            "K3.5 down --unmount: down() ran with .ram mounted, no .ram mount after; after up the marker is gone and mounted_at is new",
            down.rc == 0
            and up.rc == 0
            and ok_u
            and ok_d
            and gone.rc == 0
            and now is not None
            and now != before,
            down if down.rc else up,
            "%s; %s; mounted_at %s -> %s" % (why_u, why_d, before, now),
        )
