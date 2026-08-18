# www simplification program

**Started:** 2026-08-17. **Phase:** research. **Nothing in `packages/www` is
modified, by operator instruction.**

## Why this exists

The operator's assessment: the marketing site is *"super complex"* and needs
simplification. Their reference points are **https://claude.com/** for simple
design generally, and **https://www.anthropic.com/** specifically for the
homepage hero, which they describe as containing "a special component".

## Shape of the program

Eight domain specialists research in parallel, each owning a disjoint slice of
the site. **The researcher becomes the implementer**: each specialist is building
the knowledge it will later execute against, so its research document is written
to survive compaction and hand its own future self everything it needs.

Shared rules, the site's real CSS cascade, the running dev server, and the
agent-browser working notes all live in **[00-BRIEF.md](00-BRIEF.md)**. Read it
before touching anything here.

## The fleet

| Specialist | Domain | Owns at implementation time | Research doc |
|---|---|---|---|
| `sx-tokens` | Colors, dark/light theme, typography, spacing, radii, shadows, motion, and the consistency drift between them | the `:root` block in `BaseLayout.astro`, `public/styles/main.css` + `responsive.css`, token-level `src/styles/` | `RESEARCH-tokens.md` |
| `sx-chrome` | Top nav, both mega menus, language switcher, search, footer, announcement bar | `Navigation.tsx`, `MegaMenu.tsx`, `PersonaMegaMenu.tsx`, `LanguageMenu.tsx`, `SearchModal.tsx`, `Footer.tsx`, `AnnouncementBar.astro`, `Breadcrumb.astro`, `mega-menu.css`, `persona-mega-menu.css`, `search-modal.css` | `RESEARCH-chrome.md` |
| `sx-hero` | The anthropic.com hero component dissected, plus our above-the-fold | the hero section of `[lang]/index.astro` — **see the collision note below** | `RESEARCH-hero.md` |
| `sx-homepage` | Everything below the fold on the homepage; section inventory and what to cut | below-fold `[lang]/index.astro` and homepage-only components — **see the collision note below** | `RESEARCH-homepage.md` |
| `sx-rtl` | Anchor/slug root cause, the locale-derived-identifier class, and the RTL audit | `src/utils/sidebar-behavior.ts`, `src/utils/slug.ts`, `DocsTopTabs.astro`, the `[dir='rtl']` rules, and the direction metadata in `BaseLayout.astro:65` | `RESEARCH-rtl-anchors.md` |
| `sx-bughunt` | Systematic cross-route, mobile, dark-theme and cross-locale bug hunt | **owns no source.** Files findings against other specialists' surfaces; like `sx-metrics`, it is a checker, not a writer | `RESEARCH-bugs.md` |

**Ownership collision, found by `sx-process` and fixed here.** `sx-hero` and
`sx-homepage` both write `src/pages/[lang]/index.astro`, and §4 of
`01-SYNTHESIS.md` originally scheduled them **concurrently** — one file, two
writers, which is exactly what the repo's 2-writer rule forbids. They are now
split across separate slots (`W2a` hero, `W2b` homepage) in
`02-EXECUTION-SYSTEM.md` and must never run in the same slot. `sx-chrome` runs
**solo** for the same reason: its surface renders on every page, so it has no
disjoint partner.
| `sx-primitives` | Buttons, cards, badges, forms, modals, tabs, icons, focus states — the variant census | shared primitive rules in `main.css`, form/modal/tab components | `RESEARCH-primitives.md` |
| `sx-pricing` | Pricing page, comparison matrix, checkout entry. `pricing-page.css` is 2,321 lines | `[lang]/pricing.astro`, `pricing-page.css`, the pricing components, `[lang]/checkout/` | `RESEARCH-pricing.md` |
| `sx-docs` | Docs and blog reading surfaces, sidebar depth, route sprawl, per-page stylesheets | `DocsLayout.astro`, `ContentLayout.astro`, `DocsSidebar.astro`, `DocsTopTabs.astro`, `Sidebar.tsx`, the per-page stylesheets | `RESEARCH-docs.md` |
| `sx-metrics` | The falsifiable baseline: bytes, DOM, unused CSS, color/type entropy, a11y, page height. Owns no source, so it verifies everyone else | nothing in `packages/www` — measurement and verification | `RESEARCH-metrics.md` |

## Measured starting point

Established before the fleet launched, 2026-08-17:

| Thing | Count |
|---|---|
| Components | **80** (`find src/components -name '*.astro' -o -name '*.tsx'`). An earlier figure of 43 counted only the top level and missed the `solution-pages/`, `docs/`, `resources/`, `tutorial/` and `icons/` subdirectories — `solution-pages/` alone holds ~34 files |
| Pages | 61 (across a `[lang]` tree, 13 locales) |
| Layouts | 3 |
| CSS in `src/styles/` | 8,806 lines / 20 files |
| CSS in `public/styles/` | 4,697 lines / 5 files (`main.css` alone is 3,421) |
| Largest single stylesheet | `pricing-page.css`, 2,321 lines |
| Astro components with an inline `<style>` | 14 |
| Homepage height @1440x900 | 7,347px, roughly 8 screens |
| Fonts | Inter x4 weights, JetBrains Mono x2 |

## Order of work

1. **Research** (current) — eight documents land here.
2. **Synthesis** — one plan reconciling them, with the cross-domain
   consequences resolved and a sequence that avoids two specialists editing one
   file. `sx-tokens` and `sx-primitives` both reach into `main.css`; that
   collision is known and must be sequenced, not parallelised.
3. **Implementation** — specialists re-activated as writers, at most two
   concurrently with disjoint file ownership, per the repo's standing rule.
4. **Verification** — `sx-metrics` re-runs its own recorded measurements and
   reports the before/after delta.
