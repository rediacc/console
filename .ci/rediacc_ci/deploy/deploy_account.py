#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/deploy-account.sh`.

Deploys ONE region of the account Worker to Cloudflare: apply the D1 migrations
for that region's database, then `wrangler deploy` against that region's config.
The region selects a wrangler config file by NAME (`wrangler.<region>.toml`: one shared Worker set per region, so there is no target to pick), and everything else the deploy needs -- the D1 database, the R2 bucket, the routes -- lives inside that file rather than in this script.

NOTHING HERE REACHES CLOUDFLARE IN A TEST. `npx` (and `npm`, on the install branch) are the only external tools, so the differential (`.ci/rediacc_ci/tests/test_deploy_deploy_account.py`) puts RECORDING FAKES for both on a scratch PATH and points both sides at a fixture repo root. `.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one real run" clause and
says in as many words that the mocked parity ledger is a separate, achievable piece of work. This is that piece.

THE DATABASE NAME IS READ WITH grep/head/sed, NOT WITH A TOML PARSER, and that is a reproduction rather than a preference. The twin's line 50 is

    DB_NAME=$(grep 'database_name' "$CONFIG" | head -1 | sed 's/.*= *"\\(.*\\)"/\\1/' || true)

and every one of those three stages leaks into what gets migrated:

  * `grep` matches the SUBSTRING anywhere on any line, comments included.
  * `head -1` takes the first match, so a file with two `[[d1_databases]]`
    blocks migrates the first and never mentions the second.
  * `sed` is a SUBSTITUTION, not a match: a line the pattern does not fit is
    passed through UNCHANGED, so the "could not read" guard below never fires
    and the whole line becomes the database name.

Two of those are defects (see the two constants near the bottom of this docstring's section, `A_COMMENT_BECOMES_THE_DATABASE_NAME` and `THE_LAST_QUOTE_WINS`), both driven against the real twin and pinned in the differential in both directions. A `tomllib.load` port would produce a DIFFERENT database name on those inputs, which is exactly the thing a port may not do. So the pipeline
is shelled out to the same three binaries.

TWO DIVERGENCES IN TEXT NOBODY PARSES, both the standard `${VAR:?msg}` shape
this campaign has ruled on before (`deploy/set_www_worker_secrets.py`, `deploy/wait_for_preview_worker.py`, `deploy/delete_r2_channel.py`):

  1. `REGION="${ARG_REGION:?--region is required (eu, us)}"` (:21) is bash's own
     refusal and prints the SCRIPT PATH AS INVOKED and a bash LINE NUMBER:

         .ci/scripts/deploy/deploy-account.sh: line 21: ARG_REGION: --region is required (eu, us)

     `MISSING_REGION` carries the `VAR: message` half, on the same stream, with
     the same exit status 1.
  2. An argument whose flag is not a valid shell identifier (`--foo.bar`) is
     `printf -v`'s own failure inside `common.sh:341`, exit 2, and names
     common.sh's path and line. The port prints `rediacc_ci.deploy.deploy_account: printf:
     ...` with the same status, following `autopilot/sweep_collect.py:284`.

ONE DIVERGENCE IN BEHAVIOUR, ON PURPOSE: THE SERVICES PREFLIGHT. Before any migration, each `[[services]]` target of the config must be a Worker on the account, as `rediacc_ci.ops.service_bindings_audit` lists them; a MISSING target, or an audit with no verdict (rc 77, an unparseable config included), refuses with exit 1 and nothing is migrated (`check_services`). The twin migrated first and let `wrangler deploy` fail on code 10143 afterwards. A config with no `[[services]]` runs exactly as the twin did.

A STUB BOOTSTRAP (`--stub`), because account binds proxy and proxy binds account. wrangler refuses a service binding to a Worker that does not exist, and `check_services` refuses before any migration, so the first deploy of a new region cannot start from either side. `--stub` uploads a placeholder Worker under the config's own name, route-less and answering 503, that exports the two entrypoints the proxy binds (`CloudflareInternal`, `ExecutorIssuer`); the proxy then deploys against it and the real deploy replaces it. It refuses when a Worker of that name already exists, so it can never overwrite a live one, and it runs no migration, preflight or portal check.

TWO MORE DIVERGENCES, ON PURPOSE: THE PORTAL CHECKS (2026-10-28, stable served a keyless portal while its Worker enforced captcha). Before any write, the dist on disk must carry the bound TURNSTILE_SITE_KEY (`portal_sitekey_refusal`). After `wrangler deploy`, the host of the config's route must SERVE a portal that renders the captcha its Worker enforces (`portal_smoke`, `rediacc_ci.ops.portal_captcha`), retried briefly for propagation; a red names the rebuild command and the rollback, and exits 1. A config with no route skips the smoke silently, which keeps the twin differential's fixture runs byte-identical.

`:?` IS AN UNSET-OR-EMPTY TEST, so `--region=` refuses exactly as an absent
`--region` does. Driven; a port testing only for presence would resolve `wrangler..toml` and report it missing instead.

K=5 LEDGER: `.ci/shadow/w7p6-deploy-account.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import typing

from rediacc_ci import log
from rediacc_ci.core import common
from rediacc_ci.core import wrangler as wrangler_cmd
from rediacc_ci.deploy import console_executor
from rediacc_ci.ops import portal_captcha, queues_audit, service_bindings_audit

# This module's own dotted name, the prefix of every diagnostic it prints (the same name `python3 -m` runs it by). A literal, because `__name__` is `__main__` under `-m`.
SELF = "rediacc_ci.deploy.deploy_account"

# The `${ARG_REGION:?...}` stand-in named in the docstring. The twin's own text
# after the `VAR: ` prefix bash adds; kept verbatim, because that is the text.
MISSING_REGION = "ARG_REGION: --region is required (eu, us, asia)"

# The twin's `--target` (:22-29) picked between the production and the edge config. One shared Worker set per region replaced both, so the flag is gone and `--target` is refused like any unknown flag.

# `$REPO_ROOT/workers/account` (:20), relative to the repo root `common.sh`'s own location resolves to. NOT cwd: the twin can be invoked from anywhere.
WORKER_SUBDIR = ("workers", "account")

# The sed program at :50, byte for byte. A BRE, and both `.*` are GREEDY, which is what `THE_LAST_QUOTE_WINS` below is about.
SED_PROGRAM = r's/.*= *"\(.*\)"/\1/'

# The string grep looks for (:50). A SUBSTRING, not a key: `# database_name` and `preview_database_name` both match.
DB_NAME_NEEDLE = "database_name"

# THE TWO DEFECTS THE grep/head/sed PIPELINE HAS, named as constants so the differential can assert them by name instead of restating the sentences, and so nobody "fixes" them in the port. Both driven against the real twin on 2026-09-13 in a fixture tree; both are reproduced here, not repaired, because repairing a twin is a cutover decision and this file is not the cutover.
#
# 1. A COMMENT BECOMES THE DATABASE NAME. A config whose first `database_name` occurrence is a comment (`# database_name is chosen per environment`) fails the sed pattern, so sed passes the line through unchanged, `[[ -z "$DB_NAME" ]]` is false, and the run prints "Applying migrations to # database_name is chosen per environment..." and calls `wrangler d1 migrations apply '#
# database_name is chosen per environment'`. The guard at :51-54 exists for exactly this case and cannot see it, because the pipeline's output is only empty when grep matched NOTHING.
#   2. THE LAST QUOTE WINS. `database_name = "account-db-eu" # was "old-db"`
# yields the eleven-word string `account-db-eu" # was "old-db`, because `\(.*\)` runs to the final `"` on the line.
#
# Blast radius today is zero: all seven `workers/account/wrangler.*.toml` files carry exactly one `database_name` line each, in the canonical shape.
A_COMMENT_BECOMES_THE_DATABASE_NAME = True
THE_LAST_QUOTE_WINS = True


# A portal built without the Turnstile sitekey renders no widget while the Worker enforces Turnstile, so every login answers "Captcha verification required" (stable eu/us/asia, 2026-10-28: deploy_bench had rebuilt workers/account/dist/account for bench, which has no captcha, and the next production deploy uploaded that keyless portal).
# This tool uploads whatever dist is on disk, so it proves the dist carries the key before anything is written.
SITEKEY_SHAPE = re.compile(r"^0x[0-9A-Za-z_-]{16,}$")
PORTAL_ASSETS = ("dist", "account", "assets")
REBUILD_HINT = (
    'rebuild the portal with the key: (cd private/account/web && VITE_TURNSTILE_SITE_KEY="$TURNSTILE_SITE_KEY" '
    "VITE_CI_MODE=false npx vite build --outDir ../../../workers/account/dist/account), under the "
    "account-secrets-<region> profile"
)


def portal_sitekey_refusal(worker_dir: pathlib.Path, env: typing.Mapping[str, str]) -> str | None:
    """None when the built portal under `dist/account/assets` carries the Turnstile sitekey the environment binds, else the refusal line."""
    # TURNSTILE_SITE_KEY only: the refusal below names that binding, and every caller binds it (the deploy-workers profile, the CD step). A `VITE_` fallback let a run with only the build-time name pass a check that says the deploy name must be bound (review a43d7f08.1).
    key = (env.get("TURNSTILE_SITE_KEY") or "").strip()
    if not key:
        return "TURNSTILE_SITE_KEY is not bound, so the portal cannot be checked for the captcha widget; run under the account-secrets-<region> profile"
    if not SITEKEY_SHAPE.match(key):
        return "TURNSTILE_SITE_KEY does not look like a Turnstile sitekey (0x...)"
    assets = worker_dir.joinpath(*PORTAL_ASSETS)
    bundles = sorted(assets.glob("*.js")) if assets.is_dir() else []
    if not bundles:
        return "no built portal at %s; %s" % (assets, REBUILD_HINT)
    for bundle in bundles:
        if key in bundle.read_text(encoding="utf-8", errors="replace"):
            return None
    return (
        "the built portal at %s carries no Turnstile sitekey, so login would show no captcha while the Worker enforces it; %s"
        % (assets, REBUILD_HINT)
    )


def route_host(config: pathlib.Path) -> str | None:
    """The first custom-domain route pattern of the deployed wrangler config, or None when it has none (or is not TOML, which `wrangler deploy` would already have refused)."""
    try:
        with open(config, "rb") as fh:
            routes = tomllib.load(fh).get("routes") or []
    except (OSError, tomllib.TOMLDecodeError):
        return None
    for route in routes:
        pattern = route if isinstance(route, str) else (route or {}).get("pattern", "")
        if pattern:
            return pattern.split("/", 1)[0]
    return None


def portal_smoke(
    config: pathlib.Path,
    env: typing.Mapping[str, str],
    fetch: portal_captcha.Http = portal_captcha.http,
    sleep: typing.Callable[[float], None] = time.sleep,
    shown: typing.Callable[[str], str] = str,
) -> str | None:
    """After the deploy: None when the served portal renders the captcha its Worker enforces, else the refusal line.

    The pre-deploy `portal_sitekey_refusal` proves the dist on disk; this proves what the host SERVES, which also catches a Worker version or asset upload that did not take. A config with no route has no host to ask and is not checked (every production and edge config carries one; the twin differential's fixture configs do not). An unreachable host after the retries is a refusal too: an unverified deploy is not a verified one.
    """
    host = route_host(config)
    if host is None:
        return None
    key = (env.get("TURNSTILE_SITE_KEY") or "").strip() or None
    verdict = portal_captcha.check_with_retry(host, fetch, key, sleep=sleep)
    if verdict.state == portal_captcha.OK:
        log.info("Portal smoke: %s %s" % (shown(host), shown(verdict.why)))
        return None
    return "Portal smoke %s on https://%s/account/login: %s. Fix: %s" % (
        verdict.state,
        host,
        verdict.why,
        portal_captcha.fix_command(host),
    )


def config_name(region: str) -> str:
    """`wrangler.<region>.toml` (:24-29, minus the edge branch the rename removed)."""
    return "wrangler.%s.toml" % region


def strip_newlines(token: str) -> str:
    """`printf '%s' "$TOKEN" | tr -d '\\r\\n'` (:41).

    NOT shelled out, unlike the database-name pipeline, and the reason is that this one is provably the same: `tr -d` deletes BYTES, and in UTF-8 the bytes 0x0D and 0x0A cannot appear inside a multi-byte sequence, so deleting the two characters and deleting the two bytes agree for every input.

    WHAT IT DOES NOT DO, and the twin does not either: an ACCOUNT ID carrying a stray carriage return is passed through untouched, because only the token is cleaned. Named in the differential rather than fixed.
    """
    return token.replace("\r", "").replace("\n", "")


def needs_npm_install(worker_dir: pathlib.Path, env: dict[str, str]) -> bool:
    """`if ! command -v wrangler &>/dev/null && [[ ! -d "node_modules" ]]` (:45).

    BOTH conditions, and the `!` binds to the `command -v` pipeline alone: an install happens only when wrangler is absent from PATH AND the worker directory has no `node_modules`. A machine with a global wrangler and no local install therefore skips it, which is the CD workflow's own case.

    `node_modules` is a RELATIVE path in the twin, tested after the `cd`, so it is the worker directory's -- passed explicitly here rather than depending on the process cwd.
    """
    if shutil.which("wrangler", path=env.get("PATH")) is not None:
        return False
    return not (worker_dir / "node_modules").is_dir()


def database_name(config: str) -> str:
    """`grep ... | head -1 | sed ...`, run as the same three binaries (:50).

    STDERR IS INHERITED on all three, as the twin leaves it: a grep that cannot open the file has already been ruled out by the `-f` check above, but a read error mid-file is the only trace anyone would get.

    `|| true` MAKES THE PIPELINE'S STATUS UNOBSERVABLE, including grep's 1 for "no match" and the 141 a SIGPIPE from `head` leaves on a long file. Nothing is checked here either; the empty result is what the caller tests.

    Bytes are decoded with `surrogateescape` so a config that is not valid UTF-8 reaches `wrangler` as the same bytes bash would have handed it. The one spot where the two still differ is a diagnostic: Python renders an unpaired surrogate on stderr as a backslash escape.
    """
    grep = subprocess.Popen(["grep", DB_NAME_NEEDLE, config], stdout=subprocess.PIPE)
    head = subprocess.Popen(["head", "-1"], stdin=grep.stdout, stdout=subprocess.PIPE)
    if grep.stdout is not None:
        # The parent must drop its copy or `head` exiting early never reaches `grep` as a SIGPIPE, which is the twin's behaviour on a long file.
        grep.stdout.close()
    sed = subprocess.Popen(["sed", SED_PROGRAM], stdin=head.stdout, stdout=subprocess.PIPE)
    if head.stdout is not None:
        head.stdout.close()
    out, _ = sed.communicate()
    grep.wait()
    head.wait()
    # Command substitution strips ALL trailing newlines, not just one.
    return out.decode("utf-8", "surrogateescape").rstrip("\n")


class ServiceBindingError(Exception):
    """A `[[services]]` target the preflight could not confirm exists. Nothing has been migrated when this is raised."""


def check_services(
    root: pathlib.Path,
    config_rel: str,
    env: typing.Mapping[str, str],
    fetch: service_bindings_audit.Fetch = service_bindings_audit._get,
) -> None:
    """Refuse before any migration when a `[[services]]` target of the deployed config is not a Worker on the account, or when the audit gives no verdict (rc 77).

    NOT PART OF THE TWIN. wrangler refuses a Worker whose service binding names a missing Worker only at `wrangler deploy`, after the migrations: the 2026-10-27 eu edge run applied 0060 through 0066 and then died on code 10143 for `edge-rediacc-proxy-eu`. The parsing and the account listing are `rediacc_ci.ops.service_bindings_audit`'s, restricted to this one config (`only`): the sibling configs are not even read, so another config's missing target or parse error never blocks this deploy. A config with no bindings makes no API call, and the run is byte-identical to the twin's.
    """
    try:
        _, bindings = service_bindings_audit.load_configs(root, config_rel)
    except service_bindings_audit.AuditError as exc:
        raise ServiceBindingError(
            "The service-bindings audit cannot read the Worker configs (%s); no migration was applied"
            % exc
        ) from None
    if not any(b.config == config_rel for b in bindings):
        return
    report = service_bindings_audit.audit(root, env, fetch, config_rel)
    if report["rc"] == service_bindings_audit.EX_UNAVAILABLE:
        raise ServiceBindingError(
            "The service-bindings audit gave no verdict for %s (%s); no migration was applied"
            % (config_rel, report["error"])
        )
    missing = [
        r for r in report["bindings"] if r["config"] == config_rel and r["status"] == "MISSING"
    ]
    if missing:
        raise ServiceBindingError(
            "%s; no migration was applied"
            % "; ".join(
                "Service binding %s in %s names Worker %s, which does not exist: deploy %s first, then re-run this deploy"
                % (r["binding"], config_rel, r["service"], r["service"])
                for r in missing
            )
        )


class QueuePreflightError(Exception):
    """A queue the config binds could not be confirmed or created. Nothing has been migrated when this is raised."""


def check_queues(
    config_path: pathlib.Path,
    env: typing.Mapping[str, str],
    fetch: queues_audit.Fetch = queues_audit._get,
    post: queues_audit.Post = queues_audit._post,
    *,
    dry_run: bool = False,
) -> list[str]:
    """Before any migration, make every queue the config binds (producer, consumer, dead-letter) exist on the account; returns the names created (or, under `dry_run`, the names that would be created, with nothing written).

    NOT PART OF THE TWIN. wrangler refuses a Worker bound to a missing queue only at `wrangler deploy`, after the migrations (commit 0c133e047f bound `BACKUP_REPLICATE_QUEUE` and its dead-letter queue in every account config). The missing ones are created through `rediacc_ci.ops.queues_audit.ensure`, dead-letter queues first; creation is idempotent and nothing is deleted. A failed create, or an audit with no verdict (rc 77, an unparseable config included), raises QueuePreflightError. A config with no queues makes no API call.
    """
    report = queues_audit.audit(config_path, env, fetch)
    if report["rc"] == queues_audit.EX_UNAVAILABLE:
        raise QueuePreflightError(
            "The queues audit gave no verdict for %s (%s); no migration was applied"
            % (config_path.name, report["error"])
        )
    missing = list(report["missing"])
    if not missing or dry_run:
        return missing
    token, account = queues_audit.credentials(env)
    try:
        return queues_audit.ensure(account, token, missing, fetch, post)
    except queues_audit.QueueCreateError as exc:
        raise QueuePreflightError("%s; no migration was applied" % exc) from None


def migrations_argv(db_name: str, config: str) -> list[str]:
    """`npx wrangler d1 migrations apply "$DB_NAME" --remote --config "$CONFIG"` (:60)."""
    return [
        *wrangler_cmd.ARGV,
        "d1",
        "migrations",
        "apply",
        db_name,
        "--remote",
        "--config",
        config,
    ]


def deploy_argv(config: str) -> list[str]:
    """`npx wrangler deploy --config "$CONFIG"` (:64)."""
    return [*wrangler_cmd.ARGV, "deploy", "--config", config]


def _has_credentials(env: typing.Mapping[str, str]) -> bool:
    try:
        queues_audit.credentials(env)
    except queues_audit.QueueAuditError:
        return False
    return True


# Every `ARG_*` key `main` reads. Anything else is refused by `common.parse_args` before a side effect; `--dry-run` is real (see `main`).
ACCEPTED_ARGS = frozenset(
    {
        "ARG_REGION",
        "ARG_DRY_RUN",
        "ARG_STUB",
        "ARG_COMPANY",
        "ARG_COMPANY_ID",
        "ARG_COMPANY_DOMAIN",
        "ARG_ACCOUNT_CONFIG",
        "ARG_COMPANY_BENCH",
    }
)

# `--company NAME` deploys one Enterprise company's own account Worker from the config path `--account-config` names (with `--company-id`, `--company-domain` and `--region`), instead of the region's shared `wrangler.<region>.toml`. `console_executor.company_target` validates the lot before anything runs.
COMPANY_ARG_KEYS = {
    "company": "ARG_COMPANY",
    "company_id": "ARG_COMPANY_ID",
    "company_domain": "ARG_COMPANY_DOMAIN",
    "account_config": "ARG_ACCOUNT_CONFIG",
    "company_bench": "ARG_COMPANY_BENCH",
}


def company_from_args(
    root: pathlib.Path, args: typing.Mapping[str, str]
) -> console_executor.CompanyTarget | None:
    """The company the `ARG_COMPANY*` keys name, None without `--company`; raises `console_executor.RefusedError`."""
    values = {key: args.get(arg) for key, arg in COMPANY_ARG_KEYS.items()}
    company = console_executor.company_from_values(root, values, args.get("ARG_REGION"))
    if company is not None and company.account_config is None:
        raise console_executor.RefusedError("--company needs --account-config")
    return company


def _run(argv: list[str]) -> int:
    """One child with BOTH streams inherited, as the twin leaves them.

    wrangler's own output is the entire visible result of a good run, and capturing it would move it out of the workflow log.
    """
    return subprocess.run(argv, check=False).returncode


# The placeholder `--stub` uploads. It binds nothing and answers 503, and exports the two entrypoints other Workers bind (`ACCOUNT` -> CloudflareInternal, `ISSUER` -> ExecutorIssuer, workers/account/src/index.ts), so a binding that names an entrypoint resolves too.
STUB_SOURCE = """import { WorkerEntrypoint } from 'cloudflare:workers';

export class CloudflareInternal extends WorkerEntrypoint {}
export class ExecutorIssuer extends WorkerEntrypoint {}

export default {
  fetch() {
    return new Response('stub: the account Worker is not deployed yet', { status: 503 });
  },
};
"""
STUB_ENTRY = "index.js"


class StubError(Exception):
    """The stub cannot be uploaded; nothing has been written to Cloudflare when this is raised."""


def stub_config_text(name: str, compatibility_date: str) -> str:
    """The route-less wrangler config of the stub: the real config's name and compatibility date, no routes, bindings, vars, crons or migrations."""
    return 'name = "%s"\nmain = "%s"\ncompatibility_date = "%s"\n' % (
        name,
        STUB_ENTRY,
        compatibility_date,
    )


def read_worker_identity(config: pathlib.Path) -> tuple[str, str]:
    """(name, compatibility_date) of a wrangler config, via a real TOML parse."""
    try:
        with open(config, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise StubError("cannot read %s: %s" % (config.name, exc)) from None
    name = str(data.get("name") or "")
    date = str(data.get("compatibility_date") or "")
    if not name or not date:
        raise StubError("%s carries no name or compatibility_date" % config.name)
    return name, date


def refuse_existing_worker(
    name: str,
    env: typing.Mapping[str, str],
    fetch: service_bindings_audit.Fetch = service_bindings_audit._get,
) -> None:
    """Raise StubError when a Worker called `name` is already on the account, or when the account cannot be read: a stub must never replace a live Worker."""
    token = env.get("CLOUDFLARE_API_TOKEN", "")
    account = env.get("CLOUDFLARE_ACCOUNT_ID", "")
    try:
        existing = service_bindings_audit.list_workers(account, token, fetch)
    except service_bindings_audit.AuditError as exc:
        raise StubError(
            "cannot list the account's Workers (%s); no stub was uploaded" % exc
        ) from None
    if name in existing:
        raise StubError(
            "Worker %s already exists on the account; the stub would replace it, so nothing was uploaded"
            % name
        )


def stub_main(
    worker_dir: pathlib.Path,
    config: str,
    *,
    dry_run: bool,
    shown: typing.Callable[[str], str] = str,
) -> int:
    """`--stub`: upload the placeholder Worker named by the region's config, so the proxy (which binds this Worker) can deploy before the real account Worker does."""
    try:
        name, date = read_worker_identity(worker_dir / config)
    except StubError as exc:
        log.error(shown(str(exc)))
        return 1
    with tempfile.TemporaryDirectory(prefix="account-stub-") as tmp:
        tmp_path = pathlib.Path(tmp)
        stub_config = tmp_path / "wrangler.toml"
        argv = deploy_argv(str(stub_config))
        if dry_run:
            log.step("DRY RUN: stub %s (%s); no command is run" % (shown(name), shown(config)))
            print("would run: %s" % " ".join(argv), flush=True)
            return 0
        os.chdir(worker_dir)
        # `--stub` runs no `npm install`, so a fresh checkout has no local wrangler: name that before any credential or network call instead of letting `npx --no-install` fail opaquely.
        try:
            wrangler_cmd.require(worker_dir)
        except wrangler_cmd.WranglerNotInstalledError as exc:
            log.error(shown(str(exc)))
            return 1
        for var in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
            try:
                common.require_var(var)
            except common.RefusalError as exc:
                exc.report()
                return exc.code
        os.environ["CLOUDFLARE_API_TOKEN"] = strip_newlines(os.environ["CLOUDFLARE_API_TOKEN"])
        try:
            refuse_existing_worker(name, os.environ)
        except StubError as exc:
            log.error(shown(str(exc)))
            return 1
        (tmp_path / STUB_ENTRY).write_text(STUB_SOURCE, encoding="utf-8")
        stub_config.write_text(stub_config_text(name, date), encoding="utf-8")
        log.step("Deploying the account stub: %s" % shown(name))
        status = _run(argv)
        if status != 0:
            return status
    log.info("Account stub deployed: %s" % shown(name))
    return 0


def main(argv: list[str]) -> int:
    try:
        args = common.parse_args(argv, allowed=ACCEPTED_ARGS)
    except common.RefusalError as exc:
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    worker_dir = common.repo_root().joinpath(*WORKER_SUBDIR)

    region = args.get("ARG_REGION", "")
    if not region:
        # THE DIVERGENCE: bash prefixes this with `<script>: line 21: `.
        print(MISSING_REGION, file=sys.stderr, flush=True)
        return 1

    try:
        company = company_from_args(common.repo_root(), args)
    except console_executor.RefusedError as exc:
        log.error(str(exc))
        return 1
    if company is not None and company.account_config is not None:
        worker_dir = company.account_config.parent
        config = company.account_config.name
        # What a log line may call the target: a company's config name carries its label, so only the opaque id is printed.
        label = "company %s" % company.company_id
        shown = company.mask
    else:
        config = config_name(region)
        label = "%s (%s)" % (region, config)

        def shown(text: str) -> str:
            return text

    if not (worker_dir / config).is_file():
        log.error("Wrangler config not found: %s/%s" % (shown(str(worker_dir)), shown(config)))
        return 1

    if "ARG_STUB" in args:
        return stub_main(worker_dir, config, dry_run="ARG_DRY_RUN" in args, shown=shown)

    if "ARG_DRY_RUN" in args:
        # Stops before npm install, the services audit, migrations and the deploy: nothing is written to Cloudflare. With credentials set, the queue check below lists the account's queues over the API (read-only).
        db_preview = database_name(str(worker_dir / config))
        if not db_preview:
            # The real run refuses here too; a preview naming a placeholder database would misstate the plan.
            log.error("Could not read database_name from %s" % shown(config))
            return 1
        log.step("DRY RUN: %s; no command is run" % label)
        try:
            bound = queues_audit.config_queues(worker_dir / config)
        except queues_audit.QueueAuditError as exc:
            # The real run refuses an unreadable queues section too: check_queues raises QueuePreflightError (the audit's own no-verdict code is 77) and main returns 1, so the preview returns 1 as well.
            log.error(shown(str(exc)))
            return 1
        if bound and not _has_credentials(os.environ):
            print(
                "queues not checked (no Cloudflare credentials): %s"
                % ", ".join(q.name for q in bound),
                flush=True,
            )
        elif bound:
            try:
                would = check_queues(worker_dir / config, os.environ, dry_run=True)
            except QueuePreflightError as exc:
                log.error(shown(str(exc)))
                return 1
            for name in would:
                print("would create queue: %s" % shown(name), flush=True)
        print("would run: %s" % shown(" ".join(migrations_argv(db_preview, config))), flush=True)
        print("would run: %s" % shown(" ".join(deploy_argv(config))), flush=True)
        return 0

    os.chdir(worker_dir)

    for name in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        try:
            common.require_var(name)
        except common.RefusalError as exc:
            exc.report()
            return exc.code

    # `export CLOUDFLARE_API_TOKEN` after the strip: children see the clean one.
    os.environ["CLOUDFLARE_API_TOKEN"] = strip_newlines(os.environ["CLOUDFLARE_API_TOKEN"])

    if needs_npm_install(worker_dir, dict(os.environ)):
        status = _run(["npm", "install"])
        if status != 0:
            return status  # `set -e`

    db_name = database_name(config)
    if not db_name:
        log.error("Could not read database_name from %s" % shown(config))
        return 1

    refusal = portal_sitekey_refusal(worker_dir, os.environ)
    if refusal:
        log.error(shown(refusal))
        return 1

    log.step("Deploying account worker: %s" % label)
    try:
        check_services(common.repo_root(), "/".join((*WORKER_SUBDIR, config)), os.environ)
    except ServiceBindingError as exc:
        log.error(shown(str(exc)))
        return 1
    try:
        for name in check_queues(worker_dir / config, os.environ):
            log.info("Created queue %s" % shown(name))
    except QueuePreflightError as exc:
        log.error(shown(str(exc)))
        return 1
    log.step("Applying migrations to %s..." % shown(db_name))
    status = _run(migrations_argv(db_name, config))
    if status != 0:
        return status  # `set -e`
    log.info("Migrations applied to %s" % shown(db_name))

    status = _run(deploy_argv(config))
    if status != 0:
        return status  # `set -e`
    log.info("Account worker deployed: %s" % (region if company is None else label))
    smoke = portal_smoke(worker_dir / config, os.environ, portal_captcha.http, time.sleep, shown)
    if smoke:
        log.error(shown(smoke))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
