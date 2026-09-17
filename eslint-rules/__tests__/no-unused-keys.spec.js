/**
 * i18n/no-unused-keys.
 *
 * 'off' at eslint.config.js:160. It reads a real directory of source files
 * through shared/key-extractor.js, so its spec needs a fixture on disk rather
 * than a string of code, and that is not incidental: the option resolver
 * REFUSES a directory that does not exist, on the grounds that a rule reading
 * nothing reports nothing.
 *
 * Writing this spec found a defect. `extractUsedKeys` cached its result in a
 * single unkeyed module-level slot with a 30 second TTL, so the second call
 * within the window returned the FIRST directory's key set whatever directory
 * it was asked about. Two fixtures in one process returned identical answers.
 * The cache is now keyed by source directory; the two fixture cases below are
 * what would catch its return.
 */

export const ruleId = 'i18n/no-unused-keys';

export default async ({ jsonRuleTester, runCases, withFixture }) => {
  const { noUnusedKeys } = await import('../i18n/no-unused-keys.js');
  const { clearKeyExtractorCache } = await import('../i18n/shared/key-extractor.js');

  const results = [];

  // Fixture A: a source tree that uses `greeting` and nothing else.
  withFixture({ 'src/app.ts': "export const x = t('greeting');\n" }, (dirA) => {
    clearKeyExtractorCache();
    results.push(
      runCases(jsonRuleTester(), `${ruleId} (used-key fixture)`, noUnusedKeys, {
        valid: [
          {
            // The namespace comes from the FILENAME, and the extractor files a bare `t('greeting')` under the implicit `common` namespace, so the locale file has to be common.json for the two to meet.
            code: '{"greeting": "Hello"}',
            filename: 'common.json',
            options: [{ sourceDir: dirA }],
          },
          {
            // A parent of a used key counts as used, so an object wrapper is not reported just because nobody calls t() on the wrapper itself.
            code: '{"greeting": {"formal": "Good day"}}',
            filename: 'common.json',
            options: [{ sourceDir: dirA }],
          },
        ],
        invalid: [
          {
            code: '{"greeting": "Hello", "farewell": "Bye"}',
            filename: 'common.json',
            options: [{ sourceDir: dirA }],
            errors: [{ messageId: 'unusedKey', data: { key: 'farewell' } }],
          },
          {
            // ignorePatterns is a regex list, and it suppresses only what it matches. `farewell` stays reported, `legacyThing` does not.
            code: '{"greeting": "Hello", "farewell": "Bye", "legacyThing": "x"}',
            filename: 'common.json',
            options: [{ sourceDir: dirA, ignorePatterns: ['^legacy'] }],
            errors: [{ messageId: 'unusedKey', data: { key: 'farewell' } }],
          },
        ],
      })
    );
  });

  // Fixture B: a DIFFERENT tree, using a different key. Under the old unkeyed cache this block silently reused fixture A's key set and `farewell` came back reported as unused, which is the wrong answer.
  withFixture({ 'src/app.ts': "export const x = t('farewell');\n" }, (dirB) => {
    results.push(
      runCases(jsonRuleTester(), `${ruleId} (second fixture, cache isolation)`, noUnusedKeys, {
        valid: [
          {
            code: '{"farewell": "Bye"}',
            filename: 'common.json',
            options: [{ sourceDir: dirB }],
          },
        ],
        invalid: [
          {
            // And the key fixture A considered used must now be reported, which is the same assertion read from the other side.
            code: '{"greeting": "Hello"}',
            filename: 'common.json',
            options: [{ sourceDir: dirB }],
            errors: [{ messageId: 'unusedKey', data: { key: 'greeting' } }],
          },
        ],
      })
    );
  });

  return results;
};
