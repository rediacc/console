/**
 * i18n/translation-coverage, plural groups.
 *
 * A CLDR plural group counts once, by its `other` key, so ja/ko/zh (other alone) reach 100% against en's one/other, and ar's six categories do not inflate past it. The controls pin that a genuinely missing key and a wholly missing group still lower coverage.
 */

import path from 'node:path';

export const ruleId = 'i18n/translation-coverage';

const EN = JSON.stringify({ title: 'x', count: { one: 'a', other: 'b' } });

export default async ({ jsonRuleTester, runCases, withFixture }) => {
  const { translationCoverage } = await import('../i18n/translation-coverage.js');
  const results = [];

  const run = (label, locale, cases) =>
    withFixture({ 'en/emails.json': EN, 'xx/emails.json': locale }, (root) => {
      const filename = path.join(root, 'en', 'emails.json');
      const options = [{ localesDir: root, sourceLanguage: 'en', minimumCoverage: 100 }];
      const withCtx = (list) => list.map((c) => ({ ...c, code: EN, filename, options }));
      results.push(
        runCases(jsonRuleTester(), `${ruleId} (${label})`, translationCoverage, {
          valid: withCtx(cases.valid ?? []),
          invalid: withCtx(cases.invalid ?? []),
        })
      );
    });

  // Fails before the change: 2 locale leaves against en's 3.
  run('ja other alone', JSON.stringify({ title: 'x', count: { other: 'b' } }), {
    valid: [{}],
  });

  // CONTROLS
  run('control: key missing', JSON.stringify({ count: { other: 'b' } }), {
    invalid: [{ errors: [{ messageId: 'lowCoverage' }] }],
  });
  run('control: whole group missing', JSON.stringify({ title: 'x' }), {
    invalid: [{ errors: [{ messageId: 'lowCoverage' }] }],
  });

  return results;
};
