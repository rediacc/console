/**
 * i18n/no-empty-translations.
 *
 * 'off' at eslint.config.js:138, :1217 and :1245, so nothing in the repository
 * ever runs it. Three distinct messageIds (empty string, whitespace only, null)
 * with three distinct code paths, none of which any planted-violation gate can
 * tell apart.
 */

export const ruleId = 'i18n/no-empty-translations';

export default async ({ jsonRuleTester, runCases }) => {
  const { noEmptyTranslations } = await import('../i18n/no-empty-translations.js');

  return [
    runCases(jsonRuleTester(), ruleId, noEmptyTranslations, {
      valid: [
        { code: '{"greeting": "Hello"}' },
        // A single space is content once something else surrounds it.
        { code: '{"joiner": " and "}' },
        // Non-string leaves other than Null are not this rule's business.
        { code: '{"count": 0, "enabled": false}' },
        // Nesting is walked, and a fully populated tree is silent.
        { code: '{"a": {"b": {"c": "text"}}}' },
      ],
      invalid: [
        {
          code: '{"greeting": ""}',
          errors: [{ messageId: 'emptyValue', data: { key: 'greeting' } }],
        },
        {
          code: '{"greeting": "   "}',
          errors: [{ messageId: 'whitespaceOnly', data: { key: 'greeting' } }],
        },
        {
          code: '{"greeting": null}',
          errors: [{ messageId: 'nullValue', data: { key: 'greeting' } }],
        },
        {
          // The reported key is the FULL dotted path, not the leaf segment. A rule that reported "c" would be useless in a 4000-key file and a planted-violation check would never notice the difference.
          code: '{"a": {"b": {"c": ""}}}',
          errors: [{ messageId: 'emptyValue', data: { key: 'a.b.c' } }],
        },
        {
          // Every offending leaf is reported, not just the first.
          code: '{"one": "", "two": null, "three": " "}',
          errors: [
            { messageId: 'emptyValue' },
            { messageId: 'nullValue' },
            { messageId: 'whitespaceOnly' },
          ],
        },
      ],
    }),
  ];
};
