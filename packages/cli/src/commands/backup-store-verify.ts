/**
 * The server-side chunk walk behind `backup verify --store` and `backup repair`. It lives apart from
 * backup-storage.ts, the Commander registration file, so repair can import it without a cycle.
 */

import { accountServerFetch } from '../services/account/account-client.js';
import { assertHostedBackupAccount } from '../services/account/free-license.js';

/** POST /backups/verify, level `chunks`: one capped page of the lineage's re-hashed chunks. */
interface BackupChunkVerifyResponse {
  subscriptionId: string;
  chunks: {
    lineageGuid: string;
    checked: number;
    missing: string[];
    corrupt: string[];
    nextAfter: string | null;
  };
}

/** The `backup verify --store` verdict: every referenced chunk of the lineage, re-hashed by the server. */
export interface StoreVerifyVerdict {
  lineageGuid: string;
  checked: number;
  missing: string[];
  corrupt: string[];
}

/**
 * Walk the server's chunk verify for one lineage, page by page, until the
 * cursor runs out. Each page re-hashes at most the server's cap
 * (BACKUP_VERIFY_CHUNKS_MAX), so a large lineage is many requests.
 */
export async function runStoreVerify(lineageGuid: string): Promise<StoreVerifyVerdict> {
  assertHostedBackupAccount();
  const verdict: StoreVerifyVerdict = { lineageGuid, checked: 0, missing: [], corrupt: [] };
  let after: string | undefined;
  const sent = new Set<string>();
  for (;;) {
    const page = await accountServerFetch<BackupChunkVerifyResponse>(
      '/account/api/v1/backups/verify',
      { method: 'POST', body: { lineageGuid, level: 'chunks', after } }
    );
    verdict.checked += page.chunks.checked;
    verdict.missing.push(...page.chunks.missing);
    verdict.corrupt.push(...page.chunks.corrupt);
    if (!page.chunks.nextAfter) return verdict;
    // A cursor already sent, the last one or any earlier (A, B, A), would loop forever on a misbehaving server.
    if (sent.has(page.chunks.nextAfter) || page.chunks.nextAfter === after) {
      throw new Error(`backup verify --store: the server repeated cursor ${page.chunks.nextAfter}`);
    }
    after = page.chunks.nextAfter;
    sent.add(after);
  }
}
