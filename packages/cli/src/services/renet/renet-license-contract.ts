export const RENET_LICENSE_REQUIRED_EXIT_CODE = 10;
export const RENET_LICENSE_REQUIRED_CODE = 'LICENSE_REQUIRED';

export interface RenetLicenseFailure {
  code: string;
  reason: string;
  message?: string;
}

function parseStructuredLine(line: string): RenetLicenseFailure | null {
  try {
    const parsed = JSON.parse(line) as Partial<RenetLicenseFailure>;
    if (
      typeof parsed.code === 'string' &&
      typeof parsed.reason === 'string' &&
      parsed.code === RENET_LICENSE_REQUIRED_CODE
    ) {
      return {
        code: parsed.code,
        reason: parsed.reason,
        message: typeof parsed.message === 'string' ? parsed.message : undefined,
      };
    }
  } catch {
    return null;
  }

  return null;
}

export function parseRenetLicenseFailure(
  stderr?: string,
  stdout?: string
): RenetLicenseFailure | null {
  for (const chunk of [stderr, stdout]) {
    if (!chunk) continue;
    const lines = chunk
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .reverse();
    for (const line of lines) {
      const parsed = parseStructuredLine(line);
      if (parsed) return parsed;
    }
  }

  return null;
}

/**
 * Repository functions that do NOT require pre-flight license issuance from the CLI.
 * Operate-tier operations (up/down/delete) are validated by renet with expiry
 * skipped, so CLI does not need to issue licenses for these. If the repo license
 * is missing, renet will still report it and CLI recovery kicks in.
 */
const REPOSITORY_DENY_LIST = new Set([
  'repository_up',
  'repository_up_all',
  'repository_down',
  'repository_delete',
]);

export function isLicensedRenetFunction(functionName: string): boolean {
  if (REPOSITORY_DENY_LIST.has(functionName)) return false;
  return functionName.startsWith('repository_') || functionName.startsWith('backup_');
}
