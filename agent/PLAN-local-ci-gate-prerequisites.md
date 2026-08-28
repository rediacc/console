# PLAN: two gates read packages/www/dist and never said so
Status: executing
Owner: 9d92d9b6
Updated: 2026-08-28

## 0. The finding, measured

`npm run ci:quick` reported `check:ci-landmarks` and `check:ci-ssr-locale` as
**failed** on a tree where nothing is wrong with them:

    ✗ zero built pages found; the gate is not seeing the build.
    ✗ zero probes were comparable. The gate verified nothing; its green would be
      meaningless.

`packages/www/dist` exists and holds **zero** `.html` files. Measured
2026-08-28 on `da2ecc5b5`. Their refusal is CORRECT — a gate that cannot see its
input must not report green. The defect was the runner's CLASSIFICATION of that
refusal, which cost `da2ecc5b5` two carried-red entries.

## 1. MY FIRST DIAGNOSIS WAS WRONG, and the correction is the whole point

The first draft of this plan proposed a new `needs: {path, glob, satisfy}`
field plus a `prerequisiteSatisfied()` branch in `run.ts`. **None of that was
needed, and building it would have been a second mechanism beside a working
one.**

Reading the tree instead of designing against it:

- `GateSpec.needs?: string[]` **already exists** (`manifest.ts:32`) as ordering
  edges: "ids that must succeed first".
- `build:www` **already exists** as a gate node (`manifest.ts:2967`,
  `slow: true`, 131.9s measured).
- **Seven sibling gates that read dist already declare `needs: ['build:www']`** —
  `check:ci-seo`, `check:ci-docs-render-parity`, `check:ci-redirects`,
  `check:ci-anchor-integrity`, `check:ci-client-bundle-budget` and others.
- `manifest.ts:2218` states the rule outright: *"build:www is not an
  optimisation: without dist it REFUSES rather than self-skipping."*
- The `blocked` status is fully plumbed already: `pool.ts:35` and `:275`,
  `report.ts:89-178`, `run.ts:643` and `:816`.

So `check:ci-landmarks` and `check:ci-ssr-locale` were simply **missing a
declaration that every one of their siblings has**. The fix is two `needs`
lines, not a feature.

## 2. The sweep, and the one candidate that was NOT a member

Class: a gate whose script reads `packages/www/dist` without declaring
`needs: ['build:www']`. Swept by mapping every dist-reading script under
`scripts/` onto its manifest entry:

| gate | leaf | declared? |
|---|---|---|
| check:ci-seo | check-seo, check-client-bundle-budget | yes |
| check:ci-docs-render-parity | check-docs-render-parity | yes |
| check:ci-redirects | check-anchor-integrity, check-redirect-integrity | yes |
| check:ci-anchor-integrity | check-anchor-integrity | yes |
| check:ci-client-bundle-budget | check-client-bundle-budget | yes |
| **check:ci-landmarks** | check-landmarks | **NO** |
| **check:ci-ssr-locale** | check-ssr-locale | **NO** |
| ~~check:i18n~~ | — | FALSE POSITIVE |

`check:i18n` matched only on
`scripts/__tests__/check-docs-render-parity.control.ts` — a CONTROL running
against a fixture, not the real dist. Confirmed by evidence rather than by
reading: it passed in both `ci:quick` runs while the other two failed. **It was
checked, not "fixed".** Class size: exactly 2.

## 3. What landed

1. `needs: ['build:www']` on both entries, each with a comment saying WHY it is
   not an optimisation (matching the sibling convention at `:2218`).
2. `.ci/config/carried-reds.json` emptied. This is mandatory, not tidying: a
   carried entry whose gate stops failing is STALE, and a stale entry REFUSES
   the next push by design.

## 4. Verification

- `check:ci-parity` — 323 manifest gates, agree in both directions. GREEN.
- `ci-runner --selftest` — 21 assertions. GREEN.
- `ci:quick` — the two gates must no longer appear in the receipt's `failed`
  array; `--quick` defers gates whose prerequisite is slow, which is precisely
  what the seven siblings already do.
- The push guard reads `.failed`, so an empty `failed` needs no carried entry.

## 5. What could NOT be determined

Whether `blocked` should count toward the runner's exit code. It does not
today. That question is now moot for this finding — these two gates are
DEFERRED behind a slow prerequisite rather than blocked — but it remains open
for a gate that is genuinely unrunnable on a given machine, where a
permanently-unsatisfiable prerequisite could go quiet.

## 6. The lesson worth keeping

A plan's claim about code it has not read is a hypothesis. This one proposed
building a mechanism that already existed, was already documented in a comment,
and was already used by seven neighbours. The tree answered the question in one
grep.
