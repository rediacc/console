"""The executor proxy's container image builds, boots, and can reach a machine's renet.

WHY. `workers/proxy/Dockerfile` is built only by `wrangler deploy`, and nothing in CI ever ran that image. Two blockers shipped in it unnoticed (agent/plans/PLAN-cloudflare-proxy.md section 1.3):

  B1  `rdc serve` exits at boot without REDIACC_TOKEN, and the Worker never passed it, so every
      container start died. The Worker half is tested in workers/proxy; this gate proves the
      IMAGE stays up once it has the token, and dies without it.
  B2  the image shipped no renet binary. Outside a SEA the CLI runs the renet on PATH, so every
      machine command would have failed with "Renet binary not found".

WHAT IT DOES. `docker build -f workers/proxy/Dockerfile .` from the repo root (the context wrangler uses: `image_build_context = "../.."`), then, on a private docker network:

  1. a fake account server, run with the image's own node, answering `/proxy/introspect`;
  2. the executor, from the image's own CMD, with REDIACC_TOKEN and REDIACC_ACCOUNT_SERVER set
     exactly as the Worker's `executorEnv` sets them.

and asserts: the process is still running after boot; `/v1/health` answers 200; `/v1/server-info` answers 200 with `mode: "container"` and a `cliVersion` equal to the shipped renet's version; `POST /v1/session` with a caller token answers 200 after the executor introspected it with ITS OWN token; `renet version` runs inside the image. Every HTTP probe runs from inside the network (`docker exec` into the fake account's container), so nothing depends on host port publishing.

THE CONTROL THAT MAKES "STAYS UP" MEAN SOMETHING. The same image is also started WITHOUT REDIACC_TOKEN, and the gate requires that one to exit non-zero naming the variable. A "still running" check that could not tell those two apart would be vacuous.

WHAT IT SHIPS. The Dockerfile builds nothing: it copies `workers/proxy/stage/` (bundle, renet, natives, manifest) and checks every sha256 against the manifest. The gate stages that directory through `rediacc_ci.deploy.executor_artifacts stage-local` (the tree's `packages/cli/dist/cli-bundle.cjs`, `private/bin/renet-linux-amd64` and the lockfile-pinned natives of `node_modules`) and removes it afterwards, unless a manifest was already staged. A tree without those build outputs is exit 2: no verdict.

SLOW. Staging and the image build (no npm, no compile; the layers are the base, apt and a 200 MB renet) take a minute or two, so the gate is `slow: true` in the manifest and runs in CI only in `.github/workflows/ci-build-renet.yml` job `proxy-image-smoke`, after the renet build, with that build's renet-linux-amd64 downloaded into private/bin/ for the stage (and the CLI bundle and natives stage-local reads present beside it).

Exit 0 clean, 1 on findings, 2 when the gate's own controls fail or it cannot reach a verdict (docker absent, nothing to stage).
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import typing
import urllib.request

from rediacc_ci import paths
from rediacc_ci.controls import controls_first
from rediacc_ci.core import https
from rediacc_ci.deploy import executor_artifacts

if typing.TYPE_CHECKING:
    import pathlib

DOCKERFILE = ("workers", "proxy", "Dockerfile")
STAGE_DIR = ("workers", "proxy", "stage")

EXECUTOR_TOKEN = "rdt_image_smoke_executor"
CALLER_TOKEN = "rdt_image_smoke_caller"
ACCOUNT_PORT = 9000
EXECUTOR_PORT = 8080

BUILD_TIMEOUT_S = 1800
BOOT_TIMEOUT_S = 90
STAY_UP_S = 5

# The fake account server, run by the IMAGE's node: it answers introspection for the caller and for the executor's own token, and logs every Authorization header it saw so the gate can prove the executor used ITS token.
FAKE_ACCOUNT_JS = r"""
const http = require('http');
const identity = (email) => ({
  active: true,
  scopes: ['proxy:exec', 'audit:write'],
  orgId: 'org-smoke',
  teamId: null,
  createdByUserId: 'user-' + email,
  userEmail: email + '@smoke.test',
  orgRole: 'owner',
});
http.createServer((req, res) => {
  let body = '';
  req.on('data', (c) => (body += c));
  req.on('end', () => {
    console.log('AUTH ' + (req.headers.authorization || '-') + ' ' + req.method + ' ' + req.url);
    if (req.url !== '/account/api/v1/proxy/introspect' || req.method !== 'POST') {
      res.writeHead(404); return res.end('{}');
    }
    if (req.headers.authorization !== 'Bearer ' + process.env.EXECUTOR_TOKEN) {
      res.writeHead(401); return res.end('{"error":"bad executor token"}');
    }
    let token = '';
    try { token = JSON.parse(body).token; } catch (e) {}
    const known = { [process.env.EXECUTOR_TOKEN]: 'executor', [process.env.CALLER_TOKEN]: 'caller' };
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify(known[token] ? identity(known[token]) : { active: false }));
  });
}).listen(Number(process.env.PORT), '0.0.0.0', () => console.log('READY'));
"""

# One HTTP probe from inside the network, printed as JSON: {"status": <code>, "body": <text>} or {"error": <message>}.
PROBE_JS = r"""
const [method, url, token] = process.argv.slice(1);
fetch(url, { method, headers: token ? { authorization: 'Bearer ' + token } : {} })
  .then(async (r) => console.log(JSON.stringify({ status: r.status, body: await r.text() })))
  .catch((e) => console.log(JSON.stringify({ error: String(e && e.cause ? e.cause : e) })));
"""


def parse_renet_version(output: str) -> str | None:
    """`renet version 1.2.3` -> `1.2.3`; anything else -> None."""
    words = output.split()
    if len(words) >= 3 and words[0] == "renet" and words[1] == "version":
        return words[2]
    return None


def verdict(obs: dict) -> list[str]:
    """The findings for one run's observations. Pure, so the controls can drive it."""
    out: list[str] = []
    if not obs.get("running_after_boot"):
        out.append(
            "the executor did not stay up with REDIACC_TOKEN set (B1); its log: %s"
            % obs.get("executor_log", "").strip()[-400:]
        )
    if obs.get("health_status") != 200:
        out.append("/v1/health answered %r, expected 200" % obs.get("health_status"))
    info = obs.get("server_info") or {}
    if obs.get("server_info_status") != 200:
        out.append("/v1/server-info answered %r, expected 200" % obs.get("server_info_status"))
    elif info.get("mode") != "container":
        out.append("/v1/server-info reports mode %r, expected 'container'" % info.get("mode"))
    renet = parse_renet_version(obs.get("renet_output", ""))
    if obs.get("renet_rc") != 0 or renet is None:
        out.append(
            "`renet version` in the image failed (B2): rc %r, output %r"
            % (obs.get("renet_rc"), obs.get("renet_output", "").strip())
        )
    if obs.get("server_info_status") == 200 and info.get("cliVersion") != obs.get("bundle_version"):
        out.append(
            "/v1/server-info reports cliVersion %r but `node cli-bundle.cjs --version` says %r"
            % (info.get("cliVersion"), obs.get("bundle_version"))
        )
    manifest = obs.get("manifest_version")
    if manifest != executor_artifacts.LOCAL_VERSION and obs.get("bundle_version") != manifest:
        out.append(
            "the image's bundle reports %r but the staged manifest names %r; a released stage must agree"
            % (obs.get("bundle_version"), manifest)
        )
    if manifest != executor_artifacts.LOCAL_VERSION and renet is not None and renet != manifest:
        out.append("the image ships renet %r but the staged manifest names %r" % (renet, manifest))
    if obs.get("session_status") != 200:
        out.append(
            "POST /v1/session with a caller token answered %r, expected 200"
            % obs.get("session_status")
        )
    if "AUTH Bearer %s POST" % EXECUTOR_TOKEN not in obs.get("account_log", ""):
        out.append(
            "the executor never introspected with its own REDIACC_TOKEN against REDIACC_ACCOUNT_SERVER"
        )
    if obs.get("tokenless_running", True) or obs.get("tokenless_exit") in (None, 0):
        out.append(
            "CONTROL: the image started WITHOUT REDIACC_TOKEN did not exit non-zero, so 'stays up' proves nothing"
        )
    elif "REDIACC_TOKEN" not in obs.get("tokenless_log", ""):
        out.append(
            "CONTROL: the tokenless executor exited without naming REDIACC_TOKEN: %r"
            % obs.get("tokenless_log", "").strip()[-300:]
        )
    return out


HEALTHY = {
    "running_after_boot": True,
    "health_status": 200,
    "server_info_status": 200,
    "server_info": {"mode": "container", "cliVersion": "1.2.3"},
    "renet_rc": 0,
    "renet_output": "renet version 1.2.3",
    "bundle_version": "1.2.3",
    "manifest_version": "1.2.3",
    "session_status": 200,
    "account_log": "READY\nAUTH Bearer %s POST /account/api/v1/proxy/introspect\n" % EXECUTOR_TOKEN,
    "tokenless_running": False,
    "tokenless_exit": 1,
    "tokenless_log": "Set REDIACC_TOKEN to a token carrying the proxy:exec scope.",
}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _fake_account_control() -> bool:
    """True when the fake account server answers as the gate assumes. Needs node on the host."""
    node = shutil.which("node")
    if node is None:
        print("  SKIP  fake account control: no node on this host", file=sys.stderr)
        return True
    port = _free_port()
    env = {
        **os.environ,
        "PORT": str(port),
        "EXECUTOR_TOKEN": EXECUTOR_TOKEN,
        "CALLER_TOKEN": CALLER_TOKEN,
    }
    proc = subprocess.Popen(
        [node, "-e", FAKE_ACCOUNT_JS], env=env, stdout=subprocess.PIPE, text=True
    )
    try:
        if proc.stdout is None or proc.stdout.readline().strip() != "READY":
            return False

        def ask(executor_token: str, token: str) -> tuple[int, dict]:
            req = https.build_request(
                "http://127.0.0.1:%d/account/api/v1/proxy/introspect" % port,
                data=json.dumps({"token": token}).encode(),
                headers={"authorization": "Bearer " + executor_token},
                method="POST",
                http="loopback",
            )
            try:
                with https.urlopen(req, timeout=5, http="loopback") as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as e:
                with e:
                    return e.code, {}

        caller = ask(EXECUTOR_TOKEN, CALLER_TOKEN)
        wrong = ask("not-the-executor", CALLER_TOKEN)
        stranger = ask(EXECUTOR_TOKEN, "rdt_stranger")
        return (
            caller[0] == 200
            and caller[1].get("active") is True
            and "proxy:exec" in caller[1].get("scopes", [])
            and wrong[0] == 401
            and stranger[1].get("active") is False
        )
    finally:
        proc.kill()
        proc.wait()


def selftest() -> bool:
    """True when a control FAILED."""
    failed = False

    def control(label: str, ok: bool) -> None:
        nonlocal failed
        if ok:
            print("  PASS  %s" % label)
        else:
            failed = True
            print("  FAIL  %s" % label, file=sys.stderr)

    control("renet version parses", parse_renet_version("renet version 0.9.1\n") == "0.9.1")
    control("garbage is not a renet version", parse_renet_version("bash: renet: not found") is None)
    control("a healthy run has no findings", verdict(HEALTHY) == [])
    for label, patch in (
        ("B1: an executor that exited is a finding", {"running_after_boot": False}),
        ("B2: an image without renet is a finding", {"renet_rc": 127, "renet_output": ""}),
        (
            "a daemon-mode image is a finding",
            {"server_info": {"mode": "daemon", "cliVersion": "1.2.3"}},
        ),
        (
            "a server-info/bundle version mismatch is a finding",
            {"server_info": {"mode": "container", "cliVersion": "0.0.0-dev"}},
        ),
        (
            "a bundle that disagrees with a released manifest is a finding",
            {"manifest_version": "9.9.9", "renet_output": "renet version 9.9.9"},
        ),
        (
            "a renet that disagrees with a released manifest is a finding",
            {
                "manifest_version": "1.2.4",
                "bundle_version": "1.2.4",
                "server_info": {"mode": "container", "cliVersion": "1.2.4"},
            },
        ),
        ("an executor that never used its token is a finding", {"account_log": "READY\n"}),
        ("a refused session is a finding", {"session_status": 401}),
        ("a tokenless executor that stays up voids the control", {"tokenless_running": True}),
        (
            "a tokenless executor exiting 0 voids the control",
            {"tokenless_running": False, "tokenless_exit": 0},
        ),
    ):
        control(label, len(verdict({**HEALTHY, **patch})) == 1)
    control("the fake account server answers as assumed", _fake_account_control())
    return failed


# ---------------------------------------------------------------------------------------------


def _docker(*args: str, timeout: int = 120, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, timeout=timeout, check=check
    )


def _stage_local(root: pathlib.Path) -> tuple[bool, str]:
    """Stage the image's inputs through `executor_artifacts stage-local`: (ok, how or the refusal).

    The Dockerfile builds nothing, so the gate stages the tree's own bundle, renet and natives into `workers/proxy/stage/` exactly as a bench or local deploy does.
    """
    dest = root.joinpath(*STAGE_DIR)
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = executor_artifacts.main(["stage-local", "--dest", str(dest)])
    if rc != 0:
        return False, err.getvalue().strip()
    return True, out.getvalue().strip()


def _unstage(root: pathlib.Path) -> None:
    """Remove what `stage-local` wrote; the tracked `.gitkeep` and `.gitignore` stay."""
    dest = root.joinpath(*STAGE_DIR)
    for name in (*executor_artifacts.FILES, executor_artifacts.MANIFEST):
        dest.joinpath(name).unlink(missing_ok=True)


def staged_version(root: pathlib.Path) -> str:
    """The version the staged manifest names."""
    manifest = json.loads(root.joinpath(*STAGE_DIR, executor_artifacts.MANIFEST).read_text())
    return str(manifest["version"])


def _probe(account: str, method: str, url: str, token: str = "") -> dict:
    r = _docker("exec", account, "node", "-e", PROBE_JS, method, url, token, timeout=30)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        return {"error": (r.stdout + r.stderr).strip()[-300:]}


def _running(name: str) -> tuple[bool, int | None]:
    r = _docker("inspect", "-f", "{{.State.Running}} {{.State.ExitCode}}", name)
    if r.returncode != 0:
        return False, None
    running, code = r.stdout.split()
    return running == "true", int(code)


def observe(tag: str, suffix: str, manifest_version: str) -> dict:
    """Run the image and collect what verdict() judges."""
    net = "rediacc-proxy-smoke-%s" % suffix
    account = "rediacc-proxy-smoke-account-%s" % suffix
    executor = "rediacc-proxy-smoke-executor-%s" % suffix
    tokenless = "rediacc-proxy-smoke-tokenless-%s" % suffix
    obs: dict = {"manifest_version": manifest_version}
    try:
        _docker("network", "create", net, check=True)
        _docker(
            "run", "-d", "--name", account, "--network", net, "--network-alias", "account",
            "-e", "PORT=%d" % ACCOUNT_PORT, "-e", "EXECUTOR_TOKEN=" + EXECUTOR_TOKEN,
            "-e", "CALLER_TOKEN=" + CALLER_TOKEN,
            tag, "node", "-e", FAKE_ACCOUNT_JS,
            check=True,
        )  # fmt: skip
        # The image's own CMD, with the variables OrgExecutor's env sets (workers/proxy/src/org-executor-support.ts): the token, the account server and the one org the executor is pinned to, which the fake account's introspection names.
        _docker(
            "run", "-d", "--name", executor, "--network", net, "--network-alias", "executor",
            "-e", "REDIACC_TOKEN=" + EXECUTOR_TOKEN,
            "-e", "REDIACC_ACCOUNT_SERVER=http://account:%d" % ACCOUNT_PORT,
            "-e", "REDIACC_EXECUTOR_ORG_ID=org-smoke",
            tag,
            check=True,
        )  # fmt: skip
        _docker("run", "-d", "--name", tokenless, "--network", net, tag, check=True)

        base = "http://executor:%d" % EXECUTOR_PORT
        deadline = time.monotonic() + BOOT_TIMEOUT_S
        health: dict = {}
        while time.monotonic() < deadline:
            health = _probe(account, "GET", base + "/v1/health")
            if health.get("status") == 200 or not _running(executor)[0]:
                break
            time.sleep(1)
        obs["health_status"] = health.get("status")

        time.sleep(STAY_UP_S)
        obs["running_after_boot"] = _running(executor)[0]
        obs["executor_log"] = _docker("logs", executor).stdout + _docker("logs", executor).stderr

        info = _probe(account, "GET", base + "/v1/server-info")
        obs["server_info_status"] = info.get("status")
        try:
            obs["server_info"] = json.loads(info.get("body") or "{}")
        except json.JSONDecodeError:
            obs["server_info"] = {}

        obs["session_status"] = _probe(account, "POST", base + "/v1/session", CALLER_TOKEN).get(
            "status"
        )
        logs = _docker("logs", account)
        obs["account_log"] = logs.stdout + logs.stderr

        renet = _docker("exec", executor, "renet", "version", timeout=30)
        obs["renet_rc"] = renet.returncode
        obs["renet_output"] = renet.stdout + renet.stderr
        bundle = _docker("exec", executor, "node", "cli-bundle.cjs", "--version", timeout=30)
        obs["bundle_version"] = bundle.stdout.strip()

        deadline = time.monotonic() + BOOT_TIMEOUT_S
        while time.monotonic() < deadline and _running(tokenless)[0]:
            time.sleep(1)
        obs["tokenless_running"], obs["tokenless_exit"] = _running(tokenless)
        tl = _docker("logs", tokenless)
        obs["tokenless_log"] = tl.stdout + tl.stderr
    finally:
        for name in (executor, tokenless, account):
            _docker("rm", "-f", name)
        _docker("network", "rm", net)
    return obs


def main(argv: list[str]) -> int:
    # Line-buffered, so the verdict and docker's own output interleave in the order they happened.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(line_buffering=True)
    rc = controls_first("proxy image smoke", selftest)
    if rc or "--selftest" in argv:
        return rc
    # SIGTERM becomes an exception so the `finally` blocks that remove the containers, network and image
    # still run when a runner terminates the gate; a 2026-10-06 run killed this way left all four behind.
    _SIGTERM_SEEN[0] = False
    previous = signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        return _smoke()
    except _TerminatedError:
        print("✗ terminated; teardown ran", file=sys.stderr)
        return 143
    finally:
        signal.signal(signal.SIGTERM, previous)


class _TerminatedError(Exception):
    pass


_SIGTERM_SEEN = [False]


def _on_sigterm(_signum: int, _frame: object) -> None:
    """The first SIGTERM unwinds into the `finally` teardown; any later one is ignored, or it would raise inside that teardown and skip the removals still to run."""
    if _SIGTERM_SEEN[0]:
        return
    _SIGTERM_SEEN[0] = True
    raise _TerminatedError("SIGTERM")


def _smoke() -> int:
    if shutil.which("docker") is None or _docker("version").returncode != 0:
        print(
            "✗ docker is not available here, so the image cannot be built: no verdict",
            file=sys.stderr,
        )
        return 2

    root = paths.repo_root()
    staged_here = False
    if root.joinpath(*STAGE_DIR, executor_artifacts.MANIFEST).is_file():
        print("executor artifacts for the image: already staged (left in place)")
    else:
        staged_here = True
        ok, how = _stage_local(root)
        if not ok:
            _unstage(root)
            print("✗ cannot stage the image's inputs (%s): no verdict" % how, file=sys.stderr)
            return 2
        print("executor artifacts for the image: %s" % how)

    suffix = "%d-%d" % (os.getpid(), int(time.time()))
    tag = "rediacc-proxy-image-smoke:%s" % suffix
    try:
        print("building %s from %s (slow)..." % (tag, "/".join(DOCKERFILE)))
        with tempfile.TemporaryFile("w+") as log:
            build = subprocess.run(
                ["docker", "build", "-f", "/".join(DOCKERFILE), "-t", tag, "."],
                cwd=root,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=BUILD_TIMEOUT_S,
                check=False,
            )
            if build.returncode != 0:
                log.seek(0)
                print(log.read()[-4000:], file=sys.stderr)
                print(
                    "✗ docker build -f %s . failed (exit %d)"
                    % ("/".join(DOCKERFILE), build.returncode),
                    file=sys.stderr,
                )
                return 1
        manifest_version = staged_version(root)
        obs = observe(tag, suffix, manifest_version)
        print(
            "image `node cli-bundle.cjs --version`: %s; staged manifest version: %s"
            % (obs.get("bundle_version"), manifest_version)
        )
        found = verdict(obs)
    finally:
        _docker("rmi", "-f", tag)
        if staged_here:
            _unstage(root)

    if found:
        print("✗ %d proxy image finding(s):" % len(found), file=sys.stderr)
        for f in found:
            print("    %s" % f, file=sys.stderr)
        return 1
    print(
        "✓ the proxy image builds, stays up with its token (and exits without it), serves /v1/health, "
        "/v1/server-info and /v1/session, and ships a bundle and renet matching the staged manifest"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
