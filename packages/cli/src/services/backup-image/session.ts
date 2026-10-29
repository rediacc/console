/**
 * Client side of the `renet backup export` / `renet backup import` line protocol
 * (agent/plans/PLAN-backup-local-image.md Design 2 and 8).
 *
 * One exec channel per session, stdin held open (`SFTPClient.execSession`). The helper prints one
 * JSON ready line, then answers one-word commands, one JSON line each. The session is what holds
 * the snapshot (export) or the staging lock (import): ending stdin, `quit`, or 90 s with no line
 * makes the helper clean up, so this client pings every 20 s while it is open.
 */

import { t } from '../../i18n/index.js';
import type { ExecSessionHandle } from '../../remote/sftp/client.js';
import { shellQuote } from '../../utils/shell-quote.js';

/** Everything a path or argv token handed to a remote shell may contain; anything else is refused, not quoted. */
export const SAFE_REMOTE_TOKEN = /^[A-Za-z0-9/._-]+$/;
export const SESSION_IDLE_TIMEOUT = '90s';
export const SESSION_PING_MS = 20_000;
const QUIT_WAIT_MS = 10_000;

/** How the client's system rsync reaches the machine: the `-e` command and `user@host`. */
export interface RsyncTransport {
  sshCommand: string;
  userHost: string;
}

export interface ExportReady {
  snapshot: string;
  guid: string;
  takenAt: string;
  apparentBytes: number;
  allocatedBytes: number;
  rsyncPath: string;
  lowPriority: string[];
}

export interface ExportSession {
  ready: ExportReady;
  /** Absent only in test fakes; a real session always carries it. */
  transport?: RsyncTransport;
  /** True when the helper answered `pong`. Never throws. */
  ping(): Promise<boolean>;
  /** Hash of the snapshot, computed on the machine. */
  sha256(): Promise<string>;
  /** Ends the session (the helper deletes the snapshot). Never throws; idempotent. */
  quit(): Promise<void>;
}

export interface ImportReady {
  staging: string;
  fresh: boolean;
  seeded: boolean;
  existingBytes: number;
  rsyncPath: string;
}

export interface ImportSession {
  ready: ImportReady;
  transport?: RsyncTransport;
  ping?(): Promise<boolean>;
  /** Hash, LUKS check, owner and mode, atomic rename on the machine. Throws on any refusal. */
  finalize(sha256: string): Promise<{ path: string }>;
  discard?(): Promise<void>;
  quit(): Promise<void>;
}

interface ProtocolEvent {
  event: string;
  error?: string;
  [key: string]: unknown;
}

/** Refused before it reaches a remote shell: see SAFE_REMOTE_TOKEN. */
export function assertSafeRemoteToken(value: string, what: string): string {
  if (!SAFE_REMOTE_TOKEN.test(value) || value.split('/').includes('..')) {
    throw new Error(
      t('errors.backupImage.unsafeRemoteValue', { what, value: JSON.stringify(value) })
    );
  }
  return value;
}

function parseEvent(line: string): ProtocolEvent | null {
  try {
    const parsed = JSON.parse(line) as ProtocolEvent;
    return parsed && typeof parsed.event === 'string' ? parsed : null;
  } catch {
    return null;
  }
}

/**
 * The request/response core shared by both helpers. Requests are serialised: the helper answers
 * strictly in order, and the keepalive ping skips a beat while a request is in flight.
 */
export class HelperProtocol {
  private chain: Promise<unknown> = Promise.resolve();
  /** Requests in flight; the keepalive skips a beat while one is. */
  private inFlight = 0;
  private timer: ReturnType<typeof setInterval> | null = null;
  private quitting: Promise<void> | null = null;

  constructor(
    private readonly handle: ExecSessionHandle,
    private readonly stderrTail: () => string,
    private readonly onClosed: () => void = () => undefined
  ) {}

  /** Reads lines until a protocol event; non-JSON lines are skipped (stdout carries only the protocol). */
  private async nextEvent(): Promise<ProtocolEvent | null> {
    for (;;) {
      const line = await this.handle.nextLine();
      if (line === null) return null;
      const ev = parseEvent(line);
      if (ev) return ev;
    }
  }

  /** The first event: the ready line, or the helper's refusal. */
  async readReady(): Promise<ProtocolEvent> {
    const ev = await this.nextEvent();
    if (ev?.event === 'ready') return ev;
    const stderr = this.stderrTail();
    if (ev?.event === 'error') throw new Error(ev.error ?? stderr);
    if (/unknown command/i.test(stderr)) {
      throw new Error(t('errors.backupImage.renetTooOld'));
    }
    const code = await this.handle.exit;
    throw new Error(
      t('errors.backupImage.sessionFailed', { code: String(code), detail: stderr.trim() || '-' })
    );
  }

  request(line: string, expect: string): Promise<ProtocolEvent> {
    const run = async (): Promise<ProtocolEvent> => {
      if (this.handle.isClosed()) throw new Error(t('errors.backupImage.sessionClosed'));
      this.inFlight += 1;
      try {
        this.handle.write(line);
        const ev = await this.nextEvent();
        if (!ev) throw new Error(t('errors.backupImage.sessionClosed'));
        if (ev.event === 'error') throw new Error(ev.error ?? 'error');
        if (ev.event !== expect) {
          throw new Error(
            t('errors.backupImage.unexpectedEvent', { event: ev.event, expected: expect })
          );
        }
        return ev;
      } finally {
        this.inFlight -= 1;
      }
    };
    const next = this.chain.then(run, run);
    this.chain = next.catch(() => undefined);
    return next;
  }

  async ping(): Promise<boolean> {
    try {
      await this.request('ping', 'pong');
      return true;
    } catch {
      return false;
    }
  }

  private isIdle(): boolean {
    return this.inFlight === 0 && !this.handle.isClosed();
  }

  startKeepalive(intervalMs = SESSION_PING_MS): void {
    this.timer = setInterval(() => {
      if (this.isIdle()) void this.ping();
    }, intervalMs);
    this.timer.unref?.();
  }

  /** Sends `quit`, waits briefly for `closed` or the channel close, then ends stdin. Never throws. */
  quit(): Promise<void> {
    this.quitting ??= (async () => {
      if (this.timer) clearInterval(this.timer);
      this.timer = null;
      try {
        if (!this.handle.isClosed()) {
          this.handle.write('quit');
          await Promise.race([
            this.handle.exit,
            new Promise((r) => setTimeout(r, QUIT_WAIT_MS).unref?.()),
          ]);
        }
      } catch {
        // The helper is gone already; its own cleanup ran on EOF.
      } finally {
        this.handle.end();
        this.onClosed();
      }
    })();
    return this.quitting;
  }
}

function num(v: unknown): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : 0;
}

function str(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

export interface ExportCommandInput {
  renetPath: string;
  guid: string;
  datastore: string;
  checkpoint?: boolean;
  networkId?: number;
}

export function buildExportCommand(i: ExportCommandInput): string {
  const parts = [
    'sudo',
    '-n',
    shellQuote(i.renetPath),
    'backup',
    'export',
    '--name',
    shellQuote(assertSafeRemoteToken(i.guid, 'guid')),
    '--datastore',
    shellQuote(assertSafeRemoteToken(i.datastore, 'datastore')),
  ];
  if (i.checkpoint) {
    parts.push('--checkpoint');
    if (i.networkId) parts.push('--network-id', String(Math.trunc(i.networkId)));
  }
  parts.push('--idle-timeout', SESSION_IDLE_TIMEOUT);
  return parts.join(' ');
}

export interface ImportCommandInput {
  renetPath: string;
  guid: string;
  datastore: string;
  seedGuid?: string;
  allocatedBytes: number;
}

export function buildImportCommand(i: ImportCommandInput): string {
  const parts = [
    'sudo',
    '-n',
    shellQuote(i.renetPath),
    'backup',
    'import',
    '--guid',
    shellQuote(assertSafeRemoteToken(i.guid, 'guid')),
    '--datastore',
    shellQuote(assertSafeRemoteToken(i.datastore, 'datastore')),
  ];
  if (i.seedGuid) parts.push('--seed', shellQuote(assertSafeRemoteToken(i.seedGuid, 'seed')));
  parts.push('--allocated-bytes', String(Math.max(0, Math.trunc(i.allocatedBytes))));
  parts.push('--idle-timeout', SESSION_IDLE_TIMEOUT);
  return parts.join(' ');
}

/** `sudo -n <low-priority prefix...> <rsync>` for the machine side, every token checked. */
export function remoteRsyncPath(rsyncPath: string, lowPriority: string[] = []): string {
  const tokens = [...lowPriority, rsyncPath].map((tok) => assertSafeRemoteToken(tok, 'rsync path'));
  return ['sudo', '-n', ...tokens].join(' ');
}

export interface OpenSessionInput {
  handle: ExecSessionHandle;
  /** Recent stderr of the channel, for refusal messages. */
  stderrTail: () => string;
  transport: RsyncTransport;
  /** Runs once when the session ends (releases the connection lease, removes temp key files). */
  onClosed?: () => void;
  pingMs?: number;
}

/** Waits for the export helper's ready line and wraps the session. */
export async function startExportSession(input: OpenSessionInput): Promise<ExportSession> {
  const proto = new HelperProtocol(input.handle, input.stderrTail, input.onClosed);
  let ev: ProtocolEvent;
  try {
    ev = await proto.readReady();
  } catch (error) {
    await proto.quit();
    throw error;
  }
  const ready: ExportReady = {
    snapshot: str(ev.snapshot),
    guid: str(ev.guid),
    takenAt: str(ev.takenAt),
    apparentBytes: num(ev.apparentBytes),
    allocatedBytes: num(ev.allocatedBytes),
    rsyncPath: str(ev.rsyncPath) || 'rsync',
    lowPriority: Array.isArray(ev.lowPriority) ? ev.lowPriority.map(String) : [],
  };
  try {
    assertSafeRemoteToken(ready.snapshot, 'snapshot');
  } catch (error) {
    await proto.quit();
    throw error;
  }
  proto.startKeepalive(input.pingMs);
  return {
    ready,
    transport: input.transport,
    ping: () => proto.ping(),
    sha256: async () => str((await proto.request('sha256', 'sha256')).sha256),
    quit: () => proto.quit(),
  };
}

/** Waits for the import helper's ready line and wraps the session. */
export async function startImportSession(input: OpenSessionInput): Promise<ImportSession> {
  const proto = new HelperProtocol(input.handle, input.stderrTail, input.onClosed);
  let ev: ProtocolEvent;
  try {
    ev = await proto.readReady();
  } catch (error) {
    await proto.quit();
    throw error;
  }
  const ready: ImportReady = {
    staging: str(ev.staging),
    fresh: ev.fresh === true,
    seeded: ev.seeded === true,
    existingBytes: num(ev.existingBytes),
    rsyncPath: str(ev.rsyncPath) || 'rsync',
  };
  try {
    assertSafeRemoteToken(ready.staging, 'staging');
  } catch (error) {
    await proto.quit();
    throw error;
  }
  proto.startKeepalive(input.pingMs);
  return {
    ready,
    transport: input.transport,
    ping: () => proto.ping(),
    finalize: async (sha256: string) => {
      if (!/^[0-9a-f]{64}$/.test(sha256)) {
        throw new Error(
          t('errors.backupImage.unsafeRemoteValue', { what: 'sha256', value: sha256 })
        );
      }
      return { path: str((await proto.request(`finalize ${sha256}`, 'finalized')).path) };
    },
    discard: async () => {
      await proto.request('discard', 'discarded');
    },
    quit: () => proto.quit(),
  };
}
