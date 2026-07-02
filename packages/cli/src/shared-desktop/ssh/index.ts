/**
 * SSH module - Secure SSH connection handling
 * Ported from desktop/src/cli/core/shared.py
 */

// SSH agent
export {
  addKeyToAgent,
  getSSHAgentEnv,
  isSSHAgentAvailable,
  type SSHAgentEnv,
  type SSHAgentResult,
  startSSHAgent,
  stopSSHAgent,
} from './agent.js';
// SSH connection
export {
  buildSSHOptions,
  type ConnectionMethod,
  cleanupSSHConnection,
  convertPathForSSH,
  SSHConnection,
  type SSHConnectionCtorOptions,
  type SSHSetupResult,
  setupSSHAgentConnection,
  setupSSHConnection,
  spawnSSH,
  testSSHConnectivity,
} from './connection.js';
// Key management
export {
  createTempSSHKeyFile,
  decodeSSHKey,
  type ExtractedKeyInfo,
  extractKeyInfo,
  isValidSSHKey,
  removeTempSSHKeyFile,
} from './keyManager.js';
// Known hosts handling
export {
  createTempKnownHostsFile,
  decodeKnownHosts,
  extractHostname,
  extractKeyType,
  isValidKnownHosts,
  removeTempKnownHostsFile,
} from './knownHosts.js';

// PTY handling
export {
  createLocalPTYSession,
  createSSHPTYSession,
  getActiveSession,
  getActiveSessionCount,
  isSessionActive,
  killAllSessions,
} from './pty.js';
