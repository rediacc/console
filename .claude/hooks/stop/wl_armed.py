"""wl_armed: armed actions, a held item's trigger (`when`) and the prepared action (`run` brief or `cmd` line) that starts once the trigger fires (agent/plans/PLAN-armed-actions.md, Design 1-3).

THE STORE IS THE ONLY TRUTH. Four events ride the worklist store (`wl_store.arm_item`, `armfire_item`, `armstart_item`, `disarm_item`), and `wl_store._fold_events` keeps `rec["arm"]`. This module holds the token grammar, the arm-time validation (`parse_when`), the stop-time evaluator (`evaluate`), the cover rule the nagging checks stand down on (`covers`), and `sweep`, which evaluates every unfired arm of a session and appends the latch.

WHAT FIRES. Event tokens (NOT-BEFORE, REPORTED, EXIT, CI-QUICK:done, VM-CHECK:done) compare their artifact against the arm stamp, so an artifact older than the arm never fires it. DEFER-CLOSED and TICKED are judged from the item's current state and BOX from HEAD's plan text, not against the arm stamp. State tokens (CI-QUICK:verified, VM-CHECK:verified, BENCH:deployed, PUSHED:head) are judged live with the push guards' readers. An arm fires on the first evaluation at which every token holds at once; the hook then appends one `armfire` and the latch alone decides from then on.

Every file or git reader that cannot judge says why in its evidence and holds the token unfired: a reader failure never fires an arm, and it never reads as a silent no either. The three bool readers (VM-CHECK:verified, BENCH:deployed, PUSHED:head) answer yes or no with fixed evidence: a failure holds the token unfired, but the evidence does not name its cause.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import os
import pathlib
import re
import subprocess
from typing import TYPE_CHECKING, Any

import wl_core as C

if TYPE_CHECKING:
    from collections.abc import Callable

# The verdicts an `armfire` latch carries. An unlatched arm has verdict "".
FIRED = "fired"
EXPIRED = "expired"
VOID = "void"
VERDICTS = (FIRED, EXPIRED, VOID)
# What evaluate() answers for an arm whose trigger has not fired and whose expiry has not come.
ARMED = "armed"

# Expiry: arm stamp + 24 h for an event arm, the latest NOT-BEFORE + 24 h for a time arm; `--expires +<h>` may set up to 168 h past the arm stamp.
DEFAULT_EXPIRY_H = 24
MAX_EXPIRY_H = 168

# The item states that make an arm inert (Design 1): a done or tombstoned item has nothing left to start.
INERT_STATES = ("x", "~")

TOKEN_RE = re.compile(r"^([A-Z][A-Z-]*):(\S+)$")
KINDS = (
    "NOT-BEFORE",
    "REPORTED",
    "EXIT",
    "CI-QUICK",
    "VM-CHECK",
    "BENCH",
    "PUSHED",
    "NEEDS",
    "DEFER-CLOSED",
    "TICKED",
    "BOX",
)
# The fixed-value kinds and the one value each accepts.
FIXED_VALUES = {
    "CI-QUICK": ("done", "verified"),
    "VM-CHECK": ("done", "verified"),
    "BENCH": ("deployed",),
    "PUSHED": ("head",),
}
# NEEDS:<value> is sugar resolved at arm time to the token that reads the same fact (wl_plandeps.NEEDS_VALUES; `none` waits on nothing and is refused).
NEEDS_SUGAR = {
    "bench-deploy": "BENCH:deployed",
    "verified-vmcheck": "VM-CHECK:verified",
    "pushed-head": "PUSHED:head",
}
# Tokens judged live at each evaluation rather than against the arm stamp.
STATE_TOKENS = ("CI-QUICK:verified", "VM-CHECK:verified", "BENCH:deployed", "PUSHED:head")

ITEM_REF_RE = re.compile(r"^#([0-9a-f]{6,16})$")
AGENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{2,80}$")
TASK_RE = re.compile(r"^[A-Za-z0-9_-]{3,64}$")
BOX_RE = re.compile(r"^([A-Za-z0-9._/-]+\.md)#([0-9a-f]{8})$")
LEASE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

PREPUSH_RECEIPT_REL = (".ci", "cache", "prepush-receipt.json")
RECEIPT_ARCHIVE_REL = (".ci", "cache", "receipts")
_TREE_RE = re.compile(r"^[0-9a-f]{40}([0-9a-f]{24})?$")
_FRACTION_RE = re.compile(r"\.\d+Z$")
_TASK_OUTPUT = re.compile(r"/tasks/([A-Za-z0-9_-]+)\.output$")
GIT_TIMEOUT_S = 20


class TokenError(ValueError):
    """A `--when` token refused at arm time; the message names the token and the reason."""


# ---------------------------------------------------------------------------- stamps


def parse_instant(stamp) -> datetime.datetime | None:
    """A UTC datetime from an ISO8601Z stamp, with or without seconds or a fraction (receipts write milliseconds, the store writes seconds); None for anything else."""
    text = str(stamp or "")
    if _FRACTION_RE.search(text):
        text = _FRACTION_RE.sub("Z", text)
    return C.parse_stamp(text)


def stamp(when: datetime.datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def arm_id(item_id: str, at: str, when: list[str]) -> str:
    """8 hex of sha256 over the item id, the arm stamp and the tokens: every re-arm is a new generation, so an event naming an older `aid` is ignored by the fold."""
    canon = "%s\n%s\n%s" % (item_id, at, json.dumps(list(when), separators=(",", ":")))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()[:8]


def brief_sha(path) -> str:
    """12 hex of sha256 over the brief's bytes; raises OSError when it cannot be read."""
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()[:12]


def default_expiry(at: datetime.datetime, when: list[str]) -> datetime.datetime:
    """Design 3: the latest NOT-BEFORE + 24 h for a time arm, else the arm stamp + 24 h."""
    parsed = [parse_instant(t.split(":", 1)[1]) for t in when if t.startswith("NOT-BEFORE:")]
    instants = [i for i in parsed if i is not None]
    base = max(instants) if instants else at
    return base + datetime.timedelta(hours=DEFAULT_EXPIRY_H)


# ---------------------------------------------------------------------------- the arm record


def live_arm(rec) -> dict | None:
    """The item's arm while it can still block or cover: present, not started, and the item neither done nor tombstoned. None otherwise."""
    if not isinstance(rec, dict):
        return None
    arm = rec.get("arm")
    if not isinstance(arm, dict) or not arm.get("aid"):
        return None
    if arm.get("started_at") or rec.get("state") in INERT_STATES:
        return None
    return arm


def due(arm) -> bool:
    """True when the arm is latched (fired, expired or void) and not yet started: `armed-action-due` blocks on it."""
    return bool(arm) and arm.get("verdict") in VERDICTS and not arm.get("started_at")


def covers(arm, now: datetime.datetime, armed_blocks: bool) -> bool:
    """Whether the arm makes its item's (and its lease's) hold legitimate right now (Design 6).

    Unfired and before its expiry: covered. Fired and not started: covered only while `armed-action-due` blocks at the current effort level (`armed_blocks`), so exactly one check blocks on the item at every level. Expired, void, started, disarmed, or unfired past its expiry: not covered, so the check that nags on the hold blocks again."""
    if not isinstance(arm, dict) or not arm.get("aid") or arm.get("started_at"):
        return False
    verdict = arm.get("verdict") or ""
    if not verdict:
        exp = parse_instant(arm.get("exp"))
        return exp is not None and now < exp
    if verdict == FIRED:
        return bool(armed_blocks)
    return False


def session_arms(items, session_id) -> list[tuple[dict, dict]]:
    """[(rec, arm)] for every item this session owns that carries a live arm, in item order."""
    out = []
    for rec in items or []:
        arm = live_arm(rec)
        if arm is not None and C.owned_by_me(rec.get("owner"), session_id):
            out.append((rec, arm))
    return out


# ---------------------------------------------------------------------------- arm-time validation


@dataclasses.dataclass
class ArmWorld:
    """What `parse_when` reads at arm time. Each field may be None when its source could not be read; a token that needs a None source is refused with that reason."""

    root: pathlib.Path
    now: datetime.datetime
    by_id: dict
    # Task ids the last Stop event listed running; None when the last-event file cannot be read.
    running: set | None = None
    # Agent ids with a meta in this session's subagents directory; None when the directory cannot be located.
    agents: set | None = None
    # Why `running` / `agents` is None, quoted in the refusal.
    running_why: str = ""
    agents_why: str = ""
    # `git show HEAD:<plan>` text, injectable for tests.
    show_head: Callable[[str], str | None] | None = None


def parse_token(raw: str) -> tuple[str, str]:
    """(kind, value) for one token, syntax only; TokenError naming the problem otherwise."""
    m = TOKEN_RE.match(str(raw or "").strip())
    if not m or m.group(1) not in KINDS:
        raise TokenError(
            "%r is not a trigger token; the kinds are %s, each as KIND:<value>"
            % (raw, ", ".join(KINDS))
        )
    return m.group(1), m.group(2)


def _item_ref(kind, value, by_id):
    m = ITEM_REF_RE.match(value)
    if not m:
        raise TokenError("%s:%s does not name an item as #<id>" % (kind, value))
    rid = m.group(1)
    rec = by_id.get(rid)
    if rec is None:
        hits = [r for k, r in by_id.items() if k.startswith(rid)]
        if len(hits) == 1:
            rec = hits[0]
        elif len(hits) > 1:
            raise TokenError("%s:%s is ambiguous; it prefixes %d items" % (kind, value, len(hits)))
    if rec is None:
        raise TokenError("%s:%s names no item in the store" % (kind, value))
    return rec


def parse_when(tokens, world: ArmWorld) -> list[str]:
    """The validated, resolved token list for an arm; TokenError on the first refusal (Design 2).

    Resolution: `NEEDS:<value>` becomes the token reading the same fact, `REPORTED:#<item>` becomes `REPORTED:<the item's lease worker>`, and an item reference is stored with the item's full id."""
    if not tokens:
        raise TokenError("an arm needs at least one --when token")
    out: list[str] = []
    for raw in tokens:
        kind, value = parse_token(raw)
        if kind == "NOT-BEFORE":
            m = C.NOT_BEFORE.fullmatch("NOT-BEFORE:" + value)
            when = parse_instant(value) if m else None
            if when is None:
                raise TokenError("NOT-BEFORE:%s is not a YYYY-MM-DDTHH:MM[:SS]Z instant" % value)
            if when <= world.now:
                raise TokenError(
                    "NOT-BEFORE:%s is not in the future (now %s); a held start whose instant has passed starts now"
                    % (value, stamp(world.now))
                )
            cap = world.now + datetime.timedelta(days=C.NOT_BEFORE_MAX_DAYS)
            if when > cap:
                raise TokenError(
                    "NOT-BEFORE:%s is more than %d days past the arm (cap %s, wl_core.NOT_BEFORE_MAX_DAYS)"
                    % (value, C.NOT_BEFORE_MAX_DAYS, stamp(cap))
                )
            out.append("NOT-BEFORE:%s" % value)
        elif kind == "REPORTED":
            if value.startswith("#"):
                rec = _item_ref(kind, value, world.by_id)
                agent = str(rec.get("worker") or "")
                if not agent:
                    raise TokenError(
                        "REPORTED:%s names #%s, which no worker holds a lease on"
                        % (value, rec["id"])
                    )
            else:
                agent = value
            if not AGENT_RE.match(agent):
                raise TokenError("REPORTED:%s is not an agent id" % agent)
            if world.agents is None:
                raise TokenError(
                    "REPORTED:%s cannot be checked: this session's agent metas are unreadable (%s)"
                    % (agent, world.agents_why or "no subagents directory")
                )
            if agent not in world.agents:
                raise TokenError(
                    "REPORTED:%s names an agent with no meta in this session; pass the agent id the spawn returned"
                    % agent
                )
            out.append("REPORTED:%s" % agent)
        elif kind == "EXIT":
            if not TASK_RE.match(value):
                raise TokenError("EXIT:%s is not a background task id" % value)
            if world.running is None:
                raise TokenError(
                    "EXIT:%s cannot be checked: the last Stop event is unreadable (%s)"
                    % (value, world.running_why or "no last-event file")
                )
            if value not in world.running:
                raise TokenError(
                    "EXIT:%s is not listed running in the last Stop event (running: %s)"
                    % (value, ", ".join(sorted(world.running)) or "none")
                )
            out.append("EXIT:%s" % value)
        elif kind in FIXED_VALUES:
            if value not in FIXED_VALUES[kind]:
                raise TokenError(
                    "%s:%s is not one of %s"
                    % (kind, value, ", ".join("%s:%s" % (kind, v) for v in FIXED_VALUES[kind]))
                )
            out.append("%s:%s" % (kind, value))
        elif kind == "NEEDS":
            if value == "none":
                raise TokenError("NEEDS:none waits on nothing; start the work instead of arming it")
            if value not in NEEDS_SUGAR:
                raise TokenError(
                    "NEEDS:%s is not one of %s" % (value, ", ".join(sorted(NEEDS_SUGAR)))
                )
            out.append(NEEDS_SUGAR[value])
        elif kind == "DEFER-CLOSED":
            rec = _item_ref(kind, value, world.by_id)
            if rec.get("state") != "?":
                raise TokenError(
                    "DEFER-CLOSED:%s names #%s, which is [%s], not a [?] deferral"
                    % (value, rec["id"], rec.get("state"))
                )
            if not C.DEFAULT_TOKEN.search(str(rec.get("line") or rec.get("text") or "")):
                raise TokenError(
                    "DEFER-CLOSED:%s names #%s, a [?] with no DEFAULT:, whose window never closes"
                    % (value, rec["id"])
                )
            out.append("DEFER-CLOSED:#%s" % rec["id"])
        elif kind == "TICKED":
            rec = _item_ref(kind, value, world.by_id)
            if rec.get("state") == "x":
                raise TokenError(
                    "TICKED:%s names #%s, which is already ticked; start the work now"
                    % (value, rec["id"])
                )
            out.append("TICKED:#%s" % rec["id"])
        elif kind == "BOX":
            m = BOX_RE.match(value)
            if not m:
                raise TokenError("BOX:%s is not <plan-path>#<sig8>" % value)
            plan, sig = m.group(1), m.group(2)
            text = (world.show_head or (lambda p: show_head(world.root, p)))(plan)
            if text is None:
                raise TokenError("BOX:%s: %s is not in the commit HEAD names" % (value, plan))
            state = box_state(text, sig)
            if state != "open":
                raise TokenError(
                    "BOX:%s: sig %s is %s in HEAD's %s; only an open box can be armed on"
                    % (value, sig, "ticked" if state == "done" else "absent", plan)
                )
            out.append("BOX:%s#%s" % (plan, sig))
    if len(set(out)) != len(out):
        raise TokenError("the --when tokens repeat one condition: %s" % ", ".join(out))
    return out


# ---------------------------------------------------------------------------- readers


def _git(root, *args) -> tuple[int, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        done = subprocess.run(
            ["git", "-C", str(root), *args],
            env=env,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "%s: %s" % (type(exc).__name__, exc)
    return done.returncode, done.stdout if done.returncode == 0 else done.stderr.strip()


def show_head(root, plan) -> str | None:
    """The plan's text in the commit HEAD names, or None when git cannot show it."""
    rc, out = _git(root, "show", "HEAD:%s" % plan)
    return out if rc == 0 else None


def box_state(text: str, sig: str) -> str:
    """'open' | 'done' | 'absent' for the sig in a plan's text, through the real box parser."""
    import wl_planrec as PR

    if any(s == sig for _i, _l, _b, s in PR.open_boxes(text)):
        return "open"
    if any(s == sig for _i, _l, _b, s in PR.done_boxes(text)):
        return "done"
    return "absent"


def receipt_vouches_for_tree(receipt, tree) -> bool:
    """True when the receipt's `headTree` is `tree`, or its `advances` chain reaches `tree` from it (the shape `block_unverified_push.advance_chain` walks; the push guard verifies each step at push time)."""
    if not isinstance(receipt, dict) or not isinstance(receipt.get("headTree"), str):
        return False
    reached = {receipt["headTree"]}
    steps = receipt.get("advances")
    for step in steps if isinstance(steps, list) else []:
        if (
            isinstance(step, dict)
            and isinstance(step.get("from"), str)
            and step["from"] in reached
            and isinstance(step.get("to"), str)
        ):
            reached.add(step["to"])
    return tree in reached


def receipt_green_for_head(root) -> tuple[bool, str]:
    """(green, evidence): a whole, green ci:quick receipt speaks for HEAD's tree, read the way the push guard reads it: the archive `.ci/cache/receipts/<HEAD^{tree}>.json` first (when it exists but does not name that tree as a whole run the answer is False at once, and the latest receipt is not consulted), then `.ci/cache/prepush-receipt.json`; `exitCode` must be the int 0 and `headTree` (or its `advances` chain) must reach HEAD's tree. Whether HEAD is pushed is not read here."""
    rc, tree = _git(root, "rev-parse", "HEAD^{tree}")
    tree = tree.strip()
    if rc or not _TREE_RE.match(tree):
        return False, "HEAD's tree is unreadable (%s)" % (tree[:80] or "git failed")
    archive = pathlib.Path(root).joinpath(*RECEIPT_ARCHIVE_REL) / ("%s.json" % tree)
    latest = pathlib.Path(root).joinpath(*PREPUSH_RECEIPT_REL)
    receipt, where = None, ""
    for path in (archive, latest):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, ValueError) as exc:
            return False, "%s is unreadable (%s)" % (path.name, type(exc).__name__)
        if path == archive and not (
            isinstance(doc, dict) and doc.get("headTree") == tree and doc.get("whole") is True
        ):
            return False, "the archive receipt for tree %s is not a whole run of that tree" % tree[
                :12
            ]
        receipt, where = doc, path.name
        break
    if receipt is None:
        return False, "no ci:quick receipt exists"
    code = receipt.get("exitCode") if isinstance(receipt, dict) else None
    if type(code) is not int or code != 0:
        return False, "%s exitCode=%r" % (where, code)
    if not receipt_vouches_for_tree(receipt, tree):
        return False, "%s headTree=%s does not reach HEAD's tree %s" % (
            where,
            str(receipt.get("headTree"))[:12],
            tree[:12],
        )
    return True, "%s exitCode=0 vouches for HEAD's tree %s" % (where, tree[:12])


def read_json(path) -> tuple[Any, str]:
    """(document, "") or (None, why)."""
    try:
        return json.loads(pathlib.Path(path).read_text(encoding="utf-8")), ""
    except FileNotFoundError:
        return None, "%s is absent" % pathlib.Path(path).name
    except (OSError, ValueError) as exc:
        return None, "%s is unreadable (%s)" % (pathlib.Path(path).name, type(exc).__name__)


def vm_latest(root) -> tuple[dict | None, str]:
    """(the latest vm:check receipt passing `vm_tier.validate`, "") or (None, why)."""
    import wl_boxready as BR

    try:
        _surfaces, vm_tier = BR.proof_modules()
    except ImportError as exc:
        return None, "the vm:check receipt module cannot load (%s)" % exc
    path = vm_tier.receipt_dir(pathlib.Path(root)) / vm_tier.LATEST
    doc, why = read_json(path)
    if doc is None:
        return None, why
    errors = vm_tier.validate(doc)
    if errors:
        return None, "%s fails vm_tier.validate (%s)" % (path.name, "; ".join(errors[:2]))
    return doc, ""


def proc_task_ids(proc="/proc") -> set:
    """Background task ids some live pid writes `tasks/<id>.output` to (fd 1 or 2). An unreadable /proc answers the empty set, which never alone fires an EXIT token: the Stop event's own running list must also have dropped the task."""
    out: set[str] = set()
    try:
        pids = [d.name for d in pathlib.Path(proc).iterdir() if d.name.isdigit()]
    except OSError:
        return out
    for pid in pids:
        for fd in (1, 2):
            try:
                target = os.readlink("%s/%s/fd/%d" % (proc, pid, fd))
            except OSError:
                continue
            m = _TASK_OUTPUT.search(target)
            if m:
                out.add(m.group(1))
    return out


# ---------------------------------------------------------------------------- stop-time evaluation


@dataclasses.dataclass
class Ctx:
    """What `evaluate` reads at a stop. Every reader is a callable so a stop pays only for the tokens its arms carry; `make_ctx` builds the real ones and tests replace any of them."""

    root: pathlib.Path
    now: datetime.datetime
    by_id: dict
    # Task ids the CURRENT Stop event lists running; None when the event carries no list.
    running: set | None = None
    # {aid: [task id, ...]} the hook saw running at a stop after the arm (`note_running`).
    seen: dict = dataclasses.field(default_factory=dict)
    reports: Callable[[], list] = list
    proc_tasks: Callable[[], set] = set
    ci_latest: Callable[[], tuple[Any, str]] = lambda: (None, "unread")
    ci_green: Callable[[], tuple[bool, str]] = lambda: (False, "unread")
    vm_latest: Callable[[], tuple[dict | None, str]] = lambda: (None, "unread")
    vm_verified: Callable[[], bool] = lambda: False
    bench: Callable[[], bool] = lambda: False
    pushed: Callable[[], bool] = lambda: False
    show_head: Callable[[str], str | None] = lambda _plan: None
    defer_window_min: int = 120


def _cached(fn):
    """A zero-argument reader run at most once."""
    box: list = []

    def inner():
        if not box:
            box.append(fn())
        return box[0]

    return inner


def make_ctx(root, fold, event=None, seen=None, now=None) -> Ctx:
    """The real readers against the checkout at `root`, each run at most once per stop."""
    import wl_boxready as BR
    import wl_report as RPT
    import wl_store as S

    root = pathlib.Path(root)
    running = None
    if isinstance(event, dict) and isinstance(event.get("background_tasks"), list):
        running = {
            str(b.get("id") or "")
            for b in event["background_tasks"]
            if isinstance(b, dict) and b.get("status") == "running"
        }

    def reports():
        return RPT.read_index(RPT.store_root(root))

    return Ctx(
        root=root,
        now=now or C.utcnow(),
        by_id=dict(getattr(fold, "by_id", {}) or {}),
        running=running,
        seen=seen if seen is not None else {},
        reports=_cached(reports),
        proc_tasks=_cached(proc_task_ids),
        ci_latest=_cached(lambda: read_json(root.joinpath(*PREPUSH_RECEIPT_REL))),
        ci_green=_cached(lambda: receipt_green_for_head(root)),
        vm_latest=_cached(lambda: vm_latest(root)),
        vm_verified=_cached(lambda: BR.vmcheck_admits(root)),
        bench=_cached(lambda: BR.bench_at_branch(root)),
        pushed=_cached(lambda: BR.head_pushed(root)),
        show_head=lambda plan: show_head(root, plan),
        defer_window_min=S.DEFER_WINDOW_MIN,
    )


HELD, HOLDS, VOIDED = "held", "holds", "void"


def _after(stamp_text, base) -> bool:
    when = parse_instant(stamp_text)
    return when is not None and base is not None and when > base


def judge_token(token: str, arm: dict, ctx: Ctx) -> tuple[str, str]:
    """(HELD | HOLDS | VOIDED, evidence) for one token of one arm at this stop."""
    kind, _, value = token.partition(":")
    at = parse_instant(arm.get("at"))
    if kind == "NOT-BEFORE":
        when = parse_instant(value)
        if when is None:
            return HELD, "%s: the instant does not parse" % token
        if ctx.now >= when:
            return HOLDS, "%s: now %s is at or past it" % (token, stamp(ctx.now))
        return HELD, "%s: now %s is before it" % (token, stamp(ctx.now))
    if kind == "REPORTED":
        import wl_report as RPT

        rid = RPT.short_id(value)
        rows = [
            r
            for r in ctx.reports()
            if (str(r.get("id")) == rid or str(r.get("id")).startswith(rid + "-"))
            and r.get("src") == "hook"
        ]
        newer = [r for r in rows if _after(r.get("at"), at)]
        if newer:
            r = newer[-1]
            return HOLDS, "%s: report %s captured by the hook at %s, after the arm at %s" % (
                token,
                r.get("id"),
                r.get("at"),
                arm.get("at"),
            )
        if rows:
            return HELD, "%s: the newest hook report (%s at %s) predates the arm at %s" % (
                token,
                rows[-1].get("id"),
                rows[-1].get("at"),
                arm.get("at"),
            )
        return HELD, "%s: no hook-captured report names the agent" % token
    if kind == "EXIT":
        if ctx.running is None:
            return HELD, "%s: this stop's event lists no background tasks" % token
        if value in ctx.running:
            return HELD, "%s: the Stop event still lists the task running" % token
        if value not in (ctx.seen.get(arm.get("aid")) or []):
            return HELD, (
                "%s: the task was never seen running at a stop after the arm, so its absence proves no exit"
                % token
            )
        if value in ctx.proc_tasks():
            return HELD, "%s: a live process still writes tasks/%s.output" % (token, value)
        return HOLDS, (
            "%s: seen running after the arm, now absent from the Stop event, and no process writes tasks/%s.output"
            % (token, value)
        )
    if (kind, value) == ("CI-QUICK", "done"):
        doc, why = ctx.ci_latest()
        if not isinstance(doc, dict):
            return HELD, "%s: %s" % (token, why or "the receipt is not an object")
        fin, code = doc.get("finishedAt"), doc.get("exitCode")
        if doc.get("whole") is not True or type(code) is not int:
            return (
                HELD,
                "%s: prepush-receipt.json whole=%r exitCode=%r is not a finished whole run"
                % (
                    token,
                    doc.get("whole"),
                    code,
                ),
            )
        if not _after(fin, at):
            return HELD, "%s: prepush-receipt.json finishedAt=%s is not after the arm at %s" % (
                token,
                fin,
                arm.get("at"),
            )
        return (
            HOLDS,
            "%s: prepush-receipt.json finishedAt=%s exitCode=%d whole=True, after the arm at %s"
            % (
                token,
                fin,
                code,
                arm.get("at"),
            ),
        )
    if (kind, value) == ("CI-QUICK", "verified"):
        ok, why = ctx.ci_green()
        return (HOLDS if ok else HELD), "%s: %s" % (token, why)
    if (kind, value) == ("VM-CHECK", "done"):
        doc, why = ctx.vm_latest()
        if doc is None:
            return HELD, "%s: %s" % (token, why)
        fin = doc.get("finishedAt")
        if not _after(fin, at):
            return HELD, "%s: vm-check receipt.json finishedAt=%s is not after the arm at %s" % (
                token,
                fin,
                arm.get("at"),
            )
        return HOLDS, "%s: vm-check receipt.json status=%s finishedAt=%s, after the arm at %s" % (
            token,
            doc.get("status"),
            fin,
            arm.get("at"),
        )
    if (kind, value) == ("VM-CHECK", "verified"):
        ok = ctx.vm_verified()
        return (HOLDS if ok else HELD), "%s: vm_tier.admit %s HEAD's tree" % (
            token,
            "admits" if ok else "does not admit",
        )
    if (kind, value) == ("BENCH", "deployed"):
        ok = ctx.bench()
        return (HOLDS if ok else HELD), "%s: %s" % (
            token,
            "a clean bench deploy record carries HEAD's account code"
            if ok
            else "no clean bench deploy record carries HEAD's account code",
        )
    if (kind, value) == ("PUSHED", "head"):
        ok = ctx.pushed()
        return (HOLDS if ok else HELD), "%s: HEAD is %son its upstream" % (
            token,
            "" if ok else "not ",
        )
    if kind == "DEFER-CLOSED":
        rid = value.lstrip("#")
        rec = ctx.by_id.get(rid)
        if rec is None:
            return VOIDED, "%s: the item left the store (tombstoned)" % token
        if rec.get("state") != "?":
            return VOIDED, "%s: #%s left [?] for [%s] before its window closed" % (
                token,
                rid,
                rec.get("state"),
            )
        line = str(rec.get("line") or rec.get("text") or "")
        if not C.DEFAULT_TOKEN.search(line):
            return HELD, "%s: #%s carries no DEFAULT:" % (token, rid)
        age = C.stamp_age_min(rec.get("upd", "")) or 0
        if age < ctx.defer_window_min:
            return HELD, "%s: #%s is %d min into its %d min window" % (
                token,
                rid,
                age,
                ctx.defer_window_min,
            )
        if C.not_before_pending(line, rec.get("upd", "")):
            return HELD, "%s: #%s is held by its NOT-BEFORE" % (token, rid)
        return (
            HOLDS,
            "%s: #%s is [?] %d min past its last update, window %d min, no NOT-BEFORE holding it"
            % (
                token,
                rid,
                age,
                ctx.defer_window_min,
            ),
        )
    if kind == "TICKED":
        rid = value.lstrip("#")
        rec = ctx.by_id.get(rid)
        if rec is None:
            return VOIDED, "%s: the item left the store (tombstoned)" % token
        if rec.get("state") == "x":
            return HOLDS, "%s: #%s is [x]" % (token, rid)
        if rec.get("state") == "~":
            return VOIDED, "%s: #%s is tombstoned" % (token, rid)
        return HELD, "%s: #%s is [%s]" % (token, rid, rec.get("state"))
    if kind == "BOX":
        m = BOX_RE.match(value)
        if not m:
            return HELD, "%s: not <plan-path>#<sig8>" % token
        text = ctx.show_head(m.group(1))
        if text is None:
            return HELD, "%s: git cannot show HEAD:%s" % (token, m.group(1))
        state = box_state(text, m.group(2))
        if state == "done":
            return HOLDS, "%s: ticked in HEAD's %s" % (token, m.group(1))
        if state == "absent":
            return (
                VOIDED,
                "%s: the sig is absent from HEAD's %s (the box was rewritten or removed)"
                % (
                    token,
                    m.group(1),
                ),
            )
        return HELD, "%s: open in HEAD's %s" % (token, m.group(1))
    return HELD, "%s: not a known token kind" % token


def evaluate(arm: dict, ctx: Ctx) -> tuple[str, str]:
    """(verdict, why) for one arm at this stop: ARMED, FIRED, EXPIRED or VOID.

    A latched arm answers its latch and is not re-judged (Design 3). Otherwise: any token void makes the arm void; every token holding at once fires it; else an arm at or past its expiry is expired; else it stays armed. `why` joins each token's evidence."""
    latched = arm.get("verdict") or ""
    if latched:
        return latched, str(arm.get("why") or "")
    tokens = list(arm.get("when") or [])
    if not tokens:
        return VOID, "the arm carries no tokens"
    judged = [judge_token(t, arm, ctx) for t in tokens]
    why = "; ".join(e for _s, e in judged)
    if any(s == VOIDED for s, _e in judged):
        return VOID, why
    if all(s == HOLDS for s, _e in judged):
        return FIRED, why
    exp = parse_instant(arm.get("exp"))
    if exp is None:
        return EXPIRED, "the arm's expiry %r does not parse; %s" % (arm.get("exp"), why)
    if ctx.now >= exp:
        return EXPIRED, "expired at %s before every token held; %s" % (arm.get("exp"), why)
    return ARMED, why


def note_running(seen: dict, arms, running, now: datetime.datetime) -> dict:
    """Record, per arm, the EXIT task ids this stop's event lists running after the arm stamp, into `seen` ({aid: [task ids]}, the hook's state doc carries it between stops). Entries for arms no longer live are dropped. Returns `seen`."""
    live = {}
    for _rec, arm in arms:
        aid = arm.get("aid")
        tasks = [t.split(":", 1)[1] for t in arm.get("when") or [] if t.startswith("EXIT:")]
        if not aid or not tasks:
            continue
        got = list(seen.get(aid) or [])
        at = parse_instant(arm.get("at"))
        if running and at is not None and now > at:
            for t in tasks:
                if t in running and t not in got:
                    got.append(t)
        live[aid] = got
    seen.clear()
    seen.update(live)
    return seen


def sweep(worklist, by, items, session_id, ctx: Ctx) -> list[tuple[dict, dict, str, str]]:
    """Evaluate every unlatched live arm this session owns and append one `armfire` per newly latched arm. Returns [(rec, arm, verdict, why)] for every arm that is now due (latched, not started), the newly latched ones carrying their fresh latch. Hook-only: the CLI never latches."""
    import wl_store as S

    due_rows = []
    for rec, arm in session_arms(items, session_id):
        verdict, why = evaluate(arm, ctx)
        if verdict == ARMED:
            continue
        latched = arm
        if not arm.get("verdict"):
            S.armfire_item(worklist, by, rec["id"], arm["aid"], verdict, why)
            latched = dict(arm, verdict=verdict, why=why, fired_at=stamp(ctx.now))
        due_rows.append((rec, latched, verdict, why))
    return due_rows


# ---------------------------------------------------------------------------- the STATE.md demand


ARMED_HEAD_RE = re.compile(r"^##[ \t]+Armed\b[^\n]*$", re.MULTILINE | re.IGNORECASE)


def armed_section(body: str) -> str | None:
    """The text of the body's `## Armed` section (to the next `## ` heading), or None when it has none."""
    m = ARMED_HEAD_RE.search(body or "")
    if not m:
        return None
    rest = body[m.end() :]
    nxt = re.search(r"^##[ \t]", rest, re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def unnamed_arms(body: str, armed_ids) -> list[str] | None:
    """None when the body has no `## Armed` section; else the armed item ids the section does not name as `#<id>` (an 8-character prefix of the id counts)."""
    section = armed_section(body)
    if section is None:
        return None
    named = re.findall(r"#([0-9a-f]{6,16})\b", section)
    return [
        rid
        for rid in armed_ids
        if not any(rid.startswith(n) and len(n) >= min(8, len(rid)) for n in named)
    ]


# ---------------------------------------------------------------------------- briefs


def brief_rel(me8: str, item_id: str) -> str:
    """The one place a brief lives (Design 8): agent/<me8>/armed/<item-id>.md."""
    return "agent/%s/armed/%s.md" % (me8, item_id)


def start_line(me8: str, item_id: str) -> str:
    """A brief's first line: the command that consumes the arm."""
    return ".claude/hooks/stop/worklist.py --armed-start %s %s" % (me8, item_id)


SURVEY_HEAD_RE = re.compile(
    r"^##[ \t]+(?:\d+\.[ \t]+)?Armed\b[^\n]*$", re.MULTILINE | re.IGNORECASE
)


def survey_rows(text: str) -> tuple[list[dict], list[str]]:
    """([{blocker, sigs, trigger, draft}], [problems]) from a writers-now survey's `## Armed` table (Design 9: `blocker | dependent sigs | trigger | brief draft path`). The header and separator rows are skipped; a row with the wrong cell count is a problem, never a silent skip."""
    m = SURVEY_HEAD_RE.search(text or "")
    if not m:
        return [], ["the survey has no `## Armed` section"]
    rest = text[m.end() :]
    nxt = re.search(r"^##[ \t]", rest, re.MULTILINE)
    body = rest[: nxt.start()] if nxt else rest
    rows, problems = [], []
    for raw in body.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
            continue
        if [c.lower() for c in cells[:1]] == ["blocker"]:
            continue
        if len(cells) != 4:
            problems.append("row %r has %d cells, not 4" % (line[:80], len(cells)))
            continue
        blocker, sigs, trigger, draft = (c.strip("`") for c in cells)
        rows.append({"blocker": blocker, "sigs": sigs, "trigger": trigger, "draft": draft})
    if not rows and not problems:
        problems.append("the `## Armed` section holds no table rows")
    return rows, problems


def trigger_tokens(cell: str) -> list[str]:
    """The tokens of a survey trigger cell: whitespace, comma or ` AND ` separated, backticks dropped."""
    text = re.sub(r"\bAND\b", " ", str(cell or "").replace("`", " "))
    return [t for t in re.split(r"[\s,]+", text) if t]
