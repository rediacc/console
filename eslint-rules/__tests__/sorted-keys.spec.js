/**
 * i18n/sorted-keys.
 *
 * This rule is 'off' in every config block (eslint.config.js:139, :1218) and is
 * therefore outside check_lint_rule_liveness.py's universe by construction. It
 * is also the rule that had 2172 real findings waiting behind the 2026-08-06
 * `node.body?.members` bug, so "it is off, nobody cares" is exactly the reading
 * that cost the repository five rules.
 */

export const ruleId = 'i18n/sorted-keys';

export default async ({ jsonRuleTester, runCases }) => {
  const { sortedKeys } = await import('../i18n/sorted-keys.js');

  return [
    runCases(jsonRuleTester(), ruleId, sortedKeys, {
      valid: [
        // Flat, already sorted.
        { code: '{"alpha": "1", "beta": "2", "gamma": "3"}' },
        // Nested objects are checked independently, each already sorted.
        { code: '{"a": {"x": "1", "y": "2"}, "b": "3"}' },
        // A single key cannot be out of order.
        { code: '{"only": "1"}' },
        // caseSensitive defaults to false, so "Beta" and "alpha" compare by base letter and this IS sorted under the default.
        { code: '{"alpha": "1", "Beta": "2"}' },
        // natural defaults to true: 2 sorts before 10, not after.
        { code: '{"item2": "a", "item10": "b"}' },
        // The other half of the caseSensitive pair below: identical base letters compare equal under the default, so this is sorted.
        { code: '{"Beta": "1", "beta": "2"}' },
      ],
      invalid: [
        {
          // The plain out-of-order case, and the autofix rewrites the object.
          code: '{"beta": "2", "alpha": "1"}',
          errors: [{ messageId: 'unsorted', data: { current: 'alpha', previous: 'beta' } }],
          output: '{"alpha": "1",\n  "beta": "2"}',
        },
        {
          // Only the FIRST out-of-order pair is reported per object. Three keys in reverse order is one finding, not two: reportFirstUnsorted returns after the first report on purpose.
          code: '{"c": "3", "b": "2", "a": "1"}',
          errors: 1,
          output: '{"a": "1",\n  "b": "2",\n  "c": "3"}',
        },
        {
          // A nested object is its own scope, so the outer keys being sorted does not excuse the inner ones.
          code: '{"outer": {"z": "1", "a": "2"}}',
          errors: [{ messageId: 'unsorted', data: { current: 'a', previous: 'z' } }],
          output: '{"outer": {"a": "2",\n  "z": "1"}}',
        },
        {
          // `caseSensitive` maps to localeCompare's `sensitivity`, and it only separates two keys whose BASE letters are identical. Measured: ('Beta','beta') compares 0 under 'base' and 1 under 'case', while ('alpha','Beta') is -1 under both. So this pair is sorted by default and a finding once case counts, and the pair one line above is unaffected by the option. Same input,
          // opposite verdict, decided entirely by an option, which is the thing a planted violation cannot see.
          code: '{"Beta": "1", "beta": "2"}',
          options: [{ caseSensitive: true }],
          errors: [{ messageId: 'unsorted', data: { current: 'beta', previous: 'Beta' } }],
          output: '{"beta": "2",\n  "Beta": "1"}',
        },
        {
          // With natural sorting turned OFF, string order applies and item10 precedes item2. The option therefore changes the verdict, which is the part a single planted violation could never show.
          code: '{"item2": "a", "item10": "b"}',
          options: [{ natural: false }],
          errors: [{ messageId: 'unsorted' }],
          output: '{"item10": "b",\n  "item2": "a"}',
        },
      ],
    }),
  ];
};
