/**
 * Data-free lookups over a CLI contract.
 *
 * Every helper takes the contract as an argument, so this module never imports
 * the generated literal. A web bundle imports `@rediacc/shared/cli-contract/core`
 * beside `/load`, and the contract data stays in its own lazily loaded chunk. The
 * root entry builds the same index over the bundled contract for the CLI and the
 * worker, which import synchronously. A test refuses any import of
 * `data/contract.generated` from this file.
 */
import type { CliContract, ContractCommand } from './types.js';

/** The lookups a consumer runs over one contract. */
export interface ContractIndex {
  /** Look up a command by its space-joined path, e.g. "repo secret list". */
  getCommand(pathKey: string): ContractCommand | undefined;
  /** All commands, grouped by top-level domain ("repo", "machine", ...). */
  commandsByDomain(): Map<string, ContractCommand[]>;
  /**
   * Commands that can act on the given resources: the set a UI should offer
   * once the operator has selected a machine, a repository, or both.
   *
   * The binding is read from the FLAG bindings (`machineOption` / `repoOption`)
   * OR the POSITIONAL bindings (`machinePositional` / `repoPositional`), so a
   * command that names its machine or repo positionally still lights up on the
   * matching resource page. Passing no context returns every command.
   */
  commandsForContext(context: { machine?: boolean; repo?: boolean }): ContractCommand[];
  /** Commands a remote executor may run on the operator's behalf. */
  proxyCapableCommands(): ContractCommand[];
}

/** Build the lookups over one contract; the path-key map is built once. */
export function indexContract(contract: CliContract): ContractIndex {
  const byPathKey: ReadonlyMap<string, ContractCommand> = new Map(
    contract.commands.map((c) => [c.pathKey, c])
  );

  return {
    getCommand: (pathKey) => byPathKey.get(pathKey),

    commandsByDomain: () => {
      const grouped = new Map<string, ContractCommand[]>();
      for (const cmd of contract.commands) {
        const bucket = grouped.get(cmd.domain);
        if (bucket) bucket.push(cmd);
        else grouped.set(cmd.domain, [cmd]);
      }
      return grouped;
    },

    commandsForContext: (context) =>
      contract.commands.filter((cmd) => {
        if (
          context.machine === true &&
          cmd.machineOption === null &&
          cmd.machinePositional === null
        ) {
          return false;
        }
        if (context.repo === true && cmd.repoOption === null && cmd.repoPositional === null) {
          return false;
        }
        return true;
      }),

    proxyCapableCommands: () => contract.commands.filter((cmd) => cmd.proxyCapable),
  };
}
