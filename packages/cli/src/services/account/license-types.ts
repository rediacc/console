/**
 * Shapes shared by the license modules: what renet's scans report and what the
 * account server's license report carries. Re-exported from `license.ts`.
 */

export interface RemoteRepoLicenseScanEntry {
  repositoryGuid: string;
  /**
   * Identity of the datastore holding this repo, minted at datastore create
   * and REMINTED at fork. It scopes both the signed payload and the on-machine
   * license store, which is what makes a same-node datastore fork re-meter.
   * Absent for the plain default datastore, which carries no descriptor.
   */
  datastoreId?: string;
  datastorePath?: string;
  requestedSizeGb: number;
  luksUuid?: string;
  storageFingerprint?: string;
  currentRefreshRecommendedAt?: string;
  currentHardExpiresAt?: string;
}

/** The persistent marker renet's backup gate writes when licensing refuses a backup. */
interface RepoLicenseBlockedBackup {
  repositoryGuid: string;
  code: string;
  reason: string;
  message: string;
  at: string;
  source: string;
}

/** One repo's slice of the last unattended `renet license renew` run. */
interface RepoLicenseRenewal {
  repositoryGuid: string;
  datastoreId?: string;
  keyId: string;
  outcome: string;
  newKeyId?: string;
  newSequence?: number;
  code?: string;
  message?: string;
}

export type RepoBatchRecoveryFailureMode =
  | 'token_not_ready'
  | 'no_known_repos'
  | 'server_rejected_all'
  | null; // null = success or partial success (valid > 0)

export interface RepoBatchRefreshResult {
  scanned: number;
  issued: number;
  refreshed: number;
  unchanged: number;
  failed: number;
  valid: number;
  invalidSignatureDetected: number;
  failures: { repositoryGuid: string; error: string }[];
  recoveryFailureMode: RepoBatchRecoveryFailureMode;
  serverErrorSample?: string;
}

interface RepoLicenseIssuancesUsage {
  used: number;
  limit: number;
  windowStart: string;
  windowEnd: string;
}

export interface SubscriptionLicenseReport {
  subscriptionId: string;
  orgId?: string;
  orgName?: string;
  teamId?: string;
  teamName?: string;
  planCode: string;
  status: string;
  machineSlots: {
    active: number;
    max: number;
    machines: {
      machineId: string;
      lastSeenAt: string;
      activatedAt?: string;
      /** A renewal soft-claimed this slot beyond the machine-slot limit. */
      overLimit?: boolean;
      clusterId?: string;
    }[];
  };
  repoLicenseIssuances: RepoLicenseIssuancesUsage;
  repoLicenses: {
    totalTrackedRepos: number;
    validCount: number;
    refreshRecommendedCount: number;
    hardExpiredCount: number;
  };
}

export interface MachineActivationStatus {
  machineId: string;
  active: boolean;
  lastSeenAt?: string;
  activeCount?: number;
  maxCount?: number;
}

export interface RuntimeRepoLicenseStatus {
  repositoryGuid: string;
  status:
    | 'valid'
    | 'missing'
    | 'expired'
    | 'machine_mismatch'
    | 'repository_mismatch'
    | 'sequence_regression'
    | 'invalid_signature'
    | 'identity_mismatch'
    | 'cert_expired'
    | 'cert_invalid'
    | 'unknown';
  message?: string;
  runtimeValid: boolean;
  installed: boolean;
  issuedAt?: string;
  refreshRecommendedAt?: string;
  hardExpiresAt?: string;
  expiresAt?: string;
  machineId?: string;
  kind?: string;
  grandGuid?: string;
  datastoreId?: string;
  datastorePath?: string;
  /** Present = unattended backups for this repo have been failing on licensing. */
  blockedBackup?: RepoLicenseBlockedBackup;
  lastRenewal?: RepoLicenseRenewal;
}
