import { Secret, TOTP } from 'otpauth';
import { type CliResult, runCli } from './cli.js';

/**
 * Generate a valid TOTP code from a Base32 secret.
 * Uses the same parameters as the middleware implementation:
 * - Algorithm: HMAC-SHA1
 * - Period: 30 seconds
 * - Digits: 6
 */
export function generateTOTPCode(base32Secret: string): string {
  const totp = new TOTP({
    secret: Secret.fromBase32(base32Secret),
    algorithm: 'SHA1',
    digits: 6,
    period: 30,
  });
  return totp.generate();
}

/**
 * Extract TFA secret from CLI enable output.
 * The secret is a 32-character Base32-encoded string.
 */
export function extractSecret(result: CliResult): string | null {
  // Try JSON output first
  if (result.json && typeof result.json === 'object') {
    const json = result.json as Record<string, unknown>;
    if (typeof json.secret === 'string') {
      return json.secret;
    }
  }

  // Fall back to parsing stdout for setup key pattern
  // Matches: "Setup key: ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
  const match = result.stdout.match(/(?:Setup key|secret)[:\s]+([A-Z2-7]{32})/i);
  return match?.[1] ?? null;
}

/**
 * Enable TFA and return the secret.
 */
export async function enableTFA(): Promise<{ secret: string | null; success: boolean }> {
  const result = await runCli(['auth', 'tfa', 'enable']);
  if (!result.success) {
    return { secret: null, success: false };
  }
  const secret = extractSecret(result);
  return { secret, success: true };
}

/**
 * Disable TFA using a valid TOTP code generated from the secret.
 */
export async function disableTFA(secret: string): Promise<boolean> {
  const code = generateTOTPCode(secret);
  const result = await runCli(['auth', 'tfa', 'disable', '--code', code, '--yes']);
  return result.success;
}

/**
 * Check current TFA status.
 */
export async function getTFAStatus(): Promise<{ enabled: boolean; success: boolean }> {
  const result = await runCli(['auth', 'tfa', 'status']);
  if (!result.success) {
    return { enabled: false, success: false };
  }
  // Check output for enabled/disabled status
  const enabled = /enabled/i.test(result.stdout) && !/not enabled/i.test(result.stdout);
  return { enabled, success: true };
}
