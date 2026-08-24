# 06. Execution guide

Status: planned, not started.

## Before anything

1. Read `README.md`, then `01-verified-context.md`. The three corrected premises there each
   prevent a wasted afternoon.
2. **Re-verify the line numbers.** Everything was measured in `~/monorepo/console` before
   the repo moved to `~/console`, and nothing was re-run afterwards. Spot-check the
   load-bearing ones per wave before editing.
3. Start the dev server: `cd packages/www && npm run dev`. Cold start is about 56 seconds
   of content sync, not a hang. Use `/en`, not `/en/`, which 404s.
4. Confirm no other session is mid-build. `npm run build:www` deletes 14 tracked
   `search-index*.json` from the shared tree while it runs and a concurrent build corrupts
   `dist/`. Note the probe trap: `pgrep -f "astro build"` matches its own command line, and
   so does any wrapper whose argv contains that literal text. Probe one gate per process and
   keep the words out of it.
5. Seed the worklist (see below) before doing any work.
6. Ask the two open decision points in `README.md` in one round. Both have a RECOMMENDED
   default that executes if unanswered; do not block on them.

## Spikes, before committing to a wave

Short pre-implementation verifications. Each is minutes, and each de-risks a whole wave.

- **S1, wave C, Ask Assistant.** Open `https://claude.ai/new?q=test` and
  `https://chatgpt.com/?q=test` in a real browser and record whether each prefills, submits,
  or does neither. The Claude web parameter is undocumented and one source claims it was
  removed in October 2025. If it does not work, the menu ships with ChatGPT plus Copy, and
  Claude arrives via the `claude://` desktop scheme, which IS vendor-documented.
- **S2, wave B, the item-4 mechanism.** Reproduce the measured "11 defects to 0" result on
  `/en` at 1440x900 before building on it. A number you did not reproduce is a hypothesis.
- **S3, wave A, the surface ladder.** Confirm the three unreconciled mechanisms are still
  three. If a prior round collapsed one, the wave gets smaller.
- **S4, wave C, item 8.** Re-measure prose and player at 1440 and 1920 before editing, so
  the after-numbers mean something.

## Waves and ordering

```
A (chrome, surfaces)  ─┐
                       ├─> D (gates)  ─> baselines seeded AFTER A and C land
B (marketing)         ─┘
C (docs surface)      ───┘
```

- **A and B can run concurrently** and are the two-writer pair, provided ownership holds:
  A owns `public/styles/main.css`, B does not touch it.
- **C can run concurrently with either**, since its file set is disjoint from both.
  Never run all three writers at once: the cap is 2.
- **D runs last** for the accessibility and section-surface baselines, which must be seeded
  from the fixed state, not the broken one. The two sentence gates can be built earlier,
  since wave B needs the mechanism they enforce.
- **One cross-wave dependency:** wave A deletes the dead `.difference-row*` CSS only after
  wave B lands its replacement. B tells A when it is safe.

## Staffing

Opus by default for coding sub-agents. **Fable for the challenging pieces and for all
planning agents.** Sonnet only for translation and naturalization.

Fable-tier here: the item-4 mechanism and its two gates; the surface-colour ladder in wave
A; the docs subcategory vocabulary in wave C.

At most 2 concurrent writers, file ownership stated verbatim in every prompt, everything
else forbidden. Forbid `git checkout`, `restore`, `stash` and `clean` in every writer
prompt, and forbid any repo-wide `sync` or `regenerate` script. Investigation agents fan out
freely.

Every sub-agent names its working report `reports/<phase>-<agent>.md` under the program
state dir, and its brief `reports/<phase>-<agent>-brief.md` when one is used. The team lead
reads reports **and the artifacts**, never a bare summary: sub-agent reports are accurate
about intent and quietly wrong about placement. Update `MANIFEST.md` at every phase
boundary. Drop an uncommitted-tree patch into `checkpoints/` periodically; a host reboot
once destroyed a scratchpad, which is why durable state exists.

## Worklist wiring

Seed at start, one item per wave, tagged with your 8-char session prefix and carrying the
checklist token. Path via `.claude/hooks/stop/worklist.py --path`.

```
worklist.py --add <me> 'cl:www-round5/w1 Wave A: chrome and surfaces'
worklist.py --add <me> 'cl:www-round5/w2 Wave B: marketing comprehension'
worklist.py --add <me> 'cl:www-round5/w3 Wave C: docs surface'
worklist.py --add <me> 'cl:www-round5/w4 Wave D: gates'
```

The token links the store item to `CHECKLIST.md`. The Stop hook blocks any stopping session
while a wave is neither ticked in the checklist nor covered by such an item, because an
uncovered wave is unclaimed work. Tick a `wN` box only after the store item is ticked with
**probed** evidence. When every wave is ticked, set `Status: done`.

Decision points get asked in one early round and parked as `- [?]` with a `DEFAULT:` if
deferred. Background delegation is held as `- [>] (prefix) until:<ISO>Z worker:<bg-id>`,
leases renewed on wake. `- [x]` only after probing the artifact.

## Gates

`npm run ci` for the full set. At minimum, name the result of `check:lint`, `check:i18n`,
`check:ci-parity`, `check:ci-dead-css`, `check:ci-css-dom-refs`, `check:ci-anchor-integrity`,
`check:ci-layout-overflow`, `check:test-www` and `build:www`. Say which you ran and which
you skipped; before calling a failure pre-existing, show that none of its findings are in
files you touched.

Every new gate: run its `--selftest` control and report that it went red.

## Definition of done

- All twelve operator items are addressed, or the ones that are not are named out loud with
  the reason. No silent descoping.
- Before-and-after browser measurements exist for items 1, 3, 5, 6, 8 and 9, taken at 1440
  and 390, and for items 4 and 6 across locales including `/ar` and one CJK locale.
- The axe run on `/en` clears `.language-name`, `.footer-version` and `.form-input` in both
  themes.
- Four new gates are wired three-point, `check:ci-parity` is green, and each new gate's
  control has been run and observed to fail.
- `CHECKLIST.md` has every deliverable and wave ticked, and `Status: done`.
- Everything is uncommitted. The operator runs `/pr-babysit`.
