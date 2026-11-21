/**
 * CLDR plural groups in locale JSON.
 *
 * A PLURAL GROUP is an object whose keys are all CLDR plural categories, include `other`, and whose values are all strings. It is read at runtime as `<key>.<category>` with `Intl.PluralRules(locale)` choosing the category, so each locale legitimately holds a DIFFERENT category set (en one/other, ru one/few/many/other, ar all six, ja other alone). The key-set rules therefore treat a group as ONE leaf. The same test lives in scripts/gates/check-account-email-templates.ts, which enforces the per-locale category sets.
 *
 * Anything short of the full test (no `other`, a non-category key, a non-string value) is not a group and keeps being compared key by key, so a typo inside a would-be group still fires.
 */

const PLURAL_CATEGORIES = new Set(['zero', 'one', 'two', 'few', 'many', 'other']);

/** True when `obj` is a CLDR plural group. */
export const isPluralGroup = (obj) => {
  if (obj === null || typeof obj !== 'object' || Array.isArray(obj)) return false;
  const entries = Object.entries(obj);
  return (
    entries.some(([key]) => key === 'other') &&
    entries.every(([key, value]) => PLURAL_CATEGORIES.has(key) && typeof value === 'string')
  );
};
