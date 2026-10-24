"""The I2 session-teardown drill: its CLI-free helpers, its registration in vm_check through EXTRA_RENET_STEPS, and the live step's rows and teardown against a scripted context. The live rows run on the ops VMs through `npm run vm:check -- --only I2`."""

from __future__ import annotations

import io
import json
import os
import re
import time
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci.drills import session_teardown as st
from rediacc_ci.drills import tenant_isolation as ti
from rediacc_ci.drills import vm_check, vm_ssh
from rediacc_ci.drills import vm_check_receipt as receipt_mod
from rediacc_ci.tests import test_drills_vm_check as harness

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Mapping, Sequence

GUID_A = "11111111-2222-4333-8444-555555555555"
GUID_B = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"

# --------------------------------------------------------------------------- pure helpers


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("\r✔ Sessions ended: 2 sessions (5 processes) (40ms)\n", (2, 5)),
        ("✔ Sessions ended: 1 sessions (3 processes) (1.2s)\n", (1, 3)),
        # renet's own log line is not the step the CLI prints.
        ("Ended 2 sessions (5 processes) of repository abc\n", None),
        # The last line wins: the BeforeClose sweep can log a second one.
        (
            "✔ Sessions ended: 1 sessions (2 processes) (3ms)\n✔ Sessions ended: 1 sessions (1 processes) (2ms)",
            (1, 1),
        ),
        ("Stopping repository services\n", None),
        ("", None),
    ],
)
def test_sessions_ended(text: str, want: tuple[int, int] | None) -> None:
    assert st.sessions_ended(text) == want


def test_procs_script_and_count() -> None:
    script = st.procs_script(2816)
    assert "/sys/fs/cgroup/rediacc.slice/renet-exec-2816/cgroup.procs" in script
    assert "NOCG" in script
    assert st.procs_count("PROCS=3\n") == 3
    assert st.procs_count("PROCS=0\n") == 0
    assert st.procs_count("NOCG\n") is None
    assert st.procs_count("") is None


def test_process_scripts_anchor_the_pattern() -> None:
    assert "'^sleep 612345$'" in st.wait_alive_script(612345)
    assert "'^sleep 612345$'" in st.nohup_script(612345)
    assert "nohup sleep 612345" in st.nohup_script(612345)
    kill = st.kill_script([1, 2, 3])
    assert "'^sleep (1|2|3)$'" in kill
    assert "! pgrep" in kill


def test_sleeps_do_not_collide_with_i1() -> None:
    run_id = "vmc-10241200-abcdef"
    mine = {st.sleep_seconds(run_id, s) for s in (st.SALT_NOHUP, st.SALT_HELD, st.SALT_BARE)}
    theirs = {ti.sleep_seconds(run_id, s) for s in (1, 2)}
    assert len(mine) == 3
    assert not mine & theirs


def _probe(sleeps: dict[int, str], cgroup: str = "ABSENT", mapper: str = "ABSENT") -> str:
    lines = ["SLEEP %d %s" % (s, v) for s, v in sleeps.items()]
    if cgroup:
        lines.append("CGROUP %s" % cgroup)
    if mapper:
        lines.append("MAPPER %s" % mapper)
    return "\n".join(lines) + "\n"


def test_teardown_probe_script_reads_every_fact() -> None:
    script = st.teardown_probe_script(2816, GUID_A, [11, 12])
    assert "'^sleep 11$'" in script
    assert "'^sleep 12$'" in script
    assert "renet-exec-2816/cgroup.events" in script
    assert "/dev/mapper/%s" % GUID_A in script


@pytest.mark.parametrize(
    ("text", "ok", "fragment"),
    [
        (_probe({11: "GONE", 12: "GONE"}), True, "SLEEP 11 GONE"),
        (_probe({11: "GONE", 12: "GONE"}, cgroup="populated 0"), True, "populated 0"),
        (_probe({11: "ALIVE", 12: "GONE"}), False, "sleep 11 alive"),
        (_probe({11: "GONE"}), False, "sleep 12 unread"),
        (_probe({11: "GONE", 12: "GONE"}, cgroup="populated 1"), False, "cgroup populated 1"),
        (_probe({11: "GONE", 12: "GONE"}, cgroup=""), False, "cgroup unread"),
        (_probe({11: "GONE", 12: "GONE"}, mapper="PRESENT"), False, "mapper present"),
        (_probe({11: "GONE", 12: "GONE"}, mapper=""), False, "mapper unread"),
        ("", False, "no output"),
    ],
)
def test_teardown_verdict(text: str, ok: bool, fragment: str) -> None:
    got, why = st.teardown_verdict(text, [11, 12])
    assert got is ok, why
    assert fragment in why


# --------------------------------------------------------------------------- registration


def test_step_shape() -> None:
    step_id, deps, fn = st.STEP
    assert step_id == "I2"
    assert deps == ("V1.2",)
    assert fn is st.run


def test_vm_check_registers_i2_once_after_i1() -> None:
    ids = [s[0] for s in vm_check.EXTRA_RENET_STEPS]
    assert st.STEP in vm_check.EXTRA_RENET_STEPS
    assert ids.count("I2") == 1
    assert ids.index("I2") == ids.index("I1") + 1
    renet = vm_check.PHASE_STEPS[vm_check.SIDE_RENET]
    assert renet.count("I2") == 1
    assert renet.index("I2") > renet.index("I1")


def test_only_i2_drags_in_v12_and_its_own_dependencies() -> None:
    assert set(vm_check.VmCheck._ONLY_DEPS["I2"]) == {"V1.2", "P5", "V1.1"}


def _main(
    tmp_path: pathlib.Path, world: Any, argv: Sequence[str], extra_fns: Mapping[str, Any]
) -> tuple[int, str, dict[str, Any]]:
    out = io.StringIO()
    environ = {
        "HOME": str(tmp_path / "home"),
        "PATH": os.environ.get("PATH", ""),
        "VM_NET_BASE": harness.NET,
    }
    rc = vm_check.main(
        [*argv, "--keep-work", "--wait", "0"],
        root=world.root,
        host=world,
        account=harness.FakeAccount(),
        lock=vm_check.Lock(tmp_path / "vm-check.lock"),
        out=out,
        environ=environ,
        inputs_fn=lambda _root: harness.DIGEST,
        account_modified_fn=lambda _root: False,
        account_digest_fn=lambda _root: harness.ADIGEST,
        u1_fn=harness.stub_u1,
        extra_fns=extra_fns,
    )
    latest = world.root / receipt_mod.CACHE_DIR / receipt_mod.LATEST
    receipt = json.loads(latest.read_text()) if latest.exists() else {}
    return rc, out.getvalue(), receipt


def test_only_i2_runs_v12_then_i2(tmp_path: pathlib.Path) -> None:
    world = harness.make_world(tmp_path, stored_ok=True)
    seen: list[str] = []

    def stub(check: Any) -> None:
        seen.append("I2 forks=%d" % len(check.guids))
        check.check("I2", "stub I2", True)

    _rc, out, receipt = _main(tmp_path, world, ["--only", "I2"], {**harness.STUB_EXTRA, "I2": stub})
    assert receipt == {}, "a --only run writes no receipt.json"
    assert seen == ["I2 forks=2"]
    ids = [ln.split()[0] for ln in out.splitlines() if ln.startswith("  ")]
    assert ids.index("V1.2") < ids.index("I2")
    assert "I1" not in ids
    assert "U1" not in ids


def test_a_full_run_whose_i2_records_nothing_is_not_verified(tmp_path: pathlib.Path) -> None:
    world = harness.make_world(tmp_path)
    rc, out, receipt = _main(tmp_path, world, [], {**harness.STUB_EXTRA, "I2": lambda _check: None})
    assert rc != vm_check.EXIT_VERIFIED, out
    assert receipt.get("status") != receipt_mod.VERIFIED


# --------------------------------------------------------------------------- the live step, scripted


class Res:
    def __init__(self, rc: int = 0, out: str = "", err: str = "") -> None:
        self.rc, self.out, self.err, self.ms = rc, out, err, 0

    def text(self) -> str:
        return (self.out + "\n" + self.err).strip()


class Opts:
    parent = "vmcheck-base"


SLEEP_RE = re.compile(r"\^sleep (\d+)\$")


class FakeCtx:
    """The slice of VmCheck the I2 step drives: a worker that tracks which `sleep`s run and whether A is mounted, answering from the fixed renet (or from `broken`, a set of defect keys)."""

    def __init__(self, work: pathlib.Path, broken: frozenset[str] = frozenset()) -> None:
        self.run_id = "vmc-10241200-abcdef"
        self.tags = vm_check.fork_tags("10241200", "abcdef")
        self.network_ids = {self.tags[0]: "2816", self.tags[1]: "2880"}
        self.guids = {self.tags[0]: GUID_A, self.tags[1]: GUID_B}
        self.work = work
        self.environ: dict[str, str] = {}
        self.ssh_user, self.ssh_key, self.worker_ip = "u", "/k", "192.168.111.11"
        self.opts = Opts()
        self.sweep_leftovers: list[str] = []
        self.rows: list[tuple[str, str, bool | None]] = []
        self.calls: list[str] = []
        self.broken = broken
        self.alive: set[int] = set()
        self.mounted = True

    # VmCheck's ledger
    def check(self, step_id: str, desc: str, ok: bool, *_a: Any, **_kw: Any) -> bool:
        self.rows.append((step_id, desc, bool(ok)))
        return bool(ok)

    def record(self, step_id: str, desc: str, ok: bool | None, *_a: Any, **_kw: Any) -> bool:
        self.rows.append((step_id, desc, ok))
        return bool(ok)

    def scrub(self, text: str) -> str:
        return text

    def remote_evidence(self, res: Any) -> str:
        return "rc=%d" % res.rc

    def ref(self, tag: str) -> str:
        return "%s:%s" % (self.opts.parent, tag)

    # Commands
    def shell(self, ref: str, command: str, *_a: Any, **_kw: Any) -> Res:
        return self.rdc("term", "connect", ref, "-c", command)

    def rdc(self, *args: str, **_kw: Any) -> Res:
        line = " ".join(args)
        self.calls.append("rdc " + line)
        b = self.broken
        if args[:2] == ("repo", "down"):
            if "--unmount" in args:
                if "downfails" in b:
                    return Res(1, "", "device still in use")
                ended = len(self.alive)
                if "survive" not in b:
                    self.alive.clear()
                self.mounted = "mapperstays" in b
                text = (
                    ""
                    if "noline" in b
                    else "✔ Sessions ended: 2 sessions (%d processes) (40ms)\n" % ended
                )
                return Res(0, "Stopping repository services\n" + text)
            # A bare down: `barekills` is the defect of ending sessions without an unmount.
            if "barekills" in b:
                self.alive.clear()
            return Res(0, "Stopping repository services\n")
        if args[:2] == ("repo", "up"):
            self.mounted = True
            return Res(1, "", "mount failed") if "upfails" in b else Res()
        if args[:2] == ("term", "connect"):
            command = args[-1]
            if command.startswith("sleep "):
                # The held-open connect: its sleep runs until the down ends it.
                self.alive.add(int(command.split()[1]))
                return Res(137)
            if "nohup sleep" in command:
                self.alive.add(int(command.split()[2]))
                return Res(0, "STARTED\n")
            if command.startswith("echo "):
                return Res(0, command.split()[1] + "\n")
        return Res()

    def host_run(self, argv: Sequence[str], **_kw: Any) -> Res:
        command = argv[-1]
        self.calls.append("host " + command)
        sleeps = [int(n) for n in SLEEP_RE.findall(command)]
        if "pkill" in command:
            if "ssh-cleanup" in self.broken:
                return Res(vm_ssh.SSH_FAILED, "", "ssh: connect to host: Connection timed out")
            self.alive.clear()
            return Res()
        if "PROCS=" in command:
            return Res(0, "PROCS=%d\n" % len(self.alive))
        if "MAPPER" in command:
            lines = ["SLEEP %d %s" % (s, "ALIVE" if s in self.alive else "GONE") for s in sleeps]
            lines.append("CGROUP " + ("populated 1" if self.alive else "ABSENT"))
            lines.append("MAPPER " + ("PRESENT" if self.mounted else "ABSENT"))
            return Res(0, "\n".join(lines) + "\n")
        if "ALIVE" in command and sleeps:
            if "$(seq" in command:
                # wait_alive_script polls on the worker; here the held connect's thread may not have run yet.
                deadline = time.monotonic() + 5
                while sleeps[0] not in self.alive and time.monotonic() < deadline:
                    time.sleep(0.01)
            if sleeps[0] in self.alive:
                return Res(0, "ALIVE\n")
            return Res(1, "GONE\n")
        return Res()

    def say(self, text: str = "") -> None:
        pass


def _failed(ctx: FakeCtx) -> list[str]:
    return [d for _s, d, ok in ctx.rows if ok is False]


def test_the_live_step_passes_on_the_fixed_behaviour_and_cleans_up(tmp_path: pathlib.Path) -> None:
    ctx = FakeCtx(tmp_path)
    st.run(ctx)
    assert not _failed(ctx), _failed(ctx)
    assert {s for s, _d, _ok in ctx.rows} == {"I2"}
    descs = " | ".join(d for _s, d, _ok in ctx.rows)
    for row in ("I2.1", "I2.2", "I2.3", "I2.4", "I2.5", "I2.6", "I2.7"):
        assert row in descs, row
    # The verbs in their order: the unmounting down, up, the bare down, up again.
    verbs = [c for c in ctx.calls if c.startswith("rdc repo ")]
    ref = ctx.ref(ctx.tags[0])
    assert verbs == [
        "rdc repo down %s --unmount" % ref,
        "rdc repo up %s" % ref,
        "rdc repo down %s" % ref,
        "rdc repo up %s" % ref,
    ]
    # The held-open connect ran before the down.
    held = next(
        i for i, c in enumerate(ctx.calls) if re.match(r"rdc term connect \S+ -c sleep \d+$", c)
    )
    down = ctx.calls.index("rdc repo down %s --unmount" % ref)
    assert held < down
    # The cleanup killed every sleep this step started, and nothing was left.
    kill = [c for c in ctx.calls if "pkill" in c]
    assert len(kill) == 1
    for salt in (st.SALT_NOHUP, st.SALT_HELD, st.SALT_BARE):
        assert str(st.sleep_seconds(ctx.run_id, salt)) in kill[0]
    assert ctx.sweep_leftovers == []


@pytest.mark.parametrize(
    ("broken", "row"),
    [
        ("survive", "I2.5 after the down no session sleep is alive"),
        ("mapperstays", "I2.5 after the down no session sleep is alive"),
        ("noline", "I2.4 the down's output says it ended at least one session"),
        ("downfails", "I2.3 rdc repo down"),
        ("upfails", "I2.6 rdc repo up"),
        ("barekills", "I2.7 the nohup sleep is still alive after a bare down"),
    ],
)
def test_each_defect_is_a_fail_row(tmp_path: pathlib.Path, broken: str, row: str) -> None:
    ctx = FakeCtx(tmp_path, frozenset({broken}))
    st.run(ctx)
    assert any(d.startswith(row) for d in _failed(ctx)), _failed(ctx)


def test_a_failed_down_skips_the_rows_that_need_it_and_brings_a_back(
    tmp_path: pathlib.Path,
) -> None:
    ctx = FakeCtx(tmp_path, frozenset({"downfails"}))
    st.run(ctx)
    descs = [d for _s, d, _ok in ctx.rows]
    assert not [d for d in descs if d.startswith(("I2.4", "I2.5"))]
    assert "I2.2 the held-open connect returned once A went down" not in descs


def test_a_failed_up_brings_a_back_in_cleanup(tmp_path: pathlib.Path) -> None:
    ctx = FakeCtx(tmp_path, frozenset({"upfails"}))
    st.run(ctx)
    ref = ctx.ref(ctx.tags[0])
    ups = [c for c in ctx.calls if c == "rdc repo up %s" % ref]
    # I2.6's up, then the cleanup's retry; I2.7 never ran.
    assert len(ups) == 2
    assert not [d for _s, d, _ok in ctx.rows if d.startswith("I2.7")]


def test_missing_fork_stops_before_any_vm_command(tmp_path: pathlib.Path) -> None:
    ctx = FakeCtx(tmp_path)
    ctx.network_ids = {}
    st.run(ctx)
    assert [ok for _s, _d, ok in ctx.rows] == [False]
    assert ctx.calls == []
    assert ctx.sweep_leftovers == []


def test_a_failed_cleanup_probe_is_a_leftover_not_a_pass(tmp_path: pathlib.Path) -> None:
    ctx = FakeCtx(tmp_path, frozenset({"ssh-cleanup"}))
    st.run(ctx)
    assert len(ctx.sweep_leftovers) == 1, ctx.sweep_leftovers
    assert "root ssh probe failed (rc=255)" in ctx.sweep_leftovers[0]
