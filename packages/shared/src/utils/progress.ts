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
    lastPercentage = parseFloat(lastMatch[1]);
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
      lastPercentage = parseFloat(lastMatch[1]);
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
      lastPercentage = parseFloat(lastMatch[1]);
      lastIndex = matchIndex;
    }
  }

  if (lastPercentage === null) return null;

  // Clamp to valid range (0-100)
  return Math.min(100, Math.max(0, lastPercentage));
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
  let lastMessage: string | null = null;
  let lastIndex = -1;

  // Pattern 1: msg_progress format "message - N%"
  const msgProgressLinePattern = /^(.+)\s+-\s+\d+(?:\.\d+)?%\s*$/;

  // Pattern 1b: renet bridge format "[operation] N% - message"
  const renetProgressLinePattern = /^\[([^\]]+)\]\s+\d+(?:\.\d+)?%\s+-\s+(.+)$/;

  // Search from end to find the most recent progress message
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i].trim();
    if (!line) continue;

    // Try renet format first: "[operation] N% - message"
    const renetMatch = line.match(renetProgressLinePattern);
    if (renetMatch?.[2]) {
      const message = renetMatch[2]
        // eslint-disable-next-line no-control-regex
        .replace(/\x1b\[[0-9;]*m/g, '')
        .replace(/[\u{1F300}-\u{1F9FF}]/gu, '')
        .trim();

      if (message) {
        lastMessage = `[${renetMatch[1]}] ${message}`;
        lastIndex = i;
        break;
      }
    }

    // Try msg_progress format: "message - N%"
    const match = line.match(msgProgressLinePattern);
    if (match?.[1]) {
      // Clean up the message - remove any ANSI color codes and trim
      const message = match[1]
        // eslint-disable-next-line no-control-regex
        .replace(/\x1b\[[0-9;]*m/g, '') // Remove ANSI color codes
        .replace(/[\u{1F300}-\u{1F9FF}]/gu, '') // Remove any emojis
        .trim();

      if (message) {
        lastMessage = message;
        lastIndex = i;
        break;
      }
    }
  }

  // Pattern 2: rsync transfer line with human-readable format
  // Example: "      1.50G  18%  190.59MB/s    0:00:04"
  const rsyncPattern = /([\d.]+[KMG]?)\s+(\d+)%\s+([\d.]+[KMG]?B\/s)\s+(\d+:\d+:\d+)/;

  // Pattern 3: rclone transfer line
  // Example: "Transferred: 486.181G / 926.373 GBytes, 52%, 13.589 MBytes/s, ETA 9h12m49s"
  const rclonePattern =
    /Transferred:\s+([\d.]+[KMG]?)\s+\/\s+([\d.]+\s*[KMG]?Bytes?),\s+(\d+)%,\s+([\d.]+\s*[KMG]?Bytes?\/s)/i;

  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i].trim();
    if (!line) continue;

    // Try rsync format first - show the matched portion directly
    const rsyncMatch = line.match(rsyncPattern);
    if (rsyncMatch && i > lastIndex) {
      // Return the actual matched rsync output line
      return rsyncMatch[0];
    }

    // Try rclone format - show the matched portion directly
    const rcloneMatch = line.match(rclonePattern);
    if (rcloneMatch && i > lastIndex) {
      // Return the actual matched rclone output line
      return rcloneMatch[0];
    }
  }

  return lastMessage;
}
