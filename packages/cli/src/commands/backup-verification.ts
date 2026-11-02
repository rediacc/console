/**
 * Recording a passphrase-holder's verdict on a stored snapshot
 * (`POST /backups/snapshots/:id/verification`), shared by `backup check` and
 * `backup verify --restore-test`. Only the CLI can post it: the machine's
 * scheduled unit holds no passphrase, so only a run from here proves one opens.
 */

import { accountServerFetch } from '../services/account/account-client.js';

export type VerificationLevel = 'test-open' | 'restore-test';

/** The route's answer. `verificationState` is what the SERVER now holds, which is not always what was posted. */
export interface VerificationAnswer {
  snapshotId: string;
  verificationState: string;
  verificationLevel: string | null;
  verifiedAt: string | null;
}

/** Post a verdict. A 200 can answer `failed` for a `proven` post, so callers read `verificationState` and never echo what they sent. */
export function postVerification(
  snapshotId: string,
  level: VerificationLevel,
  status: 'proven' | 'failed'
): Promise<VerificationAnswer> {
  return accountServerFetch<VerificationAnswer>(
    `/account/api/v1/backups/snapshots/${encodeURIComponent(snapshotId)}/verification`,
    { method: 'POST', body: { level, status } }
  );
}
