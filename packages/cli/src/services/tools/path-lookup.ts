/**
 * Cross-platform PATH lookup, without shelling out to `which` (absent on Windows) or `where`.
 *
 * On Windows a bare name is tried with each extension in PATHEXT, in order, and the environment's PATH may be spelled `Path`. A name that already carries one of the PATHEXT extensions is tried as given. Empty PATH entries are skipped rather than read as the current directory.
 */

import { accessSync, constants, statSync } from 'node:fs';
import { posix, win32 } from 'node:path';

export interface PathLookupOptions {
  env?: NodeJS.ProcessEnv;
  platform?: NodeJS.Platform;
  /** Whether a candidate is a runnable file. Defaults to a real stat (plus X_OK off Windows). */
  isExecutable?: (candidate: string, platform: NodeJS.Platform) => boolean;
}

const DEFAULT_PATHEXT = '.COM;.EXE;.BAT;.CMD';

function defaultIsExecutable(candidate: string, platform: NodeJS.Platform): boolean {
  try {
    if (!statSync(candidate).isFile()) return false;
    if (platform !== 'win32') accessSync(candidate, constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

function envValue(env: NodeJS.ProcessEnv, name: string, platform: NodeJS.Platform): string {
  if (platform !== 'win32') return env[name] ?? '';
  const key = Object.keys(env).find((k) => k.toUpperCase() === name);
  return key ? (env[key] ?? '') : '';
}

/** The file names to try in one directory for `command`. */
function candidateNames(command: string, env: NodeJS.ProcessEnv, platform: NodeJS.Platform) {
  if (platform !== 'win32') return [command];
  const exts = (envValue(env, 'PATHEXT', platform) || DEFAULT_PATHEXT)
    .split(';')
    .map((e) => e.trim())
    .filter(Boolean);
  const lower = command.toLowerCase();
  if (exts.some((e) => lower.endsWith(e.toLowerCase()))) return [command];
  return exts.map((e) => `${command}${e.toLowerCase()}`);
}

/** The absolute path `command` resolves to on PATH, or null when nothing runnable matches. */
export function findOnPath(command: string, options: PathLookupOptions = {}): string | null {
  const env = options.env ?? process.env;
  const platform = options.platform ?? process.platform;
  const isExecutable = options.isExecutable ?? defaultIsExecutable;
  const names = candidateNames(command, env, platform);
  const hasDir = command.includes('/') || (platform === 'win32' && command.includes('\\'));
  const candidates = hasDir
    ? names
    : pathDirs(env, platform).flatMap((dir) => names.map((name) => joinFor(platform, dir, name)));
  return candidates.find((c) => isExecutable(c, platform)) ?? null;
}

function joinFor(platform: NodeJS.Platform, dir: string, name: string): string {
  return platform === 'win32' ? win32.join(dir, name) : posix.join(dir, name);
}

/** PATH split for the platform, quotes around Windows entries removed, empty entries dropped. */
function pathDirs(env: NodeJS.ProcessEnv, platform: NodeJS.Platform): string[] {
  const raw = envValue(env, 'PATH', platform);
  if (platform !== 'win32') return raw.split(posix.delimiter).filter(Boolean);
  return raw
    .split(win32.delimiter)
    .map((d) => d.trim().replace(/^"(.*)"$/, '$1'))
    .filter(Boolean);
}
