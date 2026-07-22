/**
 * The executor daemon: one long-lived process that runs `execute()` on behalf of
 * consecutive short-lived `rdc` invocations, so the SSH handshake, renet
 * provision checks, and warm caches are paid once and reused.
 *
 * It is deliberately thin: on an `execute` frame it calls the EXISTING
 * `localExecutorService.execute()` with the wired options plus an `onEvent` that
 * relays each renet event back as a frame, forcing events mode so the far
 * process's output streams as structured events (its own stdout is /dev/null —
 * it was spawned detached). The client re-renders those events, so the operator
 * sees exactly what a direct run would show.
 *
 * Lifecycle: idle for IDLE_TIMEOUT_MS, or a SIGTERM/`stop` frame, drains in-flight
 * work and exits, removing the socket and token. A config-file change clears the
 * in-memory provision cache so a redirected machine is not served from a stale
 * one.
 */

import * as crypto from 'node:crypto';
import * as fs from 'node:fs';
import * as net from 'node:net';
import * as path from 'node:path';
import { getConfigDir } from '@rediacc/shared/paths';
import { configFileStorage } from '../../../adapters/config-file-storage.js';
import { configService } from '../../config/config-resources.js';
import { renetProvisioner } from '../../renet/renet-provisioner.js';
import { localExecutorService } from '../local-executor.js';
import type { Executor } from '../types.js';
import {
  daemonSocketPath,
  ensureDir,
  IDLE_TIMEOUT_MS,
  processIdentity,
  tokenPathFor,
  waitForSocket,
  writeToken,
} from './lifecycle.js';
import {
  type ClientFrame,
  createFrameReader,
  encodeFrame,
  type ServerFrame,
  type WireExecuteOptions,
} from './protocol.js';

/** Injectable seams so the server is exercisable without SSH or fixed paths. */
export interface DaemonServerDeps {
  /** The executor the daemon drives. Defaults to the real localExecutorService. */
  executor?: Executor;
  /** Socket path (and, alongside it, the token). Defaults to the runtime dir. */
  socketPath?: string;
  /** This daemon's content identity; a client mismatch is answered `stale`. */
  identity?: string;
  /** Idle ceiling before a self-exit. */
  idleTimeoutMs?: number;
  /** Watch the config dir and clear the provision cache on change (default on). */
  watchConfig?: boolean;
  /** How the daemon ends the process. Defaults to process.exit; tests inject a no-op. */
  onExit?: (code: number) => void;
}

/** A running daemon; `close()` drains and tears down without exiting the process. */
export interface DaemonHandle {
  socketPath: string;
  close(): Promise<void>;
}

/**
 * Start the daemon and return a handle. The `run` command awaits this and then
 * returns; the listening socket keeps the process alive on its own.
 */
export async function startExecutorDaemon(deps: DaemonServerDeps = {}): Promise<DaemonHandle> {
  // The daemon is the one long-lived process that wants warm SSH sessions:
  // enable the connection pool's idle linger for THIS process (default is 0 —
  // an open SSH socket would keep a short-lived CLI from exiting).
  process.env.REDIACC_SSH_LINGER_MS ??= String(5 * 60 * 1000);
  const executor = deps.executor ?? localExecutorService;
  const socketPath = deps.socketPath ?? daemonSocketPath();
  const identity = deps.identity ?? processIdentity();
  const idleTimeoutMs = deps.idleTimeoutMs ?? IDLE_TIMEOUT_MS;
  const exit = deps.onExit ?? ((code: number) => process.exit(code));
  const tokenPath = tokenPathFor(socketPath);
  const startedAt = Date.now();

  ensureDir(path.dirname(socketPath));
  await claimSocket(socketPath, exit);
  const token = writeToken(tokenPath);

  // Attribute daemon-run commands: telemetry/audit that reads the environment can
  // tell a daemon-executed command from a directly-run one without a new field.
  process.env.REDIACC_VIA_DAEMON = '1';

  const inFlight = new Set<Promise<unknown>>();
  const warmHosts = new Map<string, number>();
  const server = net.createServer();
  let closed = false;
  let idleTimer: NodeJS.Timeout | undefined;
  let stopWatch: (() => void) | undefined;
  const onSignal = (): void => void teardown().finally(() => exit(0));

  const teardown = async (): Promise<void> => {
    if (closed) return;
    closed = true;
    if (idleTimer) clearTimeout(idleTimer);
    stopWatch?.();
    process.removeListener('SIGTERM', onSignal);
    process.removeListener('SIGINT', onSignal);
    server.close();
    await Promise.allSettled([...inFlight]);
    for (const p of [socketPath, tokenPath]) {
      try {
        fs.unlinkSync(p);
      } catch {
        // Already gone: nothing to remove.
      }
    }
  };

  const armIdle = (): void => {
    if (idleTimer) clearTimeout(idleTimer);
    idleTimer = setTimeout(() => void teardown(), idleTimeoutMs);
    idleTimer.unref();
  };

  server.on('connection', (socket) => {
    armIdle();
    handleConnection({
      socket,
      token,
      identity,
      executor,
      inFlight,
      warmHosts,
      armIdle,
      startedAt,
      teardown,
      exit,
    });
  });

  await listen(server, socketPath);
  try {
    fs.chmodSync(socketPath, 0o600);
  } catch {
    // Best effort: the socket dir is already 0700, so this is defence in depth.
  }
  armIdle();

  process.on('SIGTERM', onSignal);
  process.on('SIGINT', onSignal);

  if (deps.watchConfig !== false) {
    stopWatch = watchConfigDir(() => renetProvisioner.clearCache());
  }

  return { socketPath, close: teardown };
}

/** Per-connection state, kept small and passed explicitly rather than closed over. */
interface ConnectionCtx {
  socket: net.Socket;
  token: string;
  identity: string;
  executor: Executor;
  inFlight: Set<Promise<unknown>>;
  warmHosts: Map<string, number>;
  armIdle: () => void;
  startedAt: number;
  teardown: () => Promise<void>;
  exit: (code: number) => void;
}

function handleConnection(ctx: ConnectionCtx): void {
  const { socket } = ctx;
  let authed = false;
  const send = (frame: ServerFrame): void => {
    if (!socket.writableEnded) socket.write(encodeFrame(frame));
  };

  const read = createFrameReader<ClientFrame>((frame) => {
    ctx.armIdle();
    if (!authed) {
      authed = handleHello(ctx, frame, send);
      if (!authed) socket.end();
      return;
    }
    handleAuthedFrame(ctx, frame, send);
  });

  socket.on('data', (chunk) => read(chunk));
  socket.on('error', () => socket.destroy());
}

/** Validate the first frame. Returns true when the connection may proceed. */
function handleHello(
  ctx: ConnectionCtx,
  frame: ClientFrame,
  send: (f: ServerFrame) => void
): boolean {
  if (frame.type !== 'hello') return false;
  if (!tokensMatch(frame.token, ctx.token)) return false;
  if (frame.identity !== ctx.identity) {
    // The client runs a different build than this daemon. Tell it so it can fall
    // back and respawn a fresh daemon, then exit ourselves after draining.
    send({ type: 'stale' });
    void ctx.teardown().finally(() => ctx.exit(0));
    return false;
  }
  send({ type: 'helloOk' });
  return true;
}

function handleAuthedFrame(
  ctx: ConnectionCtx,
  frame: ClientFrame,
  send: (f: ServerFrame) => void
): void {
  switch (frame.type) {
    case 'execute':
      runExecute(ctx, frame.id, frame.options, send);
      return;
    case 'status':
      send({
        type: 'statusInfo',
        pid: process.pid,
        uptimeMs: Date.now() - ctx.startedAt,
        identity: ctx.identity,
        warmHosts: [...ctx.warmHosts.keys()].sort(),
      });
      return;
    case 'stop':
      send({ type: 'stopping' });
      void ctx.teardown().finally(() => ctx.exit(0));
      return;
    case 'cancel':
      // Best-effort only: the Executor interface has no cancellation channel, so
      // an in-flight execute runs to completion. Accepted here for parity.
      return;
    default:
      return;
  }
}

function runExecute(
  ctx: ConnectionCtx,
  id: string,
  options: WireExecuteOptions,
  send: (f: ServerFrame) => void
): void {
  // Per-request config freshness. ConfigFileStorage memoizes parsed configs
  // with no mtime check, and daemon clients rewrite the config between
  // requests (the tutorial preambles wipe + re-init it constantly) — serving
  // a request from the first snapshot executed against deleted repos and
  // machines (observed live: whole-sequence cascade). The fs.watch below is
  // kept for the provisioner caches but is too coalesced/latent to be the
  // correctness mechanism for wipe-then-execute patterns; a ~1ms re-read per
  // request is nothing next to the SSH/provision savings the daemon exists for.
  configFileStorage.clearCache();
  // The parsed-file cache above is only half the staleness: configService
  // memoizes a ResourceState VIEW per process, which in a long-lived daemon
  // freezes the repository/machine world at boot. Reset both per request.
  configService.resetResourceView();
  send({ type: 'accepted', id });
  ctx.warmHosts.set(options.machineName, (ctx.warmHosts.get(options.machineName) ?? 0) + 1);

  const promise = ctx.executor
    .execute({
      ...options,
      // Force events mode: the daemon's own stdout is /dev/null, so output must
      // travel as event frames the client re-renders. The events path already
      // reconstructs result.stdout from the collector, so captured JSON commands
      // still get their payload back in the result.
      eventsMode: true,
      // Silence the executor's own spinners: they would draw to the daemon's
      // /dev/null stdout, and the CLI-side provision steps are recovered client
      // side from result.cliSteps instead. Mirrors the serve/tap path.
      quietSpinners: true,
      onEvent: (event, line) => send({ type: 'event', id, event, line }),
      onJobStarted: (jobId) => send({ type: 'jobStarted', id, jobId }),
    })
    .then((result) => send({ type: 'result', id, result }))
    .catch((error: unknown) =>
      send({ type: 'error', id, message: error instanceof Error ? error.message : String(error) })
    )
    .finally(() => ctx.inFlight.delete(promise));
  ctx.inFlight.add(promise);
}

/** Constant-time token comparison. */
function tokensMatch(a: string, b: string): boolean {
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  return ab.length === bb.length && crypto.timingSafeEqual(ab, bb);
}

/**
 * Take ownership of the socket path: if a live daemon already answers there, this
 * spawn is redundant and exits 0; a stale socket file is removed so we can bind.
 */
async function claimSocket(socketPath: string, exit: (code: number) => void): Promise<void> {
  if (!fs.existsSync(socketPath)) return;
  const existing = await waitForSocket(socketPath, 200);
  if (existing) {
    existing.destroy();
    // Another daemon owns this socket. A duplicate spawn is a no-op.
    exit(0);
    return;
  }
  try {
    fs.unlinkSync(socketPath);
  } catch {
    // Someone else removed it first; binding will reveal any real conflict.
  }
}

function listen(server: net.Server, socketPath: string): Promise<void> {
  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(socketPath, () => {
      server.removeListener('error', reject);
      resolve();
    });
  });
}

/**
 * Watch the config directory and invalidate the provision cache on any change.
 * Best-effort: a platform without fs.watch keeps its caches until idle-exit. The
 * connection pool is keyed by host:port:user:credential-fingerprint, so a config
 * change that alters those naturally lands on a fresh pool entry; the provision
 * cache is the one that must be cleared explicitly.
 */
function watchConfigDir(onChange: () => void): (() => void) | undefined {
  try {
    const watcher = fs.watch(getConfigDir(), { persistent: false }, () => onChange());
    return () => watcher.close();
  } catch {
    return undefined;
  }
}
