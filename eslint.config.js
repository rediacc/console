import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactPlugin from 'eslint-plugin-react';
import reactHooksPlugin from 'eslint-plugin-react-hooks';
import importPlugin from 'eslint-plugin-import';
import globals from 'globals';

export default tseslint.config(
  // Ignore patterns
  {
    ignores: [
      'dist/',
      'packages/*/dist/',
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
    ]
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
          ],
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
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': ['warn', {
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_'
      }],
      '@typescript-eslint/no-empty-interface': 'off',
      '@typescript-eslint/no-empty-object-type': 'off',
      '@typescript-eslint/no-deprecated': 'error',
      
      // General rules
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'no-debugger': 'warn',
      'max-lines': ['error', { max: 512, skipBlankLines: true, skipComments: true }],

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
      'no-restricted-imports': ['error', {
        paths: [
          { name: 'styled-components', message: 'Use Ant Design components with CSS utility classes (className) instead.' },
          {
            name: 'antd',
            importNames: ['Layout'],
            message: 'Layout has default grey/dark backgrounds. Use Flex component instead.',
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
          selector: 'JSXAttribute[name.name="style"]',
          message: 'Inline styles are not allowed. Use CSS utility classes from global.css instead (e.g., className="w-full inline-flex"). For dynamic styles, use // eslint-disable-next-line no-restricted-syntax',
        },
      ],
    }
  },

  // Disable max-lines for auto-generated files
  {
    files: ['**/*.generated.ts', '**/*.generated.tsx'],
    rules: {
      'max-lines': 'off',
    }
  }
);
