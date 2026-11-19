"""Feedback triage entry (PLAN-rdc-feedback D5: boxes T1 and T2).

    PYTHONPATH=.ci python3 -m rediacc_ci.feedback.triage run [--region eu|us|asia|bench] [--dry-run] [--status <list>] [--cursor <path>]
        [--no-classify | --replies <dir>] [--me <session-prefix>] [--plans-root <dir>] [--orders <path>] [--critical-state <path>]
    PYTHONPATH=.ci python3 -m rediacc_ci.feedback.triage repro --region <r> --fingerprint <64 hex> --result reproduced|clean|inconclusive
        [--workaround] [--dry-run] [--me <session-prefix>] [--plans-root <dir>] [--orders <path>] [--critical-state <path>]

Without `--region` the three production regions run in turn; `bench` (the eu bench) runs only when named.

RUN, per region:

  1. Open the root session (`client.open_region`); a dry run does not elevate bench.
  2. Export the items seen since the region's cursor with a status in `--status` (default: every open status, so Stage 4 sees the aggregates of fingerprints already screened, confirmed or planned).
  3. Stage 1 (`quarantine.screen`): a `new` or `screening` item that matches a rule is quarantined, its triage note naming the rule and the field; a clean `new` item moves to `screening`. A confirmed or planned fingerprint is never demoted by Stage 1.
  4. Stage 2 (`classify`): each `new` or `screening` survivor with no category yet is classified ALONE inside the fixed wrapper. A reply that is not the schema, or flags the report suspicious, quarantines it; a report that is not meaningful with a low count is rejected; the rest stay `screening` with the category and the classification in the triage note. The model is the messages API with `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN`, or with `--replies <dir>` the files Haiku sub-agents of `/feedback-triage` wrote (a missing reply writes its prompt file and leaves the report for the next run). `--no-classify` stops after Stage 1.
  5. Stage 3: one near-duplicate call over the summaries of the open classified fingerprints records the suspected parent in the child's note; each `meaningful && safe_to_reproduce` report gets a reproduction order, merged into `--orders` (default `.ci/cache/feedback/orders-<region>.json`): an order of this run replaces the one already there for its fingerprint, and the others stay until `repro` records their result.
  6. Stage 4 (`critical`): every R8 trigger the aggregates and Stage 2 show becomes a worklist item deferred with its DEFAULT and a 6 h window, filed under `--me` (without it the run names the triggers and files nothing). A filed trigger is recorded in `--critical-state` and never filed twice.
  7. Stage 5 (`plangen`): each `confirmed` fingerprint with no plan gets `agent/plans/PLAN-feedback-<slug>.md` under `--plans-root` (default the repository) and moves to `planned` with `planRef`.
  8. Write the verdicts in batches and advance the region's cursor to the newest `lastSeenAt` exported, unless a classification is still pending, the classifier was unavailable, `--no-classify` left a `new` or `screening` report unclassified, or `--status` named only some of the open statuses, so the next run sees those reports again. `--dry-run` prints the same lines and writes no verdict, cursor, order, plan or worklist item.

REPRO records the result of a reproduction the agent ran from an order: `reproduced` confirms the fingerprint, `clean` rejects it when its count is low (and is the R8 (c) disagreement when it is high), `inconclusive` leaves it in `screening`. The R8 triggers that need a reproduction ((b) and (e)) are evaluated here, a confirmed fingerprint gets its plan at once, and once the verdict is written the fingerprint's order leaves the orders file.

One line per item names the region, the short fingerprint and the decision; no report field is ever printed.

CREDENTIALS. The run re-executes itself under the Bitwarden profile its regions need (`root-login` for eu, us and asia; `bench-login-eu` for bench) through `rediacc_ci.core.bws_env exec`, unless that profile is already bound; production and bench in one process are refused, because each needs its own profile. Stage 2 over the API reads `ANTHROPIC_CLAUDE_CODE_OAUTH_TOKEN` from the same environment. Nothing secret reaches argv or output.

EXIT. 0 every region done; 1 a failed step in some region (the others still run), a worklist step refused, or a confirmed fingerprint left with no plan (`plangen.PlanError`); 2 a refusal before any request (usage, a missing credential, an unreadable cursor) or a missing classifier token.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rediacc_ci import log, paths
from rediacc_ci.feedback import classify, client, critical, plangen, quarantine
from rediacc_ci.ops import bench_preflight, login_bench

SELF = "rediacc_ci.feedback.triage"
PROFILES_ENV = "REDIACC_BWS_PROFILES"
OPEN_STATUSES = ("new", "screening", "quarantined", "confirmed", "planned")
DEFAULT_STATUSES = OPEN_STATUSES
SCREENABLE = ("new", "screening")
SHORT_FP = 12
ORDERS_PARTS = (".ci", "cache", "feedback")

Runner = Callable[[Sequence[str], Mapping[str, str]], int]


@dataclass
class Options:
    regions: tuple[str, ...]
    dry_run: bool = False
    statuses: tuple[str, ...] = DEFAULT_STATUSES
    cursor: Path | None = None
    classify: bool = False
    replies: Path | None = None
    me: str | None = None
    plans_root: Path | None = None
    orders: Path | None = None
    critical_state: Path | None = None


@dataclass
class ReproOptions:
    region: str
    fingerprint: str
    result: str
    workaround: bool = False
    dry_run: bool = False
    me: str | None = None
    plans_root: Path | None = None
    critical_state: Path | None = None
    orders: Path | None = None


@dataclass
class RegionResult:
    """What one region's run decided: the exported items, the Stage 1 hits, the Stage 2 outcomes, the verdicts and the rest."""

    region: str
    items: list[dict[str, Any]] = field(default_factory=list)
    hits: dict[str, quarantine.Hit] = field(default_factory=dict)
    verdicts: list[dict[str, Any]] = field(default_factory=list)
    survivors: list[dict[str, Any]] = field(default_factory=list)
    outcomes: dict[str, classify.Outcome] = field(default_factory=dict)
    duplicates: dict[str, str] = field(default_factory=dict)
    orders: list[dict[str, Any]] = field(default_factory=list)
    triggers: list[critical.Trigger] = field(default_factory=list)
    filed: list[critical.Filed] = field(default_factory=list)
    plans: list[plangen.Written] = field(default_factory=list)
    plan_errors: list[str] = field(default_factory=list)
    pending: int = 0
    unclassified: int = 0
    unavailable: str | None = None
    unavailable_rc: int = 0
    written: client.VerdictResult | None = None


@dataclass
class Deps:
    """The seams `run` calls through; a test replaces them."""

    open_region: Callable[..., client.Transport] = client.open_region
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    out: Callable[[str], None] = print
    # The classifier: None builds the messages-API client from `env` (or the reply files of `--replies`).
    complete: Callable[[str], str] | None = None
    env: Mapping[str, str] = field(default_factory=lambda: os.environ)
    capture: Callable[[Sequence[str]], tuple[int, str]] = critical._capture


# ---- verdict merging -----------------------------------------------------------------------------


class Verdicts:
    """One verdict per fingerprint, later stages overriding the fields earlier ones set."""

    def __init__(self, initial: Sequence[Mapping[str, Any]] = ()):
        self._by_fp: dict[str, dict[str, Any]] = {}
        for v in initial:
            self.set(v["fingerprint"], **{k: x for k, x in v.items() if k != "fingerprint"})

    def set(self, fp: str, **fields: Any) -> None:
        held = {k: v for k, v in self._by_fp.get(fp, {}).items() if k != "fingerprint"}
        self._by_fp[fp] = client.verdict(fp, **{**held, **fields})

    def get(self, fp: str) -> dict[str, Any]:
        return dict(self._by_fp.get(fp, {}))

    def as_list(self) -> list[dict[str, Any]]:
        return list(self._by_fp.values())


# ---- argv ----------------------------------------------------------------------------------------


def _statuses(text: str) -> tuple[str, ...]:
    statuses = tuple(s for s in text.split(",") if s)
    unknown = [s for s in statuses if s not in client.STATUSES]
    if unknown or not statuses:
        raise client.FeedbackError(
            "--status takes a comma list of %s" % ", ".join(client.STATUSES), rc=2
        )
    return statuses


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=SELF, description="feedback triage")
    sub = parser.add_subparsers(dest="verb", required=True)
    run_p = sub.add_parser(
        "run", help="export, screen, classify, escalate, plan and write verdicts"
    )
    run_p.add_argument("--region", choices=client.REGIONS)
    run_p.add_argument("--dry-run", action="store_true")
    run_p.add_argument("--status", default=",".join(DEFAULT_STATUSES))
    run_p.add_argument("--cursor", type=Path)
    route = run_p.add_mutually_exclusive_group()
    route.add_argument("--no-classify", action="store_true")
    route.add_argument("--replies", type=Path)
    repro_p = sub.add_parser("repro", help="record a reproduction result")
    repro_p.add_argument("--region", choices=client.REGIONS, required=True)
    repro_p.add_argument("--fingerprint", required=True)
    repro_p.add_argument("--result", choices=critical.REPRO_RESULTS, required=True)
    repro_p.add_argument("--workaround", action="store_true")
    repro_p.add_argument("--dry-run", action="store_true")
    for p in (run_p, repro_p):
        p.add_argument("--orders", type=Path)
        p.add_argument("--me")
        p.add_argument("--plans-root", type=Path)
        p.add_argument("--critical-state", type=Path)
    return parser


def _me(value: str | None) -> str | None:
    if value is not None and not plangen.OWNER.match(value):
        msg = "--me %r is not a session prefix" % value
        raise client.FeedbackError(msg, rc=2)
    return value


def parse_any(argv: Sequence[str]) -> Options | ReproOptions:
    parser = _parser()
    try:
        ns = parser.parse_args(list(argv))
    except SystemExit as exc:
        if exc.code == 0:
            # `<verb> --help`: argparse printed the help; the run ends there, successfully.
            raise client.FeedbackError("", rc=0) from exc
        raise client.FeedbackError(parser.format_usage().strip(), rc=2) from exc
    me = _me(ns.me)
    if ns.verb == "repro":
        if not client.FINGERPRINT.match(ns.fingerprint):
            raise client.FeedbackError("--fingerprint takes 64 lowercase hex", rc=2)
        return ReproOptions(
            ns.region,
            ns.fingerprint,
            ns.result,
            ns.workaround,
            ns.dry_run,
            me,
            ns.plans_root,
            ns.critical_state,
            ns.orders,
        )
    regions = (ns.region,) if ns.region else client.PRODUCTION_REGIONS
    return Options(
        regions,
        ns.dry_run,
        _statuses(ns.status),
        ns.cursor,
        classify=not ns.no_classify,
        replies=ns.replies,
        me=me,
        plans_root=ns.plans_root,
        orders=ns.orders,
        critical_state=ns.critical_state,
    )


def parse_args(argv: Sequence[str]) -> Options:
    opts = parse_any(argv)
    if not isinstance(opts, Options):
        raise client.FeedbackError("parse_args reads the run verb only", rc=2)
    return opts


# ---- Stage 1 -------------------------------------------------------------------------------------


def decide(region: str, items: Sequence[dict[str, Any]]) -> RegionResult:
    """Stage 1 over the exported items: a `new` or `screening` hit is quarantined, a clean `new` item moves to `screening`, and every clean item is a survivor. A hit on a fingerprint already confirmed, planned or resolved is recorded and changes nothing."""
    result = RegionResult(region, list(items))
    for item in items:
        fp = item["fingerprint"]
        hit = quarantine.screen(item)
        if hit is not None:
            result.hits[fp] = hit
            if item["status"] in SCREENABLE:
                result.verdicts.append(
                    client.verdict(fp, status="quarantined", triageNote=hit.note)
                )
            continue
        result.survivors.append(item)
        if item["status"] == "new":
            result.verdicts.append(client.verdict(fp, status="screening"))
    return result


# ---- Stage 2 to 5 --------------------------------------------------------------------------------


def _low_count(item: Mapping[str, Any]) -> bool:
    return (
        critical._int(item, "distinctReporters") < critical.HIGH_REPORTERS
        and critical._int(item, "occurrenceCount") < critical.HIGH_OCCURRENCES
    )


def stage2(result: RegionResult, verdicts: Verdicts, complete: Callable[[str], str] | None) -> None:
    """Classify each unclassified `new` or `screening` survivor. An unavailable classifier stops the stage; a pending reply skips only its report."""
    if complete is None:
        return
    for item in result.survivors:
        if item["status"] not in SCREENABLE or item.get("category"):
            continue
        fp = item["fingerprint"]
        try:
            outcome = classify.classify(item, complete)
        except classify.PendingError:
            result.pending += 1
            continue
        except classify.UnavailableError as exc:
            result.unavailable, result.unavailable_rc = str(exc), exc.rc
            return
        result.outcomes[fp] = outcome
        cls = outcome.classification
        if outcome.quarantined or cls is None:
            fields: dict[str, Any] = {
                "status": "quarantined",
                "triageNote": outcome.quarantine_note,
            }
            if cls is not None:
                fields["category"] = cls.category
            verdicts.set(fp, **fields)
            continue
        status = "rejected" if not cls.meaningful and _low_count(item) else "screening"
        extra = "not meaningful, low count" if status == "rejected" else ""
        verdicts.set(
            fp, status=status, category=cls.category, triageNote=classify.note_for(cls, extra)
        )


def _classified(item: Mapping[str, Any], result: RegionResult, verdicts: Verdicts):
    """(classification, extra clauses) for an item: this run's outcome, else its triage note."""
    outcome = result.outcomes.get(item["fingerprint"])
    if outcome is not None:
        if outcome.quarantined or outcome.classification is None:
            return None
        note = verdicts.get(item["fingerprint"]).get("triageNote")
        parsed = classify.classification_from_note(note)
        return parsed or (outcome.classification, [])
    return classify.classification_from_note(item.get("triageNote"))


def _status(item: Mapping[str, Any], verdicts: Verdicts) -> str:
    return verdicts.get(item["fingerprint"]).get("status") or item["status"]


def stage3(result: RegionResult, verdicts: Verdicts, complete: Callable[[str], str] | None) -> None:
    """The near-duplicate pass over open classified fingerprints, and the reproduction orders."""
    entries = []
    for item in result.items:
        if _status(item, verdicts) not in ("screening", "confirmed", "planned"):
            continue
        parsed = _classified(item, result, verdicts)
        if parsed is None:
            continue
        cls, extra = parsed
        entries.append(
            {"fingerprint": item["fingerprint"], "category": cls.category, "summary": cls.summary}
        )
        if item["fingerprint"] in result.outcomes:
            order = classify.reproduction_order(item, cls)
            if order is not None:
                result.orders.append(order)
    # Every exported item was seen since the cursor, so the pass runs on each run with two or more open classified fingerprints, not only on the run that classified them: on the reply-file route the classifications land in one run and the dedup reply in the next, which classifies nothing.
    if complete is None or result.unavailable or result.pending:
        return
    try:
        result.duplicates = classify.near_duplicates(entries, complete)
    except classify.PendingError:
        result.pending += 1
        return
    except classify.UnavailableError as exc:
        result.unavailable, result.unavailable_rc = str(exc), exc.rc
        return
    except classify.ReplyError as exc:
        log.warn("%s: near-duplicate reply ignored (%s)" % (result.region, exc))
        return
    by_fp = {i["fingerprint"]: i for i in result.items}
    for child, parent in result.duplicates.items():
        parsed = _classified(by_fp[child], result, verdicts)
        if parsed is None:
            continue
        cls, extra = parsed
        clause = "near-duplicate of %s" % parent[:SHORT_FP]
        extra = [e for e in extra if not e.startswith("near-duplicate of ")] + [clause]
        note = classify.note_for(cls, *extra)
        if note != (verdicts.get(child).get("triageNote") or by_fp[child].get("triageNote")):
            verdicts.set(child, triageNote=note)


def stage4(
    result: RegionResult,
    opts: Options | ReproOptions,
    deps: Deps,
    now: datetime,
    triggers: Sequence[critical.Trigger],
) -> None:
    """File the triggers not filed before, under `--me`; without it, or on a dry run, name them only."""
    state_file = opts.critical_state or critical.state_path()
    state = critical.read_state(state_file)
    fresh = critical.unfiled(triggers, state)
    result.triggers = list(fresh)
    if not fresh:
        return
    if opts.dry_run or not opts.me:
        for t in fresh:
            deps.out(
                "%s %s critical R8 (%s) not filed (%s)"
                % (
                    result.region,
                    t.fingerprint[:SHORT_FP],
                    t.code,
                    "dry run" if opts.dry_run else "no --me",
                )
            )
        return
    result.filed = critical.file_triggers(fresh, opts.me, now, deps.capture)
    stamp = critical.stamp(now)
    for f in result.filed:
        deps.out(
            "%s %s critical R8 (%s) %s%s"
            % (
                result.region,
                f.trigger.fingerprint[:SHORT_FP],
                f.trigger.code,
                f.note,
                " #%s" % f.item_id if f.item_id else "",
            )
        )
        # An item that exists is filed, deferral or not: a second --add would ask the same question twice (review 23cc895b.4). A refused --defer still fails the run.
        if f.item_id:
            state[f.trigger.key] = stamp
    critical.write_state(state_file, state)


def stage5(
    result: RegionResult,
    verdicts: Verdicts,
    opts: Options | ReproOptions,
    deps: Deps,
    now: datetime,
) -> None:
    """A draft plan for each confirmed fingerprint with no plan; the fingerprint moves to `planned`."""
    root = opts.plans_root or paths.repo_root()
    for item in result.items:
        fp = item["fingerprint"]
        if _status(item, verdicts) != "confirmed" or item.get("planRef"):
            continue
        parsed = _classified(item, result, verdicts)
        if parsed is None:
            deps.out(
                "%s %s confirmed with no classification on record: no plan"
                % (result.region, fp[:SHORT_FP])
            )
            continue
        try:
            written = plangen.write(
                root, item, parsed[0], now, opts.me or plangen.DEFAULT_OWNER, opts.dry_run
            )
        except plangen.PlanError as exc:
            log.error("%s %s: %s" % (result.region, fp[:SHORT_FP], exc))
            result.plan_errors.append(fp)
            continue
        result.plans.append(written)
        verdicts.set(fp, status="planned", planRef=written.name)
        deps.out(
            "%s %s planned %s%s"
            % (result.region, fp[:SHORT_FP], written.rel, "" if written.created else " (existing)")
        )


def _complete_for(opts: Options, deps: Deps) -> Callable[[str], str] | None:
    if not opts.classify:
        return None
    if deps.complete is not None:
        return deps.complete
    if opts.replies is not None:
        return classify.FileReplies(opts.replies)
    return classify.MessagesClient(classify.token_from(deps.env)).complete


def _line(result: RegionResult, item: Mapping[str, Any], verdicts: Verdicts) -> str:
    fp = item["fingerprint"]
    short = fp[:SHORT_FP]
    hit = result.hits.get(fp)
    if hit is not None:
        return "%s %s quarantined rule=%s field=%s" % (result.region, short, hit.rule, hit.field)
    outcome = result.outcomes.get(fp)
    if outcome is not None and outcome.quarantined:
        return "%s %s quarantined stage2%s" % (
            result.region,
            short,
            " suspicious" if outcome.suspicious else " reply-not-schema",
        )
    if outcome is not None and outcome.classification is not None:
        return "%s %s %s category=%s" % (
            result.region,
            short,
            verdicts.get(fp).get("status", item["status"]),
            outcome.classification.category,
        )
    if item["status"] in SCREENABLE:
        return "%s %s screening" % (result.region, short)
    return "%s %s %s" % (result.region, short, item["status"])


def orders_path(opts: Options | ReproOptions, region: str) -> Path:
    return opts.orders or paths.from_root(*ORDERS_PARTS, "orders-%s.json" % region)


def read_orders(path: Path, region: str) -> list[dict[str, Any]]:
    """The orders on file for `region`; an absent, unreadable or other region's file holds none."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(doc, dict) or doc.get("region") != region:
        return []
    orders = doc.get("orders")
    if not isinstance(orders, list):
        return []
    return [o for o in orders if isinstance(o, dict) and isinstance(o.get("fingerprint"), str)]


def _store_orders(
    path: Path, region: str, orders: Sequence[Mapping[str, Any]], ran_at: str
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(
            {"region": region, "ranAt": ran_at, "orders": list(orders)}, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def write_orders(path: Path, region: str, orders: Sequence[Mapping[str, Any]], ran_at: str) -> None:
    """Merge this run's orders into the file: an order replaces the one on file for its fingerprint, and an order not yet reproduced stays (review 23cc895b.5)."""
    fresh = {o["fingerprint"] for o in orders}
    kept = [o for o in read_orders(path, region) if o["fingerprint"] not in fresh]
    _store_orders(path, region, [*kept, *orders], ran_at)


def consume_order(path: Path, region: str, fingerprint: str, ran_at: str) -> bool:
    """Drop the order of a fingerprint whose reproduction is recorded; True when one was on file."""
    on_file = read_orders(path, region)
    left = [o for o in on_file if o["fingerprint"] != fingerprint]
    if len(left) == len(on_file):
        return False
    _store_orders(path, region, left, ran_at)
    return True


def run_region(region: str, opts: Options, cursor: Path, deps: Deps) -> RegionResult:
    rows = client.read_cursor(cursor)
    since = client.cursor_since(rows, region)
    complete = _complete_for(opts, deps)
    transport = deps.open_region(region, not opts.dry_run)
    items = client.export(transport, since, opts.statuses)
    now = deps.now()
    result = decide(region, items)
    verdicts = Verdicts(result.verdicts)
    stage2(result, verdicts, complete)
    if complete is None:
        # `--no-classify`: a survivor still open with no category was never classified, and a cursor moved past it would keep it from every later run (review 23cc895b.1).
        result.unclassified = sum(
            1
            for item in result.survivors
            if _status(item, verdicts) in SCREENABLE and not item.get("category")
        )
    stage3(result, verdicts, complete)
    triggers = []
    for item in items:
        triggers += critical.evaluate(item, now, outcome=result.outcomes.get(item["fingerprint"]))
    stage4(result, opts, deps, now, triggers)
    stage5(result, verdicts, opts, deps, now)
    result.verdicts = verdicts.as_list()
    for item in items:
        deps.out(_line(result, item, verdicts))
    stamp = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    # The cursor is shared by every status, so only an export that covered every open status may move it: a `--status` subset would carry it past reports of the other statuses that the next default run then never sees (review 53b0c35b.1).
    subset = not set(OPEN_STATUSES) <= set(opts.statuses)
    held = result.pending or result.unavailable or result.unclassified or subset
    tail = ""
    if subset:
        tail += ", --status is a subset of the open statuses"
    if result.pending:
        tail += ", %d classification(s) pending in %s" % (result.pending, opts.replies)
    if result.unavailable:
        tail += ", classifier unavailable: %s" % result.unavailable
    if result.unclassified:
        tail += ", %d report(s) left unclassified by --no-classify" % result.unclassified
    if result.plan_errors:
        tail += ", %d confirmed fingerprint(s) with no plan" % len(result.plan_errors)
    if opts.dry_run:
        deps.out(
            "%s dry run: %d item(s), %d quarantined, %d verdict(s), %d order(s), %d plan(s) not written, cursor not advanced%s"
            % (
                region,
                len(items),
                len(result.hits),
                len(result.verdicts),
                len(result.orders),
                len(result.plans),
                tail,
            )
        )
        return result
    if result.verdicts:
        result.written = client.write_verdicts(transport, result.verdicts)
    if result.orders:
        write_orders(orders_path(opts, region), region, result.orders, stamp)
    if not held:
        client.write_cursor(cursor, region, client.next_since(items, since), stamp)
    written = result.written or client.VerdictResult()
    deps.out(
        "%s %d item(s), %d quarantined, %d verdict(s) written over %d report(s)%s, %d order(s), %d plan(s)%s%s"
        % (
            region,
            len(items),
            len(result.hits),
            written.fingerprints,
            written.reports,
            ", %d missing" % len(written.missing) if written.missing else "",
            len(result.orders),
            len(result.plans),
            tail,
            ", cursor held" if held else "",
        )
    )
    return result


def run(opts: Options, deps: Deps | None = None) -> tuple[int, list[RegionResult]]:
    """Every region of `opts` in turn; a region's failure is reported and the next region still runs. Returns the worst exit status and the per-region results."""
    deps = deps or Deps()
    cursor = opts.cursor or client.cursor_path()
    rc = 0
    results: list[RegionResult] = []
    for region in opts.regions:
        try:
            result = run_region(region, opts, cursor, deps)
        except client.FeedbackError as exc:
            log.error("%s: %s" % (region, exc))
            rc = max(rc, exc.rc)
            continue
        except classify.UnavailableError as exc:
            log.error("%s: %s" % (region, exc))
            rc = max(rc, exc.rc)
            continue
        results.append(result)
        if result.unavailable:
            log.error("%s: %s" % (region, result.unavailable))
            rc = max(rc, result.unavailable_rc or 1)
        rc = max(rc, *(1 for f in result.filed if not f.ok), 0)
        if result.plan_errors:
            rc = max(rc, 1)
    return rc, results


# ---- repro ---------------------------------------------------------------------------------------


def repro(opts: ReproOptions, deps: Deps | None = None) -> tuple[int, RegionResult | None]:
    """Record one reproduction result (module docstring, REPRO)."""
    deps = deps or Deps()
    try:
        transport = deps.open_region(opts.region, not opts.dry_run)
        items = client.export(transport, None, OPEN_STATUSES)
    except client.FeedbackError as exc:
        log.error("%s: %s" % (opts.region, exc))
        return exc.rc, None
    item = next((i for i in items if i["fingerprint"] == opts.fingerprint), None)
    short = opts.fingerprint[:SHORT_FP]
    if item is None:
        log.error("%s: %s is not an open fingerprint" % (opts.region, short))
        return 1, None
    if item["status"] == "quarantined":
        log.error(
            "%s: %s is quarantined; a quarantined report is never reproduced" % (opts.region, short)
        )
        return 2, None
    parsed = classify.classification_from_note(item.get("triageNote"))
    if parsed is None:
        log.error("%s: %s carries no classification; run the triage first" % (opts.region, short))
        return 2, None
    cls, extra = parsed
    now = deps.now()
    result = RegionResult(opts.region, [item])
    verdicts = Verdicts()
    extra = [e for e in extra if not e.startswith("repro ")]
    if opts.result == "reproduced":
        status = (
            "confirmed" if item["status"] in ("new", "screening", "rejected") else item["status"]
        )
        clause = "repro reproduced%s" % (", workaround found" if opts.workaround else "")
    elif opts.result == "clean" and _low_count(item):
        status, clause = "rejected", "repro clean, low count"
    else:
        status, clause = (
            item["status"] if item["status"] != "new" else "screening",
            "repro %s" % opts.result,
        )
    verdicts.set(
        item["fingerprint"], status=status, triageNote=classify.note_for(cls, *extra, clause)
    )
    triggers = critical.evaluate(
        item, now, repro=opts.result, workaround=opts.workaround, category=cls.category
    )
    triggers = [t for t in triggers if t.code in ("b", "c", "e")]
    stage4(result, opts, deps, now, triggers)
    stage5(result, verdicts, opts, deps, now)
    result.verdicts = verdicts.as_list()
    final = verdicts.get(item["fingerprint"]).get("status")
    deps.out("%s %s %s (%s)" % (opts.region, short, final, clause))
    if opts.dry_run:
        deps.out("%s dry run: verdict not written" % opts.region)
        return 0, result
    try:
        result.written = client.write_verdicts(transport, result.verdicts)
    except client.FeedbackError as exc:
        log.error("%s: %s" % (opts.region, exc))
        return exc.rc, result
    consume_order(
        orders_path(opts, opts.region), opts.region, item["fingerprint"], critical.stamp(now)
    )
    failed = any(not f.ok for f in result.filed) or result.plan_errors
    return (1 if failed else 0), result


# ---- credentials and entry -----------------------------------------------------------------------


def required_profile(regions: Sequence[str]) -> str:
    """The one Bitwarden profile the regions need; production and bench together are refused."""
    profiles = {client.profile_for(r) for r in regions}
    if len(profiles) != 1:
        raise client.FeedbackError(
            "production regions and bench need different Bitwarden profiles: run them separately",
            rc=2,
        )
    return profiles.pop()


def _subprocess_runner(argv: Sequence[str], env: Mapping[str, str]) -> int:
    return subprocess.run(list(argv), env=dict(env), check=False).returncode


def reexec_under_profile(
    argv: Sequence[str],
    profile: str,
    env: Mapping[str, str],
    run_child: Runner,
    module: str = SELF,
) -> int | None:
    """The entry point `module` (default this one; `link` and `ship` pass their own) under `profile`; None when it is already bound. A foreign bench login profile is refused, since `bws_env exec` never overwrites a name already set."""
    bound = [p for p in (env.get(PROFILES_ENV) or "").split(",") if p]
    if profile in bound:
        return None
    foreign = bench_preflight.foreign_profiles(login_bench.PROFILE_ROLE, client.BENCH_REGION, bound)
    if foreign:
        raise client.FeedbackError(
            "refusing to run under %s: that profile binds another bench's credentials; run from "
            "an unbound shell" % ", ".join(foreign),
            rc=2,
        )
    child = dict(env)
    ci = str(paths.repo_root() / ".ci")
    child["PYTHONPATH"] = ci + (os.pathsep + child["PYTHONPATH"] if child.get("PYTHONPATH") else "")
    return run_child(
        [
            sys.executable,
            "-m",
            "rediacc_ci.core.bws_env",
            "exec",
            "--profile",
            profile,
            "--",
            sys.executable,
            "-m",
            module,
            *argv,
        ],
        child,
    )


def main(
    argv: Sequence[str] | None = None,
    run_child: Runner = _subprocess_runner,
    deps: Deps | None = None,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print((__doc__ or "").strip())
        return 0
    try:
        opts = parse_any(args)
        regions = opts.regions if isinstance(opts, Options) else (opts.region,)
        profile = required_profile(regions)
        rebound = reexec_under_profile(args, profile, os.environ, run_child)
        if rebound is not None:
            return rebound
    except client.FeedbackError as exc:
        if exc.rc:
            log.error(str(exc))
        return exc.rc
    if isinstance(opts, ReproOptions):
        rc, _ = repro(opts, deps)
        return rc
    rc, _ = run(opts, deps)
    return rc


if __name__ == "__main__":
    sys.exit(main())
