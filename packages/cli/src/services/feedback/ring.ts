/**
 * Local ring buffer of the last commands, redacted at write time, so a later
 * `rdc feedback report --last` can pre-fill a report without the CLI ever
 * having stored a secret. A write failure is swallowed: recording must never
 * change what a command prints or the exit code it returns.
 */
import { chmodSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';
import { scrubText } from '@rediacc/shared';
import { getRediaccDirs } from '@rediacc/shared/paths';
import { currentRequestContext } from '../core/request-context.js';
import { VERSION } from '../../version.js';
import { commandWords, redactArgv, resolveCommandPath } from './redact.js';

export const RING_CAPACITY = 10;
export const STDERR_TAIL_BYTES = 4096;

export interface RingEntry {
  at: string;
  commandPath: string;
  argv: string;
  exitCode: number;
  errorCode?: string;
  errorMessage?: string;
  stderrTail: string;
  cliVersion: string;
}

export interface RecordInput {
  argv: readonly string[];
  exitCode: number;
  errorCode?: string;
  errorMessage?: string;
}

let tail = '';
let tapped = false;
let restoreStderr: (() => void) | undefined;

/** The last `max` characters, starting at a whitespace boundary so a cut secret never leaves a partial prefix. */
function boundedTail(text: string, max: number): string {
  if (text.length <= max) return text;
  const cut = text.slice(-max);
  const boundary = cut.search(/\s/);
  return boundary >= 0 ? cut.slice(boundary) : '';
}

/** Keep the last bytes the CLI wrote to stderr, so a failure can carry its own output. */
export function installStderrTap(): void {
  if (tapped) return;
  tapped = true;
  const previous = process.stderr.write;
  const original = previous.bind(process.stderr) as (...args: unknown[]) => boolean;
  restoreStderr = () => {
    process.stderr.write = previous;
  };
  process.stderr.write = ((chunk: unknown, ...rest: unknown[]) => {
    try {
      const text = typeof chunk === 'string' ? chunk : Buffer.from(chunk as Uint8Array).toString();
      tail = boundedTail(tail + text, STDERR_TAIL_BYTES * 2);
    } catch {
      // The tap never interferes with the write itself.
    }
    return original(chunk, ...rest);
  }) as typeof process.stderr.write;
}

/** Put the original stderr writer back and allow a later install (tests). */
export function uninstallStderrTap(): void {
  restoreStderr?.();
  restoreStderr = undefined;
  tapped = false;
  tail = '';
}

/** Forget the captured stderr (tests; one CLI process runs one command, so production never needs it). */
export function resetStderrTail(): void {
  tail = '';
}

export function ringFilePath(): string {
  return path.join(getRediaccDirs().state, 'feedback', 'recent.jsonl');
}

export function readRing(): RingEntry[] {
  try {
    return readFileSync(ringFilePath(), 'utf8')
      .split('\n')
      .filter((line) => line.trim() !== '')
      .flatMap((line) => {
        try {
          return [JSON.parse(line) as RingEntry];
        } catch {
          return [];
        }
      });
  } catch {
    return [];
  }
}

/** Append one redacted entry, keeping the newest {@link RING_CAPACITY}. Never throws. */
export function recordCommand(input: RecordInput): void {
  try {
    if (currentRequestContext() !== undefined) return;
    const words = resolveCommandPath(input.argv);
    if (commandWords(input.argv)[0] === 'feedback') return;
    const home = homedir();
    const entry: RingEntry = {
      at: new Date().toISOString(),
      commandPath: words.join(' '),
      argv: redactArgv(input.argv, { homeDir: home }),
      exitCode: input.exitCode,
      stderrTail: boundedTail(scrubText(tail, { homeDir: home }), STDERR_TAIL_BYTES),
      cliVersion: VERSION,
      ...(input.errorCode ? { errorCode: input.errorCode } : {}),
      ...(input.errorMessage
        ? { errorMessage: scrubText(input.errorMessage, { homeDir: home }) }
        : {}),
    };
    const entries = [...readRing(), entry].slice(-RING_CAPACITY);
    const file = ringFilePath();
    mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 });
    const temp = `${file}.${process.pid}.tmp`;
    writeFileSync(temp, `${entries.map((e) => JSON.stringify(e)).join('\n')}\n`, { mode: 0o600 });
    chmodSync(temp, 0o600);
    renameSync(temp, file);
  } catch {
    // Recording is best effort.
  }
}
