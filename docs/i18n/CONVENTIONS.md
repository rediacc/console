# i18n conventions (read this before touching translations)

This repo localizes `packages/www` into 12 languages. **English is the single source
of truth**; every other locale is derived from it. These conventions exist so that AI
sessions and humans keep translations aligned and cheap to maintain. The i18n CI gates
(`npm run check:i18n`, `npm run check:lint`) enforce them.

## 1. English is the source — keep it natural, then lock it

- English (`packages/www/src/i18n/translations/en.json`) must read as **natural, daily
  language**: grade 5-7 for marketing copy; precise and technical for docs. Clear,
  natural English is easier to translate well; convoluted or jargon-heavy English
  produces awkward translations.
- English is optimized **first**, then **locked**: after any English value change, run
  `npm run i18n:generate-hashes` (updates `.translation-hashes.json`, the per-key
  English CRC32 manifest) so the freshness gates pass.
- Every English change cascades to 12 languages. Avoid churning English after
  translating — it re-stales the translations of the changed keys.

## 2. Translations are NATURALIZED, not literal

- A translation must read the way a **native speaker actually talks**, not a
  word-for-word rendering. Example (Turkish `hero.title`):
  - English: `Clone Production.`
  - Literal (wrong): `Üretimi Klonla.`
  - Natural (right): `Canlı Ortamı Klonla.`
- Restructure word order, idioms, and sentence shape freely so it sounds native.
  Avoid calques and machine-translation stiffness.
- **Do not hand-translate literally or bulk machine-translate.** Use the
  naturalization pipeline at `private/growth/i18n_pipeline/` (or hand-write natural copy).

### Model: use haiku (cheapest) — IMPORTANT for cost

- Run the pipeline with **`--model haiku`**. It is the default and the cheapest
  capable model, and it produced good results for English and Turkish. The
  naturalization ledger records the model used per language (`$meta.models` in
  `.naturalized-hashes.json`).
- Only bump to `--model sonnet` / `--model opus` for a specific language whose haiku
  output reads awkward (the judge's `naturalness` score is the signal). Do not default
  to the expensive models — translations run ×12 languages, so model cost compounds.

## 3. What must be preserved verbatim in a translation

- Every `{{placeholder}}` (exact name + braces) — enforced by `interpolation-consistency`.
- Every HTML tag (`<a href=…>`, `<code>…`), number, currency, and product name
  (Rediacc, Docker, btrfs, LUKS, GitLab, NIS2, …).
- Keys, key order, and structure mirror English exactly. Change **values only** —
  never add/remove/rename keys (enforced by `cross-language-consistency`,
  `sorted-keys`, `translation-coverage`).
- A translation must differ from English (enforced by `no-untranslated-values`) and be
  non-empty (`no-empty-translations`).

## 4. When English changes: re-translate ONLY the delta (do not re-do everything)

The pipeline tracks, per `(language, key)`, the English CRC32 each translation was last
naturalized against, in a committed ledger:
`packages/www/src/i18n/translations/.naturalized-hashes.json`.

Workflow after an English edit:
1. `npm run i18n:generate-hashes` — refresh the English hash manifest.
2. `npm run i18n:naturalize-status` — see exactly which keys went **stale** (English
   changed since they were naturalized) and which are **never naturalized**.
3. Re-naturalize **only the changed keys** via `private/growth/i18n_pipeline`
   (`./run.sh --lang <lang> --surface <surface>`). The pipeline reads the ledger and
   **skips keys whose English is unchanged**, so you never pay to redo finished work.
   Use `--force` only for a deliberate full re-run.

`check-i18n-naturalization` is a **blocking** CI gate (part of `check:i18n`): it fails
when a key that was already naturalized has gone stale. It does **not** fail keys that
were never naturalized (that backlog shrinks as more languages/surfaces are done).

## 5. For AI sessions specifically

- Never bulk-replace a locale file with literal/machine translations.
- Respect the ledger: if `npm run i18n:naturalize-status` shows a key as naturalized
  and not stale, leave it alone.
- If you change English, follow the §4 workflow (regenerate hashes, run the pipeline on
  the delta) — do not hand-fix 12 locale files.
- Preserve every placeholder/HTML/number/product name; keep keys and order intact.

Pipeline + tooling: `private/growth/i18n_pipeline/README.md`,
`npm run i18n:generate-hashes`, `npm run i18n:sync`, `npm run i18n:naturalize-status`.

## Never glue a case suffix onto a placeholder in an agglutinative language

`{{placeholder}}` values are runtime-unknown, and in Turkish, Estonian, Finnish
and Hungarian the correct suffix depends on the sounds of the word it attaches
to. Turkish vowel harmony picks `'a` or `'e` from the last vowel, so
`{{provider}}'a sor` is right for one provider name and wrong for the next --
and no gate can catch it, because the string is only assembled at render time
with a value nobody validated.

Use a POSTPOSITION or a separate word instead, which is invariant:

    tr   {{provider}} ile sor        not  {{provider}}'a sor
    et   {{provider}} käest          not  a glued case ending

This reads slightly more formal than a native speaker's first instinct, and that
is the trade being made deliberately: mildly formal everywhere beats
grammatically wrong for half the values. Do not "improve" these back to a glued
suffix without first bounding the set of values the placeholder can take.

Recorded 2026-08-23, after the reviewing session flagged `{{provider}} ile sor`
as possibly unnatural and the translating agent's reason turned out to be the
stronger one.

## A locale value byte-identical to English is a finding, even when the words are borrowed

`check-translation-completeness` counts an identical string as untranslated, and
it is right to. German legitimately borrows "CLI", "Backup", "Standards" and
"Frameworks", but keeping the English `&` too made whole values identical to
their English source. The fix is not to abandon the loanword; it is to write the
rest of the string in the target language:

    "CLI & Tools"              ->  "CLI und Tools"
    "Backup & Migration"       ->  "Backup und Migration"
    "Standards & Frameworks"   ->  "Standards und Frameworks"

A genuine coincidence can also trip this -- French `Architecture` is spelled
exactly as the English -- and the answer there is the same: pick the phrasing a
native technical document would use (`Architecture système`) rather than
suppressing the check.
