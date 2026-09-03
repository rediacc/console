# PLAN: The client-bundle budget silently drops 124 KB, and that is the "nondeterminism"
Status: draft
Owner: 74de73ca
Updated: 2026-09-03

## Recommendation, in one line

`scripts/check-client-bundle-budget.ts:62` matches `/\bimport\s+["']/`, but rollup emits
bare side-effect imports with **no** space (`import"./x.js"`). The homepage's script entry
is a 129-byte facade whose only three edges are all that form, so the graph walk dead-ends
and 124,673 B goes unmeasured. Fix the regex. The 082f7aa94 "failure" was the gate telling
the truth for the first time; the passing runs are the defect.

## 1. What was measured

Read-only, against `packages/www/dist` as it stands in this checkout. No build was run.
The walk was exercised through the real gate, changing exactly one character at `:62`:

| walk over the SAME dist | bytes | files | TutorialVideoPlayer counted |
|---|---|---|---|
| current regex `\bimport\s+["']` | 451,621 | 28 | no |
| `\bimport\s*["']` | **576,294** | **30** | yes |

Identical for all thirteen locales in both directions. Reproduced independently by the
implementing session, not only by the planning agent.

The dead end, `packages/www/dist/assets/SPHomePage.astro_astro_type_script_index_0_lang.CR4GYgGZ.js`,
129 bytes in full:

    import"./PersonaPage.astro_astro_type_script_index_0_lang.pSt9yPWT.js";import"./index.elwlu7WY.js";import"./client.Csvl6prW.js";

Three edges, all invisible to the gate. Behind them, a 2,563 B shared chunk carries
`import("./TutorialVideoPlayer.FcNaUbde.js")` -> 122,110 B of `plyr` plus the player.

The blind spot is systemic, not incidental: **49 no-space side-effect edges across 20
files** in the current dist:

    grep -rohE 'import"[^"]+"' packages/www/dist/assets packages/www/dist/scripts | wc -l

Note that `:60` (`from`) and `:61` (`import(`) both already use `\s*`. Only `:62` requires
whitespace, so the inconsistency is visible inside the same six-line function.

## 2. The mechanism (CONFIRMED)

Two chunk shapes exist for the homepage's inline script, and rollup picks between them:

- **facade shape** (this checkout): a 129 B stub -> the 2,563 B shared chunk. All the
  stub's edges are `import"..."`. Gate reads **451,621 / 28**.
- **merged shape** (CI run 33708505104): no stub; the homepage's `script src` names the
  2,563 B chunk directly, and that chunk's `import(...)` edge IS matched by `:61`.
  Gate reads **576,165 / 29**.

The arithmetic closes to the byte:

    451,621 - 129 + 2,563 + 122,110 = 576,165     (CI's exact figure)
    28 - 1 + 1 + 1 = 29                            (CI's exact file count)
    576,294 - 576,165 = 129                        (the stub, present here, absent there)

`TutorialVideoPlayer.FcNaUbde.js` has the **same hash and the same 122,110 bytes** in both
runs. Identical hash means identical chunk content means identical module graph. That rules
out, as causes of the swing: `remark-tutorial-embed.ts` ordering, `video-manifest.json`
ordering, and any content-level build nondeterminism. Only the facade shape moved.

**Why** rollup varies it is the one open hypothesis (entry registration order for Astro
page scripts). It is no longer load-bearing: after the fix both shapes measure within 129 B
of each other and both exceed 500,000.

### 2.1 The 122 KB is real, not an artefact

- `packages/www/src/components/solution-pages/SPHomePage.astro:78` loads
  `../../scripts/tutorial-video-hydrate.ts`
- `SPHomeVideo.astro:25` renders `SPSolutionVideo`, which emits `class="video-player-mount"`
- `dist/en/index.html` contains exactly one such mount, with `data-video-src`
- `tutorial-video-hydrate.ts:27` returns early only when there are zero mounts; there is
  one, so the `import()` fires on DOMContentLoaded

Every homepage visitor in every locale downloads `plyr`. The honest figure is 576,294 B,
1.15x the 500,000 B budget.

## 3. Why not a tolerance band, and why not "pin the build" first

A tolerance band is the wrong instinct, and the reason is not the false RED. The dangerous
half is that **the green was equally unreliable** -- and here that is not hypothetical: a
genuine 122 KB of eager JavaScript has been shipping under a passing gate.

"Make the build deterministic" is also the wrong first move. The build's variance is 129 B
and one facade chunk; it produced a 124 KB swing only because it happened to route around a
measurement blind spot. Pin the build and the gate still cannot see 49 edges. Fix the
measurement and the residual wobble is 0.02% and cannot change a verdict.

Raising the budget is out of scope and would be wrong anyway: the gate's own header says a
budget set just above today's figure is a gate that ratifies the defect.

## 4. The fix, in priority order

### Step 1 (non-negotiable) -- the measurement

At `scripts/check-client-bundle-budget.ts:62`, `\s+` becomes `\s*`, with the reason stated
inline. `\s*` adds no false positives: `import(` cannot match (a paren is not a quote) and
`import.meta` has no quote; `from"..."` is already covered by `:60`.

The header comment (`:1-29`) is stale in both directions and gets rewritten: its byte figure
predates locale chunking, and its "RED on purpose" paragraph describes a gate that has been
green by accident.

### Step 2 -- controls that would have caught this (section 5)

### Step 3 -- the consequence, and keeping the required lane honest

`check:ci-client-bundle-budget` is a hard CI step (`ci-quality.yml`, job `quality-www-build`,
step `SEO`). Landing Step 1 alone turns it RED and blocks every PR, correctly. Two honest
exits, in order of preference:

**3a (preferred): split eager from deferred, and make the deferral REAL.** Measured on the
current dist: eager 454,184 B / 29 files; full closure 576,294 B / 30; deferred-only
122,110 B / 1. Report both, apply the 500,000 B budget to the eager figure, and assert the
deferred figure against its own stated ceiling so it is named rather than averaged away.

This is only honest if the deferral is genuine, and today it is not: the hydrator mounts on
DOMContentLoaded, so the "deferred" chunk is fetched by every homepage visitor. 3a must be
paired with gating `hydrateTutorialVideos()` on an IntersectionObserver over the mount (or
first interaction). **Without that pairing 3a is a fudge.**

That pairing is a USER-FACING behaviour change -- the homepage video would no longer
preload -- which makes it the operator's call, not this session's. See section 7.

**3b (fallback, and what this session takes as the default): rewire, do not soften.**
Change the manifest `ci:` block from `kind: 'step'` to `kind: 'test'`, this repo's own
documented pattern for a gate that is correctly RED on the real tree (precedent:
`check:ci-hydration-clean`). The gate keeps running every CI run and keeps its ability to
fail; what it stops doing is blocking every unrelated PR on a pre-existing product defect.
It carries a BLOCKER naming the 576,294 B figure and the deferred decision.

3b is a real reduction in blocking coverage and is recorded as such in
`docs/agent-reference/suppressions.md`, not taken silently.

### Step 4 -- name the chunk, do not just total it

Report every reachable chunk at or above 20,000 B on both the pass and fail paths, and
assert the hash-stripped set is identical across all thirteen locales. That is an intrinsic
invariant needing no committed baseline, and it fails by name when one locale acquires a
chunk the others do not. The 20,000 B floor sits deliberately above the facade wobble
(129 B) and the shared script chunk (2,563 B), so rollup's variance cannot flip it.

## 5. How it is proven

### 5.1 In the gate's own `--selftest`

The existing fixture is why this was never caught: it writes `import { x } from "./heavy.js"`
-- spaced, and via `from`. The minified no-space form was never exercised. Add:

- **PLANT:** an entry chunk that is a pure facade containing only
  `import"./mid.js";import"./client.js";` -- no whitespace, no `from` -- and assert
  `heavy.js` is still reached through it. This is the exact 28->30 shape.
- **PLANT:** a chunk reached only through `import("./x.js")` from behind such a facade.

Both fail on the pre-fix gate and pass after Step 1.

### 5.2 A new `.ci/scripts/test/gates/test-client-bundle-budget.sh`

Glob-discovered by `run-all.sh`. Four cases:

1. `--selftest` exits 0 and names both new plants.
2. **Mutant:** reverting `\s*` to `\s+` on a copy must make `--selftest` exit 1 and name the
   facade plant. This is the control proving the control can fail.
3. **Anti-vacuity against the real dist when one exists:** at least one no-space
   side-effect edge must have been followed (there are 49). Skip cleanly, never silently,
   when `packages/www/dist` is absent.
4. The heavy-chunk set from Step 4 is identical across all thirteen locales.

### 5.3 Repeat-build determinism (the cheapest real proof of section 2's open half)

Writes `packages/www/dist`, a declared `mutex` resource shared with other sessions in this
checkout. Run deliberately, coordinating first:

    npm run build:www && cp -r packages/www/dist /tmp/dist-A
    rm -rf packages/www/dist && npm run build:www && cp -r packages/www/dist /tmp/dist-B
    stat -c '%s %n' /tmp/dist-{A,B}/assets/*astro_type_script*

Pass condition: identical heavy-chunk sets and totals within 129 B. If one build shows a
129 B facade and the other ~2,563 B, the facade merge is confirmed as the varying quantity.

### 5.4 Anti-vacuity registry

`test-gate-anti-vacuity.sh` already registers this gate's refusal path. Confirm it still
passes after Step 1; the refusal paths are untouched.

## 6. Wiring

The gate is already wired at all three points (`package.json` key reached via the
`check:ci-seo` chain, a `scripts/ci-runner/manifest.ts` entry, and the `SEO` step in
`ci-quality.yml`). The new gate test needs its own three points, mirroring the other
`gate-test:*` entries: the file, a `gate-test:client-bundle-budget` manifest entry with
`qualityGateTest: true`, and nothing further in the workflow -- the "Quality-gate unit
tests" step already runs the whole battery. Run `check:ci-parity` and
`check:ci-gate-manifest` after the manifest edit.

## 7. What is NOT this session's call

The 122,110 B is a real product defect: every homepage visitor downloads a video player
they may never use. Fixing it properly means deferring hydration until the mount is in view,
which changes when the homepage video becomes ready. That is a user-facing trade-off and it
belongs to the operator, so it is parked rather than taken. This plan's default keeps the
measurement honest and the gate able to fail while that decision waits.

## 8. What this plan deliberately does not do

- Does not raise the 500,000 B budget.
- Does not add a tolerance band or a byte-delta baseline.
- Does not pin rollup's chunking; the variance is 129 B once the measurement is correct.
- Does not touch `remark-tutorial-embed.ts` or `video-manifest.json` -- identical chunk
  hashes across both CI runs rule them out.
