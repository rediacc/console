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

# `wrangler deploy` prints a version line; `wrangler deployments list --json` answers the deployments before the deploy, then after it.
FAKE_NPX = """#!/usr/bin/python3
import json
import os
import sys

log = os.environ["FAKE_CALL_LOG"]
with open(log) as fh:
    deployed = "npx\\t--no-install\\twrangler\\tdeploy\\t--config" in fh.read()
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


def test_bench_is_forward_only_when_its_recorded_migration_tag_differs(
    tmp_path: pathlib.Path,
) -> None:
    root = _fixture_root(tmp_path)
    record = tmp_path / "record.json"
    args = ("--target", "bench", "--record", str(record))
    for recorded, forward in (("v1", True), ("v2", False)):
        record.write_text(json.dumps({"migration_tag": recorded}), encoding="utf-8")
        proc, _calls = _run(tmp_path, root, args, **BENCH_PROFILE_ENV)
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
    profile = _profiles()[port.DEPLOY_PROFILE]
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
