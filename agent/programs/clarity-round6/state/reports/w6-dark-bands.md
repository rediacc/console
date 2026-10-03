# w6 - dark bands go light (operator decision A7)

Wave 5 writer. Files owned and touched:

- `/home/developer/console/packages/www/public/styles/main.css`
- `/home/developer/console/packages/www/src/styles/solution-pages.css`
- `/home/developer/console/packages/www/src/styles/solution-video.css`
- `/home/developer/console/packages/www/src/styles/tutorial-video.css` (one stale comment)

Nothing outside `public/styles/main.css` and `src/styles/*.css` was written.
No build was run. No git state was changed.

## The mechanism I chose, and why it is not a token flip

`--sp-bg-hero` and `--sp-bg-dark` could not simply be re-pointed. `--sp-bg-hero` has
four consumers and only two of them are in scope:

    solution-pages.css   breadcrumb / page-header / hero / bottom-cta / roi-summary-item
    main.css:2402        .closing-cta       homepage, NOT in scope
    main.css:2993        .footer            explicitly out of scope, stays dark
    SPHomeHero.astro:51  homepage hero      NOT MINE

Flipping the alias would have taken the footer and the homepage hero with it. So I
added a BAND group to the single `:root` and re-pointed the in-scope RULES onto it.

New tokens, `main.css` section 3b:

    --color-bg-band          light var(--color-bg-alt) #ffffff   dark #111113
    --color-bg-band-accent   light var(--color-brand-tint) #eef3ea  dark #111113
    --color-brand-on-band    light #3d6834                        dark #7fa03f
    --color-band-dot         light rgba(0,0,0,0.05)               dark rgba(255,255,255,0.04)
    --color-band-glow        light rgba(74,124,63,0.1)            dark var(--color-brand-glow)

All five verified to resolve as designed in both themes by parsing the two `:root`
blocks and following the `var()` chains.

Two band surfaces rather than one, because the dark band was doing two jobs:

- **opening band** (`--color-bg-band`, the RAISED rung). Its neighbour below is always
  `.sp-problem` at `#f7f7f8`, so the raised rung reads as a step, and
  `--color-brand-primary` clears AA on it at 4.95:1.
- **emphasis bands** (`--color-bg-band-accent`, the ACCENT rung), `.sp-benefits` and
  `.sp-bottom-cta`. Their neighbours vary per page. On all 21 solution pages benefits
  sits between `techDiff` (#f7f7f8) and `.sp-downloads-row` (#f7f7f8), but on the 4
  persona pages `PersonaPage.astro:124-128` puts `.sp-comparison-section` (#ffffff)
  directly under it, and `SolutionConstellation` (#ffffff) sits directly above the
  bottom CTA on every solution page. The accent rung is the only rung that collides
  with NEITHER #ffffff nor #f7f7f8, so these two bands cannot dissolve into their
  neighbour on any page configuration.

Both accent and band collapse to `--color-bg-dark` in dark theme, so **dark mode is
visually unchanged** apart from three deliberate legibility fixes listed below.

## Every selector flipped

`src/styles/solution-pages.css`

| selector | was | now |
|---|---|---|
| `.sp-page > nav.sp-breadcrumb` | `background: var(--sp-bg-hero)` + 4 colour overrides | `var(--color-bg-band)`, the 4 colour overrides DELETED |
| `.sp-page > .sp-page-header` | `var(--sp-bg-hero)` / `var(--sp-text-white)` | `var(--color-bg-band)` / `var(--color-heading)` |
| `.sp-hero` | `var(--sp-bg-hero)` | `var(--color-bg-band)` |
| `.sp-hero::before` | `rgba(255,255,255,0.04)` dot grid | `var(--color-band-dot)` |
| `.sp-hero::after` | `var(--sp-brand-glow)` | `var(--color-band-glow)` |
| `.sp-hero h1` | `var(--sp-text-white)` | `var(--color-heading)` |
| `.sp-hero-sub` | `var(--sp-text-muted-dark)` | `var(--color-text-secondary)` |
| `.sp-benefits` | `var(--sp-bg-dark)` | `var(--color-bg-band-accent)` |
| `.sp-benefits .sp-overline` | `var(--sp-brand-primary)` | `var(--color-brand-on-band)` |
| `.sp-benefits h2` | `var(--sp-text-white)` | `var(--color-heading)` |
| `.sp-benefit-card` | `border: 1px solid var(--sp-border-dark)` | `var(--sp-border-light)` |
| `.sp-benefit-icon svg` | `stroke: var(--sp-brand-primary)` | `var(--color-brand-on-band)` |
| `.sp-benefit-card h3` | `var(--sp-text-white)` | `var(--color-heading)` |
| `.sp-benefit-card p` | `var(--sp-text-muted-dark)` | `var(--color-text-secondary)` |
| `.sp-bottom-cta` | `var(--sp-bg-hero)` | `var(--color-bg-band-accent)` |
| `.sp-bottom-cta::before` | `var(--sp-brand-glow)` | `var(--color-band-glow)` |
| `.sp-bottom-cta h2` | `var(--sp-text-white)` | `var(--color-heading)` |
| `.sp-bottom-cta p` | `var(--sp-text-muted-dark)` | `var(--color-text-secondary)` |
| `.sp-cta-tier-badge` | `rgba(255,255,255,0.45)` | `var(--color-text-secondary)` |
| `.sp-cta-command` | `rgba(255,255,255,0.25)` | `var(--color-text-tertiary)` |
| `.sp-cta-command-prompt` | `rgba(74,124,63,0.5)` | `var(--color-brand-on-band)` |

Three sites re-pointed that were NOT band flips, because `--sp-text-white` there meant
"ink on a brand FILL" and only coincidentally matched the band ink. On a light band the
coincidence would have become a bug:

| `.sp-btn-primary`, `.sp-timeline-new-step:nth-child(2)`, `.sp-step-number` | `var(--sp-text-white)` | `var(--color-on-brand)` |

One site deliberately NOT flipped: `.sp-roi-summary-item` is a dark CARD inside a light
section, not a page-level band. Re-pointed from `var(--sp-bg-hero)` to
`var(--color-bg-dark)` so it keeps today's appearance under a token whose name is still
true.

`src/styles/solution-video.css` (see "the in-hero player" below)

| `.sp-hero-media .tvp-toolbar .language-trigger` | `rgba(255,255,255,0.12)` / `rgba(255,255,255,0.24)` / `--sp-text-white` | `--color-bg-alt` / `--color-border` / `--color-text`, with the translucent-white pair moved under `:root[data-theme='dark']` |
| `... .language-trigger:hover` | `rgba(255,255,255,0.08)` | `var(--color-hover)`, dark variant theme-scoped |
| `.sp-hero-media .tvp-toolbar` | `var(--sp-text-muted-dark)` | `var(--color-text-secondary)` |

`public/styles/main.css`

| `.footer` | `background-color: var(--sp-bg-hero)` | `var(--color-bg-dark)` (same value, honest name) |
| `.closing-cta` | `background-color: var(--sp-bg-hero)` | `var(--color-bg-dark)` (same value, honest name) |

Two aliases retired, both provably zero-consumer after the flip, verified by grep across
`src/` and `public/`:

- `--sp-bg-dark` (only consumer was `.sp-benefits`)
- `--sp-border-dark` (only consumer was `.sp-benefit-card`; the token it aliased,
  `--color-border-on-dark`, still has `ImageModal.astro:111` and stays)

## Contrast, re-derived

Every ratio below was computed from the sRGB relative-luminance formula against the
ACTUAL composited surface, not assumed. Format: light band / dark band.

**Opening band, #ffffff / #111113**

| token | value L / D | ratio L / D |
|---|---|---|
| `--color-heading` | #1a1a1a / #e4e4e7 | **17.40** / **14.86** |
| `--color-text-secondary` | #5e5e63 / #a1a1aa | **6.45** / **7.36** |
| `--color-brand-primary` (breadcrumb hover) | #4a7c3f / #7fa03f | **4.95** / **6.29** |
| `--color-text` (breadcrumb current) | #1a1a1a / #e4e4e7 | **17.40** / **14.86** |
| `--color-brand-fill` button vs band, non-text 3:1 | #4a7c3f | **4.95** / n/a |
| `--color-band-dot` composite | #f2f2f2 / #1b1b1c | **1.12** / **1.10** (ornament, matched by design) |

**Emphasis bands, #eef3ea / #111113**

| token | value L / D | ratio L / D |
|---|---|---|
| `--color-heading` | #1a1a1a / #e4e4e7 | **15.45** / **14.86** |
| `--color-text-secondary` | #5e5e63 / #a1a1aa | **5.72** / **7.36** |
| `--color-text-tertiary` | #6e6e73 / #8f8f99 | **4.50** / **5.89** |
| `--color-brand-on-band` | #3d6834 / #7fa03f | **5.78** / **6.29** |
| `--color-brand-primary` REJECTED here | #4a7c3f | **4.39** fails AA |
| `--color-brand-secondary` REJECTED in dark | #3d6834 | n/a / **2.90** fails AA |
| `--sp-border-light` card edge (non-text) | #d2d2d7 / #2e2e32 | **1.34** / **1.39** |
| benefit icon chip composite rgba(74,124,63,0.15) | #d5e1d0 / #1a211a | stroke `--color-brand-on-band` on it: **4.80** / **5.49**, past the 3:1 a graphic needs |
| `--color-brand-fill` button vs accent band, non-text 3:1 | #4a7c3f | **4.39** / n/a |

**The inversion this proves.** `--color-brand-primary` is the exact token the dark-theme
note at `main.css:~474-486` records as having failed AA on the dark surface at 2.92:1
before it was brightened to #7fa03f. Flipping the surface inverts the calculation and it
now fails on the LIGHT accent band at 4.39:1 while passing on the dark one at 6.29:1.
That is why `--color-brand-on-band` exists as a separate token rather than reusing
either brand green: neither one is legible on both bands.

**Three composites that failed AA on the surface they were authored for**, fixed while
flipping (all measured on #111113, the surface they were written against):

| was | composite | old ratio | now | new ratio |
|---|---|---|---|---|
| `.sp-cta-tier-badge` rgba(255,255,255,0.45) | #7c7c7d | 4.52 (marginal) | `--color-text-secondary` | **7.36** |
| `.sp-cta-command` rgba(255,255,255,0.25) | #4c4c4e | **2.20 FAIL** | `--color-text-tertiary` | **5.89** |
| `.sp-cta-command-prompt` rgba(74,124,63,0.5) | #2e4629 | **1.82 FAIL** | `--color-brand-on-band` | **6.29** |

Relative hierarchy preserved: badge louder than command, both quieter than the paragraph.

**In-hero player, `solution-video.css`.** The old rules hardcoded translucent white,
which was right twice when the hero was dark in both themes. On a light hero that is the
SAME white-on-white failure the file was written to fix, themes swapped. Now:
light band gets the shared component's own tokens (#1a1a1a ink on #ffffff, **17.40**, with
a #d2d2d7 edge at 1.51 exactly as the trigger renders in the nav); dark band keeps the
translucent chip under `:root[data-theme='dark']`, where #e4e4e7 on the composited
#2e2e2f reads **10.69**. The toolbar label was a fixed #a1a1aa, which is **2.56 FAIL** on
#ffffff, and is now `--color-text-secondary` at **6.45** / **7.36**.

## The CTA / footer seam - what I chose

`.sp-bottom-cta` was designed to merge with `.footer`: both painted `--sp-bg-hero`, and
`SolutionPage.astro:176` moved `exploreSolutions` ABOVE the CTA specifically so nothing
would break the continuous black strip. A7 flips the CTA and keeps the footer dark, so
that merge cannot survive in light mode. My decision, written into the CSS at the
`.sp-bottom-cta` block:

1. **The CTA takes the ACCENT rung (#eef3ea), not the raised one.**
   `SolutionConstellation` directly above it is #ffffff. On `--color-bg-band` the closing
   call to action would have vanished into the section it exists to close. The accent
   rung reads 1.13:1 against #ffffff, the same step size the site already uses everywhere
   for #ffffff against #f7f7f8, so it is a step the reader can see without being a new
   idea.
2. **The footer's top edge becomes a HARD boundary at 16.74:1** instead of an invisible
   one. That is what a page terminator is for: the page ends and the reader can see it
   end. A merged pair can only say "this is all one thing", which is the opposite.
3. **In dark mode nothing changes.** `--color-bg-band-accent` and `--color-bg-dark` are
   both #111113 there, so the original merge is preserved byte for byte and the design
   note it came from still describes dark mode accurately.

The `.footer` and `.closing-cta` comments in `main.css` were rewritten to say this rather
than to keep describing the merge, and the `--color-bg-dark` note in the dark-theme block
(which said "the dark bands are the part of the page the theme does not flip") now says
what is actually true: only the footer is.

## Gate exit codes

    npm run check:ci-dead-css       exit 0
      "21 stylesheet(s), 1310 source file(s); 62 dead class(es), baseline 62."
      "no new dead CSS. 62 known finding(s) still baselined."
    npm run check:ci-css-dom-refs   exit 0
      "Rendered classes: 874. Styled: 1431. Unstyled: 31 (baseline 31)."
    npx biome format (4 edited files, then all 20 in the two dirs)  exit 0

No baseline drain was needed in either direction: no class selector was added or removed
by this change, only declarations inside existing rules. Both baselines are unchanged at
62 and 31.

## Defects found, not owned, not touched

1. **`SPHomeHero.astro:51,71,79` is the last consumer of `--sp-bg-hero`** and still paints
   the homepage hero black in both themes with `--sp-text-white` / `--sp-text-muted-dark`
   ink. A7 as scoped does not reach it, and I did not reach into a component. Consequence
   today: a solution page opens light and the HOMEPAGE opens black. When someone flips it,
   `--color-bg-band` + `--color-heading` + `--color-text-secondary` is the drop-in, and
   `--sp-bg-hero` can then be deleted from `main.css` entirely.
2. **`.closing-cta` (`main.css:2472-2489`) is the homepage's own dark closing band** and
   is deliberately left dark by me, because flipping it alone would leave the homepage
   opening black and closing light. It is in a file I own but it is one half of a pair
   whose other half is `SPHomeHero.astro`. It needs to move with #1, under one owner.
3. **`.sp-roi-section` and `.sp-how-it-works` are both `--sp-bg-white`**
   (`solution-pages.css` lines with `background: var(--sp-bg-white)` at the
   `.sp-roi-section` and `.sp-how-it-works` rules) and render adjacent on the 17
   `ALL_SECTIONS` pages: `costCalculator` is immediately followed by `howItWorks` in
   `SolutionPage.astro:113-131`. Two #ffffff sections meet at 1.00:1 with no boundary.
   Pre-existing, unrelated to A7, and I did not change it because moving one of them
   changes a section rhythm this wave was not asked to decide.
4. **`.video-player-mount:not([data-hydrated])` paints `#0b0e14`**
   (`solution-video.css:70-75`) - a near-black rectangle now reserved on a #ffffff hero.
   This is the known open design issue about near-black videos on a light hero, which I
   was told is handled separately. Flagged so nobody reports it twice: after this change
   it is visible BEFORE hydration as well as after.
5. **`main.css:1840` narrates "on top of the dark hero"** inside a historical bug story
   about `.nav-cta-btn`. It is a past-tense account, not a live claim, so I left it, but
   the phrase no longer matches the tree.
6. **The `.nav` has no bottom border** (`main.css:945-955`, `background-color:
   var(--color-bg-alt)` = #ffffff). Against the new #ffffff opening band the fixed nav has
   no visible lower edge on a solution page, where the black hero used to give it one.
   This is not a regression relative to the rest of the site - the nav already sits on
   #f7f7f8 at 1.07:1 on every other page - but a solution page is where it will be
   noticed first. A one-line `border-bottom: 1px solid var(--color-border-subtle)` on
   `.nav` would fix it site-wide; I did not take it because it touches every page on the
   site and that is a design decision, not a band flip.

## What still needs a build to confirm

Everything above is derived from the source and from arithmetic; none of it was seen
rendered, because I was instructed not to build. The two things worth a human eye on the
next coordinated build are (a) the hero at 1440 and 390 on `/en/solutions/encryption`,
where the dot grid and the glow are now whispers rather than lifts, and (b) the
`SolutionConstellation` -> `.sp-bottom-cta` -> `.footer` sequence at the bottom of a
solution page, which is the seam decision above.
