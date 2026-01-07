/**
 * Repository module - Repository connection and path management
 * Ported from desktop/src/cli/core/shared.py
 */

export {
  RepositoryConnection,
  getRepositoryPaths,
  getRepositoryEnvironment,
  FOLDER_NAMES,
  type RepositoryPaths,
  type MachineConnectionInfo,
} from './connection.js';

// Environment variable generation
export {
  buildRepositoryEnvironment,
  buildMachineEnvironment,
  mergeWithVaultEnvironment,
  type RepositoryEnvironment,
  type MachineVaultData,
  type RepositoryVaultData,
  type BuildEnvironmentOptions,
} from './environment.js';

// Bash functions for terminal sessions
export {
  BASHRC_REDIACC_CONTENT,
  generateSetupCommand,
  generateSourceCommand,
  wrapWithBashFunctions,
  generateCheckCommand,
} from './bashFunctions.js';
