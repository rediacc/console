/**
 * Progress parsing utilities for console output
 * Supports bash scripts, rsync and renet progress formats
 */

/** The last match of a progress pattern: its percentage and where it sits in the output. */
function lastProgressMatch(
  output: string,
  pattern: RegExp
): { percentage: number; index: number } | null {
  const matches = [...output.matchAll(pattern)];
  if (matches.length === 0) return null;
  const lastMatch = matches[matches.length - 1];
  return { percentage: Number.parseFloat(lastMatch[1]), index: lastMatch.index || -1 };
}

/**
 * Extract the most recent progress percentage from console output
 * Supports multiple formats:
 * - bash msg_progress "- N%"
 * - rsync "N%"
 * - renet "[operation] N% - message"
 *
 * @param output - Console output string
 * @returns Progress percentage (0-100) or null if not found
 */
export function extractMostRecentProgress(output: string): number | null {
  if (!output) return null;

  // Pattern 1: msg_progress format "- N%" (bash scripts)
  const msgProgressPattern = /-\s+(\d+(?:\.\d+)?)%/g;

  // Pattern 2: rsync format "N% speed" (transfer tools) Matches both byte format and human-readable format (K/M/G) Examples: "199,884,800 18% 190.59MB/s" or "1.5G 18% 190.59MB/s"
  const transferPattern = /\s+(\d+)%\s+[\d.,]+[KMG]?B\/s/g;

  // Pattern 3: renet format "[operation] N% - message" Examples: "[setup] 45% - Installing packages" or "[sync] 100% - Complete"
  const renetProgressPattern = /\[[^\]]+\]\s+(\d+(?:\.\d+)?)%/g;

  let latest = lastProgressMatch(output, msgProgressPattern);
  // A later pattern's percentage wins only if it appears after the one already found.
  for (const pattern of [transferPattern, renetProgressPattern]) {
    const candidate = lastProgressMatch(output, pattern);
    if (candidate && candidate.index > (latest?.index ?? -1)) latest = candidate;
  }

  if (latest === null) return null;

  // Clamp to valid range (0-100)
  return Math.min(100, Math.max(0, latest.percentage));
}

// ESC is built rather than written into the literal: no-control-regex refuses a control character in a regex.
const ANSI_SGR = new RegExp(`${String.fromCharCode(0x1b)}\\[[0-9;]*m`, 'g');

/** Clean message by removing ANSI codes and emojis */
function cleanProgressMessage(message: string): string {
  return message
    .replaceAll(ANSI_SGR, '')
    .replaceAll(/[\u{1F300}-\u{1F9FF}]/gu, '')
    .trim();
}

/** Pattern for msg_progress format "message - N%" */
const MSG_PROGRESS_LINE_PATTERN = /^(.+)\s+-\s+\d+(?:\.\d+)?%\s*$/;

/** Pattern for renet format "[operation] N% - message" */
const RENET_PROGRESS_LINE_PATTERN = /^\[([^\]]+)\]\s+\d+(?:\.\d+)?%\s+-\s+(.+)$/;

/** Pattern for rsync transfer line */
const RSYNC_PATTERN = /([\d.]+[KMG]?)\s+(\d+)%\s+([\d.]+[KMG]?B\/s)\s+(\d+:\d+:\d+)/;

/** Try to extract renet format message from line */
function tryExtractRenetMessage(line: string): string | null {
  const match = RENET_PROGRESS_LINE_PATTERN.exec(line);
  if (!match?.[2]) {
    return null;
  }
  const message = cleanProgressMessage(match[2]);
  return message ? `[${match[1]}] ${message}` : null;
}

/** Try to extract msg_progress format message from line */
function tryExtractMsgProgressMessage(line: string): string | null {
  const match = MSG_PROGRESS_LINE_PATTERN.exec(line);
  if (!match?.[1]) {
    return null;
  }
  const message = cleanProgressMessage(match[1]);
  return message || null;
}

/** Try to extract transfer tool (rsync) message from line */
function tryExtractTransferMessage(line: string): string | null {
  const rsyncMatch = RSYNC_PATTERN.exec(line);
  if (rsyncMatch) {
    return rsyncMatch[0];
  }

  return null;
}

/** Search for progress message in lines */
function findProgressMessageInLines(lines: string[]): { message: string; index: number } | null {
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i].trim();
    if (!line) continue;

    const renetMessage = tryExtractRenetMessage(line);
    if (renetMessage) {
      return { message: renetMessage, index: i };
    }

    const msgProgressMessage = tryExtractMsgProgressMessage(line);
    if (msgProgressMessage) {
      return { message: msgProgressMessage, index: i };
    }
  }
  return null;
}

/** Search for transfer tool message in lines after given index */
function findTransferMessageInLines(lines: string[], afterIndex: number): string | null {
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i].trim();
    if (!line) continue;

    if (i > afterIndex) {
      const transferMessage = tryExtractTransferMessage(line);
      if (transferMessage) {
        return transferMessage;
      }
    }
  }
  return null;
}

/**
 * Extract the most recent progress message from console output
 * Looks for text before "- N%" format, renet format, or transfer progress lines
 *
 * @param output - Console output string
 * @returns Progress message or null if not found
 */
export function extractProgressMessage(output: string): string | null {
  if (!output) return null;

  const lines = output.split('\n');

  const progressResult = findProgressMessageInLines(lines);
  const lastIndex = progressResult?.index ?? -1;

  const transferMessage = findTransferMessageInLines(lines, lastIndex);
  if (transferMessage) {
    return transferMessage;
  }

  return progressResult?.message ?? null;
}
