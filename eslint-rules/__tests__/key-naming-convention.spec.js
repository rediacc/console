/**
 * i18n/key-naming-convention.
 *
 * 'off' at eslint.config.js:140. Four selectable key formats and a nesting-depth
 * limit, which is five behaviours behind one rule id. A liveness probe proves at
 * most that one of them fires.
 */

export const ruleId = 'i18n/key-naming-convention';

export default async ({ jsonRuleTester, runCases }) => {
  const { keyNamingConvention } = await import('../i18n/key-naming-convention.js');

  return [
    runCases(jsonRuleTester(), ruleId, keyNamingConvention, {
      valid: [
        // camelCase is the default format.
        { code: '{"someKey": "v", "another": "v"}' },
        { code: '{"outer": {"innerKey": "v"}}' },
        // An explicit allowedPatterns entry exempts a key the format rejects.
        {
          code: '{"SCREAMING_CASE": "v"}',
          options: [{ allowedPatterns: ['^SCREAMING_CASE$'] }],
        },
        // Selecting a different format changes what is legal.
        { code: '{"kebab-key": "v"}', options: [{ keyFormat: 'kebab-case' }] },
        { code: '{"snake_key": "v"}', options: [{ keyFormat: 'snake_case' }] },
        { code: '{"PascalKey": "v"}', options: [{ keyFormat: 'PascalCase' }] },
        // Exactly at the depth limit is allowed; the limit is a maximum.
        { code: '{"a": {"b": {"c": "v"}}}', options: [{ maxNestingDepth: 3 }] },
      ],
      invalid: [
        {
          code: '{"some_key": "v"}',
          // `data` must name EVERY placeholder in the message: RuleTester hydrates it and compares the whole string, so a partial `data`
          // fails with an unhydrated `{{path}}` still in the expectation.
          errors: [
            {
              messageId: 'invalidFormat',
              data: { key: 'some_key', format: 'camelCase', path: 'some_key' },
            },
          ],
        },
        {
          // A key legal under the default becomes illegal once the format is switched, which is the direction a planted violation cannot show.
          code: '{"someKey": "v"}',
          options: [{ keyFormat: 'kebab-case' }],
          errors: [
            {
              messageId: 'invalidFormat',
              data: { key: 'someKey', format: 'kebab-case', path: 'someKey' },
            },
          ],
        },
        {
          // One level past the configured limit.
          code: '{"a": {"b": {"c": "v"}}}',
          options: [{ maxNestingDepth: 2 }],
          errors: [{ messageId: 'tooDeep', data: { path: 'a.b.c', max: '2' } }],
        },
        {
          // The nested key is reported with its full path, so a reader can find it in a large file.
          code: '{"outer": {"bad_inner": "v"}}',
          errors: [
            {
              messageId: 'invalidFormat',
              data: { key: 'bad_inner', format: 'camelCase', path: 'outer.bad_inner' },
            },
          ],
        },
      ],
    }),
  ];
};
