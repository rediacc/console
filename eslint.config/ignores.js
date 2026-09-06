// ---------------------------------------------------------------------------
// GLOBAL IGNORES AND LINTER OPTIONS
//
// What eslint never looks at, and the one linter-wide switch. This has to be
// first: an `ignores`-only block is global, and reportUnusedDisableDirectives
// is inherited by every block that follows.
// ---------------------------------------------------------------------------
//
// ORDER IS THE CONTRACT. Flat config resolves by LAST MATCH WINS, so these
// blocks mean what they mean only in the position eslint.config.js splices them
// into. This module is a verbatim slice of the single 1,444-line file that came
// before it: the blocks, their order, their comments and their whitespace are
// unchanged. Anything else would be a rewrite wearing a refactor's clothes.
// ---------------------------------------------------------------------------

export default [
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
      // Throwaway sandboxes a gate builds INSIDE a package (check-guard-mutations.ts
      // copies packages/cli into `.guard-mutations.<pid>.<rand>.tmp/`). `npm run ci` is a
      // parallel pool, so eslint's glob can list that tree and then ENOENT on a file the
      // sibling gate has already removed. ESLint does not read .gitignore, so the
      // `*.tmp` rule there does not cover it.
      '**/*.tmp/',
      '*.config.js',
      '*.config.ts',
      '*.config.cjs',
      // Ignore .d.ts files (generated type declarations)
      '**/*.d.ts',
      // Ignore generated JS companions for TypeScript source/test files
      'packages/*/src/**/*.js',
      'packages/*/src/**/*.js.map',
      'packages/*/tests/**/*.js',
      'packages/*/tests/**/*.js.map',
      // Hash SIDECARS are key->hash maps, not translations. Only www's pair was
      // excluded (in the per-block ignores far below), so the identical files
      // under packages/cli and private/account/web were linted as content --
      // invisible until the five dead i18n rules were repaired on 2026-08-06,
      // at which point they produced 4008 of the 11510 findings between them.
      '**/.translation-hashes.json',
      '**/.naturalized-hashes.json',
      // Ignore www public assets — the search-index-*.json files are large
      // generated artifacts that don't need linting and slow eslint to a crawl.
      'packages/www/public/**',
      // Ignore Playwright report artifacts (generated trace viewer files)
      'packages/e2e-tests/reports/**',
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
];
