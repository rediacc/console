"""The bench production guard: bench subscriptions that carry production data, declared in `.ci/config/bench-production.json` (agent/plans/PLAN-hostinger-to-bench.md Design 3).

Bench signs with the production key, and once a production machine backs up through bench (hostinger), a bench wipe or a drill cleanup could remove the only off-site copy. Three refusals read this one declaration:

  1. `reset_refusal` -- reset_bench refuses every mode (exit 2) while the file declares anything, before any credential is read.
  2. `d1_refusal` -- reset_bench also refuses when the live bench D1 holds `backup_manifests` rows of a declared subscription; the read runs after the token is minted and before the confirmation, so it is the second layer when the declaration is present.
  3. `refuse_ids` -- the drills' cleanup refuses to delete rows of a declared subscription and deletes nothing.

There is no override flag. A file that cannot be read or parsed, or an entry without a UUID `subscription_id`, is a refusal too: the guard fails closed.
"""

from __future__ import annotations

import json
import re
import string
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rediacc_ci import paths

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Iterable, Sequence

CONFIG_REL = ".ci/config/bench-production.json"
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
# The exit code of a production refusal, distinct from a failed run (1).
REFUSAL_EXIT = 2
# `$ids` is filled only with validated UUID literals (`manifest_query`).
MANIFEST_QUERY = string.Template(
    "SELECT subscription_id, COUNT(*) AS manifests FROM backup_manifests "
    "WHERE subscription_id IN ($ids) GROUP BY subscription_id"
)


class ProductionRefusalError(Exception):
    """A destructive bench step would touch a declared production subscription, or the declaration cannot be read."""


@dataclass(frozen=True)
class Protected:
    subscription_id: str
    machine: str
    reason: str


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
        out.append(
            Protected(
                subscription_id=sub,
                machine=str(entry.get("machine") or ""),
                reason=str(entry.get("reason") or ""),
            )
        )
    return out


def _describe(entries: Iterable[Protected]) -> str:
    return "; ".join(
        "subscription %s (machine %s: %s)" % (e.subscription_id, e.machine or "-", e.reason or "-")
        for e in entries
    )


def reset_refusal(entries: Sequence[Protected]) -> str | None:
    """Why reset_bench must not run, or None when nothing is declared."""
    if not entries:
        return None
    return (
        "bench carries production data (%s): %s; reset_bench refuses every mode, and removing the entry is a reviewed commit"
        % (
            CONFIG_REL,
            _describe(entries),
        )
    )


def manifest_query(ids: Sequence[str]) -> str:
    """The D1 read counting `backup_manifests` rows per declared subscription. Ids are validated UUIDs."""
    for ident in ids:
        if not UUID.match(ident):
            raise ProductionRefusalError("refusing a non-UUID subscription id %r" % ident)
    listed = ", ".join("'%s'" % i for i in ids)
    return MANIFEST_QUERY.substitute(ids=listed)


def d1_refusal(rows: Callable[[str], list[dict]], entries: Sequence[Protected]) -> str | None:
    """Why the live D1 forbids a wipe: it holds manifests of a declared subscription. None when nothing is declared (no query is made) or no such row exists."""
    ids = [e.subscription_id for e in entries]
    if not ids:
        return None
    held = [
        "%s (%s manifests)" % (r.get("subscription_id"), r.get("manifests"))
        for r in rows(manifest_query(ids))
        if int(r.get("manifests") or 0) > 0
    ]
    if not held:
        return None
    return (
        "the bench D1 holds backup manifests of a declared production subscription: %s"
        % ", ".join(held)
    )


def refuse_ids(sub_ids: Iterable[str], entries: Sequence[Protected] | None = None) -> None:
    """ProductionRefusalError when any of `sub_ids` is declared; called before a drill deletes anything."""
    declared = load() if entries is None else entries
    by_id = {e.subscription_id: e for e in declared}
    hit = [by_id[s] for s in sub_ids if s in by_id]
    if hit:
        raise ProductionRefusalError(
            "refusing to delete rows of a declared production subscription (%s): %s"
            % (CONFIG_REL, _describe(hit))
        )
