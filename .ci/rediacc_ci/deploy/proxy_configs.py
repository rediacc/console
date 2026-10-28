#!/usr/bin/env python3
"""The proxy Worker's wrangler configs: six generated from one template, two hand-written, all held to one shape.

WHAT IT GENERATES. `workers/proxy/wrangler.template.toml` plus `regions.json` give `wrangler.<target>.toml` for the six deployable targets, `eu`, `us`, `asia` (production) and `edge-eu`, `edge-us`, `edge-asia` (edge). Each names `rediacc-proxy-<r>` or `edge-rediacc-proxy-<r>` (regions.json `proxyWorkerName` / `edgeProxyWorkerName`), routes the custom domain `proxy.<domain>` or `proxy.<edgeDomain>` (the WK_PROXY_*_HOST values of .ci/config/well-known.env), and binds both ACCOUNT (entrypoint CloudflareInternal) and ISSUER (entrypoint ExecutorIssuer) to the same target's account Worker (agent/plans/PLAN-proxy-cd-six-targets.md Design item 7).

WHAT IT REFUSES. `config_refusals(text, target)` is the generalization of `deploy_proxy.bench_refusals` to every target, the bench and dev configs included: the exact name, routes, `[vars]`, service bindings and their entrypoints, container blocks (the legacy `ExecutorContainer` entry at its budget beside the `OrgExecutor` entry of the `durable_object` scheduling policy, which carries no `max_instances` or `instance_type`), the Durable Object bindings, the migration list v1, v2 (and v3), the `EXECUTOR_BACKEND` / `EXECUTOR_CAP` / `EXECUTOR_HEAVY_CAP` vars (a backend in {container, durable}, caps at most 25 and 5), telemetry destinations with `persist = false`, the top-level key allowlist, no `[env.*]` table, no EXECUTOR_TOKEN anywhere in the text, and a name, route, service or destination naming another region or channel refused by name (a us config can never carry an eu binding). `--check` runs it over every file, refuses a generated file that differs from what the template generates, a `wrangler*.toml` that is no known target, a WK_PROXY_*_HOST that disagrees with regions.json, and a workers/account config whose EXECUTOR binding is not the same target's proxy.

USAGE.
    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.proxy_configs [generate]   write the six configs
    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.proxy_configs --check      exit 1 with every refusal, else 0
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import pathlib
import re
import sys
import tomllib

from rediacc_ci import paths
from rediacc_ci.well_known import (
    BENCH_ORIGIN,
    PROXY_ASIA_HOST,
    PROXY_BENCH_HOST,
    PROXY_EDGE_ASIA_HOST,
    PROXY_EDGE_EU_HOST,
    PROXY_EDGE_US_HOST,
    PROXY_EU_HOST,
    PROXY_US_HOST,
)

SELF = "rediacc_ci.deploy.proxy_configs"

PROXY_REL = ("workers", "proxy")
ACCOUNT_REL = ("workers", "account")
REGIONS_REL = "regions.json"
TEMPLATE = "wrangler.template.toml"
BENCH_CONFIG = "wrangler.bench.toml"
DEV_CONFIG = "wrangler.dev.toml"
CONFIG_GLOB = "wrangler*.toml"

PRODUCTION = "production"
EDGE = "edge"
CHANNELS = (PRODUCTION, EDGE)

MAIN = "src/index.ts"
VERSION_BINDING = "CF_VERSION_METADATA"
MAX_INSTANCES = 25
# The stub issuer Worker check:ci-proxy-wrangler-dev-e2e runs beside the dev Worker.
DEV_ISSUER_SERVICE = "rediacc-executor-issuer-dev"
DEV_ACCOUNT_URL = "http://127.0.0.1:9"
CONTAINER_CLASS = "ExecutorContainer"
DURABLE_CLASS = "OrgExecutor"
CAPACITY_CLASS = "ExecutorCapacity"
SCHEDULING_POLICY = "durable_object"
DURABLE_IMAGE_KEY = "executor"
DURABLE_IMAGE = {"dockerfile": "./Dockerfile", "build_context": "../.."}
BACKENDS = ("container", "durable")
# The ceilings the Worker enforces in src/capacity.ts (HARD_CAP, HARD_HEAVY_CAP); a var above either is refused here too.
MAX_EXECUTOR_CAP = 25
MAX_EXECUTOR_HEAVY_CAP = 5
ACCOUNT_BINDING = ("ACCOUNT", "CloudflareInternal")
ISSUER_BINDING = ("ISSUER", "ExecutorIssuer")
FORBIDDEN_TEXT = "EXECUTOR_TOKEN"
# Per target, the three vars that route and bound the durable backend (PLAN-executor-durable-object-policy.md Design item 2). The backend flips one target at a time by editing BACKEND_BY_TARGET and regenerating; the caps are decimal strings the Worker parses.
BACKEND_BY_TARGET: dict[str, str] = dict.fromkeys(
    ("eu", "us", "asia", "edge-eu", "edge-us", "edge-asia", "bench", "dev"), "container"
)
CAP_BY_TARGET: dict[str, str] = dict.fromkeys(BACKEND_BY_TARGET, "25")
HEAVY_CAP_BY_TARGET: dict[str, str] = dict.fromkeys(BACKEND_BY_TARGET, "5")
EXECUTOR_VARS = ("EXECUTOR_BACKEND", "EXECUTOR_CAP", "EXECUTOR_HEAVY_CAP")
PLACEHOLDER_RE = re.compile(r"@@[A-Z_]+@@")

# The WK_PROXY_*_HOST value for each (region, channel); --check holds each equal to proxy.<domain> from regions.json.
HOSTS: dict[tuple[str, str], str] = {
    ("eu", PRODUCTION): PROXY_EU_HOST,
    ("us", PRODUCTION): PROXY_US_HOST,
    ("asia", PRODUCTION): PROXY_ASIA_HOST,
    ("eu", EDGE): PROXY_EDGE_EU_HOST,
    ("us", EDGE): PROXY_EDGE_US_HOST,
    ("asia", EDGE): PROXY_EDGE_ASIA_HOST,
}

# Tokens of a name, route, service or destination (split on `.`, `-`, `_`) that name a region or a channel. A target owns some of them; any other is foreign and refused by name.
CHANNEL_TOKENS = frozenset({"edge", "prod", "production", "stable", "bench", "dev"})
NAME_TOKEN_SPLIT = re.compile(r"[.\-_]")

# The only top-level keys a proxy config may carry: anything else (an `account_id` naming another Cloudflare account, a `workers_dev` or `zone_id` switch) could point the deploy elsewhere. `env` is refused separately.
ALLOWED_KEYS = frozenset(
    {
        "name",
        "main",
        "compatibility_date",
        "compatibility_flags",
        "upload_source_maps",
        "routes",
        "vars",
        "services",
        "version_metadata",
        "containers",
        "durable_objects",
        "migrations",
        "observability",
    }
)

HEADER = (
    "GENERATED by `PYTHONPATH=.ci python3 -m %s` from wrangler.template.toml and regions.json;"
    " edit those and regenerate. `--check` refuses a hand edit." % SELF
)


@dataclasses.dataclass(frozen=True)
class Target:
    """What one proxy config must name, exactly."""

    key: str
    config: str
    name: str
    routes: tuple[str, ...]
    account_url: str
    variables: tuple[tuple[str, str], ...]
    services: tuple[tuple[str, str, str], ...]
    destinations: tuple[str, str] | None
    version_metadata: bool
    max_instances: int
    generated: bool
    own_tokens: frozenset[str]
    executor_vars: tuple[tuple[str, str], ...] = ()


class ConfigError(Exception):
    """regions.json or the template cannot produce the configs."""


def load_regions(root: pathlib.Path) -> list[dict]:
    try:
        data = json.loads((root / REGIONS_REL).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError("%s cannot be read: %s" % (REGIONS_REL, exc)) from None
    regions = data.get("regions") if isinstance(data, dict) else None
    if not isinstance(regions, list) or not regions:
        raise ConfigError("%s carries no regions list" % REGIONS_REL)
    return regions


def _region_tokens(regions: list[dict]) -> frozenset[str]:
    return frozenset(str(r.get("id", "")).lower() for r in regions)


def executor_vars(key: str) -> tuple[tuple[str, str], ...]:
    """The durable-backend vars a target's config carries, from the three per-target tables."""
    return (
        ("EXECUTOR_BACKEND", BACKEND_BY_TARGET[key]),
        ("EXECUTOR_CAP", CAP_BY_TARGET[key]),
        ("EXECUTOR_HEAVY_CAP", HEAVY_CAP_BY_TARGET[key]),
    )


def targets(regions: list[dict]) -> dict[str, Target]:
    """Every proxy config target, keyed by its config suffix: the six generated ones, bench and dev."""
    out: dict[str, Target] = {}
    for region in regions:
        rid = str(region["id"])
        for channel in CHANNELS:
            edge = channel == EDGE
            key = "%s-%s" % (EDGE, rid) if edge else rid
            domain = str(region["edgeDomain"] if edge else region["domain"])
            account = str(region["edgeWorkerName"] if edge else region["workerName"])
            name = region.get("edgeProxyWorkerName" if edge else "proxyWorkerName")
            if not name:
                raise ConfigError(
                    "%s region %s names no %s"
                    % (REGIONS_REL, rid, "edgeProxyWorkerName" if edge else "proxyWorkerName")
                )
            host = HOSTS.get((rid, channel))
            if host is None:
                raise ConfigError(
                    "region %s has no WK_PROXY_*_HOST for %s in .ci/config/well-known.env"
                    % (rid, channel)
                )
            account_url = "https://" + domain
            out[key] = Target(
                key=key,
                config="wrangler.%s.toml" % key,
                name=str(name),
                routes=(host,),
                account_url=account_url,
                variables=(("ACCOUNT_URL", account_url), ("REGION", rid), ("ENVIRONMENT", channel)),
                services=(
                    (ACCOUNT_BINDING[0], account, ACCOUNT_BINDING[1]),
                    (ISSUER_BINDING[0], account, ISSUER_BINDING[1]),
                ),
                destinations=("otlp-%s-logs" % rid, "otlp-%s-traces" % rid),
                version_metadata=True,
                max_instances=MAX_INSTANCES,
                generated=True,
                own_tokens=frozenset({rid, EDGE} if edge else {rid}),
                executor_vars=executor_vars(key),
            )
    out["bench"] = Target(
        key="bench",
        config=BENCH_CONFIG,
        name="rediacc-proxy-bench",
        routes=(PROXY_BENCH_HOST,),
        account_url=BENCH_ORIGIN,
        variables=(("ACCOUNT_URL", BENCH_ORIGIN), ("REGION", "eu"), ("ENVIRONMENT", "bench")),
        services=(
            (ACCOUNT_BINDING[0], "rediacc-account-bench", ACCOUNT_BINDING[1]),
            (ISSUER_BINDING[0], "rediacc-account-bench", ISSUER_BINDING[1]),
        ),
        destinations=("otlp-bench-logs", "otlp-bench-traces"),
        version_metadata=True,
        max_instances=MAX_INSTANCES,
        generated=False,
        own_tokens=frozenset({"bench"}),
        executor_vars=executor_vars("bench"),
    )
    out["dev"] = Target(
        key="dev",
        config=DEV_CONFIG,
        name="rediacc-proxy-dev",
        routes=(),
        account_url=DEV_ACCOUNT_URL,
        variables=(("ACCOUNT_URL", DEV_ACCOUNT_URL),),
        services=((ISSUER_BINDING[0], DEV_ISSUER_SERVICE, ISSUER_BINDING[1]),),
        destinations=None,
        version_metadata=True,
        max_instances=MAX_INSTANCES,
        generated=False,
        own_tokens=frozenset({"dev"}),
        executor_vars=executor_vars("dev"),
    )
    return out


def render(template: str, target: Target) -> str:
    """The generated config text for one target."""
    if not target.generated or target.destinations is None:
        raise ConfigError("%s is hand-written, not generated" % target.config)
    account = target.services[0][1]
    values = {
        "HEADER": HEADER,
        "NAME": target.name,
        "ROUTE": target.routes[0],
        "ACCOUNT_URL": target.account_url,
        "REGION": dict(target.variables)["REGION"],
        "ENVIRONMENT": dict(target.variables)["ENVIRONMENT"],
        "ACCOUNT_SERVICE": account,
        "OTLP_LOGS": target.destinations[0],
        "OTLP_TRACES": target.destinations[1],
        **dict(target.executor_vars),
    }
    text = template
    for key, value in values.items():
        text = text.replace("@@%s@@" % key, value)
    left = sorted(set(PLACEHOLDER_RE.findall(text)))
    if left:
        raise ConfigError("%s leaves %s unfilled" % (TEMPLATE, ", ".join(left)))
    return text


def _routes(config: dict) -> list:
    raw = config.get("routes")
    entries = list(raw) if isinstance(raw, list) else []
    if "route" in config:
        entries.append(config["route"])
    return entries


def _pattern(entry) -> str:
    return str(entry.get("pattern", "")) if isinstance(entry, dict) else str(entry)


def _executor_var_refusals(variables: dict) -> list[str]:
    out: list[str] = []
    backend = variables.get("EXECUTOR_BACKEND")
    if backend not in BACKENDS:
        out.append("vars.EXECUTOR_BACKEND is %r, not one of %s" % (backend, "/".join(BACKENDS)))
    for name, ceiling in (
        ("EXECUTOR_CAP", MAX_EXECUTOR_CAP),
        ("EXECUTOR_HEAVY_CAP", MAX_EXECUTOR_HEAVY_CAP),
    ):
        raw = variables.get(name)
        if not (isinstance(raw, str) and raw.isascii() and raw.isdecimal()):
            out.append("vars.%s is %r, not a decimal string" % (name, raw))
        elif int(raw) > ceiling:
            out.append("vars.%s is %r, over the ceiling of %d" % (name, raw, ceiling))
    return out


def _executor_refusals(config: dict, target: Target) -> list[str]:
    """The container, Durable Object and migration blocks: the legacy and durable entries together, or the durable entry alone once Phase 3 retires the legacy class."""
    out: list[str] = []
    raw = config.get("containers")
    # A non-table element of an inline `containers = [...]` array stays in the count, so it matches neither class and refuses.
    containers = raw if isinstance(raw, list) else []
    tables = [c for c in containers if isinstance(c, dict)]
    legacy = [c for c in tables if c.get("class_name") == CONTAINER_CLASS]
    durable = [c for c in tables if c.get("class_name") == DURABLE_CLASS]
    if len(containers) != len(legacy) + len(durable) or len(durable) != 1 or len(legacy) > 1:
        out.append(
            "[[containers]] is %r, not the %s entry beside at most one %s entry"
            % (
                [c.get("class_name") if isinstance(c, dict) else c for c in containers],
                DURABLE_CLASS,
                CONTAINER_CLASS,
            )
        )
    for entry in legacy:
        for ckey, cvalue in (
            ("image", "./Dockerfile"),
            ("image_build_context", "../.."),
            ("max_instances", target.max_instances),
        ):
            if entry.get(ckey) != cvalue:
                out.append("[[containers]] %s is %r, not %r" % (ckey, entry.get(ckey), cvalue))
        if "scheduling_policy" in entry:
            out.append("[[containers]] %s names a scheduling_policy" % CONTAINER_CLASS)
    for entry in durable:
        if entry.get("scheduling_policy") != SCHEDULING_POLICY:
            out.append(
                "[[containers]] %s scheduling_policy is %r, not %r"
                % (DURABLE_CLASS, entry.get("scheduling_policy"), SCHEDULING_POLICY)
            )
        out.extend(
            "[[containers]] %s sets %s; wrangler refuses it under %s, and the cap lives in capacity.ts"
            % (DURABLE_CLASS, key, SCHEDULING_POLICY)
            for key in ("max_instances", "instance_type")
            if key in entry
        )
        if entry.get("images") != {DURABLE_IMAGE_KEY: DURABLE_IMAGE}:
            out.append(
                "[[containers]] %s images is %r, not exactly {%r: %r}"
                % (DURABLE_CLASS, entry.get("images"), DURABLE_IMAGE_KEY, DURABLE_IMAGE)
            )
        extra = sorted(set(entry) - {"class_name", "scheduling_policy", "images"})
        if extra:
            out.append("[[containers]] %s carries %s, which it may not" % (DURABLE_CLASS, extra))

    bindings = (config.get("durable_objects") or {}).get("bindings")
    wanted = [
        {"name": "ORG_EXECUTOR", "class_name": DURABLE_CLASS},
        {"name": "EXECUTOR_CAPACITY", "class_name": CAPACITY_CLASS},
    ]
    legacy_binding = {"name": "EXECUTOR", "class_name": CONTAINER_CLASS}
    allowed = ([legacy_binding, *wanted], wanted)
    if bindings not in allowed or (bindings == wanted and legacy):
        out.append(
            "[[durable_objects.bindings]] is %r, not %s"
            % (bindings, " or ".join(repr(a) for a in allowed))
        )
    if (bindings == allowed[0]) != bool(legacy):
        out.append(
            "the EXECUTOR binding and the %s entry must stand or go together" % CONTAINER_CLASS
        )

    v1 = {"tag": "v1", "new_sqlite_classes": [CONTAINER_CLASS]}
    v2 = {"tag": "v2", "new_sqlite_classes": [DURABLE_CLASS, CAPACITY_CLASS]}
    v3 = {"tag": "v3", "deleted_classes": [CONTAINER_CLASS]}
    migrations = config.get("migrations")
    if migrations not in ([v1, v2], [v1, v2, v3]):
        out.append("[[migrations]] is %r, not v1, v2 (and v3)" % (migrations,))
    elif (migrations == [v1, v2, v3]) == bool(legacy):
        out.append(
            "the v3 migration and the %s entry cannot both stand or both go" % CONTAINER_CLASS
        )
    return out


def config_refusals(text: str, target: Target, all_regions: frozenset[str]) -> list[str]:
    """Why this text must not stand as `target`'s proxy config; empty when it may.

    `all_regions` is every region id in regions.json, so a token naming any region or channel the target does not own is refused by name.
    """
    try:
        config = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return ["does not parse as TOML: %s" % exc]
    out: list[str] = []
    foreign = (all_regions | CHANNEL_TOKENS) - target.own_tokens

    def foreign_hits(label: str, value: str) -> None:
        hits = [t for t in NAME_TOKEN_SPLIT.split(value.lower()) if t in foreign]
        if hits:
            out.append(
                "%s %r names %s, which is not %s" % (label, value, "/".join(hits), target.key)
            )

    if FORBIDDEN_TEXT in text:
        out.append(
            "the text names %s; the token comes from the ISSUER binding, never a secret or var"
            % FORBIDDEN_TEXT
        )

    name = config.get("name")
    if name != target.name:
        out.append("name is %r, not %r" % (name, target.name))
    foreign_hits("name", str(name or ""))

    out.extend(
        "top-level key %r is not one a proxy config may carry" % key
        for key in sorted(set(config) - ALLOWED_KEYS - {"env"})
    )
    if "env" in config:
        out.append("an [env.*] table can rename the Worker or its routes; a config carries none")
    if config.get("main") != MAIN:
        out.append("main is %r, not %r" % (config.get("main"), MAIN))

    routes = _routes(config)
    patterns = [_pattern(r) for r in routes]
    if patterns != list(target.routes):
        out.append("routes are %r, not exactly %r" % (patterns, list(target.routes)))
    for entry in routes:
        if not (isinstance(entry, dict) and entry.get("custom_domain") is True):
            out.append("route %r is not a custom domain" % _pattern(entry))
        foreign_hits("route", _pattern(entry))

    variables = config.get("vars") or {}
    want = dict(target.variables)
    for key, value in want.items():
        if variables.get(key) != value:
            out.append("vars.%s is %r, not %r" % (key, variables.get(key), value))
    out.extend(
        "vars.%s is not one a %s config may carry" % (key, target.key)
        for key in sorted(set(variables) - set(want) - set(EXECUTOR_VARS))
    )
    out.extend(_executor_var_refusals(variables))

    services = config.get("services") or []
    seen: dict[str, list[dict]] = {}
    for entry in services:
        if not isinstance(entry, dict):
            out.append("[[services]] entry %r is not a table" % (entry,))
            continue
        seen.setdefault(str(entry.get("binding", "")), []).append(entry)
        foreign_hits(
            "[[services]] %s service" % entry.get("binding"), str(entry.get("service", ""))
        )
    for binding, service, entrypoint in target.services:
        got = seen.get(binding, [])
        if [e.get("service") for e in got] != [service]:
            out.append(
                "the %s service binding is %r, not exactly one binding to %r"
                % (binding, [e.get("service") for e in got], service)
            )
        elif got[0].get("entrypoint") != entrypoint:
            out.append(
                "the %s service binding's entrypoint is %r, not %r"
                % (binding, got[0].get("entrypoint"), entrypoint)
            )
    out.extend(
        "[[services]] binding %r is not one a %s config may carry" % (binding, target.key)
        for binding in sorted(set(seen) - {b for b, _, _ in target.services})
    )

    if target.version_metadata and config.get("version_metadata") != {"binding": VERSION_BINDING}:
        out.append(
            "[version_metadata] is %r, not exactly binding = %r"
            % (config.get("version_metadata"), VERSION_BINDING)
        )

    out.extend(_executor_refusals(config, target))

    observability = config.get("observability")
    if target.destinations is None:
        if observability is not None:
            out.append("[observability] is set; the %s config exports nothing" % target.key)
    else:
        obs = observability if isinstance(observability, dict) else {}
        if obs.get("enabled") is not True:
            out.append("observability.enabled is %r, not true" % obs.get("enabled"))
        for section, dest in zip(("logs", "traces"), target.destinations, strict=True):
            raw_block = obs.get(section)
            block: dict = raw_block if isinstance(raw_block, dict) else {}
            dests = block.get("destinations")
            if dests != [dest]:
                out.append("observability.%s.destinations is %r, not [%r]" % (section, dests, dest))
            for d in dests if isinstance(dests, list) else []:
                foreign_hits("observability.%s destination" % section, str(d))
            if block.get("persist") is not False:
                out.append(
                    "observability.%s.persist is %r; Cloudflare keeps no copy, so it is false"
                    % (section, block.get("persist"))
                )
            if block.get("enabled") is not True:
                out.append(
                    "observability.%s.enabled is %r, not true" % (section, block.get("enabled"))
                )
    return out


def account_refusals(
    text: str, proxy_name: str, key: str, all_regions: frozenset[str], own: frozenset[str]
) -> list[str]:
    """Why a workers/account config does not bind EXECUTOR to exactly its own target's proxy."""
    try:
        config = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return ["does not parse as TOML: %s" % exc]
    out: list[str] = []
    services = [s for s in config.get("services") or [] if isinstance(s, dict)]
    executor = [s.get("service") for s in services if s.get("binding") == "EXECUTOR"]
    if executor != [proxy_name]:
        out.append(
            "the EXECUTOR service binding is %r, not exactly one binding to %r"
            % (executor, proxy_name)
        )
    foreign = (all_regions | CHANNEL_TOKENS) - own
    for entry in services:
        value = str(entry.get("service", ""))
        hits = [t for t in NAME_TOKEN_SPLIT.split(value.lower()) if t in foreign]
        if hits:
            out.append(
                "[[services]] %s service %r names %s, which is not %s"
                % (entry.get("binding"), value, "/".join(hits), key)
            )
    return out


def generate(root: pathlib.Path) -> dict[str, str]:
    """`{config file name: text}` for the six generated targets."""
    template = (root.joinpath(*PROXY_REL) / TEMPLATE).read_text(encoding="utf-8")
    return {
        t.config: render(template, t) for t in targets(load_regions(root)).values() if t.generated
    }


def check(root: pathlib.Path) -> list[str]:
    """Every refusal over the tree at `root`; empty when the configs hold."""
    out: list[str] = []
    try:
        regions = load_regions(root)
        all_targets = targets(regions)
        rendered = generate(root)
    except (ConfigError, OSError, KeyError) as exc:
        return ["%s: %s" % (SELF, exc)]
    all_regions = _region_tokens(regions)
    proxy_dir = root.joinpath(*PROXY_REL)
    rel = "/".join(PROXY_REL)

    for region in regions:
        for channel in CHANNELS:
            domain = region["edgeDomain" if channel == EDGE else "domain"]
            host = HOSTS[(str(region["id"]), channel)]
            if host != "proxy." + domain:
                out.append(
                    ".ci/config/well-known.env: the %s %s proxy host is %r, not %r"
                    % (region["id"], channel, host, "proxy." + domain)
                )

    known = {TEMPLATE} | {t.config for t in all_targets.values()}
    out.extend(
        "%s/%s is no known proxy target; the configs are %s"
        % (rel, path.name, ", ".join(sorted(known - {TEMPLATE})))
        for path in sorted(proxy_dir.glob(CONFIG_GLOB))
        if path.name not in known
    )

    for target in all_targets.values():
        path = proxy_dir / target.config
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            out.append("%s/%s cannot be read: %s" % (rel, target.config, exc.strerror or exc))
            continue
        if target.generated:
            if text != rendered[target.config]:
                out.append(
                    "%s/%s is stale: it differs from what %s and %s generate; run `PYTHONPATH=.ci python3 -m %s`"
                    % (rel, target.config, TEMPLATE, REGIONS_REL, SELF)
                )
            out.extend(
                "%s/%s (as generated): %s" % (rel, target.config, r)
                for r in config_refusals(rendered[target.config], target, all_regions)
            )
        out.extend(
            "%s/%s: %s" % (rel, target.config, r)
            for r in config_refusals(text, target, all_regions)
        )

    account_dir = root.joinpath(*ACCOUNT_REL)
    for target in all_targets.values():
        if target.key == "dev":
            continue
        path = account_dir / target.config
        arel = "/".join(ACCOUNT_REL) + "/" + target.config
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            out.append("%s cannot be read: %s" % (arel, exc.strerror or exc))
            continue
        out.extend(
            "%s: %s" % (arel, r)
            for r in account_refusals(text, target.name, target.key, all_regions, target.own_tokens)
        )
    return out


def write(root: pathlib.Path) -> list[str]:
    proxy_dir = root.joinpath(*PROXY_REL)
    written = []
    for name, text in generate(root).items():
        path = proxy_dir / name
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
            written.append(name)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=SELF, description=__doc__.splitlines()[0])
    parser.add_argument("command", nargs="?", choices=["generate"], default="generate")
    parser.add_argument(
        "--check", action="store_true", help="refuse drift and bad shapes; write nothing"
    )
    parser.add_argument("--root", type=pathlib.Path, default=None, help="repository root (tests)")
    args = parser.parse_args(argv)
    root = args.root or paths.repo_root()
    if args.check:
        reasons = check(root)
        for reason in reasons:
            print("%s: %s" % (SELF, reason), file=sys.stderr)
        if reasons:
            print("%s: %d refusal(s)" % (SELF, len(reasons)), file=sys.stderr)
            return 1
        print("%s: %d proxy configs hold" % (SELF, len(targets(load_regions(root)))))
        return 0
    try:
        written = write(root)
    except (ConfigError, OSError, KeyError) as exc:
        print("%s: %s" % (SELF, exc), file=sys.stderr)
        return 1
    print("%s: wrote %s" % (SELF, ", ".join(written) if written else "nothing (all current)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
