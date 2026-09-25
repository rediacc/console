#!/usr/bin/env tsx
/**
 * The host gate for `eslint-rules/`: runs the SAME rule modules `scripts/data/source-rules.ts` describes, over the real tree, without ESLint.
 *
 * WHY THIS IS SAFE TO TRUST. PLAN-biome-only-lint.md Phase 0 recorded, while ESLint still runs the real config: (a) ESLint's own resolved config for every tracked path, filtered to the rule ids this gate owns, and (b) the `(file, line, column, ruleId)` tuples ESLint reports on HEAD and on one planted defect per rule -- the same probes `.ci/scripts/quality/lint-rule-liveness.mjs` uses, reused here rather than re-invented. `--differential <dir>` replays those same probes through `scripts/lib/rule-host.ts` and the same whole-tree corpus, and diffs the tuples byte for byte against that saved snapshot. `--config-differential <dir>` checks the OTHER half of the same claim -- not just "same findings" but "same rule turned on, with the same options, on the same paths" -- by diffing `matchingInstances()` against (a)'s snapshot directly, with exactly two documented exceptions (see `isExplainedScopeMismatch` and `fillBenignDefaults`) rather than a silent tolerance.
 *
 * SUPPRESSION REFUSAL. `reportUnusedDisableDirectives` dies with ESLint, and nothing else in this repo's toolchain understands an `eslint-disable` comment once it does. Rather than let one sit inert and misleading, this gate refuses ANY `eslint-disable`/`eslint-enable` token left in the files it scans -- the refusal the rule map (row 130) assigns this gate.
 *
 * ---- gate ----
 * step: Source-authored lint rules, host-run
 * needs: node
 * selftest: true
 * lane: quality-code
 * why: eslint-rules/ has no type-aware or esquery-dependent rule (finding #4 of PLAN-biome-only-lint.md), so it can run on a small host instead of ESLint; nothing else proves the host and the rules still agree with what ESLint reported before ESLint is retired.
 * ---- end gate ----
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

import { runSourceRule, runJsonRule, type RuleModule, type Finding } from '../lib/rule-host.ts';
import {
  RULE_INSTANCES,
  RULE_IDS,
  isGloballyIgnored,
  matchesEslintGlob,
  type RuleInstance,
} from '../data/source-rules.ts';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

// Mirrors eslint-rules/__tests__/config-resolution-differential.mjs's own corpus definition, so this gate's tuples and the Phase 0 snapshot are drawn from the identical file set.
const LINT_ROOTS = [
  'packages',
  'scripts',
  'private/account',
  'eslint-rules',
  '.ci',
  'workers',
  '.github/actions',
];
const LINTABLE = new Set(['.ts', '.tsx', '.mts', '.cts', '.js', '.jsx', '.cjs', '.mjs', '.json']);

function trackedFiles(root: string): string[] {
  const abs = path.join(REPO_ROOT, root);
  if (!fs.existsSync(abs)) return [];
  const isSubmodule = fs.existsSync(path.join(abs, '.git'));
  const cwd = isSubmodule ? abs : REPO_ROOT;
  const args = isSubmodule ? ['ls-files'] : ['ls-files', '--', root];
  const out = execFileSync('git', args, { cwd, encoding: 'utf8', maxBuffer: 256 * 1024 * 1024 });
  return out
    .split('\n')
    .filter(Boolean)
    .map((rel) => (isSubmodule ? path.posix.join(root, rel) : rel));
}

/** Every tracked, lintable, non-globally-ignored path, POSIX-separated and sorted. */
export function corpus(): string[] {
  const seen = new Set<string>();
  for (const root of LINT_ROOTS) {
    for (const rel of trackedFiles(root)) {
      const posix = rel.split(path.sep).join('/');
      if (!LINTABLE.has(path.extname(posix))) continue;
      if (isGloballyIgnored(posix)) continue;
      seen.add(posix);
    }
  }
  return [...seen].sort();
}

/** Every instance whose `files`/`ignores` resolve `posixPath` in scope. */
export function matchingInstances(posixPath: string): RuleInstance[] {
  return RULE_INSTANCES.filter(
    (inst) =>
      inst.files.some((g) => matchesEslintGlob(posixPath, g)) &&
      !(inst.ignores ?? []).some((g) => matchesEslintGlob(posixPath, g))
  );
}

const moduleCache = new Map<string, Promise<Record<string, unknown>>>();

async function loadRuleModule(modulePath: string, exportName: string): Promise<RuleModule> {
  const abs = path.join(REPO_ROOT, modulePath);
  let mod = moduleCache.get(abs);
  if (!mod) {
    mod = import(abs) as Promise<Record<string, unknown>>;
    moduleCache.set(abs, mod);
  }
  const resolved = await mod;
  const rule = resolved[exportName];
  if (!rule) throw new Error(`check-source-rules: ${modulePath} has no export "${exportName}"`);
  return rule as RuleModule;
}

export interface TaggedFinding extends Finding {
  ruleId: string;
  file: string;
}

/** Lint one real file against every instance in scope for it. */
export async function lintFile(posixPath: string): Promise<TaggedFinding[]> {
  const instances = matchingInstances(posixPath);
  if (instances.length === 0) return [];
  const abs = path.join(REPO_ROOT, posixPath);
  const code = fs.readFileSync(abs, 'utf8');
  const out: TaggedFinding[] = [];
  for (const instance of instances) {
    const rule = await loadRuleModule(instance.modulePath, instance.exportName);
    const run = { filename: abs, cwd: REPO_ROOT, options: instance.options ?? [] };
    const findings =
      instance.kind === 'json' ? runJsonRule(rule, code, run) : runSourceRule(rule, code, run);
    for (const f of findings) out.push({ ...f, ruleId: instance.ruleId, file: posixPath });
  }
  return out;
}

async function runWholeTree(): Promise<TaggedFinding[]> {
  const all: TaggedFinding[] = [];
  for (const rel of corpus()) all.push(...(await lintFile(rel)));
  return all;
}

const DISABLE_TOKEN = /\/[/*]\s*eslint-(disable|enable)/;

/** Every scanned file carrying a now-inert `eslint-disable`/`eslint-enable` comment. */
function findStaleDirectives(paths: string[]): string[] {
  return paths.filter((rel) => {
    if (!/\.(ts|tsx|js|jsx)$/.test(rel)) return false;
    return DISABLE_TOKEN.test(fs.readFileSync(path.join(REPO_ROOT, rel), 'utf8'));
  });
}

// PLANTED PROBES, one per host rule id. Ported from the specimens in `.ci/scripts/quality/lint-rule-liveness.mjs`'s MATRIX (same repository facts, same files, same "must trip it" inputs), adapted to call the host instead of ESLint. A precondition guards every specimen that reads a live value out of the tree, exactly as the source it was ported from does: a stale specimen going silent must be reported as STALE, never as "the rule is dead".

interface Probe {
  ruleId: string;
  kind: 'source' | 'json';
  modulePath: string;
  exportName: string;
  filePath: string;
  /** The buggy input. Must trip the rule. */
  bad: string;
  /** A clean sibling. Must NOT trip the rule. */
  good: string;
  options?: unknown[];
  precondition?: () => string | null;
  /**
   * Overrides for the GREEN half only. Needed by the two option-dir rules
   * (`cross-language-consistency`, `translation-coverage`), which read their
   * source-language file straight off disk rather than from the linted text:
   * the fixture path itself has to change to a symmetric sibling, not just
   * the string handed to the linter.
   */
  goodFilePath?: string;
  goodOptions?: unknown[];
}

function readJson(rel: string): Record<string, unknown> {
  return JSON.parse(fs.readFileSync(path.join(REPO_ROOT, rel), 'utf8')) as Record<string, unknown>;
}

const EN_CLI = 'packages/cli/src/i18n/locales/en/cli.json';
const EN_TRANSCRIPT =
  'packages/www/src/data/tutorial-transcripts/en/tutorial-storage-management.json';

function keyPath(obj: unknown, dotted: string): unknown {
  return dotted
    .split('.')
    .reduce<unknown>(
      (cur, seg) =>
        cur && typeof cur === 'object' ? (cur as Record<string, unknown>)[seg] : undefined,
      obj
    );
}

/** Two on-disk locale fixtures for the two rules that read `localesDir` directly rather than the linted text: one asymmetric (both rules must fire), one symmetric (both must stay silent). Built once, reused across probes and by `selftest`'s GREEN half. */
function localeFixtures(): { asymmetric: string; symmetric: string } {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'check-source-rules-'));
  const write = (dir: string, en: object, tr: object) => {
    fs.mkdirSync(path.join(dir, 'en'), { recursive: true });
    fs.mkdirSync(path.join(dir, 'tr'), { recursive: true });
    fs.writeFileSync(path.join(dir, 'en', 'cli.json'), JSON.stringify(en));
    fs.writeFileSync(path.join(dir, 'tr', 'cli.json'), JSON.stringify(tr));
  };
  const asymmetric = path.join(root, 'asymmetric');
  const symmetric = path.join(root, 'symmetric');
  write(asymmetric, { a: 'x', b: 'y' }, { a: 'x' });
  write(symmetric, { a: 'x' }, { a: 'y' });
  return { asymmetric, symmetric };
}

const FIXTURES = localeFixtures();

interface CommandTreeNode {
  name?: string;
  subcommands?: CommandTreeNode[];
  arguments?: unknown[];
}

function buildProbes(): Probe[] {
  const commandTree = readJson(
    'packages/cli/scripts/command-tree.json'
  ) as unknown as CommandTreeNode;
  const isZeroPositionalLeaf = (target: string): boolean => {
    const leaves = new Set<string>();
    const walk = (node: CommandTreeNode, parts: string[]): void => {
      if (parts.length > 0) {
        const isLeaf = (node.subcommands ?? []).length === 0;
        const takesPositional = (node.arguments ?? []).length > 0;
        if (isLeaf && !takesPositional && parts.join(' ') !== 'run') leaves.add(parts.join(' '));
      }
      for (const sub of node.subcommands ?? []) walk(sub, [...parts, sub.name ?? '']);
    };
    walk(commandTree, []);
    return leaves.has(target);
  };

  return [
    {
      ruleId: 'custom/no-direct-sftp-client',
      kind: 'source',
      modulePath: 'eslint-rules/no-direct-sftp-client.js',
      exportName: 'noDirectSftpClient',
      filePath: 'packages/cli/src/commands/backup.ts',
      bad: 'export const c = new SFTPClient();\n',
      good: 'export const c = 1;\n',
      options: [{ allow: ['src/services/machine/machine-connection.ts'] }],
    },
    {
      ruleId: 'custom/no-hardcoded-cli-text',
      kind: 'source',
      modulePath: 'eslint-rules/no-hardcoded-cli-text.js',
      exportName: 'noHardcodedCliText',
      filePath: 'packages/cli/src/commands/backup.ts',
      bad: 'declare const outputService: any;\noutputService.success("Backup completed successfully");\n',
      good: 'declare const outputService: any;\ndeclare const t: any;\noutputService.success(t("cli:ok"));\n',
    },
    {
      ruleId: 'custom/require-command-summary',
      kind: 'source',
      modulePath: 'eslint-rules/require-command-summary.js',
      exportName: 'requireCommandSummary',
      filePath: 'packages/cli/src/commands/backup.ts',
      bad: 'declare const cmd: any;\ndeclare const t: any;\ncmd.description(t("commands.cluster.description"));\n',
      good: 'declare const cmd: any;\ncmd.description("short");\n',
      precondition: () => {
        const value = keyPath(readJson(EN_CLI), 'commands.cluster.description');
        if (typeof value !== 'string' || value.length <= 100)
          return `${EN_CLI} commands.cluster.description is no longer >100 chars`;
        return null;
      },
    },
    {
      ruleId: 'custom/require-translation',
      kind: 'source',
      modulePath: 'eslint-rules/require-translation.js',
      exportName: 'requireTranslation',
      filePath: 'packages/cli/src/commands/backup.ts',
      bad: 'declare const t: any;\nt("cli:zz.nope");\n',
      good: 'declare const t: any;\nt("cli:cli.description");\n',
      options: [{ localeDir: CLI_EN }],
    },
    {
      ruleId: 'custom/require-translation-key-arg',
      kind: 'source',
      modulePath: 'eslint-rules/require-translation-key-arg.js',
      exportName: 'requireTranslationKeyArg',
      filePath: 'packages/cli/src/commands/backup.ts',
      bad: 'declare const errorResult: any;\nerrorResult("zz.nope.absent");\n',
      good: 'declare const errorResult: any;\nerrorResult("cli.description");\n',
      options: [{ localeDir: CLI_EN, functions: [{ name: 'errorResult', argIndex: 0 }] }],
    },
    {
      ruleId: 'custom/no-positional-cli-syntax-source',
      kind: 'source',
      modulePath: 'eslint-rules/no-positional-cli-syntax-source.js',
      exportName: 'noPositionalCliSyntaxSource',
      filePath: 'packages/cli/src/commands/backup.ts',
      bad: 'export const s = "rdc repo list <name>";\n',
      good: 'export const s = "rdc repo list --name <name>";\n',
      precondition: () =>
        isZeroPositionalLeaf('repo list')
          ? null
          : '"repo list" is no longer a zero-positional leaf in command-tree.json',
    },
    {
      ruleId: 'i18n-source/interpolation-match',
      kind: 'source',
      modulePath: 'eslint-rules/i18n/interpolation-match.js',
      exportName: 'interpolationMatch',
      filePath: 'packages/cli/src/commands/backup.ts',
      bad: 'declare const t: any;\nt("cli:timing.step.configLoaded");\n',
      good: 'declare const t: any;\nt("cli:timing.step.configLoaded", { duration: 1 });\n',
      options: [{ localeDir: CLI_EN }],
      precondition: () => {
        const value = keyPath(readJson(EN_CLI), 'timing.step.configLoaded');
        if (typeof value !== 'string' || !value.includes('{{duration}}'))
          return `${EN_CLI} timing.step.configLoaded no longer carries {{duration}}`;
        return null;
      },
    },
    {
      ruleId: 'custom/no-duplicate-translation-props',
      kind: 'source',
      modulePath: 'eslint-rules/no-duplicate-translation-props.js',
      exportName: 'noDuplicateTranslationProps',
      filePath: 'packages/shared/src/index.ts',
      bad: 'type TypedTFunction = (k: string) => string;\nexport interface P { t: TypedTFunction; tC: TypedTFunction; }\n',
      good: 'type TypedTFunction = (k: string) => string;\nexport interface P { t: TypedTFunction; }\n',
    },
    {
      ruleId: 'custom/prefer-const-arrays',
      kind: 'source',
      modulePath: 'eslint-rules/prefer-const-arrays.js',
      exportName: 'preferConstArrays',
      filePath: 'packages/shared/src/index.ts',
      bad: 'export const A_B = ["x"];\n',
      good: 'export const A_B = ["x"] as const;\n',
    },
    {
      ruleId: 'custom/no-hardcoded-nullish-defaults',
      kind: 'source',
      modulePath: 'eslint-rules/no-hardcoded-nullish-defaults.js',
      exportName: 'noHardcodedNullishDefaults',
      filePath: 'packages/shared/src/index.ts',
      bad: 'export const f = (y?: number) => y ?? 22;\n',
      good: 'export const f = (y?: number) => y ?? 1;\n',
      options: [
        { allowZero: true, allowNegativeOne: true, allowedNumbers: [1], allowedStrings: [] },
      ],
    },
    {
      ruleId: 'custom/require-testid',
      kind: 'source',
      modulePath: 'eslint-rules/require-testid.js',
      exportName: 'requireTestId',
      filePath: 'eslint-rules/zz-probe.js',
      bad: 'export const A = () => <Modal />;\n',
      good: 'export const A = () => <Modal data-testid="a" />;\n',
      options: [
        {
          requiredElements: ['Modal', 'Drawer'],
          interactiveElements: ['Button'],
          formElements: [],
          allowTemplateLiterals: true,
        },
      ],
    },
    {
      ruleId: 'custom/no-hardcoded-text',
      kind: 'source',
      modulePath: 'eslint-rules/no-hardcoded-text.js',
      exportName: 'noHardcodedText',
      filePath: 'private/account/web/src/pages/Activity.tsx',
      bad: 'export const A = () => <div>Hello world</div>;\n',
      good: 'export const A = () => <div>{t("common.hello")}</div>;\n',
    },
    {
      ruleId: 'custom/no-unawaited-drizzle-terminator',
      kind: 'source',
      modulePath: 'eslint-rules/no-unawaited-drizzle-terminator.js',
      exportName: 'noUnawaitedDrizzleTerminator',
      filePath: 'private/account/src/routes/configs.ts',
      bad: 'declare const db: any;\ndeclare const tbl: any;\nexport function go() { db.select().from(tbl).all(); }\n',
      good: 'declare const db: any;\ndeclare const tbl: any;\nexport async function go() { await db.select().from(tbl).all(); }\n',
    },
    {
      ruleId: 'custom/require-data-track',
      kind: 'source',
      modulePath: 'eslint-rules/require-data-track.js',
      exportName: 'requireDataTrack',
      filePath: 'packages/www/src/components/AccountCta.tsx',
      bad: 'export const X = () => <a href="/en/docs">Docs</a>;\n',
      good: 'export const X = () => <a href="/en/docs" data-track="x">Docs</a>;\n',
      options: [{ elements: ['a', 'button'], exemptParents: [] }],
    },
    {
      ruleId: 'custom/seo-no-vague-anchor-text',
      kind: 'source',
      modulePath: 'eslint-rules/seo-no-vague-anchor-text.js',
      exportName: 'seoNoVagueAnchorText',
      filePath: 'packages/www/src/components/AccountCta.tsx',
      bad: 'export const X = () => <a href="/en/docs" data-track="x">Click here</a>;\n',
      good: 'export const X = () => <a href="/en/docs" data-track="x">Read the docs</a>;\n',
    },
    {
      ruleId: 'custom/seo-require-img-alt',
      kind: 'source',
      modulePath: 'eslint-rules/seo-require-img-alt.js',
      exportName: 'seoRequireImgAlt',
      filePath: 'packages/www/src/components/AccountCta.tsx',
      bad: 'export const X = () => <img src="/a.png" />;\n',
      good: 'export const X = () => <img src="/a.png" alt="a" />;\n',
    },
    {
      ruleId: 'custom/seo-no-hash-breadcrumb-url',
      kind: 'source',
      modulePath: 'eslint-rules/seo-no-hash-breadcrumb-url.js',
      exportName: 'seoNoHashBreadcrumbUrl',
      filePath: 'packages/www/src/components/AccountCta.tsx',
      bad: 'const breadcrumbItems = [{ name: "S", url: "/en/#solutions" }];\nexport default breadcrumbItems;\n',
      good: 'const breadcrumbItems = [{ name: "S", url: "/en/solutions" }];\nexport default breadcrumbItems;\n',
    },
    {
      ruleId: 'custom/seo-no-trailing-slash-internal-link',
      kind: 'source',
      modulePath: 'eslint-rules/seo-no-trailing-slash-internal-link.js',
      exportName: 'seoNoTrailingSlashInternalLink',
      filePath: 'packages/www/src/components/AccountCta.tsx',
      bad: 'export const X = () => <a href="/en/docs/" data-track="x">Docs</a>;\n',
      good: 'export const X = () => <a href="/en/docs" data-track="x">Docs</a>;\n',
    },
    {
      ruleId: 'custom/e2e-test-naming-convention',
      kind: 'source',
      modulePath: 'eslint-rules/e2e-test-naming-convention.js',
      exportName: 'e2eTestNamingConvention',
      filePath: 'packages/e2e-tests/tests/zz_Bad-Name.test.ts',
      bad: 'export const x = 1;\n',
      good: 'export const x = 1;\n',
      goodFilePath: 'packages/e2e-tests/tests/99-probe-good.test.ts',
      options: [{}],
    },
    {
      ruleId: 'i18n/seo-title-length',
      kind: 'json',
      modulePath: 'eslint-rules/i18n/seo-title-length.js',
      exportName: 'seoTitleLength',
      filePath: 'packages/www/src/i18n/translations/tr.json',
      bad: JSON.stringify({ pages: { x: { meta: { title: 'uzun baslik '.repeat(12) } } } }),
      good: JSON.stringify({
        pages: { x: { meta: { title: 'Bu makul uzunlukta bir baslik metnidir simdi' } } },
      }),
      options: [{ minLength: 30, maxLength: 60, exemptKeys: [] }],
    },
    {
      ruleId: 'i18n/seo-description-length',
      kind: 'json',
      modulePath: 'eslint-rules/i18n/seo-description-length.js',
      exportName: 'seoDescriptionLength',
      filePath: 'packages/www/src/i18n/translations/tr.json',
      bad: JSON.stringify({
        pages: { x: { meta: { description: 'cok uzun aciklama '.repeat(20) } } },
      }),
      good: JSON.stringify({
        pages: {
          x: {
            meta: {
              description:
                'Bu, elli ile yuz altmis karakter arasinda olmasi gereken orta uzunlukta bir aciklama metnidir simdi burada.',
            },
          },
        },
      }),
      options: [{ minLength: 50, maxLength: 160, exemptKeys: [] }],
    },
    {
      ruleId: 'i18n/seo-no-duplicate-h1-title',
      kind: 'json',
      modulePath: 'eslint-rules/i18n/seo-no-duplicate-h1-title.js',
      exportName: 'seoNoDuplicateH1Title',
      filePath: 'packages/www/src/i18n/translations/tr.json',
      bad: JSON.stringify({
        pages: { x: { meta: { title: 'Yedekleme Cozumu' }, hero: { title: 'Yedekleme Cozumu' } } },
      }),
      good: JSON.stringify({
        pages: { x: { meta: { title: 'Yedekleme Cozumu' }, hero: { title: 'Farkli Baslik' } } },
      }),
      options: [{ brandSuffixes: [] }],
    },
    {
      ruleId: 'i18n/no-untranslated-tutorial-transcript-values',
      kind: 'json',
      modulePath: 'eslint-rules/i18n/no-untranslated-tutorial-transcript-values.js',
      exportName: 'noUntranslatedTutorialTranscriptValues',
      filePath: 'packages/www/src/data/tutorial-transcripts/tr/tutorial-storage-management.json',
      bad: JSON.stringify({ events: [{ text: EN_TRANSCRIPT_TEXT() }] }),
      good: JSON.stringify({ events: [{ text: 'Turkce ceviri metni burada' }] }),
      options: [{ transcriptsDir: 'packages/www/src/data/tutorial-transcripts', minLength: 3 }],
      precondition: () => {
        const value = keyPath(readJson(EN_TRANSCRIPT), 'events.0.text');
        if (value !== EN_TRANSCRIPT_TEXT())
          return `${EN_TRANSCRIPT} events[0].text no longer matches the probe's copy`;
        return null;
      },
    },
    {
      ruleId: 'i18n/no-positional-cli-syntax',
      kind: 'json',
      modulePath: 'eslint-rules/i18n/no-positional-cli-syntax.js',
      exportName: 'noPositionalCliSyntax',
      filePath: EN_CLI,
      bad: JSON.stringify({ cli: { description: 'rdc config current <name>' } }),
      good: JSON.stringify({ cli: { description: 'rdc config current --name <name>' } }),
      options: [{ autoDerive: true, exemptCommandPrefixes: [] }],
      precondition: () =>
        isZeroPositionalLeaf('config current')
          ? null
          : '"config current" is no longer a zero-positional leaf in command-tree.json',
    },
    {
      ruleId: 'i18n/no-undefined-cli-flags',
      kind: 'json',
      modulePath: 'eslint-rules/i18n/no-undefined-cli-flags.js',
      exportName: 'noUndefinedCliFlags',
      filePath: EN_CLI,
      bad: JSON.stringify({ cli: { description: 'Use --zzz-not-a-flag now' } }),
      good: JSON.stringify({ cli: { description: 'Use --config now' } }),
      options: [{ exemptFlags: [], exemptKeyPrefixes: [] }],
    },
    {
      ruleId: 'i18n/cli-flag-consistency',
      kind: 'json',
      modulePath: 'eslint-rules/i18n/cli-flag-consistency.js',
      exportName: 'cliFlagConsistency',
      filePath: 'packages/cli/src/i18n/locales/tr/cli.json',
      bad: JSON.stringify({ cli: { description: 'Makineleri --current-ita ile yonet' } }),
      good: JSON.stringify({ cli: { description: 'Makineleri --current ile yonet' } }),
      options: [{ localesDir: 'packages/cli/src/i18n/locales' }],
      precondition: () =>
        typeof keyPath(readJson(EN_CLI), 'cli.description') === 'string'
          ? null
          : `${EN_CLI} no longer has cli.description`,
    },
    {
      ruleId: 'i18n/no-untranslated-values',
      kind: 'json',
      modulePath: 'eslint-rules/i18n/no-untranslated-values.js',
      exportName: 'noUntranslatedValues',
      filePath: 'packages/cli/src/i18n/locales/tr/cli.json',
      bad: JSON.stringify({ cli: { description: EN_CLI_DESCRIPTION() } }),
      good: JSON.stringify({ cli: { description: 'Turkce farkli bir metin buraya' } }),
      options: [{ localesDir: 'packages/cli/src/i18n/locales', minLength: 3, allowedPatterns: [] }],
      precondition: () =>
        keyPath(readJson(EN_CLI), 'cli.description') === EN_CLI_DESCRIPTION()
          ? null
          : `${EN_CLI} cli.description no longer matches the probe's copy`,
    },
    {
      ruleId: 'i18n/interpolation-consistency',
      kind: 'json',
      modulePath: 'eslint-rules/i18n/interpolation-consistency.js',
      exportName: 'interpolationConsistency',
      filePath: 'packages/cli/src/i18n/locales/tr/cli.json',
      bad: JSON.stringify({ timing: { step: { configLoaded: 'Yapilandirma yuklendi' } } }),
      good: JSON.stringify({
        timing: { step: { configLoaded: 'Yapilandirma {{duration}} icinde yuklendi' } },
      }),
      options: [{ localesDir: 'packages/cli/src/i18n/locales' }],
      precondition: () => {
        const value = keyPath(readJson(EN_CLI), 'timing.step.configLoaded');
        return typeof value === 'string' && value.includes('{{duration}}')
          ? null
          : `${EN_CLI} timing.step.configLoaded no longer carries {{duration}}`;
      },
    },
    {
      ruleId: 'i18n/cross-language-consistency',
      kind: 'json',
      modulePath: 'eslint-rules/i18n/cross-language-consistency.js',
      exportName: 'crossLanguageConsistency',
      filePath: path.join(FIXTURES.asymmetric, 'en', 'cli.json'),
      bad: JSON.stringify({ a: 'x', b: 'y' }),
      good: JSON.stringify({ a: 'x' }),
      options: [{ localesDir: FIXTURES.asymmetric, sourceLanguage: 'en' }],
      // The rule reads en's keys straight off DISK (loadLocaleKeys(filePath)), never from the linted text, so the GREEN half needs a different fixture directory -- the symmetric one -- not just a different string.
      goodFilePath: path.join(FIXTURES.symmetric, 'en', 'cli.json'),
      goodOptions: [{ localesDir: FIXTURES.symmetric, sourceLanguage: 'en' }],
    },
    {
      ruleId: 'i18n/translation-coverage',
      kind: 'json',
      modulePath: 'eslint-rules/i18n/translation-coverage.js',
      exportName: 'translationCoverage',
      filePath: path.join(FIXTURES.asymmetric, 'en', 'cli.json'),
      bad: JSON.stringify({ a: 'x', b: 'y' }),
      good: JSON.stringify({ a: 'x' }),
      options: [{ localesDir: FIXTURES.asymmetric, sourceLanguage: 'en', minimumCoverage: 100 }],
      goodFilePath: path.join(FIXTURES.symmetric, 'en', 'cli.json'),
      goodOptions: [{ localesDir: FIXTURES.symmetric, sourceLanguage: 'en', minimumCoverage: 100 }],
    },
  ];
}

const CLI_EN = 'packages/cli/src/i18n/locales/en';
const EN_CLI_DESCRIPTION = () => (keyPath(readJson(EN_CLI), 'cli.description') as string) ?? '';
const EN_TRANSCRIPT_TEXT = () =>
  (keyPath(readJson(EN_TRANSCRIPT), 'events.0.text') as string) ?? '';

/**
 * Planted-defect probes for the two NEW host rules (PLAN-biome-only-lint.md's
 * H3), kept OUT of `buildProbes()` on purpose: Phase 0's snapshot predates
 * both rules (see `CONFIG_SNAPSHOT_BLIND_RULE_IDS`), so there is no ESLint
 * tuple to diff against and `differential()` must not see them. `selftest()`
 * is their only proof: red on `bad`, green on `good`.
 */
function buildNewHostRuleProbes(): Probe[] {
  return [
    {
      ruleId: 'custom/no-unused-underscore-var',
      kind: 'source',
      modulePath: 'eslint-rules/no-unused-underscore-var.js',
      exportName: 'noUnusedUnderscoreVar',
      filePath: 'packages/shared/src/index.ts',
      bad: 'export function f() {\n  const _unused = 1;\n  return 1;\n}\n',
      good: 'export function f() {\n  const _used = 1;\n  return _used;\n}\n',
    },
    {
      ruleId: 'custom/e2e-expect-expect',
      kind: 'source',
      modulePath: 'eslint-rules/e2e-expect-expect.js',
      exportName: 'e2eExpectExpect',
      filePath: 'packages/e2e-tests/tests/zz-probe.test.ts',
      bad: "test('does a thing', async ({ page }) => {\n  await page.goto('/');\n});\n",
      good: "test('does a thing', async ({ page }) => {\n  await page.goto('/');\n  expect(page).toBeDefined();\n});\n",
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
}

async function runProbe(
  probe: Probe,
  code: string,
  side: 'bad' | 'good' = 'bad'
): Promise<Finding[]> {
  const rule = await loadRuleModule(probe.modulePath, probe.exportName);
  const filePath = (side === 'good' ? probe.goodFilePath : undefined) ?? probe.filePath;
  const options = (side === 'good' ? probe.goodOptions : undefined) ?? probe.options ?? [];
  const abs = path.isAbsolute(filePath) ? filePath : path.join(REPO_ROOT, filePath);
  const run = { filename: abs, cwd: REPO_ROOT, options };
  return probe.kind === 'json' ? runJsonRule(rule, code, run) : runSourceRule(rule, code, run);
}

/** `(file, line, column, ruleId)` tuples for a whole-tree run, restricted to the H rule ids. */
function toHeadTuples(findings: TaggedFinding[]): string[] {
  return findings
    .filter((f) => RULE_IDS.includes(f.ruleId))
    .map((f) => `${f.file}:${f.line}:${f.column}:${f.ruleId}`)
    .sort();
}

interface Phase0ConfigEntry {
  path: string;
  rules?: Record<string, unknown[]>;
  error?: string;
}

/** Any severity ESLint's `calculateConfigForFile` reports as ON, in either its string or numeric spelling. */
function isEnabledSeverity(severity: unknown): boolean {
  return severity === 'error' || severity === 'warn' || severity === 1 || severity === 2;
}

/**
 * Directory-valued option keys every affected rule spells the same way
 * (`require-translation.js`, `require-translation-key-arg.js`,
 * `i18n/interpolation-match.js`, and the five `localesDir`-reading i18n/json
 * rules). ESLint's real config blocks build these with `path.join(...)` against
 * the repo root, so `calculateConfigForFile` reports an ABSOLUTE path;
 * `scripts/data/source-rules.ts` spells the same directory relative to the repo
 * root, for readability. Both name the same directory once resolved against
 * `REPO_ROOT` -- the host always runs with `cwd: REPO_ROOT` (`lintFile`,
 * `runProbe`) -- so this is normalization of two equally-valid spellings, not
 * an exception: it applies to every rule uniformly rather than being listed
 * rule by rule. Verified 2026-09-24: resolving these three keys on both sides
 * is what turns 1714 of the 1727 raw option mismatches on the real tree into
 * exact matches; the remaining 13 are the `exemptKeys` default handled below.
 */
const DIR_OPTION_KEYS = new Set(['localeDir', 'localesDir', 'transcriptsDir']);

function normalizeDirOptions(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(normalizeDirOptions);
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] =
        typeof v === 'string' && DIR_OPTION_KEYS.has(k)
          ? path.resolve(REPO_ROOT, v)
          : normalizeDirOptions(v);
    }
    return out;
  }
  return value;
}

/**
 * `i18n/seo-no-duplicate-h1-title`'s real config (`eslint.config/packages.js`)
 * spells `exemptKeys: []` explicitly, but `seo-no-duplicate-h1-title.js` itself
 * falls back to `[]` when the option is absent (`options.exemptKeys || []`
 * pattern, matching its siblings) -- so `[]` is the rule's OWN default, not a
 * real difference in behaviour. `scripts/data/source-rules.ts`'s instance
 * (13 `packages/www/src/i18n/translations/*.json` paths) omits the no-op key.
 * Filled in on whichever side lacks it, scoped to this one rule id, so the
 * exception is exactly as wide as the thing it explains.
 */
function fillBenignDefaults(ruleId: string, options: unknown[]): unknown[] {
  if (ruleId !== 'i18n/seo-no-duplicate-h1-title') return options;
  return options.map((opt) =>
    opt && typeof opt === 'object' && !('exemptKeys' in (opt as Record<string, unknown>))
      ? { ...(opt as Record<string, unknown>), exemptKeys: [] }
      : opt
  );
}

/**
 * The 6 real `eslint-disable custom/no-hardcoded-text` file headers in the
 * current tree (`private/account/web/src/pages/*.tsx`, none with an inline
 * reason). ESLint's `calculateConfigForFile` resolves STATIC config only -- it
 * has no notion of a disable comment inside the file -- so its snapshot shows
 * this rule ON for all 6. `scripts/data/source-rules.ts`'s own `ignores` list
 * for `custom/no-hardcoded-text` (rule map row 141) replicates what the
 * disable comment actually suppressed at lint time by scoping the rule OFF for
 * these paths instead, which is by design, not a gap. Any OTHER path, or any
 * other rule id, where the host's on/off state disagrees with this snapshot is
 * NOT covered by this exception and fails the gate.
 */
const ACCOUNT_NO_HARDCODED_TEXT_DISABLE_FILES = new Set([
  'private/account/web/src/pages/ConfigMemberAccept.tsx',
  'private/account/web/src/pages/ConfigMembers.tsx',
  'private/account/web/src/pages/ConfigSetup.tsx',
  'private/account/web/src/pages/ConfigStorage.tsx',
  'private/account/web/src/pages/DeviceConfigSetup.tsx',
  'private/account/web/src/pages/admin/ConfigAdmin.tsx',
]);

function isExplainedScopeMismatch(
  filePath: string,
  ruleId: string,
  eslintOn: boolean,
  hostOn: boolean
): boolean {
  return (
    ruleId === 'custom/no-hardcoded-text' &&
    eslintOn &&
    !hostOn &&
    ACCOUNT_NO_HARDCODED_TEXT_DISABLE_FILES.has(filePath)
  );
}

/**
 * `custom/no-unused-underscore-var` and `custom/e2e-expect-expect` are NEW
 * host rule ids (PLAN-biome-only-lint.md's H3): they port
 * `@typescript-eslint/no-unused-vars` and `playwright/expect-expect`, whose
 * REAL ESLint rule ids are spelled differently and, in the first case, never
 * matches `gen-config-snapshot.mjs`'s `custom/`/`i18n/`/`i18n-source/`
 * `TARGET_PREFIXES` at all. Phase 0's snapshot -- taken before either host
 * rule existed -- has no key by either synthetic id on any path, so there is
 * no ESLint verdict to diff against; every one of the ~2794 paths would
 * otherwise show up as "host enables, ESLint does not" for a rule the
 * snapshot was never asked about. `check-source-rules.ts --selftest`'s
 * planted probes are this pair's real proof (see `NEW_HOST_RULE_PROBES`).
 */
const CONFIG_SNAPSHOT_BLIND_RULE_IDS = new Set([
  'custom/no-unused-underscore-var',
  'custom/e2e-expect-expect',
]);

/**
 * `--config-differential`: for every path ESLint resolved a config for at
 * Phase 0 (`.ci/cache/biome-parity/phase0-config-snapshot.jsonl`, one JSON
 * object per line), compares which of the H rule ids are ON there against
 * `matchingInstances(path)` -- the same resolver `lintFile`/`corpus` use for
 * real linting -- and, where both agree a rule is on, compares its options.
 * A path this gate's own `corpus()` would not reach (a file removed or
 * reclassified since Phase 0) is skipped rather than flagged: that drift is
 * `corpus().length` disagreeing with the snapshot's line count, which
 * `differential()`'s own tuple comparison already surfaces.
 */
async function configDifferential(dir: string): Promise<number> {
  const snapshotPath = path.join(dir, 'phase0-config-snapshot.jsonl');
  const lines = fs
    .readFileSync(snapshotPath, 'utf8')
    .split('\n')
    .filter((l) => l.trim().length > 0);
  const corpusSet = new Set(corpus());

  let checked = 0;
  let bad = 0;
  const problems: string[] = [];

  for (const line of lines) {
    const entry = JSON.parse(line) as Phase0ConfigEntry;
    if (entry.error || !corpusSet.has(entry.path)) continue;
    checked++;

    const expected = new Map<string, unknown[]>();
    for (const [ruleId, value] of Object.entries(entry.rules ?? {})) {
      if (ruleId === 'max-lines') continue; // its own gate (check-max-lines.ts), not a RuleInstance
      if (isEnabledSeverity(value[0])) expected.set(ruleId, value.slice(1));
    }

    const actual = new Map<string, unknown[]>();
    for (const inst of matchingInstances(entry.path)) {
      if (RULE_IDS.includes(inst.ruleId) && !CONFIG_SNAPSHOT_BLIND_RULE_IDS.has(inst.ruleId))
        actual.set(inst.ruleId, inst.options ?? []);
    }

    const allIds = new Set([...expected.keys(), ...actual.keys()]);
    for (const ruleId of allIds) {
      const eslintOn = expected.has(ruleId);
      const hostOn = actual.has(ruleId);
      if (eslintOn !== hostOn) {
        if (isExplainedScopeMismatch(entry.path, ruleId, eslintOn, hostOn)) continue;
        bad++;
        problems.push(
          `${entry.path} :: ${ruleId} :: ESLint ${eslintOn ? 'enables' : 'does not enable'}, host ${hostOn ? 'enables' : 'does not enable'} it`
        );
        continue;
      }
      if (!eslintOn) continue;
      const eslintOptions = fillBenignDefaults(
        ruleId,
        normalizeDirOptions(expected.get(ruleId)) as unknown[]
      );
      const hostOptions = fillBenignDefaults(
        ruleId,
        normalizeDirOptions(actual.get(ruleId)) as unknown[]
      );
      if (JSON.stringify(eslintOptions) !== JSON.stringify(hostOptions)) {
        bad++;
        problems.push(
          `${entry.path} :: ${ruleId} :: options differ: eslint=${JSON.stringify(eslintOptions)} host=${JSON.stringify(hostOptions)}`
        );
      }
    }
  }

  if (bad > 0) {
    console.error(
      `✗ config differential: ${bad} unexplained mismatch(es) across ${checked} path(s)`
    );
    for (const p of problems.slice(0, 40)) console.error(`    ${p}`);
    if (problems.length > 40) console.error(`    ... and ${problems.length - 40} more`);
  } else {
    console.log(
      `✓ config differential: ${checked} path(s), 0 unexplained mismatch(es) (6 documented no-hardcoded-text ignores, 13 documented exemptKeys defaults)`
    );
  }
  return bad === 0 ? 0 : 1;
}

interface Phase0Tuples {
  head: string[];
  planted: Record<string, string[]>;
}

async function differential(dir: string): Promise<number> {
  const raw = JSON.parse(
    fs.readFileSync(path.join(dir, 'phase0-tuples.json'), 'utf8')
  ) as Phase0Tuples;
  let bad = 0;

  const headTuples = toHeadTuples(await runWholeTree());
  const expectedHead = [...raw.head].sort();
  if (JSON.stringify(headTuples) !== JSON.stringify(expectedHead)) {
    bad++;
    const headSet = new Set(headTuples);
    const expSet = new Set(expectedHead);
    console.error(
      `✗ HEAD differential: ${expectedHead.filter((t) => !headSet.has(t)).length} missing, ${headTuples.filter((t) => !expSet.has(t)).length} extra`
    );
    for (const t of expectedHead.filter((t) => !headSet.has(t)).slice(0, 10))
      console.error(`    missing: ${t}`);
    for (const t of headTuples.filter((t) => !expSet.has(t)).slice(0, 10))
      console.error(`    extra:   ${t}`);
  } else {
    console.log(`✓ HEAD differential: ${headTuples.length} tuple(s), byte-identical to Phase 0`);
  }

  // These two never read the linted text -- only `localesDir` on disk -- so their probe runs against a fresh mkdtemp fixture each time, and that path is never reproducible across two separate runs (this gate's and the Phase 0 snapshot script's). Their tuples drop the file component; the position and rule id are still a real assertion.
  const POSITION_ONLY = new Set(['i18n/cross-language-consistency', 'i18n/translation-coverage']);

  const probes = buildProbes();
  for (const probe of probes) {
    const expected = (raw.planted[probe.ruleId] ?? []).slice().sort();
    const problem = probe.precondition?.();
    if (problem) {
      console.error(`⚠ ${probe.ruleId}: SPECIMEN STALE, not a verdict on the rule: ${problem}`);
      bad++;
      continue;
    }
    const findings = await runProbe(probe, probe.bad);
    const relFile = path.isAbsolute(probe.filePath)
      ? path.relative(REPO_ROOT, probe.filePath)
      : probe.filePath;
    const tuples = POSITION_ONLY.has(probe.ruleId)
      ? findings.map((f) => `${f.line}:${f.column}:${probe.ruleId}`).sort()
      : findings.map((f) => `${relFile}:${f.line}:${f.column}:${probe.ruleId}`).sort();
    if (JSON.stringify(tuples) !== JSON.stringify(expected)) {
      bad++;
      console.error(
        `✗ ${probe.ruleId} planted probe: expected ${JSON.stringify(expected)}, got ${JSON.stringify(tuples)}`
      );
    } else {
      console.log(
        `✓ ${probe.ruleId} planted probe: ${tuples.length} tuple(s), byte-identical to Phase 0`
      );
    }
  }

  return bad === 0 ? 0 : 1;
}

async function selftest(): Promise<number> {
  let bad = 0;
  const probes = [...buildProbes(), ...buildNewHostRuleProbes()];
  for (const probe of probes) {
    const problem = probe.precondition?.();
    if (problem) {
      console.error(`⚠ ${probe.ruleId}: SPECIMEN STALE: ${problem}`);
      bad++;
      continue;
    }
    const redFindings = await runProbe(probe, probe.bad, 'bad');
    const greenFindings = await runProbe(probe, probe.good, 'good');
    const red = redFindings.length > 0;
    const green = greenFindings.length === 0;
    if (red && green) {
      console.log(`✓ ${probe.ruleId}: red with the planted defect, green on the clean sibling`);
    } else {
      bad++;
      if (!red) console.error(`✗ ${probe.ruleId}: did NOT fire on its planted defect`);
      if (!green)
        console.error(
          `✗ ${probe.ruleId}: fired on its CLEAN sibling (${JSON.stringify(greenFindings.map((f) => f.messageId))})`
        );
    }
  }

  const disableHits = findStaleDirectives([
    'scripts/gates/check-source-rules.ts',
    'scripts/lib/rule-host.ts',
  ]);
  if (disableHits.length > 0) {
    bad++;
    console.error(
      `✗ stale-directive scanner found a token in its own source: ${disableHits.join(', ')}`
    );
  } else {
    console.log('✓ stale-directive scanner finds no eslint-disable/enable token in its own source');
  }

  console.log(
    `${bad === 0 ? '✓' : '✗'} check-source-rules selftest: ${probes.length} probe(s) covering ${RULE_IDS.length} rule id(s)`
  );
  return bad === 0 ? 0 : 1;
}

async function main(): Promise<number> {
  const args = process.argv.slice(2);
  if (args.includes('--selftest')) return selftest();
  const diffIndex = args.indexOf('--differential');
  if (diffIndex !== -1) return differential(args[diffIndex + 1]);
  const configDiffIndex = args.indexOf('--config-differential');
  if (configDiffIndex !== -1) return configDifferential(args[configDiffIndex + 1]);

  const findings = await runWholeTree();
  const stale = findStaleDirectives(corpus());
  if (stale.length > 0) {
    console.error(
      `✗ ${stale.length} file(s) still carry an eslint-disable/eslint-enable token nothing honours any more:`
    );
    for (const f of stale) console.error(`    ${f}`);
  }
  if (findings.length > 0) {
    console.error(`✗ ${findings.length} finding(s):`);
    for (const f of findings)
      console.error(`    ${f.file}:${f.line}:${f.column}  ${f.ruleId}  ${f.message}`);
  }
  if (findings.length === 0 && stale.length === 0) {
    console.log(
      `✓ check-source-rules: ${corpus().length} file(s) scanned, ${RULE_IDS.length} rule id(s), 0 findings`
    );
  }
  return findings.length === 0 && stale.length === 0 ? 0 : 1;
}

if (path.resolve(process.argv[1] ?? '') === path.resolve(fileURLToPath(import.meta.url))) {
  main()
    .then((code) => process.exit(code))
    .catch((error: unknown) => {
      console.error('✗ check-source-rules crashed');
      console.error(error);
      process.exit(1);
    });
}
