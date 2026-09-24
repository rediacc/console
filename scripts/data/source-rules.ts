/**
 * The flat, per-rule-instance table `check-source-rules.ts` (the H gate, per
 * PLAN-biome-only-lint.md's rule map) runs against the real tree.
 *
 * WHY FLAT, AND WHY THIS IS A MOVE RATHER THAN A REWRITE. `eslint.config.js`
 * resolves LAST MATCH WINS across six modules, so a rule's real `files` scope
 * today is "the union of every block that sets it minus every later block that
 * turns it off for a sub-path" -- readable only by re-deriving it from
 * `eslint.config/{i18n,packages,tests,tooling,typescript}.js`. This table does
 * that derivation once, by hand, against those five files, and stores only the
 * RESULT: one entry per (rule, effective scope, effective options) triple.
 * There is no cascade to resolve at read time any more, which is the plan's own
 * word for this ("order stops being a contract").
 *
 * WHAT IS NOT HERE. Every rule this table lists is one the plan's rule map
 * marks **H** -- a `custom/*`, `i18n/*` or `i18n-source/*` rule with no Biome or
 * GritQL equivalent. `json/no-duplicate-keys` (an `@eslint/json` core rule, not
 * one of ours) and the five rules that are 'off' everywhere
 * (`i18n/no-empty-translations`, `sorted-keys`, `key-naming-convention`,
 * `no-unused-keys`, `translation-staleness`) are both deliberately absent: the
 * former belongs to Biome's `suspicious/noDuplicateObjectKeys`, the latter have
 * no enabled scope to derive and are proven only by `check:ci-lint-rule-units`
 * (via the host-backed tester), never by this gate. `max-lines` is a core
 * ESLint rule with its own replacement (`check-max-lines.ts`) and is not a
 * `Type`/`Document` rule module at all, so it is out of this table too.
 *
 * GLOBS ARE POSIX AND REPO-ROOT-RELATIVE, matched with `minimatch` against a
 * path already normalised to `/`. `GLOBAL_IGNORES` mirrors
 * `eslint.config/ignores.js`'s ignore-only block, which is global and applies
 * before any per-rule scope -- exactly as it does in the real flat config,
 * where an ignores-only object is spliced first and inherited by everything
 * after it.
 */

import { minimatch } from 'minimatch';

export interface RuleInstance {
  /** `<namespace>/<rule-name>`, exactly as ESLint reports it in `message.ruleId`. */
  ruleId: string;
  kind: 'source' | 'json';
  /** Path to the rule module, relative to the repository root. */
  modulePath: string;
  /** The module's named export for the rule object. */
  exportName: string;
  files: string[];
  ignores?: string[];
  options?: unknown[];
}

/**
 * Verbatim from `eslint.config/ignores.js`'s ignore-only block (its `:14-66`):
 * every entry, in the same order. This used to be a hand-picked subset -- 11
 * of the 30 entries there -- which left the host corpus at 2952 tracked paths
 * against ESLint's own 2793 (`.ci/cache/biome-parity/phase0-config-snapshot.jsonl`
 * line count). The 9 missing build/dependency-output globs (`dist`, the
 * per-package `dist`, `dist-typecheck`, `node_modules` and `bin` globs, the
 * repo-root `bin`, `cli/dist`, `node_modules`, the `*.tmp` dir glob and
 * `.ci/cache`) cost nothing here since `trackedFiles()` already only sees
 * git-tracked paths, but the 4 generated-JS globs (the per-package
 * `src`-and-`tests` `.js`/`.js.map` pairs) and the 5 account-submodule
 * build/vendor globs (`node_modules`, web `node_modules`, `dist`, web `dist`,
 * `e2e`, all under `private/account`) and `workers/account/dist` are all
 * tracked, and their absence is exactly the 159-path gap: 150 of it is the
 * `private/account/e2e` glob, which ESLint never lints and which
 * `require-testid` below (`files: ALL_SOURCE_FILES`, no `private/account/e2e`
 * ignore of its own -- `TEST_FILE_GLOBS` never listed it) was never meant to
 * reach either. See `check-source-rules.ts --config-differential`.
 */
export const GLOBAL_IGNORES: string[] = [
  'dist/',
  'packages/*/dist/',
  'packages/*/dist-typecheck/',
  'packages/*/node_modules/',
  'packages/*/bin/',
  'bin/',
  'cli/dist/',
  'node_modules/',
  '**/*.tmp/',
  '.ci/cache/',
  '*.config.js',
  '*.config.ts',
  '*.config.cjs',
  '**/*.d.ts',
  'packages/*/src/**/*.js',
  'packages/*/src/**/*.js.map',
  'packages/*/tests/**/*.js',
  'packages/*/tests/**/*.js.map',
  '**/.translation-hashes.json',
  '**/.naturalized-hashes.json',
  'packages/www/public/**',
  'packages/e2e-tests/reports/**',
  'private/!(account)/**',
  'private/account/node_modules/**',
  'private/account/web/node_modules/**',
  'private/account/dist/**',
  'private/account/web/dist/**',
  'private/account/e2e/**',
  'workers/account/dist/**',
  'packages/www/.astro/**',
  'packages/cli/templates/**',
];

/**
 * The one OTHER files-less `ignores`-only block among all six
 * `eslint.config/{ignores,typescript,i18n,tests,packages,tooling}.js` modules
 * (checked by hand, every `ignores:` in the tree cross-referenced against a
 * sibling `files:` in the same object): `eslint.config/packages.js:238-240`,
 * "JSON package is bash-based, exclude from ESLint". A files-less `ignores`
 * block is global in flat config exactly like `ignores.js`'s own block --
 * ESLint's own `isPathIgnored()` confirms it (`packages/json/package.json` ->
 * `true`) -- so `GLOBAL_IGNORES` alone still left 5 `packages/json/**` paths
 * in this table's corpus that ESLint never lints. Kept separate from
 * `GLOBAL_IGNORES` rather than folded in, so that constant stays an honest,
 * checkable copy of exactly one file.
 */
export const OTHER_GLOBAL_IGNORES: string[] = ['packages/json/**'];

/**
 * ESLint's own built-in flat-config ignores (`@eslint/config-array`'s defaults), applied
 * before any config's own: `node_modules` at ANY depth (ESLint ignores
 * `scripts/node_modules/a.ts`, which `GLOBAL_IGNORES`'s root-only `node_modules/` does not
 * cover) and `.git`.
 */
export const ESLINT_DEFAULT_IGNORES: string[] = ['**/node_modules/', '.git/'];

/**
 * Match one flat-config glob the way ESLint does. A trailing `/` names a DIRECTORY, and ESLint
 * ignores everything beneath it; plain `minimatch('packages/cli/dist/a.ts', 'packages/*\/dist/')`
 * is false, so every directory-style entry (`dist/`, `packages/*\/dist/`, `packages/*\/bin/`,
 * `node_modules/`, `**\/*.tmp/`) would silently match nothing. Checked against ESLint's own
 * `isPathIgnored()` by `.ci/cache/biome-parity/verify3/ign.mjs`.
 */
export function matchesEslintGlob(posixPath: string, glob: string): boolean {
  return minimatch(posixPath, glob.endsWith('/') ? `${glob}**` : glob, { dot: true });
}

/** True when ESLint's global ignores (its built-in defaults, `GLOBAL_IGNORES` and `OTHER_GLOBAL_IGNORES`) drop `posixPath` before any rule block is consulted. */
export function isGloballyIgnored(posixPath: string): boolean {
  return [...ESLINT_DEFAULT_IGNORES, ...GLOBAL_IGNORES, ...OTHER_GLOBAL_IGNORES].some((g) =>
    matchesEslintGlob(posixPath, g)
  );
}

const CLI_EN_LOCALE_DIR = 'packages/cli/src/i18n/locales/en';
const ACCOUNT_WEB_EN_LOCALE_DIR = 'private/account/web/src/i18n/locales/en';

/** Verbatim from `eslint.config/i18n.js`'s `UNTRANSLATED_BASE_PATTERNS`: shared across every locale tree, before each tree's own `extraUntranslatedPatterns`. */
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
  '^Token$',
  '^Flag$',
  '^Password$',
  '^Rediacc logo$',
  '^Clusters?$',
  '^Datastores?$',
  '^Communications$',
  '^[A-Z]{2,}([ /|,+-]+[A-Z]{2,})+$',
];

const CLI_EXTRA_UNTRANSLATED_PATTERNS = [
  '^[A-Za-z]+\\d+$',
  '^(Docker|Renet|Go|Node\\.js|Status|Version|Machines|Configuration)$',
  '^rdc\\s',
  '^(Installation|Description|Note|Error|Reference|Infrastructure)$',
  '^(Rename|Create|Delete|Show)\\s',
  'vault management',
  'vault status',
  'dedicated TLS cert',
  'Generate command reference',
  '^Activation failed$',
];

const ACCOUNT_WEB_EXTRA_UNTRANSLATED_PATTERNS = [
  '^[A-Za-z]+\\d+$',
  '^(Rediacc|Stripe|Docker|Kubernetes|rdc|rediacc)$',
  'Rediacc$',
  '^rdc\\s',
  '^#\\s',
  '^N/A$',
  '^Sandbox$',
  '^S3 ID$',
  '^CERT-\\d{4}-\\d{4}$',
  '^RC1-X{8}-X{8}-X{8}-X{8}$',
  '^Passkey$',
  '^Tag$',
  '^(Business|Community|Enterprise|Professional)$',
  '^Pro$',
  '^Clustering$',
  '^(Plan|Type|Newsletter|Name|Limit|Source|Admin|Total|Team|Status|Magnet|Machines|Code|Permissions|General|Description|Date|Dashboard|Contact|Activations|Actions)$',
  '^Commit$',
  '^Backend$',
  '^Provider$',
  '^Repository$',
  '^(Destinations|Services)$',
  '^Mode$',
  '^Port$',
  '^Pools$',
  '^(Region|Image|Cluster|Datastore)$',
  '^[KMGTPE]iB$',
];

const ACCOUNT_EXTRA_UNTRANSLATED_PATTERNS = [
  '^(Rediacc|Stripe|rediacc)$',
  'Rediacc$',
  '^rdc\\s',
  '^(Name|Source|Status)$',
];

// A single non-scripts JS/JSX/TS/TSX source file, matching typescript.js's
// react-plugin block (":52" onward) minus its own `scripts/**/*.ts` exclusion.
const ALL_SOURCE_FILES = ['**/*.js', '**/*.jsx', '**/*.ts', '**/*.tsx'];
const SCRIPTS_TS = ['scripts/**/*.ts'];
const TEST_FILE_GLOBS = [
  'packages/e2e-tests/**/*.ts',
  'packages/shared/src/**/__tests__/**/*.ts',
  'packages/shared/src/**/__tests__/**/*.tsx',
  'packages/cli/src/**/__tests__/**/*.ts',
];

/** i18n.js's generated-file relaxation block (renet contract schemas, the CLI's embedded-template constant, api-schema.zod.ts): the one entry of it that hits an H rule is `custom/no-hardcoded-nullish-defaults`, since every other rule the block turns off there is B-mapped. */
const GENERATED_FILE_GLOBS = [
  '**/*.generated.ts',
  '**/*.generated.tsx',
  '**/api-schema.zod.ts',
  '**/renet-contract/data/*.schema.ts',
];

/** typescript.js:52-379's four `custom/*` rules, base-scoped repo-wide. */
const BASE_SCOPED: RuleInstance[] = [
  {
    ruleId: 'custom/no-duplicate-translation-props',
    kind: 'source',
    modulePath: 'eslint-rules/no-duplicate-translation-props.js',
    exportName: 'noDuplicateTranslationProps',
    files: ALL_SOURCE_FILES,
    // packages.js:30 turns this off for the whole account tree.
    ignores: [...SCRIPTS_TS, 'private/account/**/*.ts', 'private/account/**/*.tsx'],
  },
  {
    ruleId: 'custom/prefer-const-arrays',
    kind: 'source',
    modulePath: 'eslint-rules/prefer-const-arrays.js',
    exportName: 'preferConstArrays',
    // tooling.js:22-27: plain JS/JSX cannot spell `as const` at all, so the
    // rule's real reach is TypeScript only.
    files: ['**/*.ts', '**/*.tsx'],
    ignores: [...SCRIPTS_TS, 'private/account/**/*.ts', 'private/account/**/*.tsx'],
  },
  {
    ruleId: 'custom/no-hardcoded-nullish-defaults',
    kind: 'source',
    modulePath: 'eslint-rules/no-hardcoded-nullish-defaults.js',
    exportName: 'noHardcodedNullishDefaults',
    files: ALL_SOURCE_FILES,
    // tests.js:59 turns this off for every test-file glob too, alongside account.
    ignores: [
      ...SCRIPTS_TS,
      'private/account/**/*.ts',
      'private/account/**/*.tsx',
      ...TEST_FILE_GLOBS,
      ...GENERATED_FILE_GLOBS,
    ],
    options: [
      {
        allowZero: true,
        allowNegativeOne: true,
        allowedNumbers: [1],
        allowedStrings: [
          '',
          'file-based',
          '-',
          '—',
          'N/A',
          'none',
          '!',
          '{}',
          '[]',
          'default',
          '(none)',
          'terminal',
          'System has critical issues',
        ],
      },
    ],
  },
  /**
   * `@typescript-eslint/no-unused-vars`'s `varsIgnorePattern: '^$'` half
   * (typescript.js:172-176), scoped exactly like this same block's
   * `no-unused-vars` entry: the react-plugin block's own `files`/`ignores`
   * (`**\/*.{js,jsx,ts,tsx}` minus `scripts/**\/*.ts`), further OFF for the
   * whole account tree (`@typescript-eslint/no-unused-vars: 'off'`,
   * packages.js:30). No test-file relaxation exists for this rule in the real
   * config (tests.js:63 only touches `prefer-nullish-coalescing`), so it stays
   * ON for test files here too. H per PLAN-biome-only-lint.md's rule map, "no-unused-vars" row (H3a): Biome's `noUnusedVariables`/`noUnusedFunctionParameters`
   * exempt every `_`-prefixed name unconditionally, which is the one half of
   * this rule Biome cannot express.
   */
  {
    ruleId: 'custom/no-unused-underscore-var',
    kind: 'source',
    modulePath: 'eslint-rules/no-unused-underscore-var.js',
    exportName: 'noUnusedUnderscoreVar',
    files: ALL_SOURCE_FILES,
    ignores: [...SCRIPTS_TS, 'private/account/**/*.ts', 'private/account/**/*.tsx'],
  },
  {
    ruleId: 'custom/require-testid',
    kind: 'source',
    modulePath: 'eslint-rules/require-testid.js',
    exportName: 'requireTestId',
    files: ALL_SOURCE_FILES,
    // tests.js turns it off for every test-file glob; it stays ON for account
    // (see the banner at packages.js:100-104: swept and enabled 2026-08-15).
    ignores: [...SCRIPTS_TS, ...TEST_FILE_GLOBS],
    options: [
      {
        requiredElements: ['Modal', 'Drawer'],
        interactiveElements: ['Button'],
        formElements: [
          'Input',
          'Input.Password',
          'Input.Search',
          'Input.TextArea',
          'Input.OTP',
          'Select',
          'Select.Option',
          'Checkbox',
          'Checkbox.Group',
          'Radio',
          'Radio.Group',
          'Radio.Button',
          'Switch',
          'Upload',
          'Upload.Dragger',
          'InputNumber',
          'Slider',
          'Rate',
          'DatePicker',
          'DatePicker.RangePicker',
          'RangePicker',
          'TimePicker',
          'TimePicker.RangePicker',
          'AutoComplete',
          'Cascader',
          'TreeSelect',
          'Transfer',
          'Mentions',
          'ColorPicker',
        ],
        allowTemplateLiterals: true,
      },
    ],
  },
];

/**
 * i18n.js:146-192's CLI i18n enforcement block. Three of its rules --
 * `no-hardcoded-cli-text`, `require-command-summary` and `require-translation`
 * -- are turned back OFF for CLI unit tests by tests.js's later "disable
 * production-only rules" block, so `TEST_FILE_GLOBS` joins their ignores too;
 * the other four in this block are never touched by that later override and
 * stay enabled inside `__tests__/**`, matching `calculateConfigForFile`.
 */
const CLI_I18N: RuleInstance[] = [
  {
    ruleId: 'custom/no-hardcoded-cli-text',
    kind: 'source',
    modulePath: 'eslint-rules/no-hardcoded-cli-text.js',
    exportName: 'noHardcodedCliText',
    files: ['packages/cli/src/**/*.js', 'packages/cli/src/**/*.ts'],
    ignores: [
      'packages/cli/src/__tests__/**',
      'packages/cli/src/commands/refprobe.ts',
      ...TEST_FILE_GLOBS,
    ],
  },
  {
    ruleId: 'custom/require-command-summary',
    kind: 'source',
    modulePath: 'eslint-rules/require-command-summary.js',
    exportName: 'requireCommandSummary',
    files: ['packages/cli/src/**/*.js', 'packages/cli/src/**/*.ts'],
    ignores: [
      'packages/cli/src/__tests__/**',
      'packages/cli/src/commands/refprobe.ts',
      ...TEST_FILE_GLOBS,
    ],
  },
  {
    ruleId: 'custom/require-translation',
    kind: 'source',
    modulePath: 'eslint-rules/require-translation.js',
    exportName: 'requireTranslation',
    files: ['packages/cli/src/**/*.js', 'packages/cli/src/**/*.ts'],
    ignores: [
      'packages/cli/src/__tests__/**',
      'packages/cli/src/commands/refprobe.ts',
      ...TEST_FILE_GLOBS,
    ],
    options: [{ localeDir: CLI_EN_LOCALE_DIR }],
  },
  {
    ruleId: 'custom/require-translation-key-arg',
    kind: 'source',
    modulePath: 'eslint-rules/require-translation-key-arg.js',
    exportName: 'requireTranslationKeyArg',
    files: ['packages/cli/src/**/*.js', 'packages/cli/src/**/*.ts'],
    ignores: ['packages/cli/src/__tests__/**', 'packages/cli/src/commands/refprobe.ts'],
    options: [{ localeDir: CLI_EN_LOCALE_DIR, functions: [{ name: 'errorResult', argIndex: 0 }] }],
  },
  {
    ruleId: 'i18n-source/interpolation-match',
    kind: 'source',
    modulePath: 'eslint-rules/i18n/interpolation-match.js',
    exportName: 'interpolationMatch',
    files: ['packages/cli/src/**/*.js', 'packages/cli/src/**/*.ts'],
    ignores: ['packages/cli/src/__tests__/**', 'packages/cli/src/commands/refprobe.ts'],
    options: [{ localeDir: CLI_EN_LOCALE_DIR }],
  },
  {
    ruleId: 'custom/no-positional-cli-syntax-source',
    kind: 'source',
    modulePath: 'eslint-rules/no-positional-cli-syntax-source.js',
    exportName: 'noPositionalCliSyntaxSource',
    files: ['packages/cli/src/**/*.js', 'packages/cli/src/**/*.ts'],
    ignores: ['packages/cli/src/__tests__/**', 'packages/cli/src/commands/refprobe.ts'],
  },
  {
    ruleId: 'custom/no-direct-sftp-client',
    kind: 'source',
    modulePath: 'eslint-rules/no-direct-sftp-client.js',
    exportName: 'noDirectSftpClient',
    files: ['packages/cli/src/**/*.js', 'packages/cli/src/**/*.ts'],
    ignores: ['packages/cli/src/__tests__/**', 'packages/cli/src/commands/refprobe.ts'],
    options: [{ allow: ['src/services/machine/machine-connection.ts'] }],
  },
];

/** i18n.js:194-215's account-web i18n enforcement block. */
const ACCOUNT_WEB_I18N: RuleInstance[] = [
  {
    ruleId: 'custom/require-translation',
    kind: 'source',
    modulePath: 'eslint-rules/require-translation.js',
    exportName: 'requireTranslation',
    files: ['private/account/web/src/**/*.ts', 'private/account/web/src/**/*.tsx'],
    ignores: [
      'private/account/web/src/**/__tests__/**',
      'private/account/web/src/components/ui/**',
    ],
    options: [{ localeDir: ACCOUNT_WEB_EN_LOCALE_DIR }],
  },
  {
    ruleId: 'custom/no-hardcoded-text',
    kind: 'source',
    modulePath: 'eslint-rules/no-hardcoded-text.js',
    exportName: 'noHardcodedText',
    files: ['private/account/web/src/**/*.ts', 'private/account/web/src/**/*.tsx'],
    // The 6 files below carry a file-level ESLint suppression comment for this rule in the current tree (none states an inline reason), carried over here as explicit ignores per the rule map (row 141): a directive nothing honours once ESLint is gone must not silently start reporting instead.
    ignores: [
      'private/account/web/src/**/__tests__/**',
      'private/account/web/src/components/ui/**',
      'private/account/web/src/pages/DeviceConfigSetup.tsx',
      'private/account/web/src/pages/ConfigMemberAccept.tsx',
      'private/account/web/src/pages/admin/ConfigAdmin.tsx',
      'private/account/web/src/pages/ConfigStorage.tsx',
      'private/account/web/src/pages/ConfigMembers.tsx',
      'private/account/web/src/pages/ConfigSetup.tsx',
    ],
  },
  {
    ruleId: 'i18n-source/interpolation-match',
    kind: 'source',
    modulePath: 'eslint-rules/i18n/interpolation-match.js',
    exportName: 'interpolationMatch',
    files: ['private/account/web/src/**/*.ts', 'private/account/web/src/**/*.tsx'],
    ignores: [
      'private/account/web/src/**/__tests__/**',
      'private/account/web/src/components/ui/**',
    ],
    options: [{ localeDir: ACCOUNT_WEB_EN_LOCALE_DIR }],
  },
  {
    ruleId: 'custom/no-positional-cli-syntax-source',
    kind: 'source',
    modulePath: 'eslint-rules/no-positional-cli-syntax-source.js',
    exportName: 'noPositionalCliSyntaxSource',
    files: ['private/account/web/src/**/*.ts', 'private/account/web/src/**/*.tsx'],
    ignores: [
      'private/account/web/src/**/__tests__/**',
      'private/account/web/src/components/ui/**',
    ],
  },
];

/** packages.js:132-142's account Drizzle backstop. */
const ACCOUNT_DRIZZLE: RuleInstance[] = [
  {
    ruleId: 'custom/no-unawaited-drizzle-terminator',
    kind: 'source',
    modulePath: 'eslint-rules/no-unawaited-drizzle-terminator.js',
    exportName: 'noUnawaitedDrizzleTerminator',
    files: ['private/account/src/**/*.ts'],
    ignores: ['private/account/src/db/index.ts'],
  },
];

/** packages.js:147-182's www overrides: SEO, a11y-adjacent and analytics rules. */
const WWW_SRC = ['packages/www/src/**/*.ts', 'packages/www/src/**/*.tsx'];
const WWW_RULES: RuleInstance[] = [
  {
    ruleId: 'custom/seo-no-vague-anchor-text',
    kind: 'source',
    modulePath: 'eslint-rules/seo-no-vague-anchor-text.js',
    exportName: 'seoNoVagueAnchorText',
    files: WWW_SRC,
  },
  {
    ruleId: 'custom/seo-require-img-alt',
    kind: 'source',
    modulePath: 'eslint-rules/seo-require-img-alt.js',
    exportName: 'seoRequireImgAlt',
    files: WWW_SRC,
  },
  {
    ruleId: 'custom/seo-no-hash-breadcrumb-url',
    kind: 'source',
    modulePath: 'eslint-rules/seo-no-hash-breadcrumb-url.js',
    exportName: 'seoNoHashBreadcrumbUrl',
    files: WWW_SRC,
  },
  {
    ruleId: 'custom/seo-no-trailing-slash-internal-link',
    kind: 'source',
    modulePath: 'eslint-rules/seo-no-trailing-slash-internal-link.js',
    exportName: 'seoNoTrailingSlashInternalLink',
    files: WWW_SRC,
  },
  {
    ruleId: 'custom/no-positional-cli-syntax-source',
    kind: 'source',
    modulePath: 'eslint-rules/no-positional-cli-syntax-source.js',
    exportName: 'noPositionalCliSyntaxSource',
    files: WWW_SRC,
  },
  {
    ruleId: 'custom/require-data-track',
    kind: 'source',
    modulePath: 'eslint-rules/require-data-track.js',
    exportName: 'requireDataTrack',
    files: WWW_SRC,
    options: [
      { elements: ['a', 'button'], exemptParents: ['SearchModal', 'LanguageMenu', 'Sidebar'] },
    ],
  },
];

/** tests.js:17-29: the one rule test files turn ON, self-guarded to its own basename pattern. */
const E2E_NAMING: RuleInstance[] = [
  {
    ruleId: 'custom/e2e-test-naming-convention',
    kind: 'source',
    modulePath: 'eslint-rules/e2e-test-naming-convention.js',
    exportName: 'e2eTestNamingConvention',
    files: TEST_FILE_GLOBS,
  },
];

/**
 * tests.js:36-47's `playwright/expect-expect`, with the exact
 * `assertFunctionPatterns` list, host-ported per the rule map ("H: port as
 * `e2e-expect-expect`") since real corpus files use bare `test(...)`, not
 * `it(...)`, and this repo sets no `settings.playwright.globalAliases` --
 * `eslint-rules/e2e-expect-expect.js`'s own header traces why that makes `it`
 * invisible to the REAL rule too, so scoping this table the same as
 * `TEST_FILE_GLOBS` costs nothing extra. The 3 stub exemptions are
 * tests.js:77-88's file list verbatim.
 */
const E2E_EXPECT_EXPECT: RuleInstance[] = [
  {
    ruleId: 'custom/e2e-expect-expect',
    kind: 'source',
    modulePath: 'eslint-rules/e2e-expect-expect.js',
    exportName: 'e2eExpectExpect',
    files: TEST_FILE_GLOBS,
    ignores: [
      'packages/e2e-tests/tests/12a-full-integration-repository.test.ts',
      'packages/e2e-tests/tests/13-postgres-fork-isolation.test.ts',
      'packages/e2e-tests/tests/ops-lifecycle/18-ops-lifecycle.test.ts',
    ],
    options: [
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
    ],
  },
];

const CUSTOM_SOURCE_RULES: RuleInstance[] = [
  ...BASE_SCOPED,
  ...CLI_I18N,
  ...ACCOUNT_WEB_I18N,
  ...ACCOUNT_DRIZZLE,
  ...WWW_RULES,
  ...E2E_NAMING,
  ...E2E_EXPECT_EXPECT,
];

/** The three `i18nLocaleConfigs()` blocks (i18n.js:59-134), instantiated per locale tree. */
function i18nJsonInstances(cfg: {
  localesDir: string;
  cliSyntax?: { exemptCommandPrefixes: string[] };
  cliFlags?: boolean;
  extraUntranslatedPatterns?: string[];
}): RuleInstance[] {
  const languages = ['ar', 'de', 'es', 'et', 'fr', 'it', 'ja', 'ko', 'pt', 'ru', 'tr', 'zh'];
  const nonEnglishFiles = languages.map((lang) => `${cfg.localesDir}/${lang}/**/*.json`);
  const localesDirAbs = cfg.localesDir;
  const out: RuleInstance[] = [];
  if (cfg.cliSyntax) {
    out.push({
      ruleId: 'i18n/no-positional-cli-syntax',
      kind: 'json',
      modulePath: 'eslint-rules/i18n/no-positional-cli-syntax.js',
      exportName: 'noPositionalCliSyntax',
      files: [`${cfg.localesDir}/**/*.json`],
      options: [{ autoDerive: true, exemptCommandPrefixes: cfg.cliSyntax.exemptCommandPrefixes }],
    });
  }
  if (cfg.cliFlags) {
    out.push({
      ruleId: 'i18n/cli-flag-consistency',
      kind: 'json',
      modulePath: 'eslint-rules/i18n/cli-flag-consistency.js',
      exportName: 'cliFlagConsistency',
      files: [`${cfg.localesDir}/**/*.json`],
      options: [{ localesDir: localesDirAbs }],
    });
    out.push({
      ruleId: 'i18n/no-undefined-cli-flags',
      kind: 'json',
      modulePath: 'eslint-rules/i18n/no-undefined-cli-flags.js',
      exportName: 'noUndefinedCliFlags',
      files: [`${cfg.localesDir}/en/**/*.json`],
      options: [{ exemptFlags: [], exemptKeyPrefixes: [] }],
    });
  }
  out.push(
    {
      ruleId: 'i18n/cross-language-consistency',
      kind: 'json',
      modulePath: 'eslint-rules/i18n/cross-language-consistency.js',
      exportName: 'crossLanguageConsistency',
      files: [`${cfg.localesDir}/en/**/*.json`],
      options: [{ localesDir: localesDirAbs, sourceLanguage: 'en' }],
    },
    {
      ruleId: 'i18n/translation-coverage',
      kind: 'json',
      modulePath: 'eslint-rules/i18n/translation-coverage.js',
      exportName: 'translationCoverage',
      files: [`${cfg.localesDir}/en/**/*.json`],
      options: [{ localesDir: localesDirAbs, sourceLanguage: 'en', minimumCoverage: 100 }],
    },
    {
      ruleId: 'i18n/no-untranslated-values',
      kind: 'json',
      modulePath: 'eslint-rules/i18n/no-untranslated-values.js',
      exportName: 'noUntranslatedValues',
      files: nonEnglishFiles,
      options: [
        {
          localesDir: localesDirAbs,
          minLength: 3,
          allowedPatterns: [
            ...UNTRANSLATED_BASE_PATTERNS,
            ...(cfg.extraUntranslatedPatterns ?? []),
          ],
        },
      ],
    },
    {
      ruleId: 'i18n/interpolation-consistency',
      kind: 'json',
      modulePath: 'eslint-rules/i18n/interpolation-consistency.js',
      exportName: 'interpolationConsistency',
      files: nonEnglishFiles,
      options: [{ localesDir: localesDirAbs }],
    }
  );
  return out;
}

// packages/cli/scripts/command-tree.json already carries no legacy cloud-adapter
// commands, so the shared exempt list (eslint-rules/lib/cli-exempt-lists.js) is
// empty; account-web's block in i18n.js still hardcodes the pre-P4 literal list.
const ACCOUNT_WEB_EXEMPT_PREFIXES = [
  'rdc auth',
  'rdc audit',
  'rdc bridge',
  'rdc organization',
  'rdc permission',
  'rdc protocol',
  'rdc queue',
  'rdc region',
  'rdc repository',
  'rdc team',
  'rdc user',
  'rdc ceph',
];

const CLI_JSON = i18nJsonInstances({
  localesDir: 'packages/cli/src/i18n/locales',
  cliSyntax: { exemptCommandPrefixes: [] },
  cliFlags: true,
  extraUntranslatedPatterns: CLI_EXTRA_UNTRANSLATED_PATTERNS,
});
const ACCOUNT_WEB_JSON = i18nJsonInstances({
  localesDir: 'private/account/web/src/i18n/locales',
  cliSyntax: { exemptCommandPrefixes: ACCOUNT_WEB_EXEMPT_PREFIXES },
  extraUntranslatedPatterns: ACCOUNT_WEB_EXTRA_UNTRANSLATED_PATTERNS,
});
const ACCOUNT_JSON = i18nJsonInstances({
  localesDir: 'private/account/src/i18n/locales',
  extraUntranslatedPatterns: ACCOUNT_EXTRA_UNTRANSLATED_PATTERNS,
});

/** packages.js:186-233's www translation and tutorial-transcript SEO checks. */
const WWW_JSON: RuleInstance[] = [
  {
    ruleId: 'i18n/seo-title-length',
    kind: 'json',
    modulePath: 'eslint-rules/i18n/seo-title-length.js',
    exportName: 'seoTitleLength',
    files: ['packages/www/src/i18n/translations/*.json'],
    ignores: [
      'packages/www/src/i18n/translations/.translation-hashes.json',
      'packages/www/src/i18n/translations/.naturalized-hashes.json',
    ],
    options: [{ minLength: 30, maxLength: 60, exemptKeys: ['notFound', 'checkout.success'] }],
  },
  {
    ruleId: 'i18n/seo-description-length',
    kind: 'json',
    modulePath: 'eslint-rules/i18n/seo-description-length.js',
    exportName: 'seoDescriptionLength',
    files: ['packages/www/src/i18n/translations/*.json'],
    ignores: [
      'packages/www/src/i18n/translations/.translation-hashes.json',
      'packages/www/src/i18n/translations/.naturalized-hashes.json',
    ],
    options: [{ minLength: 50, maxLength: 160, exemptKeys: ['checkout.success'] }],
  },
  {
    ruleId: 'i18n/seo-no-duplicate-h1-title',
    kind: 'json',
    modulePath: 'eslint-rules/i18n/seo-no-duplicate-h1-title.js',
    exportName: 'seoNoDuplicateH1Title',
    files: ['packages/www/src/i18n/translations/*.json'],
    ignores: [
      'packages/www/src/i18n/translations/.translation-hashes.json',
      'packages/www/src/i18n/translations/.naturalized-hashes.json',
    ],
    options: [{ brandSuffixes: [' | Rediacc', ' — Rediacc', ' - Rediacc'] }],
  },
  {
    ruleId: 'i18n/no-untranslated-tutorial-transcript-values',
    kind: 'json',
    modulePath: 'eslint-rules/i18n/no-untranslated-tutorial-transcript-values.js',
    exportName: 'noUntranslatedTutorialTranscriptValues',
    files: ['packages/www/src/data/tutorial-transcripts/*/*.json'],
    options: [{ transcriptsDir: 'packages/www/src/data/tutorial-transcripts', minLength: 3 }],
  },
];

export const RULE_INSTANCES: RuleInstance[] = [
  ...CUSTOM_SOURCE_RULES,
  ...CLI_JSON,
  ...ACCOUNT_WEB_JSON,
  ...ACCOUNT_JSON,
  ...WWW_JSON,
];

/** Every ruleId this table can ever produce a finding for -- the H universe. */
export const RULE_IDS: string[] = [...new Set(RULE_INSTANCES.map((r) => r.ruleId))].sort();
