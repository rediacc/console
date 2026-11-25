/**
 * `rdc completion bash|zsh|fish|pwsh` and the hidden `rdc __complete`
 * (D9 of PLAN-console-command-line).
 *
 * The printed script carries every command, flag and choice word of the
 * contract, read through the command line core at print time, so static
 * completion runs in the shell alone. A value slot bound to a config-sourced
 * resource kind asks `rdc __complete --kind <k> [--config <n>]` for names, and
 * the script keeps each answer for the shell session, keyed on the config
 * file's mtime, so only the first lookup after a config change pays a CLI start.
 *
 * `__complete` reads the config file directly. cli.ts answers it from
 * {@link createCompleteProgram}, a program holding only this command, so the
 * full command tree is never built for it and it never reaches the contract.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  CLI_CONTRACT,
  type CliContract,
  type ContractCommand,
  type ContractOption,
  type ContractPositional,
  RESOURCE_DISCOVERY,
  RESOURCE_KINDS,
  type ResourceKind,
} from '@rediacc/shared/cli-contract';
import { GLOBAL_OPTIONS, optionKinds, positionalKinds } from '@rediacc/shared/command-line';
import { childrenOf } from '@rediacc/shared/command-line/contract-index';
import { getConfigDir } from '@rediacc/shared/paths';
import { composeRef } from '@rediacc/shared/ref';
import { Command } from 'commander';
import { t } from '../i18n/index.js';
import { getEffectiveConfigName } from '../services/config/config-name.js';
import { writeStdout } from '../services/core/request-context.js';
import { ValidationError } from '../types/errors.js';
import { handleError } from '../utils/errors.js';
import { renderModelScript } from './completion-scripts.js';

export const COMPLETE_COMMAND = '__complete';

export const COMPLETION_SHELLS = ['bash', 'zsh', 'fish', 'pwsh'] as const;
export type CompletionShell = (typeof COMPLETION_SHELLS)[number];

/** Kinds whose names live in the config file; the rest need a discovery command and get no names. */
const CONFIG_KINDS: readonly ResourceKind[] = RESOURCE_KINDS.filter(
  (kind) => RESOURCE_DISCOVERY[kind].source === 'config'
);

// ── Static model ─────────────────────────────────────────────────────────

/**
 * One node of the command path tree, keyed `rdc`, `rdc repo`, `rdc repo fork`.
 * A value spec is a word list: a literal choice, `@<kind>` for the names of a
 * config kind, or `%file` for a path.
 */
interface CompletionNode {
  key: string;
  children: string[];
  runnable: boolean;
  /** Long flags offered for completion. */
  flags: string[];
  /** Every spelling (long and short) of a value-taking flag, so the walker skips its value. */
  valueFlags: string[];
  /** Value spec per long flag, only for flags with one. */
  flagValues: [string, string[]][];
  /** Value spec per positional, in order. */
  positionals: string[][];
  variadic: boolean;
}

export interface CompletionModel {
  nodes: CompletionNode[];
  globalFlags: string[];
  globalValueFlags: string[];
}

const FILE_SPEC = '%file';
const SAFE_WORD = /^[A-Za-z0-9][A-Za-z0-9._:/+=,-]*$/;
const SAFE_FLAG = /^--?[A-Za-z0-9][A-Za-z0-9_-]*$/;

/** Every word lands unquoted-safe in four shell languages, so anything else is refused at print time. */
function checked(word: string, pattern: RegExp): string {
  if (!pattern.test(word)) {
    throw new ValidationError(t('commands.completion.errors.unsafeWord', { word }));
  }
  return word;
}

function kindWords(kinds: readonly ResourceKind[]): string[] {
  return kinds.filter((kind) => CONFIG_KINDS.includes(kind)).map((kind) => `@${kind}`);
}

function optionSpec(command: ContractCommand, option: ContractOption): string[] {
  const choices = (option.choices ?? []).map((c) => checked(c, SAFE_WORD));
  return [...choices, ...kindWords(optionKinds(command, option))];
}

function positionalSpec(positional: ContractPositional): string[] {
  if (positional.kind === 'file') return [FILE_SPEC];
  return kindWords(positionalKinds(positional));
}

function flagSpellings(option: ContractOption): string[] {
  const long = checked(`--${option.long}`, SAFE_FLAG);
  return option.short ? [long, checked(`-${option.short}`, SAFE_FLAG)] : [long];
}

function commandFields(command: ContractCommand | undefined) {
  if (!command) {
    return { runnable: false, flags: [], valueFlags: [], flagValues: [], positionals: [] };
  }
  const flags = command.options.map((o) => checked(`--${o.long}`, SAFE_FLAG));
  const valueFlags = command.options.filter((o) => o.valueTaking).flatMap(flagSpellings);
  const flagValues = command.options
    .filter((o) => o.valueTaking)
    .map((o): [string, string[]] => [`--${o.long}`, optionSpec(command, o)])
    .filter(([, spec]) => spec.length > 0);
  return {
    runnable: true,
    flags,
    valueFlags,
    flagValues,
    positionals: command.positionals.map(positionalSpec),
  };
}

/** Every path prefix of the contract, root first, in contract order. */
function pathPrefixes(contract: CliContract): string[][] {
  const seen = new Set<string>();
  const prefixes: string[][] = [[]];
  for (const command of contract.commands) {
    for (let n = 1; n <= command.path.length; n++) {
      const prefix = command.path.slice(0, n);
      const key = prefix.join(' ');
      if (seen.has(key)) continue;
      seen.add(key);
      prefixes.push(prefix);
    }
  }
  return prefixes;
}

/** The static words of every shell script, read from the contract through the command line core. */
export function buildCompletionModel(contract: CliContract): CompletionModel {
  const byKey = new Map(contract.commands.map((c) => [c.pathKey, c]));
  const nodes = pathPrefixes(contract).map((prefix): CompletionNode => {
    const command = prefix.length > 0 ? byKey.get(prefix.join(' ')) : undefined;
    return {
      key: ['rdc', ...prefix].join(' '),
      children: childrenOf(contract, prefix).map((child) => checked(child.word, SAFE_WORD)),
      variadic: command?.positionals.at(-1)?.variadic ?? false,
      ...commandFields(command),
    };
  });
  return {
    nodes,
    globalFlags: GLOBAL_OPTIONS.map((o) => `--${o.long}`),
    globalValueFlags: GLOBAL_OPTIONS.filter((o) => o.valueTaking).flatMap((o) =>
      o.short ? [`--${o.long}`, `-${o.short}`] : [`--${o.long}`]
    ),
  };
}

export function renderCompletionScript(shell: CompletionShell, contract: CliContract): string {
  return renderModelScript(shell, buildCompletionModel(contract));
}

function parseShell(value: string): CompletionShell {
  const shell = COMPLETION_SHELLS.find((s) => s === value);
  if (!shell) {
    throw new ValidationError(
      t('commands.completion.errors.unknownShell', {
        shell: value,
        shells: COMPLETION_SHELLS.join(', '),
      })
    );
  }
  return shell;
}

export function registerCompletionCommand(program: Command): void {
  program
    .command('completion')
    .summary(t('commands.completion.descriptionShort'))
    .description(t('commands.completion.description'))
    .argument('<shell>', t('commands.completion.shellArgument'))
    .action((shell: string) => {
      try {
        writeStdout(renderCompletionScript(parseShell(shell), CLI_CONTRACT));
      } catch (error) {
        handleError(error);
      }
    });
}

// ── __complete: names from the local config file ───────────────────────────

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function parseConfigKind(value: string): ResourceKind {
  const kind = CONFIG_KINDS.find((k) => k === value);
  if (!kind) {
    throw new ValidationError(
      t('commands.completion.errors.unknownKind', { kind: value, kinds: CONFIG_KINDS.join(', ') })
    );
  }
  return kind;
}

function readConfigFile(file: string): Record<string, unknown> {
  let text: string;
  try {
    text = readFileSync(file, 'utf-8');
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
    throw new ValidationError(t('commands.completion.errors.configMissing', { path: file }));
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    // The parser's message may quote the file's text, which can hold tokens: name only the file.
    throw new ValidationError(
      t('commands.completion.errors.configInvalid', { path: file, error: 'not valid JSON' })
    );
  }
  if (!isRecord(parsed)) {
    throw new ValidationError(
      t('commands.completion.errors.configInvalid', { path: file, error: typeof parsed })
    );
  }
  return parsed;
}

/** Every repository ref: the bare family name for the grand tag, `name:tag` for a fork. */
function repoRefs(families: Record<string, unknown>, file: string): string[] {
  return Object.entries(families).flatMap(([family, record]) => {
    if (!isRecord(record) || !isRecord(record.tags)) {
      throw new ValidationError(
        t('commands.completion.errors.configInvalid', { path: file, error: family })
      );
    }
    const grand = record.grand;
    return Object.keys(record.tags).map((tag) =>
      composeRef(family, tag === grand ? undefined : tag)
    );
  });
}

/** Names of one config-sourced kind in a parsed config file. */
function resourceNames(
  config: Record<string, unknown>,
  kind: ResourceKind,
  file: string
): string[] {
  const source = RESOURCE_DISCOVERY[kind];
  if (source.source !== 'config') return [];
  const resources = isRecord(config.resources) ? config.resources : {};
  const family = resources[source.family];
  if (family === undefined) {
    // A remote config keeps its resources on the server; the local file is only a pointer.
    if (isRecord(config.remote)) {
      throw new ValidationError(t('commands.completion.errors.remoteConfig', { path: file }));
    }
    return [];
  }
  if (!isRecord(family)) {
    throw new ValidationError(
      t('commands.completion.errors.configInvalid', { path: file, error: source.family })
    );
  }
  return kind === 'repo' ? repoRefs(family, file) : Object.keys(family);
}

/** A config name is one file stem: no path separator and no leading dot (so no `..`), so the lookup stays in the config dir. */
const PLAIN_CONFIG_NAME = /^(?!\.)[^/\\\0]+$/;

/** The names `rdc __complete` prints: the config file is `<config dir>/<name>.json`. */
export function completeNames(options: { kind: string; config?: string }): string[] {
  const kind = parseConfigKind(options.kind);
  const name = options.config ?? getEffectiveConfigName();
  if (!PLAIN_CONFIG_NAME.test(name)) {
    throw new ValidationError(
      t('commands.completion.errors.configInvalid', {
        path: name,
        error: 'not a plain config name',
      })
    );
  }
  const file = join(getConfigDir(), `${name}.json`);
  return resourceNames(readConfigFile(file), kind, file);
}

/** True when this process was started as `rdc __complete ...`. */
export function isCompleteInvocation(argv: readonly string[]): boolean {
  return argv[2] === COMPLETE_COMMAND;
}

/** A program holding only `__complete`, so a name lookup never builds the full command tree. */
export function createCompleteProgram(): Command {
  const program = new Command('rdc');
  program
    .command(COMPLETE_COMMAND, { hidden: true })
    .summary(t('commands.completion.complete.descriptionShort'))
    .requiredOption('--kind <kind>', t('commands.completion.complete.kindOption'))
    .option('--config <name>', t('commands.completion.complete.configOption'))
    .action((options: { kind: string; config?: string }) => {
      try {
        const names = completeNames(options);
        writeStdout(names.map((name) => `${name}\n`).join(''));
      } catch (error) {
        handleError(error);
      }
    });
  return program;
}
