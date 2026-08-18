/**
 * The languages Directive (EU) 2022/2555 (NIS2) is officially published in AND that we
 * translate the surrounding www content into.
 *
 * This is a REAL, permanent subset of the site's locales, not drift: EUR-Lex publishes the
 * directive in these seven, and `scripts/data/nis2-directive-2022-2555-<lang>.txt` vendors
 * a snapshot for each. Locales outside this set fall back to the English snapshot for the
 * directive-quote check, because no official translation exists to quote.
 *
 * It lived as two identical hand-maintained arrays — `SNAPSHOT_LANGS` in
 * check-directive-quotes.ts and `SUPPORTED_LANGS` in fetch-directive-snapshot.ts — which
 * is one fact declared twice, with nothing keeping them equal. They now import from here.
 *
 * Built with `subset()` so an unknown code throws at module load instead of silently never
 * matching a file that was never going to exist.
 */
import { type SiteLocale, subset } from '@rediacc/locales';

export const NIS2_SNAPSHOT_LANGS = subset('nis2-snapshot', [
  'en',
  'de',
  'es',
  'fr',
  'et',
  'it',
  'pt',
]) as readonly ['en', 'de', 'es', 'fr', 'et', 'it', 'pt'];

export type Nis2SnapshotLang = (typeof NIS2_SNAPSHOT_LANGS)[number];

/** Compile-time guard: every entry above must be a real site locale. */
type _AllAreSiteLocales = Nis2SnapshotLang extends SiteLocale ? true : never;
const _check: _AllAreSiteLocales = true;
void _check;
