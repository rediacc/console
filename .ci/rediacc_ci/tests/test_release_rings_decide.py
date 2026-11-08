"""The oracle for `rediacc_ci.release.rings.decide` (agent/plans/PLAN-enterprise-isolation.md box K1): a planted failure, the pauses, windows, the override, the ring thresholds, and a security order with and without a soak waiver."""

from __future__ import annotations

import dataclasses
import datetime

import pytest

from rediacc_ci.release import rings
from rediacc_ci.release.rings import Company, Order, Resume, State, Window, decide

UTC = datetime.UTC
# A Wednesday, so the window cases below can name weekdays relative to it.
NOW = datetime.datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
H = datetime.timedelta(hours=1)
D = datetime.timedelta(days=1)
V = "0.9.1"


def soaked(*companies: Company) -> State:
    """A state whose bench and fast-tier soak are behind it; cases vary it with `dataclasses.replace`."""
    return State(version=V, bench_done=True, fast_at=NOW - 8 * D, companies=companies)


def done(cid: str, machines: int, at: datetime.datetime, override: str | None = None) -> Company:
    return Company(cid, "eu", machines, status="done", finished_at=at, override=override)


def pending(
    cid: str, machines: int, override: str | None = None, windows: tuple[Window, ...] = ()
) -> Company:
    return Company(cid, "eu", machines, override=override, windows=windows)


# -- thresholds and the override ------------------------------------------------


@pytest.mark.parametrize(
    ("machines", "ring"),
    [(0, "small"), (9, "small"), (10, "medium"), (49, "medium"), (50, "large"), (900, "large")],
)
def test_ring_thresholds(machines: int, ring: str) -> None:
    assert rings.ring_of(machines) == ring


def test_override_wins_over_the_count_and_canary_is_override_only() -> None:
    assert rings.ring_of(3, "large") == "large"
    assert rings.ring_of(80, "canary") == "canary"
    assert all(rings.ring_of(n) != "canary" for n in (0, 9, 10, 49, 50, 10_000))


def test_unknown_override_and_negative_count_are_refused() -> None:
    with pytest.raises(ValueError, match="override 'fast'"):
        rings.ring_of(1, "fast")
    with pytest.raises(ValueError, match="negative"):
        rings.ring_of(-1)


def test_high_water_never_falls() -> None:
    assert rings.high_water(12, 7) == 12
    assert rings.high_water(12, 30) == 30


def test_override_moves_a_company_to_its_ring_in_decide() -> None:
    state = soaked(pending("c01", 300, override="canary"), pending("c02", 2))
    got = decide(state, NOW)
    assert (got.action, got.ring, got.companies) == ("deploy", "canary", ("c01",))


def test_rings_deploy_in_order_canary_small_medium_large() -> None:
    assert (
        decide(soaked(pending("cL", 70), pending("cM", 20), pending("cS", 3)), NOW).ring == "small"
    )
    assert decide(soaked(pending("cL", 70), pending("cM", 20)), NOW).ring == "medium"
    assert decide(soaked(pending("cL", 70)), NOW).ring == "large"


# -- preconditions: bench and the fast tier's soak ------------------------------


def test_bench_first() -> None:
    got = decide(dataclasses.replace(soaked(pending("c01", 1)), bench_done=False), NOW)
    assert (got.action, got.ring) == ("wait", "bench")


def test_fast_tier_must_have_taken_the_version() -> None:
    got = decide(dataclasses.replace(soaked(pending("c01", 1)), fast_at=None), NOW)
    assert (got.action, got.ring) == ("wait", "fast")


def test_soak_holds_until_seven_days() -> None:
    fast_at = NOW - 6 * D
    got = decide(dataclasses.replace(soaked(pending("c01", 1)), fast_at=fast_at), NOW)
    assert (got.action, got.ring, got.until) == ("wait", "fast", fast_at + 7 * D)
    got = decide(dataclasses.replace(soaked(pending("c01", 1)), fast_at=NOW - 7 * D), NOW)
    assert got.action == "deploy"


# -- security order -------------------------------------------------------------


def _paused_young(order: Order) -> State:
    """Small finished an hour ago (pause running) and the fast tier took the version a day ago (soak running)."""
    base = soaked(pending("cM", 20), done("cS", 2, NOW - H))
    return dataclasses.replace(base, fast_at=NOW - D, order=order)


def test_order_without_waiver_skips_pauses_but_keeps_the_soak() -> None:
    young = _paused_young(Order("SEC-1", skip_pauses=True))
    got = decide(young, NOW)
    assert (got.action, got.ring) == ("wait", "fast")
    got = decide(dataclasses.replace(young, fast_at=NOW - 8 * D), NOW)
    assert (got.action, got.ring, got.companies) == ("deploy", "medium", ("cM",))


def test_order_with_waiver_skips_the_soak_and_the_pauses() -> None:
    got = decide(_paused_young(Order("SEC-2", skip_pauses=True, waive_soak=True)), NOW)
    assert (got.action, got.ring) == ("deploy", "medium")


def test_waiver_alone_does_not_skip_pauses() -> None:
    got = decide(_paused_young(Order("SEC-3", waive_soak=True)), NOW)
    assert got.action == "wait"
    assert got.reason.startswith("pause after small")


def test_flags_without_an_order_are_refused() -> None:
    assert rings.order_refusals(None, skip_pauses=True, waive_soak=False) == [
        "--skip-pauses needs --order <id>: only a security order skips pauses"
    ]
    assert len(rings.order_refusals("  ", skip_pauses=True, waive_soak=True)) == 2
    assert rings.order_refusals("SEC-1", skip_pauses=True, waive_soak=True) == []
    assert rings.order_refusals(None, skip_pauses=False, waive_soak=False) == []


# -- pauses ---------------------------------------------------------------------


def test_pause_after_small_is_24h_from_the_last_finished() -> None:
    last = NOW - 23 * H
    state = soaked(done("cS1", 2, NOW - 30 * H), done("cS2", 4, last), pending("cM", 20))
    got = decide(state, NOW)
    assert (got.action, got.ring, got.until) == ("wait", "medium", last + 24 * H)
    got = decide(state, last + 24 * H)
    assert (got.action, got.ring, got.companies) == ("deploy", "medium", ("cM",))


def test_pause_after_medium_is_48h() -> None:
    last = NOW - 47 * H
    state = soaked(done("cM", 20, last), pending("cL", 70))
    got = decide(state, NOW)
    assert (got.action, got.until) == ("wait", last + 48 * H)
    assert decide(state, last + 48 * H).action == "deploy"


def test_no_pause_after_canary() -> None:
    state = soaked(done("cC", 1, NOW - H, override="canary"), pending("cS", 2))
    got = decide(state, NOW)
    assert (got.action, got.ring, got.resmoke) == ("deploy", "small", ())


def test_resmoke_before_leaving_a_paused_ring_and_only_once() -> None:
    state = soaked(done("cS2", 4, NOW - 30 * H), done("cS1", 2, NOW - 25 * H), pending("cM", 20))
    got = decide(state, NOW)
    assert got.resmoke == ("cS1", "cS2")
    got = decide(dataclasses.replace(state, resmoked=frozenset({"small"})), NOW)
    assert (got.action, got.resmoke) == ("deploy", ())


def test_empty_ring_carries_the_pause_of_the_ring_before_it() -> None:
    state = soaked(done("cS", 2, NOW - H), pending("cL", 70))
    got = decide(state, NOW)
    assert (got.action, got.ring, got.until) == ("wait", "large", NOW + 23 * H)


# -- windows --------------------------------------------------------------------


def test_window_parse_and_holds() -> None:
    w = rings.parse_window("mon,wed-fri 22:00-02:00")
    assert w.days == frozenset({0, 2, 3, 4})
    assert (w.start, w.end) == (22 * 60, 2 * 60)
    wed_2330 = datetime.datetime(2026, 11, 11, 23, 30, tzinfo=UTC)
    assert w.holds(wed_2330)
    assert w.holds(wed_2330 + 2 * H)
    assert not w.holds(wed_2330 - D)
    assert rings.parse_window("sat-mon 00:00-00:00").days == frozenset({5, 6, 0})


@pytest.mark.parametrize(
    "text", ["", "mon", "xyz 01:00-02:00", "mon 1:00-02:00", "mon 24:00-01:00"]
)
def test_window_parse_refusals(text: str) -> None:
    with pytest.raises(ValueError, match="window"):
        rings.parse_window(text)


def test_company_outside_its_window_holds_its_ring_open() -> None:
    sat = rings.parse_window("sat 02:00-04:00")
    state = soaked(pending("cS1", 1, windows=(sat,)), pending("cM", 20))
    got = decide(state, NOW)
    assert got.action == "window"
    assert (got.ring, got.companies) == ("small", ("cS1",))
    assert got.until == datetime.datetime(2026, 11, 14, 2, 0, tzinfo=UTC)


def test_in_window_companies_deploy_while_another_waits_for_its_window() -> None:
    sat = rings.parse_window("sat 02:00-04:00")
    state = soaked(pending("cS1", 1, windows=(sat,)), pending("cS2", 2), pending("cM", 20))
    got = decide(state, NOW)
    assert (got.action, got.ring, got.companies) == ("deploy", "small", ("cS2",))


def test_company_inside_its_window_deploys() -> None:
    wed = rings.parse_window("wed 11:00-13:00")
    got = decide(soaked(pending("cS1", 1, windows=(wed,))), NOW)
    assert (got.action, got.companies) == ("deploy", ("cS1",))


# -- the planted failure --------------------------------------------------------


def test_planted_failure_latches_a_stop_naming_the_company() -> None:
    failed = Company("cBAD", "eu", 3, status="failed", finished_at=NOW - H)
    state = soaked(done("cS", 2, NOW - 2 * H), failed, pending("cM", 20), pending("cL", 80))
    got = decide(state, NOW + 30 * D)
    assert (got.action, got.companies) == ("stop", ("cBAD",))
    assert "cBAD" in got.reason
    assert f"--resume {V}" in got.reason


def test_stop_survives_a_security_order() -> None:
    failed = Company("cBAD", "eu", 3, status="failed")
    order = Order("SEC-9", skip_pauses=True, waive_soak=True)
    assert decide(dataclasses.replace(soaked(failed), order=order), NOW).action == "stop"


def test_resume_must_name_the_same_version_and_company() -> None:
    failed = Company("cBAD", "eu", 3, status="failed")
    state = soaked(failed, pending("cM", 20))
    assert decide(dataclasses.replace(state, resume=Resume("0.9.0", "cBAD")), NOW).action == "stop"
    assert decide(dataclasses.replace(state, resume=Resume(V, "cOTHER")), NOW).action == "stop"
    got = decide(dataclasses.replace(state, resume=Resume(V, "cBAD")), NOW)
    assert (got.action, got.ring, got.companies) == ("deploy", "small", ("cBAD",))


# -- unreachable region ---------------------------------------------------------


def test_unreachable_region_holds_only_its_own_companies() -> None:
    state = soaked(Company("cUS", "us", 2), pending("cEU", 3))
    got = decide(dataclasses.replace(state, unreachable=frozenset({"us"})), NOW)
    assert (got.action, got.companies, got.held) == ("deploy", ("cEU",), ("cUS",))


def test_run_is_not_done_while_a_region_is_unreachable() -> None:
    state = soaked(Company("cUS", "us", 2), done("cEU", 3, NOW - D))
    got = decide(dataclasses.replace(state, unreachable=frozenset({"us"})), NOW)
    assert (got.action, got.held) == ("wait", ("cUS",))
    assert "region unreachable: us" in got.reason


def test_done_when_every_company_runs_the_version() -> None:
    assert (
        decide(soaked(done("cS", 2, NOW - 3 * D), done("cM", 20, NOW - 2 * D)), NOW).action
        == "done"
    )
    assert decide(soaked(), NOW).action == "done"


# -- input refusals -------------------------------------------------------------


def test_naive_times_are_refused() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        decide(soaked(), NOW.replace(tzinfo=None))


def test_duplicate_and_inconsistent_companies_are_refused() -> None:
    with pytest.raises(ValueError, match="twice"):
        decide(soaked(pending("c1", 1), pending("c1", 2)), NOW)
    with pytest.raises(ValueError, match="no finished_at"):
        decide(soaked(Company("c1", "eu", 1, status="done")), NOW)


def test_decide_is_pure() -> None:
    state = soaked(pending("cS", 2), done("cC", 1, NOW - H, override="canary"))
    before = dataclasses.asdict(state)
    assert decide(state, NOW) == decide(state, NOW)
    assert dataclasses.asdict(state) == before
