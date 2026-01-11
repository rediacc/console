/**
 * VS Code Remote SSH Integration Module
 * Provides VS Code Remote SSH connection management
 */

// Types
export type {
  VSCodeInfo,
  VSCodeInstallations,
  VSCodePreference,
  SSHConfigEntry,
  VSCodeLaunchOptions,
  VSCodeRemoteSettings,
  KeyPersistencePaths,
} from './types.js';

// Executable detection and launching
export {
  findVSCode,
  findVSCodeInWSL,
  findAllVSCodeInstallations,
  generateRemoteUri,
  launchVSCode,
  isRemoteSSHExtensionInstalled,
} from './executable.js';

// SSH config management
export type { BuildSSHConfigOptions } from './sshConfig.js';

export {
  getSSHConfigPath,
  generateConnectionName,
  addSSHConfigEntry,
  removeSSHConfigEntry,
  getSSHConfigEntry,
  listSSHConfigEntries,
  buildVSCodeSSHConfigEntry,
} from './sshConfig.js';

// Key persistence
export {
  persistSSHKey,
  persistKnownHosts,
  getPersistedKeyPaths,
  removePersistedKeys,
  listPersistedKeys,
  cleanupAllPersistedKeys,
} from './keyPersistence.js';

// VS Code settings management
export {
  getVSCodeSettingsPath,
  getVSCodeInsidersSettingsPath,
  readVSCodeSettings,
  writeVSCodeSettings,
  getServerInstallPath,
  getRequiredRemoteSSHSettings,
  setHostServerInstallPath,
  configureVSCodeSettings,
  removeHostFromRemotePlatform,
  configureTerminalProfile,
  checkVSCodeConfiguration,
} from './settings.js';

// Environment composition (ported from Python CLI)
export {
  formatBashExports,
  formatSSHSetEnv,
  composeEnvBlock,
  buildRepositoryEnvironment,
  buildMachineEnvironment,
  composeSudoEnvCommand,
  needsUserSwitch,
  buildRemoteCommand,
} from './envCompose.js';

// Remote environment bootstrap
export type {
  RemoteEnvSetupOptions,
  RemoteEnvSetupResult,
} from './bootstrap.js';

export {
  ensureVSCodeEnvSetup,
  generateVerifyCommand,
} from './bootstrap.js';
