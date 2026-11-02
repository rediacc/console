"""G1 of agent/plans/PLAN-gpu-device-grants.md (box T1): a CDI device reaches a repository's containers only through its device grant, proven with a FAKE device on the ops worker (which has no GPU).

`vm_check.py` registers this module once, through `EXTRA_RENET_STEPS`, as the `G1` step of the renet phase, after U2; `--only G1` drags in P5, so the run's parent grand exists. `ctx` is the running `VmCheck`: every VM action goes through its `./rdc.sh` helpers (`rdc`, `shell`), its raw ssh probe recipe (`vm_ssh.ssh_argv` through `host_run`, the U1/U2/I1 pattern) and its ledger (`check`, `record`).

THE FAKE DEVICE. A character node `/dev/rediacc-fake` and a CDI spec `/etc/cdi/fake.yaml` (kind `rediacc.io/fake`, device `one` mapping that node, its type and numbers spelled out so no daemon has to stat the host path). Both are written BEFORE the forks exist, so each fork's dockerd starts with the spec already in `/etc/cdi`, and both are removed by the teardown. The node is `c 60:0`, not the box's `c 1 3`: 1:3 is `/dev/null`, which every container's default device rules already admit, so the cgroup row could never fail on it. Major 60 is a LANANA "local/experimental" number no driver claims, so opening the node is harmless: ENXIO when the device cgroup admits it, EPERM when it does not, an open probe that judges the cgroup on v1 and v2 alike.

THE ROWS. G1.0 the fake node and spec are in place; G1.1 an ungranted fork's `docker run --device rediacc.io/fake=one` is refused with D6's message; G1.2 `rdc repo gpu grant` grants it and the machine's grant lists it; G1.3 a granted container sees `/dev/rediacc-fake` and no other node beyond an ungranted container's `/dev`; G1.4 its device cgroup admits `c 60:0` beyond the defaults (the open probe gives ENXIO, and v1 `devices.list` or the v2 device eBPF program read through `bpftool cgroup list` carries exactly that one rule more than an ungranted container's); G1.5 an exclusive grant on fork A refuses a grant on fork B, which stays ungranted; G1.6 the grant survives `rdc repo down`/`rdc repo up`; G1.7 it survives `rdc machine converge --policy always`, which restarts the fork's daemon.

TEARDOWN. Both forks join `ctx.forks`, so the run's own teardown deletes them and purges their licence state even when G1 crashes. The detached containers, the grants, the spec and the node are removed here; anything that stays rides `ctx.sweep_leftovers`, so the run cannot reach VERIFIED over it.

The CLI-free pieces (the spec text, the root scripts, and the parsers and verdicts of `/dev` listings, cgroup readouts, grant files and refusals) are pure functions, pinned by `tests/test_drills_gpu_grants.py` without a machine.
"""

from __future__ import annotations

import base64
import json
import re
import shlex
from typing import Any

from rediacc_ci.drills import converge_preflight, vm_ssh
from rediacc_ci.drills.upgrade_converge import new_docker_socket
from rediacc_ci.well_known import INFRA_DOMAIN

STEP_ID = "G1"

CDI_KIND = INFRA_DOMAIN + "/fake"
CDI_DEVICE = "one"
CDI_NAME = "%s=%s" % (CDI_KIND, CDI_DEVICE)
CDI_VERSION = "0.6.0"
SPEC_PATH = "/etc/cdi/fake.yaml"
NODE_PATH = "/dev/rediacc-fake"
NODE_NAME = NODE_PATH.rsplit("/", 1)[1]
# LANANA "local/experimental use" (60-63): no driver claims it, so an open is ENXIO when the cgroup admits it.
NODE_MAJOR = 60
NODE_MINOR = 0
NODE_RULE = "c %d:%d rwm" % (NODE_MAJOR, NODE_MINOR)
IMAGE = "busybox:1.36"
# D6's refusal of an ungranted CDI name (private/renet/pkg/dockerpolicy/devices.go evalDeviceRequests).
NOT_GRANTED = "is not granted to this repository"
GRANT_VERB = "rdc repo gpu grant"
# dockergrant.ErrDeviceHeld's English text (grant.device_held_exclusively, grant.device_held_cannot_be_exclusive).
HELD_EXCLUSIVELY = "granted exclusively to network"
HELD_CANNOT_BE_EXCLUSIVE = "cannot be granted exclusively"
ENXIO = "No such device or address"
EPERM = "Operation not permitted"
# Output markers of the in-container probes and the root cgroup readout.
DEV_PREFIX = "N:"
OPEN_PREFIX = "O:"
RULE_PREFIX = "RULE:"
XLATED_PREFIX = "XL:"
SECTION = "== "
DOCKER_RC = "DOCKER_RC="
MAIN_PID = "MAINPID="
# renet's runtime stamp directory (private/renet/pkg/daemon/runtime_epoch.go runtimeStateDir); a running daemon with no stamp is stale (`no_stamp`).
STAMP_DIR = "/var/lib/rediacc/runtime"


def spec_text() -> str:
    """The CDI spec of the fake device: kind `rediacc.io/fake`, device `one`, one character node with its numbers spelled out."""
    return (
        'cdiVersion: "%(ver)s"\n'
        "kind: %(kind)s\n"
        "devices:\n"
        "  - name: %(dev)s\n"
        "    containerEdits:\n"
        "      deviceNodes:\n"
        "        - path: %(node)s\n"
        "          type: c\n"
        "          major: %(major)d\n"
        "          minor: %(minor)d\n"
    ) % {
        "ver": CDI_VERSION,
        "kind": CDI_KIND,
        "dev": CDI_DEVICE,
        "node": NODE_PATH,
        "major": NODE_MAJOR,
        "minor": NODE_MINOR,
    }


def setup_script() -> str:
    """Root on the worker: create the fake node and write the spec (through base64, so no quoting meets the YAML), then print the node's `ls -ln` and the spec's kind line as proof."""
    b64 = base64.b64encode(spec_text().encode()).decode()
    return (
        "set -e; rm -f %(node)s; mknod -m 0666 %(node)s c %(major)d %(minor)d; "
        "mkdir -p %(dir)s; printf %%s %(b64)s | base64 -d > %(spec)s; chmod 0644 %(spec)s; "
        "ls -ln %(node)s; grep '^kind:' %(spec)s"
    ) % {
        "node": NODE_PATH,
        "major": NODE_MAJOR,
        "minor": NODE_MINOR,
        "dir": SPEC_PATH.rsplit("/", 1)[0],
        "b64": b64,
        "spec": SPEC_PATH,
    }


def remove_containers_script(*names: str) -> str:
    """`docker rm -f` of each name; only a `No such container` answer is forgiven (a failed first `docker run -d` leaves the second name absent), so a container whose removal fails for any other reason fails the script."""
    return (
        'rc=0; for c in %s; do o=$(docker rm -f $c 2>&1) || case "$o" in '
        '*"No such container"*) ;; *) echo "$o" >&2; rc=1 ;; esac; done; exit $rc' % " ".join(names)
    )


def teardown_script() -> str:
    """Root on the worker: remove the spec and the node; exits 0 only when both are gone."""
    return "rm -f %(spec)s %(node)s; test ! -e %(spec)s && test ! -e %(node)s" % {
        "spec": SPEC_PATH,
        "node": NODE_PATH,
    }


def stamp_path(network_id: int | str) -> str:
    return "%s/net-%d.json" % (STAMP_DIR, int(network_id))


def main_pid_script(network_id: int | str) -> str:
    """Root on the worker: the repo daemon unit's MainPID as `MAINPID=<n>` (0 when the unit has no process)."""
    return "echo %s$(systemctl show -p MainPID --value rediacc-docker-%d)" % (
        MAIN_PID,
        int(network_id),
    )


def make_stale_script(network_id: int | str) -> str:
    """Root on the worker: delete the network's runtime stamp, so `converge --policy always` finds the running daemon stale (`no_stamp`) and restarts it; exits 0 only when the stamp is gone."""
    path = stamp_path(network_id)
    return "rm -f %s; test ! -e %s" % (path, path)


def parse_main_pid(text: str) -> int | None:
    """The last `MAINPID=<n>` of `text`, or None when there is none or the unit has no process (0)."""
    found = re.findall(r"^%s(\d+)\s*$" % MAIN_PID, text, re.MULTILINE)
    pid = int(found[-1]) if found else 0
    return pid or None


def restarted_verdict(before: int | None, after: int | None) -> tuple[bool, str]:
    """(restarted, evidence): both MainPIDs were read and differ."""
    ok = before is not None and after is not None and before != after
    return ok, "MainPID %s -> %s" % (before, after)


def setup_verdict(text: str) -> bool:
    """True when the setup printed a character node with the fake's numbers and the spec's kind."""
    node = re.search(
        r"^c\S*\s.*\b%d,\s*%d\b.*%s\s*$" % (NODE_MAJOR, NODE_MINOR, re.escape(NODE_PATH)),
        text,
        re.MULTILINE,
    )
    return bool(node) and ("kind: %s" % CDI_KIND) in text


def docker_run(args: str, command: str = "true") -> str:
    """A fork shell's `docker run --rm <args> busybox <command>`, its output folded onto stdout and its status printed as `DOCKER_RC=<n>`."""
    return "docker run --rm %s %s %s 2>&1; echo %s$?" % (args, IMAGE, command, DOCKER_RC)


def device_flag() -> str:
    return "--device %s" % CDI_NAME


def probe_command() -> str:
    """The in-container probe: every `/dev` entry as `N:<name>`, then the open of the fake node as `O:<line>` (`head` prints the errno on failure)."""
    return "sh -c %s" % shlex.quote(
        "ls -1A /dev | sed 's/^/%s/'; head -c1 %s 2>&1 | sed 's/^/%s/'; echo %sdone"
        % (DEV_PREFIX, NODE_PATH, OPEN_PREFIX, OPEN_PREFIX)
    )


def open_command() -> str:
    """The open probe alone, for `docker exec` into a running granted container."""
    return "sh -c %s" % shlex.quote(
        "head -c1 %s 2>&1 | sed 's/^/%s/'; echo %sdone" % (NODE_PATH, OPEN_PREFIX, OPEN_PREFIX)
    )


def docker_rc(text: str) -> int | None:
    """The status `docker_run` printed, or None when the marker never printed."""
    found = re.findall(r"^%s(\d+)\s*$" % DOCKER_RC, text, re.MULTILINE)
    return int(found[-1]) if found else None


def dev_entries(text: str) -> set[str]:
    """The `/dev` entries a probe printed."""
    return {
        m.strip()
        for m in re.findall(r"^%s(.+)$" % re.escape(DEV_PREFIX), text, re.MULTILINE)
        if m.strip()
    }


def open_lines(text: str) -> list[str]:
    return [m.strip() for m in re.findall(r"^%s(.*)$" % OPEN_PREFIX, text, re.MULTILINE)]


def not_granted_verdict(text: str) -> tuple[bool, str]:
    """(refused, evidence) of G1.1: `docker run` failed and the output names D6's refusal of the fake device and the grant verb."""
    rc = docker_rc(text)
    named = NOT_GRANTED in text and GRANT_VERB in text and CDI_NAME in text
    line = next((ln.strip() for ln in text.splitlines() if NOT_GRANTED in ln), "")
    return (
        rc is not None and rc != 0 and named,
        "docker rc=%s D6 message named=%s %s" % (rc, named, line or _clip(text)),
    )


def added_nodes_verdict(granted: str, baseline: str) -> tuple[bool, str]:
    """(ok, evidence) of G1.3: both probes ran (rc 0, a listing), and the granted container's `/dev` holds the fake node and nothing else beyond the baseline's."""
    g_rc, b_rc = docker_rc(granted), docker_rc(baseline)
    g, b = dev_entries(granted), dev_entries(baseline)
    added = sorted(g - b)
    ok = g_rc == 0 and b_rc == 0 and bool(b) and added == [NODE_NAME]
    return ok, "granted rc=%s baseline rc=%s added=%s (baseline %d entries)" % (
        g_rc,
        b_rc,
        added,
        len(b),
    )


def open_verdict(text: str) -> tuple[bool, str]:
    """(admitted, evidence): the open of the fake node failed with ENXIO (the cgroup admitted it, no driver answered), never EPERM (the cgroup refused it)."""
    lines = open_lines(text)
    joined = " | ".join(x for x in lines if x and x != "done")
    return (ENXIO in joined and EPERM not in joined), "open: %s" % (joined or "<nothing>")


BPFTOOL_PREREQUISITE = (
    "PREREQUISITE MISSING, not a device-cgroup verdict: v2 rule read needs bpftool on the worker and provisioning does not install it; "
    "the drill's own install (apt linux-tools-common + linux-tools-$(uname -r), else bpftool) failed on this worker; "
    "install it by hand: Debian/Ubuntu `sudo apt-get update && sudo apt-get install -y linux-tools-common linux-tools-$(uname -r)` (Debian: `bpftool`), "
    "Fedora/Oracle/RHEL `sudo dnf install -y bpftool`, openSUSE `sudo zypper --non-interactive install bpftool`"
)


def cgroup_script(socket: str, names: tuple[str, ...]) -> str:
    """Root on the worker: for each container (by name, on the repo daemon at `socket`), a `== <name>` section with its cgroup version and its device rules: v1 `devices.list` as `RULE:` lines, v2 every device program `bpftool cgroup list` names, dumped as `XL:` lines (`NOBPFTOOL` without bpftool)."""
    body = (
        # The drill installs its own prerequisite on the dev worker: bpftool is a test tool, not a renet runtime need, so it stays out of renet's customer package sets.
        "ensure_bpftool() { "
        'if command -v apt-get >/dev/null 2>&1; then apt-get update -qq; DEBIAN_FRONTEND=noninteractive apt-get install -y linux-tools-common "linux-tools-$(uname -r)" || DEBIAN_FRONTEND=noninteractive apt-get install -y bpftool; '
        "elif command -v dnf >/dev/null 2>&1; then dnf install -y bpftool; "
        "elif command -v zypper >/dev/null 2>&1; then zypper --non-interactive install bpftool; fi; }; "
        'rd() { echo "%(sec)s$1"; '
        'pid=$(docker -H unix://%(sock)s inspect -f \'{{.State.Pid}}\' "$1" 2>&1) || { echo "NOPID: $pid"; return; }; '
        "v1=$(awk -F: '$2 ~ /(^|,)devices(,|$)/ {print $3}' /proc/$pid/cgroup); "
        'if [ -n "$v1" ]; then echo CGV=1; sed \'s/^/%(rule)s/\' "/sys/fs/cgroup/devices$v1/devices.list"; return; fi; '
        'v2=$(awk -F: \'$1=="0" {print $3}\' /proc/$pid/cgroup); echo "CGV=2 CG=$v2"; '
        # One install attempt per script run: a failed install is not repeated for every container.
        'command -v bpftool >/dev/null 2>&1 || [ -n "$BT_TRIED" ] || { BT_TRIED=1; ensure_bpftool >/dev/null 2>&1; }; '
        "command -v bpftool >/dev/null 2>&1 || { echo NOBPFTOOL; return; }; "
        "for id in $(bpftool cgroup list \"/sys/fs/cgroup$v2\" | awk '$2 ~ /device/ {print $1}'); do "
        "echo PROG=$id; bpftool prog dump xlated id $id | sed 's/^/%(xl)s/'; done; }; "
    ) % {"sec": SECTION, "sock": shlex.quote(socket), "rule": RULE_PREFIX, "xl": XLATED_PREFIX}
    return body + "; ".join("rd %s" % shlex.quote(n) for n in names)


def split_cgroup_sections(text: str) -> dict[str, str]:
    """The `cgroup_script` output by container name."""
    sections: dict[str, str] = {}
    current = None
    for line in text.splitlines():
        if line.startswith(SECTION):
            current = line[len(SECTION) :].strip()
            sections[current] = ""
        elif current is not None:
            sections[current] += line + "\n"
    return sections


def cgroup_version(section: str) -> int | None:
    m = re.search(r"^CGV=(\d)", section, re.MULTILINE)
    return int(m.group(1)) if m else None


def v1_rules(section: str) -> set[str]:
    """The `devices.list` rules of a v1 section, whitespace-normalized."""
    return {
        " ".join(m.split())
        for m in re.findall(r"^%s(.+)$" % re.escape(RULE_PREFIX), section, re.MULTILINE)
        if m.strip()
    }


_IMM = re.compile(r"\bif [rw]\d+ (?:!=|==) (0x[0-9a-fA-F]+|-?\d+) goto\b")


def v2_compare_immediates(section: str) -> set[int]:
    """The immediates the dumped device programs compare a register against (`if r4 != 0x3c goto ...`): the device types, majors and minors their rules name."""
    values: set[int] = set()
    for line in section.splitlines():
        if not line.startswith(XLATED_PREFIX):
            continue
        for raw in _IMM.findall(line):
            values.add(int(raw, 0))
    return values


def cgroup_rules_verdict(granted: str, baseline: str) -> tuple[bool, str]:
    """(ok, evidence) of G1.4's rule half: both containers on the same cgroup version, and the granted one carries exactly the fake device's rule beyond the baseline's. v1: `devices.list` differs by `c 60:0 rwm` alone. v2: the programs' compared immediates differ by the major 60 alone (minor 0 is already compared for `c 5:0`)."""
    gv, bv = cgroup_version(granted), cgroup_version(baseline)
    if gv is None or gv != bv:
        return False, "cgroup version granted=%s baseline=%s %s" % (gv, bv, _clip(granted))
    if gv == 1:
        g, b = v1_rules(granted), v1_rules(baseline)
        extra = sorted(g - b)
        return bool(b) and extra == [NODE_RULE], "v1 extra rules=%s (baseline %d rules)" % (
            extra,
            len(b),
        )
    if "NOBPFTOOL" in granted or "NOBPFTOOL" in baseline:
        return False, BPFTOOL_PREREQUISITE
    granted_imm, baseline_imm = v2_compare_immediates(granted), v2_compare_immediates(baseline)
    extra_imm = sorted(granted_imm - baseline_imm)
    progs = len(re.findall(r"^PROG=", granted, re.MULTILINE))
    return bool(baseline_imm) and extra_imm == [
        NODE_MAJOR
    ], "v2 extra compared values=%s (programs %d)" % (
        extra_imm,
        progs,
    )


def grant_show_script(network_id: int | str) -> str:
    """Root on the worker: the network's grant as renet prints it."""
    return "renet daemon grant --network-id %d --show" % int(network_id)


def revoke_script(network_id: int | str) -> str:
    """Root on the worker: revoke the fake device from the network's grant (the teardown's fallback when the CLI verb failed)."""
    return "renet daemon grant --network-id %d --revoke-device %s" % (
        int(network_id),
        shlex.quote(CDI_NAME),
    )


def parse_grant_devices(text: str) -> dict[str, bool] | None:
    """The granted devices (name -> exclusive) of the first grant object in `text` (one with `version`, `devices` or `repo_mount_path`), or None when there is none. A grant with no devices is `{}`."""
    decoder = json.JSONDecoder()
    pos = text.find("{")
    while pos >= 0:
        try:
            doc, _end = decoder.raw_decode(text, pos)
        except ValueError:
            pos = text.find("{", pos + 1)
            continue
        if isinstance(doc, dict) and any(
            k in doc for k in ("version", "devices", "repo_mount_path")
        ):
            out: dict[str, bool] = {}
            for dev in doc.get("devices") or []:
                if isinstance(dev, dict) and dev.get("name"):
                    out[str(dev["name"])] = bool(dev.get("exclusive"))
            return out
        pos = text.find("{", pos + 1)
    return None


def exclusive_refusal_verdict(rc: int, text: str, holder: int | str) -> tuple[bool, str]:
    """(refused, evidence) of G1.5: the grant on the second fork failed and named the exclusive holder's network."""
    named = HELD_EXCLUSIVELY in text and str(holder) in text
    line = next((ln.strip() for ln in text.splitlines() if HELD_EXCLUSIVELY in ln), "")
    return rc != 0 and named, "rc=%d holder named=%s %s" % (rc, named, line or _clip(text))


def _clip(text: str, limit: int = 200) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "..."


def fork_tags(tags: tuple[str, str]) -> tuple[str, str]:
    """G1's two forks: fork A's run tag with `-a` turned into `-d` and `-e`, so the stale-fork sweep (`vm_check.FORK_TAG`) still recognises them."""
    stem = tags[0].removesuffix("-a")
    return stem + "-d", stem + "-e"


# --------------------------------------------------------------------------- live


def run(ctx: Any) -> None:
    """The live G1 step. Records G1 rows on `ctx`; removes its containers, grants, spec and node, and appends any leftover to `ctx.sweep_leftovers`."""
    _LiveG1(ctx).execute()


# The registration entry vm_check's EXTRA_RENET_STEPS takes: (step id, the steps `--only` drags in, the live function). G1 forks the run's parent grand, so it needs P5.
STEP = (STEP_ID, ("P5",), run)


class _LiveG1:
    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self.tag_a, self.tag_b = fork_tags(ctx.tags)
        self.ref_a, self.ref_b = ctx.ref(self.tag_a), ctx.ref(self.tag_b)
        suffix = ctx.run_id[-6:]
        self.ctr_dev = "vmc-g1-dev-%s" % suffix
        self.ctr_base = "vmc-g1-base-%s" % suffix
        self.nid: dict[str, int] = {}
        self.guid: dict[str, str] = {}
        self.fake_written = False
        self.granted: set[str] = set()
        self.detached = False

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

    def quiet_shell(self, ref: str, command: str) -> Any:
        """A shell whose refusal must not stop the step (a refused `docker run` is the row, and a cleanup must run on)."""
        return self.ctx.rdc("term", "connect", ref, "-c", command, refuse=False)

    def grant_devices(self, key: str) -> tuple[Any, dict[str, bool] | None]:
        res = self.root(grant_show_script(self.nid[key]))
        return res, parse_grant_devices(res.out) if res.rc == 0 else None

    def gpu(self, verb: str, ref: str, *extra: str) -> Any:
        return self.ctx.rdc("repo", "gpu", verb, ref, "--device", CDI_NAME, *extra, refuse=False)

    # -- the run ---------------------------------------------------------------

    def execute(self) -> None:
        try:
            if not self.g1_0_setup():
                return
            if not self._fork("a", self.tag_a, self.ref_a):
                return
            self.g1_1_ungranted()
            if not self.g1_2_grant():
                return
            self.g1_3_nodes("G1.3")
            self.g1_4_cgroup()
            if self._fork("b", self.tag_b, self.ref_b):
                self.g1_5_exclusive()
            self.g1_6_down_up()
            self.g1_7_converge()
        finally:
            self._cleanup()

    def g1_0_setup(self) -> bool:
        res = self.root(setup_script())
        self.fake_written = True
        return self.check(
            "G1.0 %s (c %d:%d) and %s (kind %s, device %s) written on the worker"
            % (NODE_PATH, NODE_MAJOR, NODE_MINOR, SPEC_PATH, CDI_KIND, CDI_DEVICE),
            res.rc == 0 and setup_verdict(res.out),
            res,
            res.text(),
        )

    def _fork(self, key: str, tag: str, ref: str) -> bool:
        fork = {"tag": tag, "guid": "", "created": True, "deleted": False}
        self.ctx.forks.append(fork)
        res = self.ctx.rdc("repo", "fork", self.ctx.opts.parent, "--tag", tag, "--up", timeout=1800)
        if not self.check("G1 fork %s --up" % ref, res.rc == 0, res):
            return False
        listed, entries = self.ctx.repo_list()
        for entry in entries:
            if entry.get("name") == ref:
                self.guid[key] = str(entry.get("guid", ""))
                nid = entry.get("networkId", entry.get("network_id"))
                if str(nid or "").isdigit():
                    self.nid[key] = int(nid)
        fork["guid"] = self.guid.get(key, "")
        return self.check(
            "G1 fork %s listed with a guid and network id" % ref,
            bool(self.guid.get(key)) and bool(self.nid.get(key)),
            listed,
            "guid %s network id %s" % (self.guid.get(key), self.nid.get(key)),
        )

    def g1_1_ungranted(self) -> None:
        res = self.quiet_shell(self.ref_a, docker_run(device_flag()))
        ok, why = not_granted_verdict(res.out + "\n" + res.err)
        self.check(
            "G1.1 ungranted %s: docker run --device %s refused with D6's message"
            % (self.ref_a, CDI_NAME),
            ok,
            res,
            why,
        )

    def g1_2_grant(self) -> bool:
        res = self.gpu("grant", self.ref_a)
        if res.rc == 0:
            self.granted.add("a")
        show, devices = self.grant_devices("a")
        return self.check(
            "G1.2 rdc repo gpu grant %s --device %s; net-%d's grant lists it"
            % (self.ref_a, CDI_NAME, self.nid["a"]),
            res.rc == 0 and devices is not None and CDI_NAME in devices,
            res if res.rc != 0 else show,
            "grant rc=%d devices=%s" % (res.rc, devices),
        )

    def _granted_probe(self) -> tuple[Any, Any]:
        granted = self.quiet_shell(self.ref_a, docker_run(device_flag(), probe_command()))
        baseline = self.quiet_shell(self.ref_a, docker_run("", probe_command()))
        return granted, baseline

    def g1_3_nodes(self, row: str, when: str = "") -> None:
        granted, baseline = self._granted_probe()
        ok, why = added_nodes_verdict(granted.out, baseline.out)
        self.check(
            "%s granted %s%s: the container sees %s and no other node beyond an ungranted one's /dev"
            % (row, self.ref_a, when, NODE_PATH),
            ok,
            granted,
            why,
        )

    def g1_4_cgroup(self) -> None:
        start = self.quiet_shell(
            self.ref_a,
            "docker run -d --name %s %s %s sleep 900 && docker run -d --name %s %s sleep 900"
            % (self.ctr_dev, device_flag(), IMAGE, self.ctr_base, IMAGE),
        )
        self.detached = True
        if not self.check(
            "G1.4 two detached containers in %s, one with %s, one without" % (self.ref_a, CDI_NAME),
            start.rc == 0,
            start,
            self.ctx.remote_evidence(start) if start.rc != 0 else "",
        ):
            return
        probe = self.quiet_shell(self.ref_a, "docker exec %s %s" % (self.ctr_dev, open_command()))
        opened, open_why = open_verdict(probe.out)
        read = self.root(
            cgroup_script(new_docker_socket(self.nid["a"]), (self.ctr_dev, self.ctr_base))
        )
        sections = split_cgroup_sections(read.out)
        rules_ok, rules_why = cgroup_rules_verdict(
            sections.get(self.ctr_dev, ""), sections.get(self.ctr_base, "")
        )
        log_path = self.ctx.keep_log(STEP_ID, "cgroup", ["cgroup_script"], read)
        self.ctx.check(
            STEP_ID,
            "G1.4 the granted container's device cgroup admits c %d:%d beyond the defaults"
            % (NODE_MAJOR, NODE_MINOR),
            read.rc == 0 and opened and rules_ok,
            read,
            "%s; %s" % (open_why, rules_why),
            log_path=log_path,
        )

    def g1_5_exclusive(self) -> None:
        excl = self.gpu("grant", self.ref_a, "--exclusive")
        show, devices = self.grant_devices("a")
        if not self.check(
            "G1.5 rdc repo gpu grant %s --exclusive; net-%d's grant marks it exclusive"
            % (self.ref_a, self.nid["a"]),
            excl.rc == 0 and bool(devices) and (devices or {}).get(CDI_NAME) is True,
            excl if excl.rc != 0 else show,
            "grant rc=%d devices=%s" % (excl.rc, devices),
        ):
            return
        second = self.gpu("grant", self.ref_b)
        if second.rc == 0:
            self.granted.add("b")
        ok, why = exclusive_refusal_verdict(second.rc, second.text(), self.nid["a"])
        _show_b, devices_b = self.grant_devices("b")
        self.check(
            "G1.5 an exclusive grant on %s refuses %s, whose grant stays without the device"
            % (self.ref_a, self.ref_b),
            ok and devices_b is not None and CDI_NAME not in devices_b,
            second,
            "%s; %s devices=%s" % (why, self.ref_b, devices_b),
        )
        run_b = self.quiet_shell(self.ref_b, docker_run(device_flag()))
        refused, refused_why = not_granted_verdict(run_b.out + "\n" + run_b.err)
        self.check(
            "G1.5 %s's docker run --device %s is still refused" % (self.ref_b, CDI_NAME),
            refused,
            run_b,
            refused_why,
        )

    def _grant_still_listed(self, row: str, when: str) -> None:
        show, devices = self.grant_devices("a")
        self.check(
            "%s net-%d's grant still lists %s %s" % (row, self.nid["a"], CDI_NAME, when),
            devices is not None and CDI_NAME in devices,
            show,
            "devices=%s" % devices,
        )

    def g1_6_down_up(self) -> None:
        self._remove_detached()
        down = self.ctx.rdc("repo", "down", self.ref_a, timeout=900, refuse=False)
        up = self.ctx.rdc("repo", "up", self.ref_a, timeout=900, refuse=False)
        if not self.check(
            "G1.6 rdc repo down then up %s" % self.ref_a,
            down.rc == 0 and up.rc == 0,
            down if down.rc != 0 else up,
            "down rc=%d up rc=%d" % (down.rc, up.rc),
        ):
            return
        self._grant_still_listed("G1.6", "after down/up")
        self.g1_3_nodes("G1.6", " after down/up")

    def _main_pid(self, key: str) -> int | None:
        return parse_main_pid(self.root(main_pid_script(self.nid[key])).out)

    def g1_7_converge(self) -> None:
        # --policy always restarts only a stale daemon or one stamped by another renet binary; G1.6 just restarted this one under the installed binary, so make it stale first.
        pid_before = self._main_pid("a")
        # The MainPID is read before anything changes, so a row that cannot judge a restart leaves the stamp untouched.
        if not self.check(
            "G1.7 net-%d's daemon MainPID is readable before the converge" % self.nid["a"],
            pid_before is not None,
            None,
            "MainPID=%s" % pid_before,
        ):
            return
        stale = self.root(make_stale_script(self.nid["a"]))
        if not self.check(
            "G1.7 net-%d's runtime stamp is removed (the daemon is stale: no_stamp)"
            % self.nid["a"],
            stale.rc == 0,
            stale,
            "rc=%d MainPID=%s" % (stale.rc, pid_before),
        ):
            return
        res = self.ctx.rdc(
            "machine",
            "converge",
            self.ctx.machine,
            "--policy",
            "always",
            "--continue-on-error",
            "--json",
            timeout=1800,
            refuse=False,
        )
        report = converge_preflight.parse_converge_report(res.out)
        entry = converge_preflight.result_for(report, self.guid.get("a", ""), self.ref_a)
        log_path = self.ctx.keep_log(STEP_ID, "converge", ["rdc", "machine", "converge"], res)
        if not self.ctx.check(
            STEP_ID,
            "G1.7 rdc machine converge --policy always restarts the stale %s (converged)"
            % self.ref_a,
            converge_preflight.is_converged(entry),
            res,
            "rc=%d entry=%s counts=%s"
            % (res.rc, _clip(json.dumps(entry)), converge_preflight.summary_counts(report)),
            log_path=log_path,
        ):
            return
        restarted, why = restarted_verdict(pid_before, self._main_pid("a"))
        if not self.check(
            "G1.7 net-%d's daemon actually restarted" % self.nid["a"], restarted, res, why
        ):
            return
        self._grant_still_listed("G1.7", "after converge")
        self.g1_3_nodes("G1.7", " after converge")

    # -- teardown --------------------------------------------------------------

    def _remove_detached(self) -> list[str]:
        if not self.detached:
            return []
        res = self.quiet_shell(self.ref_a, remove_containers_script(self.ctr_dev, self.ctr_base))
        if res.rc != 0:
            return [
                "G1 containers %s, %s in %s (rm rc=%d)"
                % (
                    self.ctr_dev,
                    self.ctr_base,
                    self.ref_a,
                    res.rc,
                )
            ]
        self.detached = False
        return []

    def _cleanup(self) -> None:
        left = self._remove_detached()
        for key, ref in (("a", self.ref_a), ("b", self.ref_b)):
            if key not in self.granted or not self.nid.get(key):
                continue
            self.gpu("revoke", ref)
            _show, devices = self.grant_devices(key)
            if devices is None or CDI_NAME in devices:
                self.root(revoke_script(self.nid[key]))
                _show, devices = self.grant_devices(key)
            if devices is None or CDI_NAME in devices:
                left.append("G1 grant of %s on %s (net-%d)" % (CDI_NAME, ref, self.nid[key]))
        if self.fake_written:
            res = self.root(teardown_script())
            if res.rc != 0:
                left.append(
                    "G1 fake device %s / spec %s still on the worker (rc=%d)"
                    % (NODE_PATH, SPEC_PATH, res.rc)
                )
        self.ctx.sweep_leftovers.extend(self.ctx.scrub(x) for x in left)


__all__ = [
    "CDI_NAME",
    "STEP",
    "STEP_ID",
    "added_nodes_verdict",
    "cgroup_rules_verdict",
    "cgroup_script",
    "dev_entries",
    "docker_rc",
    "docker_run",
    "exclusive_refusal_verdict",
    "fork_tags",
    "grant_show_script",
    "main_pid_script",
    "make_stale_script",
    "not_granted_verdict",
    "open_command",
    "open_verdict",
    "parse_grant_devices",
    "parse_main_pid",
    "probe_command",
    "remove_containers_script",
    "restarted_verdict",
    "revoke_script",
    "run",
    "setup_script",
    "setup_verdict",
    "spec_text",
    "split_cgroup_sections",
    "stamp_path",
    "teardown_script",
    "v1_rules",
    "v2_compare_immediates",
]
