# 06. Execution guide

Status: **planning**, 2026-08-27.

## Before anything

1. **Read `02-inherited-decisions.md` end to end.** Twenty-three decisions are already
   made. Re-opening one wastes the session that settled it.
2. **Ask the operator decision points in ONE early round** (README `## Operator decision
   points`). Every one carries a RECOMMENDED default. Park an unanswered one as a
   worklist `- [?]` with its DEFAULT and keep working anything safe under either answer.
3. **Seed the worklist**, one item per wave:

       .claude/hooks/stop/worklist.py --add e580532b 'cl:clarity-round6/w1 Wave 0: frozen-build harness and template contract'

   The `cl:` token links the store item to `CHECKLIST.md`. The Stop hook blocks ANY
   stopping session while a wave is neither ticked in the checklist nor covered by such an
   item. Tick a `wN` box only after the store item is ticked with probed evidence.
4. **Check for peers in this tree.** `ListAgents` showed a concurrent interactive session
   at plan time. The tree usually holds other sessions' work. Never
   `git checkout/restore/stash/clean`; repair forward.
5. **Write a tree patch to `checkpoints/` at every wave boundary.** There is no git
   rollback point because the work stays uncommitted.

## Spikes, before the waves that depend on them

**S1. Prove the frozen-build harness before any page agent runs.** Build once, serve
`dist/` on a RANDOM port, then verify all three: `ss -lptn 'sport = :<port>'` names the pid
you started; the page's hashed asset matches `ls dist/_astro/`; and the probe's floor fires
when pointed at an empty directory. Cost: minutes. Skipping it is how a session measured a
stale snapshot from another agent's squatting server and got internally consistent,
completely fictional numbers.

**S2. Measure one real VoxCPM2 narration on THIS host** and take a true VRAM peak with
`nvidia-smi --query-gpu=memory.used -l 1` across the synthesis phase. Free VRAM here is
11243 MiB against a recorded peak of 12105 MiB on the previous host. One sample is not a
measurement. Only then decide whether `MIN_FREE_MIB` moves.

**S3. Reproduce the Remotion render on 4.0.518 and SSIM it against 4.0.463 output**, one
slug, before any fleet render. Same instrument that proved the `--disable-gpu` switch.

**S4. Confirm the trapguard-versus-block decision empirically** (README decision 3): a
trapguard rule is invisible to `check-hook-integrity.sh`, whose globs are `block-*.sh`
across `pre-bash|pre-edit|pre-ask` only. Establish whether a trapguard rule can be given
both-direction coverage the integrity gate can see, or whether it escapes the gate.

## Waves and ordering

Ordering, not postponement (I2).

    w1  Wave 0  frozen-build harness + template contract    SERIAL, lead only
    w2  Wave 1  agent-browser output guard                  independent, any time
    w3  Wave 2  Remotion 4.0.463 -> 4.0.518                 blocks w8
    w4  Wave 3  video decisions: CTA, terminal, palette     blocks w8
    w5  Wave 4  solution-page density, 21 pages             needs w1
    w6  Wave 5  dark bands outside dark mode                single owner, main.css
    w7  Wave 6  new persona + homepage videos               blocks w8
    w8  Wave 7  ONE render and publish pass                 needs w3, w4, w7
    w9  Wave 8  Docker portability                          independent of the www waves
    w10 Wave 9  verification and scorecard                  last

**The load-bearing ordering constraint is w8.** Four decisions change rendered pixels and
two change the fleet size. 338 videos times 2 orientations is 676 renders, an order of 15
to 30 hours. Render ONCE, after w3, w4 and w7 have all landed. See `04-video-fleet.md`.

**w5 and w6 must not overlap.** The darkness change is a token and CSS change living
almost entirely in `public/styles/main.css`, which is single-writer by decree (I8). The
density change is a config and i18n change. Kept that way, they touch no common line. If a
page agent finds a dark-band defect it REPORTS it with `file:line` and leaves it.

## Staffing

Opus is the default for coding sub-agents. **Fable for the challenging pieces AND for
planning agents.** Sonnet for all translation and naturalization work.

**At most 2 concurrent WRITERS, with disjoint file ownership stated verbatim in every
prompt.** Investigation agents fan out freely. Every sub-agent report is spot-checked
against the ARTIFACT, never the summary, before anything builds on it.

**Fable-tier pieces, named as the handoff requires:**

- **The Docker GPU image and the lease boundary (w9).** T1 is a correctness trap with a
  silent failure mode (two VoxCPM jobs OOM), and the ci-overhaul docs already flag the
  image-hashing under-inclusion direction as dangerous.
- **The palette change and the `semantic_sense` gate (w4c).** Changing a constant is easy;
  changing a constant, a rubric and a convention together without the QA loop re-darkening
  the fleet is not.
- **The per-page cut decisions (w5).** Deciding WHICH of twenty-five restatements is the
  one that carries the argument is judgement, not mechanics.

**Sonnet-tier:** the 12-locale splices once English is settled, and any re-naturalization.

### The i18n writer is serialised, and this is not negotiable

`packages/www/src/i18n/translations/` is owned by NOBODY (prior-program ruling).
N page agents PROPOSE: each emits a per-page i18n splice plus its own `sections` line-block
diff into `reports/w5-page-<slug>.md`. ONE serialising owner applies every splice, runs
`npm run i18n:generate-hashes` ONCE, and drains the shrink-only baselines ONCE. That script
rewrites every tree and has been observed touching `packages/cli`'s manifest and writing
through into `private/account`, so per-wave runs multiply that blast radius.

**Splice bytes. Never parse-and-reserialize a catalog.**

### Reports

Every writing or planning sub-agent names its working report
`reports/<phase>-<agent>.md` under
`~/.claude/projects/-home-developer-console/programs/clarity-round6/`. The team lead reads
reports AND artifacts, never bare summaries. `MANIFEST.md` updates at every phase boundary.

## Gates

**Run and name what you ran.** Never call a failure pre-existing without showing that none
of its findings are in files you touched.

Gates that fire on this work, with what each rejects, are tabulated in
`03-solution-page-density.md`. The ones most likely to bite:

- `check:i18n:completeness` in the ORPHAN direction, which makes the 13-file deletion
  symmetric and unskippable
- `check:i18n:hashes`, which fires on any English value change without a regenerate
- `check:ci-em-dash-surfaces`, shrink-only, which hard-errors on a baselined finding you
  FIXED and did not drain. 1527 baselined entries live under `pages.solutionPages.*`
- `check:ci-dead-css` and `check:ci-css-dom-refs`, the two directions of the same coin
- `check:ci-browser-smoke`, which hardcodes `/en/solutions/instant-recovery`
- `check:ci-hook-integrity`, which fails a `block-*.sh` absent from
  `scripts/data/hook-inventory-baseline.json` and one lacking BOTH directions

**`check:ci-dead-translation-keys` will NOT catch an orphaned section.** Its wildcard
matches every key under every page. Key deletion is a deliberate step.

New gates follow the three-point wiring: `package.json`, `scripts/ci-runner/manifest.ts`
with a `ci:` entry naming a REAL step, and the matching step name in
`.github/workflows/ci-quality.yml`. No `paths:` to make one cheaper (I21). Register every
new gate in `.ci/scripts/test/gates/test-gate-anti-vacuity.sh` with a PINNED DIAGNOSTIC
SUBSTRING (I22).

Control-first, every time: plant the violation on the real tree, watch it go red, remove
it, confirm green. A control that does not fire is a claim about your control first.

## Definition of done

- Every `wN` in `CHECKLIST.md` ticked, its worklist item ticked with probed evidence, and
  `Status:` flipped to `done`.
- The 21 solution pages re-measured against a FROZEN BUILD, with a before and after
  scorecard in the same units used here: height, screens, words, atoms. The homepage's
  6.5 screens and 157 atoms is the benchmark to beat, and it is the same codebase, so it
  is a fair one.
- The video fleet rendered ONCE and published through all four steps, with the CDN purge
  verified against the BUCKET and not the exit code, and one `words.json` fetched and
  diffed against its local copy to prove the cache is fresh.
- `renderer` provenance present in the video manifest alongside `engine`.
- Every rdc command remaining on camera parses against the CLI catalog, or no command
  remains on camera.
- `remotion/src/fonts.ts` asserts its Latin face, and the five fonts are vendored.
- Docker images build and a real narration plus a real render complete inside them, with
  the GPU lease proven to hold ACROSS the container boundary.
- `./run.sh setup` installs agent-browser and the fonts on a clean host, verified by
  running it on a tree with them removed.
- `npm run ci` green, with the gates named and the skipped ones named.
- The working tree uncommitted, unless the operator asks otherwise in-task.
