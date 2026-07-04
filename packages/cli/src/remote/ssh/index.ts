/**
 * SSH module - Secure SSH connection handling
 * Ported from desktop/src/cli/core/shared.py
 */

// SSH connection
export { SSHConnection, spawnSSH, testSSHConnectivity } from './connection.js';
// Key management
export { createTempSSHKeyFile, isValidSSHKey, removeTempSSHKeyFile } from './keyManager.js';
// Known hosts handling
export { createTempKnownHostsFile, removeTempKnownHostsFile } from './knownHosts.js';
