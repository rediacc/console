"""`./run.sh enterprise <verb>`: the operator's command line for Enterprise companies (agent/plans/PLAN-enterprise-isolation.md, boxes C1, C2, K2 and P1).

    ./run.sh enterprise add <company> --region <r> --owner <mail> --storage-gb <n>
        [--allow-ip <ip|cidr>]... [--unlisted] [--lookup-domain <d>] [--bench]
        [--bws-project <id>] [--lookup-namespace-id <id>]
    ./run.sh enterprise list [--all] [--bench]
    ./run.sh enterprise update <company> [--max-machines N] [--max-storage-gb N] [--max-expiry-days N]
        [--allow-ip <ip|cidr>]... [--clear-allow-ips] [--ring R --ring-reason T] [--bench]
    ./run.sh enterprise suspend <company> [--resume] [--bench]
    ./run.sh enterprise export <company> [--export-root <dir>] [--bws-project <id>] [--bench]
    ./run.sh enterprise remove <company> [--delete-data --confirm <company>] [--export-root <dir>]
        [--lookup-domain <d>]... [--bws-project <id>] [--bench]
    ./run.sh enterprise release ...          (box K2, rediacc_ci.release.rings_run)
    ./run.sh enterprise proof <verb> [--bench]
    ./run.sh enterprise control ensure [--bench] [--region <r>]

`add` (box C1) is `onboarding.run` over the live steps, after `control_db.ensure_all` has made sure every control database of the environment exists with its schema. `list`, `update`, `suspend`, `export` and `remove` are box C2's `lifecycle` verbs over one `lifecycle.Context`; the context binds the production Exporter and Teardown (`lifecycle_adapters`) lazily, so `list`, `update` and `suspend` need no Cloudflare credentials, while `export` and `remove` read CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID (plus the R2 S3 pair, and `--bws-project` for `remove`) from the environment, as `bws_env exec --profile <p>` provides them, and refuse naming the one that is missing. A verb whose module has not landed refuses with `not built yet: <box>` and exit 2, rather than claiming anything.

EXIT CODES. 0 done; 1 a refusal or a failed step; 2 usage, or a verb not built yet.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import os
import pathlib
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from rediacc_ci import paths
from rediacc_ci.core import bws_env
from rediacc_ci.core import wrangler as wrangler_mod
from rediacc_ci.deploy import proxy_configs as pc
from rediacc_ci.enterprise import control_db, onboarding, proof, registry, secrets
from rediacc_ci.enterprise import lifecycle_adapters as la
from rediacc_ci.ops import enterprise_lookup

if TYPE_CHECKING:
    import types

SELF = "rediacc_ci.enterprise.cli"
LIFECYCLE = "rediacc_ci.enterprise.lifecycle"
RINGS_RUN = "rediacc_ci.release.rings_run"
LIFECYCLE_VERBS = ("list", "update", "suspend", "export", "remove")
EXPORT_ROOT = pathlib.Path.home() / ".local" / "state" / "rediacc" / "enterprise-exports"
CF_API_ENV = "CLOUDFLARE_API_TOKEN"
ACCOUNT_ENV = "CLOUDFLARE_ACCOUNT_ID"
EXIT_USAGE = 2

USAGE = (__doc__ or "").split("\n\n")[1]


def _module(name: str) -> types.ModuleType | None:
    """The module, or None when it has not landed. An import error from inside it propagates."""
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name != name:
            raise
        return None


def _refuse_not_built(box: str, module: str) -> int:
    print("%s: not built yet: %s (%s)" % (SELF, box, module), file=sys.stderr)
    return EXIT_USAGE


# --- add -------------------------------------------------------------------------


def _add_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="./run.sh enterprise add", description="onboard a company")
    ap.add_argument("company")
    ap.add_argument("--region", required=True)
    ap.add_argument("--owner", required=True, help="the owner's mail address")
    ap.add_argument("--storage-gb", type=int, required=True)
    ap.add_argument("--allow-ip", action="append", default=[], help="repeat for each IP or CIDR")
    ap.add_argument("--unlisted", action="store_true", help="no www lookup entry")
    ap.add_argument("--lookup-domain", default="", help="default: the owner's mail domain")
    ap.add_argument("--bench", action="store_true", help="bench control, signers and ENVIRONMENT")
    ap.add_argument("--bws-project", default="", help="the enterprise bws project id")
    ap.add_argument("--lookup-namespace-id", default=enterprise_lookup.NAMESPACE_ID)
    return ap


def live_add(req: onboarding.Request, opts: argparse.Namespace) -> onboarding.Outcome:
    """The production add: every control database ensured, then the resumable run over the live steps."""
    try:
        control_db.ensure_all(bench=req.bench)
    except control_db.ControlDbError as exc:
        return onboarding.Outcome(1, "", (), "refused: %s" % exc)
    provision = onboarding.live_provision(opts.bws_project) if opts.bws_project else None
    actions = onboarding.live_actions(
        provision=provision, lookup_namespace=opts.lookup_namespace_id
    )
    return onboarding.run(req, query=control_db.transport(), actions=actions)


Add = Callable[[onboarding.Request, argparse.Namespace], onboarding.Outcome]


def add_main(argv: Sequence[str], *, add: Add | None = None) -> int:
    try:
        opts = _add_parser().parse_args(list(argv))
    except SystemExit as exc:
        return 0 if exc.code == 0 else EXIT_USAGE
    req = onboarding.Request(
        name=opts.company,
        region=opts.region,
        owner=opts.owner,
        storage_gb=opts.storage_gb,
        allow_ips=tuple(opts.allow_ip),
        unlisted=opts.unlisted,
        lookup_domain=opts.lookup_domain,
        bench=opts.bench,
    )
    outcome = (add or live_add)(req, opts)
    if outcome.rc != 0:
        print("%s: %s" % (SELF, outcome.error), file=sys.stderr)
    return outcome.rc


# --- lifecycle -------------------------------------------------------------------


class Unbound:
    """A lifecycle seam with no production adapter: every method raises the lifecycle's own refusal with `message`."""

    def __init__(self, error: type[Exception], message: str):
        self._error = error
        self._message = message

    def __getattr__(self, attr: str) -> Callable[..., Any]:
        if attr.startswith("_"):
            raise AttributeError(attr)

        def refuse(*args: object, **kwargs: object) -> Any:
            del args, kwargs
            raise self._error(self._message)

        return refuse


@dataclasses.dataclass(frozen=True)
class LiveSeams:
    """The transports under the production adapters; None takes the live one from `lifecycle_adapters`."""

    wrangler: Callable[..., Any] | None = None  # (cwd, env) -> Wrangler
    s3: Callable[..., Any] | None = None  # (endpoint, env) -> S3
    http: Callable[..., Any] | None = None  # (headers) -> Http
    bws: Callable[..., Any] | None = None  # (project, env) -> (list_rows, delete)
    lookup_run: Callable[..., Any] | None = None


class Lazy:
    """An adapter built on first use for the region of the company a call names (one per region; a later call that names no company, such as a bucket or object read, goes to the adapter of the last company named, and is refused when adapters of more than one region exist, since the last one named would be a guess), so a verb that never reaches it needs none of its credentials."""

    def __init__(self, error: type[Exception], build: Callable[[str], Any]):
        self._error = error
        self._build = build
        self._inners: dict[str, Any] = {}
        self._current: Any = None

    def __getattr__(self, attr: str) -> Callable[..., Any]:
        if attr.startswith("_"):
            raise AttributeError(attr)

        def call(*args: Any, **kwargs: Any) -> Any:
            region = getattr(args[0], "region", None) if args else None
            if region:
                if str(region) not in self._inners:
                    self._inners[str(region)] = self._build(str(region))
                self._current = self._inners[str(region)]
            if self._current is None:
                raise self._error("the adapter was reached before a company was named")
            if not region and len(self._inners) > 1:
                raise self._error(
                    "a call that names no company is ambiguous: adapters exist for %s"
                    % ", ".join(sorted(self._inners))
                )
            return getattr(self._current, attr)(*args, **kwargs)

        return call


def _credentials(error: type[Exception], env: Mapping[str, str]) -> str:
    """The Cloudflare token; a missing variable is refused by name."""
    missing = [n for n in (CF_API_ENV, ACCOUNT_ENV) if not env.get(n)]
    if missing:
        raise error(
            "missing Cloudflare credentials: set %s (`bws_env exec --profile <p>` provides them)"
            % ", ".join(missing)
        )
    return env[CF_API_ENV]


def _r2(
    error: type[Exception], region: str, env: Mapping[str, str], seams: LiveSeams
) -> tuple[Any, str | None]:
    """(the R2 S3 transport for the region's jurisdiction, that jurisdiction)."""
    try:
        jurisdiction = onboarding.region_entry(region).get("r2Jurisdiction")
    except (onboarding.OnboardingError, OSError, ValueError, KeyError) as exc:
        raise error("the region %r cannot be read from regions.json: %s" % (region, exc)) from None
    prefix = "%s." % jurisdiction if jurisdiction else ""
    endpoint = "https://%s.%sr2.cloudflarestorage.com" % (env[ACCOUNT_ENV], prefix)
    return (seams.s3 or la.r2_s3_from_env)(endpoint, env), jurisdiction


def _live_exporter(error: type[Exception], env: Mapping[str, str], seams: LiveSeams) -> Lazy:
    def build(region: str) -> Any:
        _credentials(error, env)
        s3, _ = _r2(error, region, env, seams)
        cwd = paths.repo_root().joinpath(*pc.ACCOUNT_REL)
        try:
            run = (seams.wrangler or la.live_wrangler)(cwd, env)
        except wrangler_mod.WranglerNotInstalledError as exc:
            raise error(str(exc)) from None
        return la.CloudflareExporter(wrangler=run, s3=s3)

    return Lazy(error, build)


def _live_bws(error: type[Exception], env: Mapping[str, str]) -> tuple[Any, Any]:
    """(list_rows, delete) over the bws binary, the delete taking only the entry's uuid."""
    try:
        environ = bws_env.with_token(dict(env))
    except bws_env.RefusalError:
        raise error("no bws access token") from None
    binary = bws_env.binary(environ)
    if not binary:
        raise error("no bws binary")

    def list_rows() -> list[dict]:
        try:
            return bws_env.listing(binary, environ)
        except bws_env.RefusalError as exc:
            reason = (str(exc).splitlines() or [""])[0]
        raise error("bws secret list failed: %s" % reason if reason else "bws secret list failed")

    def delete(secret_id: str) -> int:
        proc = subprocess.run(
            [binary, "secret", "delete", secret_id],
            env=environ,
            capture_output=True,
            text=True,
            check=False,
        )
        return int(proc.returncode)

    return list_rows, delete


def _live_teardown(
    error: type[Exception],
    env: Mapping[str, str],
    seams: LiveSeams,
    bws_project: str,
    lookup_domains: Sequence[str],
) -> Lazy:
    def build(region: str) -> Any:
        token = _credentials(error, env)
        if not bws_project:
            raise error("--bws-project names the enterprise bws project whose entries are deleted")
        s3, jurisdiction = _r2(error, region, env, seams)
        list_rows, delete = (seams.bws or _live_bws_pair(error, env))(bws_project, env)
        return la.CloudflareTeardown(
            account_id=env[ACCOUNT_ENV],
            http=(seams.http or la.cloudflare_http)(["-H", "Authorization: Bearer %s" % token]),
            s3=s3,
            secrets=la.BwsDeleter(bws_project, list_rows=list_rows, delete=delete),
            lookup_domains=lambda _company: tuple(lookup_domains),
            lookup_run=seams.lookup_run,
            r2_jurisdiction=jurisdiction,
        )

    return Lazy(error, build)


def _live_bws_pair(error: type[Exception], env: Mapping[str, str]) -> Callable[..., Any]:
    return lambda _project, _env: _live_bws(error, env)


def lifecycle_context(
    lifecycle: Any,
    *,
    bench: bool,
    query: registry.Query | None = None,
    bws_project: str = "",
    export_root: pathlib.Path | None = None,
    env: Mapping[str, str] | None = None,
    lookup_domains: Sequence[str] = (),
    seams: LiveSeams | None = None,
) -> Any:
    """One `lifecycle.Context` over the control databases; the Exporter and Teardown are the live adapters, built on first use, and the store needs `--bws-project`."""
    q = query or control_db.transport()
    error = lifecycle.LifecycleError
    environ = dict(os.environ if env is None else env)
    live = seams or LiveSeams()
    store: Any
    if bws_project:
        try:
            store = secrets.BwsStore.from_env(bws_project)
        except secrets.SecretsError as exc:
            store = Unbound(error, "the enterprise bws store cannot be opened: %s" % exc)
    else:
        store = Unbound(error, "--bws-project names the enterprise bws project this verb reads")
    return lifecycle.Context(
        registry=registry.Registry(q, bench=bench),
        query=q,
        exporter=_live_exporter(error, environ, live),
        teardown=_live_teardown(error, environ, live, bws_project, lookup_domains),
        store=store,
        export_root=export_root or EXPORT_ROOT,
        env=environ,
        now=onboarding.utc_now,
        actor="operator",
    )


def _lifecycle_parser(verb: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="./run.sh enterprise %s" % verb)
    ap.add_argument("--bench", action="store_true")
    if verb == "list":
        ap.add_argument("--all", action="store_true", help="include removed companies")
        return ap
    ap.add_argument("company")
    if verb == "update":
        ap.add_argument("--max-machines", type=int, default=None)
        ap.add_argument("--max-storage-gb", type=int, default=None)
        ap.add_argument("--max-expiry-days", type=int, default=None)
        ap.add_argument("--allow-ip", action="append", default=None)
        ap.add_argument("--clear-allow-ips", action="store_true")
        ap.add_argument("--ring", default=None)
        ap.add_argument("--ring-reason", default=None)
    elif verb == "suspend":
        ap.add_argument("--resume", action="store_true")
    else:
        ap.add_argument("--export-root", type=pathlib.Path, default=None)
        ap.add_argument("--bws-project", default="")
        if verb == "remove":
            ap.add_argument("--delete-data", action="store_true")
            ap.add_argument("--confirm", default=None)
            ap.add_argument("--lookup-domain", action="append", default=None)
    return ap


def lifecycle_main(
    verb: str, argv: Sequence[str], *, context: Callable[..., Any] | None = None
) -> int:
    lifecycle = _module(LIFECYCLE)
    if lifecycle is None:
        return _refuse_not_built("C2", LIFECYCLE)
    try:
        args = _lifecycle_parser(verb).parse_args(list(argv))
    except SystemExit as exc:
        return 0 if exc.code == 0 else EXIT_USAGE
    ctx = (context or lifecycle_context)(
        lifecycle,
        bench=args.bench,
        bws_project=getattr(args, "bws_project", ""),
        export_root=getattr(args, "export_root", None),
        lookup_domains=tuple(getattr(args, "lookup_domain", None) or ()),
    )
    if verb == "list":
        return int(lifecycle.cmd_list(ctx, include_removed=args.all))
    if verb == "suspend":
        return int(lifecycle.cmd_suspend(ctx, args.company, resume=args.resume))
    if verb == "export":
        return int(lifecycle.cmd_export(ctx, args.company))
    if verb == "remove":
        return int(
            lifecycle.cmd_remove(
                ctx, args.company, delete_data=args.delete_data, confirm=args.confirm
            )
        )
    allow_ips = [] if args.clear_allow_ips else args.allow_ip
    return int(
        lifecycle.cmd_update(
            ctx,
            args.company,
            max_machines=args.max_machines,
            max_storage_gb=args.max_storage_gb,
            max_expiry_days=args.max_expiry_days,
            allow_ips=allow_ips,
            ring=args.ring,
            ring_reason=args.ring_reason,
        )
    )


# --- dispatch --------------------------------------------------------------------


def main(
    argv: Sequence[str], *, add: Add | None = None, context: Callable[..., Any] | None = None
) -> int:
    args = list(argv)
    if not args:
        print(USAGE, file=sys.stderr)
        return EXIT_USAGE
    verb, rest = args[0], args[1:]
    if verb in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    if verb == "add":
        return add_main(rest, add=add)
    if verb in LIFECYCLE_VERBS:
        return lifecycle_main(verb, rest, context=context)
    if verb == "release":
        rings = _module(RINGS_RUN)
        if rings is None:
            return _refuse_not_built("K2", RINGS_RUN)
        return int(rings.main(rest))
    if verb == "proof":
        return int(proof.main(rest))
    if verb == "control":
        return int(control_db.main(rest))
    print("%s: unknown enterprise verb: %s" % (SELF, verb), file=sys.stderr)
    print(USAGE, file=sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
