/**
 * Report fingerprint: SHA-256 over command path, exit code and the normalised
 * error, so the same failure on different machines collapses to one id.
 * Paths, ids, IP addresses, clock times and numbers are normalised; hostnames
 * and other machine names are not, so an error that differs only by host
 * yields a different fingerprint.
 */

const UUID = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/g;
const HEX_RUN = /\b[0-9a-f]{8,}\b/g;
const IPV4 = /\b\d{1,3}(?:\.\d{1,3}){3}\b/g;
const CLOCK = /(?<![:\w])\d{1,2}:\d{2}(?::\d{2})?(?![:\w])/g;
const IPV6 = /\b(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}\b/g;
const WIN_PATH = /\b[a-z]:\\[^\s'"]*/g;
const UNIX_PATH = /(?<![\w<])(?:~|\.{1,2})?\/[^\s'"]+/g;
const DIGITS = /\d+/g;

export function normalizeError(error: string): string {
  return error
    .toLowerCase()
    .replace(UUID, '<uuid>')
    .replace(WIN_PATH, '<path>')
    .replace(UNIX_PATH, '<path>')
    .replace(IPV4, '<ip>')
    .replace(CLOCK, '<time>')
    .replace(IPV6, '<ip>')
    .replace(HEX_RUN, '<hex>')
    .replace(DIGITS, '<n>')
    .replace(/\s+/g, ' ')
    .trim();
}

export interface FingerprintInput {
  commandPath: string;
  exitCode: number;
  error: string;
}

/** Lowercase hex SHA-256 (64 chars). */
export async function feedbackFingerprint(input: FingerprintInput): Promise<string> {
  const text = `${input.commandPath}\n${input.exitCode}\n${normalizeError(input.error)}`;
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('');
}

/** Display form: first 12 hex characters. */
export function shortFeedbackFingerprint(fingerprint: string): string {
  return fingerprint.slice(0, 12);
}
