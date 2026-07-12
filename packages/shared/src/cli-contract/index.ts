/**
 * The `rdc` CLI contract.
 *
 * Generated from the live Commander tree — regenerate with
 * `npm run generate:cli-contract -w @rediacc/cli`. The check:ci-cli-contract
 * gate fails when the checked-in data drifts from the CLI.
 */
export { CLI_CONTRACT, CLI_CONTRACT_VERSION } from './data/contract.generated';
export {
  CONTRACT_LANGUAGES,
  type ContractLanguage,
  isContractLanguage,
  loadContractStrings,
  translate,
} from './i18n';
export type {
  CliContract,
  CommandGroup,
  CommandPlane,
  ContractCommand,
  ContractOption,
  ContractStrings,
  TimeoutClass,
} from './types';
export {
  CliContractSchema,
  CommandGroupSchema,
  CommandPlaneSchema,
  ContractCommandSchema,
  ContractOptionSchema,
  ContractStringsSchema,
  checkContractInvariants,
  parseCliContract,
  safeParseCliContract,
  TimeoutClassSchema,
} from './validation';

import { CLI_CONTRACT } from './data/contract.generated';
import type { ContractCommand } from './types';

const BY_PATH_KEY: ReadonlyMap<string, ContractCommand> = new Map(
  CLI_CONTRACT.commands.map((c) => [c.pathKey, c])
);

/** Look up a command by its space-joined path, e.g. "repo secret list". */
export function getCommand(pathKey: string): ContractCommand | undefined {
  return BY_PATH_KEY.get(pathKey);
}

/** All commands, grouped by top-level domain ("repo", "machine", ...). */
export function commandsByDomain(): Map<string, ContractCommand[]> {
  const grouped = new Map<string, ContractCommand[]>();
  for (const cmd of CLI_CONTRACT.commands) {
    const bucket = grouped.get(cmd.domain);
    if (bucket) bucket.push(cmd);
    else grouped.set(cmd.domain, [cmd]);
  }
  return grouped;
}

/**
 * Commands that can act on the given resources — the set a UI should offer
 * once the operator has selected a machine, a repository, or both.
 *
 * The binding is read from `machineOption` / `repoOption`, which the generator
 * resolves per command (see ContractCommand). Passing no context returns every
 * command.
 */
export function commandsForContext(context: {
  machine?: boolean;
  repo?: boolean;
}): ContractCommand[] {
  return CLI_CONTRACT.commands.filter((cmd) => {
    if (context.machine === true && cmd.machineOption === null) return false;
    if (context.repo === true && cmd.repoOption === null) return false;
    return true;
  });
}

/** Commands a remote executor may run on the operator's behalf. */
export function proxyCapableCommands(): ContractCommand[] {
  return CLI_CONTRACT.commands.filter((cmd) => cmd.proxyCapable);
}
