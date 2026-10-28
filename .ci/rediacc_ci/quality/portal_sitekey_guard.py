"""Every Cloudflare deploy workflow that builds the account portal feeds it the Turnstile site key and proves the build contains it.

WHY. On 2026-09-24 every production login failed with "Captcha verification required": the account worker enforces Turnstile whenever its secret is set (private/account/src/app.ts), but the deployed portal had been built with an empty `VITE_TURNSTILE_SITE_KEY` (the v1.3.12 workflows read the since-deleted `vars.TURNSTILE_SITE_KEY`), so no widget rendered. Nothing in CI could see it: the build succeeds with an empty key, and no gate read the workflows for it.

WHAT IT CHECKS, in every `.github/workflows/cd-deploy-*.yml`: each step that runs `vite build` for the account portal into a `workers/<name>/dist/account` directory must
  1. set `VITE_TURNSTILE_SITE_KEY` from the Bitwarden-fetched env (`env.BWS_TURNSTILE_SITE_KEY`), never from `vars.*` or a literal, and
  2. be followed, in the same job, by a step that fails when the key is empty or absent from that output directory (a `grep` of the key over `<dir>/assets` plus an empty-key `test -n`).

AND THE LOCAL DEPLOY PATHS, since stable eu/us/asia served a keyless portal on 2026-10-28 (deploy_bench had rebuilt workers/account/dist/account for bench, and the next production deploy uploaded it):
  3. every `rediacc_ci.release.local` step that runs `vite build` into a `workers/<name>/dist/account` binds `TURNSTILE_SITE_KEY > VITE_TURNSTILE_SITE_KEY` and never sets `VITE_TURNSTILE_SITE_KEY` itself;
  4. `rediacc_ci.deploy.deploy_account` main refuses a keyless dist before `wrangler deploy` (`portal_sitekey_refusal`) and smokes the served portal after it (`portal_smoke`), and its rebuild hint binds `VITE_TURNSTILE_SITE_KEY="$TURNSTILE_SITE_KEY"` into `workers/account/dist/account`;
  5. `rediacc_ci.ops.deploy_bench` builds its keyless portal through `portal_out_dir`, which lies outside the production assets directory; wrangler.bench.toml's [assets] directory is that build root, and every production and edge account config uploads `./dist`, which holds no bench build root.

Self-hosted image builds (ci-build-docker.yml) and the CI e2e build (ci.yml) are out of scope: they build keyless or with a per-run widget on purpose.

Exit 0 clean, 1 on findings, 2 when the gate's own controls fail (controls_first convention).
"""

from __future__ import annotations

import ast
import copy
import pathlib
import re
import sys
import tomllib
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import yaml

from rediacc_ci import paths
from rediacc_ci.controls import controls_first
from rediacc_ci.ops import deploy_bench
from rediacc_ci.release import local

if TYPE_CHECKING:
    from collections.abc import Iterable

WORKFLOW_GLOB = ".github/workflows/cd-deploy-*.yml"
_OUTDIR = re.compile(r"vite build\b.*?--outDir\s+(?:\.\./)*(workers/[\w.-]+/dist/account)")
_BWS_KEY = re.compile(r"^\$\{\{\s*env\.BWS_TURNSTILE_SITE_KEY\s*\}\}$")


def findings_for(name: str, doc: dict) -> list[str]:
    out: list[str] = []
    for job_id, job in (doc.get("jobs") or {}).items():
        steps = (job or {}).get("steps") or []
        for i, step in enumerate(steps):
            run = str(step.get("run") or "")
            m = _OUTDIR.search(run)
            if not m:
                continue
            outdir = m.group(1)
            label = "%s job %s step %r" % (name, job_id, step.get("name") or i)
            key = str(((step.get("env") or {}).get("VITE_TURNSTILE_SITE_KEY")) or "")
            if not _BWS_KEY.match(key.strip()):
                out.append(
                    "%s: VITE_TURNSTILE_SITE_KEY is %r, not ${{ env.BWS_TURNSTILE_SITE_KEY }}"
                    % (label, key)
                )
            later = " ".join(str(s.get("run") or "") for s in steps[i + 1 :])
            if not (
                re.search(r"test -n \"\$VITE_TURNSTILE_SITE_KEY\"", later)
                and outdir + "/assets" in later
            ):
                out.append(
                    "%s: no later step fails when the site key is empty or missing from %s/assets"
                    % (label, outdir)
                )
    return out


def findings(root: pathlib.Path) -> list[str]:
    files = sorted(root.glob(WORKFLOW_GLOB))
    if not files:
        return ["no %s found: the gate would pass vacuously" % WORKFLOW_GLOB]
    out: list[str] = []
    builds = 0
    for f in files:
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        builds += sum(
            1
            for job in (doc.get("jobs") or {}).values()
            for s in ((job or {}).get("steps") or [])
            if _OUTDIR.search(str(s.get("run") or ""))
        )
        out.extend(findings_for(f.name, doc))
    if builds == 0:
        out.append(
            "no portal build step found in %s: the gate would pass vacuously" % WORKFLOW_GLOB
        )
    return out


# ---- the local deploy paths ---------------------------------------------------------------

TURNSTILE_BIND = "TURNSTILE_SITE_KEY > VITE_TURNSTILE_SITE_KEY"
DEPLOY_ACCOUNT_REL = ".ci/rediacc_ci/deploy/deploy_account.py"
DEPLOY_BENCH_REL = ".ci/rediacc_ci/ops/deploy_bench.py"
ACCOUNT_WORKER_REL = "workers/account"
HINT_BIND = 'VITE_TURNSTILE_SITE_KEY="$TURNSTILE_SITE_KEY"'


def local_step_findings(steps: Iterable[Any]) -> list[str]:
    """Each release/local.py step (`id`, `argv`, `binds`, `env`) that builds a portal into a deployed Worker's dist binds the site key from TURNSTILE_SITE_KEY and does not override it."""
    out: list[str] = []
    builds = 0
    for step in steps:
        m = _OUTDIR.search(" ".join(step.argv))
        if not m:
            continue
        builds += 1
        label = "release/local.py step %r (%s)" % (step.id, m.group(1))
        if TURNSTILE_BIND not in step.binds:
            out.append(
                "%s: does not bind %r, so the portal builds with no captcha widget"
                % (label, TURNSTILE_BIND)
            )
        if any(k == "VITE_TURNSTILE_SITE_KEY" for k, _ in step.env):
            out.append("%s: sets VITE_TURNSTILE_SITE_KEY in env, overriding the bound key" % label)
    if builds == 0:
        out.append("release/local.py: no portal build step found; the check would pass vacuously")
    return out


def _calls_in(func: ast.AST) -> list[tuple[int, str]]:
    found = []
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            f = node.func
            name = (
                f.id
                if isinstance(f, ast.Name)
                else (f.attr if isinstance(f, ast.Attribute) else "")
            )
            found.append((node.lineno, name))
    return found


def deploy_account_findings(source: str) -> list[str]:
    """deploy_account main checks the dist before the deploy and the served portal after it, and its rebuild hint binds the key."""
    out: list[str] = []
    tree = ast.parse(source)
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    main = funcs.get("main")
    if main is None:
        return ["%s: no main(); the check would pass vacuously" % DEPLOY_ACCOUNT_REL]
    calls = _calls_in(main)
    first: dict[str, int] = {}
    for line, name in sorted(calls):
        first.setdefault(name, line)
    deploy = first.get("deploy_argv")
    if deploy is None:
        out.append(
            "%s: main never calls deploy_argv; the check would pass vacuously" % DEPLOY_ACCOUNT_REL
        )
    refusal = first.get("portal_sitekey_refusal")
    if refusal is None or (deploy is not None and refusal > deploy):
        out.append(
            "%s: main does not refuse a keyless dist (portal_sitekey_refusal) before wrangler deploy"
            % DEPLOY_ACCOUNT_REL
        )
    smoke = first.get("portal_smoke")
    if smoke is None or (deploy is not None and smoke < deploy):
        out.append(
            "%s: main does not smoke the served portal (portal_smoke) after wrangler deploy"
            % DEPLOY_ACCOUNT_REL
        )
    hint = ""
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "REBUILD_HINT" for t in node.targets
        ):
            try:
                hint = ast.literal_eval(node.value)
            except ValueError:
                hint = ""
    if HINT_BIND not in hint or "workers/account/dist/account" not in hint:
        out.append(
            "%s: REBUILD_HINT does not build workers/account/dist/account with %s"
            % (DEPLOY_ACCOUNT_REL, HINT_BIND)
        )
    return out


def _assets_dir(toml_text: str) -> str:
    try:
        return str((tomllib.loads(toml_text).get("assets") or {}).get("directory", ""))
    except tomllib.TOMLDecodeError:
        return ""


def bench_findings(
    bench_source: str,
    bench_out: pathlib.PurePosixPath,
    configs: dict[str, str],
) -> list[str]:
    """The keyless bench build lands only where wrangler.bench.toml serves from, and never in the directory a production or edge config uploads.

    `bench_out` is deploy_bench.portal_out_dir relative to workers/account; `configs` maps each account wrangler config name to its text.
    """
    out: list[str] = []
    outdirs = re.findall(r'"--outDir",\s*([^\]\n]+)', bench_source)
    if outdirs != ["str(out_dir)"] or "out_dir = portal_out_dir(worker_dir)" not in bench_source:
        out.append(
            "%s: the vite build must write to portal_out_dir(worker_dir) and nowhere else (found --outDir %s)"
            % (DEPLOY_BENCH_REL, outdirs or "none")
        )
    if "bench_assets_refusal(worker_dir)" not in bench_source:
        out.append(
            "%s: the build no longer checks wrangler.bench.toml's [assets] first (bench_assets_refusal)"
            % DEPLOY_BENCH_REL
        )
    bench_root = bench_out.parent
    production = [n for n in configs if n != "wrangler.bench.toml"]
    if "wrangler.bench.toml" not in configs or not production:
        return [
            *out,
            "workers/account: no bench or production config found; the check would pass vacuously",
        ]
    served = pathlib.PurePosixPath(_assets_dir(configs["wrangler.bench.toml"]).removeprefix("./"))
    if served != bench_root:
        out.append(
            "wrangler.bench.toml: [assets] directory is %r, not ./%s where deploy_bench builds"
            % (str(served), bench_root)
        )
    for name in sorted(production):
        uploads = pathlib.PurePosixPath(_assets_dir(configs[name]).removeprefix("./"))
        if uploads == pathlib.PurePosixPath("."):
            out.append("%s: [assets] directory is missing or the worker root" % name)
            continue
        if (
            uploads == bench_root
            or uploads in bench_out.parents
            or bench_root in uploads.parents
            or uploads in bench_root.parents
        ):
            out.append(
                "%s: uploads ./%s, which overlaps the keyless bench build at ./%s"
                % (name, uploads, bench_out)
            )
    return out


def local_findings(root: pathlib.Path) -> tuple[list[str], int]:
    """Findings over the three local deploy paths and how many inputs were read."""
    worker = root / ACCOUNT_WORKER_REL
    configs = {
        p.name: p.read_text(encoding="utf-8") for p in sorted(worker.glob("wrangler.*.toml"))
    }
    bench_out = pathlib.PurePosixPath(
        deploy_bench.portal_out_dir(worker).relative_to(worker).as_posix()
    )
    found = [
        *local_step_findings(local._table()),
        *deploy_account_findings((root / DEPLOY_ACCOUNT_REL).read_text(encoding="utf-8")),
        *bench_findings((root / DEPLOY_BENCH_REL).read_text(encoding="utf-8"), bench_out, configs),
    ]
    return found, len(configs)


_GUARDED: dict[str, Any] = {
    "jobs": {
        "d": {
            "steps": [
                {
                    "name": "Build account portal",
                    "run": "npm install && npx vite build --outDir ../../../workers/account/dist/account",
                    "env": {"VITE_TURNSTILE_SITE_KEY": "${{ env.BWS_TURNSTILE_SITE_KEY }}"},
                },
                {
                    "name": "Portal carries the Turnstile site key",
                    "run": 'test -n "$VITE_TURNSTILE_SITE_KEY" || exit 1\n'
                    'grep -rqF -- "$VITE_TURNSTILE_SITE_KEY" workers/account/dist/account/assets || exit 1',
                },
            ]
        }
    }
}


def selftest() -> bool:
    """True when a control FAILED."""
    failed = False
    if findings_for("ok.yml", _GUARDED):
        print("✗ control: a guarded build read as a finding", file=sys.stderr)
        failed = True
    vars_key = copy.deepcopy(_GUARDED)
    vars_key["jobs"]["d"]["steps"][0]["env"]["VITE_TURNSTILE_SITE_KEY"] = (
        "${{ vars.TURNSTILE_SITE_KEY }}"
    )
    if not findings_for("vars.yml", vars_key):
        print("✗ control: the 2026-09-24 vars.* key source was not reported", file=sys.stderr)
        failed = True
    no_guard = copy.deepcopy(_GUARDED)
    del no_guard["jobs"]["d"]["steps"][1]
    if not findings_for("noguard.yml", no_guard):
        print("✗ control: a build with no key-presence step was not reported", file=sys.stderr)
        failed = True
    failed |= _local_selftest()
    return failed


def _step(argv: str, binds=(TURNSTILE_BIND,), env=()) -> SimpleNamespace:
    return SimpleNamespace(id="account-portal", argv=("sh", "-c", argv), binds=binds, env=env)


_BUILD = "npm install && npx vite build --outDir ../../../workers/account/dist/account"
_ACCOUNT_OK = """
REBUILD_HINT = 'cd web && VITE_TURNSTILE_SITE_KEY="$TURNSTILE_SITE_KEY" npx vite build --outDir ../../../workers/account/dist/account'
def main(argv):
    refusal = portal_sitekey_refusal(worker_dir, os.environ)
    status = _run(deploy_argv(config))
    smoke = portal_smoke(worker_dir / config, os.environ)
"""
_BENCH_OK = """
    refusal = bench_assets_refusal(worker_dir)
    out_dir = portal_out_dir(worker_dir)
    _run(
        ["npx", "--no-install", "vite", "build", "--outDir", str(out_dir)],
"""
_BENCH_OUT = pathlib.PurePosixPath("bench/dist/account")
_CONFIGS = {
    "wrangler.bench.toml": '[assets]\ndirectory = "./bench/dist"\n',
    "wrangler.eu.toml": '[assets]\ndirectory = "./dist"\n',
}


def _local_selftest() -> bool:
    """Each local-path defect is planted and must be reported; the guarded shapes must not be."""
    failed = False

    def expect(label: str, got: list[str], want_finding: bool) -> None:
        nonlocal failed
        if bool(got) != want_finding:
            print("✗ control: %s (%s)" % (label, got or "no finding"), file=sys.stderr)
            failed = True

    expect(
        "a bound release/local.py build read as a finding",
        local_step_findings([_step(_BUILD)]),
        False,
    )
    expect(
        "a release/local.py build without the TURNSTILE bind was not reported",
        local_step_findings([_step(_BUILD, binds=())]),
        True,
    )
    expect(
        "a release/local.py build overriding VITE_TURNSTILE_SITE_KEY was not reported",
        local_step_findings([_step(_BUILD, env=(("VITE_TURNSTILE_SITE_KEY", ""),))]),
        True,
    )
    expect(
        "a release/local.py table with no portal build was not reported",
        local_step_findings([_step("true")]),
        True,
    )
    expect(
        "a guarded deploy_account read as a finding", deploy_account_findings(_ACCOUNT_OK), False
    )
    expect(
        "deploy_account without the pre-deploy refusal was not reported",
        deploy_account_findings(_ACCOUNT_OK.replace("portal_sitekey_refusal", "noop")),
        True,
    )
    expect(
        "deploy_account without the post-deploy smoke was not reported",
        deploy_account_findings(_ACCOUNT_OK.replace("portal_smoke", "noop")),
        True,
    )
    swapped = _ACCOUNT_OK.replace("    smoke = portal_smoke(worker_dir / config, os.environ)\n", "")
    swapped = swapped.replace(
        "    status = _run",
        "    smoke = portal_smoke(worker_dir / config, os.environ)\n    status = _run",
    )
    expect(
        "deploy_account smoking BEFORE the deploy was not reported",
        deploy_account_findings(swapped),
        True,
    )
    expect(
        "a deploy_account rebuild hint with no key was not reported",
        deploy_account_findings(_ACCOUNT_OK.replace(HINT_BIND, "VITE_TURNSTILE_SITE_KEY=")),
        True,
    )
    expect(
        "a guarded deploy_bench read as a finding",
        bench_findings(_BENCH_OK, _BENCH_OUT, _CONFIGS),
        False,
    )
    incident = _BENCH_OK.replace("str(out_dir)", 'str(worker_dir / "dist" / "account")')
    expect(
        "the 2026-10-28 deploy_bench build into dist/account was not reported",
        bench_findings(incident, _BENCH_OUT, _CONFIGS),
        True,
    )
    expect(
        "a deploy_bench build that skips bench_assets_refusal was not reported",
        bench_findings(
            _BENCH_OK.replace("bench_assets_refusal(worker_dir)", "None"), _BENCH_OUT, _CONFIGS
        ),
        True,
    )
    expect(
        "a bench config serving ./dist was not reported",
        bench_findings(
            _BENCH_OK,
            _BENCH_OUT,
            {**_CONFIGS, "wrangler.bench.toml": '[assets]\ndirectory = "./dist"\n'},
        ),
        True,
    )
    expect(
        "a production config uploading the bench build root was not reported",
        bench_findings(
            _BENCH_OK,
            _BENCH_OUT,
            {**_CONFIGS, "wrangler.eu.toml": '[assets]\ndirectory = "./bench"\n'},
        ),
        True,
    )
    expect(
        "a bench build root inside production dist was not reported",
        bench_findings(
            _BENCH_OK,
            pathlib.PurePosixPath("dist/bench/account"),
            {**_CONFIGS, "wrangler.bench.toml": '[assets]\ndirectory = "./dist/bench"\n'},
        ),
        True,
    )
    return failed


def main(argv: list[str]) -> int:
    rc = controls_first("portal Turnstile site-key guard", selftest)
    if rc or "--selftest" in argv:
        return rc
    root = paths.repo_root()
    local, configs = local_findings(root)
    found = findings(root) + local
    if found:
        print("✗ %d portal site-key finding(s):" % len(found), file=sys.stderr)
        for f in found:
            print("    %s" % f, file=sys.stderr)
        return 1
    print(
        "✓ every cd-deploy portal build takes the Bitwarden site key and proves the build contains it;"
        " release/local.py binds it, deploy_account checks the dist and the served portal,"
        " and deploy_bench builds outside the dist %d account configs upload" % (configs - 1)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
