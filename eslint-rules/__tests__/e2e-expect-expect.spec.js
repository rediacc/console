/**
 * custom/e2e-expect-expect.
 *
 * Host port of `eslint-plugin-playwright`'s `expect-expect`, configured with
 * this repo's real `assertFunctionPatterns` (`eslint.config/tests.js:36-47`).
 * See `eslint-rules/e2e-expect-expect.js`'s own header for why bare `test(...)`
 * is the only call this repo's config makes reachable (vitest's `it`/`describe`
 * are invisible to the REAL plugin too, absent a configured
 * `settings.playwright.globalAliases`).
 */

const OPTIONS = [
  {
    assertFunctionPatterns: [
      '^verify',
      '^ensure',
      '^validate',
      '^assert',
      '^expect[A-Z]',
      '^createTeamViaUI$',
      '^createUserViaUI$',
      '^waitForTeamRow$',
    ],
  },
];

export const ruleId = 'custom/e2e-expect-expect';

export default async ({ sourceRuleTester, runCases }) => {
  const { e2eExpectExpect } = await import('../e2e-expect-expect.js');

  return [
    runCases(sourceRuleTester(), ruleId, e2eExpectExpect, {
      valid: [
        // A direct expect(...).matcher() call.
        {
          code: "test('t', async ({ page }) => {\n  expect(page).toBeDefined();\n});\n",
          options: OPTIONS,
        },
        // A call matching one of assertFunctionPatterns counts too, not just expect() itself.
        {
          code: "test('t', async ({ page }) => {\n  await verifyLogin(page);\n});\n",
          options: OPTIONS,
        },
        // An exact-match pattern.
        { code: "test('t', async () => {\n  await createTeamViaUI();\n});\n", options: OPTIONS },
        // An assertion nested inside a test.step still counts for the parent test.
        {
          code: "test('t', async ({ page }) => {\n  await test.step('a step', async () => {\n    expect(1).toBe(1);\n  });\n});\n",
          options: OPTIONS,
        },
        // Not a test call at all -- an ordinary function is not graded on carrying an assertion.
        { code: 'function helper() {\n  return 1;\n}\n', options: OPTIONS },
        // vitest's it(...) is invisible to this rule, matching the real plugin (see the rule's own header).
        { code: "it('t', () => {\n  doSomething();\n});\n", options: OPTIONS },
        // test.describe / test.use / hooks are not test bodies and are never graded.
        { code: "test.describe('suite', () => {\n  doSetup();\n});\n", options: OPTIONS },
      ],
      invalid: [
        {
          code: "test('does a thing', async ({ page }) => {\n  await page.goto('/');\n});\n",
          options: OPTIONS,
          errors: [{ messageId: 'noAssertions' }],
        },
        {
          // test.only carries the same requirement as bare test.
          code: "test.only('does a thing', async ({ page }) => {\n  await page.goto('/');\n});\n",
          options: OPTIONS,
          errors: [{ messageId: 'noAssertions' }],
        },
        {
          // A nested test.step with no assertion anywhere in the whole test still leaves the outer test unchecked.
          code: "test('t', async () => {\n  await test.step('a step', async () => {\n    doWork();\n  });\n});\n",
          options: OPTIONS,
          errors: [{ messageId: 'noAssertions' }],
        },
      ],
    }),
  ];
};
