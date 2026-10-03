# w10. Scorecard

Status: **www half COMPLETE, video half PENDING w8**. Measured 2026-08-27 against a
frozen static build with a verified server pid and a matching hashed asset, never a dev
server. Harness: `packages/www/scripts/measure-page-density.sh`.

## Read the height and words columns, not atoms

`atoms` counts class-substring matches. It scores a `techDiff` row cut at ZERO while
that cut removes 44 to 128px and 9 to 33 words, and it over-weights textless visual
blocks by counting `[class*=card]`/`[class*=row]`. Roughly 42 atoms on every solution
page are Plyr player chrome that the homepage does not have, so a raw home-versus-solution
atom comparison overstates the gap. Height and words are the trustworthy columns.

## The 7 pages that were cut

| page | height | screens | words | atoms |
|---|---|---|---|---|
| retention-compliance | 8731 -> 7629 (-1102) | 9.7 -> 8.5 | 885 -> 770 (-115) | 277 -> 248 (-29) |
| infrastructure-costs | 8749 -> 7613 (-1136) | 9.7 -> 8.5 | 851 -> 733 (-118) | 255 -> 226 (-29) |
| immutable-backups | 8861 -> 7758 (-1103) | 9.8 -> 8.6 | 945 -> 813 (-132) | 252 -> 223 (-29) |
| integrations | 8590 -> 7437 (-1153) | 9.5 -> 8.3 | 857 -> 725 (-132) | 245 -> 216 (-29) |
| encryption | 8719 -> 7643 (-1076) | 9.7 -> 8.5 | 892 -> 779 (-113) | 245 -> 216 (-29) |
| rapid-recovery | 8752 -> 7623 (-1129) | 9.7 -> 8.5 | 883 -> 747 (-136) | 242 -> 198 (-44) |
| backup-verification | 8771 -> 7639 (-1132) | 9.7 -> 8.5 | 877 -> 754 (-123) | 240 -> 188 (-52) |
| **total** | **-7831px** | **13.6 screens** | **-869** | **-241** |


**Screens corrected 2026-08-27.** Every `screens` figure here divided the page height by
900, the viewport `measure-page-density.sh` ASKED for. `agent-browser open --viewport
1280x900` is silently ignored and yields 1280x577, and a bare `viewport 1280 900` does not
move it either, so the real divisor was 577 and every screens count was understated by
1.56x. The pixel, word, atom and node columns are unaffected: they depend on the WIDTH,
which was the 1280 requested. The harness now reads `innerHeight` back and divides by that,
and refuses to emit a row if it cannot (`measure-page-density.sh`).

## Control: pages that were NOT cut must not have moved

14 untouched solution pages checked. Pages shifting more than 60px: **0**.
If the section removal had leaked into a shared component, these would have moved. They did not.

## Benchmark

| | height | screens | words | atoms |
|---|---|---|---|---|
| home | 5839 | 6.5 | 518 | 157 |
| for-ceos | 5365 | 6.0 | 483 | 104 |
| for-devops | 6259 | 7.0 | 601 | 135 |
| for-ctos | 7562 | 8.4 | 712 | 167 |
| for-ai-agents | 6350 | 7.1 | 628 | 134 |
| 7 cut pages, mean | 7620 | 8.5 | 760 | 216 |

The homepage sits at 10.1 screens after its own nine-sections-to-five pass. The cut
pages now average 8.5, down from 9.7. They are not at the homepage's density and were
never going to be: the homepage carries no video player, no comparison table and no
citation list.

## What produced the change

- `sections: ALL_SECTIONS.filter((s) => s !== 'stats' && s !== 'benefits')` on 7 config entries
- 3185 i18n leaves removed across 13 locales: `problem.timeline` 1365, `benefits` 1001, `stats` 819
- 66 entries drained from the em-dash shrink-only baseline, 0 added

## Not measured, and why

- **Mobile.** Timeline chevrons, benefit cards and howItWorks steps are horizontal at
  desktop, so element-level cuts there are worth 0px at 1280 and may be worth more at 390.
- **The video half.** Runtime, scene counts and the render of the 338-video fleet do not
  exist yet; w8 has not run.

## Pending for the video half

English runtime before the cuts was 22.7 minutes across 21 slugs, with cta at 12.1% of
screen time and 38.4% of screen time in alarm red on a near-black frame. After Wave 3:
504 English scenes became 420, 0 cta remain, and 273 storyboards satisfy
`last.start + duration == total_seconds` with 0 violations. Runtime and colour share
must be re-measured from the rendered fleet.

## Video half, audio AND frames measured 2026-08-27

Apples to apples on the ORIGINAL 21 slugs, from the storyboard and voiceover artifacts:

| metric | before | after |
|---|---|---|
| English runtime | 22.7 min | **20.1 min** (-11.3%) |
| cta share of screen time | 12.1% | **0.0%** |
| red share (hook + problem) | 38.4% | **45.0%** |

Plus 5 new subjects (4 personas and the homepage), all narrated in-container, English only
so far: total across 26 slugs is 26.7 min.

### The red share went UP, and that is a real consequence, not a measurement artifact

Cutting the CTA removed 12.1% of screen time that was TEAL, so the remaining red
`hook` and `problem` beats now occupy a larger share of a shorter video. The operator's
complaint was that the videos are too dark and too alarming; on the colour axis this
change moved the fleet the WRONG WAY.

The palette work was the missing half, and it has since LANDED, in the same session and
ahead of the render, so no video was rendered dark and then redone. `remotion/src/palette.ts`
is now the single source; `config.py`, `prompts/visual_comprehension.py` and
`prompts/storyboard.py` moved with it, because `visual_comprehension.py:358` read "Background
must be dark, flag any light background" and would otherwise have made the adjudicator
re-darken the whole fleet. Constants, rubric and convention moved together, which is what the
paragraph above said they had to.

The red share staying at 45.0% is therefore not the whole colour story: red on a near-black
frame and the same red on a near-white frame are not the same experience, and the frame
measurement below is the one that answers the operator's actual complaint.

### Frame-level colour, measured from the rendered mp4s

One frame every 3 seconds, `signalstats` YAVG on a 192px downscale, landscape English only.
The probe (`scratchpad/frame-luma.sh`) is controlled in BOTH directions: a missing file
prints `NOFRAMES`, a real file prints numbers. Its first version was VACUOUS, because
`metadata=print` writes to stderr at INFO level and `-v error` swallowed it; `file=-`
fixes that. A control that only proves the negative direction proves nothing.

| | slugs | frames | mean Y (0-255) | frames below Y=64 | frames above Y=180 |
|---|---|---|---|---|---|
| before, old palette | 11 | 244 | **45.7** | **70.7%** | **0.0%** |
| after, light palette | 13 | 275 | **211.6** | **3.6%** | **94.8%** |

Per-slug ranges do not overlap: before 38.3 to 54.8, after 203.3 to 222.5. The after set
includes `home`, whose own before/after is the sharpest single case: meanY 50.9 to 213.0 and
80% of frames dark to none, on a template that is not a solution page. The after set also covers all four persona
slugs (203.3 to 208.7), so every template family in the fleet is represented, not just
the solution pages the palette was tuned against. This is the
operator's complaint, closed on the artifact rather than on the constants.

The "before" set is the 11 slugs the running render had NOT yet overwritten. That filter is
load-bearing: `failover-testing` was re-rendered mid-sweep and measured 213.0, and left in
the before column it would have dragged the before mean from 45.7 to 59.6 and invented a
7.9% light share that never existed. A measurement taken against a tree that is being
rewritten has to record WHEN each file was read.

### Whole-fleet confirmation, after the render completed

The table above samples the 13 slugs that had finished when it was written. With all 26
English mains rendered, measured end to end: **26 slugs, 559 frames, mean Y 213.3, 2.8% of
frames below Y=64, 95.9% above Y=180, per-slug range 203.3 to 222.5, and NOT ONE slug left
below Y=150.** The complaint is closed across the whole English fleet, not a sample of it.

**What this pass did NOT touch, stated so publishing is not mistaken for finished.** The
driver runs `--until 6000`, so it refreshed the 26 English mains and their 26 verticals and
nothing else. Still on disk from 2026-07-30, pre-palette, dark, and still carrying the cut
CTA: **280 teasers** and **258 localized mains** across the 12 non-English locales. A
publish today would ship light main videos beside dark social cuts.

A measurement trap worth keeping: globbing `*.en.mp4` also matches `<slug>.teaser.en.mp4`,
and keyed by slug the 11-second teaser overwrites the 61-second main. That briefly reported
the fleet as 63.7% dark. The tell was the frame count: n=4 where the real file gives n=20.

### Screens, now MEASURED rather than scaled

Re-run 2026-08-28 with the corrected harness, which reads `innerHeight` back instead of
dividing by a viewport it merely asked for. All 26 pages measured; the 7 dense pages now
total **49335px across 85.4 screens**, and the whole measured set is
189907px / 328.8
screens. The earlier 13.6 figure was arithmetic on the pixel delta; this one comes off the
browser.

Getting there needed one more instrument fix. `agent-browser open` exits **1 when its
stdout is redirected** and 0 on a terminal, for a URL that loads correctly either way, so
under `set -e` the harness died at its first page leaving an empty log and a CSV holding
only its header. The harness no longer trusts that exit code; a genuinely failed load is
still caught by the DOM-node floor, which is a statement about the page rather than about
a wrapper's exit status.

### The 27 stock scenes: measured, and deliberately left as filmed

The palette work covered scenes we GENERATE. Each video also carries about one Pexels
stock clip, real footage that no palette governs, and after the fleet went light those
clips are now the darkest thing in it. 27 stock scenes across 25 of 26 slugs; 10 of them
sit at `scene_id 1`.

Sampled at ONE FRAME PER SECOND across all 26 English mains: **1683 seconds, of which 63
are below Y=100. That is 3.7%, and 24 of 26 videos contain at least one such second.**
Only `immutable-backups` and `infrastructure-costs` have none. The heaviest is
`vulnerability-management` at 7 seconds of 59.

**The videos do NOT open dark**, which was my first and wrong reading. Every slug sampled
opens at Y about 227, including all ten whose stock clip is `scene_id 1`. What
`migration-safety` actually has is a one-second dip at t=1s (Y 39.9) with t=0 at 227.6.

**A limit of the headline number, stated so it is not over-read.** The fleet figure of
meanY 213.3 comes from sampling every 3 seconds, which steps straight over one and two
second dips. `migration-safety` scores `pct_dark 0.0` under that sampling and demonstrably
contains a dark second. The 3-second figure is right about the fleet's overall look and
blind to its brief dips; this 1-second scan is the one to cite for those.

**Decision, 2026-08-28: left as filmed.** The operator was asked and the deferral expired
into its stated default. Regrading real footage is a change to the product's face rather
than a correctness fix, the videos are light end to end otherwise, and 3.7% of runtime in
one-to-two second clips is a different complaint from the one that started this work
(71 to 98% near-black frames). Reversible at any time: the lift belongs in the stock scene
component, the way `IconScene.tsx` already filters icons.
