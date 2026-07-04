/**
 * Repository module - Repository connection and path management
 * Ported from desktop/src/cli/core/shared.py
 */

// Bash functions for terminal sessions
export { generateSetupCommand, generateSourceCommand } from './bashFunctions.js';
// Composite repo-name parsing
export { parentRepoName, repoTagFromName } from './repo-name.js';
