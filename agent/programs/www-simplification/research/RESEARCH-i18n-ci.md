# www simplification: i18n and its CI protections

**Domain:** `packages/www/src/i18n/`, the 13 locale JSON catalogs, and every gate that
guards them. **Date:** 2026-08-17. **Author:** `sx-i18n-ci`.

Every claim about a gate's behaviour below was produced by **mutating a scratch copy of
the tree and running the gate**, not by reading it. The scratch mirror was built with
`git checkout-index -a --prefix=<scratch>/` (read-only against the working tree), given a
symlinked `node_modules`, its own `git init`, and a pristine snapshot restored after every
single case. Nothing in `packages/www` was modified. Command transcripts are quoted inline.

---

## 0. Verdict

Eighteen gates touch www's translations. **Fifteen I proved can fail. One I proved
cannot fail on the defect it exists to catch.** Two I could not drive to red without a
full astro build and are reported as unproven rather than as passing.

The three findings that matter more than the count:

1. **`check-i18n-cross-locale` does not scan `packages/www` at all.** That is the gate
   written specifically to catch one locale's text sitting in another locale's file. Its
   `LOCALE_ROOTS` lists cli, account-web and account-src. I planted German, then French,
   into `www/it.json`; it reported `✓ No cross-locale contamination across 3 locale
   root(s)` both times. www is covered for German only, by the separate
   `check-locale-de-contamination`. Any other language pair is invisible.
2. **`check-translation-completeness` rounds its untranslated percentage to one decimal
   before comparing it to zero,** so up to **4 English-identical values per locale** pass
   as a warning with exit 0. Measured: 4 → `(0.0%)` exit 0; 9 → `(0.1%) - exceeds 0%
   threshold` exit 1.
3. **The naturalization ledger covers 1,864 of 8,469 English keys (22.0%).** Change any of
   the other 6,605 and `check-i18n-naturalization` stays green, by design
   (`CONVENTIONS.md` §4: never-naturalized keys are not failed). Combined with finding 2,
   an English rewrite outside the ledger can leave all 12 locales stating the old claim
   with every gate green.

And the number the whole program cares about: the 6.7 MB locale payload on every page
exists because **two call sites read one field**. `MegaMenu.tsx:33` and `Sidebar.tsx:145`
do `to(\`pages.solutionPages.${config.contentKey}\`)` and use `content?.hero?.title`.
The eighteen hydrated islands need **240 keys, 15.6 KB per locale, 224 KB for all
thirteen. That is 2.4% of the 9.28 MB on disk.**

---

## 1. The gate table

`.github/workflows/ci.yml:464` calls `.github/workflows/ci-quality.yml`. The i18n gates
live in three of its lanes: `quality-i18n` (`ci-quality.yml:948-1050`), `quality-content`
(`:138` value-types) and `quality-www-build` (`:1126` render parity). Grepping `ci.yml`
for `i18n` returns one comment because the lanes are a reusable workflow, not because the
gates are absent.

Legend: **LIVE** = I made it fail and restored. **DEAD** = I made the defect it exists for
and it stayed green. **UNPROVEN** = baseline green, not driven to red here.

| # | CI step (`quality-i18n` unless noted) | Command | Implementation | Asserts | Verdict |
|---|---|---|---|---|---|
| 1 | i18n | `npm run check:i18n` → `tsx scripts/check-translation-hashes.ts` | `scripts/check-translation-hashes.ts` | English CRC32 vs `.translation-hashes.json`; reports stale / new / **deleted** English keys; a declared tree that vanished is an error, not a skip | **LIVE** |
| 2 | i18n | → `check-translation-completeness.ts` | `scripts/check-translation-completeness.ts:588-760` | missing keys, **orphan** keys (locale has what English lacks), untranslated (value === English) | **LIVE (partial)**. Missing and orphan fire; untranslated has a rounding floor (§2.2); blind to a deleted locale file (§2.4) |
| 3 | i18n | → `check-translation-key-usage.ts` | `scripts/check-translation-key-usage.ts` | every `t()/ta()/to()` key in `.astro`/`.tsx` exists in `en.json` | **LIVE** (+ own control, 7 namespace shapes) |
| 4 | i18n | → `check-i18n-naturalization.ts` | `scripts/check-i18n-naturalization.ts` | ledger staleness per (lang, key); per-language 50% coverage floor | **LIVE**, over 22% of the key set (§2.3) |
| 5 | i18n | → `npm run check:ci-i18n-locale-only` | `scripts/check-locale-only-edits.ts` | a locale value changed while its English did not, for ledger-covered keys only | **LIVE**, and its discrimination is live too |
| 6 | i18n | → `check-component-hardcoded-strings.ts --strict` | same | raw user-facing text in `.astro`/`.tsx` outside `t()` | **LIVE** |
| 7 | i18n | → `check-docs-inline-translations.ts` | same | `{{t:ns.key}}` in docs md resolves in all 13 locales, same count, same line numbers | **UNPROVEN** (baseline green; not mutated) |
| 8 | i18n | → `check-docs-untranslated-text.ts` | same | non-English docs "appear translated" | **DEAD for its stated purpose** (§2.1) |
| 9 | i18n | → `validate:translation-freshness -w @rediacc/www` | `packages/www/scripts/validate-translation-freshness.js` | each locale doc's `sourceHash` vs its English source; prints the exact hash/commit to stamp | **LIVE** |
| 10 | i18n placeholders | `npm run check:ci-i18n-placeholders` | `scripts/check-i18n-placeholders.ts` | `{{x}}` set parity, 3 sets **including www** | **LIVE** both directions (DROPPED and INVENTED) |
| 11 | i18n untranslated | `npm run check:ci-i18n-untranslated` | `scripts/check-i18n-untranslated.ts:37` | value === English, **`packages/cli` only** | live for cli; **does not scan www** despite a docstring saying "every locale" |
| 12 | i18n cross-locale | `npm run check:ci-i18n-cross-locale` | `scripts/check-i18n-cross-locale.ts:60-64` | another language's text in a locale; hard errors on unknown/missing locale dirs; 12-case selftest | selftest LIVE; **does not scan www at all** (§2.1) |
| 13 | i18n cross-locale (chained) | `npm run check:ci-locale-de-contamination` | `scripts/check-locale-de-contamination.ts:62-66` | German text in a non-German locale; **www is root #1** | **LIVE on www**, and the **only** gate that catches a deleted www locale file |
| 14 | Locale sources | `npm run check:ci-locale-sources` | `scripts/check-locale-sources.ts` | stray locale **array literals**; 3-way agreement of `index.js` / `index.d.ts` / `site-locales.json` | **LIVE** for arrays; an object map of 13 locale keys is not seen (§4.3) |
| 15 | Page locale imports | `npm run check:ci-page-locale-imports` | `scripts/check-page-locale-imports.ts` | a route file may not `?raw`-import markdown nor name `content/docs/en/` | **LIVE** (+ 10-case control) |
| 16 | Docs structure parity | `npm run check:ci-docs-structure-parity` | `scripts/check-docs-structure-parity.ts` | heading and table-row counts match English per locale | **LIVE** |
| 17 | Search index | `npm run check:ci-search-index` | `scripts/check-search-index-freshness.ts` | committed `public/search-index*.json` regenerate byte-identical | **LIVE** |
| 18 | *(content lane)* i18n value types | `npm run check:ci-i18n-value-types` | `.ci/scripts/quality/check_i18n_value_types.py` | leaf **type** parity (number/bool/string) for shared keys | **LIVE** on a bool→string swap; see §2.5 for its two blind edges |
| 19 | *(www-build lane)* Docs render parity | `npm run check:ci-docs-render-parity` | `scripts/check-docs-render-parity.ts` | headings in the **built HTML** `.article-content` per locale | **UNPROVEN here** (needs `npm run build:www`); its own control passes 7 cases including "refuse when dist is absent" |
| 20 | *(Code lane)* eslint on locale JSON | `npm run check:lint` | `eslint.config.js:1188-1218` | `json/no-duplicate-keys`, `i18n/seo-title-length` (30-60), `i18n/seo-description-length` (50-160), `i18n/seo-no-duplicate-h1-title`, on **all 13** files | **LIVE** (both length rules proved on `de.json`) |

Plus four CLI-scoped members of the same lane, out of www's blast radius but in the same
job: `check:ci-i18n-command-parity`, `check:ci-i18n-cli-key-usage`,
`check:ci-i18n-cli-help-render`, and `check:cli-docs`.

**Tally: 20 rows, 18 of which touch www. 15 proven live, 1 proven dead, 2 unproven, plus
2 CLI-only rows that are live for their own surface and simply do not cover www.**

### 1.1 Transcripts

`check-i18n-cross-locale`, German then French planted in `www/it.json`:

```
=== I cross-locale / GERMAN planted in www it.json      exit: 0
    | ✓ No cross-locale contamination across 3 locale root(s).
=== M cross-locale / FRENCH planted in www it.json      exit: 0
    | ✓ No cross-locale contamination across 3 locale root(s).
```

The same German value, same file, against the de-contamination gate:

```
=== K de-contamination / GERMAN value copied verbatim into www it.json   exit: 1
    | scripts/data/locale-de-contamination-baseline.json exists to record the
    |   backlog, not to absorb fresh breakage.
```

The untranslated rounding floor:

```
=== H  1 untranslated de value(s)   exit: 0   ! [www/de] 1 untranslated strings (0.0%)
=== H  4 untranslated de value(s)   exit: 0   ! [www/de] 3 untranslated strings (0.0%)
=== H  5 untranslated de value(s)   exit: 0   ! [www/de] 4 untranslated strings (0.0%)
=== H 10 untranslated de value(s)   exit: 1   ✗ [www/de] 9 untranslated strings (0.1%) - exceeds 0% threshold
```

`ko.json` deleted outright:

```
=== D completeness      exit: 0   ✓ All translations are complete   (www drops to 11 locales, silently)
=== G placeholders      exit: 0   ✓ Placeholder parity holds (3 sets, 37 locale files scanned)
=== O value-types       exit: 0   23 locale pair(s)   (was 24)
=== P cross-locale      exit: 0   (does not scan www anyway)
=== Q de-contamination  exit: 1   Error: .../packages/www/src/i18n/translations is missing 1 site locale(s): ko
```

---

## 2. What each blind spot actually costs

### 2.1 www has no general cross-locale protection, and the docs gate is decorative

`scripts/check-i18n-cross-locale.ts:60-64` declares:

```ts
const LOCALE_ROOTS = [
  'packages/cli/src/i18n/locales',
  'private/account/web/src/i18n/locales',
  'private/account/src/i18n/locales',
];
```

`packages/www/src/i18n/translations` is not there. That gate is the one carrying English
function-word detection, per-script evidence for ar/ja/ko/ru/zh, and a hard error on an
unmodelled locale. None of it reaches www. Its neighbour
`check-locale-de-contamination.ts:62-66` does include www (`layout: 'flat'`), so the *one*
contamination class www is protected against is German.

Independently, `check-docs-untranslated-text.ts` **could not be made to fire**. I appended
a wholly English paragraph to `content/docs/de/quick-start.md`:

```
=== AB docs-untranslated-text / a wholly English paragraph in the German doc   exit: 0
    | ! de/on-premise.md: Frontmatter (title+description) has 0 German diacritics in 104 chars
    |   ... and 52 more
    | ✓ All non-English documentation appears to be properly translated
```

It emits 57 warnings about frontmatter and exits 0. This is a second, independent
confirmation of what the brief already recorded; it should not be counted as coverage.

**Consequence for the program:** a naturalization pass that leaves English (or any
non-German language) in a www locale value ships green. This is the failure mode Wave 2
creates most of, because Wave 2 rewrites English and re-runs the pipeline over 12 locales.

### 2.2 The untranslated check has a rounding fail-open of ~5 keys per locale

`check-translation-completeness.ts` computes
`untranslatedPercent = ((untranslated / total) * 100).toFixed(1)` and then fails on
`parseFloat(untranslatedPercent) > MAX_UNTRANSLATED_PERCENT` with `MAX = 0`. `toFixed(1)`
rounds, so anything below 0.05% becomes `"0.0"` and `0.0 > 0` is false. Over www's 8,469
keys that is **4 values per locale, 48 across the twelve**, sitting green as warnings.
The gate prints them (`! [www/de] 4 untranslated strings (0.0%)`), so the information is
not lost, but nothing blocks on it, and a warning in a 78-line CI step is not read.

Fix, when someone owns this file: compare the raw count, not the rounded percentage
(`if (untranslated > 0)`), or keep the percentage for reporting and gate on the integer.

### 2.3 The naturalization ledger covers 22% of English

```
languages in .naturalized-hashes.json: 12
de entries: 1864          en.json leaves: 8469        → 22.0%
top-level prefixes: pages 1689, footer 28, getStarted 24, newsletter 22, hero 18,
  testimonials 12, beforeAfter 11, notASlice 11, whyNow 9, featureShowcase 8,
  integrations 7, solutions 7, logoWall 6, metrics 4, problem 4
```

Editing a covered key stales all twelve at once. Proven:

```
=== S2 naturalization / en value changed for a LEDGER-COVERED key (announcement.text)
    exit: 1   12 naturalized translation(s) are STALE  [tr][de][es][fr][it][pt][ar][ru][zh][ja][ko][et] 1 each
```

Editing an uncovered key (`common.contentNotAvailable`) produced exit 0. `$meta.models`
records `claude-sonnet-5` for all twelve languages, not haiku, which is worth knowing before
quoting a cost from `CONVENTIONS.md` §2, which says haiku is what was used.

**Wave 2 relevance:** `logoWall`, `metrics` and `whyNow`, three of Wave 2's deletion
targets, are all inside the ledger, so their removal *is* tracked. The homepage keys
outside it are not.

### 2.4 A deleted locale file is seen by exactly one gate

Both `check-translation-completeness.ts:610-620` and `check-i18n-placeholders.ts:102-108`
derive www's locale list from `readdirSync` of the translations directory. Delete
`ko.json` and the set under test silently becomes twelve. `check_i18n_value_types.py` has
a `MIN_PAIRS = 8` floor, which a single deletion (24 → 23 pairs) does not reach.

Only `check-locale-de-contamination.ts:220` compares the directory against
`@rediacc/locales` and throws. That one gate is currently the entire structural guarantee
that www ships thirteen catalogs. It is also, separately, the only gate that would notice
if a Wave 0 refactor moved the files. **Do not weaken it, and prefer widening the same
`SITE_LOCALES` assertion into the other two.**

(The TypeScript build would also break, because `utils.ts:1-13` statically imports each
file by name. That is a real backstop today and a backstop the Wave 0 refactor removes,
which is exactly why §2.4 matters more after Wave 0 than before it.)

### 2.5 Two smaller edges, recorded so nobody re-derives them

- `check_i18n_value_types.py` compares only keys present in **both** documents, and its
  flattener turns arrays into `key.0`, `key.1`. So a locale that turns a string into an
  array is not a type finding. It becomes one missing key plus N orphans, which
  `check-translation-completeness` does catch. Confirmed: the string→array mutation
  passed value-types (exit 0) and would fail completeness.
- `check-i18n-untranslated.ts` is `packages/cli`-only (`LOCALES_DIR` at line 37) despite a
  docstring promising "every locale". Its www-equivalent duty is inside
  `check-translation-completeness`, subject to §2.2.

---

## 3. Correctness findings in the locale data itself

These are defects, not simplification opinions. All four are invisible to every gate.

### 3.1 `announcement.enabled` is `false` in English and `true` in all twelve other locales

```
ar True | de True | es True | et True | fr True | it True | ja True | ko True
pt True | ru True | tr True | zh True | en False
```

An English visitor gets no announcement bar; every other locale gets one. No gate compares
non-string values (value-types compares *types*; completeness skips non-strings). This
lands in `sx-chrome`'s files (`AnnouncementBar.astro`): flagged, not fixed.

### 3.2 2,401 locale values contain an em dash, and the em-dash gate cannot see them

```
ar 251 | de 243 | tr 243 | es 230 | zh 231 | ru 374 | fr 236 | ja 219 | pt 136
en  84 | et  74 | it  47 | ko  33          TOTAL 2401
```

`.ci/config/content-quality-patterns.conf:66` lists U+2014 as an **ERROR** pattern, and I
proved the gate fires on it:

```
✗ packages/www/src/content/docs/en/zz-emdash-probe.md:5   Pattern: "<U+2014>"
✗ 1 content quality violation(s) found     EXIT=1
```

But `check-content-quality.sh:29-32` scans only
`packages/www/src/content/{docs,blog}` for `*.md`/`*.mdx`. The 13 locale JSON files and
21 `.astro`/`.tsx` files carrying em dashes are outside its reach. The gate exists, the
rule exists, the UI strings are not covered. A subset is legitimate (the pricing
comparison table uses a bare U+2014 as a "not included" marker); the rest is prose.

### 3.3 "9 languages" is baked into all thirteen catalogs

`pages.pricing.comparison.allPlansInclude` says nine in every locale: `9 Sprachen`,
`9 idiomas`, `9 langues`, `9言語`, `9개 언어`, `9 种语言`, `9 لغات`, `9 языков`, `9 keelt`,
`9 dil`, `9 lingue`. A second key (`en.json:598`) repeats it, and
`pages/[lang]/changelog.astro:67` hardcodes `'Multi-language support (9 languages)'`.
The site ships thirteen. Fixing it is **26 locale values plus one component string**, and
because `allPlansInclude` is a ledger-covered key it will stale twelve translations
(§2.3). See the §5 procedure.

### 3.4 148 search-index entries per locale carry raw `{{t:...}}`

Verified: `search-index-de.json` holds 1,408 entries, of which **148** contain `{{t:`.
Fourteen index files × 148 = 2,072 entries site-wide. Example entry:

```json
{"id":"search-2831","content":"CLI-Anwendung","body":"# {{t:cli.docs.pageTitle}}",
 "excerpt":"# {{t:cli.docs.pageTitle}}","page":"/de/docs/cli-application","language":"de"}
```

Root cause: docs markdown uses `{{t:ns.key}}` placeholders resolved at render time by the
remark plugin, and `packages/www/scripts/generate-search-index.js` reads the raw markdown
without running that resolution. `check-docs-inline-translations.ts` validates the
placeholders resolve; it never asks whether the indexer resolved them. The fix belongs in
the generator, and `sx-docs` owns that file.

### 3.5 Dead keys, counted

A conservative analyzer (exact keys, `to()` prefixes, resolved namespace constants, and
dynamic template stems treated as *uncertain*, never dead) over all `.astro/.tsx/.ts/.md`
under `packages/www/src` plus `packages/www/scripts`:

```
en.json leaves           : 9190
live (exact or prefix)   : 1574
UNCERTAIN (dynamic reach): 7470
DEAD (no reference)      : 146
```

**146 English leaves are unreachable by any static or dynamic path, so 146 × 13 = 1,898
values.** Verified samples: `common.contentNotAvailable` (zero references outside the
catalogs), `getStarted.form.fields.*` (17), `pages.contact.form.*` (14),
`pages.notFound.suggestions.*` (5), `hero.install.alt.*` (4), the four `problem.*`
headings, six `featureShowcase.categoryDescriptions.*`.

`sx-pricing`'s two claims both check out exactly:

- **`pages.pricing.plans.*.features`**: 8+10+10+12 = **40 English strings, 520 values**.
  `CfPricingCard.astro:71` renders `metrics.map(...)`, not `plan.features`; the only
  `.features` reference in the whole tree is `SPComparisonTable.astro:64`, a different
  data source. Dead.
- **12 dead `ui.*` keys**, reproduced exactly: `limitedOffer`, `whatsIncluded`,
  `contactSales`, `keyBenefits`, `monthOrYear`, `foreverFree`, `edgeLimitsNote`,
  `cta.business.valueNote` (`"Includes $9,999 setup credit"`), `cta.business.launchBadge`,
  `guarantees.{freeTrial,cancelAnytime,noContracts}`.

They fall inside my UNCERTAIN bucket rather than DEAD because `pricing.astro:101` builds
keys dynamically; the 146 are the ones no dynamic path can reach either.

**There is no gate for this class.** `check-translation-key-usage` runs source → en.json
only. The eslint rule that would run the other direction, `i18n/no-unused-keys`, is
configured for `packages/cli` and the account portal and is set to `'off'` there
(`eslint.config.js:152-154`); it is not configured for www at all. Dead keys accumulate
with nothing to say so.

---

## 4. Wave 0, the locale chunking refactor

### 4.1 The measurement, re-taken independently

`packages/www/dist/assets/react.zEl4485N.js`, straight off disk:

```
6,708,716 bytes    Cyrillic 212,598   Arabic 166,726   Hangul 95,128   CJK 94,218   Kana 68,800
```

(The synthesis quotes `react.DrK1BhOX.js` at 6,673,504, a different build of the same
thing. The next-largest asset is `client.1YwG0wtV.js` at 184,037 B, so this one chunk is
the entire problem.)

The chain is `utils.ts:1-13` (13 static `import … from './translations/*.json'`) →
`utils.ts:16-30` builds one `translations` object → `react.ts:3` `createTranslator` →
`useTranslation` in **18 island components**. `BaseLayout.astro` hydrates six of them on
every route (`client:load` ×3, `client:idle` ×2, `client:visible` ×1), so the chunk is
unconditional.

### 4.2 The two call sites that make it look necessary

```ts
// MegaMenu.tsx:33-38  and  Sidebar.tsx:145-150, byte-identical
const content = to(`pages.solutionPages.${config.contentKey}`) as
  | { hero?: { title?: string } }
  | undefined;
return { href: `/${currentLang}/solutions/${slug}`, label: content?.hero?.title ?? slug };
```

Twenty-five full solution-page catalogs are handed to the client so two components can
read `hero.title`. Per-island reach, measured:

| Island | leaves reachable | widest prefix |
|---|---:|---|
| `Sidebar.tsx` | 6,660 | `pages.solutionPages` |
| `MegaMenu.tsx` | 6,646 | `pages.solutionPages` |
| `PartnerApplicationForm.tsx` | 40 | `pages.partners.form.*` |
| `PersonaMegaMenu.tsx` | 35 | `navigation.*` |
| `Footer.tsx` | 28 | `footer.*` |
| `InstallMethods.tsx` | 23 | `pages.install.methods` |
| every other island | ≤ 20 | n/a |

Narrow those two to `pages.solutionPages.<id>.hero.title` and the client's true need is:

```
en.json   full 653,791 B   client-slice  15,591 B   240 keys
ru.json   full 885,779 B   client-slice  21,462 B   240 keys
zh.json   full 634,803 B   client-slice  15,338 B   240 keys
ALL 13    full 9,284,710 B     narrowed 224,507 B     ratio 2.418%
```

**240 keys. 224 KB for all thirteen.** Even the laziest shape, shipping all thirteen
narrowed slices eagerly in one chunk, is a 96.6% cut and needs no async anywhere.

### 4.3 What the gates say about the shape of the change

Proven, not inferred:

- **`check-locale-sources` flags an array literal, not an object map.**
  ```
  V  export const LOCALES = ['en','de','es','fr','ja','ar','ru'];        exit 1  ✗ 1 hardcoded locale list(s)
  V2 { en: () => import('./translations/en.json'), … 13 keys }           exit 0
  V3 import.meta.glob('./translations/*.json')                           exit 0
  ```
  So a hand-rolled 13-key loader map is **not** caught. That is a hole, not a licence:
  derive the map from `SITE_LOCALES` or use `import.meta.glob`, and consider adding the
  object-key shape to that gate's detector while you are in the file.
- **`check-page-locale-imports` is live and is not in the way.** It scans only
  `src/pages/**` and `src/layouts/**`, and only rejects `?raw` markdown and
  `content/docs/en/` paths. `src/i18n/**` is out of its scope entirely.
- **`check-translation-key-usage` regexes `\b(t|ta|to)\(`** (`:115`) and resolves
  namespace constants from `const X = 'dotted.string'` (`:88`). **Keep the three function
  names and keep namespace constants as plain quoted strings**, or this gate silently
  stops seeing call sites, which is exactly how
  `pages.partners.form.fields.howHeardPlaceholder` shipped missing from every locale.
- **`types.ts:2` does `import type enTranslations from './translations/en.json'`.** Type-
  only, zero runtime cost, and `Translations`/`PathValue`/`to()`'s return typing all hang
  off it. Preserve it verbatim.
- **`types.ts:26-40` `LANGUAGES` carries a compile-time permutation proof** against
  `SiteLocale`. Do not touch it; it is the reason a dropped locale is a build error.
- **`check-locale-de-contamination` reads `packages/www/src/i18n/translations` by path**
  and throws if a site locale is absent. If Wave 0 relocates or renames the catalogs, that
  path must move with them, or the one structural guarantee in §2.4 dies quietly.

### 4.4 Recommended shape, in order

**Step 0, narrow the two `to()` calls.** Replace both with
`t(\`pages.solutionPages.${config.contentKey}.hero.title\`)`. No gate objects (key-usage
resolves it via the `config.contentKey` dynamic path the same as today). This changes zero
bytes on its own; it is what makes step 2 small.

**Step 1, generate per-locale client catalogs.** A build-time script emits
`src/i18n/client/<locale>.json` for all 13, from a declared key allowlist (~240 keys),
iterating `SITE_LOCALES` from `@rediacc/locales` and **hard-erroring on a locale it cannot
produce**. Commit them, and add a freshness gate in the shape of
`check-search-index-freshness.ts`: regenerate into a temp dir, diff, fail on drift. Do not
gitignore them: a generated artifact nobody can diff is how the search index went stale.

**The path `src/i18n/client/` is load-bearing, not cosmetic.** Three gates derive www's
locale set by listing `src/i18n/translations` and filtering `*.json`
(`check-translation-completeness.ts:610`, `check-i18n-placeholders.ts:102`,
`check_i18n_value_types.py:83`). A thirteen-file `client/` payload placed *inside* that
directory would either be scanned as if it were a locale catalog or, worse, would pass
because the filters happen to skip a subdirectory today. Keep the generated catalogs in a
sibling directory and leave `translations/` holding exactly thirteen files and two
dot-prefixed sidecars.

**Step 2, `react.ts` reads the client catalogs while `utils.ts` keeps the full ones.**
`createTranslator` stays synchronous and stays the server-side API for all 55 `.astro`
consumers. `useTranslation` gets a client-only translator over the small catalogs. Use
`import.meta.glob('./client/*.json', { eager: true })`: 224 KB in one chunk, no async, no
API change. Going lazy (drop `eager`, resolve per `lang`) is a later, separate step worth
~207 KB more; it is not worth coupling to this one.

**Step 3, prove it.** Rebuild and re-measure the largest asset by script count, not by
eyeball:

```bash
cd packages/www && npm run build
find dist -name '*.js' -path '*assets*' -printf '%s %p\n' | sort -rn | head -3
python3 - <<'EOF'
import re,glob
f=max(glob.glob('dist/assets/*.js'), key=lambda p: __import__('os').path.getsize(p))
s=open(f,encoding='utf-8',errors='ignore').read()
print(f, len(s), {n: len(re.findall(r, s)) for n, r in
  [('Cyrillic',r'[Ѐ-ӿ]'),('Arabic',r'[؀-ۿ]'),
   ('Hangul',r'[가-힯]'),('CJK',r'[一-鿿]')]})
EOF
```

Target: the largest asset under 500,000 B, and **Hangul + Arabic + CJK counts at zero in
any chunk a `/en` page loads**. A byte number alone can be met by minification; the script
counts are what prove the locales left.

**Step 4, run these in this order** (all are fast except the last):

```bash
npm run check:ci-locale-sources
npm run check:ci-page-locale-imports
npx tsx scripts/check-translation-key-usage.ts
npx tsx scripts/__tests__/check-translation-key-usage.control.ts
npm run check:ci-locale-de-contamination      # the deleted/moved-file guard
npm run check:types
npm run check:lint
npm run build:www && npm run check:ci-docs-render-parity
```

Nothing in Wave 0 touches a translation *value*, so hashes, completeness, naturalization
and locale-only-edits are all no-ops for it. The synthesis's "zero i18n-gate exposure" is
right in substance; the exposure is to `check-locale-sources` (§4.3) and to the type
system, not to the translation gates.

---

## 5. Wave 2, deleting keys in all thirteen locales

### 5.1 There is no deletion tooling. `i18n:sync` only adds.

`npm run i18n:sync` (`scripts/sync-translations.ts`) fills missing keys; the pipeline at
`private/growth/i18n_pipeline` translates. **Deletion is a manual, thirteen-file edit**,
and the gates are what make it safe.

### 5.2 The rehearsal, including the mistake it caught

I deleted `pages.pricing.plans.*.features` from all 13 files by exact line excision (never
a `json.dumps` round-trip, because `en.json` reformats and prettier does not restore it) and ran
nine gates at three points.

```
---------- AFTER DELETION, BEFORE generate-hashes ----------
  FAIL  hashes               Translation hash check FAILED   (Keys removed from English)
  FAIL  completeness         Errors:
  pass  placeholders / naturalization / key-usage / de-contamination / value-types
  pass  locale-only-edits / cross-locale

generate-hashes exit 0
files touched by generate-hashes:
     M packages/cli/src/i18n/locales/.translation-hashes.json      <-- a tree I did not touch
     M packages/www/src/i18n/translations/.translation-hashes.json

---------- AFTER generate-hashes ----------
  pass  hashes
  FAIL  completeness         Errors:
```

The residual `completeness` failure was **my bug, and the gate named it precisely.** My
line matcher also removed `pages.disasterRecovery.plans.*.features` from English and from
*some* locales:

```
✗ [www/ar] 10 orphan keys not present in English (pages.disasterRecovery.plans.professional.features.0, …)
✗ [www/es] 21 orphan keys not present in English (pages.disasterRecovery.plans.business.features.0, …)
✗ [www/de]  9 orphan keys …   ✗ [www/et] 9 …   ✗ [www/fr] 20 …   ✗ [www/ja] 21 …
✗ [www/ko] 10 …   ✗ [www/pt] 9 …   ✗ [www/ru] 20 …   ✗ [www/tr] 21 …   ✗ [www/zh] 9 …
```

**`check-translation-completeness`'s orphan check is the safety net for an uneven
deletion, and it is live.** That is the single most useful thing to know before doing this
by hand across thirteen files.

### 5.3 The procedure

1. **Delete the consuming component first**, so `check-translation-key-usage` and
   `check-component-hardcoded-strings` are consistent at every intermediate state.
2. **Delete the keys from `en.json` by exact string replacement.** Never
   `json.load`/`json.dumps` on `en.json`. It reformats 2,018 lines and prettier does not
   restore it. Repair forward from `git show HEAD:packages/www/src/i18n/translations/en.json`
   if damaged.
3. **Delete the same keys from the other twelve.** Two mechanical traps, both hit during
   the rehearsal:
   - **Trailing comma.** When the deleted member is the last one in its object, the line
     above keeps a now-illegal comma. Every file must still `json.loads` after the edit;
     assert it.
   - **Key order differs from English.** `en.json` is authored-order; the twelve are
     alphabetically sorted (`de.json` holds `enabled, link, text` where `en.json` holds
     `enabled, text, link`). Locate by key name, never by position. Nothing gates this
     (`i18n/sorted-keys` is `'off'` for www, `eslint.config.js:132`), so the convention
     survives only by hand.
   - **Arrays: append, never insert.** Deleting a middle element of a FAQ-style array
     shifts every later index and silently mismatches all twelve locales. Delete the whole
     array or the trailing elements.
4. **`npm run i18n:generate-hashes`.** It clears the "Keys removed from English" failure.
   **It also rewrites `$meta.sourceCommit` in every other manifest.** Proven on an
   otherwise clean tree:
   ```
   M packages/cli/src/i18n/locales/.translation-hashes.json
   -    "sourceCommit": "d00c35b0…"
   +    "sourceCommit": "93a36eae…"
   ```
   It writes into `private/account` too (`account-web: 2326 keys hashed`,
   `account-emails: 255 keys hashed`); those two manifests carry no `sourceCommit`, so the
   write was byte-identical and the submodule stayed clean. **Restore any manifest of a
   tree you did not touch to its prior bytes**, by editing the field back, not by
   `git checkout`.
5. **The ledger needs nothing.** `check-i18n-naturalization.ts:88-90` counts entries whose
   English key vanished as `orphan` and explicitly does not fail on them
   (`harmless; cleaned on next run`). Leave `.naturalized-hashes.json` alone.
6. **Run the deletion battery:**
   ```bash
   npx tsx scripts/check-translation-hashes.ts
   npx tsx scripts/check-translation-completeness.ts        # the orphan/missing net
   npx tsx scripts/check-i18n-placeholders.ts
   npx tsx scripts/check-i18n-naturalization.ts
   npx tsx scripts/check-translation-key-usage.ts
   npx tsx scripts/check-locale-de-contamination.ts
   .ci/scripts/quality/check_i18n_value_types.py
   npx tsx scripts/check-locale-only-edits.ts               # needs origin/main
   npx eslint packages/www/src/i18n/translations/           # the SEO length rules
   ```
7. **Regenerate the search index only if `content/{docs,blog}` changed.** The index is
   built from markdown, not from the JSON catalogs, so a pure key deletion does not stale
   it: `cd packages/www && node scripts/generate-search-index.js`.

### 5.4 Changing an English *value* (the expensive direction)

1. Edit `en.json` by exact string replacement.
2. `npm run i18n:generate-hashes` (and restore foreign manifests, step 4 above).
3. `npm run i18n:naturalize-status` lists the stale keys per language.
4. `cd private/growth/i18n_pipeline && ./run.sh --lang <lang> --surface <surface>` per
   language. `CONVENTIONS.md` §2 says `--model haiku`; the ledger's `$meta.models` records
   `claude-sonnet-5` for all twelve, so the last full run was not haiku. Start from haiku
   and only bump a language whose output reads awkward.
5. Re-run the battery.

**Cost model, measured.** One ledger-covered key edited → **12 stale entries, one per
language** → 12 pipeline calls for that key. One key that is *not* in the ledger → zero
gate pressure and zero automatic re-translation, which is the dangerous case, not the
cheap one. The nav-relabel figure in the synthesis (21 keys × 13 = 273 strings) is the
right order for a ledger-covered rename; add the SEO length constraint below to it.

### 5.5 Constraints Wave 2 will hit that are not about translation

- **`i18n/seo-title-length` (30-60) and `i18n/seo-description-length` (50-160) are ERRORS
  on all thirteen files**, non-English included. Proven:
  ```
  2697:18  error  Title "Zu kurz" for key "pages.pricing.meta.title" is 7 chars (min 30)   i18n/seo-title-length
  1033:24  error  Description for key "pages.home.meta.description" is 8 chars (min 50)    i18n/seo-description-length
  ```
  Shortening an English meta title, a very plausible simplification move, reds twelve
  more files unless every locale is shortened within the same band. Exemptions exist
  (`notFound`, `checkout.success`) and are the only escape.
- **`check-component-hardcoded-strings --strict` is live**: any replacement copy written
  directly into an `.astro`/`.tsx` fails immediately (`ERROR Line 3 (text node)`). New
  strings must go through `t()` and therefore through all thirteen catalogs.
- **`check-docs-structure-parity` counts headings and table rows per locale.** Cutting a
  section from an English doc without cutting it from twelve translations fails with
  `ja: 40 headings vs English 41`.
- **`validate-translation-freshness` names the exact stamp to apply.** Its output carries
  `sourceHash: "…"` and `sourceCommit: "…"` per stale file; paste those into the locale
  doc's frontmatter after updating it.

---

## 6. Cross-domain consequences

Named, not fixed, per the brief.

| Finding | Owner |
|---|---|
| `announcement.enabled` false in en, true in twelve (§3.1) | `sx-chrome` (`AnnouncementBar.astro`) |
| `generate-search-index.js` does not resolve `{{t:…}}`, 148 entries/locale (§3.4) | `sx-docs` |
| "9 languages" in `changelog.astro:67` (§3.3) | unowned page; the 26 JSON values are mine |
| 21 `.astro`/`.tsx` files carrying em dashes (§3.2) | whoever owns each component |
| `MegaMenu.tsx` / `Sidebar.tsx` `to()` narrowing (§4.2) | Wave 0 owner; both files are also in `sx-chrome`'s nav work. **Coordinate: these are the same two files** |

**Gates I would change but do not own**, all in files under `scripts/` and `.ci/`, which
I do own at implementation time, except the workflow:

1. Add `packages/www/src/i18n/translations` (flat layout) to
   `check-i18n-cross-locale.ts`'s `LOCALE_ROOTS`. This is the single highest-value gate
   change available and it closes §2.1.
2. Gate on the integer in `check-translation-completeness.ts`, not the rounded percentage
   (§2.2).
3. Derive www's locale list from `SITE_LOCALES` in `check-translation-completeness.ts` and
   `check-i18n-placeholders.ts` instead of `readdirSync` (§2.4).
4. Extend `check-content-quality.sh`'s `CONTENT_DIRS` to the locale JSON, or add a
   JSON-aware em-dash rule to the eslint i18n plugin (§3.2). 2,401 findings means this
   needs a shrink-only baseline, not a flag day.
5. Add the object-map shape to `check-locale-sources.ts`'s detector (§4.3).
6. Turn on a www-scoped unused-key check, or write the reverse of
   `check-translation-key-usage` (§3.5).

**Nothing in `.github/workflows/ci.yml` needs to change for any of the above.** Every gate
named here already has a step in `ci-quality.yml`, and items 1-6 are edits to scripts the
existing steps already invoke. The one workflow-shaped question, for the operator rather
than for me: `quality-i18n` is `ubuntu-latest`, `timeout-minutes: 15`, and pays a ~100 s
R2 audio restore before any i18n gate runs. Adding www to the cross-locale scan grows that
job; if it approaches the cap, the fix is a lane split, not a shorter timeout.

---

## 7. Open questions for the operator

1. **The 2,401 em dashes.** The rule is "zero, any language, any file", and the gate that
   enforces it does not reach these strings. Do we (a) drain them as a dedicated pass with
   a shrink-only baseline, (b) fix them opportunistically inside Wave 2's rewrites, or
   (c) leave the locale JSON out of scope deliberately and say so in the config? I would
   pick (b) plus the gate extension, so the number can only go down.
2. **"9 languages".** It should say thirteen, but the string is also a marketing claim
   about a feature list. Confirm thirteen is the number to publish before I edit 26 values
   and stale twelve translations.
3. **`announcement.enabled`.** Is the announcement bar meant to be live? Right now the
   answer is "in twelve languages, yes; in English, no", which cannot be intentional.
4. **The 146 dead keys plus 40 dead `plans.*.features` plus 12 dead `ui.*`.** Delete them
   in Wave 2, or leave them until the components that would have used them are settled?
   Deleting is ~1,900 values across thirteen files and is fully covered by §5.3.
