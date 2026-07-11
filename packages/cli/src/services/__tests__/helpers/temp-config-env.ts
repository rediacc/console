/**
 * Side-effecting test helper: redirects the CLI config directory to a fresh
 * temp dir BEFORE the config-file-storage singleton captures getConfigDir().
 *
 * Import this FIRST (before any config/service module) so `XDG_CONFIG_HOME`
 * is set before `adapters/config-file-storage.ts` evaluates its module-level
 * `CONFIG_DIR = getConfigDir()`. ES module side-effects run in import order,
 * so a first-position import of this file wins the race.
 */
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const dir = mkdtempSync(join(tmpdir(), 'rdc-configv3-'));
process.env.XDG_CONFIG_HOME = dir;
// A master password so the encrypted-mode path never prompts on a TTY-less runner.
process.env.REDIACC_MASTER_PASSWORD = 'test-master-password';

export const TEST_CONFIG_HOME = join(dir, 'rediacc');
