#!/usr/bin/env tsx
/**
 * CLI Contract Generator
 *
 * Joins the live Commander tree with COMMAND_METADATA (planes, policy, MCP
 * annotations), the command registry (domain grouping, experimental gating),
 * and the i18n catalogues, and emits the contract that drives the web console,
 * the `rdc --proxy` thin client, and the executor.
 *
 * Emits into packages/shared/src/cli-contract/data:
 *   contract.generated.ts   typed literal (the import surface)
 *   contract.json           same data, for consumers that load it as an asset
 *   i18n/<lang>.json        per-language strings, lazily loadable
 *
 * Usage:
 *   npx tsx packages/cli/scripts/generate-cli-contract.ts [--output <dir>] [--version <v>]
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Option } from 'commander';
import type {
  CliContract,
  CommandGroup,
  ContractCommand,
  ContractOption,
  ContractPositional,
  PositionalKind,
} from '../../shared/src/cli-contract/types.js';
import { cli } from '../src/cli.js';
import { COMMAND_METADATA, READ_TIMEOUT, WRITE_TIMEOUT } from '../src/config/command-metadata.js';
import { getCommandPlane, isInteractiveCommand } from '../src/config/command-planes.js';
import { COMMAND_REGISTRY } from '../src/config/command-registry.js';
import {
  createDescriptionResolver,
  flattenHelpNamespaces,
  GLOBAL_OPTION_LONGS,
  listLocales,
  loadLocale,
  walkContractCommands,
} from './lib/command-tree-lib.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Machine-plane commands a remote executor must never run for the caller, and
 * why. Each reason is user-facing: the CLI prints it when `--proxy` refuses the
 * command, so it must say what the operator should do instead.
 *
 * Two distinct classes end up here.
 *
 * 1. Client-side transfer — the file paths exist only on the operator's own
 *    disk, so an executor could not see them. (This is NOT the same as building
 *    params from a local file: `repo template apply --file` reads the file and
 *    base64s the bytes INTO the renet params, which crosses the wire fine and
 *    stays proxyable.)
 *
 * 2. Local effect — the command reaches a machine, but its whole point is to
 *    write what it found back into the CALLER's config or filesystem. A remote
 *    executor would write it into its own, and the caller would be none the
 *    wiser. The wire carries params and events, not config mutations.
 */
const PROXY_EXCLUSIONS: Record<string, string> = {
  // ── Client-side transfer ──────────────────────────────────────────────
  'repo sync upload':
    'Uploads from the local filesystem with rsync/SFTP; a remote executor cannot see the source paths. Run it without --proxy.',
  'repo sync download':
    'Downloads to the local filesystem with rsync/SFTP; a remote executor would write the files onto its own disk. Run it without --proxy.',
  // Registered as a dry-run download: it still shells out to a client-side
  // rsync that diffs against the operator's local tree.
  'repo sync status':
    'Diffs the machine against the local filesystem with a client-side rsync; a remote executor has no copy of the local tree. Run it without --proxy.',

  // ── Local effect ──────────────────────────────────────────────────────
  'machine infra cert pull':
    "Its effect is writing the machine's acme.json into the caller's local config; a remote executor would write it into its own. Run it without --proxy.",
  'cluster kubeconfig':
    'Caches the kubeconfig to a local 0600 file and prints that path; a remote executor would write the file onto its own disk. Run it without --proxy.',
  'machine scan-keys':
    "Runs ssh-keyscan from the caller's network position and stores knownHosts in the caller's local config; a remote executor would scan from its own and keep the result. Run it without --proxy.",
  'config reconcile':
    "It queries every machine but writes the result into the CALLER's local state bucket; a remote executor would rebuild its own state and the caller would be none the wiser. Run it without --proxy.",
};

/**
 * Machine-plane commands that are proxyable but must NOT be detached, keyed by
 * command path, with the reason.
 *
 * Empty for now: `detachable = proxyCapable && domain !== 'job'` already covers
 * every current case (the classes proxyCapable excludes are exactly the ones
 * that break under detach, and `rdc job *` manages jobs rather than doing
 * machine work). This table exists as the escape hatch for a proxyable,
 * non-job command that a future reshape must keep synchronous: the analog of
 * PROXY_EXCLUSIONS one layer up.
 */
const DETACH_EXCLUSIONS: Record<string, string> = {};

/**
 * What a positional token names, keyed by its argument name.
 *
 * The addressing grammar (docs/design/spec/03-cli-contracts.md §2.2) names each
 * noun's positional so that the NAME already signals the kind: a repo verb's
 * `<repo-ref>`, a datastore verb's `<datastore-ref>`, `storage import`'s
 * `<file>`. So the classifier keys on the argument name, with a couple of
 * domain refinements where the same bare name means different things.
 */
const POSITIONAL_KIND_BY_NAME: Record<string, PositionalKind> = {
  ref: 'repo-ref',
  'repo-ref': 'repo-ref',
  // Repo-ref aliases: some repo verbs name their positional by role for clarity
  // (`repo fork <parent-ref>`, `repo promote <fork-ref>`, `repo checkout
  // <commit-or-branch-ref>`, `repo merge --from <source-ref>`). They all name a
  // repo, so they bind the console's repo picker exactly like `<ref>`.
  'parent-ref': 'repo-ref',
  'fork-ref': 'repo-ref',
  'commit-or-branch-ref': 'repo-ref',
  'source-ref': 'repo-ref',
  machine: 'machine',
  datastore: 'datastore-ref',
  'datastore-ref': 'datastore-ref',
  cluster: 'cluster',
  strategy: 'strategy',
  artifact: 'artifact-ref',
  'artifact-ref': 'artifact-ref',
  storage: 'storage',
  file: 'file',
  target: 'target',
  'job-id': 'job-id',
};

function classifyPositional(domain: string, name: string): PositionalKind {
  // `rdc job status <job-id>` and `rdc job logs <job-id>` name the job; an `id`
  // argument on the `job` domain is the same thing under an older spelling.
  if (domain === 'job' && (name === 'id' || name === 'job-id')) return 'job-id';
  return POSITIONAL_KIND_BY_NAME[name] ?? 'plain';
}

/** Why a command that reaches a machine still cannot be proxied. */
function proxyBlockedReason(
  pathKey: string,
  plane: string,
  interactive: boolean
): string | undefined {
  const excluded = PROXY_EXCLUSIONS[pathKey];
  if (excluded) return excluded;
  if (interactive) {
    return 'Needs a terminal or never returns on its own (interactive shell, editor, tunnel, stream, or daemon), so a headless executor cannot run it. Run it without --proxy.';
  }
  if (plane === 'config') {
    return 'Runs entirely against the local config and never reaches a machine, so there is nothing to proxy. Run it without --proxy.';
  }
  if (plane === 'other') {
    return 'Local tooling that never reaches a machine, so there is nothing to proxy. Run it without --proxy.';
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
/**
 * Fixed 'dev' by default so regeneration is deterministic and the staleness
 * gate can diff. The real version is injected at build time, like the renet
 * contract's *_VERSION constants.
 */
const version = readArg('version', 'dev');

// ---------- Registry lookup ----------

const registryByName = new Map(COMMAND_REGISTRY.map((c) => [c.name, c]));

function resolveGroup(domain: string): CommandGroup | null {
  return (registryByName.get(domain)?.domain as CommandGroup | undefined) ?? null;
}

/** Experimental commands are hidden unless REDIACC_EXPERIMENTAL=1. */
function resolveExperimental(pathSegments: string[]): boolean {
  const def = registryByName.get(pathSegments[0]);
  if (!def) return false;
  if (def.experimental) return true;
  if (pathSegments.length < 2) return false;
  return def.subcommands?.[pathSegments[1]]?.experimental === true;
}

// ---------- Options ----------

function stripDashes(flag: string): string {
  return flag.replace(/^-+/, '');
}

function toContractOption(
  opt: Option,
  resolver: ReturnType<typeof createDescriptionResolver>
): ContractOption {
  if (!opt.long) {
    throw new Error(
      `Option "${opt.flags}" has no long flag. The contract identifies options by ` +
        'their long flag so consumers can serialise a command back to argv; ' +
        'give every option a long form.'
    );
  }

  const defaultValue =
    opt.defaultValue === undefined ||
    opt.defaultValue === null ||
    typeof opt.defaultValue === 'function' ||
    (Array.isArray(opt.defaultValue) && opt.defaultValue.length === 0)
      ? null
      : String(opt.defaultValue);

  // Commander stores a .choices([...]) declaration on argChoices. Its presence
  // is what tells a consumer to render a Select instead of a text input.
  const choices = opt.argChoices;

  return {
    flags: opt.flags,
    long: stripDashes(opt.long),
    ...(opt.short ? { short: stripDashes(opt.short) } : {}),
    valueTaking: opt.required || opt.optional,
    variadic: opt.variadic,
    mandatory: opt.mandatory ?? false,
    defaultValue,
    ...(choices && choices.length > 0 ? { choices: [...choices] } : {}),
    descriptionKey: resolver.findDescriptionKey(opt.description),
    label: opt.description,
  };
}

/**
 * Which option names the target machine: `--machine` when the command has one,
 * otherwise `--name` on the `machine` domain (where the machine IS the subject,
 * e.g. `machine query --name`).
 */
function resolveMachineOption(domain: string, options: ContractOption[]): string | null {
  if (options.some((o) => o.long === 'machine')) return 'machine';
  if (domain === 'machine' && options.some((o) => o.long === 'name')) return 'name';
  return null;
}

/**
 * Which option names the target repository: the MCP `repoArg` annotation when
 * present (it exists to answer exactly this), otherwise `--repo`, otherwise
 * `--name` on the `repo` domain.
 */
function resolveRepoOption(
  domain: string,
  options: ContractOption[],
  repoArg: string | undefined
): string | null {
  if (repoArg && options.some((o) => o.long === repoArg)) return repoArg;
  if (options.some((o) => o.long === 'repo')) return 'repo';
  if (domain === 'repo' && options.some((o) => o.long === 'name')) return 'name';
  return null;
}

/**
 * Which POSITIONAL names the target machine / repository, kept distinct from the
 * FLAG bindings above. A `machine`-kind positional names a machine; a
 * `repo-ref`-kind positional names a repo. This is what lets `targetFrom` scope
 * policy on a positional-addressed command, and the console bind its pickers to
 * the ref rather than to a flag that no longer exists.
 */
function resolveMachinePositional(positionals: ContractPositional[]): string | null {
  return positionals.find((p) => p.kind === 'machine')?.name ?? null;
}

function resolveRepoPositional(positionals: ContractPositional[]): string | null {
  return positionals.find((p) => p.kind === 'repo-ref')?.name ?? null;
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
 * that goes stale through a rename does not fail loudly — the lookup simply misses,
 * the exclusion STOPS EXCLUDING, and the command silently becomes proxyCapable.
 *
 * That is bug #51's exact failure mode occurring inside the mechanism built to
 * prevent it: `machine scan-keys` is excluded because it scans from the CALLER's
 * network position and stores the result in the CALLER's config. Rename it, forget
 * this key, and a remote executor starts scanning from its own network and keeping
 * the answer — with no gate anywhere saying so.
 *
 * COMMAND_PLANES already has this protection (plane-coverage.test.ts fails on a stale
 * entry). Its sibling did not. It does now.
 */
const livePathKeys = new Set(walked.map((w) => w.pathKey));
const staleExclusions = [
  ...Object.keys(PROXY_EXCLUSIONS).map((k) => [k, 'PROXY_EXCLUSIONS'] as const),
  ...Object.keys(DETACH_EXCLUSIONS).map((k) => [k, 'DETACH_EXCLUSIONS'] as const),
].filter(([pathKey]) => !livePathKeys.has(pathKey));

if (staleExclusions.length > 0) {
  console.error('\x1b[31m✗ Stale exclusion keys — these commands do not exist\x1b[0m\n');
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

const commands: ContractCommand[] = walked.map((w) => {
  const domain = w.path[0];
  const meta = COMMAND_METADATA[w.pathKey];
  const mcp = meta?.mcp;
  const plane = getCommandPlane(w.pathKey);
  const interactive = isInteractiveCommand(w.pathKey);

  // Re-extract options from the live command so the contract carries the rich
  // shape (long/short/valueTaking/variadic) that argv serialisation needs.
  const liveCommand = w.path.reduce<import('commander').Command | undefined>(
    (cmd, segment) => cmd?.commands.find((c) => c.name() === segment),
    cli
  );
  if (!liveCommand) throw new Error(`Could not re-resolve command "${w.pathKey}" in the tree`);

  const options = liveCommand.options
    .filter((o) => !GLOBAL_OPTION_LONGS.has(o.long ?? ''))
    .map((o) => toContractOption(o, resolver));

  const positionals: ContractPositional[] = w.positionals.map((p) => ({
    name: p.name,
    kind: classifyPositional(domain, p.name),
    required: p.required,
    variadic: p.variadic,
    descriptionKey: p.descriptionKey,
    label: p.label,
  }));

  const proxyCapable = plane === 'machine' && !interactive && !(w.pathKey in PROXY_EXCLUSIONS);
  const blockedReason = proxyCapable
    ? undefined
    : proxyBlockedReason(w.pathKey, plane, interactive);

  // Detach is the same predicate as proxy, minus jobs (they manage jobs, not
  // machine work) and an escape-hatch table. The serve dispatch turns it on for
  // a proxied command; `--background` turns it on for a local one.
  const detachable = proxyCapable && domain !== 'job' && !(w.pathKey in DETACH_EXCLUSIONS);

  return {
    path: w.path,
    pathKey: w.pathKey,
    domain,
    group: resolveGroup(domain),
    experimental: resolveExperimental(w.path),
    plane,
    descriptionKey: w.descriptionKey,
    label: liveCommand.description(),
    options,
    positionals,
    hasSubcommands: w.hasSubcommands,

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
    ...(blockedReason ? { proxyBlockedReason: blockedReason } : {}),
    detachable,

    machineOption: resolveMachineOption(domain, options),
    repoOption: resolveRepoOption(domain, options, mcp?.repoArg),
    machinePositional: resolveMachinePositional(positionals),
    repoPositional: resolveRepoPositional(positionals),
  };
});

commands.sort((a, b) => a.pathKey.localeCompare(b.pathKey));

const languages = listLocales();

const contract: CliContract = { version, languages, commands };

// ---------- Emit ----------

fs.mkdirSync(path.join(outputDir, 'i18n'), { recursive: true });

const generatedTs = `// AUTO-GENERATED by packages/cli/scripts/generate-cli-contract.ts - DO NOT EDIT
// Run: npm run generate:cli-contract -w @rediacc/cli
// Source: the live Commander tree + COMMAND_METADATA + command-registry + i18n

import type { CliContract } from '../types';

export const CLI_CONTRACT_VERSION = '${version}';

export const CLI_CONTRACT: CliContract = ${JSON.stringify(contract, null, 2)};
`;

fs.writeFileSync(path.join(outputDir, 'contract.generated.ts'), generatedTs, 'utf-8');
fs.writeFileSync(
  path.join(outputDir, 'contract.json'),
  JSON.stringify(contract, null, 2) + '\n',
  'utf-8'
);

for (const lang of languages) {
  const strings = Object.fromEntries(
    [...flattenHelpNamespaces(loadLocale(lang))].sort(([a], [b]) => a.localeCompare(b))
  );
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
    .sort()
    .map(([k, v]) => `${k}=${v}`)
    .join(' ')}`
);
console.log(`  proxyCapable:  ${commands.filter((c) => c.proxyCapable).length}`);
console.log(`  Interactive:   ${commands.filter((c) => c.interactive).length}`);
console.log(`  Languages:     ${languages.length}`);
