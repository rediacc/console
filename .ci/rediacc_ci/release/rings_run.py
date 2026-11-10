"""The Enterprise release ring runner (agent/plans/PLAN-enterprise-isolation.md, Design *Rings*, box K2).

    PYTHONPATH=.ci python3 -m rediacc_ci.release.rings_run --version V [--bench] [--dry-run]
        [--company c<hex> ...] [--resume V --company c<hex>]
        [--order <id> [--skip-pauses] [--waive-soak]]
        [--bench only: --plant-failure c<hex> --soak-days N --pause-minutes N]

STATELESS PER INVOCATION. Every run reads the whole picture again from each region's control database (`control-<region>`, `control-bench-<region>` under `--bench`): the active companies, their stored machine high-water mark, ring override and upgrade window, this version's `rollout` rows, and the rings already re-smoked (`audit` rows of action `ring-resmoke`). Bench and the fast tier are the shared release's: both count as taken once the edge release record `release-records/v<V>/edge.json` exists over the public releases origin with no failed step, and its `recorded_at` starts the soak. The pure core `rings.decide` (box K1) then names the next action, and the runner loops decide-and-act until the answer is `wait`, `window`, `stop` or `done`, so one run walks every ring whose pause has run.

MACHINE SAMPLING. Before deciding, each company's own database (`account-<name>`) answers `COUNT(DISTINCT machine_id)` over `subscription_activations`, and `rings.high_water` keeps the larger of that and the stored mark, written back to the `ring` row. A sample that fails falls back to the stored mark; a company that was never sampled and cannot be sampled refuses the run, because a ring read from nothing could deploy a large company first.

ONE `Run` PER COMPANY. `Run.execute` rolls back every armed target of a run when one step fails (.ci/rediacc_ci/release/local.py `Run.execute`), so each company gets its own `Run` over its own `Step` rows, built from the company's validated `CompanyTarget`: `record-before`, `account-deploy`, `proxy-deploy`, `proxy-smoke`, `executor-enable`, then `rollback` on a failure and `record-after` always, both armed by `record-before`. The company rows drop `account-secrets`: a company's secrets are pushed by its own required list (box D2), never the shared pusher. `record-after` writes the record to the region's control database (`--sink control`), never the releases bucket, which sits behind a public origin. The first attempt of a version is rollout key `v<V>`; a later attempt of the same company is `v<V>+a<n>`, because a rollout key is written once.

A FAILURE LATCHES A STOP. A company whose run exits non-zero gets a `failed` rollout row from the runner too (key `v<V>+f<n>`), whatever `record-after` managed, and the run stops naming it. Nothing deploys again until `--resume V --company <id>` names that version and company. A re-smoke that fails latches the same way on the company that failed it.

`--company` TAKES THE OPAQUE ID ONLY (`c` and 8 or more hex digits), never a name, because the GitHub path's inputs can be visible; a name is refused without being echoed. Given alone, it restricts the deploys to the named companies, and the other companies still shape the decision; beside `--resume` it names the company put back in its ring, and the release continues past it. Every line this module prints names a company by its id; labels and hosts reach only child argv.

AN UNREACHABLE REGION stops only its own companies: the others release, the region is named, and the run exits 1.

`--dry-run` reads (samples included) and prints the decision and the rows each company would run, writes nothing and runs no child.

BENCH ONLY. `--plant-failure <id>` fails that company's run right after `record-before` (the V5 proof), and `--soak-days N` and `--pause-minutes N` shorten the soak and the pauses for fake companies. Each is refused without `--bench`.

THE GUARD. `block_unasked_release` admits a `--bench` or `--dry-run` run freely and asks for a proven `RELEASE_ASKED` before a real company's release: company Workers carry the stable channel.

EXIT CODES. 0 the run ended on `wait`, `window` or `done`; 1 a company failed, a stop is latched, a sample could not be read, or a region was unreachable; 2 the flags were refused before anything was read (a malformed `--version` or `--company` included), or a `--company` names no active company of the reachable regions (found only after the regions were read).
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from typing import TYPE_CHECKING, Any

from rediacc_ci import paths
from rediacc_ci.core import wrangler as wrangler_cmd
from rediacc_ci.deploy import console_executor
from rediacc_ci.enterprise import lab, proof, registry
from rediacc_ci.release import local, rings
from rediacc_ci.well_known import PRODUCT_DOMAIN

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Sequence

SELF = "rediacc_ci.release.rings_run"
PY = ("python3", "-m")
ACCOUNT_PROFILE = "deploy-workers"
RESMOKE_ACTION = "ring-resmoke"
ACTOR = "rings_run"
EDGE_RECORD = "%s/release-records/v%s/edge.json"
OUT_REL = ".ci/cache/rings"
BENCH_PAUSE_ORDER = "bench-pause"
MAX_ROUNDS = 64
# The version reaches a curl URL and rollout keys, so only a plain semantic version is admitted.
# [0-9], not \d: in a str pattern \d also matches non-ASCII digits.
VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?")
# The failures a D1 transport raises (the same set `registry.Registry.read_all` names): the region or company database is what matters.
TRANSPORT_ERRORS = (OSError, RuntimeError, ValueError, LookupError)
SAMPLE_SQL = "SELECT COUNT(DISTINCT machine_id) AS n FROM subscription_activations"
COMPANIES_SQL = (
    "SELECT c.id, c.name, c.region, r.machines_high_water AS stored, r.sampled_at,"
    " o.ring AS override, w.days, w.start_hour, w.end_hour FROM companies c"
    " LEFT JOIN ring r ON r.company_id = c.id"
    " LEFT JOIN ring_override o ON o.company_id = c.id"
    " LEFT JOIN upgrade_window w ON w.company_id = c.id"
    " WHERE c.state = 'active' ORDER BY c.id"
)
ROLLOUT_SQL = (
    "SELECT release_id, company_id, ring, status, version, finished_at FROM rollout"
    " ORDER BY finished_at, release_id"
)
RESMOKED_SQL = "SELECT detail FROM audit WHERE action = ? ORDER BY id"
HIGH_WATER_SQL = (
    "INSERT INTO ring (company_id, machines_high_water, sampled_at) VALUES (?, ?, ?)"
    " ON CONFLICT(company_id) DO UPDATE SET"
    " machines_high_water = MAX(machines_high_water, excluded.machines_high_water),"
    " sampled_at = excluded.sampled_at"
)
ROLLOUT_INSERT = (
    "INSERT INTO rollout (release_id, company_id, ring, status, version, finished_at)"
    " VALUES (?, ?, ?, ?, ?, ?)"
)
AUDIT_INSERT = "INSERT INTO audit (at, company_id, actor, action, detail) VALUES (?, ?, ?, ?, ?)"
STATUS: dict[str, rings.Status] = {"deployed": "done", "failed": "failed"}

Query = registry.Query


# --------------------------------------------------------------------------- the world


@dataclasses.dataclass(frozen=True)
class CompanyRow:
    """One active company as the control database holds it. `name` is the label and stays in this process."""

    id: str
    name: str
    region: str
    stored: int
    machines: int
    sampled: bool
    override: str | None
    windows: tuple[rings.Window, ...]
    bench: bool


@dataclasses.dataclass
class World:
    """What a run touches, every part injectable: the D1 transport (control and company databases), the edge release record reader, the child runner of the `Step` rows, the clock, and the company target builder."""

    query: Query
    release_record: Callable[[str], dict[str, Any] | None]
    runner: local.Runner
    now: Callable[[], datetime.datetime]
    root: pathlib.Path
    out: pathlib.Path
    target: Callable[[CompanyRow], console_executor.CompanyTarget]


@dataclasses.dataclass
class Read:
    state: rings.State
    rows: dict[str, CompanyRow]
    rollouts: dict[str, list[dict[str, Any]]]
    previous: dict[str, str]
    unreachable: dict[str, str]
    unsampled: list[str]


def windows_of(days: str | None, start: int | None, end: int | None) -> tuple[rings.Window, ...]:
    """The `upgrade_window` row (ISO weekdays, 1 is Monday, as `1-3,5`; UTC hours, `end_hour` up to 24) as a `rings.Window`."""
    if days is None or start is None or end is None:
        return ()
    picked: set[int] = set()
    for item in str(days).split(","):
        lo, _, hi = item.strip().partition("-")
        first, last = int(lo), int(hi or lo)
        picked.update(d - 1 for d in range(first, last + 1))
    return (rings.Window(frozenset(picked), int(start) * 60, (int(end) * 60) % (24 * 60)),)


def _parse_at(text: str | None) -> datetime.datetime | None:
    if not text:
        return None
    return datetime.datetime.fromisoformat(str(text))


def _stamp(at: datetime.datetime) -> str:
    return at.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sample(world: World, row: dict[str, Any]) -> int | None:
    """The company's distinct machine count, or None when its database cannot answer (the stored mark then decides)."""
    try:
        got = world.query("account-%s" % row["name"], SAMPLE_SQL, [])
    except TRANSPORT_ERRORS:
        return None
    return int(got[0]["n"]) if got else 0


def _status(rows: Sequence[dict[str, Any]]) -> tuple[rings.Status, datetime.datetime | None]:
    if not rows:
        return "pending", None
    last = rows[-1]
    return STATUS.get(str(last.get("status")), "pending"), _parse_at(last.get("finished_at"))


def read_world(
    world: World,
    version: str,
    *,
    bench: bool,
    sample: bool,
    write: bool = False,
    soak_days: int = rings.SOAK_DAYS,
    order: rings.Order | None = None,
    resume: rings.Resume | None = None,
) -> Read:
    """Every reachable region's companies and this version's progress, as the `rings.State` `decide` reads."""
    now = world.now()
    rows: dict[str, CompanyRow] = {}
    rollouts: dict[str, list[dict[str, Any]]] = {}
    previous: dict[str, str] = {}
    resmoked: set[str] = set()
    unreachable: dict[str, str] = {}
    unsampled: list[str] = []
    for region, database in registry.databases(bench).items():
        try:
            companies = world.query(database, COMPANIES_SQL, [])
            rollout = world.query(database, ROLLOUT_SQL, [])
            audit = world.query(database, RESMOKED_SQL, [RESMOKE_ACTION])
        except TRANSPORT_ERRORS as exc:
            unreachable[region] = type(exc).__name__
            continue
        for row in rollout:
            if row.get("version") == version:
                rollouts.setdefault(row["company_id"], []).append(row)
            elif row.get("status") == "deployed":
                previous[row["company_id"]] = str(row["version"])
        for row in audit:
            try:
                detail = json.loads(row.get("detail") or "{}")
            except ValueError:
                continue
            if detail.get("version") == version and detail.get("ring") in rings.COMPANY_RINGS:
                resmoked.add(detail["ring"])
        for row in companies:
            stored = int(row.get("stored") or 0)
            got = _sample(world, row) if sample else None
            if got is None and sample and not row.get("sampled_at"):
                unsampled.append(row["id"])
                continue
            machines = rings.high_water(stored, got if got is not None else 0)
            if write and got is not None:
                try:
                    world.query(database, HIGH_WATER_SQL, [row["id"], machines, _stamp(now)])
                except TRANSPORT_ERRORS as exc:
                    _say(
                        "region %s: the machine mark of company %s could not be stored (%s); the stored mark stays"
                        % (region, row["id"], type(exc).__name__)
                    )
                    if not row.get("sampled_at"):
                        unsampled.append(row["id"])
                        continue
                    machines, got = stored, None
            rows[row["id"]] = CompanyRow(
                id=row["id"],
                name=row["name"],
                region=row.get("region") or region,
                stored=stored,
                machines=machines,
                sampled=got is not None,
                override=row.get("override"),
                windows=windows_of(row.get("days"), row.get("start_hour"), row.get("end_hour")),
                bench=bench,
            )
    companies_state = []
    for cid, company in rows.items():
        status, finished = _status(rollouts.get(cid, []))
        companies_state.append(
            rings.Company(
                cid,
                company.region,
                company.machines,
                status=status,
                override=company.override,
                windows=company.windows,
                finished_at=finished,
            )
        )
    record = world.release_record(version)
    taken = bool(record) and not (record or {}).get("failed_step")
    fast_at = _parse_at((record or {}).get("recorded_at")) if taken else None
    state = rings.State(
        version=version,
        bench_done=taken,
        fast_at=fast_at,
        companies=tuple(companies_state),
        order=order,
        resume=resume,
        resmoked=frozenset(resmoked),
        unreachable=frozenset(unreachable),
        soak_days=soak_days,
    )
    return Read(state, rows, rollouts, previous, unreachable, unsampled)


# --------------------------------------------------------------------------- the company rows


def _step_env(company: console_executor.CompanyTarget, sid: str) -> tuple[tuple[str, str], ...]:
    """The non-secret metadata each company child carries: its row id, and the company by opaque id and region."""
    return (
        ("RINGS_STEP", sid),
        ("RINGS_COMPANY", company.company_id),
        ("RINGS_REGION", company.region),
    )


def company_steps(
    company: console_executor.CompanyTarget,
    *,
    ring: str,
    release_id: str,
    previous: str,
    planted: bool = False,
) -> tuple[local.Step, ...]:
    """One company's rows: the release table's deploy rows for a company target, with no `account-secrets`. Ids never carry the label."""
    argv = tuple(console_executor.company_argv(company))
    k = argv.index("--proxy-config") if "--proxy-config" in argv else -1
    # deploy_account accepts no --proxy-config (its ACCEPTED_ARGS).
    account_argv = argv[:k] + argv[k + 2 :] if k >= 0 else argv
    proxy = console_executor.profile_for(company.profile_target)
    prev = ("--previous-release", previous) if previous else ()

    def step(sid: str, cmd: tuple[str, ...], **kw: Any) -> local.Step:
        return local.Step(sid, "deploy", cmd, cwd="root", env=_step_env(company, sid), **kw)

    rows = [
        step(
            "record-before",
            (
                *PY,
                "rediacc_ci.deploy.deploy_record",
                "before",
                *argv,
                "--version",
                "{version}",
                "--out",
                "{out}/before.json",
                *prev,
            ),
            profiles=(proxy,),
        ),
    ]
    if planted:
        rows.append(step("planted-failure", ("python3", "-c", "raise SystemExit(1)")))
    rows += [
        step(
            "account-deploy",
            (*PY, "rediacc_ci.deploy.deploy_account", *account_argv),
            profiles=(ACCOUNT_PROFILE,),
        ),
        step(
            "proxy-deploy",
            (
                *PY,
                "rediacc_ci.deploy.deploy_proxy",
                *argv,
                "--version",
                "{version}",
                "--record",
                "{out}/proxy.json",
            ),
            profiles=(proxy,),
        ),
        step(
            "proxy-smoke",
            (
                *PY,
                "rediacc_ci.deploy.deploy_proxy",
                *argv,
                "--smoke-only",
                "--record",
                "{out}/proxy.json",
            ),
            profiles=(proxy,),
        ),
        step(
            "executor-enable",
            (*PY, "rediacc_ci.deploy.console_executor", "--enable", *argv),
            profiles=(proxy,),
        ),
        step(
            "rollback",
            (*PY, "rediacc_ci.deploy.deploy_record", "rollback", "--before", "{out}/before.json"),
            profiles=(proxy,),
            on_failure=True,
            arm="record-before",
        ),
        step(
            "record-after",
            (
                *PY,
                "rediacc_ci.deploy.deploy_record",
                "after",
                "--before",
                "{out}/before.json",
                "--proxy-record",
                "{out}/proxy.json",
                "--manifest",
                "workers/proxy/stage/manifest.json",
                "--enable-outcome",
                "{outcome:executor-enable}",
                "--rollback-outcome",
                "{outcome:rollback}",
                "--out",
                "{out}/record.json",
                "--sink",
                "control",
                "--ring",
                ring,
                "--release-id",
                release_id,
            ),
            profiles=(proxy,),
            always=True,
            arm="record-before",
        ),
    ]
    return tuple(rows)


def smoke_steps(company: console_executor.CompanyTarget) -> tuple[local.Step, ...]:
    argv = tuple(console_executor.company_argv(company))
    return (
        local.Step(
            "proxy-smoke",
            "smoke",
            (*PY, "rediacc_ci.deploy.deploy_proxy", *argv, "--smoke-only"),
            profiles=(console_executor.profile_for(company.profile_target),),
            cwd="root",
            env=_step_env(company, "proxy-smoke"),
        ),
    )


# --------------------------------------------------------------------------- acting


def _say(text: str) -> None:
    print("%s: %s" % (SELF, text), file=sys.stderr)


def _ring(row: CompanyRow) -> str:
    return rings.ring_of(row.machines, row.override)


def _release_id(version: str, rollouts: Sequence[dict[str, Any]], kind: str) -> str:
    if not rollouts and kind == "a":
        return "v%s" % version
    return "v%s+%s%d" % (version, kind, len(rollouts))


def _database(row: CompanyRow) -> str:
    return registry.control_database(row.region, row.bench)


def _mark_failed(world: World, read: Read, row: CompanyRow, version: str) -> None:
    rid = _release_id(version, read.rollouts.get(row.id, []), "f")
    now = _stamp(world.now())
    try:
        world.query(
            _database(row), ROLLOUT_INSERT, [rid, row.id, _ring(row), "failed", version, now]
        )
    except TRANSPORT_ERRORS as exc:
        _say(
            "company %s failed on %s, but the stop could not be persisted (%s); a rerun will not know it"
            % (row.id, version, type(exc).__name__)
        )


def _run(world: World, version: str, row: CompanyRow, steps: Sequence[local.Step], rid: str) -> int:
    out = world.out / version / row.id / rid
    ctx = local.Context(version=version, out=str(out), outcomes={})
    return local.Run(world.root, ctx, runner=world.runner, backoff=()).execute(steps)


def _target(world: World, row: CompanyRow) -> console_executor.CompanyTarget | None:
    try:
        return world.target(row)
    except console_executor.RefusedError as exc:
        _say(
            "company %s cannot be targeted: %s"
            % (row.id, console_executor.mask_label(str(exc), row.name, row.id))
        )
        return None


def _prev_ring(read: Read, ring: str | None) -> str | None:
    """The last ring before `ring` that has companies: the one a pause or re-smoke is about."""
    if ring not in rings.COMPANY_RINGS:
        return None
    have = {_ring(r) for r in read.rows.values()}
    before = [r for r in rings.COMPANY_RINGS[: rings.COMPANY_RINGS.index(ring)] if r in have]
    return before[-1] if before else None


def _bench_pause(
    read: Read, decision: rings.Decision, now: datetime.datetime, minutes: int
) -> rings.Decision:
    """A pause shortened to `minutes` (bench only): once that has run, the same state is decided again with the pause skipped."""
    prev = _prev_ring(read, decision.ring)
    if decision.action != "wait" or decision.until is None or prev not in rings.PAUSE_AFTER:
        return decision
    short = decision.until - rings.PAUSE_AFTER[prev] + datetime.timedelta(minutes=minutes)
    if now < short:
        return dataclasses.replace(
            decision, until=short, reason="pause after %s until %s" % (prev, short.isoformat())
        )
    order = read.state.order
    skip = rings.Order(
        BENCH_PAUSE_ORDER, skip_pauses=True, waive_soak=bool(order and order.waive_soak)
    )
    return rings.decide(dataclasses.replace(read.state, order=skip), now)


def describe(decision: rings.Decision) -> str:
    parts: list[str] = [decision.action]
    if decision.ring:
        parts.append("ring=%s" % decision.ring)
    if decision.companies:
        parts.append("companies=%s" % ",".join(decision.companies))
    if decision.resmoke:
        parts.append("resmoke=%s" % ",".join(decision.resmoke))
    if decision.held:
        parts.append("held=%s" % ",".join(decision.held))
    return "%s -- %s" % (" ".join(parts), decision.reason)


def _resmoke(
    world: World, read: Read, decision: rings.Decision, version: str, dry: bool
) -> str | None:
    """Re-smoke the ring before; None on a pass, else the company id that failed."""
    ring = _prev_ring(read, decision.ring)
    for cid in decision.resmoke:
        row = read.rows[cid]
        if dry:
            print("would re-smoke %s (ring %s)" % (cid, ring))
            continue
        target = _target(world, row)
        if target is None or _run(world, version, row, smoke_steps(target), "resmoke") != 0:
            return cid
    if dry:
        return None
    detail = json.dumps({"version": version, "ring": ring}, sort_keys=True)
    for database in sorted({_database(read.rows[c]) for c in decision.resmoke}):
        world.query(
            database, AUDIT_INSERT, [_stamp(world.now()), None, ACTOR, RESMOKE_ACTION, detail]
        )
    _say("ring %s re-smoked" % ring)
    return None


def _deploy(world: World, read: Read, cid: str, version: str, planted: str, dry: bool) -> bool:
    row = read.rows[cid]
    rid = _release_id(version, read.rollouts.get(cid, []), "a")
    ring = _ring(row)
    if dry:
        print("would deploy %s to %s in ring %s as %s" % (version, cid, ring, rid))
        return True
    target = _target(world, row)
    if target is None:
        _mark_failed(world, read, row, version)
        return False
    steps = company_steps(
        target,
        ring=ring,
        release_id=rid,
        previous=read.previous.get(cid, ""),
        planted=planted == cid,
    )
    if _run(world, version, row, steps, rid) != 0:
        _mark_failed(world, read, row, version)
        _say("company %s failed on %s (ring %s); the release is stopped" % (cid, version, ring))
        return False
    _say("company %s runs %s (ring %s)" % (cid, version, ring))
    return True


# --------------------------------------------------------------------------- the run


def parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog=SELF, description=(__doc__ or "").splitlines()[0])
    p.add_argument("--version", required=True)
    p.add_argument("--bench", action="store_true", help="bench companies and control databases")
    p.add_argument("--dry-run", action="store_true", help="decide and print; write and run nothing")
    p.add_argument("--company", action="append", default=[], help="an opaque c<hex> id")
    p.add_argument("--resume", default=None, metavar="V")
    p.add_argument("--order", default=None, help="a security order id")
    p.add_argument("--skip-pauses", action="store_true")
    p.add_argument("--waive-soak", action="store_true")
    p.add_argument("--plant-failure", default=None, metavar="ID", help="bench only")
    p.add_argument("--soak-days", type=int, default=None, help="bench only")
    p.add_argument("--pause-minutes", type=int, default=None, help="bench only")
    return p.parse_args(argv)


def refusals(args: argparse.Namespace) -> list[str]:
    out = rings.order_refusals(args.order, skip_pauses=args.skip_pauses, waive_soak=args.waive_soak)
    if not VERSION_RE.fullmatch(args.version):
        out.append(
            "--version %r is not a semantic version (N.N.N, optional -pre and +build)"
            % args.version
        )
    if any(not console_executor.COMPANY_ID_RE.fullmatch(c) for c in args.company):
        out.append(
            "--company takes the opaque id (c followed by 8 or more hex digits), never a name"
        )
    if args.resume is not None and len(args.company) != 1:
        out.append("--resume V needs exactly one --company <id>")
    planted = args.plant_failure
    if planted is not None and not console_executor.COMPANY_ID_RE.fullmatch(planted):
        out.append("--plant-failure takes the opaque id")
    for flag, value in (
        ("--plant-failure", planted),
        ("--soak-days", args.soak_days),
        ("--pause-minutes", args.pause_minutes),
    ):
        if value is not None and not args.bench:
            out.append("%s is for bench companies only (--bench)" % flag)
    for flag, value in (("--soak-days", args.soak_days), ("--pause-minutes", args.pause_minutes)):
        if value is not None and value < 0:
            out.append("%s %d is negative" % (flag, value))
    return out


def release(args: argparse.Namespace, world: World) -> int:
    version = args.version
    order = rings.Order(args.order, args.skip_pauses, args.waive_soak) if args.order else None
    resume = rings.Resume(args.resume, args.company[0]) if args.resume is not None else None
    soak = args.soak_days if args.soak_days is not None else rings.SOAK_DAYS
    # Beside --resume, --company names the company put back in its ring and restricts nothing: the release then continues.
    only = set() if resume is not None else set(args.company)
    sample = True
    read: Read | None = None
    decision: rings.Decision | None = None
    for _round in range(MAX_ROUNDS):
        read = read_world(
            world,
            version,
            bench=args.bench,
            sample=sample,
            write=sample and not args.dry_run,
            soak_days=soak,
            order=order,
            resume=resume,
        )
        sample = False
        if read.unsampled:
            _say(
                "never sampled and the sample failed: %s; no ring can be read for them"
                % ", ".join(sorted(read.unsampled))
            )
            return 1
        missing = sorted(only - set(read.rows))
        if missing:
            where = sorted(read.unreachable)
            tail = " (unreachable: %s)" % ", ".join(where) if where else ""
            _say("no active company %s in the reachable regions%s" % (", ".join(missing), tail))
            return 2
        now = world.now()
        decision = rings.decide(read.state, now)
        if args.bench and args.pause_minutes is not None:
            decision = _bench_pause(read, decision, now, args.pause_minutes)
        print(describe(decision))
        if decision.action != "deploy":
            break
        if decision.resmoke:
            failed = _resmoke(world, read, decision, version, args.dry_run)
            if failed:
                _mark_failed(world, read, read.rows[failed], version)
                _say("company %s failed its re-smoke; the release is stopped" % failed)
                return 1
        picked = [c for c in decision.companies if not only or c in only]
        if not picked:
            _say("nothing due for %s: ring %s is next" % (", ".join(sorted(only)), decision.ring))
            break
        for cid in picked:
            if not _deploy(world, read, cid, version, args.plant_failure or "", args.dry_run):
                return 1
        if args.dry_run:
            break
        # A resume applies once: the company it names is pending again only until this round redeploys it.
        resume = None
    else:
        _say("the run did not settle in %d rounds" % MAX_ROUNDS)
        return 1
    rc = 1 if decision is not None and decision.action == "stop" else 0
    if read is not None and read.unreachable:
        _say(
            "region unreachable: %s; its companies were not released"
            % ", ".join("%s (%s)" % (r, c) for r, c in sorted(read.unreachable.items()))
        )
        rc = 1
    return rc


# --------------------------------------------------------------------------- the live world


def inline(sql: str, params: Sequence[Any]) -> str:
    """`sql` with each `?` replaced by its parameter as a literal: text single-quoted with quotes doubled, numbers bare, None as NULL. `wrangler d1 execute --command` takes no bound parameters."""
    pieces = sql.split("?")
    if len(pieces) - 1 != len(params):
        msg = "%d placeholders, %d parameters" % (len(pieces) - 1, len(params))
        raise ValueError(msg)
    out = [pieces[0]]
    for value, rest in zip(params, pieces[1:], strict=True):
        if value is None:
            lit = "NULL"
        elif isinstance(value, bool):
            lit = str(int(value))
        elif isinstance(value, int | float):
            lit = str(value)
        else:
            lit = "'%s'" % str(value).replace("'", "''")
        out += [lit, rest]
    return "".join(out)


def d1_rows(text: str) -> list[dict[str, Any]]:
    """The rows of every statement in `wrangler d1 execute --json` output."""
    doc = json.loads(text)
    rows: list[dict[str, Any]] = []
    for part in doc if isinstance(doc, list) else [doc]:
        rows.extend(part.get("results") or [])
    return rows


def d1_query(database: str, sql: str, params: list) -> list[dict]:
    """The production transport: `wrangler d1 execute <database> --remote --json` from a neutral directory. Raises RuntimeError naming the database only, never the statement."""
    argv = [*wrangler_cmd.ARGV, "d1", "execute", database, "--remote", "--json"]
    argv += ["--command", inline(sql, params)]
    with tempfile.TemporaryDirectory(prefix="rings-run-") as tmp:
        try:
            proc = subprocess.run(argv, cwd=tmp, capture_output=True, text=True, check=False)
        except OSError as exc:
            msg = "wrangler d1 execute %s could not run: %s" % (database, exc.strerror)
            raise RuntimeError(msg) from None
    if proc.returncode != 0:
        msg = "wrangler d1 execute %s failed (rc %d)" % (database, proc.returncode)
        raise RuntimeError(msg)
    return d1_rows(proc.stdout)


def edge_record(version: str) -> dict[str, Any] | None:
    """`release-records/v<V>/edge.json` over the public releases origin, or None when absent or unreadable."""
    origin = local.well_known(paths.repo_root()).get("WK_RELEASES_ORIGIN", "")
    if not origin:
        return None
    try:
        proc = subprocess.run(
            ["curl", "-sf", EDGE_RECORD % (origin, version)],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    try:
        doc = json.loads(proc.stdout)
    except ValueError:
        return None
    return doc if isinstance(doc, dict) else None


def live_target(row: CompanyRow) -> console_executor.CompanyTarget:
    """The company's validated target over its generated configs (`workers/{account,proxy}/enterprise.<name>.toml`)."""
    root = paths.repo_root()
    leaf = "enterprise.%s.toml" % row.name
    return console_executor.company_target(
        root,
        name=row.name,
        company_id=row.id,
        region=row.region,
        domain=PRODUCT_DOMAIN,
        account_config=root / "workers" / "account" / leaf,
        proxy_config=root / "workers" / "proxy" / leaf,
        bench=row.bench,
    )


def live_world() -> World:
    root = paths.repo_root()
    return World(
        query=d1_query,
        release_record=edge_record,
        runner=local.default_runner,
        now=lambda: datetime.datetime.now(datetime.UTC),
        root=root,
        out=root / OUT_REL / uuid.uuid4().hex[:12],
        target=live_target,
    )


# --------------------------------------------------------------------------- the lab group (box K2 in rediacc_ci.enterprise.lab)

# `enterprise proof release` (box V5) on bench: no soak, and pauses shortened to a minute that the driver waits out.
PROOF_SOAK_DAYS = 0
PROOF_PAUSE_MINUTES = 1
PROOF_SETTLE_RUNS = 16
FAST = "fast"


def target_version(*, edge: Callable[[], str] | None = None) -> str:
    """The version a proof release rolls out: the one edge runs (`cli/edge/latest.json`), whose edge record the soak reads."""
    return (edge or lab.edge_version)()


def versions(
    targets: Sequence[str],
    *,
    world: World | None = None,
    edge: Callable[[], str] | None = None,
) -> dict[str, str]:
    """`{target: version}` for each bench company id among `targets` (its last `deployed` rollout row, unless a later `failed` row of the same version rolled it back), and `fast` (the version edge runs). A target with no deployed version is absent."""
    w = world or live_world()
    wanted = set(targets)
    history: dict[str, list[str]] = {}
    for region, database in registry.databases(True).items():
        try:
            rows = w.query(database, ROLLOUT_SQL, [])
        except TRANSPORT_ERRORS as exc:
            raise proof.LabError("region %s: %s" % (region, type(exc).__name__)) from None
        for row in rows:
            cid = str(row.get("company_id", ""))
            if cid not in wanted:
                continue
            seen = history.setdefault(cid, [])
            version = str(row.get("version") or "")
            if row.get("status") == "deployed":
                seen.append(version)
            elif row.get("status") == "failed":
                # A failed run rolls the company back: the version it failed on is not what it runs.
                while seen and seen[-1] == version:
                    seen.pop()
    out = {cid: seen[-1] for cid, seen in history.items() if seen}
    if FAST in wanted:
        out[FAST] = target_version(edge=edge)
    return out


def _stopped(world: World, version: str) -> str:
    """The company whose last rollout row of `version` is `failed`: the one a latched stop names."""
    read = read_world(world, version, bench=True, sample=False)
    failed = [c for c, rows in read.rollouts.items() if rows and rows[-1].get("status") == "failed"]
    return failed[-1] if failed else ""


def lab_release(
    *,
    skip_pauses: bool = False,
    order: str = "",
    plant_failure: str = "",
    resume: str = "",
    world: World | None = None,
    version: str | None = None,
    sleep: Callable[[float], None] | None = None,
    pause_minutes: int = PROOF_PAUSE_MINUTES,
) -> proof.ReleaseResult:
    """One bench release as `enterprise proof release` asks for it, as a `proof.ReleaseResult`.

    Each invocation of the runner ends at a `wait` while a shortened pause runs, so the driver sleeps the pause and invokes again until the run ends on anything else (at most `PROOF_SETTLE_RUNS`). `--resume` applies to the first invocation only. A non-zero exit names the company whose last rollout row of the version is `failed`. The runner's own lines are captured, not printed: the proof prints its claims."""
    w = world or live_world()
    v = version or target_version()
    nap = sleep or time.sleep
    base = ["--version", v, "--bench", "--soak-days", str(PROOF_SOAK_DAYS)]
    base += ["--pause-minutes", str(pause_minutes)]
    if order:
        base += ["--order", order]
    if skip_pauses:
        base.append("--skip-pauses")
    if plant_failure:
        base += ["--plant-failure", plant_failure]
    first = [*base, "--resume", v, "--company", resume] if resume else base
    argv = first
    for _ in range(PROOF_SETTLE_RUNS):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = main(argv, world=w)
        lines = [ln for ln in err.getvalue().splitlines() if ln.strip()]
        error = lines[-1] if lines else ""
        if rc == 2:
            return proof.ReleaseResult(rc, "", error or "refused")
        if rc != 0:
            return proof.ReleaseResult(rc, _stopped(w, v), error)
        decided = [ln for ln in out.getvalue().splitlines() if ln and not ln.startswith("would ")]
        if not decided or not decided[-1].startswith("wait"):
            return proof.ReleaseResult(0)
        nap(pause_minutes * 60.0)
        argv = base
    return proof.ReleaseResult(1, "", "the release did not settle in %d runs" % PROOF_SETTLE_RUNS)


def main(argv: list[str], world: World | None = None) -> int:
    args = parse(argv)
    found = refusals(args)
    if found:
        for line in found:
            _say("refused: %s" % line)
        return 2
    if world is None:
        target = console_executor.BENCH_TARGET if args.bench else console_executor.STABLE_TARGET
        profile = console_executor.profile_for(target)
        if console_executor.missing_env() and not console_executor.profile_bound(profile):
            again = console_executor.reexec_argv(profile, argv, module=SELF)
            return subprocess.run(again, check=False, env=dict(os.environ)).returncode
        world = live_world()
    return release(args, world)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
