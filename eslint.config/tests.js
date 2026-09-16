// ---------------------------------------------------------------------------
// TEST FILE OVERRIDES
//
// Every test surface in the repo: playwright E2E, the __tests__ convention for
// unit tests, the stub-test exemption, and the no-skip policy for vitest.
// ---------------------------------------------------------------------------
//
// ORDER IS THE CONTRACT. Flat config resolves by LAST MATCH WINS, so these
// blocks mean what they mean only in the position eslint.config.js splices them
// into. This module is a verbatim slice of the single 1,444-line file that came
// before it: the blocks, their order, their comments and their whitespace are
// unchanged. Anything else would be a rewrite wearing a refactor's clothes.
// ---------------------------------------------------------------------------

import playwrightPlugin from 'eslint-plugin-playwright';

export default [
  // =============================================================
  // TEST FILE OVERRIDES
  // =============================================================
  // These patterns cover ALL test file locations:
  // - E2E tests: packages/e2e-tests/**
  // - CLI Unit tests: packages/cli/src/**/__tests__/**
  // - Shared: packages/shared/src/**/__tests__/**
  // =============================================================
  {
    files: [
      'packages/e2e-tests/**/*.ts',
      // Unit test files (__tests__ convention)
      'packages/shared/src/**/__tests__/**/*.{ts,tsx}',
      'packages/cli/src/**/__tests__/**/*.ts',
    ],
    plugins: {
      playwright: playwrightPlugin,
    },
    rules: {
      // Enforce the e2e test filename convention. The rule was imported and
      // registered but never switched on in any config block, so it was dead
      // weight that read as coverage. It self-guards to packages/e2e-tests/tests,
      // so listing it here does not reach the unit-test globs above.
      'custom/e2e-test-naming-convention': 'error',

      // --- Playwright-specific rules ---
      'playwright/no-wait-for-timeout': 'error',
      'playwright/no-focused-test': 'error',
      'playwright/no-skipped-test': 'off',
      'playwright/valid-expect': 'error',
      'playwright/expect-expect': ['error', {
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
      }],

      // --- General test file rules ---
      'max-lines': 'off',
      'max-nested-callbacks': ['error', 5],

      // --- Disable production-only rules ---
      'custom/require-translation': 'off',
      'custom/no-hardcoded-text': 'off',
      'custom/no-hardcoded-cli-text': 'off',
      'custom/require-command-summary': 'off',
      'custom/no-hardcoded-nullish-defaults': 'off',
      'react/forbid-elements': 'off',
      'custom/require-testid': 'off',

      // --- TypeScript relaxations for tests ---
      '@typescript-eslint/prefer-nullish-coalescing': ['error', {
        ignorePrimitives: {
          boolean: true,
          number: true,
          string: true,
        },
      }],
    },
  },

  // =============================================================
  // E2E STUB TESTS - PENDING IMPLEMENTATION
  // =============================================================
  // Stub test files (test.skip with TODO bodies) are exempted from
  // expect-expect until they are implemented. Remove entries from this
  // list as tests are filled in.
  {
    files: [
      // E2E: tests with setup/cleanup steps lacking assertions
      'packages/e2e-tests/tests/12a-full-integration-repository.test.ts',
      'packages/e2e-tests/tests/13-postgres-fork-isolation.test.ts',
      // The destructive VM-lifecycle tests (diagnostic reachability logging
      // without assertions) moved here from 18-ops-workflow.test.ts; the
      // remaining Parallel Execution test in that file DOES assert, so it left
      // the list.
      'packages/e2e-tests/tests/ops-lifecycle/18-ops-lifecycle.test.ts',
    ],
    rules: {
      'playwright/expect-expect': 'off',
    },
  },

  // =============================================================
  // UNIT TESTS - STRICT NO SKIP POLICY
  // =============================================================
  // Vitest unit tests should never be skipped - fix them
  {
    files: [
      'packages/shared/src/**/__tests__/**/*.{ts,tsx}',
    ],
    rules: {
      'no-restricted-syntax': ['error',
        {
          selector: "CallExpression[callee.object.name='it'][callee.property.name='skip']",
          message: 'it.skip() is not allowed in unit tests. Fix the test.',
        },
        {
          selector: "CallExpression[callee.object.name='test'][callee.property.name='skip']",
          message: 'test.skip() is not allowed in unit tests. Fix the test.',
        },
        {
          selector: "CallExpression[callee.object.name='describe'][callee.property.name='skip']",
          message: 'describe.skip() is not allowed in unit tests. Fix the tests.',
        },
      ],
    },
  },
];
