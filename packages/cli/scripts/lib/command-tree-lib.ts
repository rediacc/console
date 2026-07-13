/**
 * Shared Commander.js tree introspection.
 *
 * Factored out of export-command-tree.ts so that the CLI contract generator
 * (generate-cli-contract.ts) walks the exact same tree, with the exact same
 * i18n reverse lookup, as the docs command-tree export. export-command-tree.ts
 * must keep emitting a byte-identical command-tree.json after this refactor.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Argument, Command, Option } from 'commander';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** packages/cli/src/i18n/locales */
export const LOCALES_DIR = path.resolve(__dirname, '../../src/i18n/locales');

/**
 * The only i18n namespaces that carry command/option help text.
 *
 * Order is load-bearing: the reverse lookup is first-wins, so when the same
 * English string exists under both namespaces (e.g. "Skip confirmation prompt"
 * is both `options.yes` and `commands.machine.deprovision.optionForce`), the
 * generic `options.*` key must win. Reversing this silently rewrites
 * descriptionKeys in command-tree.json.
 */
export const HELP_NAMESPACES = ['options', 'commands'] as const;

// ---------- Types ----------

export interface CommandNode {
  name: string;
  descriptionKey: string | null;
  options: OptionNode[];
  arguments: ArgumentNode[];
  subcommands: CommandNode[];
}

export interface OptionNode {
  flags: string;
  descriptionKey: string | null;
  mandatory: boolean;
  defaultValue: string | null;
}

export interface ArgumentNode {
  name: string;
  required: boolean;
  variadic: boolean;
  defaultValue: string | null;
}

// ---------- Locale loading ----------

/** Read a locale's cli.json. */
export function loadLocale(lang: string): Record<string, unknown> {
  const file = path.join(LOCALES_DIR, lang, 'cli.json');
  return JSON.parse(fs.readFileSync(file, 'utf-8'));
}

/** The locales shipped with the CLI, sorted for deterministic output. */
export function listLocales(): string[] {
  return fs
    .readdirSync(LOCALES_DIR, { withFileTypes: true })
    .filter((e) => e.isDirectory())
    .map((e) => e.name)
    .sort();
}

/**
 * Flatten a nested object into a Map of dot-separated keys to string values.
 */
export function flattenObject(obj: Record<string, unknown>, prefix = ''): Map<string, string> {
  const result = new Map<string, string>();
  const recurse = (currentObj: Record<string, unknown>, p: string): void => {
    for (const [key, value] of Object.entries(currentObj)) {
      const fullKey = p ? `${p}.${key}` : key;
      if (typeof value === 'string') {
        result.set(fullKey, value);
      } else if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
        recurse(value as Record<string, unknown>, fullKey);
      }
    }
  };
  recurse(obj, prefix);
  return result;
}

/**
 * Flatten only the help-bearing namespaces (commands.*, options.*) of a locale.
 * This is what ships as a per-language contract bundle.
 */
export function flattenHelpNamespaces(cliJson: Record<string, unknown>): Map<string, string> {
  const result = new Map<string, string>();
  for (const namespace of HELP_NAMESPACES) {
    const nsData = cliJson[namespace];
    if (!nsData || typeof nsData !== 'object') continue;
    for (const [key, value] of flattenObject(nsData as Record<string, unknown>, namespace)) {
      result.set(key, value);
    }
  }
  return result;
}

// ---------- Reverse i18n lookup ----------

interface InterpolatedEntry {
  pattern: RegExp;
  key: string;
}

export interface DescriptionResolver {
  /** Find the i18n key for a given English description string. */
  findDescriptionKey(description: string): string | null;
  /** The flattened English help strings (the `commands` and `options` namespaces). */
  strings: Map<string, string>;
}

/**
 * Build a reverse lookup from English description strings to their i18n key
 * paths. Handles both exact matches and interpolated templates ({{...}}).
 *
 * Commander only ever hands us the rendered English string, so the key has to
 * be recovered by matching the value back to en/cli.json.
 */
export function createDescriptionResolver(cliJson: Record<string, unknown>): DescriptionResolver {
  const exact = new Map<string, string>();
  const interpolated: InterpolatedEntry[] = [];
  const strings = new Map<string, string>();

  for (const namespace of HELP_NAMESPACES) {
    const nsData = cliJson[namespace];
    if (!nsData || typeof nsData !== 'object') continue;
    const flat = flattenObject(nsData as Record<string, unknown>, namespace);
    for (const [key, value] of flat) {
      strings.set(key, value);
      if (value.includes('{{')) {
        const escaped = value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const pattern = new RegExp('^' + escaped.replace(/\\\{\\\{.*?\\\}\\\}/g, '.*') + '$');
        interpolated.push({ pattern, key });
      } else {
        if (!exact.has(value)) exact.set(value, key);
      }
    }
  }

  return {
    strings,
    findDescriptionKey(description: string): string | null {
      const exactKey = exact.get(description);
      if (exactKey) return exactKey;
      for (const { pattern, key } of interpolated) {
        if (pattern.test(description)) return key;
      }
      return null;
    },
  };
}

// ---------- Extraction helpers ----------

export function serialiseDefault(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value === 'function') return null;
  if (Array.isArray(value) && value.length === 0) return null;
  return String(value);
}

export function extractOption(opt: Option, resolver: DescriptionResolver): OptionNode {
  return {
    flags: opt.flags,
    descriptionKey: resolver.findDescriptionKey(opt.description),
    mandatory: opt.mandatory ?? false,
    defaultValue: serialiseDefault(opt.defaultValue),
  };
}

export function extractArgument(arg: Argument): ArgumentNode {
  return {
    name: arg.name(),
    required: arg.required,
    variadic: arg.variadic,
    defaultValue: serialiseDefault(arg.defaultValue),
  };
}

/**
 * A positional argument, serialised for the CONTRACT walker.
 *
 * Separate from ArgumentNode (which the docs command-tree export must keep
 * byte-identical): this one resolves the description back to its i18n key,
 * exactly as options do, so a consumer can translate a positional's help text.
 * The `kind` classification is the generator's job, not the walker's, because
 * only the generator knows the per-noun kind table.
 */
export interface WalkedPositional {
  name: string;
  required: boolean;
  variadic: boolean;
  descriptionKey: string | null;
  /** English description, always present (may be empty). */
  label: string;
}

export function extractContractPositional(
  arg: Argument,
  resolver: DescriptionResolver
): WalkedPositional {
  const description = (arg as Argument & { description?: string }).description ?? '';
  return {
    name: arg.name(),
    required: arg.required,
    variadic: arg.variadic,
    descriptionKey: description ? resolver.findDescriptionKey(description) : null,
    label: description,
  };
}

// ---------- Tree walker ----------

/** Global options that appear on every command and are excluded per-command. */
export const GLOBAL_OPTION_LONGS = new Set([
  '--output',
  '--context',
  '--lang',
  '--version',
  '--help',
]);

/**
 * Top-level commands held out of the generated contract.
 *
 * An entry here is invisible to EVERY consumer of the contract: the plane gate,
 * MCP coverage, console coverage and the docs checks all walk this tree. So a
 * stale entry fails OPEN — name a command that does not exist yet, and the day
 * someone adds it, it is silently exempt from all of them. `contract-surface`
 * (plane-coverage.test.ts) therefore asserts every entry is a live command.
 *
 * `run` is the deliberate one: the Rediaccfile-function escape hatch, an absolute
 * agent block, and not a shape the contract can describe.
 *
 * Pruned in P4: `login`/`logout` (now `subscription login`/`logout`), and
 * `trace`/`cancel`/`retry`, none of which are commands.
 */
export const EXCLUDED_TOP_LEVEL = new Set(['run']);

export function walkCommand(cmd: Command, resolver: DescriptionResolver): CommandNode | null {
  const name = cmd.name();
  if (name === 'help') return null;

  const rawDesc = cmd.description();
  const descriptionKey = rawDesc ? resolver.findDescriptionKey(rawDesc) : null;

  const options: OptionNode[] = [];
  for (const opt of cmd.options) {
    if (GLOBAL_OPTION_LONGS.has(opt.long ?? '')) continue;
    options.push(extractOption(opt, resolver));
  }

  const args: ArgumentNode[] = cmd.registeredArguments.map(extractArgument);

  const subcommands: CommandNode[] = [];
  for (const sub of cmd.commands) {
    const node = walkCommand(sub, resolver);
    if (node) subcommands.push(node);
  }

  return { name, descriptionKey, options, arguments: args, subcommands };
}

// ---------- Contract walker ----------

/**
 * A command that gets its own contract entry: every leaf, plus any group that
 * carries its own action handler (e.g. `repo replicate`, `repo canary`,
 * `repo replicate` are runnable AND have subcommands).
 */
export interface WalkedCommand {
  path: string[];
  /** Space-joined path, e.g. "repo secret list". */
  pathKey: string;
  descriptionKey: string | null;
  options: OptionNode[];
  /** Positional arguments in declared order, [] for the options-only leaves. */
  positionals: WalkedPositional[];
  hasSubcommands: boolean;
}

/** Commander marks a runnable command by attaching an action handler. */
function hasActionHandler(cmd: Command): boolean {
  return (cmd as Command & { _actionHandler?: unknown })._actionHandler != null;
}

/**
 * Walk the live tree and collect every command that is directly runnable:
 * leaves, plus groups that also registered an action handler.
 *
 * Positional arguments are serialised into `positionals` (they used to throw:
 * the contract was options-only, and every consumer serialised a command as
 * flags alone). The ref concept added the serialisation rule the throw guarded,
 * so a positional now travels as a bare token before the flags.
 */
export function walkContractCommands(
  root: Command,
  resolver: DescriptionResolver
): WalkedCommand[] {
  const result: WalkedCommand[] = [];

  const visit = (cmd: Command, prefix: string[]): void => {
    const name = cmd.name();
    if (name === 'help') return;
    if (prefix.length === 0 && EXCLUDED_TOP_LEVEL.has(name)) return;

    const commandPath = [...prefix, name];
    const pathKey = commandPath.join(' ');

    const subcommands = cmd.commands.filter((c) => c.name() !== 'help');
    const runnable = subcommands.length === 0 || hasActionHandler(cmd);

    if (runnable) {
      const rawDesc = cmd.description();
      const options: OptionNode[] = [];
      for (const opt of cmd.options) {
        if (GLOBAL_OPTION_LONGS.has(opt.long ?? '')) continue;
        options.push(extractOption(opt, resolver));
      }
      const positionals = cmd.registeredArguments.map((arg) =>
        extractContractPositional(arg, resolver)
      );
      result.push({
        path: commandPath,
        pathKey,
        descriptionKey: rawDesc ? resolver.findDescriptionKey(rawDesc) : null,
        options,
        positionals,
        hasSubcommands: subcommands.length > 0,
      });
    }

    for (const sub of subcommands) visit(sub, commandPath);
  };

  for (const cmd of root.commands) visit(cmd, []);
  return result;
}
