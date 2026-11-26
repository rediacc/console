/**
 * The contract's option and target-binding helpers, moved out of generate-cli-contract.ts so that script stays under the line budget: a Commander option as a ContractOption, and which flag or positional names a command's machine and repository.
 */
import type { Option } from 'commander';
import type { ContractOption, ContractPositional } from '../../../shared/src/cli-contract/types.js';
import type { createDescriptionResolver } from './command-tree-lib.js';
import {
  resolveOptionFormat,
  resolveOptionKinds,
  resolveOptionSensitive,
  resolveOptionTier,
} from './option-classification.js';

export function stripDashes(flag: string): string {
  return flag.replace(/^-+/, '');
}

export function toContractOption(
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
export function resolveMachineOption(domain: string, options: ContractOption[]): string | null {
  if (options.some((o) => o.long === 'machine')) return 'machine';
  if (domain === 'machine' && options.some((o) => o.long === 'name')) return 'name';
  return null;
}

/**
 * Which option names the target repository: the MCP `repoArg` annotation when
 * present (it exists to answer exactly this), otherwise `--repo`, otherwise
 * `--name` on the `repo` domain.
 */
export function resolveRepoOption(
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
export function resolveMachinePositional(positionals: ContractPositional[]): string | null {
  return positionals.find((p) => p.kind === 'machine')?.name ?? null;
}

export function resolveRepoPositional(positionals: ContractPositional[]): string | null {
  return positionals.find((p) => p.kind === 'repo-ref')?.name ?? null;
}
