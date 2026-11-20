import { t } from '../i18n/index.js';
import {
  isRenetFlagUnsupported,
  renetOlderThanCliMessage,
} from '../services/executor/job-client.js';
import { renetFailureReason } from '../services/executor/renet-output.js';
import { ERROR_CODES } from '../types/errors.js';
import { CliExitError } from '../utils/cli-exit-error.js';

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

/** The last STDERR_TAIL_CHARS of the stderr text added to it. */
export function createStderrTail(): { add(text: string): void; read(): string } {
  let tail = '';
  return {
    add(text) {
      tail = (tail + text).slice(-STDERR_TAIL_CHARS);
    },
    read: () => tail,
  };
}

/**
 * The error for a non-zero ssh exit. A `-c` command's own exit code becomes the CLI's exit code (255 stays
 * ssh's connection failure); an interactive shell keeps the generic failure code.
 */
export function sshExitError(
  code: number,
  stderrTail: string,
  machineName: string,
  oneShot: boolean
): Error {
  const message = buildSSHExitErrorMessage(code, stderrTail, machineName);
  if (!oneShot || code === 255) return new Error(message);
  return new CliExitError(ERROR_CODES.GENERAL_ERROR, message, { exitCode: code });
}
