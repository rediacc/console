# Handoff checklist: www-round5

Status: done
Owner: a68f3ab4

Source session `a68f3ab4` (`console-39`), 2026-08-23, planned in `~/monorepo/console`
before the repo moved to `~/console`. Branch at handoff time: `0823-1`.

## Deliverables

- [x] d1 file:agent/programs/www-round5/README.md
- [x] d2 file:agent/programs/www-round5/01-verified-context.md
- [x] d3 file:agent/programs/www-round5/02-marketing-comprehension.md
- [x] d4 file:agent/programs/www-round5/03-chrome-and-surfaces.md
- [x] d5 file:agent/programs/www-round5/04-docs-surface.md
- [x] d6 file:agent/programs/www-round5/05-gates.md
- [x] d7 file:agent/programs/www-round5/06-execution-guide.md
- [x] d8 file:agent/programs/www-round5/PROMPT.md
- [x] d9 file:~/.claude/projects/-home-muhammed-console/programs/www-round5/MANIFEST.md
- [x] d10 file:agent/PLAN-sentence-aware-wrapping.md

## Waves

- [x] w1 Wave A: chrome and surfaces (items 3, 5, 6, and the a11y defects in owned files)
- [x] w2 Wave B: marketing comprehension -- items 1 and 2 SHIPPED. The item-4 copy
      fixes are NOT done and are carried forward below: they need a `<Sentences>`
      mechanism that does not exist yet.
- [x] w3 Wave C: docs surface (items 7, 8, 9, 10, including Ask Assistant)
- [x] w4 Wave D: gates -- SCOPED DOWN by the operator's own DEFAULT after the 120-minute
      autonomy window closed. SHIPPED: check:ci-sentence-wrapping (gate 1) and
      check:ci-docs-thumb-coverage (gate 3). NOT shipped, and deliberately so:
      the browser gates (2 sentence-lines, 4 section-surface) and 5 accessibility.
      Ticking the box for what shipped, with the remainder named here, because an
      overstating handoff is worse than an incomplete one.

NOTE (promote when started): a follow-up wave for item 12's optional additions, which are
listed in the README's Scope but deliberately not waved yet.

## Operator decisions, answered 2026-08-23 (executing session b7baf3ee)

Both open decision points from README.md were asked in one round, before any
file was read for writing, and both are now closed. The four locked ones are
untouched and must not be relitigated.

**5. Player cap (item 8): RECOMMENDED, as proposed.**

    width: min(960px, max(80%, var(--docs-prose)));

    1920 -> 960px (ceiling)   1440 -> 688px (= prose)   1280 -> 688px

The invariant to gate on is `player >= paragraph at every width`, which is the
thing plain `min(960px, 80%)` broke at 1440 (612px, narrower than the 688px
paragraph above it and narrower than today).

**6. Reference parity (item 9): the recommended set PLUS two additions.**

SHIP: category eyebrow, grouped sidebar, What's next cards, `Ctrl/Cmd+K`,
inline language picker, **nested collapsible TOC**, **copy-page dropdown**.

OMIT: the persistent question composer, on the README's own reasoning that Ask
Assistant already covers that job without a floating element -- and a floating
element cuts against items 3 and 6, whose theme is reducing visual noise.

The operator widened this beyond the README's recommendation: the two additions
are self-contained and neither competes with Ask Assistant. Wave C is therefore
wider than the README scoped it, and wave D's docs-surface gate must cover both.

### Amendment to decision 5, same session: fullscreen already exists

The operator corrected the framing: the player already has a fullscreen button
and users are expected to use it. **Verified rather than taken on trust** -- the
docs player is a native `<video controls>` emitted by
`src/plugins/remark-video-embed.ts:66`, and native controls carry a fullscreen
button in every major browser. It is free and already shipped.

The chosen formula does not change; its JUSTIFICATION gets stronger and the
alternative gets clearly worse. If fullscreen is the real "watch it properly"
path, the inline player is an ILLUSTRATION IN THE READING FLOW and should never
fight the prose for width. `max(80%, var(--docs-prose))` is exactly "never
narrower than the text it illustrates, and no wider than it needs to be". The
x1.4 alternative would push the player wider than the prose at mid widths,
adding visual disruption to partially substitute for something fullscreen
already does completely -- and this round's theme (items 3 and 6) is reducing
visual noise.

### Two premises in the README that did NOT survive first contact

Flagged here before wave C starts, because item 8 is scoped against them:

1. **`--docs-prose` is `34rem`** (`DocsLayout.astro:704`), which is **544px** at
   a 16px root, not the **688px** the decision text quotes. Every width in
   decision 5's table is therefore wrong in absolute terms. The INVARIANT
   ("player is never narrower than the prose") is unaffected, because the
   formula is expressed in the token rather than in pixels -- which is why it
   was written that way.
2. **The tutorial container is not capped today.** `DocsLayout.astro:1060-1064`
   sets `max-inline-size: none` on `.tutorial-video-container` (and `.cs-cards`,
   `.print-page-header`), so it spans the full article width. The claim that
   `min(960px, 80%)` would be "narrower than today" needs re-measuring against
   an UNCAPPED baseline, not against a 960/80% one.

Neither changes the decision. Both change what wave D's gate must assert, and
both are exactly the drift `01-verified-context.md` warns about: the
measurements were taken in `~/monorepo/console` before the repo moved.

### Decision 5's arithmetic does not survive `01-verified-context.md` either

The choice stands; the reason given for it was wrong in both directions, and the
correction is recorded so wave C is not built on it.

`01` measures prose at **544px (34rem) at BOTH 1440 and 1920**, and
`.docs-content` at 765px / 1245px. So under plain `min(960px, 80%)`:

    1440:  0.80 x 765  = 612px   vs 544px prose  -> WIDER, not narrower
    1920:  min(960, 996)= 960px  vs 544px prose  -> wider

The decision text's "612px at 1440, **narrower than the 688px paragraph**" is
false twice: the paragraph is 544px, not 688px, and 612 > 544. The invariant it
was protecting was never actually violated by the simple formula.

**Keep the chosen formula anyway.** It is a strict superset: it holds the
invariant by construction rather than by arithmetic coincidence at two specific
viewport widths, and it keeps holding if `--docs-prose` or the column ever
changes. A formula that is correct for a stated reason beats one that happens to
be correct at the two widths somebody measured.

**The real behaviour change is the opposite of the one described.** Today the
container is UNCAPPED (`max-inline-size: none`, `DocsLayout.astro:1060-1064`),
so the player renders 1245px at 1920 and 765px at 1440 -- `01` measures exactly
that, "a 1245px player above 544px-wide text in the same 1245px column". Item 8
therefore makes the player **substantially narrower than today at every width**
(1245 -> 960 at 1920, 765 -> 612 at 1440), which is the point: prose uses 43.7%
of its column while the player uses 100%.

That is also precisely why the operator's fullscreen hint matters, and it is
consistent with the choice: shrinking the inline player is acceptable because
watching it properly was never the inline player's job.

### Correction to my own amendment, from the wave C writer

My fullscreen note above cited the WRONG element and the writer caught it.
`remark-video-embed.ts:66` builds `.video-container`, a plain
`<video controls>` used for blog embeds. The DOCS player is
`.tutorial-video-container`, produced by `remark-tutorial-embed.ts` and rendered
by `TutorialVideoPlayer.tsx`, whose `<video>` has **no `controls` attribute at
all** -- Plyr supplies the chrome.

**The operator's rationale survives intact; only my citation was wrong.**
`fullscreen` is in Plyr's control list (`TutorialVideoPlayer.tsx:316`) and
exactly one `[data-plyr="fullscreen"]` button renders live. Verified here, not
taken from the report.

### Deviation accepted: `max-inline-size`, not `width`

Written literally as `width:`, the operator's formula is a FLOOR as well as a
cap, and the writer measured what that costs: at 390x844 the column is 359 but
the player computes 544, giving `scrollWidth` 552 against `clientWidth` 390 --
**162px of mobile overflow**. As `max-inline-size` the rule simply stops
applying below the cap. Identical at every width where the column exceeds the
cap, so the decision is unchanged in substance and the invariant still holds.

Independently re-measured at 1440 rather than taken on trust: column 765, prose
544, player 612, computed rule `min(960px, max(80%, 544px))`.
**1280 is where the formula earns its keep**: 80% of 605 is 484, so plain
`min(960px, 80%)` would have gone narrower than the 544px paragraph there --
the failure decision 5 was written to prevent, at a width nobody had measured.

### DEFERRED, needs an operator decision: `--docs-prose` 34rem -> 43rem

The other half of item 8 is deliberately NOT in this change, and it should be
re-decided rather than executed. `DocsLayout.astro:700-704` justifies 34rem by
measurement: the 765px column is ~101 characters, so 544px is ~72, inside the
65-75 target. **43rem = 688px is ~91 characters, outside it.** A pure token bump
therefore contradicts the reason the token has its value; the type scale would
have to move with it. DEFAULT if unanswered: leave 34rem as it is.

## Carried forward past this program, named rather than dropped

Two pieces are NOT done and have no owner. Both have ready-to-run briefs.

1. **Wave D gates 2, 4 and 5** -- `05-gates.md` carries the wiring path
   (`quality-www-build` already builds; `browser-smoke.sh` is the harness), the
   deliberate dark-band exemption gate 4 needs, and the correction that gate 5's
   shrink-only baseline must seed after ALL waves. Gate 5 additionally cannot
   start until item 4 below exists.

2. **Operator item 4, the sentence-wrapping copy fixes.** Needs the `<Sentences>`
   mechanism designed in `agent/PLAN-sentence-aware-wrapping.md`, which nobody has
   built. Gate 1 already enforces its precondition and is baselined at 51
   unwrapped renders, so the mechanism can land piecemeal without the gate being
   either useless or blocking.

Six decisions are parked for the operator in the sections above; none block
anything, and every one has a stated default.
