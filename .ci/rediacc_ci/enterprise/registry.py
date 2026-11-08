"""The enterprise registry: every region's control database, read together.

Each region holds only its own companies (private/account/control/migrations/0001_control.sql), so the full picture needs every region, and a region that cannot be read is named rather than skipped: `enterprise add` must refuse when it cannot prove a name is free everywhere, and `enterprise list` must say which region is missing.

The transport is injected: `Query(database, sql, params) -> rows`, which raises on an unreachable database. The production transport is the Cloudflare D1 query API; tests pass a recording fake or an in-memory sqlite.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from rediacc_ci import paths

Query = Callable[[str, str, list], list[dict]]

MIGRATION_REL = "private/account/control/migrations/0001_control.sql"
BENCH_REGIONS = ("eu", "us")


class RegistryUnreachableError(RuntimeError):
    """One or more regions could not be read; `regions` names them."""

    def __init__(self, regions: list[str], causes: dict[str, str]):
        self.regions = regions
        self.causes = causes
        super().__init__(
            "control database unreachable for: %s"
            % ", ".join("%s (%s)" % (r, causes[r]) for r in regions)
        )


def control_database(region: str, bench: bool = False) -> str:
    return "control-bench-%s" % region if bench else "control-%s" % region


def region_ids() -> list[str]:
    data = json.loads((paths.repo_root() / "regions.json").read_text())
    return [str(r["id"]) for r in data["regions"]]


def databases(bench: bool = False) -> dict[str, str]:
    """Region id -> control database name. Bench has two signers, so two databases."""
    if bench:
        return {r: control_database(r, True) for r in BENCH_REGIONS}
    return {r: control_database(r) for r in region_ids()}


def migration_sql() -> str:
    return (Path(paths.repo_root()) / MIGRATION_REL).read_text()


@dataclass
class Registry:
    query: Query
    bench: bool = False
    _dbs: dict[str, str] = field(init=False)

    def __post_init__(self) -> None:
        self._dbs = databases(self.bench)

    def read_all(self, sql: str, params: list | None = None) -> dict[str, list[dict]]:
        """The rows of `sql` per region. Raises RegistryUnreachableError naming every region that failed."""
        rows: dict[str, list[dict]] = {}
        failed: dict[str, str] = {}
        for region, database in self._dbs.items():
            try:
                rows[region] = list(self.query(database, sql, list(params or [])))
            except (
                OSError,
                RuntimeError,
                ValueError,
                LookupError,
            ) as exc:  # transport, HTTP and decode failures; the region is what matters
                failed[region] = "%s: %s" % (type(exc).__name__, exc)
        if failed:
            raise RegistryUnreachableError(sorted(failed), failed)
        return rows

    def companies(self) -> list[dict]:
        """Every company across all regions, each row tagged with its region."""
        out: list[dict] = []
        for region, rows in self.read_all(
            "SELECT id, name, region, state, unlisted FROM companies ORDER BY name"
        ).items():
            out.extend({**row, "region": row.get("region") or region} for row in rows)
        return out

    def find(self, name: str) -> dict | None:
        for row in self.companies():
            if row["name"] == name and row.get("state") != "removed":
                return row
        return None

    def name_free(self, name: str) -> bool:
        """True only when every region was read and none holds the name; an unreachable region raises."""
        return self.find(name) is None
