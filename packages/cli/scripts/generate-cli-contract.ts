#!/usr/bin/env tsx
/**
 * CLI Contract Generator
 *
 * Joins the live Commander tree with COMMAND_METADATA (planes, policy, MCP
 * annotations), COMMAND_SEVERITY / COMMAND_PREVIEW (command-safety.ts), the
 * error-code origins (error-origins.ts), the command registry (domain grouping),
 * and the i18n catalogues, and emits the contract that drives the web console,
 * the `rdc --proxy` thin client, and the executor.
 *
 * Emits into packages/shared/src/cli-contract/data:
 *   contract.generated.ts           typed literal (the import surface)
 *   contract.json                   same data, for consumers that load it as an asset
 *   contract-version.generated.ts   the version alone, so a web bundle can send it
 *                                   without pulling the contract literal in
 *   i18n/<lang>.json                per-language strings, lazily loadable
 *
 * The version is a content hash (see contractVersion), so regeneration is
 * deterministic and there is no version flag.
 *
 * Usage:
 *   npx tsx packages/cli/scripts/generate-cli-contract.ts [--output <dir>]
 */
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type {
  CliContract,
  CommandExample,
  CommandGroup,
  CommandPreview,
  CommandSeverity,
  ContractCommand,
  ContractErrorCode,
  ContractOption,
  ContractPositional,
  OutputHints,
} from '../../shared/src/cli-contract/types.js';
import {
  checkContractInvariants,
  SUMMARY_MAX_LENGTH,
} from '../../shared/src/cli-contract/validation.js';
import { isMcpLayerErrorCode } from '../../shared/src/mcp/errors.js';
import { cli } from '../src/cli.js';
import {
  COMMAND_EXAMPLES,
  COMMAND_KEYWORDS,
  COMMAND_OUTPUT_HINTS,
} from '../src/config/command-docs.js';
import { COMMAND_METADATA, READ_TIMEOUT, WRITE_TIMEOUT } from '../src/config/command-metadata.js';
import { getCommandPlane, isInteractiveCommand } from '../src/config/command-planes.js';
import { COMMAND_REGISTRY } from '../src/config/command-registry.js';
import { COMMAND_PREVIEW, COMMAND_SEVERITY, NOT_PREVIEW } from '../src/config/command-safety.js';
import { listErrorCodeOrigins } from '../src/types/error-origins.js';
import {
  createDescriptionResolver,
  flattenHelpNamespaces,
  GLOBAL_OPTION_LONGS,
  listLocales,
  loadLocale,
  walkContractCommands,
} from './lib/command-tree-lib.js';
import {
  classifyPositional,
  DETACH_EXCLUSIONS,
  EXECUTOR_SERVED,
  GENERIC_DETACH_BLOCKED,
  GENERIC_PROXY_BLOCKED,
  PROXY_EXCLUSIONS,
} from './lib/contract-curation.js';
import {
  resolveMachineOption,
  resolveMachinePositional,
  resolveRepoOption,
  resolveRepoPositional,
  toContractOption,
} from './lib/contract-options.js';
import { parseExampleValues } from './lib/example-parse.js';
import { collectClassificationProblems } from './lib/option-classification.js';
import { at } from './lib/table.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** `repo sync upload` -> `commands.proxyBlocked.repoSyncUpload`; `-` splits words too. */
function proxyBlockedKeyFor(pathKey: string): string {
  const words = pathKey.split(/[\s-]+/).filter(Boolean);
  const camel = words
    .map((w, i) => (i === 0 ? w : w.charAt(0).toUpperCase() + w.slice(1)))
    .join('');
  return `commands.proxyBlocked.${camel}`;
}

/** Why a command that reaches a machine still cannot be proxied, with the i18n key of that text. */
function proxyBlockedReason(
  pathKey: string,
  plane: string,
  interactive: boolean
): { text: string; key: string } | undefined {
  const excluded = PROXY_EXCLUSIONS[pathKey];
  if (excluded) return { text: excluded, key: proxyBlockedKeyFor(pathKey) };
  if (interactive) {
    return { text: GENERIC_PROXY_BLOCKED.interactive, key: 'commands.proxyBlocked.interactive' };
  }
  if (plane === 'config') {
    return { text: GENERIC_PROXY_BLOCKED.localConfig, key: 'commands.proxyBlocked.localConfig' };
  }
  if (plane === 'other') {
    return { text: GENERIC_PROXY_BLOCKED.localTooling, key: 'commands.proxyBlocked.localTooling' };
  }
  return undefined;
}

// ---------- Args ----------

function readArg(name: string, fallback: string): string {
  const i = process.argv.indexOf(`--${name}`);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

const DEFAULT_OUTPUT = path.resolve(__dirname, '../../shared/src/cli-contract/data');
const outputDir = path.resolve(readArg('output', DEFAULT_OUTPUT));
if (process.argv.includes('--version')) {
  console.error(
    '--version was dropped: the contract version is a content hash of the command surface (contractVersion).'
  );
  process.exit(1);
}

// ---------- Registry lookup ----------

const registryByName = new Map(COMMAND_REGISTRY.map((c) => [c.name, c]));

function resolveGroup(domain: string): CommandGroup | null {
  return registryByName.get(domain)?.domain ?? null;
}

// ---------- Build ----------

const resolver = createDescriptionResolver(loadLocale('en'));
const walked = walkContractCommands(cli, resolver);

/**
 * Every PROXY_EXCLUSIONS / DETACH_EXCLUSIONS key must name a command that exists.
 *
 * ★ This is the table whose ENTIRE JOB is to stop a command being shipped to a
 * remote executor, and until now nothing checked its keys. `proxyCapable` is
 * `plane === 'machine' && !interactive && !(pathKey in PROXY_EXCLUSIONS)`, so a key
 * that goes stale through a rename does not fail loudly: the lookup simply misses,
 * the exclusion STOPS EXCLUDING, and the command silently becomes proxyCapable.
 *
 * That is bug #51's exact failure mode occurring inside the mechanism built to
 * prevent it: `machine scan-keys` is excluded because it scans from the CALLER's
 * network position and stores the result in the CALLER's config. Rename it, forget
 * this key, and a remote executor starts scanning from its own network and keeping
 * the answer, with no gate anywhere saying so.
 *
 * COMMAND_PLANES already has this protection (plane-coverage.test.ts fails on a stale
 * entry). Its sibling did not. It does now.
 */
const livePathKeys = new Set(walked.map((w) => w.pathKey));
const staleExclusions = [
  ...Object.keys(PROXY_EXCLUSIONS).map((k) => [k, 'PROXY_EXCLUSIONS'] as const),
  ...Object.keys(DETACH_EXCLUSIONS).map((k) => [k, 'DETACH_EXCLUSIONS'] as const),
  ...Object.keys(EXECUTOR_SERVED).map((k) => [k, 'EXECUTOR_SERVED'] as const),
].filter(([pathKey]) => !livePathKeys.has(pathKey));

if (staleExclusions.length > 0) {
  console.error('\x1b[31m✗ Stale exclusion keys: these commands do not exist\x1b[0m\n');
  for (const [pathKey, table] of staleExclusions) {
    console.error(`  ${table}["${pathKey}"]`);
  }
  console.error(
    '\n  A stale key does not fail loudly: the lookup misses, the exclusion stops applying,\n' +
      '  and the command silently becomes proxyCapable (or detachable). Re-key it to the\n' +
      "  command's current name, or delete it deliberately.\n"
  );
  process.exit(1);
}

/**
 * Same staleness discipline for the curated registries (command-docs.ts): a
 * key naming a command that no longer exists means its examples/keywords/
 * output hints silently stop shipping: curation lost through a rename, with
 * no gate anywhere saying so.
 */
const staleRegistryKeys = [
  ...Object.keys(COMMAND_EXAMPLES).map((k) => [k, 'COMMAND_EXAMPLES'] as const),
  ...Object.keys(COMMAND_KEYWORDS).map((k) => [k, 'COMMAND_KEYWORDS'] as const),
  ...Object.keys(COMMAND_OUTPUT_HINTS).map((k) => [k, 'COMMAND_OUTPUT_HINTS'] as const),
].filter(([pathKey]) => !livePathKeys.has(pathKey));

if (staleRegistryKeys.length > 0) {
  console.error('\x1b[31m✗ Stale registry keys: these commands do not exist\x1b[0m\n');
  for (const [pathKey, table] of staleRegistryKeys) {
    console.error(`  ${table}["${pathKey}"]`);
  }
  console.error(
    '\n  A stale key does not fail loudly: the lookup misses and the curated metadata\n' +
      "  silently stops shipping. Re-key it to the command's current name, or delete it\n" +
      '  deliberately.\n'
  );
  process.exit(1);
}

/**
 * Problems found while attaching the curated registries (example parse
 * failures, malformed keywords, inconsistent output hints). Collected during
 * the build and reported in one red block alongside the classification gates.
 */
const curationProblems: string[] = [];

/** Curated examples for a command, parsed into contract shape (or undefined). */
function buildCommandExamples(
  pathKey: string,
  options: ContractOption[],
  positionals: ContractPositional[]
): CommandExample[] | undefined {
  const defs = at(COMMAND_EXAMPLES, pathKey);
  if (!defs || defs.length === 0) return undefined;

  return defs.map((def) => {
    const values = parseExampleValues(
      pathKey,
      def.command,
      options,
      positionals,
      GLOBAL_OPTION_LONGS,
      { livePathKeys, problems: curationProblems }
    );
    if (!/^commands\..+\.examples\.[a-zA-Z0-9-]+$/.test(def.descriptionKey)) {
      curationProblems.push(
        `COMMAND_EXAMPLES["${pathKey}"]: descriptionKey "${def.descriptionKey}" does not follow commands.<path>.examples.<slug>`
      );
    }
    const label = resolver.strings.get(def.descriptionKey);
    if (label === undefined) {
      curationProblems.push(
        `COMMAND_EXAMPLES["${pathKey}"]: descriptionKey "${def.descriptionKey}" has no English string in en/cli.json`
      );
    }
    return { command: def.command, values, descriptionKey: def.descriptionKey, label: label ?? '' };
  });
}

/** Curated keywords, gated to lowercase-ascii palette tokens. */
function buildCommandKeywords(pathKey: string): string[] | undefined {
  const keywords = at(COMMAND_KEYWORDS, pathKey);
  if (!keywords) return undefined;
  if (keywords.length === 0) {
    curationProblems.push(`COMMAND_KEYWORDS["${pathKey}"]: entry is empty. Delete it instead`);
  }
  for (const keyword of keywords) {
    if (!/^[a-z][a-z0-9-]*$/.test(keyword)) {
      curationProblems.push(
        `COMMAND_KEYWORDS["${pathKey}"]: ${JSON.stringify(keyword)} is not a lowercase-ascii token`
      );
    }
  }
  return [...keywords];
}

/** Curated output hints, gated so primaryKey is always one of columns. */
function buildCommandOutput(pathKey: string): OutputHints | undefined {
  const hints = at(COMMAND_OUTPUT_HINTS, pathKey);
  if (!hints) return undefined;
  if (hints.columns.length === 0) {
    curationProblems.push(`COMMAND_OUTPUT_HINTS["${pathKey}"]: columns is empty`);
  } else if (!hints.columns.includes(hints.primaryKey)) {
    curationProblems.push(
      `COMMAND_OUTPUT_HINTS["${pathKey}"]: primaryKey "${hints.primaryKey}" is not one of its columns (${hints.columns.join(', ')})`
    );
  }
  return { primaryKey: hints.primaryKey, columns: [...hints.columns] };
}

/**
 * The i18n key of a command's summary. The `.summary()` text is resolved back
 * to its key the way descriptions are, preferring the command's own
 * `descriptionShort` / `summary` key when its English matches, so two commands
 * sharing one English sentence still each point at their own key.
 */
function resolveSummaryKey(path: string[], summary: string): string | null {
  const base = `commands.${path.join('.')}`;
  for (const candidate of [`${base}.descriptionShort`, `${base}.summary`]) {
    if (resolver.strings.get(candidate) === summary) return candidate;
  }
  return resolver.findDescriptionKey(summary);
}

/** The command's `.summary()`, refused when missing or over the contract's limit. */
function resolveSummary(pathKey: string, liveSummary: string): string {
  if (liveSummary.trim() === '') {
    curationProblems.push(
      `${pathKey}: no .summary(). Add .summary(t('commands.<path>.descriptionShort')) and its English key`
    );
  } else if ([...liveSummary].length > SUMMARY_MAX_LENGTH) {
    curationProblems.push(
      `${pathKey}: summary is ${[...liveSummary].length} characters, over ${SUMMARY_MAX_LENGTH}`
    );
  }
  return liveSummary;
}

/** The severity from COMMAND_SEVERITY; a command with no entry is refused (D2). */
function resolveSeverity(pathKey: string): CommandSeverity {
  const severity = at(COMMAND_SEVERITY, pathKey);
  if (severity === undefined) {
    curationProblems.push(
      `COMMAND_SEVERITY["${pathKey}"]: missing. Every contract command declares none, caution or destructive (command-safety.ts)`
    );
    return 'caution';
  }
  return severity;
}

/**
 * The preview switch from COMMAND_PREVIEW. A command taking `--dry-run` or
 * `--apply` must be in COMMAND_PREVIEW or in NOT_PREVIEW with a reason, never
 * both and never neither (D2).
 */
function resolvePreview(pathKey: string, options: ContractOption[]): CommandPreview | undefined {
  const preview = at(COMMAND_PREVIEW, pathKey);
  const notPreview = at(NOT_PREVIEW, pathKey);
  if (preview && notPreview !== undefined) {
    curationProblems.push(`${pathKey}: listed in both COMMAND_PREVIEW and NOT_PREVIEW`);
  }
  if (notPreview !== undefined && notPreview.trim() === '') {
    curationProblems.push(`NOT_PREVIEW["${pathKey}"]: the reason is empty`);
  }
  const previewFlags = options.filter((o) => o.long === 'dry-run' || o.long === 'apply');
  if (previewFlags.length > 0 && !preview && notPreview === undefined) {
    curationProblems.push(
      `${pathKey}: takes ${previewFlags.map((o) => `--${o.long}`).join(' and ')} but is in neither COMMAND_PREVIEW nor NOT_PREVIEW (command-safety.ts)`
    );
  }
  return preview ? { flag: preview.flag, polarity: preview.polarity } : undefined;
}

/** The i18n key of a proxy refusal, refused when en/cli.json does not hold the same text under it. */
function checkProxyBlockedKey(pathKey: string, reason: { text: string; key: string }): void {
  const english = resolver.strings.get(reason.key);
  if (english === undefined) {
    curationProblems.push(
      `${pathKey}: proxy refusal key "${reason.key}" has no English string in en/cli.json`
    );
  } else if (english !== reason.text) {
    curationProblems.push(
      `${pathKey}: en/cli.json "${reason.key}" differs from the refusal text the generator emits`
    );
  }
}

const commands: ContractCommand[] = walked.map((w) => {
  const domain = w.path[0];
  const meta = at(COMMAND_METADATA, w.pathKey);
  const mcp = meta?.mcp;
  const plane = getCommandPlane(w.pathKey);
  const interactive = isInteractiveCommand(w.pathKey);

  // Re-extract options from the live command so the contract carries the rich shape (long/short/valueTaking/variadic) that argv serialisation needs.
  const liveCommand = w.path.reduce<import('commander').Command | undefined>(
    (cmd, segment) => cmd?.commands.find((c) => c.name() === segment),
    cli
  );
  if (!liveCommand) throw new Error(`Could not re-resolve command "${w.pathKey}" in the tree`);

  const options = liveCommand.options
    .filter((o) => !GLOBAL_OPTION_LONGS.has(o.long ?? ''))
    .map((o) => toContractOption(o, resolver, w.pathKey));

  const positionals: ContractPositional[] = w.positionals.map((p) => ({
    name: p.name,
    kind: classifyPositional(w.pathKey, domain, p.name),
    required: p.required,
    variadic: p.variadic,
    descriptionKey: p.descriptionKey,
    label: p.label,
  }));

  const examples = buildCommandExamples(w.pathKey, options, positionals);
  const keywords = buildCommandKeywords(w.pathKey);
  const output = buildCommandOutput(w.pathKey);

  const proxyCapable =
    (plane === 'machine' || w.pathKey in EXECUTOR_SERVED) &&
    !interactive &&
    !(w.pathKey in PROXY_EXCLUSIONS);
  const blockedReason = proxyCapable
    ? undefined
    : proxyBlockedReason(w.pathKey, plane, interactive);
  if (blockedReason) checkProxyBlockedKey(w.pathKey, blockedReason);

  const summary = resolveSummary(w.pathKey, liveCommand.summary());
  const summaryKey = summary ? resolveSummaryKey(w.path, summary) : null;
  if (summary && summaryKey === null) {
    curationProblems.push(
      `${w.pathKey}: summary has no English key. Add commands.<path>.descriptionShort with the same text`
    );
  }
  const severity = resolveSeverity(w.pathKey);
  const preview = resolvePreview(w.pathKey, options);

  // Every proxyable machine-plane command runs as one machine job (PLAN-detached-jobs section 14), minus the `job *` verbs (they read the spool) and the
  // section 24 exceptions in DETACH_EXCLUSIONS. `--background` is accepted exactly where this is true.
  const noMachineJob = proxyCapable && plane !== 'machine';
  const detachable =
    proxyCapable && !noMachineJob && domain !== 'job' && !(w.pathKey in DETACH_EXCLUSIONS);
  const detachBlockedReason = noMachineJob
    ? GENERIC_DETACH_BLOCKED.executorServed
    : proxyCapable
      ? DETACH_EXCLUSIONS[w.pathKey]
      : undefined;

  return {
    path: w.path,
    pathKey: w.pathKey,
    domain,
    group: resolveGroup(domain),
    plane,
    descriptionKey: w.descriptionKey,
    label: liveCommand.description(),
    summaryKey,
    summary,
    severity,
    ...(preview ? { preview } : {}),
    options,
    positionals,
    hasSubcommands: w.hasSubcommands,

    ...(examples ? { examples } : {}),
    ...(keywords ? { keywords } : {}),
    ...(output ? { output } : {}),

    ...(mcp ? { destructive: mcp.destructive, idempotent: mcp.idempotent } : {}),
    ...(mcp ? { timeout: mcp.timeout } : {}),
    ...(mcp ? { timeoutMs: mcp.timeout === 'write' ? WRITE_TIMEOUT : READ_TIMEOUT } : {}),
    ...(mcp?.repoArg ? { repoArg: mcp.repoArg } : {}),
    ...(meta?.grandGuard ? { grandGuard: true } : {}),
    ...(meta?.forkBlocked ? { forkBlocked: true } : {}),
    ...(meta?.agentBlocked ? { agentBlocked: true } : {}),
    ...(meta?.mcpExcludeReason ? { mcpExcludeReason: meta.mcpExcludeReason } : {}),

    interactive,
    proxyCapable,
    ...(blockedReason
      ? { proxyBlockedReason: blockedReason.text, proxyBlockedReasonKey: blockedReason.key }
      : {}),
    detachable,
    ...(detachBlockedReason ? { detachBlockedReason } : {}),

    machineOption: resolveMachineOption(domain, options),
    repoOption: resolveRepoOption(domain, options, mcp?.repoArg),
    machinePositional: resolveMachinePositional(positionals),
    repoPositional: resolveRepoPositional(positionals),
  };
});

commands.sort((a, b) => a.pathKey.localeCompare(b.pathKey));

/** Safety-table keys naming no contract command: the curation silently stops applying (D2). */
const staleSafetyKeys = [
  ...Object.keys(COMMAND_SEVERITY).map((k) => [k, 'COMMAND_SEVERITY'] as const),
  ...Object.keys(COMMAND_PREVIEW).map((k) => [k, 'COMMAND_PREVIEW'] as const),
  ...Object.keys(NOT_PREVIEW).map((k) => [k, 'NOT_PREVIEW'] as const),
].filter(([pathKey]) => !livePathKeys.has(pathKey));
for (const [pathKey, table] of staleSafetyKeys) {
  curationProblems.push(`${table}["${pathKey}"]: names no contract command`);
}
for (const cmd of commands) {
  if (cmd.destructive === true && cmd.severity === 'none') {
    curationProblems.push(
      `COMMAND_SEVERITY["${cmd.pathKey}"]: none, but its MCP annotation is destructive`
    );
  }
}

/**
 * Metadata gates: the classification tables (staleness, resource-noun
 * coverage, waiver quality, tier floor, all in option-classification.ts) plus
 * everything collected while attaching the curated registries. One red block,
 * exit 1: a wrong or stale entry must never survive a regen silently.
 */
const metadataProblems = [...curationProblems, ...collectClassificationProblems(commands)];

if (metadataProblems.length > 0) {
  console.error('\x1b[31m✗ Contract metadata gates failed\x1b[0m\n');
  for (const problem of metadataProblems) {
    console.error(`  ${problem}`);
  }
  console.error(
    '\n  Fix the classification-table, command-docs, command-safety or en/cli.json entry\n' +
      '  each line names. A stale or wrong entry does not fail on its own: the lookup\n' +
      '  misses and the metadata silently stops applying, so generation refuses to\n' +
      '  proceed instead.\n'
  );
  process.exit(1);
}

const languages = listLocales();

// The MCP-layer codes (POLICY_DENIED and its siblings) carry an origin, since the executor's MCP routes raise them, but they are the MCP registry's own family, never the contract's: the registry refuses a code in both.
const errorCodes: ContractErrorCode[] = listErrorCodeOrigins()
  .filter(({ code }) => !isMcpLayerErrorCode(code))
  .map(({ code, origin }) => ({ code, origin }))
  .sort((a, b) => (a.code < b.code ? -1 : a.code > b.code ? 1 : 0));

/** JSON with object keys sorted at every level, so the hash ignores key order. */
function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value !== null && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, v]) => v !== undefined)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
    return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonicalJson(v)}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

/**
 * The contract version (D5): the first 16 hex characters of sha256 over the
 * canonical JSON of the command surface, the languages and the error codes.
 * Translations are left out: they do not change what the executor accepts. The
 * web bundle and the executor ship separately, and what must match is the
 * surface each was built against, not the release tag.
 */
function contractVersion(
  surface: Pick<CliContract, 'commands' | 'languages' | 'errorCodes'>
): string {
  return createHash('sha256').update(canonicalJson(surface)).digest('hex').slice(0, 16);
}

const version = contractVersion({ commands, languages, errorCodes });
const contract: CliContract = { version, languages, commands, errorCodes };

const invariantProblems = checkContractInvariants(contract);
if (invariantProblems.length > 0) {
  console.error('\x1b[31m✗ Contract invariants failed\x1b[0m\n');
  for (const problem of invariantProblems) console.error(`  ${problem}`);
  process.exit(1);
}

// ---------- Emit ----------

// tree-write: safe outputDir is --output when given; check_cli_contract.py always passes a TemporaryDirectory
fs.mkdirSync(path.join(outputDir, 'i18n'), { recursive: true });

const generatedTs = `// AUTO-GENERATED by packages/cli/scripts/generate-cli-contract.ts - DO NOT EDIT
// Run: npm run generate:cli-contract -w @rediacc/cli
// Source: the live Commander tree + COMMAND_METADATA + command-registry + i18n

import type { CliContract } from '../types.js';

export const CLI_CONTRACT_VERSION = '${version}';

export const CLI_CONTRACT: CliContract = ${JSON.stringify(contract, null, 2)};
`;

// tree-write: safe outputDir is --output when given; check_cli_contract.py always passes a TemporaryDirectory
fs.writeFileSync(path.join(outputDir, 'contract.generated.ts'), generatedTs, 'utf-8');

const versionTs = `// AUTO-GENERATED by packages/cli/scripts/generate-cli-contract.ts - DO NOT EDIT
// Run: npm run generate:cli-contract -w @rediacc/cli
// The contract version alone, so a web bundle can send it without loading the contract.

export const CLI_CONTRACT_VERSION = '${version}';
`;
// tree-write: safe outputDir is --output when given; check_cli_contract.py always passes a TemporaryDirectory
fs.writeFileSync(path.join(outputDir, 'contract-version.generated.ts'), versionTs, 'utf-8');
// tree-write: safe outputDir is --output when given; check_cli_contract.py always passes a TemporaryDirectory
fs.writeFileSync(
  path.join(outputDir, 'contract.json'),
  JSON.stringify(contract, null, 2) + '\n',
  'utf-8'
);

for (const lang of languages) {
  const strings = Object.fromEntries(
    [...flattenHelpNamespaces(loadLocale(lang))].sort(([a], [b]) => a.localeCompare(b))
  );
  // tree-write: safe outputDir is --output when given; check_cli_contract.py always passes a TemporaryDirectory
  fs.writeFileSync(
    path.join(outputDir, 'i18n', `${lang}.json`),
    JSON.stringify(strings, null, 2) + '\n',
    'utf-8'
  );
}

// ---------- Report ----------

const planeCounts = commands.reduce<Record<string, number>>((acc, c) => {
  acc[c.plane] = (acc[c.plane] ?? 0) + 1;
  return acc;
}, {});

console.log(`\x1b[32m✓\x1b[0m Wrote CLI contract to ${outputDir}`);
console.log(`  Commands:      ${commands.length}`);
console.log(
  `  Planes:        ${Object.entries(planeCounts)
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([k, v]) => `${k}=${v}`)
    .join(' ')}`
);
console.log(`  proxyCapable:  ${commands.filter((c) => c.proxyCapable).length}`);
console.log(`  Interactive:   ${commands.filter((c) => c.interactive).length}`);
console.log(`  Languages:     ${languages.length}`);
console.log(`  Error codes:   ${errorCodes.length}`);
console.log(`  Version:       ${version}`);
