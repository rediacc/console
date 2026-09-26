/**
 * Vitest setup file (vitest.config.ts `setupFiles`): every test file runs against an empty,
 * throwaway config, state and cache home, never the developer's own.
 *
 * Without it, a test that loads "the active config" read the real `~/.config/rediacc`. When that
 * config was remote-enabled, the test pulled it from the production config server with the
 * developer's real config token (2026-09-26: repo-container.test.ts and repo-executor.test.ts
 * failed with RemoteTokenIpMismatchError from the live server). CI has no such directory, which is
 * why only a developer machine saw it.
 *
 * A test that needs its own directory still sets XDG_CONFIG_HOME itself; this only changes the
 * default it starts from.
 */

import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll } from 'vitest';

const home = mkdtempSync(join(tmpdir(), 'rdc-cli-test-home-'));
process.env.XDG_CONFIG_HOME = join(home, 'config');
process.env.XDG_STATE_HOME = join(home, 'state');
process.env.XDG_CACHE_HOME = join(home, 'cache');
delete process.env.REDIACC_CONFIG;

afterAll(() => {
  rmSync(home, { recursive: true, force: true });
});
