# 03. Chrome and surfaces (Wave A)

Status: planned, not started. Covers operator items 3, 5, 6, and the accessibility defects
that live in this wave's files.

**File ownership for this wave.** `src/components/Navigation.tsx`,
`src/components/Footer.astro`, `public/styles/main.css`,
`src/styles/language-switcher.css`, `src/styles/solution-pages.css`.

**`public/styles/main.css` belongs to this wave alone.** It is 3,421 lines and two
concurrent writers corrupt it. If another wave needs a rule in it, that wave asks; it does
not edit.

## Item 5: the footer language switcher (do this first, it is the cheapest proof)

Light theme renders the trigger as `#e4e4e7` text on `#ffffff`, about 1.13:1, with an
invisible border. Dark theme is correct at 13.7:1, so this is a light-theme-only bug.

Root cause: `main.css:2797-2806` re-points five custom properties on `.footer` so its
descendants read on the black band, but **it does not re-point `--color-bg-alt`**, and
`src/styles/language-switcher.css:15` paints the trigger surface from exactly that token.

**Fix:** add `--color-bg-alt` and `--color-hover` to that `.footer` token block, pointing at
the dark values already present at `main.css:471` and `:477`. One edit fixes the trigger,
the panel and every row, and it stays consistent with the block's own stated design
(`main.css:2787-2792`), which is to re-point tokens on the container rather than edit thirty
`.footer-*` rules.

**Do NOT patch `language-switcher.css`.** The same component mounts in the header with
different styling and you would break it.

**Verification with a free control:** axe already flags `.language-name` as a serious
`color-contrast` violation on `/en`. Re-run `agent-browser a11y http://localhost:4321/en` in
both themes (`agent-browser set media light|dark`) and require that node to clear.

## Item 3: condense the nav instead of blanking it

Read `01-verified-context.md` first: there is no hide-on-scroll and no direction detection.
What exists is `Navigation.tsx:58-112` clamping `y = min(max(scrollY,0), 80)` and writing
four custom properties, plus the body attribute `data-nav-collapsed` at `y >= 80` which
applies `pointer-events: none` through `main.css:932-934`. The result is an empty fixed bar.

**Locked by the operator:** cross-fade to a condensed row rather than fading to nothing. As
the full nav fades out, a slim row fades in carrying the mark, a breadcrumb of the current
page, the search trigger and the primary CTA. The full nav returns on scroll-up.

Constraints that will bite:

- **Keep the single `requestAnimationFrame`-coalesced listener.** Do not add a second scroll
  listener. The existing one already drives everything through custom properties, which is
  the right seam for a cross-fade.
- **Drop the `pointer-events: none` rule.** The bar is now interactive at every scroll depth,
  so that rule becomes a bug rather than a tidy-up.
- **Scroll-up return is new.** There is no direction detection today, so you are adding one.
  Keep it inside the same handler and the same rAF.
- `--nav-top-offset` is not a constant: `AnnouncementBar.astro:32` sets an announcement
  height token and overwrites it with the measured pixel height. Anything you position off
  the nav must derive from the token, not a literal.
- **Reuse the docs breadcrumb** rather than inventing a second one.
- Desktop and mobile menus have drifted apart; `evidence/EXPLORE-chrome.md` section 1.5
  documents the divergence. Do not let the condensed bar deepen it.

**Verification:** at `scrollY` 0, 40, 200 and 800, assert the condensed bar is present and
its computed `pointer-events` is not `none`, and assert the primary CTA is clickable at
depth 800. Then scroll up and assert the full nav returns.

## Item 6: one surface ladder

A token ladder already exists (`evidence/EXPLORE-chrome.md` section 3.2). Three
unreconciled mechanisms sit on top of it (section 3.3). Reduce to one.

Five concrete defects to clear:

1. **Two near-identical darks.** `#111113` and `#1a1a1a` land adjacent on `/en/for-devops`
   (`sp-benefits` then `sp-bottom-cta`), producing a visible seam. Collapse them to one
   token unless there is a reason for two, and if there is, name it in the token.
2. **`/en/pricing` runs six consecutive `section-light` sections** at the same `#f7f7f8`.
   Nothing reads as a section boundary. Give the page real alternation.
3. **`.pricing-hero.section-dark` on `/en/disaster-recovery` computes transparent.** A
   dark-classed hero renders light. Find why the class provides no background there.
4. **The homepage bypasses the system entirely**, with bespoke `sp-not-a-slice`,
   `home-difference` and `cf-pricing-section` backgrounds. Migrate them onto
   `section-light` / `section-dark`.
5. **`#eef3ea` on `sp-stats` is a one-off.** Fold it into the ladder as a named accent
   surface or delete it.

**Verification:** re-run the section survey that produced the six-colour table and assert no
two adjacent sections resolve to the same surface on `/en`, `/en/pricing`,
`/en/for-devops` and `/en/disaster-recovery`. Wave D turns that survey into a gate.

## Accessibility defects in this wave's files

From the axe baseline in `01-verified-context.md`:

- `heading-order`: `#footer-product-heading` skips a level.
- `aria-valid-attr-value` (critical): `.persona-menu-trigger`, `#learn-menu-trigger`,
  `#nav-cta-caret`.
- `aria-allowed-role` (minor): `#navigation-sidebar`.
- `color-contrast`: `.footer-version` and `.form-input`, alongside `.language-name`.

`aria-prohibited-attr` on the 15 `.cf-feature-info` divs is pricing-card markup; take it
here if it is in an owned file, otherwise hand it to wave B with the node list.

## Cleanup once wave B has landed

Delete `main.css:1956-2090` (`.difference-row*`, `.difference-zoom*`), the dead remains of
the previous alternating Difference implementation. **Only after wave B's replacement is in**,
and confirm `check:ci-dead-css` and `check:ci-css-dom-refs` are both still green: those two
gates have different scopes, and deleting markup without its component-scoped CSS passes the
first and fails the second.
