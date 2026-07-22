/**
 * Executor-daemon runtime paths, identity, permissions, and spawn plumbing.
 *
 * The I/O-adjacent bits the server and client both need, kept separate from the
 * pure protocol so the protocol stays testable without touching the filesystem.
 */

import { spawn } from 'node:child_process';
import * as crypto from 'node:crypto';
import * as fs from 'node:fs';
import * as net from 'node:net';
import * as os from 'node:os';
import * as path from 'node:path';
import { getConfigDir } from '@rediacc/shared/paths';
import { configService } from '../../config/config-resources.js';
import { isSEA } from '../../../utils/platform.js';
import { VERSION } from '../../../version.js';

/** The daemon runs only where a unix-domain socket is the natural transport. */
export function isDaemonPlatform(): boolean {
  return process.platform === 'linux' || process.platform === 'darwin';
}

/** Idle ceiling: a daemon with no work for this long exits and cleans up. */
export const IDLE_TIMEOUT_MS = 5 * 60 * 1000;

const SOCKET_NAME = 'executor-daemon.sock';

/**
 * The daemon executes with ITS OWN config view, so a daemon is only valid for
 * clients sharing the same config CONTEXT: the config directory AND the
 * selected config name (`--config production` is a different universe than
 * the default `rediacc`). A per-UID socket alone let a daemon spawned under
 * one HOME serve clients running under another (observed live: a real-HOME
 * daemon executed a scratch-HOME tutorial's template apply against a config
 * with no such repo — renet fell back to a name-keyed mount path and failed).
 * Scoping the socket per (dir, name) gives each context its own daemon; the
 * client and server each derive the suffix from their own environment, so a
 * mismatch is structurally impossible rather than a checked error.
 */
function configScopeSuffix(): string {
  // Defensive: unit tests mock config-resources with partial shapes, and path
  // derivation must never crash a caller that will route direct anyway.
  const name =
    typeof configService.getEffectiveConfigName === 'function'
      ? configService.getEffectiveConfigName()
      : 'rediacc';
  const scope = `${getConfigDir()}:${name}`;
  return crypto.createHash('sha256').update(scope).digest('hex').slice(0, 12);
}

function currentUid(): number {
  return process.getuid?.() ?? 0;
}

/**
 * The per-user runtime directory holding the socket and token. Prefers
 * `$XDG_RUNTIME_DIR/rediacc` (a tmpfs the kernel reaps on logout), falling back
 * to a uid-scoped dir under the system temp dir when it is unset (macOS).
 */
function daemonRuntimeDir(): string {
  const xdg = process.env.XDG_RUNTIME_DIR;
  if (xdg) return path.join(xdg, 'rediacc');
  return path.join(os.tmpdir(), `rediacc-${currentUid()}`);
}

export function daemonSocketPath(): string {
  return path.join(daemonRuntimeDir(), `${configScopeSuffix()}-${SOCKET_NAME}`);
}

/** The token file that sits beside a given socket. */
export function tokenPathFor(socketPath: string): string {
  return path.join(path.dirname(socketPath), `${path.basename(socketPath, '.sock')}.token`);
}

function daemonTokenPath(): string {
  return tokenPathFor(daemonSocketPath());
}

/** Create `dir` 0700 (owner-only) if it does not exist. */
export function ensureDir(dir: string): string {
  fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  // mkdir honours the umask, so re-assert the mode on an existing dir.
  fs.chmodSync(dir, 0o700);
  return dir;
}

/** Mint a fresh auth token and write it 0600 at `tokenPath`. */
export function writeToken(tokenPath: string = daemonTokenPath()): string {
  const token = crypto.randomBytes(32).toString('hex');
  fs.writeFileSync(tokenPath, token, { mode: 0o600 });
  fs.chmodSync(tokenPath, 0o600);
  return token;
}

/** Read the token the running daemon wrote, or undefined when there is none. */
export function readToken(tokenPath: string = daemonTokenPath()): string | undefined {
  try {
    return fs.readFileSync(tokenPath, 'utf-8').trim() || undefined;
  } catch {
    return undefined;
  }
}

/**
 * This process's content identity. A running daemon honours a client only when
 * the two match, so a redeploy (SEA: a new VERSION) or a dev rebuild (same dev
 * VERSION but a fresh bundle stat) forces the old daemon out and a fresh one in.
 * In a SEA the immutable VERSION is enough; in dev the bundle changes under a
 * constant `0.0.0-dev`, so its (mtime,size) is folded in.
 */
export function processIdentity(): string {
  if (isSEA()) return VERSION;
  const bundle = process.argv[1];
  if (!bundle) return VERSION;
  try {
    const st = fs.statSync(bundle);
    return `${VERSION}:${Math.floor(st.mtimeMs)}:${st.size}`;
  } catch {
    return VERSION;
  }
}

/**
 * How to re-invoke THIS binary as `executor-daemon run`, mirroring how the
 * current process was launched: a SEA is its own executable, while a dev/npm run
 * is `node <execArgv> <bundle>`. execArgv is preserved so a tsx loader survives.
 */
function daemonSpawnArgv(): { command: string; args: string[] } {
  const tail = ['executor-daemon', 'run'];
  if (isSEA()) {
    return { command: process.execPath, args: tail };
  }
  const bundle = process.argv[1];
  const prefix = bundle ? [...process.execArgv, bundle] : [...process.execArgv];
  return { command: process.execPath, args: [...prefix, ...tail] };
}

/** Fire-and-forget a detached daemon that outlives this invocation. */
export function spawnDaemon(): void {
  const { command, args } = daemonSpawnArgv();
  const child = spawn(command, args, { detached: true, stdio: 'ignore' });
  child.unref();
}

/**
 * Poll-connect to the socket until it accepts or the deadline passes. Resolves
 * with a live socket (the caller owns it) or null when the daemon never came up.
 */
export function waitForSocket(socketPath: string, timeoutMs: number): Promise<net.Socket | null> {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve) => {
    const attempt = (): void => {
      const socket = net.connect(socketPath);
      const onError = (): void => {
        socket.destroy();
        if (Date.now() >= deadline) {
          resolve(null);
          return;
        }
        setTimeout(attempt, 50);
      };
      socket.once('error', onError);
      socket.once('connect', () => {
        socket.removeListener('error', onError);
        resolve(socket);
      });
    };
    attempt();
  });
}
