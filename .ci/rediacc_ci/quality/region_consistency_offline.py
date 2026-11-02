"""check:ci-region-consistency, offline layer: the seven account targets are one shape, modulo the documented per-target differences.

THE SEVEN TARGETS. `stable-{eu,us,asia}`, `edge-{eu,us,asia}` (one per `regions.json` region and channel) and `bench`. Each is an account Worker, a proxy Worker, a D1 database, two R2 buckets (CONFIG_BUCKET, BACKUP_BUCKET) and a bws profile that feeds its secret push. Operator ask 2026-10-29: "a CI job to check consistency between regions (2*3+1)".

WHY. Every per-target fact is written down more than once (regions.json, workers/account/wrangler.<t>.toml, workers/proxy/wrangler.<t>.toml, the `account-secrets-<r>-<c>` and `deploy-bench` profiles of .ci/config/secret-supply.json) and each family was grown one target at a time. Siblings that check one slice exist and are not repeated here: check:ci-backup-bucket-conformance (BACKUP_BUCKET name and jurisdiction against regions.json), check:ci-proxy-configs (every proxy toml against its template), check:ci-builder-env-contract (CD's env exports against the pusher), check:ci-backup-credential-isolation (the backup key pairs). None of them asks the cross-target question: is target X missing something the other six have, or naming something that belongs to another target.

OFFLINE LAYER (this module, every CI run, no credential):
  regions    every regions.json name follows its pattern (`{edge-}rediacc-account-<r>`, `{edge-}account-db-<r>`, `{edge-}rediacc-{configs,backups}-<r>`, `{edge-}rediacc-proxy-<r>`, `<r>.rediacc.com` / `edge-<r>.rediacc.com`, suffix `<R>`), bench by the same pattern with `<r>` = bench;
  account    each account toml: name, route, D1 name (and a database_id no other target shares), both bucket names and jurisdictions, EXECUTOR service, REGION / WEBAUTHN vars, observability destinations, and a structural SHAPE (binding names per kind, crons, compatibility, assets and observability knobs) equal to the reference target stable-<default region>, modulo `SHAPE_EXCEPTIONS`;
  proxy      each proxy toml: name, route, ACCOUNT and ISSUER services naming this target's account Worker, ACCOUNT_URL, REGION, ENVIRONMENT, destinations;
  profile    each regional profile binds exactly the store names the pusher reads for its region and channel (derived from set_account_worker_secrets' own constants and read_env source), no other target's name, and the three regions of a channel are equal modulo the suffix; bench's profile binds every per-target family under its `_BENCH` name; bench's push payload carries exactly the regional pusher's Worker keys.

LIVE LAYER (`--live`, rediacc_ci.quality.region_consistency_live; `main` is in rediacc_ci.quality.region_consistency): the same seven targets against Cloudflare.

ANTI-VACUITY. Fewer than 7 targets, a missing toml or profile, or zero parsed bindings is exit 2. The success line prints the counts. `--selftest` plants one drift per class into a copy of the real inputs and requires each to go red, and plants benign changes that must stay green.

Exit 0 consistent, 1 drift, 2 no verdict.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import re
import tomllib
from typing import TYPE_CHECKING

from rediacc_ci.deploy import account_secrets_local as local_push
from rediacc_ci.deploy import set_account_worker_secrets as pusher
from rediacc_ci.well_known import APEX_DOMAIN, BENCH_ORIGIN

if TYPE_CHECKING:
    import pathlib

SELF = "region-consistency"
EXPECTED_TARGETS = 7
REGIONS_REL = "regions.json"
SUPPLY_REL = ".ci/config/secret-supply.json"
BENCH_DEPLOY_REL = ".ci/rediacc_ci/ops/deploy_bench.py"
BENCH = "bench"
BENCH_DOMAIN = BENCH_ORIGIN.removeprefix("https://")
STABLE, EDGE = "stable", "edge"
BENCH_PROFILE = "deploy-bench"
CLASSES = ("regions", "account", "proxy", "profile")

# Names a regional profile binds that the pusher does not read: account_secrets_local's own preflight (wrangler token and account, and the Turnstile drift check that compares the site key with the secret).
PREFLIGHT_NAMES = frozenset({"CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "TURNSTILE_SITE_KEY"})
# The per-target secret families bench binds under its own `_BENCH` store name (deploy-bench profile `F_BENCH > F`).
BENCH_FAMILIES = (
    "AWS_SES_ACCESS_KEY_ID",
    "AWS_SES_SECRET_ACCESS_KEY",
    "OBS_OTLP_CREDENTIALS",
    "ACCOUNT_CONFIG_SERVER_KEY",
    "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID",
    "ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY",
    "CLOUDFLARE_TURNSTILE_SECRET_KEY",
)
# The six signing and session store names every regional profile binds and bench binds the same way, unaliased (production key, operator 2026-10-29).
BENCH_UNALIASED = (
    "ACCOUNT_ED25519_PRIVATE_KEY",
    "ACCOUNT_ED25519_PUBLIC_KEY",
    "ACCOUNT_X25519_PRIVATE_KEY",
    "ACCOUNT_X25519_PUBLIC_KEY",
    "ACCOUNT_SERVER_API_KEY",
    "ACCOUNT_JWT_SECRET",
)
# Vars each channel's account toml carries beyond REGION / WEBAUTHN_RP_ID / WEBAUTHN_ORIGIN, with the value where it is fixed.
CHANNEL_VARS: dict[str, dict[str, str | None]] = {
    STABLE: {},
    EDGE: {"ENVIRONMENT": "edge"},
    # Bench-only switches, each documented in wrangler.bench.toml as "never add to a production config".
    BENCH: {
        "ENVIRONMENT": "bench",
        "ALLOWED_EMAIL_DOMAINS": None,
        "TURNSTILE_ENABLED": "false",
        "EMAIL_CAPTURE_D1": "true",
    },
}
PROXY_ENVIRONMENT = {STABLE: "production", EDGE: "edge", BENCH: "bench"}
# (target, shape field) -> the reason it may differ from the reference. Printed every run, so an exemption stays visible.
SHAPE_EXCEPTIONS: dict[tuple[str, str], str] = {
    (BENCH, "assets.directory"): (
        "bench builds its keyless portal into ./bench/dist so a bench build can never ship to "
        "stable (wrangler.bench.toml, 2026-10-28 incident)"
    ),
}


@dataclasses.dataclass(frozen=True)
class Target:
    """One of the seven: every name derived from the pattern, plus where its declarations live."""

    id: str
    channel: str
    region: str
    suffix: str
    account_worker: str
    proxy_worker: str
    d1: str
    config_bucket: str
    backup_bucket: str
    domain: str
    jurisdiction: str | None
    otlp: str

    @property
    def account_toml(self) -> str:
        return "workers/account/wrangler.%s.toml" % self.file_stem

    @property
    def proxy_toml(self) -> str:
        return "workers/proxy/wrangler.%s.toml" % self.file_stem

    @property
    def file_stem(self) -> str:
        return {STABLE: self.region, EDGE: "edge-" + self.region, BENCH: BENCH}[self.channel]

    @property
    def profile(self) -> str:
        if self.channel == BENCH:
            return BENCH_PROFILE
        return local_push.profile_name(self.region, self.channel)


@dataclasses.dataclass(frozen=True)
class Finding:
    target: str
    cls: str
    message: str

    def line(self) -> str:
        return "  %-11s %-8s %s" % (self.target, self.cls, self.message)


class NoVerdictError(Exception):
    """The gate cannot rule: an input is missing or unreadable."""


def pattern(channel: str, rid: str, jurisdiction: str | None) -> Target:
    """The target every regions.json row and the bench constants must equal."""
    pre = "edge-" if channel == EDGE else ""
    domain = BENCH_DOMAIN if channel == BENCH else "%s%s.%s" % (pre, rid, APEX_DOMAIN)
    return Target(
        id=BENCH if channel == BENCH else "%s-%s" % (channel, rid),
        channel=channel,
        region=rid,
        suffix=rid.upper(),
        account_worker="%srediacc-account-%s" % (pre, rid),
        proxy_worker="%srediacc-proxy-%s" % (pre, rid),
        d1="%saccount-db-%s" % (pre, rid),
        config_bucket="%srediacc-configs-%s" % (pre, rid),
        backup_bucket="%srediacc-backups-%s" % (pre, rid),
        domain=domain,
        jurisdiction=jurisdiction,
        otlp=rid,
    )


def targets_from(doc: dict) -> tuple[list[Target], list[Finding]]:
    """The seven targets, and every regions.json value that disagrees with its pattern."""
    rows = doc.get("regions") if isinstance(doc, dict) else None
    if not isinstance(rows, list) or not rows:
        raise NoVerdictError("regions.json has no `regions` list; nothing to compare")
    out: list[Target] = []
    found: list[Finding] = []
    for row in rows:
        rid = row.get("id", "")
        jur = row.get("r2Jurisdiction")
        for channel, fields in (
            (STABLE, ("workerName", "proxyWorkerName", "d1", "r2", "backupR2", "domain")),
            (
                EDGE,
                (
                    "edgeWorkerName",
                    "edgeProxyWorkerName",
                    "edgeD1",
                    "edgeR2",
                    "edgeBackupR2",
                    "edgeDomain",
                ),
            ),
        ):
            t = pattern(channel, rid, jur)
            want = (
                t.account_worker,
                t.proxy_worker,
                t.d1,
                t.config_bucket,
                t.backup_bucket,
                t.domain,
            )
            for field, expect in zip(fields, want, strict=True):
                got = row.get(field)
                got = got.get("name") if isinstance(got, dict) else got
                if got != expect:
                    found.append(
                        Finding(
                            t.id,
                            "regions",
                            "regions.json %s is %r, the pattern says %r" % (field, got, expect),
                        )
                    )
            out.append(t)
        if row.get("secretSuffix") != rid.upper():
            found.append(
                Finding(
                    "stable-" + rid,
                    "regions",
                    "secretSuffix %r is not %r" % (row.get("secretSuffix"), rid.upper()),
                )
            )
        if "r2Jurisdiction" not in row:
            found.append(
                Finding(
                    "stable-" + rid,
                    "regions",
                    "regions.json carries no r2Jurisdiction key (null is a value; absent is not)",
                )
            )
    out.append(pattern(BENCH, BENCH, None))
    return out, found


def blocks(doc: dict, kind: str) -> dict[str, dict]:
    return {
        str(b.get("binding") or b.get("name") or ""): b
        for b in doc.get(kind, [])
        if isinstance(b, dict)
    }


def account_shape(doc: dict) -> dict[str, object]:
    """The structural facts that must be equal across the seven account tomls."""
    obs = doc.get("observability", {})
    assets = doc.get("assets", {})
    return {
        "top-level keys": sorted(doc),
        "main": doc.get("main"),
        "compatibility_date": doc.get("compatibility_date"),
        "compatibility_flags": doc.get("compatibility_flags"),
        "upload_source_maps": doc.get("upload_source_maps"),
        "triggers.crons": doc.get("triggers", {}).get("crons"),
        "d1 bindings": sorted(blocks(doc, "d1_databases")),
        "d1 migrations_dir": sorted({b.get("migrations_dir") for b in doc.get("d1_databases", [])}),
        "r2 bindings": sorted(blocks(doc, "r2_buckets")),
        "service bindings": sorted(blocks(doc, "services")),
        "var keys (base)": sorted(
            k for k in doc.get("vars", {}) if k in ("REGION", "WEBAUTHN_RP_ID", "WEBAUTHN_ORIGIN")
        ),
        "assets.binding": assets.get("binding"),
        "assets.directory": assets.get("directory"),
        "assets.not_found_handling": assets.get("not_found_handling"),
        "assets.run_worker_first": assets.get("run_worker_first"),
        "observability.enabled": obs.get("enabled"),
        "observability.logs.enabled": obs.get("logs", {}).get("enabled"),
        "observability.logs.invocation_logs": obs.get("logs", {}).get("invocation_logs"),
        "observability.logs.persist": obs.get("logs", {}).get("persist"),
        "observability.traces.enabled": obs.get("traces", {}).get("enabled"),
        "observability.traces.persist": obs.get("traces", {}).get("persist"),
    }


def _routes(doc: dict) -> list[tuple[object, object]]:
    return [
        (r.get("pattern"), r.get("custom_domain"))
        for r in doc.get("routes", [])
        if isinstance(r, dict)
    ]


def _destinations(doc: dict) -> tuple[object, object]:
    obs = doc.get("observability", {})
    return obs.get("logs", {}).get("destinations"), obs.get("traces", {}).get("destinations")


def check_account(t: Target, doc: dict, ref: dict[str, object]) -> list[Finding]:
    f: list[Finding] = []

    def bad(msg: str) -> None:
        f.append(Finding(t.id, "account", "%s: %s" % (t.account_toml, msg)))

    if doc.get("name") != t.account_worker:
        bad("name %r, expected %r" % (doc.get("name"), t.account_worker))
    if _routes(doc) != [(t.domain, True)]:
        bad("routes %r, expected one custom domain %r" % (_routes(doc), t.domain))
    db = blocks(doc, "d1_databases").get("DB", {})
    if db.get("database_name") != t.d1:
        bad("DB database_name %r, expected %r" % (db.get("database_name"), t.d1))
    r2 = blocks(doc, "r2_buckets")
    for binding, want in (("CONFIG_BUCKET", t.config_bucket), ("BACKUP_BUCKET", t.backup_bucket)):
        got = r2.get(binding, {})
        if got.get("bucket_name") != want:
            bad("%s bucket_name %r, expected %r" % (binding, got.get("bucket_name"), want))
        if got.get("jurisdiction") != t.jurisdiction:
            bad(
                "%s jurisdiction %r, regions.json says %r"
                % (binding, got.get("jurisdiction"), t.jurisdiction)
            )
    ex = blocks(doc, "services").get("EXECUTOR", {})
    if ex.get("service") != t.proxy_worker:
        bad("EXECUTOR service %r, expected %r" % (ex.get("service"), t.proxy_worker))
    want_vars: dict[str, str | None] = {
        "REGION": "eu" if t.channel == BENCH else t.region,
        "WEBAUTHN_RP_ID": t.domain,
        "WEBAUTHN_ORIGIN": "https://" + t.domain,
        **CHANNEL_VARS[t.channel],
    }
    got_vars = doc.get("vars", {})
    if sorted(got_vars) != sorted(want_vars):
        bad(
            "[vars] keys %s, the %s channel carries %s"
            % (sorted(got_vars), t.channel, sorted(want_vars))
        )
    for key, value in want_vars.items():
        if value is not None and key in got_vars and got_vars[key] != value:
            bad("[vars] %s=%r, expected %r" % (key, got_vars[key], value))
    want_dest = (["otlp-%s-logs" % t.otlp], ["otlp-%s-traces" % t.otlp])
    if _destinations(doc) != want_dest:
        bad("observability destinations %r, expected %r" % (_destinations(doc), want_dest))
    shape = account_shape(doc)
    for field, actual in shape.items():
        if actual != ref[field] and (t.id, field) not in SHAPE_EXCEPTIONS:
            bad("%s is %r where the reference target has %r" % (field, actual, ref[field]))
    return f


def check_proxy(t: Target, doc: dict) -> list[Finding]:
    f: list[Finding] = []

    def bad(msg: str) -> None:
        f.append(Finding(t.id, "proxy", "%s: %s" % (t.proxy_toml, msg)))

    if doc.get("name") != t.proxy_worker:
        bad("name %r, expected %r" % (doc.get("name"), t.proxy_worker))
    if _routes(doc) != [("proxy." + t.domain, True)]:
        bad("routes %r, expected one custom domain %r" % (_routes(doc), "proxy." + t.domain))
    services = blocks(doc, "services")
    for binding in ("ACCOUNT", "ISSUER"):
        if services.get(binding, {}).get("service") != t.account_worker:
            bad(
                "%s service %r, expected this target's account Worker %r"
                % (binding, services.get(binding, {}).get("service"), t.account_worker)
            )
    v = doc.get("vars", {})
    for key, want in (
        ("ACCOUNT_URL", "https://" + t.domain),
        ("REGION", "eu" if t.channel == BENCH else t.region),
        ("ENVIRONMENT", PROXY_ENVIRONMENT[t.channel]),
    ):
        if v.get(key) != want:
            bad("[vars] %s=%r, expected %r" % (key, v.get(key), want))
    want_dest = (["otlp-%s-logs" % t.otlp], ["otlp-%s-traces" % t.otlp])
    if _destinations(doc) != want_dest:
        bad("observability destinations %r, expected %r" % (_destinations(doc), want_dest))
    return f


def check_d1_ids(targets: list[Target], docs: dict[str, dict]) -> list[Finding]:
    """Two targets sharing a database_id would write one database from two Workers: a copy-paste shape."""
    seen: dict[str, str] = {}
    f: list[Finding] = []
    for t in targets:
        uuid = blocks(docs[t.id], "d1_databases").get("DB", {}).get("database_id")
        if not uuid:
            f.append(Finding(t.id, "account", "%s: DB carries no database_id" % t.account_toml))
        elif uuid in seen:
            f.append(
                Finding(
                    t.id,
                    "account",
                    "%s: DB database_id is also %s's" % (t.account_toml, seen[uuid]),
                )
            )
        else:
            seen[uuid] = t.id
    return f


def pusher_reads() -> frozenset[str]:
    """The literal names set_account_worker_secrets.read_env reads, from its own source."""
    return frozenset(
        re.findall(r'os\.environ\.get\(\s*"([A-Z][A-Z0-9_]*)"', inspect.getsource(pusher.read_env))
    )


def expected_store_names(t: Target, reads: frozenset[str], suffixes: set[str]) -> set[str]:
    """What the profile of a regional target must bind: what the pusher reads for it, minus what regions.json derives."""
    derived = DERIVED_NAMES
    own = pusher.BACKUP_PAIR_STABLE if t.channel == STABLE else pusher.BACKUP_PAIR_EDGE
    other = pusher.BACKUP_PAIR_EDGE if t.channel == STABLE else pusher.BACKUP_PAIR_STABLE
    names = set(reads) - derived - set(other)
    names -= {
        n for n in names if any(n.endswith("_" + s) for s in suffixes)
    }  # region literals, re-added below
    names |= set(own)
    if t.channel != STABLE:
        names -= set(pusher.REQUIRED_NONEMPTY_STABLE)
    for prefix in pusher.SUFFIXED_PREFIXES:
        if prefix == "STRIPE_WEBHOOK_SECRET" and t.channel != STABLE:
            continue
        names.add("%s_%s" % (prefix, t.suffix))
    if t.suffix == pusher.ASIA:
        names |= set(pusher.ASIA_BORROWS)
    channel = pusher.CHANNEL_STABLE if t.channel == STABLE else pusher.CHANNEL_EDGE
    for prefix in pusher.SUFFIXED_CHANNEL_PREFIXES:
        names.add("%s_%s_%s" % (prefix, t.suffix, channel))
    return names


# The non-secret inputs account_secrets_local.derive() takes from regions.json; never a store name. The selftest holds this set equal to derive()'s keys.
DERIVED_NAMES = frozenset(
    {
        "WORKER_NAME",
        "TARGET",
        "SUFFIX",
        "AWS_SES_REGION",
        "BACKUP_BUCKET_STABLE",
        "BACKUP_BUCKET_EDGE",
        "R2_JURISDICTION",
    }
)


def _store_names(profile: dict) -> list[str]:
    specs = list(profile.get("required", [])) + list(profile.get("optional", []))
    return [s.split(">")[0].strip() for s in specs]


def normalize(name: str, t: Target) -> str:
    channel = pusher.CHANNEL_STABLE if t.channel == STABLE else pusher.CHANNEL_EDGE
    name = re.sub(r"_%s_%s$" % (t.suffix, channel), "_{R}_{C}", name)
    name = re.sub(r"_%s$" % t.suffix, "_{R}", name)
    return re.sub(r"_%s$" % channel, "_{C}", name)


def check_profiles(
    targets: list[Target], consumers: dict, bench_payload: list[str]
) -> list[Finding]:
    f: list[Finding] = []
    reads = pusher_reads()
    suffixes = {t.suffix for t in targets}
    norm: dict[str, set[str]] = {}
    for t in targets:
        prof = consumers.get(t.profile)
        if not isinstance(prof, dict):
            f.append(
                Finding(
                    t.id, "profile", "secret-supply.json has no consumer profile %r" % t.profile
                )
            )
            continue
        names = _store_names(prof)
        if t.channel == BENCH:
            f.extend(_check_bench_profile(t, prof, suffixes))
            continue
        want = expected_store_names(t, reads, suffixes)
        have = set(names)
        f.extend(
            Finding(
                t.id,
                "profile",
                "%s does not bind %s, which the pusher reads for this target" % (t.profile, n),
            )
            for n in sorted(want - have)
        )
        f.extend(
            Finding(
                t.id, "profile", "%s binds %s, which nothing reads for this target" % (t.profile, n)
            )
            for n in sorted(have - want - PREFLIGHT_NAMES)
        )
        norm[t.id] = {
            normalize(n, t)
            for n in have
            if not (t.suffix == pusher.ASIA and n in pusher.ASIA_BORROWS)
        }
    for channel in (STABLE, EDGE):
        group = {tid: s for tid, s in norm.items() if tid.startswith(channel + "-")}
        union = set().union(*group.values()) if group else set()
        f.extend(
            Finding(tid, "profile", "binds no %s where another %s region does" % (n, channel))
            for tid, s in sorted(group.items())
            for n in sorted(union - s)
        )
    pushed = {k for k, _var, _src in pusher.KEYS}
    payload = set(bench_payload)
    if len(bench_payload) < len(pushed) // 2:
        raise NoVerdictError(
            "read %d key(s) from deploy_bench.secrets_payload(); the extractor lost the payload"
            % len(bench_payload)
        )
    f.extend(
        Finding(
            BENCH,
            "profile",
            "deploy_bench.secrets_payload() does not push %s, which every regional Worker gets" % n,
        )
        for n in sorted(pushed - payload)
    )
    f.extend(
        Finding(
            BENCH,
            "profile",
            "deploy_bench.secrets_payload() pushes %s, which no regional Worker gets" % n,
        )
        for n in sorted(payload - pushed)
    )
    return f


def _check_bench_profile(t: Target, prof: dict, suffixes: set[str]) -> list[Finding]:
    specs = [s.replace(" ", "") for s in [*prof.get("required", []), *prof.get("optional", [])]]
    f = [
        Finding(
            t.id, "profile", "%s does not bind `%s_%s > %s`" % (t.profile, family, t.suffix, family)
        )
        for family in BENCH_FAMILIES
        if "%s_%s>%s" % (family, t.suffix, family) not in specs
    ]
    f.extend(
        Finding(t.id, "profile", "%s does not bind %s unaliased" % (t.profile, n))
        for n in BENCH_UNALIASED
        if n not in specs
    )
    f.extend(
        Finding(
            t.id,
            "profile",
            "%s binds `%s`, which must be the unaliased production name" % (t.profile, spec),
        )
        for spec in specs
        if ">" in spec and spec.split(">")[1] in BENCH_UNALIASED
    )
    foreign = [*sorted(suffixes - {t.suffix}), pusher.CHANNEL_STABLE, pusher.CHANNEL_EDGE]
    stores = [s.split(">")[0] for s in specs]
    f.extend(
        Finding(t.id, "profile", "%s binds %s, another target's name" % (t.profile, store))
        for store in stores
        if any(store.endswith("_" + x) for x in foreign)
    )
    return f


def bench_payload_keys(text: str) -> list[str]:
    """The keys of the dict deploy_bench.secrets_payload() returns (the slice check:ci-worker-secret-names reads)."""
    start = text.find("\ndef secrets_payload(")
    body_start = text.find("\n    return {\n", start) if start >= 0 else -1
    end = text.find("\n    }\n", body_start) if body_start >= 0 else -1
    if end < 0:
        return []
    return re.findall(r'^\s+"([A-Z][A-Z0-9_]*)":', text[body_start:end], re.MULTILINE)


@dataclasses.dataclass
class Inputs:
    regions: dict
    account: dict[str, dict]
    proxy: dict[str, dict]
    consumers: dict
    bench_payload: list[str]


def load(root: pathlib.Path) -> tuple[Inputs, list[Target], list[Finding]]:
    def read(rel: str) -> str:
        path = root / rel
        if not path.is_file():
            raise NoVerdictError(
                "%s does not exist; a target with no declaration is not consistent, it is unchecked"
                % rel
            )
        return path.read_text(encoding="utf-8")

    regions = json.loads(read(REGIONS_REL))
    targets, found = targets_from(regions)
    if len(targets) != EXPECTED_TARGETS:
        raise NoVerdictError(
            "built %d target(s), expected %d (3 regions x stable+edge, plus bench)"
            % (len(targets), EXPECTED_TARGETS)
        )
    account = {t.id: tomllib.loads(read(t.account_toml)) for t in targets}
    proxy = {t.id: tomllib.loads(read(t.proxy_toml)) for t in targets}
    consumers = json.loads(read(SUPPLY_REL)).get("consumers", {})
    payload = bench_payload_keys(read(BENCH_DEPLOY_REL))
    return Inputs(regions, account, proxy, consumers, payload), targets, found


def offline(inputs: Inputs, targets: list[Target], found: list[Finding]) -> list[Finding]:
    ref_target = next(t for t in targets if t.channel == STABLE)
    ref = account_shape(inputs.account[ref_target.id])
    if not ref["r2 bindings"] or not ref["d1 bindings"]:
        raise NoVerdictError(
            "the reference toml %s parsed to zero R2 or D1 bindings" % ref_target.account_toml
        )
    out = list(found)
    for t in targets:
        out += check_account(t, inputs.account[t.id], ref)
        out += check_proxy(t, inputs.proxy[t.id])
    out += check_d1_ids(targets, inputs.account)
    out += check_profiles(targets, inputs.consumers, inputs.bench_payload)
    return out


def report(
    targets: list[Target],
    findings: list[Finding],
    classes: tuple[str, ...],
    unchecked: tuple[tuple[str, str | None, str], ...] | list[tuple[str, str | None, str]] = (),
) -> list[str]:
    """One row per target, one column per class: ok, DRIFT, or UNCHECKED (a class whose listing failed is never ok)."""
    bad = {(f.target, f.cls) for f in findings}
    blind = {(cls, tid) for cls, tid, _why in unchecked}

    def cell(t: Target, c: str) -> str:
        if (t.id, c) in bad:
            return "DRIFT"
        return "UNCHECKED" if (c, None) in blind or (c, t.id) in blind else "ok"

    head = "  %-11s " % "target" + " ".join("%-9s" % c for c in classes)
    return [
        head,
        *("  %-11s " % t.id + " ".join("%-9s" % cell(t, c) for c in classes) for t in targets),
    ]
