"""`rediacc_ci.deploy.deploy_proxy`: one target's proxy deploy, its config gate, the version id it captures, and the smoke that proves the deployed version answers.

RECORDING FAKES ON A SCRATCH PATH, A FIXTURE REPO ROOT, NOTHING REACHES CLOUDFLARE. `npm`, `npx` and `curl` are fakes on PATH; the two `python3 -m` children (`executor_artifacts` and, for bench, `build_renet`) and the in-process `resolve_version` are swapped for recording fakes by DRIVER. The fixture root carries the real regions.json and the real `workers/proxy/wrangler*.toml`, so the argv pins below are the argv the real configs produce.

THE GOLDEN. `tests/goldens/twins/deploy.deploy-proxy.jsonl` began as the frozen answers of the retired bash twin. The generalized deploy (agent/plans/PLAN-proxy-cd-six-targets.md D1) answers differently in every case that twin had, so the golden's records are now the port's own answers for the cases `run_golden` routes, re-recorded with

    PYTHONPATH=.ci python3 -m rediacc_ci.tests.regolden .ci/scripts/deploy/deploy-proxy.sh --source port --reason "<why>"

and a compare run holds each live answer equal to its record. The `twin_blob` in the header still names the bash text.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
import types
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.deploy import deploy_proxy as port
from rediacc_ci.deploy import proxy_configs
from rediacc_ci.tests import differential as diff
from rediacc_ci.well_known import PROXY_BENCH_HOST, PROXY_EDGE_US_HOST, PROXY_US_HOST

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
TWIN_REL = ".ci/scripts/deploy/deploy-proxy.sh"
PROXY_DIR = ROOT / "workers" / "proxy"

NEW_ID = "22222222-2222-4222-8222-222222222222"
PREV_ID = "11111111-1111-4111-8111-111111111111"
VERSION = "1.2.3"

# The port, with its children swapped for recording fakes. READY_TIMEOUT_S comes from FAKE_READY_TIMEOUT so a ready failure ends at once.
DRIVER = """
import os
import sys

from rediacc_ci.deploy import deploy_proxy
from rediacc_ci.version import resolve_version


def log(line):
    with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
        fh.write(line + "\\n")
        fh.write("  cwd=" + os.path.basename(os.getcwd()) + "\\n")


def fake_resolve(argv):
    log("resolve_version\\t" + "\\t".join(argv))
    return 0, "9.9.9\\n", ""


def fake_build_renet(repo_root, version):
    return [os.environ["FAKE_CHILD"], "build_renet", "--version", version]


def fake_artifacts(verb, *args):
    return [os.environ["FAKE_CHILD"], "executor_artifacts", verb, *args]


resolve_version.run = fake_resolve
deploy_proxy.build_renet_argv = fake_build_renet
deploy_proxy.artifacts_argv = fake_artifacts
deploy_proxy.READY_TIMEOUT_S = float(os.environ.get("FAKE_READY_TIMEOUT", "300"))
deploy_proxy.READY_INTERVAL_S = 0.0
sys.exit(deploy_proxy.main(sys.argv[1:]))
"""

FAKE_CHILD = """#!/usr/bin/python3
import os
import sys

with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("\\t".join(sys.argv[1:]) + "\\n")
    fh.write("  cwd=" + os.path.basename(os.getcwd()) + "\\n")
rc = int(os.environ.get("FAKE_CHILD_RC", "0"))
if rc:
    sys.stderr.write(sys.argv[1] + ": failed\\n")
sys.exit(rc)
"""

FAKE_NPM = """#!/usr/bin/python3
import os
import sys

with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("npm\\t" + "\\t".join(sys.argv[1:]) + "\\n")
    fh.write("  cwd=" + os.path.basename(os.getcwd()) + "\\n")
rc = int(os.environ.get("FAKE_NPM_RC", "0"))
if rc:
    sys.stderr.write("npm ERR! build failed\\n")
    sys.exit(rc)
sys.stdout.write("> build done\\n")
"""

# `wrangler deploy` (with or without `--var`) and `wrangler rollback` print a version line; `wrangler deployments list --json` answers the deployments before either, then after it.
FAKE_NPX = """#!/usr/bin/python3
import json
import os
import sys

log = os.environ["FAKE_CALL_LOG"]
with open(log) as fh:
    deployed = any(
        line.startswith(("npx\\t--no-install\\twrangler\\tdeploy\\t", "npx\\t--no-install\\twrangler\\trollback\\t"))
        and "\\t--dry-run\\t" not in line
        for line in fh
    )
with open(log, "a") as fh:
    fh.write("npx\\t" + "\\t".join(sys.argv[1:]) + "\\n")
    fh.write("  cwd=" + os.path.basename(os.getcwd()) + "\\n")

args = sys.argv[1:]
assert args[:1] == ["--no-install"], args
args = args[1:]
prev = {"created_on": "2026-10-01T00:00:00Z", "versions": [{"version_id": os.environ["FAKE_PREV_ID"], "percentage": 100}]}
if args[:3] == ["wrangler", "deployments", "list"]:
    if not deployed:
        if os.environ.get("FAKE_NO_PREVIOUS"):
            sys.stderr.write("wrangler: This Worker does not exist on your account.\\n")
            sys.exit(1)
        print(json.dumps([prev]))
    else:
        listed = os.environ.get("FAKE_LISTED_ID", os.environ["FAKE_NEW_ID"])
        new = {"created_on": "2026-10-25T20:00:00Z", "versions": [{"version_id": listed, "percentage": 100}]}
        print(json.dumps([new, prev]))
    sys.exit(0)
if args[:3] == ["wrangler", "versions", "view"]:
    view_rc = int(os.environ.get("FAKE_VIEW_RC", "0"))
    if view_rc:
        sys.stderr.write("wrangler: version not found\\n")
        sys.exit(view_rc)
    bindings = [{"type": "secret_text", "name": "SOME_SECRET"}]
    if os.environ.get("FAKE_VIEW_BACKEND", "container"):
        bindings.append({"type": "plain_text", "name": "EXECUTOR_BACKEND", "text": os.environ.get("FAKE_VIEW_BACKEND", "container")})
    print(json.dumps({"id": args[3], "resources": {"bindings": bindings}}))
    sys.exit(0)
rc = int(os.environ.get("FAKE_NPX_RC", "0"))
if rc:
    sys.stderr.write("wrangler: deploy failed\\n")
    sys.exit(rc)
sys.stdout.write("Total Upload: 1.00 KiB\\n")
if "--dry-run" not in args and not os.environ.get("FAKE_NO_VERSION_LINE"):
    sys.stdout.write("Deployed rediacc-proxy triggers\\nCurrent Version ID: " + os.environ["FAKE_NEW_ID"] + "\\n")
"""

# A git that knows one previous release tag, `v2.3.2`, and answers `git show v2.3.2:<path>` with the file named by FAKE_PREV_CONFIG. Without FAKE_PREV_CONFIG it fails, as a checkout with no tag does. It logs nothing: git is not part of the recorded calls.
FAKE_GIT = """#!/usr/bin/python3
import os
import sys

args = sys.argv[1:]
prev = os.environ.get("FAKE_PREV_CONFIG")
if not prev:
    sys.exit(1)
if args[:2] == ["tag", "--list"]:
    print("v%s" % "1.2.3")
    print("v2.3.2")
    sys.exit(0)
if args[:1] == ["show"] and args[1].startswith("v2.3.2:"):
    sys.stdout.write(open(prev).read())
    sys.exit(0)
sys.exit(1)
"""

# Codes by path. /v1/ready is asked with `-w '\\n%{http_code}'`, so it prints its body, a newline, then the code.
FAKE_CURL = """#!/usr/bin/python3
import json
import os
import sys
from rediacc_ci.well_known import PROXY_EDGE_US_HOST

url = sys.argv[-1]
with open(os.environ["FAKE_CALL_LOG"], "a") as fh:
    fh.write("curl\\t" + "\\t".join(sys.argv[1:]) + "\\n")
rc = int(os.environ.get("FAKE_CURL_RC", "0"))
if rc:
    sys.stdout.write("000")
    sys.stderr.write("curl: (6) Could not resolve host\\n")
    sys.exit(rc)
if url.endswith("/v1/health"):
    sys.stdout.write(os.environ.get("FAKE_HEALTH", "200"))
elif url.endswith("/v1/ready"):
    code = os.environ.get("FAKE_READY_CODE", "200")
    if code == "200":
        body = {"ready": True, "workerVersion": os.environ.get("FAKE_READY_VERSION", os.environ["FAKE_NEW_ID"])}
    else:
        body = {"ready": False, "reason": "issuer-refused"}
    sys.stdout.write(json.dumps(body) + "\\n" + code)
else:
    sys.stdout.write(os.environ.get("FAKE_INFO", "401"))
"""

PATH_MINIMUM = ("uname", "dirname")

BASE_ENV = {
    "CLOUDFLARE_API_TOKEN": "tok",
    "ACCOUNT_ED25519_PUBLIC_KEY": "pubkey",
    "REDIACC_SMOKE_RESOLVE_WINDOW_S": "0",
    "REDIACC_SMOKE_DOH_URL": "",
    "FAKE_NEW_ID": NEW_ID,
    "FAKE_PREV_ID": PREV_ID,
}

CURL = "curl\t-sS\t-o\t/dev/null\t-w\t%{http_code}\t--max-time\t30\t"
CURL_BODY = "curl\t-sS\t-w\t\\n%{http_code}\t--max-time\t30\t"

# The six generated targets: (target, region, config, route).
SIX = tuple(
    (
        "edge" if key.startswith("edge-") else "stable",
        key.removeprefix("edge-"),
        t.config,
        t.routes[0],
    )
    for key, t in proxy_configs.targets(proxy_configs.load_regions(ROOT)).items()
    if t.generated
)


def _fixture_root(tmp_path: pathlib.Path) -> pathlib.Path:
    """A repo root holding regions.json and every real `workers/proxy/wrangler*.toml`."""
    root = tmp_path / "root"
    proxy = root / "workers" / "proxy"
    proxy.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "regions.json", root / "regions.json")
    for path in PROXY_DIR.glob("wrangler*.toml"):
        shutil.copy2(path, proxy / path.name)
    return root


def _plant(root: pathlib.Path, config: str, old: str, new: str) -> None:
    path = root / "workers" / "proxy" / config
    text = path.read_text(encoding="utf-8")
    assert text.count(old) >= 1, "the plant's anchor %r is absent from %s" % (old, config)
    path.write_text(text.replace(old, new), encoding="utf-8")


def _bin(tmp_path: pathlib.Path) -> tuple[str, str]:
    stub = tmp_path / "bin"
    stub.mkdir(parents=True, exist_ok=True)
    for real_name in PATH_MINIMUM:
        real = shutil.which(real_name)
        assert real is not None, f"{real_name} is missing from this machine"
        link = stub / real_name
        if not link.exists():
            link.symlink_to(real)
    for name, body in (
        ("npx", FAKE_NPX),
        ("npm", FAKE_NPM),
        ("curl", FAKE_CURL),
        ("git", FAKE_GIT),
    ):
        fake = stub / name
        fake.write_text(body, encoding="utf-8")
        fake.chmod(0o755)
    child = tmp_path / "fake-child"
    child.write_text(FAKE_CHILD, encoding="utf-8")
    child.chmod(0o755)
    return str(stub), str(child)


def _run(
    tmp_path: pathlib.Path,
    root: pathlib.Path,
    args: tuple[str, ...],
    *,
    drop_env: tuple[str, ...] = (),
    **extra: str,
) -> tuple[subprocess.CompletedProcess, str]:
    call_log = tmp_path / "calls.log"
    call_log.write_text("", encoding="utf-8")
    stub, child = _bin(tmp_path)
    env = {
        "PATH": stub,
        "HOME": os.environ.get("HOME", "/tmp"),
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(ROOT / ".ci"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "REDIACC_CI_ROOT": str(root),
        "FAKE_CALL_LOG": str(call_log),
        "FAKE_CHILD": child,
        **BASE_ENV,
    }
    env.update(extra)
    for name in drop_env:
        env.pop(name, None)
    proc = subprocess.run(
        [sys.executable, "-c", DRIVER, *args],
        cwd=root,
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=120,
        input="",
    )
    return proc, call_log.read_text(encoding="utf-8")


def run_golden(tmp_path: pathlib.Path, root: pathlib.Path, *args: str, **kw):
    """The live answer, held equal to the golden's record of the same case. A regolden `--source port` run records it."""
    box: dict[str, str] = {}

    def live() -> tuple[int, str, str]:
        proc, calls = _run(tmp_path, root, args, **kw)
        box["calls"] = calls
        return proc.returncode, proc.stdout, proc.stderr

    def no_bash() -> tuple[int, str, str]:
        raise AssertionError("the bash twin is retired; record from the port")

    rc, out, err, frozen = diff.twin_run(
        TWIN_REL,
        ["args=%r" % (args,), "kw=%r" % (sorted(kw.items()),)],
        no_bash,
        port=live,
        extras={"calls": lambda: box["calls"]},
        work=(str(tmp_path),),
    )
    new, calls = _run(tmp_path, root, args, **kw)
    assert (new.returncode, new.stdout, new.stderr) == (rc, out, err), (
        "the live answer diverged from the golden record:\nrecord: %r\nlive:   %r"
        % ((rc, out, err), (new.returncode, new.stdout, new.stderr))
    )
    assert calls == frozen["calls"], "the recorded calls diverged:\nrecord: %r\nlive:   %r" % (
        frozen["calls"],
        calls,
    )
    return new, calls


def _release_calls(root: pathlib.Path, config: str, host: str) -> str:
    stage = root / "workers" / "proxy" / "stage"
    return (
        f"executor_artifacts\tfetch\t--version\t{VERSION}\t--dest\t{stage}\n"
        "  cwd=root\n"
        f"npx\t--no-install\twrangler\tdeployments\tlist\t--json\t--config\t{config}\n"
        "  cwd=proxy\n"
        f"npx\t--no-install\twrangler\tdeploy\t--config\t{config}\n"
        "  cwd=proxy\n"
        f"npx\t--no-install\twrangler\tdeployments\tlist\t--json\t--config\t{config}\n"
        "  cwd=proxy\n"
        f"{CURL}https://{host}/v1/health\n"
        f"{CURL}https://{host}/v1/server-info\n"
        f"{CURL_BODY}https://{host}/v1/ready\n"
    )


# ---- the six generated targets ---------------------------------------------


def test_the_six_targets_are_the_generated_configs() -> None:
    """ANTI-VACUITY for the parametrization below: six, one per (channel, region)."""
    assert sorted((t, r) for t, r, _c, _h in SIX) == sorted(
        (t, r) for t in ("edge", "stable") for r in ("eu", "us", "asia")
    )


@pytest.mark.parametrize(("target", "region", "config", "host"), SIX, ids=[s[2] for s in SIX])
def test_each_target_deploys_its_own_config_with_the_pinned_argv(
    tmp_path: pathlib.Path, target: str, region: str, config: str, host: str
) -> None:
    """Fetch the release's artifacts, read the previous deployment, deploy with `--config`, cross-check the version, smoke three paths. Nothing is built."""
    root = _fixture_root(tmp_path)
    proc, calls = run_golden(
        tmp_path, root, "--target", target, "--region", region, "--version", VERSION
    )
    assert proc.returncode == 0, proc.stderr
    assert calls == _release_calls(root, config, host)
    assert config == port.config_name(target, region)
    assert "Current Version ID: %s\n" % NEW_ID in proc.stdout, "wrangler's output is teed"
    assert (
        "✓ Deployed %s: version %s.\n"
        % (
            proxy_configs.targets(proxy_configs.load_regions(ROOT))[
                port.config_key(target, region)
            ].name,
            NEW_ID,
        )
        in proc.stderr
    )
    assert (
        "✓ Rollback: cd workers/proxy && npx --no-install wrangler rollback %s --config %s\n"
        % (PREV_ID, config)
        in proc.stderr
    )
    assert "npm" not in calls
    assert "build_renet" not in calls


def test_the_edge_us_and_stable_us_routes_are_the_well_known_hosts() -> None:
    hosts = {(t, r): h for t, r, _c, h in SIX}
    assert hosts[("edge", "us")] == PROXY_EDGE_US_HOST
    assert hosts[("stable", "us")] == PROXY_US_HOST


def test_every_real_config_passes_the_gate_it_is_deployed_through() -> None:
    for target, region, config, _host in SIX:
        spec, _text = port.select(ROOT, target, region)
        assert spec.config == config
    spec, _text = port.select(ROOT, "bench", None)
    assert spec.config == "wrangler.bench.toml"
    assert spec.routes == (PROXY_BENCH_HOST,)


# ---- the config gate runs before any credential ------------------------------


def test_a_us_config_carrying_an_eu_binding_refuses_before_any_fetch_or_build(
    tmp_path: pathlib.Path,
) -> None:
    """With no token in the environment: the gate runs first, so a config that reaches another region is never handed a credential, and the call log stays empty."""
    root = _fixture_root(tmp_path)
    _plant(
        root, "wrangler.us.toml", 'service = "rediacc-account-us"', 'service = "rediacc-account-eu"'
    )
    proc, calls = run_golden(
        tmp_path,
        root,
        "--target",
        "stable",
        "--region",
        "us",
        "--version",
        VERSION,
        drop_env=("CLOUDFLARE_API_TOKEN",),
    )
    assert proc.returncode == 1
    assert proc.stdout == ""
    assert calls == ""
    lines = proc.stderr.splitlines()
    assert lines
    assert all(
        line.startswith("✗ --target stable refused: workers/proxy/wrangler.us.toml: ")
        for line in lines
    ), proc.stderr
    assert "rediacc-account-eu" in proc.stderr
    assert "names eu, which is not us" in proc.stderr


def test_an_edge_config_naming_the_stable_worker_refuses(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    _plant(
        root, "wrangler.edge-eu.toml", 'name = "edge-rediacc-proxy-eu"', 'name = "rediacc-proxy-eu"'
    )
    proc, calls = _run(tmp_path, root, ("--target", "edge", "--region", "eu", "--version", VERSION))
    assert proc.returncode == 1
    assert calls == ""
    assert "rediacc-proxy-eu" in proc.stderr


def test_a_missing_config_refuses_before_any_fetch(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    (root / "workers" / "proxy" / "wrangler.asia.toml").unlink()
    proc, calls = _run(
        tmp_path, root, ("--target", "stable", "--region", "asia", "--version", VERSION)
    )
    assert proc.returncode == 1
    assert calls == ""
    assert proc.stderr.startswith(
        "✗ --target stable refused: workers/proxy/wrangler.asia.toml cannot be read"
    )


@pytest.mark.parametrize(
    ("args", "fragment"),
    [
        (("--target", "production", "--region", "eu"), "--target production is not supported"),
        (("--target", "edge"), "--region is required for --target edge"),
        (
            ("--target", "stable", "--region", "mars", "--version", VERSION),
            "--region mars is not supported",
        ),
        (("--target", "bench", "--region", "us"), "--target bench refuses --region us"),
        (("--target", "stable", "--region", "eu"), "--version is required for a stable deploy"),
        (
            ("--target", "edge", "--region", "eu", "--version", "next"),
            "--version 'next' is not a release version",
        ),
    ],
    ids=["unknown-target", "no-region", "unknown-region", "bench-us", "no-version", "bad-version"],
)
def test_argument_refusals_need_no_token_and_run_nothing(
    tmp_path: pathlib.Path, args: tuple[str, ...], fragment: str
) -> None:
    root = _fixture_root(tmp_path)
    proc, calls = _run(tmp_path, root, args, drop_env=("CLOUDFLARE_API_TOKEN",))
    assert proc.returncode == 1, proc.stderr
    assert calls == ""
    assert proc.stderr.startswith("✗ "), proc.stderr
    assert fragment in proc.stderr, proc.stderr


def test_a_missing_target_is_a_usage_error(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    proc, calls = _run(tmp_path, root, ())
    assert proc.returncode == 2
    assert "--target" in proc.stderr
    assert calls == ""


def test_a_missing_token_refuses_before_the_fetch(tmp_path: pathlib.Path) -> None:
    """With the deploy-proxy profile already bound, a missing token is a refusal, not a second re-exec."""
    root = _fixture_root(tmp_path)
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "edge", "--region", "us", "--version", VERSION),
        drop_env=("CLOUDFLARE_API_TOKEN",),
        REDIACC_BWS_PROFILES="deploy-proxy",
    )
    assert proc.returncode == 1
    assert proc.stderr == port.MISSING_AUTH_MSG + "\n"
    assert calls == ""


# ---- dry runs ---------------------------------------------------------------


DRY_TARGETS = (*((t, r, c) for t, r, c, _h in SIX), ("bench", "eu", "wrangler.bench.toml"))


@pytest.mark.parametrize(
    ("target", "region", "config"), DRY_TARGETS, ids=[d[2] for d in DRY_TARGETS]
)
def test_a_dry_run_works_for_every_target_without_credentials(
    tmp_path: pathlib.Path, target: str, region: str, config: str
) -> None:
    """The gate, then `wrangler deploy --dry-run --config`: no token, no version, no fetch, no build, no smoke."""
    root = _fixture_root(tmp_path)
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", target, "--region", region, "--dry-run"),
        drop_env=("CLOUDFLARE_API_TOKEN", "ACCOUNT_ED25519_PUBLIC_KEY"),
    )
    assert proc.returncode == 0, proc.stderr
    assert calls == (
        "npx\t--no-install\twrangler\tdeploy\t--dry-run\t--outdir\t%s\t--containers-rollout\tnone\t--config\t%s\n  cwd=proxy\n"
        % (port.DRY_RUN_OUTDIR, config)
    )
    assert proc.stderr.endswith("✓ Dry run passed. Nothing was deployed.\n")


def test_the_edge_us_dry_run_is_pinned(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    proc, _calls = run_golden(tmp_path, root, "--target", "edge", "--region", "us", "--dry-run")
    assert proc.returncode == 0, proc.stderr


def test_a_failed_dry_run_propagates_wranglers_status(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    proc, _calls = _run(
        tmp_path, root, ("--target", "edge", "--region", "eu", "--dry-run"), FAKE_NPX_RC="5"
    )
    assert proc.returncode == 5
    assert "Dry run passed" not in proc.stderr


# ---- bench ------------------------------------------------------------------

BENCH_PROFILE_ENV = {"REDIACC_BWS_PROFILES": "deploy-proxy-bench"}


def test_a_bench_deploy_builds_from_the_tree_and_stages_locally(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    proc, calls = run_golden(tmp_path, root, "--target", "bench", **BENCH_PROFILE_ENV)
    assert proc.returncode == 0, proc.stderr
    stage = root / "workers" / "proxy" / "stage"
    config = "wrangler.bench.toml"
    assert calls == (
        "npm\trun\tbuild\t--workspace\t@rediacc/shared\n"
        "  cwd=root\n"
        "npm\trun\tbuild\t--workspace\t@rediacc/cli\n"
        "  cwd=root\n"
        "npm\trun\tbuild:bundle\t--workspace\t@rediacc/cli\n"
        "  cwd=root\n"
        "resolve_version\t--current\n"
        "  cwd=root\n"
        "build_renet\t--version\t9.9.9\n"
        "  cwd=root\n"
        f"executor_artifacts\tstage-local\t--dest\t{stage}\n"
        "  cwd=root\n"
        f"npx\t--no-install\twrangler\tdeployments\tlist\t--json\t--config\t{config}\n"
        "  cwd=proxy\n"
        f"npx\t--no-install\twrangler\tdeploy\t--config\t{config}\n"
        "  cwd=proxy\n"
        f"npx\t--no-install\twrangler\tdeployments\tlist\t--json\t--config\t{config}\n"
        "  cwd=proxy\n"
        f"{CURL}https://{PROXY_BENCH_HOST}/v1/health\n"
        f"{CURL}https://{PROXY_BENCH_HOST}/v1/server-info\n"
        f"{CURL_BODY}https://{PROXY_BENCH_HOST}/v1/ready\n"
    )
    assert "✓ Deployed rediacc-proxy-bench: version %s.\n" % NEW_ID in proc.stderr


def test_a_bench_deploy_without_the_licence_key_refuses_before_any_build(
    tmp_path: pathlib.Path,
) -> None:
    root = _fixture_root(tmp_path)
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "bench"),
        drop_env=("ACCOUNT_ED25519_PUBLIC_KEY",),
        **BENCH_PROFILE_ENV,
    )
    assert proc.returncode == 1
    assert proc.stderr == "✗ %s\n" % port.MISSING_KEY
    assert calls == ""


def test_a_stable_deploy_needs_no_licence_key(tmp_path: pathlib.Path) -> None:
    """The renet arrives built in the release's artifacts, so only bench (which builds one) needs the key."""
    root = _fixture_root(tmp_path)
    proc, _calls = _run(
        tmp_path,
        root,
        ("--target", "stable", "--region", "eu", "--version", VERSION),
        drop_env=("ACCOUNT_ED25519_PUBLIC_KEY",),
    )
    assert proc.returncode == 0, proc.stderr


def test_a_bench_run_without_its_profile_reexecutes_under_it(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unbound, the run hands itself to `bws_env exec --profile deploy-proxy-bench` after the gate and returns that child's status."""
    root = _fixture_root(tmp_path)
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    monkeypatch.delenv("REDIACC_BWS_PROFILES", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    seen: list[tuple[list[str], dict | None]] = []

    def fake_run(argv: list[str], *, env: dict | None = None) -> int:
        seen.append((argv, env))
        return 7

    monkeypatch.setattr(port, "_run", fake_run)
    assert port.main(["--target", "bench"]) == 7
    assert len(seen) == 1
    argv, env = seen[0]
    assert argv == port.reexec_argv(["--target", "bench"])
    assert argv[1:7] == [
        "-m",
        "rediacc_ci.core.bws_env",
        "exec",
        "--profile",
        "deploy-proxy-bench",
        "--",
    ]
    assert env is not None
    assert env["PYTHONPATH"].split(os.pathsep)[0] == port.PACKAGE_PARENT


def test_an_edge_run_without_a_token_reexecutes_under_the_deploy_proxy_profile(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unbound and with no token, a stable or edge run hands itself to `bws_env exec --profile deploy-proxy`."""
    root = _fixture_root(tmp_path)
    monkeypatch.setenv("REDIACC_CI_ROOT", str(root))
    monkeypatch.delenv("REDIACC_BWS_PROFILES", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    seen: list[list[str]] = []

    def fake_run(argv: list[str], *, env: dict | None = None) -> int:
        del env
        seen.append(argv)
        return 5

    monkeypatch.setattr(port, "_run", fake_run)
    args = ["--target", "edge", "--region", "eu", "--smoke-only"]
    assert port.main(args) == 5
    assert seen == [port.reexec_argv(args, port.PROFILE)]
    assert seen[0][5] == "deploy-proxy"


# ---- the version id ---------------------------------------------------------

WRANGLER_OUTPUT = f"""Total Upload: 312.40 KiB / gzip: 61.02 KiB
Worker Startup Time: 12 ms
Uploaded edge-rediacc-proxy-us (6.10 sec)
Deployed edge-rediacc-proxy-us triggers (1.20 sec)
  {PROXY_EDGE_US_HOST} (custom domain)
Current Version ID: 4fb58b44-1c2d-4e5f-8a9b-0c1d2e3f4a5b
"""


def test_the_version_id_is_parsed_from_wranglers_output() -> None:
    assert port.parse_version_id(WRANGLER_OUTPUT) == "4fb58b44-1c2d-4e5f-8a9b-0c1d2e3f4a5b"
    assert port.parse_version_id("Total Upload: 1.00 KiB\n") is None
    assert port.parse_version_id("Current Version ID: a\nCurrent Version ID: b-2\n") == "b-2"


def test_the_newest_deployment_names_the_version_at_100_percent() -> None:
    old = {
        "created_on": "2026-10-01T00:00:00Z",
        "versions": [{"version_id": "old", "percentage": 100}],
    }
    split = {
        "created_on": "2026-10-25T00:00:00Z",
        "versions": [
            {"version_id": "half", "percentage": 50},
            {"version_id": "other", "percentage": 50},
        ],
    }
    new = {
        "created_on": "2026-10-25T00:00:00Z",
        "versions": [{"version_id": "new", "percentage": 100.0}],
    }
    assert port.newest_deployment_version(json.dumps([old, new])) == "new"
    assert port.newest_deployment_version(json.dumps([new, old])) == "new"
    assert port.newest_deployment_version(json.dumps([old, split])) is None
    assert port.newest_deployment_version("[]") is None
    assert port.newest_deployment_version("not json") is None
    assert port.newest_deployment_version(json.dumps({"versions": []})) is None


def test_a_deploy_without_a_version_line_fails(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "edge", "--region", "eu", "--version", VERSION),
        FAKE_NO_VERSION_LINE="1",
    )
    assert proc.returncode == 1
    assert "printed no 'Current Version ID:' line" in proc.stderr
    assert "curl" not in calls


def test_a_listed_version_that_differs_from_the_printed_one_fails(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "edge", "--region", "eu", "--version", VERSION),
        FAKE_LISTED_ID="33333333-3333-4333-8333-333333333333",
    )
    assert proc.returncode == 1
    assert "names 33333333-3333-4333-8333-333333333333 at 100%" in proc.stderr
    assert "curl" not in calls
    assert "✓ Deployed" not in proc.stderr


def test_a_first_deploy_has_no_rollback_target(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    record = tmp_path / "record.json"
    proc, _calls = _run(
        tmp_path,
        root,
        ("--target", "edge", "--region", "asia", "--version", VERSION, "--record", str(record)),
        FAKE_NO_PREVIOUS="1",
    )
    assert proc.returncode == 0, proc.stderr
    assert "✓ Rollback: none: no earlier deployment of this Worker exists\n" in proc.stderr
    assert json.loads(record.read_text())["previous_version_id"] is None


# ---- the smoke and /v1/ready ------------------------------------------------


def test_a_ready_failure_exits_1_and_prints_no_closing_lines(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    record = tmp_path / "record.json"
    proc, calls = run_golden(
        tmp_path,
        root,
        "--target",
        "stable",
        "--region",
        "eu",
        "--version",
        VERSION,
        "--record",
        str(record),
        FAKE_READY_CODE="503",
        FAKE_READY_TIMEOUT="0",
    )
    assert proc.returncode == 1
    assert "✗ Smoke test failed: /v1/ready did not answer 200 on version %s" % NEW_ID in proc.stderr
    assert "issuer-refused" in proc.stderr
    assert "✓ Deployed" not in proc.stderr
    assert calls.endswith("/v1/ready\n")
    data = json.loads(record.read_text())
    assert data["smoke_rc"] == 1
    assert data["version_id"] == NEW_ID


def test_ready_on_the_old_version_is_not_ready(tmp_path: pathlib.Path) -> None:
    """The rollout started but an old instance answered: the smoke must not pass on it."""
    root = _fixture_root(tmp_path)
    proc, _calls = _run(
        tmp_path,
        root,
        ("--target", "edge", "--region", "us", "--version", VERSION),
        FAKE_READY_VERSION=PREV_ID,
        FAKE_READY_TIMEOUT="0",
    )
    assert proc.returncode == 1
    assert "ready on version %s, not %s" % (PREV_ID, NEW_ID) in proc.stderr


def test_ready_is_polled_until_the_new_version_answers(monkeypatch) -> None:
    answers = iter(
        [
            (json.dumps({"ready": False, "reason": "issuer-refused"}), "503"),
            (json.dumps({"ready": True, "workerVersion": "old"}), "200"),
            (json.dumps({"ready": True, "workerVersion": "new"}), "200"),
        ]
    )
    sleeps: list[float] = []
    monkeypatch.setattr(port, "_curl_body", lambda _url, _pin=None: next(answers))
    monkeypatch.setattr(port, "_sleep", sleeps.append)
    assert (
        port.wait_ready(port._Fetcher("proxy.test.example"), "https://proxy.test.example", "new")
        == 0
    )
    assert sleeps == [port.READY_INTERVAL_S, port.READY_INTERVAL_S]


def test_an_unhealthy_deploy_fails_the_smoke_before_server_info(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "edge", "--region", "eu", "--version", VERSION),
        FAKE_HEALTH="503",
    )
    assert proc.returncode == 1
    assert "✗ Smoke test failed: /v1/health answered 503, expected 200\n" in proc.stderr
    assert "/v1/server-info" not in calls


def test_an_open_server_info_fails_the_smoke_before_ready(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "edge", "--region", "eu", "--version", VERSION),
        FAKE_INFO="200",
    )
    assert proc.returncode == 1
    assert "an unauthenticated /v1/server-info answered 200, expected 401" in proc.stderr
    assert "/v1/ready" not in calls


def test_a_failed_fetch_deploys_nothing(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "edge", "--region", "eu", "--version", VERSION),
        FAKE_CHILD_RC="3",
    )
    assert proc.returncode == 3
    assert "wrangler" not in calls


def test_a_failed_deploy_prints_no_closing_lines(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "edge", "--region", "eu", "--version", VERSION),
        FAKE_NPX_RC="6",
    )
    assert proc.returncode == 6
    assert "✓ Deployed" not in proc.stderr
    assert "curl" not in calls


# ---- the record and --smoke-only --------------------------------------------


def test_the_record_carries_what_a_rollback_needs(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    record = tmp_path / "out" / "record.json"
    proc, _calls = _run(
        tmp_path,
        root,
        ("--target", "edge", "--region", "us", "--version", VERSION, "--record", str(record)),
    )
    assert proc.returncode == 0, proc.stderr
    written = json.loads(record.read_text())
    assert isinstance(written.pop("cold_start_ms"), int)
    assert written == {
        "release_by_version": {NEW_ID: VERSION},
        "target": "edge",
        "region": "us",
        "worker": "edge-rediacc-proxy-us",
        "config": "workers/proxy/wrangler.edge-us.toml",
        "version_id": NEW_ID,
        "previous_version_id": PREV_ID,
        "artifacts_version": VERSION,
        "smoke_rc": 0,
        "rollback": "cd workers/proxy && npx --no-install wrangler rollback %s --config wrangler.edge-us.toml"
        % PREV_ID,
        "backend": "container",
        "migration_tag": "v2",
        "var_overrides": {},
    }


def _previous_config(
    tmp_path: pathlib.Path, root: pathlib.Path, config: str, migrations: str
) -> str:
    """A copy of `config` whose `[[migrations]]` tables are replaced by `migrations`: the previous release's file."""
    text = (root / "workers" / "proxy" / config).read_text(encoding="utf-8")
    head = text[: text.index("[[migrations]]")]
    tail = text[text.index("# Telemetry export") :]
    path = tmp_path / "previous.toml"
    path.write_text(head + migrations + "\n" + tail, encoding="utf-8")
    return str(path)


V1 = '[[migrations]]\ntag = "v1"\nnew_sqlite_classes = ["ExecutorContainer"]\n'
V2 = V1 + '\n[[migrations]]\ntag = "v2"\nnew_sqlite_classes = ["OrgExecutor", "ExecutorCapacity"]\n'


def test_a_v1_to_v2_deploy_is_forward_only(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    record = tmp_path / "record.json"
    previous = _previous_config(tmp_path, root, "wrangler.edge-us.toml", V1)
    proc, _calls = _run(
        tmp_path,
        root,
        ("--target", "edge", "--region", "us", "--version", VERSION, "--record", str(record)),
        FAKE_PREV_CONFIG=previous,
    )
    assert proc.returncode == 0, proc.stderr
    want = "forward-only: Durable Object class lifecycle change (v2); fix forward"
    written = json.loads(record.read_text())
    assert written["rollback"] == want
    assert written["migration_tag"] == "v2"
    assert written["previous_version_id"] == PREV_ID
    assert "Rollback: " + want + "\n" in proc.stderr
    assert "wrangler rollback" not in proc.stderr


def test_a_v2_to_v2_deploy_writes_the_rollback_command(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    record = tmp_path / "record.json"
    previous = _previous_config(tmp_path, root, "wrangler.edge-us.toml", V2)
    proc, _calls = _run(
        tmp_path,
        root,
        ("--target", "edge", "--region", "us", "--version", VERSION, "--record", str(record)),
        FAKE_PREV_CONFIG=previous,
    )
    assert proc.returncode == 0, proc.stderr
    want = (
        "cd workers/proxy && npx --no-install wrangler rollback %s --config wrangler.edge-us.toml"
    )
    assert json.loads(record.read_text())["rollback"] == want % PREV_ID
    assert "forward-only" not in proc.stderr


def test_a_deploy_with_no_previous_release_config_is_not_forward_only(
    tmp_path: pathlib.Path,
) -> None:
    root = _fixture_root(tmp_path)
    record = tmp_path / "record.json"
    proc, _calls = _run(
        tmp_path,
        root,
        ("--target", "edge", "--region", "us", "--version", VERSION, "--record", str(record)),
    )
    assert proc.returncode == 0, proc.stderr
    assert "forward-only" not in json.loads(record.read_text())["rollback"]


def _tagged_repo(tmp_path: pathlib.Path, tags: tuple[str, ...]) -> pathlib.Path:
    repo = tmp_path / "tagged"
    repo.mkdir()
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "tag.gpgsign=false"]
    subprocess.run([*git, "init", "-q"], cwd=repo, env=env, check=True)
    subprocess.run(
        [*git, "commit", "-q", "--allow-empty", "-m", "x"], cwd=repo, env=env, check=True
    )
    for tag in tags:
        subprocess.run([*git, "tag", tag], cwd=repo, env=env, check=True)
    return repo


def test_the_previous_release_tag_is_older_than_the_release_not_just_different(
    tmp_path: pathlib.Path,
) -> None:
    repo = _tagged_repo(tmp_path, ("v1.2.0", "v1.3.0", "v1.10.0"))
    assert port.previous_release_tag(repo, "1.3.0") == "v1.2.0"
    assert port.previous_release_tag(repo, "1.10.0") == "v1.3.0"
    assert port.previous_release_tag(repo, "1.2.0") is None
    assert port.previous_release_tag(repo, "2.0.0") == "v1.10.0"
    assert port.previous_release_tag(tmp_path / "nowhere", "2.0.0") is None


def test_an_untagged_release_older_than_the_newest_tag_compares_against_its_own_line(
    tmp_path: pathlib.Path,
) -> None:
    """c7233ce0.2: an untagged hotfix 1.2.5 with v1.3.0 present is older than v1.3.0, so its previous release is v1.2.0."""
    repo = _tagged_repo(tmp_path, ("v1.2.0", "v1.3.0"))
    assert port.previous_release_tag(repo, "1.2.5") == "v1.2.0"
    assert port.previous_release_tag(repo, "1.3.1") == "v1.3.0"
    assert port.previous_release_tag(repo, "1.1.9") is None
    assert port.previous_release_tag(repo, "not-a-version") == "v1.3.0"
    assert port.previous_release_tag(repo, None) == "v1.3.0"


def test_a_shallow_checkout_is_named_not_silently_treated_as_a_first_release(
    tmp_path: pathlib.Path,
) -> None:
    full = _tagged_repo(tmp_path, ("v1.0.0",))
    shallow = tmp_path / "shallow"
    subprocess.run(
        ["git", "clone", "-q", "--depth", "1", "file://%s" % full, str(shallow)],
        check=True,
        env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull},
    )
    assert port.shallow_checkout(shallow) is True
    assert port.shallow_checkout(full) is False
    assert port.shallow_checkout(tmp_path / "nowhere") is False


def test_bench_is_forward_only_when_its_recorded_migration_tag_differs(
    tmp_path: pathlib.Path,
) -> None:
    root = _fixture_root(tmp_path)
    record = tmp_path / "record.json"
    args = ("--target", "bench", "--record", str(record))
    for recorded, forward in (("v1", True), ("v2", False)):
        record.write_text(json.dumps({"migration_tag": recorded}), encoding="utf-8")
        proc, _calls = _run(tmp_path, root, args, drop_env=(), **BENCH_PROFILE_ENV)
        assert proc.returncode == 0, proc.stderr
        written = json.loads(record.read_text())
        assert written["migration_tag"] == "v2"
        assert written["rollback"].startswith("forward-only:") is forward


def test_the_forward_only_rule_compares_whole_migration_lists() -> None:
    v1 = port.config_migrations(V1)
    v2 = port.config_migrations(V2)
    assert port.is_forward_only(v2, v1)
    assert port.is_forward_only(v1, v2)
    assert not port.is_forward_only(v2, v2)
    assert not port.is_forward_only(v2, None)
    assert port.migration_tag(v2) == "v2"
    assert port.migration_tag([]) is None


def test_smoke_only_smokes_the_recorded_version_and_deploys_nothing(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    record = tmp_path / "record.json"
    record.write_text(json.dumps({"version_id": NEW_ID, "target": "edge"}), encoding="utf-8")
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "edge", "--region", "us", "--smoke-only", "--record", str(record)),
    )
    assert proc.returncode == 0, proc.stderr
    assert calls == (
        f"{CURL}https://{PROXY_EDGE_US_HOST}/v1/health\n"
        f"{CURL}https://{PROXY_EDGE_US_HOST}/v1/server-info\n"
        f"{CURL_BODY}https://{PROXY_EDGE_US_HOST}/v1/ready\n"
    )
    data = json.loads(record.read_text())
    assert data["smoke_rc"] == 0
    assert data["target"] == "edge", "the deploy step's fields are kept"


def test_smoke_only_without_a_record_reads_the_newest_deployment(tmp_path: pathlib.Path) -> None:
    """With no record the newest deployment is the version to smoke; here that is the previous one, so the ready check expects PREV_ID."""
    root = _fixture_root(tmp_path)
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "stable", "--region", "asia", "--smoke-only"),
        FAKE_READY_VERSION=PREV_ID,
    )
    assert proc.returncode == 0, proc.stderr
    assert calls.startswith(
        "npx\t--no-install\twrangler\tdeployments\tlist\t--json\t--config\twrangler.asia.toml\n"
    )
    assert "on version %s." % PREV_ID in proc.stderr


# ---- no executor token, anywhere --------------------------------------------


def test_no_closing_line_names_executor_token(tmp_path: pathlib.Path) -> None:
    """The Worker mints its own token over ISSUER (operator ruling 2026-10-25T19:08Z), so a deploy never tells a human to put one."""
    root = _fixture_root(tmp_path)
    for target, region in (("edge", "eu"), ("stable", "us")):
        proc, _calls = _run(
            tmp_path, root, ("--target", target, "--region", region, "--version", VERSION)
        )
        assert proc.returncode == 0, proc.stderr
        assert "EXECUTOR_TOKEN" not in proc.stderr + proc.stdout
    proc, _calls = _run(
        tmp_path, root, ("--target", "bench"), REDIACC_BWS_PROFILES="deploy-proxy-bench"
    )
    assert proc.returncode == 0, proc.stderr
    assert "EXECUTOR_TOKEN" not in proc.stderr + proc.stdout
    for line in port.closing_lines("w", "v", "r"):
        assert "EXECUTOR_TOKEN" not in line
    assert "EXECUTOR_TOKEN" not in (ROOT / ".ci/rediacc_ci/deploy/deploy_proxy.py").read_text()


def test_the_docstring_cites_the_operator_order_and_no_longer_says_manual_only() -> None:
    doc = port.__doc__ or ""
    assert "operator order 2026-10-25T18:10Z" in doc
    assert "CD deploys it" in doc.replace("CD DEPLOYS IT", "CD deploys it")
    assert "MANUAL ONLY" not in doc


def test_diagnostics_are_prefixed_with_the_module_name() -> None:
    assert port.SELF == "rediacc_ci.deploy.deploy_proxy"
    assert port.__name__ == port.SELF


# ---- the Bitwarden profiles -------------------------------------------------


def _profiles() -> dict:
    return json.loads((ROOT / ".ci" / "config" / "secret-supply.json").read_text(encoding="utf-8"))[
        "consumers"
    ]


def test_the_bench_profile_binds_the_production_public_key_and_the_workers_token() -> None:
    """Bench signs licences with the production key (operator ruling 2026-10-27), so its proxy renet verifies with it."""
    profile = _profiles()[port.BENCH_PROFILE]
    assert set(profile["required"]) == {
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "ACCOUNT_ED25519_PUBLIC_KEY",
    }
    assert "EXECUTOR_TOKEN" not in profile["why"]


def test_the_deploy_proxy_profile_binds_the_production_key_and_the_artifact_reader() -> None:
    profile = _profiles()[port.PROFILE]
    assert {
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_ACCOUNT_ID",
        "ACCOUNT_ED25519_PUBLIC_KEY",
    } <= set(profile["required"])
    assert "ACCOUNT_ED25519_PUBLIC_KEY_DEV" not in " ".join(
        profile["required"] + profile["optional"]
    )


def test_the_live_console_profile_exists() -> None:
    profile = _profiles()["live-console"]
    assert profile["why"].strip()
    assert profile["required"] or profile["optional"]


# ---- the account and proxy bindings agree ------------------------------------


def test_the_eu_account_worker_binds_the_eu_proxy_and_the_proxy_binds_back() -> None:
    """Review fa7742a0.1: a dropped or misnamed binding on either side fails here rather than in a deploy."""
    account = tomllib.loads((ROOT / "workers" / "account" / "wrangler.eu.toml").read_text())
    proxy = tomllib.loads((PROXY_DIR / "wrangler.eu.toml").read_text())
    executor = [s for s in account.get("services", []) if s.get("binding") == "EXECUTOR"]
    assert [s.get("service") for s in executor] == [proxy["name"]]
    back = [s for s in proxy.get("services", []) if s.get("binding") == "ACCOUNT"]
    assert [s.get("service") for s in back] == [account["name"]]
    assert back[0].get("entrypoint") == "CloudflareInternal"


# ---- the smoke survives a fresh domain's cached NXDOMAIN ---------------------


def _clock(monkeypatch, ticks: list[float]) -> None:
    """Replace the module's `time` with a scripted monotonic clock, so the retry window is exact."""
    monkeypatch.setenv(port.RESOLVE_WINDOW_ENV, "50")
    monkeypatch.setattr(
        port, "time", types.SimpleNamespace(monotonic=iter(ticks).__next__, sleep=lambda _s: None)
    )


class _Curl:
    """A scripted `_curl`: answers per call, in order, as (code, rc); the last repeats. Records (url, pin)."""

    def __init__(self, answers: list[tuple[str, int]]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, str | None]] = []

    def __call__(self, url: str, pin: str | None = None) -> tuple[str, int]:
        self.calls.append((url, pin))
        return self.answers[min(len(self.calls), len(self.answers)) - 1]


def _smoke_fixture(monkeypatch, answers, doh=None):
    fake = _Curl(answers)
    sleeps: list[float] = []
    monkeypatch.setattr(port, "_curl", fake)
    monkeypatch.setattr(port, "_sleep", sleeps.append)
    monkeypatch.setattr(port, "_doh_lookup", lambda _host: doh)
    monkeypatch.setattr(port, "wait_ready", lambda _fetch, _url, _version, _timing=None: 0)
    monkeypatch.setenv(port.RESOLVE_WINDOW_ENV, "1000")
    monkeypatch.setenv(port.DOH_URL_ENV, "https://doh.invalid/dns-query")
    return fake, sleeps


HOST = "proxy.test.example"


@pytest.mark.parametrize("value", ["inf", "-inf", "nan", "x"])
def test_a_non_finite_resolve_window_falls_back_to_the_default(monkeypatch, value) -> None:
    monkeypatch.setenv(port.RESOLVE_WINDOW_ENV, value)
    assert port._resolve_window() == float(port.DEFAULT_RESOLVE_WINDOW_S)


def test_persistent_nxdomain_with_doh_disabled_still_says_it_does_not_resolve(
    monkeypatch, capsys
) -> None:
    _smoke_fixture(monkeypatch, [("000", 6)])
    monkeypatch.setenv(port.DOH_URL_ENV, "")
    _clock(monkeypatch, [0.0, 100.0])
    assert port.smoke(HOST, NEW_ID) == 1
    assert "does not resolve locally" in capsys.readouterr().err


def test_nxdomain_then_ok_passes_without_a_pin(monkeypatch) -> None:
    fake, sleeps = _smoke_fixture(monkeypatch, [("000", 6), ("200", 0), ("401", 0)])
    assert port.smoke(HOST, NEW_ID) == 0
    assert [pin for _, pin in fake.calls] == [None, None, None]
    assert sleeps == [port.RESOLVE_INTERVAL_S]


def test_persistent_nxdomain_with_a_doh_answer_passes_through_a_pin(monkeypatch) -> None:
    fake, _ = _smoke_fixture(monkeypatch, [("000", 6), ("200", 0), ("401", 0)], doh="203.0.113.7")
    _clock(monkeypatch, [0.0, 100.0, 200.0])
    assert port.smoke(HOST, NEW_ID) == 0
    assert [pin for _, pin in fake.calls] == [None, "203.0.113.7", "203.0.113.7"]
    url = "https://proxy.test.example/v1/health"
    assert port.curl_argv(url, "203.0.113.7")[-3:] == [
        "--resolve",
        "proxy.test.example:443:203.0.113.7",
        url,
    ]
    assert port.curl_body_argv(url, "203.0.113.7")[-3:-1] == [
        "--resolve",
        "proxy.test.example:443:203.0.113.7",
    ]
    assert "--resolve" not in port.curl_argv(url)


def test_a_500_fails_at_once_without_retry(monkeypatch, capsys) -> None:
    fake, sleeps = _smoke_fixture(monkeypatch, [("500", 0)])
    assert port.smoke(HOST, NEW_ID) == 1
    assert len(fake.calls) == 1
    assert sleeps == []
    assert "/v1/health answered 500, expected 200" in capsys.readouterr().err


def test_persistent_resolution_failure_fails_with_a_clear_message(monkeypatch, capsys) -> None:
    _smoke_fixture(monkeypatch, [("000", 6)], doh=None)
    _clock(monkeypatch, [0.0, 100.0])
    assert port.smoke(HOST, NEW_ID) == 1
    err = capsys.readouterr().err
    assert "does not resolve locally" in err
    assert "DNS-over-HTTPS has no answer" in err
    assert "answered 000, expected 200" in err


def test_the_doh_lookup_reads_the_first_a_record(monkeypatch) -> None:
    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps(
                {"Answer": [{"type": 5, "data": "x."}, {"type": 1, "data": "198.51.100.9"}]}
            ).encode()

    seen = {}

    def fake_open(request, **_kw):
        seen["url"] = request.full_url
        return Resp()

    monkeypatch.setattr(port.https, "urlopen", fake_open)
    monkeypatch.delenv(port.DOH_URL_ENV, raising=False)
    assert port._doh_lookup("proxy.test.example") == "198.51.100.9"
    assert "name=proxy.test.example" in seen["url"]


# ---- --rollback <version-id> ------------------------------------------------

# The version a drill rolls back to; the fake lists it at 100% once `wrangler rollback` has run.
TO_ID = "33333333-3333-4333-8333-333333333333"


def _rollback_calls(config: str, host: str, version_id: str) -> str:
    return (
        f"npx\t--no-install\twrangler\tdeployments\tlist\t--json\t--config\t{config}\n"
        "  cwd=proxy\n"
        f"npx\t--no-install\twrangler\tversions\tview\t{version_id}\t--json\t--config\t{config}\n"
        "  cwd=proxy\n"
        f"npx\t--no-install\twrangler\trollback\t{version_id}\t--message\t"
        f"{port.ROLLBACK_MESSAGE}\t--yes\t--config\t{config}\n"
        "  cwd=proxy\n"
        f"npx\t--no-install\twrangler\tdeployments\tlist\t--json\t--config\t{config}\n"
        "  cwd=proxy\n"
        f"{CURL}https://{host}/v1/health\n"
        f"{CURL}https://{host}/v1/server-info\n"
        f"{CURL_BODY}https://{host}/v1/ready\n"
    )


def test_a_bench_rollback_runs_wrangler_rollback_smokes_and_records(
    tmp_path: pathlib.Path,
) -> None:
    """The bench config, `wrangler rollback <id> --message --yes`, the listing cross-check, the smoke on that id, and the same record with `rolled_back: true`. Nothing is built, fetched or staged."""
    root = _fixture_root(tmp_path)
    record = tmp_path / "record.json"
    record.write_text(json.dumps({"migration_tag": "v2", "version_id": PREV_ID}), encoding="utf-8")
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "bench", "--rollback", TO_ID, "--record", str(record)),
        FAKE_LISTED_ID=TO_ID,
        FAKE_READY_VERSION=TO_ID,
        REDIACC_BWS_PROFILES=port.BENCH_PROFILE,
    )
    assert proc.returncode == 0, proc.stderr
    assert calls == _rollback_calls("wrangler.bench.toml", PROXY_BENCH_HOST, TO_ID)
    written = json.loads(record.read_text())
    assert isinstance(written.pop("cold_start_ms"), int)
    assert written == {
        "target": "bench",
        "region": "eu",
        "worker": "rediacc-proxy-bench",
        "config": "workers/proxy/wrangler.bench.toml",
        "rolled_back": True,
        "version_id": TO_ID,
        "requested_version_id": TO_ID,
        "previous_version_id": PREV_ID,
        "artifacts_version": None,
        "smoke_rc": 0,
        "rollback": "cd workers/proxy && npx --no-install wrangler rollback %s --config wrangler.bench.toml"
        % PREV_ID,
        "backend": "container",
        "migration_tag": "v2",
        "var_overrides": {},
    }
    assert "✓ Rolled back rediacc-proxy-bench: version %s.\n" % TO_ID in proc.stderr
    assert "Deployed" not in proc.stderr


def test_a_stable_rollback_uses_the_stable_config(tmp_path: pathlib.Path) -> None:
    """Every target may roll back, against the config it deploys with; no `--version` is needed."""
    root = _fixture_root(tmp_path)
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "stable", "--region", "us", "--rollback", TO_ID),
        FAKE_LISTED_ID=TO_ID,
        FAKE_READY_VERSION=TO_ID,
    )
    assert proc.returncode == 0, proc.stderr
    assert calls == _rollback_calls("wrangler.us.toml", PROXY_US_HOST, TO_ID)


def test_a_rollback_whose_smoke_fails_exits_1_and_records_it(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    record = tmp_path / "record.json"
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "bench", "--rollback", TO_ID, "--record", str(record)),
        FAKE_LISTED_ID=TO_ID,
        FAKE_READY_VERSION=TO_ID,
        FAKE_READY_CODE="503",
        FAKE_READY_TIMEOUT="0",
        REDIACC_BWS_PROFILES=port.BENCH_PROFILE,
    )
    assert proc.returncode == 1
    assert "✗ Smoke test failed: /v1/ready did not answer 200 on version %s" % TO_ID in proc.stderr
    assert "✗ Rollback: cd workers/proxy && npx --no-install wrangler rollback %s" % PREV_ID in (
        proc.stderr
    )
    assert "Rolled back" not in proc.stderr
    assert calls.endswith("/v1/ready\n")
    data = json.loads(record.read_text())
    assert (data["rolled_back"], data["smoke_rc"], data["version_id"]) == (True, 1, TO_ID)


def test_a_rollback_the_listing_does_not_confirm_fails_before_the_smoke(
    tmp_path: pathlib.Path,
) -> None:
    root = _fixture_root(tmp_path)
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "bench", "--rollback", TO_ID),
        FAKE_LISTED_ID=PREV_ID,
        REDIACC_BWS_PROFILES=port.BENCH_PROFILE,
    )
    assert proc.returncode == 1
    assert "names %s at 100%%" % PREV_ID in proc.stderr
    assert "curl" not in calls


def test_a_failed_wrangler_rollback_propagates_and_smokes_nothing(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    record = tmp_path / "record.json"
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "bench", "--rollback", TO_ID, "--record", str(record)),
        FAKE_NPX_RC="3",
        REDIACC_BWS_PROFILES=port.BENCH_PROFILE,
    )
    assert proc.returncode == 3
    assert "curl" not in calls
    assert not record.exists()


@pytest.mark.parametrize(
    ("extra", "fragment"),
    [
        ((), "--rollback '0ac1523d' is not a full Worker version id"),
        (("--dry-run",), "--rollback refuses --dry-run"),
        (("--smoke-only",), "--rollback refuses --smoke-only"),
        (("--version", VERSION), "--rollback refuses --version"),
        (("--var", "EXECUTOR_BACKEND=container"), "--rollback refuses --var"),
    ],
    ids=["short-id", "dry-run", "smoke-only", "version", "var"],
)
def test_rollback_refusals_need_no_token_and_run_nothing(
    tmp_path: pathlib.Path, extra: tuple[str, ...], fragment: str
) -> None:
    """A `--dry-run` beside `--rollback` is refused, not obeyed: the release guard admits any `--dry-run` of this module, so a dry run that rolled back stable would publish unasked."""
    root = _fixture_root(tmp_path)
    rollback_to = "0ac1523d" if not extra else TO_ID
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "bench", "--rollback", rollback_to, *extra),
        drop_env=("CLOUDFLARE_API_TOKEN",),
        REDIACC_BWS_PROFILES=port.BENCH_PROFILE,
    )
    assert proc.returncode == 1, proc.stderr
    assert calls == ""
    assert proc.stderr.startswith("✗ "), proc.stderr
    assert fragment in proc.stderr, proc.stderr


GUARD_DISPATCH = ROOT / ".claude" / "rediacc_hooks" / "dispatch.py"
GUARD_STEM = "block_unasked_release"


def _guard(command: str) -> subprocess.CompletedProcess:
    """One agent Bash payload through the real pre-bash release guard, with no transcript, so no ASKED minute can be proven."""
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(ROOT))
    env.pop("RELEASE_ASKED", None)
    payload = {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(ROOT)}
    proc = subprocess.run(
        [sys.executable, str(GUARD_DISPATCH), GUARD_STEM],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        env=env,
        cwd=str(ROOT),
        timeout=60,
    )
    assert proc.returncode in (0, 2), "the guard crashed (rc %d): %s" % (
        proc.returncode,
        proc.stderr[-800:],
    )
    return proc


@pytest.mark.parametrize(
    "prefix",
    ["", "RELEASE_ASKED=ASKED:2026-01-01T00:00Z ", "RELEASE_ASKED=yes "],
    ids=["no-ask", "unproven-ask", "malformed-ask"],
)
def test_a_stable_rollback_is_held_by_the_same_ask_as_a_stable_deploy(prefix: str) -> None:
    """The stable deploy path's guard is `block_unasked_release`, which judges this module by its `--target`: a stable rollback is refused without a proven RELEASE_ASKED exactly as the stable deploy beside it is, and the bench rollback is free in the same run (both directions)."""
    py = "PYTHONPATH=.ci python3 -m %s" % port.SELF
    stable_deploy = _guard("%s%s --target stable --region eu --version %s" % (prefix, py, VERSION))
    stable_rollback = _guard("%s%s --target stable --region eu --rollback %s" % (prefix, py, TO_ID))
    bench_rollback = _guard("%s --target bench --rollback %s" % (py, TO_ID))
    assert stable_deploy.returncode == 2, "control: the stable deploy itself must be refused"
    assert stable_rollback.returncode == 2, stable_rollback.stderr
    assert "deploy_proxy (a stable target)" in stable_rollback.stderr
    assert "RELEASE_ASKED" in stable_rollback.stderr
    assert bench_rollback.returncode == 0, bench_rollback.stderr


def test_the_raw_wrangler_rollback_on_bench_stays_refused() -> None:
    """The sanctioned path is this module: the guard keeps refusing the raw verb it replaces."""
    proc = _guard(
        "cd workers/proxy && npx wrangler rollback %s --config wrangler.bench.toml" % TO_ID
    )
    assert proc.returncode == 2
    assert "a raw publish verb" in proc.stderr


def test_the_new_options_keep_target_the_only_t_option() -> None:
    """The guard reads `--target` by any `--t...` prefix and is sound only while no other long option starts with `--t`."""
    longs = [o for a in port._parser()._actions for o in a.option_strings if o.startswith("--")]
    assert "--rollback" in longs
    assert "--var" in longs
    assert [o for o in longs if o.startswith("--t")] == ["--target"]


# ---- --var KEY=VALUE --------------------------------------------------------


@pytest.mark.parametrize(
    ("target", "region"),
    [("edge", "eu"), ("stable", "eu")],
)
@pytest.mark.parametrize("dry_run", [False, True], ids=["deploy", "dry-run"])
def test_var_is_refused_off_bench(
    tmp_path: pathlib.Path, target: str, region: str, dry_run: bool
) -> None:
    root = _fixture_root(tmp_path)
    args = ["--target", target, "--region", region, "--var", "EXECUTOR_BACKEND=durable"]
    args += ["--dry-run"] if dry_run else ["--version", VERSION]
    proc, calls = _run(tmp_path, root, tuple(args))
    assert proc.returncode == 1, proc.stderr
    assert calls == ""
    assert "--var is refused on --target %s" % target in proc.stderr


def test_var_reaches_wrangler_deploy_as_its_own_var_flag_and_is_recorded(
    tmp_path: pathlib.Path,
) -> None:
    """`--var KEY=VALUE` becomes wrangler's `--var KEY:VALUE`, in order, the toml is not touched, and the record names the overrides and the overridden backend."""
    root = _fixture_root(tmp_path)
    config = root / "workers" / "proxy" / "wrangler.bench.toml"
    before = config.read_bytes()
    record = tmp_path / "record.json"
    proc, calls = _run(
        tmp_path,
        root,
        (
            "--target",
            "bench",
            "--var",
            "EXECUTOR_BACKEND=container",
            "--var",
            "EXECUTOR_CAP=2",
            "--record",
            str(record),
        ),
        REDIACC_BWS_PROFILES=port.BENCH_PROFILE,
    )
    assert proc.returncode == 0, proc.stderr
    assert (
        "npx\t--no-install\twrangler\tdeploy\t--var\tEXECUTOR_BACKEND:container\t"
        "--var\tEXECUTOR_CAP:2\t--config\twrangler.bench.toml\n"
    ) in calls
    assert config.read_bytes() == before, "the toml must never be rewritten"
    data = json.loads(record.read_text())
    assert data["var_overrides"] == {"EXECUTOR_BACKEND": "container", "EXECUTOR_CAP": "2"}
    assert data["backend"] == "container", "the record names the overridden backend"


def test_a_colon_in_a_var_value_survives_wranglers_first_colon_split() -> None:
    assert port.var_args({"K": "a:b:c"}) == ["--var", "K:a:b:c"]


@pytest.mark.parametrize(
    ("word", "fragment"),
    [
        (
            "ACCOUNT_URL=https://evil.example",
            "vars.ACCOUNT_URL is 'https://evil.example', not 'https://bench.rediacc.com'",
        ),
        ("ENVIRONMENT=production", "vars.ENVIRONMENT is 'production', not 'bench'"),
        ("EXECUTOR_CAP=99", "vars.EXECUTOR_CAP is '99', over the ceiling of 25"),
        ("EXECUTOR_BACKEND=lambda", "vars.EXECUTOR_BACKEND is 'lambda', not one of"),
        ("EXECUTOR_CAP=EXECUTOR_TOKEN", "the token comes from the ISSUER binding"),
    ],
    ids=["account-url", "environment", "cap-over-ceiling", "unknown-backend", "token-text"],
)
@pytest.mark.parametrize("dry_run", [False, True], ids=["deploy", "dry-run"])
def test_a_var_the_config_refusals_reject_is_refused_before_anything_runs(
    tmp_path: pathlib.Path, word: str, fragment: str, dry_run: bool
) -> None:
    """An override passes exactly the gate the toml passes: `config_refusals` judges the config as the overrides leave it, so a `--var` cannot deploy a host, environment or cap the config could not carry."""
    root = _fixture_root(tmp_path)
    args = ("--target", "bench", "--var", word, *(("--dry-run",) if dry_run else ()))
    proc, calls = _run(
        tmp_path,
        root,
        args,
        drop_env=("CLOUDFLARE_API_TOKEN",),
        REDIACC_BWS_PROFILES=port.BENCH_PROFILE,
    )
    assert proc.returncode == 1, proc.stderr
    assert calls == ""
    assert "--var %s refused: " % word.partition("=")[0] in proc.stderr, proc.stderr
    assert fragment in proc.stderr, proc.stderr


def test_the_rendered_override_parses_back_to_exactly_the_overridden_vars() -> None:
    text = (PROXY_DIR / "wrangler.bench.toml").read_text(encoding="utf-8")
    rendered = port.with_var_overrides(text, {"EXECUTOR_CAP": '2" # "x\\'})
    assert rendered is not None
    got = tomllib.loads(rendered)
    assert got["vars"]["EXECUTOR_CAP"] == '2" # "x\\'
    assert {k: v for k, v in got.items() if k != "vars"} == {
        k: v for k, v in tomllib.loads(text).items() if k != "vars"
    }
    inline = 'name = "w"\nvars = { EXECUTOR_CAP = "25" }\n'
    assert port.with_var_overrides(inline, {"EXECUTOR_CAP": "2"}) is None


def test_var_reaches_the_bench_dry_run_too(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "bench", "--var", "EXECUTOR_CAP=3", "--dry-run"),
        drop_env=("CLOUDFLARE_API_TOKEN",),
    )
    assert proc.returncode == 0, proc.stderr
    assert calls == (
        "npx\t--no-install\twrangler\tdeploy\t--dry-run\t--outdir\t%s\t--containers-rollout\tnone\t"
        "--var\tEXECUTOR_CAP:3\t--config\twrangler.bench.toml\n  cwd=proxy\n" % port.DRY_RUN_OUTDIR
    )


@pytest.mark.parametrize(
    ("words", "fragment"),
    [
        (("EXECUTOR_BACKEND",), "--var 'EXECUTOR_BACKEND' is not KEY=VALUE"),
        (("=durable",), "--var '=durable' is not KEY=VALUE"),
        (("1BAD=x",), "--var '1BAD=x' is not KEY=VALUE"),
        (("EXECUTOR:BACKEND=x",), "--var 'EXECUTOR:BACKEND=x' is not KEY=VALUE"),
        (("EXECUTOR_BAKEND=durable",), "has no [vars] key EXECUTOR_BAKEND"),
        (("EXECUTOR_CAP=1", "EXECUTOR_CAP=2"), "--var EXECUTOR_CAP is given twice"),
    ],
    ids=["no-equals", "no-key", "digit-key", "colon-key", "unknown-key", "repeated"],
)
def test_a_malformed_var_is_refused_before_anything_runs(
    tmp_path: pathlib.Path, words: tuple[str, ...], fragment: str
) -> None:
    root = _fixture_root(tmp_path)
    args: list[str] = ["--target", "bench"]
    for word in words:
        args += ["--var", word]
    proc, calls = _run(
        tmp_path,
        root,
        tuple(args),
        drop_env=("CLOUDFLARE_API_TOKEN",),
        REDIACC_BWS_PROFILES=port.BENCH_PROFILE,
    )
    assert proc.returncode == 1, proc.stderr
    assert calls == ""
    assert fragment in proc.stderr, proc.stderr


def test_var_is_refused_with_smoke_only(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "bench", "--smoke-only", "--var", "EXECUTOR_CAP=3"),
        REDIACC_BWS_PROFILES=port.BENCH_PROFILE,
    )
    assert proc.returncode == 1
    assert calls == ""
    assert "--var is refused with --smoke-only" in proc.stderr


def test_help_names_both_new_options() -> None:
    text = port._parser().format_help()
    assert "--rollback VERSION_ID" in text
    assert "--var KEY=VALUE" in text


# ---- review 4a915178: the rollback's revert line, id case and failure record ----


@pytest.mark.parametrize(("recorded", "forward"), [("v1", True), ("v2", False)])
def test_a_rollback_consults_the_forward_only_check_for_its_revert_line(
    tmp_path: pathlib.Path, recorded: str, forward: bool
) -> None:
    """The same check a deploy makes: bench's config is at v2, so a record at v1 makes the revert forward-only and a record at v2 leaves the plain command (review 4a915178.2)."""
    root = _fixture_root(tmp_path)
    record = tmp_path / "record.json"
    record.write_text(json.dumps({"migration_tag": recorded}), encoding="utf-8")
    proc, _calls = _run(
        tmp_path,
        root,
        ("--target", "bench", "--rollback", TO_ID, "--record", str(record)),
        FAKE_LISTED_ID=TO_ID,
        FAKE_READY_VERSION=TO_ID,
        REDIACC_BWS_PROFILES=port.BENCH_PROFILE,
    )
    assert proc.returncode == 0, proc.stderr
    written = json.loads(record.read_text())
    if forward:
        want = "forward-only: Durable Object class lifecycle change (v2); fix forward"
        assert written["rollback"] == want
        assert "Rollback: %s\n" % want in proc.stderr
    else:
        assert written["rollback"].startswith("cd workers/proxy && npx --no-install wrangler")
    assert written["migration_tag"] == recorded, "a rollback undoes no migration"


def test_the_shared_forward_only_check_reads_the_previous_release_off_bench(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    worker = root / "workers" / "proxy"
    v1 = port.config_migrations(V1)
    monkeypatch.setattr(port, "previous_release_migrations", lambda *_a: v1)
    monkeypatch.setattr(port, "shallow_checkout", lambda _r: False)
    state = port.forward_only_state(
        root, worker, "wrangler.edge-us.toml", bench=False, record_path=None, version=None
    )
    assert state == (True, "v2")
    assert port.revert_line("c", PREV_ID, True, "v2").startswith("forward-only:")
    assert port.revert_line("c", None, True, "v2").startswith("none:")


UPPER_ID = "ABCDEF01-2345-4678-9ABC-DEF012345678"


def test_an_uppercase_rollback_id_is_lowercased_for_wrangler_the_smoke_and_the_record(
    tmp_path: pathlib.Path,
) -> None:
    """`wrangler deployments list` and `/v1/ready` print lowercase ids (review 4a915178.3)."""
    root = _fixture_root(tmp_path)
    record = tmp_path / "record.json"
    low = UPPER_ID.lower()
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "bench", "--rollback", UPPER_ID, "--record", str(record)),
        FAKE_LISTED_ID=low,
        FAKE_READY_VERSION=low,
        REDIACC_BWS_PROFILES=port.BENCH_PROFILE,
    )
    assert proc.returncode == 0, proc.stderr
    assert calls == _rollback_calls("wrangler.bench.toml", PROXY_BENCH_HOST, low)
    assert UPPER_ID not in calls + proc.stderr
    assert json.loads(record.read_text())["version_id"] == low


def test_a_rollback_the_listing_does_not_confirm_still_writes_its_record(
    tmp_path: pathlib.Path,
) -> None:
    """wrangler has already moved the Worker, so the record is kept, with the failure named and no smoke (review 4a915178.4)."""
    root = _fixture_root(tmp_path)
    record = tmp_path / "record.json"
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "bench", "--rollback", TO_ID, "--record", str(record)),
        FAKE_LISTED_ID=PREV_ID,
        REDIACC_BWS_PROFILES=port.BENCH_PROFILE,
    )
    assert proc.returncode == 1
    assert "curl" not in calls
    written = json.loads(record.read_text())
    assert written["rolled_back"] is True
    assert written["version_id"] == PREV_ID, "version_id is what is live, not the target"
    assert written["requested_version_id"] == TO_ID
    assert written["smoke_rc"] is None
    assert "names %s at 100%%" % PREV_ID in written["failure"]


# ---- review a4d57548 and the bench drill: what a rollback record says is live ----


def test_smoke_only_after_a_failed_rollback_smokes_the_live_version_not_the_target(
    tmp_path: pathlib.Path,
) -> None:
    """The listing named PREV_ID after `wrangler rollback`, so the record's `version_id` is PREV_ID and a later `--smoke-only` smokes it (review a4d57548.1)."""
    root = _fixture_root(tmp_path)
    record = tmp_path / "record.json"
    proc, _calls = _run(
        tmp_path,
        root,
        ("--target", "bench", "--rollback", TO_ID, "--record", str(record)),
        FAKE_LISTED_ID=PREV_ID,
        REDIACC_BWS_PROFILES=port.BENCH_PROFILE,
    )
    assert proc.returncode == 1
    proc, calls = _run(
        tmp_path,
        root,
        ("--target", "bench", "--smoke-only", "--record", str(record)),
        FAKE_READY_VERSION=PREV_ID,
        FAKE_READY_TIMEOUT="0",
        REDIACC_BWS_PROFILES=port.BENCH_PROFILE,
    )
    assert proc.returncode == 0, proc.stderr
    assert "on version %s." % PREV_ID in proc.stderr
    assert "wrangler" not in calls, "the record named the live version, so nothing is listed"
    assert json.loads(record.read_text())["requested_version_id"] == TO_ID


def test_the_previous_release_differs_for_no_version_and_a_version(tmp_path: pathlib.Path) -> None:
    """The pin under review a4d57548.2: with no version the newest tag is the answer, even when that is the live release itself; with the release named, the one before it."""
    repo = _tagged_repo(tmp_path, ("v1.0.0", "v2.0.0"))
    assert port.previous_release_tag(repo, None) == "v2.0.0"
    assert port.previous_release_tag(repo, "2.0.0") == "v1.0.0"


def test_an_edge_rollback_asks_the_forward_only_question_about_the_live_release(
    tmp_path: pathlib.Path,
) -> None:
    """The record names the live release 1.2.3, so the rollback compares against the tag after v1.2.3's position (v2.3.2, whose config is at v1), as a deploy of 1.2.3 would: forward-only. Asked with no version it would read v1.2.3 itself and say a plain rollback (review a4d57548.2)."""
    root = _fixture_root(tmp_path)
    record = tmp_path / "record.json"
    record.write_text(
        json.dumps({"artifacts_version": VERSION, "migration_tag": "v2"}), encoding="utf-8"
    )
    previous = _previous_config(tmp_path, root, "wrangler.edge-us.toml", V1)
    proc, _calls = _run(
        tmp_path,
        root,
        ("--target", "edge", "--region", "us", "--rollback", TO_ID, "--record", str(record)),
        FAKE_LISTED_ID=TO_ID,
        FAKE_READY_VERSION=TO_ID,
        FAKE_PREV_CONFIG=previous,
    )
    assert proc.returncode == 0, proc.stderr
    want = "forward-only: Durable Object class lifecycle change (v2); fix forward"
    assert json.loads(record.read_text())["rollback"] == want


def test_an_edge_rollback_with_no_recorded_release_says_so(tmp_path: pathlib.Path) -> None:
    root = _fixture_root(tmp_path)
    proc, _calls = _run(
        tmp_path,
        root,
        ("--target", "edge", "--region", "us", "--rollback", TO_ID),
        FAKE_LISTED_ID=TO_ID,
        FAKE_READY_VERSION=TO_ID,
    )
    assert proc.returncode == 0, proc.stderr
    assert "no record names the release of the live" in proc.stderr


@pytest.mark.parametrize(
    ("view_backend", "view_rc", "backend"),
    [
        ("container", "0", "container"),
        ("durable", "0", "durable"),
        ("container", "1", "unknown"),
        ("", "0", "unknown"),
    ],
    ids=["container", "durable", "view-fails", "no-backend-var"],
)
def test_a_rollback_records_the_target_versions_own_backend(
    tmp_path: pathlib.Path, view_backend: str, view_rc: str, backend: str
) -> None:
    """The drill rolled bench back to a container version and recorded backend null: the backend is the target version's own, read with `wrangler versions view --json`, and "unknown" when it cannot be read."""
    root = _fixture_root(tmp_path)
    record = tmp_path / "record.json"
    proc, _calls = _run(
        tmp_path,
        root,
        ("--target", "bench", "--rollback", TO_ID, "--record", str(record)),
        FAKE_LISTED_ID=TO_ID,
        FAKE_READY_VERSION=TO_ID,
        REDIACC_BWS_PROFILES=port.BENCH_PROFILE,
        FAKE_VIEW_BACKEND=view_backend,
        FAKE_VIEW_RC=view_rc,
    )
    assert proc.returncode == 0, proc.stderr
    written = json.loads(record.read_text())
    assert written["backend"] == backend
    assert written["migration_tag"] == "unknown", "no earlier record: unknown, never null"
    assert "SOME_SECRET" not in proc.stdout + proc.stderr


def test_the_versions_view_reader_takes_only_the_named_plain_text_var() -> None:
    view = {
        "resources": {
            "bindings": [
                {"type": "secret_text", "name": "EXECUTOR_BACKEND", "text": "s3cret"},
                {"type": "plain_text", "name": "EXECUTOR_BACKEND", "text": "container"},
            ]
        }
    }
    assert port.version_plain_var(json.dumps(view), "EXECUTOR_BACKEND") == "container"
    assert port.version_plain_var(json.dumps(view), "EXECUTOR_CAP") is None
    assert port.version_plain_var("not json", "EXECUTOR_BACKEND") is None
    assert port.versions_view_argv("c.toml", TO_ID) == [
        "npx",
        "--no-install",
        "wrangler",
        "versions",
        "view",
        TO_ID,
        "--json",
        "--config",
        "c.toml",
    ]


def test_two_consecutive_rollbacks_both_know_the_live_release(tmp_path: pathlib.Path) -> None:
    """Review 941e1bff.1: a deploy record names the release of every version it has seen, so the first rollback records the release of the version it rolled to, and the second rollback asks the forward-only question about that release instead of warning and reading the newest tag. CONTROL: a target version no record names stays None, honestly."""
    root = _fixture_root(tmp_path)
    record = tmp_path / "record.json"
    record.write_text(
        json.dumps(
            {
                "version_id": NEW_ID,
                "artifacts_version": "1.2.4",
                "release_by_version": {TO_ID: VERSION},
                "migration_tag": "v2",
            }
        ),
        encoding="utf-8",
    )
    common = {"FAKE_LISTED_ID": TO_ID, "FAKE_READY_VERSION": TO_ID}
    args = ("--target", "edge", "--region", "us", "--rollback", TO_ID, "--record", str(record))
    proc, _calls = _run(tmp_path, root, args, **common)
    assert proc.returncode == 0, proc.stderr
    first = json.loads(record.read_text())
    assert first["artifacts_version"] == VERSION
    assert first["release_by_version"] == {TO_ID: VERSION, NEW_ID: "1.2.4"}
    proc, _calls = _run(tmp_path, root, args, **common)
    assert proc.returncode == 0, proc.stderr
    assert "no record names the release of the live" not in proc.stderr
    assert json.loads(record.read_text())["artifacts_version"] == VERSION
    other = "44444444-4444-4444-8444-444444444444"
    proc, _calls = _run(
        tmp_path,
        root,
        ("--target", "edge", "--region", "us", "--rollback", other, "--record", str(record)),
        FAKE_LISTED_ID=other,
        FAKE_READY_VERSION=other,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(record.read_text())["artifacts_version"] is None


def test_a_failed_rollback_records_the_listed_id_lowercased(tmp_path: pathlib.Path) -> None:
    """Review 941e1bff.2: the listing's id is written lowercased, as every other id in the record."""
    root = _fixture_root(tmp_path)
    record = tmp_path / "record.json"
    proc, _calls = _run(
        tmp_path,
        root,
        ("--target", "bench", "--rollback", TO_ID, "--record", str(record)),
        FAKE_LISTED_ID=UPPER_ID,
        REDIACC_BWS_PROFILES=port.BENCH_PROFILE,
    )
    assert proc.returncode == 1
    assert json.loads(record.read_text())["version_id"] == UPPER_ID.lower()
