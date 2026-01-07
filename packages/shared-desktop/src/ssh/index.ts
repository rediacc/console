/**
 * SSH module - Secure SSH connection handling
 * Ported from desktop/src/cli/core/shared.py
 */

// Key management
export {
  decodeSSHKey,
  createTempSSHKeyFile,
  removeTempSSHKeyFile,
  extractKeyInfo,
  isValidSSHKey,
  type ExtractedKeyInfo,
} from './keyManager.js';

// Known hosts handling
export {
  decodeKnownHosts,
  createTempKnownHostsFile,
  removeTempKnownHostsFile,
  isValidKnownHosts,
  extractHostname,
  extractKeyType,
} from './knownHosts.js';

// SSH connection
export {
  SSHConnection,
  setupSSHConnection,
  setupSSHAgentConnection,
  cleanupSSHConnection,
  buildSSHOptions,
  convertPathForSSH,
  spawnSSH,
  testSSHConnectivity,
  type ConnectionMethod,
  type SSHSetupResult,
  type SSHConnectionCtorOptions,
} from './connection.js';

// SSH agent
export {
  startSSHAgent,
  addKeyToAgent,
  stopSSHAgent,
  isSSHAgentAvailable,
  getSSHAgentEnv,
  type SSHAgentResult,
  type SSHAgentEnv,
} from './agent.js';

// PTY handling
export {
  createSSHPTYSession,
  createLocalPTYSession,
  getActiveSession,
  isSessionActive,
  getActiveSessionCount,
  killAllSessions,
} from './pty.js';
