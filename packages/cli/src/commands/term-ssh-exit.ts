import { t } from '../i18n/index.js';
import { writeStderr } from '../services/core/request-context.js';
import {
  isRenetFlagUnsupported,
  renetOlderThanCliMessage,
} from '../services/executor/job-client.js';
import { renetFailureReason } from '../services/executor/renet-output.js';

const sshExitCodeMessages: Record<number, string> = {
  1: 'sshCode1',
  126: 'sshCode126',
  127: 'sshCode127',
  130: 'sshCode130',
  255: 'sshCode255',
};

/** ssh's own sign-off when a PTY session ends; never the remote's reason. */
const SSH_CLOSED_LINE = /^Connection to \S+ closed\.?$/;

/** How much of the remote's stderr the error keeps; only its last lines can explain the exit. */
const STDERR_TAIL_CHARS = 4096;

/** True when renet itself rejected a flag: cobra's `Error:` line with renet's usage text. A heuristic: a `-c` command's own "unknown flag" line would have to carry both the `Error:` prefix and a renet mention to match. */
function isRenetFlagRejection(stderrTail: string): boolean {
  return (
    isRenetFlagUnsupported(stderrTail) &&
    /^Error: unknown (shorthand )?flag\b/im.test(stderrTail) &&
    /\brenet\b/.test(stderrTail)
  );
}

/**
 * The error for a non-zero ssh exit. When the remote printed why it failed (renet's cobra "Error:" line, or its last informative line), that reason IS the message, so `errors[].message` carries renet's text rather than the generic per-code hint (C11).
 */
export function buildSSHExitErrorMessage(
  code: number,
  stderrTail = '',
  machineName?: string
): string {
  // A flag the remote renet does not know is version skew, not a usage error: cobra's raw text says nothing about the fix.
  if (machineName && isRenetFlagRejection(stderrTail)) {
    return renetOlderThanCliMessage(machineName);
  }
  let message = t('errors.term.sshExitCode', { code });
  const reason = renetFailureReason(stderrTail, SSH_CLOSED_LINE);
  if (reason) return `${message}: ${reason}`;
  const codeKey = sshExitCodeMessages[code];
  if (codeKey) {
    message += `\n  ${t(`errors.term.${codeKey}`)}`;
  }
  return message;
}

/** Tee a child's stderr to the terminal as it arrives and keep its tail; the returned getter reads the tail. */
export function teeStderrTail(stream: NodeJS.ReadableStream | null): () => string {
  let tail = '';
  stream?.setEncoding('utf8');
  stream?.on('data', (chunk: string) => {
    writeStderr(chunk);
    tail = (tail + chunk).slice(-STDERR_TAIL_CHARS);
  });
  return () => tail;
}
