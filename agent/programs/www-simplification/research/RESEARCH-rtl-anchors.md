# RESEARCH: anchors, fragments, and RTL

**Author:** `sx-rtl` | **Date:** 2026-08-17 | **Status:** research only, zero edits to `packages/www`

Screenshots referenced below live in
`/tmp/claude-1000/-home-muhammed-monorepo-console/e6500e92-55b2-4f40-b8f2-149511f68334/scratchpad/shots/sx-rtl/`.

---

## 1. Verdict

The site runs **two different slug algorithms over the same heading text**: Astro's
built-in `rehype` heading-id pass (github-slugger, Unicode-preserving, deduplicating) writes
the `id`, and a hand-rolled `stringToSlug` (`src/utils/slug.ts:6-13`, ASCII-only via `\w`,
no deduplication) writes the TOC `href`. They disagree on **8,013 of 15,521 in-page links
across 1,107 docs and blog pages (51.6%)**, and **963 of those pages (87.0%) have at least
one dead anchor**. This is not a 5-locale problem split on script: **every locale including
English is broken**, because `\w` also drops `&`, `/`, `+` and every accented Latin letter,
and because `stringToSlug` never dedupes so 3,036 TOC entries point at a fragment they
share with another entry. The single highest-leverage change is to **delete `stringToSlug`
and have the TOC read the ids Astro already wrote into the rendered HTML**, which is a
smaller diff than the bug. Separately, and independently of the anchors, Arabic has six
real RTL defects, the loudest being that the "Copy section" button sits on top of the first
40px of **every** `h2` and `h3` because its reservation is the physical `padding-right`.

---

## 2. Root cause, with `file:line`

### 2.1 The two slug generators

**Generator A, which writes the `id`.** `astro.config.mjs:168-175` configures
`markdown.remarkPlugins` and declares **no `rehypePlugins`**, so Astro's default
`rehypeHeadingIds` pass runs untouched. It uses `github-slugger`
(`/home/muhammed/monorepo/console/node_modules/github-slugger`). Measured behaviour:

```
"3. أضف خادمك"          -> "3-أضف-خادمك"
"Работа с репозиторием"  -> "работа-с-репозиторием"
"什么是集群"              -> "什么是集群"
"Members & Roles"        -> "members--roles"      (& deleted, its spaces both kept)
"--name-only"            -> "--name-only"
"set" (second time)      -> "set-1"               (stateful dedupe)
```

**Generator B, which writes the TOC `href`.** `src/utils/slug.ts:6-13`:

```js
export function stringToSlug(str: string): string {
  return str
    .toLowerCase()
    .trim()
    .replaceAll(/[^\w\s-]/g, '')   // <- the bug
    .replaceAll(/\s+/g, '-')
    .replaceAll(/-+/g, '-');       // <- the second bug
}
```

`\w` in a JavaScript regex without the `u` flag and without `\p{...}` is exactly
`[A-Za-z0-9_]`. So line 10 deletes **every character outside ASCII**: Arabic, Han, Kana,
Hangul, Cyrillic, and also `é ü ç ş ı õ ã`. Line 12 then collapses `--` to `-`, which
diverges from github-slugger even in pure ASCII.

It is called once, at `src/utils/sidebar-behavior.ts:86`, inside `generateTOCFromHtml`:

```js
const id = stringToSlug(title);   // sidebar-behavior.ts:86
```

`generateTOCFromHtml` re-derives an id **from the heading text it just scraped out of the
rendered HTML**, while the correct id is sitting in the very same `<h2 ...>` tag it matched.
Its regex `/<h([2-6])[^>]*>(.*?)<\/h\1>/gi` (`sidebar-behavior.ts:62`) captures the tag's
attributes in `[^>]*` and throws them away.

**Both layouts consume it:**

- `src/layouts/DocsLayout.astro:65` `generateTOCFromHtml(await Astro.slots.render('default'))`
- `src/layouts/ContentLayout.astro:71` (blog)

and emit the links at `DocsLayout.astro:187`, `:192` and `:200` (`href={`#${...id}`}`) and
`ContentLayout.astro` equivalently.

### 2.2 Why one keeps Unicode and the other does not, in one sentence

github-slugger implements the GitHub rule (strip a fixed punctuation set, lowercase with
locale-independent case folding, space to hyphen, **keep everything else**) and carries a
`Map` for dedupe; `stringToSlug` implements an allowlist (`keep only \w and whitespace`)
with no state. An allowlist written as `\w` in ASCII mode is a decision to support English
only, made silently by a regex escape.

### 2.3 The third consumer of the same mistake: scroll-spy

`DocsLayout.astro:642`:

```js
const tocLink = container?.querySelector(`a[href="#${id}"]`);
```

`id` here is the **real** heading id (`entry.target.id`), so in any broken locale it matches
nothing and the `if (!tocLink) return` on the next line silently swallows it. Proven live:

| Page | active TOC link after `scrollTo(0, 2500)` |
|---|---|
| `/en/docs/quick-start` | `"2. Apply a Template"` |
| `/ar/docs/quick-start` | `[]` |

So the TOC never highlights where you are, in every affected locale. Same root cause, third
symptom, and it fails silently by design.

---

## 3. Blast radius, measured

### 3.1 Live crawl of every docs page in every locale

Method: fetch all 1,015 pages from the running dev server, extract `id` from every
`<h2..h6>`, extract `href` from every `a.sidebar-link.toc-link`, and from every
`<a href="#...">` inside `.article-content`; compare after `decodeURIComponent`.
Script: `scratchpad/crawl.mjs`, raw results `scratchpad/crawl.json`.

| locale | pages | pages with a dead TOC anchor | TOC links | dead | duplicate fragments | in-article `#` links | dead |
|---|---|---|---|---|---|---|---|
| ar | 78 | **78** | 1142 | 929 | 566 | 12 | 4 |
| de | 78 | 65 | 1142 | 224 | 28 | 12 | 3 |
| **en** | 79 | **18** | 1152 | **36** | **28** | 12 | 0 |
| es | 78 | 72 | 1142 | 407 | 28 | 12 | 2 |
| et | 78 | 76 | 1144 | 387 | 28 | 12 | 2 |
| fr | 78 | 78 | 1142 | 553 | 28 | 12 | 0 |
| it | 78 | 37 | 1144 | 65 | 28 | 12 | 3 |
| ja | 78 | 78 | 1142 | 920 | 570 | 12 | 2 |
| ko | 78 | 78 | 1144 | 925 | 537 | 12 | 0 |
| pt | 78 | 72 | 1144 | 502 | 28 | 12 | 4 |
| ru | 78 | 78 | 1142 | 907 | 527 | 12 | 0 |
| tr | 78 | 78 | 1142 | 781 | 28 | 12 | 4 |
| zh | 78 | 78 | 1142 | 923 | 612 | 12 | 4 |
| **TOTAL** | **1015** | **886 (87.3%)** | **14864** | **7559 (50.9%)** | **3036** | **156** | **30** |

### 3.2 Blog, same crawl (`scratchpad/crawlblog.mjs`)

| locale | pages | broken pages | TOC links | dead |
|---|---|---|---|---|
| en | 8 | 0 | 57 | 0 |
| every other locale (12) | 7 each | 4 to 7 | 50 each | 4 to 50 |
| **TOTAL** | **92** | **77** | **657** | **454** |

### 3.3 Combined

**1,107 pages, 963 with a dead anchor (87.0%). 15,521 in-page links, 8,013 dead (51.6%).**

### 3.4 The English failures are a distinct family, and this corrects the framing

The lead's measurement counted TOC anchors that were **empty or digits-only**, which is the
signature of non-Latin script loss. That metric reports 1/25 for en/de/fr/tr/et. It
undercounts, because a wrong-but-non-empty anchor is just as dead. The English family, from
`scratchpad/slug-details.json`:

| Cause | github-slugger | stringToSlug | Example (file) |
|---|---|---|---|
| `&`, `/`, `+` leave a doubled hyphen | `members--roles` | `members-roles` | `account-management.md` |
| repeated heading text | `set-1`, `list-2` | `set`, `list` | `cli-application.md` |
| leading CLI flag | `--name-only` | `-name-only` | `repo-diff.md` |
| flag mid-heading | `change-magnitude-with---stat` | `change-magnitude-with-stat` | `repo-diff.md` |

`cli-application.md` alone contributes **28 duplicate fragments in every locale**: `set`,
`list`, `show`, `remove` appear repeatedly, github-slugger numbers them, `stringToSlug` does
not, so the TOC emits the same `#set` several times. Those links are both dead and
ambiguous.

Accented Latin locales fail through the same `\w` deletion as CJK, just less visibly:
`de` "Größe ändern" gives `grösse-ändern` vs `gre-ndern`. That is why de/es/et/fr/it/pt/tr
show 65 to 781 dead links despite scoring 1/25 on the empty-anchor metric.

### 3.5 In-page markdown links written by translators

`[text](#anchor)` inside the markdown body: 156 across the site, **30 dead**, all in
non-English files. Two distinct causes, both worth naming:

- **ASCII-folded by hand.** `de/repositories.md` links `#speicherplatz-zuruckgewinnen-trim`
  and `#grosse-andern` while the headings slug to `...zurückgewinnen...` and `größe-ändern`.
- **English anchor left behind after the heading was translated.** `#safety-model` appears
  in `de/pruning.md` and `ar/pruning.md`; neither page has that id any more.

### 3.6 What is NOT affected

- **Document URLs.** Filenames are English slugs in all 13 locale directories (verified:
  every locale differs from `en` by exactly the one file `en` has extra). No locale ships a
  translated path segment.
- **Legal pages.** `src/pages/[lang]/privacy-policy.astro:46` reads `sections[key].id` from
  the locale catalog, and every catalog carries the **same ASCII id** (`changes`,
  `children-privacy`, `data-retention`, ...) with only `title` translated. 10 ids x 13
  locales, 0 non-ASCII. This is already the correct pattern and it is the template for the
  fix.
- **The "Copy section link" button.** `DocsLayout.astro:413-418` builds the URL from
  `heading.getAttribute('id')`, the real id, so the copied link works. Docs pages therefore
  have one control that produces a correct fragment and a TOC beside it that cannot.
- **Scroll offset.** `scroll-margin-top` is configured and the browser does scroll when the
  fragment is right (see 5.4 for a separate, smaller offset defect).
- **The search index**, for the boring reason that it never emits a fragment at all: see 4.4.

---

## 4. The class sweep: everywhere a slug, id, fragment, filename or sort key comes from translated text

### 4.1 `category` frontmatter is translated in one file, in all 12 locales

`scripts` grep over `src/content/docs/*/*.md*` for `^category:` against the English
vocabulary `{Concepts, Guides, Legal, Reference, Tutorials, Use Cases}`:

| locale | file | value |
|---|---|---|
| ar | `cli-application.md` | `مرجع` |
| de | `cli-application.md` | `Referenz` |
| es / et / fr / it / pt | `cli-application.md` | `Referencia` / `Viide` / `Référence` / `Riferimento` / `Referência` |
| ja / ko / ru / tr / zh | `cli-application.md` | `リファレンス` / `참조` / `Справочник` / `Başvuru` / `参考` |

`DocsTopTabs.astro:29-32` maps a known English category to a translation key and
**falls back to the raw string**, so the value becomes a seventh tab. Measured live:

```
en  tutorials guides concepts reference use-cases legal              (6)
ar  tutorials guides concepts reference use-cases legal مرجع         (7)
ru  tutorials guides concepts reference use-cases legal справочник   (7)
```

In Arabic the label `مرجع` therefore appears **twice**, once as the real Reference tab and
once as the orphan. `cli-application` is pulled out of Reference into a one-item category
in all 12 locales, and `DocsSidebar.astro:43-47` sorts the category list with
`localeCompare` over this now-mixed-script vocabulary. One line of frontmatter x 12 files.

### 4.2 `dir` is decided by a hand-rolled locale check

`src/layouts/BaseLayout.astro:65`:

```js
const dir = currentLang === 'ar' ? 'rtl' : 'ltr';
```

`packages/locales/site-locales.json` carries `siteLocales` and `defaultLocale` and **no
direction metadata**, so there is nowhere correct to read this from today. Adding an
`rtlLocales` field there and deriving `dir` from it is the shape the repo's own
non-negotiable asks for: one source, hard error on an unmodelled locale. Today a new RTL
locale (he, fa, ur) would silently render LTR.

### 4.3 Direction-flipping done with `direction: rtl`, which no-ops on the RTL page

`src/styles/pricing-page.css:2263-2269` and `public/styles/main.css:2314-2320` both use the
zig-zag hack:

```css
.trust-row-reverse   { direction: rtl; }
.trust-row-reverse>* { direction: ltr; }
```

On an Arabic page the row is already `rtl`, so the rule changes nothing and the alternation
disappears. Measured on `/pricing` (child left offsets, 6 rows):

```
en   [113,721] [721,113] [113,721] [721,113] [113,721] [721,113]   alternating
ar   [721,113] [721,113] [721,113] [721,113] [721,113] [721,113]   all identical
```

Screenshot: `ar-pricing-trustrow.png`. Consumers: `PricingTrustSection.astro:62,140,221`
and `HomeDifference.astro:74` (which reaches the site through
`solution-pages/SPHomeBeforeAfter.astro:12`).

### 4.4 Search: the anchor is computed and then discarded

`scripts/generate-search-index.js:202-217` splits each document into H2/H3 sections and
indexes each one, but writes `page: /${langDir}/${urlPrefix}/${slug}` with **no fragment**,
even though `section.heading` is right there. `SearchModal.tsx:152-153` then dedupes
results by `item.page`, collapsing every section hit of a document into one row, and
`:209` navigates with `window.location.href = result.page`. So search knows which section
matched and always lands you at the top of the page. Immune to this bug, and useless for
jumping. Fixing the TOC gives search a correct fragment for free.

### 4.5 Checks that came back clean, so they are not part of the class

- **DOM id collisions:** 69 ids on `/ar/docs/quick-start`, zero duplicates. github-slugger's
  dedupe holds.
- **`aria-labelledby`:** 3 references, all resolve.
- **`aria-controls`:** 30 references, **3 dangling** (`mega-menu-panel`,
  `persona-menu-panel`, `search-modal`). Locale-independent, panels are lazily mounted.
  Cross-domain, `sx-chrome`.
- **Filenames and URL slugs:** English everywhere, see 3.6.

---

## 5. RTL audit

Arabic is the only RTL locale. The menu side the operator noticed is correct: `dir="rtl"`
reaches `<html>`, `getComputedStyle(body).direction === 'rtl'`, the docs sidebar mirrors to
the right and the TOC rail to the left. Everything below is what is wrong underneath that.

Baseline screenshots: `ar-docs-1440.png` beside `en-docs-1440.png`, plus `ar-docs-390.png`
and `ar-codeblock-1440.png`.

### 5.1 The share button covers the start of every heading (worst defect)

`DocsLayout.astro:990-1001`:

```css
.article-content :global(h2[id], h3[id]) { position: relative; padding-right: 4.75rem; }
.article-content :global(.heading-share) { position: absolute; right: 0; ... }
```

Both properties are physical. Measured on `/ar/docs/quick-start`, first `h2` ("مقدمة"):

```
heading border box right = 1115      padding-right = 76px
text run   954 .. 1039               share button 998 .. 1115
overlap = 40px, button paints on top (z-index: 3)
```

In LTR the button hangs 40px past its own reservation into the **end** of the line, where a
short heading has no text, so it is invisible. In RTL the same 40px lands on the **start**
of the line, which always has text. Result: `مقدمة` renders as `دمة`,
`المفاهيم الأساسية` renders as `اهيم الأساسية`, on every `h2` and `h3`, at 1440 and at 390.
This is the first thing an Arabic reader sees.

The fix is `padding-inline-end` plus `inset-inline-end`, and separately the reservation
(76px) must match the control (116px measured here, 141px in `RESEARCH-docs` at the English
label length, so it is locale-dependent and cannot be a constant). `sx-docs` proposes
deleting this control entirely, which resolves it better than fixing it.

### 5.2 Logical property coverage: 144 physical against 37 direction-sensitive logical

Counted over `src/**` and `public/styles/**` (`.css`, `.astro`, `.tsx`, `.ts`):

| physical | n | logical (direction-sensitive) | n |
|---|---|---|---|
| `left` | 31 | `margin-inline-start` | 13 |
| `border-left` | 27 | `inset-inline-end` | 8 |
| `right` | 21 | `inset-inline-start` | 6 |
| `padding-left` | 16 | `border-inline-start` | 5 |
| `text-align: left/right` | 13 | `padding-inline-start` | 3 |
| `margin-right` / `margin-left` | 12 / 11 | `padding-inline` | 2 |
| `padding-right` | 6 | | |
| `border-right` | 3 | | |
| other | 4 | | |
| **total** | **144** | **total** | **37** |

(`inset: 0`, `margin-inline: auto` and `inset-inline` are excluded from the right column as
direction-neutral.) Heaviest files: `src/styles/solution-pages.css` (33),
`src/styles/pricing-page.css` (11), `src/styles/cheatsheet.css` (10),
`src/components/ImageModal.astro` (9), `src/pages/[lang]/changelog.astro` (8),
`src/layouts/DocsLayout.astro` (8), `public/styles/main.css` (8).

Someone started a logical-property migration and stopped at 20%. Against that, the whole
site carries exactly **6 `[dir='rtl']` override rules**: `main.css:1169,1173,1327,1330` and
`contact-modal.css:166,365`.

### 5.3 Code blocks inherit `direction: rtl` and the bidi algorithm rearranges them

Measured on `/ar/docs/quick-start`: `pre` and its `code` both compute `direction: rtl`,
`text-align: start`. Inline `<code>` too. Visible damage in `ar-codeblock-1440.png`:

- `rdc repo create my-app -m my-server --size 2G  # إنشاء مستودع مشفر بحجم 2 جيجابايت`
  renders with the Arabic comment moved to the **left of the command** and the `#` marker
  stranded between them. A reader cannot tell which part is the comment.
- Blocks are right-aligned and overflow-clip on the **left**, so the truncated end of
  `cat ~/.config/rediacc/rediacc.json # ملف JSON الخام: ...` is cut at the left edge, which
  is not where a reader looks for a scroll hint.
- Inside the pricing SVG mock, `rdc repo sync download mail@prod-1 --local ./out` renders
  with `--local` reordered (`ar-pricing-trustrow.png`).

`pre`, `code`, `kbd` and `samp` need `direction: ltr; text-align: left; unicode-bidi: isolate`
under `[dir='rtl']`. There is no such rule today.

### 5.4 Anchor landing position double-counts, in every locale

Three overlapping rules apply to the same jump:

- `public/styles/main.css:484` `html { scroll-padding-top: calc(var(--nav-top-offset) + var(--space-4)) }` = 72px
- `public/styles/main.css:491-493` `:target { scroll-margin-top: calc(--nav-top-offset + --space-8) }` = 88px
- `src/styles/article-content.css:12` the same 88px on `.article-content h2..h6`

Measured on a direct load of a **correct** fragment, identically in `en` and `ar`:

```
element top after settle = 160px      (= 72 + 88)
```

The header is 56px tall. So every anchor lands 104px below the header instead of the
intended ~32px gap. Small, cosmetic, locale-independent, and it is the same "three sources
for one value" shape as the rest.

### 5.5 Chevrons do not mirror

`DocsSidebar.astro:165` and `:181` render a literal `▶` (U+25B6). It has bidi class ON and
is not `Bidi_Mirrored`, so it stays pointing right in Arabic. The only transform on it is
`rotate(-90deg)` for the collapsed state (`sidebar-shared.css:210-212`), which is
direction-agnostic. `main.css:1327-1330` already does the right thing for
`.sidebar-solutions-chevron` under `[dir='rtl']`, so the pattern exists and was not applied
here.

### 5.6 31 left-to-right arrows inside Arabic translated strings

`src/i18n/translations/ar.json` contains 53 directional glyphs: **31 `→` and 28 `←`**. The
translator mirrored some and not others, so `المزيد →` and `احسب →` point away from the
reading direction while `اقرأ الدليل ←` and the four `pages.cookiePolicy.sections.managingCookies.items[*]`
breadcrumbs are correct. For scale: `en` has 45, `fr` 163, `ru` 136, `pt` 88, which are
themselves worth a look by whoever owns copy.

### 5.7 Mobile RTL at 390x844

No horizontal overflow: `scrollWidth 375` against `clientWidth 390`. The docs top-tab strip
scrolls from the right correctly. The heading overlap of 5.1 is present and worse, because
the heading wraps. `ar-docs-390.png`.

### 5.8 Untranslated English inside the Arabic page

Visible in `ar-pricing-trustrow.png`: `EXPIRED`, `backup <em dash> always work`, `REPOS`,
`NEW REPO`, `License`, `create +`, all baked into the inline SVG illustrations of
`PricingTrustSection.astro`, and the label glyphs collide with their tick marks under RTL
text anchoring. `sx-metrics` owns the SVG de-texting; note that one of those strings carries
an em dash.

---

## 6. What docs.claude.com does, measured

`https://docs.claude.com/ja/docs/get-started`, read live with `eval`:

```
document.documentElement.lang      "en-US"
h2/h3 text                         前提条件 / APIを呼び出す / 次のステップ
anchors on page                    #prerequisites, #call-the-api, #next-steps
anchors that do not resolve        0
```

**The headings are translated and the fragments are not.** They derive the slug from the
English source once and carry it into every locale, so a translation can never move a URL
fragment, a shared link survives a language switch, and the anchor stays copy-pasteable in a
terminal. The English page (`/en/docs/get-started`) has the identical three fragments, 0
broken.

This is the same design our own legal pages already use (3.6), from the other direction: a
stable ASCII `id` beside a translated `title`.

| | rediacc docs | docs.claude.com |
|---|---|---|
| slug algorithms over one heading | **2** | 1 |
| fragment stability across locales | none, and 51.6% dead | stable, 0 dead |
| fragment for a Japanese heading | `#-` (or nothing) | `#prerequisites` |
| gate that would catch a dead anchor | **none** | not observable, but 0 defects |

---

## 7. The gate that should exist and does not

**Nothing in the repo validates that an in-page fragment resolves.** Greps over
`.ci/scripts/quality/` and `packages/www/scripts/` for anchor, fragment or link checking
return one unrelated hit (`lint-rule-liveness.mjs`). `check-docs-untranslated-text` was
already proven dead by `sx-i18n-ci`; the three other blind spots it found are all about
*values*. This is a sixth class: **a link the site generates against itself**.

There is also no unit test for either slug function. `src/utils/__tests__/` exists and holds
three tests (`account-url`, `card-grid`, `marketing-host`); `stringToSlug` and
`generateTOCFromHtml` have zero.

### Proposed gate: `gate-test:anchor-integrity`

**What it asserts.** For every built page under `dist/`, every `href="#x"` that is not empty
and not a known skip-link target resolves to an element with `id="x"` on that same page,
after `decodeURIComponent`. Additionally: no two `a.toc-link` on one page share a fragment.

**Where it runs.** After `astro build`, over `dist/**/*.html`. It is a static HTML parse, no
browser, no dev server. Cost is one pass over the already-built output.

**Locale handling, per the standing non-negotiable.** It must iterate
`siteLocales` from `@rediacc/locales` and **hard-error on a locale directory in `dist/`
that is not in that list, and on a listed locale with no directory**. Not a skip. That is
precisely how ar/ja/ru/zh went unprotected before.

**Baseline.** Shrink-only, seeded at the current 8,013 so the gate can land before the fix,
with a hard error when a baselined finding is fixed but not drained. Target 0. The fix in
section 8 takes it to 0 in one change, so the baseline may not be needed at all; decide
after the first run.

**The mutation that proves it fires** (control-first, matching
`check-gate-id-convention.sh`'s own convention of planting the exact historical shape):

1. Plant a heading `## Über & Größe` in a scratch copy of `content/docs/de/quick-start.md`.
   The gate must report `#ber-gr-e` unresolved against `id="über--größe"`. This is the
   `\w` deletion and the `-+` collapse in one line.
2. Plant a second `## Setup` where one already exists. The gate must report the duplicate
   fragment, not just the dead one.
3. Plant a locale directory `dist/xx/` not in `siteLocales`. The gate must exit non-zero
   with "unknown locale", not skip it.
4. Remove `dist/ar/` entirely. The gate must exit non-zero for the missing modelled locale,
   which is the failure mode that let a whole script go unchecked.

If any plant passes, the gate declares itself broken and exits non-zero, the way
`check-gate-id-convention.sh:31-33` does.

**A second, cheaper gate worth having beside it:** a unit test on `stringToSlug` or its
replacement, with the 12 cases in this document's tables as fixtures. It runs in
milliseconds and it is the thing that would have caught this on the day the function was
written.

**A third, one-line gate:** assert that every `category:` frontmatter value in
`src/content/docs/*/` is a member of the English vocabulary. That catches 4.1 and costs a
grep.

---

## 8. Proposed fix, ordered by leverage. NOT implemented.

### F1. Read the id instead of re-deriving it (fixes 8,013 dead links)

**Change.** In `src/utils/sidebar-behavior.ts:59-93`, capture the `id` attribute from the
heading tag the regex already matched, and use it. `stringToSlug` then has no callers and
`src/utils/slug.ts:6-13` can be deleted (keep `getBaseSlug`, which has 12 callers and is
unrelated).

**Files.** `src/utils/sidebar-behavior.ts`, `src/utils/slug.ts`. Nothing else: both layouts
already consume the returned `id` verbatim.

**Risk.** Low, and one thing to check: the heading regex is `[^>]*` greedy over attributes,
so it must tolerate Astro's `data-astro-source-loc` and friends. A heading with no `id`
(h4-h6 outside the default `minLevel`) should be skipped rather than fall back.

**Proof.** Re-run `scratchpad/crawl.mjs` over all 13 locales and require `tocBad = 0` and
`dups = 0` on all 1,107 pages, plus the scroll-spy check in 2.3 returning a non-empty active
link on `/ar/docs/quick-start`.

**What it does not fix.** Fragments become Unicode and locale-specific
(`/ar/docs/quick-start#مقدمة`), so a link shared across a language switch still breaks, and
the fragment is ugly in a chat message. That is F2.

### F2. Stable English fragments in every locale, the docs.claude.com model

**Change.** Give each heading an explicit id that is identical across locales. Two routes:

- **Explicit syntax:** `## مقدمة {#introduction}` via a rehype pass. Touches 1,015 files.
- **Positional mapping:** derive the id from the English file's Nth heading at build time.
  Feasible, measured: **920 of 936 translated files (98.3%) have the same heading count as
  their English counterpart**; only 16 files (2 each in ar/de/es/fr/ja/ru/tr/zh, 0 in
  et/it/ko/pt) diverge and would need a hand pass.

**Recommendation.** F1 first, this session, because it is small and takes the bug to zero.
F2 as the durable follow-up, because it is what makes a docs link survive translation, and
because it also fixes 3.5 (the 30 hand-written anchors become correct by construction) and
makes the search index fragment (4.4) locale-independent.

### F3. RTL fixes, each independent of the anchors

| # | Change | Files |
|---|---|---|
| R1 | `padding-inline-end` + `inset-inline-end` for the heading share control, reservation matched to the rendered width | `DocsLayout.astro:990-1001` (moot if `sx-docs` deletes the control) |
| R2 | `[dir='rtl'] pre, code, kbd, samp { direction: ltr; text-align: left }` | `src/styles/article-content.css` |
| R3 | Replace the `direction: rtl` zig-zag with `flex-direction: row-reverse` | `src/styles/pricing-page.css:2263-2269`, `public/styles/main.css:2314-2320` |
| R4 | Derive `dir` from a new `rtlLocales` field in `@rediacc/locales`, hard-error on an unmodelled locale | `packages/locales/site-locales.json`, `index.js`, `index.d.ts`, `BaseLayout.astro:65` |
| R5 | Mirror `.category-chevron` / `.subcategory-chevron` under `[dir='rtl']`, following the existing `main.css:1327-1330` pattern | `src/styles/sidebar-shared.css:201-212`, `DocsSidebar.astro:300-306` |
| R6 | Flip the 31 stray `→` in `ar.json` to `←` | `src/i18n/translations/ar.json` |
| R7 | Delete two of the three overlapping scroll offsets (5.4) | `public/styles/main.css:484,491-493`, `src/styles/article-content.css:12` |
| R8 | Restore `cli-application.md`'s `category` to `Reference` in 12 files | `src/content/docs/{12 locales}/cli-application.md` |

R2, R3, R4, R7 and R8 are each a handful of lines and each removes a whole locale-specific
failure. R6 is a data edit inside the naturalization surface, so it should ride the i18n
pipeline rather than a hand edit.

### F4. Give search the fragment it already computed

`scripts/generate-search-index.js:215` writes `page` without a fragment while
`section.heading` is in scope; `SearchModal.tsx:152-153` dedupes by `page` and would need to
dedupe by `page + fragment`. Only worth doing after F1 or F2, since before then there is no
correct fragment to write. Cross-domain, `sx-docs` owns the search modal.

---

## 9. Cross-domain consequences

- **`sx-docs`** owns `DocsLayout.astro` and the share control. F1 lands in
  `src/utils/sidebar-behavior.ts` only, so it does not collide. R1 becomes unnecessary if
  their P1 (delete the share machinery) lands. F4 is theirs.
- **`sx-chrome`** owns the header and the 3 dangling `aria-controls` in 4.5.
- **`sx-metrics`** owns the SVG de-texting; 5.8 adds RTL evidence to it, including one
  em dash inside an English SVG string.
- **`sx-i18n-ci`** owns the gate inventory; section 7 is a new row for it.
- **`sx-tokens`** owns the token cascade; 5.4's triple offset is three declarations of one
  value across two stylesheets.
- **`sx-primitives`** owns the physical-to-logical property migration surface in 5.2 outside
  the docs layout.
- **`packages/locales`** is outside `packages/www` entirely. R4 changes it. Flagging, not
  touching.

---

## 10. Open questions for the operator

1. **F1 now or F1 plus F2 together?** F1 is small and fixes every dead link today, but the
   fragments it produces are per-locale, so a link shared between an Arabic reader and an
   English one still breaks. F2 makes them stable, matches docs.claude.com, and costs a pass
   over 1,015 files plus 16 by hand. Recommended default if you do not rule: **F1 this
   session, F2 as the next change**, because F1 unblocks the reported bug and F2 does not
   conflict with it.
2. **Should the fix carry a redirect for the fragments that were never right?** No fragment
   in a broken locale ever resolved, so nothing can be linking to one from outside. My
   assumption is no redirect is needed. Say if you disagree.
3. **R6 (`ar.json` arrows)** is a translated-value edit. Should it go through
   `private/growth/i18n_pipeline` for the whole 13-locale arrow audit, or be a targeted
   Arabic-only hand fix? The pipeline is the safer route and the slower one.
