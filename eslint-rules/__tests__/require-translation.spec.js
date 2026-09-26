/**
 * custom/require-translation.
 *
 * A key is looked up only when the callee is a `t`: one bound by useTranslation(), or an identifier
 * named `t` (the CLI imports it and prefixes keys `cli:`). Before 2026-09-26 a string with a colon was
 * split as `ns:key` and checked whatever the callee was, so the Tailwind class string in
 * `cn('h-11 md:text-lg')` was reported as a missing translation key.
 */

export const ruleId = 'custom/require-translation';

const OPTIONS = [{ localeDir: 'private/account/web/src/i18n/locales/en' }];
const FILE = 'private/account/web/src/pages/Probe.tsx';

const importedT = (body) => `import { t } from '../i18n/index.js';\n${body}\n`;

const withT = (body) =>
  `import { useTranslation } from 'react-i18next';\nexport function Probe() {\n  const { t } = useTranslation('admin');\n  ${body}\n}\n`;

export default async ({ sourceRuleTester, runCases }) => {
  const { requireTranslation } = await import('../require-translation.js');

  return [
    runCases(sourceRuleTester(), ruleId, requireTranslation, {
      valid: [
        // A real key under the binding's namespace.
        { code: withT("return t('contact.allStatusesOption');"), filename: FILE, options: OPTIONS },
        // A class string with a variant prefix is not a translation call (the regression).
        {
          code: withT("return cn('h-11 font-mono text-lg md:text-lg');"),
          filename: FILE,
          options: OPTIONS,
        },
        // Any other function taking a colon string is not a translation call either.
        { code: withT("return log('scope:detail');"), filename: FILE, options: OPTIONS },
        // An imported `t` with a real namespaced key.
        {
          code: importedT("t('admin:contact.allStatusesOption');"),
          filename: FILE,
          options: OPTIONS,
        },
      ],
      invalid: [
        // CONTROL: a missing key through the bound `t` is still reported.
        {
          code: withT("return t('contact.noSuchKeyForTheSpec');"),
          filename: FILE,
          options: OPTIONS,
          errors: [{ messageId: 'missingKey' }],
        },
        // CONTROL: an explicit namespace through the bound `t` is still checked.
        {
          code: withT("return t('admin:contact.noSuchKeyForTheSpec');"),
          filename: FILE,
          options: OPTIONS,
          errors: [{ messageId: 'missingKey' }],
        },
        // CONTROL: an imported `t` (the CLI's form) is checked too; the first 2026-09-26 fix skipped it.
        {
          code: importedT("t('admin:contact.noSuchKeyForTheSpec');"),
          filename: FILE,
          options: OPTIONS,
          errors: [{ messageId: 'missingKey' }],
        },
      ],
    }),
  ];
};
