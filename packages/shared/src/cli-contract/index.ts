/**
 * The `rdc` CLI contract.
 *
 * Generated from the live Commander tree — regenerate with
 * `npm run generate:cli-contract -w @rediacc/cli`. The check:ci-cli-contract
 * gate fails when the checked-in data drifts from the CLI.
 *
 * This root entry imports the contract literal statically, for the CLI and the
 * worker. A web bundle imports `./core` and `./load` instead, so the data lands
 * in a chunk of its own.
 */
export { type ContractIndex, indexContract } from './core.js';
export { CLI_CONTRACT, CLI_CONTRACT_VERSION } from './data/contract.generated.js';
export {
  DISCOVERY_FAMILIES,
  type DiscoveryFamily,
  type DiscoverySource,
  RESOURCE_DISCOVERY,
  RESOURCE_KINDS,
} from './discovery.js';
export {
  CONTRACT_LANGUAGES,
  type ContractLanguage,
  isContractLanguage,
  loadContractStrings,
  translate,
} from './i18n.js';
export { loadCliContract } from './load.js';
export type {
  CliContract,
  CommandExample,
  CommandGroup,
  CommandPlane,
  CommandPreview,
  CommandSeverity,
  ContractCommand,
  ContractErrorCode,
  ContractOption,
  ContractPositional,
  ContractStrings,
  ErrorOrigin,
  FormatHint,
  OptionTier,
  OutputHints,
  PositionalKind,
  PreviewPolarity,
  ResourceKind,
  TimeoutClass,
} from './types.js';
export {
  CliContractSchema,
  CommandExampleSchema,
  CommandGroupSchema,
  CommandPlaneSchema,
  CommandPreviewSchema,
  CommandSeveritySchema,
  ContractCommandSchema,
  ContractErrorCodeSchema,
  ContractOptionSchema,
  ContractPositionalSchema,
  ContractStringsSchema,
  checkContractInvariants,
  ErrorOriginSchema,
  FormatHintSchema,
  OptionTierSchema,
  OutputHintsSchema,
  PositionalKindSchema,
  PreviewPolaritySchema,
  parseCliContract,
  ResourceKindSchema,
  SUMMARY_MAX_LENGTH,
  safeParseCliContract,
  TimeoutClassSchema,
} from './validation.js';

import { indexContract } from './core.js';
import { CLI_CONTRACT } from './data/contract.generated.js';
import type { ContractCommand } from './types.js';

/** The lookups of ./core, built once over the bundled contract. */
const BUNDLED = indexContract(CLI_CONTRACT);

/** Look up a command by its space-joined path, e.g. "repo secret list". */
export function getCommand(pathKey: string): ContractCommand | undefined {
  return BUNDLED.getCommand(pathKey);
}

/** All commands, grouped by top-level domain ("repo", "machine", ...). */
export function commandsByDomain(): Map<string, ContractCommand[]> {
  return BUNDLED.commandsByDomain();
}

/**
 * Commands that can act on the given resources (see ContractIndex in ./core).
 * Passing no context returns every command.
 */
export function commandsForContext(context: {
  machine?: boolean;
  repo?: boolean;
}): ContractCommand[] {
  return BUNDLED.commandsForContext(context);
}

/** Commands a remote executor may run on the operator's behalf. */
export function proxyCapableCommands(): ContractCommand[] {
  return BUNDLED.proxyCapableCommands();
}
