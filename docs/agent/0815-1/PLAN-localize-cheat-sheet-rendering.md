# PLAN: Localize the rendered RDC cheat sheet by deleting its private rendering path
Status: accepted, scheduled post-push
Owner: 97604f47
Updated: 2026-08-16

## Verdict in one paragraph

The cheat-sheet page does not have a localization bug. It has a **second document**.
`packages/www/src/marp/rdc-cheat-sheet.marp.md` is a 371-line English-only document that
no gate scans and no translator touches, and it is the one every reader sees in all 13
locales. `packages/www/src/content/docs/<lang>/rdc-cheat-sheet.md` is a separate,
newer, better, fully-translated document that reaches the `.md`/`.txt` exports, the ZIP,
the search index and the freshness gate, and never reaches a rendered page. The fix is
not to teach the marp path about locales. It is to **delete the marp path**, render the
content collection, and reproduce the card-grid + print presentation in about 40 lines of
CSS and a 30-line HTML splitter. Marp is not load-bearing; it is actively fought.

---

## 1. Root cause, with verified anchors

### 1.1 One English source, thirteen routes

`packages/www/src/pages/[lang]/docs/rdc-cheat-sheet.astro:9`

```
import markdownSource from '../../../marp/rdc-cheat-sheet.marp.md?raw';
```

`getStaticPaths` at `rdc-cheat-sheet.astro:15-19` emits one route per `LANGUAGES` entry,
and `rdc-cheat-sheet.astro:26` renders that same string for every one of them. `lang`
(`rdc-cheat-sheet.astro:21`) is consumed only by `DocsLayout` for chrome, never by the
body.

### 1.2 The localized document exists and is shadowed

`packages/www/src/pages/[lang]/docs/[slug].astro:8-30` builds a route for every entry in
the `docs` collection, which includes `rdc-cheat-sheet.md` in all 13 locales (verified:
`ls packages/www/src/content/docs/*/rdc-cheat-sheet.md` returns 13 files, 137 lines en,
139 each locale). Astro gives the literal segment `rdc-cheat-sheet.astro` priority over
the dynamic `[slug].astro`, so the collection entry is built for its `.md`/`.txt`
siblings but never for its HTML page.

### 1.3 Verified in the built output

The `dist/` on this branch was produced by a real `astro build` (timestamps 2026-08-16
09:49). Grepping it:

| Artifact | Language served |
|---|---|
| `packages/www/dist/de/docs/rdc-cheat-sheet/index.html` | **English** (`Quick Reference`, `Repository Lifecycle`; 13 `<section>` elements; 75 `marp` occurrences) |
| `packages/www/dist/de/docs/rdc-cheat-sheet.md` | **German** (`## Repository-Lebenszyklus`, `Neues Repository auf einer Maschine erstellen`) |
| `packages/www/dist/de/docs/rdc-cheat-sheet.txt` | **German** (same body) |

Same URL family, same build, two different languages. The human reader gets English; the
LLM-facing export gets German. That asymmetry is the bug in one line.

### 1.4 Why every gate stayed green

Both CLI-accuracy validators root at the content collection and cannot see `src/marp/`:

- `packages/www/scripts/validate-docs-cli-usage.js:162` -> `DOCS_DIR = .../src/content/docs`
- `packages/www/scripts/validate-content-accuracy.js:28` -> `DOCS_DIR = <root>/src/content/docs`
- `packages/www/scripts/generate-search-index.js:56` -> indexes `src/content/docs`

`validate:translation-freshness` compares a `sourceHash` stamped in each locale file's
frontmatter (e.g. `packages/www/src/content/docs/de/rdc-cheat-sheet.md:7`,
`sourceHash: "ae49dd7fbc179d35"`) against a digest of the English **collection** file
(`validate-translation-freshness.js:85`). It knows nothing about what the page renders.
Run today on this tree: `✓ Translation freshness checks passed`. That is exactly the
failure mode the brief names: a green gate over content the reader never sees.

**I ran both gates on this tree.** `npm run validate:docs-cli-usage` ->
`✓ All targeted docs command examples are valid.` `npm run validate:translation-freshness`
-> `✓ Translation freshness checks passed`. No baseline file exists
(`packages/www/scripts/docs-cli-usage-baseline.json` is absent, so
`p7-backlog.js:loadBacklog` returns `{}`), which means the CLI-usage gate is fully live,
not partially waived. Its clean bill of health today is a statement about
`src/content/docs` only.

### 1.5 The two documents have already diverged badly

Command inventories (`grep -oE 'rdc [a-z-]+( [a-z-]+)?' | sort -u`) differ in **31**
entries. Not a drift risk: an accomplished drift.

Only in the marp deck (the page that ships): `rdc run`, `rdc run -f`, `rdc repo tunnel`,
`rdc repo exec`, `rdc repo logs`, `rdc repo resize`, `rdc repo expand`, `rdc repo admin`,
`rdc cluster snapshot`, `rdc datastore snapshot`, `rdc config list`, `rdc config set`,
`rdc machine health`, `rdc machine scan-keys`, `rdc vscode list`, `rdc vscode cleanup`.

Only in the content collection (the document nobody renders): `rdc backup run`,
`rdc backup status`, `rdc backup cancel`, `rdc backup verify`, `rdc repo promote`,
`rdc repo pull`, `rdc repo migrate`, `rdc repo secret`, `rdc repo delete`,
`rdc storage list`, `rdc storage browse`, `rdc machine prune`, `rdc machine deprovision`,
`rdc --config`.

Two of the marp-only entries are **already invalid against the live command tree**. I
called the gate's own parser directly on them
(`packages/www/scripts/lib/cli-reference-catalog.js:339`, `parseRdcCommand`):

```
run -f container_stats -m mach --param repository=r   -> ok:false  unknown-command  near:"run"
cluster snapshot foo                                  -> ok:false  excess-positional-args
```

(The `rdc` prefix is dropped in the two lines above ON PURPOSE. They are examples
of input the parser REJECTS, and `check:cli-docs` cannot tell a command being
demonstrated as invalid from one being recommended -- the same blindness that had
it flag a `backup ls` mention inside a "do NOT add this" sentence.)

`rdc run` is not incidental in the deck: it has a dedicated card
(`src/marp/rdc-cheat-sheet.marp.md:348-361`, "Rediaccfile Functions") plus uses at
`:126` and `:228`. Per `CLAUDE.md`, `rdc run` is hidden from help and MCP and is a
debugging escape hatch, so the live public cheat sheet is teaching a hidden debug verb as
a headline feature, in 13 languages. The localized collection document already handles
this correctly: its "Debug and Escape Hatch" section
(`packages/www/src/content/docs/en/rdc-cheat-sheet.md:130-137`) routes through
`rdc term connect <repo>@<machine> -c "docker ..."` instead.

---

## 2. Is Marp load-bearing? No. It is incidental, and it is being fought.

Read `packages/www/src/utils/marp.ts` and `packages/www/src/styles/marp-cheatsheet.css`.

Marp contributes exactly two things to this page:

1. `---` in the markdown becomes a `<section>` boundary.
2. `<!-- _class: cat-teal -->` becomes `class="cat-teal"` on that section.

Everything else Marp does is explicitly switched off or overridden:

| Marp behaviour | How the code disposes of it |
|---|---|
| SVG slide wrapping | `inlineSVG: false` (`marp.ts:47`) |
| Browser runtime JS | `script: false` (`marp.ts:44`) |
| Generated theme CSS | **discarded**; only `html` is destructured (`rdc-cheat-sheet.astro:26`), with the reason in the comment at `:23-25` |
| Fixed slide geometry | overridden twice: `marp-cheatsheet.css:11-17` and `rdc-cheat-sheet.astro:105-113`, with `width/height/min-height/position/container-type` all `!important` |

A dependency whose entire output is neutralised by `!important` in two separate files is
not providing the presentation. The presentation comes from the 447 lines of
`marp-cheatsheet.css` and the 255 lines of scoped `<style>` in the `.astro` page, neither
of which needs Marp to exist.

**The slide-deck framing is not the point; the print sheet is.** The genuinely valuable
behaviour on this page is `@page { size: A4 landscape }` plus the 2-column
`break-inside: avoid` print rules (`rdc-cheat-sheet.astro:139-308`), which turn the doc
into a printable one-page reference. That must survive. It is pure CSS and does not
depend on Marp at all.

So: **drop `@marp-team/marp-core`.** The two features it provides are replaced by a
30-line HTML splitter over `<h2>` boundaries, which is also more robust, because it keys
on a structure the translators already preserve (all 13 locale files carry exactly 10
`## ` headings; verified by `grep -c '^## '` across `src/content/docs/*/rdc-cheat-sheet.md`).

---

## 3. Where localized content should come from

### Options weighed

**(A) Twelve more marp files, one per locale.** Rejected. It creates a second
translation surface with no `sourceHash` plumbing, no freshness gate, no
`validate-docs-cli-usage` coverage, and no search indexing, and it doubles every future
CLI-rename sweep from 13 files to 26. Build cost trivial, **maintenance cost the highest
of the three**, and it institutionalises exactly the divergence that caused this bug.

**(B) Generate the marp source from the content collection at build time.** Rejected, but
it is the near-miss worth naming. It fixes the language bug and keeps divergence
impossible, at the price of keeping a generator, keeping the Marp dependency, and keeping
a rendering path with two representations of one document in memory. Maintenance cost:
one generator script plus its conventions (which `##` starts a card, where tints come
from) plus a dependency that contributes nothing the generator could not do directly.
It buys nothing over (C).

**(C) Render the content collection directly and delete Marp. RECOMMENDED.** One document
per locale, in the collection, already translated, already gated. The card grid becomes a
presentation concern implemented in the page, where it always actually lived. Maintenance
cost after landing: **zero incremental**. A future CLI rename touches the same 13 files it
already had to touch; nothing else exists to keep in sync. Net deletion of one dependency,
one util module, one page, one 371-line document.

### The recommended shape, concretely

Do **not** keep a dedicated `rdc-cheat-sheet.astro` route. Route it through
`[slug].astro` like every other doc, switched by a frontmatter flag. Reasons:

- The dedicated page hardcodes English metadata (`rdc-cheat-sheet.astro:31-35`:
  `title: 'RDC CLI Cheat Sheet'`, English `description`). Going through `[slug].astro`
  takes `doc.data` (`[slug].astro:47`), so `<title>`, `<meta description>` and the
  breadcrumb become localized for free. Fixing the body alone would leave the page head
  English.
- The dedicated page passes no `availableLanguages` and no `showFallbackNotice`
  (`rdc-cheat-sheet.astro:38-44` versus `[slug].astro:46-53`), so the language switcher
  and the fallback banner are degraded on it today. That is a second, smaller bug that
  this route change fixes without extra work.
- It removes the implicit static-beats-dynamic route shadowing entirely. Right now the
  correctness of the whole page rests on an unwritten Astro precedence rule.

So `[slug].astro` gains one conditional: when `doc.data.cardGrid` is true, wrap
`<Content />` in `<CheatSheetGrid>`; otherwise render as today.

---

## 4. Divergence risk and the gate

### What divergence remains after (C)

For the cheat sheet specifically: **none**. There is exactly one body per locale, and the
page renders it. Divergence is not policed, it is made unrepresentable. That is the
correct answer to "name the gate that would make divergence impossible": the gate is the
deletion.

But the **class** of bug survives (a page that renders something other than its locale's
content), and the brief is right that nothing notices it. Two gates, one primary.

### Gate 1 (primary): `check:ci-docs-render-parity`, over built HTML

**Where it runs.** As a new step in the existing `quality-www-build` job
(`.github/workflows/ci-quality.yml:1045-1116`), immediately after the
`Build www (produces dist/route-manifest.json)` step and alongside `Redirects`, `SEO` and
`CTA bolt`. That job already pays for the one expensive input (`npm run build:www`), and
its comment block at `:1037-1044` states this is precisely what it exists for. No new
build cost.

**What it asserts, mechanically.** For every locale `L` in `SITE_LOCALES` and every docs
slug `S` for which `packages/www/src/content/docs/L/S.md` exists:

1. Parse the `^## ` headings out of the source markdown.
2. Read `packages/www/dist/L/docs/S/index.html` and extract the article body (the
   container `DocsLayout` already emits; scope to it so sidebar/TOC text cannot satisfy
   the assertion by accident, which matters because the German TOC in today's dist
   contains the English heading text).
3. Assert every source heading's text appears in that body.

Decidable, no heuristics, no fuzzy matching, no per-file baseline. A missing heading is a
page that is not rendering its locale's document.

**The planted defect it must catch (control test).** Following the repo's existing
convention (`scripts/__tests__/check-translation-key-usage.control.ts` is the only member
of that directory today), ship
`scripts/__tests__/check-docs-render-parity.control.ts`. It builds a synthetic fixture
tree with a locale source containing `## Repository-Lebenszyklus` and a built HTML file
containing `<h2>Repository Lifecycle</h2>`, runs the checker against it, and asserts a
**non-zero exit naming the missing heading**. A second case (matching heading) must exit
zero, so the control proves the gate discriminates rather than merely failing.

**Would it have caught today's bug?** Yes, on the day the page was written: German source
has `## Repository-Lebenszyklus`
(`packages/www/src/content/docs/de/rdc-cheat-sheet.md`), German dist body has
`Repository Lifecycle`. Red.

### Gate 2 (cheap complement): no fixed-locale content imports in pages

A source-level grep gate, runnable in the fast lane with no build:
`packages/www/src/pages/**` and `src/layouts/**` may not import a markdown file via
`?raw`, nor import anything under `src/content/docs/en/`. Rationale: any page reaching
into a single locale's content by path is, by construction, serving one language to
thirteen routes.

**Control:** it must be RED on today's tree. `grep -rn '?raw' packages/www/src/pages`
returns exactly `rdc-cheat-sheet.astro:9` (markdown) and `:13` (CSS). The rule must
allow the CSS `?raw` and reject the markdown `?raw`, and the control test asserts both
halves. After the marp deletion the gate is green with zero suppressions, which is the
right end state: it is not being introduced pre-satisfied.

Gate 2 is a proxy and cannot replace Gate 1 (a page could hardcode English inline). It is
worth having anyway because it is instant and it names the mistake precisely at the point
someone would make it again.

---

## 5. Implementation, in dependency order

Each step names its exact files. Steps 1 to 2 are the content decision; 3 to 6 are the
mechanism; 7 to 8 are the gates. Steps 3 to 6 can proceed in parallel with step 2's
translation work, since they do not touch locale files.

**Step 1. Merge the marp deck's surviving content into the English collection doc.**
File: `packages/www/src/content/docs/en/rdc-cheat-sheet.md`.
The collection doc is the better and more current of the two; this is an additive merge,
not a rewrite. Verified-valid additions (I ran each through `parseRdcCommand`, all
`ok: true`): `rdc repo logs <repo> -c <container> --lines 50`,
`rdc repo exec <repo> -c <container> -- <cmd>`, `rdc repo tunnel`, `rdc config list`,
`rdc config set machine <alias>`, `rdc machine scan-keys`, `rdc machine health`,
`rdc vscode list`, `rdc vscode cleanup`, `rdc repo resize <repo> --size <size>`.
Explicitly **drop** from the merge:
- `rdc run` / `rdc run -f ...` (parser: `unknown-command`; hidden debug verb per
  `CLAUDE.md`; the collection doc's `docker`-via-`term connect` treatment supersedes it).
- `rdc cluster snapshot <name>` (parser: `excess-positional-args`).
- `rdc datastore snapshot <ds>` (parser: `excess-positional-args`).
- `rdc repo expand <repo>` as written (parser: `missing-mandatory-option --size <size>`);
  include it only with `--size`.
Also fold `rdc repo logs` / `rdc repo exec` into the existing "Debug and Escape Hatch"
section as the *preferred* form, ahead of the `docker`-via-`term` fallbacks
(`en/rdc-cheat-sheet.md:130-137`); `CLAUDE.md` names them as the commands to prefer and
the current text omits them entirely.
Keep the section count at 10 or grow it deliberately; the card grid keys on `## `.

**Step 2. Re-translate the 12 locales and restamp `sourceHash`.**
Files: `packages/www/src/content/docs/{ar,de,es,et,fr,it,ja,ko,pt,ru,tr,zh}/rdc-cheat-sheet.md`.
Step 1 invalidates every `sourceHash`, so `validate:translation-freshness` goes red until
this lands; that is the gate doing its job. `validate-translation-freshness.js:275` prints
the exact hash to stamp. Naturalized, not literal, per `docs/i18n/CONVENTIONS.md`. Use
Sonnet for the translation work per standing policy. **This is the bulk of the wall clock**
and it is the one step that must not be skipped, because skipping it is how the wave
re-creates the bug in a different shape.

**Step 3. Add the `cardGrid` flag to the docs schema.**
File: `packages/www/src/content/config.ts` (the `docsCollection` schema, currently at
lines 21-34). Add `cardGrid: z.boolean().default(false)`. Set `cardGrid: true` in the
frontmatter of all 13 `rdc-cheat-sheet.md` files (fold into steps 1 and 2 to avoid a
second pass over locale files).

**Step 4. New component: the card grid.**
New files:
- `packages/www/src/utils/card-grid.ts`, exporting `splitIntoCards(html: string): string[]`,
  which splits a rendered HTML string on top-level `<h2` boundaries. Pure function, no
  dependencies, unit-testable.
- `packages/www/src/utils/__tests__/card-grid.test.ts` (vitest is already wired:
  `packages/www/package.json` `test:unit`). Cover: no h2, one h2, many h2, an `<h2>` inside
  a `<pre>` fence (must not split).
- `packages/www/src/components/CheatSheetGrid.astro`, which does
  `const html = await Astro.slots.render('default')`, splits it, and emits
  `<section class="cs-card cat-N">` per card with the tint cycling by index. The
  slot-to-string pattern is already proven in this codebase at
  `packages/www/src/layouts/DocsLayout.astro:64`
  (`generateTOCFromHtml(await Astro.slots.render('default'))`), so this is not a new
  technique. Move the screen + print `<style>` block from
  `rdc-cheat-sheet.astro:54-308` into this component verbatim, renaming
  `.marp-grid`/`.marp-output` to `.cs-grid`/`.cs-cards` and dropping the
  `div.marpit` display-contents rule (`rdc-cheat-sheet.astro:83-85`), which exists only to
  neutralise a Marp wrapper that will no longer be emitted.

**Step 5. Rework the stylesheet.**
File: `packages/www/src/styles/marp-cheatsheet.css` -> rename to
`packages/www/src/styles/cheatsheet.css`. Delete the Marp-geometry override block
(`:11-17`), rewrite the `.marp-output` prefix to `.cs-cards`, and keep the tint variables
and `section.cat-*` rules (`:41-46`, `:121-137`) as-is. Import it normally from the
component; the `?raw` + `set:html` injection dance
(`rdc-cheat-sheet.astro:13`, `:45`) existed only to escape Marp's theme scoping
(reason stated in the comment at `rdc-cheat-sheet.astro:10-12`) and goes away with Marp.
Note: `packages/www/package.json` runs `lint:css` / `lint:css-files` (unused-CSS gates), so
expect to run those after the rename.

**Step 6. Delete the marp path and wire `[slug].astro`.**
- Edit `packages/www/src/pages/[lang]/docs/[slug].astro`: import `CheatSheetGrid`, and
  render `doc.data.cardGrid ? <CheatSheetGrid><Content /></CheatSheetGrid> : <Content />`.
  Pass `tocTrackingSelector=".cs-cards section h2"` when `cardGrid` is set, mirroring
  `rdc-cheat-sheet.astro:43`.
- Delete `packages/www/src/pages/[lang]/docs/rdc-cheat-sheet.astro`.
- Delete `packages/www/src/marp/rdc-cheat-sheet.marp.md` and the now-empty `src/marp/`.
- Delete `packages/www/src/utils/marp.ts`.
- Remove `"@marp-team/marp-core": "^4.4.0"` from `packages/www/package.json` and refresh
  the lockfile with `npx -y npm@10 install --package-lock-only --ignore-scripts` (npm 10 is
  the canonical lockfile form per `CLAUDE.md`; do not let system npm 11 write it).

**Step 7. Gate 1.**
New: `scripts/check-docs-render-parity.ts`; new script entry
`"check:ci-docs-render-parity"` in the root `package.json` next to `check:ci-seo`
(`package.json:123`); new control test
`scripts/__tests__/check-docs-render-parity.control.ts`; new step in
`.github/workflows/ci-quality.yml` `quality-www-build`, guarded with the same
`if: ${{ !cancelled() && steps.build-www.outcome == 'success' }}` the neighbouring steps
use. Add the control test to whatever runs `scripts/__tests__/*.control.ts` today (it is
invoked explicitly from `check:i18n` at `package.json:151` for the existing one; follow
that precedent rather than inventing a runner).

**Step 8. Gate 2.**
New: `.ci/scripts/quality/check-page-locale-imports.sh` (or a `scripts/*.ts` sibling if
the surrounding lane is TS; match the neighbours rather than the format I happen to
prefer). Wire into the fast quality lane. Ship its control.

**Step 9. Verify for real, not by reading.**
`npm run build:www`, then re-grep the artifact the same way this plan's evidence was
gathered:
```
grep -o 'Repository-Lebenszyklus' packages/www/dist/de/docs/rdc-cheat-sheet/index.html
grep -o 'Repository Lifecycle'    packages/www/dist/de/docs/rdc-cheat-sheet/index.html
```
First must hit; second must not (outside chrome). Then run `npm run check:i18n`
(covers `validate:docs-cli-usage`, `validate:translation-freshness`,
`validate:content-accuracy`) and the two new gates, and confirm Gate 1's control still
fails on its planted defect after the real tree is green. A gate proven only against a
green tree has not been proven.

---

## 6. Scope honesty

**This is not a week. It is roughly one session, and the long pole is translation, not
code.** Steps 3 to 8 are a few hundred lines of mostly-moved CSS. Step 2 is 12 files of
naturalized translation, and it is unavoidable: any change to the English body invalidates
12 `sourceHash` values, and `validate:translation-freshness` is a blocking gate.

**If the wave needs a narrow thing today**, the narrow thing is **steps 3 to 6 with step 1
reduced to zero**: switch the page to render the existing, already-translated collection
document unchanged, and delete the marp file outright rather than merging anything out of
it first. That is a same-session change, it makes all 13 pages correct in their own
language immediately, and it removes the ungated document.

What the narrow version leaves unfixed: the ~16 commands that exist only in the marp deck
(`repo logs`, `repo exec`, `repo tunnel`, `config list/set`, `machine health/scan-keys`,
`vscode list/cleanup`, `repo resize`) vanish from the cheat sheet entirely. That is a
content regression in coverage, traded against a correctness fix in 12 languages. I would
take that trade only if step 1's merge cannot ride the same session, and I would file the
merge as a tracked open item, not as a comment. Note that two of the marp-only commands
(`rdc run`, `rdc cluster snapshot`) should be dropped regardless, so the true loss is
smaller than the 16-entry diff suggests.

I would **not** narrow further than that. In particular, "fix the marp file's language
later" is not a narrow version of this, it is the bug with a date on it.

---

## 7. What I would NOT do

- **Would not add per-locale marp files.** It doubles the translation surface and adds a
  surface with no gate coverage. This is the option the constraints explicitly warn about,
  and the 31-entry command divergence measured above is the evidence for why.
- **Would not add a marp-vs-collection diff gate.** A gate that policies two copies of one
  document into agreement is a worse answer than having one copy. Keeping both files and
  checking them against each other institutionalises the duplication.
- **Would not keep Marp "just in case slides matter later".** Nothing in the repo consumes
  `marp.ts` except the page being deleted (`grep -rn 'marp' --include=*.astro --include=*.ts`
  over `packages/www/src` returns exactly `src/utils/marp.ts` and
  `src/pages/[lang]/docs/rdc-cheat-sheet.astro`). Sole operator, no external consumers; a
  dependency retained for a hypothetical is a compatibility layer with better PR.
- **Would not "fix" this by pointing the `?raw` import at a locale-keyed path**
  (`../../../marp/rdc-cheat-sheet.${lang}.marp.md?raw`). Vite `?raw` needs a static
  specifier, it would still leave the English page metadata at
  `rdc-cheat-sheet.astro:31-35` untranslated, and it is option (A) wearing a disguise.
- **Would not baseline anything.** `packages/www/scripts/docs-cli-usage-baseline.json` does
  not exist and must not start existing for this. If the merged English doc trips
  `validate:docs-cli-usage`, the command text is wrong and gets fixed; the whole point of
  step 1's parser probes was to know that in advance.
- **Would not touch `dist/`.** The evidence in this plan was read from a build another
  session produced; the implementation regenerates it, and nothing here should be
  hand-edited there.

---

## 8. Side findings surfaced while verifying (fix in the same wave)

1. **`src/marp/` is outside every content gate's scan root.** Anchors:
   `validate-docs-cli-usage.js:162`, `validate-content-accuracy.js:28`,
   `generate-search-index.js:56`. This is why the deck taught retired commands undetected.
   Deleting `src/marp/` closes it; Gate 2 stops it recurring under a new directory name.
2. **The live cheat sheet teaches a hidden debug verb.** `rdc run` occupies a full card
   (`src/marp/rdc-cheat-sheet.marp.md:348-361`) plus `:126` and `:228`, and the gate's own
   parser rejects it as `unknown-command`. `CLAUDE.md` states `rdc run` is hidden from help
   and MCP and is for debugging only.
3. **The cheat-sheet page degrades its own language switcher.**
   `rdc-cheat-sheet.astro:38-44` passes neither `availableLanguages` nor
   `showFallbackNotice`, both of which `[slug].astro:46-53` supplies for every other doc.
   Fixed as a side effect of step 6.
4. **The collection doc's "Debug and Escape Hatch" omits the preferred commands.**
   `packages/www/src/content/docs/en/rdc-cheat-sheet.md:130-137` documents only
   `term connect -c "docker ..."`, while `CLAUDE.md` names `rdc repo logs` and
   `rdc repo exec` as what to prefer. Both parse clean. Folded into step 1.
5. **Search results already promise German and deliver English.** The search index is built
   from `src/content/docs` (`generate-search-index.js:56`), so a German query matches the
   German cheat-sheet body and links to a page that renders none of it. No separate fix
   needed; step 6 resolves it.

---

## 9. Unverified / left for the implementer

- The exact article-body container selector Gate 1 should scope to. I read
  `DocsLayout.astro:1-70` and confirmed `.article-content` is referenced by the page's own
  overrides (`rdc-cheat-sheet.astro:74`), but I did not confirm it is the innermost wrapper
  around `<slot />` in the emitted markup. Confirm against `dist/` before writing the
  extractor; getting this wrong makes the gate pass on sidebar text, which is the one way
  it could be green while wrong.
- Whether `lint:css-files` (`packages/www/package.json`) tracks stylesheet filenames in a
  manifest that step 5's rename must also update. Not checked.
- Whether Astro emits a build warning for the current `rdc-cheat-sheet.astro` /
  `[slug].astro` route collision. The shadowing is proven empirically by the dist contents;
  I did not read build logs.

## Execution commitment, 2026-08-16

**Accepted in full. Scheduled to execute immediately after the 0815-1 wave
pushes**, not deferred indefinitely. Recording it here rather than only in a
worklist deferral, because a deferral evaporates and a committed plan does not.

Why after the push rather than before, stated so a stranger can judge it:

- The plan's **Gate 2 is deliberately RED on today's tree**, which is correct:
  it is not introduced pre-satisfied. Landing it before the render fix would
  block CI on an architectural change.
- The fix deletes a 371-line document and reroutes a customer-facing page
  through `[slug].astro` with a card-grid and print presentation that can be
  verified structurally but NOT visually by this session.
- The wave push was already gated on i18n at the time; adding this would have
  extended that block rather than shortened it.

**What is already done, so the dangerous half is not waiting on any of the
above:** the marp source no longer teaches retired commands (commit
`a56b03aa5`, verified in the BUILT pages: en/de/ja show zero retired commands),
and `check:ci-retired-commands` scans `src/marp/*.md`, mutation-proven firing at
`marp:273` on the pre-fix rows. A reader is no longer being taught a workflow
the engine refuses.

**What remains is the localization gap**: non-English cheat-sheet pages render
English by construction. Real, pre-existing, and not dangerous in the way the
first half was.

Order of execution when it starts: steps 1-2 (content decision), then 3-6 (the
route change), then Gate 1 and Gate 2 together, so neither gate lands before
the tree can satisfy it.
