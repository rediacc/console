"""The pure core of the Enterprise release rings: `decide(state, now)` (agent/plans/PLAN-enterprise-isolation.md, Design *Rings*, box K1).

THE STAGES, in order: `bench`, the fast tier's soak (`SOAK_DAYS`, the same 7 days `rediacc_ci.release.check_soak_period` judges), then the company rings `canary`, `small`, `medium` and `large`. Bench and the fast tier are taken by the shared release (`release:local`), so here they are preconditions the state reports, never deploys this core orders.

THE RING OF A COMPANY comes from its machine high-water mark: under `SMALL_BELOW` (10) is small, under `MEDIUM_BELOW` (50) is medium, the rest is large. A per-company override names any company ring, and `canary` is reached only by override (the internal canary company). The count the runner samples is `COUNT(DISTINCT machine_id)` over `subscription_activations`, whose rows prune, so `high_water` keeps the larger of the stored mark and the new sample.

PAUSES. `PAUSE_AFTER` holds 24 h after small and 48 h after medium, counted from the LAST company that finished in that ring. Once a pause has run, the ring is re-smoked before the next ring deploys: the decision names those companies in `resmoke`, and the runner records the ring in `State.resmoked` when they pass. A ring with no companies has nothing to pause on.

WINDOWS. A company with upgrade windows deploys only inside one of them. A company outside its window holds its ring open: the next ring waits, and when nothing else in the ring can deploy the decision is `window`, naming the companies and the next opening.

STOP. A failed company latches a stop naming it, and nothing deploys anywhere until `--resume V --company <id>` names that same version and company, which puts the company back in its ring. An unreachable region stops only its own companies: they are named in `held` and excluded from their ring's completion, and while they remain the run is never `done`.

A SECURITY ORDER (`Order`) skips every pause, and waives the soak only when the same order says `waive_soak`. `order_refusals` refuses either flag without an order id, which is how `--skip-pauses` without `--order` is refused before anything is decided.

`decide` reads nothing but its arguments and writes nothing; the runner (`rediacc_ci.release.rings_run`, box K2) owns the reads, the deploys and the records.
"""

from __future__ import annotations

import dataclasses
import datetime
import re
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

STAGES: tuple[str, ...] = ("bench", "fast", "canary", "small", "medium", "large")
COMPANY_RINGS: tuple[str, ...] = ("canary", "small", "medium", "large")
OVERRIDE_RINGS: frozenset[str] = frozenset(COMPANY_RINGS)

SMALL_BELOW = 10
MEDIUM_BELOW = 50
SOAK_DAYS = 7
PAUSE_AFTER: dict[str, datetime.timedelta] = {
    "small": datetime.timedelta(hours=24),
    "medium": datetime.timedelta(hours=48),
}

Action = Literal["deploy", "wait", "window", "stop", "done"]
Status = Literal["pending", "done", "failed"]

_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_WINDOW = re.compile(r"^(\S+)\s+(\S+)$")
_MINUTES_PER_DAY = 24 * 60


@dataclasses.dataclass(frozen=True)
class Window:
    """Weekdays (0 is Monday) and a UTC span in minutes from midnight. An `end` at or before `start` crosses midnight and belongs to the day it starts on."""

    days: frozenset[int]
    start: int
    end: int

    def holds(self, now: datetime.datetime) -> bool:
        now = _utc(now)
        length = (self.end - self.start) % _MINUTES_PER_DAY or _MINUTES_PER_DAY
        for back in (0, 1):
            day = (now - datetime.timedelta(days=back)).date()
            begin = _at(day, self.start)
            in_span = begin <= now < begin + datetime.timedelta(minutes=length)
            if day.weekday() in self.days and in_span:
                return True
        return False

    def next_open(self, now: datetime.datetime) -> datetime.datetime:
        """The first opening strictly after `now`."""
        now = _utc(now)
        for ahead in range(8):
            day = (now + datetime.timedelta(days=ahead)).date()
            begin = _at(day, self.start)
            if day.weekday() in self.days and begin > now:
                return begin
        msg = f"window has no weekday: {self!r}"
        raise ValueError(msg)


def _utc(now: datetime.datetime) -> datetime.datetime:
    """`now` in UTC; a naive datetime is refused, because `astimezone` would read it as local time."""
    if now.tzinfo is None:
        msg = "a window needs a timezone-aware datetime, got a naive one"
        raise ValueError(msg)
    return now.astimezone(datetime.UTC)


def _at(day: datetime.date, minute: int) -> datetime.datetime:
    return datetime.datetime(
        day.year, day.month, day.day, minute // 60, minute % 60, tzinfo=datetime.UTC
    )


def _minute(text: str, whole: str) -> int:
    m = _HHMM.match(text)
    if not m:
        msg = f"window {whole!r}: span must be HH:MM-HH:MM"
        raise ValueError(msg)
    return int(m.group(1)) * 60 + int(m.group(2))


def parse_window(text: str) -> Window:
    """`mon,wed-fri 22:00-02:00` (UTC) as a `Window`. Raises ValueError naming the part it cannot read."""
    whole = _WINDOW.match(text.strip().lower())
    if not whole:
        msg = f"window {text!r}: expected '<days> <HH:MM-HH:MM>'"
        raise ValueError(msg)
    days: set[int] = set()
    for item in whole.group(1).split(","):
        lo, dash, hi = item.partition("-")
        if lo not in _DAYS or (dash and hi not in _DAYS):
            msg = f"window {text!r}: unknown day in {item!r}"
            raise ValueError(msg)
        first, last = _DAYS.index(lo), _DAYS.index(hi or lo)
        span = range(first, last + 1) if first <= last else [*range(first, 7), *range(last + 1)]
        days.update(span)
    start_s, _, end_s = whole.group(2).partition("-")
    return Window(frozenset(days), _minute(start_s, text), _minute(end_s, text))


@dataclasses.dataclass(frozen=True)
class Company:
    """One company's place in this release. `id` is the opaque `c<hex>`, never a name."""

    id: str
    region: str
    machines: int
    status: Status = "pending"
    override: str | None = None
    windows: tuple[Window, ...] = ()
    finished_at: datetime.datetime | None = None


@dataclasses.dataclass(frozen=True)
class Order:
    """A security order: `skip_pauses` skips every pause; `waive_soak` waives the fast tier's soak."""

    id: str
    skip_pauses: bool = False
    waive_soak: bool = False


@dataclasses.dataclass(frozen=True)
class Resume:
    version: str
    company: str


@dataclasses.dataclass(frozen=True)
class State:
    version: str
    bench_done: bool
    fast_at: datetime.datetime | None
    companies: tuple[Company, ...]
    order: Order | None = None
    resume: Resume | None = None
    resmoked: frozenset[str] = frozenset()
    unreachable: frozenset[str] = frozenset()
    soak_days: int = SOAK_DAYS


@dataclasses.dataclass(frozen=True)
class Decision:
    action: Action
    reason: str
    ring: str | None = None
    companies: tuple[str, ...] = ()
    resmoke: tuple[str, ...] = ()
    until: datetime.datetime | None = None
    held: tuple[str, ...] = ()


def ring_of(machines: int, override: str | None = None) -> str:
    """The company ring for a machine count, or the override when one is set. Raises ValueError on an unknown override or a negative count."""
    if override is not None:
        if override not in OVERRIDE_RINGS:
            msg = f"ring override {override!r} is not one of {', '.join(COMPANY_RINGS)}"
            raise ValueError(msg)
        return override
    if machines < 0:
        msg = f"machine count {machines} is negative"
        raise ValueError(msg)
    if machines < SMALL_BELOW:
        return "small"
    if machines < MEDIUM_BELOW:
        return "medium"
    return "large"


def high_water(stored: int, sampled: int) -> int:
    """The mark kept on the control row: activations prune, so a smaller sample never lowers it."""
    return max(stored, sampled)


def order_refusals(order_id: str | None, *, skip_pauses: bool, waive_soak: bool) -> list[str]:
    """Why a release's flags are refused, empty when they are admitted."""
    out: list[str] = []
    if not (order_id or "").strip():
        if skip_pauses:
            out.append("--skip-pauses needs --order <id>: only a security order skips pauses")
        if waive_soak:
            out.append("--waive-soak needs --order <id>: only a security order waives the soak")
    return out


def in_window(company: Company, now: datetime.datetime) -> bool:
    return not company.windows or any(w.holds(now) for w in company.windows)


def next_opening(company: Company, now: datetime.datetime) -> datetime.datetime | None:
    if not company.windows:
        return None
    return min(w.next_open(now) for w in company.windows)


def _aware(value: datetime.datetime, what: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"{what} must be timezone-aware, got {value!r}"
        raise ValueError(msg)


def _validate(state: State, now: datetime.datetime) -> None:
    _aware(now, "now")
    if state.fast_at is not None:
        _aware(state.fast_at, "fast_at")
    seen: set[str] = set()
    for c in state.companies:
        if c.id in seen:
            msg = f"company {c.id} appears twice"
            raise ValueError(msg)
        seen.add(c.id)
        ring_of(c.machines, c.override)
        if c.status == "done" and c.finished_at is None:
            msg = f"company {c.id} is done with no finished_at"
            raise ValueError(msg)
        if c.finished_at is not None:
            _aware(c.finished_at, f"finished_at of {c.id}")


def _effective(state: State) -> tuple[Company, ...]:
    """The companies with a matching `--resume` applied: the named failed company is pending again."""
    r = state.resume
    if r is None or r.version != state.version:
        return state.companies
    return tuple(
        dataclasses.replace(c, status="pending")
        if c.id == r.company and c.status == "failed"
        else c
        for c in state.companies
    )


def _ids(companies: Iterable[Company]) -> tuple[str, ...]:
    return tuple(sorted(c.id for c in companies))


def _preconditions(
    state: State, companies: Sequence[Company], now: datetime.datetime
) -> Decision | None:
    """The latched stop, then bench, then the fast tier's soak; None once all three admit the company rings."""
    failed = _ids(c for c in companies if c.status == "failed")
    if failed:
        return Decision(
            "stop",
            f"stopped: {', '.join(failed)} failed on {state.version}; resume with "
            f"--resume {state.version} --company <id>",
            companies=failed,
        )
    if not state.bench_done:
        return Decision("wait", f"bench has not taken {state.version}", ring="bench")
    if state.fast_at is None:
        return Decision("wait", f"the fast tier has not taken {state.version}", ring="fast")
    soak_end = state.fast_at + datetime.timedelta(days=state.soak_days)
    waived = state.order is not None and state.order.waive_soak
    if now < soak_end and not waived:
        return Decision(
            "wait", f"the fast tier soaks until {soak_end.isoformat()}", ring="fast", until=soak_end
        )
    return None


def _ring_decision(
    state: State,
    now: datetime.datetime,
    ring: str,
    pending: Sequence[Company],
    prev: tuple[str, Sequence[Company]] | None,
) -> Decision:
    """The decision for the first ring with pending companies, given the ring before it that has members."""
    resmoke: tuple[str, ...] = ()
    if prev is not None and prev[0] in PAUSE_AFTER:
        prev_ring, prev_members = prev
        last = max(c.finished_at for c in prev_members if c.finished_at is not None)
        until = last + PAUSE_AFTER[prev_ring]
        skipped = state.order is not None and state.order.skip_pauses
        if now < until and not skipped:
            return Decision(
                "wait", f"pause after {prev_ring} until {until.isoformat()}", ring=ring, until=until
            )
        if prev_ring not in state.resmoked:
            resmoke = _ids(prev_members)
    ready = [c for c in pending if in_window(c, now)]
    if ready:
        return Decision(
            "deploy",
            f"deploy {state.version} to ring {ring}",
            ring=ring,
            companies=_ids(ready),
            resmoke=resmoke,
        )
    opening = min(o for c in pending if (o := next_opening(c, now)) is not None)
    return Decision(
        "window",
        f"ring {ring} is held open by companies outside their window until {opening.isoformat()}",
        ring=ring,
        companies=_ids(pending),
        until=opening,
    )


def decide(state: State, now: datetime.datetime) -> Decision:
    """The next action for `state` at `now`. Pure: reads its arguments only."""
    _validate(state, now)
    companies = _effective(state)
    gate = _preconditions(state, companies, now)
    if gate is not None:
        return gate

    held = [c for c in companies if c.region in state.unreachable and c.status != "done"]
    held_ids = _ids(held)
    live = [c for c in companies if c not in held]

    prev: tuple[str, Sequence[Company]] | None = None
    for ring in COMPANY_RINGS:
        members = [c for c in live if ring_of(c.machines, c.override) == ring]
        pending = [c for c in members if c.status == "pending"]
        if pending:
            found = _ring_decision(state, now, ring, pending, prev)
            return dataclasses.replace(found, held=held_ids)
        if members:
            prev = (ring, members)

    if held:
        regions = ", ".join(sorted({c.region for c in held}))
        return Decision(
            "wait",
            f"region unreachable: {regions}; held: {', '.join(held_ids)}",
            companies=held_ids,
            held=held_ids,
        )
    return Decision("done", f"every company runs {state.version}")
