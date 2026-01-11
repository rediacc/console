/**
 * Progress parsing utilities for console output
 * Supports bash scripts, rsync, rclone, and renet bridge progress formats
 */

/**
 * Extract the most recent progress percentage from console output
 * Supports multiple formats:
 * - bash msg_progress "- N%"
 * - rsync/rclone "N%"
 * - renet bridge "[operation] N% - message"
 *
 * @param output - Console output string
 * @returns Progress percentage (0-100) or null if not found
 */
export function extractMostRecentProgress(output: string): number | null {
  if (!output) return null;

  let lastPercentage: number | null = null;
  let lastIndex = -1;

  // Pattern 1: msg_progress format "- N%" (bash scripts)
  const msgProgressPattern = /-\s+(\d+(?:\.\d+)?)%/g;
  const msgProgressMatches = [...output.matchAll(msgProgressPattern)];

  if (msgProgressMatches.length > 0) {
    const lastMatch = msgProgressMatches[msgProgressMatches.length - 1];
    lastPercentage = Number.parseFloat(lastMatch[1]);
    lastIndex = lastMatch.index || -1;
  }

  // Pattern 2: rsync/rclone format "N% speed" (transfer tools)
  // Matches both byte format and human-readable format (K/M/G)
  // Examples: "199,884,800  18%  190.59MB/s" or "1.5G  18%  190.59MB/s"
  const transferPattern = /\s+(\d+)%\s+[\d.,]+[KMG]?B\/s/g;
  const transferMatches = [...output.matchAll(transferPattern)];

  if (transferMatches.length > 0) {
    const lastMatch = transferMatches[transferMatches.length - 1];
    const matchIndex = lastMatch.index || -1;
    // Use this percentage if it appears after the msg_progress percentage
    if (matchIndex > lastIndex) {
      lastPercentage = Number.parseFloat(lastMatch[1]);
      lastIndex = matchIndex;
    }
  }

  // Pattern 3: renet bridge format "[operation] N% - message"
  // Examples: "[setup] 45% - Installing packages" or "[sync] 100% - Complete"
  const renetProgressPattern = /\[[^\]]+\]\s+(\d+(?:\.\d+)?)%/g;
  const renetMatches = [...output.matchAll(renetProgressPattern)];

  if (renetMatches.length > 0) {
    const lastMatch = renetMatches[renetMatches.length - 1];
    const matchIndex = lastMatch.index || -1;
    if (matchIndex > lastIndex) {
      lastPercentage = Number.parseFloat(lastMatch[1]);
      lastIndex = matchIndex;
    }
  }

  if (lastPercentage === null) return null;

  // Clamp to valid range (0-100)
  return Math.min(100, Math.max(0, lastPercentage));
}

/** Clean message by removing ANSI codes and emojis */
function cleanProgressMessage(message: string): string {
  return (
    message
      // eslint-disable-next-line no-control-regex
      .replaceAll(/\x1b\[[0-9;]*m/g, '')
      .replaceAll(/[\u{1F300}-\u{1F9FF}]/gu, '')
      .trim()
  );
}

/** Pattern for msg_progress format "message - N%" */
const MSG_PROGRESS_LINE_PATTERN = /^(.+)\s+-\s+\d+(?:\.\d+)?%\s*$/;

/** Pattern for renet bridge format "[operation] N% - message" */
const RENET_PROGRESS_LINE_PATTERN = /^\[([^\]]+)\]\s+\d+(?:\.\d+)?%\s+-\s+(.+)$/;

/** Pattern for rsync transfer line */
const RSYNC_PATTERN = /([\d.]+[KMG]?)\s+(\d+)%\s+([\d.]+[KMG]?B\/s)\s+(\d+:\d+:\d+)/;

/** Pattern for rclone transfer line */
const RCLONE_PATTERN =
  /Transferred:\s+([\d.]+[KMG]?)\s+\/\s+([\d.]+\s*[KMG]?Bytes?),\s+(\d+)%,\s+([\d.]+\s*[KMG]?Bytes?\/s)/i;

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

/** Try to extract transfer tool (rsync/rclone) message from line */
function tryExtractTransferMessage(line: string): string | null {
  const rsyncMatch = RSYNC_PATTERN.exec(line);
  if (rsyncMatch) {
    return rsyncMatch[0];
  }

  const rcloneMatch = RCLONE_PATTERN.exec(line);
  if (rcloneMatch) {
    return rcloneMatch[0];
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
