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
    return typeof payload.renewalUrl === 'string' ? originOf(payload.renewalUrl) : undefined;
  } catch {
    // Not a licence file renet could use either.
    return undefined;
  }
}

/** The account-server origins of every licence installed on the machine for one repository GUID. */
async function readInstalledLicenseOrigins(
  sftp: Pick<SFTPClient, 'exec'>,
  repositoryGuid: string
): Promise<string[]> {
  const script =
    `for f in ${LICENSE_DIR}/repos/${repositoryGuid}/*.json ${LICENSE_DIR}/datastores/*/repos/${repositoryGuid}/*.json; ` +
    `do [ -f "$f" ] && base64 -w0 "$f" && echo; done; true`;
  const listing = await sftp.exec(`sudo -n sh -c ${shellQuote(script)} 2>/dev/null || true`);
  return licenseOriginsFromListing(listing);
}

/**
 * Refuse a backup-session verb whose repository holds a licence issued by another account server than this config's.
 * Nothing installed passes: the licence pre-flight or renet itself answers that case.
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

  const expected = originOf(getSubscriptionServerUrl());
  if (!expected) return;
  const installed = await readInstalledLicenseOrigins(sftp, repositoryGuid);
  const foreign = installed.filter((origin) => origin !== expected);
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
