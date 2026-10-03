# W4C: video palette (clarity-round6, Wave 3 part C)

Executed 2026-08-27. The fleet's ground moves from near-black to light, alarm red moves
to a warm ember, and the palette becomes a single module instead of ten copies. The
rubric, config constants and CONTRACT moved in the same change, so the visual gate now
enforces the new palette instead of reverting it.

## The new palette (remotion/src/palette.ts, the one source of truth)

| token | hex | role | contrast on bg |
|---|---|---|---|
| bg | #f4f7fb | frame ground (one step off the site's #ffffff hero band) | - |
| surface | #ffffff | cards, rows | - |
| surfaceAlt | #e2e8f0 | tracks, dividers, wells | - |
| panel | #141820 | framed dark panel for dark-classified art and footage title cards | - |
| accent (SOLUTION_COLOR) | #0f766e | mechanism/proof accent, deep brand teal | 5.1:1 |
| danger (PROBLEM_COLOR) | #c2410c | hook/problem accent, warm ember, NOT alarm red | 4.8:1 |
| warning / changed | #a16207 | checking / changed-block states, golden so it never reads as failure | 5.0:1 |
| textPrimary | #0f172a | ink | 15.9:1 |
| textSecondary | #475569 | secondary ink | 7.0:1 |
| textMuted | #64748b | captions, credits | 4.4:1 |
| overlayInk / overlayInkSoft | #f8fafc / #cbd5e1 | ONLY over darkened footage or the dark panel | - |

Plus derived exports: CARD_SHADOW (soft slate, replaces black plumes), SCRIM_LIGHT_* /
SCRIM_DARK_BOTTOM, LOGO_INK_FILTER (invert(0.92): the staged brand mark is monochrome
near-white #f0f0f0 and would vanish on the light ground), STAGED_ICON_INK_FILTER
(brightness(0.64) saturate(1.15): deepens step6000's staged old-palette SVG icons at
render time).

Reasoning: the operator's complaint was "too dark for visitors. Doesn't bring
happiness", and the site's solution heroes are now light (#ffffff band), so a
near-black video was also a black rectangle on a white page. A full inversion answers
both. The emotional grammar survives: hook/problem still read warm danger, but ember
on a light ground is urgency, not dread; mechanism/proof stay teal, deepened for
contrast. Note the site brand green (#4a7c3f) was considered and deliberately NOT
adopted for the solution accent: step6000's staged teal icons are outside this seam,
and mixing green accents with teal icons would fracture the frame.

## Files repointed at the module

remotion/src/: Scene.tsx (PROBLEM_COLOR/SOLUTION_COLOR now imported),
SolutionVideo.tsx (frame bg, clock accent, corner-bug ink filter), palette.ts (new),
components/BrandOutro.tsx, components/CaptionBand.tsx (dark pill -> white chip, dark
ink), components/TimePassingClock.tsx, scenes/BigStat.tsx, BlockShare.tsx,
ContrastScene.tsx, DataFlow.tsx, IconScene.tsx (staged-icon + brand-logo ink filters),
IllustrationScene.tsx, KineticText.tsx, RaceClock.tsx, StockVideoScene.tsx,
SystemStack.tsx, props.ts (doc wording). Zero palette hexes remain outside palette.ts
(verified by grep; the only rgba(11,14,20) left is the deliberate vignette/scrim over
real footage).

Structural changes beyond retinting:
- IllustrationScene: every illustration is now framed in a card. needsLightBg=true
  (dark-ink art) -> white card; needsLightBg=false -> DARK PANEL card, because those
  40 catalog entries were classified legible on the OLD dark ground and their fills
  are #e6e6e6/#fff - raw on the light bg they wash out to invisible. The raw
  full-bleed path and the now-unused KenBurnsContainer wrapper were removed.
- StockVideoScene: overlay contrast is footage-relative (dark scrim + light ink,
  unchanged); the no-footage title-card fallback keeps a dark panel ground because its
  ink is light. Footage grade lifted from brightness(0.82) to 0.92.
- CaptionBand: white chip, dark ink, works over footage and light ground alike.

## Gate and convention edits (the part that stops reversion)

- config.py:218-228: PROBLEM_COLOR="#c2410c", SOLUTION_COLOR="#0f766e", comment
  records the retirement of #f87171/#0b0e14 and why.
- prompts/visual_comprehension.py Check 2: hook/problem dominant accent must read
  warm danger ember (#c2410c or similar), mechanism/proof deep teal (#0f766e or
  similar), plus an explicit instruction NOT to flag the light ground as "calm" on a
  problem frame. Check 3 wording follows. The BRANDING audit now REQUIRES the light
  ground (#f4f7fb or similar), flags near-black grounds except framed panels, and
  requires dark ink except over footage/panels. The old "Background must be dark"
  line, which would have re-darkened the fleet, is gone.
- prompts/storyboard.py: turn-beat climax, icon tone, dataFlow status, raceClock and
  contrast guidance all say ember/teal instead of red/teal; illustration card layout
  guidance updated to the two-card model.
- CONTRACT.md "Emotional color convention": table now #c2410c/#0f766e with the
  history and the light-ground rule; semantic_sense wording and the contrast template
  description updated; the "blank dark frame" outro note updated.

## Proof: stills inspected and measured

11 after-stills across 10 templates (slug home, plus ai-pentesting for bigStat and
audit-trail for raceClock, plus one vertical), against 8 before-stills. In scratchpad:
/tmp/claude-1000/-home-developer-console/e580532b-53bf-4b76-92d8-b15b242c96d5/scratchpad/stills/{before,after}/

Measured dominant colours (every 7th pixel, 24-step buckets):
- BEFORE: motion-graphics frames were 70.9-97.6% near-black (#000000 bucket = the
  #0b0e14 ground). E.g. hook kineticText 95.5% black + 1.5% #f06060 red.
- AFTER: the same frames are 75.1-96.2% near-white (#f0f0f0 bucket = #f4f7fb ground).
  Hook kineticText: 93.0% light ground + 1.5% #c03000 (the ember). SystemStack hook:
  96.2% light, ember accents. Mechanism blockShare: 91.4% light with #489090/#d8f0f0
  teal family. Panel-card illustration frames: 75-77% light + 12-15% dark panel.
  BrandOutro: 98.4% light with the mark as ink. Stock footage frames remain footage.
- On the operator's axis: red share of a hook frame went from "red glow on black
  dread" to a 1.5% ember accent on a light ground; no frame's GROUND is dark any more
  outside deliberate framed panels and real footage.

Renders used --gl=swangle + chrome-cpu-raster.sh throughout. tsc --noEmit clean.

## Found, not owned (exact edits included)

1. steps/step6000_render.py:90-96 still stages SVGs in the OLD palette
   (_COLOR_PRIMARY "#2dd4bf", _COLOR_SUPPORTING "#94a3b8", _COLOR_BRAND_BADGE
   "#f1f5f9", _COLOR_DANGER "#f87171"). Compensated at render time by
   STAGED_ICON_INK_FILTER and LOGO_INK_FILTER in IconScene.tsx (verified in stills:
   staged clock icon reads deep brick, staged server icon deep teal). The clean fix is
   _COLOR_PRIMARY="#0f766e", _COLOR_DANGER="#c2410c", _COLOR_SUPPORTING="#475569",
   _COLOR_BRAND_BADGE="#0f172a" - but it MUST land together with removing those two
   filters from IconScene.tsx, or icons double-darken to near-black.
2. prompts/stock_select.py:52 says footage should fit a "dark, teal-accented brand".
   Still roughly true (footage keeps a dark scrim + teal tint) but the "dark" wording
   is now stale; harmless, one-line edit when that file's owner is in there.
3. assets/svg-library/build_preview.py:24 BG="#0b0e14" - dev preview tool only.
4. visual_comprehension.py's TERMINAL CARDS audit block is vestigial (the terminal
   template no longer exists); it can never fire, left as-is.
5. Old processing artifacts (e.g. ai-pentesting props.json) still carry a cta scene
   from before the CTA cut; Scene.tsx maps it to the solution accent, renders fine.
