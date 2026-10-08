"""The ONE retention contract for a CLI release: how many releases are kept, and which ones may never go.

TWO PRUNERS OWN ONE RELEASE'S LIFETIME, AND THEY USED TO DISAGREE. The R2 upload (`rediacc_ci.deploy.upload_to_r2`, every release) trims `cli/versions.json` and removes each pruned `cli/v<V>/`, sentinel included. Housekeeping (`rediacc_ci.housekeeping.cleanup_versions`, Phases 1 and 2, nightly) deletes old GitHub Releases and git tags. Each restated its own keep count and its own idea of what counts: housekeeping kept the newest 20 TAGS, and the non-semver `production` pointer took one of those slots, so only 19 release tags survived while R2 kept 20 sentinels plus every promotion candidate. The scheduled run of 2026-10-07 (37604651929) deleted tag v1.3.1 while `cli/v1.3.1/.released` stayed, and the release-state bijection (`release_state.assert_bijection`) went red on main (worklist #a5a1f981, `agent/plans/PLAN-cd-errors-in-ci.md` W1/W2).

So both pruners now ask THIS module, and the agreement is by construction rather than by coincidence:

  * `KEEP_RELEASES` is the only keep count. Neither caller restates it.
  * `tracker_retention_plan` is the R2 side: the newest `KEEP_RELEASES` versions, plus every version `check_soak_period.in_walk` may still select for promotion.
  * `tag_retention_plan` is the git side: the newest `KEEP_RELEASES` STRICT-SEMVER tags (a pointer tag such as `production` or a pre-release is counted in its own group and never takes a release slot), plus every tag whose sentinel is known to exist, plus every `in_walk` version.

`.ci/rediacc_ci/tests/test_release_retention_contract.py` drives both plans over generated release histories with `release_state.assert_bijection` as the oracle, and replays the 2026-10-07 rule as the control that must go red.

BOTH FUNCTIONS ARE PURE. They read nothing and print nothing: R2 probes, the stable-manifest read, the date window and the delete budget stay with the callers, which is what lets a pre-merge check (`cd_preflight`) project the next housekeeping run from live state without deleting anything.

UNKNOWN IS NEVER "PRUNABLE". `stable=""` (no manifest, an unreadable one, a `null` version) makes `in_walk` answer True for every version, so both plans hold everything outside the window and say why. A caller that wants to know whether a stable read is worth making asks the plan computed with `stable=""` (`TrackerPlan.held` / `TagPlan.needs_stable`): nothing there means nothing is outside the window, and no read is needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from rediacc_ci.release.check_soak_period import in_walk
from rediacc_ci.release.list_edge_releases import semver

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

# The one keep count. `.ci/config/constants.sh` `R2_MAX_RELEASE_VERSIONS` (read by the bash twin `upload-to-r2.sh`) is pinned to this by `test_deploy_upload_to_r2.test_the_max_release_versions_is_the_twins`.
KEEP_RELEASES = 20

# `^v[0-9]+\.[0-9]+\.[0-9]+$`: the release tags the bijection covers (`release_state.STRICT_SEMVER`).
_STRICT_SEMVER_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+$")

# Verdict kinds. A `keep` is inside the window; a `held` is outside it and protected; a `delete` is outside it and unprotected as far as the plan knows.
KEEP = "keep"
HELD = "held"
DELETE = "delete"

# Reasons. `REASON_STABLE_UNKNOWN` is the fail-closed hold: a caller treats it as UNCHECKED, not as a settled keep.
REASON_WINDOW = "inside the newest %d %s"
REASON_SENTINEL = "its sentinel cli/%s/.released still exists"
REASON_CANDIDATE = "newer than stable v%s, a promotion candidate"
REASON_STABLE_UNKNOWN = "the stable version is unknown (cli/stable/manifest.json unreadable)"
REASON_OUTSIDE = "outside the newest %d %s"
REASON_NO_CONTRACT = "outside the newest %d %s (no release contract for this repo)"


def is_release_tag(name: str) -> bool:
    """A strict-semver `vX.Y.Z`: the tags the release contract and the bijection cover."""
    return bool(_STRICT_SEMVER_RE.match(name))


def _tag(version: str) -> str:
    """`1.2.3` and `v1.2.3` as the tag spelling `v1.2.3`."""
    return version if version.startswith("v") else "v" + version


def stable_known(stable: str) -> bool:
    """Whether `stable` names a plain release version (`in_walk`'s own test)."""
    return semver(stable) is not None


def candidate_reason(stable: str) -> str:
    """Why an `in_walk` version outside the window is held. The text the R2 upload has always logged."""
    if stable_known(stable):
        return REASON_CANDIDATE % stable.lstrip("v")
    return REASON_STABLE_UNKNOWN


@dataclass(frozen=True)
class TrackerPlan:
    """The R2 tracker after one upload.

    `kept` is the new `cli/versions.json`, in order: the window, then every held candidate in tracker order. `pruned` is every version whose `cli/v<V>/` (and snapshot) goes. `held` is the candidates kept outside the window, as `(version, reason)`.
    """

    kept: tuple[str, ...]
    pruned: tuple[str, ...]
    held: tuple[tuple[str, str], ...]


def tracker_retention_plan(
    tracker: Sequence[str], new_version: str, stable: str, keep: int = KEEP_RELEASES
) -> TrackerPlan:
    """The `cli/versions.json` retention for an upload of `new_version`.

    `tracker` is the current list, newest first, as R2 holds it. `new_version` is prepended unless already present (a re-release keeps its place, which is what makes a stable promotion of an existing edge version a no-op for the window). The first `keep` entries stay; of the rest, every version `in_walk(version, stable)` answers True for is held (appended after the window) and the others are pruned. `stable=""` holds everything outside the window.
    """
    updated = list(tracker) if new_version in tracker else [new_version, *tracker]
    window = updated[:keep]
    pruned: list[str] = []
    held: list[tuple[str, str]] = []
    for version in updated[keep:]:
        if in_walk(version, stable):
            held.append((version, candidate_reason(stable)))
        else:
            pruned.append(version)
    return TrackerPlan(
        kept=tuple(window) + tuple(v for v, _ in held), pruned=tuple(pruned), held=tuple(held)
    )


@dataclass(frozen=True)
class Verdict:
    name: str
    kind: str
    reason: str


@dataclass(frozen=True)
class TagPlan:
    """Every tag's verdict, in the order given.

    `delete` means "unprotected as far as this plan knows". A caller that passed no complete sentinel listing (housekeeping asks R2 per tag) MUST still probe each `delete` before acting on it; the plan does not know what it was not told.
    """

    verdicts: tuple[Verdict, ...]

    @property
    def keep(self) -> tuple[Verdict, ...]:
        return tuple(v for v in self.verdicts if v.kind == KEEP)

    @property
    def held(self) -> tuple[Verdict, ...]:
        return tuple(v for v in self.verdicts if v.kind == HELD)

    @property
    def delete(self) -> tuple[Verdict, ...]:
        return tuple(v for v in self.verdicts if v.kind == DELETE)

    @property
    def needs_stable(self) -> bool:
        """True when some verdict is held ONLY because the stable version is unknown, i.e. a stable read could change the plan."""
        return any(v.kind == HELD and v.reason == REASON_STABLE_UNKNOWN for v in self.verdicts)

    def verdict(self, name: str) -> Verdict:
        for v in self.verdicts:
            if v.name == name:
                return v
        raise KeyError(name)


def tag_retention_plan(
    tags: Sequence[str],
    *,
    stable: str,
    sentinels: Collection[str] = (),
    keep: int = KEEP_RELEASES,
    contract: bool = True,
) -> TagPlan:
    """The retention verdict for every tag (or GitHub Release, by its tag name) of one repo.

    `tags` is newest first, in the caller's own order (Phase 2 dates tags, Phase 1 sorts Releases by `createdAt`). Strict-semver tags are counted among strict-semver tags only, and every other tag (`production`, a pre-release) among the others, so a pointer tag never takes a release slot. The newest `keep` of each group are kept.

    Outside the window, when `contract` holds (the console repo, whose releases write `cli/<tag>/.released`), a strict-semver tag is HELD when its sentinel is in `sentinels` (`vX.Y.Z` or `X.Y.Z`, the versions KNOWN to be sealed) or when `in_walk(tag, stable)` (a promotion candidate, or `stable` unknown); otherwise it is a DELETE. A non-semver tag outside its window is a DELETE: it is outside the bijection. With `contract=False` (renet: no sentinels, no promotion walk) every tag outside its window is a DELETE.
    """
    sealed = {_tag(v) for v in sentinels}
    index = {True: 0, False: 0}
    out: list[Verdict] = []
    for name in tags:
        release = is_release_tag(name)
        position = index[release]
        index[release] += 1
        group = "strict-semver tags" if release else "non-release tags"
        if position < keep:
            out.append(Verdict(name, KEEP, REASON_WINDOW % (keep, group)))
            continue
        if not (contract and release):
            reason = REASON_OUTSIDE if contract else REASON_NO_CONTRACT
            out.append(Verdict(name, DELETE, reason % (keep, group)))
            continue
        if name in sealed:
            out.append(Verdict(name, HELD, REASON_SENTINEL % name))
        elif in_walk(name, stable):
            out.append(Verdict(name, HELD, candidate_reason(stable)))
        else:
            out.append(Verdict(name, DELETE, REASON_OUTSIDE % (keep, group)))
    return TagPlan(tuple(out))
