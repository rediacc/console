/**
 * The Free License (PLAN-free-license R4-R13): a 3 GB repo licence any machine
 * can take from the configured account server without an account.
 *
 * - `resolveLicenseAuthority` answers the "no login" case of the licence paths:
 *   a human at a terminal is offered a login or a free licence, an agent or a
 *   `--yes` run takes the free licence with a warning naming the signup link.
 * - `issueFreeRepoLicense` calls `POST /licenses/free` (unauthenticated, E2E
 *   tunnel like every other account call) and installs the blob through the
 *   same writer `/activate-repo` blobs go through.
 * - `renewInstalledLicenses` runs renet's own blob-authenticated renewal on the
 *   machine. A FREE licence carries `renewalUrl` like any other, so this
 *   existing path renews it without limit (R6) and without a token.
 * - FREE has no hosted backup plane (R13): `assertHostedBackupAccount` and
 *   `isFreeLicenseBackupRefusal` turn the two ways that surfaces into the
 *   upgrade message instead of a bare token or session error.
 */

import { DEFAULTS } from '@rediacc/shared/config';
import { t } from '../../i18n/index.js';
import type { SFTPClient } from '../../remote/sftp/index.js';
import type { MachineConfig } from '../../types/index.js';
import { isAgentEnvironment } from '../../utils/agent-guard.js';
import { ValidationError } from '../../utils/errors.js';
import { askChoice } from '../../utils/prompt.js';
import { shellQuote } from '../../utils/shell-quote.js';
import { outputService } from '../core/output.js';
import { sftpConfigForMachine, withSharedOrPooledSftp } from '../machine/machine-connection.js';
import { accountServerFetch } from './account-client.js';
import { readLocalMachineId, readRemoteMachineId, writeRepoLicense } from './license-machine.js';
import { getSubscriptionServerUrl, getSubscriptionTokenState } from './subscription-auth.js';

export const FREE_LICENSE_PATH = '/account/api/v1/licenses/free';
/** The account server's refusal code when a FREE blob asks for a backup session. */
export const FREE_LICENSE_NO_BACKUP_CODE = 'FREE_LICENSE_NO_BACKUP';
/** The repository size cap of a FREE licence (R4). */
export const FREE_LICENSE_MAX_SIZE_GB = 3;

/** Who answers a licence request: the logged-in account, or a FREE licence. */
export type LicenseAuthority = 'token' | 'free';

/** The choice made in this process, so recovery and the pre-flight it re-runs ask once. */
let chosenAuthority: LicenseAuthority | undefined;
/** The signup link the server returned with the last FREE licence. */
let serverSignupUrl: string | undefined;

/** Test seam: forget the process-wide choice and signup link. */
export function resetFreeLicenseStateForTests(): void {
  chosenAuthority = undefined;
  serverSignupUrl = undefined;
}

/** The account page a FREE user signs up at: the server's own answer, else the configured server's login page. */
export function freeLicenseSignupUrl(): string {
  return serverSignupUrl ?? `${getSubscriptionServerUrl()}/account/login`;
}

function autoTakesFree(): boolean {
  return isAgentEnvironment() || process.env.REDIACC_YES === '1';
}

/**
 * Decide who licenses this run when there may be no login.
 *
 * - A ready token: `token`, nothing is asked.
 * - An agent or `--yes` (REDIACC_YES=1): `free`, with a warning naming the cap
 *   and the signup link (R11).
 * - A terminal: the operator picks a login (`login` runs, then `token`) or a
 *   free licence.
 * - Neither: `login` runs non-interactively (it prints the device-code URL),
 *   which is what this path did before FREE existed.
 */
export async function resolveLicenseAuthority(
  login: () => Promise<unknown>
): Promise<LicenseAuthority> {
  if (getSubscriptionTokenState().kind === 'ready') return 'token';
  if (chosenAuthority === 'free') return 'free';

  if (autoTakesFree()) {
    outputService.warn(
      t('errors.freeLicense.autoTaken', {
        url: freeLicenseSignupUrl(),
        maxGb: FREE_LICENSE_MAX_SIZE_GB,
      })
    );
    chosenAuthority = 'free';
    return 'free';
  }

  if (process.stdin.isTTY === true && process.stdout.isTTY === true) {
    const choice = await askChoice<'login' | 'free'>(t('errors.freeLicense.offerPrompt'), [
      { name: t('errors.freeLicense.offerLogin'), value: 'login' },
      {
        name: t('errors.freeLicense.offerFree', { maxGb: FREE_LICENSE_MAX_SIZE_GB }),
        value: 'free',
      },
    ]);
    if (choice === 'free') {
      chosenAuthority = 'free';
      return 'free';
    }
  }

  await login();
  chosenAuthority = 'token';
  return 'token';
}

export interface FreeLicenseParams {
  repositoryGuid: string;
  grandGuid?: string;
  kind: 'grand' | 'fork';
  requestedSizeGb?: number;
  datastoreId?: string;
}

/**
 * Take a FREE licence for one repository from the configured account server and
 * install it where renet reads this datastore's licences. The server's refusal
 * (the per-address window, the per-machine cap, a reused GUID, a size above
 * 3 GB) propagates with its own message, which names the signup link.
 */
export function issueFreeRepoLicense(
  machine: MachineConfig,
  sshPrivateKey: string,
  params: FreeLicenseParams,
  remoteRenetPath?: string,
  sharedSftp?: SFTPClient
): Promise<void> {
  return withSharedOrPooledSftp(
    sharedSftp,
    sftpConfigForMachine(machine, sshPrivateKey),
    async (sftp) => {
      const [machineId, clientMachineId] = await Promise.all([
        readRemoteMachineId(sftp, remoteRenetPath),
        readLocalMachineId(),
      ]);
      const { license, signupUrl } = await accountServerFetch<{
        license: unknown;
        signupUrl?: string;
      }>(FREE_LICENSE_PATH, {
        method: 'POST',
        noAuth: true,
        serverUrl: getSubscriptionServerUrl(),
        body: {
          machineId,
          clientMachineId,
          repositoryGuid: params.repositoryGuid,
          grandGuid: params.grandGuid,
          kind: params.kind,
          requestedSizeGb: params.requestedSizeGb,
          datastoreId: params.datastoreId,
        },
      });
      if (signupUrl) serverSignupUrl = signupUrl;
      await writeRepoLicense(sftp, params.repositoryGuid, license, params.datastoreId);
      outputService.info(t('errors.freeLicense.issued', { maxGb: FREE_LICENSE_MAX_SIZE_GB }));
    }
  );
}

/** One blob's verdict from `renet license renew --output json` (pkg/license/renew.go RenewResult). */
export interface LicenseRenewResult {
  repositoryGuid: string;
  outcome: string;
  code?: string;
  message?: string;
}

/**
 * Run renet's blob-authenticated renewal on the machine. It needs no token: the
 * installed blob is the credential and its `renewalUrl` the address, so a FREE
 * licence renews through it exactly like a paid one. `force` renews blobs not
 * yet due (the recovery of an expired licence); without it only due blobs are
 * sent. Returns how many were renewed and every result.
 */
export function renewInstalledLicenses(
  machine: MachineConfig,
  sshPrivateKey: string,
  options: { force?: boolean; remoteRenetPath?: string; sftp?: SFTPClient } = {}
): Promise<{ renewed: number; results: LicenseRenewResult[] }> {
  return withSharedOrPooledSftp(
    options.sftp,
    sftpConfigForMachine(machine, sshPrivateKey),
    async (sftp) => {
      const renetPath = options.remoteRenetPath ?? DEFAULTS.CONTEXT.RENET_BINARY;
      const force = options.force ? ' --force' : '';
      const output = await sftp.exec(
        `sudo -n ${shellQuote(renetPath)} license renew${force} --output json`
      );
      const parsed = JSON.parse(output) as { results?: LicenseRenewResult[] | null };
      const results = Array.isArray(parsed.results) ? parsed.results : [];
      return { renewed: results.filter((r) => r.outcome === 'renewed').length, results };
    }
  );
}

/** The upgrade message for a backup verb that needs the hosted plane. */
export function freeLicenseNoBackupMessage(): string {
  return t('errors.freeLicense.noHostedBackup', { url: freeLicenseSignupUrl() });
}

/**
 * The hosted backup plane is an account's: without a login (a FREE licence, or
 * none) its control-plane reads would fail on the missing token, a message that
 * says nothing about backups. Refuse with the upgrade message instead.
 */
export function assertHostedBackupAccount(): void {
  if (getSubscriptionTokenState().kind === 'ready') return;
  throw new ValidationError(freeLicenseNoBackupMessage());
}

/**
 * Whether a failed renet run is the account server refusing a FREE blob a
 * backup session: renet prints the server's code in its refusal
 * (chunkstore.SessionError), on stderr, stdout or the error line.
 */
export function isFreeLicenseBackupRefusal(result: {
  error?: string;
  stdout?: string;
  stderr?: string;
  errorCode?: string;
}): boolean {
  return [result.errorCode, result.error, result.stderr, result.stdout].some(
    (text) => typeof text === 'string' && text.includes(FREE_LICENSE_NO_BACKUP_CODE)
  );
}
