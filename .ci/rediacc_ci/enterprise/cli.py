"""`./run.sh enterprise <verb>`: the operator's command line for Enterprise companies (agent/plans/PLAN-enterprise-isolation.md, boxes C1, C2, K2 and P1).

    ./run.sh enterprise add <company> --region <r> --owner <mail> --storage-gb <n>
        [--allow-ip <ip|cidr>]... [--unlisted] [--lookup-domain <d>] [--bench]
        [--bws-project <id>] [--lookup-namespace-id <id>]
    ./run.sh enterprise list [--all] [--bench]
    ./run.sh enterprise update <company> [--max-machines N] [--max-storage-gb N] [--max-expiry-days N]
        [--allow-ip <ip|cidr>]... [--clear-allow-ips] [--ring R --ring-reason T] [--bench]
    ./run.sh enterprise suspend <company> [--resume] [--bench]
    ./run.sh enterprise export <company> [--export-root <dir>] [--bws-project <id>] [--bench]
    ./run.sh enterprise remove <company> [--delete-data --confirm <company>] [--export-root <dir>] [--bench]
    ./run.sh enterprise release ...          (box K2, rediacc_ci.release.rings_run)
    ./run.sh enterprise proof <verb> [--bench]
    ./run.sh enterprise control ensure [--bench] [--region <r>]

`add` (box C1) is `onboarding.run` over the live steps, after `control_db.ensure_all` has made sure every control database of the environment exists with its schema. `list`, `update`, `suspend`, `export` and `remove` are box C2's `lifecycle` verbs over one `lifecycle.Context`; the production Exporter and Teardown adapters over D1, R2, wrangler and bws are not written yet, so the context binds them to a seam that refuses naming what is missing. A verb whose module has not landed refuses with `not built yet: <box>` and exit 2, rather than claiming anything.

EXIT CODES. 0 done; 1 a refusal or a failed step; 2 usage, or a verb not built yet.
"""

from __future__ import annotations

import argparse
import importlib
import os
import pathlib
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from rediacc_ci.enterprise import control_db, onboarding, proof, registry, secrets
from rediacc_ci.ops import enterprise_lookup

if TYPE_CHECKING:
    import types

SELF = "rediacc_ci.enterprise.cli"
LIFECYCLE = "rediacc_ci.enterprise.lifecycle"
RINGS_RUN = "rediacc_ci.release.rings_run"
LIFECYCLE_VERBS = ("list", "update", "suspend", "export", "remove")
EXPORT_ROOT = pathlib.Path.home() / ".local" / "state" / "rediacc" / "enterprise-exports"
ADAPTERS_MISSING = (
    "not built yet: the production lifecycle %s over D1, R2, wrangler and bws "
    "(lifecycle.py declares the protocol; no box has written the adapter)"
)
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


def lifecycle_context(
    lifecycle: Any,
    *,
    bench: bool,
    query: registry.Query | None = None,
    bws_project: str = "",
    export_root: pathlib.Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Any:
    """One `lifecycle.Context` over the control databases; the Exporter and Teardown stay unbound until their adapters exist, and the store needs `--bws-project`."""
    q = query or control_db.transport()
    error = lifecycle.LifecycleError
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
        exporter=Unbound(error, ADAPTERS_MISSING % "Exporter"),
        teardown=Unbound(error, ADAPTERS_MISSING % "Teardown"),
        store=store,
        export_root=export_root or EXPORT_ROOT,
        env=dict(os.environ if env is None else env),
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
