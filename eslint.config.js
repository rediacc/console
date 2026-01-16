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
import { noHardcodedText } from './eslint-rules/no-hardcoded-text.js';
import { noHardcodedCliText } from './eslint-rules/no-hardcoded-cli-text.js';
import { noRawApiCalls } from './eslint-rules/no-raw-api-calls.js';
import { noDuplicateTranslationProps } from './eslint-rules/no-duplicate-translation-props.js';
import { preferConstArrays } from './eslint-rules/prefer-const-arrays.js';
import { noHardcodedNullishDefaults } from './eslint-rules/no-hardcoded-nullish-defaults.js';
import { i18nJsonPlugin, i18nSourcePlugin } from './eslint-rules/i18n/index.js';

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
      'packages/web/vite.config.ts',
      'packages/cli/bundle.mjs',
      // Ignore .d.ts files (generated type declarations)
      '**/*.d.ts',
      // Ignore public config files
      'packages/web/public/**',
      // Ignore desktop build output
      'packages/desktop/out/**',
      // Ignore custom eslint rules (plain JS)
      'eslint-rules/**',
      // Ignore scripts directories (plain JS utilities)
      'scripts/**',
      'packages/*/scripts/**',
      // Ignore Playwright report artifacts (generated trace viewer files)
      'packages/e2e/reports/**',
      'packages/bridge-tests/reports/**',
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
  
  // React plugin configuration
  {
    files: ['**/*.{js,jsx,ts,tsx}'],
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
          'no-hardcoded-text': noHardcodedText,
          'no-hardcoded-cli-text': noHardcodedCliText,
          'no-raw-api-calls': noRawApiCalls,
          'no-duplicate-translation-props': noDuplicateTranslationProps,
          'prefer-const-arrays': preferConstArrays,
          'no-hardcoded-nullish-defaults': noHardcodedNullishDefaults,
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
        projectService: true,
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

      // Import rules - enforce consistent import paths
      // Note: no-relative-parent-imports is not used because @/ aliases resolve to parent
      // directories and the rule cannot distinguish between ../foo and @/foo patterns.
      // All parent imports have been converted to use @/ alias which is the desired pattern.
      'import/order': ['error', {
        groups: [
          'builtin',
          'external',
          'internal',
          ['parent', 'sibling', 'index'],
          'type',
        ],
        pathGroups: [
          { pattern: 'react', group: 'builtin', position: 'before' },
          { pattern: '@/**', group: 'internal', position: 'before' },
          { pattern: '@rediacc/shared/**', group: 'internal', position: 'before' },
        ],
        pathGroupsExcludedImportTypes: ['react'],
        'newlines-between': 'never',
        alphabetize: { order: 'asc', caseInsensitive: true },
      }],

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
      // Enforce t() for CLI-specific patterns
      'custom/no-hardcoded-cli-text': ['error'],
      // Enforce translation keys exist in locale files
      'custom/require-translation': ['error', {
        localeDir: 'packages/cli/src/i18n/locales/en',
      }],
      'i18n-source/interpolation-match': ['error', {
        localeDir: 'packages/cli/src/i18n/locales/en',
      }],
      // Enforce type-safe API calls - use typedApi instead of raw apiClient methods
      'custom/no-raw-api-calls': 'error',
    }
  },

  // JSON locale file linting (all languages) - Web
  {
    files: ['packages/web/src/i18n/locales/**/*.json'],
    plugins: {
      json,
      'i18n': i18nJsonPlugin,
    },
    language: 'json/json',
    rules: {
      // JSON-specific rules
      'json/no-duplicate-keys': 'error',
      'i18n/no-empty-translations': 'error',
      'i18n/sorted-keys': 'error',
      'i18n/key-naming-convention': ['error', {
        keyFormat: 'camelCase',
        allowedPatterns: [
          // Allow single uppercase letters (common for status codes)
          '^[A-Z]$',
          // Allow pluralization suffixes like _one, _other
          '_one$', '_other$', '_zero$', '_few$', '_many$',
        ],
      }],
    },
  },

  // JSON locale file linting (all languages) - CLI
  {
    files: ['packages/cli/src/i18n/locales/**/*.json'],
    plugins: {
      json,
      'i18n': i18nJsonPlugin,
    },
    language: 'json/json',
    rules: {
      // JSON-specific rules
      'json/no-duplicate-keys': 'error',
      'i18n/no-empty-translations': 'error',
      'i18n/sorted-keys': 'error',
      'i18n/key-naming-convention': ['error', {
        keyFormat: 'camelCase',
        allowedPatterns: [
          // Allow single uppercase letters (common for status codes)
          '^[A-Z]$',
          // Allow pluralization suffixes like _one, _other
          '_one$', '_other$', '_zero$', '_few$', '_many$',
        ],
      }],
    },
  },

  // English locale files only - cross-language validation (Web)
  {
    files: ['packages/web/src/i18n/locales/en/**/*.json'],
    plugins: {
      json,
      'i18n': i18nJsonPlugin,
    },
    language: 'json/json',
    rules: {
      // Cross-language consistency - ensure all languages have same keys
      'i18n/cross-language-consistency': ['error', {
        localesDir: 'packages/web/src/i18n/locales',
        sourceLanguage: 'en',
      }],
      // Translation coverage - ensure minimum coverage threshold
      'i18n/translation-coverage': ['error', {
        localesDir: 'packages/web/src/i18n/locales',
        sourceLanguage: 'en',
        minimumCoverage: 100,
      }],
      // Unused keys detection - find keys not used in source code
      'i18n/no-unused-keys': ['error', {
        sourceDir: 'packages/web/src',
        ignorePatterns: [
          // Ignore keys that might be used dynamically
          '^errors\\.',
          '^messages\\.',
          '^validation\\.',
        ],
      }],
      // Translation staleness - detect when English values change
      'i18n/translation-staleness': ['error', {
        hashFileName: '.translation-hashes.json',
      }],
    },
  },

  // English locale files only - cross-language validation (CLI)
  {
    files: ['packages/cli/src/i18n/locales/en/**/*.json'],
    plugins: {
      json,
      'i18n': i18nJsonPlugin,
    },
    language: 'json/json',
    rules: {
      // Cross-language consistency - ensure all languages have same keys
      'i18n/cross-language-consistency': ['error', {
        localesDir: 'packages/cli/src/i18n/locales',
        sourceLanguage: 'en',
      }],
      // Translation coverage - ensure minimum coverage threshold
      'i18n/translation-coverage': ['error', {
        localesDir: 'packages/cli/src/i18n/locales',
        sourceLanguage: 'en',
        minimumCoverage: 100,
      }],
      // Unused keys detection - find keys not used in source code
      'i18n/no-unused-keys': ['error', {
        sourceDir: 'packages/cli/src',
        ignorePatterns: [
          // Ignore keys that might be used dynamically
          '^errors\\.',
          '^spinners\\.',
          '^prompts\\.',
          '^status\\.',
        ],
      }],
      // Translation staleness - detect when English values change
      'i18n/translation-staleness': ['error', {
        hashFileName: '.translation-hashes.json',
      }],
    },
  },

  // Non-English locale files - untranslated value detection (Web)
  {
    files: [
      'packages/web/src/i18n/locales/ar/**/*.json',
      'packages/web/src/i18n/locales/de/**/*.json',
      'packages/web/src/i18n/locales/es/**/*.json',
      'packages/web/src/i18n/locales/fr/**/*.json',
      'packages/web/src/i18n/locales/ja/**/*.json',
      'packages/web/src/i18n/locales/ru/**/*.json',
      'packages/web/src/i18n/locales/tr/**/*.json',
      'packages/web/src/i18n/locales/zh/**/*.json',
    ],
    plugins: {
      json,
      'i18n': i18nJsonPlugin,
    },
    language: 'json/json',
    rules: {
      // Detect untranslated values (identical to English)
      'i18n/no-untranslated-values': ['error', {
        localesDir: 'packages/web/src/i18n/locales',
        minLength: 3,
        allowedPatterns: [
          // Allow technical abbreviations and acronyms
          '^[A-Z]{2,}$',
          // Allow URLs and paths
          '^https?://',
          '^/',
          // Allow domain names and example URLs (contain dots)
          '.*\\..*',
          // Allow email addresses
          '.*@.*',
          // Allow IDs with special characters (like b!Ei1XXXXXXXXXX)
          '^[a-zA-Z0-9!]+$',
          // Allow colon-separated values (like port numbers, UUIDs, etc.)
          '.*:.*',
          // Allow format strings with placeholder variables
          '.*\\{\\{.*\\}\\}.*',
          // Allow command examples (docker ps, etc.)
          '^[a-z]+\\s+[a-z]+$',
          // Allow command-line flags (--transfers, -f, --fast-list)
          '^-{1,2}[a-zA-Z]',
          // Allow technical lowercase-hyphenated values (my-bucket, us-east-1)
          '^[a-z][a-z0-9]*(-[a-z0-9]+)+$',
          // Allow port numbers (443, 8080, 22)
          '^\\d{2,5}$',
          // Allow file extensions and technical suffixes
          '\\.(json|xml|txt|log|pem|key|crt)$',
          // Allow technical terms with numbers (OAuth2, S3, B2)
          '^[A-Za-z]+\\d+$',
          // Allow placeholder patterns (my-bucket, your-key, example-name)
          '^(my|your|example|sample|test)-',
        ],
      }],
      // Ensure translations have same {{placeholders}} as English
      'i18n/interpolation-consistency': ['error', {
        localesDir: 'packages/web/src/i18n/locales',
      }],
    },
  },

  // Non-English locale files - untranslated value detection (CLI)
  {
    files: [
      'packages/cli/src/i18n/locales/ar/**/*.json',
      'packages/cli/src/i18n/locales/de/**/*.json',
      'packages/cli/src/i18n/locales/es/**/*.json',
      'packages/cli/src/i18n/locales/fr/**/*.json',
      'packages/cli/src/i18n/locales/ja/**/*.json',
      'packages/cli/src/i18n/locales/ru/**/*.json',
      'packages/cli/src/i18n/locales/tr/**/*.json',
      'packages/cli/src/i18n/locales/zh/**/*.json',
    ],
    plugins: {
      json,
      'i18n': i18nJsonPlugin,
    },
    language: 'json/json',
    rules: {
      // Detect untranslated values (identical to English)
      'i18n/no-untranslated-values': ['error', {
        localesDir: 'packages/cli/src/i18n/locales',
        minLength: 3,
        allowedPatterns: [
          // Allow technical abbreviations and acronyms
          '^[A-Z]{2,}$',
          // Allow URLs and paths
          '^https?://',
          '^/',
          // Allow domain names and example URLs (contain dots)
          '.*\\..*',
          // Allow email addresses
          '.*@.*',
          // Allow colon-separated values (like port numbers, UUIDs, etc.)
          '.*:.*',
          // Allow format strings with placeholder variables
          '.*\\{\\{.*\\}\\}.*',
          // Allow command examples (docker ps, etc.)
          '^[a-z]+\\s+[a-z]+$',
          // Allow command-line flags (--transfers, -f, --fast-list)
          '^-{1,2}[a-zA-Z]',
          // Allow technical lowercase-hyphenated values (my-bucket, us-east-1)
          '^[a-z][a-z0-9]*(-[a-z0-9]+)+$',
          // Allow port numbers (443, 8080, 22)
          '^\\d{2,5}$',
          // Allow file extensions and technical suffixes
          '\\.(json|xml|txt|log|pem|key|crt)$',
          // Allow CLI-specific patterns
          '^rdc\\s',  // CLI commands like "rdc login"
        ],
      }],
      // Ensure translations have same {{placeholders}} as English
      'i18n/interpolation-consistency': ['error', {
        localesDir: 'packages/cli/src/i18n/locales',
      }],
    },
  },

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
      'packages/cli/src/__tests__/**/*.ts',
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
      'playwright/expect-expect': 'off',

      // --- General test file rules ---
      'max-lines': 'off',
      'max-nested-callbacks': ['error', 5],

      // --- Disable production-only rules ---
      'custom/require-translation': 'off',
      'custom/no-hardcoded-text': 'off',
      'custom/no-hardcoded-cli-text': 'off',
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
  // WWW PACKAGE OVERRIDES (Astro marketing site)
  // =============================================================
  // Disable web-specific rules for www package since it's an Astro site
  // with different translation patterns and no Ant Design components
  {
    files: ['packages/www/src/**/*.{ts,tsx}'],
    rules: {
      // Disable web-specific i18n rules (www uses different translation system)
      'custom/require-translation': 'off',
      'custom/no-hardcoded-text': 'off',
      'custom/require-testid': 'off',
      'custom/no-raw-api-calls': 'off',
      // Disable Ant Design restrictions (www uses native HTML)
      'react/forbid-elements': 'off',
      'no-restricted-imports': 'off',
    },
  },

  // WWW translation JSON files - basic JSON linting
  {
    files: ['packages/www/src/i18n/translations/*.json'],
    plugins: {
      json,
      'i18n': i18nJsonPlugin,
    },
    language: 'json/json',
    rules: {
      'json/no-duplicate-keys': 'error',
      'i18n/no-empty-translations': 'error',
      'i18n/sorted-keys': 'error',
    },
  },

  // JSON package is bash-based, exclude from ESLint
  {
    ignores: ['packages/json/**'],
  },

);
