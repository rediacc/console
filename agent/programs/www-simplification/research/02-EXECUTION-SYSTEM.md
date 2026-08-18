# www simplification, the execution system

**Status:** design. **Nothing here is implemented. Nothing in `packages/www` is
modified.** **Date:** 2026-08-17. **Author:** `sx-process`.

**Inputs:** `00-BRIEF.md`, `README.md`, `01-SYNTHESIS.md`, the repo's `CLAUDE.md`
Session Defaults, plus 14 facts measured live for this document and listed in
§10. Where a claim here is measured, it says so. Where it is designed but not
yet proven, it says that too, and gives the one command that settles it.

Read §1 and §2, then follow §5 as a checklist.

---

## 1. The hazard, stated exactly

There is one Astro dev server (`http://localhost:4321`, pid 1170158), serving one
working tree, with hot module replacement. `agent-browser` isolates *browsers*
per agent. Nothing isolates *the thing under test*.

So the moment implementation starts:

1. `sx-tokens` saves `public/styles/main.css`.
2. Vite pushes the new CSS to every connected client within milliseconds.
3. `sx-primitives`, mid-way through a before/after measurement on an unrelated
   page, reads the merged state.
4. Its number is wrong, and **nothing reports an error**. It writes a confident
   figure into a research document, and that figure survives into the final
   report because nobody can tell by looking.

Three properties make this worse than it sounds.

- **It is silent.** There is no exception, no warning, no changed exit code.
- **It is invisible in review.** The corrupted artifact is a number in a
  markdown table. The diff that caused it is in another agent's files.
- **File-disjointness does not help.** The repo rule caps writers at 2 with
  disjoint file ownership. That prevents *edit* collisions. It does nothing
  about *observation* collisions, because the dev server renders one merged
  document. `main.css` is global: a token change by one writer repaints every
  page every other writer is looking at.

There is a second, larger hazard the brief did not name, and it is already
proven: **a build run in the shared tree corrupts the shared tree.**
`astro.config.mjs:26` runs `node scripts/generate-search-index.js` on
`astro:build:start`, and `packages/www/scripts/generate-search-index.js:79-84`
does `fs.unlinkSync` on every file matching `search-index*.json` in
`packages/www/public` before rewriting them. **Those 14 files are tracked in
git** (`git ls-files packages/www/public | grep search-index` returns 14). So
any agent running `npm run build:www` from the repo root deletes 14 tracked
files out of a shared tree that has no safety net, and the dev server serves 404
for `/search-index-<lang>.json` for the duration.

`astro.config.mjs:28` catches the failure and prints
`Failed to generate search index. Continuing with build...`, then the build
succeeds. Two concurrent builds can therefore race, one can lose its index
generation entirely, and **the build still exits 0**.

And the protection that looks like it covers this does not. `build:www` declares
`mutex: ['www-dist']` in `scripts/ci-runner/manifest.ts:321`, but the mutex is
an in-memory `Set` inside one runner process (`scripts/ci-runner/pool.ts:170`,
`:210`, `:232`). Two agents each running `npm run ci --only ...` are two
processes. **The mutex holds nothing between them.**

---

## 2. The isolation model, chosen

### 2.1 The decision

> **The dev server is for looking. The rig is for measuring. The rig is frozen
> while anyone measures it. No number from `localhost:4321` is ever evidence.**

Concretely:

- Writers keep editing the shared tree, freely, under the existing 2-writer
  disjoint-ownership rule. Nothing about how they work changes.
- `localhost:4321` stays up and stays useful, **reclassified as exploration
  only**. Look at it, click it, form intuitions from it. Never quote it. Never
  screenshot it into a document. Never put a number from it in a table.
- All evidence comes from a **frozen snapshot**: a static production build of a
  point-in-time copy of the tree, served on its own port, immutable for its
  lifetime, produced by exactly one agent at a wave boundary.

This does not *mitigate* the operator's hazard. It *removes* it. A measurement
cannot be corrupted mid-flight by another agent's save if measurements are never
taken against a surface another agent can write to.

### 2.2 Why this one and not the others

| Model | Wall clock | Risk it leaves | Verdict |
|---|---|---|---|
| **A. Strictly sequential single-writer turns on the dev server** | Worst. Serialises everything, including the four Wave 2 specialists whose files genuinely do not overlap. Roughly 2x to 4x the program's duration. | Depends entirely on discipline: one agent that saves while not holding the token silently corrupts a peer, with no detector. Also does not fix the *baseline* problem, since a "before" captured three waves ago on a mutating dev server is not comparable to anything. | Rejected. Pays the full cost of serialisation and still leaves the silent-corruption channel open. |
| **B. Per-agent static build, per agent, per iteration** | Each build is 221 s local EWMA (`.ci/cache/gate-durations.json`, `build:www`), at ~2.5 vCPU and 3.4 GB RSS (`.ci/scripts/quality/runner-sizing-baseline.json`). Two concurrent writers iterating is 5 vCPU and 7 GB on a machine already running three dev servers and a dozen Chrome instances. | Rigs drift. Agent A's rig does not contain agent B's landed token change, so A measures a world that does not exist and B's change looks like it did nothing. Trades one silent-wrong-number channel for another. | Rejected. Most expensive option, and it reintroduces the same class of defect. |
| **C. Frozen snapshot on one shared rig** (chosen) | 1 build per wave gate, not per agent per iteration. About 8 to 12 builds across the whole program. The rig payload is **112 MB** (measured, §10.6), so refreshing it is an rsync of seconds plus one build. | The failure mode moves to *staleness*: an agent can measure a snapshot that predates its own change. That failure is loud, not silent, because snapshot provenance is a recorded git SHA plus a patch, and §8.1 makes checking it a required gate step. | **Chosen.** |
| **D. Measure against `packages/www/dist` in the shared tree** | Cheapest of all. | The worst option available. It is the shared tree, so it is exactly the resource under contention, and building into it destroys 14 tracked files (§1). | Rejected outright. |

### 2.3 The argument that settles it

Even with no concurrency problem at all, **Wave 0 cannot be verified without a
rig.** Wave 0's entire deliverable is a byte reduction (6,998,912 B of JS down to
a claimed ~224 KB of locale payload). `RESEARCH-metrics.md` §7 already records
that the dev server is invalid for weight: 157 requests against 44, 10.8 MB of
unbundled JS against 23 bundled files, 150,334 B of injected inline `<style>`
against 1,276. It is a valid instrument for structure and an invalid one for
bytes.

So a production-shaped local build is not an isolation luxury. It is the only
way to measure the largest single win in the plan. The isolation comes free with
it.

---

## 3. The rig

### 3.1 What it is

A complete, runnable, throwaway copy of the parts of the repo that `packages/www`
and its gates need, living outside the shared tree, with its own `dist/`, its own
Astro caches, and its own port.

    RIG=/tmp/claude-1000/-home-muhammed-monorepo-console/<session>/scratchpad/rig
    SNAP=/tmp/claude-1000/-home-muhammed-monorepo-console/<session>/scratchpad/snapshots

**Sizing, measured (§10.6):** the rig payload is 112 MB
(`packages/www` 89 M, `.ci` 18 M, `scripts` 3.7 M, `workers` 492 K,
`packages/locales` 56 K, plus six root config files), because the 6.9 GB of
`public/assets/{videos,tutorials}` media is gitignored, R2-hosted, and not needed
for a build. CI builds without it. Free disk is 151 GB.

That number is the reason this design works. The shared tree's `packages/www/dist`
is currently 7.1 GB, almost all of it copied media. A rig that excludes media
produces a dist small enough that keeping every wave's snapshot on disk costs
nothing.

### 3.2 Why not a git worktree

A worktree is the textbook answer and it was the first thing considered. Three
facts push against it here:

1. **An agent cannot create one.** `.claude/hooks/pre-bash/block-worktree-add.sh`
   blocks `git worktree add` unconditionally from the assistant's Bash tool. It
   is an operator action, which puts a human on the critical path of every
   snapshot.
2. **This checkout is itself a submodule worktree.** `.git` is a *file* reading
   `gitdir: ../.git/modules/console`, and `git worktree list` shows the git dir
   is `/home/muhammed/monorepo/.git/modules/console`. Adding a worktree of a
   submodule is fiddlier than the usual case and would need the operator to get
   it exactly right.
3. **It does not solve the interesting problem.** A worktree is a checkout of a
   *commit*, and this program is uncommitted by standing rule. The rig has to
   carry the working tree, so a worktree still needs an rsync on top, plus a
   `node_modules` link. The worktree's only remaining advantage is git-native
   provenance, and §3.5 gets better provenance from a recorded SHA plus a patch
   file, because that is an artifact you keep rather than a state you query.

**So: no operator action is required for the rig.** See §9 for what genuinely
does need the operator.

### 3.3 R0, bring-up (run once, at program start)

**This step is DESIGNED, NOT YET PROVEN.** It is the one load-bearing mechanism
in this document that was not executed, because this session was scoped to design
and forbidden to modify. It has an acceptance test, and a fallback if it fails.

```bash
RIG=/tmp/claude-1000/-home-muhammed-monorepo-console/<session>/scratchpad/rig
SRC=/home/muhammed/monorepo/console
mkdir -p "$RIG"

# 1. Payload. Allowlist, not denylist: it is 112 MB and it stays that way.
rsync -a --delete \
  --exclude=node_modules --exclude=dist --exclude=.astro \
  --exclude='public/assets/videos' --exclude='public/assets/tutorials' \
  "$SRC/packages/www" "$SRC/packages/locales" "$RIG/packages/"
rsync -a --delete "$SRC/scripts" "$SRC/.ci" "$SRC/workers" "$RIG/"
cp "$SRC"/{package.json,package-lock.json,tsconfig.json,knip.jsonc,biome.json,eslint.config.js} "$RIG/"

# 2. Dependencies by symlink. No npm install, no network, no minimum-release-age.
ln -sfn "$SRC/node_modules" "$RIG/node_modules"
```

Node resolution from `$RIG/packages/www` walks up, finds no
`packages/www/node_modules`, and lands on `$RIG/node_modules`, which is the real
one. Astro will create `$RIG/packages/www/node_modules/.astro` for its
`cacheDir` (default `./node_modules/.astro` relative to root,
`node_modules/astro/dist/core/config/schemas/base.js:12`); an otherwise-empty
`node_modules` directory does not stop Node's upward walk, so the symlinked root
still resolves every package.

**Acceptance test for R0. All four must pass before the rig is trusted:**

```bash
cd "$RIG/packages/www" && npx astro build 2>&1 | tail -20
#  expect: "Complete!", exit 0, and NO "Failed to generate search index"

test -f "$RIG/packages/www/dist/route-manifest.json" && echo MANIFEST-OK
#  proves the astro:build:done integrations ran with a correct cwd

git -C "$SRC" status --porcelain packages/www
#  expect: EMPTY. Proves the rig build did not touch the shared tree.
#  This is the control. If it prints 14 search-index lines, the rig leaked.

cd "$RIG/packages/www" && npx astro preview --port 4331 --host 127.0.0.1 &
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:4331/en   # expect 200
```

**Why `--root` and `--outDir` are not the shortcut they look like.** `astro build
--outDir <elsewhere>` fails on this project. `src/integrations/json-generator.ts:24`
and `src/integrations/route-manifest-generator.ts:16` both compute their `execSync`
cwd as `new URL('..', outDir)`, so an out-of-tree `--outDir` sets cwd to a
directory with no `scripts/`, and `astro:build:done` throws. Worse,
`packages/www/scripts/generate-json.js:12` hardcodes
`path.join(projectRoot, 'dist', 'json')` and `:334` does `fs.rmSync` on it, so a
build redirected elsewhere **still deletes the shared tree's `dist/json`**. A
separate root is the only clean isolation; `--outDir` is a trap.

**Fallback if R0 fails:** escalate to the operator for
`git worktree add` (§9, item O1), then apply the same `node_modules` symlink and
the same acceptance test inside the worktree. Do not attempt `npm install` in the
rig: `.npmrc` sets `ignore-scripts=true` and `minimum-release-age=1440`, and a
fresh install would need `npm run install:natives` afterwards for no benefit.

### 3.4 R1, refresh (run at every wave gate, by the gate owner only)

```bash
rsync -a --delete \
  --exclude=node_modules --exclude=dist --exclude=.astro \
  --exclude='public/assets/videos' --exclude='public/assets/tutorials' \
  "$SRC/packages/www" "$RIG/packages/"
cd "$RIG/packages/www" && npx astro build
```

**Exactly one agent refreshes the rig, and only at a gate.** A refresh during a
measurement is the same hazard this whole design exists to remove, just moved. If
two agents both hold a reason to refresh, the wave gate is misdesigned; stop and
fix the sequencing.

### 3.5 R2, snapshot (immediately after every refresh)

A snapshot is a named, immutable, self-describing copy of a rig build.

```bash
S=S1                      # S0, S1, S2 ... never reused, never overwritten
mkdir -p "$SNAP/$S"
cp -al "$RIG/packages/www/dist" "$SNAP/$S/dist"      # hardlinks: near-free

# Provenance. This is what makes staleness detectable instead of silent.
git -C "$SRC" rev-parse HEAD                > "$SNAP/$S/HEAD.sha"
git -C "$SRC" diff HEAD -- packages/www     > "$SNAP/$S/www.patch"
git -C "$SRC" diff --stat HEAD -- packages/www > "$SNAP/$S/www.stat"
date -u +%Y-%m-%dT%H:%M:%SZ                 > "$SNAP/$S/captured.utc"

chmod -R a-w "$SNAP/$S"   # an accidental overwrite now FAILS instead of succeeding
```

`HEAD.sha` plus `www.patch` is a complete, checkable description of what was
built. It is strictly better provenance than a worktree's `git status`, because
it is an artifact that persists rather than a state you have to remember to
query. §8.1 turns it into a gate check.

**S0 is special and it is on the critical path.** `packages/www` is clean right
now: `git status --porcelain packages/www` returns nothing (measured, §10.5). So
today `HEAD == working tree` for www, and S0 is exactly HEAD. **Capture S0 before
the first implementation edit lands.** If that is missed, S0 is still
recoverable, because `git archive HEAD -- packages/www | tar -x -C $RIG` rebuilds
it from HEAD at any time, but only for as long as nobody commits. Capture it
early anyway.

### 3.6 Ports

| Port | Owner | Purpose |
|---|---|---|
| 4321 | existing dev server, pid 1170158 | exploration only, never evidence |
| 4801, 4802, 4800 | in use by other node processes | do not touch |
| **4331** | the rig | `astro preview`, the current snapshot |
| **4332 to 4339** | reserved | serving an older snapshot side by side for an A/B |

Serving two snapshots at once on 4331 and 4332 is how you compare S0 against S2
without rebuilding either.

---

## 4. The visual regression baseline

### 4.1 The assertion, in falsifiable form

Not "the site still looks right". That is unfalsifiable and it is how visual
regression suites rot into a rubber stamp.

> **Every wave declares its blast radius in advance. The gate asserts zero pixel
> change on every captured surface OUTSIDE that radius.**

Inside the radius, change is expected and is adjudicated by eye. Outside it,
change is a regression by definition, no judgement required, and a machine
decides. That is what makes it a gate rather than an opinion.

Wave 1 (tokens) has a blast radius of *everything*, so its outside-set is empty
and its pixel gate is vacuous. **This is stated up front so nobody mistakes Wave
1's silence for a pass** (see §8.2). Wave 1 is gated by §7's numeric targets
instead. Waves 2 and later have small radii and get real pixel gates.

### 4.2 Determinism, measured

Full-page screenshots of `/en` at 1440x900 are **byte-identical**: sha256
`940dd417ed88cfa4340e2ed953e1e65cb88fd3af195d5487b5166278e1f192dd` across three
shots in one session, across a reload, and across a *fresh browser session*
(§10.3). So today, `sha256sum` is a free and exact zero-diff oracle. No
threshold, no tolerance, no flake.

**This expires at Wave 3.** Wave 3 turns on scroll-reveal motion, and
`RESEARCH-motion.md` records that `document.getAnimations()` currently returns 0
at load. Once elements animate, load-time screenshots stop being byte-stable.
That is a *predicted, dated* invalidation, not a surprise: from Wave 3 onward the
oracle switches from sha256 to a thresholded pixel diff, and the switch is
recorded in the wave's handoff so a later reader knows why the instrument
changed.

### 4.3 The capture matrix

Tiered, because the full matrix is 96 shots and nobody will run that eight times.

**Tier A, every gate.** 6 routes x 2 viewports x light x `en` = 24 shots.

| Route | Why it is in the minimum set |
|---|---|
| `/en` | the primary subject |
| `/en/pricing` | the only other page with a recorded metrics baseline |
| `/en/docs/quick-start` | the docs reading surface, `DocsLayout` |
| `/en/blog` | `ContentLayout`, the third layout |
| `/en/solutions/disaster-recovery` | a solution page, carries `solution-pages.css` and its own `:root` |
| `/en/partners` | the largest form (`PartnerApplicationForm.tsx`, 441 lines) |

Viewports: **1440x900** and **390x844**, per `00-BRIEF.md`.

**Tier B, added at any gate whose wave touched global CSS (Waves 1 and 3), and at
the final gate.** Same 6 routes, plus:

- **dark theme** (`agent-browser set media dark`). The site has a dark path:
  `public/styles/main.css:323` is `@media (prefers-color-scheme: dark)`, and
  `data-theme` appears in `BaseLayout.astro` and `main.css`. `RESEARCH-metrics.md`
  §10.3 flagged that the 43-painted-colors baseline was taken in a single
  unspecified theme and offered to re-baseline both. **Do that at S0.** A token
  collapse measured in one theme only is half a measurement.
- **`ar`** on `/ar` and `/ar/pricing`, for RTL. This is `sx-rtl`'s surface and
  there is no prior baseline for it.
- **`de`** on `/de` and `/de/pricing`. German is the longest-string locale and is
  where a tightened type scale or a narrowed button will overflow first.

**Full matrix (all 6 routes x 2 viewports x 2 themes x 3 locales = 72, plus the 24
Tier A) at S0 and at the final gate only.**

### 4.4 Capture procedure

```bash
export AGENT_BROWSER_SESSION=sx-metrics-vis
SHOTS="$SNAP/$S/shots"; mkdir -p "$SHOTS"
agent-browser set viewport 1440 900
agent-browser open http://127.0.0.1:4331/en
agent-browser wait --load networkidle; sleep 2
agent-browser screenshot "$SHOTS/en-1440-light.png" --full     # ABSOLUTE path, always
```

Three rules, each paid for:

- **Absolute screenshot paths, always.** `AGENT_BROWSER_SCREENSHOT_DIR` is ignored
  by agent-browser 0.34.0; a bare filename resolves against the working
  directory, which is the repo. It already put three untracked PNGs into
  `packages/www/` (`00-BRIEF.md:104-124`).
- **Never `agent-browser close --all`.** It closes every peer's browser.
- **`sleep 2` after `networkidle`**, matching `RESEARCH-metrics.md` §9.2's
  `cold.sh`, so these shots are comparable to the metrics instruments.

### 4.5 Comparison procedure

Two independent instruments, because one of them is already known to lie about
one of its outputs.

```bash
# Instrument 1, exact: free, and today it is sufficient (§4.2).
sha256sum "$SNAP/S1/shots/"*.png > /tmp/s1.sums
cd "$SNAP/S2/shots" && sha256sum -c /tmp/s1.sums 2>&1 | grep -v ': OK$'
#   empty output = zero pixel change across the whole set

# Instrument 2, thresholded: required from Wave 3, and for adjudicating a delta.
agent-browser diff screenshot --baseline "$SNAP/S1/shots/en-1440-light.png" \
  --full --threshold 0.1
#   verdict is trustworthy; its --output file is NOT (see below)

# Instrument 3, the diff IMAGE, because instrument 2 cannot produce one:
compare "$SNAP/S1/shots/en-1440-light.png" "$SNAP/S2/shots/en-1440-light.png" \
  "$SNAP/S2/diffs/en-1440-light.png"
compare -metric AE "$SNAP/S1/..." "$SNAP/S2/..." null:
```

**`agent-browser diff screenshot --output <path>` writes nothing.** Verified twice
this session (§10.4): it prints `Diff image: <the exact path you passed>` and no
file exists at that path, or anywhere else. The *verdict* is sound, and its
control fires correctly in both directions (100.00% / 10,686,962 px for two
different pages, 0% for identical inputs). The *image* is fiction. Use
ImageMagick `compare`, which is installed (6.9.12-98) and writes a real file.

**The percentage is not a severity measure.** The diff normalises to the
baseline's dimensions: `/en` (1573x6794) against `/en/pricing` (1573x8397)
reported `10,686,962 / 10,686,962` different, which is exactly 1573 x 6794, that
is, 100% of the baseline area. Any height change shifts everything below it and
reads as ~100%. **Treat the verdict as zero or nonzero and nothing else.**

Related trap: **full-page screenshots of `/en` are 1573 px wide at a 1440
viewport**, because `documentElement.scrollWidth` is 1573 (§10.7). Never derive
page geometry from screenshot pixel dimensions, and be aware that fixing the
horizontal overflow will change the width of every captured baseline at once,
making every diff read 100%. That is a legitimate, deliberate, whole-matrix
invalidation and it must be declared as such in the handoff.

### 4.6 Deliberate versus accidental invalidation

The distinction is procedural, and it is the part that keeps this honest.

- **A snapshot is never overwritten.** `S0`, `S1`, `S2` are separate immutable
  directories, `chmod -R a-w`. There is no "update the baseline" verb. There is
  only "capture the next one".
- **A wave gate cannot pass with an unadjudicated delta.** Every shot whose hash
  changed is labelled in the handoff as either **INTENDED**, naming the plan item
  from `01-SYNTHESIS.md` that caused it, or **UNINTENDED**. One UNINTENDED entry
  blocks the gate.
- **Promotion, not acceptance.** `S<n>` becomes the comparison base for wave
  `n+1` only after every delta in it is adjudicated. An unpromoted snapshot is
  evidence of a problem, not a new normal.
- **A whole-matrix invalidation is announced before it happens**, not explained
  after. Wave 1 (global tokens), Wave 3 (motion breaking byte-determinism) and
  any overflow fix (changing capture width) are the three known ones. If a diff
  goes matrix-wide and nobody predicted it, that is the alarm.

---

## 5. The sequencing protocol

### 5.0 Vocabulary

- **SLOT.** A period in which at most **2 writers** hold **disjoint file
  ownership**. During a slot the rig is frozen and nobody refreshes it.
- **GATE.** The boundary between slots. Exactly one agent acts. Writers are idle.
- **BLAST RADIUS.** The set of captured surfaces a wave is permitted to change,
  declared before the slot opens.
- **HANDOFF.** What a writer produces at the end of its slot (§5.2).

### 5.1 Two ownership corrections before anything starts

Both are defects in the current plan, found while designing this, and both must be
resolved at G0.

1. **`src/pages/[lang]/index.astro` is a single-owner file, so `sx-hero` and
   `sx-homepage` cannot run concurrently.** `README.md` assigns "the hero section
   of `[lang]/index.astro`" to one and "below-fold `[lang]/index.astro`" to the
   other. That is one file with two owners, which the standing rule forbids, and
   `01-SYNTHESIS.md` §4 Wave 2 pairs them anyway. The slot table below separates
   them.

2. **Two specialists in the fleet have no entry in the ownership map.** `sx-rtl`
   and `sx-bughunt` are active agents but appear in neither `README.md`'s table
   nor `01-SYNTHESIS.md`. Add them, or state that they own nothing and work
   through other owners. This document assumes the latter for `sx-bughunt`
   (§5.4) and assigns `sx-rtl` a slot.

Plus the three files `01-SYNTHESIS.md` §8 already flags as unowned:
`PartnerApplicationForm.tsx` with `partners.astro`, `SearchModal.tsx` with
`search-modal.css`, and `scripts/generate-search-index.js`. **No slot opens while
any file in its blast radius is unowned.**

### 5.2 The handoff block

Every writer ends its slot by writing this, in its own research document under a
dated `## Implementation log` heading. It is the interface between slots.

```
SLOT:            W2a
AGENT:           sx-hero
FILES TOUCHED:   <paste of `git diff --stat HEAD -- <owned paths>`>
BLAST RADIUS:    /en @1440, /en @390     (declared before the slot)
TOKENS ADDED:    --hero-lead, --hero-measure
TOKENS REMOVED:  (none)
CLASSES REMOVED: .hero-terminal, .hero-disclaimer
GATES RUN:       <command> -> <verbatim last line of output>
GATES SKIPPED:   <gate> because <reason>
KNOWN BREAKS:    <anything the next slot must expect>
```

`TOKENS REMOVED` and `CLASSES REMOVED` are load-bearing. This is a subtraction
project (`01-SYNTHESIS.md` §1), so the most likely cross-slot break is one agent
deleting a rule another agent's markup still references. Nothing in the repo will
catch that: knip's `packages/www` project glob is
`src/**/*.{ts,tsx,astro,mdx}` with **no `css`**, and the two
`check-unused-css*.js` scripts in `packages/www/scripts/` are wired to
`lint:css` in `packages/www/package.json` and referenced by **no gate**.

### 5.3 The slots

Hard dependencies from `01-SYNTHESIS.md` are encoded as gate entry conditions.

| Slot | Writers (max 2, disjoint) | Owns | Blast radius | Entry condition |
|---|---|---|---|---|
| **G0** | `sx-metrics` alone | nothing | none | R0 acceptance test passes; §5.1 ownership resolved; **S0 captured, full matrix, both themes** |
| **W0** | `sx-i18n-ci` alone | `src/i18n/{utils,react,types}.ts`, the new `src/i18n/client/`, `MegaMenu.tsx:33`, `Sidebar.tsx:145` | **none** (zero visual change is the claim) | G0 passed |
| **G1** | `sx-metrics` | | | S1 captured. **Pixel gate: zero change on the ENTIRE Tier A matrix.** Wave 0 changes bytes, not pixels; any pixel delta here is a bug, and this is the cleanest gate in the program |
| **W1a** | `sx-tokens` alone | `main.css` `:root`, `BaseLayout.astro:279-414`, `responsive.css`, token-level `src/styles/` | everything | G1 passed |
| **G2** | `sx-metrics` | | | S2. Pixel gate **vacuous by declaration** (§4.1). Gated on §7 numerics instead: font-sizes 23 to 8, colors 43 to 16, radii 11 to 3, shadows 6 to 1 |
| **W1b** | `sx-primitives` alone | shared primitive rules in `main.css`, form/modal/tab components, `main.css:3348-3387` incl. **the `no-preference` + `html.js-anim` guard** | everything | **G2 passed. Cannot overlap W1a: both edit `public/styles/main.css`** |
| **G3** | `sx-metrics` | | | S3. **Records that the motion guard shipped**, which is M0's entry condition |
| **W2a** | `sx-hero` ∥ `sx-pricing` | `index.astro` hero region ∥ `pricing.astro`, `pricing-page.css`, pricing components, `checkout/` | `/en` ∥ `/en/pricing` | G3 passed |
| **G4** | `sx-metrics` | | | S4. **Pixel gate: zero change on `/en/docs/*`, `/en/blog`, `/en/partners`, `/en/solutions/*`.** This is the first gate that can actually catch a cross-page leak |
| **W2b** | `sx-homepage` ∥ `sx-docs` | below-fold `index.astro` + homepage-only components ∥ `DocsLayout`, `ContentLayout`, `DocsSidebar`, `DocsTopTabs`, `Sidebar.tsx`, per-page stylesheets | `/en` ∥ `/en/docs/*`, `/en/blog` | G4 passed. **`sx-hero` is out of `index.astro` (§5.1.1)** |
| **G5** | `sx-metrics` | | | S5. Pixel gate: zero change on `/en/pricing`, `/en/partners` |
| **W2c** | `sx-chrome` alone | `Navigation.tsx`, both mega menus, `LanguageMenu`, `SearchModal` + `search-modal.css`, `Footer`, `AnnouncementBar`, `Breadcrumb`, `mega-menu.css`, `persona-mega-menu.css` | **every route** | G5 passed. **Solo: chrome renders on every page, so it has no disjoint partner** |
| **G6** | `sx-metrics` | | | S6. Pixel gate limited to "the delta is confined to header and footer bands", adjudicated with `compare`'s diff image |
| **W3** | `sx-motion` ∥ `sx-rtl` | `.reveal` class attributes, icon SVGs, illustrations ∥ RTL rules and `ar` surfaces | all `/en` ∥ all `/ar` | G6 passed **and** S3 recorded the `no-preference` guard. **M0 must not land before it, or a no-JS visitor gets a blank homepage** |
| **G7** | `sx-metrics` | | | S7. **Oracle switches from sha256 to thresholded diff (§4.2), recorded in the handoff** |
| **W4** | `sx-metrics` alone | nothing | none | Final: full matrix, re-run §9 of `RESEARCH-metrics.md` verbatim, S0-vs-S7 report |

### 5.4 `sx-bughunt` and the §6 correctness findings

`01-SYNTHESIS.md` §6 lists defects that are not design work: the `cf-badge`
"Strategic anchor" string live on production, the mega-menu click that closes the
menu, `#image-modal` `aria-hidden` around focusable buttons on every page, the
docs share menu corrupting every heading's accessible name, search returning
"Pruning" for `pricing`.

They are not a wave. They are **owned by whichever specialist owns the file**, and
`sx-bughunt` hands each owner its list at the gate *before* that owner's slot.
Reason: these fixes touch files that are already spoken for, and a third writer in
someone else's files is exactly the collision the 2-writer rule exists to prevent.

**One exception.** The `cf-badge` string is live on production and is visitor-
facing internal jargon. It should not wait for Wave 2. Fix it in W0's slot, as a
one-line change, declared in W0's handoff as out-of-scope-but-shipped, per
CLAUDE.md's "do the minimum, then say so loudly".

---

## 6. Rollback, without `git checkout`

### 6.1 What "undo" means here

`git checkout`, `restore`, `stash` and `clean` are forbidden because they operate
on paths, not on authorship, and this tree holds other sessions' uncommitted
work. That ban is correct and stays.

But **the pessimistic reading of "no safety net" is wrong for this program**, and
the difference matters. Measured (§10.5): `git status --porcelain packages/www`
is **empty**. `packages/www` is clean at `HEAD` = `8bcd3ed17`. Therefore, for the
entire duration of this program and for as long as nobody commits:

> Every byte of difference between `HEAD` and the working tree inside
> `packages/www` was put there by this program. There is no third-party
> uncommitted work in `packages/www` to destroy.

That converts rollback from "impossible" to "precise".

### 6.2 The one-file restore

```bash
git show HEAD:packages/www/public/styles/main.css > packages/www/public/styles/main.css
```

This is not `git checkout`. It reads one blob and writes one file. It cannot
touch a path you did not name, cannot walk a directory, and cannot reach outside
`packages/www`. It is reviewable in a single line.

**It still destroys this program's work on that file**, so it is governed:

1. Copy the current file into the scratchpad first. Always.
   `cp packages/www/public/styles/main.css $SNAP/rollback/main.css.$(date +%s)`
2. Announce it in the handoff. A silent rollback looks identical to work that was
   never done.
3. Never loop it over a directory. One named file per invocation. A loop is
   `git checkout` wearing a different hat.

### 6.3 Wave-level rollback, and why repair-forward is tractable

`git diff HEAD -- packages/www` is exactly this program's cumulative change, and
each snapshot froze a copy of it as `www.patch`. So:

- **Revert one wave:** `git apply -R` the difference between two snapshots'
  patches. Reviewable before applying with `git apply --check -R`.
- **See exactly what a wave did, later:** `diff $SNAP/S3/www.patch
  $SNAP/S4/www.patch`.
- **Rebuild any past state in the rig:** `git archive HEAD -- packages/www |
  tar -x -C $RIG` then `git apply $SNAP/S<n>/www.patch`. Fully out of the shared
  tree.

**What makes repair-forward tractable per wave**, which is the real answer since
repair-forward is the standing rule:

| Wave | Why a mistake is repairable rather than catastrophic |
|---|---|
| W0 | Purely mechanical: two `to()` calls narrowed plus a generated catalog. Zero visual surface. Its gate is a zero-pixel-change assertion, which is the strongest gate in the program. A wrong W0 is caught immediately and is one file to fix. |
| W1a | Single file (`main.css` `:root`) plus one deleted block in `BaseLayout.astro`. The deletion is the risk, so the block is preserved verbatim in the handoff before removal. `--sp-border-light` collapsing onto `--color-border` is a rename, reversible by a rename. |
| W1b | Deletions of whole stylesheets (`contact-modal.css`, `search-modal.css`, `region-picker.css`, `platform-tabs.css`). **A deleted file has no `git show HEAD:` problem, so this is the safest kind of change to undo and the most dangerous to get wrong silently.** Adopting the dead `.form-*` system is additive first, subtractive second: land the adoption, gate it, then delete. Never both in one slot. |
| W2a/b/c | Per-page and per-component. Blast radius is one or two routes, and G4/G5/G6 assert zero change elsewhere. A mistake is contained by construction. |
| W3 | M0 is **class attributes only, zero new code**. Rollback is deleting the attributes. This is why the synthesis ordered it first among the motion items. |

The genuinely hard-to-reverse items are the ones that leave `packages/www`:
`i18n:generate-hashes` writes through into `packages/cli`'s manifest and
`private/account` (`01-SYNTHESIS.md` §5c), and any locale deletion has no tooling.
Those are called out in §7 as needing their own confirmation step.

---

## 7. The verification contract

### 7.1 The three rules that make the rest work

1. **Never run `build:www`, or any gate that needs it, from the shared tree.**
   It deletes 14 tracked files (§1). Gates that need it are `check:ci-seo`
   (partially), `check:ci-cta-bolt`, `check:ci-redirects`,
   `check:ci-docs-render-parity`, `check:test-workers`. **Run those from the
   rig**, which has its own `scripts/`, `.ci/` and `dist/`.
2. **Never run two ci-runner processes at once anywhere in this program.** The
   `mutex: ['www-dist']` on `build:www` is process-local (`pool.ts:170`) and
   protects nothing across agents. Gate runs happen at gates, by one agent.
3. **`--only` selects by gate id and silently drags in the `needs` closure**, so
   any selection containing a `build:www` dependent costs +221 s and a build.
   Also, `npm run ci:list --only <x>` prints everything: `--list` short-circuits
   before selection (`run.ts:333`). **Validate a selection by running it, never
   by listing it.**

### 7.2 Per-slot gate commands

Costs are the measured local EWMA from `.ci/cache/gate-durations.json`.

| Slot | Command | Expected output | s |
|---|---|---|---|
| **W1a, W1b** (CSS only) | `npx tsx scripts/ci-runner/run.ts --only 'check:format'` | `1/1 ok` | 2.4 |
| any slot touching `.tsx` | `npx eslint packages/www/src --max-warnings 0` | no output, exit 0 | 25 |
| any slot touching `.astro` or `.tsx` | `npx tsx scripts/ci-runner/run.ts --only 'check:ci-page-locale-imports,check:test-www,lint:unused'` | `3/3 ok` | ~30 |
| **W2a, W2b, W2c** (needs built HTML) | from the rig: `npx tsx scripts/ci-runner/run.ts --only 'check:ci-seo,check:ci-cta-bolt,check:ci-redirects,check:ci-docs-render-parity,check:test-workers'` | `5/5 ok` | ~240 incl. build |
| **W0** (locale JSON) | `npx eslint packages/www/src/i18n/translations --max-warnings 0` then `--only 'check:i18n,check:ci-i18n-placeholders,check:ci-i18n-value-types,check:ci-locale-de-contamination,check:ci-locale-sources,check:ci-pricing-consistency'` | `6/6 ok` | ~95 |
| any slot touching `src/content/**` | `--only 'check:ci-content-quality,check:ci-search-index,check:ci-docs-structure-parity,check:ci-nis2-quotes'` | `4/4 ok` | ~115 |
| **final gate only** | `npm run ci` | all green | ~5,700 serial |

Two gates deserve naming because they will bite:

- **`check:i18n` is a 19-leaf `&&` chain.** The first failure hides the other 18.
  When it reds, expect to run it more than once.
- **`check:ci-locale-sources` fires on any array of 5 or more locale codes**
  outside a 6-file allowlist. Wave 0 generates `src/i18n/client/<locale>.json`
  from `SITE_LOCALES`; if the generator inlines a locale list, this gate reds.
  `01-SYNTHESIS.md` also records that it does **not** catch a 13-key object map
  or `import.meta.glob`, so passing it is not proof the locale set is derived.

### 7.3 What the gates do not cover, stated plainly

This is the single most important paragraph in this section, because it explains
why §4's visual protocol is not optional.

**There is no CSS gate, no accessibility gate, and no page-weight gate anywhere
in the 232-gate set.** No Lighthouse, no bundle budget, no CSS size assertion, no
contrast check, no focus order, no visual regression. The only accessibility rule
in the entire config is `jsx-a11y/alt-text` in `eslint.config.js:1159`, scoped to
`packages/www/src/**/*.{ts,tsx}`.

And `.astro` is worse than ungated, it is *unreached*: `biome.json` excludes it
(`"!**/*.astro"`), `eslint.config.js` has no astro parser (running eslint on
`BaseLayout.astro` returns "File ignored because no matching configuration was
supplied"), and there is no `astro check` and no tsc project for www in any gate.
The entire page and layout surface of the marketing site, which is what this
program rewrites, is linted by nothing, formatted by nothing, and typechecked by
nothing.

**Consequence:** a green gate run says almost nothing about whether this program
broke the site. The pixel gate in §4 is not belt-and-braces. It is the only
regression detector that exists.

### 7.4 A wave is done when

All five, no adjectives:

1. Rig refreshed, `astro build` exits 0 with no
   `Failed to generate search index` in the output, and
   `git -C $SRC status --porcelain packages/www` shows only files this program
   intends to have changed.
2. Snapshot captured with `HEAD.sha`, `www.patch`, `captured.utc`, and
   `chmod -R a-w` applied.
3. The pixel gate for that wave passes: `sha256sum -c` clean outside the declared
   blast radius, and every delta inside it labelled INTENDED with its plan item.
4. The gate commands in §7.2 for that slot's file types ran and printed their
   expected output, pasted verbatim into the handoff. Gates skipped are named,
   with the reason.
5. The handoff block (§5.2) is written into the specialist's research document.

---

## 8. Where this system can still produce a silently wrong green

Assume it will. `sx-metrics` caught its own above-fold instrument inflating a 3x
win, `sx-i18n-ci` proved a gate that could not fire, and this session found a
third lying instrument in an hour (§10.4). Here are the ones I can see, each with
the detector that would catch it.

### 8.1 Measuring a stale snapshot (highest risk, most likely)

An agent lands a change, then measures against a snapshot captured before it.
Every number is internally consistent and describes a world that no longer
exists. Nothing errors.

This is the residual risk of choosing model C, and it is deliberate: it replaces
a silent failure with a checkable one, but only if the check is actually run.

**Detector, mandatory at every gate, before any measurement:**

```bash
diff <(git -C $SRC diff HEAD -- packages/www) "$SNAP/$S/www.patch" && echo SNAPSHOT-CURRENT
```

If that prints nothing but `SNAPSHOT-CURRENT`, the snapshot is exactly the
working tree. Any output at all means refresh before measuring. **Paste this
command's result into the handoff.** A gate that does not show it did not run it.

### 8.2 A vacuous pixel gate reading as a pass

Wave 1's blast radius is everything, so its outside-set is empty and
`sha256sum -c` over an empty set exits 0. A future reader sees "pixel gate:
passed" and concludes nothing regressed.

**Detector:** the gate must print the *count* of surfaces compared, and a count of
zero is a failure, not a pass. This is the same anti-vacuity discipline the repo
already applies elsewhere (`check_i18n_value_types.py` has `MIN_PAIRS = 8`).
Concretely: `sha256sum -c` output must be accompanied by
`wc -l < /tmp/s1.sums`, and the handoff records both. Wave 1's entry says
**"pixel gate vacuous by declaration"** in §5.3 for exactly this reason.

### 8.3 The rig diverging from reality without saying so

The rig excludes 6.9 GB of `public/assets/{videos,tutorials}` media. Those files
exist in the shared tree and on the production CDN. So a page that renders a
video poster locally may render an empty box in the rig, permanently, on every
snapshot.

That is *fine* for regression detection, since S0 and S7 are both missing it and
the diff is clean. It is *not* fine if anyone compares a rig number to a
production number, or looks at a rig screenshot and reports a missing poster as a
regression this program caused.

**Rule:** a rig measurement is comparable only to another rig measurement. Any
comparison against `www.rediacc.com` or against the recorded
`RESEARCH-metrics.md` baselines (which were taken against **production**) is
invalid and must be redone as rig-to-rig. **This means S0 is not optional.**

**Detector:** at G0, capture S0 and diff it against the production screenshots
already in `RESEARCH-metrics.md` §9.8. The deltas found there are the rig's known
divergences. Write them down once, and never re-litigate them.

### 8.4 Instruments that lie, the running register

| # | Instrument | The lie | Countermeasure |
|---|---|---|---|
| L1 | `agent-browser diff screenshot --output` | Prints `Diff image: <path>`; **writes no file**. Verified twice this session. | Verdict only. Use `compare` for the image. |
| L2 | `AGENT_BROWSER_SCREENSHOT_DIR` | Ignored; bare filenames land in the repo. Already put 3 untracked PNGs in `packages/www/`. | Absolute paths, always. |
| L3 | `agent-browser a11y` | Reported `violations: 0` on our hero while silently downgrading 30 nodes to *incomplete*. Four contrast failures then measured by hand. | `violations: 0` alongside a nonzero `incomplete` is **unproven**, not passed. |
| L4 | Diff percentage | Normalises to baseline dimensions, so any height change reads ~100%. | Zero or nonzero. Never a magnitude. |
| L5 | `probe.js` naive above-fold count | 51 vs 18/17, a fake 3x win. | `hittest.js`, never the naive count. |
| L6 | Warm-cache `transferSize` | Silently reports 0 for cached assets. | Fresh named browser session per URL. |
| L7 | `npm run ci:list --only <x>` | Ignores `--only`, prints all 232. | Validate a selection by running it. |
| L8 | `mutex: ['www-dist']` | Reads as cross-agent protection; is a process-local `Set`. | One ci-runner process at a time, at gates only. |
| L9 | `astro:build:start` search-index hook | `catch {}` at `astro.config.mjs:28` swallows the failure and the build still exits 0. | Grep the build output for `Failed to generate search index`. A build is only green if that string is absent. |

**L10, the one I would bet on next: this document's own protocol.** Every control
above is a step an agent can skip while writing "gate passed". The repo already
knows this pattern (`project_trap_enforcement`: a doc an agent can skip is not a
control). The countermeasure available without writing new tooling is that each
gate's handoff must contain **the verbatim output** of §8.1's `SNAPSHOT-CURRENT`
check and §8.2's surface count. A handoff without both is not a gate, and the
next slot does not open.

### 8.5 The ephemeral instrument problem

`hittest.js`, `probe.js`, `cold.sh`, `coverage.mjs`, `detail.js` and `boxes.js`
live in
`/tmp/claude-1000/-home-muhammed-monorepo-console/e6500e92-.../scratchpad/metrics/`.
`RESEARCH-metrics.md` §9 acknowledges this and takes the position that the
markdown code blocks are canonical: *"That directory is session-scoped and will
be gone; the source below is canonical. Nothing here is added to the repo."*

That is a defensible position for a research phase and a bad one for an execution
phase, because the whole premise of §7.4 is that a wave gate re-runs the same
instrument and compares. A snippet re-typed out of a markdown block is not the
same instrument, and a single character of drift in `hittest.js`'s effective-
opacity walk changes the number with no error.

**Recommendation, and it needs a decision (§9, O2):** at G0, copy the six
instruments from `RESEARCH-metrics.md` §9 into
`agent/programs/www-simplification/research/instruments/`, in the repo, once, and record their
sha256 in each snapshot. Then "re-run the instrument" is checkable rather than
aspirational. This is ~15 KB of files and reverses a decision `sx-metrics`
deliberately made, which is why it is an ask rather than an action.

### 8.6 Two smaller ones, named so they are not rediscovered

- **`check:ci-docs-render-parity` reads the `.article-content` container that
  `DocsLayout.astro` emits.** `sx-docs` is scheduled to delete
  `DocsLayout.astro:281-617` and `:990-1120`. If the redesign renames or removes
  that class, the gate's oracle silently stops selecting anything and the gate
  can pass while measuring nothing. Same shape for
  `check:ci-locale-tutorial-assets`, which depends on the `data-*` attributes on
  `.tutorial-video-container`.
- **`check:ci-cta-bolt` skips itself when `announcement.enabled` is `false` in
  `en.json`.** It is `false` in `en.json` and `true` in all twelve other locales
  (`01-SYNTHESIS.md` §5c). So the gate is **currently self-skipping**, and if
  `sx-chrome` fixes that data defect the gate switches on mid-program and may red
  on pre-existing conditions. Expect it, do not treat it as a Wave 2c regression.

---

## 9. What needs the operator, and why

Everything else in this document is executable by an agent. These are not.

| # | Ask | Why it cannot be an agent decision |
|---|---|---|
| **O1** | `git worktree add` for the rig, **only if R0's acceptance test fails** | `.claude/hooks/pre-bash/block-worktree-add.sh` blocks it unconditionally from an agent's Bash tool. Per `CLAUDE.md` this is also the point where the operator should be asked whether a worktree is wanted at all. Not needed if R0 passes. |
| **O2** | Approve moving the six measurement instruments into `agent/programs/www-simplification/research/instruments/` (§8.5) | Reverses an explicit decision `sx-metrics` recorded ("Nothing here is added to the repo"). One specialist should not silently overturn another's. |
| **O3** | Go / no-go at each gate G0 through G7 | Nine slots is a large autonomous run. The gates are the natural checkpoints and they already require an agent to stop. **Default if unanswered: proceed**, per the standing rule that a deferral's default executes. G0 and G7 are the two worth a real answer. |
| **O4** | The six decisions in `01-SYNTHESIS.md` §9 | Genuinely the operator's: disaster-recovery prices, the fake terminal, the nav label bill (273 naturalized strings), Blog/Partners demotion, `sp-why-now`, Community. **Blocking for W2a** (terminal, prices) and **W2c** (nav labels). Ask before G3, not at G3. |
| **O5** | Any `npm run i18n:generate-hashes` run | It writes through into `packages/cli`'s manifest and `private/account`, outside this program's boundary. Confirm before running. |
| **O6** | Any locale-file deletion | No tooling exists for deletion; `i18n:sync` only adds. Deleting a whole locale file is invisible to completeness, placeholders and value-types, and Wave 0 removes the TS-build backstop that currently catches it. |

---

## 10. Facts measured for this document

Everything above rests on these. Each was run this session, in this tree.

1. **`generate-search-index.js` deletes 14 tracked files.** Read at
   `packages/www/scripts/generate-search-index.js:79-84` (`fs.unlinkSync` over
   `/^search-index(-[a-z]{2})?\.json$/`), hooked at `astro.config.mjs:26`.
   `git ls-files packages/www/public | grep -c search-index` returns **14**.
2. **The ci-runner mutex is process-local.** `scripts/ci-runner/pool.ts:170`,
   `:210`, `:232` operate on an in-memory `Set` named `held`. No `flock`, no lock
   file, no pid file anywhere in `scripts/ci-runner/`.
3. **Screenshots are byte-deterministic today.** Three full-page shots of
   `http://localhost:4321/en` at 1440x900 in session `sx-process`, plus one in a
   fresh session `sx-process-fresh`, all sha256
   `940dd417ed88cfa4340e2ed953e1e65cb88fd3af195d5487b5166278e1f192dd`, all
   500,036 bytes, including across a `reload`.
4. **`agent-browser diff screenshot` verdict works; its `--output` does not.**
   Control fired both ways: `/en` vs `/en/pricing` gave
   `100.00% pixels differ, 10686962 different / 10686962 total`; identical inputs
   gave `Images match (0% difference), 0 different`. ImageMagick agreed:
   `compare -metric AE` returned `0` and `9.18616e+06`. **The `--output` file was
   absent after both runs**, at the exact path echoed back, twice. ImageMagick
   `compare a.png b.png out.png` did write real files (465,627 B and 497,673 B).
5. **`packages/www` is clean.** `git status --porcelain packages/www` is empty.
   Whole-tree status is three entries, none under `packages/www`. `HEAD` is
   `8bcd3ed17` on branch `0815-1`.
6. **Rig payload is 112 MB.** `du -sh` with `node_modules`, `dist`, `.astro`,
   `videos`, `tutorials` excluded: `packages/www` 89 M, `.ci` 18 M, `scripts`
   3.7 M, `workers` 492 K, `packages/locales` 56 K. For contrast: the shared
   `packages/www/dist` is 7.1 G and `packages/www/public` is 6.9 G, of which
   videos are 4.8 G and tutorials 2.1 G. Free disk 151 G.
7. **`/en` overflows horizontally at desktop width.** At a 1440x900 viewport,
   `documentElement.scrollWidth` is **1573** against `clientWidth` **1440**, so
   133 px of horizontal overflow. Zero *visible* elements have a right edge past
   the viewport; the only element far outside the box is the off-canvas
   `aside.sidebar`, 1425 px wide at `left: -1425`. Consequence for this document:
   full-page screenshots come out 1573 px wide. **Raised as a finding for
   `sx-chrome` / `sx-bughunt`; the cause is not established and it is not my
   file.** Worklist `#b7441f78`.
8. **This checkout is a submodule worktree.** `.git` is a file reading
   `gitdir: ../.git/modules/console`; `git worktree list` reports
   `/home/muhammed/monorepo/.git/modules/console`.
9. **Diff tooling inventory.** Present: ImageMagick 6.9.12-98 (`compare`,
   `convert`), Python PIL 12.1.1, numpy 2.4.4, `sharp`, `playwright` with
   browsers cached. Absent: `pixelmatch`, `odiff`, `magick`, `pngjs`.
10. **The dark path exists.** `public/styles/main.css:323` is
    `@media (prefers-color-scheme: dark)`; `data-theme` appears in
    `BaseLayout.astro`, `main.css`, `solution-pages.css`,
    `lead-magnet-modal.css`.
11. **Ports in use:** 4321 (dev server, pid 1170158), 4800, 4801, 4802 (node).
    4331 and up are free.

Facts 1, 2, 5, 6, 7, 8, 10 and 11 were read or run directly by me. Facts about
gate composition, costs and `--outDir` behaviour come from two `Explore` agents
and are cited to `file:line` above; the two claims I depended on most heavily
(the search-index deletion and the mutex scope) I re-verified myself rather than
trusting the report, which is how facts 1 and 2 got into this list.

**Not verified, and flagged as such:** R0's bring-up (§3.3) was designed and not
executed, because this session was forbidden to modify anything and a build would
have written to the tree and burned 2.5 vCPU for minutes alongside twelve live
agents. Its acceptance test is written to be run first, and its fallback is O1.
