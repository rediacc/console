# Consolidating locale lists onto one source

Plan produced 2026-07-29 after the operator noticed `VIDEO_LANGS` had 11 entries instead
of 13. Written by a planning agent that read the real files; its inventory corrected an
earlier hand-made one upward, and its load-bearing claims were then spot-checked against
the artifacts (results inline below).

## The short answer to "why are two missing"

The array the operator saw is `VIDEO_LANGS` at `packages/www/src/utils/solution-video.ts:33`.
Its gap is exactly `{ar, et}` — **`tr` is present**. That gap is not drift. Verified:

    solutions locales in video-manifest.json: de,en,es,fr,it,ja,ko,pt,ru,tr,zh   (11)
    VIDEO_LANGS:                              en,de,es,fr,it,pt,ru,ja,ko,tr,zh   (11)
    tutorials locales in the same manifest:   ar,de,en,es,et,fr,it,ja,ko,pt,ru,tr,zh (13)

`VIDEO_LANGS` matches the **published** manifest exactly. Arabic and Estonian solution
videos exist locally but have not been published to R2, and publishing is frozen by
operator instruction. Widening the list before the publish turns `check:ci-solution-videos`
red across 21 slugs with no fix available except publishing.

**But real inconsistency does exist**, just not here: 31 declarations of the locale set in
the console tree, in five different orderings, plus more in the submodules.

## 0. Measured inventory

31 declarations in console, 8 in the gitignored Python repos, 4 in `private/account`.

**15 exact-13 declarations** in the dominant order `en,de,es,fr,ja,ar,ru,tr,zh,et,ko,pt,it`:
`packages/cli/src/i18n/config.ts:21`, `packages/cli/src/services/core/context-language.ts:6`,
`packages/shared/src/i18n/types.ts:24`, `packages/www/scripts/build-account-onboarding.ts:26`,
`generate-cli-docs.js:24`, `lib/landing-terminal-catalog.js:10`, `validate-cli-docs.js:28`,
`validate-content-accuracy.js:30`, `validate-content.js:23`, `validate-docs-cli-usage.js:162`,
`validate-tutorial-transcripts.js:11`, `scripts/check-directive-quotes.ts:68`,
`scripts/check-docs-inline-translations.ts:34`, `workers/www/src/index.ts:132`,
`workers/www/src/smart-redirect.ts:38`.

Other orderings: `packages/www/src/i18n/types.ts:18` (display order),
`scripts/check-account-email-templates.ts:11`, and in the submodule
`private/account/tests/integration/lead-magnet-template.test.ts:12` (a fifth, alphabetical).

**4 non-English lists** (the 13 minus `en`, derivable): `scaffold-tutorial-transcript-locales.js:11`,
`translate-tutorial-transcripts.ts:29`, `validate-translation-freshness.js:13`,
`scripts/check-docs-untranslated-text.ts:30`.

**Deliberate subsets that must NOT be blindly widened**, because they gate on published
media in R2: `VIDEO_LANGS` (11, gap `{ar,et}`), and two `AUDIO_LANGUAGES`
(`check-tutorial-caption-sync.ts:56`, `validate-tutorial-audio.js:53`, both 10, gap
`{ar,et,tr}`). Note the gaps are **different** — anything treating them as one list is wrong.

### Why `eslint.config.js:43` has only 8

Not stale drift. `eslint.config.js:87-90` says block 1 deliberately globs every language
"not just the curated `I18N_LANGUAGES` set", and `private/growth/i18n_pipeline/config.py:109`
declares the identical 8-tuple as "languages the eslint non-English rules apply to" — one
fact in two repos. What was never established is *why* those five are exempt. Measured by
running the two rules against `et,it,ko,pt`:

| locale dir | et | it | ko | pt | total |
|---|---|---|---|---|---|
| `packages/cli/src/i18n/locales` | 2 | 3 | 1 | 2 | **8** |
| `private/account/web/src/i18n/locales` | 8 | 31 | 6 | 18 | **63** |
| `private/account/src/i18n/locales` | 0 | 0 | 0 | 0 | **0** |

71 errors, all `i18n/no-untranslated-values`, all genuine. The 8-set is **71 unfixed
translations wearing a curated-list costume**.

## 1. The single source: `packages/locales/`, a buildless workspace package

Four files, no build script, no generator, no `dist`:
`package.json` (main `./index.js`, types `./index.d.ts`), `index.js` (plain ESM),
`index.d.ts` (hand-written literal tuple), `site-locales.json` (for Python).

Exports `SITE_LOCALES` (13, canonical order), `DEFAULT_LOCALE`, `NON_ENGLISH_LOCALES`
(**derived**), `isSiteLocale()`, `assertSiteLocale()` (throws), `subset(name, codes)`
(throws on any code outside `SITE_LOCALES`).

Rejected alternatives, each for a concrete reason:

- **`packages/shared`** — its exports resolve through `./dist/*`, so consumers need a build
  first. `eslint.config.js` runs before any build and eleven consumers are `node`-run `.js`.
- **A repo-root file** — `packages/shared/tsconfig.json:5` and `packages/cli/tsconfig.json:11`
  set `rootDir: "./src"`, so a relative import out of `src` either trips TS6059 or emits a
  path that breaks at runtime. Both need a **bare specifier**.
- **JSON as the TS source** — `resolveJsonModule` infers `string[]`, destroying
  `SupportedLanguage` and `Language`. 109 files under `packages/www/src` import that type,
  and `Record<Language, string>` at `language-utils.ts:43` is the exhaustiveness check worth keeping.
- **A generated artifact** — nothing to generate *from*; it would be more machinery for the
  same guarantee the gate already provides.

Consumers: bare specifier everywhere (Node's upward `node_modules` walk reaches the root
workspace link, which is the whole reason to use a package rather than a path), except
`workers/www/src/*.ts` which uses a relative import because `workers/www` is not a root
workspace and already relative-imports across the tree.

**Cost, stated up front:** step 2 writes `package-lock.json` (one additive workspace node)
via `npx -y npm@10 install --package-lock-only --ignore-scripts`. It is the only
shared-state write in the plan. `knip.jsonc` also needs a workspaces entry or `lint:unused` fails.

## 2. Subsets stay where they are, but become constructed and checked

"Which locales have published media in R2" is a fact about a bucket, not about the site's
locale set; hoisting it into the single source would make that source lie. Instead each
subset is built with `subset('solution-video', [...])`, which throws at module load on any
unknown code — killing the typo class permanently.

The freeze is **registered**, not remembered: an entry in `.locale-set-exempt`,
BLOCKER-gated like every other suppression, whose enumerated gap must equal the runtime
array's complement.

The liveness oracle is `video-manifest.json`, offline by construction.
`check-solution-videos.ts:120-128` currently asserts only `VIDEO_LANGS ⊆ manifest`; add the
**reverse**: if the manifest gains a locale `VIDEO_LANGS` lacks, fail with "the publish
landed; widen VIDEO_LANGS". That makes the ar/et fix land at exactly the right moment and
never earlier. The fix itself is one line: `export const VIDEO_LANGS = SITE_LOCALES;`

## 3. Verdicts

| list | verdict |
|---|---|
| 15 exact-13 + `check-account-email-templates.ts:11` | **Consolidate** — no order dependency found |
| `packages/www/src/i18n/types.ts:18` | **Keep, renamed** `LOCALE_DISPLAY_ORDER`; a real presentation fact driving `LanguageMenu`. Gate asserts it is a *permutation* of `SITE_LOCALES`. Do not reorder. |
| 4 non-English lists | **Consolidate** to `NON_ENGLISH_LOCALES` |
| NIS2 7-set (`check-directive-quotes.ts:62` + `fetch-directive-snapshot.ts:38`) | **Keep as a set, dedupe to one module** — a permanent fact about EU Directive 2022/2555 |
| **Team videos, all 4 lists + the Python one** | **DELETE as dead** — verified: `TEAM_MEMBERS = {}`, **0** `teamVideo:` call sites, transcript dir absent, and the validator **exits 0 on the absent directory** while chained into `check:i18n`. A textbook vacuous gate. |
| `eslint.config.js:43` ↔ `i18n_pipeline/config.py:109` | **Widen to the 12, fix the 71, delete both** |

## 4. Python side

**In scope** (site-locale copies) — read `packages/locales/site-locales.json` through a
~15-line loader that **raises** if the file or a code is missing, never defaults:
`tutorial_tts/cli.py:17`, `video_pipeline/config.py:251-252`, `www_pipeline/config.py:96`,
`i18n_pipeline/config.py:107`, `illustration_pipeline/config.py:77`,
`apollo-companies/gemma_outreach/language.py:26`.

**Out of scope, keep hand-written** — these are facts about *third-party models*, not about
Rediacc, and folding them in is exactly the category error that produced the
`map.get(code, "English")` bug: `engine_qwen.py:29` `LANGUAGE_LABELS` (no `et`; already
raises), `asr.py:321` `language_map`, `tts_bridge.py:39` `ASR_CAPTION_LANGS`.
`asr.py:332-334` even documents the reverse mistake having happened once.

Console CI cannot gate gitignored repos. Say so in the package README rather than pretending.

## 5. Sequence

The gate lands **after** the conversions: the BLOCKER convention bans "not converted yet"
reasons, so a gate-first order would require suppressions the validator rejects.

| # | step | shippable alone |
|---|---|---|
| 1 | Delete team videos (4 declarations, 2 scripts, 3 npm scripts, component, 2 astro branches, python pkg) | **Yes — do first, it shrinks the problem** |
| 2 | Create `packages/locales` + workspaces + knip + lockfile, **and convert the 16 exact-13 sites in the same commit** (an unused package fails `lint:unused`) | Yes; flag the lockfile write |
| 3 | `packages/www/src/i18n/types.ts` → `LOCALE_DISPLAY_ORDER`, `type Language = SiteLocale` | Yes |
| 4 | 4 non-English lists → `NON_ENGLISH_LOCALES` | Yes |
| 5 | NIS2 dedupe → `scripts/lib/nis2-langs.ts` | Yes |
| 6 | Subsets through `subset()` + reverse assertion + fix 2 stale ar/et/tr comments. **Widens nothing.** | Yes |
| 7 | The gate: `check-locale-sources.ts`, `.locale-set-exempt`, anti-vacuity registry line, `ci` chain, workflow lane | Yes |
| 8 | eslint 8→12 + the 8 CLI translations | Console half only |
| 8b | The 63 `private/account/web` translations | **Separate submodule PR**; step 8 cannot merge first |
| 9 | Python loaders | Per-repo, not console-gated |
| 10 | **BLOCKED** — ar/et widening, only in the commit that publishes them | **No** |

## 6. Controls (each gate must be shown able to FAIL)

- **Step 1**: before deleting, run the validator and observe **exit 0 on an absent
  directory** — that *is* the proof it was vacuous. (Confirmed: exit 0.)
- **Step 2**: in a scratch copy drop one code from `index.js`, confirm `check:types` fails
  on `Record<Language,…>` at `language-utils.ts:43`.
- **Step 6**: (a) `subset('x', ['en','xx'])` must throw at import; (b) copy the manifest to
  a scratch path, inject `solutions[*].ar`, confirm the reverse assertion fires. Without
  (b), step 6 is theatre.
- **Step 7**: three fixtures via a `LOCALE_SOURCES_ROOT` test seam (modelled on
  `CHAIN_PARITY_ROOT`) so nothing tracked is edited — stray array, mismatched `.d.ts`, and
  an **empty tree** which must fail rather than pass vacuously.
- **Step 8**: confirm `check:lint` reports exactly **8** errors in `packages/cli` before
  fixing. Immediate green would mean the rules never engaged.
- **Step 9**: delete `site-locales.json`, confirm the loader raises; pass `xx`, confirm a
  raise rather than an English fallback.

## 7. Risks

- **`eslint.config.js:114` must get `NON_ENGLISH_LOCALES`, never `SITE_LOCALES`.** Adding
  `en` makes `no-untranslated-values` compare English to English — every string in
  `en/cli.json` becomes a violation. Unbounded false-positive storm.
- **Four sites iterate a list to write files or routes** and must not change size in steps
  2-7: `generate-cli-docs.js:24` (writes per-locale docs), `www/src/i18n/types.ts:18`
  (`getStaticPaths` for `[lang]` routes), and `workers/www/src/index.ts:132` +
  `smart-redirect.ts:38` (**production edge routing** — a shrink 404s a locale, a grow
  redirects to pages Astro never built).
- **Four lists exclude `en` structurally, not for coverage.** Mapping them to
  `SITE_LOCALES` causes silent data loss: `scaffold-tutorial-transcript-locales.js` would
  overwrite authored English transcripts with `TODO:` stubs; `translate-tutorial-transcripts.ts`
  would translate English into English over the source; the two freshness/untranslated
  checks would compare English to itself.
- **The silent-fallback rule needs a distinction, not a blanket ban.**
  `packages/cli/src/i18n/config.ts:107-111` does `? base : 'en'` and that is **correct** —
  it normalizes untrusted input (`$LANG`, `--lang`). Use `assertSiteLocale()` only where the
  input is an internal invariant (manifest key, directory name). Conflating the two either
  crashes the CLI on a foreign `$LANG` or reintroduces the wrong-language bug.
- **Adding a 14th locale becomes a compile error by design** — that is the feature, but it
  makes adding one a multi-file change. Say so rather than let someone find out mid-flight.
- **`video-manifest.json` is a working-tree file** currently mid-migration, so a locally
  regenerated manifest can fire step 6's assertion before the real publish. The diagnostic
  must say the fix is either widening or not committing a manifest ahead of its publish.
