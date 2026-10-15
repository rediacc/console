/**
 * A test that deletes a directory deletes only a throwaway one. The vitest setup file points the
 * config home at a temp directory, but a run that skips it (a root-level `npx vitest run
 * packages/cli/...`, which loads no package config) left `getConfigDir()` on the developer's real
 * ~/.config/rediacc, and on 2026-10-14 config-remote-reenroll.test.ts removed it, the BWS
 * bootstrap token with it (#61fb7bc3). Called before every recursive delete of a path a test did
 * not create itself.
 */

import * as os from 'node:os';
import * as path from 'node:path';

export function assertThrowawayDir(dir: string): void {
  const resolved = path.resolve(dir);
  const temp = path.resolve(os.tmpdir());
  if (!resolved.startsWith(temp + path.sep)) {
    throw new Error(
      `refusing to delete ${resolved}: it is not under ${temp}, so this run is not isolated ` +
        '(run vitest from packages/cli, where its setup file points the config home at a temp directory)'
    );
  }
}
