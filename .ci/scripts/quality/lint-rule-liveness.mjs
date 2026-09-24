#!/usr/bin/env node
/**
 * Lint-rule liveness, as a matrix derived from eslint.config.js itself.
 *
 * WHY A MATRIX AND NOT A LIST. The predecessor gate (see the docstring history
 * in check_lint_rule_liveness.py, which is still the entry point) proved three
 * i18n rules at one probe path and was silent about the other twenty-seven. A
 * hand-written probe list is exactly the artefact that misses a config block,
 * so the universe here is READ OUT OF THE CONFIG: every rule registered under
 * the `custom`, `i18n` and `i18n-source` plugins, and every one of those that
 * any block assigns a severity other than off. The matrix key set must EQUAL
 * the enabled set, both directions, or the run fails. A new enabled rule with
 * no specimen is `unproven`; a specimen for a rule that stopped being enabled
 * is a `stale matrix entry`.
 *
 * WHY ONE PROCESS. `npx eslint` costs ~2.05 s per lint and ~1.03 s per
 * --print-config. Thirty of those is over 90 s, which is how a gate gets
 * switched off. Everything below runs against node_modules/eslint's JS API in
 * a single process, where the second lint inside an already-warm TypeScript
 * project costs 3-40 ms.
 *
 * WHY NOTHING IS WRITTEN INTO THE REPO. 29 of the 30 specimens go through
 * `lintText`, which takes a VIRTUAL filePath (it decides which config block
 * applies) and never touches disk. Only the two cross-file locale rules need a
 * real directory, and that fixture is an OS temp dir removed in a `finally`.
 * It must NEVER be created inside a locales tree: the cross-file rules
 * enumerate languages by listing `localesDir`, so a probe directory planted
 * there becomes a fourteenth "language" for every i18n rule and for the
 * locale-set gates that derive from @rediacc/locales.
 *
 * DESIGN: agent/plans/PLAN-lint-rule-matrix-probe.md
 */

import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { minimatch } from 'minimatch';

const HERE = path.dirname(fileURLToPath(import.meta.url));
// .ci/scripts/quality/ -> repo root
const ROOT = path.resolve(HERE, '../../..');

// Several rules resolve paths against process.cwd() rather than against the linted file: require-path-option.js:24 (every i18n localesDir) and require-command-summary.js:59 (en/cli.json). A wrong cwd makes some of them throw and others silently no-op, i.e. look dead. Pin it.
process.chdir(ROOT);

export const NAMESPACES = new Set(['custom', 'i18n', 'i18n-source']);

// Floors. Today the config resolves 35 registered / 30 enabled. These leave room for a deliberate removal and none at all for the config resolving to nothing, which is the failure that would otherwise exit 0 while proving nothing -- indistinguishable from a healthy repo.
const MIN_REGISTERED = 30;
const MIN_ENABLED = 25;
// Directory representatives the .tsx/.jsx reachability sweep must find (§6.3).
const MIN_JSX_DIRS = 10;

// --------------------------------------------------------------------------- Registered but enabled nowhere, by an explicit and documented decision.
// The banner at eslint.config.js:104-137 records why (7245 findings on waking,
// plus a fixer that does not converge). This map must EQUAL registered-minus- enabled exactly, so a FUTURE rule that becomes registered-but-never-enabled -- dead wiring, the way custom/no-raw-api-calls was before it was deleted -- cannot slip in unremarked. ---------------------------------------------------------------------------
const KNOWN_OFF = {
  'i18n/sorted-keys':
    "off since 2026-08-06: 2172 findings on waking, and its 'fixable' fixer does not converge",
  'i18n/no-unused-keys':
    'off since 2026-08-06: 3773 findings, and it cannot see dynamically constructed keys',
  'i18n/key-naming-convention':
    'off since 2026-08-06: 1261 findings; the tree has never conformed to the convention',
  'i18n/no-empty-translations': 'off since 2026-08-06: 39 findings, part of the same wave',
  'i18n/translation-staleness':
    'off since 2026-08-06: same wave, needs the hash sidecars re-scoped',
};

// --------------------------------------------------------------------------- Enabled, alive as code, and unable to report on any file that exists. This is a DISTINCT failure from a dead rule and it is recorded rather than hidden: the gate stays green, the finding stays written down. --------------------------------------------------------------------------- EMPTY ON PURPOSE, and
// it should stay that way.
//
// `custom/require-testid` lived here until 2026-08-15: it was 'error' on the js/jsx/ts/tsx glob while every tree containing JSX switched it off, so it protected ZERO files. The operator's answer was to ENABLE it rather than keep documenting the exception. Measured before the change: packages/www reports 0 findings across its 28 .tsx/.jsx files, so that tree was switched
// on immediately and for free; private/account/** stays off pending a sweep of
// its 287 findings across 68 files, tracked as its own item.
//
// The gate caught the staleness itself the moment www was enabled -- it refused
// with STALE KNOWN_UNREACHABLE rather than letting a documented exception
// outlive the condition that justified it. Adding an entry here is declaring
// that a rule protects nothing; it needs a reason with the same evidence.
const KNOWN_UNREACHABLE = {};

/**
 * Minimum .tsx/.jsx directories a rule must still reach.
 *
 * WHY A FLOOR AND NOT JUST "REACHABLE". A rule can regress from protecting the
 * tree to protecting a corner WITHOUT becoming unreachable: switch it off for
 * one tree and the count falls but stays above zero, so the UNREACHABLE verdict
 * never fires and the rule reads as healthy. Measured 2026-08-15,
 * `custom/require-testid` reached 0 -> 3 (www enabled) -> 27 (account-web swept
 * and enabled, 292 attributes added). The floor sits below 27 on purpose: adding
 * or removing a component directory must not fail the gate, but switching a
 * whole tree back off must.
 */
const REACH_FLOOR = { 'custom/require-testid': 20 };

// --------------------------------------------------------------------------- Specimens that read a live value out of the tree.
//
// A stale specimen going silent reads EXACTLY like a dead rule, and that false accusation is the thing this gate exists to avoid. Each of these entries therefore carries a `precondition` that runs BEFORE the lint and, when it fails, produces its own message saying so in as many words. ---------------------------------------------------------------------------
const readJson = (rel) => JSON.parse(fs.readFileSync(path.join(ROOT, rel), 'utf8'));

const EN_CLI = 'packages/cli/src/i18n/locales/en/cli.json';
const EN_TRANSCRIPT =
  'packages/www/src/data/tutorial-transcripts/en/tutorial-storage-management.json';

/** Zero-positional leaves of command-tree.json, the same classification the two
 *  positional-syntax rules do (no-positional-cli-syntax-source.js:63-72). */
let leafCache = null;
const zeroPositionalLeaves = () => {
  if (leafCache) return leafCache;
  const tree = readJson('packages/cli/scripts/command-tree.json');
  const leaves = new Set();
  const freeform = new Set(['run']);
  const walk = (node, parts) => {
    if (parts.length > 0) {
      const commandPath = parts.join(' ');
      const isLeaf = (node.subcommands ?? []).length === 0;
      const takesPositional = (node.arguments ?? []).length > 0;
      if (isLeaf && !takesPositional && !freeform.has(commandPath)) leaves.add(commandPath);
    }
    for (const sub of node.subcommands ?? []) walk(sub, [...parts, sub.name]);
  };
  walk(tree, []);
  leafCache = leaves;
  return leaves;
};

const EN_CLI_DESCRIPTION = 'Manage machines, repositories, and deployments over SSH';
const EN_TRANSCRIPT_TEXT =
  'Fill the repository most of the way and check: the filesystem is getting tight.';

const preconditions = {
  commandSummaryTooLong: () => {
    const value = readJson(EN_CLI).commands?.cluster?.description;
    if (typeof value !== 'string') {
      return `${EN_CLI} no longer has commands.cluster.description`;
    }
    // require-command-summary.js:125 -> maxSummary = 100 (no options at eslint.config.js:605)
    if (value.length <= 100) {
      return `commands.cluster.description is now ${value.length} chars, at or under the 100-char summary limit, so nothing can be reported`;
    }
    return null;
  },
  configLoadedHasDuration: () => {
    const value = readJson(EN_CLI).timing?.step?.configLoaded;
    if (typeof value !== 'string') return `${EN_CLI} no longer has timing.step.configLoaded`;
    if (!value.includes('{{duration}}')) {
      return `timing.step.configLoaded is now ${JSON.stringify(value)} and no longer carries {{duration}}, so a call with no interpolation is not a mismatch`;
    }
    return null;
  },
  repoListIsZeroPositionalLeaf: () => {
    if (!zeroPositionalLeaves().has('repo list')) {
      return '"repo list" is no longer a zero-positional leaf in packages/cli/scripts/command-tree.json, so it is not on the derived denylist';
    }
    return null;
  },
  configCurrentIsZeroPositionalLeaf: () => {
    if (!zeroPositionalLeaves().has('config current')) {
      return '"config current" is no longer a zero-positional leaf in packages/cli/scripts/command-tree.json, so it is not on the derived denylist';
    }
    return null;
  },
  cliDescriptionKeyExists: () => {
    if (typeof readJson(EN_CLI).cli?.description !== 'string') {
      return `${EN_CLI} no longer has cli.description, and cli-flag-consistency only checks key paths that exist in the English source`;
    }
    return null;
  },
  cliDescriptionMatchesSpecimen: () => {
    const value = readJson(EN_CLI).cli?.description;
    if (value !== EN_CLI_DESCRIPTION) {
      return `${EN_CLI} cli.description is now ${JSON.stringify(value)}; the specimen copies the OLD English text, so it is no longer byte-identical and no-untranslated-values has nothing to report`;
    }
    return null;
  },
  transcriptTextMatchesSpecimen: () => {
    const value = readJson(EN_TRANSCRIPT).events?.[0]?.text;
    if (value !== EN_TRANSCRIPT_TEXT) {
      return `${EN_TRANSCRIPT} events[0].text is now ${JSON.stringify(value)}; the specimen copies the OLD English text, so it is no longer byte-identical`;
    }
    return null;
  },
};

// --------------------------------------------------------------------------- The matrix.
//
// `filePath` is a VIRTUAL path handed to lintText. It decides which config block applies, so it must sit exactly where the enabling glob matches -- and the gate re-checks that with calculateConfigForFile rather than trusting it, because `packages/www/src/i18n/translations/*.json` is a SINGLE star and a path one directory deeper resolves zero rules while looking like five dead
// ones.
//
// `mode`: in-config - real severity, real options, no override. The strongest proof. option-dir - real path and severity, `localesDir` redirected at a temp fixture, because these two rules never read the linted text.
//   isolated   - own ESLint instance; the only mode for a rule that reports on
// the FILENAME, since no violating filename exists on disk and a virtual .ts path is rejected by the typed-linting projectService. ---------------------------------------------------------------------------
const MATRIX = {
  // -- packages/cli/src/commands/backup.ts ---------------------------------
  'custom/no-direct-sftp-client': {
    filePath: 'packages/cli/src/commands/backup.ts',
    code: 'export const c = new SFTPClient();\n',
    // The `allow` list (no-direct-sftp-client.js:38, set at eslint.config.js:631)
    // exempts machine-connection.ts, so the probe must not be that file.
  },
  'custom/no-hardcoded-cli-text': {
    filePath: 'packages/cli/src/commands/backup.ts',
    // The string must contain a space, or shouldIgnore treats it as an identifier.
    code: 'declare const outputService: any;\noutputService.success("Backup completed successfully");\n',
  },
  'custom/require-command-summary': {
    filePath: 'packages/cli/src/commands/backup.ts',
    code: 'declare const cmd: any;\ndeclare const t: any;\ncmd.description(t("commands.cluster.description"));\n',
    precondition: preconditions.commandSummaryTooLong,
  },
  'custom/require-translation': {
    filePath: 'packages/cli/src/commands/backup.ts',
    // The `cli:` namespace prefix is load-bearing: an unprefixed key resolves no namespace and the rule returns silently.
    code: 'declare const t: any;\nt("cli:zz.nope");\n',
  },
  'custom/require-translation-key-arg': {
    filePath: 'packages/cli/src/commands/backup.ts',
    // Function name and arg index come from eslint.config.js:616-621.
    code: 'declare const errorResult: any;\nerrorResult("zz.nope.absent");\n',
  },
  'custom/no-positional-cli-syntax-source': {
    filePath: 'packages/cli/src/commands/backup.ts',
    code: 'export const s = "rdc repo list <name>";\n',
    precondition: preconditions.repoListIsZeroPositionalLeaf,
  },
  'i18n-source/interpolation-match': {
    filePath: 'packages/cli/src/commands/backup.ts',
    code: 'declare const t: any;\nt("cli:timing.step.configLoaded");\n',
    precondition: preconditions.configLoadedHasDuration,
  },

  // -- packages/shared/src/index.ts ----------------------------------------
  'custom/no-duplicate-translation-props': {
    filePath: 'packages/shared/src/index.ts',
    code: 'type TypedTFunction = (k: string) => string;\nexport interface P { t: TypedTFunction; tC: TypedTFunction; }\n',
  },
  'custom/prefer-const-arrays': {
    filePath: 'packages/shared/src/index.ts',
    // Must be UPPER_SNAKE_CASE, all-literal, no `as const`, and in a .ts --
    // the rule is off for **/*.js at eslint.config.js:1265.
    code: 'export const A_B = ["x"];\n',
  },
  'custom/no-hardcoded-nullish-defaults': {
    filePath: 'packages/shared/src/index.ts',
    // 22 avoids the allowlist at eslint.config.js:410-432 (0, 1, -1, 13 strings).
    code: 'export const f = (y?: number) => y ?? 22;\n',
  },

  // -- eslint-rules/zz-probe.js (JSX in a .js path) ------------------------
  'custom/require-testid': {
    filePath: 'eslint-rules/zz-probe.js',
    // `Modal` is in requiredElements at eslint.config.js:437. This co-fires
    // react/jsx-no-undef and no-undef, which is harmless: the assertion is per rule id. See KNOWN_UNREACHABLE -- this is the ONLY shape that can fire, and no real file in the repo has it.
    code: 'export const A = () => <Modal />;\n',
  },

  // -- private/account/web/src/pages/Activity.tsx --------------------------
  'custom/no-hardcoded-text': {
    filePath: 'private/account/web/src/pages/Activity.tsx',
    code: 'export const A = () => <div>Hello world</div>;\n',
  },

  // -- private/account/src/routes/configs.ts -------------------------------
  'custom/no-unawaited-drizzle-terminator': {
    filePath: 'private/account/src/routes/configs.ts',
    code: 'declare const db: any;\ndeclare const tbl: any;\nexport function go() { db.select().from(tbl).all(); }\n',
  },

  // -- packages/www/src/components/AccountCta.tsx --------------------------
  'custom/require-data-track': {
    filePath: 'packages/www/src/components/AccountCta.tsx',
    code: 'export const X = () => <a href="/en/docs">Docs</a>;\n',
  },
  'custom/seo-no-vague-anchor-text': {
    filePath: 'packages/www/src/components/AccountCta.tsx',
    // data-track keeps require-data-track quiet; a dynamic child would silence
    // this rule instead.
    code: 'export const X = () => <a href="/en/docs" data-track="x">Click here</a>;\n',
  },
  'custom/seo-require-img-alt': {
    filePath: 'packages/www/src/components/AccountCta.tsx',
    code: 'export const X = () => <img src="/a.png" />;\n',
  },
  'custom/seo-no-hash-breadcrumb-url': {
    filePath: 'packages/www/src/components/AccountCta.tsx',
    // THE VARIABLE NAME IS THE TRAP: the rule only looks inside an array whose declarator id matches /breadcrumb/i, so the identical object under any other name is silent.
    code: 'const breadcrumbItems = [{ name: "S", url: "/en/#solutions" }];\nexport default breadcrumbItems;\n',
  },
  'custom/seo-no-trailing-slash-internal-link': {
    filePath: 'packages/www/src/components/AccountCta.tsx',
    // The path must not start with an exempt prefix (/account/, /api/, ...).
    code: 'export const X = () => <a href="/en/docs/" data-track="x">Docs</a>;\n',
  },

  // -- packages/www/src/i18n/translations/tr.json -------------------------- Key SHAPE matters as much as content: seo-title-length only looks at paths ending ".meta.title" (seo-title-length.js:53), seo-description-length at ".meta.description" (:51), and seo-no-duplicate-h1-title compares a sibling "hero.title" against "meta.title". Right text under the wrong key is silent, and
  // reads exactly like a dead rule.
  'i18n/seo-title-length': {
    filePath: 'packages/www/src/i18n/translations/tr.json',
    code: JSON.stringify({ pages: { x: { meta: { title: 'uzun baslik '.repeat(12) } } } }, null, 2),
  },
  'i18n/seo-description-length': {
    filePath: 'packages/www/src/i18n/translations/tr.json',
    code: JSON.stringify(
      { pages: { x: { meta: { description: 'cok uzun aciklama '.repeat(20) } } } },
      null,
      2
    ),
  },
  'i18n/seo-no-duplicate-h1-title': {
    filePath: 'packages/www/src/i18n/translations/tr.json',
    code: JSON.stringify(
      {
        pages: { x: { meta: { title: 'Yedekleme Cozumu' }, hero: { title: 'Yedekleme Cozumu' } } },
      },
      null,
      2
    ),
  },

  // -- tutorial transcripts -------------------------------------------------
  'i18n/no-untranslated-tutorial-transcript-values': {
    // The value must be byte-identical to events[0].text of the English cast of
    // the SAME basename, and the rule returns {} for en/ (:80).
    filePath: 'packages/www/src/data/tutorial-transcripts/tr/tutorial-storage-management.json',
    code: JSON.stringify({ events: [{ text: EN_TRANSCRIPT_TEXT }] }, null, 2),
    precondition: preconditions.transcriptTextMatchesSpecimen,
  },

  // -- packages/cli/src/i18n/locales/en/cli.json ---------------------------
  'i18n/no-positional-cli-syntax': {
    filePath: EN_CLI,
    code: JSON.stringify({ cli: { description: 'rdc config current <name>' } }, null, 2),
    precondition: preconditions.configCurrentIsZeroPositionalLeaf,
  },
  'i18n/no-undefined-cli-flags': {
    filePath: EN_CLI,
    // exemptFlags / exemptKeyPrefixes are both empty at eslint.config.js:701-704.
    code: JSON.stringify({ cli: { description: 'Use --zzz-not-a-flag now' } }, null, 2),
  },

  // -- packages/cli/src/i18n/locales/tr/cli.json ---------------------------
  'i18n/cli-flag-consistency': {
    filePath: 'packages/cli/src/i18n/locales/tr/cli.json',
    // The key path must EXIST in the real en/cli.json; the rule returns {} for en/.
    code: JSON.stringify({ cli: { description: 'Makineleri --current-ita ile yonet' } }, null, 2),
    precondition: preconditions.cliDescriptionKeyExists,
  },
  'i18n/no-untranslated-values': {
    filePath: 'packages/cli/src/i18n/locales/tr/cli.json',
    // Byte-identical to en AND must survive the allowlist at eslint.config.js:46-81
    // plus :670-687, which exempts anything with a dot, colon, at-sign or placeholder. cli.description is one of the few en values that qualifies.
    code: JSON.stringify({ cli: { description: EN_CLI_DESCRIPTION } }, null, 2),
    precondition: preconditions.cliDescriptionMatchesSpecimen,
  },
  'i18n/interpolation-consistency': {
    filePath: 'packages/cli/src/i18n/locales/tr/cli.json',
    // The nested key path must mirror en exactly; the same string at a flat key
    // is silent. Rule returns {} for en/.
    code: JSON.stringify({ timing: { step: { configLoaded: 'Yapilandirma yuklendi' } } }, null, 2),
    precondition: preconditions.configLoadedHasDuration,
  },

  // -- option-override mode ------------------------------------------------- These two never read the linted text beyond a type check: they read English off DISK from localesDir. A text-based liveness probe scores them dead while
  // they work. Probe path and severity stay real; only localesDir moves.
  'i18n/cross-language-consistency': {
    filePath: EN_CLI,
    code: JSON.stringify({ a: 'x', b: 'y' }, null, 2),
    mode: 'option-dir',
    options: (dir) => ({ localesDir: dir, sourceLanguage: 'en' }),
  },
  'i18n/translation-coverage': {
    filePath: EN_CLI,
    code: JSON.stringify({ a: 'x', b: 'y' }, null, 2),
    mode: 'option-dir',
    options: (dir) => ({ localesDir: dir, sourceLanguage: 'en', minimumCoverage: 100 }),
  },

  // -- isolated mode --------------------------------------------------------
  'custom/e2e-test-naming-convention': {
    // Reports purely on the BASENAME (e2e-test-naming-convention.js:51/:76) and self-guards to paths containing packages/e2e-tests/tests (:62). No violating filename exists on disk -- the repo's files all conform, which is the rule doing its job -- and a virtual .ts path is rejected outright by the typed-linting projectService (allowDefaultProject covers only scripts/*.ts and
    // packages/locales/*.js), which returns a FATAL parse error and runs zero rules. So the firing half runs in an isolated instance carrying only this rule and a plain TS parser, and the enabled half is proven separately with calculateConfigForFile against a REAL e2e test. The two together are the same claim the other 29 get in
    // one step. Do not "simplify" this into the in-config mode; it cannot work.
    filePath: 'packages/e2e-tests/tests/zz_Bad-Name.test.ts',
    code: 'export const x = 1;\n',
    mode: 'isolated',
    enabledAt: 'packages/e2e-tests/tests/01-system-checks.test.ts',
    controlCode: 'export const x = 1;\n',
  },

  // Net-new host-only ports (PLAN-biome-only-lint.md's rule map): NEITHER of
  // these two ruleIds was ever registered in eslint.config.js, so there is no
  // real ESLint config to resolve severity against at any path -- isolated
  // mode is the only mode that can work here, same reasoning as the entry
  // above, just for a rule with no ESLint history at all rather than one a
  // typed-linting parse error rules out.
  'custom/no-unused-underscore-var': {
    filePath: 'packages/shared/src/index.ts',
    code: 'const _biomeLivenessProbe = 1;\n',
    mode: 'isolated',
    enabledAt: 'packages/shared/src/index.ts',
    controlCode: 'const _biomeLivenessProbe = 1;\nconsole.log(_biomeLivenessProbe);\n',
  },
  'custom/e2e-expect-expect': {
    filePath: 'packages/e2e-tests/tests/zz_expect_probe.test.ts',
    code: "test('probe', async () => {\n  console.log('no assertion');\n});\n",
    mode: 'isolated',
    enabledAt: 'packages/e2e-tests/tests/zz_expect_probe.test.ts',
    controlCode: "test('probe', async () => {\n  expect(1).toBe(1);\n});\n",
  },
};

// Rules that can only ever report on JSX. "Enabled somewhere" is not the same as "can ever report", and this is the check that tells those apart.
const REQUIRES_JSX = new Set([
  'custom/require-testid',
  'custom/no-hardcoded-text',
  'custom/require-data-track',
  'custom/seo-no-vague-anchor-text',
  'custom/seo-require-img-alt',
]);

// --------------------------------------------------------------------------- Helpers ---------------------------------------------------------------------------
const err = (...args) => console.error(...args);

const severityOf = (value) => {
  const raw = Array.isArray(value) ? value[0] : value;
  if (raw === 'off' || raw === 0 || raw === undefined) return 0;
  if (raw === 'warn') return 1;
  if (raw === 'error') return 2;
  return typeof raw === 'number' ? raw : 0;
};

/**
 * The universe used to come from walking eslint.config.js's `plugins`/`rules`
 * blocks (last-match-wins across 6 modules). It now comes from
 * `scripts/data/source-rules.ts`'s flat `RULE_IDS` -- the same table
 * `check-source-rules.ts` (the host gate) runs against the real tree -- via
 * `sourceRulesUniverse()` below. `NAMESPACES` stays as documentation of which
 * plugin prefixes this gate ever covers.
 *
 * Pulling the registered rule OBJECT for isolated mode used to mean digging
 * `block.plugins[ns].rules[name]` out of an eslint.config.js block. It is now
 * a plain `import()` of the module path `RULE_INSTANCES` already records for
 * that rule -- `ruleModuleExport()` below -- since a `RuleInstance` carries
 * `modulePath`/`exportName` for exactly this purpose.
 */
async function sourceRulesUniverse() {
  const mod = await import(path.join(ROOT, 'scripts/data/source-rules.ts'));
  return { RULE_IDS: mod.RULE_IDS, RULE_INSTANCES: mod.RULE_INSTANCES };
}

/** Every `.js` rule module file under eslint-rules/, excluding helpers and tests:
 *  the filesystem-truth half of dead-wiring detection now that there is no
 *  ESLint plugin registration to walk. A file here that is neither wired into
 *  `RULE_INSTANCES` (enabled) nor in `KNOWN_OFF_MODULES` (parked, documented)
 *  is exactly the old "registered but enabled by no block" defect, just
 *  detected from disk instead of from eslint.config.js. */
const RULE_FILE_SKIP_DIRS = new Set(['lib', 'shared', '__tests__']);
const RULE_FILE_SKIP_NAMES = new Set(['index.js', 'translation-helpers.js']);
function allRuleModuleFiles(dir) {
  const out = [];
  const walk = (d) => {
    for (const entry of fs.readdirSync(d, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (RULE_FILE_SKIP_DIRS.has(entry.name)) continue;
        walk(path.join(d, entry.name));
      } else if (entry.name.endsWith('.js') && !RULE_FILE_SKIP_NAMES.has(entry.name)) {
        out.push(path.relative(ROOT, path.join(d, entry.name)).split(path.sep).join('/'));
      }
    }
  };
  walk(dir);
  return out.sort();
}

/** modulePath for each of KNOWN_OFF's 5 rules. `source-rules.ts`'s own docstring
 *  says it deliberately excludes rules that are off everywhere, so these do not
 *  appear in RULE_INSTANCES and must be listed here instead, same as KNOWN_OFF
 *  itself is a hand-kept, deliberately-friction list. */
const KNOWN_OFF_MODULES = {
  'i18n/sorted-keys': 'eslint-rules/i18n/sorted-keys.js',
  'i18n/no-unused-keys': 'eslint-rules/i18n/no-unused-keys.js',
  'i18n/key-naming-convention': 'eslint-rules/i18n/key-naming-convention.js',
  'i18n/no-empty-translations': 'eslint-rules/i18n/no-empty-translations.js',
  'i18n/translation-staleness': 'eslint-rules/i18n/translation-staleness.js',
};

const firedRuleIds = (results) => {
  const fired = new Set();
  const fatals = [];
  for (const result of results) {
    for (const message of result.messages ?? []) {
      if (message.fatal) fatals.push(message.message);
      if (message.ruleId) fired.add(message.ruleId);
    }
  }
  return { fired, fatals };
};

/** Recursive .tsx/.jsx sweep, one representative per (directory, extension). */
const SKIP_DIRS = new Set(['node_modules', '.git', 'dist', 'build', '.next', 'coverage', '.astro']);
const jsxCandidates = (dir, out) => {
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue;
      jsxCandidates(full, out);
    } else if (entry.name.endsWith('.tsx') || entry.name.endsWith('.jsx')) {
      // Config is path-scoped, so one file per directory-and-extension decides.
      const key = `${dir}\0${path.extname(entry.name)}`;
      if (!out.has(key)) out.set(key, path.relative(ROOT, full));
    }
  }
  return out;
};

// --------------------------------------------------------------------------- Biome half: every GritQL plugin under biome-plugins/ must fire on a planted violation. Biome has no in-memory lint API, and GritQL plugins only evaluate when the CLI target is the project root `.` -- linting a subdirectory or a single file silently runs zero plugins (measured, see .ci/cache/biome-parity/biome-counts.md's "Environmental note", point 1). So the specimens are REAL files, run with `biome lint .` from a project root -- but that root is a MIRROR in an OS temp dir, never the repo itself. The mirror carries the repo's own biome.json VERBATIM and every biome-plugins/*.grit, and each fixture sits at the SAME repo-relative path it would have in the real tree, so each plugin's real `includes` is evaluated against the real path shape. Nothing is written into the shared tree, so a hard kill (which skips every `finally`) cannot leave a planted file or an append to a tracked file behind, and the gate needs no `tree:repo` mutex.
// WHY NOT THE REAL TREE (wave 2 did that, verify3 VERDICT.md N2): it created 7 files, 2 of them in the private/account submodule, and APPENDED to the tracked private/account/src/services/email.service.ts, restoring it only in a `finally`. Under the parallel pool, any reader of the tree saw the planted files; after a SIGKILL the append stayed.
// WHAT KEEPS THE MIRROR HONEST: a fixture's directory must exist in the real tree (a moved or renamed directory fails here instead of being silently invented in the mirror), and an `append` fixture starts from the real file's current content (read, never written).
// ---------------------------------------------------------------------------
const BIOME_BIN = path.join(ROOT, 'node_modules', '.bin', 'biome');

// `var(--ant-` assembled from two pieces: written as one literal, this gate's own source is a no-ant-css-var violation (verify3 VERDICT.md N4 -- `biome lint .` counted 2 errors here).
const ANT_CSS_VAR_PREFIX = ['var(', '--ant-'].join('');

// One specimen per file in biome-plugins/. Adding a plugin without adding one here is caught below (missing/stale fixture check), the same discipline the
// ESLint-side MATRIX enforces against RULE_IDS.
const BIOME_PLUGIN_FIXTURES = [
  {
    plugin: 'no-d1-transaction',
    file: 'private/account/src/__biome_plugin_liveness_d1.ts',
    mode: 'create',
    code: 'export async function __biomePluginLivenessD1(db: any) {\n  await db.transaction(async () => {\n    return 1;\n  });\n}\n',
    message: 'db.transaction() is not supported on D1. Use sequential awaited operations instead.',
  },
  {
    plugin: 'no-route-db-dynamic-import',
    file: 'private/account/src/routes/__biome_plugin_liveness_route.ts',
    mode: 'create',
    code: "export async function __biomePluginLivenessRoute() {\n  return await import('../db/client');\n}\n",
    message: 'Dynamic imports from the database layer are not allowed in routes.',
  },
  {
    // This plugin's own `includes` names one file, not a directory glob, so the specimen is an append to the MIRROR's copy of the real file (the real file is only read): no other path is in this plugin's scope at all. Four arguments, the shape every real call site has.
    plugin: 'no-email-literal-copy',
    file: 'private/account/src/services/email.service.ts',
    mode: 'append',
    code: "\nexport function __biomePluginLivenessEmail(svc: any, to: string, r: any) {\n  svc.sendEmail(to, 'Subject line', r.html, r.text);\n}\n",
    message:
      'Do not hardcode email copy in EmailService. Render subject/html/text via translated email templates.',
  },
  {
    plugin: 'no-constant-alias',
    file: 'scripts/__biome_plugin_liveness_constant_alias.ts',
    mode: 'create',
    code: 'const LAYOUT = { HEADER_HEIGHT: 10 };\nexport const aliasVar = LAYOUT.HEADER_HEIGHT;\n',
    message:
      'Do not create local aliases from constants. Use the original property access directly (e.g. LAYOUT.HEADER_HEIGHT instead of const X = LAYOUT.HEADER_HEIGHT).',
  },
  {
    plugin: 'no-ant-css-var',
    file: 'scripts/__biome_plugin_liveness_ant_css_var.ts',
    mode: 'create',
    code: `export const cssVar = '${ANT_CSS_VAR_PREFIX}primary-color)';\n`,
    message: `Do not use CSS variables (${ANT_CSS_VAR_PREFIX}*)). Remove color styling or use Ant Design component props instead.`,
  },
  {
    plugin: 'no-t-default-value',
    file: 'scripts/__biome_plugin_liveness_t_default.ts',
    mode: 'create',
    code: "declare function t(key: string, opts?: unknown): string;\nt('k', { defaultValue: 'x' });\n",
    message:
      'Do not use defaultValue in translation calls. Add the key to English translation JSON files instead.',
  },
  {
    plugin: 'no-inline-style-prop',
    file: 'packages/cli/src/__biome_plugin_liveness_inline_style.tsx',
    mode: 'create',
    code: 'export const BiomePluginLivenessInlineStyle = () => <div className="x" style={{ color: "red" }} />;\n',
    message:
      'Inline styles are not allowed. Use CSS utility classes from global.css or Ant Design component props instead.',
  },
  {
    plugin: 'no-exported-type-alias',
    file: 'scripts/__biome_plugin_liveness_exported_alias.ts',
    mode: 'create',
    code: 'type BiomePluginLivenessBase = { a: number };\nexport type BiomePluginLivenessAlias = BiomePluginLivenessBase;\n',
    message:
      'Do not create type aliases. Use the original type directly instead of creating an alias.',
  },
];

/** Run `biome lint .` and parse its (experimental) JSON reporter. Biome exits 1
 *  when diagnostics are present -- that is the expected, successful case here,
 *  not a launch failure -- so stdout is read off the error too. */
function biomeLintJson(cwd) {
  let stdout = '';
  try {
    stdout = execFileSync(BIOME_BIN, ['lint', '.', '--reporter=json', '--max-diagnostics=none'], {
      cwd,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
      maxBuffer: 1024 * 1024 * 64,
    });
  } catch (e) {
    if (typeof e.stdout === 'string' && e.stdout.length > 0) {
      stdout = e.stdout;
    } else {
      throw new Error(`biome lint (cwd=${cwd}) did not run at all: ${e.message}`);
    }
  }
  try {
    return JSON.parse(stdout);
  } catch (parseErr) {
    throw new Error(
      `biome --reporter=json produced non-JSON stdout (cwd=${cwd}): ${parseErr.message}\n` +
        stdout.slice(0, 1000)
    );
  }
}

/** Every GritQL diagnostic reports category "plugin" regardless of which
 *  plugin fired it, so a fixture is identified by its (path, exact message)
 *  pair, not by category. */
function pluginFired(result, relFile, message) {
  const posixFile = relFile.split(path.sep).join('/');
  return (result.diagnostics ?? []).some(
    (d) => d.category === 'plugin' && d.location?.path === posixFile && d.message === message
  );
}

/** Write one fixture at its repo-relative path inside the mirror. Returns why it could not be planted, or null. The real tree is only READ: an `append` fixture starts from the real file's current content, and a fixture whose directory the real tree no longer has is refused rather than invented. */
async function plantInMirror(mirrorRoot, fx) {
  const realAbs = path.join(ROOT, fx.file);
  const mustExist = fx.mode === 'append' ? realAbs : path.dirname(realAbs);
  if (!fs.existsSync(mustExist))
    return `${fx.plugin}: ${path.relative(ROOT, mustExist)} does not exist in the real tree`;
  const mirrorAbs = path.join(mirrorRoot, fx.file);
  await fs.promises.mkdir(path.dirname(mirrorAbs), { recursive: true });
  const base = fx.mode === 'append' ? await fs.promises.readFile(realAbs, 'utf8') : '';
  await fs.promises.writeFile(mirrorAbs, base + fx.code, 'utf8');
  return null;
}

/** Every fixture planted in ONE temp mirror carrying the verbatim biome.json and every plugin, one `biome lint .` over it. */
async function probeBiomePlugins(gritPlugins) {
  const dead = [];
  const missingDirs = [];
  const mirrorRoot = await fs.promises.mkdtemp(path.join(os.tmpdir(), 'biome-plugin-liveness-'));
  try {
    await fs.promises.copyFile(path.join(ROOT, 'biome.json'), path.join(mirrorRoot, 'biome.json'));
    await fs.promises.mkdir(path.join(mirrorRoot, 'biome-plugins'), { recursive: true });
    for (const plugin of gritPlugins) {
      await fs.promises.copyFile(
        path.join(ROOT, 'biome-plugins', `${plugin}.grit`),
        path.join(mirrorRoot, 'biome-plugins', `${plugin}.grit`)
      );
    }
    const planted = [];
    for (const fx of BIOME_PLUGIN_FIXTURES) {
      const refusal = await plantInMirror(mirrorRoot, fx);
      if (refusal) missingDirs.push(refusal);
      else planted.push(fx);
    }
    const result = biomeLintJson(mirrorRoot);
    for (const fx of planted) {
      if (!pluginFired(result, fx.file, fx.message)) dead.push(fx.plugin);
    }
  } finally {
    await fs.promises.rm(mirrorRoot, { recursive: true, force: true });
  }
  return { dead, missingDirs };
}

async function runBiomePluginLiveness() {
  const gritPlugins = fs
    .readdirSync(path.join(ROOT, 'biome-plugins'))
    .filter((f) => f.endsWith('.grit'))
    .map((f) => f.slice(0, -'.grit'.length))
    .sort();
  const fixturePlugins = BIOME_PLUGIN_FIXTURES.map((f) => f.plugin).sort();
  const missingFixtures = gritPlugins.filter((g) => !fixturePlugins.includes(g));
  const staleFixtures = fixturePlugins.filter((f) => !gritPlugins.includes(f));
  const complete = missingFixtures.length === 0 && staleFixtures.length === 0;
  const { dead, missingDirs } = complete
    ? await probeBiomePlugins(gritPlugins)
    : { dead: [], missingDirs: [] };
  const controlFailures = await runBiomeControl();
  return {
    missingFixtures,
    staleFixtures,
    missingDirs,
    dead,
    controlFailures,
    total: BIOME_PLUGIN_FIXTURES.length,
  };
}

async function runBiomeControl() {
  // ------------------------------------------------------------------------- CONTROL, inline on every run like the ESLint-half controls above: an
  // isolated mirror where one plugin's `includes` is broken so it cannot match any real path. The same fixture that fires above must stay silent here, or this checker cannot tell firing from dead, and every "fired" verdict above would be unfalsifiable. -------------------------------------------------------------------------
  const controlFailures = [];
  const control = BIOME_PLUGIN_FIXTURES[0]; // no-d1-transaction
  const mirrorRoot = await fs.promises.mkdtemp(path.join(os.tmpdir(), 'biome-plugin-control-'));
  try {
    await fs.promises.mkdir(path.join(mirrorRoot, 'biome-plugins'), { recursive: true });
    await fs.promises.copyFile(
      path.join(ROOT, 'biome-plugins', `${control.plugin}.grit`),
      path.join(mirrorRoot, 'biome-plugins', `${control.plugin}.grit`)
    );
    await fs.promises.writeFile(
      path.join(mirrorRoot, 'biome.json'),
      JSON.stringify({
        linter: { enabled: true },
        files: { includes: ['**/*.ts'], ignoreUnknown: true },
        plugins: [
          {
            path: `biome-plugins/${control.plugin}.grit`,
            // Deliberately broken: no real path under this mirror can ever match.
            includes: ['**/__biome-plugin-liveness-unreachable__/**'],
          },
        ],
      })
    );
    const fixtureAbs = path.join(mirrorRoot, control.file);
    await fs.promises.mkdir(path.dirname(fixtureAbs), { recursive: true });
    await fs.promises.writeFile(fixtureAbs, control.code, 'utf8');

    const controlResult = biomeLintJson(mirrorRoot);
    if (pluginFired(controlResult, control.file, control.message)) {
      controlFailures.push(
        `${control.plugin} fired in the control mirror despite an includes pattern that cannot ` +
          'match any real path. This checker cannot tell a firing plugin from a dead one, so ' +
          'every "fired" verdict above would be unfalsifiable.'
      );
    }
  } finally {
    await fs.promises.rm(mirrorRoot, { recursive: true, force: true });
  }

  return controlFailures;
}

/** Print every Biome-half failure; true when there was one. Each section: its findings, a header, how one finding prints, and an optional closing line. */
function reportBiomeHalf(biomeHalf) {
  const sections = [
    [
      biomeHalf.missingFixtures,
      `${biomeHalf.missingFixtures.length} GritQL plugin(s) under biome-plugins/ have no fixture in BIOME_PLUGIN_FIXTURES, so nothing proves they can fire:`,
      (plugin) => `    ${plugin}.grit`,
    ],
    [
      biomeHalf.staleFixtures,
      `${biomeHalf.staleFixtures.length} stale BIOME_PLUGIN_FIXTURES entry(ies): a fixture for a plugin no longer under biome-plugins/:`,
      (plugin) => `    ${plugin}`,
    ],
    [
      biomeHalf.dead,
      `${biomeHalf.dead.length} GritQL plugin(s) did NOT fire on a violation planted at its real repo-relative path under the real biome.json (in a temp mirror):`,
      (plugin) => `    ${plugin}.grit`,
      '  Fix the plugin or its biome.json `includes` -- do not lower its scope to hide this.',
    ],
    [
      biomeHalf.missingDirs,
      `${biomeHalf.missingDirs.length} GritQL fixture(s) name a path the real tree no longer has:`,
      (line) => `    ${line}`,
      "  Move the fixture to where the plugin's `includes` now points, or fix the `includes`.",
    ],
    [
      biomeHalf.controlFailures,
      'BIOME CONTROL FAILED: this checker cannot distinguish a firing plugin from a dead one.',
      (line) => `    ${line}`,
      'Refusing a verdict. Every "fired" result above would be unfalsifiable.',
    ],
  ];
  let failed = false;
  for (const [items, header, format, footer] of sections) {
    if (items.length === 0) continue;
    failed = true;
    err(header);
    for (const item of items) err(format(item));
    if (footer) err(footer);
  }
  return failed;
}

// --------------------------------------------------------------------------- Main ---------------------------------------------------------------------------
async function main() {
  const started = Date.now();
  // Bare specifiers: this file lives inside the repo, so Node's resolver walks up to the repo's own node_modules. The launcher has already proven it exists.
  const { ESLint } = await import('eslint');
  const { RULE_IDS, RULE_INSTANCES, GLOBAL_IGNORES } = await sourceRulesUniverse();

  if (!Array.isArray(RULE_IDS) || !Array.isArray(RULE_INSTANCES)) {
    err(
      'VACUOUS INPUT: scripts/data/source-rules.ts did not export RULE_IDS/RULE_INSTANCES arrays'
    );
    return 1;
  }

  const enabled = new Set(RULE_IDS);
  const registered = new Set([...enabled, ...Object.keys(KNOWN_OFF)]);

  // Is `ruleId` enabled at `relPath`, per source-rules.ts's OWN files/ignores -- not eslint.config.js's. This replaces `calculateConfigForFile` for the enablement check below: a rule this table lists never existed in eslint.config.js at all (both `custom/e2e-expect-expect` and `custom/no-unused-underscore-var` are net-new host-only ports), so asking the real ESLint config whether it is "on" always says no, regardless of path -- the wrong tool now that source-rules.ts is the universe.
  //
  // ONE ruleId CAN HAVE SEVERAL RuleInstance entries (source-rules.ts's own docstring: "one entry per (rule, effective scope, effective options) triple"), e.g. `custom/no-positional-cli-syntax-source` has a separate instance for the CLI tree, the account-web tree and the www tree. A path is enabled for the rule if it matches ANY of that rule's instances, so this groups by ruleId into an ARRAY rather than keeping only the last one -- a `Map` built straight from `[ruleId, instance]` pairs silently drops every instance but the last for a rule with more than one, which read as "not enabled" for every OTHER instance's own paths.
  const ruleInstancesById = new Map();
  for (const instance of RULE_INSTANCES) {
    const list = ruleInstancesById.get(instance.ruleId) ?? [];
    list.push(instance);
    ruleInstancesById.set(instance.ruleId, list);
  }
  const globalIgnores = Array.isArray(GLOBAL_IGNORES) ? GLOBAL_IGNORES : [];
  function isEnabledAtPath(ruleId, relPath) {
    const instances = ruleInstancesById.get(ruleId);
    if (!instances || instances.length === 0) return false;
    const posix = relPath.split(path.sep).join('/');
    if (globalIgnores.some((g) => minimatch(posix, g))) return false;
    return instances.some((info) => {
      if (!info.files.some((g) => minimatch(posix, g))) return false;
      return !(info.ignores ?? []).some((g) => minimatch(posix, g));
    });
  }

  if (registered.size < MIN_REGISTERED) {
    err(
      `VACUOUS INPUT: only ${registered.size} rule(s) known between scripts/data/source-rules.ts's\n` +
        `RULE_IDS and this file's KNOWN_OFF (floor ${MIN_REGISTERED}). A table that resolves to\n` +
        'nothing proves nothing and exits 0, which is exactly what a healthy repo looks like.'
    );
    return 1;
  }
  if (enabled.size < MIN_ENABLED) {
    err(
      `VACUOUS INPUT: only ${enabled.size} of ${registered.size} known rule(s) are enabled\n` +
        `(RULE_IDS, floor ${MIN_ENABLED}). Proving a handful of rules live while the rest are off\n` +
        'is not evidence the rule set works.'
    );
    return 1;
  }

  // DEAD-WIRING CONTROL, from disk rather than from an ESLint plugin walk: a
  // rule module that exists under eslint-rules/ but is wired into neither
  // RULE_INSTANCES (enabled) nor KNOWN_OFF_MODULES (parked, documented) is the
  // same defect the eslint.config.js walk used to catch -- an import behind a
  // rule nobody runs -- just found by scanning the files instead of the config.
  const wiredModules = new Set(RULE_INSTANCES.map((r) => r.modulePath));
  const ruleFiles = allRuleModuleFiles(path.join(ROOT, 'eslint-rules'));
  const knownOffModulePaths = new Set(Object.values(KNOWN_OFF_MODULES));
  const undocumented = ruleFiles.filter((f) => !wiredModules.has(f) && !knownOffModulePaths.has(f));
  const knownOff = Object.keys(KNOWN_OFF).sort();
  const staleKnownOffModules = Object.entries(KNOWN_OFF_MODULES)
    .filter(([ruleId]) => !(ruleId in KNOWN_OFF))
    .map(([ruleId]) => ruleId);
  const missingKnownOffFiles = Object.entries(KNOWN_OFF_MODULES).filter(
    ([, modulePath]) => !fs.existsSync(path.join(ROOT, modulePath))
  );
  if (undocumented.length > 0) {
    err(
      `${undocumented.length} rule module file(s) under eslint-rules/ are wired into NEITHER\n` +
        "scripts/data/source-rules.ts's RULE_INSTANCES nor this file's KNOWN_OFF_MODULES. That is\n" +
        'dead wiring: a rule file nobody runs. Either add it to source-rules.ts (and a matrix\n' +
        'specimen here) or delete it; if it is deliberately parked, add it to KNOWN_OFF and\n' +
        'KNOWN_OFF_MODULES with the reason.'
    );
    for (const file of undocumented) err(`    ${file}`);
    return 1;
  }
  if (staleKnownOffModules.length > 0) {
    err(
      `${staleKnownOffModules.length} KNOWN_OFF_MODULES entry(ies) name a ruleId no longer in\n` +
        'KNOWN_OFF. Keep both maps in sync, or drop the entry if the rule was deleted.'
    );
    for (const rule of staleKnownOffModules) err(`    ${rule}`);
    return 1;
  }
  if (missingKnownOffFiles.length > 0) {
    err(
      `${missingKnownOffFiles.length} KNOWN_OFF_MODULES entry(ies) name a file that no longer exists:`
    );
    for (const [rule, modulePath] of missingKnownOffFiles) err(`    ${rule} -> ${modulePath}`);
    err('  The rule was deleted; drop it from both KNOWN_OFF and KNOWN_OFF_MODULES.');
    return 1;
  }

  // SET EQUALITY against the matrix, both directions.
  const matrixKeys = new Set(Object.keys(MATRIX));
  const unproven = [...enabled].filter((r) => !matrixKeys.has(r)).sort();
  const stale = [...matrixKeys].filter((r) => !enabled.has(r)).sort();
  if (unproven.length > 0) {
    err(
      `${unproven.length} enabled rule(s) have no specimen here, so nothing proves they can fire:`
    );
    for (const rule of unproven) err(`    ${rule}`);
    err('  Add one to MATRIX: a probe path inside the enabling glob, and input that MUST trip it.');
  }
  if (stale.length > 0) {
    err(
      `${stale.length} stale matrix entry(ies): a specimen for a rule no longer enabled anywhere:`
    );
    for (const rule of stale) err(`    ${rule}`);
    err('  Either re-enable the rule, or move it to KNOWN_OFF with a written reason.');
  }
  if (unproven.length > 0 || stale.length > 0) return 1;

  const eslint = new ESLint({ cwd: ROOT });

  // ------------------------------------------------------------------------- The temp fixture for the two cross-file locale rules. NEVER inside a locales tree: those rules enumerate languages by listing localesDir, so a directory planted there becomes a fourteenth language for every i18n rule and for the locale-set gates that read @rediacc/locales.
  // -------------------------------------------------------------------------
  const fixtureRoot = await fs.promises.mkdtemp(path.join(os.tmpdir(), 'lint-liveness-'));
  try {
    const asymmetric = path.join(fixtureRoot, 'asymmetric');
    const symmetric = path.join(fixtureRoot, 'symmetric');
    for (const [dir, en, tr] of [
      // tr is MISSING "b" -> both rules must fire.
      [asymmetric, { a: 'x', b: 'y' }, { a: 'x' }],
      // Same key set, different values -> both rules must stay silent. The English side has to shrink too: leaving en at two keys here makes the "control" fixture asymmetric and the control fires, which is how the first draft of this file discovered its own bug.
      [symmetric, { a: 'x' }, { a: 'y' }],
    ]) {
      await fs.promises.mkdir(path.join(dir, 'en'), { recursive: true });
      await fs.promises.mkdir(path.join(dir, 'tr'), { recursive: true });
      await fs.promises.writeFile(path.join(dir, 'en', 'cli.json'), JSON.stringify(en));
      await fs.promises.writeFile(path.join(dir, 'tr', 'cli.json'), JSON.stringify(tr));
    }

    const optionRules = [...matrixKeys].filter((r) => MATRIX[r].mode === 'option-dir');
    const optionInstance = (dir) =>
      new ESLint({
        cwd: ROOT,
        overrideConfig: {
          rules: Object.fromEntries(optionRules.map((r) => [r, ['error', MATRIX[r].options(dir)]])),
        },
      });

    // --------------------------------------------------------------------- CONTROLS. One per execution mode, all inline on every run, none behind a flag: a mode nobody remembers to run is how a control stops controlling anything. If any of these FIRES, the harness cannot tell firing from not firing and every verdict below it is meaningless.
    // ---------------------------------------------------------------------
    const controlFailures = [];

    // 1. in-config mode: sorted-keys on already-sorted input (severity forced on, since the rule is off by documented decision).
    {
      const probe = new ESLint({
        cwd: ROOT,
        overrideConfig: { rules: { 'i18n/sorted-keys': 'error' } },
      });
      const { fired } = firedRuleIds(
        await probe.lintText(JSON.stringify({ a: '1', b: '2' }, null, 2), {
          filePath: path.join(ROOT, 'packages/www/src/i18n/translations/tr.json'),
          warnIgnored: false,
        })
      );
      if (fired.has('i18n/sorted-keys')) {
        controlFailures.push("in-config: i18n/sorted-keys 'fired' on ALREADY-SORTED input");
      }
    }

    // 2. option-override mode: a SYMMETRIC fixture must silence both.
    {
      const probe = optionInstance(symmetric);
      const { fired } = firedRuleIds(
        await probe.lintText(JSON.stringify({ a: 'x', b: 'y' }, null, 2), {
          filePath: path.join(ROOT, EN_CLI),
          warnIgnored: false,
        })
      );
      for (const rule of optionRules) {
        if (fired.has(rule)) {
          controlFailures.push(`option-override: ${rule} 'fired' on a SYMMETRIC locale fixture`);
        }
      }
    }

    // 3. isolated mode: a conforming/clean specimen must stay silent, for
    // EVERY isolated-mode rule. Originally just custom/e2e-test-naming-
    // convention; now also the two net-new host-only ports that never
    // existed in eslint.config.js at all (custom/e2e-expect-expect,
    // custom/no-unused-underscore-var), which is why this loop is generic
    // over `matrixKeys` rather than one hard-coded rule.
    const isolatedRuleIds = [...matrixKeys]
      .filter((r) => (MATRIX[r].mode ?? 'in-config') === 'isolated')
      .sort();
    const isolatedRules = {};
    for (const ruleId of isolatedRuleIds) {
      if (!ruleId.startsWith('custom/')) {
        err(`${ruleId}: isolated mode only supports the 'custom' namespace today (this file's`);
        err('  isolated ESLint instance registers everything under one "custom" plugin object).');
        return 1;
      }
      const info = ruleInstancesById.get(ruleId)?.[0];
      const ruleModule = info
        ? (await import(path.join(ROOT, info.modulePath)))[info.exportName]
        : null;
      if (!ruleModule) {
        err(
          `${ruleId} has no RULE_INSTANCES entry (or its module has no ` +
            `${info?.exportName ?? '<unknown>'} export), so the isolated probe has nothing to run.`
        );
        return 1;
      }
      isolatedRules[ruleId.slice('custom/'.length)] = ruleModule;
    }
    const tsParser = await import('@typescript-eslint/parser');
    const isolated = new ESLint({
      cwd: ROOT,
      overrideConfigFile: true,
      overrideConfig: {
        files: ['**/*.ts'],
        languageOptions: { parser: tsParser.default ?? tsParser },
        plugins: { custom: { rules: isolatedRules } },
        rules: Object.fromEntries(isolatedRuleIds.map((r) => [r, 'error'])),
      },
    });
    for (const ruleId of isolatedRuleIds) {
      const entry = MATRIX[ruleId];
      if (entry.controlCode === undefined) continue;
      const { fired } = firedRuleIds(
        await isolated.lintText(entry.controlCode, {
          filePath: path.join(ROOT, entry.enabledAt),
          warnIgnored: false,
        })
      );
      if (fired.has(ruleId)) {
        controlFailures.push(`isolated: ${ruleId} fired on a CONFORMING/clean specimen`);
      }
    }

    if (controlFailures.length > 0) {
      err('CONTROL FAILED: this harness cannot distinguish firing from not firing.');
      for (const line of controlFailures) err(`    ${line}`);
      err('Refusing a verdict. Every "the rule fired" below would be unfalsifiable.');
      return 1;
    }

    // --------------------------------------------------------------------- The matrix run. ---------------------------------------------------------------------
    const dead = [];
    const specimenStale = [];
    const didNotParse = [];
    const notEnabledAtProbe = [];

    const optionProbe = optionInstance(asymmetric);

    for (const ruleId of [...matrixKeys].sort()) {
      const entry = MATRIX[ruleId];
      const mode = entry.mode ?? 'in-config';

      // Precondition FIRST. A stale specimen going silent is indistinguishable
      // from a dead rule, and calling it dead is a false accusation.
      if (entry.precondition) {
        const problem = entry.precondition();
        if (problem) {
          specimenStale.push([ruleId, problem]);
          continue;
        }
      }

      // Is the rule actually on at the probe path, per source-rules.ts's own
      // files/ignores? "Enabled in some block" is a candidate, not a
      // verdict: two of these ruleIds have no eslint.config.js entry at all
      // to ask calculateConfigForFile instead.
      const enablementPath = mode === 'isolated' ? entry.enabledAt : entry.filePath;
      if (!isEnabledAtPath(ruleId, enablementPath)) {
        notEnabledAtProbe.push([ruleId, enablementPath]);
        continue;
      }

      const instance =
        mode === 'option-dir' ? optionProbe : mode === 'isolated' ? isolated : eslint;
      const { fired, fatals } = firedRuleIds(
        await instance.lintText(entry.code, {
          filePath: path.join(ROOT, entry.filePath),
          warnIgnored: false,
        })
      );
      if (!fired.has(ruleId) && fatals.length > 0) {
        didNotParse.push([ruleId, entry.filePath, fatals[0]]);
        continue;
      }
      if (!fired.has(ruleId)) dead.push(ruleId);
    }

    // --------------------------------------------------------------------- Reachability. For a rule that can only report on JSX, "enabled" is not "can ever report": require-testid is 'error' repo-wide and protects zero files, because every tsx/jsx path in the tree turns it off. ---------------------------------------------------------------------
    const candidates = [...jsxCandidates(ROOT, new Map()).values()];
    // A sweep over zero files declares every JSX rule unreachable, and one of them is SUPPOSED to be unreachable, so the degenerate case would look partly correct. Floor it. Today: ~30 directory representatives.
    if (candidates.length < MIN_JSX_DIRS) {
      err(
        `VACUOUS INPUT: the JSX sweep found only ${candidates.length} directory representative(s)\n` +
          `(floor ${MIN_JSX_DIRS}). Over an empty candidate set every JSX-only rule reads as\n` +
          'unreachable, which is the same answer a correct sweep gives for one of them.'
      );
      return 1;
    }
    const reach = new Map([...REQUIRES_JSX].map((r) => [r, 0]));
    for (const rel of candidates) {
      const abs = path.join(ROOT, rel);
      if (await eslint.isPathIgnored(abs)) continue;
      const cfg = await eslint.calculateConfigForFile(abs);
      for (const rule of REQUIRES_JSX) {
        if (severityOf(cfg.rules?.[rule]) > 0) reach.set(rule, reach.get(rule) + 1);
      }
    }
    const unreachable = [...reach].filter(([, n]) => n === 0).map(([r]) => r);
    const newlyUnreachable = unreachable.filter((r) => !(r in KNOWN_UNREACHABLE));
    const nowReachable = Object.keys(KNOWN_UNREACHABLE).filter((r) => !unreachable.includes(r));

    // --------------------------------------------------------------------- Verdicts. Each shape gets its OWN message, because "dead" is the one accusation that must never be made loosely. ---------------------------------------------------------------------
    if (specimenStale.length > 0) {
      for (const [ruleId, problem] of specimenStale) {
        err(
          `SPECIMEN STALE: ${ruleId}: ${problem}.\n` +
            '  Update the specimen; this is NOT evidence the rule is dead.'
        );
      }
    }
    if (didNotParse.length > 0) {
      for (const [ruleId, file, message] of didNotParse) {
        err(
          `SPECIMEN DID NOT PARSE: ${ruleId} at ${file}: ${message}\n` +
            '  A fatal parse error runs ZERO rules, so this says nothing about the rule.'
        );
      }
    }
    if (notEnabledAtProbe.length > 0) {
      for (const [ruleId, file] of notEnabledAtProbe) {
        err(
          `PROBE PATH DOES NOT ENABLE THIS RULE: ${ruleId} resolves to severity 0 at ${file}.\n` +
            '  The specimen would be silent no matter how broken or healthy the rule is.\n' +
            '  Move the probe inside a path the enabling glob actually matches.'
        );
      }
    }
    if (dead.length > 0) {
      err(`${dead.length} ENABLED rule(s) did NOT fire on a violation they are supposed to catch:`);
      for (const rule of dead) err(`    ${rule}`);
      err(
        '  That is the sorted-keys defect again: enabled, and structurally unable to report.\n' +
          '  Fix the rule -- do not lower its severity to hide this.'
      );
    }
    if (newlyUnreachable.length > 0) {
      for (const rule of newlyUnreachable) {
        err(
          `ENABLED BUT UNREACHABLE: ${rule} is enabled but resolves to severity 0 at every\n` +
            '  real .tsx/.jsx path in the tree, and it can only report on JSX. It protects no file.\n' +
            '  Enable it where JSX actually lives, or turn it off and say so.'
        );
      }
    }
    if (nowReachable.length > 0) {
      for (const rule of nowReachable) {
        err(
          `STALE KNOWN_UNREACHABLE: ${rule} now resolves above severity 0 in ${reach.get(rule)}\n` +
            '  real .tsx/.jsx directory(ies) in the tree, so it can reach a file.\n' +
            '  Drop it from KNOWN_UNREACHABLE; the documented exception no longer applies.'
        );
      }
    }
    const belowFloor = [];
    for (const [rule, floor] of Object.entries(REACH_FLOOR)) {
      const got = reach.get(rule) ?? 0;
      if (got >= floor) continue;
      belowFloor.push(rule);
      err(
        `REACH REGRESSED: ${rule} now reaches only ${got} .tsx/.jsx directory(ies), below its\n` +
          `  floor of ${floor}. The UNREACHABLE check above cannot catch this: switching a rule\n` +
          '  off for ONE tree drops its coverage while leaving the count above zero, so the rule\n' +
          '  keeps "protecting" a corner of the repo and reads as healthy. That is the exact state\n' +
          "  require-testid sat in until 2026-08-15 -- 'error' repo-wide, off in both trees that\n" +
          '  contain JSX, protecting ZERO files. Re-enable the tree that was switched off, or\n' +
          '  lower the floor DELIBERATELY and say why here.'
      );
    }

    // ------------------------------------------------------------------- The biome half. Independent of everything above (it needs no ESLint
    // instance and no eslint.config.js), run here so one invocation gives one
    // combined verdict instead of two gates to remember to run. -------------------------------------------------------------------------
    const biomeHalf = await runBiomePluginLiveness();
    const biomeFailed = reportBiomeHalf(biomeHalf);

    if (
      specimenStale.length > 0 ||
      didNotParse.length > 0 ||
      notEnabledAtProbe.length > 0 ||
      dead.length > 0 ||
      newlyUnreachable.length > 0 ||
      nowReachable.length > 0 ||
      belowFloor.length > 0 ||
      biomeFailed
    ) {
      return 1;
    }

    const elapsed = ((Date.now() - started) / 1000).toFixed(1);
    console.log(
      `${matrixKeys.size} enabled custom/i18n rule(s) each fired on a planted violation ` +
        `(${registered.size} registered, ${knownOff.length} off by documented decision, ` +
        `${Object.keys(KNOWN_UNREACHABLE).length} enabled-but-unreachable and recorded); ` +
        `${2 + isolatedRuleIds.length} negative controls stayed silent; ${elapsed}s`
    );
    // The reach counts are printed rather than merely asserted: a reader can see at a glance that the sweep resolved real files, instead of taking a silent pass as proof that it ran.
    console.log(
      `  JSX reachability over ${candidates.length} directory representative(s): ` +
        [...reach].map(([r, n]) => `${r.replace('custom/', '')}=${n}`).join(', ')
    );
    for (const [rule, reason] of Object.entries(KNOWN_UNREACHABLE)) {
      console.log(`  RECORDED, not fixed: ${rule} -- ${reason}`);
    }
    console.log(
      `${biomeHalf.total} GritQL plugin(s) under biome-plugins/ each fired on a planted violation ` +
        'at its real repo-relative path under the verbatim biome.json, in a temp mirror (nothing written to the ' +
        'tree); 1 control (a broken `includes`) stayed silent.'
    );
    return 0;
  } finally {
    // ALWAYS, including on an exception: the fixture is outside the repo, but a leaked temp tree is still litter and the cleanup path must not depend on the happy path being taken.
    await fs.promises.rm(fixtureRoot, { recursive: true, force: true });
  }
}

process.exitCode = await main();
