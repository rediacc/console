/**
 * @rediacc/shared-desktop
 *
 * Node.js-only utilities for CLI and Electron main process.
 * Provides SSH, terminal, sync, and protocol handling functionality.
 */

// Re-export all types
export * from './types/index.js';

// Re-export utilities
export * from './utils/index.js';

// Re-export config
export * from './config/index.js';

// Note: Submodules (ssh, sync, terminal, protocol, msys2, repository, sftp)
// are imported directly via package.json exports:
//   import { SSHConnection } from '@rediacc/shared-desktop/ssh';
//   import { RsyncExecutor } from '@rediacc/shared-desktop/sync';
//   import { TerminalDetector } from '@rediacc/shared-desktop/terminal';
//   import { ProtocolParser } from '@rediacc/shared-desktop/protocol';
