/**
 * i18n/translation-staleness.
 *
 * 'off' at eslint.config.js:158. It derives the hash manifest's location from
 * `context.filename` (the parent of the language directory), reads it from
 * disk, and reports three different things depending on what it finds. All
 * three are filesystem-shaped, so this spec is fixture-driven.
 *
 * The stored hashes here are deliberately NOT computed with the rule's own
 * crc32. A spec that recomputes the value under test proves only that the
 * function equals itself. What matters is the DECISION: manifest missing,
 * key absent from the manifest, and stored value disagreeing with the current
 * one, each of which is provable with a hash the test simply asserts is wrong.
 */

import fs from 'node:fs';
import path from 'node:path';

export const ruleId = 'i18n/translation-staleness';

export default async ({ jsonRuleTester, runCases, withFixture }) => {
  const { translationStaleness } = await import('../i18n/translation-staleness.js');

  const results = [];

  // The rule only acts on files whose parent directory is named `en`, and it
  // looks for the manifest one level above that.
  //
  // The manifest's real shape is `{ "hashes": { <key>: <crc32> } }`. Writing a
  // FLAT object here was the spec's first mistake, and the rule read it as an
  // empty manifest and answered `newKey`: a hash file whose top-level key is
  // wrong degrades silently to "nothing is recorded", which is worth knowing.
  withFixture({ '.translation-hashes.json': '{"hashes": {}}' }, (root) => {
    const enFile = path.join(root, 'en', 'common.json');

    results.push(
      runCases(jsonRuleTester(), `${ruleId} (non-en is skipped)`, translationStaleness, {
        valid: [
          {
            // Any language other than `en` returns an empty visitor, so no
            // manifest is even consulted. This is why a missing manifest under
            // a translated tree is silent rather than noisy.
            code: '{"greeting": "Merhaba"}',
            filename: path.join(root, 'tr', 'common.json'),
          },
        ],
        invalid: [],
      })
    );

    results.push(
      runCases(jsonRuleTester(), `${ruleId} (key absent from manifest)`, translationStaleness, {
        valid: [],
        invalid: [
          {
            // An empty manifest exists, so this is `newKey`, not
            // `missingHashFile`. The key is namespaced by the file basename.
            code: '{"greeting": "Hello"}',
            filename: enFile,
            // Only the messageId is asserted. The message also carries the
            // freshly computed crc32, and a test that recomputed it with the
            // rule's own function would prove only that the function equals
            // itself. The DECISION is the assertion worth making.
            errors: [{ messageId: 'newKey' }],
          },
        ],
      })
    );

    // Now put a WRONG hash in the manifest and the verdict changes from
    // "new key" to "stale translation" without the source file moving.
    fs.writeFileSync(
      path.join(root, '.translation-hashes.json'),
      JSON.stringify({ hashes: { 'common.greeting': 'deadbeef' } })
    );

    results.push(
      runCases(jsonRuleTester(), `${ruleId} (stored hash disagrees)`, translationStaleness, {
        valid: [],
        invalid: [
          {
            code: '{"greeting": "Hello"}',
            filename: enFile,
            // Same key, same file, same rule: the verdict flipped from
            // `newKey` to `staleTranslation` purely because the manifest now
            // records a value and it disagrees. That flip is the rule's whole
            // job and no planted-violation probe can see it.
            errors: [{ messageId: 'staleTranslation' }],
          },
        ],
      })
    );
  });

  // A tree with no manifest at all reports `missingHashFile` once against the
  // document, not once per key.
  withFixture({ 'en/.keep': '' }, (root) => {
    results.push(
      runCases(jsonRuleTester(), `${ruleId} (manifest missing)`, translationStaleness, {
        valid: [],
        invalid: [
          {
            code: '{"greeting": "Hello", "farewell": "Bye"}',
            filename: path.join(root, 'en', 'common.json'),
            errors: [{ messageId: 'missingHashFile' }],
          },
        ],
      })
    );
  });

  return results;
};
