"""I1 of agent/plans/PLAN-sandbox-tenant-separation.md: one repository's shell reaches only its own repository's Docker API, network policy, mount and cgroups.

`vm_check.py` registers this module once, through `EXTRA_RENET_STEPS`, as the `I1` step of the renet phase; `--only I1` drags in V1.2 (and with it P5 and V1.1), so the run's forks A and B exist when `run(ctx)` is called. `ctx` is the running `VmCheck`: every VM action goes through its `./rdc.sh` helpers (`rdc`, `shell`), its raw ssh probe recipe (`vm_ssh.ssh_argv` through `host_run`, the U1 pattern) and its ledger (`check`, `record`). Every row records under the step id `I1`, its plan row named in the description, and asserts the FIXED behaviour; a defect is a FAIL row, never papered over.

THE ROWS. I1.1 the sandbox's group list; I1.2 the own Docker socket answers and the neighbour's refuses; I1.3 the gate's peer-cgroup check (403 from A's exec cgroup, 200 from outside every repo cgroup); I1.4 the gate seeds a never-seen compose service and the repository default; I1.5 a plain `docker run` in B cannot connect to a listener on an A address (EPERM) while A itself can; I1.6 the mount view and the session PID namespace; I1.8 a session's nohup background job outlives the session in that session's own PID namespace and private view, invisible to B and to a fresh A session, and the namespace ends with its last job, while VS Code's connection keeps its server and its exec channel returns within ALIAS_CHANNEL_MAX_MS rather than when its job ends; I1.7 deleting a fork removes its cgroups, map entries and socket group.

THE ROOT GO TESTS (rows `I1.R`). RB's and RC's acceptance lines (`TestPrivateRepoViewLinux`, the `ebpf_e2e` tests) need root on a real kernel. A pre-bash guard refuses hand-copying binaries to a VM with scp/ssh, so they travel the way vm_check already moves files: `go test -c` builds the test binaries on the host (the way U1 builds its pre-isolation renet), `rdc repo sync upload` puts them into the throwaway fork C's mount, and the run's ssh probe executes them under sudo from a private staging directory it removes again. Fork C's deletion (I1.7) takes the uploaded copies with it. A test that SKIPs (no root, missing kernel prerequisite) is a FAIL row: only `--- PASS` counts.

TEARDOWN. Fork C joins `ctx.forks`, so the run's own teardown deletes it and purges its licence state even when I1 crashes before I1.7. The listener container, B's compose service and the background `sleep` processes are removed here; anything that stays rides `ctx.sweep_leftovers`, so the run cannot reach VERIFIED over it.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shlex
import shutil
from typing import TYPE_CHECKING, Any

from rediacc_ci.drills import vm_ssh
from rediacc_ci.drills.upgrade_converge import new_docker_socket
from rediacc_ci.well_known import DATASTORE_PATH

if TYPE_CHECKING:
    from collections.abc import Sequence

STEP_ID = "I1"

CGROUP_ROOT = "/sys/fs/cgroup"
REDIACC_SLICE = "rediacc.slice"
MOUNTS = DATASTORE_PATH + "/mounts"
COMPOSE_FILE = "docker-compose.yml"
# The one image every container row runs: busybox carries `sleep` and an `nc` with `-l -k -s -p -w`. Each repository has its own Docker daemon, so each pulls it once.
IMAGE = "busybox:1.36"
# The listener's offset in A's /26: inside the service range (2-62, pkg/config/constants.go) and above where a small compose file's sequential allocation lands.
LISTEN_OFFSET = 60
LISTEN_PORT = 47123
# A repository Docker API gate's refusal of a peer in another repository's cgroup, and its answer to a caller outside every repository cgroup.
GATE_REFUSED = 403
GATE_SERVED = 200
EPERM_TEXT = "operation not permitted"
DENIED_TEXT = "permission denied"
GUID_RE = re.compile(
    r"/mounts/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:/|$)"
)
VSCODE_ABSENT = "VS Code not found"
URI_PREFIX = "vscode-remote://ssh-remote+"

# RB's and RC's root acceptance tests: (row label, test binary name, go package, build tags, test names).
ROOT_TESTS: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    (
        "RB",
        "renet-cmd.test",
        "./cmd/renet",
        "",
        ("TestPrivateRepoViewLinux", "TestPrivateRepoViewBackgroundJobOutlivesTheTarget"),
    ),
    (
        "RC",
        "renet-ebpf.test",
        "./pkg/ebpf",
        "ebpf_e2e",
        (
            "TestEBPF_DeepestEntryWins",
            "TestEBPF_RepoDefaultBlocksCrossRepo",
            "TestEBPF_Bind4LoopbackRewrite",
            "TestEBPF_ExecEntryStaysWhileACgroupHoldsProcesses",
        ),
    ),
)
ROOT_TEST_DIR = "vmc-i1-tests"
ROOT_TEST_TIMEOUT_S = 900
# How the test binaries are built: static, for the ops VMs' architecture, the way build.sh builds renet itself.
GO_TEST_ENV = {"CGO_ENABLED": "0", "GOOS": "linux", "GOARCH": "amd64"}
# VS Code Remote-SSH's exec channel must return once its background job is started, not when the job ends.
ALIAS_CHANNEL_MAX_MS = 30000


# --------------------------------------------------------------------------- pure helpers


def ip_at_offset(network_id: int | str, offset: int) -> str:
    """The loopback address at `offset` in network N's /26: `127.<(N + offset) as three octets>` (config.GetIPAtOffset; the dockerproxy gate's labelOffset is its inverse)."""
    value = int(network_id) + offset
    return "127.%d.%d.%d" % ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)


def subnet_base(network_id: int | str) -> str:
    """The /26 base address the eBPF map records as `subnet_base` (subnetBaseNative)."""
    return ip_at_offset(network_id, 0)


def net_group(network_id: int | str) -> str:
    """The per-network socket group of decision 1, `rediacc-net-<N>`."""
    return "rediacc-net-%s" % network_id


def exec_cgroup(network_id: int | str) -> str:
    """The sandbox shells' cgroup directory, `/sys/fs/cgroup/rediacc.slice/renet-exec-<N>` (ebpf.ExecCgroupPath)."""
    return "%s/%s/renet-exec-%s" % (CGROUP_ROOT, REDIACC_SLICE, network_id)


def repo_cgroup_rel(network_id: int | str, service: str = "") -> str:
    """A repository's cgroup relative to /sys/fs/cgroup, `rediacc.slice/rediacc-<N>[/<service>]` (dockerpolicy.CgroupSlice)."""
    base = "%s/rediacc-%s" % (REDIACC_SLICE, network_id)
    return "%s/%s" % (base, service) if service else base


def service_name(run_id: str, suffix: str = "") -> str:
    """A compose service no earlier run used, `vmc-i1<suffix>-<stamp>-<nonce>`: the gate's service-dir pattern allows 63 bytes of `[A-Za-z0-9_.-]`."""
    tail = run_id.removeprefix("vmc-")
    return "vmc-i1%s-%s" % (suffix, tail)


def fork_c_tag(tags: Sequence[str]) -> str:
    """The throwaway third fork's tag: fork A's tag with its `-a` turned into `-c`, so the stale-fork sweep's pattern still recognises it."""
    a = tags[0]
    return (a.removesuffix("-a")) + "-c"


def sleep_seconds(run_id: str, salt: int) -> int:
    """A `sleep` argument unique to this run and row, so `pgrep -f '^sleep <n>$'` finds only the row's own process."""
    digest = int(hashlib.sha256(("%s/%d" % (run_id, salt)).encode()).hexdigest()[:8], 16)
    return 600000 + digest % 300000


def compose_body(service: str, image: str = IMAGE) -> str:
    """A one-service compose file whose container only sleeps; renet compose adds the host network, the service address label and the cgroup parent."""
    return 'services:\n  %s:\n    image: %s\n    command: ["sleep", "86400"]\n' % (service, image)


def groups_verdict(id_gn: str, own: int | str, other: int | str) -> tuple[bool, str]:
    """I1.1: `id -Gn` holds the own network group and neither `docker` nor the neighbour's group."""
    groups = id_gn.split()
    missing = net_group(own) not in groups
    leaked = [g for g in ("docker", net_group(other)) if g in groups]
    if missing or leaked:
        why = []
        if missing:
            why.append("no %s" % net_group(own))
        if leaked:
            why.append("holds %s" % ", ".join(leaked))
        return False, "%s (groups: %s)" % ("; ".join(why), " ".join(groups) or "<none>")
    return True, "groups: %s" % " ".join(groups)


def denied(text: str) -> bool:
    """A refused socket connect as the docker CLI words it."""
    return DENIED_TEXT in text.lower()


def eperm(text: str) -> bool:
    """A connect the eBPF program refused (EPERM), as nc or bash word it."""
    return EPERM_TEXT in text.lower()


def nc_rc(text: str) -> int | None:
    """The status the `NC_RC=` marker printed after the cross-repo `docker run`, or None when the marker never printed."""
    found = re.findall(r"^NC_RC=(\d+)\s*$", text, re.MULTILINE)
    return int(found[-1]) if found else None


def nc_evidence(text: str) -> str:
    """The `nc:`, `docker:` and `NC_RC=` lines of a cross-repo connect, which the 200-byte evidence otherwise spends on the CLI's progress lines (I1.5, 2026-10-24). `NC_RC` is the `docker run` status, so a docker failure shows as its own `docker:` line beside it."""
    keep = [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip().startswith(("nc:", "docker:", "NC_RC="))
    ]
    return " | ".join(keep)


def cross_connect_verdict(out: str, listener_log: str | None, marker: str) -> tuple[bool, str]:
    """(refused, evidence) of I1.5: the `docker run` in B exited non-zero with nc's EPERM line, and A's listener log (None when it could not be read) never saw B's marker. A marker in the log is a connect that got through, whatever nc printed."""
    rc = nc_rc(out)
    # With none of the kept lines present the raw output is the evidence: a `docker run` that failed in some other voice must still show what it said.
    ev = nc_evidence(out) or "no nc:, docker: or NC_RC= line; output: %s" % (
        " ".join(out.split())[:200] or "<empty>"
    )
    if listener_log is None:
        return False, "A's listener log could not be read; %s" % ev
    if marker in listener_log:
        return False, "A's listener RECEIVED %s from B; %s" % (marker, ev)
    if rc is None:
        return False, "the NC_RC marker never printed; %s" % ev
    if rc == 0 or not eperm(out):
        return False, "B's connect was not refused with EPERM; %s" % ev
    return True, ev


def http_status(text: str) -> int | None:
    """The status curl's `-w '%{http_code}'` printed: the last line that is exactly three digits."""
    for raw in reversed(text.strip().splitlines()):
        line = raw.strip()
        if re.fullmatch(r"\d{3}", line):
            return int(line)
    return None


def parse_inspection(text: str) -> dict[str, Any] | None:
    """The `renet ebpf inspect --json` object in `text` (indented over several lines), or None."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        doc = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return doc if isinstance(doc, dict) and "entries" in doc else None


def inspection_count(doc: dict[str, Any] | None) -> int | None:
    """An inspection's `count` (entries plus orphans), or None when it carries none."""
    if not doc:
        return None
    count = doc.get("count")
    return count if isinstance(count, int) else None


def find_entry(doc: dict[str, Any] | None, cgroup_rel: str) -> dict[str, Any] | None:
    """The entry keyed by the cgroup `cgroup_rel` (relative to /sys/fs/cgroup; a leading slash is ignored on both sides)."""
    want = cgroup_rel.strip("/")
    for entry in (doc or {}).get("entries") or []:
        if isinstance(entry, dict) and str(entry.get("cgroup", "")).strip("/") == want:
            return entry
    return None


def service_entry_verdict(
    doc: dict[str, Any] | None, network_id: int | str, service: str, label_ip: str
) -> tuple[bool, str]:
    """I1.4: the inspection holds the repository default at `rediacc-<N>` and the service dir's entry, in N's /26 and on the label's address."""
    if doc is None:
        return False, "no inspection JSON"
    base = subnet_base(network_id)
    default = find_entry(doc, repo_cgroup_rel(network_id))
    entry = find_entry(doc, repo_cgroup_rel(network_id, service))
    why = []
    if default is None:
        why.append("no default entry at %s" % repo_cgroup_rel(network_id))
    elif default.get("subnet_base") != base:
        why.append("default subnet %s, not %s" % (default.get("subnet_base"), base))
    if entry is None:
        why.append("no entry at %s" % repo_cgroup_rel(network_id, service))
    else:
        if entry.get("subnet_base") != base:
            why.append("service subnet %s, not %s" % (entry.get("subnet_base"), base))
        if not label_ip or entry.get("service_ip") != label_ip:
            why.append(
                "service_ip %s, label %s" % (entry.get("service_ip") or "-", label_ip or "-")
            )
    if why:
        return False, "; ".join(why) + " (%s entries)" % len(doc.get("entries") or [])
    return True, "default and %s in %s, service_ip %s" % (service, base, label_ip)


def mount_guids(mountinfo: str) -> list[str]:
    """The repository guids that have a mount point under `/mounts/` in a `/proc/self/mountinfo` text (field 5 is the mount point), in order, each once."""
    found: list[str] = []
    for line in mountinfo.splitlines():
        fields = line.split()
        if len(fields) < 5:
            continue
        match = GUID_RE.search(fields[4])
        if match and match.group(1) not in found:
            found.append(match.group(1))
    return found


def split_sections(text: str, marker: str = "===") -> list[str]:
    """`text` cut at each line that is exactly `marker`."""
    sections: list[str] = [""]
    for line in text.splitlines():
        if line.strip() == marker:
            sections.append("")
        else:
            sections[-1] += line + "\n"
    return sections


def go_test_verdict(output: str, names: Sequence[str]) -> tuple[bool, str]:
    """A `-test.v` run passes only when every named test printed `--- PASS`; a SKIP (no root, a missing kernel prerequisite), a FAIL or a test that never ran fails the row with its reason."""
    why = []
    for name in names:
        if re.search(r"^\s*--- PASS: %s\b" % re.escape(name), output, re.MULTILINE):
            continue
        skip = re.search(r"^\s*--- SKIP: %s\b.*$" % re.escape(name), output, re.MULTILINE)
        fail = re.search(r"^\s*--- FAIL: %s\b" % re.escape(name), output, re.MULTILINE)
        if skip:
            # The skip reason is the indented line after the SKIP line.
            tail = output[skip.end() :].lstrip("\n").splitlines()
            why.append("%s skipped: %s" % (name, tail[0].strip() if tail else "?"))
        elif fail:
            why.append("%s failed" % name)
        else:
            why.append("%s did not run" % name)
    return (not why), "; ".join(why) or "all passed: %s" % ", ".join(names)


def build_tests_script(renet_dir: str, out_dir: str) -> str:
    """The host shell that builds every ROOT_TESTS binary with `go test -c` into `out_dir`, without touching renet's own bin/."""
    lines = ["set -eu", "cd %s" % shlex.quote(renet_dir)]
    lines.extend(
        "go test -c -tags %s -o %s %s"
        % (shlex.quote(tags), shlex.quote("%s/%s" % (out_dir, binary)), package)
        for _label, binary, package, tags, _names in ROOT_TESTS
    )
    return "\n".join(lines) + "\n"


def root_test_script(src: str, binary: str, names: Sequence[str], timeout_s: int) -> str:
    """The worker-side shell, run under sudo, that stages `src` (the uploaded test binary) into a fresh 0700 directory under /var/tmp, runs the named tests verbosely from there and removes the directory on exit. A missing upload exits 2 before anything runs."""
    regex = "^(%s)$" % "|".join(re.escape(n) for n in names)
    return (
        "set -u\n"
        "test -f %(src)s || { echo 'NO-UPLOAD %(src)s'; exit 2; }\n"
        "stage=$(mktemp -d /var/tmp/vmc-i1-XXXXXX) || exit 2\n"
        "trap 'rm -rf \"$stage\"' EXIT\n"
        'install -m 0755 %(src)s "$stage/%(bin)s" || exit 2\n'
        'cd "$stage" && ./%(bin)s -test.run %(regex)s -test.count=1 -test.v -test.timeout=%(t)ds\n'
        % {
            "src": shlex.quote(src),
            "bin": binary,
            "regex": shlex.quote(regex),
            "t": timeout_s,
        }
    )


def ns_gone_script(seconds: int, pidns: str, tries: int = 5) -> str:
    """Root on the worker: kills the `sleep <seconds>` job, then prints NSGONE once no `/proc/*/ns/pid` points at `pidns` (the job's namespace, whose lingering init exits with its last process), NSLINGERS (exit 1) when one still does after `tries` seconds."""
    pat = shlex.quote("^sleep %d$" % seconds)
    ns = shlex.quote(pidns)
    return (
        "pkill -f %(pat)s; "
        "for i in $(seq %(tries)d); do found=; "
        'for f in /proc/[0-9]*/ns/pid; do [ "$(readlink "$f" 2>/dev/null)" = %(ns)s ] && { found=$f; break; }; done; '
        '[ -z "$found" ] && { echo NSGONE; exit 0; }; sleep 1; done; '
        'echo "NSLINGERS $found"; exit 1' % {"pat": pat, "ns": ns, "tries": tries}
    )


def job_view_script(seconds: int) -> str:
    """Root on the worker: the `sleep <seconds>` job's PID namespace, the worker's own, and the job's mountinfo, cut by `===` lines. NOJOB (exit 3) when no such job runs."""
    pat = shlex.quote("^sleep %d$" % seconds)
    return (
        'p=$(pgrep -f %s | head -n1); test -n "$p" || { echo NOJOB; exit 3; }; '
        'readlink "/proc/$p/ns/pid"; echo ===; readlink /proc/self/ns/pid; echo ===; '
        'cat "/proc/$p/mountinfo"' % pat
    )


def job_view_verdict(text: str, guid_b: str) -> tuple[bool, str, str]:
    """(ok, evidence, the job's namespace) of job_view_script's output: the job runs in a PID namespace other than the worker's, and its mountinfo has no mount point under B's guid."""
    sections = split_sections(text)
    job_ns = sections[0].strip() if sections else ""
    host_ns = sections[1].strip() if len(sections) > 1 else ""
    guids = mount_guids(sections[2] if len(sections) > 2 else "")
    why = []
    if not job_ns.startswith("pid:[") or not host_ns.startswith("pid:["):
        why.append("no namespaces read (job %r, worker %r)" % (job_ns, host_ns))
    elif job_ns == host_ns:
        why.append("the job runs in the worker's PID namespace %s" % host_ns)
    if guid_b in guids:
        why.append("B's guid %s is mounted in the job's view" % guid_b)
    ev = "job %s, worker %s, guids %s" % (job_ns or "-", host_ns or "-", guids)
    if why:
        # A namespace of the job's own is returned even when only the view failed, so the drain row still runs (review 55ab6cf1.2); it counts as the job's own only when the worker's namespace was read too and differs (661409e8.2).
        ns_shape = r"pid:\[\d+\]"
        read_both = re.fullmatch(ns_shape, job_ns) and re.fullmatch(ns_shape, host_ns)
        own = job_ns if read_both and job_ns != host_ns else ""
        return False, "; ".join(why) + " (%s)" % ev, own
    return True, ev, job_ns


def absent_script(seconds: int) -> str:
    """A sandbox shell's probe for the `sleep <seconds>` job, with a positive control: the shell starts its own `sleep <seconds+1>` and must see that one within 2 s (CONTROL_SEEN; the retry covers the fork before the child execs sleep, review 661409e8.1), so a pgrep that cannot look at processes at all never reads as the job being absent; PGREP_RC is the status of the search for the job (1 = not found)."""
    control = shlex.quote("^sleep %d$" % (seconds + 1))
    return (
        "sleep %d & c=$!; s=CONTROL_MISSING; for i in 1 2 3 4 5 6 7 8 9 10; do "
        "pgrep -f %s >/dev/null && { s=CONTROL_SEEN; break; }; sleep 0.2; done; echo $s; "
        "pgrep -f %s >/dev/null; r=$?; kill $c 2>/dev/null; echo PGREP_RC=$r"
        % (seconds + 1, control, shlex.quote("^sleep %d$" % seconds))
    )


def absent_verdict(text: str) -> tuple[bool, str]:
    """(job absent, evidence) from `absent_script`'s output: the control was seen and the job search found nothing (status 1)."""
    seen = "CONTROL_SEEN" in text
    rc = re.findall(r"^PGREP_RC=(\d+)\s*$", text, re.MULTILINE)
    status = rc[-1] if rc else None
    if not seen:
        return (
            False,
            "the positive control (the shell's own sleep) was not seen, so pgrep did not look",
        )
    if status != "1":
        return False, "the job search returned %s, not 1 (found, or pgrep failed)" % (
            status or "nothing"
        )
    return True, "control seen, job search status 1"


def alive_script(seconds: int) -> str:
    """Root on the worker: prints ALIVE when a `sleep <seconds>` process exists, GONE (exit 1) otherwise."""
    return "sleep 2; pgrep -f %s >/dev/null && echo ALIVE || { echo GONE; exit 1; }" % shlex.quote(
        "^sleep %d$" % seconds
    )


def peer_curl_script(cgroup_dir: str, socket: str) -> str:
    """Root on the worker: move this shell into `cgroup_dir` and ask the gate at `socket` for `/_ping`; prints the HTTP status. NOCG (exit 3) when the cgroup does not exist."""
    cg = shlex.quote(cgroup_dir)
    return (
        "test -d %(cg)s || { echo NOCG; exit 3; }; "
        'echo $$ > %(cg)s/cgroup.procs && exec curl -sS -o /dev/null -w "%%{http_code}\\n" '
        "--unix-socket %(sock)s http://localhost/_ping" % {"cg": cg, "sock": shlex.quote(socket)}
    )


def tcp_connect_script(ip: str, port: int, tries: int = 5) -> str:
    """A sandbox shell's connect to ip:port with bash's /dev/tcp, retried while a listener starts; CONNECTED on success."""
    probe = shlex.quote("exec 3<>/dev/tcp/%s/%d" % (ip, port))
    return (
        "for i in $(seq %d); do timeout 3 bash -c %s && { echo CONNECTED; exit 0; }; sleep 1; done; exit 1"
        % (tries, probe)
    )


# --------------------------------------------------------------------------- live


def run(ctx: Any) -> None:
    """The live I1 step: records I1 rows on `ctx` and removes what it created (fork C through `ctx.forks`)."""
    _LiveI1(ctx).execute()


STEP = (STEP_ID, ("V1.2",), run)


class _LiveI1:
    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self.tag_a, self.tag_b = ctx.tags
        self.tag_c = fork_c_tag(ctx.tags)
        self.ref_a, self.ref_b, self.ref_c = (
            ctx.ref(t) for t in (ctx.tags[0], ctx.tags[1], self.tag_c)
        )
        self.nid: dict[str, int] = {}
        self.guid: dict[str, str] = {}
        self.tmp = pathlib.Path(ctx.work) / ("i1-%s" % ctx.run_id)
        self.tests_dir = self.tmp / "tests"
        self.svc_b = service_name(ctx.run_id)
        self.svc_c = service_name(ctx.run_id, "c")
        self.listener = "vmc-i1-listen-%s" % ctx.run_id[-6:]
        self.sleep_term = sleep_seconds(ctx.run_id, 1)
        self.sleep_vscode = sleep_seconds(ctx.run_id, 2)
        self.listener_up = False
        # Set before either background `sleep` is launched, so the cleanup knows a process may be left to kill.
        self.sleeps_started = False
        self.b_compose_up = False
        self.built = False

    # -- helpers ---------------------------------------------------------------

    def check(self, desc: str, ok: bool, res: Any = None, evidence: str = "") -> bool:
        return self.ctx.check(STEP_ID, desc, ok, res, evidence)

    def skip(self, desc: str, evidence: str = "") -> None:
        self.ctx.record(STEP_ID, desc, None, evidence=evidence)

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
        """A cleanup shell: an agent refusal here must not stop the teardown."""
        return self.ctx.rdc("term", "connect", ref, "-c", command, refuse=False)

    def mount(self, key: str) -> str:
        return "%s/%s" % (MOUNTS, self.guid.get(key, "<unknown>"))

    def ev(self, res: Any) -> str:
        return self.ctx.remote_evidence(res)

    def inspect(self, network_id: int) -> tuple[Any, dict[str, Any] | None]:
        res = self.root("renet ebpf inspect --network-id %d --json" % network_id)
        return res, parse_inspection(res.out) if res.rc == 0 else None

    def upload(self, ref: str, name: str, files: dict[str, bytes | str]) -> Any:
        """`files` (relative path -> content) synced into `ref`'s mount root by `rdc repo sync upload`, additively (no mirror)."""
        up = self.tmp / ("up-" + name)
        for rel, content in files.items():
            path = up / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                path.write_bytes(content)
            else:
                path.write_text(content)
        return self.ctx.rdc("repo", "sync", "upload", ref, "--local", str(up) + "/", timeout=900)

    # -- the run ---------------------------------------------------------------

    def execute(self) -> None:
        try:
            if not self._preconditions():
                return
            self._build_root_tests()
            self.i1_1_groups()
            self.i1_2_sockets()
            self.i1_3_peer_check()
            self.i1_4_gate_seeding()
            self.i1_5_cross_repo_connect()
            self.i1_6_mount_view()
            self.i1_8_session_lifetime()
            if self._fork_c():
                self._root_tests()
                self.i1_7_delete()
        finally:
            self._cleanup()

    def _preconditions(self) -> bool:
        for key, tag in (("a", self.tag_a), ("b", self.tag_b)):
            nid = self.ctx.network_ids.get(tag)
            if str(nid or "").isdigit():
                self.nid[key] = int(nid)
            self.guid[key] = self.ctx.guids.get(tag, "")
        ok = all(self.nid.get(k) and self.guid.get(k) for k in ("a", "b"))
        return self.check(
            "forks A and B have a network id and guid (from V1.1)",
            ok,
            evidence="network ids %s guids %s" % (self.nid, self.guid),
        )

    def _build_root_tests(self) -> None:
        self.tests_dir.mkdir(parents=True, exist_ok=True)
        renet_dir = str(pathlib.Path(self.ctx.root) / "private" / "renet")
        env = {**self.ctx.environ, **GO_TEST_ENV}
        res = self.ctx.host_run(
            ["bash", "-c", build_tests_script(renet_dir, str(self.tests_dir))],
            env=env,
            timeout=1800,
        )
        self.built = self.check(
            "I1.R build the root test binaries (go test -c: %s)"
            % ", ".join(binary for _l, binary, _p, _t, _n in ROOT_TESTS),
            res.rc == 0,
            res,
        )

    def i1_1_groups(self) -> None:
        res = self.ctx.shell(self.ref_a, "id -Gn")
        ok, why = groups_verdict(res.out, self.nid["a"], self.nid["b"])
        self.check(
            "I1.1 A's sandbox holds %s, neither docker nor %s"
            % (net_group(self.nid["a"]), net_group(self.nid["b"])),
            res.rc == 0 and ok,
            res,
            why if res.rc == 0 else self.ev(res),
        )

    def i1_2_sockets(self) -> None:
        own = self.ctx.shell(
            self.ref_a, "docker -H unix://%s version" % new_docker_socket(self.nid["a"])
        )
        self.check(
            "I1.2 A: docker version on its own socket",
            own.rc == 0,
            own,
            "" if own.rc == 0 else self.ev(own),
        )
        other = self.ctx.shell(
            self.ref_a, "docker -H unix://%s version" % new_docker_socket(self.nid["b"])
        )
        self.check(
            "I1.2 A: docker version on B's socket fails permission denied",
            other.rc != 0 and denied(other.text()),
            other,
            self.ev(other),
        )

    def i1_3_peer_check(self) -> None:
        # The exec cgroup exists once A has had a sandbox session (I1.1 opened one).
        sock_b = new_docker_socket(self.nid["b"])
        res = self.root(peer_curl_script(exec_cgroup(self.nid["a"]), sock_b))
        status = http_status(res.out)
        self.check(
            "I1.3 root in renet-exec-%d: B's gate answers /_ping %d"
            % (self.nid["a"], GATE_REFUSED),
            status == GATE_REFUSED,
            res,
            "status %s; %s" % (status, self.ev(res)),
        )
        control = self.root(
            'curl -sS -o /dev/null -w "%%{http_code}\\n" --unix-socket %s http://localhost/_ping'
            % shlex.quote(sock_b)
        )
        status = http_status(control.out)
        self.check(
            "I1.3 root outside every repo cgroup: B's gate answers /_ping %d" % GATE_SERVED,
            status == GATE_SERVED,
            control,
            "status %s; %s" % (status, self.ev(control)),
        )

    def i1_4_gate_seeding(self) -> None:
        nid = self.nid["b"]
        up = self.upload(self.ref_b, "b", {COMPOSE_FILE: compose_body(self.svc_b)})
        if not self.check(
            "I1.4 B: compose file with service %s uploaded" % self.svc_b, up.rc == 0, up
        ):
            return
        res = self.ctx.shell(
            self.ref_b, "cd %s && renet compose -- up -d" % shlex.quote(self.mount("b"))
        )
        self.b_compose_up = res.rc == 0
        if not self.check(
            "I1.4 B: renet compose -- up -d brings up %s" % self.svc_b,
            res.rc == 0,
            res,
            "" if res.rc == 0 else self.ev(res),
        ):
            return
        label = self.ctx.shell(
            self.ref_b,
            "docker ps --filter label=com.docker.compose.service=%s --format '{{.Label \"rediacc.service_ip\"}}'"
            % self.svc_b,
        )
        label_ip = (label.out.strip().splitlines() or [""])[0].strip()
        insp, doc = self.inspect(nid)
        ok, why = service_entry_verdict(doc, nid, self.svc_b, label_ip)
        self.check(
            "I1.4 ebpf inspect: entries for %s and %s"
            % (repo_cgroup_rel(nid, self.svc_b), repo_cgroup_rel(nid)),
            insp.rc == 0 and ok,
            insp,
            why if insp.rc == 0 else self.ev(insp),
        )

    def i1_5_cross_repo_connect(self) -> None:
        ip = ip_at_offset(self.nid["a"], LISTEN_OFFSET)
        start = self.ctx.shell(
            self.ref_a,
            "docker run -d --name %s --network host %s nc -lk -s %s -p %d"
            % (self.listener, IMAGE, ip, LISTEN_PORT),
        )
        self.listener_up = start.rc == 0
        if not self.check(
            "I1.5 A: a listener container on %s:%d" % (ip, LISTEN_PORT),
            start.rc == 0,
            start,
            "" if start.rc == 0 else self.ev(start),
        ):
            return
        own = self.ctx.shell(self.ref_a, tcp_connect_script(ip, LISTEN_PORT))
        if not self.check(
            "I1.5 A's sandbox connects to its own listener (the control)",
            own.rc == 0 and "CONNECTED" in own.out,
            own,
            "" if own.rc == 0 else self.ev(own),
        ):
            return
        # busybox 1.36 nc exits 1 silently on a failed connect; -vv makes it name the errno (`nc: <ip> (<ip>:<port>): Operation not permitted`).
        marker = "VMC-I1-FROM-B-%s" % self.ctx.run_id[-6:]
        cross = self.ctx.shell(
            self.ref_b,
            "echo %s | docker run --rm -i --network host %s nc -vv -w 3 %s %d 2>&1; echo NC_RC=$?"
            % (marker, IMAGE, ip, LISTEN_PORT),
        )
        logs = self.ctx.shell(self.ref_a, "docker logs %s 2>&1" % self.listener)
        ok, why = cross_connect_verdict(cross.out, logs.out if logs.rc == 0 else None, marker)
        self.check(
            "I1.5 a plain docker run in B cannot connect to A's %s:%d (EPERM)" % (ip, LISTEN_PORT),
            ok,
            cross,
            why,
        )

    def i1_6_mount_view(self) -> None:
        res = self.ctx.shell(
            self.ref_a, "readlink /proc/self/ns/pid; echo ===; cat /proc/self/mountinfo"
        )
        sections = split_sections(res.out)
        pidns = sections[0].strip() if sections else ""
        guids = mount_guids(sections[1] if len(sections) > 1 else "")
        self.check(
            "I1.6 A's mountinfo names only A's guid under /mounts/",
            res.rc == 0 and guids == [self.guid["a"]],
            res,
            "guids %s (A %s, B %s)" % (guids, self.guid["a"], self.guid["b"]),
        )
        self.check(
            "I1.6 %s/%s is not a mount point in A's sandbox" % (MOUNTS, self.guid["b"]),
            res.rc == 0 and self.guid["b"] not in guids,
            res,
            "guids %s" % guids,
        )
        host = self.root("readlink /proc/self/ns/pid")
        host_ns = host.out.strip()
        self.check(
            "I1.6 A's session has its own PID namespace",
            res.rc == 0 and host.rc == 0 and bool(pidns) and bool(host_ns) and pidns != host_ns,
            host,
            "session %s, worker %s" % (pidns or "-", host_ns or "-"),
        )

    def i1_8_session_lifetime(self) -> None:
        secs = self.sleep_term
        self.sleeps_started = True
        started = self.ctx.shell(
            self.ref_a,
            "nohup sleep %d >/dev/null 2>&1 & sleep 1; pgrep -f %s >/dev/null && echo STARTED"
            % (secs, shlex.quote("^sleep %d$" % secs)),
        )
        if self.check(
            "I1.8 A: a nohup background job starts in the session",
            started.rc == 0 and "STARTED" in started.out,
            started,
            "" if started.rc == 0 else self.ev(started),
        ):
            alive = self.root(alive_script(secs))
            if self.check(
                "I1.8 a session's nohup background job outlives its session",
                alive.rc == 0 and "ALIVE" in alive.out,
                alive,
                alive.text(),
            ):
                self._lingering_job(secs)
        self._vscode_keeps_server()

    def _lingering_job(self, secs: int) -> None:
        """The job A's ended session left behind keeps that session's PID namespace and private view, is invisible to every other session, and its namespace ends with it."""
        view = self.root(job_view_script(secs))
        ok, why, job_ns = job_view_verdict(view.out if view.rc == 0 else "", self.guid["b"])
        self.check(
            "I1.8 the lingering job keeps its session's PID namespace and a view without B's mount",
            ok,
            view,
            why if view.rc == 0 else "%s; %s" % (why, view.text()),
        )
        b_sees = self.ctx.shell(self.ref_b, absent_script(secs))
        b_ok, b_why = absent_verdict(b_sees.out)
        self.check(
            "I1.8 B's session does not see A's lingering job",
            b_sees.rc == 0 and b_ok,
            b_sees,
            b_why if b_sees.rc == 0 else self.ev(b_sees),
        )
        a_sees = self.ctx.shell(self.ref_a, absent_script(secs))
        a_ok, a_why = absent_verdict(a_sees.out)
        self.check(
            "I1.8 a fresh A session does not see the job either (each session has its own PID namespace)",
            a_sees.rc == 0 and a_ok,
            a_sees,
            a_why if a_sees.rc == 0 else self.ev(a_sees),
        )
        if not job_ns:
            self.check(
                "I1.8 the job's PID namespace ends with the job",
                False,
                view,
                "the namespace was not read",
            )
            return
        gone = self.root(ns_gone_script(secs, job_ns))
        self.check(
            "I1.8 the job's PID namespace ends with the job",
            gone.rc == 0 and "NSGONE" in gone.out,
            gone,
            gone.text(),
        )

    def _vscode_connect(self, attempt: str) -> bool | None:
        """One `rdc vscode connect --url-only`: it prepares the per-repo VS Code server and the ssh alias, prints the URI and exits, so no session outlives the command. None when VS Code is absent here (a skip row)."""
        res = self.ctx.rdc("vscode", "connect", self.ref_a, "--url-only")
        if res.rc != 0 and VSCODE_ABSENT in res.text():
            self.skip("I1.8 rdc vscode not run: VS Code is not installed here", res.text())
            return None
        uri = next(
            (ln.strip() for ln in res.out.splitlines() if ln.strip().startswith(URI_PREFIX)), ""
        )
        return self.check(
            "I1.8 rdc vscode connect %s (%s) prints a remote URI" % (self.ref_a, attempt),
            res.rc == 0 and bool(uri),
            res,
            uri or self.ev(res),
        )

    def _vscode_keeps_server(self) -> None:
        if not self._vscode_connect("first"):
            return
        # A marker inside the server directory the first connect prepared: a second connect, after the first command has exited, must re-prepare A without wiping it.
        server_dir = "%s/.vscode-server" % self.mount("a")
        marker = "%s/.vmc-i1-%s" % (server_dir, self.ctx.run_id)
        placed = self.ctx.shell(
            self.ref_a,
            "test -d %s && touch %s" % (shlex.quote(server_dir), shlex.quote(marker)),
        )
        if not self.check(
            "I1.8 the first connect prepared %s" % server_dir,
            placed.rc == 0,
            placed,
            "" if placed.rc == 0 else self.ev(placed),
        ):
            return
        if not self._vscode_connect("second, after the first exited"):
            return
        kept = self.ctx.shell(self.ref_a, "test -f %s" % shlex.quote(marker))
        self.check(
            "I1.8 a second rdc vscode connect keeps the prepared VS Code server directory",
            kept.rc == 0,
            kept,
            "" if kept.rc == 0 else self.ev(kept),
        )
        config = pathlib.Path(self.ctx.work) / "ssh_config"
        connection = getattr(self.ctx, "connection", "")
        if not connection or not config.exists():
            self.skip(
                "I1.8 VS Code server lifetime not run: no ssh alias config (V1.6 and V1.7 did not run here)",
                "connection %r, config %s" % (connection, config),
            )
            return
        # VS Code Remote-SSH starts its server as a background job of an exec channel on the alias, then disconnects; the job must outlive that channel.
        secs = self.sleep_vscode
        self.sleeps_started = True
        launched = self.ctx.host_run(
            [
                "ssh",
                "-F",
                str(config),
                "-o",
                "BatchMode=yes",
                connection,
                "nohup sleep %d >/dev/null 2>&1 &" % secs,
            ],
            env=self.ctx.environ,
            timeout=120,
        )
        if not self.check(
            "I1.8 a background job launched over the VS Code alias %s" % connection,
            launched.rc == 0,
            launched,
            "" if launched.rc == 0 else self.ev(launched),
        ):
            return
        self.check(
            "I1.8 the alias exec channel returned in under %ds, not when its job ends"
            % (ALIAS_CHANNEL_MAX_MS // 1000),
            launched.ms < ALIAS_CHANNEL_MAX_MS,
            launched,
            "%d ms" % launched.ms,
        )
        alive = self.root(alive_script(secs))
        self.check(
            "I1.8 the job VS Code's connection started outlives its channel (the server's lifetime)",
            alive.rc == 0 and "ALIVE" in alive.out,
            alive,
            alive.text(),
        )

    def _fork_c(self) -> bool:
        fork = {"tag": self.tag_c, "guid": "", "created": True, "deleted": False}
        self.ctx.forks.append(fork)
        res = self.ctx.rdc(
            "repo", "fork", self.ctx.opts.parent, "--tag", self.tag_c, "--up", timeout=1800
        )
        if not self.check("I1.7 fork %s --up" % self.ref_c, res.rc == 0, res):
            return False
        listed, entries = self.ctx.repo_list()
        for entry in entries:
            if entry.get("name") == self.ref_c:
                self.guid["c"] = str(entry.get("guid", ""))
                nid = entry.get("networkId", entry.get("network_id"))
                if str(nid or "").isdigit():
                    self.nid["c"] = int(nid)
        fork["guid"] = self.guid.get("c", "")
        if not self.check(
            "I1.7 fork C listed with a guid and network id",
            bool(self.guid.get("c")) and bool(self.nid.get("c")),
            listed,
            "guid %s network id %s" % (self.guid.get("c"), self.nid.get("c")),
        ):
            return False
        files: dict[str, bytes | str] = {COMPOSE_FILE: compose_body(self.svc_c)}
        if self.built:
            for _label, binary, _p, _t, _n in ROOT_TESTS:
                files["%s/%s" % (ROOT_TEST_DIR, binary)] = (self.tests_dir / binary).read_bytes()
        up = self.upload(self.ref_c, "c", files)
        if not self.check(
            "I1.7 C: compose file%s uploaded" % (" and root test binaries" if self.built else ""),
            up.rc == 0,
            up,
        ):
            return False
        res = self.ctx.shell(
            self.ref_c, "cd %s && renet compose -- up -d" % shlex.quote(self.mount("c"))
        )
        if not self.check(
            "I1.7 C: renet compose -- up -d brings up %s" % self.svc_c,
            res.rc == 0,
            res,
            "" if res.rc == 0 else self.ev(res),
        ):
            return False
        insp, doc = self.inspect(self.nid["c"])
        count = inspection_count(doc)
        return self.check(
            "I1.7 before the delete C has eBPF entries (so the after-check is not vacuous)",
            insp.rc == 0 and bool(count),
            insp,
            "count %s" % count,
        )

    def _root_tests(self) -> None:
        if not self.built:
            self.skip("I1.R root tests not run: the test binaries did not build")
            return
        for label, binary, _package, _tags, names in ROOT_TESTS:
            src = "%s/%s/%s" % (self.mount("c"), ROOT_TEST_DIR, binary)
            res = self.root(
                root_test_script(src, binary, names, ROOT_TEST_TIMEOUT_S),
                timeout=ROOT_TEST_TIMEOUT_S + 120,
            )
            ok, why = go_test_verdict(res.out, names)
            log_path = self.ctx.keep_log(STEP_ID, "root-" + label, [binary, *names], res)
            self.ctx.check(
                STEP_ID,
                "I1.R %s root tests on the worker: %s" % (label, ", ".join(names)),
                res.rc == 0 and ok,
                res,
                why,
                log_path=log_path,
            )

    def i1_7_delete(self) -> None:
        nid = self.nid["c"]
        res = self.ctx.rdc("repo", "delete", self.ref_c, "-y", timeout=1800)
        if not self.check("I1.7 rdc repo delete %s" % self.ref_c, res.rc == 0, res):
            return
        self._forget_fork_c()
        cg = "%s/%s" % (CGROUP_ROOT, repo_cgroup_rel(nid))
        gone = self.root("test -d %s && echo PRESENT || echo ABSENT" % shlex.quote(cg))
        self.check(
            "I1.7 %s absent after the delete" % repo_cgroup_rel(nid),
            gone.rc == 0 and "ABSENT" in gone.out,
            gone,
            gone.text(),
        )
        insp, doc = self.inspect(nid)
        count = inspection_count(doc)
        self.check(
            "I1.7 ebpf inspect --network-id %d counts 0" % nid,
            insp.rc == 0 and count == 0,
            insp,
            "count %s" % count if insp.rc == 0 else self.ev(insp),
        )
        group = self.root("getent group %s; echo rc=$?" % net_group(nid))
        self.check(
            "I1.7 getent group %s rc 2 (no such group)" % net_group(nid),
            "rc=2" in group.out,
            group,
            group.text(),
        )

    def _forget_fork_c(self) -> None:
        """Fork C is gone: once the list confirms it, its `ctx.forks` entry is marked deleted and handed over, so the run's teardown, which deletes every fork it holds (vm_check `_teardown_steps`), never deletes it a second time. Its licence state is purged here instead, the purge that teardown gives every deleted fork, and a purge that fails rides `ctx.sweep_leftovers`. A C still listed stays in `ctx.forks` for teardown."""
        listed, entries = self.ctx.repo_list()
        still = any(e.get("name") == self.ref_c for e in entries)
        if not self.check(
            "I1.7 fork C no longer listed after the delete",
            listed.rc == 0 and not still,
            listed,
            "repo list rc=%d, listed %s" % (listed.rc, still),
        ):
            return
        for fork in list(self.ctx.forks):
            if fork.get("tag") == self.tag_c:
                fork["deleted"] = True
                self.ctx.forks.remove(fork)
        leftover = self.ctx.purge_licences([self.guid.get("c", "")], "I1 fork C")
        if leftover:
            self.ctx.sweep_leftovers.append(self.ctx.scrub(leftover))

    # -- teardown --------------------------------------------------------------

    def _cleanup(self) -> None:
        left: list[str] = []
        if self.listener_up:
            res = self.quiet_shell(self.ref_a, "docker rm -f %s" % self.listener)
            if res.rc != 0:
                left.append(
                    "I1 listener container %s in %s (rm rc=%d)"
                    % (self.listener, self.ref_a, res.rc)
                )
        if self.b_compose_up:
            res = self.quiet_shell(
                self.ref_b, "cd %s && renet compose -- down" % shlex.quote(self.mount("b"))
            )
            if res.rc != 0:
                left.append(
                    "I1 compose service %s in %s (down rc=%d)" % (self.svc_b, self.ref_b, res.rc)
                )
        if self.sleeps_started:
            pattern = "^sleep (%d|%d)$" % (self.sleep_term, self.sleep_vscode)
            res = self.root(
                "pkill -f %s; sleep 1; ! pgrep -f %s" % (shlex.quote(pattern), shlex.quote(pattern))
            )
            # An ssh failure proves nothing was killed, so it is a leftover like a surviving process.
            if res.rc == vm_ssh.SSH_FAILED:
                left.append(
                    "I1 background sleep processes (%s) not checked: the root ssh probe failed (rc=%d)"
                    % (pattern, res.rc)
                )
            elif res.rc != 0:
                left.append(
                    "I1 background sleep processes still running on the worker (%s)" % pattern
                )
        shutil.rmtree(self.tmp, ignore_errors=True)
        self.ctx.sweep_leftovers.extend(self.ctx.scrub(x) for x in left)


__all__ = [
    "IMAGE",
    "ROOT_TESTS",
    "STEP",
    "STEP_ID",
    "absent_script",
    "absent_verdict",
    "alive_script",
    "build_tests_script",
    "compose_body",
    "denied",
    "eperm",
    "exec_cgroup",
    "find_entry",
    "fork_c_tag",
    "go_test_verdict",
    "groups_verdict",
    "http_status",
    "inspection_count",
    "ip_at_offset",
    "job_view_script",
    "job_view_verdict",
    "mount_guids",
    "net_group",
    "ns_gone_script",
    "parse_inspection",
    "peer_curl_script",
    "repo_cgroup_rel",
    "root_test_script",
    "run",
    "service_entry_verdict",
    "service_name",
    "sleep_seconds",
    "split_sections",
    "subnet_base",
    "tcp_connect_script",
]
