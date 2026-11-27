"""`rediacc_ci.drills.win_check`: the whole flow driven through a fake host, so no case reaches a VM, a build or a lock file.

`FakeHost` answers every command the check issues (the ssh probe, `ssh-keyscan`, `./rdc.sh --version`, the windows renet build, scp, the suite runs and the screenshot) from scripted answers, keyed on what the argv is. Each verdict class comes from bending one answer. The three controls the plan names (agent/plans/PLAN-windows-lane.md WL6) are `test_failed_step_is_failed`, `test_no_step_line_is_no_assertions` and `test_unreachable_vm_is_win_vm_unavailable`.
"""

from __future__ import annotations

import base64
import contextlib
import datetime
import json
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci.drills import win_check

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator, Mapping, Sequence

TREE = "a" * 40
HEAD = "e" * 40
DIGEST = "d" * 64
KEYSCAN = (
    "# 192.168.111.11:22 SSH-2.0-OpenSSH_9.6\n"
    "192.168.111.11 ssh-ed25519 AAAAED\n"
    "192.168.111.11 ecdsa-sha2-nistp256 AAAAEC\n"
)
PROBE_OK = "RDC-PROBE node=C:\\Program Files\\nodejs\\node.exe\r\nRDC-PROBE user=rdc\r\nRDC-PROBE profile=C:\\Users\\rdc\r\n"


def step(
    suite: str, name: str, rc: int, expect: object = 0, ok: bool | None = None, **extra: Any
) -> str:
    if ok is None:
        ok = (rc != 0) if expect == "nonzero" else (rc == expect)
    payload = {"id": "%s.%s" % (suite, name), "rc": rc, "expect": expect, "ok": ok, **extra}
    return "RDC-STEP " + json.dumps(payload)


def suite_out(suite: str, lines: Sequence[str], *, end: bool = True) -> str:
    body = ["prose that the judge ignores", *lines]
    if end:
        body.append("RDC-SUITE " + json.dumps({"suite": suite, "steps": len(lines)}))
    return "\r\n".join(body) + "\r\n"


def passing(suite: str) -> str:
    return suite_out(
        suite, [step(suite, "one", 0), step(suite, "two", 6, 6), step(suite, "neg", 2, "nonzero")]
    )


def identity() -> dict[str, Any]:
    return {
        "tree": TREE,
        "head": HEAD,
        "dirty": False,
        "inputs": DIGEST,
        "surfaces": list(win_check.SURFACES),
        "submodules": {
            "private/renet": {"pointer": "c" * 40, "checkout": "c" * 40, "modified": False},
            "private/account": {"pointer": "b" * 40, "checkout": "b" * 40, "modified": False},
        },
        "renet": {"built": "c" * 40, "modified": False, "sha256": "f" * 64},
    }


class FakeHost(win_check.Host):
    """Scripted answers. `suites` maps a suite name to (rc, stdout); `answers` overrides any other call by its `key`."""

    def __init__(self, root: pathlib.Path) -> None:
        super().__init__(root, {"HOME": str(root), "USER": "dev"})
        self.calls: list[list[str]] = []
        self.envs: list[dict[str, str]] = []
        self.suites: dict[str, tuple[int, str]] = {
            s: (0, passing(s)) for s in win_check.SUITE_ORDER
        }
        self.answers: dict[str, win_check.Result] = {}
        self.busy = False
        self.timeouts: list[float] = []
        self.waits: list[float] = []
        for rel in (win_check.BUNDLE, win_check.RENET_LINUX, win_check.RENET_EXE):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(rel.encode())
        suites = root / win_check.SUITES_DIR
        suites.mkdir(parents=True, exist_ok=True)
        for name in ("common", *win_check.SUITE_ORDER):
            (suites / (name + ".ps1")).write_text("# %s\n" % name, encoding="utf-8")

    @staticmethod
    def key(argv: Sequence[str]) -> str:
        if argv[0] == "ssh":
            command = argv[-1]
            if "-EncodedCommand" in command:
                return "ssh-encoded"
            for suite in win_check.SUITE_ORDER:
                if command.endswith("\\%s.ps1" % suite):
                    return "suite:" + suite
            return "ssh"
        if argv[0] == "scp":
            return "scp:" + argv[-1].split(":", 1)[1]
        if argv[0] == "bash":
            return "renet-exe"
        return argv[0]

    def run(
        self, argv: Sequence[str], *, timeout: float, env: Mapping[str, str] | None = None
    ) -> win_check.Result:
        self.calls.append(list(argv))
        self.timeouts.append(timeout)
        self.envs.append(dict(env or {}))
        key = self.key(argv)
        if key in self.answers:
            return self.answers[key]
        if key.startswith("suite:"):
            rc, out = self.suites[key.split(":", 1)[1]]
            return win_check.Result(rc, out, "")
        if key == "ssh-encoded":
            if argv[-1] == win_check.encoded(win_check.PROBE_PS):
                return win_check.Result(0, PROBE_OK)
            return win_check.Result(0, "RDC-PROBE staged=1\r\nRDC-PROBE acl=0\r\n")
        if key == "ssh-keyscan":
            return win_check.Result(0, KEYSCAN)
        return win_check.Result(0, "")

    @contextlib.contextmanager
    def fleet_lock(self, wait_s: float) -> Iterator[None]:
        self.waits.append(wait_s)
        if self.busy:
            raise win_check.NotVerifiedError("fleet-busy", "resource fleet is busy: pid 1 holds it")
        yield

    def account_key(self) -> str:
        return "PUBKEY"

    def identity(self) -> dict[str, Any]:
        return identity()

    def now(self) -> datetime.datetime:
        return datetime.datetime(2026, 11, 27, 12, 0, 0, tzinfo=datetime.UTC)


def options(**over: Any) -> win_check.Options:
    base: dict[str, Any] = {
        "vm": "192.168.111.31",
        "key": "/k/id_rsa",
        "fleet_key": "/k/id_rsa",
        "worker_user": "dev",
        "domain": "rediacc31",
        "suites": win_check.FLEET_SUITES,
    }
    base.update(over)
    return win_check.Options(**base)


def run(host: FakeHost, **over: Any) -> tuple[int, dict[str, Any], list[str]]:
    said: list[str] = []
    rc = win_check.run_check(options(**over), host, said.append)
    runs = host.root / win_check.CACHE_DIR / win_check.RUNS_DIR
    (run_dir,) = list(runs.iterdir())
    receipt = json.loads((run_dir / win_check.LATEST).read_text(encoding="utf-8"))
    return rc, receipt, said


@pytest.fixture
def host(tmp_path: pathlib.Path) -> FakeHost:
    return FakeHost(tmp_path)


# --------------------------------------------------------------------------- verdicts


def test_all_suites_pass_is_verified(host: FakeHost) -> None:
    rc, receipt, said = run(host)
    assert rc == 0, said
    assert receipt["status"] == "VERIFIED"
    assert receipt["reason"] is None
    assert receipt["tier"] == "win"
    assert receipt["assertions"] == 3 * len(win_check.FLEET_SUITES)
    assert all(s["completed"] for s in receipt["suites"].values())
    latest = host.root / win_check.CACHE_DIR / win_check.LATEST
    assert json.loads(latest.read_text(encoding="utf-8"))["runId"] == receipt["runId"]
    ran = [k for k in map(FakeHost.key, host.calls) if k.startswith("suite:")]
    assert ran == ["suite:" + s for s in win_check.FLEET_SUITES]


def test_failed_step_is_failed(host: FakeHost) -> None:
    host.suites["guard"] = (0, suite_out("guard", [step("guard", "refused", 0, 2)]))
    rc, receipt, _ = run(host)
    assert rc == 1
    assert receipt["status"] == "FAILED"
    assert receipt["reason"]["class"] == "step-failed"
    assert "guard.refused: rc 0, expected 2" in receipt["reason"]["detail"]


def test_no_step_line_is_no_assertions(host: FakeHost) -> None:
    for suite in win_check.FLEET_SUITES:
        host.suites[suite] = (0, suite_out(suite, []))
    rc, receipt, _ = run(host)
    assert rc == 77
    assert receipt["status"] == "NOT_VERIFIED"
    assert receipt["reason"]["class"] == "no-assertions"


def test_unreachable_vm_is_win_vm_unavailable(host: FakeHost) -> None:
    host.answers["ssh-encoded"] = win_check.Result(
        255, "", "ssh: connect to host 192.168.111.31 port 22: No route to host"
    )
    rc, receipt, _ = run(host)
    assert rc == 77
    assert receipt["reason"]["class"] == "win-vm-unavailable"
    assert "No route to host" in receipt["reason"]["detail"]
    assert not any(FakeHost.key(c).startswith(("suite:", "scp:")) for c in host.calls)


def test_vm_without_node_is_win_bake_missing(host: FakeHost) -> None:
    host.answers["ssh-encoded"] = win_check.Result(0, "RDC-PROBE node=\r\nRDC-PROBE user=rdc\r\n")
    rc, receipt, _ = run(host)
    assert rc == 77
    assert receipt["reason"]["class"] == "win-bake-missing"


def test_worker_without_keys_is_worker_unavailable(host: FakeHost) -> None:
    host.answers["ssh-keyscan"] = win_check.Result(1, "", "")
    _, receipt, _ = run(host)
    assert receipt["reason"]["class"] == "worker-unavailable"


def test_build_failure_is_build_failed(host: FakeHost) -> None:
    host.answers["renet-exe"] = win_check.Result(1, "", "cmd/renet: undefined: foo")
    _, receipt, _ = run(host)
    assert receipt["reason"]["class"] == "build-failed"
    assert "undefined: foo" in receipt["reason"]["detail"]


def test_windows_build_carries_the_key_in_the_environment(host: FakeHost) -> None:
    run(host)
    idx = [FakeHost.key(c) for c in host.calls].index("renet-exe")
    assert host.envs[idx]["ACCOUNT_ED25519_PUBLIC_KEY"] == "PUBKEY"
    assert host.envs[idx]["GOOS"] == "windows"
    assert "PUBKEY" not in " ".join(host.calls[idx])


def test_skip_build_runs_no_build(host: FakeHost) -> None:
    rc, _, _ = run(host, skip_build=True)
    assert rc == 0
    keys = [FakeHost.key(c) for c in host.calls]
    assert "renet-exe" not in keys
    assert "./rdc.sh" not in keys


def test_scp_failure_is_stage_failed(host: FakeHost) -> None:
    host.answers["scp:" + win_check.REMOTE_BUNDLE] = win_check.Result(1, "", "scp: write failed")
    _, receipt, _ = run(host)
    assert receipt["reason"]["class"] == "stage-failed"


def test_missing_suite_file_is_stage_failed(host: FakeHost) -> None:
    (host.root / win_check.SUITES_DIR / "guard.ps1").unlink()
    _, receipt, _ = run(host)
    assert receipt["reason"]["class"] == "stage-failed"
    assert "guard.ps1" in receipt["reason"]["detail"]


def test_lost_lock_is_fleet_busy_and_not_latest(host: FakeHost) -> None:
    host.busy = True
    rc, receipt, _ = run(host)
    assert rc == 77
    assert receipt["reason"]["class"] == "fleet-busy"
    assert not (host.root / win_check.CACHE_DIR / win_check.LATEST).exists()
    assert host.calls == []


def test_suite_without_end_line_is_phase_not_run(host: FakeHost) -> None:
    host.suites["term"] = (0, suite_out("term", [step("term", "fleet", 0)], end=False))
    _, receipt, _ = run(host)
    assert receipt["reason"]["class"] == "phase-not-run"
    assert "term" in receipt["reason"]["detail"]


def test_end_count_mismatch_is_phase_not_run(host: FakeHost) -> None:
    out = "\r\n".join([step("dpapi", "ssh", 0), 'RDC-SUITE {"suite": "dpapi", "steps": 2}'])
    host.suites["dpapi"] = (0, out)
    _, receipt, _ = run(host)
    assert receipt["reason"]["class"] == "phase-not-run"


def test_ssh_lost_mid_suite_is_win_vm_unavailable(host: FakeHost) -> None:
    host.suites["term"] = (255, suite_out("term", [step("term", "fleet", 0)], end=False))
    _, receipt, _ = run(host)
    assert receipt["reason"]["class"] == "win-vm-unavailable"
    ran = [k for k in map(FakeHost.key, host.calls) if k.startswith("suite:")]
    assert ran[-1] == "suite:term"


def test_failed_step_outranks_could_not_judge(host: FakeHost) -> None:
    host.suites["keys"] = (0, suite_out("keys", [step("keys", "scan", 6, 0)]))
    host.suites["term"] = (255, "")
    _, receipt, _ = run(host)
    assert receipt["status"] == "FAILED"


def test_evidence_is_kept(host: FakeHost) -> None:
    _, receipt, _ = run(host)
    run_dir = host.root / receipt["runDir"]
    assert (run_dir / "keys.log").read_text(encoding="utf-8").startswith("prose")
    params = json.loads((run_dir / "params.json").read_text(encoding="utf-8"))
    assert params["expectedHostKeys"] == ["ecdsa-sha2-nistp256 AAAAEC", "ssh-ed25519 AAAAED"]
    assert params["key"] == "C:\\Users\\rdc\\.ssh\\fleet_rsa"
    assert any(c[0] == "virsh" and "rediacc31" in c for c in host.calls)


# --------------------------------------------------------------------------- the judge


@pytest.mark.parametrize(
    ("line", "why"),
    [
        ("not json", "malformed"),
        (json.dumps({"id": "other.x", "rc": 0, "expect": 0, "ok": True}), "is not <keys>.<step>"),
        (
            json.dumps({"id": "keys.x", "rc": "0", "expect": 0, "ok": True}),
            "rc '0' is not an integer",
        ),
        (json.dumps({"id": "keys.x", "rc": 0, "expect": "zero", "ok": True}), "expect 'zero'"),
        (json.dumps({"id": "keys.x", "rc": 0, "expect": 0}), "ok None is not a boolean"),
        (json.dumps({"id": "keys.x", "rc": 1, "expect": 0, "ok": True}), "the suite says ok=true"),
        (
            json.dumps({"id": "keys.x", "rc": 0, "expect": "nonzero", "ok": False}),
            "rc 0, expected nonzero",
        ),
        (
            json.dumps({"id": "keys.x", "rc": 2, "expect": 2, "ok": False, "match": False}),
            "output did not match",
        ),
    ],
)
def test_judge_refuses(line: str, why: str) -> None:
    row, failure = win_check.judge_step("keys", line)
    assert row["verdict"] == "failed"
    assert failure is not None
    assert why in failure


def test_judge_admits_nonzero_and_exact() -> None:
    for payload in (
        {"id": "keys.a", "rc": 6, "expect": 6, "ok": True},
        {"id": "keys.b", "rc": 2, "expect": "nonzero", "ok": True, "match": True},
    ):
        row, failure = win_check.judge_step("keys", json.dumps(payload))
        assert failure is None
        assert row["verdict"] == "ok"


def test_repeated_step_id_fails() -> None:
    out = suite_out("keys", [step("keys", "a", 0), step("keys", "a", 0)])
    outcome = win_check.parse_suite("keys", win_check.Result(0, out))
    assert outcome.failures == ["keys.a: the step id was printed twice"]


def test_indented_step_line_is_prose() -> None:
    out = "  " + step("keys", "a", 1) + "\r\n" + 'RDC-SUITE {"suite": "keys", "steps": 0}\r\n'
    outcome = win_check.parse_suite("keys", win_check.Result(0, out))
    assert outcome.rows == []
    assert outcome.completed


def test_selftest_fires() -> None:
    said: list[str] = []
    assert win_check.selftest(said.append) == 1
    assert "selftest fired as designed" in said[0]


# --------------------------------------------------------------------------- the plan


def test_plan_suites_adds_keys_and_hostinger_sync() -> None:
    assert win_check.plan_suites(["term"], "fleet") == ("keys", "term")
    assert win_check.plan_suites([], "fleet") == win_check.FLEET_SUITES
    assert "sync" in win_check.plan_suites([], "hostinger")
    assert win_check.plan_suites(["dpapi"], "fleet") == ("dpapi",)


def test_sync_needs_a_hostinger_fork() -> None:
    env = {"HOME": "/h", "USER": "u"}
    with pytest.raises(SystemExit):
        win_check.parse_args(["--suite", "sync"], env)
    with pytest.raises(SystemExit):
        win_check.parse_args(["--target", "hostinger"], env)
    _, opts = win_check.parse_args(["--target", "hostinger", "--fork", "app:wc"], env)
    assert "sync" in opts.suites
    assert opts.key == "/h/.renet/staging/.ssh/id_rsa"
    assert opts.worker_user == "u"
    assert opts.domain == "rediacc31"


def test_unknown_suite_is_refused() -> None:
    with pytest.raises(SystemExit):
        win_check.parse_args(["--suite", "nope"], {"HOME": "/h", "USER": "u"})


def test_default_domain() -> None:
    assert win_check.default_domain("192.168.111.31") == "rediacc31"
    assert win_check.default_domain("192.168.111.11") == ""
    assert win_check.default_domain("192.168.122.40") == ""


def test_dry_run_touches_nothing(tmp_path: pathlib.Path) -> None:
    said: list[str] = []
    assert win_check.dry_run(options(), said.append) == 0
    assert any("suites    keys, guard, term, dpapi, vscode" in s for s in said)
    assert not list(tmp_path.iterdir())


def test_encoded_round_trips() -> None:
    line = win_check.encoded("'a' + $b")
    assert base64.b64decode(line.rsplit(" ", 1)[1]).decode("utf-16-le") == "'a' + $b"


def test_prune_keeps_newest(tmp_path: pathlib.Path) -> None:
    for i in range(25):
        (tmp_path / ("winc-%02d" % i)).mkdir()
    win_check.prune_runs(tmp_path, keep=20)
    names = sorted(p.name for p in tmp_path.iterdir())
    assert names[0] == "winc-05"
    assert len(names) == 20


# --------------------------------------------------------------------------- the suites in the tree


def test_every_suite_in_the_tree_keeps_the_contract() -> None:
    """Each suite the driver can run exists, dot-sources common.ps1, names itself, and ends with the RDC-SUITE line; the files stay ASCII, since Windows PowerShell 5.1 reads a script without a BOM in the ANSI code page."""
    suites = win_check.repo_root() / win_check.SUITES_DIR
    for name in ("common.ps1", "vscode.cmd", *(s + ".ps1" for s in win_check.SUITE_ORDER)):
        text = (suites / name).read_text(encoding="utf-8")
        assert text.isascii(), name
    for suite in win_check.SUITE_ORDER:
        text = (suites / (suite + ".ps1")).read_text(encoding="utf-8")
        assert ". (Join-Path $PSScriptRoot 'common.ps1')" in text, suite
        assert "Initialize-RdcSuite '%s'" % suite in text, suite
        assert text.rstrip().endswith("Complete-RdcSuite"), suite
