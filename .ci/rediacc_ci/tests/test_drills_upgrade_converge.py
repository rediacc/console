"""`rediacc_ci.drills.upgrade_converge`: the CLI-free helpers of the U1 step, pinned without a machine. The live `run(ctx)` orchestration is exercised by `npm run vm:check` (its U1 rows) and is wired into vm_check by an injected `u1_fn` the vm_check tests stub; here only the pure pieces -- the layout path strings, the build and status command text, and the parsers that read the stamp and the converge report -- are checked."""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import pathlib
import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest

from rediacc_ci.drills import upgrade_converge as u
from rediacc_ci.drills import vm_check
from rediacc_ci.well_known import RUNTIME_DIR

if TYPE_CHECKING:
    from collections.abc import Callable

SHA = "16538095dbbae2202b2d00bd9ff0a1b8a086ed11168ae3ecf1b2a195f4cdc4c0"
# The stamp exactly as renet wrote it on ops-worker, 2026-10-24 (pretty-printed over several lines).
LIVE_STAMP = (
    '{\n  "epoch": 1,\n  "renet_sha256": "%s",\n  "pid": 69811,\n  "started_at": "2026-10-24T08:16:20.724692721Z"\n}\n'
    % SHA
)


def test_layout_paths_match_the_per_network_and_flat_forms() -> None:
    assert u.old_docker_socket(8512) == f"{RUNTIME_DIR}/docker-8512.sock"
    assert u.new_docker_socket(8512) == f"{RUNTIME_DIR}/net-8512/docker-8512.sock"
    assert u.runtime_stamp_path(8512) == "/var/lib/rediacc/runtime/net-8512.json"
    assert u.new_docker_socket("8512") == u.new_docker_socket(8512)


def test_pre_isolation_commit_is_the_parent_of_the_layout_change() -> None:
    assert u.PRE_ISOLATION_COMMIT == "0c3a88a^"


def test_build_script_clones_and_builds_without_touching_bin() -> None:
    script = u.build_old_renet_script("/w/src", "/w/old", "7070d286")
    # A checkout, not `git archive`: renet's `.gitattributes` marks `* export-ignore`, so archive would export only LICENSE.
    assert "git clone --quiet --shared --no-checkout private/renet /w/src" in script
    assert "checkout --quiet 7070d286" in script
    assert "archive" not in script
    assert "go build -tags nolicense -o /w/old ./cmd/renet" in script
    assert "private/renet/bin" not in script
    assert script.startswith("set -eu")


def test_build_script_quotes_a_hostile_path() -> None:
    script = u.build_old_renet_script("/w/a b; rm -rf /", "/w/out", "7070d28")
    assert "'/w/a b; rm -rf /'" in script
    assert "; rm -rf / &&" not in script


def _envelope(report: dict[str, object], success: bool = True) -> str:
    return json.dumps({"success": success, "command": "machine converge", "data": report})


@pytest.mark.parametrize(
    ("payload", "clean"),
    [
        ('{"summary": {"would_converge": 0}, "plan": []}', True),
        ('{"summary": {"would_converge": 0}, "plan": [{"name": "a"}]}', True),
        ('{"summary": {"would_converge": 2}, "plan": []}', False),
        ('{"summary": {"would_converge": 0}, "plan": [{"stale_reasons": ["epoch"]}]}', False),
        ("not json", False),
        ('{"plan": []}', False),
        # The CLI's `--json` envelope, as the 2026-10-24 live run printed it.
        (
            _envelope(
                {"summary": {"would_converge": 0}, "plan": [{"name": "a", "action": "current"}]}
            ),
            True,
        ),
        (
            _envelope(
                {"summary": {"would_converge": 1}, "plan": [{"stale_reasons": ["no_stamp"]}]}
            ),
            False,
        ),
        (_envelope({"summary": {"would_converge": 0}, "plan": []}, success=False), False),
        ('{"summary": {}, "plan": []}', False),
        ('{"summary": {"would_converge_renamed": 0}, "plan": []}', False),
    ],
)
def test_dry_run_reports_zero_stale(payload: str, clean: bool) -> None:
    assert u.dry_run_reports_zero_stale(payload) is clean


def test_config_name_is_run_scoped() -> None:
    assert u.config_name("vmc-10240427-94d613") == "u1-vmc-10240427-94d613"


def test_parse_stamp_reads_the_live_multi_line_file() -> None:
    stamp = u.parse_stamp("NEWSOCK\n" + LIVE_STAMP)
    assert stamp is not None
    assert stamp["epoch"] == 1
    assert stamp["pid"] == 69811
    assert stamp["renet_sha256"] == SHA


@pytest.mark.parametrize("text", ["", "not json", "NEWSOCK\n", "{broken"])
def test_parse_stamp_rejects_what_is_not_a_stamp(text: str) -> None:
    assert u.parse_stamp(text) is None


@pytest.mark.parametrize(
    ("stamp", "deployed", "current"),
    [
        ({"epoch": 1, "pid": 42, "renet_sha256": SHA}, SHA, True),
        ({"epoch": 2, "pid": 42, "renet_sha256": SHA}, SHA, True),
        # A stamp left by a daemon the old binary started: the converge pass did not restart it.
        ({"epoch": 1, "pid": 42, "renet_sha256": "0" * 64}, SHA, False),
        ({"epoch": 0, "pid": 42, "renet_sha256": SHA}, SHA, False),
        ({"epoch": 1, "pid": 0, "renet_sha256": SHA}, SHA, False),
        ({"epoch": 1, "renet_sha256": SHA}, SHA, False),
        ({"epoch": 1, "pid": 42, "renet_sha256": SHA}, "", False),
        (None, SHA, False),
    ],
)
def test_stamp_is_current(stamp: dict[str, object] | None, deployed: str, current: bool) -> None:
    assert u.stamp_is_current(stamp, deployed) is current


def test_file_sha256(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "bin"
    path.write_bytes(b"renet")
    assert u.file_sha256(path) == hashlib.sha256(b"renet").hexdigest()
    assert u.file_sha256(tmp_path / "absent") == ""


def test_run_is_the_default_u1_step() -> None:
    # vm_check wires this function as the default u1_fn; a rename here would silently drop the live step, so pin the attribute.
    sig = inspect.signature(vm_check.VmCheck.__init__)
    assert sig.parameters["u1_fn"].default is u.run


OLD_LISTING = "docker-8512.sock\ndocker-8513.sock\ncontainerd-8512\nsecrets\n"
NEW_LISTING = "net-8512\n"


def test_runtime_view_verdict_reads_the_old_layout_breach_and_the_converged_isolation() -> None:
    assert u.runtime_view_verdict(OLD_LISTING, 8512, 8513, expect_peer_visible=True)[0]
    assert u.runtime_view_verdict(NEW_LISTING, 8512, 8513, expect_peer_visible=False)[0]
    # The converged layout is not ok while the peer is still listed, and the old one is not a breach when it is not.
    assert not u.runtime_view_verdict(OLD_LISTING, 8512, 8513, expect_peer_visible=False)[0]
    assert not u.runtime_view_verdict(NEW_LISTING, 8512, 8513, expect_peer_visible=True)[0]
    assert not u.runtime_view_verdict("net-8513\n", 8512, 8513, expect_peer_visible=False)[0]


@pytest.mark.parametrize("text", ["", "NOPID\n", "  \n"])
@pytest.mark.parametrize("expect", [True, False])
def test_a_probe_that_listed_nothing_is_never_ok(text: str, expect: bool) -> None:
    ok, evidence = u.runtime_view_verdict(text, 8512, 8513, expect_peer_visible=expect)
    assert not ok
    assert "no runtime listing" in evidence


def test_pid_file_paths_follow_each_layout() -> None:
    assert u.old_docker_pid_file(8512) == f"{RUNTIME_DIR}/docker-8512.pid"
    assert u.new_docker_pid_file("8512") == f"{RUNTIME_DIR}/net-8512/docker-8512.pid"


def test_runtime_view_script_reads_the_pid_file_and_is_valid_shell() -> None:
    script = u.runtime_view_script(u.new_docker_pid_file(8512))
    assert "nsenter -t $pid -m ls -1" in script
    assert "net-8512/docker-8512.pid" in script
    assert "pgrep" not in script
    assert "HOSTNS" in script
    assert subprocess.run(["bash", "-n", "-c", script], check=False).returncode == 0
    # The before-upgrade row opts out of the host-namespace refusal.
    assert "HOSTNS" not in u.runtime_view_script("/x.pid", allow_host_ns=True)


def _run_script(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)


def test_no_dockerd_prints_nopid(tmp_path: pathlib.Path) -> None:
    missing = _run_script(u.runtime_view_script(str(tmp_path / "absent.pid")))
    assert (missing.returncode, missing.stdout.strip()) == (3, "NOPID")
    # A live pid that is not a dockerd (this very test process) is NOPID too.
    pid_file = tmp_path / "docker.pid"
    pid_file.write_text("%d\n" % os.getpid())
    other = _run_script(u.runtime_view_script(str(pid_file)))
    assert (other.returncode, other.stdout.strip()) == (3, "NOPID")
    pid_file.write_text("not-a-pid")
    assert _run_script(u.runtime_view_script(str(pid_file))).stdout.strip() == "NOPID"


@pytest.mark.skipif(
    not os.access("/proc/1/ns/mnt", os.R_OK),
    reason=(
        "CANNOT RUN (1 of 1 requirement(s) missing): a readable /proc/1/ns/mnt. "
        "A non-root user cannot read pid 1's namespace link when pid 1 is root's."
    ),
)
def test_a_dockerd_in_the_host_namespace_is_refused(tmp_path: pathlib.Path) -> None:
    fake = tmp_path / "dockerd"
    shutil.copy(shutil.which("sleep") or "/bin/sleep", fake)
    proc = subprocess.Popen([str(fake), "30"])
    try:
        pid_file = tmp_path / "docker.pid"
        pid_file.write_text("%d\n" % proc.pid)
        res = _run_script(u.runtime_view_script(str(pid_file)))
        assert (res.returncode, res.stdout.strip()) == (4, "HOSTNS")
    finally:
        proc.kill()
        proc.wait()


def test_a_host_namespace_listing_is_not_checkable() -> None:
    ok, evidence = u.runtime_view_verdict("HOSTNS\n", 8512, 8513, expect_peer_visible=True)
    assert not ok
    assert "NOT ISOLATED-CHECKABLE" in evidence


def test_sees_peer_on_a_sample_listing() -> None:
    _, evidence = u.runtime_view_verdict(OLD_LISTING, 8512, 8513, expect_peer_visible=True)
    assert "sees_own=True sees_peer=True" in evidence
    _, evidence = u.runtime_view_verdict(NEW_LISTING, 8512, 8513, expect_peer_visible=False)
    assert "sees_own=True sees_peer=False" in evidence


def test_host_namespace_guard_fails_closed_on_an_unreadable_namespace() -> None:
    # Review d7cb08f1.1: an empty readlink on either side must refuse, not compare unequal and pass.
    script = u.runtime_view_script(u.new_docker_pid_file(7))
    assert "echo HOSTNS; exit 4" in script
    # Run the guard itself, with readlink stubbed: an empty link on either side must print HOSTNS, two distinct links must pass.
    guard = script[script.index("own=") : script.index("nsenter")]
    for own, host, expect in (
        ("", "mnt:[1]", "HOSTNS"),
        ("mnt:[2]", "", "HOSTNS"),
        ("mnt:[1]", "mnt:[1]", "HOSTNS"),
        ("mnt:[2]", "mnt:[1]", "PASSED"),
    ):
        stub = (
            'readlink() { case "$1" in /proc/1/*) echo "%s";; *) echo "%s";; esac; }; pid=42; '
            % (host, own)
        )
        out = subprocess.run(
            ["bash", "-c", stub + guard + "echo PASSED"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        assert out.strip() == expect, (own, host, out)


# --------------------------------------------------------------------------- the old-layout bring-up without a CLI job


def test_with_stdin_from_feeds_the_file_and_keeps_it_out_of_argv(tmp_path: pathlib.Path) -> None:
    secret = tmp_path / "cred"
    secret.write_text("s3cret-value\n")
    argv = u.with_stdin_from(str(secret), ["cat"])
    assert not any("s3cret-value" in a for a in argv)
    out = subprocess.run(argv, capture_output=True, text=True, check=False)
    assert out.returncode == 0
    assert out.stdout == "s3cret-value\n"


def _install_world(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    root = tmp_path / "renet-root"
    slot = root / "0.0.0-dev"
    slot.mkdir(parents=True)
    (slot / "renet").write_text("new binary\n")
    (root / "current").mkdir()
    (root / "current" / "renet").symlink_to(slot / "renet")
    monkeypatch.setattr(u, "RENET_CURRENT", str(root / "current" / "renet"))
    monkeypatch.setattr(u, "RENET_PROVISION_LOCK", str(tmp_path / "lock"))
    return slot / "renet"


@pytest.mark.skipif(shutil.which("flock") is None, reason="flock (util-linux) is not installed")
def test_install_script_replaces_the_slot_current_resolves_to(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slot = _install_world(tmp_path, monkeypatch)
    staged = tmp_path / "staged"
    staged.write_text("old binary\n")
    script = u.install_current_renet_script(str(staged), sudo="")
    out = subprocess.run(["sh", "-c", script], capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stderr
    assert slot.read_text() == "old binary\n"
    assert not staged.exists()
    assert os.access(slot, os.X_OK)
    assert u.installed_sha(out.stdout) == hashlib.sha256(b"old binary\n").hexdigest()


def test_install_script_refuses_a_current_outside_the_install_root(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(u, "RENET_CURRENT", str(tmp_path / "nowhere" / "current" / "renet"))
    staged = tmp_path / "staged"
    staged.write_text("old binary\n")
    script = u.install_current_renet_script(str(staged), sudo="")
    out = subprocess.run(["sh", "-c", script], capture_output=True, text=True, check=False)
    assert not staged.exists()  # a refused install still removes the upload
    assert out.returncode == 3
    assert "NOTARGET" in out.stdout
    assert u.installed_sha(out.stdout) == ""


def test_the_live_install_script_targets_the_provisioned_slot() -> None:
    script = u.install_current_renet_script("/tmp/x")
    assert "/usr/lib/rediacc/renet/current/renet" in script
    assert "/usr/lib/rediacc/renet/*/renet)" in script
    # The lock is the ssh user's; only the install is privileged (fs.protected_regular).
    assert "flock -w 120 /tmp/.rdc-renet-provision.lock sudo sh -c" in script
    assert subprocess.run(["sh", "-n", "-c", script], check=False).returncode == 0


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("INSTALLED %s\n" % SHA, SHA),
        ("noise\nINSTALLED %s\n" % SHA, SHA),
        ("INSTALLED \n", ""),
        ("INSTALLED abc\n", ""),
        ("", ""),
    ],
)
def test_installed_sha(text: str, want: str) -> None:
    assert u.installed_sha(text) == want


def test_old_repo_up_command_is_the_old_builder_shape() -> None:
    cmd = u.old_repo_up_command("g-fork", 8512, "base:u1a", "g-grand")
    assert u.shlex.split(cmd) == [
        "sudo",
        "renet",
        "repository",
        "up",
        "--name",
        "g-fork",
        "--datastore",
        u.DATASTORE_PATH,
        "--network-id",
        "8512",
        "--repo-name",
        "base:u1a",
        "--grand-guid",
        "g-grand",
        "--password-stdin",
    ]


def _doc(tags: dict[str, dict[str, object]], net: dict[str, object]) -> dict[str, object]:
    """A config document in the live shape: resources half for identity, state half for the network id."""
    return {
        "resources": {"repositories": {"base": {"tags": tags}}},
        "state": {"repos": {"base": {t: {"networkId": n} for t, n in net.items()}}},
    }


def test_fork_record_reads_both_halves_and_falls_back_to_the_grand_latest() -> None:
    doc = _doc(
        {
            "latest": {"repositoryGuid": "g-grand", "credential": "c0"},
            "u1a": {"repositoryGuid": "g-a", "credential": "c1", "grandGuid": "g-explicit"},
            "u1b": {"repositoryGuid": "g-b", "credential": "c2"},
            "u1c": {"repositoryGuid": "g-c", "grandGuid": "g-explicit"},
            "u1d": {"repositoryGuid": "g-d", "credential": "c4"},
            "u1e": {"repositoryGuid": "g-e", "credential": "c5"},
        },
        {"u1a": 8512, "u1b": 8513, "u1c": 8514, "u1e": True},
    )
    assert u.fork_record(doc, "base", "u1a") == u.ForkRecord("g-a", 8512, "c1", "g-explicit")
    assert u.fork_record(doc, "base", "u1b") == u.ForkRecord("g-b", 8513, "c2", "g-grand")
    assert u.fork_record(doc, "base", "u1c") is None  # no credential
    assert u.fork_record(doc, "base", "u1d") is None  # no network id
    assert u.fork_record(doc, "base", "u1e") is None  # a bool is not a network id
    assert u.fork_record(doc, "other", "u1a") is None
    assert u.fork_record({}, "base", "u1a") is None


def test_config_files_include_the_cli_backup_copy(tmp_path: pathlib.Path) -> None:
    names = [p.name for p in u.config_files(tmp_path / "u1-x.json", "u1-x")]
    assert names == ["u1-x.json", "api-token-u1-x.json", "u1-x.json.bak"]


def _recorder(rows: list[tuple[str, bool]]) -> Callable[..., bool]:
    """A `check` callable with the drill's signature that records (desc, ok) and returns ok."""

    def check(desc: str, ok: bool, res: object = None, evidence: str = "") -> bool:
        del res, evidence
        rows.append((desc, ok))
        return ok

    return check


class _Res:
    def __init__(self, rc: int = 0, out: str = "", err: str = "") -> None:
        self.rc, self.out, self.err = rc, out, err


def test_bring_up_creates_on_the_current_renet_and_starts_on_the_old(
    tmp_path: pathlib.Path,
) -> None:
    """The order is the design: create and fork (no --up) while the symlink names the current build, then the old binary is installed and the forks are started by it, the credential on stdin only."""
    old_bin, new_bin = tmp_path / "renet-old", tmp_path / "renet-new"
    old_bin.write_bytes(b"old")
    new_bin.write_bytes(b"new")
    cfg = tmp_path / "u1.json"
    cfg.write_text(
        json.dumps(
            _doc(
                {
                    "latest": {"repositoryGuid": "g-grand"},
                    "a": {"repositoryGuid": "g-a", "credential": "SECRET-a"},
                    "b": {"repositoryGuid": "g-b", "credential": "SECRET-b"},
                },
                {"a": 8512, "b": 8513},
            )
        )
    )
    events: list[tuple[str, ...]] = []
    rows: list[tuple[str, bool]] = []
    old_sha = hashlib.sha256(b"old").hexdigest()

    def crdc(*args: str, **_kw: object) -> _Res:
        events.append(("rdc", *args))
        return _Res()

    def host_run(argv: list[str], **_kw: object) -> _Res:
        assert not any("SECRET-" in a for a in argv), argv
        if argv[:3] == ["bash", "-c", 'exec "$@" < "$0"']:
            events.append(("stdin", pathlib.Path(argv[3]).read_text().strip(), argv[-1]))
        else:
            events.append(("ssh", argv[-1]))
        return _Res(out="INSTALLED %s\n" % old_sha)

    ctx = type(
        "Ctx",
        (),
        {
            "machine": "ops-worker",
            "run_id": "vmc-1",
            "ssh_user": "u",
            "ssh_key": "k",
            "worker_ip": "1.2.3.4",
            "environ": {},
            "host_run": staticmethod(host_run),
        },
    )()
    bring = u.OldLayoutBringUp(
        ctx,
        step="U1",
        check=_recorder(rows),
        crdc=crdc,
        parent="base",
        tags=("a", "b"),
        config_path=cfg,
        point_symlink=lambda target: events.append(("symlink", target.name)),
        clear_provision_cache=lambda: events.append(("clear-cache",)),
        old_bin=old_bin,
        new_bin=new_bin,
        tmp=tmp_path,
    )
    assert bring.run(), rows
    assert all(ok for _d, ok in rows)
    kinds = [e[0] if e[0] != "rdc" else "rdc " + " ".join(e[1:3]) for e in events]
    assert kinds == [
        "symlink",
        "rdc repo create",
        "rdc repo fork",
        "rdc repo fork",
        "symlink",
        "clear-cache",
        "stdin",  # the binary upload
        "ssh",  # the install
        "stdin",  # fork a up
        "stdin",  # fork b up
    ]
    assert events[0] == ("symlink", "renet-new")
    assert events[4] == ("symlink", "renet-old")
    assert not any("--up" in e for e in events if e[0] == "rdc")
    assert events[6][1] == "old"
    assert events[8][1] == "SECRET-a"
    assert "--network-id 8512" in events[8][2]
    assert "--grand-guid g-grand" in events[8][2]
    assert events[9][1] == "SECRET-b"
    assert "--name g-b" in events[9][2]
    assert bring.created_grand
    assert bring.net_ids == {"a": 8512, "b": 8513}
    assert not list(tmp_path.glob("cred-*"))


def test_bring_up_stops_when_the_installed_sha_is_not_the_old_build(
    tmp_path: pathlib.Path,
) -> None:
    old_bin = tmp_path / "renet-old"
    old_bin.write_bytes(b"old")
    rows: list[tuple[str, bool]] = []
    ctx = type(
        "Ctx",
        (),
        {
            "run_id": "vmc-1",
            "ssh_user": "u",
            "ssh_key": "k",
            "worker_ip": "1.2.3.4",
            "environ": {},
            "host_run": staticmethod(lambda _argv, **_kw: _Res(out="INSTALLED %s\n" % SHA)),
        },
    )()
    bring = u.OldLayoutBringUp(
        ctx,
        step="U1",
        check=_recorder(rows),
        crdc=lambda *_a, **_k: _Res(),
        parent="base",
        tags=("a",),
        config_path=tmp_path / "missing.json",
        point_symlink=lambda _t: None,
        clear_provision_cache=lambda: None,
        old_bin=old_bin,
        new_bin=old_bin,
        tmp=tmp_path,
    )
    assert not bring._install_old()
    assert rows[-1] == ("the pre-isolation renet is the worker's current renet", False)


@pytest.mark.parametrize(
    "doc",
    [
        {"resources": None, "state": {"repos": {"base": {"u1a": {"networkId": 8512}}}}},
        {"resources": [], "state": {"repos": {"base": {"u1a": {"networkId": 8512}}}}},
        {"resources": "x", "state": {}},
    ],
)
def test_fork_record_is_none_for_a_null_or_non_dict_resources(doc: object) -> None:
    assert u.fork_record(doc, "base", "u1a") is None


@pytest.mark.parametrize("state", [None, [], "x", 3])
def test_fork_record_is_none_for_a_null_or_non_dict_state(state: object) -> None:
    doc = {
        "resources": {
            "repositories": {
                "base": {
                    "tags": {"u1a": {"repositoryGuid": "g-a", "credential": "c1", "grandGuid": "g"}}
                }
            }
        },
        "state": state,
    }
    assert u.fork_record(doc, "base", "u1a") is None


# --------------------------------------------------------------------------- PLAN-detached-jobs L1 step 5: the old renet refuses a job


MACHINE = "ops-worker"
HINT_ERR = (
    "renet on '%s' is older than this CLI and cannot run repo status as a job. "
    "Upgrade it: rdc machine setup %s\n" % (MACHINE, MACHINE)
)


def test_upgrade_hint_is_the_cli_refusal_line() -> None:
    assert u.upgrade_hint(MACHINE) == "Upgrade it: rdc machine setup ops-worker"
    # The row matches the CLI's own text (job-client.ts jobsUnsupportedMessage), so a reword there must turn this red.
    cli = pathlib.Path(__file__).resolve().parents[3] / (
        "packages/cli/src/services/executor/job-client.ts"
    )
    assert "`Upgrade it: rdc machine setup ${machineName}`" in cli.read_text()


@pytest.mark.parametrize(
    ("text", "want"),
    [
        ("SNAPSHOT-DONE\n", frozenset()),
        (
            "JOB j1\nUNIT rediacc-job-j1.service\nSNAPSHOT-DONE\n",
            frozenset({"JOB j1", "UNIT rediacc-job-j1.service"}),
        ),
        # No marker: the probe failed part-way, which is not "no job".
        ("JOB j1\n", None),
        ("", None),
        ("JOB a b\nnoise\nSNAPSHOT-DONE\n", frozenset()),
    ],
)
def test_parse_job_snapshot(text: str, want: frozenset[str] | None) -> None:
    assert u.parse_job_snapshot(text) == want


def _stub_systemctl(tmp_path: pathlib.Path, body: str) -> dict[str, str]:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    stub = bindir / "systemctl"
    stub.write_text("#!/bin/sh\n" + body)
    stub.chmod(0o755)
    return {**os.environ, "PATH": "%s:%s" % (bindir, os.environ.get("PATH", ""))}


def _snapshot_run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "-c", u.job_snapshot_script()], capture_output=True, text=True, env=env, check=False
    )


def test_job_snapshot_script_lists_spool_and_units(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spool = tmp_path / "jobs"
    monkeypatch.setattr(u, "JOBS_SPOOL_DIR", str(spool))
    env = _stub_systemctl(tmp_path, "echo 'rediacc-job-j2.service loaded active running x'\n")
    # No spool directory at all is an empty spool, not a failure.
    first = _snapshot_run(env)
    assert first.returncode == 0, first.stderr
    assert u.parse_job_snapshot(first.stdout) == frozenset({"UNIT rediacc-job-j2.service"})
    (spool / "j1").mkdir(parents=True)
    (spool / "stray-file").write_text("x")
    second = _snapshot_run(env)
    assert second.returncode == 0, second.stderr
    assert u.parse_job_snapshot(second.stdout) == frozenset(
        {"JOB j1", "UNIT rediacc-job-j2.service"}
    )


def test_job_snapshot_script_with_a_failing_systemctl_is_no_reading(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(u, "JOBS_SPOOL_DIR", str(tmp_path / "jobs"))
    out = _snapshot_run(_stub_systemctl(tmp_path, "exit 1\n"))
    assert out.returncode != 0
    assert u.parse_job_snapshot(out.stdout) is None


SNAP = frozenset({"JOB old-1"})


@pytest.mark.parametrize(
    ("rc", "output", "after", "ok"),
    [
        (1, HINT_ERR, SNAP, True),
        # Controls: a verb that ran (rc 0), another exit code, a refusal without the hint or naming another machine, a job left behind, an unread spool.
        (0, HINT_ERR, SNAP, False),
        (0, "", SNAP, False),
        (2, HINT_ERR, SNAP, False),
        (1, "Error: something else\n", SNAP, False),
        (1, HINT_ERR.replace(MACHINE, "other-vm"), SNAP, False),
        (1, HINT_ERR, SNAP | {"JOB new-2"}, False),
        (1, HINT_ERR, SNAP | {"UNIT rediacc-job-new-2.service"}, False),
        (1, HINT_ERR, None, False),
    ],
)
def test_old_renet_refusal_verdict(
    rc: int, output: str, after: frozenset[str] | None, ok: bool
) -> None:
    assert u.old_renet_refusal_verdict(rc, output, MACHINE, SNAP, after)[0] is ok


def test_old_renet_refusal_verdict_needs_a_before_reading() -> None:
    ok, evidence = u.old_renet_refusal_verdict(1, HINT_ERR, MACHINE, None, SNAP)
    assert not ok
    assert "unreadable" in evidence


def _live_u1(
    tmp_path: pathlib.Path, verb: _Res, snapshots: list[str]
) -> tuple[u._LiveU1, list[tuple[str, bool, str]], list[tuple[str, ...]]]:
    """A `_LiveU1` on a fake ctx: `rdc` answers `verb`, each ssh probe answers the next of `snapshots`."""
    rows: list[tuple[str, bool, str]] = []
    calls: list[tuple[str, ...]] = []
    probes = iter(snapshots)

    class Ctx:
        machine = MACHINE
        run_id = "vmc-1-abcdef"
        work = str(tmp_path)
        ssh_user, ssh_key, worker_ip = "u", "k", "1.2.3.4"

        def __init__(self) -> None:
            self.environ: dict[str, str] = {}
            self.sweep_leftovers: list[str] = []

        def rdc(self, *args: str, **_kw: object) -> _Res:
            calls.append(("rdc", *args))
            return verb

        def host_run(self, argv: list[str], **_kw: object) -> _Res:
            calls.append(("ssh", argv[-1]))
            return _Res(out=next(probes))

        def check(
            self, step: str, desc: str, ok: bool, res: object = None, evidence: str = ""
        ) -> bool:
            del step, res
            rows.append((desc, ok, evidence))
            return ok

    return u._LiveU1(Ctx()), rows, calls


def test_the_live_step_passes_on_a_refusal_that_ran_no_job(tmp_path: pathlib.Path) -> None:
    live, rows, calls = _live_u1(
        tmp_path, _Res(rc=1, err=HINT_ERR), ["JOB old-1\nSNAPSHOT-DONE\n"] * 2
    )
    live._old_renet_refuses_a_job()
    assert [ok for _d, ok, _e in rows] == [True], rows
    # Snapshot, the one verb on fork A, snapshot: in that order.
    assert [c[0] for c in calls] == ["ssh", "rdc", "ssh"]
    assert calls[1][1:] == ("repo", "status", "%s:u1a" % live.parent)
    assert "SNAPSHOT-DONE" in calls[0][1]


@pytest.mark.parametrize(
    ("verb", "snapshots"),
    [
        # Control: a verb that ran the job and exited 0.
        (_Res(rc=0, out="status ok\n"), ["SNAPSHOT-DONE\n", "JOB j9\nSNAPSHOT-DONE\n"]),
        # Control: a verb that exited 0 and left nothing behind is still red.
        (_Res(rc=0, out="status ok\n"), ["SNAPSHOT-DONE\n", "SNAPSHOT-DONE\n"]),
        # Control: rc 1 with the hint, but a job appeared on the worker.
        (_Res(rc=1, err=HINT_ERR), ["SNAPSHOT-DONE\n", "JOB j9\nSNAPSHOT-DONE\n"]),
        # Control: the refusal is right, but the after-snapshot never completed.
        (_Res(rc=1, err=HINT_ERR), ["SNAPSHOT-DONE\n", "JOB j9\n"]),
    ],
)
def test_the_live_step_is_red_when_a_job_ran_or_exit_is_zero(
    tmp_path: pathlib.Path, verb: _Res, snapshots: list[str]
) -> None:
    live, rows, _calls = _live_u1(tmp_path, verb, snapshots)
    live._old_renet_refuses_a_job()
    assert [ok for _d, ok, _e in rows] == [False], rows


def test_the_refusal_row_runs_between_the_old_layout_rows_and_the_upgrade() -> None:
    src = inspect.getsource(u._LiveU1.execute)
    assert (
        src.index("_old_layout_before_upgrade()")
        < src.index("_old_renet_refuses_a_job()")
        < src.index("self._upgrade()")
    )
