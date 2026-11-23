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
import type { Option } from 'commander';
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
  PositionalKind,
} from '../../shared/src/cli-contract/types.js';
import {
  checkContractInvariants,
  SUMMARY_MAX_LENGTH,
} from '../../shared/src/cli-contract/validation.js';
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
import { parseExampleValues } from './lib/example-parse.js';
import {
  collectClassificationProblems,
  resolveOptionFormat,
  resolveOptionKinds,
  resolveOptionSensitive,
  resolveOptionTier,
} from './lib/option-classification.js';
import { at } from './lib/table.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Machine-plane commands a remote executor must never run for the caller, and
 * why. Each reason is user-facing: the CLI prints it when `--proxy` refuses the
 * command, so it must say what the operator should do instead.
 *
 * Two distinct classes end up here.
 *
 * 1. Client-side transfer: the file paths exist only on the operator's own
 *    disk, so an executor could not see them. (This is NOT the same as building
 *    params from a local file: `repo template apply --file` reads the file and
 *    base64s the bytes INTO the renet params, which crosses the wire fine and
 *    stays proxyable.)
 *
 * 2. Local effect: the command reaches a machine, but its whole point is to
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
  // Registered as a dry-run download: it still shells out to a client-side rsync that diffs against the operator's local tree.
  'repo sync status':
    'Diffs the machine against the local filesystem with a client-side rsync; a remote executor has no copy of the local tree. Run it without --proxy.',
  'backup download':
    'Copies the repository image to a local directory with a client-side rsync; a remote executor would write the image onto its own disk. Run it without --proxy.',
  'backup upload':
    'Sends a local image file with a client-side rsync and registers the repository in the local config; a remote executor cannot see the file. Run it without --proxy.',

  // ── The operator's credential ─────────────────────────────────────────
  'backup churn':
    'a client-side loop of probes that can run for hours, and it must forget its base when it ends',
  'backup check':
    'reads a listing and restores a file with the repository credential, which stays where the config lives',
  'backup repair':
    "Deletes bad chunks on the account with the caller's backup:manage token, then re-uploads from the machine; a remote executor holds neither the token nor the caller's config. Run it without --proxy.",
  'backup toc-key sync':
    'derives the public key from the repository credential, which stays where the config lives',

  // ── Local effect ──────────────────────────────────────────────────────
  'machine infra cert pull':
    "Its effect is writing the machine's acme.json into the caller's local config; a remote executor would write it into its own. Run it without --proxy.",
  'cluster kubeconfig':
    'Caches the kubeconfig to a local 0600 file and prints that path; a remote executor would write the file onto its own disk. Run it without --proxy.',
  'machine scan-keys':
    "Runs ssh-keyscan from the caller's network position and stores knownHosts in the caller's local config; a remote executor would scan from its own and keep the result. Run it without --proxy.",
  'config reconcile':
    "It queries every machine but writes the result into the CALLER's local state bucket; a remote executor would rebuild its own state and the caller would be none the wiser. Run it without --proxy.",
  'machine access push':
    "Rewrites who may log in to the machine from the CALLER's access keys; an executor never rewrites the access it connects with, and it would push its own config's keys. Run it without --proxy.",

  // ── The install record and child processes on the caller's machine ─────
  'server status':
    "Finds the server through the caller's local install record; a remote executor holds none. Run it without --proxy.",
  'server upgrade':
    "Drives child commands and the caller's local install record (and --local-image, the caller's Docker); a remote executor would act from its own. Run it without --proxy.",
  'server backup':
    "Writes the recovery bundle (the server's keys) to the caller's terminal or file; through an executor the keys would cross another machine. Run it without --proxy.",
  'server bundle':
    "Runs the caller's local docker (pull and save) and writes the bundle to the caller's disk; a remote executor would write it to its own. Run it without --proxy.",
  'server licence mint':
    "Mints the certificate with the caller's login and writes it to the caller's file; a remote executor holds neither. Run it without --proxy.",
  'server licence':
    "Mints the certificate with the caller's login and records it in the caller's local install record; a remote executor holds neither. Run it without --proxy.",

  // ── The caller's config set ───────────────────────────────────────────
  'repo admin orphan list':
    "Judges each image against every config the CALLER can read; a remote executor would judge against its own configs and report the caller's repositories as orphans. Run it without --proxy.",
  'repo admin orphan delete':
    "Refuses a GUID any config the CALLER can read still names; a remote executor would check its own configs and could delete an image the caller's config names. Run it without --proxy.",

  'machine prune':
    "With --orphaned-repos or --prune-unknown it judges each image against every config the CALLER can read; a remote executor would judge against its own configs and delete the caller's repositories. Run it without --proxy.",

  // ── Caller-held secrets ───────────────────────────────────────────────
  'machine converge':
    "Restarts each repo daemon with the env secrets from the CALLER's config; a remote executor would restart them with its own copy, or with none. Run it without --proxy.",
};

/**
 * Proxyable machine-plane commands that do NOT run as a machine job, keyed by
 * command path, with the reason (agent/plans/PLAN-detached-jobs.md section 24
 * and the J0b audit). Every other proxyable, non-`job` command is `detachable`:
 * its renet calls run as one machine job (section 14), and `--background`
 * returns the ticket at once.
 *
 * Each reason is user-facing: `--background` prints it when it refuses the
 * command (`detachBlockedReason` in the contract), so it says why and what to
 * run instead.
 */
const DETACH_EXCLUSIONS: Record<string, string> = {
  'cluster destroy':
    'Tears the cluster down with local OpenTofu or ops calls and never reaches a machine over SSH, so there is no machine job to detach. Run it without --background.',
  'datastore list':
    'Reads the local config and state only and makes no machine call, so there is no machine job to detach. Run it without --background.',
  'machine deprovision':
    'Destroys the machine with local OpenTofu and has no SSH leg, so there is no machine job to detach. Run it without --background.',
  'machine infra cert push':
    'Writes the local certificate cache to the machine in one raw file write, with no renet call to run as a job. Run it without --background.',
  'vscode serve status':
    'Runs a script as the repository user, not as root, so it cannot run as a root job unit. Run it without --background.',
  'vscode serve stop':
    'Runs a script as the repository user, not as root, so it cannot run as a root job unit. Run it without --background.',
};

/**
 * What a positional token names, keyed by its argument name.
 *
 * The addressing grammar (docs/design/spec/03-cli-contracts.md §2.2) names each
 * noun's positional so that the NAME already signals the kind: a repo verb's
 * `<repo-ref>`, a datastore verb's `<datastore-ref>`, a file argument's
 * `<file>`. So the classifier keys on the argument name, with a couple of
 * domain refinements where the same bare name means different things.
 */
const POSITIONAL_KIND_BY_NAME: Record<string, PositionalKind> = {
  ref: 'repo-ref',
  'repo-ref': 'repo-ref',
  // Repo-ref aliases: some repo verbs name their positional by role for clarity (`repo fork <parent-ref>`, `repo promote <fork-ref>`, `repo checkout <commit-or-branch-ref>`, `repo merge --from <source-ref>`). They all name a repo, so they bind the console's repo picker exactly like `<ref>`.
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
  file: 'file',
  target: 'target',
  'job-id': 'job-id',
};

/**
 * What an argument name the table does not classify falls back to: a plain
 * free-text token, binding no console picker.
 */
const DEFAULT_POSITIONAL_KIND: PositionalKind = 'plain';

/**
 * Machine-domain commands whose `<name>` positional names a machine (or
 * provider) that does NOT exist yet, so it must NOT bind the console's machine
 * picker. Everything else on the `machine` domain named `name` references an
 * existing machine (see `classifyPositional`).
 */
const MACHINE_NAME_CREATORS = new Set<string>([
  'machine add',
  'machine provision',
  'machine provider add',
]);

function classifyPositional(pathKey: string, domain: string, name: string): PositionalKind {
  // `rdc job status <job-id>` and `rdc job logs <job-id>` name the job; an `id`
  // argument on the `job` domain is the same thing under an older spelling.
  if (domain === 'job' && (name === 'id' || name === 'job-id')) return 'job-id';
  // `machine provider remove <name>` names an EXISTING configured provider, so the console can bind its provider picker to it. Path-aware on purpose: `machine provider add <name>` and `machine provision <name>` name NEW resources, so there is nothing to pick and they stay plain.
  if (pathKey === 'machine provider remove' && name === 'name') return 'provider';
  // A machine verb's `<name>` positional names an EXISTING configured machine (`machine status`, `health`, `deprovision`, `prune`, `remove`, `setup`, `scan-keys`), so the console can bind its machine picker to it and its container discovery / context / policy layers can resolve the machine from the ref. Same path-aware carve-out as `machine provider remove` above: the commands
  // below name a machine (or provider) that does NOT exist yet, so there is nothing to pick and they stay plain: `machine add` registers a brand-new machine under this name, `machine provision` provisions a brand-new cloud machine under this name, `machine provider add` names a new cloud PROVIDER, not a machine.
  if (domain === 'machine' && name === 'name' && !MACHINE_NAME_CREATORS.has(pathKey)) {
    return 'machine';
  }
  return POSITIONAL_KIND_BY_NAME[name] ?? DEFAULT_POSITIONAL_KIND;
}

/**
 * The refusal texts shared by every command of a class, keyed by their i18n key
 * under `commands.proxyBlocked.*`. A PROXY_EXCLUSIONS entry carries its own text
 * and is keyed by its camel-cased path (`proxyBlockedKeyFor`).
 */
const GENERIC_PROXY_BLOCKED = {
  interactive:
    'Needs a terminal or never returns on its own (interactive shell, editor, tunnel, stream, or daemon), so a headless executor cannot run it. Run it without --proxy.',
  localConfig:
    'Runs entirely against the local config and never reaches a machine, so there is nothing to proxy. Run it without --proxy.',
  localTooling:
    'Local tooling that never reaches a machine, so there is nothing to proxy. Run it without --proxy.',
} as const;

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

// ---------- Options ----------

function stripDashes(flag: string): string {
  return flag.replace(/^-+/, '');
}

function toContractOption(
  opt: Option,
  resolver: ReturnType<typeof createDescriptionResolver>,
  pathKey: string
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

  // Commander stores a .choices([...]) declaration on argChoices. Its presence is what tells a consumer to render a Select instead of a text input.
  const choices = opt.argChoices;

  // Classification (scripts/lib/option-classification.ts): kinds feed the console's pick-or-type combobox, format its input control, sensitive its masking/redaction, tier its progressive disclosure. All hints: none of them constrains what the CLI accepts.
  const long = stripDashes(opt.long);
  const valueTaking = opt.required || opt.optional;
  const mandatory = opt.mandatory;
  const kinds = resolveOptionKinds(pathKey, long, valueTaking);
  const format = valueTaking ? resolveOptionFormat(pathKey, long) : undefined;
  const sensitive = resolveOptionSensitive(pathKey, long);
  const tier = resolveOptionTier(pathKey, long, {
    mandatory,
    hasKinds: kinds !== undefined && kinds.length > 0,
    hasChoices: choices !== undefined && choices.length > 0,
  });

  return {
    flags: opt.flags,
    long,
    ...(opt.short ? { short: stripDashes(opt.short) } : {}),
    valueTaking,
    variadic: opt.variadic,
    mandatory,
    defaultValue,
    ...(choices && choices.length > 0 ? { choices: [...choices] } : {}),
    ...(kinds && kinds.length > 0 ? { kinds: [...kinds] } : {}),
    ...(format ? { format } : {}),
    tier,
    ...(sensitive ? { sensitive: true } : {}),
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
  } else if (liveSummary.length > SUMMARY_MAX_LENGTH) {
    curationProblems.push(
      `${pathKey}: summary is ${liveSummary.length} characters, over ${SUMMARY_MAX_LENGTH}`
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

  const proxyCapable = plane === 'machine' && !interactive && !(w.pathKey in PROXY_EXCLUSIONS);
  const blockedReason = proxyCapable
    ? undefined
    : proxyBlockedReason(w.pathKey, plane, interactive);
  if (blockedReason) checkProxyBlockedKey(w.pathKey, blockedReason);

  const summary = resolveSummary(w.pathKey, liveCommand.summary());
  const summaryKey = summary ? resolveSummaryKey(w.path, summary) : null;
  const severity = resolveSeverity(w.pathKey);
  const preview = resolvePreview(w.pathKey, options);

  // Every proxyable machine-plane command runs as one machine job (PLAN-detached-jobs section 14), minus the `job *` verbs (they read the spool) and the
  // section 24 exceptions in DETACH_EXCLUSIONS. `--background` is accepted exactly where this is true.
  const detachable = proxyCapable && domain !== 'job' && !(w.pathKey in DETACH_EXCLUSIONS);
  const detachBlockedReason = proxyCapable ? DETACH_EXCLUSIONS[w.pathKey] : undefined;

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

const errorCodes: ContractErrorCode[] = listErrorCodeOrigins()
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
