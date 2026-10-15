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

/**
 * The path a recursive delete would reach: every symlink on the way followed, a dangling one too, since `fs.rm` removes what the
 * link's final target names once it exists (review 1f969add.1, f434e6dc.2). A component that does not exist yet is kept as typed.
 */
function realPathOf(dir: string): string {
  let rest = path.resolve(dir).split(path.sep).filter(Boolean);
  let current = path.parse(path.resolve(dir)).root;
  for (let hops = 0; rest.length > 0; ) {
    const next = path.join(current, rest[0] as string);
    let stat: fs.Stats | undefined;
    try {
      stat = fs.lstatSync(next);
    } catch {
      stat = undefined;
    }
    if (stat?.isSymbolicLink()) {
      if (++hops > 40) throw new Error(`refusing to delete ${dir}: too many symlinks`);
      const target = path.resolve(current, fs.readlinkSync(next));
      rest = [...target.split(path.sep).filter(Boolean), ...rest.slice(1)];
      current = path.parse(target).root;
      continue;
    }
    current = next;
    rest = rest.slice(1);
  }
  return current;
}

export function assertThrowawayDir(dir: string): void {
  const resolved = realPathOf(dir);
  const temp = realPathOf(os.tmpdir());
  if (!resolved.startsWith(temp + path.sep)) {
    throw new Error(
      `refusing to delete ${resolved}: it is not under ${temp}, so this run is not isolated ` +
        '(run vitest from packages/cli, where its setup file points the config home at a temp directory)'
    );
  }
}
