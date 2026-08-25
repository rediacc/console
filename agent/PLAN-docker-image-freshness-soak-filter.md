# PLAN: docker image freshness must soak on release age, not rebuild age
Status: done
Owner: 854ac1c6
Updated: 2026-08-25

## The defect

`scripts/check-docker-image-freshness.ts:328-330` decides whether a pin is stale:

```ts
const newer = tags
  .filter((t) => isNewer(p.tag, t.name))
  .filter((t) => !(t.pushedMs !== null && isWithinFreshnessWindow(t.pushedMs, now, win)));
```

The second filter implements the `minimum-release-age` soak (1440 minutes, from
`.npmrc`): a version that has only just been released should not fail CI before
it has baked. Sound intent, wrong clock.

`pushedMs` comes from Docker Hub's `tag_last_pushed`
(`scripts/check-docker-image-freshness.ts:177-180`, `listHubTags`). For Docker
Official Images that is a **rebuild** timestamp, not a release date. The Python
image rebuilds every supported minor on a schedule, so a single rebuild wave
re-stamps `3.10-slim` through `3.15-rc-slim` within the same minute.

Measured 2026-08-25 against `library/python` (3911 tags, window of 100 newest by
`last_updated`) for the pin at
`packages/json/templates/networking/cloud-switch/web/Dockerfile:2  python:3.9-slim`:

    3.15.0rc1-slim   pushed  1.1h ago    INSIDE 24h soak
    3.14-slim        pushed  1.2h ago    INSIDE 24h soak
    3.13-slim        pushed  1.2h ago    INSIDE 24h soak
    3.12-slim        pushed  1.2h ago    INSIDE 24h soak
    3.11-slim        pushed  1.2h ago    INSIDE 24h soak
    3.10-slim        pushed  1.3h ago    INSIDE 24h soak

Every candidate newer than 3.9 was soaked, so `newer` came back empty and the
gate reported the pin as no longer stale. Python 3.10 is not a fresh release
needing time to bake; it is years old.

## Why it matters

The baseline is shrink-only, so this oscillates and costs a CI cycle each way:

- Inside a rebuild wave: baselined pins read "no longer stale" and the gate
  fails, demanding a drain.
- 24 hours later: the same pins read stale again and the gate fails with "newly
  stale past the soak window".

Three drains were demanded in one session (2026-08-25, landing console#574):
`node:22-slim`, `golang:1.26-bookworm`, `python:3.9-slim`. Two were committed
before the mechanism was understood, on a verification that checked the *pin's
own* push date rather than whether a newer tag existed, which does not bear on
staleness at all. Both will flip back.

## The fix

Soak the **newest available version only**. A rebuild of an established series
is not a release; the thing the soak exists to protect against is a brand-new
version appearing minutes ago.

In `scripts/check-docker-image-freshness.ts`, replace the unconditional soak
filter with: sort the newer candidates newest-first (the file already has this
comparator at :332), drop the single newest if it is inside the window, and
treat whatever remains as evidence of staleness.

Behaviour in the two cases that matter:

| situation | candidates | old | new |
|---|---|---|---|
| rebuild wave, pin 3.9 | 3.10-3.15rc all rebuilt 1h ago | not stale (wrong) | stale via 3.14 (right) |
| genuine release, pin 3.13 | only 3.14, released 1h ago | not stale | not stale (soak still works) |

No state, no first-seen tracking, no new network calls.

## Tests — AS BUILT

Six cases, not the three first sketched, in the `--selftest` battery of the same
file (so they run inside `check:ci-docker-image-freshness`, which is reachable
from `npm run ci` via `manifest.ts:1940`). Three FAIL against the planted
original filter, verified by planting it in a copy and running it in-tree:

1. a rebuild wave does NOT hide an established newer series  *(fails pre-fix)*
2. the newest is the only soakable one, so the next one down is the evidence  *(fails pre-fix)*
3. with a third candidate, only ONE is dropped  *(fails pre-fix)*
4. CONTROL: a genuinely NEW release still soaks (sole candidate is the newest)
5. CONTROL: a newer tag past the soak counts, as it always did
6. CONTROL: an unknown push date is not silently treated as soaked

Case 2 corrects an expectation the design got wrong: with candidates `3.10` and
`3.14` both rebuilt, the evidence is **`3.10`**, not `3.14` — `3.14` is the
newest and therefore the soakable one. The rule drops exactly one candidate, so
the sketch's "must report STALE via 3.14" was wrong about which tag gets named.
Case 6 was added because `pushedMs === null` must not read as soaked.

## Rollout — AS BUILT

Landed in `3b05a20f` on branch `0825-1` (console#574), CI-only, no product code.

The rollout paragraph above was written before the fix ran against the real
tree, and it was wrong. It assumed the two spurious drains would stay drained.
They could not: with the clock corrected, both pins read stale again
immediately, so the gate failed with "newly stale past the soak window" — the
exact reversal this defect causes. The correct repair was to **restore the
baseline**, not to bump `node:22-slim` to 26 and `golang:1.26-bookworm` to 1.27
(a real dependency change, one of them inside a submodule, outside this PR).

`scripts/data/docker-image-freshness-baseline.json` is therefore now
byte-identical to `main`, verified with `diff`, and the gate passes with **no
drain at all** — which is what it should have done from the start. All four
entries remain known-stale and baselined; none of the three drains this session
was real.

An automated reviewer separately claimed `tag_last_pushed` "does not exist for
Docker official images". It does: 5/5 tags of `library/python` carry it (e.g.
`slim` → `2026-08-25T05:16:11.741565Z`). The defect was never an absent field,
only a misread one.
