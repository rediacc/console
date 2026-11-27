"""The bench production guard: bench subscriptions that carry production data, declared in `.ci/config/bench-production.json` (agent/plans/PLAN-hostinger-to-bench.md Design 3).

Bench signs with the production key, and once a production machine backs up through bench (hostinger), a bench wipe or a drill cleanup could remove the only off-site copy, and a stopped bench signer stops its licence renewals. Four refusals read this one declaration:

  1. `reset_refusal` -- reset_bench refuses every mode (exit 2) while the file declares anything for the region being wiped, before any credential is read. It refuses as well while the file declares NOTHING: an empty list is a guard nobody armed, not proof that bench holds no production data. On 2026-11-27 an empty list let `reset_bench --yes` wipe the bench D1 that held hostinger's backup manifests (PLAN-hostinger-to-bench L5), so the empty state fails closed like an unreadable one.
  2. `d1_refusal` -- reset_bench also refuses when the live bench D1 holds ANY `backup_manifests` row, declared subscription or not: a manifest is a machine's off-site copy, the production signal a declaration can miss. The read runs after the token is minted and before the confirmation, in every mode, and a failed read refuses too.
  3. `refuse_ids` -- the drills' cleanup refuses to delete rows of a declared subscription and deletes nothing.
  4. `signer_stop_refusal` -- the enterprise proofs' signer stop and region cut (`rediacc_ci.deploy.deploy_signer.stop_signer`, reached by `enterprise proof signer --bench` and `region-loss --bench`) refuse a bench signer while the file declares anything for its region (`signer-bench-<region>`), and while it declares nothing at all (the unarmed guard fails closed, as for reset_bench), before any secret is deleted.

Each entry names the `region` of the bench that holds it (`eu`, `us`, `asia`), and a refusal covers only that region: a us wipe is not stopped by an eu subscription. A refusal asked without a region (a drill's `refuse_ids`) covers every entry. There is no override flag. A file that cannot be read or parsed, or an entry without a UUID `subscription_id`, is a refusal too: the guard fails closed. `target_refusal` is reset_bench's third check, also before any credential: the database and buckets the region's bench config names must be bench-named and bound by no production region config (`workers/account/wrangler.<region>.toml`).
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rediacc_ci import paths

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Iterable, Sequence

CONFIG_REL = ".ci/config/bench-production.json"
# `\Z`, not `$`: `$` also matches before a trailing newline, and a declared id carrying one would never equal the newline-free D1 id.
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
REGION = re.compile(r"^[a-z][a-z0-9-]*\Z")
SIGNER_PREFIX = "signer-bench-"
# The exit code of a production refusal, distinct from a failed run (1).
REFUSAL_EXIT = 2
# Every subscription's manifests, not only the declared ones: any row is a production signal.
MANIFEST_QUERY = (
    "SELECT subscription_id, COUNT(*) AS manifests FROM backup_manifests GROUP BY subscription_id"
)
# The word every name a wipe touches carries, and the production account configs whose bindings it must not share.
BENCH_MARK = "bench"
PRODUCTION_CONFIG = "workers/account/wrangler.%s.toml"


class ProductionRefusalError(Exception):
    """A destructive bench step would touch a declared production subscription, or the declaration cannot be read."""


@dataclass(frozen=True)
class Protected:
    subscription_id: str
    machine: str
    reason: str
    # The bench that holds the subscription; "" (never produced by `load`, which requires one) stands for every region.
    region: str = ""


def config_path(root: pathlib.Path | None = None) -> pathlib.Path:
    return (root or paths.repo_root()) / CONFIG_REL


def load(path: pathlib.Path | None = None) -> list[Protected]:
    """The declared entries. ProductionRefusalError when the file is unreadable, malformed, or an entry lacks a UUID subscription id."""
    target = path or config_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProductionRefusalError(
            "cannot read %s (%s); the bench production guard fails closed" % (CONFIG_REL, exc)
        ) from None
    entries = data.get("protected") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        raise ProductionRefusalError(
            "%s has no `protected` list; the guard fails closed" % CONFIG_REL
        )
    out: list[Protected] = []
    for index, entry in enumerate(entries):
        sub = entry.get("subscription_id") if isinstance(entry, dict) else None
        if not isinstance(sub, str) or not UUID.match(sub):
            raise ProductionRefusalError(
                "%s entry %d has no UUID subscription_id; the guard fails closed"
                % (CONFIG_REL, index)
            )
        region = entry.get("region")
        if not isinstance(region, str) or not REGION.match(region):
            raise ProductionRefusalError(
                "%s entry %d has no `region` (a lowercase region id such as eu, us or asia); the guard fails closed"
                % (CONFIG_REL, index)
            )
        out.append(
            Protected(
                subscription_id=sub,
                machine=str(entry.get("machine") or ""),
                reason=str(entry.get("reason") or ""),
                region=region,
            )
        )
    return out


def _describe(entries: Iterable[Protected]) -> str:
    return "; ".join(
        "subscription %s (region %s, machine %s: %s)"
        % (e.subscription_id, e.region or "all", e.machine or "-", e.reason or "-")
        for e in entries
    )


def for_region(entries: Sequence[Protected], region: str | None) -> list[Protected]:
    """The entries held by REGION's bench; every entry when REGION is None."""
    return [e for e in entries if region is None or e.region in ("", region)]


def reset_refusal(entries: Sequence[Protected], region: str | None = None) -> str | None:
    """Why reset_bench must not run on REGION's bench: the declaration is empty (an unarmed guard), or it declares a subscription in REGION. None only when the file declares something and none of it is in REGION."""
    if not entries:
        return (
            "%s declares no protected subscription, so the bench production guard is unarmed and fails closed: "
            "reset_bench refuses every mode. Declare each bench subscription that carries production data "
            "(agent/plans/PLAN-hostinger-to-bench.md L5) in a reviewed commit first" % CONFIG_REL
        )
    entries = for_region(entries, region)
    if not entries:
        return None
    return (
        "bench carries production data (%s): %s; reset_bench refuses every mode, and removing the entry is a reviewed commit"
        % (
            CONFIG_REL,
            _describe(entries),
        )
    )


def signer_stop_refusal(signer: str, entries: Sequence[Protected]) -> str | None:
    """Why the bench signer `signer` must not be stopped or cut, or None when the file declares something and none of it is in the signer's region. An EMPTY declaration refuses (an unarmed guard fails closed, as for reset_bench). A `signer-bench-<region>` name scopes the refusal to that region; any other name is held against every entry."""
    if not entries:
        return (
            "%s declares no protected subscription, so the bench production guard is unarmed and fails closed: "
            "%s is not stopped or cut. Declare each bench subscription that carries production data "
            "(agent/plans/PLAN-hostinger-to-bench.md L5) in a reviewed commit first"
            % (CONFIG_REL, signer)
        )
    region = signer.removeprefix(SIGNER_PREFIX) if signer.startswith(SIGNER_PREFIX) else None
    entries = for_region(entries, region)
    if not entries:
        return None
    return (
        "bench carries production data (%s): %s; %s is not stopped or cut, because a declared subscription's licences renew through the bench signers, and removing the entry is a reviewed commit"
        % (CONFIG_REL, _describe(entries), signer)
    )


def d1_refusal(rows: Callable[[str], list[dict]], entries: Sequence[Protected]) -> str | None:
    """Why the live D1 forbids a wipe: it holds any `backup_manifests` row (a declared subscription's is named as declared). The query always runs; None only when no row carries a manifest. A count that is not a number raises ProductionRefusalError."""
    declared = {e.subscription_id for e in entries}
    held = []
    for row in rows(MANIFEST_QUERY):
        try:
            count = int(row.get("manifests") or 0)
        except (TypeError, ValueError):
            raise ProductionRefusalError(
                "the manifest count %r is not a number" % (row.get("manifests"),)
            ) from None
        if count > 0:
            sub = row.get("subscription_id")
            held.append(
                "%s (%d manifests%s)" % (sub, count, ", declared" if sub in declared else "")
            )
    if not held:
        return None
    return (
        "the bench D1 holds backup manifests, a production signal (a machine's off-site copy): %s; "
        "reset_bench refuses every mode while any remain" % ", ".join(held)
    )


def _bindings(path: pathlib.Path) -> set[str]:
    """The DB database names and ids and every R2 bucket name a wrangler config binds."""
    with open(path, "rb") as fh:
        doc = tomllib.load(fh)
    out: set[str] = set()
    for db in doc.get("d1_databases") or []:
        out |= {str(db.get("database_name") or ""), str(db.get("database_id") or "")}
    for bucket in doc.get("r2_buckets") or []:
        out.add(str(bucket.get("bucket_name") or ""))
    return out - {""}


def target_refusal(
    names: Sequence[tuple[str, str]], regions: Iterable[str], root: pathlib.Path | None = None
) -> str | None:
    """Why the wipe target is not a bench, or None. NAMES is `(what, value)` for the database name and id and each bucket the wipe empties; an empty value is skipped, and the id is only collision-checked. A name without `bench`, or a value a production region config (PRODUCTION_CONFIG per id in REGIONS) also binds, refuses; so does a production config that exists and cannot be parsed."""
    base = root or paths.repo_root()
    problems = [
        "%s %r is not bench-named" % (what, value)
        for what, value in names
        if value and what != "database_id" and BENCH_MARK not in value
    ]
    for region in regions:
        path = base / (PRODUCTION_CONFIG % region)
        if not path.is_file():
            continue
        try:
            taken = _bindings(path)
        except (OSError, ValueError) as exc:
            return "cannot read %s (%s); the wipe target check fails closed" % (path.name, exc)
        problems += [
            "%s %r is also bound by %s" % (what, value, path.name)
            for what, value in names
            if value and value in taken
        ]
    if not problems:
        return None
    return "the wipe target is not a bench: %s; reset_bench refuses" % "; ".join(problems)


def refuse_ids(
    sub_ids: Iterable[str],
    entries: Sequence[Protected] | None = None,
    region: str | None = None,
) -> None:
    """ProductionRefusalError when any of `sub_ids` is declared (in REGION, or in any region when None); called before a drill deletes anything."""
    declared = for_region(load() if entries is None else entries, region)
    by_id = {e.subscription_id: e for e in declared}
    hit = [by_id[s] for s in sub_ids if s in by_id]
    if hit:
        raise ProductionRefusalError(
            "refusing to delete rows of a declared production subscription (%s): %s"
            % (CONFIG_REL, _describe(hit))
        )
