import js from '@eslint/js';
import json from '@eslint/json';
import tseslint from 'typescript-eslint';
import reactPlugin from 'eslint-plugin-react';
import reactHooksPlugin from 'eslint-plugin-react-hooks';
import importPlugin from 'eslint-plugin-import';
import unicornPlugin from 'eslint-plugin-unicorn';
import sonarjsPlugin from 'eslint-plugin-sonarjs';
import regexpPlugin from 'eslint-plugin-regexp';
import playwrightPlugin from 'eslint-plugin-playwright';
import globals from 'globals';
import { requireTestId } from './eslint-rules/require-testid.js';
import { requireTranslation } from './eslint-rules/require-translation.js';
import { requireTranslationKeyArg } from './eslint-rules/require-translation-key-arg.js';
import { noHardcodedText } from './eslint-rules/no-hardcoded-text.js';
import { noHardcodedCliText } from './eslint-rules/no-hardcoded-cli-text.js';
import { requireCommandSummary } from './eslint-rules/require-command-summary.js';
import { noRawApiCalls } from './eslint-rules/no-raw-api-calls.js';
import { noDuplicateTranslationProps } from './eslint-rules/no-duplicate-translation-props.js';
import { preferConstArrays } from './eslint-rules/prefer-const-arrays.js';
import { noHardcodedNullishDefaults } from './eslint-rules/no-hardcoded-nullish-defaults.js';
import { noPositionalArguments } from './eslint-rules/no-positional-arguments.js';
import { noPositionalCliSyntaxSource } from './eslint-rules/no-positional-cli-syntax-source.js';
import { e2eTestNamingConvention } from './eslint-rules/e2e-test-naming-convention.js';
import { requireDataTrack } from './eslint-rules/require-data-track.js';
import { seoNoVagueAnchorText } from './eslint-rules/seo-no-vague-anchor-text.js';
import { seoRequireImgAlt } from './eslint-rules/seo-require-img-alt.js';
import { seoNoHashBreadcrumbUrl } from './eslint-rules/seo-no-hash-breadcrumb-url.js';
import { seoNoTrailingSlashInternalLink } from './eslint-rules/seo-no-trailing-slash-internal-link.js';
import { noUnawaitedDrizzleTerminator } from './eslint-rules/no-unawaited-drizzle-terminator.js';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import { i18nJsonPlugin, i18nSourcePlugin } from './eslint-rules/i18n/index.js';

// =============================================================
// i18n LOCALE CONFIG HELPER
// =============================================================
// Generates 3 ESLint config blocks for each package's locale directory:
//   1. JSON linting (all languages): sorted keys, camelCase naming, no duplicates/empty
//   2. English cross-language validation: consistency, coverage, staleness, unused keys
//   3. Non-English validation: untranslated values, interpolation consistency

const I18N_LANGUAGES = ['ar', 'de', 'es', 'fr', 'ja', 'ru', 'tr', 'zh'];

const UNTRANSLATED_BASE_PATTERNS = [
  '^[A-Z]{2,}$',
  '^https?://',
  '^/',
  '.*\\..*',
  '.*@.*',
  '.*:.*',
  '.*\\{\\{.*\\}\\}.*',
  '^[a-z]+\\s+[a-z]+$',
  '^-{1,2}[a-zA-Z]',
  '^[a-z][a-z0-9]*(-[a-z0-9]+)+$',
  '^\\d{2,5}$',
  '\\.(json|xml|txt|log|pem|key|crt)$',
  '^Edge$',
];

function i18nLocaleConfigs({
  localesDir,
  sourceDir,
  unusedKeyIgnores,
  extraUntranslatedPatterns = [],
  cliSyntax,
  cliFlags,
}) {
  const jsonBase = {
    plugins: { json, 'i18n': i18nJsonPlugin },
    language: 'json/json',
  };

  const configs = [
    // 1. JSON locale file linting (all languages)
    {
      files: [`${localesDir}/**/*.json`],
      ...jsonBase,
      rules: {
        'json/no-duplicate-keys': 'error',
        'i18n/no-empty-translations': 'error',
        'i18n/sorted-keys': 'error',
        'i18n/key-naming-convention': ['error', {
          keyFormat: 'camelCase',
          allowedPatterns: ['^[A-Z]$', '_one$', '_other$', '_zero$', '_few$', '_many$'],
        }],
        ...(cliSyntax ? { 'i18n/no-positional-cli-syntax': ['error', cliSyntax] } : {}),
        // Runs on EVERY language file (this block globs all of them, not just the
        // curated I18N_LANGUAGES set) so flag-name mangling is caught even in
        // locales like et/it/ko/pt that the heavier non-English block skips. The
        // rule self-guards the en source.
        ...(cliFlags ? { 'i18n/cli-flag-consistency': ['error', { localesDir }] } : {}),
      },
    },
    // 2. English cross-language validation
    {
      files: [`${localesDir}/en/**/*.json`],
      ...jsonBase,
      rules: {
        'i18n/cross-language-consistency': ['error', { localesDir, sourceLanguage: 'en' }],
        'i18n/translation-coverage': ['error', { localesDir, sourceLanguage: 'en', minimumCoverage: 100 }],
        'i18n/translation-staleness': ['error', { hashFileName: '.translation-hashes.json' }],
        ...(sourceDir && unusedKeyIgnores ? {
          'i18n/no-unused-keys': ['error', { sourceDir, ignorePatterns: unusedKeyIgnores }],
        } : {}),
        // Flags are language-invariant, so this only runs on the en source locale
        // (this block is scoped to `${localesDir}/en/**`). Avoids translation-only
        // false positives (e.g. Estonian case endings agglutinated onto flag names).
        ...(cliFlags ? { 'i18n/no-undefined-cli-flags': ['error', cliFlags] } : {}),
      },
    },
    // 3. Non-English locale validation
    {
      files: I18N_LANGUAGES.map(lang => `${localesDir}/${lang}/**/*.json`),
      ...jsonBase,
      rules: {
        'i18n/no-untranslated-values': ['error', {
          localesDir,
          minLength: 3,
          allowedPatterns: [...UNTRANSLATED_BASE_PATTERNS, ...extraUntranslatedPatterns],
        }],
        'i18n/interpolation-consistency': ['error', { localesDir }],
      },
    },
  ];

  return configs;
}

export default tseslint.config(
  // Ignore patterns
  {
    ignores: [
      'dist/',
      'packages/*/dist/',
      'packages/*/dist-typecheck/',
      'packages/*/node_modules/',
      'packages/*/bin/',
      'bin/',
      'cli/dist/',
      'node_modules/',
      '*.config.js',
      '*.config.ts',
      '*.config.cjs',
      'packages/web/postcss.config.cjs',
      'packages/web/tailwind.config.cjs',
      'packages/web/vite.config.ts',
      'packages/cli/bundle.mjs',
      // Ignore .d.ts files (generated type declarations)
      '**/*.d.ts',
      // Ignore generated JS companions for TypeScript source/test files
      'packages/*/src/**/*.js',
      'packages/*/src/**/*.js.map',
      'packages/*/tests/**/*.js',
      'packages/*/tests/**/*.js.map',
      // Ignore public config files
      'packages/web/public/**',
      // Ignore www public assets — the search-index-*.json files are large
      // generated artifacts that don't need linting and slow eslint to a crawl.
      'packages/www/public/**',
      // Ignore desktop build output
      'packages/desktop/out/**',
      // Ignore custom eslint rules (plain JS)
      'eslint-rules/**',
      // Ignore package-level scripts (plain JS utilities)
      'packages/*/scripts/**',
      // Ignore Playwright report artifacts (generated trace viewer files)
      'packages/e2e/reports/**',
      'packages/bridge-tests/reports/**',
      // Ignore private submodules except account (which has i18n enforcement)
      'private/!(account)/**',
      'private/account/node_modules/**',
      'private/account/web/node_modules/**',
      'private/account/dist/**',
      'private/account/web/dist/**',
      'private/account/e2e/**',
      // Account worker build artifacts (vite SPA bundles, served as Worker assets)
      'workers/account/dist/**',
      // Ignore Astro build artifacts
      'packages/www/.astro/**',
      // Ignore CI scripts (shell scripts linted by shellcheck, JS scripts are github-script glue)
      '.ci/**',
      // Ignore CLI template files (embedded into the CLI binary, not source code)
      'packages/cli/templates/**',
    ]
  },
  
  // Linter options - treat unused directive comments as errors to avoid pollution
  {
    linterOptions: {
      reportUnusedDisableDirectives: 'error',
    },
  },

  // Base JavaScript rules
  js.configs.recommended,
  
  // TypeScript rules
  ...tseslint.configs.recommended,

  // =============================================================
  // SCRIPTS - TypeScript utility scripts
  // =============================================================
  // Scripts are parsed with TypeScript parser via allowDefaultProject
  {
    files: ['scripts/**/*.ts'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.node,
        ...globals.es2021,
      }
    },
    rules: {
      // CLI scripts output to console by design
      'no-console': 'off',
      // Utility scripts can have complex logic
      'sonarjs/cognitive-complexity': 'off',
      // Allow simple patterns in utility scripts
      'unicorn/prefer-number-properties': 'off',
      'unicorn/no-negated-condition': 'off',
      'no-nested-ternary': 'off',
      'prefer-template': 'off',
      'no-regex-spaces': 'off',
    }
  },

  // React plugin configuration
  {
    files: ['**/*.{js,jsx,ts,tsx}'],
    ignores: ['scripts/**/*.ts'],
    plugins: {
      react: reactPlugin,
      'react-hooks': reactHooksPlugin,
      import: importPlugin,
      unicorn: unicornPlugin,
      sonarjs: sonarjsPlugin,
      regexp: regexpPlugin,
      'custom': {
        rules: {
          'require-testid': requireTestId,
          'require-translation': requireTranslation,
          'require-translation-key-arg': requireTranslationKeyArg,
          'no-hardcoded-text': noHardcodedText,
          'no-hardcoded-cli-text': noHardcodedCliText,
          'require-command-summary': requireCommandSummary,
          'no-raw-api-calls': noRawApiCalls,
          'no-duplicate-translation-props': noDuplicateTranslationProps,
          'prefer-const-arrays': preferConstArrays,
          'no-hardcoded-nullish-defaults': noHardcodedNullishDefaults,
          'e2e-test-naming-convention': e2eTestNamingConvention,
          'require-data-track': requireDataTrack,
          'no-positional-arguments': noPositionalArguments,
          'no-positional-cli-syntax-source': noPositionalCliSyntaxSource,
          'seo-no-vague-anchor-text': seoNoVagueAnchorText,
          'seo-require-img-alt': seoRequireImgAlt,
          'seo-no-hash-breadcrumb-url': seoNoHashBreadcrumbUrl,
          'seo-no-trailing-slash-internal-link': seoNoTrailingSlashInternalLink,
          'no-unawaited-drizzle-terminator': noUnawaitedDrizzleTerminator,
        },
      },
    },
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parser: tseslint.parser,
      parserOptions: {
        ecmaFeatures: {
          jsx: true
        },
        projectService: {
          allowDefaultProject: [
            'scripts/*.ts',
            'scripts/utils/*.ts',
            'packages/desktop/electron.vite.config.js',
          ],
          maximumDefaultProjectFileMatchCount_THIS_WILL_SLOW_DOWN_LINTING: 12,
        },
        tsconfigRootDir: import.meta.dirname,
      },
      globals: {
        ...globals.browser,
        ...globals.es2021,
        ...globals.node,
      }
    },
    settings: {
      react: {
        version: 'detect'
      },
      'import/resolver': {
        typescript: {
          project: [
            'packages/web/tsconfig.json',
            'packages/shared/tsconfig.json',
            'packages/cli/tsconfig.json',
            'packages/cli/tests/tsconfig.json',
            'packages/e2e/tsconfig.json',
          ],
          // Suppress warning about multiple tsconfig files (expected in monorepo)
          noWarnOnMultipleProjects: true,
        },
      },
    },
    rules: {
      // React rules
      ...reactPlugin.configs.recommended.rules,
      'react/react-in-jsx-scope': 'off',
      'react/prop-types': 'off',
      
      // React Hooks rules
      ...reactHooksPlugin.configs.recommended.rules,
      
      // TypeScript rules
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-inferrable-types': ['error', {
        ignoreParameters: false,
        ignoreProperties: false,
      }],
      // STRICT: No underscore prefix allowed - if unused, delete it
      // Only exception: function parameters required by interfaces (use _ prefix for those)
      '@typescript-eslint/no-unused-vars': ['error', {
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^$' // Empty pattern = no variables allowed with underscore
      }],
      '@typescript-eslint/no-empty-interface': 'off',
      '@typescript-eslint/no-empty-object-type': 'off',
      '@typescript-eslint/no-deprecated': 'error',
      
      // General rules
      'no-console': ['error', { allow: ['warn', 'error'] }],
      'no-debugger': 'error',
      'max-lines': ['error', { max: 512, skipBlankLines: true, skipComments: true }],

      // === TypeScript Strict Rules (Bug Prevention) ===
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/await-thenable': 'error',
      '@typescript-eslint/no-misused-promises': ['error', { checksVoidReturn: false }],
      '@typescript-eslint/no-unnecessary-type-assertion': 'error',
      '@typescript-eslint/no-unnecessary-condition': 'error',
      '@typescript-eslint/require-await': 'error',
      '@typescript-eslint/use-unknown-in-catch-callback-variable': 'error',

      // === TypeScript Stylistic Rules (Modern Patterns) ===
      '@typescript-eslint/prefer-nullish-coalescing': 'error',
      '@typescript-eslint/prefer-optional-chain': 'error',
      '@typescript-eslint/prefer-includes': 'error',
      '@typescript-eslint/prefer-for-of': 'error',
      '@typescript-eslint/prefer-string-starts-ends-with': 'error',
      '@typescript-eslint/array-type': ['error', { default: 'array' }],
      '@typescript-eslint/consistent-type-assertions': ['error', {
        assertionStyle: 'as',
        objectLiteralTypeAssertions: 'allow-as-parameter'
      }],

      // === Translation Prop Rules ===
      // Prevent multiple TypedTFunction props - use single t with namespace prefixes
      'custom/no-duplicate-translation-props': 'error',

      // === Type Safety Rules ===
      // Enforce `as const` on UPPER_SNAKE_CASE constant arrays for narrow literal types
      'custom/prefer-const-arrays': 'error',

      // === Centralized Defaults Rule ===
      // Disallow hardcoded numbers and strings in nullish coalescing - use DEFAULTS from @rediacc/shared/config
      'custom/no-hardcoded-nullish-defaults': ['error', {
        allowZero: true,
        allowNegativeOne: true,
        // Allow 1 for vault version initialization
        allowedNumbers: [1],
        // Allow common acceptable string patterns
        allowedStrings: [
          '',             // Empty string clearing
          'file-based',   // SSH connection method enum
          '-',            // Table cell placeholder for empty values
          '\u2014',        // Em-dash placeholder for empty values
          'N/A',          // Not applicable placeholder
          'none',         // No value placeholder
          '!',            // Test reporter symbols
          '{}',           // Empty JSON object for vault defaults
          '[]',           // Empty JSON array
          'default',      // CLI context default name
          '(none)',       // Display placeholder
          'terminal',     // Default container action
          // Health status messages (non-i18n context in shared package)
          'System has critical issues',
        ],
      }],

      // === E2E Testing Rules ===
      // Enforce data-testid on interactive elements for E2E test coverage
      // This is strict (error) to ensure all interactive elements have testids
      'custom/require-testid': ['error', {
        requiredElements: ['Modal', 'Drawer'],
        interactiveElements: ['Button'],
        // All Ant Design data entry components (https://ant.design/components/overview)
        formElements: [
          // Input variants
          'Input', 'Input.Password', 'Input.Search', 'Input.TextArea', 'Input.OTP',
          // Selection components
          'Select', 'Select.Option', 'Checkbox', 'Checkbox.Group',
          'Radio', 'Radio.Group', 'Radio.Button', 'Switch',
          // Upload
          'Upload', 'Upload.Dragger',
          // Numeric inputs
          'InputNumber', 'Slider', 'Rate',
          // Date/Time pickers
          'DatePicker', 'DatePicker.RangePicker', 'RangePicker', 'TimePicker', 'TimePicker.RangePicker',
          // Advanced selectors
          'AutoComplete', 'Cascader', 'TreeSelect', 'Transfer', 'Mentions',
          // Other
          'ColorPicker',
        ],
        allowTemplateLiterals: true,
      }],
      // === React Rules (Quality & Consistency) ===
      'react/hook-use-state': 'error',
      'react/button-has-type': 'error',
      'react/jsx-no-useless-fragment': ['error', { allowExpressions: true }],
      'react/self-closing-comp': 'error',
      'react/jsx-boolean-value': ['error', 'never'],
      'react/jsx-curly-brace-presence': ['error', {
        props: 'never',
        children: 'never',
        propElementValues: 'always'
      }],

      // === Core ESLint Rules (JavaScript Quality) ===
      'eqeqeq': ['error', 'always', { null: 'ignore' }],
      'prefer-const': 'error',
      'no-var': 'error',
      'object-shorthand': ['error', 'always'],
      'prefer-template': 'error',
      'prefer-arrow-callback': 'error',
      'no-else-return': 'error',
      'no-lonely-if': 'error',
      'no-implicit-coercion': ['error', { allow: ['!!'] }],

      // === SonarQube Parity Rules (with stricter limits) ===

      // CRITICAL - Cognitive Complexity (SonarQube S3776 default is 15, we use 10 for stricter enforcement)
      'sonarjs/cognitive-complexity': ['error', 10],

      // CRITICAL - Nested callbacks (SonarQube S2004 default is 4, we use 3 for stricter enforcement)
      'max-nested-callbacks': ['error', 3],

      // CRITICAL - Sort without compare function (SonarQube S2871)
      '@typescript-eslint/require-array-sort-compare': 'error',

      // MAJOR - Prefer readonly class members (SonarQube S2933)
      '@typescript-eslint/prefer-readonly': 'error',

      // MAJOR - No nested ternary operators (SonarQube S3358)
      'no-nested-ternary': 'error',

      // MAJOR - Regex best practices (SonarQube S5850)
      'regexp/strict': 'error',

      // MINOR - Modern JS patterns (unicorn plugin)
      'unicorn/prefer-node-protocol': 'error',        // S7772: prefer node: imports
      'unicorn/prefer-number-properties': 'error',    // S7773: Number.parseInt
      'unicorn/prefer-string-replace-all': 'error',   // S7781: String.replaceAll
      'unicorn/no-array-push-push': 'error',          // S7778: batch Array.push
      'unicorn/no-negated-condition': 'error',        // S7735: avoid negated conditions

      // MINOR - TypeScript patterns (already installed)
      '@typescript-eslint/prefer-regexp-exec': 'error',           // S6594: RegExp.exec
      '@typescript-eslint/no-redundant-type-constituents': 'error', // S6571: unknown in union

      // Import ordering is handled by Biome (organizeImports in biome.json).
      // Do not add import/order here — it conflicts with Biome's formatter.

      // Ban styled-components and Layout to enforce Ant Design best practices
      // Ban deprecated type utilities to prevent hopping type patterns
      'no-restricted-imports': ['error', {
        paths: [
          { name: 'styled-components', message: 'Use Ant Design components with CSS utility classes (className) instead.' },
          {
            name: 'antd',
            importNames: ['Layout'],
            message: 'Layout has default grey/dark backgrounds. Use Flex component instead.',
          },
          {
            name: '@rediacc/shared/types',
            importNames: ['WithOptionalVault'],
            message: 'WithOptionalVault is deprecated. vaultContent and vaultVersion are now optional with SQL defaults in generated types. Use CreateXxxParams directly.',
          },
        ],
        patterns: [
          { group: ['styled-components/*'], message: 'Use Ant Design components instead.' },
          { group: ['antd/es/layout', 'antd/es/layout/*', 'antd/lib/layout', 'antd/lib/layout/*'], message: 'Layout has default grey/dark backgrounds. Use Flex component instead.' },
        ],
      }],

      // Ban raw HTML elements to enforce Ant Design component usage
      'react/forbid-elements': ['error', {
        forbid: [
          { element: 'div', message: 'Use Flex, Card, or other antd layout components.' },
          { element: 'span', message: 'Use Typography.Text.' },
          { element: 'button', message: 'Use antd Button component.' },
          { element: 'input', message: 'Use antd Input component.' },
          { element: 'select', message: 'Use antd Select component.' },
        ],
      }],

      // Ban local aliases of constants and CSS variables
      'no-restricted-syntax': ['error',
        {
          selector: "VariableDeclarator[init.type='MemberExpression'][init.computed=false][init.object.name=/^[A-Z][A-Z_0-9]*$/]",
          message: 'Do not create local aliases from constants. Use the original property access directly (e.g., LAYOUT.HEADER_HEIGHT instead of const X = LAYOUT.X).',
        },
        {
          selector: "Literal[value=/var\\(--ant-/]",
          message: 'Do not use CSS variables (var(--ant-*)). Remove color styling or use Ant Design component props.',
        },
        {
          selector: "CallExpression[callee.name=/^t$|^tSystem$|^tCommon$/] ObjectExpression Property[key.name='defaultValue']",
          message: 'Do not use defaultValue in translation calls. Add the key to English translation JSON files instead.',
        },
        {
          selector: 'JSXAttribute[name.name=/^styles?$/]',
          message: 'Inline styles are not allowed. Use CSS utility classes from global.css or Ant Design component props instead. For dynamic styles, use // eslint-disable-next-line no-restricted-syntax',
        },
        {
          selector: "ExportNamedDeclaration > TSTypeAliasDeclaration:not([typeParameters]) > TSTypeAnnotation > TSTypeReference",
          message: 'Do not create type aliases. Use the original type directly instead of creating an alias.',
        },
      ],
    }
  },

  // Web UI i18n enforcement
  {
    files: ['packages/web/src/**/*.{js,jsx,ts,tsx}'],
    ignores: ['packages/web/src/**/__tests__/**'],
    plugins: {
      'i18n-source': i18nSourcePlugin,
    },
    rules: {
      'custom/require-translation': ['error', {
        localeDir: 'packages/web/src/i18n/locales/en',
      }],
      'custom/no-hardcoded-text': ['error'],
      'i18n-source/interpolation-match': ['error', {
        localeDir: 'packages/web/src/i18n/locales/en',
      }],
      // Enforce type-safe API calls - use typedApi instead of raw apiClient methods
      'custom/no-raw-api-calls': 'error',
    }
  },

  // CLI i18n enforcement
  {
    files: ['packages/cli/src/**/*.{js,ts}'],
    ignores: ['packages/cli/src/__tests__/**'],
    plugins: {
      'i18n-source': i18nSourcePlugin,
    },
    rules: {
      // Ban positional arguments -- enforce named options in Commander.js commands
      'custom/no-positional-arguments': ['error', {
        exemptFiles: [
          // Experimental cloud-only commands
          'packages/cli/src/commands/auth.ts',
          'packages/cli/src/commands/audit.ts',
          'packages/cli/src/commands/bridge.ts',
          'packages/cli/src/commands/organization.ts',
          'packages/cli/src/commands/permission.ts',
          'packages/cli/src/commands/protocol.ts',
          'packages/cli/src/commands/queue.ts',
          'packages/cli/src/commands/region.ts',
          'packages/cli/src/commands/repository.ts',
          'packages/cli/src/commands/team.ts',
          'packages/cli/src/commands/user.ts',
          'packages/cli/src/commands/ceph/**',
        ],
      }],
      // Enforce t() for CLI-specific patterns
      'custom/no-hardcoded-cli-text': ['error'],
      'custom/require-command-summary': ['error', {
        excludeFromMinDescription: [
          'auth', 'audit', 'bridge', 'ceph', 'organization', 'permission',
          'protocol', 'queue', 'region', 'repository', 'team', 'user', 'snapshot',
        ],
      }],
      // Enforce translation keys exist in locale files
      'custom/require-translation': ['error', {
        localeDir: 'packages/cli/src/i18n/locales/en',
      }],
      // Validate string literals passed to indirect translation-key helpers
      // (e.g., errorResult('commands.update.errors.lockFailed')) against the
      // locale dir. Prevents raw-key leaks where the string bypasses t() and
      // is later interpolated into a translated template.
      'custom/require-translation-key-arg': ['error', {
        localeDir: 'packages/cli/src/i18n/locales/en',
        functions: [
          { name: 'errorResult', argIndex: 0 },
        ],
      }],
      'i18n-source/interpolation-match': ['error', {
        localeDir: 'packages/cli/src/i18n/locales/en',
      }],
      // Enforce type-safe API calls - use typedApi instead of raw apiClient methods
      'custom/no-raw-api-calls': 'error',
      // Ban positional CLI syntax in help text / error strings / JSX.
      // Mirrors custom/i18n/no-positional-cli-syntax but for source strings.
      'custom/no-positional-cli-syntax-source': 'error',
    }
  },

  // Account Web UI i18n enforcement
  {
    files: ['private/account/web/src/**/*.{ts,tsx}'],
    ignores: [
      'private/account/web/src/**/__tests__/**',
      // shadcn/ui primitives contain only Tailwind CSS classes, not user-facing text
      'private/account/web/src/components/ui/**',
    ],
    plugins: {
      'i18n-source': i18nSourcePlugin,
    },
    rules: {
      'custom/require-translation': ['error', {
        localeDir: 'private/account/web/src/i18n/locales/en',
      }],
      'custom/no-hardcoded-text': ['error'],
      'i18n-source/interpolation-match': ['error', {
        localeDir: 'private/account/web/src/i18n/locales/en',
      }],
      'custom/no-positional-cli-syntax-source': 'error',
    }
  },

  // =============================================================
  // i18n JSON LOCALE RULES (shared across all packages)
  // =============================================================
  // Each package gets 3 config blocks generated by i18nLocaleConfigs():
  //   1. JSON linting (all languages): sorted keys, camelCase, no duplicates
  //   2. English cross-language validation: consistency, coverage, staleness, unused keys
  //   3. Non-English validation: untranslated values, interpolation consistency
  ...i18nLocaleConfigs({
    localesDir: 'packages/web/src/i18n/locales',
    sourceDir: 'packages/web/src',
    unusedKeyIgnores: ['^errors\\.', '^messages\\.', '^validation\\.'],
    extraUntranslatedPatterns: [
      '^[a-zA-Z0-9!]+$',
      '^[A-Za-z]+\\d+$',
      '^(my|your|example|sample|test)-',
    ],
  }),
  ...i18nLocaleConfigs({
    localesDir: 'packages/cli/src/i18n/locales',
    sourceDir: 'packages/cli/src',
    unusedKeyIgnores: ['^errors\\.', '^spinners\\.', '^prompts\\.', '^status\\.'],
    extraUntranslatedPatterns: [
      '^[A-Za-z]+\\d+$',
      '^(Docker|Renet|Go|Node\\.js|Status|Version|Machines|Configuration)$',
      '^rdc\\s',
      '^(Installation|Description|Note|Error|Reference|Infrastructure)$',
      // Command CRUD descriptions (machine/storage vault, rename, create, delete)
      '^(Rename|Create|Delete|Show)\\s',
      'vault management',
      'vault status',
      'dedicated TLS cert',
      'Generate command reference',
      '^Activation failed$',
    ],
    // Ban documentation/help strings that teach positional syntax for
    // commands that actually require named options (see issue #446).
    // Complements custom/no-positional-arguments which enforces the
    // Commander API side in source files.
    //
    // autoDerive reads packages/cli/scripts/command-tree.json and builds
    // the denylist from every leaf command with zero positional arguments.
    // Keeps the rule in sync with Commander source with zero hand-editing.
    cliSyntax: {
      autoDerive: true,
      // Legacy / cloud-adapter command groups that use positional
      // subcommands legitimately. Skips a line if its trimmed start
      // matches any prefix.
      exemptCommandPrefixes: [
        'rdc auth', 'rdc audit', 'rdc bridge', 'rdc organization',
        'rdc permission', 'rdc protocol', 'rdc queue', 'rdc region',
        'rdc repository', 'rdc team', 'rdc user', 'rdc ceph',
      ],
    },
    // Ban help/description prose that references a `--flag` not registered on any
    // rdc command (see issue #489 — `repo up --mount` did not exist). Derives the
    // valid-flag set from packages/cli/scripts/command-tree.json. en-only (see the
    // rule wiring above).
    cliFlags: {
      exemptFlags: [],
      exemptKeyPrefixes: [],
    },
  }),
  ...i18nLocaleConfigs({
    localesDir: 'private/account/web/src/i18n/locales',
    sourceDir: 'private/account/web/src',
    unusedKeyIgnores: ['^errors\\.', '^validation\\.'],
    extraUntranslatedPatterns: [
      '^[A-Za-z]+\\d+$',
      // Brand and product names (exact match)
      '^(Rediacc|Stripe|Docker|rdc|rediacc)$',
      // Strings ending with the brand (e.g. signoffs like "— Rediacc")
      'Rediacc$',
      // CLI commands (rdc ...) must not be translated
      '^rdc\\s',
      // Code comment markers
      '^#\\s',
      // Universal abbreviations and tech terms kept in English across all languages
      '^N/A$',
      '^Sandbox$',
      '^S3 ID$',
      // Plan tier proper names (product names used as-is internationally)
      '^(Business|Community|Enterprise|Professional)$',
      // Words that are legitimately identical in many target languages
      // (borrowed/shared vocabulary across European languages and international tech terms)
      '^(Plan|Type|Newsletter|Name|Limit|Source|Admin|Total|Team|Status|Magnet|Machines|Code|Permissions|General|Description|Date|Dashboard|Contact|Activations|Actions)$',
    ],
    cliSyntax: {
      autoDerive: true,
      exemptCommandPrefixes: [
        'rdc auth', 'rdc audit', 'rdc bridge', 'rdc organization',
        'rdc permission', 'rdc protocol', 'rdc queue', 'rdc region',
        'rdc repository', 'rdc team', 'rdc user', 'rdc ceph',
      ],
    },
  }),
  ...i18nLocaleConfigs({
    localesDir: 'private/account/src/i18n/locales',
    extraUntranslatedPatterns: [
      '^(Rediacc|Stripe|rediacc)$',
      // Strings ending with the brand (e.g. "— Rediacc" signoff used across all languages)
      'Rediacc$',
      // CLI commands must not be translated
      '^rdc\\s',
      // Labels that are legitimately the same in some target languages
      '^(Name|Source|Status)$',
    ],
  }),

  // Disable JS/TS rules for JSON files (they inherit from base config)
  {
    files: ['**/*.json'],
    rules: {
      // Turn off all inherited rules that don't apply to JSON
      'no-irregular-whitespace': 'off',
      'no-unused-vars': 'off',
      'no-unused-expressions': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      '@typescript-eslint/no-unused-expressions': 'off',
      '@typescript-eslint/no-explicit-any': 'off',
    },
  },

  {
    files: ['private/account/src/services/email.service.ts'],
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector:
            "CallExpression[callee.property.name='sendEmail'] > Literal:nth-child(n+2)",
          message:
            'Do not hardcode email copy in EmailService. Render subject/html/text via translated email templates.',
        },
        {
          selector:
            "CallExpression[callee.property.name='sendEmail'] > TemplateLiteral:nth-child(n+2)",
          message:
            'Do not hardcode email copy in EmailService. Render subject/html/text via translated email templates.',
        },
      ],
    },
  },

  // Disable rules for auto-generated files
  {
    files: ['**/*.generated.ts', '**/*.generated.tsx', '**/api-schema.zod.ts'],
    rules: {
      'max-lines': 'off',
      '@typescript-eslint/no-unnecessary-condition': 'off',
      '@typescript-eslint/no-unnecessary-type-assertion': 'off',
      '@typescript-eslint/prefer-nullish-coalescing': 'off',
      '@typescript-eslint/prefer-optional-chain': 'off',
      '@typescript-eslint/array-type': 'off',
      '@typescript-eslint/consistent-type-assertions': 'off',
      '@typescript-eslint/no-deprecated': 'off',
      'custom/no-hardcoded-nullish-defaults': 'off',
    }
  },

  // =============================================================
  // TEST FILE OVERRIDES
  // =============================================================
  // These patterns cover ALL test file locations:
  // - E2E tests: packages/e2e/**
  // - Bridge tests: packages/bridge-tests/**
  // - CLI Playwright: packages/cli/tests/**
  // - CLI Unit tests: packages/cli/src/__tests__/**
  // - Web Vitest: packages/web/src/**/__tests__/**
  // - Shared: packages/shared/src/**/__tests__/**
  // =============================================================
  {
    files: [
      // Playwright/E2E test files
      'packages/e2e/**/*.ts',
      'packages/bridge-tests/**/*.ts',
      'packages/cli/tests/**/*.ts',
      // Unit test files (__tests__ convention)
      'packages/web/src/**/__tests__/**/*.{ts,tsx}',
      'packages/shared/src/**/__tests__/**/*.{ts,tsx}',
      'packages/cli/src/**/__tests__/**/*.ts',
    ],
    ignores: [
      // Has legitimate waitForTimeout for exponential backoff retry logic
      'packages/e2e/src/base/BasePage.ts',
    ],
    plugins: {
      playwright: playwrightPlugin,
    },
    rules: {
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
      // E2E: real tests with missing assertions (need proper fix)
      'packages/e2e/tests/01-auth/01-01-registration.test.ts',
      'packages/e2e/tests/01-auth/01-02-login.test.ts',
      // E2E: scattered stubs in mixed directories
      'packages/e2e/tests/02-organization/01-users/02-01-02-user-permissions.test.ts',
      'packages/e2e/tests/02-organization/02-teams/02-02-02-team-edit.test.ts',
      'packages/e2e/tests/03-machines/02-04-02-connectivity-test.test.ts',
      'packages/e2e/tests/03-machines/02-04-03-machine-refresh.test.ts',
      'packages/e2e/tests/03-machines/02-04-05-machine-edit.test.ts',
      // E2E: entire directories that are stubs
      'packages/e2e/tests/04-repositories/**/*.ts',
      'packages/e2e/tests/05-connection/**/*.ts',
      'packages/e2e/tests/06-settings/**/*.ts',
      'packages/e2e/tests/07-storage/**/*.ts',
      'packages/e2e/tests/08-credentials/**/*.ts',
      'packages/e2e/tests/09-queue/**/*.ts',
      'packages/e2e/tests/10-audit/**/*.ts',
      // Bridge: tests with setup/cleanup steps lacking assertions
      'packages/bridge-tests/tests/12a-full-integration-repository.test.ts',
      'packages/bridge-tests/tests/13-postgres-fork-isolation.test.ts',
      'packages/bridge-tests/tests/18-ops-workflow.test.ts',
      // CLI: tests with missing assertions
      'packages/cli/tests/tests/03-operations/04-shortcuts.test.ts',
      'packages/cli/tests/tests/08-e2e/01-local-execution.test.ts',
    ],
    rules: {
      'playwright/expect-expect': 'off',
    },
  },

  // =============================================================
  // WEB PACKAGE UNIT TESTS - STRICT NO SKIP POLICY
  // =============================================================
  // Vitest unit tests should never be skipped - fix them
  {
    files: [
      'packages/web/src/**/__tests__/**/*.{ts,tsx}',
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

  // =============================================================
  // E2E TEST FILE NAMING CONVENTION
  // =============================================================
  // Enforce doc-aligned naming pattern: {XX}-{YY}[-{ZZ}]-{feature-name}[.negative].test.ts
  {
    files: ['packages/e2e/tests/**/*.test.ts'],
    rules: {
      'custom/e2e-test-naming-convention': ['error', {
        excludeDirs: ['helpers', 'setup', 'electron'],
      }],
    },
  },

  // =============================================================
  // ACCOUNT PACKAGE OVERRIDES (private/account)
  // =============================================================
  // Disable ALL inherited rules for account package. Account only
  // uses ESLint for i18n enforcement (require-translation,
  // no-hardcoded-text, interpolation-match) via dedicated config
  // blocks above. Other code quality is handled by Biome + tsc.
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
      // --- Custom rules (packages/web specific) ---
      'custom/require-testid': 'off',
      'custom/no-raw-api-calls': 'off',
      'custom/no-duplicate-translation-props': 'off',
      'custom/no-hardcoded-nullish-defaults': 'off',
      'custom/prefer-const-arrays': 'off',
      // --- Import/syntax restrictions (packages/web specific) ---
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

  // Account service scope enforcement is handled by:
  // 1. scope-registry.ts (table classification)
  // 2. scope-audit.test.ts (CI test verifying all tables are registered + have scope columns)
  // 3. withOrg/withUser/withStore helpers in scoped-query.ts (runtime enforcement)
  // ESLint scope warnings removed to avoid --max-warnings 0 conflicts.
  // D1 transaction restriction is in the general account block above (line 909).

  // Account package: catch unawaited Drizzle terminators (.run/.get/.all/.values).
  // Defence-in-depth backstop for the production-only D1 async footgun. The
  // shared Database type is now DrizzleD1Database (async); this rule fires for
  // any chain that drops the resulting Promise on the floor. db/index.ts is
  // ignored so the dbRun helper itself can call .run() internally; tests are
  // ignored so test-helper synchronous .run() calls (better-sqlite3 only) keep
  // working.
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
      'custom/require-testid': 'off',
      'custom/no-raw-api-calls': 'off',
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
      // SEO: prevent trailing slashes on internal links (conflicts with
      // trailingSlash: "never" in astro.config.mjs — Astro dev overlay errors
      // and extra redirect hops in production)
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
    ignores: ['packages/www/src/i18n/translations/.translation-hashes.json'],
    plugins: {
      json,
      'i18n': i18nJsonPlugin,
    },
    language: 'json/json',
    rules: {
      'json/no-duplicate-keys': 'error',
      'i18n/no-empty-translations': 'error',
      'i18n/sorted-keys': 'error',
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
      'i18n/no-empty-translations': 'error',
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

);
