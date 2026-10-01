"""`rediacc_ci.drills.universe` and `rediacc_ci.drills.transfer` against their bash twins.

The universe drill's live phases are driven with a FAKE `rdc.sh` that emulates the few `rdc config` / `rdc subscription` behaviours the assertions read (file effects under a sandbox `XDG_CONFIG_HOME`, source labels, selection precedence, per-config token files) and a stub account gateway on loopback, so the CI-runnable differential covers the drill's own logic: the same fake and the same stub serve the bash and the port, and the assertion tables must match. The real-gateway runs are the acceptance and are recorded by the lead.

The transfer drill is compared on `--selftest`, the declared keyring skip, argument errors and the constant it pins to the CLI's exit-code table. Its live phases need a real config store (RustFS) and an OS keyring and are not faked here.
"""

from __future__ import annotations

import http.server
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys
import time
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.drills import transfer
from rediacc_ci.tests import differential as diff

ROOT = paths.repo_root()
BASH = shutil.which("bash") or "/bin/bash"

FAKE_RDC = """#!{py}
import json, os, sys

argv = sys.argv[1:]
cfg_flag = None
fmt = None
rest = []
i = 0
while i < len(argv):
    if argv[i] == "--config":
        cfg_flag = argv[i + 1]; i += 2; continue
    if argv[i] == "-o":
        fmt = argv[i + 1]; i += 2; continue
    rest.append(argv[i]); i += 1
home = os.environ["XDG_CONFIG_HOME"]
cdir = os.path.join(home, "rediacc")
os.makedirs(cdir, exist_ok=True)
name = cfg_flag or os.environ.get("REDIACC_CONFIG") or "rediacc"
path = os.path.join(cdir, name + ".json")
tok = os.path.join(cdir, "api-token-" + name + ".json")

def emit(data, ok=True):
    sys.stdout.write(json.dumps({{"success": ok, "data": data}}))

if rest[:2] == ["config", "current"]:
    created = not os.path.exists(path)
    if created:
        open(path, "w").write(json.dumps({{"id": os.urandom(4).hex()}}))
    cfg = json.load(open(path))
    env_server = os.environ.get("REDIACC_ACCOUNT_SERVER")
    if env_server:
        server, source = env_server, "env REDIACC_ACCOUNT_SERVER"
    elif cfg.get("accountServer"):
        server, source = cfg["accountServer"], "config"
    else:
        server, source = "https://account.example.invalid", "default"
    emit({{"name": name, "fileExists": True, "accountServer": server, "accountServerSource": source,
          "updateChannelSource": "default", "tokenState": "ready" if os.path.exists(tok) else "missing",
          "tokenFile": tok}})
elif rest[:2] == ["config", "init"]:
    target = os.path.join(cdir, rest[2] + ".json")
    if os.path.exists(target):
        if fmt == "json":
            sys.stdout.write(json.dumps({{"success": False, "errors": [{{"code": "VALIDATION_ERROR"}}]}}))
        else:
            sys.stderr.write('Error: config "%s" already exists\\\\n' % rest[2])
        sys.exit(2)
    server = rest[rest.index("--server") + 1]
    open(target, "w").write(json.dumps({{"id": os.urandom(4).hex(), "accountServer": server}}))
    sys.stderr.write('Config "%s" initialized\\\\n' % rest[2])
elif rest[:3] == ["config", "ssh", "set"]:
    cfg = json.load(open(path))
    cfg["ssh"] = open(rest[rest.index("--key") + 1]).read()[:40]
    open(path, "w").write(json.dumps(cfg))
elif rest[:2] == ["subscription", "login"]:
    server = rest[rest.index("--server") + 1]
    open(tok, "w").write(json.dumps({{"serverUrl": server}}))
    cfg = json.load(open(path))
    cfg["identity"] = os.urandom(4).hex()
    open(path, "w").write(json.dumps(cfg))
elif rest[:2] == ["subscription", "logout"]:
    os.path.exists(tok) and os.unlink(tok)
else:
    sys.stderr.write("fake rdc: unhandled %s\\\\n" % rest)
    sys.exit(64)
"""


class _Gateway(http.server.BaseHTTPRequestHandler):
    def _reply(self, payload: dict, cookie: str | None = None) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(200)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._reply({"ok": True})
        elif self.path.endswith("/portal/subscription"):
            self._reply({"id": "sub-1"})
        else:
            self._reply({})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        if self.path.endswith("/auth/login"):
            self._reply({"user": {"id": "u1"}}, "session=abc; Path=/")
        elif self.path.endswith("/api-tokens"):
            self._reply({"token": "rdt_faketoken123456"})
        else:
            self._reply({"ok": True})

    def log_message(self, *_args: object) -> None:
        return


def serve_stub() -> None:
    """Entry point of the stub gateway child process: prints its port, then serves until killed."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Gateway)
    print(server.server_address[1], flush=True)
    server.serve_forever()


class World:
    """A scratch repo root and a stub gateway in a CHILD process: a drill's teardown may SIGKILL whatever listens on the gateway port, and that must never be the pytest process."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self.stub: subprocess.Popen | None = None

    def start_gateway(self) -> int:
        self.stop_gateway()
        self.stub = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "from rediacc_ci.tests import test_drills_universe_transfer as t; t.serve_stub()",
            ],
            stdout=subprocess.PIPE,
            env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT / ".ci")},
            text=True,
        )
        assert self.stub.stdout is not None
        port = int(self.stub.stdout.readline())
        (self.root / ".account-state").write_text(
            "gateway_port=%d\nstarted=%d\n" % (port, int(time.time()))
        )
        return port

    def gateway_alive(self) -> bool:
        return self.stub is not None and self.stub.poll() is None

    def stop_gateway(self) -> None:
        if self.stub is not None:
            if self.stub.poll() is None:
                self.stub.kill()
            self.stub.wait()
            if self.stub.stdout:
                self.stub.stdout.close()
            self.stub = None


@pytest.fixture
def world(tmp_path: pathlib.Path) -> typing.Iterator[World]:
    """A scratch repo root holding the fake rdc.sh (and, only for a re-freeze from bash, the drills' bash twins)."""
    root = tmp_path / "root"
    for rel in (
        "scripts/drills/lib.sh",
        "scripts/drills/universe.sh",
        "scripts/drills/transfer.sh",
        ".ci/scripts/lib/common.sh",
        ".ci/config/well-known.env",
        ".ci/config/well-known.generated.sh",
    ):
        if not (ROOT / rel).is_file():  # a retired twin: only a re-freeze from bash needs it
            continue
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
    rdc = root / "rdc.sh"
    rdc.write_text(FAKE_RDC.format(py=sys.executable))
    rdc.chmod(rdc.stat().st_mode | stat.S_IEXEC)
    scratch = World(root)
    scratch.start_gateway()
    yield scratch
    scratch.stop_gateway()


def _env(world: World, **extra: str) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(world.root),
        "LC_ALL": "C",
        "TMPDIR": str(world.root),
        "PYTHONPATH": str(ROOT / ".ci"),
        "REDIACC_CI_ROOT": str(world.root),
    }
    env.update(extra)
    return env


def _env_key(env: dict[str, str], work: pathlib.Path) -> list[str]:
    """The environment as a key: machine-specific PATH entries are named, not spelled (the sealed one holds the tmp dir and the interpreter's directory)."""
    rows = []
    for k in sorted(env):
        v = env[k]
        if k == "PATH":
            v = "sealed" if str(work) in v else "inherited"
        rows.append("%s=%s" % (k, v))
    return rows


def _bash(world: World, script: str, args: list[str], env: dict[str, str]) -> tuple[int, str, str]:
    """The retired twin's run of `scripts/drills/<script>`, from `goldens/twins/scripts.drills.<name>.jsonl` (PLAN-retire-bash-oracles B3).

    Besides the streams the golden holds whether the twin left the stub gateway alive (its teardown SIGKILLs whatever listens on the gateway port), replayed here by stopping the stub. The key is the argv, the environment, and the fake `rdc.sh` text.
    """
    twin = "scripts/drills/%s" % script

    def go() -> tuple[int, str, str]:
        proc = subprocess.run(
            [BASH, str(world.root / "scripts/drills" / script), *args],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(world.root),
            check=False,
            timeout=120,
        )
        return proc.returncode, proc.stdout, proc.stderr

    rdc_text = (world.root / "rdc.sh").read_text().replace(sys.executable, "<PY>")
    rc, out, err, got = diff.twin_run(
        twin,
        ["args=%r" % (args,), "env=%r" % (_env_key(env, world.root.parent),), "rdc=%s" % rdc_text],
        go,
        extras={"gateway": lambda: "1" if world.gateway_alive() else "0"},
        work=(str(world.root.parent),),
    )
    if diff.regolden_mode(twin) is None and got["gateway"] == "0":
        world.stop_gateway()
    return rc, out, err


def _port(module: str, args: list[str], env: dict[str, str], world: World) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "rediacc_ci.drills.%s" % module, *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(world.root),
        check=False,
        timeout=120,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _norm(text: str) -> str:
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    text = re.sub(r"/[^\s]*rediacc-drill-[A-Za-z0-9_-]+", "<WORK>", text)
    text = re.sub(r"\(\d+s\)", "(Ns)", text)
    text = re.sub(r"after \d+s", "after Ns", text)
    text = re.sub(r"127\.0\.0\.1:\d+", "127.0.0.1:<PORT>", text)
    text = re.sub(r"port \d+", "port <PORT>", text)
    text = re.sub(r"md5 drill-a=\w+ drill-b=\w+", "md5 <HASHES>", text)
    return re.sub(r"subscription \S+, token \S+", "<SUB>", text)


def test_universe_live_phases_match_bash_against_the_fake_rdc(world: World) -> None:
    env = _env(world)
    b = _bash(world, "universe.sh", ["--no-restart"], env)
    world.start_gateway()
    p = _port("universe", ["--no-restart"], env, world)
    assert b[0] == p[0] == 0, (b[2][-400:], p[2][-400:])
    assert _norm(b[1]) == _norm(p[1])
    assert _norm(b[2]) == _norm(p[2])
    assert "42 assertions: 42 passed, 0 failed" in p[1]
    assert "drill universe PASSED" in p[1]


def test_universe_phase_failures_are_reported_the_same(world: World) -> None:
    # A fake that mislabels the env override breaks exactly one assertion in both implementations.
    rdc = world.root / "rdc.sh"
    rdc.write_text(rdc.read_text().replace('"env REDIACC_ACCOUNT_SERVER"', '"config"'))
    env = _env(world)
    b = _bash(world, "universe.sh", ["--no-restart"], env)
    world.start_gateway()
    p = _port("universe", ["--no-restart"], env, world)
    assert b[0] == p[0] == 1
    assert _norm(b[1]) == _norm(p[1])
    assert "REDIACC_ACCOUNT_SERVER overrides the config file and is labelled as env" in p[2]
    assert "41 passed, 1 failed" in p[1]


@pytest.mark.parametrize("drill", ["universe", "transfer"])
def test_selftest_matches_bash(world: World, drill: str) -> None:
    env = _env(world)
    b = _bash(world, "%s.sh" % drill, ["--selftest"], env)
    p = _port(drill, ["--selftest"], env, world)
    assert b[0] == p[0] == 1
    assert _norm(b[1]) == _norm(p[1])
    assert _norm(b[2]) == _norm(p[2])
    assert "selftest fired as designed" in p[1]


@pytest.mark.parametrize("drill", ["universe", "transfer"])
def test_an_unknown_option_exits_2_in_both(world: World, drill: str) -> None:
    env = _env(world)
    b = _bash(world, "%s.sh" % drill, ["--bogus"], env)
    p = _port(drill, ["--bogus"], env, world)
    assert b[0] == p[0] == 2
    assert _norm(b[2]) == _norm(p[2])
    assert "Unknown option: --bogus" in p[2]


def _sealed_path(tmp_path: pathlib.Path) -> str:
    """A PATH holding the tools the drills need and NO `keyctl`."""
    bindir = tmp_path / "sealed-bin"
    bindir.mkdir()
    for tool in (
        "bash",
        "date",
        "mktemp",
        "rm",
        "mkdir",
        "cat",
        "sed",
        "cut",
        "tail",
        "ssh-keygen",
        "md5sum",
        "dirname",
        "env",
        "node",
        "grep",
        "head",
        "tr",
        "uname",
    ):
        real = shutil.which(tool)
        if real:
            (bindir / tool).symlink_to(real)
    return str(bindir)


def test_the_keyring_preflight_matches_bash(world: World, tmp_path: pathlib.Path) -> None:
    path = _sealed_path(tmp_path)
    undeclared = _env(world, PATH=path + os.pathsep + str(pathlib.Path(sys.executable).parent))
    b = _bash(world, "transfer.sh", [], undeclared)
    p = _port("transfer", [], undeclared, world)
    assert b[0] == p[0] == 1
    assert _norm(b[2]) == _norm(p[2])
    assert "No usable OS keyring" in p[2]
    declared = _env(
        world,
        PATH=path + os.pathsep + str(pathlib.Path(sys.executable).parent),
        DRILL_EXPECT_NO_KEYRING="runner has no keyring",
    )
    b = _bash(world, "transfer.sh", [], declared)
    p = _port("transfer", [], declared, world)
    assert b[0] == p[0] == 0
    assert _norm(b[1]) == _norm(p[1])
    assert _norm(b[2]) == _norm(p[2])
    assert "drill transfer SKIPPED" in p[1]
    assert "SKIPPED BY DECLARATION" in p[2]


def test_delta_the_offline_write_exit_is_the_clis_network_exit_code() -> None:
    cli_types = (ROOT / "packages/cli/src/types/index.ts").read_text()
    match = re.search(r"NETWORK_ERROR:\s*(\d+)", cli_types)
    assert match, "the CLI's EXIT_CODES table no longer names NETWORK_ERROR"
    assert int(match.group(1)) == transfer.OFFLINE_WRITE_EXIT
    # The control: the bash twin hard-codes exit 1 for the same assertion, which the live CLI contradicts. Frozen with the twin: whether its text carried that line.

    def read_twin() -> tuple[int, str, str]:
        text = (ROOT / "scripts/drills/transfer.sh").read_text()
        return 0, "1" if 'assert_exit 1 "the write fails (exit 1)"' in text else "0", ""

    carried = diff.twin_call("scripts/drills/transfer.sh", ["hard-codes exit 1"], read_twin)[1]
    assert carried == "1"


def test_delta_a_reused_gateway_survives_the_drill(world: World) -> None:
    env = _env(world)
    _bash(world, "universe.sh", ["--no-restart"], env)
    assert (
        not world.gateway_alive()
    )  # the control: the bash teardown SIGKILLed the gateway it was told to reuse
    world.start_gateway()
    p = _port("universe", ["--no-restart"], env, world)
    assert p[0] == 0
    assert world.gateway_alive()
