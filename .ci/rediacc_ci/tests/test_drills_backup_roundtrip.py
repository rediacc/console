"""`rediacc_ci.drills.backup_roundtrip`, the port of `programs/backup-storage/local-roundtrip.sh`.

THE BASH WAS RETIRED WITH THIS FILE (PLAN-retire-bash-oracles B5, W10). The proof itself needs the worker VM at 192.168.111.11, docker on the host and a renet built from this tree, so it is run by an operator (`docs/backup-storage/09-local-roundtrip-proof.md`); nothing here claims to have run it. What is pinned is the logic the verdict rests on, against a scripted VM and a scripted account API: the order of the steps, that the comparison is a comparison (a mismatch and a control that fails to fire both fail the run), that every failure still reaches the teardown, that the token never appears in a VM command, and that the exit status cannot wrap to zero. Each deliberate delta (Rule T) has a case that fails on the bash behaviour.
"""

from __future__ import annotations

import http.server
import json
import re
import stat
import subprocess
import threading
from typing import TYPE_CHECKING, ClassVar

import pytest

from rediacc_ci import well_known
from rediacc_ci.drills import backup_roundtrip as rt
from rediacc_ci.drills import vm_ssh

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator

BEARER = "tok-SECRET-1234"
SNAP_OK = '{"status":"stored","snapshotId":"S1","bytesUploaded":4242}'


class FakeVm:
    """A scripted worker VM: answers by the command text and keeps every command it was sent."""

    def __init__(
        self,
        src_sha: str = "aaa",
        tgt_sha: str = "aaa",
        cmp_rc: int = 0,
        control_rc: int = 1,
        snapshot_out: str = SNAP_OK,
        restore_out: str = '{"status":"restored","passphraseCheck":"opened"}',
        fail_containing: str = "",
        enforce_license: bool = True,
    ) -> None:
        self.src_sha = src_sha
        self.tgt_sha = tgt_sha
        self.cmp_rc = cmp_rc
        self.control_rc = control_rc
        self.snapshot_out = snapshot_out
        self.restore_out = restore_out
        self.fail_containing = fail_containing
        # An enforcing renet: `repository create` is refused for a guid with no installed licence (cmd/renet/repository_create.go, validateCreateSizeLimit).
        self.enforce_license = enforce_license
        self.licensed: set[str] = set()
        self.commands: list[str] = []
        self.stdins: list[str | None] = []
        self.created: list[str] = []

    def __call__(self, command: str, stdin_data: str | None = None) -> rt.VmResult:
        self.commands.append(command)
        self.stdins.append(stdin_data)
        if self.fail_containing and self.fail_containing in command:
            return rt.VmResult(1, "", "boom")
        installed = re.search(
            r"cp /tmp/rt-lic\.json /var/lib/rediacc/license/repos/([^/\s]+)/", command
        )
        if installed:
            self.licensed.add(installed.group(1))
        made = re.search(r"repository create --name (\S+)", command)
        if made:
            if self.enforce_license and made.group(1) not in self.licensed:
                return rt.VmResult(
                    1, "", "license required: no installed licence for this repository"
                )
            self.created.append(made.group(1))
        if "renet machine-id" in command:
            return rt.VmResult(0, "mid-1\r\n")
        if "license-status" in command:
            rows = [{"repositoryGuid": g, "status": "valid"} for g in self.created]
            return rt.VmResult(0, json.dumps(rows))
        if "sha256sum" in command:
            sha = self.src_sha if self.created and self.created[0] in command else self.tgt_sha
            return rt.VmResult(0, "%s  %s/repositories/x\n" % (sha, well_known.DATASTORE_PATH))
        if "backup snapshot" in command:
            return rt.VmResult(0, self.snapshot_out)
        if "backup restore" in command:
            if (stdin_data or "").startswith("not-"):
                return rt.VmResult(1, '{"status":"failed","passphraseCheck":"refused"}')
            return rt.VmResult(0, self.restore_out)
        if "test -e" in command:
            return rt.VmResult(1)
        if "cmp -s" in command:
            return rt.VmResult(self.control_rc)
        if "sudo -n cmp " in command:
            return rt.VmResult(self.cmp_rc)
        return rt.VmResult(0)


class FakeApi(rt.Api):
    """A scripted account API."""

    def __init__(self, fail_path: str = "") -> None:
        super().__init__("http://127.0.0.1:1")
        self.fail_path = fail_path
        self.calls: list[tuple[str, str, dict | None]] = []

    def call(self, method: str, path: str, body: dict | None = None, *_ignored: object) -> dict:
        self.calls.append((method, path, body))
        if self.fail_path and path == self.fail_path:
            raise rt.StepError("%s %s -> HTTP 500" % (method, path))
        if path == "/test/ensure-subscription":
            return {"subscriptionId": "sub-1"}
        if path == "/api-tokens":
            return {"token": BEARER}
        if path == "/licenses/activate-repo":
            return {"license": {"publicKeyId": "kid-1", "blob": "x"}}
        if path == "/backups/manifests":
            return {"manifests": [{"snapshotId": "S1"}]}
        if path == "/backups/usage":
            return {"storedBytes": 4242}
        return {}


@pytest.fixture(autouse=True)
def _machine_id(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ident = tmp_path / "machine-id"
    ident.write_text("client-1\n", encoding="utf-8")
    monkeypatch.setattr(rt, "CLIENT_MACHINE_ID", ident)


def _run(
    tmp_path: pathlib.Path, vm: FakeVm, api: FakeApi | None = None
) -> tuple[int, str, FakeApi]:
    lines: list[str] = []
    api = api or FakeApi()
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    rc = rt.Roundtrip(vm, api, work, say=lines.append).run()
    return rc, "\n".join(lines), api


def test_a_clean_run_passes_and_tears_down_both_repos(tmp_path: pathlib.Path) -> None:
    vm = FakeVm()
    rc, out, api = _run(tmp_path, vm)
    assert rc == 0, out
    assert "ROUND TRIP PASSED" in out
    for label in (
        "source repo licence is valid",
        "snapshot stored",
        "manifest index carries the snapshot",
        "quota ledger equals bytes uploaded",
        "wrong passphrase: refused",
        "wrong passphrase: places nothing",
        "restore completed",
        "the image opens",
        "restored image is byte-identical to the source",
        "cmp reports the two images identical",
        "control fired",
    ):
        assert label in out, label
    assert "FAIL" not in out
    assert len(vm.created) == 1
    src = vm.created[0]
    deletes = [c for c in vm.commands if "repository delete" in c]
    assert len(deletes) == 2
    assert any(src in c for c in deletes)
    assert vm.commands[-1] == "rm -f /tmp/rt_pass.txt"
    licences = [b or {} for _m, p, b in api.calls if p == "/licenses/activate-repo"]
    assert [b["kind"] for b in licences] == ["grand", "fork"]
    assert licences[1]["grandGuid"] == src
    assert licences[1]["repositoryGuid"] != src


def test_steps_run_in_order(tmp_path: pathlib.Path) -> None:
    _, out, _ = _run(tmp_path, FakeVm())
    titles = re.findall(r"=== (\d)\. ", out)
    assert titles == list("123456789")


def test_a_byte_mismatch_fails_the_run(tmp_path: pathlib.Path) -> None:
    rc, out, _ = _run(tmp_path, FakeVm(tgt_sha="bbb", cmp_rc=1))
    assert rc == 2
    assert "FAIL  restored image is byte-identical" in out
    assert "FAIL  cmp reports the two images differ" in out
    assert "ROUND TRIP FAILED (2)" in out


def test_a_control_that_does_not_fire_fails_the_run(tmp_path: pathlib.Path) -> None:
    """A comparison that cannot fail is not evidence: the mutated image must be seen to differ."""
    rc, out, _ = _run(tmp_path, FakeVm(control_rc=0))
    assert rc == 1
    assert "FAIL  control did NOT fire" in out


def test_a_failed_snapshot_is_a_verdict_and_still_tears_down(tmp_path: pathlib.Path) -> None:
    """Rule T: the bash died on the unparseable output with a traceback and skipped the teardown."""
    vm = FakeVm(snapshot_out="renet: no space left on device")
    rc, out, _ = _run(tmp_path, vm)
    assert rc >= 1
    assert "FAIL  snapshot stored" in out
    assert "unparseable" in out
    assert "Traceback" not in out
    assert any("repository delete" in c for c in vm.commands)
    assert not any("backup restore" in c for c in vm.commands)


def test_a_failed_restore_stops_before_the_comparison(tmp_path: pathlib.Path) -> None:
    vm = FakeVm(restore_out='{"status":"failed"}')
    rc, out, _ = _run(tmp_path, vm)
    assert rc >= 1
    assert "FAIL  restore completed" in out
    assert "BYTE COMPARISON" not in out
    assert sum("repository delete" in c for c in vm.commands) == 2


def test_a_vm_command_that_fails_mid_run_still_reaches_the_teardown(
    tmp_path: pathlib.Path,
) -> None:
    """Rule T: under `set -e` the bash left the repo, its licence and the passphrase file on the VM."""
    vm = FakeVm(fail_containing="repository create")
    rc, out, _ = _run(tmp_path, vm)
    assert rc == 1
    assert "VM command failed" in out
    assert vm.commands[-1] == "rm -f /tmp/rt_pass.txt"
    assert any("rm -rf /var/lib/rediacc/license/repos/" in c for c in vm.commands)


def test_an_api_failure_before_any_repo_exists_removes_nothing(tmp_path: pathlib.Path) -> None:
    vm = FakeVm()
    rc, out, _ = _run(tmp_path, vm, FakeApi(fail_path="/auth/login"))
    assert rc == 1
    assert "HTTP 500" in out
    assert "nothing to remove" in out
    assert not any("repository delete" in c for c in vm.commands)


def test_the_token_never_reaches_a_vm_command_or_stdin(tmp_path: pathlib.Path) -> None:
    """Rule T: the bash put the bearer token on a curl command line."""
    vm = FakeVm()
    rc, _, api = _run(tmp_path, vm)
    assert rc == 0
    assert api.token == BEARER
    assert all(BEARER not in c for c in vm.commands)
    assert all(BEARER not in (s or "") for s in vm.stdins)


def test_the_licence_file_is_private(tmp_path: pathlib.Path) -> None:
    """Rule T: the bash left lic.json world-readable."""
    _run(tmp_path, FakeVm())
    work = tmp_path / "work"
    for name in ("lic.json", "luks.txt"):
        assert stat.S_IMODE((work / name).stat().st_mode) == 0o600, name


def test_the_exit_status_cannot_wrap_to_zero(tmp_path: pathlib.Path) -> None:
    """Rule T: `exit "$FAILURES"` reads 256 failures as success."""

    class Many(rt.Roundtrip):
        def _prove(self) -> None:
            self.failures = 256

    rc = Many(FakeVm(), FakeApi(), tmp_path, say=lambda _line: None).run()
    assert rc == 255


def test_remote_commands_name_the_planted_content_and_the_one_byte_mutation(
    tmp_path: pathlib.Path,
) -> None:
    vm = FakeVm()
    _run(tmp_path, vm)
    planted = next(c for c in vm.commands if "payload.bin" in c)
    assert "head -c 8388608 /dev/urandom" in planted
    assert "nested content 1234567890" in planted
    mutation = next(c for c in vm.commands if "seek=1048576" in c)
    assert "conv=notrunc" in mutation
    assert any("--cell-bytes 65536" in c for c in vm.commands)
    assert any("--network-id 2880" in c for c in vm.commands)


# ---------------------------------------------------------------------------- the real HTTP client


class _Handler(http.server.BaseHTTPRequestHandler):
    seen: ClassVar[list[dict[str, str]]] = []

    def log_message(self, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        self._reply()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self._reply()

    def _reply(self) -> None:
        type(self).seen.append(dict(self.headers.items()) | {"path": self.path})
        if self.path.endswith("/boom"):
            self.send_response(500)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Set-Cookie", "sid=abc123; Path=/; HttpOnly")
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true, "token": "t"}')


@pytest.fixture
def server() -> Iterator[http.server.HTTPServer]:
    _Handler.seen = []
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


def test_api_keeps_the_login_cookie_and_sends_the_bearer_token_in_a_header(
    server: http.server.HTTPServer,
) -> None:
    api = rt.Api("http://127.0.0.1:%d" % server.server_address[1])
    assert api.call("POST", "/auth/login", {"a": 1}) == {"ok": True, "token": "t"}
    api.token = BEARER
    api.call("GET", "/backups/usage")
    first, second = _Handler.seen
    assert first["path"] == "/account/api/v1/auth/login"
    assert "Cookie" not in first
    assert second["Cookie"] == "sid=abc123"
    assert second["Authorization"] == "Bearer " + BEARER


def test_api_http_errors_and_health(server: http.server.HTTPServer) -> None:
    api = rt.Api("http://127.0.0.1:%d" % server.server_address[1])
    with pytest.raises(rt.StepError, match="HTTP 500"):
        api.call("GET", "/boom")
    assert api.healthy() is True
    dead = rt.Api("http://127.0.0.1:1")
    assert dead.healthy() is False
    with pytest.raises(rt.StepError):
        dead.call("GET", "/anything")


# ---------------------------------------------------------------------------- the U0 live-run defects


def test_the_source_licence_is_installed_before_the_repo_is_created(tmp_path: pathlib.Path) -> None:
    """Rule T: the bash ran `repository create` (local-roundtrip.sh:126) before installing the grand licence (:133), which an enforcing renet refuses; the scripted VM enforces, so the old order fails the run."""
    vm = FakeVm()
    rc, out, _ = _run(tmp_path, vm)
    assert rc == 0, out
    src = vm.created[0]
    install = next(i for i, c in enumerate(vm.commands) if "license/repos/%s/" % src in c)
    create = next(i for i, c in enumerate(vm.commands) if "repository create" in c)
    assert install < create


def test_an_enforcing_vm_refuses_a_create_without_a_licence() -> None:
    """The scripted refusal itself: a create with nothing installed fails, so the ordering test above can go red."""
    vm = FakeVm()
    assert vm("sudo -n sh -c 'renet repository create --name g1 --size 1G'").returncode == 1
    vm("sudo -n mkdir -p x && sudo -n cp /tmp/rt-lic.json /var/lib/rediacc/license/repos/g1/k.json")
    assert vm("sudo -n sh -c 'renet repository create --name g1 --size 1G'").returncode == 0


def test_ssh_goes_as_the_provisioned_user_with_exactly_the_staged_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bash ssh'd to a hardcoded `muhammed@` with no identity; the fleet provisions $USER and authorizes only the renet-staged id_rsa."""
    env = {"USER": "alice", "HOME": "/home/alice"}
    assert vm_ssh.default_user(env) == "alice"
    assert vm_ssh.default_key(env) == "/home/alice/.renet/staging/.ssh/id_rsa"
    env_rd = env | {"RENET_DATA_DIR": "/data/renet"}
    assert vm_ssh.default_key(env_rd) == "/data/renet/staging/.ssh/id_rsa"
    assert vm_ssh.default_user(env | {"SSH_USER": "bob"}) == "bob"
    assert vm_ssh.default_key(env | {"SSH_KEY": "/k"}) == "/k"

    seen: list[list[str]] = []

    def fake_run(argv: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, "out", "")

    monkeypatch.setattr(rt.subprocess, "run", fake_run)
    result = rt.ssh_vm("alice", "/k/id_rsa", "192.168.111.11", "true")
    assert result.returncode == 0
    argv = seen[0]
    assert "alice@192.168.111.11" in argv
    assert not any("muhammed" in a for a in argv)
    assert argv[argv.index("-i") + 1] == "/k/id_rsa"
    for opt in ("IdentitiesOnly=yes", "IdentityAgent=none", "BatchMode=yes"):
        assert opt in argv, opt
    assert argv[argv.index("-F") + 1] == "/dev/null"


def test_an_ssh_failure_is_not_reported_as_renet_missing() -> None:
    """The bash preflight read every non-zero exit, an auth refusal (255) included, as "renet missing on <vm>"."""
    denied = rt.preflight_vm(
        lambda _c, _s: rt.VmResult(255, "", "alice@192.168.111.11: Permission denied (publickey)."),
        "192.168.111.11",
        "alice",
        "/k/id_rsa",
    )
    assert "renet missing" not in denied
    assert "cannot ssh to 192.168.111.11 as alice with /k/id_rsa" in denied
    assert "Permission denied (publickey)" in denied
    missing = rt.preflight_vm(lambda _c, _s: rt.VmResult(1), "192.168.111.11", "alice", "/k")
    assert missing.startswith("renet missing on 192.168.111.11")
    assert rt.preflight_vm(lambda _c, _s: rt.VmResult(0), "h", "u", "k") == ""
