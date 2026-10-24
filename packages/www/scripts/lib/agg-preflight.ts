import { accessSync, constants } from 'node:fs';
import path from 'node:path';

/**
 * The agg binary the renderer will run, resolved EXACTLY as lib/ffmpeg-video.ts resolves
 * it (`AGG_BIN`, else `~/.local/bin/agg`). The two must not diverge: a preflight that finds
 * an agg the renderer then does not use would pass and still fail ENOENT mid-render.
 * `.ci/media/pool.sh` exports AGG_BIN from `.ci/bootstrap.sh which agg`, which is how the
 * pinned cache install reaches both.
 */
export function resolveAggPath(env: NodeJS.ProcessEnv = process.env): string {
  return env.AGG_BIN ?? path.join(env.HOME ?? '', '.local', 'bin', 'agg');
}

export const AGG_INSTALL_HINT = 'bash .ci/bootstrap.sh install agg';

/** Throws, naming the install command, when agg cannot be executed. Called before any scene work so a missing tool costs seconds, not a half-rendered tutorial. */
export function assertAggAvailable(env: NodeJS.ProcessEnv = process.env): string {
  const bin = resolveAggPath(env);
  try {
    accessSync(bin, constants.X_OK);
  } catch {
    const origin = env.AGG_BIN ? 'AGG_BIN' : 'the default ~/.local/bin/agg';
    throw new Error(
      `agg (asciinema gif generator) is not an executable file at ${bin} (from ${origin}). ` +
        `The tutorial renderer needs it for every terminal cast scene. Install the pinned, ` +
        `checksum-verified release with: ${AGG_INSTALL_HINT}`
    );
  }
  return bin;
}
