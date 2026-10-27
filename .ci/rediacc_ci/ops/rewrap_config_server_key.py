#!/usr/bin/env python3
"""Rewrap one account database's layer-3 rows from the public constant to the Worker's own config server key (agent/plans/PLAN-config-server-key.md, box K4).

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.rewrap_config_server_key --region eu --target edge             # dry run
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.rewrap_config_server_key --region eu --target edge --apply
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.rewrap_config_server_key --region eu --target edge --verify
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.rewrap_config_server_key --target bench --apply --verify

THE ROWS. An untagged row is a `config_stores.server_recoverable_org_passphrase` that is not NULL and does not start with `csk1.`: it was sealed under the dev constant. `UNTAGGED_SQL` selects them through `wrangler d1 execute --remote --json`, the way `rediacc_ci.ops.executor_orgs` reads, against the account config `rediacc_ci.deploy.console_executor.account_config` names.

THE CRYPTO IS THE WORKER'S. The rows go on stdin to `private/account/scripts/rewrap-config-server-key.ts`, which imports the Worker's `config-server-key.ts` and `legacy-server-key.ts`, opens each row with the constant, seals it under the key with AAD `csk1|<storeId>`, and opens it again. Nothing here reimplements the format, so a rewrapped row is byte-compatible with what the Worker seals. The key reaches the helper as `ACCOUNT_CONFIG_SERVER_KEY` in its environment, never on argv.

THE WRITE. `--apply` takes a D1 bookmark first (`rediacc_ci.deploy.deploy_record.d1_bookmark`) and prints it with its restore command; no bookmark, no write. It then writes one compare-and-swap UPDATE per row (`WHERE id = <id> AND server_recoverable_org_passphrase = <old value>`) to a private temp file, runs it with `wrangler d1 execute --file`, and deletes the file. A row the Worker rewrote on read in the meantime is left alone by its CAS. Rollback after a rewrap is the bookmark restore, together with the code rollback: older code cannot read a `csk1.` row.

`--verify` exits 0 only when no untagged row is left and every tagged row carries the key's kid; it runs after `--apply` when both are given. The default is a dry run: the rows are read and sealed in memory, nothing is written.

NO VALUE IS PRINTED. Neither the key nor a row value reaches stdout or stderr: a store is named by its first 8 characters, wrangler's output is captured and masked before any of it is shown, and the helper's stdout is a pipe this module reads and never echoes.

THE ENVIRONMENT. `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` and the Worker's own key, `ACCOUNT_CONFIG_SERVER_KEY_<SUFFIX>_<STABLE|EDGE>` (`SUFFIX` is the region's `secretSuffix` in regions.json) or `ACCOUNT_CONFIG_SERVER_KEY_BENCH`. When one is unset and the `rewrap-config-server-key` bws profile is not bound, the run re-executes itself under `bws_env exec --profile rewrap-config-server-key`.

Exit codes: 0 done (dry run planned, apply left nothing untagged, verify clean); 1 refused, or untagged or foreign-kid rows remain; 2 usage.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.deploy import console_executor as target_mod
from rediacc_ci.deploy import deploy_record
from rediacc_ci.ops import executor_orgs

SELF = "rediacc_ci.ops.rewrap_config_server_key"
PROFILE = "rewrap-config-server-key"
PREFIX_LEN = 8
TAG = "csk1."
WORKER_KEY_ENV = "ACCOUNT_CONFIG_SERVER_KEY"
KEY_NAME_PREFIX = "ACCOUNT_CONFIG_SERVER_KEY_"
HELPER_SUBDIR = ("private", "account")
HELPER_SCRIPT = "scripts/rewrap-config-server-key.ts"

COLUMN = "server_recoverable_org_passphrase"
UNTAGGED_SQL = (
    "SELECT id, server_recoverable_org_passphrase FROM config_stores "
    "WHERE server_recoverable_org_passphrase IS NOT NULL "
    "AND server_recoverable_org_passphrase NOT LIKE 'csk1.%'"
)
COUNT_SQL = (
    "SELECT COUNT(*) AS n FROM config_stores "
    "WHERE server_recoverable_org_passphrase IS NOT NULL "
    "AND server_recoverable_org_passphrase NOT LIKE 'csk1.%'"
)
KIDS_SQL = (
    "SELECT substr(server_recoverable_org_passphrase, 6, 8) AS kid, COUNT(*) AS n "
    "FROM config_stores WHERE server_recoverable_org_passphrase LIKE 'csk1.%' "
    "GROUP BY substr(server_recoverable_org_passphrase, 6, 8)"
)
# One compare-and-swap UPDATE; @NEW@, @ID@ and @OLD@ are filled by `cas_sql` after each is checked to hold no quote.
CAS_SQL = (
    "UPDATE config_stores SET server_recoverable_org_passphrase = '@NEW@' "
    "WHERE id = '@ID@' AND server_recoverable_org_passphrase = '@OLD@';"
)

SQL_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}\Z")
KID = re.compile(r"^[0-9a-f]{8}\Z")
LEGACY_VALUE = re.compile(r"^[A-Za-z0-9+/]+=*\Z")
REDACTED = "<redacted>"


class RefusedError(Exception):
    """A run that must stop with exit 1; the message carries no value."""


def prefix(value: object) -> str:
    return str(value)[:PREFIX_LEN]


def key_env_name(root: pathlib.Path, target: str, region: str) -> str:
    """The bws name of the Worker's own key for one target."""
    if target == target_mod.BENCH_TARGET:
        return KEY_NAME_PREFIX + "BENCH"
    try:
        doc = json.loads((root / "regions.json").read_text(encoding="utf-8"))
        suffix = next(str(r["secretSuffix"]) for r in doc["regions"] if str(r.get("id")) == region)
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        raise RefusedError("regions.json names no secretSuffix for region %s" % region) from None
    if not re.match(r"^[A-Z]+\Z", suffix):
        raise RefusedError("regions.json secretSuffix of %s is not upper-case letters" % region)
    return "%s%s_%s" % (KEY_NAME_PREFIX, suffix, target.upper())


def missing_env(key_name: str) -> list[str]:
    return target_mod.missing_env() + ([] if os.environ.get(key_name) else [key_name])


# ---- output hygiene ------------------------------------------------------------


def mask(text: str, secrets: list[str], ids: list[str] | None = None) -> str:
    """`text` with every known secret value replaced; longest first, so a value inside another is not left half-shown."""
    for value in sorted({s for s in secrets if len(s) >= 4}, key=len, reverse=True):
        text = text.replace(value, REDACTED)
    for sid in sorted(set(ids or []), key=len, reverse=True):
        if len(sid) > PREFIX_LEN:
            text = text.replace(sid, prefix(sid))
    return text


def tail(text: str, secrets: list[str], ids: list[str] | None = None, lines: int = 3) -> str:
    kept = [ln for ln in mask(text, secrets, ids).splitlines() if ln.strip()]
    return "; ".join(kept[-lines:])


# ---- D1 ------------------------------------------------------------------------


class D1:
    """One account database through wrangler, every stream captured and masked."""

    def __init__(self, worker_dir: pathlib.Path, config: str, secrets: list[str]) -> None:
        self.worker_dir = worker_dir
        self.config = config
        self.database = executor_orgs.database_name(worker_dir / config)
        self.secrets = secrets
        self.ids: list[str] = []

    def _run(self, argv: list[str], what: str) -> str:
        proc = subprocess.run(
            argv,
            cwd=self.worker_dir,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RefusedError(
                "%s on %s exited %d: %s"
                % (
                    what,
                    self.database,
                    proc.returncode,
                    tail(proc.stderr or proc.stdout, self.secrets, self.ids),
                )
            )
        return proc.stdout

    def query(self, sql: str) -> list[dict]:
        out = self._run(executor_orgs.d1_argv(self.database, self.config, sql), "d1 read")
        rows = executor_orgs.parse_rows(out)
        if rows is None:
            raise RefusedError("UNVERIFIED: d1 read on %s printed no result rows" % self.database)
        return rows

    def execute_file(self, path: pathlib.Path) -> None:
        argv = [
            "npx", "wrangler", "d1", "execute", self.database, "--remote", "--json",
            "--yes", "--file", str(path), "--config", self.config,
        ]  # fmt: skip
        out = self._run(argv, "d1 write")
        if executor_orgs.parse_rows(out) is None:
            raise RefusedError(
                "UNVERIFIED: d1 write on %s did not report every statement a success"
                % self.database
            )

    def bookmark(self) -> str:
        try:
            return deploy_record.d1_bookmark(self.worker_dir, self.database, self.config)
        except deploy_record.RecordError as exc:
            raise RefusedError("%s; nothing is written" % exc) from None


def untagged_rows(d1: D1) -> list[dict]:
    """The untagged rows, each checked to be a plain id and a legacy base64 value."""
    rows = d1.query(UNTAGGED_SQL)
    out = []
    for row in rows:
        sid, value = row.get("id"), row.get(COLUMN)
        if not isinstance(sid, str) or not SQL_ID.match(sid):
            raise RefusedError("a config_stores id (%s) is not safe to put in SQL" % prefix(sid))
        if not isinstance(value, str) or not LEGACY_VALUE.match(value):
            raise RefusedError("store %s holds a value that is not legacy base64" % prefix(sid))
        out.append({"id": sid, "value": value})
    return out


def untagged_count(d1: D1) -> int:
    rows = d1.query(COUNT_SQL)
    try:
        return int(rows[0]["n"])
    except (IndexError, KeyError, TypeError, ValueError):
        raise RefusedError(
            "UNVERIFIED: the untagged count on %s did not parse" % d1.database
        ) from None


def kid_counts(d1: D1) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in d1.query(KIDS_SQL):
        try:
            out[str(row["kid"])] = int(row["n"])
        except (KeyError, TypeError, ValueError):
            raise RefusedError(
                "UNVERIFIED: the kid census on %s did not parse" % d1.database
            ) from None
    return out


# ---- the helper ----------------------------------------------------------------


def helper_argv(mode: str) -> list[str]:
    return ["npx", "tsx", HELPER_SCRIPT, mode]


def run_helper(
    root: pathlib.Path, key: str, mode: str, payload: dict | None, secrets: list[str]
) -> dict:
    """One helper call; its stdout is parsed and never shown."""
    ids = [str(r.get("id")) for r in (payload or {}).get("rows", [])]
    env = dict(os.environ)
    env[WORKER_KEY_ENV] = key
    proc = subprocess.run(
        helper_argv(mode),
        cwd=root.joinpath(*HELPER_SUBDIR),
        input=json.dumps(payload) if payload is not None else "",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RefusedError(
            "the rewrap helper (%s) exited %d: %s"
            % (mode, proc.returncode, tail(proc.stderr, [*secrets, key], ids))
        )
    line = next((ln for ln in reversed(proc.stdout.splitlines()) if ln.startswith("{")), "")
    try:
        doc = json.loads(line)
    except ValueError:
        doc = None
    if not isinstance(doc, dict) or not KID.match(str(doc.get("kid") or "")):
        raise RefusedError("UNVERIFIED: the rewrap helper (%s) printed no kid" % mode)
    return doc


def check_rewrapped(rows: list[dict], doc: dict) -> list[dict]:
    """The helper's rows, refused unless they are exactly the input rows, each sealed under the kid."""
    kid = str(doc["kid"])
    got = doc.get("rows")
    if not isinstance(got, list) or len(got) != len(rows):
        raise RefusedError(
            "the rewrap helper returned %s rows for %d"
            % (len(got) if isinstance(got, list) else "no", len(rows))
        )
    sealed = re.compile(r"^csk1\.%s\.[A-Za-z0-9+/]+=*\Z" % kid)
    by_id = {r["id"]: r["value"] for r in rows}
    out = []
    for item in got:
        sid = item.get("id") if isinstance(item, dict) else None
        if sid not in by_id or item.get("old") != by_id[sid]:
            raise RefusedError(
                "the rewrap helper returned a row it was not given (%s)" % prefix(sid)
            )
        if not isinstance(item.get("new"), str) or not sealed.match(item["new"]):
            raise RefusedError("store %s did not come back sealed as csk1.%s." % (prefix(sid), kid))
        out.append({"id": sid, "old": by_id.pop(sid), "new": item["new"]})
    return out


def cas_sql(rewrapped: list[dict]) -> str:
    """One compare-and-swap UPDATE per row; every literal is checked to hold no quote."""
    lines = []
    for r in rewrapped:
        for v in (r["id"], r["old"], r["new"]):
            if "'" in v:
                raise RefusedError("store %s has a quote in a literal" % prefix(r["id"]))
        lines.append(
            CAS_SQL.replace("@NEW@", r["new"]).replace("@ID@", r["id"]).replace("@OLD@", r["old"])
        )
    return "\n".join(lines) + "\n"


def write_cas(d1: D1, sql: str) -> None:
    fd, name = tempfile.mkstemp(prefix="rewrap-csk-", suffix=".sql")
    path = pathlib.Path(name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(sql)
        d1.execute_file(path)
    finally:
        path.unlink(missing_ok=True)


# ---- run -----------------------------------------------------------------------


def _verify(d1: D1, kid: str, where: str) -> int:
    left = untagged_count(d1)
    kids = kid_counts(d1)
    foreign = {k: n for k, n in kids.items() if k != kid}
    tagged = kids.get(kid, 0)
    if left or foreign:
        log.error(
            "%s: %d untagged row(s), %d row(s) under a foreign kid (%s), %d under csk1.%s"
            % (where, left, sum(foreign.values()), " ".join(sorted(foreign)) or "none", tagged, kid)
        )
        return 1
    log.success("%s: no untagged row; %d row(s) under csk1.%s" % (where, tagged, kid))
    return 0


def _work(args: argparse.Namespace, root: pathlib.Path, config: str, key: str, where: str) -> int:
    secrets = [key]
    d1 = D1(root.joinpath(*target_mod.ACCOUNT_SUBDIR), config, secrets)
    kid = str(run_helper(root, key, "kid", None, secrets)["kid"])
    if args.verify and not args.apply:
        return _verify(d1, kid, where)
    if args.apply:
        bookmark = d1.bookmark()
        log.info(
            "D1 bookmark %s; restore: %s"
            % (bookmark, deploy_record.restore_command(d1.database, bookmark, config))
        )
    rows = untagged_rows(d1)
    secrets += [r["value"] for r in rows]
    d1.ids += [r["id"] for r in rows]
    names = " ".join(prefix(r["id"]) for r in rows) or "none"
    if not rows:
        log.info("%s: no untagged row" % where)
        return _verify(d1, kid, where) if args.verify else 0
    doc = run_helper(root, key, "rewrap", {"rows": rows}, secrets)
    rewrapped = check_rewrapped(rows, doc)
    secrets += [r["new"] for r in rewrapped]
    if not args.apply:
        log.info(
            "%s: %d untagged row(s) open and seal under csk1.%s: %s"
            % (where, len(rows), kid, names)
        )
        log.info("dry run: nothing written; re-run with --apply")
        return 0
    write_cas(d1, cas_sql(rewrapped))
    left = untagged_count(d1)
    log.info("%s: %d row(s) written under csk1.%s: %s" % (where, len(rewrapped), kid, names))
    if args.verify:
        return _verify(d1, kid, where)
    if left:
        log.error("%s: %d untagged row(s) remain after the write" % (where, left))
        return 1
    return 0


def reexec_argv(argv: list[str]) -> list[str]:
    """This same run under the rewrap-config-server-key bws profile."""
    return [
        sys.executable, "-m", "rediacc_ci.core.bws_env", "exec", "--profile", PROFILE,
        "--", sys.executable, "-m", SELF, *argv,
    ]  # fmt: skip


def run(
    args: argparse.Namespace, argv: list[str] | None = None, root: pathlib.Path | None = None
) -> int:
    root = root or paths.repo_root()
    try:
        region, config = target_mod.resolve_target(root, args.target, args.region)
        key_name = key_env_name(root, args.target, region)
    except (target_mod.RefusedError, RefusedError) as exc:
        log.error(str(exc))
        return 1
    missing = missing_env(key_name)
    if missing:
        if argv is not None and not target_mod.profile_bound(PROFILE):
            return subprocess.run(
                reexec_argv(argv),
                check=False,
                env=target_mod.package_env(),
            ).returncode
        log.error("%s must be set (bws_env exec --profile %s)" % (" and ".join(missing), PROFILE))
        return 1
    where = "%s %s" % (args.target, region)
    try:
        return _work(args, root, config, os.environ[key_name], where)
    except (RefusedError, target_mod.RefusedError) as exc:
        log.error(str(exc))
        return 1


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=SELF, description=(__doc__ or "").splitlines()[0])
    p.add_argument("--target", required=True, help="stable, edge or bench")
    p.add_argument("--region", default=None, help="eu, us or asia (bench: eu only)")
    p.add_argument(
        "--apply", action="store_true", help="write the rewrapped rows (default: dry run)"
    )
    p.add_argument("--verify", action="store_true", help="exit 0 only when no untagged row is left")
    return p


def main(argv: list[str]) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    return run(args, argv=argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
