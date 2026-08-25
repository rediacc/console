# PLAN: docker image freshness must soak on release age, not rebuild age
Status: executing
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

## Tests

Added to the existing `--selftest` battery in the same file, which already runs
as part of `check:ci-docker-image-freshness`:

1. **Fires on the defect**: pin `3.9-slim`, candidates `3.10-slim`/`3.14-slim`
   both pushed 1h ago, no unsoaked candidate. Must report STALE. Under the old
   filter this returns not-stale, so it fails before the fix and passes after.
2. **Soak still holds**: pin `3.13-slim`, single candidate `3.14-slim` pushed
   1h ago. Must report NOT stale. Guards against "fixed it by deleting the
   soak", which would make every upstream release redden CI instantly.
3. **Unsoaked candidate still counts**: pin `3.9-slim`, candidate `3.10-slim`
   pushed 40 days ago. Must report STALE, both before and after.

## Rollout

Rides console#574 (docs/CI-only, no product code). After it lands, the two
spurious drains stay drained; the corrected gate will re-flag them as newly
stale on the next run, which is the correct signal and the point at which those
pins get bumped or re-baselined deliberately.
