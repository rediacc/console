/**
 * Runtime validation for the CLI contract.
 *
 * The generated contract is trusted at build time; these schemas exist so a
 * consumer that loads contract.json over the wire (or a test that guards the
 * generator's output) can prove the shape before relying on it.
 */
import { z } from 'zod';
import type { CliContract, ContractCommand } from './types.js';

export const CommandPlaneSchema = z.enum(['config', 'machine', 'other']);

export const TimeoutClassSchema = z.enum(['read', 'write']);

export const CommandGroupSchema = z.enum([
  'INFRASTRUCTURE',
  'REPOSITORIES',
  'EXECUTION',
  'ORGANIZATION',
  'TOOLS',
]);

export const PositionalKindSchema = z.enum([
  'repo-ref',
  'machine',
  'datastore-ref',
  'cluster',
  'storage',
  'strategy',
  'artifact-ref',
  'job-id',
  'target',
  'file',
  'provider',
  'plain',
]);

export const ResourceKindSchema = z.enum([
  'machine',
  'repo',
  'datastore',
  'cluster',
  'provider',
  'container',
  'template',
  'snapshot',
  'job',
  'strategy',
  'artifact',
]);

export const FormatHintSchema = z.enum([
  'size',
  'cron',
  'duration',
  'integer',
  'port',
  'path',
  'ip',
  'ipv4',
  'ipv6',
  'cidr',
  'domain',
  'url',
  'percent',
  'guid',
  'bandwidth',
]);

export const OptionTierSchema = z.enum(['common', 'advanced']);

export const CommandSeveritySchema = z.enum(['none', 'caution', 'destructive']);

export const PreviewPolaritySchema = z.enum(['opt-in', 'default']);

/** Whether `flag` names a boolean option of the command is checked below. */
export const CommandPreviewSchema = z.object({
  flag: z.string().min(1),
  polarity: PreviewPolaritySchema,
});

export const ErrorOriginSchema = z.enum(['user', 'environment', 'rediacc']);

export const ContractErrorCodeSchema = z.object({
  code: z.string().min(1),
  origin: ErrorOriginSchema,
});

/** The longest summary a command may carry, in characters. */
export const SUMMARY_MAX_LENGTH = 100;

export const CommandExampleSchema = z.object({
  command: z.string().min(1),
  values: z.record(z.string(), z.string()),
  descriptionKey: z.string().min(1),
  label: z.string(),
});

/** Both fields are required; the primaryKey ∈ columns invariant is checked below. */
export const OutputHintsSchema = z.object({
  primaryKey: z.string().min(1),
  columns: z.array(z.string().min(1)).min(1),
});

export const ContractPositionalSchema = z.object({
  name: z.string().min(1),
  kind: PositionalKindSchema,
  required: z.boolean(),
  variadic: z.boolean(),
  descriptionKey: z.string().nullable(),
  label: z.string(),
});

export const ContractOptionSchema = z.object({
  flags: z.string().min(1),
  long: z.string().min(1),
  short: z.string().min(1).optional(),
  valueTaking: z.boolean(),
  variadic: z.boolean(),
  mandatory: z.boolean(),
  defaultValue: z.string().nullable(),
  choices: z.array(z.string().min(1)).min(1).optional(),
  kinds: z.array(ResourceKindSchema).min(1).optional(),
  format: FormatHintSchema.optional(),
  tier: OptionTierSchema,
  sensitive: z.boolean().optional(),
  descriptionKey: z.string().nullable(),
  label: z.string(),
});

export const ContractCommandSchema = z.object({
  path: z.array(z.string().min(1)).min(1),
  pathKey: z.string().min(1),
  domain: z.string().min(1),
  group: CommandGroupSchema.nullable(),
  plane: CommandPlaneSchema,
  descriptionKey: z.string().nullable(),
  label: z.string(),
  summaryKey: z.string().min(1).nullable(),
  summary: z.string().min(1),
  severity: CommandSeveritySchema,
  preview: CommandPreviewSchema.optional(),
  options: z.array(ContractOptionSchema),
  positionals: z.array(ContractPositionalSchema),
  hasSubcommands: z.boolean(),

  examples: z.array(CommandExampleSchema).optional(),
  keywords: z.array(z.string().min(1)).optional(),
  output: OutputHintsSchema.optional(),

  destructive: z.boolean().optional(),
  idempotent: z.boolean().optional(),
  timeout: TimeoutClassSchema.optional(),
  timeoutMs: z.number().int().positive().optional(),
  repoArg: z.string().optional(),
  grandGuard: z.boolean().optional(),
  forkBlocked: z.boolean().optional(),
  agentBlocked: z.boolean().optional(),
  mcpExcludeReason: z.string().optional(),

  interactive: z.boolean(),
  proxyCapable: z.boolean(),
  proxyBlockedReason: z.string().min(1).optional(),
  proxyBlockedReasonKey: z.string().min(1).optional(),
  detachable: z.boolean(),
  detachBlockedReason: z.string().min(1).optional(),

  machineOption: z.string().nullable(),
  repoOption: z.string().nullable(),
  machinePositional: z.string().nullable(),
  repoPositional: z.string().nullable(),
});

export const CliContractSchema = z.object({
  version: z.string().min(1),
  languages: z.array(z.string().min(1)).min(1),
  commands: z.array(ContractCommandSchema).min(1),
  errorCodes: z.array(ContractErrorCodeSchema),
});

/** A flattened i18n bundle: key -> translated string. */
export const ContractStringsSchema = z.record(z.string(), z.string());

/** Parse and validate an unknown value as a CliContract. Throws on failure. */
export function parseCliContract(value: unknown): CliContract {
  return CliContractSchema.parse(value);
}

/** Non-throwing variant. */
export function safeParseCliContract(
  value: unknown
): z.ZodSafeParseResult<z.infer<typeof CliContractSchema>> {
  return CliContractSchema.safeParse(value);
}

/**
 * The non-machine commands the executor serves against the session config
 * (PLAN-rmcp-local-mcp LM10, D57). It mirrors the generator's EXECUTOR_SERVED
 * table on purpose: the contract under validation cannot vouch for itself, and
 * a test pins this set to the real contract's off-machine proxyable commands.
 */
export const EXECUTOR_SERVED_COMMANDS: ReadonlySet<string> = new Set([
  'backup immutability show',
  'backup manifests',
  'backup reconcile',
  'backup retention',
  'backup retention preview',
  'backup strategy list',
  'backup strategy show',
  'backup undelete',
  'backup usage',
  'cluster status',
  'config access list',
  'config prune',
  'config show',
  'credits',
  'feedback list',
  'feedback report',
  'feedback show',
  'legal',
  'machine access show',
  'machine add',
  'machine infra show',
  'machine list',
  'machine provider add',
  'machine provider list',
  'machine provider remove',
  'machine remove',
  'repo replicate status',
  'repo secret get',
  'repo secret list',
]);

/** Identity invariants: a command's path, key and domain must agree. */
function checkIdentity(cmd: ContractCommand): string[] {
  const problems: string[] = [];
  if (cmd.pathKey !== cmd.path.join(' ')) {
    problems.push(`${cmd.pathKey}: pathKey does not match path`);
  }
  if (cmd.domain !== cmd.path[0]) {
    problems.push(`${cmd.pathKey}: domain "${cmd.domain}" is not the first path segment`);
  }
  return problems;
}

/**
 * proxyCapable is derived, and a consumer must never be handed a proxyable
 * command that is interactive or off the machine plane, unless it is named in
 * EXECUTOR_SERVED_COMMANDS, and then it can never be detachable
 * (checkDetachableCommand). Every refusal must also carry a reason, so the CLI
 * can always tell the operator why.
 */
function checkProxyCapability(cmd: ContractCommand): string[] {
  const problems: string[] = cmd.proxyCapable ? proxyCapableProblems(cmd) : [];

  if (!cmd.proxyCapable && cmd.proxyBlockedReason === undefined) {
    problems.push(`${cmd.pathKey}: not proxyCapable but gives no proxyBlockedReason`);
  }
  if (cmd.proxyBlockedReasonKey !== undefined && cmd.proxyBlockedReason === undefined) {
    problems.push(`${cmd.pathKey}: proxyBlockedReasonKey set without a proxyBlockedReason`);
  }

  return problems;
}

/** What a proxyCapable command may not be: off the machine plane unless executor-served, interactive, or carrying a block reason. */
function proxyCapableProblems(cmd: ContractCommand): string[] {
  const problems: string[] = [];
  if (cmd.plane !== 'machine' && !EXECUTOR_SERVED_COMMANDS.has(cmd.pathKey)) {
    problems.push(
      `${cmd.pathKey}: proxyCapable but plane is "${cmd.plane}" and the command is not executor-served`
    );
  }
  if (cmd.interactive) {
    problems.push(`${cmd.pathKey}: proxyCapable but interactive`);
  }
  if (cmd.proxyBlockedReason !== undefined) {
    problems.push(`${cmd.pathKey}: proxyCapable but carries a proxyBlockedReason`);
  }
  return problems;
}

/**
 * The semantic fields a console renders from: a summary short enough for one
 * line, a preview switch that is a real boolean option of the same command, and
 * a severity that never undercuts the MCP destructive annotation.
 */
function checkSemantics(cmd: ContractCommand): string[] {
  const problems: string[] = [];

  // Characters are code points, so an emoji counts once, as the type doc says.
  const summaryLength = [...cmd.summary].length;
  if (summaryLength > SUMMARY_MAX_LENGTH) {
    problems.push(
      `${cmd.pathKey}: summary is ${summaryLength} characters, over ${SUMMARY_MAX_LENGTH}`
    );
  }
  if (cmd.preview) {
    const flag = cmd.preview.flag;
    const opt = cmd.options.find((o) => o.long === flag);
    if (!opt) {
      problems.push(`${cmd.pathKey}: preview.flag "${flag}" names no option of this command`);
    } else if (opt.valueTaking) {
      problems.push(`${cmd.pathKey}: preview.flag "${flag}" takes a value, not a switch`);
    }
  }
  if (cmd.destructive === true && cmd.severity === 'none') {
    problems.push(`${cmd.pathKey}: MCP-annotated destructive but severity is "none"`);
  }

  return problems;
}

/**
 * An enum option must accept a value, and its default must be one of the values
 * it accepts — otherwise the CLI would reject its own default.
 */
function checkOptionChoices(cmd: ContractCommand): string[] {
  const problems: string[] = [];

  for (const opt of cmd.options) {
    if (!opt.choices) continue;
    if (!opt.valueTaking) {
      problems.push(`${cmd.pathKey} --${opt.long}: declares choices but takes no value`);
    }
    if (opt.defaultValue !== null && !opt.choices.includes(opt.defaultValue)) {
      problems.push(
        `${cmd.pathKey} --${opt.long}: default "${opt.defaultValue}" is not one of its choices (${opt.choices.join(', ')})`
      );
    }
  }

  return problems;
}

/**
 * Resource-binding hints must be well-formed: `kinds` may only sit on a
 * value-taking option (a boolean switch names no resource), and — enforced by
 * the schema's `.min(1)` — is never empty. A tier, when present, may not demote
 * a mandatory option to `advanced`: an option the CLI refuses to run without can
 * never be folded out of sight.
 */
function checkOptionHints(cmd: ContractCommand): string[] {
  const problems: string[] = [];

  for (const opt of cmd.options) {
    if (opt.kinds && !opt.valueTaking) {
      problems.push(`${cmd.pathKey} --${opt.long}: declares kinds but takes no value`);
    }
    if (opt.mandatory && opt.tier === 'advanced') {
      problems.push(`${cmd.pathKey} --${opt.long}: mandatory option may not be tier "advanced"`);
    }
  }

  return problems;
}

/**
 * Every example must be a command line for THIS command: it starts with `rdc `
 * followed by the command's own path. (Whether each `values` key names a real
 * option is a stronger check the generator does, where the option set is known
 * from the live tree; the schema alone can only prove the path prefix.)
 */
function checkExamples(cmd: ContractCommand): string[] {
  if (!cmd.examples) return [];
  const problems: string[] = [];
  const prefix = `rdc ${cmd.pathKey}`;

  for (const ex of cmd.examples) {
    if (ex.command !== prefix && !ex.command.startsWith(`${prefix} `)) {
      problems.push(
        `${cmd.pathKey}: example ${JSON.stringify(ex.command)} does not start with "${prefix}"`
      );
    }
  }

  return problems;
}

/** An output hint's primaryKey must be one of the columns it lists. */
function checkOutput(cmd: ContractCommand): string[] {
  if (!cmd.output) return [];
  if (!cmd.output.columns.includes(cmd.output.primaryKey)) {
    return [
      `${cmd.pathKey}: output.primaryKey "${cmd.output.primaryKey}" is not one of its columns (${cmd.output.columns.join(', ')})`,
    ];
  }
  return [];
}

/**
 * Positional bindings must be self-consistent, and this is where the §2.0
 * fail-open trap is caught. A `repo-ref` positional MUST surface as
 * `repoPositional`, and a `machine` positional as `machinePositional`; without
 * that, the console's picker and the executor's policy scope both bind to a null
 * and silently degrade: a text box where a picker belongs, an unscoped policy
 * rule where a machine-scoped one was meant. Every named binding must point at a
 * real positional of the right kind.
 */
function checkPositionalBindings(cmd: ContractCommand): string[] {
  const problems: string[] = [];
  const byName = new Map(cmd.positionals.map((p) => [p.name, p]));

  const repoRef = cmd.positionals.find((p) => p.kind === 'repo-ref');
  if (repoRef && cmd.repoPositional !== repoRef.name) {
    problems.push(
      `${cmd.pathKey}: has a repo-ref positional "${repoRef.name}" but repoPositional is ${JSON.stringify(cmd.repoPositional)}`
    );
  }
  const machineRef = cmd.positionals.find((p) => p.kind === 'machine');
  if (machineRef && cmd.machinePositional !== machineRef.name) {
    problems.push(
      `${cmd.pathKey}: has a machine positional "${machineRef.name}" but machinePositional is ${JSON.stringify(cmd.machinePositional)}`
    );
  }
  if (cmd.repoPositional !== null && byName.get(cmd.repoPositional)?.kind !== 'repo-ref') {
    problems.push(
      `${cmd.pathKey}: repoPositional "${cmd.repoPositional}" is not a repo-ref positional`
    );
  }
  if (cmd.machinePositional !== null && byName.get(cmd.machinePositional)?.kind !== 'machine') {
    problems.push(
      `${cmd.pathKey}: machinePositional "${cmd.machinePositional}" is not a machine positional`
    );
  }

  return problems;
}

/** What a detachable command must not be: off the proxy, off the machine plane (it runs no machine job there), or a job verb. */
function checkDetachableCommand(cmd: ContractCommand): string[] {
  const problems: string[] = [];
  if (!cmd.proxyCapable) problems.push(`${cmd.pathKey}: detachable but not proxyCapable`);
  if (cmd.plane !== 'machine') {
    problems.push(
      `${cmd.pathKey}: detachable but plane is "${cmd.plane}", so it runs no machine job`
    );
  }
  if (cmd.domain === 'job') problems.push(`${cmd.pathKey}: a job verb cannot be detachable`);
  return problems;
}

/**
 * detachable is derived from proxyCapable, so it can never be set on a command
 * that is not, nor on a `job` verb. A proxyable non-job command that is not
 * detachable is a section 24 exception and must say why (detachBlockedReason);
 * any other command must not carry that reason.
 */
function checkDetachable(cmd: ContractCommand): string[] {
  const problems: string[] = [];
  if (cmd.detachable) problems.push(...checkDetachableCommand(cmd));
  const exception = cmd.proxyCapable && cmd.domain !== 'job' && !cmd.detachable;
  if (exception && !cmd.detachBlockedReason) {
    problems.push(`${cmd.pathKey}: proxyable but not detachable, with no detachBlockedReason`);
  }
  if (!exception && cmd.detachBlockedReason) {
    problems.push(`${cmd.pathKey}: detachBlockedReason set on a command that is not an exception`);
  }
  return problems;
}

/**
 * Invariants the schema alone cannot express. Returns a list of human-readable
 * violations; empty means the contract is self-consistent.
 */
export function checkContractInvariants(contract: CliContract): string[] {
  const problems: string[] = [];
  const seen = new Set<string>();

  for (const cmd of contract.commands) {
    problems.push(
      ...checkIdentity(cmd),
      ...checkProxyCapability(cmd),
      ...checkOptionChoices(cmd),
      ...checkOptionHints(cmd),
      ...checkExamples(cmd),
      ...checkOutput(cmd),
      ...checkPositionalBindings(cmd),
      ...checkDetachable(cmd),
      ...checkSemantics(cmd)
    );
    if (seen.has(cmd.pathKey)) problems.push(`${cmd.pathKey}: duplicate entry`);
    seen.add(cmd.pathKey);
  }

  const seenCodes = new Set<string>();
  for (const row of contract.errorCodes) {
    if (seenCodes.has(row.code)) problems.push(`error code ${row.code}: duplicate entry`);
    seenCodes.add(row.code);
  }

  return problems;
}
