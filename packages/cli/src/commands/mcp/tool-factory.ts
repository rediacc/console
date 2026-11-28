/**
 * MCP Tool Factory, derives MCP tool definitions from the generated CLI contract.
 *
 * Iterates CLI_CONTRACT.commands (the single generated description of the `rdc`
 * surface) and builds a ToolDef for every command that carries `mcp` metadata in
 * COMMAND_METADATA. The zod schema, argv builder, and annotations are derived
 * from the contract's option/positional shape, including the `.choices()` enums
 * the big-bang enriched it with, rather than from a second, independent walk of
 * the Commander tree.
 *
 * Split of sources: the STRUCTURE (which options/positionals a command has, their
 * value/variadic/choice shape, and their English descriptions) comes from the
 * contract. The MCP-specific SHAPING the contract does not carry, which options
 * to drop (`excludeOptions`), which optional positionals or options to force-require
 * (`requiredArgs`), what to append (`appendArgs`), the LLM-tuned description
 * (`descriptionOverride`), and the MCP policy (destructive/idempotent/timeout/
 * repoArg) still come from COMMAND_METADATA.mcp, which is where they are authored.
 * The contract merely mirrors that policy for its other consumers.
 */

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
  type McpSurface,
  READ_TIMEOUT,
  WRITE_TIMEOUT,
} from '../../config/command-metadata.js';
import { JOB_ATTACH_WINDOW_MS } from '../../services/jobs/attach.js';

export interface ToolDef {
  name: string;
  /** The contract `pathKey` of the command the tool runs, e.g. "repo up" (the custom machine_* views run "machine status"). */
  commandPath: string;
  description: string;
  /** The tool's input fields; `registerTool` receives them wrapped in `z.object()`. */
  schema: Record<string, z.ZodType>;
  command: (args: Record<string, unknown>) => string[];
  isDestructive: boolean;
  isIdempotent: boolean;
  timeoutMs?: number;
  /** The timeout class the tool's timeoutMs was resolved from. */
  timeoutClass: 'read' | 'write';
  /** Where the tool is served (COMMAND_METADATA mcpSurface); the registry generator checks it against the contract. */
  surface: McpSurface;
  /** Field name in args that holds the repository ref. Metadata only: the MCP layer judges no repo; the child `rdc` does. */
  repoArgField?: string;
  /**
   * The attach window of the child `rdc` (PLAN-detached-jobs J8b): a machine job that finishes inside it returns
   * its result, a longer one returns the ticket with `next: "job_status"`. Absent for a tool that starts no job.
   */
  attachWindowMs?: number;
  /** Repeat the command until `done` holds or the ceiling nears (job_wait); each run is a full child `rdc` call. */
  poll?: ToolPoll;
  /** The tool takes a `page` argument that fetches the next page of a result above the page size. */
  pageable?: true;
}

/** How a polling tool repeats its command. */
export interface ToolPoll {
  /** The wall-clock ceiling of one tool call. */
  ceilingMs: number;
  /** The pause between two runs; also the `nextPollSeconds` hint of a call that hits the ceiling. */
  intervalMs: number;
  /** Whether a successful run's data is final. */
  done: (data: unknown) => boolean;
}

/**
 * The MCP annotations a tool is registered with; the stdio server and the generated registry read this one function.
 *
 * `readOnlyHint` comes from the timeout class (the contract carries no separate read flag): a `read` tool is
 * read-only unless it is also destructive, so a non-destructive write (`repo up`, `backup run`) is never
 * advertised read-only. Clients run read-only tools in parallel and skip their confirmation.
 */
export function toolAnnotations(tool: ToolDef): {
  destructiveHint: boolean;
  readOnlyHint: boolean;
  idempotentHint: boolean;
  openWorldHint: boolean;
} {
  return {
    destructiveHint: tool.isDestructive,
    readOnlyHint: tool.timeoutClass === 'read' && !tool.isDestructive,
    idempotentHint: tool.isIdempotent,
    openWorldHint: true,
  };
}

/** What a windowed tool's description tells the model about the job it may start. */
const ATTACH_WINDOW_NOTE = `Returns the result, or a job id when the run outlasts about ${JOB_ATTACH_WINDOW_MS / 1000} s (follow it with job_status or job_logs).`;

/** The optional `background` field of a windowed tool: start the job and return its ticket at once (the child runs `rdc --background`, which a `--proxy` executor honours). */
const BACKGROUND_FIELD = z
  .boolean()
  .optional()
  .describe('Start the job and return its job id at once instead of waiting for it.');

/** Does a command run as a machine job the MCP child attaches to for the window? One predicate, shared with the executor. */
export function hasAttachWindow(cmd: Pick<ContractCommand, 'plane' | 'detachable'>): boolean {
  return cmd.plane === 'machine' && cmd.detachable;
}

/**
 * Global options (long names without --) that are never exposed in MCP tools.
 *
 * The contract already drops the root-program globals (--output/--lang/--help/…);
 * this set is the MCP-specific extra, per-command flags like --yes/--quiet/
 * --fields/--config an agent must never drive, so it is still applied on top of
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
 * distinction, which decides whether a mandatory option's field is required, is read
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
export function deriveOptionType(opt: ContractOption, forceRequired = false): z.ZodType {
  if (!opt.valueTaking) {
    const flag = z.boolean().describe(opt.label);
    return forceRequired ? flag : flag.optional();
  }
  const base =
    opt.choices && opt.choices.length > 0
      ? z.enum(opt.choices as [string, ...string[]]).describe(opt.label)
      : z.string().describe(opt.label);
  // An option is a required field when the tool's requiredArgs names it (whatever the flag shape: `<v>`, `[v]` or boolean), or when the CLI itself requires it (mandatory with a `<v>` value). `<v>` alone says the flag needs a value WHEN given, not that the flag must be given.
  const required = forceRequired || (opt.mandatory && takesRequiredValue(opt));
  return required ? base : base.optional();
}

/**
 * Derive a Zod schema from a command's positionals and options.
 */
function deriveSchema(
  positionals: ContractPositional[],
  options: ContractOption[],
  requiredArgs?: string[]
): Record<string, z.ZodType> {
  const schema: Record<string, z.ZodType> = {};
  const requiredSet = new Set(requiredArgs ?? []);
  const argNames = new Set<string>();

  for (const pos of positionals) {
    argNames.add(pos.name);
    schema[pos.name] = deriveArgType(pos, pos.required || requiredSet.has(pos.name));
  }

  for (const opt of options) {
    const key = flagToSchemaKey(opt.long);
    if (!argNames.has(key)) schema[key] = deriveOptionType(opt, requiredSet.has(opt.long));
  }

  // Mutually-exclusive target pair (design D14): -m XOR --cluster. When a repo verb exposes both, make BOTH optional MCP fields, so a requiredArgs entry or a mandatory flag can never make the pair demand both. The auto-deriver can't express "exactly one", so the runtime (resolveRepoTarget) enforces it and returns a clear error for neither/both.
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
 * Positionals are emitted first in declared order, then the flags, the same
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
 * `machine health` is auto-derived here like any other command. It used to be
 * skipped as experimental and shadowed by a hand-written `machine_health` tool
 * that actually ran `machine status --system`, so the tool named "health" never
 * invoked the health checker at all. That custom tool is gone; this one runs the
 * real command and returns its aggregated issues.
 */
export function buildToolsFromContract(): ToolDef[] {
  const tools: ToolDef[] = [];

  for (const cmd of CLI_CONTRACT.commands) {
    const meta = COMMAND_METADATA[cmd.pathKey] as CommandMeta | undefined;
    if (!meta?.mcp) continue;

    const mcp = meta.mcp;
    const excludeSet = new Set(mcp.excludeOptions ?? []);
    const options = selectOptions(cmd, excludeSet);

    const schema = deriveSchema(cmd.positionals, options, mcp.requiredArgs);
    const commandFn = buildCommandFactory(cmd.path, cmd.positionals, options, mcp.appendArgs);

    const windowed = hasAttachWindow(cmd);
    const baseDescription = mcp.descriptionOverride ?? cmd.label;
    if (!meta.mcpSurface) {
      throw new Error(`COMMAND_METADATA["${cmd.pathKey}"] carries mcp but no mcpSurface`);
    }
    tools.push({
      name: cmd.pathKey.replaceAll(' ', '_'),
      commandPath: cmd.pathKey,
      description: windowed
        ? `${baseDescription.replace(/\.$/, '')}. ${ATTACH_WINDOW_NOTE}`
        : baseDescription,
      ...(windowed ? { attachWindowMs: JOB_ATTACH_WINDOW_MS } : {}),
      schema: windowed ? { ...schema, background: BACKGROUND_FIELD } : schema,
      command: commandFn,
      isDestructive: mcp.destructive,
      isIdempotent: mcp.idempotent,
      timeoutMs: mcp.timeout === 'read' ? READ_TIMEOUT : WRITE_TIMEOUT,
      timeoutClass: mcp.timeout,
      surface: meta.mcpSurface,
      repoArgField: mcp.repoArg,
    });
  }

  return tools;
}
