"""`rediacc_ci.release.retention_contract`: the one retention rule both release pruners share.

THE ORACLE IS NOT THIS FILE'S. Every history below is judged by `rediacc_ci.quality.release_state.assert_bijection`, the gate that went red on main after the scheduled housekeeping run of 2026-10-07 (37604651929) deleted tag v1.3.1 while R2 still held `cli/v1.3.1/.released`. A retention rule that satisfies this file therefore satisfies the gate, not a restatement of it.

THREE KINDS OF CASE:

  * unit cases for `tracker_retention_plan` and `tag_retention_plan`, each with a case that must fire and one that must not;
  * a property test that replays generated release histories (releases, promotions, the `production` pointer, pre-release tags, pre-contract tags, nightly housekeeping with an age window) through BOTH plans the way the two callers apply them, and asserts the bijection and the `in_walk` guarantee after every step;
  * controls that MUST go red under the same oracle: the pre-fix housekeeping rule replayed on the 10-07 state, an `in_walk` version outside the top 20 under that rule, a deliberately mismatched keep constant, and housekeeping without its sentinel guard. A control that stays green means the oracle or the generator stopped seeing the case, and each says so.
"""

from __future__ import annotations

import inspect
import pathlib
import random
import re

import pytest

from rediacc_ci.deploy import upload_to_r2
from rediacc_ci.housekeeping import cleanup_versions
from rediacc_ci.quality import release_state
from rediacc_ci.release import retention_contract as rc
from rediacc_ci.release.check_soak_period import in_walk

KEEP = rc.KEEP_RELEASES
NO_ROOT = pathlib.Path("/nonexistent-retention-contract-root")


@pytest.fixture(autouse=True)
def _no_ratchet(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """The bijection's floor is the oldest OBSERVED sentinel only: no git ratchet file (a path that does not exist) and no override."""
    monkeypatch.setenv("RSV_FLOOR_FILE", str(tmp_path / "no-floor-file"))
    monkeypatch.delenv("RSV_GRANDFATHER_BEFORE", raising=False)


def bijection(sentinels: set[str], tags: set[str]) -> tuple[list[str], int]:
    semver = [t for t in tags if rc.is_release_tag(t)]
    # `root` only locates the ratchet file, which `_no_ratchet` has already pointed at nothing.
    return release_state.assert_bijection(sorted(sentinels), sorted(semver), "", NO_ROOT)


def versions(count: int, major: int = 1) -> list[str]:
    """`count` ascending release versions, without the `v` (the tracker's spelling)."""
    return ["%d.%d.%d" % (major, i // 10, i % 10) for i in range(count)]


# --------------------------------------------------------------------------- tracker_retention_plan ---------------------------------------------------------------------------


def test_the_tracker_keeps_the_window_and_prunes_at_or_below_stable() -> None:
    history = versions(22)
    tracker = list(reversed(history[:-1]))
    plan = rc.tracker_retention_plan(tracker, history[-1], stable=history[-1])
    assert plan.kept == tuple(reversed(history[2:]))
    assert plan.pruned == (history[1], history[0])
    assert plan.held == ()


def test_the_tracker_holds_a_promotion_candidate_after_the_window() -> None:
    history = versions(23)
    tracker = list(reversed(history[:-1]))
    plan = rc.tracker_retention_plan(tracker, history[-1], stable=history[0])
    assert plan.kept[:KEEP] == tuple(reversed(history[3:]))
    assert plan.kept[KEEP:] == (history[2], history[1])
    assert plan.pruned == (history[0],), "stable itself is not newer than stable"
    assert plan.held == tuple(
        (v, "newer than stable v%s, a promotion candidate" % history[0])
        for v in (history[2], history[1])
    )


@pytest.mark.parametrize("stable", ["", "null", "not-a-version"])
def test_an_unknown_stable_prunes_nothing(stable: str) -> None:
    history = versions(25)
    plan = rc.tracker_retention_plan(list(reversed(history[:-1])), history[-1], stable=stable)
    assert plan.pruned == ()
    assert len(plan.kept) == 25
    assert all(why == rc.REASON_STABLE_UNKNOWN for _v, why in plan.held)


def test_a_re_release_keeps_its_place() -> None:
    plan = rc.tracker_retention_plan(["9.9.1", "1.2.3", "9.9.0"], "1.2.3", stable="")
    assert plan.kept == ("9.9.1", "1.2.3", "9.9.0")
    assert plan.pruned == ()
    assert plan.held == ()


def test_the_tracker_window_is_the_keep_argument() -> None:
    plan = rc.tracker_retention_plan(["3.0.0", "2.0.0", "1.0.0"], "4.0.0", stable="4.0.0", keep=2)
    assert plan.kept == ("4.0.0", "3.0.0")
    assert plan.pruned == ("2.0.0", "1.0.0")


# --------------------------------------------------------------------------- tag_retention_plan ---------------------------------------------------------------------------


def _tags(history: list[str]) -> list[str]:
    """Newest first, `v`-prefixed."""
    return ["v" + v for v in reversed(history)]


def test_a_pointer_tag_does_not_take_a_release_slot() -> None:
    history = versions(KEEP)
    names = ["production", *_tags(history)]
    plan = rc.tag_retention_plan(names, stable=history[-1])
    assert [v.name for v in plan.keep] == names, "production took a release slot"
    assert plan.delete == ()
    assert plan.held == ()


def test_a_pre_release_is_counted_among_the_non_release_tags() -> None:
    names = ["v2.0.0-rc.2", "v2.0.0-rc.1", "v1.0.0", "v0.9.0"]
    plan = rc.tag_retention_plan(names, stable="1.0.0", keep=1)
    assert plan.verdict("v2.0.0-rc.2").kind == rc.KEEP
    assert plan.verdict("v1.0.0").kind == rc.KEEP
    assert plan.verdict("v2.0.0-rc.1").kind == rc.DELETE
    assert plan.verdict("v0.9.0").kind == rc.DELETE


@pytest.mark.parametrize("spelling", ["v1.0.0", "1.0.0"])
def test_a_tag_whose_sentinel_exists_is_held(spelling: str) -> None:
    plan = rc.tag_retention_plan(["v2.0.0", "v1.0.0"], stable="2.0.0", keep=1, sentinels={spelling})
    verdict = plan.verdict("v1.0.0")
    assert verdict.kind == rc.HELD
    assert verdict.reason == "its sentinel cli/v1.0.0/.released still exists"
    # The control: without the sentinel it goes.
    assert (
        rc.tag_retention_plan(["v2.0.0", "v1.0.0"], stable="2.0.0", keep=1).verdict("v1.0.0").kind
        == rc.DELETE
    )


def test_a_promotion_candidate_tag_is_held() -> None:
    plan = rc.tag_retention_plan(["v3.0.0", "v2.0.0", "v1.0.0"], stable="1.0.0", keep=1)
    assert plan.verdict("v2.0.0").kind == rc.HELD
    assert plan.verdict("v2.0.0").reason == "newer than stable v1.0.0, a promotion candidate"
    assert plan.verdict("v1.0.0").kind == rc.DELETE


def test_an_unknown_stable_holds_every_release_tag_and_says_a_read_would_help() -> None:
    plan = rc.tag_retention_plan(
        ["v3.0.0", "v2.0.0", "production", "old-pointer"], stable="", keep=1
    )
    assert plan.verdict("v2.0.0").kind == rc.HELD
    assert plan.verdict("v2.0.0").reason == rc.REASON_STABLE_UNKNOWN
    assert plan.needs_stable
    assert plan.verdict("old-pointer").kind == rc.DELETE, (
        "a non-release tag is outside the contract"
    )
    # Nothing outside the window: no read is worth making.
    assert not rc.tag_retention_plan(["v3.0.0", "production"], stable="", keep=1).needs_stable


def test_a_repo_without_the_contract_keeps_the_window_only() -> None:
    plan = rc.tag_retention_plan(
        ["v3.0.0", "v2.0.0", "v1.0.0"], stable="", sentinels={"v1.0.0"}, keep=1, contract=False
    )
    assert [v.name for v in plan.delete] == ["v2.0.0", "v1.0.0"]


def test_both_callers_read_the_one_keep_constant() -> None:
    """The point of the module: neither pruner restates the count."""
    assert not hasattr(upload_to_r2, "MAX_RELEASE_VERSIONS")
    assert str(KEEP) == cleanup_versions.DEFAULT_KEEP_VERSIONS
    source = inspect.getsource(upload_to_r2)
    assert re.search(
        r"update_versions_tracker\(\s*\"cli\", version, retention_contract\.KEEP_RELEASES\s*\)",
        source,
    ), "upload_to_r2 no longer passes the contract's keep count to the tracker"
    assert "retention_contract.tracker_retention_plan(" in source
    assert "retention_contract.tag_retention_plan(" in inspect.getsource(cleanup_versions)


# --------------------------------------------------------------------------- the property test ---------------------------------------------------------------------------


class History:
    """One release history, applied the way the two callers apply the plans.

    `mode` is how housekeeping learns about sentinels:
      * `probe`   no listing, a per-tag probe before each delete (`cleanup_versions` today);
      * `listing` the full sentinel set handed to the plan (`cd_preflight`'s projection);
      * `window`  neither: the window and `in_walk` alone. NOT SAFE, and a control below proves it.
    """

    def __init__(
        self, rng: random.Random, mode: str, *, tag_keep: int = KEEP, prefix_rule: bool = False
    ) -> None:
        self.rng = rng
        self.mode = mode
        self.tag_keep = tag_keep
        self.prefix_rule = prefix_rule
        self.clock = 0
        self.released: list[str] = []
        self.tracker: list[str] = []
        self.sentinels: set[str] = set()
        self.tags: dict[str, int] = {}
        self.stable = ""
        self.pruned_total = 0
        self.held_total = 0
        self.tag_deletes = 0
        # Pre-contract tags: old releases that never had a sentinel.
        for i in range(rng.randrange(0, 6)):
            self.tags["v0.%d.0" % i] = self._tick()

    def _tick(self) -> int:
        self.clock += 1
        return self.clock

    def release(self) -> None:
        n = len(self.released)
        version = "1.%d.%d" % (n // 10, n % 10)
        self.released.append(version)
        self.tags["v" + version] = self._tick()
        self.sentinels.add("v" + version)
        plan = rc.tracker_retention_plan(self.tracker, version, self.stable)
        self.tracker = list(plan.kept)
        self.held_total += len(plan.held)
        for gone in plan.pruned:
            self.sentinels.discard("v" + gone)
            self.pruned_total += 1

    def promote(self) -> None:
        candidates = [
            v for v in self.released if in_walk(v, self.stable) and "v" + v in self.sentinels
        ]
        if not candidates:
            return
        self.stable = self.rng.choice(candidates)
        self.tags["production"] = self._tick()

    def pre_release(self) -> None:
        self.tags["v9.%d.0-rc.1" % self.clock] = self._tick()

    def housekeeping(self) -> None:
        names = sorted(self.tags, key=lambda t: self.tags[t], reverse=True)
        recent = set(names[: self.rng.randrange(0, 30)])
        if self.prefix_rule:
            # The rule before 2026-10-08: the newest `tag_keep` tags of ANY kind, no sentinel and no in_walk hold.
            doomed = [t for t in names[self.tag_keep :] if t not in recent]
        else:
            plan = rc.tag_retention_plan(
                names,
                stable=self.stable,
                sentinels=self.sentinels if self.mode == "listing" else (),
                keep=self.tag_keep,
            )
            doomed = [v.name for v in plan.delete if v.name not in recent]
            if self.mode == "probe":
                doomed = [t for t in doomed if t not in self.sentinels]
        for tag in doomed:
            del self.tags[tag]
            self.tag_deletes += 1

    def step(self) -> None:
        roll = self.rng.random()
        if roll < 0.55:
            self.release()
        elif roll < 0.70:
            self.promote()
        elif roll < 0.75:
            self.pre_release()
        else:
            self.housekeeping()

    def violations(self) -> list[str]:
        lines, code = bijection(self.sentinels, set(self.tags))
        out = [line for line in lines if line.startswith("DRIFT")] if code else []
        if release_state_known(self.stable):
            for version in self.released:
                if in_walk(version, self.stable):
                    tag = "v" + version
                    if (
                        tag not in self.tags
                        or tag not in self.sentinels
                        or version not in self.tracker
                    ):
                        out.append("IN_WALK %s lost its tag, sentinel or tracker entry" % tag)
        return out


def release_state_known(stable: str) -> bool:
    return rc.stable_known(stable)


SEEDS = range(400)


def _replay(seed: int, mode: str, **kw) -> tuple[History, list[str]]:
    history = History(random.Random(seed), mode, **kw)
    for _ in range(history.rng.randrange(20, 90)):
        history.step()
        found = history.violations()
        if found:
            return history, found
    history.housekeeping()
    return history, history.violations()


@pytest.mark.parametrize("mode", ["probe", "listing"])
def test_both_plans_together_never_break_the_bijection(mode: str) -> None:
    """THE PROPERTY. For every generated history, after every step: `assert_bijection` holds, and every version `in_walk` keeps its tag, its sentinel and its tracker entry.

    The totals at the end are the anti-vacuity check: the generator must actually prune sentinels, hold candidates and delete tags, or the property was asserted over histories where nothing happened."""
    pruned = held = deleted = 0
    for seed in SEEDS:
        history, found = _replay(seed, mode)
        assert not found, "seed %d (%s): %s" % (seed, mode, found)
        pruned += history.pruned_total
        held += history.held_total
        deleted += history.tag_deletes
    assert pruned > 1000, "the generator stopped pruning R2 (%d)" % pruned
    assert held > 100, "the generator stopped holding promotion candidates (%d)" % held
    assert deleted > 1000, "the generator stopped deleting tags (%d)" % deleted


# --------------------------------------------------------------------------- controls: each MUST go red ---------------------------------------------------------------------------


def _incident(stable_index: int, count: int = 22) -> tuple[list[str], set[str], list[str]]:
    """`count` releases, R2's tracker applied release by release with stable fixed at `history[stable_index]`. Returns (history, surviving sentinels, tags newest first with `production` newest of all)."""
    history = versions(count)
    tracker: list[str] = []
    sentinels: set[str] = set()
    for version in history:
        sentinels.add("v" + version)
        plan = rc.tracker_retention_plan(tracker, version, history[stable_index])
        tracker = list(plan.kept)
        sentinels -= {"v" + v for v in plan.pruned}
    return history, sentinels, ["production", *_tags(history)]


def _prefix_rule(names: list[str], keep: int = KEEP) -> set[str]:
    """Housekeeping before 2026-10-08: the newest `keep` tags of any kind survive."""
    return set(names[:keep])


def test_control_the_10_07_rule_breaks_the_bijection() -> None:
    """THE REPLAY. Twenty sentinels in R2, and `production` newest among the tags: the pre-fix rule keeps `production` plus 19 release tags, so the oldest sealed release loses its tag. The contract's rule keeps all twenty."""
    history, sentinels, names = _incident(stable_index=-2)
    assert len(sentinels) == KEEP, "the replay no longer holds twenty sentinels"
    lines, code = bijection(sentinels, _prefix_rule(names))
    assert code == 1, "the control stayed green: %s" % lines
    assert "DRIFT v%s: cli sentinel present, git tag missing" % history[2] in lines
    plan = rc.tag_retention_plan(names, stable=history[-2])
    assert bijection(sentinels, {v.name for v in plan.verdicts if v.kind != rc.DELETE})[1] == 0


def test_control_an_in_walk_version_outside_the_window_breaks_the_old_rule() -> None:
    """Stable is the oldest release, so R2 holds the 21st-newest as a promotion candidate. The pre-fix rule (no `production` this time, a clean 20) deletes its tag; the contract holds it."""
    history, sentinels, names = _incident(stable_index=0)
    names = names[1:]
    assert "v" + history[1] in sentinels, "R2 stopped holding the candidate"
    lines, code = bijection(sentinels, _prefix_rule(names))
    assert code == 1, "the control stayed green: %s" % lines
    plan = rc.tag_retention_plan(names, stable=history[0])
    assert plan.verdict("v" + history[1]).kind == rc.HELD
    assert bijection(sentinels, {v.name for v in plan.verdicts if v.kind != rc.DELETE})[1] == 0


def test_control_a_mismatched_keep_constant_breaks_the_bijection() -> None:
    """The two windows MUST be one constant. A tag window one short of the tracker's deletes a sealed release's tag whenever nothing else holds it (no listing handed in). With the sentinel set handed in, the hold still saves it: the sentinel guard is the second line, not a substitute for agreeing."""
    history, sentinels, names = _incident(stable_index=-1)
    short = rc.tag_retention_plan(names, stable=history[-1], keep=KEEP - 1)
    lines, code = bijection(sentinels, {v.name for v in short.verdicts if v.kind != rc.DELETE})
    assert code == 1, "the control stayed green: %s" % lines
    guarded = rc.tag_retention_plan(names, stable=history[-1], keep=KEEP - 1, sentinels=sentinels)
    assert bijection(sentinels, {v.name for v in guarded.verdicts if v.kind != rc.DELETE})[1] == 0


def test_control_the_generator_finds_the_old_rule_and_the_unguarded_rule() -> None:
    """The property test's own control: over the same seeds, the pre-fix rule and the contract WITHOUT a sentinel guard (`window` mode: a promotion between an upload and a housekeeping run moves `in_walk` past a candidate R2 still holds) must each produce drift. If either stays green the generator is not producing the states the property is about."""
    prefix = sum(1 for seed in SEEDS if _replay(seed, "probe", prefix_rule=True)[1])
    window = sum(1 for seed in SEEDS if _replay(seed, "window")[1])
    mismatched = sum(1 for seed in SEEDS if _replay(seed, "window", tag_keep=KEEP - 1)[1])
    assert prefix > 0, "the pre-fix rule never broke a generated history"
    assert window > 0, "housekeeping without its sentinel guard never broke a generated history"
    assert mismatched > 0, "a mismatched keep constant never broke a generated history"


def test_control_the_oracle_is_the_real_gate() -> None:
    """A planted drift reads as drift, and a clean state as clean, through the very function the gate calls."""
    assert bijection({"v1.0.0", "v1.0.1"}, {"v1.0.0", "v1.0.1", "production"})[1] == 0
    lines, code = bijection({"v1.0.0", "v1.0.1"}, {"v1.0.1"})
    assert code == 1
    assert any(
        re.match(r"DRIFT v1\.0\.0: cli sentinel present, git tag missing", line) for line in lines
    )
