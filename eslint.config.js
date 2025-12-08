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
        }
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
          project: ['packages/web/tsconfig.json', 'packages/shared/tsconfig.json'],
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
      
      // General rules
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'no-debugger': 'warn',

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
    }
  }
);
