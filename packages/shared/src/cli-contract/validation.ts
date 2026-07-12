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

export const ContractOptionSchema = z.object({
  flags: z.string().min(1),
  long: z.string().min(1),
  short: z.string().min(1).optional(),
  valueTaking: z.boolean(),
  variadic: z.boolean(),
  mandatory: z.boolean(),
  defaultValue: z.string().nullable(),
  choices: z.array(z.string().min(1)).min(1).optional(),
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
  hasSubcommands: z.boolean(),

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

  machineOption: z.string().nullable(),
  repoOption: z.string().nullable(),
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
 * Invariants the schema alone cannot express. Returns a list of human-readable
 * violations; empty means the contract is self-consistent.
 */
export function checkContractInvariants(contract: CliContract): string[] {
  const problems: string[] = [];
  const seen = new Set<string>();

  for (const cmd of contract.commands) {
    problems.push(...checkIdentity(cmd), ...checkProxyCapability(cmd), ...checkOptionChoices(cmd));
    if (seen.has(cmd.pathKey)) problems.push(`${cmd.pathKey}: duplicate entry`);
    seen.add(cmd.pathKey);
  }

  return problems;
}
