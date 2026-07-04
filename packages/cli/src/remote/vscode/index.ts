/**
 * VS Code Remote SSH Integration Module
 * Provides VS Code Remote SSH connection management
 */

// Remote environment bootstrap
export { ensureVSCodeEnvSetup } from './bootstrap.js';
// Executable detection and launching
export {
  findVSCode,
  generateRemoteUri,
  isRemoteSSHExtensionInstalled,
  launchVSCode,
} from './executable.js';

// Key persistence
export {
  cleanupAllPersistedKeys,
  listPersistedKeys,
  persistKnownHosts,
  persistSSHKey,
  removePersistedKeys,
} from './keyPersistence.js';

// VS Code settings management
export {
  checkVSCodeConfiguration,
  configureVSCodeSettings,
  setHostRemotePlatform,
  setHostServerInstallPath,
} from './settings.js';
// SSH config management
export {
  addMachineSSHConfigEntry,
  addSSHConfigEntry,
  buildVSCodeSSHConfigEntry,
  generateConnectionName,
  getSSHConfigPath,
  listSSHConfigEntries,
  removeMachineSSHConfigEntry,
  removeSSHConfigEntry,
} from './sshConfig.js';
