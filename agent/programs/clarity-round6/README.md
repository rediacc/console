# clarity-round6

Reduce what a visitor has to process, on the pages and in the videos, and make the
toolchain that produces both survive a machine rebuild.

Planned in session `e580532b` on 2026-08-27, branch `0827-1`, in `/home/developer/console`.
Program state, including reports and checkpoints:
`~/.claude/projects/-home-developer-console/programs/clarity-round6/`.
Memory pointer: `~/.claude/projects/-home-developer-console/memory/MEMORY.md`.

This is the next round after `agent/programs/www-simplification` (which fixed the
homepage) and `agent/programs/www-round5`. Both are `Status: done`; their locked decisions
bind this program and are collected in `02-inherited-decisions.md`.

## Read order

1. `01-verified-context.md` - the host, nine verified defects, the measured numbers
2. `02-inherited-decisions.md` - twenty-three decisions already made elsewhere
3. `03-solution-page-density.md` - the biggest wave, and why it parallelises the way it does
4. `04-video-fleet.md` - the render-once rule that orders half the program
5. `05-toolchain-portability.md` - Docker, GPU, fonts, `./run.sh setup`
6. `06-execution-guide.md` - spikes, waves, staffing, gates, definition of done

## Non-negotiable working ethos

**Validate, do not believe.** Every file:line reference in this suite is a hypothesis;
re-verify it against the tree. Run the real thing and read stdout and stderr separately.
Plant a control before trusting any zero. Do not trust a sub-agent report you have not
spot-checked against the artifact, including your own from earlier in the session.

**Everything stays local and uncommitted.** No commit, no branch, no push, no PR unless
the operator asks in-task. Never `git checkout`, `restore`, `stash` or `clean`; the tree
holds other sessions' work. Repair forward.

**Testing and concurrency support are first-class deliverables**, not follow-ups.

**No em dashes in any authored text, in any language.**

## Staffing

Opus is the default for coding sub-agents. **Fable for the challenging pieces AND for
planning agents.** Sonnet for all translation and naturalization work.

At most **2 concurrent writers**, with disjoint file ownership stated verbatim in every
prompt. Investigation agents fan out freely. Every sub-agent report is spot-checked
against the artifact before anything builds on it.

Fable-tier pieces, named: the Docker GPU image and the lease boundary (w9); the palette
change together with the `semantic_sense` gate (w4c); the per-page cut decisions (w5).

The i18n catalogs are a SERIALISED, single-owner surface. Page agents propose splices;
one owner applies them and runs `i18n:generate-hashes` once. See `06-execution-guide.md`.

## Scope

- **w1 Wave 0** - frozen-build measurement harness and the template contract. Serial, lead
  only, and the prerequisite for w5.
- **w2 Wave 1** - the agent-browser output guard, its cases, its inventory entry.
- **w3 Wave 2** - Remotion 4.0.463 to 4.0.518, an SSIM A/B, and `renderer` provenance in
  the video manifest.
- **w4 Wave 3** - the three video decisions that must land before any render: cut the CTA
  scenes, cut the invalid terminal scenes, lighten the palette with its gate.
- **w5 Wave 4** - solution-page density across 21 pages, per-page treatment, parallel
  readers and one serialised writer.
- **w6 Wave 5** - eliminate the dark bands outside dark mode. Single owner, `main.css`.
- **w7 Wave 6** - the new videos: four persona pages and the homepage, via the source
  adapter ported from `www_pipeline/surfaces.py`.
- **w8 Wave 7** - ONE render and publish pass for the whole fleet, 338 videos.
- **w9 Wave 8** - Docker portability for the helper toolchain, GPU included, plus the
  `./run.sh setup` gaps.
- **w10 Wave 9** - verification and the before/after scorecard.

**Explicitly OUT**

- Remotion 5.0. Announced, not shipped, and it changes rendered colour space, the default
  GL renderer, `<Sequence>` premount and `<Img>` loading behaviour. Not in this program.
- NVENC hardware encoding. Encoding is 0.39% of render time by this repo's own profile.
- ElevenLabs and any cloud TTS. Operator directive this session: local GPU only.
- Re-running pipeline steps 1000 to 5000 on the 273 EXISTING videos. Operator directive:
  the pipeline is for NEW videos; existing-video surgery is direct edits.
- Wiring `private/growth`, the Remotion bump or the GPU images into console CI. That
  boundary is deliberate (I15). Ask before crossing it.
- `SPSocialProof.astro` and its re-enable comments. Deliberate dead code, rediacc/console#519.
- Anything in `private/account`.
- Migrating the existing 18 hooks to trapguard (I14).

## Operator decisions (ANSWERED 2026-08-27, do not relitigate)

**A1. All five new videos are AI-generated motion graphics.** The founder-video track was
an idea that never happened. Operator: *"Sorry founder video was an idea. didn't happen.
we'll go with only AI generated."* Consequence: all four persona videos AND the homepage
video go through `video_pipeline`, at 13 locales each, which a camera could not have done.
`private/growth/founder-video-photo-shoot-plan.md` is DELETED. The two research documents
(`founder-hero-video-research.md`, `founder-visual-presentation.md`) are KEPT; they cost
real research effort and remain valid.

**A2. The CTA ending becomes a held brand mark.** The final `proof` beat holds on the
Rediacc mark with no offer text, so the video ends deliberately rather than appearing
truncated.

**A3. The agent-browser guard is a `block-*.sh`.** Visible to `check-hook-integrity.sh`,
gets both-direction coverage and an inventory entry. The per-call process cost is accepted
and recorded as known debt against `PLAN-trap-enforcement.md`.

**A4. The guard BLOCKS.** The failure is silent and exits 0, and has already put untracked
files in the repo by two different mechanisms. The block message must name the correct
alternative, an absolute path outside the repo.

**A5. `howItWorks` is a per-page DENSITY candidate, not a phrasing question.** The site's
17 "One command." headlines are not rewritten (that would trip `check:i18n:hashes` and a
12-locale re-naturalization for no gain). Instead Wave 4 evaluates dropping the whole
`howItWorks` section per page where it is thin. On `infrastructure-costs` it is 966px and
62 atoms, the densest section on the page, and most of that is the invented-server
`costVisual` table. The 18 `terminalType` VIDEO scenes are cut regardless (A-side of w4).

**A6. Persona and homepage videos get a THIRD manifest namespace.** Not `solutions`. Both
existing CI gates derive their slug list from `src/pages/[lang]/solutions/*.astro`, so
persona entries would be silently unguarded under either choice; a separate namespace makes
the shape of the matching gate obvious and keeps the solutions gate's counts honest.

**A7. Dark bands: page-level surfaces go light, the footer stays dark.** Flip hero,
breadcrumb, benefits and bottom CTA in light mode; the footer remains a deliberate page
terminator. Start from the already-diagnosed fix at I9. **The bottom CTA is designed to
merge with the footer** (`main.css:2392-2399`), so that seam needs redesign, not just a
token flip.

**A8. Every video gets a 1.5 second hold before narration starts.** Operator: the viewer
may want to focus or switch to full screen, so give them room. Applies to the new videos
AND to the 273 regenerated ones. See `04-video-fleet.md` for the two candidate
implementation points and the gate collision it causes.
