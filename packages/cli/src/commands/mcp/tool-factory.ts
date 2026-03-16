/**
 * MCP Tool Factory — auto-derives MCP tool definitions from the Commander tree.
 *
 * Walks the Commander command tree and generates ToolDef entries for every command
 * path that has MCP metadata in COMMAND_METADATA. Zod schemas, command builders,
 * and annotations are all derived automatically.
 */
import type { Command } from 'commander';
import { z } from 'zod';
import {
  COMMAND_METADATA,
  type CommandMeta,
  READ_TIMEOUT,
  WRITE_TIMEOUT,
} from '../../config/command-metadata.js';

export interface ToolDef {
  name: string;
  description: string;
  schema: Record<string, z.ZodType>;
  command: (args: Record<string, unknown>) => string[];
  isDestructive: boolean;
  isIdempotent: boolean;
  timeoutMs?: number;
  /** Field name in args that contains the repository name. Used for grand repo guard in MCP. */
  repoArgField?: string;
}

/** Global options (long names without --) that are never exposed in MCP tools. */
const GLOBAL_EXCLUDED_OPTIONS = new Set([
  'output',
  'config',
  'lang',
  'quiet',
  'fields',
  'yes',
  'help',
  'version',
]);

interface ArgDef {
  name: string;
  required: boolean;
  description: string;
}

interface OptionDef {
  long: string;
  short?: string;
  flags: string;
  description: string;
  required: boolean;
  isBoolean: boolean;
}

/**
 * Convert a Commander option long name to a Zod schema key.
 * --dry-run → dry_run, --machine → machine, --to-machine → to_machine
 */
export function flagToSchemaKey(long: string): string {
  return long.replace(/^--/, '').replaceAll('-', '_');
}

/**
 * Check if a Commander option takes a value (vs being a boolean flag).
 * Options with <value> or [value] in their flags string take values.
 */
function isValueTaking(flags: string): boolean {
  return flags.includes('<') || flags.includes('[');
}

/**
 * Extract positional argument definitions from a Commander command.
 */
function extractArgs(cmd: Command): ArgDef[] {
  const args = (
    cmd as unknown as { _args: { _name: string; required: boolean; description: string }[] }
  )._args;
  return args.map((a) => ({
    name: a._name,
    required: a.required,
    description: a.description || a._name,
  }));
}

/**
 * Extract option definitions from a Commander command, filtering globals.
 */
function extractOptions(cmd: Command, excludeSet: Set<string>): OptionDef[] {
  return cmd.options
    .filter((o) => {
      if (!o.long) return false;
      const longName = o.long.replace(/^--/, '');
      return !GLOBAL_EXCLUDED_OPTIONS.has(longName) && !excludeSet.has(longName);
    })
    .map((o) => ({
      long: o.long!,
      short: o.short,
      flags: o.flags,
      description: o.description,
      required: o.required,
      isBoolean: !isValueTaking(o.flags),
    }));
}

/** Derive a Zod type for a single positional argument. */
function deriveArgType(arg: ArgDef, isRequired: boolean): z.ZodType {
  const base = z.string().describe(arg.description);
  return isRequired ? base : base.optional();
}

/** Derive a Zod type for a single Commander option. */
function deriveOptionType(opt: OptionDef): z.ZodType {
  if (opt.isBoolean) return z.boolean().optional().describe(opt.description);
  const base = z.string().describe(opt.description);
  return opt.required ? base : base.optional();
}

/**
 * Derive a Zod schema from Commander args and options.
 */
function deriveSchema(
  args: ArgDef[],
  options: OptionDef[],
  requiredArgs?: string[]
): Record<string, z.ZodType> {
  const schema: Record<string, z.ZodType> = {};
  const requiredSet = new Set(requiredArgs ?? []);
  const argNames = new Set<string>();

  for (const arg of args) {
    argNames.add(arg.name);
    schema[arg.name] = deriveArgType(arg, arg.required || requiredSet.has(arg.name));
  }

  for (const opt of options) {
    const key = flagToSchemaKey(opt.long);
    if (!argNames.has(key)) schema[key] = deriveOptionType(opt);
  }

  return schema;
}

/** Push positional arguments onto argv and return the set of arg names consumed. */
function pushPositionalArgs(
  argv: string[],
  args: ArgDef[],
  toolArgs: Record<string, unknown>
): Set<string> {
  const argNames = new Set<string>();
  for (const arg of args) {
    argNames.add(arg.name);
    const value = toolArgs[arg.name];
    if (value !== undefined) argv.push(String(value));
  }
  return argNames;
}

/** Push option flags onto argv, skipping positional-shadowed and unset options. */
function pushOptionArgs(
  argv: string[],
  options: OptionDef[],
  argNames: Set<string>,
  toolArgs: Record<string, unknown>
): void {
  for (const opt of options) {
    const key = flagToSchemaKey(opt.long);
    if (argNames.has(key)) continue;
    const value = toolArgs[key];
    if (value === undefined || value === false) continue;
    if (value === true) {
      argv.push(opt.long);
    } else {
      argv.push(opt.long, String(value));
    }
  }
}

/**
 * Build a command factory function that converts MCP args to CLI argv.
 */
function buildCommandFactory(
  pathParts: string[],
  args: ArgDef[],
  options: OptionDef[],
  appendArgs?: string[]
): (toolArgs: Record<string, unknown>) => string[] {
  return (toolArgs: Record<string, unknown>) => {
    const argv = [...pathParts];
    const argNames = pushPositionalArgs(argv, args, toolArgs);
    pushOptionArgs(argv, options, argNames, toolArgs);
    if (appendArgs) argv.push(...appendArgs);
    return argv;
  };
}

/**
 * Recursively walk the Commander tree and collect leaf commands with their full paths.
 */
function walkCommandTree(cmd: Command, prefix: string): { path: string; command: Command }[] {
  const results: { path: string; command: Command }[] = [];

  for (const sub of cmd.commands) {
    if (sub.name() === 'help') continue;
    // Skip experimental/hidden commands (defense in depth — COMMAND_METADATA allowlist also filters)
    if ((sub as Command & { _hidden?: boolean })._hidden) continue;

    const name = prefix ? `${prefix} ${sub.name()}` : sub.name();

    if (sub.commands.length > 0) {
      results.push(...walkCommandTree(sub, name));
    } else {
      results.push({ path: name, command: sub });
    }
  }

  return results;
}

/**
 * Auto-derive MCP tool definitions from the Commander tree + COMMAND_METADATA.
 *
 * For each leaf command whose path has a `mcp` entry in COMMAND_METADATA,
 * generates a ToolDef with auto-derived Zod schema and command builder.
 */
export function buildToolsFromCommander(program: Command): ToolDef[] {
  const tools: ToolDef[] = [];
  const leafCommands = walkCommandTree(program, '');

  for (const { path, command: cmd } of leafCommands) {
    const meta = COMMAND_METADATA[path] as CommandMeta | undefined;
    if (!meta?.mcp) continue;

    const mcp = meta.mcp;
    const excludeSet = new Set(mcp.excludeOptions ?? []);

    const args = extractArgs(cmd);
    const options = extractOptions(cmd, excludeSet);
    const pathParts = path.split(' ');

    const schema = deriveSchema(args, options, mcp.requiredArgs);
    const commandFn = buildCommandFactory(pathParts, args, options, mcp.appendArgs);

    const toolName = path.replaceAll(' ', '_');
    const description = mcp.descriptionOverride ?? cmd.description();

    tools.push({
      name: toolName,
      description,
      schema,
      command: commandFn,
      isDestructive: mcp.destructive,
      isIdempotent: mcp.idempotent,
      timeoutMs: mcp.timeout === 'read' ? READ_TIMEOUT : WRITE_TIMEOUT,
      repoArgField: mcp.repoArg,
    });
  }

  return tools;
}
