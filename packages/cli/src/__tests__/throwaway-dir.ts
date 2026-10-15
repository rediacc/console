/**
 * A test that deletes a directory deletes only a throwaway one. The vitest setup file points the
 * config home at a temp directory, but a run that skips it (a root-level `npx vitest run
 * packages/cli/...`, which loads no package config) left `getConfigDir()` on the developer's real
 * ~/.config/rediacc, and on 2026-10-14 config-remote-reenroll.test.ts removed it, the BWS
 * bootstrap token with it (#61fb7bc3). Called before every recursive delete of a path a test did
 * not create itself.
 */

import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';

/** The path with every symlink in its existing part resolved: a link under the temp directory that points elsewhere is judged where it lands, since that is what a recursive delete removes (review 1f969add.1). */
function realPathOf(dir: string): string {
  let head = path.resolve(dir);
  const tail: string[] = [];
  while (!fs.existsSync(head)) {
    const parent = path.dirname(head);
    if (parent === head) break;
    tail.unshift(path.basename(head));
    head = parent;
  }
  return path.join(fs.realpathSync(head), ...tail);
}

export function assertThrowawayDir(dir: string): void {
  const resolved = realPathOf(dir);
  const temp = fs.realpathSync(os.tmpdir());
  if (!resolved.startsWith(temp + path.sep)) {
    throw new Error(
      `refusing to delete ${resolved}: it is not under ${temp}, so this run is not isolated ` +
        '(run vitest from packages/cli, where its setup file points the config home at a temp directory)'
    );
  }
}
