// --------------------------------------------------------------------------- i18n ENFORCEMENT: SOURCE RULES, LOCALE JSON, AND THE GENERATOR
//
// The i18nLocaleConfigs() generator and everything downstream of it: the CLI and account-web source-side enforcement, the three per-package locale trees it expands into nine blocks, the JSON rule disables that keep JS/TS rules off locale files, the account email-copy restriction, and the generated-file exemption that sits between them in the original.
//
// The last two blocks are here because they are here in the original. Order is the contract (see below), so a block does not move across a module boundary to make a filename read better. ---------------------------------------------------------------------------
//
// ORDER IS THE CONTRACT. Flat config resolves by LAST MATCH WINS, so these
// blocks mean what they mean only in the position eslint.config.js splices them
// into. This module is a verbatim slice of the single 1,444-line file that came before it: the blocks, their order, their comments and their whitespace are unchanged. Anything else would be a rewrite wearing a refactor's clothes. ---------------------------------------------------------------------------

import { NON_ENGLISH_LOCALES } from '@rediacc/locales';
import path from 'node:path';
import json from '@eslint/json';
import { EXEMPT_COMMAND_PREFIXES } from '../eslint-rules/lib/cli-exempt-lists.js';
import { i18nJsonPlugin, i18nSourcePlugin } from '../eslint-rules/i18n/index.js';

// The single-file config sat at the repository root, so `import.meta.dirname` meant the root and the two values below were absolute against it. From inside
// eslint.config/ that same expression means one directory DEEPER, which would
// silently retarget the TypeScript project service and the locale directories one level down without any error to read. Derive the root once, explicitly.
const REPO_ROOT = path.resolve(import.meta.dirname, '..');

// =============================================================
// i18n LOCALE CONFIG HELPER
// =============================================================
// Generates 3 ESLint config blocks for each package's locale directory:
// 1. JSON linting (all languages): sorted keys, camelCase naming, no duplicates/empty 2. English cross-language validation: consistency, coverage, staleness, unused keys 3. Non-English validation: untranslated values, interpolation consistency

const I18N_LANGUAGES = NON_ENGLISH_LOCALES;

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
  // BORROWED TERMS. These are the correct word in at least one locale we ship, so demanding a "translation" would make the UI worse, not better: Italian genuinely uses "Password", and "Token"/"Flag" are the standard technical terms in it/pt/et. Locales that DO have a native word (de "Passwort", fr "Mot de passe", es "Contraseña", tr "Parola") already use it and are unaffected —
  // this only stops the rule demanding a change where the identical value is already right.
  '^Token$',
  '^Flag$',
  '^Password$',
  // Product name plus a word that is identical across our locales.
  '^Rediacc logo$',
  // Infrastructure nouns French (and several other locales) borrow verbatim. Both translation agents independently kept these bare after checking sibling keys, and "Communications" is simply the same word in French. Demanding a translation here would replace correct UI text with an invented one.
  '^Clusters?$',
  '^Datastores?$',
  '^Communications$',
  // Acronym-only values, including pairs like "RPO / RTO". The plain ^[A-Z]{2,}$ above
  // misses these because of the separator, and an acronym has no translation.
  '^[A-Z]{2,}([ /|,+-]+[A-Z]{2,})+$',
];

function i18nLocaleConfigs({
  localesDir,
  sourceDir,
  unusedKeyIgnores,
  extraUntranslatedPatterns = [],
  cliSyntax,
  cliFlags,
}) {
  // `files:` globs stay relative (ESLint resolves them against this config's
  // directory), but the RULE options are read by the plugin at lint time
  // relative to process.cwd(). Running eslint from a workspace directory made
  // that resolve to private/account/private/account/src/... and the rule refused. Absolute here, so the config means the same thing from any cwd.
  const localesDirAbs = path.resolve(REPO_ROOT, localesDir);
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
        // ---- THE FIVE RULES THAT WERE INERT FROM BIRTH ------------------ Until 2026-08-06 these five read `node.body?.members` on an
        // @eslint/json Object node, which carries `members` DIRECTLY. They
        // walked an empty list and COULD NOT REPORT, while sitting at 'error' the whole time. The access is fixed now (one helper,
        // eslint-rules/i18n/shared/json-ast.js::objectMembers) and no rule
        // spells the walk inline any more.
        //
        // They are OFF rather than on, and that is a deliberate, reviewable choice instead of the silent inertness it replaces. Measured the moment they woke: 7245 findings after excluding the generated hash sidecars (which were themselves being linted as content - a second scoping bug this exposed, worth 4265 of an initial 11510). no-unused-keys 3773 sorted-keys 2172
        // key-naming-convention 1261 no-empty-translations 39 None of it is mechanically fixable: sorted-keys declares `fixable: 'code'` but its fixer DOES NOT CONVERGE - five --fix passes over packages/cli/src/i18n/locales/en/cli.json left 1589 findings unchanged while rewriting 3930 lines. So a fourth defect sits inside these rules, and turning them on means auditing thousands
        // of translation keys by hand, including deletions that no-unused-keys cannot prove are unused (it sees no dynamic key construction).
        //
        // Turning them on is its own wave, on its own branch, with the conventions re-decided first: the tree has never conformed to them, so 'error' was never a tested setting. Tracked, not forgotten.
        'i18n/no-empty-translations': 'off',
        'i18n/sorted-keys': 'off',
        'i18n/key-naming-convention': ['off', {
          keyFormat: 'camelCase',
          allowedPatterns: ['^[A-Z]$', '_one$', '_other$', '_zero$', '_few$', '_many$'],
        }],
        ...(cliSyntax ? { 'i18n/no-positional-cli-syntax': ['error', cliSyntax] } : {}),
        // Runs on EVERY language file, including the `en` source that the non-English block below excludes, so flag-name mangling is caught everywhere. The rule self-guards the en source where that matters.
        ...(cliFlags ? { 'i18n/cli-flag-consistency': ['error', { localesDir: localesDirAbs }] } : {}),
      },
    },
    // 2. English cross-language validation
    {
      files: [`${localesDir}/en/**/*.json`],
      ...jsonBase,
      rules: {
        'i18n/cross-language-consistency': ['error', { localesDir: localesDirAbs, sourceLanguage: 'en' }],
        'i18n/translation-coverage': ['error', { localesDir: localesDirAbs, sourceLanguage: 'en', minimumCoverage: 100 }],
        'i18n/translation-staleness': ['off', { hashFileName: '.translation-hashes.json' }],
        ...(sourceDir && unusedKeyIgnores ? {
          'i18n/no-unused-keys': ['off', { sourceDir, ignorePatterns: unusedKeyIgnores }],
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
          localesDir: localesDirAbs,
          minLength: 3,
          allowedPatterns: [...UNTRANSLATED_BASE_PATTERNS, ...extraUntranslatedPatterns],
        }],
        'i18n/interpolation-consistency': ['error', { localesDir: localesDirAbs }],
      },
    },
  ];

  return configs;
}

export default [
  // CLI i18n enforcement
  {
    files: ['packages/cli/src/**/*.{js,ts}'],
    ignores: [
      'packages/cli/src/__tests__/**',
      // P4 task-zero throwaway probe (commands/refprobe.ts): it deliberately uses hardcoded English and a positional <ref>, and w1 deletes it, so it is exempt from the CLI i18n + positional rules rather than churning 13 locales for a leaf that will not survive.
      'packages/cli/src/commands/refprobe.ts',
    ],
    plugins: {
      'i18n-source': i18nSourcePlugin,
    },
    rules: {
      // `custom/no-positional-arguments` used to live here, banning positional arguments in Commander registrations and requiring named options. P4's ref concept (spec 03 §2.2, operator ruling R-P4-1) INVERTS that: a noun's primary name is now a positional (`rdc repo up shop`), which is the whole addressing grammar the phase is built on. A rule that reds on every converted leaf is
      // not a rule that needs a longer exempt list, it is a rule
      // that is backwards, so it was deleted along with eslint-rules/
      // no-positional-arguments.js.
      //
      // The DOCS side is still guarded, and correctly: `i18n/no-positional-cli-syntax` and `custom/no-positional-cli-syntax-source` autoDerive their denylist from command-tree.json, so they flag a positional example only for a command that genuinely takes no positional. They follow the tree instead of fighting it.

      // Enforce t() for CLI-specific patterns
      'custom/no-hardcoded-cli-text': ['error'],
      'custom/require-command-summary': 'error',
      // Enforce translation keys exist in locale files
      'custom/require-translation': ['error', {
        localeDir: 'packages/cli/src/i18n/locales/en',
      }],
      // Validate string literals passed to indirect translation-key helpers (e.g., errorResult('commands.update.errors.lockFailed')) against the locale dir. Prevents raw-key leaks where the string bypasses t() and is later interpolated into a translated template.
      'custom/require-translation-key-arg': ['error', {
        localeDir: 'packages/cli/src/i18n/locales/en',
        functions: [
          { name: 'errorResult', argIndex: 0 },
        ],
      }],
      'i18n-source/interpolation-match': ['error', {
        localeDir: 'packages/cli/src/i18n/locales/en',
      }],
      // Ban positional CLI syntax in help text / error strings / JSX. Mirrors custom/i18n/no-positional-cli-syntax but for source strings.
      'custom/no-positional-cli-syntax-source': 'error',
      // Every SSH/SFTP session must come from the refcounted pool. A direct `new SFTPClient(...)` is unpooled and skips host-key verification. The pool module itself is the single exception.
      'custom/no-direct-sftp-client': ['error', {
        allow: ['src/services/machine/machine-connection.ts'],
      }],
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
  // Each package gets 3 config blocks generated by i18nLocaleConfigs(): 1. JSON linting (all languages): sorted keys, camelCase, no duplicates 2. English cross-language validation: consistency, coverage, staleness, unused keys 3. Non-English validation: untranslated values, interpolation consistency
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
    // Ban documentation/help strings that teach positional syntax for commands that actually require named options (see issue #446).
    //
    // autoDerive reads packages/cli/scripts/command-tree.json and builds the denylist from every leaf command with zero positional arguments. Keeps the rule in sync with Commander source with zero hand-editing.
    cliSyntax: {
      autoDerive: true,
      // IMPORTED, not re-listed — this was a FOURTH copy of a list that also lived in
      // scripts/lib/positional-cli-detector.ts and both ESLint rules. All four named
      // the same twelve cloud-adapter commands (`rdc auth`, `rdc organization`, …), and all twelve were DELETED WITH THE CLOUD ADAPTER. The list exempted nothing that exists, in four places, and would have silently exempted any of those names the day one came back.
      exemptCommandPrefixes: EXEMPT_COMMAND_PREFIXES,
    },
    // Ban help/description prose that references a `--flag` not registered on any rdc command (see issue #489 — `repo up --mount` did not exist). Derives the valid-flag set from packages/cli/scripts/command-tree.json. en-only (see the rule wiring above).
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
      '^(Rediacc|Stripe|Docker|Kubernetes|rdc|rediacc)$',
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
      // Certificate-number format example (public verify page placeholder) — a literal ID format, identical in every locale by design
      '^CERT-\\d{4}-\\d{4}$',
      // Recovery-code format placeholder (config-unlock input hint) — a literal format mask (RC1 prefix + four 8-char groups), product syntax with nothing to translate, identical in every locale by design. Same case as the CERT- placeholder above.
      '^RC1-X{8}-X{8}-X{8}-X{8}$',
      // Passkey: the WebAuthn/FIDO product term. German keeps the loanword ("der Passkey"), used throughout the de configStorage strings; other locales that coin a native term differ and are unaffected by this exempt.
      '^Passkey$',
      // Tag: the fork/git tag label. German keeps "Tag" (also used in "Fork-Tag"); locales that translate it differ and stay checked.
      '^Tag$',
      // Plan tier proper names (product names used as-is internationally)
      '^(Business|Community|Enterprise|Professional)$',
      // Certificate level designation ("Pro" certificate): a product-level label kept as the word "Pro" in every locale by design
      '^Pro$',
      // Clustering track label: an IT anglicism retained by several locales (de/es/fr/it/pt); mirrors ALLOWED_IDENTICAL in scripts/gates/check-translation-completeness.ts
      '^Clustering$',
      // Words that are legitimately identical in many target languages (borrowed/shared vocabulary across European languages and international tech terms)
      '^(Plan|Type|Newsletter|Name|Limit|Source|Admin|Total|Team|Status|Magnet|Machines|Code|Permissions|General|Description|Date|Dashboard|Contact|Activations|Actions)$',
      // Console table column headers (columnLabel_*): infrastructure nouns that several locales keep as loanwords/cognates rather than coin a native term, matching the SAME word already used elsewhere in this product for the identical concept (e.g. CLI locale files, or this same console.json's own nav/title labels for cluster/datastore/tag). "Commit" (git-like commit) has zero
      // established local translation in ANY of the 12 locales — every CLI translation keeps "commit" untranslated, so it is kept identical across all languages here too.
      '^Commit$',
      // "Backend" (storage backend: local/S3/etc.) — de/es/fr/it/pt keep this as a loanword, mirroring packages/cli/src/i18n/locales' own translation of the same concept ("Speicher-Backend", "backend de almacenamiento", "backend de stockage", "backend di storage", "backend de armazenamento").
      '^Backend$',
      // "Provider" (cloud provider) — Italian keeps this as a loanword, matching this same console.json file's own providersTitle ("Provider cloud").
      '^Provider$',
      // "Repository" — Italian keeps this identical (singular = plural,
      // invariant loanword), matching this same console.json file's own navRepos/reposEmpty wording ("Repository").
      '^Repository$',
      // "Destinations"/"Services" — genuine French cognates (backup destinations, Docker services), spelled identically in French and English; French CLI translations of the same concepts already keep them identical ("Destinations :", "Services :").
      '^(Destinations|Services)$',
      // "Mode" — genuine French cognate (le mode), spelled identically in both languages; no distinct native alternative in common use.
      '^Mode$',
      // "Port" (network port) — de/fr keep this as the standard technical term (no distinct native alternative in common IT usage).
      '^Port$',
      // "Pools" (resource/storage pools) — de/es/fr/pt keep the loanword "pool" and pluralize it as "Pools", matching packages/cli's own translation of the same datastore concept ("Nombre del pool", "Nom du pool", "Nome do pool").
      '^Pools$',
      // "Region"/"Image"/"Cluster"/"Datastore" — genuine German/French/ Italian cognates or established loanwords for these cloud/storage nouns; already allowlisted for the same reason in the broader scripts/gates/check-translation-completeness.ts ALLOWED_IDENTICAL set.
      '^(Region|Image|Cluster|Datastore)$',
      // IEC binary storage-unit symbols (KiB/MiB/GiB/TiB/PiB/EiB). This same file's storageQuotaHelperText key already keeps "GiB" verbatim, embedded in an otherwise fully-translated sentence, for every one of these locales (ar "بوحدة GiB. ...", de "GiB. Leer lassen ...", es "GiB. Deja en blanco ...", et "GiB. Jäta tühjaks ...", fr "GiB. Laissez vide ...", it "GiB. Lascia vuoto
      // ...", ja "GiB単位。...", ko "GiB 단위. ...", pt "GiB. Deixe em branco ...", tr "GiB. Plan varsayılanını ...", zh "以 GiB 为单位。..."). This exemption lets the standalone storageQuotaUnit label match that established sibling-key choice instead of inventing a different rendering for the same unit. ru is the one locale that transliterates to native Cyrillic ("ГиБ") in both keys,
      // already differs from English, and is unaffected by this pattern.
      '^[KMGTPE]iB$',
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
    files: [
      '**/*.generated.ts',
      '**/*.generated.tsx',
      '**/api-schema.zod.ts',
      // renet contract Zod schemas emitted by `renet functions generate-types` (DO NOT EDIT headers); they grow past max-lines as functions are added.
      '**/renet-contract/data/*.schema.ts',
    ],
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
];
