/**
 * A backup verb run with `--config X` must reach X's backup store.
 *
 * renet never asks the CLI which account a chunk-store session belongs to: `backup snapshot`, `backup restore`,
 * `backup browse-at` and `backup repair` mint their session at the URL derived from the installed repository
 * licence's `renewalUrl` (private/renet cmd/renet/backup_endpoints.go backupSessionURL), and the licence is picked by
 * signer, the renet build's baked key first (pkg/license/preferred.go LoadPreferredRepoLicense). On a machine whose
 * repository holds a licence from another account universe, a run through this config therefore writes to, or reads
 * from, that other account's store: a `backup snapshot ...@hostinger --config eu-bench` landed in the eu production
 * store while `backup usage` through eu-bench read bench's.
 *
 * This pre-flight reads every licence installed for the repository and refuses when any names an account server other
 * than this config's, since which of them renet picks is not the CLI's to know.
 */

import { t } from '../../i18n/index.js';
import type { SFTPClient } from '../../remote/sftp/index.js';
import { ValidationError } from '../../utils/errors.js';
import { shellQuote } from '../../utils/shell-quote.js';
import { getSubscriptionServerUrl } from '../account/subscription-auth.js';
import { getEffectiveConfigName } from '../config/config-name.js';
import { configService } from '../config/config-resources.js';

/** The renet functions that mint a chunk-store session from the installed repository licence. */
const BACKUP_SESSION_FUNCTIONS: ReadonlySet<string> = new Set([
  'backup_snapshot',
  'backup_restore',
  'backup_restore_path',
  'backup_browse_at',
  'backup_repair',
]);

/** renet's licence store (pkg/license/store.go): the unscoped layout and the per-datastore one. */
const LICENSE_DIR = '/var/lib/rediacc/license';
const GUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isBackupSessionFunction(functionName: string): boolean {
  return BACKUP_SESSION_FUNCTIONS.has(functionName);
}

/** The origin of a URL, or undefined when it is not one. */
function originOf(url: string): string | undefined {
  try {
    return new URL(url).origin;
  } catch {
    return undefined;
  }
}

/** The renet function param that holds a session verb to this config's account server (the verb's `--expect-account-server`). */
export const EXPECT_ACCOUNT_SERVER_PARAM = 'expect_account_server';

/** The active config's account-server origin, the one every licence a backup verb presents must name. */
export function expectedAccountServerOrigin(): string | undefined {
  return originOf(getSubscriptionServerUrl());
}

/**
 * `params` with the expected account-server origin added for a backup-session function, so renet itself refuses a
 * licence from another account server (`--expect-account-server`). The pre-flight below asks the same question from
 * the CLI; this answer travels with the run, which is what a scheduled unit (no CLI in the loop) relies on too.
 * It OVERWRITES an `expect_account_server` the caller passed: the config's origin is the only one a verb may be held to,
 * so a caller cannot widen it.
 */
export function withExpectedAccountServer(
  functionName: string,
  params: Record<string, unknown>
): Record<string, unknown> {
  if (!isBackupSessionFunction(functionName)) return params;
  const origin = expectedAccountServerOrigin();
  return origin ? { ...params, [EXPECT_ACCOUNT_SERVER_PARAM]: origin } : params;
}

/**
 * The account-server origins of the licences in `listing`: base64 lines, one per installed licence file, as the
 * remote read in {@link readInstalledLicenseOrigins} prints them. A line that does not decode to a licence carrying a
 * `renewalUrl` is skipped, as renet's own selection skips a file that does not parse.
 */
export function licenseOriginsFromListing(listing: string): string[] {
  const origins = new Set<string>();
  for (const line of listing.split('\n')) {
    const origin = licenseLineOrigin(line.trim());
    if (origin) origins.add(origin);
  }
  return [...origins].sort((a, b) => a.localeCompare(b));
}

/** The account-server origin of one base64 licence file, or undefined when it is not a licence with a `renewalUrl`. */
function licenseLineOrigin(encoded: string): string | undefined {
  if (!encoded) return undefined;
  try {
    const file = JSON.parse(Buffer.from(encoded, 'base64').toString('utf8')) as {
      payload?: unknown;
    };
    if (typeof file.payload !== 'string') return undefined;
    const payload = JSON.parse(Buffer.from(file.payload, 'base64').toString('utf8')) as {
      renewalUrl?: unknown;
    };
    // A `renewalUrl` that does not parse stays in the listing as itself: it is never this config's origin, so the
    // verb is refused rather than passed on a licence renet may still select.
    return typeof payload.renewalUrl === 'string'
      ? (originOf(payload.renewalUrl) ?? payload.renewalUrl)
      : undefined;
  } catch {
    // Not a licence file renet could use either.
    return undefined;
  }
}

/** Printed by the listing script only after it read every file, so a listing without it was cut short. */
export const LISTING_COMPLETE_MARKER = '__RDC_LICENSE_LISTING_COMPLETE__';

/**
 * The account-server origins of every licence installed on the machine for one repository GUID, or undefined when
 * the listing could not be read (sudo refused, a file unreadable, the command failed): the caller fails closed then,
 * since an empty answer would let a backup verb through without the check.
 */
async function readInstalledLicenseOrigins(
  sftp: Pick<SFTPClient, 'exec'>,
  repositoryGuid: string
): Promise<string[] | undefined> {
  const script =
    `set -e; for f in ${LICENSE_DIR}/repos/${repositoryGuid}/*.json ${LICENSE_DIR}/datastores/*/repos/${repositoryGuid}/*.json; ` +
    `do if [ -f "$f" ]; then base64 -w0 "$f"; echo; fi; done; echo ${LISTING_COMPLETE_MARKER}`;
  let listing: string;
  try {
    listing = await sftp.exec(`sudo -n sh -c ${shellQuote(script)}`);
  } catch {
    return undefined;
  }
  if (!listing.split('\n').some((line) => line.trim() === LISTING_COMPLETE_MARKER))
    return undefined;
  return licenseOriginsFromListing(listing);
}

/**
 * Refuse a backup-session verb whose repository holds a licence issued by another account server than this config's.
 * Nothing installed passes when the listing could be read: the licence pre-flight or renet itself answers that case.
 * An unreadable listing (sudo needs a password, or the completion marker is missing) refuses, installed or not.
 */
export async function assertBackupStoreUniverse(
  functionName: string,
  machineName: string,
  params: Record<string, unknown>,
  sftp: Pick<SFTPClient, 'exec'>
): Promise<void> {
  if (!isBackupSessionFunction(functionName)) return;
  const repoName = typeof params.repository === 'string' ? params.repository : '';
  if (!repoName) return;
  const repositoryGuid = (await configService.getRepository(repoName))?.repositoryGuid;
  if (!repositoryGuid || !GUID_PATTERN.test(repositoryGuid)) return;

  const serverUrl = getSubscriptionServerUrl();
  // A server URL that does not parse still gates: it matches no licence origin, so any installed licence refuses.
  const expected = originOf(serverUrl) ?? serverUrl;
  const installed = await readInstalledLicenseOrigins(sftp, repositoryGuid);
  if (installed === undefined) {
    throw new ValidationError(
      t('errors.license.backupStoreUnreadable', { repo: repoName, machine: machineName })
    );
  }
  // A licence origin that is not itself a URL origin (an unparseable renewalUrl kept as its raw string) is never this config's, even when the config's own server URL is the same raw string.
  const foreign = installed.filter((origin) => origin !== expected || originOf(origin) !== origin);
  if (foreign.length === 0) return;

  throw new ValidationError(
    t('errors.license.backupStoreMismatch', {
      repo: repoName,
      machine: machineName,
      installed: foreign.join(', '),
      expected,
      config: getEffectiveConfigName(),
    })
  );
}
