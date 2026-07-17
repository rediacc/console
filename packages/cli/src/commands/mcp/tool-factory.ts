/**
 * MCP Tool Factory — derives MCP tool definitions from the generated CLI contract.
 *
 * Iterates CLI_CONTRACT.commands (the single generated description of the `rdc`
 * surface) and builds a ToolDef for every command that carries `mcp` metadata in
 * COMMAND_METADATA. The zod schema, argv builder, and annotations are derived
 * from the contract's option/positional shape — including the `.choices()` enums
 * the big-bang enriched it with — rather than from a second, independent walk of
 * the Commander tree.
 *
 * Split of sources: the STRUCTURE (which options/positionals a command has, their
 * value/variadic/choice shape, and their English descriptions) comes from the
 * contract. The MCP-specific SHAPING the contract does not carry — which options
 * to drop (`excludeOptions`), which optional positionals to force-require
 * (`requiredArgs`), what to append (`appendArgs`), the LLM-tuned description
 * (`descriptionOverride`) — and the MCP policy (destructive/idempotent/timeout/
 * repoArg) still come from COMMAND_METADATA.mcp, which is where they are authored.
 * The contract merely mirrors that policy for its other consumers.
 */

import type { ZodRawShapeCompat } from '@modelcontextprotocol/sdk/server/zod-compat.js';
import {
  CLI_CONTRACT,
  type ContractCommand,
  type ContractOption,
  type ContractPositional,
} from '@rediacc/shared/cli-contract';
import { z } from 'zod';
import {
  COMMAND_METADATA,
  type CommandMeta,
  READ_TIMEOUT,
  WRITE_TIMEOUT,
} from '../../config/command-metadata.js';

// The MCP SDK pulls zod from the hoisted root copy (zod@3.25.76, both v3 and
// v4 subpaths are bundled there) while this workspace imports zod from its own
// packages/cli/node_modules/zod@4.4.3. Even though both v4/core trees export a
// structurally-identical $ZodType interface, TS treats them as distinct nominal
// types because they live at different file paths. Using the SDK's own
// ZodRawShapeCompat alias keeps the registerTool() call site type-clean.

export interface ToolDef {
  name: string;
  description: string;
  schema: ZodRawShapeCompat;
  command: (args: Record<string, unknown>) => string[];
  isDestructive: boolean;
  isIdempotent: boolean;
  timeoutMs?: number;
  /** Field name in args that contains the repository name. Used for grand repo guard in MCP. */
  repoArgField?: string;
}

/**
 * Global options (long names without --) that are never exposed in MCP tools.
 *
 * The contract already drops the root-program globals (--output/--lang/--help/…);
 * this set is the MCP-specific extra — per-command flags like --yes/--quiet/
 * --fields/--config an agent must never drive — so it is still applied on top of
 * the contract's option list.
 */
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

/**
 * Convert a contract option's long name to a Zod schema key.
 * dry-run → dry_run, machine → machine, to-machine → to_machine
 */
function flagToSchemaKey(long: string): string {
  return long.replaceAll('-', '_');
}

/**
 * Does a value-taking option take a REQUIRED value (`<v>`) rather than an
 * optional one (`[v]`)? The contract collapses both into `valueTaking`, so the
 * distinction — which decides whether the derived field is required — is read
 * back off the raw Commander flags string the contract carries verbatim. This is
 * exactly Commander's own `Option.required`.
 */
function takesRequiredValue(opt: ContractOption): boolean {
  return opt.flags.includes('<');
}

/** The MCP-visible options for a command: contract options minus globals and per-tool excludes. */
function selectOptions(cmd: ContractCommand, excludeSet: Set<string>): ContractOption[] {
  return cmd.options.filter((o) => !GLOBAL_EXCLUDED_OPTIONS.has(o.long) && !excludeSet.has(o.long));
}

/** Derive a Zod type for a single positional argument. */
function deriveArgType(pos: ContractPositional, isRequired: boolean): z.ZodType {
  const base = z.string().describe(pos.label || pos.name);
  return isRequired ? base : base.optional();
}

/** Derive a Zod type for a single contract option. */
function deriveOptionType(opt: ContractOption): z.ZodType {
  if (!opt.valueTaking) return z.boolean().optional().describe(opt.label);
  const base =
    opt.choices && opt.choices.length > 0
      ? z.enum(opt.choices as [string, ...string[]]).describe(opt.label)
      : z.string().describe(opt.label);
  return takesRequiredValue(opt) ? base : base.optional();
}

/**
 * Derive a Zod schema from a command's positionals and options.
 */
function deriveSchema(
  positionals: ContractPositional[],
  options: ContractOption[],
  requiredArgs?: string[]
): ZodRawShapeCompat {
  const schema: ZodRawShapeCompat = {};
  const requiredSet = new Set(requiredArgs ?? []);
  const argNames = new Set<string>();

  for (const pos of positionals) {
    argNames.add(pos.name);
    schema[pos.name] = deriveArgType(pos, pos.required || requiredSet.has(pos.name));
  }

  for (const opt of options) {
    const key = flagToSchemaKey(opt.long);
    if (!argNames.has(key)) schema[key] = deriveOptionType(opt);
  }

  // Mutually-exclusive target pair (design D14): -m XOR --cluster. When a repo
  // verb exposes both, make BOTH optional MCP fields — a value-taking option
  // otherwise derives to a REQUIRED field, so exposing both would demand both.
  // The auto-deriver can't express "exactly one", so the runtime
  // (resolveRepoTarget) enforces it and returns a clear error for neither/both.
  if ('machine' in schema && 'cluster' in schema) {
    schema.machine = (schema.machine as z.ZodType).optional();
    schema.cluster = (schema.cluster as z.ZodType).optional();
  }

  return schema;
}

/** Push positional arguments onto argv and return the set of arg names consumed. */
function pushPositionalArgs(
  argv: string[],
  positionals: ContractPositional[],
  toolArgs: Record<string, unknown>
): Set<string> {
  const argNames = new Set<string>();
  for (const pos of positionals) {
    argNames.add(pos.name);
    const value = toolArgs[pos.name];
    if (value !== undefined) argv.push(String(value));
  }
  return argNames;
}

/** Push option flags onto argv, skipping positional-shadowed and unset options. */
function pushOptionArgs(
  argv: string[],
  options: ContractOption[],
  argNames: Set<string>,
  toolArgs: Record<string, unknown>
): void {
  for (const opt of options) {
    const key = flagToSchemaKey(opt.long);
    if (argNames.has(key)) continue;
    const value = toolArgs[key];
    if (value === undefined || value === false) continue;
    const flag = `--${opt.long}`;
    if (value === true) {
      argv.push(flag);
    } else {
      argv.push(flag, String(value));
    }
  }
}

/**
 * Build a command factory function that converts MCP args to CLI argv.
 *
 * Positionals are emitted first in declared order, then the flags — the same
 * serialisation rule the contract documents, so the argv a laptop would have
 * typed is reproduced exactly.
 */
function buildCommandFactory(
  pathParts: string[],
  positionals: ContractPositional[],
  options: ContractOption[],
  appendArgs?: string[]
): (toolArgs: Record<string, unknown>) => string[] {
  return (toolArgs: Record<string, unknown>) => {
    const argv = [...pathParts];
    const argNames = pushPositionalArgs(argv, positionals, toolArgs);
    pushOptionArgs(argv, options, argNames, toolArgs);
    if (appendArgs) argv.push(...appendArgs);
    return argv;
  };
}

/**
 * Derive MCP tool definitions from the CLI contract + COMMAND_METADATA.
 *
 * For each contract command whose path has a `mcp` entry in COMMAND_METADATA,
 * generates a ToolDef with a contract-derived Zod schema and command builder.
 *
 * Experimental commands are skipped: they are `_hidden` in the live tree (unless
 * REDIACC_EXPERIMENTAL=1), so they never became MCP tools, and one of them
 * (`machine health`) also ships a hand-written custom tool of the same name —
 * auto-deriving it here would collide with that. The contract carries the
 * `experimental` flag, so the skip is honoured without consulting the env.
 */
export function buildToolsFromContract(): ToolDef[] {
  const tools: ToolDef[] = [];

  for (const cmd of CLI_CONTRACT.commands) {
    if (cmd.experimental) continue;

    const meta = COMMAND_METADATA[cmd.pathKey] as CommandMeta | undefined;
    if (!meta?.mcp) continue;

    const mcp = meta.mcp;
    const excludeSet = new Set(mcp.excludeOptions ?? []);
    const options = selectOptions(cmd, excludeSet);

    const schema = deriveSchema(cmd.positionals, options, mcp.requiredArgs);
    const commandFn = buildCommandFactory(cmd.path, cmd.positionals, options, mcp.appendArgs);

    tools.push({
      name: cmd.pathKey.replaceAll(' ', '_'),
      description: mcp.descriptionOverride ?? cmd.label,
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
