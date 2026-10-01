"""`rediacc_ci.drills.backup` and `rediacc_ci.drills.license` against their bash twins.

DIFFERENTIALS run the real `scripts/drills/backup.sh` and `license.sh` and the ports through the same arguments in a scratch repo root (a FAKE `rdc.sh` that answers `ops status`, a fake `ssh` on PATH) and compare exit status and the refusal text: selftest, argument errors, the leg registry, the disposable-store guard, and the license preflight refusals (VM absent, second machine absent, Ceph absent, agent override missing). The fixture image and the manifest builder are compared byte for byte with the node code the bash generated at run time, and the in-process SigV4 signer with `curl --aws-sigv4`. A stub control plane and store on loopback drive the byte-moving halves (`upload_cells`, `put_manifest`, `restore_snapshot`) with binary bodies.

`test_delta_*` cases pin a Rule T difference from the bash and say what the bash did. The live runs against the dev gateway, RustFS and the ops fleet are the acceptance and are recorded by the lead.
"""

from __future__ import annotations

import datetime
import hashlib
import http.cookiejar
import http.server
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.core import run_verbs
from rediacc_ci.drills import backup, lib, wire
from rediacc_ci.drills import license as license_drill

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
RESTORE_TOKEN = "rbs_" + "restore"
MARKER = "sentinel"
BASH = shutil.which("bash") or "/bin/bash"
NODE = shutil.which("node") or ""
CURL = shutil.which("curl") or ""

FAKE_RDC = """#!{py}
import os, sys

if sys.argv[1:3] == ["ops", "status"]:
    sys.stdout.write(os.environ["FAKE_OPS_STATUS"])
    sys.exit(0)
sys.stderr.write("fake rdc: unhandled %s\\\\n" % sys.argv[1:])
sys.exit(64)
"""


def _status(*ips: str, absent: tuple[str, ...] = ()) -> str:
    vms = [{"ip": ip, "status": "running"} for ip in ips]
    vms += [{"ip": ip, "status": "absent"} for ip in absent]
    return json.dumps({"success": True, "data": {"vms": vms}})


@pytest.fixture
def root(tmp_path: pathlib.Path) -> pathlib.Path:
    scratch = tmp_path / "root"
    for rel in (
        "scripts/drills/lib.sh",
        "scripts/drills/backup.sh",
        "scripts/drills/license.sh",
        ".ci/scripts/lib/common.sh",
        ".ci/config/well-known.env",
    ):
        dest = scratch / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
    rdc = scratch / "rdc.sh"
    rdc.write_text(FAKE_RDC.format(py=sys.executable))
    rdc.chmod(rdc.stat().st_mode | stat.S_IEXEC)
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    ssh = fakebin / "ssh"
    ssh.write_text("#!/bin/sh\nexit 0\n")
    ssh.chmod(ssh.stat().st_mode | stat.S_IEXEC)
    (scratch / "key").write_text("not a key\n")
    return scratch


def _env(root: pathlib.Path, **extra: str) -> dict[str, str]:
    env = {
        "PATH": str(root.parent / "fakebin") + os.pathsep + os.environ.get("PATH", ""),
        "HOME": str(root),
        "LC_ALL": "C",
        "TMPDIR": str(root),
        "PYTHONPATH": str(ROOT / ".ci"),
        "REDIACC_CI_ROOT": str(root),
        "USER": "tester",
        "NO_COLOR": "1",
    }
    env.update(extra)
    return env


def _bash(root: pathlib.Path, script: str, args: list[str], env: dict[str, str]):
    proc = subprocess.run(
        [BASH, str(root / "scripts/drills" / ("%s.sh" % script)), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(root),
        check=False,
        timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _port(root: pathlib.Path, script: str, args: list[str], env: dict[str, str]):
    proc = subprocess.run(
        [sys.executable, "-m", "rediacc_ci.drills.%s" % script, *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(root),
        check=False,
        timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _norm(text: str) -> str:
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    text = re.sub(r"/[^\s]*rediacc-drill-[A-Za-z0-9_-]+", "<WORK>", text)
    text = re.sub(r"\(\d+s\)", "(Ns)", text)
    # The tools line differs on purpose (Rule T 1/2: the port needs neither curl nor node).
    text = re.sub(r"   curl [^\n]*\n", "   <TOOLS>\n", text)
    return re.sub(r"   python [^\n]*\n", "   <TOOLS>\n", text)


# ---------------------------------------------------------------------- differentials against the bash


@pytest.mark.parametrize("drill", ["backup", "license"])
def test_selftest_matches_bash(root: pathlib.Path, drill: str) -> None:
    env = _env(root)
    b = _bash(root, drill, ["--selftest"], env)
    p = _port(root, drill, ["--selftest"], env)
    assert b[0] == p[0] == 1
    assert _norm(b[1]) == _norm(p[1])
    assert _norm(b[2]) == _norm(p[2])
    assert "selftest fired as designed" in p[1]


@pytest.mark.parametrize("drill", ["backup", "license"])
def test_an_unknown_option_exits_2_in_both(root: pathlib.Path, drill: str) -> None:
    env = _env(root)
    b = _bash(root, drill, ["--bogus"], env)
    p = _port(root, drill, ["--bogus"], env)
    assert b[0] == p[0] == 2
    assert _norm(b[2]) == _norm(p[2])
    assert "Unknown option: --bogus" in p[2]


@pytest.mark.parametrize("legs", ["a,jj", "z", ","])
def test_an_unknown_or_empty_leg_list_is_refused_in_both(root: pathlib.Path, legs: str) -> None:
    env = _env(root)
    b = _bash(root, "backup", ["--legs", legs, "--selftest"], env)
    p = _port(root, "backup", ["--legs", legs, "--selftest"], env)
    assert b[0] == p[0] == 1
    assert _norm(b[2]) == _norm(p[2])
    assert "Unknown leg" in p[2] or "empty list" in p[2]


def test_delta_an_empty_leg_item_is_refused_by_name(root: pathlib.Path) -> None:
    """The bash split `a,,b` with `${LEGS//,/ }`, dropped the empty item and ran `a,b`; a typo that narrows the battery must be refused."""
    env = _env(root)
    b = _bash(root, "backup", ["--legs", "a,,b", "--selftest"], env)
    p = _port(root, "backup", ["--legs", "a,,b", "--selftest"], env)
    assert "selftest fired as designed" in b[1]
    assert "Unknown leg" not in b[2]
    assert p[0] == 1
    assert "Unknown leg ''" in p[2]


@pytest.mark.parametrize(
    "bucket",
    ["rediacc-backups", "prod-data", "my-probe-bucket"],
)
def test_the_disposable_store_guard_matches_bash(root: pathlib.Path, bucket: str) -> None:
    env = _env(root, DRILL_STORE_ENDPOINT="http://store.invalid", DRILL_STORE_BUCKET=bucket)
    b = _bash(root, "backup", ["--selftest"], env)
    p = _port(root, "backup", ["--selftest"], env)
    assert b[0] == p[0] == 1
    assert _norm(b[2]) == _norm(p[2])
    assert ("fired as designed" in p[1]) == (bucket == "my-probe-bucket")


@pytest.mark.parametrize(
    ("running", "legs", "needle"),
    [
        ((".1",), "c", "Worker VM 192.168.111.11 is not running"),
        ((".1", ".11"), "b", "needs a SECOND machine at 192.168.111.12"),
        ((".1", ".11", ".12"), "a,b", "needs Ceph, and 192.168.111.21 is not running"),
    ],
)
def test_the_license_vm_preflight_refusals_match_bash(
    root: pathlib.Path, running: tuple[str, ...], legs: str, needle: str
) -> None:
    status = _status(*("192.168.111%s" % s for s in running))
    env = _env(root, FAKE_OPS_STATUS=status)
    args = ["--legs", legs, "--ssh-key", str(root / "key")]
    b = _bash(root, "license", args, env)
    p = _port(root, "license", args, env)
    assert b[0] == p[0] == 1
    assert _norm(b[1]) == _norm(p[1])
    assert _norm(b[2]) == _norm(p[2])
    assert needle in p[2]


def test_the_license_agent_override_refusal_matches_bash(root: pathlib.Path) -> None:
    status = _status("192.168.111.1", "192.168.111.11", "192.168.111.12", "192.168.111.21")
    env = _env(root, FAKE_OPS_STATUS=status, CLAUDECODE="1")
    args = ["--legs", "a,b", "--ssh-key", str(root / "key")]
    b = _bash(root, "license", args, env)
    p = _port(root, "license", args, env)
    assert b[0] == p[0] == 1
    assert _norm(b[1]) == _norm(p[1])
    assert _norm(b[2]) == _norm(p[2])
    assert "REDIACC_ALLOW_CLUSTER_OPS=*" in p[2]
    assert "REDIACC_ALLOW_GRAND_REPO=*" in p[2]


def test_the_license_ssh_preflight_names_the_key(root: pathlib.Path) -> None:
    status = _status("192.168.111.1", "192.168.111.11")
    failing = root.parent / "fakebin" / "ssh"
    failing.write_text("#!/bin/sh\nexit 255\n")
    env = _env(root, FAKE_OPS_STATUS=status)
    args = ["--legs", "c", "--ssh-key", str(root / "key")]
    b = _bash(root, "license", args, env)
    p = _port(root, "license", args, env)
    assert b[0] == p[0] == 1
    assert _norm(b[2]) == _norm(p[2])
    assert "Cannot authenticate to 192.168.111.11" in p[2]


# ---------------------------------------------------------------------- the fixture image and manifests


def _node_image_helper(tmp_path: pathlib.Path) -> pathlib.Path:
    text = (ROOT / "scripts/drills/backup.sh").read_text()
    match = re.search(r"<<'IMAGE_JS'\n(.*?)\nIMAGE_JS\n", text, re.DOTALL)
    assert match
    helper = tmp_path / "image.js"
    helper.write_text(match.group(1))
    return helper


@pytest.mark.skipif(not NODE, reason="needs node for the bash twin's image helper")
@pytest.mark.parametrize("version", ["1", "2"])
def test_the_fixture_image_and_plan_match_the_node_helper(
    tmp_path: pathlib.Path, version: str
) -> None:
    helper = _node_image_helper(tmp_path)
    theirs = tmp_path / "node.bin"
    ours = tmp_path / "py.bin"
    subprocess.run([NODE, str(helper), "make", str(theirs), version], check=True)
    backup.make_image(ours, version)
    assert theirs.read_bytes() == ours.read_bytes()
    node_plan = subprocess.run(
        [NODE, str(helper), "plan", str(theirs)], capture_output=True, text=True, check=True
    ).stdout
    assert wire.compact(backup.plan_of(ours)) == node_plan
    assert (
        backup.sha256_hex(ours.read_bytes())
        == subprocess.run(
            [NODE, str(helper), "sha", str(theirs)], capture_output=True, text=True, check=True
        ).stdout
    )
    node_slice = tmp_path / "slice.bin"
    subprocess.run([NODE, str(helper), "slice", str(theirs), "3", str(node_slice)], check=True)
    assert node_slice.read_bytes() == backup.slice_cell(ours, 3)


@pytest.mark.skipif(not NODE, reason="needs node for the bash twin's manifest builder")
def test_manifests_match_the_node_builder(tmp_path: pathlib.Path) -> None:
    text = (ROOT / "scripts/drills/backup.sh").read_text()
    match = re.search(
        r"manifest_body\(\) \{.*?node -e '\n(.*?)\n    ' \"\$snapshot\"", text, re.DOTALL
    )
    assert match
    script = match.group(1)
    seed, incr = tmp_path / "v1.bin", tmp_path / "v2.bin"
    backup.make_image(seed, "1")
    backup.make_image(incr, "2")
    seed_plan, incr_plan = backup.plan_of(seed), backup.plan_of(incr)
    lineage = "11111111-2222-3333-4444-555555555555"

    def node(snapshot: str, plan: dict, parent: str, parent_plan: dict | None) -> str:
        return subprocess.run(
            [
                NODE,
                "-e",
                script,
                snapshot,
                json.dumps(plan),
                parent,
                json.dumps(parent_plan) if parent_plan else "",
                lineage,
                str(backup.CELL_BYTES),
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    def strip(raw: str) -> dict:
        data = json.loads(raw)
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", data.pop("createdAt"))
        return data

    full_ours = backup.manifest_body("s1", seed_plan, lineage)
    full_theirs = node("s1", seed_plan, "", None)
    assert strip(full_ours) == strip(full_theirs)
    assert list(json.loads(full_ours)) == list(json.loads(full_theirs))
    delta_ours = backup.manifest_body("s2", incr_plan, lineage, "s1", seed_plan)
    delta_theirs = node("s2", incr_plan, "s1", seed_plan)
    assert strip(delta_ours) == strip(delta_theirs)
    assert list(json.loads(delta_ours)) == list(json.loads(delta_theirs))
    assert json.loads(delta_ours)["changedCells"] == {"3": incr_plan["cells"][3]}


@pytest.mark.skipif(not NODE, reason="needs node for String(v)")
def test_jstr_and_typeof_match_the_node_expressions() -> None:
    values = [None, True, False, 0, 7, 1.5, "x", "", [], [1, "a"], {"a": 1}]
    script = (
        "const v = JSON.parse(process.argv[1]); "
        "process.stdout.write(JSON.stringify(v.map(x => [x === null ? '' : String(x) === '[object Object]' "
        "? JSON.stringify(x) : (Array.isArray(x) ? JSON.stringify(x) : String(x)), typeof x])));"
    )
    out = json.loads(
        subprocess.run(
            [NODE, "-e", script, json.dumps(values)], capture_output=True, text=True, check=True
        ).stdout
    )
    for value, (text, kind) in zip(values, out, strict=True):
        assert wire.jstr(value) == text
        expected_kind = "object" if value is None or isinstance(value, (list, dict)) else kind
        assert wire.typeof(value) == expected_kind
    assert wire.typeof(wire.MISSING) == "undefined"
    assert wire.jstr(wire.MISSING) == ""


@pytest.mark.skipif(not CURL, reason="needs curl for --aws-sigv4")
def test_the_sigv4_signer_matches_curl() -> None:
    seen: dict[str, str] = {}

    class Capture(http.server.BaseHTTPRequestHandler):
        def do_PUT(self) -> None:
            seen.update({k.lower(): v for k, v in self.headers.items()})
            seen["path"] = self.path
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *_a: object) -> None:
            return

    server = http.server.HTTPServer(("127.0.0.1", 0), Capture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d/rediacc-backups" % server.server_address[1]
    try:
        subprocess.run(
            [
                CURL,
                "-sS",
                "--aws-sigv4",
                "aws:amz:us-east-1:s3",
                "-u",
                "key:secret",
                "-X",
                "PUT",
                "-o",
                "/dev/null",
                url,
            ],
            check=True,
        )
    finally:
        server.shutdown()
        server.server_close()
    when = datetime.datetime.strptime(seen["x-amz-date"], "%Y%m%dT%H%M%SZ").replace(
        tzinfo=datetime.UTC
    )
    ours = wire.sigv4_headers("PUT", url, b"", "us-east-1", "key", "secret", now=when)
    assert ours["Authorization"] == seen["authorization"]
    assert ours["x-amz-content-sha256"] == seen["x-amz-content-sha256"]


# ---------------------------------------------------------------------- a stub control plane and store


class Stub:
    """Serves what `upload_cells`, `put_manifest` and `restore_snapshot` touch, with BINARY bodies."""

    def __init__(self, image: pathlib.Path, snapshots: dict[str, list[str]]) -> None:
        self.puts: list[tuple[str, dict[str, str], bytes]] = []
        self.objects: dict[str, bytes] = {}
        self.snapshots = snapshots
        self.chunks = {
            backup.sha256_hex(backup.slice_cell(image, i)): backup.slice_cell(image, i)
            for i in range(backup.CELLS)
        }
        stub = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _reply(self, payload: bytes, code: int = 200) -> None:
                self.send_response(code)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_PUT(self) -> None:
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                stub.puts.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
                self._reply(b"")

            def do_GET(self) -> None:
                if self.path.startswith("/m/"):
                    self._reply(stub.objects[self.path[3:]]) if self.path[
                        3:
                    ] in stub.objects else self._reply(b"", 404)
                elif self.path.startswith("/c/"):
                    self._reply(stub.chunks[self.path[3:]])
                else:
                    self._reply(b"{}")

            def do_POST(self) -> None:
                body = json.loads(
                    self.rfile.read(int(self.headers.get("Content-Length") or 0)) or "{}"
                )
                base = "http://127.0.0.1:%d" % stub.port
                snap = body.get("snapshotId", "")
                if self.path.endswith("/read-grants"):
                    chain = stub.snapshots[snap]
                    reply: dict = {
                        "manifestChain": chain,
                        "manifestGetUrls": {c: "%s/m/%s" % (base, c) for c in chain},
                    }
                    if body.get("hashes"):
                        reply["getUrls"] = {h: "%s/c/%s" % (base, h) for h in body["hashes"]}
                    self._reply(json.dumps(reply).encode())
                else:
                    self._reply(b"{}")

            def log_message(self, *_a: object) -> None:
                return

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def drill_root(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    scratch = tmp_path / "droot"
    scratch.mkdir()
    monkeypatch.setenv("REDIACC_CI_ROOT", str(scratch))
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    return scratch


def _backup(drill_root: pathlib.Path, port: int) -> backup.Backup:
    (drill_root / ".account-state").write_text("gateway_port=%d\nstarted=1\n" % port)
    drill = backup.BackupDrill("backup", selftest=False, keep_work=False)
    drill.init()
    subject = backup.Backup(drill, backup.Options())
    subject.restore_session_token = RESTORE_TOKEN
    subject.lineage = "11111111-2222-3333-4444-555555555555"
    return subject


def test_a_restore_reassembles_the_snapshot_byte_for_byte(
    tmp_path: pathlib.Path, drill_root: pathlib.Path
) -> None:
    seed, incr = tmp_path / "v1.bin", tmp_path / "v2.bin"
    backup.make_image(seed, "1")
    backup.make_image(incr, "2")
    stub = Stub(seed, {"s1": ["s1"], "s2": ["s1", "s2"]})
    for path in (seed, incr):
        for i in range(backup.CELLS):
            stub.chunks[backup.sha256_hex(backup.slice_cell(path, i))] = backup.slice_cell(path, i)
    lineage = "11111111-2222-3333-4444-555555555555"
    stub.objects["s1"] = backup.manifest_body("s1", backup.plan_of(seed), lineage).encode()
    stub.objects["s2"] = backup.manifest_body(
        "s2", backup.plan_of(incr), lineage, "s1", backup.plan_of(seed)
    ).encode()
    subject = _backup(drill_root, stub.port)
    try:
        out1, out2 = tmp_path / "r1.bin", tmp_path / "r2.bin"
        assert subject.restore_snapshot("s1", out1) is True
        assert subject.restore_snapshot("s2", out2) is True
        assert out1.read_bytes() == seed.read_bytes()
        assert out2.read_bytes() == incr.read_bytes()
        assert out1.read_bytes() != out2.read_bytes()
    finally:
        stub.close()
        subject.d.teardown()


def test_a_restore_without_a_chain_reports_failure_not_an_image(
    tmp_path: pathlib.Path, drill_root: pathlib.Path
) -> None:
    seed = tmp_path / "v1.bin"
    backup.make_image(seed, "1")
    stub = Stub(seed, {"s1": []})
    subject = _backup(drill_root, stub.port)
    try:
        assert subject.restore_snapshot("s1", tmp_path / "r.bin") is False
        assert not (tmp_path / "r.bin").exists()
    finally:
        stub.close()
        subject.d.teardown()


def test_uploads_send_the_presigned_put_headers_and_the_exact_cell_bytes(
    tmp_path: pathlib.Path, drill_root: pathlib.Path
) -> None:
    image = tmp_path / "v1.bin"
    backup.make_image(image, "1")
    plan = backup.plan_of(image)
    stub = Stub(image, {})
    subject = _backup(drill_root, stub.port)
    base = "http://127.0.0.1:%d" % stub.port
    try:
        subject.grant = {
            "grant": {
                "putUrls": {
                    h: "%s/c/%s?X-Amz-Signature=x" % (base, h) for h in plan["unique"][:-1]
                },
                "manifestPutUrl": "%s/m/s1" % base,
            }
        }
        failures = subject.upload_cells(plan, image, plan["unique"])
        assert failures == 1, "the hash with no URL counts as a failure and is not skipped"
        assert len(stub.puts) == len(plan["unique"]) - 1
        for path, headers, body in stub.puts:
            assert headers["if-none-match"] == "*"
            assert hashlib.sha256(body).hexdigest() == path.split("/c/")[1].split("?")[0]
            assert len(body) == backup.CELL_BYTES
        assert subject.put_manifest("s1", '{"x":1}') == "200"
        assert stub.puts[-1][2] == b'{"x":1}'
        assert stub.puts[-1][1]["if-none-match"] == "*"
    finally:
        stub.close()
        subject.d.teardown()


# ---------------------------------------------------------------------- Rule T deltas and unit cases


def test_running_ips_reads_both_status_shapes_and_ignores_absent_vms() -> None:
    enveloped = _status("192.168.111.1", "192.168.111.11", absent=("192.168.111.12",))
    bare = json.dumps(
        {"vms": [{"ip": "10.0.0.1", "status": "running"}, {"ip": "10.0.0.2", "status": "absent"}]}
    )
    assert (
        backup.running_ips(enveloped)
        == license_drill.running_ips(enveloped)
        == [
            "192.168.111.1",
            "192.168.111.11",
        ]
    )
    assert backup.running_ips(bare) == license_drill.running_ips(bare) == ["10.0.0.1"]
    assert license_drill.running_ips("not json") == []


@pytest.mark.skipif(not NODE, reason="needs node for the bash expression")
def test_delta_the_max_sequence_of_no_results_is_zero() -> None:
    """The bash evaluated `Math.max(...d.results.map(...))`, which is -Infinity for an empty list and then passed `assert_not_equal 0`."""
    theirs = subprocess.run(
        [NODE, "-e", "process.stdout.write(String(Math.max(...[].map(r => r.newSequence || 0))))"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert theirs == "-Infinity"
    assert license_drill.renewed_sequence([]) == 0
    assert license_drill.renewed_sequence(None) == 0
    assert (
        license_drill.renewed_sequence([{"newSequence": 4}, {"newSequence": None}, {"x": 1}]) == 4
    )


@pytest.mark.usefixtures("drill_root")
def test_delta_the_gateway_does_not_inherit_the_sandbox_and_the_store_env_reaches_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bash exported `XDG_CONFIG_HOME` (and the rest of the sandbox) into its own environment before restarting the gateway, so the gateway's secret loader searched the throwaway home for its token; the chunk-store variables reached it only by the same inheritance."""
    monkeypatch.setenv("BWS_ACCESS_TOKEN", MARKER)
    drill = backup.BackupDrill("backup", selftest=False, keep_work=False)
    drill.init()
    subject = backup.Backup(drill, backup.Options())
    try:
        subject.setup_sandbox()
        subject.setup_store_env()
        gateway = drill.gateway_env()
        cli = drill.cli_env()
        assert "XDG_CONFIG_HOME" not in gateway
        assert "REDIACC_CONFIG" not in gateway
        assert cli["XDG_CONFIG_HOME"].endswith("/xdg")
        assert cli["REDIACC_CONFIG"] == "drill-backup"
        assert gateway["BWS_ACCESS_TOKEN"] == MARKER
        assert gateway["ACCOUNT_BACKUP_S3_BUCKET"] == "rediacc-backups"
        assert gateway["BACKUP_MAINTENANCE_INTERVAL_MS"] == "0"
        assert "ACCOUNT_BACKUP_S3_BUCKET" not in cli
    finally:
        drill.teardown()
    other = lib.Drill("license", selftest=False, keep_work=False)
    other.init()
    try:
        lic = license_drill.License(other, license_drill.Options())
        lic.setup_sandbox()
        assert "XDG_CONFIG_HOME" not in other.gateway_env()
        assert "RDC_RENET_LICENSE" not in other.gateway_env()
        assert other.cli_env()["RDC_RENET_LICENSE"] == "1"
    finally:
        other.teardown()


class _Patcher(lib.Drill):
    def account_patch_subscription(self, *_args: object) -> str:  # type: ignore[override]
        raise OSError("connection refused")


@pytest.mark.usefixtures("drill_root")
def test_delta_a_failed_subscription_restore_is_reported(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The bash teardown ran the restoring PUT as `... >/dev/null 2>&1 || true`, so a drill that left the subscription suspended or capped at 1 said nothing."""
    drill = _Patcher("license", selftest=False, keep_work=False)
    drill.init()
    try:
        lic = license_drill.License(drill, license_drill.Options())
        lic.admin_jar, lic.subscription_id, lic.subscription_lapsed = (
            http.cookiejar.CookieJar(),
            "sub",
            True,
        )
        lic.teardown_hook()
        err = capsys.readouterr().err
        assert "restoring the subscription" in err
        assert "connection refused" in err
        sub = backup.Backup(backup.BackupDrill("backup"), backup.Options())
        sub.d = _Patcher("backup")  # type: ignore[assignment]
        sub.admin_jar, sub.subscription_id, sub.quota_lowered = (
            http.cookiejar.CookieJar(),
            "sub",
            True,
        )
        sub.teardown_hook()
        assert "restoring the subscription" in capsys.readouterr().err
    finally:
        drill.teardown()


def test_the_leg_f_planted_strip_control_fails_on_a_server_that_strips() -> None:
    """Leg f's control is a computed check, so it must see the field gone from a body that lacks it and present in one that has it."""
    body = {"license": {"payload": "p", "signature": "s", "chainHash": "h"}}
    assert wire.typeof(wire.lookup(body, "license.chainHash")) == "string"
    del body["license"]["chainHash"]
    assert wire.typeof(wire.lookup(body, "license.chainHash")) == "undefined"


class _FakeLicense(license_drill.License):
    """A License whose HTTP and ssh edges answer from fixed text."""

    status_text = "{}"
    activate_text = ""

    def license_status(self) -> str:
        return self.status_text

    def activate_repo_for(self, machine_id: str) -> str:  # noqa: ARG002
        return self.activate_text

    def ssh_out(self, host: str, command: str, stdin: str | None = None) -> tuple[int, str]:  # noqa: ARG002
        return 0, "own-id\n"


@pytest.mark.usefixtures("drill_root")
@pytest.mark.parametrize(
    "refusal",
    [
        '{"error":"Maximum machines (3) reached.","code":"MAX_MACHINES_REACHED"}',
        "",
        "<html>502</html>",
    ],
)
def test_leg_f_reports_a_refused_activation_as_failed_assertions_not_a_crash(refusal: str) -> None:
    """2026-10-01: the bash leg f died with a raw `TypeError` on `delete d.license.chainHash` when activate-repo answered a refusal; the port must record failures and carry on."""
    drill = lib.Drill("license", selftest=False, keep_work=False)
    drill.init()
    try:
        lic = _FakeLicense(drill, license_drill.Options())
        lic.setup_sandbox()
        lic.activate_text = refusal
        lic.leg_f_dto_boundary()
        assert drill.failures >= 3
    finally:
        drill.teardown()


@pytest.mark.usefixtures("drill_root")
@pytest.mark.parametrize(
    ("machines", "passes"),
    [
        ([{"machineId": "own-id"}], True),
        ([{"machineId": "own-id"}, {"machineId": "drifted-id"}], False),
        ([], False),
    ],
)
def test_the_meter_baseline_names_a_phantom_machine(machines: list[dict], passes: bool) -> None:
    """The starting meter is exactly the machine under test; a second id on a fresh subscription fails the leg where the cause is visible."""
    drill = lib.Drill("license", selftest=False, keep_work=False)
    drill.init()
    try:
        lic = _FakeLicense(drill, license_drill.Options())
        lic.status_text = wire.compact({"machines": machines})
        assert lic.claimed_machine_ids() == sorted(m["machineId"] for m in machines)
        lic.assert_meter_baseline()
        assert (drill.failures == 0) is passes
    finally:
        drill.teardown()


def test_the_preclean_script_is_valid_bash_and_names_the_drill_datastores() -> None:
    script = license_drill.preclean_script("renet")
    assert subprocess.run([BASH, "-n"], input=script, text=True, check=False).returncode == 0
    assert "drill-ds:remeter drill-ds" in script
    assert '"${ds%:*}"' in script or "${ds%%:*}" in script


FAKE_PRECLEAN_RENET = """#!{py}
import json, os, sys

args = " ".join(sys.argv[1:])
with open(os.environ["FAKE_RENET_LOG"], "a") as log:
    log.write(args + "\\n")
rc, out, err = json.loads(os.environ["FAKE_RENET_SCENARIO"]).get(args, [0, "", ""])
sys.stdout.write(out)
sys.stderr.write(err)
sys.exit(rc)
"""

# `sudo rm -rf /var/lib/rediacc/license/...` must never run on the test host: the fake sudo swallows rm and runs everything else as the calling user.
FAKE_PRECLEAN_SUDO = """#!/bin/sh
if [ "$1" = rm ]; then echo "$*" >> "$FAKE_RENET_LOG"; exit 0; fi
exec "$@"
"""

NOT_REGISTERED = 'Error: datastore "%s" is not registered on this machine\n'


def _run_preclean(tmp_path: pathlib.Path, scenario: dict[str, list]) -> tuple[int, str, list[str]]:
    """Run the port's remote script under bash against a fake renet; (exit, stderr, renet calls)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    renet = bin_dir / "renet"
    renet.write_text(FAKE_PRECLEAN_RENET.format(py=sys.executable))
    sudo = bin_dir / "sudo"
    sudo.write_text(FAKE_PRECLEAN_SUDO)
    for exe in (renet, sudo):
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    log_file = tmp_path / "calls.log"
    log_file.write_text("")
    env = dict(os.environ)
    env["PATH"] = "%s:%s" % (bin_dir, env.get("PATH", ""))
    env["FAKE_RENET_LOG"] = str(log_file)
    env["FAKE_RENET_SCENARIO"] = json.dumps(scenario)
    proc = subprocess.run(
        [BASH, "-s"],
        input=license_drill.preclean_script(str(renet)),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    calls = [c for c in log_file.read_text().splitlines() if not c.startswith("rm ")]
    return proc.returncode, proc.stderr, calls


def test_preclean_on_a_fresh_machine_is_silent_and_clean(tmp_path: pathlib.Path) -> None:
    code, err, calls = _run_preclean(tmp_path, {"datastore list --json": [0, "[]", ""]})
    assert (code, err) == (0, "")
    assert calls == ["datastore list --json"]


def test_preclean_reports_a_failed_delete_with_renets_own_words(tmp_path: pathlib.Path) -> None:
    """The 2026-10-01 shape: a VM crash left drill-ds registered and held detached, so the delete is the step that fails; its cause used to go to /dev/null and the next create said only "already exists"."""
    listing = [
        {
            "name": "drill-ds",
            "state": "detached",
            "heldDetached": True,
            "mountPath": "/mnt/rediacc-ds/drill-ds",
        }
    ]
    code, err, calls = _run_preclean(
        tmp_path,
        {
            "datastore list --json": [0, json.dumps(listing), ""],
            "datastore delete --name drill-ds": [
                1,
                "",
                "Error: rbd: error removing image: image still has watchers\n",
            ],
        },
    )
    assert code == 1
    assert (
        "PRECLEAN FAILED: sudo %s datastore delete --name drill-ds (rc=1)"
        % (tmp_path / "bin" / "renet")
        in err
    )
    assert "image still has watchers" in err
    assert "datastore detach --name drill-ds" not in calls, (
        "a detached parent is not detached again"
    )
    assert calls[-1] == "datastore delete --name drill-ds"


def test_preclean_keeps_not_registered_quiet(tmp_path: pathlib.Path) -> None:
    listing = [
        {
            "name": "drill-ds:remeter",
            "state": "detached",
            "mountPath": "/mnt/rediacc-ds/drill-ds-remeter",
        }
    ]
    code, err, calls = _run_preclean(
        tmp_path,
        {
            "datastore list --json": [0, json.dumps(listing), ""],
            "datastore detach --name drill-ds:remeter --discard": [
                1,
                "",
                NOT_REGISTERED % "drill-ds:remeter",
            ],
        },
    )
    assert (code, err) == (0, "")
    assert "datastore detach --name drill-ds:remeter --discard" in calls


def test_preclean_unmounts_only_mounted_repos_with_their_listed_network_id(
    tmp_path: pathlib.Path,
) -> None:
    mount = "/mnt/rediacc-ds/drill-ds"
    listing = [{"name": "drill-ds", "state": "attached", "mountPath": mount}]
    repos = [
        {"name": ".lock-g1", "size": "0 B", "mounted": False},
        {"name": "g1", "network_id": 2816, "mounted": True},
        {"name": "g2", "network_id": 2880, "mounted": False},
    ]
    code, err, calls = _run_preclean(
        tmp_path,
        {
            "datastore list --json": [0, json.dumps(listing), ""],
            "repository list --datastore %s --json" % mount: [
                0,
                json.dumps(repos),
                "a warning on stderr\n",
            ],
        },
    )
    assert (code, err) == (0, "")
    unmounts = [c for c in calls if c.startswith("repository unmount")]
    assert unmounts == [
        "repository unmount --name g1 --network-id 2816 --datastore %s --stop-docker --force"
        % mount
    ]
    assert calls[-2:] == ["datastore detach --name drill-ds", "datastore delete --name drill-ds"]


def test_preclean_stops_and_says_so_when_the_datastore_list_fails(tmp_path: pathlib.Path) -> None:
    code, err, calls = _run_preclean(
        tmp_path, {"datastore list --json": [2, "", "renet: registry locked by pid 4242\n"]}
    )
    assert code == 1
    assert "PRECLEAN FAILED: datastore list --json (rc=2)" in err
    assert "registry locked by pid 4242" in err
    assert calls == ["datastore list --json"]


@pytest.mark.usefixtures("drill_root")
@pytest.mark.parametrize(
    ("code", "stderr", "warned"),
    [(0, "", False), (1, "PRECLEAN FAILED: x (rc=1)\n    boom\n", True), (255, "", True)],
)
def test_a_failed_preclean_is_warned_with_its_lines(
    capsys: pytest.CaptureFixture[str], code: int, stderr: str, warned: bool
) -> None:
    drill = lib.Drill("license", selftest=False, keep_work=False)
    drill.init()
    try:
        _FakeLicense(drill, license_drill.Options()).report_preclean("192.168.111.11", code, stderr)
    finally:
        drill.teardown()
    err = capsys.readouterr().err
    assert ("pre-clean on 192.168.111.11 did not finish clean (exit %d)" % code in err) is warned
    if stderr:
        assert "boom" in err
    if warned and not stderr:
        assert "<no stderr" in err


def test_the_bash_preclean_heredoc_equals_the_ports_script() -> None:
    """The remote script is the one thing both sides send over ssh; the port's text must equal the bash heredoc once the shell escapes are undone."""
    text = (ROOT / "scripts/drills/license.sh").read_text()
    match = re.search(r'bash -s" <<EOF\n(.*?)\nEOF\n', text, re.DOTALL)
    assert match
    heredoc = match.group(1)
    # Skip the leading commentary, then undo the unquoted-heredoc escapes the way the shell would.
    lines = heredoc.splitlines(keepends=True)
    while lines and lines[0].startswith("#"):
        lines.pop(0)
    body = "".join(lines)
    expanded = (
        body.replace("\\\\\n", "\\\n")
        .replace("\\`", "`")
        .replace("\\$", "$")
        .replace("${DATASTORE_NAME}", "drill-ds")
        .replace("${FORK_TAG}", "remeter")
        .replace("${VM_RENET}", "renet")
    )
    ours = license_drill.preclean_script("renet")
    squash = lambda s: re.sub(r"\s+", " ", s.replace("%%", "%")).strip()  # noqa: E731
    assert squash(expanded) == squash(ours)


def test_the_run_verbs_route_license_and_backup_to_the_ports() -> None:
    assert run_verbs.DRILL_MODULES["license"] == "rediacc_ci.drills.license"
    assert run_verbs.DRILL_MODULES["backup"] == "rediacc_ci.drills.backup"
    assert set(run_verbs.DRILLS) == {"license", "backup"}, "the bash twins stay named until B3"
    assert list(run_verbs.DRILL_ARMS) == ["universe", "transfer", "license", "backup"]
