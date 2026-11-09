#!/usr/bin/env python3
"""Deploy one regional licence signer Worker, push its signing key, and verify what is live.

    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_signer --target eu|us|asia|bench-eu|bench-us [--record PATH] [--dry-run]

THE TARGETS (agent/plans/PLAN-enterprise-isolation.md, Design "Signers" and "Scope data"). One signer per region of regions.json, `signer-<r>`, and two on bench, `signer-bench-eu` and `signer-bench-us`. Each binds two D1 databases: `CONTROL`, its own region's control database (`control-<r>`, `control-bench-<r>`), and `SHARED`, the shared account database the same region's account Worker binds as `DB`. The shared database's name and id, and the hosts a shared caller's renewalUrl may name, are read from that account Worker's own config (`workers/account/wrangler.<r>.toml`, bench: `wrangler.bench.toml`), so nothing here repeats a database id or a host. Both bench signers read `account-bench`, the one bench account Worker.

THE CONFIG. `workers/signer/wrangler.template.toml` is rendered into the gitignored `workers/signer/.generated/wrangler.<target>.toml`. A token left unrendered, a route, a workers.dev host or a preview URL, a Worker name other than the target's, or the private key's name anywhere in the rendered text refuses the run before any credential is read: the signer has no route, and the key arrives only as a secret. The control database's id is looked up with `wrangler d1 list --json`; a missing control database refuses the run and names it, because creating and migrating it belongs to `enterprise add` and the live boxes, not to a deploy.

THE KEY. `ACCOUNT_ED25519_PRIVATE_KEY` and `ACCOUNT_ED25519_PUBLIC_KEY` are read from the environment (a Bitwarden profile binds them) and reach wrangler only as the JSON document on the stdin of `wrangler secret bulk`. No value is ever put in argv, printed, written to the record or carried by an exception: every line of wrangler output this module prints is first redacted of both values, and a missing value is refused by its name alone.

THE ORDER. `wrangler deploy`, whose `Current Version ID:` line is captured; then `wrangler secret bulk`; then the verification: `wrangler secret list --format json` must name exactly the two key names, so a signer never runs with an extra secret or without its key. The signer answers no internet request, so its `probe()` RPC is proven by its callers over their binding (live box V1, `./run.sh enterprise proof signer --bench`), not here.

THE WRANGLER. Every call runs from `workers/signer`, whose own lockfile pins wrangler (`npm ci --prefix workers/signer` installs it), with `--config` naming the rendered file; wrangler resolves `main` relative to the config.

A DRY RUN (`--dry-run`) renders with a placeholder control id and runs `wrangler deploy --dry-run`, which bundles the Worker and needs no credential or key.

THE LAB READERS AND DRIVERS (box S2's group in `rediacc_ci.enterprise.lab`, the `Lab` protocol of `rediacc_ci.enterprise.proof`). Fifteen module functions that `LiveLab` binds by name at call time. Each live call goes through an injectable seam, a keyword-only argument that defaults to the production transport: `run` (the wrangler `Runner` above), `api` (a Cloudflare account GET, `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` from the environment), `companies` (the registry's rows) and `probe`. `bench=True` selects `signer-bench-<r>` and `account-bench`; `callers` and `account_workers` also list each non-removed company's `account-<name>` Worker. `secret_names` is `wrangler secret list`; `signer_of` and `signer_props` read the caller's `LICENSE_SIGNER` service binding from the Workers settings API; `expected_props` is what S4's binding must carry (`{tier: shared, region}` from the account config's `vars.REGION`, `{tier: enterprise, companyId, region}` from the control row); `certificate_audited` reads the signer region's control `audit` table. A signer is stopped by `wrangler delete --force` (what the plan's V2 text calls removing a bench signer) and started by this module's own `deploy`, which re-pushes the key; `cut_region` stops that region's bench signer and does NOT delete or detach its control database, because D1 offers no unreachable state short of destroying the data, and the signer is the only Worker that reads it for signing. `issue`, `renew` and `current_licence_works` need the caller Worker to ask its signer, and no caller-side probe route exists yet (box S4 binds `LICENSE_SIGNER`); their default `probe` raises `LabError("not built yet: ...")`, never an answer, so a refused claim cannot pass on a missing route.

THE RECORD. `--record PATH` writes JSON: target, worker, region, config, version id, the previous version id, whether it could be read (`previous_known`), the secret names seen, and the rollback command (`wrangler rollback <previous>`, or null). The record is written, and the rollback line printed, right after `wrangler deploy` succeeds, with empty `secret_names`; it is rewritten once the secret list is verified, so a failure of the key push still leaves the way back on disk.
"""

from __future__ import annotations

import argparse
import dataclasses
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tomllib
import typing

from rediacc_ci import paths
from rediacc_ci.core import wrangler
from rediacc_ci.enterprise import control_db, proof, registry
from rediacc_ci.housekeeping import cf_leftovers

SELF = "rediacc_ci.deploy.deploy_signer"

SIGNER_REL = ("workers", "signer")
ACCOUNT_REL = ("workers", "account")
TEMPLATE = "wrangler.template.toml"
GENERATED_DIR = ".generated"

PRIVATE_KEY = "ACCOUNT_ED25519_PRIVATE_KEY"
PUBLIC_KEY = "ACCOUNT_ED25519_PUBLIC_KEY"
SECRET_NAMES = (PRIVATE_KEY, PUBLIC_KEY)
# The Bitwarden profile a local run binds the two keys and the Cloudflare token under (added by box S4).
PROFILE = "deploy-signer"

BENCH_REGIONS = ("eu", "us")
DRY_RUN_DB_ID = "00000000-0000-0000-0000-000000000000"
TOKEN_RE = re.compile(r"@[A-Z_]+@")
VERSION_ID_RE = re.compile(r"Current Version ID:\s*([0-9A-Za-z][0-9A-Za-z-]*)")
REDACTED = "[redacted]"
# What `wrangler deployments list` prints for a Worker that has never been deployed ("This Worker does not exist on your account. [code: 10007]"). The phrases name the Worker or the code: a bare "not found" or "does not exist" also appears in unrelated failures (a missing config, a missing binary) and must not read as a first deploy (review 759876e3.1).
NO_WORKER_RE = re.compile(r"\b10007\b|worker does not exist|no such worker", re.IGNORECASE)


class RefusedError(Exception):
    """A run that must stop with exit 1. Its lines never carry a secret value."""

    def __init__(self, *lines: str) -> None:
        super().__init__(lines[0] if lines else "")
        self.lines = lines


@dataclasses.dataclass(frozen=True)
class Target:
    key: str
    worker: str
    region: str
    control_db: str
    account_config: str


@dataclasses.dataclass(frozen=True)
class Result:
    rc: int
    stdout: str
    stderr: str


# (argv, cwd, stdin) -> Result. The tests swap it for a recording fake.
Runner = typing.Callable[[list[str], pathlib.Path, "str | None"], Result]


def run_process(argv: list[str], cwd: pathlib.Path, stdin: str | None) -> Result:
    proc = subprocess.run(argv, cwd=cwd, input=stdin, capture_output=True, text=True, check=False)
    return Result(proc.returncode, proc.stdout, proc.stderr)


# ---- targets and config ------------------------------------------------------


def load_region_ids(repo_root: pathlib.Path) -> list[str]:
    data = json.loads((repo_root / "regions.json").read_text(encoding="utf-8"))
    return [str(r["id"]).lower() for r in data["regions"]]


def targets(region_ids: typing.Iterable[str]) -> dict[str, Target]:
    out: dict[str, Target] = {}
    for r in region_ids:
        out[r] = Target(r, "signer-%s" % r, r, "control-%s" % r, "wrangler.%s.toml" % r)
    for r in BENCH_REGIONS:
        key = "bench-%s" % r
        out[key] = Target(key, "signer-%s" % key, r, "control-%s" % key, "wrangler.bench.toml")
    return out


def shared_binding(account_text: str, rel: str) -> tuple[str, str, list[str]]:
    """(database name, database id, route hosts) of an account Worker config's `DB` binding and routes."""
    try:
        doc = tomllib.loads(account_text)
    except tomllib.TOMLDecodeError as exc:
        raise RefusedError("%s: %s does not parse: %s" % (SELF, rel, exc)) from None
    db = [d for d in doc.get("d1_databases", []) if d.get("binding") == "DB"]
    if len(db) != 1 or not db[0].get("database_name") or not db[0].get("database_id"):
        raise RefusedError("%s: %s has no single DB d1 binding with a name and id" % (SELF, rel))
    hosts = [
        str(r["pattern"]) for r in doc.get("routes", []) if isinstance(r, dict) and r.get("pattern")
    ]
    if not hosts:
        raise RefusedError(
            "%s: %s names no route, so the shared renewal host is unknown" % (SELF, rel)
        )
    return str(db[0]["database_name"]), str(db[0]["database_id"]), hosts


def render(template: str, values: dict[str, str]) -> str:
    text = template
    for name, value in values.items():
        text = text.replace("@%s@" % name, value)
    return text


def config_refusals(text: str, target: Target) -> list[str]:
    """Every reason a rendered signer config may not deploy; empty when it may."""
    reasons: list[str] = []
    leftover = sorted(set(TOKEN_RE.findall(text)))
    if leftover:
        reasons.append("unrendered token(s): %s" % ", ".join(leftover))
    if PRIVATE_KEY in text:
        reasons.append("%s is named in the config; the key is a secret only" % PRIVATE_KEY)
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return [*reasons, "does not parse: %s" % exc]
    if doc.get("name") != target.worker:
        reasons.append("name is %r, not %r" % (doc.get("name"), target.worker))
    reasons.extend("has `%s`: a signer has no route" % k for k in ("route", "routes") if k in doc)
    if doc.get("workers_dev") is not False:
        reasons.append("workers_dev is not false")
    if doc.get("preview_urls") is not False:
        reasons.append("preview_urls is not false")
    if "env" in doc:
        reasons.append("has an [env.*] table")
    if doc.get("vars", {}).get("REGION") != target.region:
        reasons.append("vars.REGION is not %r" % target.region)
    names = [d.get("binding") for d in doc.get("d1_databases", [])]
    reasons.extend(
        "d1 binding %s is declared %d times" % (n, names.count(n))
        for n in sorted({n for n in names if names.count(n) > 1}, key=str)
    )
    bindings = {d.get("binding"): d.get("database_name") for d in doc.get("d1_databases", [])}
    if bindings.get("CONTROL") != target.control_db:
        reasons.append("CONTROL binds %r, not %r" % (bindings.get("CONTROL"), target.control_db))
    if set(bindings) != {"CONTROL", "SHARED"}:
        reasons.append("d1 bindings are %s, not CONTROL and SHARED" % sorted(map(str, bindings)))
    return reasons


# ---- argv builders -----------------------------------------------------------


def d1_list_argv() -> list[str]:
    return [*wrangler.ARGV, "d1", "list", "--json"]


def deploy_argv(config: pathlib.Path, *, dry_run: bool) -> list[str]:
    argv = [*wrangler.ARGV, "deploy", "--config", str(config)]
    if dry_run:
        argv += ["--dry-run", "--outdir", str(config.parent / "dry-run")]
    return argv


def deployments_argv(config: pathlib.Path) -> list[str]:
    return [*wrangler.ARGV, "deployments", "list", "--json", "--config", str(config)]


def secret_bulk_argv(config: pathlib.Path) -> list[str]:
    return [*wrangler.ARGV, "secret", "bulk", "--config", str(config)]


def secret_list_argv(config: pathlib.Path) -> list[str]:
    return [*wrangler.ARGV, "secret", "list", "--format", "json", "--config", str(config)]


def rollback_command(config_rel: str, version: str) -> str:
    return "npx --no-install wrangler rollback %s --config %s --yes" % (version, config_rel)


# ---- the run -----------------------------------------------------------------


class Redactor:
    """Replaces every secret value in text before it is printed or raised."""

    def __init__(self, values: typing.Iterable[str]) -> None:
        self.values = sorted({v for v in values if v}, key=len, reverse=True)

    def __call__(self, text: str) -> str:
        for v in self.values:
            text = text.replace(v, REDACTED)
        return text


def control_db_id(run: Runner, cwd: pathlib.Path, name: str) -> str:
    res = run(d1_list_argv(), cwd, None)
    if res.rc != 0:
        raise RefusedError("%s: wrangler d1 list failed (rc %d)" % (SELF, res.rc))
    try:
        rows = json.loads(res.stdout)
    except json.JSONDecodeError:
        raise RefusedError("%s: wrangler d1 list printed no JSON" % SELF) from None
    ids = [str(r.get("uuid", "")) for r in rows if isinstance(r, dict) and r.get("name") == name]
    if len(ids) != 1 or not ids[0]:
        raise RefusedError(
            "%s: the control database %s does not exist (or is named twice); "
            "it is created and migrated from private/account/control/migrations by `enterprise add` or the live boxes, never by a deploy"
            % (SELF, name)
        )
    return ids[0]


class DeploymentsUnreadableError(Exception):
    """The deployments list failed or printed something that is not a list, which is not the same as a first deploy."""


def newest_version(run: Runner, cwd: pathlib.Path, config: pathlib.Path) -> str | None:
    """The version id of the newest deployment at 100%, or None (a first deploy: an empty list, or wrangler saying the Worker does not exist). Raises `DeploymentsUnreadableError` for any other failure, so a rollback line never claims a first deploy it cannot know."""
    res = run(deployments_argv(config), cwd, None)
    if res.rc != 0:
        if NO_WORKER_RE.search(res.stdout + res.stderr):
            return None
        raise DeploymentsUnreadableError
    try:
        rows = json.loads(res.stdout)
    except json.JSONDecodeError:
        raise DeploymentsUnreadableError from None
    if not isinstance(rows, list):
        raise DeploymentsUnreadableError
    if not all(isinstance(d, dict) for d in rows):
        raise DeploymentsUnreadableError
    if not rows:
        return None
    newest = max(rows, key=lambda d: str(d.get("created_on", "")))
    versions = newest.get("versions", [])
    if not isinstance(versions, list) or not all(isinstance(v, dict) for v in versions):
        raise DeploymentsUnreadableError
    for v in versions:
        if v.get("percentage") == 100:
            return str(v.get("version_id"))
    return None


def deploy(
    repo_root: pathlib.Path,
    target_key: str,
    *,
    env: typing.Mapping[str, str],
    run: Runner,
    dry_run: bool = False,
    record: pathlib.Path | None = None,
    out: typing.TextIO = sys.stdout,
) -> dict[str, typing.Any]:
    all_targets = targets(load_region_ids(repo_root))
    if target_key not in all_targets:
        raise RefusedError(
            "--target %s is not a signer target (one of %s)"
            % (target_key, ", ".join(sorted(all_targets)))
        )
    target = all_targets[target_key]
    signer_dir = repo_root.joinpath(*SIGNER_REL)
    account_dir = repo_root.joinpath(*ACCOUNT_REL)
    account_rel = "/".join(ACCOUNT_REL) + "/" + target.account_config
    shared_db, shared_id, hosts = shared_binding(
        (account_dir / target.account_config).read_text(encoding="utf-8"), account_rel
    )

    private_key = env.get(PRIVATE_KEY, "")
    public_key = env.get(PUBLIC_KEY, "")
    redact = Redactor([private_key, public_key])

    def say(text: str) -> None:
        if text:
            out.write(redact(text) if text.endswith("\n") else redact(text) + "\n")

    if not dry_run:
        missing = [n for n in ("CLOUDFLARE_API_TOKEN", *SECRET_NAMES) if not env.get(n)]
        if missing:
            raise RefusedError(
                "%s: a deploy needs %s set (bind with bws_env exec --profile %s)"
                % (SELF, ", ".join(missing), PROFILE)
            )
        wrangler.require(signer_dir, env)

    control_id = DRY_RUN_DB_ID if dry_run else control_db_id(run, signer_dir, target.control_db)
    text = render(
        (signer_dir / TEMPLATE).read_text(encoding="utf-8"),
        {
            "WORKER": target.worker,
            "REGION": target.region,
            "SHARED_HOSTS": ",".join(hosts),
            "CONTROL_DB": target.control_db,
            "CONTROL_DB_ID": control_id,
            "SHARED_DB": shared_db,
            "SHARED_DB_ID": shared_id,
        },
    )
    reasons = config_refusals(text, target)
    if reasons:
        raise RefusedError(*("--target %s refused: %s" % (target.key, r) for r in reasons))
    config = signer_dir / GENERATED_DIR / ("wrangler.%s.toml" % target.key)
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(text, encoding="utf-8")
    config_rel = "/".join(SIGNER_REL) + "/%s/%s" % (GENERATED_DIR, config.name)

    if dry_run:
        res = run(deploy_argv(config, dry_run=True), signer_dir, None)
        say(res.stdout)
        say(res.stderr)
        if res.rc != 0:
            raise RefusedError("%s: wrangler deploy --dry-run failed (rc %d)" % (SELF, res.rc))
        say("Dry run passed: %s bundles with %s." % (target.worker, config_rel))
        return {"target": target.key, "worker": target.worker, "dry_run": True}

    previous_known = True
    try:
        previous = newest_version(run, signer_dir, config)
    except DeploymentsUnreadableError:
        previous, previous_known = None, False
    res = run(deploy_argv(config, dry_run=False), signer_dir, None)
    say(res.stdout)
    say(res.stderr)
    if res.rc != 0:
        raise RefusedError("%s: wrangler deploy failed (rc %d)" % (SELF, res.rc))
    found = VERSION_ID_RE.findall(res.stdout)
    if not found:
        raise RefusedError("%s: wrangler deploy printed no Current Version ID" % SELF)
    version = found[-1]

    # The version is live from here, so the record and the way back are written before the key is pushed.
    result: dict[str, typing.Any] = {
        "target": target.key,
        "worker": target.worker,
        "region": target.region,
        "config": config_rel,
        "version_id": version,
        "previous_version_id": previous,
        "previous_known": previous_known,
        "secret_names": [],
        "rollback": rollback_command(config_rel, previous) if previous else None,
    }
    if record is not None:
        record.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    say("Deployed %s version %s." % (target.worker, version))
    if result["rollback"]:
        say("Rollback: %s" % result["rollback"])
    elif previous_known:
        say("Rollback: none (first deploy)")
    else:
        say("Rollback: unknown (the deployments list could not be read before this deploy)")

    document = json.dumps({PRIVATE_KEY: private_key, PUBLIC_KEY: public_key})
    res = run(secret_bulk_argv(config), signer_dir, document)
    say(res.stdout)
    say(res.stderr)
    if res.rc != 0:
        raise RefusedError("%s: wrangler secret bulk failed (rc %d)" % (SELF, res.rc))

    res = run(secret_list_argv(config), signer_dir, None)
    if res.rc != 0:
        raise RefusedError("%s: wrangler secret list failed (rc %d)" % (SELF, res.rc))
    try:
        names = sorted(str(s.get("name")) for s in json.loads(res.stdout))
    except (json.JSONDecodeError, AttributeError, TypeError):
        raise RefusedError("%s: wrangler secret list printed no JSON list" % SELF) from None
    if names != sorted(SECRET_NAMES):
        raise RefusedError(
            "%s: %s holds secrets %s, not exactly %s"
            % (SELF, target.worker, names, sorted(SECRET_NAMES))
        )

    result["secret_names"] = names
    if record is not None:
        record.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    say("Secrets %s verified on %s." % (", ".join(names), target.worker))
    return result


# ---- the lab readers and drivers (box S2's method group) ----------------------

SIGNER_BINDING = "LICENSE_SIGNER"
COMPANY_WORKER_PREFIX = "account-"
BENCH_ACCOUNT = "account-bench"

# (path under /accounts/<id>) -> the decoded `result`. The tests swap it for a dict lookup.
Api = typing.Callable[[str], typing.Any]
Companies = typing.Callable[[bool], list[dict]]
# (caller, action in issue|renew|current, kind) -> Answer.
Probe = typing.Callable[[str, str, str], proof.Answer]


def _no_probe(caller: str, action: str, kind: str) -> proof.Answer:
    raise proof.LabError(
        "not built yet: S4 (no caller-side signing probe: %s cannot be asked to %s %s, "
        "and nothing was signed)" % (caller, action, kind)
    )


def _root() -> pathlib.Path:
    return pathlib.Path(paths.repo_root())


def _signer_dir() -> pathlib.Path:
    return _root().joinpath(*SIGNER_REL)


def _all_targets() -> dict[str, Target]:
    return targets(load_region_ids(_root()))


def default_api() -> Api:
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not token or not account:
        raise proof.LabError(
            "CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are required (bws_env exec --profile %s)"
            % PROFILE
        )

    def get(path: str) -> typing.Any:
        try:
            return cf_leftovers.fetch("/accounts/%s%s" % (account, path), token).get("result")
        except cf_leftovers.CfError as exc:
            raise proof.LabError(str(exc)) from None

    return get


def default_companies(bench: bool) -> list[dict]:
    try:
        rows = registry.Registry(control_db.transport(), bench=bench).companies()
    except registry.RegistryUnreachableError as exc:
        raise proof.LabError(str(exc)) from None
    return [r for r in rows if r.get("state") != "removed"]


def _wrangler(run: Runner, argv: list[str]) -> Result:
    cwd = _signer_dir()
    try:
        wrangler.require(cwd, os.environ)
    except wrangler.WranglerNotInstalledError as exc:
        raise proof.LabError(str(exc)) from None
    return run(argv, cwd, None)


def account_workers(*, bench: bool, companies: Companies = default_companies) -> list[str]:
    """Every account Worker whose secret list must hold no private key: the shared ones, then each live company's."""
    shared = (
        [BENCH_ACCOUNT] if bench else [COMPANY_WORKER_PREFIX + r for r in load_region_ids(_root())]
    )
    return [*shared, *(COMPANY_WORKER_PREFIX + str(r["name"]) for r in companies(bench))]


def signers(*, bench: bool) -> list[str]:
    keys = ["bench-%s" % r for r in BENCH_REGIONS] if bench else load_region_ids(_root())
    return [_all_targets()[k].worker for k in keys]


def secret_names(worker: str, *, run: Runner = run_process) -> list[str]:
    res = _wrangler(run, [*wrangler.ARGV, "secret", "list", "--format", "json", "--name", worker])
    if res.rc != 0:
        raise proof.LabError("wrangler secret list for %s exited %d" % (worker, res.rc))
    try:
        return sorted(str(s["name"]) for s in json.loads(res.stdout))
    except (json.JSONDecodeError, KeyError, TypeError):
        raise proof.LabError("wrangler secret list for %s printed no JSON list" % worker) from None


def callers(*, bench: bool, companies: Companies = default_companies) -> list[str]:
    """The Workers that ask a signer: every account Worker."""
    return account_workers(bench=bench, companies=companies)


def _binding(caller: str, api: Api | None) -> dict:
    result = (api or default_api())("/workers/scripts/%s/settings" % caller)
    rows = result.get("bindings", []) if isinstance(result, dict) else []
    found = [
        b
        for b in rows
        if isinstance(b, dict) and b.get("type") == "service" and b.get("name") == SIGNER_BINDING
    ]
    if len(found) != 1:
        raise proof.LabError(
            "%s has %d %s service binding(s), not 1" % (caller, len(found), SIGNER_BINDING)
        )
    return found[0]


def signer_of(caller: str, *, api: Api | None = None) -> str:
    return str(_binding(caller, api).get("service", ""))


def signer_props(caller: str, *, api: Api | None = None) -> dict[str, str]:
    props = _binding(caller, api).get("props")
    return {str(k): str(v) for k, v in props.items()} if isinstance(props, dict) else {}


def _account_region(config: str) -> str:
    path = _root().joinpath(*ACCOUNT_REL) / config
    return str(tomllib.loads(path.read_text(encoding="utf-8")).get("vars", {}).get("REGION", ""))


def expected_props(caller: str, *, companies: Companies = default_companies) -> dict[str, str]:
    """The props S4's binding must carry for `caller`: shared `{tier, region}`, a company's `{tier, companyId, region}`."""
    if caller == BENCH_ACCOUNT:
        return {"tier": "shared", "region": _account_region("wrangler.bench.toml")}
    name = caller[len(COMPANY_WORKER_PREFIX) :] if caller.startswith(COMPANY_WORKER_PREFIX) else ""
    if name in load_region_ids(_root()):
        return {"tier": "shared", "region": name}
    for bench in (True, False):
        for row in companies(bench):
            if str(row["name"]) == name:
                return {
                    "tier": "enterprise",
                    "companyId": str(row["id"]),
                    "region": str(row["region"]),
                }
    raise proof.LabError("no shared Worker or company is named by %s" % caller)


def issue(caller: str, kind: str, *, probe: Probe = _no_probe) -> proof.Answer:
    return probe(caller, "issue", kind)


def _like_escape(text: str) -> str:
    """`text` as a literal inside a LIKE pattern that declares `ESCAPE '\\'` (review c0ce889a.3)."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def certificate_audited(
    signer: str, certificate_id: str, *, run: control_db.Runner = control_db.run_wrangler
) -> bool:
    """A `delegation_cert.signed` row naming the certificate's subscription id sits in the signer region's control audit table."""
    if not signer.startswith("signer-"):
        raise proof.LabError("%r is not a signer Worker" % signer)
    database = "control-" + signer[len("signer-") :]
    try:
        rows = control_db.query(
            database,
            "SELECT COUNT(*) AS n FROM audit WHERE action = ? AND detail LIKE ? ESCAPE '\\'",
            [
                "delegation_cert.signed",
                '%%"subscriptionId":%s%%' % _like_escape(json.dumps(certificate_id)),
            ],
            runner=run,
        )
    except control_db.ControlDbError as exc:
        raise proof.LabError(str(exc)) from None
    return bool(rows) and int(rows[0].get("n", 0)) > 0


def current_licence_works(caller: str, *, probe: Probe = _no_probe) -> bool:
    return probe(caller, "current", "licence").ok


def renew(caller: str, *, probe: Probe = _no_probe) -> proof.Answer:
    return probe(caller, "renew", "licence")


def _bench_signer_names() -> set[str]:
    return {"signer-bench-%s" % r for r in BENCH_REGIONS}


def _require_bench_signer(signer: str) -> None:
    """The lab drivers act on bench signers only: a production signer is never deleted or redeployed from here (review c0ce889a.1)."""
    if signer not in _bench_signer_names():
        raise proof.LabError(
            "%r is not a bench signer Worker (one of %s); the lab never touches a production signer"
            % (signer, ", ".join(sorted(_bench_signer_names())))
        )


def stop_signer(signer: str, *, run: Runner = run_process) -> None:
    """Delete a bench signer Worker (`--force`, since callers bind it); `start_signer` redeploys it. Bench only."""
    _require_bench_signer(signer)
    res = _wrangler(run, [*wrangler.ARGV, "delete", "--name", signer, "--force"])
    if res.rc != 0:
        raise proof.LabError("wrangler delete %s exited %d" % (signer, res.rc))


def start_signer(
    signer: str, *, run: Runner = run_process, env: typing.Mapping[str, str] | None = None
) -> None:
    _require_bench_signer(signer)
    keys = [k for k, t in _all_targets().items() if t.worker == signer]
    if not keys:
        raise proof.LabError("%r is not a signer Worker" % signer)
    try:
        deploy(
            _root(),
            keys[0],
            env=os.environ if env is None else env,
            run=run,
            out=io.StringIO(),
        )
    except (RefusedError, wrangler.WranglerNotInstalledError) as exc:
        raise proof.LabError("; ".join(getattr(exc, "lines", (str(exc),)))) from None


def _bench_signer(region: str) -> str:
    if region not in BENCH_REGIONS:
        raise proof.LabError(
            "bench has no signer in %r (one of %s)" % (region, ", ".join(BENCH_REGIONS))
        )
    return "signer-bench-%s" % region


def cut_region(region: str, *, run: Runner = run_process) -> None:
    """Bench only: stop the region's bench signer. Its control database is not cut (see the module docstring)."""
    stop_signer(_bench_signer(region), run=run)


def restore_region(
    region: str, *, run: Runner = run_process, env: typing.Mapping[str, str] | None = None
) -> None:
    start_signer(_bench_signer(region), run=run, env=env)


def main(argv: list[str] | None = None, *, run: Runner = run_process) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m %s" % SELF, description=__doc__.split("\n\n")[0]
    )
    parser.add_argument("--target", required=True)
    parser.add_argument("--record", type=pathlib.Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        deploy(
            pathlib.Path(paths.repo_root()),
            args.target,
            env=os.environ,
            run=run,
            dry_run=args.dry_run,
            record=args.record,
        )
    except (RefusedError, wrangler.WranglerNotInstalledError) as exc:
        for line in getattr(exc, "lines", (str(exc),)):
            print("ERROR: %s" % line, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
