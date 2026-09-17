// --------------------------------------------------------------------------- JAVASCRIPT AND TYPESCRIPT BASE, AND THE LOCAL RULE PLUGIN
//
// The recommended sets, the relaxations for scripts/**/*.ts, and the one repo-wide type-aware block that carries every plugin this repo lints with,
// including the `custom` plugin that wires up eslint-rules/.
//
// The plugin wiring does NOT get a module of its own, on purpose. `plugins` and the `custom/*` severities live in the SAME config object, and pulling the plugin map into a separate block would either change which files the rules attach to or add a block that was not there before. Both are edits, and this split is a move.
// ---------------------------------------------------------------------------
//
// ORDER IS THE CONTRACT. Flat config resolves by LAST MATCH WINS, so these
// blocks mean what they mean only in the position eslint.config.js splices them
// into. This module is a verbatim slice of the single 1,444-line file that came before it: the blocks, their order, their comments and their whitespace are unchanged. Anything else would be a rewrite wearing a refactor's clothes. ---------------------------------------------------------------------------

import path from 'node:path';
import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactPlugin from 'eslint-plugin-react';
import reactHooksPlugin from 'eslint-plugin-react-hooks';
import importPlugin from 'eslint-plugin-import';
import unicornPlugin from 'eslint-plugin-unicorn';
import sonarjsPlugin from 'eslint-plugin-sonarjs';
import regexpPlugin from 'eslint-plugin-regexp';
import globals from 'globals';
import { requireTestId } from '../eslint-rules/require-testid.js';
import { requireTranslation } from '../eslint-rules/require-translation.js';
import { requireTranslationKeyArg } from '../eslint-rules/require-translation-key-arg.js';
import { noHardcodedText } from '../eslint-rules/no-hardcoded-text.js';
import { noHardcodedCliText } from '../eslint-rules/no-hardcoded-cli-text.js';
import { requireCommandSummary } from '../eslint-rules/require-command-summary.js';
import { noDuplicateTranslationProps } from '../eslint-rules/no-duplicate-translation-props.js';
import { preferConstArrays } from '../eslint-rules/prefer-const-arrays.js';
import { noHardcodedNullishDefaults } from '../eslint-rules/no-hardcoded-nullish-defaults.js';
import { noPositionalCliSyntaxSource } from '../eslint-rules/no-positional-cli-syntax-source.js';
import { e2eTestNamingConvention } from '../eslint-rules/e2e-test-naming-convention.js';
import { requireDataTrack } from '../eslint-rules/require-data-track.js';
import { seoNoVagueAnchorText } from '../eslint-rules/seo-no-vague-anchor-text.js';
import { seoRequireImgAlt } from '../eslint-rules/seo-require-img-alt.js';
import { seoNoHashBreadcrumbUrl } from '../eslint-rules/seo-no-hash-breadcrumb-url.js';
import { seoNoTrailingSlashInternalLink } from '../eslint-rules/seo-no-trailing-slash-internal-link.js';
import { noUnawaitedDrizzleTerminator } from '../eslint-rules/no-unawaited-drizzle-terminator.js';
import { noDirectSftpClient } from '../eslint-rules/no-direct-sftp-client.js';

// The single-file config sat at the repository root, so `import.meta.dirname` meant the root and the two values below were absolute against it. From inside
// eslint.config/ that same expression means one directory DEEPER, which would
// silently retarget the TypeScript project service and the locale directories one level down without any error to read. Derive the root once, explicitly.
const REPO_ROOT = path.resolve(import.meta.dirname, '..');

export default [
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
          'no-duplicate-translation-props': noDuplicateTranslationProps,
          'prefer-const-arrays': preferConstArrays,
          'no-hardcoded-nullish-defaults': noHardcodedNullishDefaults,
          'e2e-test-naming-convention': e2eTestNamingConvention,
          'require-data-track': requireDataTrack,
          'no-positional-cli-syntax-source': noPositionalCliSyntaxSource,
          'seo-no-vague-anchor-text': seoNoVagueAnchorText,
          'seo-require-img-alt': seoRequireImgAlt,
          'seo-no-hash-breadcrumb-url': seoNoHashBreadcrumbUrl,
          'seo-no-trailing-slash-internal-link': seoNoTrailingSlashInternalLink,
          'no-unawaited-drizzle-terminator': noUnawaitedDrizzleTerminator,
          'no-direct-sftp-client': noDirectSftpClient,
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
            // @rediacc/locales is deliberately buildless plain ESM with a hand-written .d.ts, so it has no tsconfig of its own to be included by. It exists in
            // that shape because eslint itself — this file — is one of its consumers and
            // runs before any build could produce a dist/.
            'packages/locales/*.js',
          ],
          maximumDefaultProjectFileMatchCount_THIS_WILL_SLOW_DOWN_LINTING: 12,
        },
        tsconfigRootDir: REPO_ROOT,
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
            'packages/shared/tsconfig.json',
            'packages/cli/tsconfig.json',
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
      // STRICT: No underscore prefix allowed - if unused, delete it Only exception: function parameters required by interfaces (use _ prefix for those)
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
      // Enforce data-testid on interactive elements for E2E test coverage This is strict (error) to ensure all interactive elements have testids
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

      // Import ordering is handled by Biome (organizeImports in biome.json). Do not add import/order here — it conflicts with Biome's formatter.

      // Ban styled-components and Layout to enforce Ant Design best practices Ban deprecated type utilities to prevent hopping type patterns
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
];
