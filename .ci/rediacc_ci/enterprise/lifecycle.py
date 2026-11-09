"""Company lifecycle after `enterprise add`: list, update, suspend, export and remove.

Every verb is a plain function over a `Context` whose seams are injected, so tests drive them over in-memory control databases and recording fakes and never reach Cloudflare, bws or AWS. The production seams (a D1 query transport, an exporter over the D1 and R2 APIs, a teardown over wrangler and the Cloudflare API, the enterprise bws store) are built by the caller.

The rules of PLAN-enterprise-isolation.md (Design, *Company lifecycle*; ruling 10):

- `remove` needs a completed export whose files still hash to the manifest, keeps every byte unless `delete_data` is set with `confirm` equal to the company name, has no timer, and refuses whenever `GITHUB_ACTIONS` is set. No workflow calls it; the leak and proof gates check that.
- `list`, `export` and `remove` print or write company labels, so they refuse under GitHub Actions as well, where the log is public.
- Nothing destructive happens before every check has passed, and with `delete_data` the checks include a fresh D1 dump and bucket listing compared with the export (a company that changed since the export is refused; object contents are not re-read). After the last destructive step succeeded the audit row is written first and the control row turns `removed` second, so a failure between them leaves a remove that can be repeated (it then writes a second audit row) rather than a removed company with no audit. Every verb writes more than one row in separate statements, so a failure mid-way is recovered by repeating the verb, not rolled back.
- A region that cannot be read stops the verb (`RegistryUnreachableError` names it): a name that cannot be proven absent everywhere is never guessed.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from rediacc_ci.deploy import proxy_configs as pc
from rediacc_ci.enterprise import registry, secrets

if TYPE_CHECKING:
    import pathlib

    from rediacc_ci.enterprise.registry import Query

RINGS = ("canary", "small", "medium", "large")
AUTO_RING = "auto"
MANIFEST = "manifest.json"
DUMP = "d1.sql"
SECRETS_FILE = "secrets.json"
# Written once a `delete_data` remove has passed its stale-export check, holding the export's `exported_at`: a resumed remove (its buckets or database already gone) is then not judged against data its own earlier run deleted. `export` removes it with the manifest.
CHECKED = "remove-checked"
# Kept in the export: losing the config server key loses layer 3 data, and the backup KEK opens the backups.
DURABLE = ("ACCOUNT_CONFIG_SERVER_KEY", "ACCOUNT_BACKUP_STORE_KEK")
CI_VAR = "GITHUB_ACTIONS"
Out = Callable[[str], None]


class LifecycleError(RuntimeError):
    """A refusal or a failed step. Messages name the step and the error type, never a secret value."""


@dataclass(frozen=True)
class Target:
    """One company as the control database holds it."""

    id: str
    name: str
    region: str
    state: str
    unlisted: bool

    @property
    def configs_bucket(self) -> str:
        return "configs-%s" % self.name

    @property
    def backups_bucket(self) -> str:
        return "backups-%s" % self.name

    @property
    def buckets(self) -> tuple[str, str]:
        return (self.configs_bucket, self.backups_bucket)


class Exporter(Protocol):
    def dump_d1(self, company: Target) -> str: ...

    def bucket_keys(self, bucket: str) -> Sequence[str]: ...

    def get_object(self, bucket: str, key: str) -> bytes: ...


class Teardown(Protocol):
    def undeploy(self, company: Target) -> None: ...

    def delete_d1(self, company: Target) -> None: ...

    def delete_bucket(self, company: Target, bucket: str) -> None: ...

    def delete_secret(self, name: str) -> None: ...

    def revoke_tokens(self, company: Target) -> None: ...

    def drop_lookup(self, company: Target) -> None: ...


@dataclass
class Context:
    registry: registry.Registry
    query: Query
    exporter: Exporter
    teardown: Teardown
    store: secrets.Store
    export_root: pathlib.Path
    env: Mapping[str, str] = field(default_factory=dict)
    now: Callable[[], str] = lambda: ""
    actor: str = "operator"

    @property
    def bench(self) -> bool:
        return self.registry.bench


@dataclass
class UpdateResult:
    changes: dict[str, Any]
    redeploy_needed: bool


@dataclass
class RemoveResult:
    company_id: str
    data_deleted: bool
    steps: list[str]


# --- shared helpers ------------------------------------------------------------------


def _refuse_ci(ctx: Context) -> None:
    if ctx.env.get(CI_VAR):
        raise LifecycleError(
            "refused under %s: this verb prints or removes company data and no workflow may run it"
            % CI_VAR
        )


def _step(what: str, fn: Callable[..., Any], *args: Any) -> Any:
    """Run one seam call; a failure keeps only its type, because its text may quote a value. Raised outside the except block so no seam exception is chained."""
    try:
        return fn(*args)
    except LifecycleError:
        raise
    except secrets.SEAM_ERRORS as exc:
        failed = type(exc).__name__
    raise LifecycleError("%s failed (%s)" % (what, failed))


def load_company(ctx: Context, name: str) -> Target:
    """The live company named `name`; every region is read, and an unreachable one raises RegistryUnreachableError."""
    row = ctx.registry.find(name)
    if row is None:
        raise LifecycleError("no company named %s" % name)
    return Target(
        id=row["id"],
        name=row["name"],
        region=row["region"],
        state=row["state"],
        unlisted=bool(row.get("unlisted")),
    )


def _db(ctx: Context, company: Target) -> str:
    return registry.control_database(company.region, ctx.bench)


def _audit(
    ctx: Context, company: Target, action: str, detail: Mapping[str, Any] | None = None
) -> None:
    ctx.query(
        _db(ctx, company),
        "INSERT INTO audit (at, company_id, actor, action, detail) VALUES (?, ?, ?, ?, ?)",
        [
            ctx.now(),
            company.id,
            ctx.actor,
            action,
            json.dumps(detail, sort_keys=True) if detail else None,
        ],
    )


def _touch(ctx: Context, company: Target, state: str) -> None:
    ctx.query(
        _db(ctx, company),
        "UPDATE companies SET state = ?, updated_at = ? WHERE id = ?",
        [state, ctx.now(), company.id],
    )


# --- list ----------------------------------------------------------------------------

LIST_SQL = (
    "SELECT c.id, c.name, c.region, c.state, c.unlisted, s.max_machines, s.max_storage_gb, "
    "s.max_expiry_days, r.machines_high_water "
    "FROM companies c LEFT JOIN scope s ON s.company_id = c.id LEFT JOIN ring r ON r.company_id = c.id "
    "ORDER BY c.name"
)


def list_companies(ctx: Context, *, include_removed: bool = False) -> list[dict]:
    _refuse_ci(ctx)
    out: list[dict] = []
    for region, rows in ctx.registry.read_all(LIST_SQL).items():
        out.extend({**row, "region": row.get("region") or region} for row in rows)
    out.sort(key=lambda r: r["name"])
    return out if include_removed else [r for r in out if r["state"] != "removed"]


# --- suspend -------------------------------------------------------------------------


def suspend(ctx: Context, name: str, *, resume: bool = False) -> Target:
    """Suspend or resume a company. The signer reads suspension from `companies.state` alone (control/migrations/0001_control.sql), so the state is the one write. Repeating it is harmless."""
    company = load_company(ctx, name)
    if company.state == "onboarding":
        raise LifecycleError(
            "company %s is still onboarding; finish or resume `enterprise add` first" % company.id
        )
    _audit(ctx, company, "resume" if resume else "suspend")
    _touch(ctx, company, "active" if resume else "suspended")
    return company


# --- update --------------------------------------------------------------------------


# One fixed statement per column: no SQL text is built from a name.
SCOPE_UPDATES = {
    "max_machines": "UPDATE scope SET max_machines = ? WHERE company_id = ?",
    "max_storage_gb": "UPDATE scope SET max_storage_gb = ? WHERE company_id = ?",
    "max_expiry_days": "UPDATE scope SET max_expiry_days = ? WHERE company_id = ?",
    "allow_ips": "UPDATE scope SET allow_ips = ? WHERE company_id = ?",
}


def _limit(label: str, value: Any, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise LifecycleError("%s must be an integer of at least %d" % (label, minimum))
    return value


def update(
    ctx: Context,
    name: str,
    *,
    max_machines: int | None = None,
    max_storage_gb: int | None = None,
    max_expiry_days: int | None = None,
    allow_ips: Sequence[str] | None = None,
    ring: str | None = None,
    ring_reason: str | None = None,
) -> UpdateResult:
    """Change the limits the signer checks, the proxy IP allowlist (a redeploy applies it) or the release ring override."""
    sets: dict[str, Any] = {}
    if max_machines is not None:
        sets["max_machines"] = _limit("max_machines", max_machines, 1)
    if max_storage_gb is not None:
        sets["max_storage_gb"] = _limit("max_storage_gb", max_storage_gb, 0)
    if max_expiry_days is not None:
        sets["max_expiry_days"] = _limit("max_expiry_days", max_expiry_days, 1)
    if allow_ips is not None:
        ips = [str(i).strip() for i in allow_ips]
        if ips:
            reason = pc.allow_ips_refusal(",".join(ips))
            if reason:
                raise LifecycleError(reason)
        sets["allow_ips"] = ips
    if ring is not None:
        if ring != AUTO_RING and ring not in RINGS:
            raise LifecycleError("ring must be one of %s or %s" % (", ".join(RINGS), AUTO_RING))
        if ring != AUTO_RING and not (ring_reason or "").strip():
            raise LifecycleError("a ring override needs a reason")
    if not sets and ring is None:
        raise LifecycleError("nothing to update")
    company = load_company(ctx, name)
    database = _db(ctx, company)
    changes = dict(sets)
    if ring is not None:
        if ring != AUTO_RING:
            changes["ring_reason"] = ring_reason
        changes["ring"] = ring
    _audit(ctx, company, "update", changes)
    for column, value in sets.items():
        ctx.query(
            database,
            SCOPE_UPDATES[column],
            [json.dumps(value) if column == "allow_ips" else value, company.id],
        )
    if ring is not None:
        if ring == AUTO_RING:
            ctx.query(database, "DELETE FROM ring_override WHERE company_id = ?", [company.id])
        else:
            ctx.query(
                database,
                "INSERT OR REPLACE INTO ring_override (company_id, ring, reason, set_at) VALUES (?, ?, ?, ?)",
                [company.id, ring, ring_reason, ctx.now()],
            )
    return UpdateResult(changes=changes, redeploy_needed="allow_ips" in sets)


# --- export --------------------------------------------------------------------------


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(
    path: pathlib.Path, data: bytes, mode: int = 0o600, root: pathlib.Path | None = None
) -> None:
    """Write `path` at `mode` (an export holds company data, so the default is owner-only); every directory from its parent up to `root` is made 0700."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    os.chmod(path, mode)
    folder = path.parent
    while True:
        os.chmod(folder, 0o700)
        if root is None or folder in (root, folder.parent):
            break
        folder = folder.parent


def export(ctx: Context, name: str) -> pathlib.Path:
    """Dump the D1 database, copy both buckets and keep the durable secrets under `<export_root>/<company id>/`. The manifest, with `complete` and a hash per file, is written last, so an interrupted export never looks finished."""
    _refuse_ci(ctx)
    company = load_company(ctx, name)
    target = ctx.export_root / company.id
    manifest_path = target / MANIFEST
    failed = ""
    try:
        # An older export must not vouch for a half-written new one.
        manifest_path.unlink(missing_ok=True)
        (target / CHECKED).unlink(missing_ok=True)
        files: dict[str, str] = {}
        dump = _step("export failed: d1 dump", ctx.exporter.dump_d1, company).encode()
        _write(target / DUMP, dump, root=target)
        files[DUMP] = _sha(dump)
        objects: list[dict[str, str]] = []
        for bucket in company.buckets:
            for index, key in enumerate(
                _step("export failed: list bucket", ctx.exporter.bucket_keys, bucket)
            ):
                data = _step("export failed: get object", ctx.exporter.get_object, bucket, key)
                rel = "objects/%s/%d" % (bucket, index)
                _write(target / rel, data, root=target)
                files[rel] = _sha(data)
                objects.append({"bucket": bucket, "key": key, "file": rel})
        wanted = {secrets.store_name(company.id, k): k for k in DURABLE}
        held = _step("export failed: read secrets", ctx.store.read, list(wanted))
        if secrets.store_name(company.id, "ACCOUNT_CONFIG_SERVER_KEY") not in held:
            raise LifecycleError("export failed: the config server key is not in the store")
        kept = {wanted[n]: v for n, v in held.items()}
        blob = json.dumps(kept, sort_keys=True).encode()
        _write(target / SECRETS_FILE, blob, 0o600, root=target)
        files[SECRETS_FILE] = _sha(blob)
        manifest = {
            "company_id": company.id,
            "exported_at": ctx.now(),
            "state_at_export": company.state,
            "complete": True,
            "files": files,
            "objects": objects,
            "secret_names": sorted(kept),
        }
        manifest_tmp = target / (MANIFEST + ".tmp")
        _write(manifest_tmp, json.dumps(manifest, indent=2, sort_keys=True).encode(), root=target)
        os.replace(manifest_tmp, manifest_path)
    except LifecycleError as exc:
        if str(exc).startswith("export failed"):
            raise
        raise LifecycleError("export failed: %s" % exc) from None
    except OSError as exc:
        failed = type(exc).__name__
    if failed:
        raise LifecycleError("export failed: %s" % failed)
    return target


def verify_export(ctx: Context, company: Target) -> str:
    """The export's timestamp when a complete manifest of this company exists and every file still hashes to it; raises naming the first problem."""
    target = ctx.export_root / company.id
    try:
        manifest = json.loads((target / MANIFEST).read_text())
    except (OSError, ValueError):
        raise LifecycleError(
            "no completed export of company %s; run `enterprise export` first" % company.id
        ) from None
    if not isinstance(manifest, dict) or manifest.get("complete") is not True:
        raise LifecycleError(
            "the export of company %s is not complete; run `enterprise export` again" % company.id
        )
    if manifest.get("company_id") != company.id:
        raise LifecycleError(
            "the export manifest belongs to another company; run `enterprise export` again"
        )
    files = manifest.get("files")
    if not isinstance(files, dict) or DUMP not in files:
        raise LifecycleError(
            "the export manifest lists no database dump; run `enterprise export` again"
        )
    if SECRETS_FILE not in files:
        raise LifecycleError(
            "the export manifest lists no secrets file; run `enterprise export` again"
        )
    for entry in manifest.get("objects") or []:
        if not isinstance(entry, dict) or entry.get("file") not in files:
            raise LifecycleError(
                "the export manifest names an object file it does not hash; run `enterprise export` again"
            )
    for rel, digest in sorted(files.items()):
        try:
            data = (target / rel).read_bytes()
        except OSError:
            raise LifecycleError(
                "export file %s is missing; run `enterprise export` again" % rel
            ) from None
        if _sha(data) != digest:
            raise LifecycleError("export file %s no longer matches its manifest hash" % rel)
    return str(manifest.get("exported_at", ""))


# --- remove --------------------------------------------------------------------------


def _refuse_stale_export(ctx: Context, company: Target) -> None:
    """Refuse `delete_data` when the company's database or bucket listing no longer matches its verified export: what changed since would be deleted unexported. Object contents are not re-read; their keys are."""
    folder = ctx.export_root / company.id
    manifest = json.loads((folder / MANIFEST).read_text())
    exported_at = manifest.get("exported_at", "")
    try:
        if (folder / CHECKED).read_text() == exported_at:
            return
    except OSError:
        pass
    again = "changed since the export of %s; run `enterprise export` again" % exported_at
    fresh = _step("stale-export check: d1 dump", ctx.exporter.dump_d1, company).encode()
    if _sha(fresh) != manifest["files"][DUMP]:
        raise LifecycleError("the database of company %s %s" % (company.id, again))
    held = {(o.get("bucket"), o.get("key")) for o in manifest.get("objects") or []}
    now = {
        (bucket, key)
        for bucket in company.buckets
        for key in _step("stale-export check: list bucket", ctx.exporter.bucket_keys, bucket)
    }
    if now != held:
        raise LifecycleError("the buckets of company %s %s" % (company.id, again))
    _step("stale-export check: record", _write, folder / CHECKED, exported_at.encode())


def _secret_names(company: Target) -> list[str]:
    keys = {*secrets.GENERATED, *secrets.OWNED, *secrets.PAIRS}
    return sorted(secrets.store_name(company.id, k) for k in keys)


def remove(
    ctx: Context, name: str, *, delete_data: bool, confirm: str | None = None
) -> RemoveResult:
    """Undeploy a company. Needs a verified export, never runs under GitHub Actions, and keeps D1, buckets and secrets unless `delete_data` comes with `confirm` equal to the company name."""
    _refuse_ci(ctx)
    company = load_company(ctx, name)
    if delete_data and confirm != company.name:
        raise LifecycleError("--delete-data needs --confirm <company> with the exact company name")
    verify_export(ctx, company)
    if delete_data:
        _refuse_stale_export(ctx, company)
    steps: list[str] = []

    def run(what: str, fn: Callable[..., Any], *args: Any) -> None:
        _step(what, fn, *args)
        steps.append(what)

    run("undeploy", ctx.teardown.undeploy, company)
    if not company.unlisted:
        run("drop lookup", ctx.teardown.drop_lookup, company)
    if delete_data:
        run("revoke tokens", ctx.teardown.revoke_tokens, company)
        for bucket in company.buckets:
            run("delete bucket", ctx.teardown.delete_bucket, company, bucket)
        run("delete d1", ctx.teardown.delete_d1, company)
        for secret in _secret_names(company):
            run("delete secret", ctx.teardown.delete_secret, secret)
    _audit(ctx, company, "remove", {"data_deleted": delete_data, "steps": len(steps)})
    _touch(ctx, company, "removed")
    return RemoveResult(company_id=company.id, data_deleted=delete_data, steps=steps)


# --- command wrappers ----------------------------------------------------------------

REFUSALS = (LifecycleError, registry.RegistryUnreachableError)


def cmd_list(ctx: Context, *, include_removed: bool = False, out: Out = print) -> int:
    try:
        rows = list_companies(ctx, include_removed=include_removed)
    except REFUSALS as exc:
        out("enterprise list: %s" % exc)
        return 1
    for r in rows:
        out(
            "%-20s %-5s %-10s machines<=%s storage<=%sGB%s"
            % (
                r["name"],
                r["region"],
                r["state"],
                r.get("max_machines", "?"),
                r.get("max_storage_gb", "?"),
                " unlisted" if r.get("unlisted") else "",
            )
        )
    return 0


def cmd_suspend(ctx: Context, name: str, *, resume: bool = False, out: Out = print) -> int:
    try:
        company = suspend(ctx, name, resume=resume)
    except REFUSALS as exc:
        out("enterprise suspend: %s" % exc)
        return 1
    out("company %s %s" % (company.id, "resumed" if resume else "suspended"))
    return 0


def cmd_update(ctx: Context, name: str, *, out: Out = print, **changes: Any) -> int:
    try:
        result = update(ctx, name, **changes)
    except REFUSALS as exc:
        out("enterprise update: %s" % exc)
        return 1
    out("updated: %s" % ", ".join(sorted(result.changes)))
    if result.redeploy_needed:
        out(
            "the allowlist reaches the Worker on its next deploy: run `enterprise release` for this company"
        )
    return 0


def cmd_export(ctx: Context, name: str, *, out: Out = print) -> int:
    try:
        path = export(ctx, name)
    except REFUSALS as exc:
        out("enterprise export: %s" % exc)
        return 1
    out("exported to %s (holds secrets.json at mode 0600; keep it off shared disks)" % path)
    return 0


def cmd_remove(
    ctx: Context,
    name: str,
    *,
    delete_data: bool = False,
    confirm: str | None = None,
    out: Out = print,
) -> int:
    try:
        result = remove(ctx, name, delete_data=delete_data, confirm=confirm)
    except REFUSALS as exc:
        out("enterprise remove: %s" % exc)
        return 1
    out(
        "company %s removed; %s"
        % (
            result.company_id,
            "data deleted" if result.data_deleted else "data kept (D1, buckets, secrets)",
        )
    )
    return 0
