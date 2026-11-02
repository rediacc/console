/**
 * Helpers and types shared by the download and upload loops of `rdc backup download|upload`.
 */

import { statSync } from 'node:fs';
import { t } from '../../i18n/index.js';
import { allocatedBytesOf } from './preflight.js';
import type { RsyncTransport } from './session.js';

const DEFAULT_SSH_COMMAND = 'ssh';

/** Backoff before the first, second and third in-run retry. */
const RETRY_BACKOFF_MS = [10_000, 30_000, 60_000] as const;
export const DEFAULT_RETRIES = 3;
export const EXIT_INTERRUPTED = 130;

export interface RsyncRequest {
  args: string[];
  source: string;
  dest: string;
}

export interface RsyncOutcome {
  exitCode: number;
  literalBytes: number;
  matchedBytes: number;
  stderr?: string;
}

/** Thrown inside a repo run to stop it as interrupted (Ctrl-C). */
export class Interrupted extends Error {}

export function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function localAllocated(path: string): number {
  try {
    return allocatedBytesOf(statSync(path));
  } catch {
    return 0;
  }
}

export function remoteSpec(transport: RsyncTransport | undefined, path: string): string {
  return transport ? `${transport.userHost}:${path}` : path;
}

export function sshCommandOf(transport: RsyncTransport | undefined): string {
  return transport?.sshCommand ?? DEFAULT_SSH_COMMAND;
}

export function backoff(attempt: number): number {
  return RETRY_BACKOFF_MS[Math.min(attempt, RETRY_BACKOFF_MS.length - 1)];
}

/** Wraps a session so its quit runs at most once whatever path ends the run. */
export function onceQuit<S extends { quit(): Promise<void> }>(s: S): S {
  let q: Promise<void> | null = null;
  const quit = () => {
    q ??= s.quit().catch(() => undefined);
    return q;
  };
  return Object.assign(Object.create(Object.getPrototypeOf(s) as object) as S, s, { quit });
}
export function rsyncFailure(outcome: RsyncOutcome): string {
  const stderr = outcome.stderr?.trim();
  return t('errors.backupImage.rsyncExit', {
    code: String(outcome.exitCode),
    detail: stderr ? `: ${stderr}` : '',
  });
}
