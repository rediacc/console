/**
 * How a one-shot `ssh host <command>` session ends when the command does.
 *
 * sshd keeps a session's channel open until every process holding the
 * channel's stdout or stderr has let go, not until the command exits. A child
 * the command started in the background (a daemon, a `nohup` job, a helper a
 * tool forked) inherits those descriptors, so the local ssh, and the `rdc`
 * call waiting on it, outlived a finished command for as long as that child
 * ran (`term connect -c` on hostinger, stopped after 20+ minutes, 2026-11-20).
 *
 * The remote command therefore reports its own exit: an EXIT trap prints a
 * per-call marker and the exit status on stderr. The local side strips that
 * line from the stderr it shows, and once it has seen it, gives the channel a
 * short grace to close by itself (so the command's last output still lands),
 * then ends ssh and reports the marker's status. A command that never reaches
 * the trap (`exec`, its own EXIT trap) prints no marker and ends the way ssh
 * ends.
 */

import type { ChildProcess } from 'node:child_process';
import { randomBytes } from 'node:crypto';

/** How long a channel may stay open after the command reported its exit. */
export const EXIT_GRACE_MS = 2_000;

/** A fresh marker per call, so no output of the command can forge one. */
export function newExitMarker(): string {
  return `__rdc_exit_${randomBytes(8).toString('hex')}__:`;
}

/** The trap that makes the remote shell print `<marker><status>` on stderr as it exits. */
export function exitTrapShell(marker: string): string {
  return `trap 'printf "%s%s\\n" "${marker}" "$?" >&2' EXIT`;
}

const STATUS_LINE = /^(\d{1,3})\r?\n/;
/** What may follow a marker before its status line is complete. */
const PARTIAL_STATUS = /^\d{0,3}\r?$/;

/** How many trailing characters of `text` could still be the start of `marker`. */
function partialMarkerLength(text: string, marker: string): number {
  for (let len = Math.min(text.length, marker.length - 1); len > 0; len--) {
    if (marker.startsWith(text.slice(text.length - len))) return len;
  }
  return 0;
}

interface Scan {
  /** Text that can be shown now. */
  show: string;
  /** Text held back until more arrives. */
  hold: string;
  /** The status of a complete marker line. */
  status?: number;
  /** Text after a marker line, or after a marker-looking string that was not one, still to scan. */
  rest?: string;
}

/** One step over the held text. */
function scanOnce(held: string, marker: string): Scan {
  const at = held.indexOf(marker);
  if (at === -1) {
    const keep = partialMarkerLength(held, marker);
    return { show: held.slice(0, held.length - keep), hold: held.slice(held.length - keep) };
  }
  const after = held.slice(at + marker.length);
  const status = STATUS_LINE.exec(after);
  if (status) {
    return {
      show: held.slice(0, at),
      hold: '',
      status: Number(status[1]),
      rest: after.slice(status[0].length),
    };
  }
  if (PARTIAL_STATUS.test(after)) return { show: held.slice(0, at), hold: held.slice(at) };
  return { show: held.slice(0, at + marker.length), hold: '', rest: after };
}

/**
 * A streaming filter over the remote stderr: text passes through `onText`, the
 * marker line is removed and its status goes to `onExit`. A chunk boundary may
 * split the marker, so a tail that could still become one is held back.
 */
export function createExitMarkerFilter(
  marker: string,
  onText: (text: string) => void,
  onExit: (status: number) => void
): { push(chunk: string): void; end(): void } {
  let held = '';
  let seen = false;
  const show = (text: string | undefined): void => {
    if (text) onText(text);
  };

  return {
    push(chunk) {
      held += chunk;
      while (!seen) {
        const scan = scanOnce(held, marker);
        show(scan.show);
        if (scan.status !== undefined) {
          seen = true;
          onExit(scan.status);
          held = scan.rest ?? '';
        } else if (scan.rest === undefined) {
          held = scan.hold;
          return;
        } else {
          held = scan.rest;
        }
      }
      show(held);
      held = '';
    },
    end() {
      show(held);
      held = '';
    },
  };
}

export interface SessionEnd {
  /** The exit code to report: the marker's status when the command reported one, else ssh's. */
  code: number | null;
  /** True when the channel was still held open after the command exited and ssh was ended here. */
  forced: boolean;
}

export interface SessionEndOptions {
  /** The marker the remote command's {@link exitTrapShell} prints; absent for an interactive shell. */
  marker?: string;
  /** Receives the child's stderr as text, the marker line removed. */
  onStderr: (text: string) => void;
  graceMs?: number;
}

/**
 * Wait for an ssh child and resolve how it ended.
 *
 * It resolves once ssh has exited and its stderr has drained, so the last
 * lines are shown before the caller moves on; a stderr pipe that some other
 * process still holds is waited on for at most `graceMs` after the exit. With
 * a marker, a command that reported its exit while the channel stays open is
 * given `graceMs`, then ssh is ended and the marker's status is the answer.
 */
export function waitForSessionEnd(
  child: Pick<ChildProcess, 'on' | 'kill' | 'stderr'>,
  options: SessionEndOptions
): Promise<SessionEnd> {
  const graceMs = options.graceMs ?? EXIT_GRACE_MS;
  return new Promise<SessionEnd>((resolve, reject) => {
    let reported: number | undefined;
    let exitCode: number | null | undefined;
    let stderrEnded = !child.stderr;
    let forced = false;
    let settled = false;
    const timers: NodeJS.Timeout[] = [];
    const later = (fn: () => void): void => {
      timers.push(setTimeout(fn, graceMs));
    };
    const settle = (fn: () => void): void => {
      if (settled) return;
      settled = true;
      for (const timer of timers) clearTimeout(timer);
      fn();
    };
    const finish = (): void =>
      settle(() => resolve({ code: reported ?? exitCode ?? null, forced }));

    const onExitReported = (status: number): void => {
      reported = status;
      later(() => {
        if (exitCode !== undefined) return;
        // The command is done and the channel is still held open: end ssh, keep the command's status.
        forced = true;
        child.kill('SIGTERM');
        later(finish);
      });
    };
    const filter = options.marker
      ? createExitMarkerFilter(options.marker, options.onStderr, onExitReported)
      : { push: options.onStderr, end: () => undefined };

    child.stderr?.setEncoding('utf8');
    child.stderr?.on('data', (chunk: string) => filter.push(chunk));
    child.stderr?.on('end', () => {
      filter.end();
      stderrEnded = true;
      if (exitCode !== undefined) finish();
    });

    child.on('exit', (code: number | null) => {
      exitCode = code;
      if (stderrEnded) finish();
      else later(finish);
    });
    child.on('error', (error) => settle(() => reject(error)));
  });
}
