/**
 * CLI Audit Service
 *
 * Fire-and-forget audit event logging for machine-level CLI operations.
 * Events are queued in memory during command execution and flushed
 * to the account server in a single batch on process exit.
 *
 * Only active when a subscription token is available (cloud adapter).
 * Local adapter users (no token) get silent no-ops.
 */

import { getSubscriptionTokenState } from './subscription-auth.js';
import { accountServerFetch } from './account-client.js';
import { VERSION } from '../version.js';

export interface AuditEvent {
  type: string;
  data: {
    functionName: string;
    machineName: string;
    repoName?: string;
    success: boolean;
    exitCode: number;
    durationMs: number;
    cliVersion: string;
    error?: string;
  };
}

const FLUSH_TIMEOUT_MS = 5_000;
const AUDIT_ENDPOINT = '/account/api/v1/licenses/audit-events';

/**
 * Map renet function names to audit event types.
 *
 * Pattern: strip known prefixes, add `cli.` namespace.
 * e.g. `repository_up` -> `cli.repo.up`
 *      `backup_push`   -> `cli.backup.push`
 */
export function functionNameToEventType(functionName: string): string {
  if (functionName.startsWith('repository_')) {
    return `cli.repo.${functionName.slice('repository_'.length)}`;
  }
  if (functionName.startsWith('backup_')) {
    return `cli.backup.${functionName.slice('backup_'.length)}`;
  }
  if (functionName.startsWith('datastore_')) {
    return `cli.datastore.${functionName.slice('datastore_'.length)}`;
  }
  if (functionName.startsWith('machine_')) {
    return `cli.machine.${functionName.slice('machine_'.length)}`;
  }
  return `cli.${functionName}`;
}

class AuditService {
  private queue: AuditEvent[] = [];

  private hasToken(): boolean {
    try {
      return getSubscriptionTokenState().kind === 'ready';
    } catch {
      return false;
    }
  }

  /** Queue an audit event. Synchronous, never blocks. */
  record(event: AuditEvent): void {
    if (!this.hasToken()) return;
    this.queue.push(event);
  }

  /** Record a machine-level operation from localExecutorService context. */
  recordOperation(opts: {
    functionName: string;
    machineName: string;
    repoName?: string;
    success: boolean;
    exitCode: number;
    durationMs: number;
    error?: string;
  }): void {
    this.record({
      type: functionNameToEventType(opts.functionName),
      data: {
        functionName: opts.functionName,
        machineName: opts.machineName,
        repoName: opts.repoName,
        success: opts.success,
        exitCode: opts.exitCode,
        durationMs: opts.durationMs,
        cliVersion: VERSION,
        error: opts.error?.slice(0, 500),
      },
    });
  }

  /** Flush queued events to the account server. Timeout-bounded, swallows errors. */
  async flush(): Promise<void> {
    if (this.queue.length === 0) return;
    if (!this.hasToken()) {
      this.queue = [];
      return;
    }

    const events = this.queue.splice(0);
    try {
      const request = accountServerFetch(AUDIT_ENDPOINT, {
        method: 'POST',
        body: { events: events.map((e) => ({ type: e.type, data: e.data })) },
      });
      const timeout = new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('audit flush timeout')), FLUSH_TIMEOUT_MS)
      );
      await Promise.race([request, timeout]);
    } catch {
      // Fire-and-forget: audit failures must never block CLI operations
    }
  }
}

export const auditService = new AuditService();
