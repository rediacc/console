// --------------------------------------------------------------------------- PER-PACKAGE OVERRIDES
//
// private/account, packages/www, packages/json and the scripts/ tree. These are the blocks whose reason for existing is a package boundary rather than a rule
// family: what account lints for instead of ESLint, what an Astro site does not
// have, and which trees are handed to another tool entirely. ---------------------------------------------------------------------------
//
// ORDER IS THE CONTRACT. Flat config resolves by LAST MATCH WINS, so these
// blocks mean what they mean only in the position eslint.config.js splices them
// into. This module is a verbatim slice of the single 1,444-line file that came before it: the blocks, their order, their comments and their whitespace are unchanged. Anything else would be a rewrite wearing a refactor's clothes. ---------------------------------------------------------------------------

import json from '@eslint/json';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import { i18nJsonPlugin } from '../eslint-rules/i18n/index.js';

export default [
  // =============================================================
  // ACCOUNT PACKAGE OVERRIDES (private/account)
  // =============================================================
  // Disable ALL inherited rules for account package. Account only
  // uses ESLint for i18n enforcement (require-translation,
  // no-hardcoded-text, interpolation-match) via dedicated config blocks above. Other code quality is handled by Biome + tsc.
  {
    files: ['private/account/**/*.{ts,tsx}'],
    rules: {
      // --- TypeScript strict rules ---
      '@typescript-eslint/no-floating-promises': 'off',
      '@typescript-eslint/await-thenable': 'off',
      '@typescript-eslint/no-misused-promises': 'off',
      '@typescript-eslint/no-unnecessary-type-assertion': 'off',
      '@typescript-eslint/no-unnecessary-condition': 'off',
      '@typescript-eslint/require-await': 'off',
      '@typescript-eslint/use-unknown-in-catch-callback-variable': 'off',
      // --- TypeScript stylistic rules ---
      '@typescript-eslint/prefer-nullish-coalescing': 'off',
      '@typescript-eslint/prefer-optional-chain': 'off',
      '@typescript-eslint/prefer-includes': 'off',
      '@typescript-eslint/prefer-for-of': 'off',
      '@typescript-eslint/prefer-string-starts-ends-with': 'off',
      '@typescript-eslint/array-type': 'off',
      '@typescript-eslint/consistent-type-assertions': 'off',
      '@typescript-eslint/prefer-readonly': 'off',
      '@typescript-eslint/prefer-regexp-exec': 'off',
      '@typescript-eslint/no-redundant-type-constituents': 'off',
      '@typescript-eslint/require-array-sort-compare': 'off',
      '@typescript-eslint/no-inferrable-types': 'off',
      '@typescript-eslint/no-deprecated': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      '@typescript-eslint/prefer-as-const': 'off',
      // --- General quality rules ---
      'no-console': 'off',
      'max-lines': 'off',
      'max-nested-callbacks': 'off',
      'no-nested-ternary': 'off',
      'prefer-template': 'off',
      // --- SonarQube parity ---
      'sonarjs/cognitive-complexity': 'off',
      // --- Unicorn rules ---
      'unicorn/prefer-number-properties': 'off',
      'unicorn/prefer-string-replace-all': 'off',
      'unicorn/no-negated-condition': 'off',
      'unicorn/no-array-push-push': 'off',
      'unicorn/prefer-node-protocol': 'off',
      // --- React rules ---
      'react/forbid-elements': 'off',
      'react/hook-use-state': 'off',
      'react/button-has-type': 'off',
      'react/no-unescaped-entities': 'off',
      // --- React Hooks (pre-existing patterns) ---
      'react-hooks/exhaustive-deps': 'off',
      'react-hooks/rules-of-hooks': 'off',
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/purity': 'off',
      'react-hooks/preserve-manual-memoization': 'off',
      // --- Custom rules (inherited from base config) --- require-testid is ON for this tree since 2026-08-15. All 287 findings across 68 files were fixed first (292 attributes added, 0 existing values renamed, so no e2e selector moved), then this switch came out. It stays OFF only for the test-files block, where testids are moot.
      'custom/no-duplicate-translation-props': 'off',
      'custom/no-hardcoded-nullish-defaults': 'off',
      'custom/prefer-const-arrays': 'off',
      // --- Import/syntax restrictions ---
      'no-restricted-imports': 'off',
      'no-restricted-syntax': ['error', {
        selector: "CallExpression[callee.property.name='transaction']",
        message: 'db.transaction() is not supported on D1. Use sequential awaited operations instead.',
      }],
      // import/order disabled globally (handled by Biome)
    },
  },

  // Account route layer isolation: prevent routes from accessing DB layer
  {
    files: ['private/account/src/routes/**/*.ts'],
    ignores: ['private/account/src/routes/test.ts'],
    rules: {
      'no-restricted-imports': ['error', {
        patterns: [{
          group: ['../db/*', '../db', 'drizzle-orm', 'drizzle-orm/*'],
          message: 'Routes cannot import from the database layer. Use services and DTO schemas.',
        }],
      }],
      'no-restricted-syntax': ['error',
        {
          selector: "CallExpression[callee.property.name='transaction']",
          message: 'db.transaction() is not supported on D1.',
        },
        {
          selector: "ImportExpression[source.value=/\\.\\.\\/(db|db\\/)/]",
          message: 'Dynamic imports from the database layer are not allowed in routes.',
        },
        {
          selector: "ImportExpression[source.value=/drizzle/]",
          message: 'Dynamic imports from drizzle-orm are not allowed in routes.',
        },
      ],
    },
  },

  // Account service scope enforcement is handled by: 1. scope-registry.ts (table classification) 2. scope-audit.test.ts (CI test verifying all tables are registered + have scope columns) 3. withOrg/withUser/withStore helpers in scoped-query.ts (runtime enforcement)
  // ESLint scope warnings removed to avoid --max-warnings 0 conflicts.
  // D1 transaction restriction is in the general account block above, the one
  // whose files: is ['private/account/**/*.{ts,tsx}'] (:30 in this module).
  // It used to say "line 909", which had already drifted to a line in the TEST FILE OVERRIDES banner long before this file was split out of the single config. A line number in a comment is a reference that rots silently, so this one names the block instead.

  // Account package: catch unawaited Drizzle terminators (.run/.get/.all/.values). Defence-in-depth backstop for the production-only D1 async footgun. The
  // shared Database type is now DrizzleD1Database (async); this rule fires for
  // any chain that drops the resulting Promise on the floor. db/index.ts is
  // ignored so the dbRun helper itself can call .run() internally; tests are
  // ignored so test-helper synchronous .run() calls (better-sqlite3 only) keep working.
  {
    files: ['private/account/src/**/*.ts'],
    ignores: ['private/account/src/db/index.ts'],
    rules: {
      'custom/no-unawaited-drizzle-terminator': 'error',
    },
  },

  // =============================================================
  // WWW PACKAGE OVERRIDES (Astro marketing site)
  // =============================================================
  // Disable web-specific rules for www package since it's an Astro site
  // with different translation patterns and no Ant Design components
  {
    files: ['packages/www/src/**/*.{ts,tsx}'],
    plugins: {
      'jsx-a11y': jsxA11y,
    },
    rules: {
      // Disable web-specific i18n rules (www uses different translation system)
      'custom/require-translation': 'off',
      'custom/no-hardcoded-text': 'off',
      // require-testid is ON here. Measured 2026-08-15: the rule reports ZERO findings across all 28 .tsx/.jsx files in this tree, so switching it on costs no cleanup and it starts actually protecting them. It stays off
      // for private/account/** (line ~1053) only until that tree's 287 findings
      // across 68 files are fixed; that is a separate, tracked sweep.
      // Disable Ant Design restrictions (www uses native HTML)
      'react/forbid-elements': 'off',
      'no-restricted-imports': 'off',
      // SEO: prevent non-descriptive anchor text
      'custom/seo-no-vague-anchor-text': 'error',
      // Accessibility: require alt text on images
      'jsx-a11y/alt-text': 'error',
      'custom/seo-require-img-alt': 'error',
      // SEO: prevent hash-fragment URLs in breadcrumbs (GSC rejects them)
      'custom/seo-no-hash-breadcrumb-url': 'error',
      // SEO: prevent trailing slashes on internal links (conflicts with trailingSlash: "never" in astro.config.mjs — Astro dev overlay errors and extra redirect hops in production)
      'custom/seo-no-trailing-slash-internal-link': 'error',
      // Ban positional CLI syntax in help text / error strings / JSX.
      'custom/no-positional-cli-syntax-source': 'error',
    },
  },

  // WWW analytics tracking enforcement
  {
    files: ['packages/www/src/**/*.{ts,tsx}'],
    rules: {
      'custom/require-data-track': ['error', {
        elements: ['a', 'button'],
        exemptParents: [
          'SearchModal',      // React events handle search tracking
          'LanguageMenu',     // React event handles language_change
          'Sidebar',          // Links tracked by pageview, toggle tracked by React
        ],
      }],
    },
  },

  // WWW translation JSON files - basic JSON linting + SEO validation
  {
    files: ['packages/www/src/i18n/translations/*.json'],
    // Hash sidecar files store key->hash maps (not real translations), so they must be excluded from translation/SEO content rules like the localized JSON.
    ignores: [
      'packages/www/src/i18n/translations/.translation-hashes.json',
      'packages/www/src/i18n/translations/.naturalized-hashes.json',
    ],
    plugins: {
      json,
      'i18n': i18nJsonPlugin,
    },
    language: 'json/json',
    rules: {
      'json/no-duplicate-keys': 'error',
      // see the banner at the top block: inert since birth, now OFF by choice
      'i18n/no-empty-translations': 'off',
      'i18n/sorted-keys': 'off',
      'i18n/seo-title-length': ['error', {
        minLength: 30,
        maxLength: 60,
        exemptKeys: ['notFound', 'checkout.success'],
      }],
      'i18n/seo-description-length': ['error', {
        minLength: 50,
        maxLength: 160,
        exemptKeys: ['checkout.success'],
      }],
      'i18n/seo-no-duplicate-h1-title': ['error', {
        brandSuffixes: [' | Rediacc', ' \u2014 Rediacc', ' - Rediacc'],
      }],
    },
  },

  // Tutorial transcript JSON files - translation parity checks
  {
    files: ['packages/www/src/data/tutorial-transcripts/*/*.json'],
    plugins: {
      json,
      'i18n': i18nJsonPlugin,
    },
    language: 'json/json',
    rules: {
      'json/no-duplicate-keys': 'error',
      'i18n/no-empty-translations': 'off',  // see the banner above
      'i18n/no-untranslated-tutorial-transcript-values': ['error', {
        transcriptsDir: 'packages/www/src/data/tutorial-transcripts',
        minLength: 3,
      }],
    },
  },

  // JSON package is bash-based, exclude from ESLint
  {
    ignores: ['packages/json/**'],
  },

  // CLI utility scripts - relaxed rules for command-line tools
  {
    files: ['scripts/**/*.ts'],
    rules: {
      // CLI scripts output to console by design
      'no-console': 'off',
      // Utility scripts can have complex logic
      'sonarjs/cognitive-complexity': 'off',
      // Top-level async calls are handled at script exit
      '@typescript-eslint/no-floating-promises': 'off',
      '@typescript-eslint/require-await': 'off',
      // Allow simple patterns in utility scripts
      'unicorn/prefer-number-properties': 'off',
      'unicorn/no-negated-condition': 'off',
      'no-nested-ternary': 'off',
      'prefer-template': 'off',
      'no-regex-spaces': 'off',
      // Custom rules not applicable to utility scripts
      'custom/prefer-const-arrays': 'off',
    },
  },
];
