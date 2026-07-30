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

/*
 * `isLicensedRenetFunction` and its REPOSITORY_DENY_LIST used to live here.
 * Both are deleted, and the deletion is the point.
 *
 * They were a SECOND source of truth for which bridge functions need a licence,
 * maintained by hand alongside renet's tier map, and they had already drifted:
 * the prefix rule claimed every `backup_*` function was licensed, while renet
 * licenses none of them. Proven live, one enforcing binary, no licence
 * installed: `repository create` exits 10 LICENSE_REQUIRED, `backup list`
 * sails past licensing and fails on a missing flag.
 *
 * Nothing consumed it. The only production reference was the comment in
 * local-executor.ts explaining why recovery deliberately does NOT gate on it
 * (rediacc/console#482: skipping recovery for deny-listed functions is what
 * broke `repo push --up` to a fresh machine). Its only other callers were its
 * own tests. So it was dead code asserting something false, which is worse
 * than no code: the next person to need this answer would have found a
 * plausible helper and trusted it.
 *
 * You cannot drift from a duplicate that does not exist. When a consumer
 * genuinely needs this answer, derive it from renet's tier map through the
 * generated contract rather than restating it here. renet's pkg/license
 * imports neither pkg/functions nor pkg/functions/commands, so a generator
 * can read the map without an import cycle. That is T3 of
 * docs/config-universe-follow-up/03-testing-pillar.md.
 */
