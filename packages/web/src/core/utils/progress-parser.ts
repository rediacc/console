/**
 * Core utilities for parsing progress from console output
 * These utilities are framework-agnostic and can be used in both React and CLI
 */

/**
 * Extract the most recent progress percentage from console output
 * Supports multiple formats:
 * - bash msg_progress "- N%"
 * - rsync/rclone "N%"
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

  if (lastPercentage === null) return null;

  // Clamp to valid range (0-100)
  return Math.min(100, Math.max(0, lastPercentage));
}

/**
 * Extract the most recent progress message from console output
 * Looks for text before "- N%" format or transfer progress lines
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

  // Search from end to find the most recent msg_progress message
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i].trim();
    if (!line) continue;

    const match = line.match(msgProgressLinePattern);
    if (match && match[1]) {
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

/**
 * Parse progress information from console output
 * Returns both percentage and message
 *
 * @param output - Console output string
 * @returns Object with progress percentage and message
 */
export function parseProgress(output: string): {
  percentage: number | null;
  message: string | null;
} {
  return {
    percentage: extractMostRecentProgress(output),
    message: extractProgressMessage(output),
  };
}

/**
 * Check if output indicates task completion
 * @param output - Console output string
 * @returns True if output contains completion indicators
 */
export function isTaskComplete(output: string): boolean {
  if (!output) return false;

  const completionPatterns = [
    /completed\s+successfully/i,
    /task\s+completed/i,
    /done\s*$/im,
    /finished\s+successfully/i,
    /100%.*completed/i,
  ];

  return completionPatterns.some((pattern) => pattern.test(output));
}

/**
 * Check if output indicates task failure
 * @param output - Console output string
 * @returns True if output contains failure indicators
 */
export function isTaskFailed(output: string): boolean {
  if (!output) return false;

  const failurePatterns = [/error:/i, /failed:/i, /fatal:/i, /exception:/i, /task\s+failed/i];

  return failurePatterns.some((pattern) => pattern.test(output));
}

/**
 * Extract error message from console output
 * @param output - Console output string
 * @returns Error message or null if not found
 */
export function extractErrorMessage(output: string): string | null {
  if (!output) return null;

  const lines = output.split('\n');

  // Search from end for error lines
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i].trim();
    if (!line) continue;

    // Check for error patterns
    const errorMatch = line.match(/(?:error|failed|fatal):\s*(.+)/i);
    if (errorMatch && errorMatch[1]) {
      return errorMatch[1].trim();
    }
  }

  return null;
}

/**
 * Calculate estimated time remaining based on progress
 * @param percentage - Current progress percentage
 * @param elapsedSeconds - Time elapsed in seconds
 * @returns Estimated remaining seconds or null if cannot calculate
 */
export function calculateETA(percentage: number, elapsedSeconds: number): number | null {
  if (percentage <= 0 || percentage >= 100 || elapsedSeconds <= 0) {
    return null;
  }

  const remainingPercentage = 100 - percentage;
  const secondsPerPercent = elapsedSeconds / percentage;
  const estimatedRemaining = remainingPercentage * secondsPerPercent;

  return Math.round(estimatedRemaining);
}

/**
 * Format ETA in human-readable format
 * @param seconds - Remaining seconds
 * @returns Formatted string like "5m 30s" or "1h 15m"
 */
export function formatETA(seconds: number): string {
  if (seconds < 60) {
    return `${seconds}s`;
  } else if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return secs > 0 ? `${minutes}m ${secs}s` : `${minutes}m`;
  } else {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`;
  }
}
