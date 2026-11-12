/**
 * i18n/cross-language-consistency, plural groups.
 *
 * A CLDR plural group (every key a category, `other` present, every value a string) is ONE leaf: ar holds zero/one/two/few/many/other where en holds one/other, and that is not a cross-language finding. The controls pin what must still fire, so the exemption cannot widen into "anything nested under a category-like key".
 */

import path from 'node:path';

export const ruleId = 'i18n/cross-language-consistency';

const EN_GROUP = JSON.stringify({
  title: 'x',
  count: { one: 'a', other: 'b' },
});
const AR_GROUP = JSON.stringify({
  title: 'x',
  count: { zero: 'a', one: 'b', two: 'c', few: 'd', many: 'e', other: 'f' },
});

const missing = { messageId: 'missingInLanguage' };
const extra = { messageId: 'extraInLanguage' };

export default async ({ jsonRuleTester, runCases, withFixture }) => {
  const { crossLanguageConsistency } = await import('../i18n/cross-language-consistency.js');
  const results = [];

  const run = (label, locale, cases, en = EN_GROUP) =>
    withFixture({ 'en/emails.json': en, 'xx/emails.json': locale }, (root) => {
      const filename = path.join(root, 'en', 'emails.json');
      const options = [{ localesDir: root, sourceLanguage: 'en' }];
      const withCtx = (list) => list.map((c) => ({ ...c, code: en, filename, options }));
      results.push(
        runCases(jsonRuleTester(), `${ruleId} (${label})`, crossLanguageConsistency, {
          valid: withCtx(cases.valid ?? []),
          invalid: withCtx(cases.invalid ?? []),
        })
      );
    });

  // Fail before the plural-group change.
  run('ar categories beside en one/other', AR_GROUP, { valid: [{}] });
  run('ja other alone', JSON.stringify({ title: 'x', count: { other: 'b' } }), {
    valid: [{}],
  });

  // CONTROLS: all three must still fire.
  run(
    'control: non-plural key extra in a locale',
    JSON.stringify({ title: 'x', extra: 'y', count: { other: 'b' } }),
    { invalid: [{ errors: [extra] }] }
  );
  run(
    'control: group missing other',
    JSON.stringify({ title: 'x', count: { one: 'a', many: 'b' } }),
    {
      invalid: [{ errors: [missing, extra, extra] }],
    }
  );
  run(
    'control: non-category key inside a would-be group',
    JSON.stringify({
      title: 'x',
      count: { one: 'a', other: 'b', plenty: 'c' },
    }),
    { invalid: [{ errors: [missing, extra, extra, extra] }] }
  );

  // Fails before the shape check: a plain string where en holds a plural group flattened to the same leaf and passed.
  run('plain string where en holds a plural group', JSON.stringify({ title: 'x', count: 'y' }), {
    invalid: [{ errors: [{ messageId: 'shapeMismatch' }] }],
  });
  // CONTROL: a plain string on both sides stays silent, so the shape check fires on the mismatch alone.
  const PLAIN = JSON.stringify({ title: 'x', count: 'y' });
  run('control: plain string on both sides', PLAIN, { valid: [{}] }, PLAIN);

  return results;
};
