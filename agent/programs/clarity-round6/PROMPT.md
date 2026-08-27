# clarity-round6 - session prompt

Your mission: execute the `clarity-round6` program. Read
`agent/programs/clarity-round6/README.md` first and follow its `## Read order`. Six
documents, and `02-inherited-decisions.md` is not optional: twenty-three decisions are
already made and re-opening one wastes the session that settled it.

**Validation ethos.** Every file:line in that suite is a hypothesis until you check it
against the tree; run the real thing and read stdout and stderr separately. Plant a control
before trusting any zero, and spot-check every sub-agent report against the artifact rather
than the summary.

**Ask the seven operator decision points in ONE early round**, before building anything
they would change. They are at the end of the README, each with a RECOMMENDED default. Park
an unanswered one as a worklist `- [?]` carrying its DEFAULT, and keep working whatever is
safe under either answer.

## Staffing

Opus is the default for coding sub-agents. **Fable for the challenging pieces AND for
planning agents.** Sonnet for all translation and naturalization work. At most **2
concurrent writers, with disjoint file ownership stated verbatim in every prompt**;
investigation agents fan out freely.

Fable-tier: the Docker GPU image and the lease boundary (w9); the palette change together
with the `semantic_sense` gate (w4c); the per-page cut decisions (w5).

The i18n catalogs are a SERIALISED single-owner surface. Page agents PROPOSE splices into
`reports/`; ONE owner applies them and runs `npm run i18n:generate-hashes` ONCE. Splice
bytes, never parse-and-reserialize a catalog.

## Program state

    ~/.claude/projects/-home-developer-console/programs/clarity-round6/
      MANIFEST.md      model policy, wave table, active agents, discovered bugs
      reports/         one per writing or planning sub-agent: <phase>-<agent>.md
      checkpoints/     a full tree patch at every wave boundary

Update `MANIFEST.md` at every phase boundary. Write a checkpoint patch at every wave
boundary: the work stays uncommitted, so there is no git rollback point.

## Checklist and worklist

`agent/programs/clarity-round6/CHECKLIST.md` carries ten waves, `w1` to `w10`.

Seed the shared worklist at start, one item per wave, tagged with your session prefix and
carrying the checklist token:

    .claude/hooks/stop/worklist.py --add <me> 'cl:clarity-round6/w1 Wave 0: frozen-build harness and template contract'
    .claude/hooks/stop/worklist.py --add <me> 'cl:clarity-round6/w2 Wave 1: agent-browser output guard'
    ... one per wave through w10

The literal `cl:clarity-round6/<wN>` token is what links the store item to the checklist.
The Stop hook blocks ANY stopping session while a wave is neither ticked in `CHECKLIST.md`
nor covered by such an item. Tick a `wN` box only after its store item is ticked with
probed evidence. When every wave is ticked, set `Status: done`.

## The two things most likely to go wrong

**Measure against a FROZEN STATIC BUILD on a random port, never the dev server.** One
server, one tree, HMR; `packages/www/.astro/` is derived from `config.root` with no
override, so ANY build rewrites the cache every running dev server reads. Verify the pid
with `ss -lptn`, diff the hashed asset against `ls dist/_astro/`, and give every probe a
floor that exits non-zero under about 50 DOM nodes. A session once measured a page that
came entirely from another agent's stale snapshot and the numbers were internally
consistent and completely fictional.

**Render the video fleet ONCE.** Four decisions change rendered pixels and two change the
fleet size. 338 videos times 2 orientations is 676 renders, an order of 15 to 30 hours.
Waves 2, 3 and 6 all land before Wave 7 starts. This is ordering, not postponement.

## Local and uncommitted

No commit, no branch, no push, no PR unless the operator asks in-task. Never
`git checkout`, `restore`, `stash` or `clean`; the tree holds other sessions' work. Repair
forward. No em dashes in any authored text, in any language.

## Definition of done

Every wave ticked with probed evidence and `CHECKLIST.md` at `Status: done`; the 21
solution pages re-measured against a frozen build with a before and after scorecard in
height, screens, words and atoms; the fleet rendered once and published through all four
steps with the purge verified against the bucket; `renderer` provenance in the manifest;
every on-camera rdc command parsing against the CLI catalog, or none remaining; the Latin
font assertion in place and all five fonts vendored; the Docker images proven with a real
narration and a real render, GPU lease holding across the container boundary;
`./run.sh setup` verified on a tree with agent-browser and the fonts removed; `npm run ci`
green with the gates named and the skipped ones named.
