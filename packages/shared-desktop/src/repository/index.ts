/**
 * Repository module - Repository connection and path management
 * Ported from desktop/src/cli/core/shared.py
 */

// Bash functions for terminal sessions
export {
  BASHRC_REDIACC_CONTENT,
  generateCheckCommand,
  generateSetupCommand,
  generateSourceCommand,
  wrapWithBashFunctions,
} from './bashFunctions.js';
export {
  FOLDER_NAMES,
  getRepositoryEnvironment,
  getRepositoryPaths,
  type MachineConnectionInfo,
  RepositoryConnection,
  type RepositoryPaths,
} from './connection.js';
// Environment variable generation
export {
  type BuildEnvironmentOptions,
  buildMachineEnvironment,
  buildRepositoryEnvironment,
  type MachineVaultData,
  mergeWithVaultEnvironment,
  type RepositoryEnvironment,
  type RepositoryVaultData,
} from './environment.js';
