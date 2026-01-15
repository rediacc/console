/**
 * VS Code Remote SSH Integration Module
 * Provides VS Code Remote SSH connection management
 */

// Remote environment bootstrap
export type {
  RemoteEnvSetupOptions,
  RemoteEnvSetupResult,
} from './bootstrap.js';
export {
  ensureVSCodeEnvSetup,
  generateVerifyCommand,
} from './bootstrap.js';
// Environment composition (ported from Python CLI)
export {
  buildMachineEnvironment,
  buildRemoteCommand,
  buildRepositoryEnvironment,
  composeEnvBlock,
  composeSudoEnvCommand,
  formatBashExports,
  formatSSHSetEnv,
  needsUserSwitch,
} from './envCompose.js';
// Executable detection and launching
export {
  findAllVSCodeInstallations,
  findVSCode,
  findVSCodeInWSL,
  generateRemoteUri,
  isRemoteSSHExtensionInstalled,
  launchVSCode,
} from './executable.js';

// Key persistence
export {
  cleanupAllPersistedKeys,
  getPersistedKeyPaths,
  listPersistedKeys,
  persistKnownHosts,
  persistSSHKey,
  removePersistedKeys,
} from './keyPersistence.js';

// VS Code settings management
export {
  checkVSCodeConfiguration,
  configureTerminalProfile,
  configureVSCodeSettings,
  getRequiredRemoteSSHSettings,
  getServerInstallPath,
  getVSCodeInsidersSettingsPath,
  getVSCodeSettingsPath,
  readVSCodeSettings,
  removeHostFromRemotePlatform,
  setHostServerInstallPath,
  writeVSCodeSettings,
} from './settings.js';
// SSH config management
export type { BuildSSHConfigOptions } from './sshConfig.js';
export {
  addSSHConfigEntry,
  buildVSCodeSSHConfigEntry,
  generateConnectionName,
  getSSHConfigEntry,
  getSSHConfigPath,
  listSSHConfigEntries,
  removeSSHConfigEntry,
} from './sshConfig.js';
// Types
export type {
  KeyPersistencePaths,
  SSHConfigEntry,
  VSCodeInfo,
  VSCodeInstallations,
  VSCodeLaunchOptions,
  VSCodePreference,
  VSCodeRemoteSettings,
} from './types.js';
