/**
 * Runtime validation for the CLI contract.
 *
 * The generated contract is trusted at build time; these schemas exist so a
 * consumer that loads contract.json over the wire (or a test that guards the
 * generator's output) can prove the shape before relying on it.
 */
import { z } from 'zod';
import type { CliContract, ContractCommand } from './types';

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
  'storage',
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
  experimental: z.boolean(),
  plane: CommandPlaneSchema,
  descriptionKey: z.string().nullable(),
  label: z.string(),
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
  detachable: z.boolean(),

  machineOption: z.string().nullable(),
  repoOption: z.string().nullable(),
  machinePositional: z.string().nullable(),
  repoPositional: z.string().nullable(),
});

export const CliContractSchema = z.object({
  version: z.string().min(1),
  languages: z.array(z.string().min(1)).min(1),
  commands: z.array(ContractCommandSchema).min(1),
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
 * command that is interactive or off the machine plane. Every refusal must also
 * carry a reason, so the CLI can always tell the operator why.
 */
function checkProxyCapability(cmd: ContractCommand): string[] {
  const problems: string[] = [];

  if (cmd.proxyCapable) {
    if (cmd.plane !== 'machine') {
      problems.push(`${cmd.pathKey}: proxyCapable but plane is "${cmd.plane}"`);
    }
    if (cmd.interactive) {
      problems.push(`${cmd.pathKey}: proxyCapable but interactive`);
    }
    if (cmd.proxyBlockedReason !== undefined) {
      problems.push(`${cmd.pathKey}: proxyCapable but carries a proxyBlockedReason`);
    }
  } else if (cmd.proxyBlockedReason === undefined) {
    problems.push(`${cmd.pathKey}: not proxyCapable but gives no proxyBlockedReason`);
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

/** detachable is derived from proxyCapable, so it can never be set on a command that is not. */
function checkDetachable(cmd: ContractCommand): string[] {
  if (cmd.detachable && !cmd.proxyCapable) {
    return [`${cmd.pathKey}: detachable but not proxyCapable`];
  }
  return [];
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
      ...checkDetachable(cmd)
    );
    if (seen.has(cmd.pathKey)) problems.push(`${cmd.pathKey}: duplicate entry`);
    seen.add(cmd.pathKey);
  }

  return problems;
}
