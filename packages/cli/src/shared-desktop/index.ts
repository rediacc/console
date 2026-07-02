/**
 * shared-desktop — Node.js utilities for SSH, SFTP, terminal, sync,
 * repository, and VS Code server orchestration. Merged into the CLI from
 * the former @rediacc/shared-desktop workspace package.
 */

// Re-export config
export * from './config/index.js';
// Re-export all types
export * from './types/index.js';
// Re-export utilities
export * from './utils/index.js';

// Note: Submodules (ssh, sync, terminal, msys2, repository, sftp, vscode,
// vscode-server) are imported directly, e.g.:
//   import { SSHConnection } from '../shared-desktop/ssh/index.js';
