"""`check:ci-region-consistency --selftest`: one planted drift per class must go red, and benign changes must stay green.

THE BASE IS THE REAL TREE, PARSED, NEVER EDITED. Each plant deep-copies the parsed inputs, changes one fact, and asks whether a finding of the named (target, class) appears that the unplanted run did not have. Comparing against the unplanted run, rather than against zero, keeps the controls meaningful while the real tree carries a finding of its own, and a plant whose change does not land is caught by the same comparison: no new finding, red.

The live layer is driven through a fake `get` built from the same parsed tomls, so a clean fake must produce zero findings and zero unchecked classes before any live plant is trusted.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from rediacc_ci import paths
from rediacc_ci.controls import Controls
from rediacc_ci.deploy import account_secrets_local as local_push
from rediacc_ci.deploy import set_account_worker_secrets as pusher
from rediacc_ci.quality import region_consistency_live as live
from rediacc_ci.quality import region_consistency_offline as g

if TYPE_CHECKING:
    from collections.abc import Callable

FLOOR = 45


def _new(
    base: list[g.Finding], inputs: g.Inputs, targets: list[g.Target], found: list[g.Finding]
) -> set[tuple[str, str]]:
    after = g.offline(inputs, targets, found)
    return {(f.target, f.cls) for f in after if f not in base}


def _set(doc: dict, kind: str, binding: str, key: str, value: object) -> None:
    for block in doc[kind]:
        if block.get("binding") == binding:
            if value is None:
                block.pop(key, None)
            else:
                block[key] = value
            return
    raise AssertionError("plant needle gone: no %s binding %s" % (kind, binding))


def _profile(inputs: g.Inputs, name: str) -> dict:
    return inputs.consumers[name]


def offline_plants() -> list[
    tuple[str, tuple[str, str] | None, Callable[[g.Inputs, list[g.Finding]], list[g.Finding]]]
]:
    """(label, the (target, class) that must newly fire or None for must-not-fire, mutate(inputs, found) -> found)."""

    def regions(field: str, rid: str, value: object):
        def m(i: g.Inputs, _found):
            row = next(r for r in i.regions["regions"] if r["id"] == rid)
            if value is None:
                row.pop(field)
            elif isinstance(row[field], dict):
                row[field]["name"] = value
            else:
                row[field] = value
            return g.targets_from(i.regions)[1]

        return m

    def acc(tid: str, fn):
        def m(i: g.Inputs, found):
            fn(i.account[tid])
            return found

        return m

    def prx(tid: str, fn):
        def m(i: g.Inputs, found):
            fn(i.proxy[tid])
            return found

        return m

    def prof(name: str, fn):
        def m(i: g.Inputs, found):
            fn(_profile(i, name))
            return found

        return m

    def swap(names: list[str], old: str, new: str) -> None:
        names[names.index(old)] = new

    def dup_id(i: g.Inputs, found):
        _set(
            i.account["stable-us"],
            "d1_databases",
            "DB",
            "database_id",
            i.account["stable-eu"]["d1_databases"][0]["database_id"],
        )
        return found

    def bench_payload(i: g.Inputs, found):
        i.bench_payload.remove("STRIPE_WEBHOOK_SECRET")
        return found

    def drop_profile(i: g.Inputs, found):
        del i.consumers["account-secrets-asia-edge"]
        return found

    def reorder(i: g.Inputs, found):
        i.account["stable-eu"]["r2_buckets"].reverse()
        return found

    def extra_consumer(i: g.Inputs, found):
        i.consumers["unrelated-probe"] = {
            "required": ["ACCOUNT_CONFIG_SERVER_KEY_EU_EDGE"],
            "optional": [],
        }
        return found

    return [
        (
            "regions: an off-pattern edge backup bucket",
            ("edge-us", "regions"),
            regions("edgeBackupR2", "us", "edge-rediacc-backup-us"),
        ),
        (
            "regions: an absent r2Jurisdiction key",
            ("stable-asia", "regions"),
            regions("r2Jurisdiction", "asia", None),
        ),
        (
            "regions: a wrong secretSuffix",
            ("stable-us", "regions"),
            regions("secretSuffix", "us", "USA"),
        ),
        (
            "account: another target's config bucket",
            ("stable-asia", "account"),
            acc(
                "stable-asia",
                lambda d: _set(
                    d, "r2_buckets", "CONFIG_BUCKET", "bucket_name", "rediacc-configs-eu"
                ),
            ),
        ),
        (
            "account: a dropped EU jurisdiction",
            ("edge-eu", "account"),
            acc("edge-eu", lambda d: _set(d, "r2_buckets", "BACKUP_BUCKET", "jurisdiction", None)),
        ),
        (
            "account: a jurisdiction where regions.json has none",
            ("bench", "account"),
            acc("bench", lambda d: _set(d, "r2_buckets", "CONFIG_BUCKET", "jurisdiction", "eu")),
        ),
        ("account: a shared D1 database_id", ("stable-us", "account"), dup_id),
        (
            "account: a dropped cron (shape)",
            ("edge-asia", "account"),
            acc("edge-asia", lambda d: d.pop("triggers")),
        ),
        (
            "account: a bench-only var on stable",
            ("stable-eu", "account"),
            acc("stable-eu", lambda d: d["vars"].__setitem__("EMAIL_CAPTURE_D1", "true")),
        ),
        (
            "account: edge EXECUTOR bound to the stable proxy",
            ("edge-us", "account"),
            acc(
                "edge-us", lambda d: _set(d, "services", "EXECUTOR", "service", "rediacc-proxy-us")
            ),
        ),
        (
            "account: another region's telemetry destination",
            ("stable-asia", "account"),
            acc(
                "stable-asia",
                lambda d: d["observability"]["logs"].__setitem__("destinations", ["otlp-eu-logs"]),
            ),
        ),
        (
            "account: the bench assets exemption is per-target",
            ("stable-us", "account"),
            acc("stable-us", lambda d: d["assets"].__setitem__("directory", "./bench/dist")),
        ),
        (
            "proxy: edge ACCOUNT bound to the stable account Worker",
            ("edge-eu", "proxy"),
            prx(
                "edge-eu", lambda d: _set(d, "services", "ACCOUNT", "service", "rediacc-account-eu")
            ),
        ),
        (
            "proxy: a bench proxy claiming ENVIRONMENT=edge",
            ("bench", "proxy"),
            prx("bench", lambda d: d["vars"].__setitem__("ENVIRONMENT", "edge")),
        ),
        (
            "profile: a missing stable backup key id",
            ("stable-us", "profile"),
            prof(
                "account-secrets-us-stable",
                lambda p: p["required"].remove("ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_STABLE"),
            ),
        ),
        (
            "profile: another region's config server key",
            ("edge-us", "profile"),
            prof(
                "account-secrets-us-edge",
                lambda p: swap(
                    p["required"],
                    "ACCOUNT_CONFIG_SERVER_KEY_US_EDGE",
                    "ACCOUNT_CONFIG_SERVER_KEY_EU_EDGE",
                ),
            ),
        ),
        (
            "profile: Stripe bound on edge",
            ("edge-eu", "profile"),
            prof("account-secrets-eu-edge", lambda p: p["required"].append("STRIPE_SECRET_KEY")),
        ),
        (
            "profile: the asia SES borrow removed",
            ("stable-asia", "profile"),
            prof(
                "account-secrets-asia-stable",
                lambda p: p["required"].remove("AWS_SES_ACCESS_KEY_ID_EU"),
            ),
        ),
        (
            "profile: bench backup pair from the edge name",
            ("bench", "profile"),
            prof(
                "deploy-bench",
                lambda p: swap(
                    p["required"],
                    "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_BENCH > ACCOUNT_BACKUP_S3_ACCESS_KEY_ID",
                    "ACCOUNT_BACKUP_S3_ACCESS_KEY_ID_EDGE > ACCOUNT_BACKUP_S3_ACCESS_KEY_ID",
                ),
            ),
        ),
        (
            "profile: bench JWT secret from the DEV name",
            ("bench", "profile"),
            prof(
                "deploy-bench",
                lambda p: swap(p["required"], "ACCOUNT_JWT_SECRET", "ACCOUNT_JWT_SECRET_DEV > ACCOUNT_JWT_SECRET"),
            ),
        ),
        ("profile: a key the bench payload stops pushing", ("bench", "profile"), bench_payload),
        ("profile: a deleted regional profile", ("edge-asia", "profile"), drop_profile),
        ("benign: reordered R2 blocks", None, reorder),
        ("benign: an unrelated consumer profile", None, extra_consumer),
        (
            "benign: a fresh unique D1 id",
            None,
            acc(
                "edge-us",
                lambda d: _set(
                    d, "d1_databases", "DB", "database_id", "00000000-0000-4000-8000-000000000000"
                ),
            ),
        ),
        (
            "benign: an unrelated var on the proxy",
            None,
            prx("stable-us", lambda d: d["vars"].__setitem__("EXECUTOR_CAP", "24")),
        ),
    ]


def fake_get(
    inputs: g.Inputs,
    targets: list[g.Target],
    *,
    secrets=None,
    buckets=None,
    dbs=None,
    workers=None,
    refuse: frozenset = frozenset(),
):
    pushed = sorted(k for k, _v, _s in pusher.KEYS)
    if workers is None:
        workers = [w for t in targets for w in (t.account_worker, t.proxy_worker)]
    if secrets is None:
        secrets = {
            t.account_worker: pushed
            + ["__ARCHIVE_API_KEY"]
            + (["EXECUTOR_MODE"] if t.channel != g.STABLE else [])
            for t in targets
        }
        secrets.update({t.proxy_worker: [] for t in targets})
    if buckets is None:
        buckets = {}
        for t in targets:
            for b in inputs.account[t.id]["r2_buckets"]:
                buckets.setdefault(b.get("jurisdiction"), []).append(b["bucket_name"])
    if dbs is None:
        dbs = [
            {"name": b["database_name"], "uuid": b["database_id"]}
            for t in targets
            for b in inputs.account[t.id]["d1_databases"]
        ]

    def get(path: str, extra: dict[str, str]):
        kind = (
            "r2"
            if "/r2/" in path
            else "d1"
            if "/d1/" in path
            else "secrets"
            if path.endswith("/secrets")
            else "workers"
        )
        if kind in refuse:
            raise live.LiveError("HTTP 403 on %s: 10000 Authentication error" % kind)
        if kind == "workers":
            return [{"id": w} for w in workers], {}
        if kind == "secrets":
            worker = path.split("/scripts/")[1].split("/", maxsplit=1)[0]
            return [{"name": n, "type": "secret_text"} for n in secrets.get(worker, [])], {}
        if kind == "r2":
            return {
                "buckets": [
                    {"name": n} for n in buckets.get(extra.get(live.JURISDICTION_HEADER), [])
                ]
            }, {}
        return dbs, {"total_pages": 1}

    return get


def live_plants(inputs: g.Inputs, targets: list[g.Target]):
    pushed = sorted(k for k, _v, _s in pusher.KEYS)
    base = fake_get(inputs, targets)

    def secrets_with(worker: str, names: list[str]):
        s = {t.account_worker: list(pushed) for t in targets}
        s.update({t.proxy_worker: [] for t in targets})
        s[worker] = names
        return fake_get(inputs, targets, secrets=s)

    moved: dict[str | None, list[str]] = {}
    for t in targets:
        for b in inputs.account[t.id]["r2_buckets"]:
            moved.setdefault(b.get("jurisdiction"), []).append(b["bucket_name"])
    moved[None].remove("rediacc-backups-us")
    moved["eu"].append("rediacc-backups-us")
    gone = copy.deepcopy(moved)
    gone["eu"].remove("rediacc-backups-us")
    dbs = [
        {"name": b["database_name"], "uuid": b["database_id"]}
        for t in targets
        for b in inputs.account[t.id]["d1_databases"]
    ]
    dbs[0] = dict(dbs[0], uuid="ffffffff-0000-4000-8000-000000000000")
    workers = [
        w
        for t in targets
        for w in (t.account_worker, t.proxy_worker)
        if w != "edge-rediacc-proxy-asia"
    ]
    return [
        ("live: a clean account is clean", base, set(), set()),
        (
            "live: a pushed key missing on edge-us",
            secrets_with(
                "edge-rediacc-account-us", [n for n in pushed if n != "ACCOUNT_JWT_SECRET"]
            ),
            {("edge-us", "secrets")},
            set(),
        ),
        (
            "live: a legacy name on bench",
            secrets_with("rediacc-account-bench", [*pushed, "JWT_SECRET"]),
            {("bench", "secrets")},
            set(),
        ),
        (
            "live: archives and EXECUTOR_MODE are not extras",
            secrets_with("rediacc-account-eu", [*pushed, "__ARCHIVE_JWT_SECRET", "EXECUTOR_MODE"]),
            set(),
            set(),
        ),
        (
            "live: a secret on a proxy Worker",
            secrets_with("rediacc-proxy-asia", ["EXECUTOR_TOKEN"]),
            {("stable-asia", "secrets")},
            set(),
        ),
        (
            "live: a bucket in the wrong jurisdiction",
            fake_get(inputs, targets, buckets=moved),
            {("stable-us", "r2")},
            set(),
        ),
        (
            "live: a bucket that does not exist",
            fake_get(inputs, targets, buckets=gone),
            {("stable-us", "r2")},
            set(),
        ),
        (
            "live: a D1 id that disagrees with the toml",
            fake_get(inputs, targets, dbs=dbs),
            {(targets[0].id, "d1")},
            set(),
        ),
        (
            "live: an undeployed proxy Worker",
            fake_get(inputs, targets, workers=workers),
            {("edge-asia", "workers")},
            set(),
        ),
        (
            "live: an R2 refusal is UNCHECKED, not clean",
            fake_get(inputs, targets, refuse=frozenset({"r2"})),
            set(),
            {"r2"},
        ),
        (
            "live: an empty Workers listing is UNCHECKED",
            fake_get(inputs, targets, workers=[]),
            set(),
            {"workers"},
        ),
    ]


def run() -> int:
    ctl = Controls("region-consistency", floor=FLOOR, verbose=True)
    root = paths.repo_root()
    base_inputs, targets, base_found = g.load(root)
    base = g.offline(base_inputs, targets, base_found)

    ctl.check(
        "seven targets",
        [t.id for t in targets],
        ["stable-eu", "edge-eu", "stable-us", "edge-us", "stable-asia", "edge-asia", "bench"],
    )
    ctl.check(
        "DERIVED_NAMES is derive()'s key set",
        set(g.DERIVED_NAMES),
        set(local_push.derive("eu", "stable", root)),
    )
    ctl.truthy("pusher_reads() found at least 20 literal reads", len(g.pusher_reads()) >= 20)
    ctl.check(
        "bench payload extractor",
        g.bench_payload_keys(
            'x\ndef secrets_payload(a):\n    s = {"NOT": 1}\n    return {\n        "A_B": x,\n        "C": y,\n    }\n'
        ),
        ["A_B", "C"],
    )
    ctl.check(
        "bench payload extractor on no payload",
        g.bench_payload_keys("def other():\n    return {}\n"),
        [],
    )
    edge_us = next(t for t in targets if t.id == "edge-us")
    ctl.check(
        "normalize strips region and channel",
        g.normalize("ACCOUNT_CONFIG_SERVER_KEY_US_EDGE", edge_us),
        "ACCOUNT_CONFIG_SERVER_KEY_{R}_{C}",
    )
    ctl.check(
        "normalize leaves a foreign suffix alone",
        g.normalize("AWS_SES_ACCESS_KEY_ID_EU", edge_us),
        "AWS_SES_ACCESS_KEY_ID_EU",
    )
    ctl.raises(
        "a short target list is no verdict", g.NoVerdictError, g.targets_from, {"regions": []}
    )

    for label, want, mutate in offline_plants():
        inputs = copy.deepcopy(base_inputs)
        found = mutate(inputs, list(base_found))
        new = _new(base, inputs, targets, found)
        if want is None:
            ctl.check(label + " fires nothing", new, set())
        else:
            ctl.truthy(
                "%s fires %s/%s (new: %s)" % (label, want[0], want[1], sorted(new)), want in new
            )

    for label, get, want, blind in live_plants(base_inputs, targets):
        found, unchecked, _info = live.judge(targets, base_inputs, get, "acct")
        got = {(f.target, f.cls) for f in found}
        ctl.check(label + " (findings)", got, want)
        ctl.check(label + " (unchecked)", {c for c, _t, _w in unchecked}, blind)
    found, unchecked, _cls = live.run(targets, base_inputs, env={})
    ctl.check(
        "live: no credential leaves every live class UNCHECKED",
        ({c for c, _t, _w in unchecked}, found),
        (set(live.LIVE_CLASSES), []),
    )
    lines = g.report(targets, [], live.LIVE_CLASSES, [("r2", None, "refused")])
    ctl.truthy(
        "report shows an unchecked class as UNCHECKED, never ok",
        all("UNCHECKED" in row for row in lines[1:]),
    )
    return 0 if ctl.report() else 1
