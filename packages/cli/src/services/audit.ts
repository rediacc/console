/**
 * CLI Audit Service
 *
 * Fire-and-forget audit event logging for machine-level CLI operations.
 * Events are queued in memory during command execution and flushed
 * to the account server in a single batch on process exit.
 *
 * Only active when a subscription token is available (cloud adapter).
 * Local adapter users (no token) get silent no-ops.
 *
 * Event types are validated against the shared discriminated-union
 * schema at packages/shared/src/audit/event-schema.ts. Unrecognized
 * function names are silently dropped — they would fail server-side
 * validation anyway, and dropping locally keeps the queue clean.
 */

import {
  type AuditEvent,
  type AuditEventType,
  AuditEventSchema,
  functionNameToEventType,
} from '@rediacc/shared';
import { getSubscriptionTokenState } from './subscription-auth.js';
import { accountServerFetch } from './account-client.js';
import { VERSION } from '../version.js';

export type { AuditEvent, AuditEventType };
export { functionNameToEventType };

const FLUSH_TIMEOUT_MS = 5_000;
const AUDIT_ENDPOINT = '/account/api/v1/licenses/audit-events';

class AuditService {
  private queue: AuditEvent[] = [];

  private hasToken(): boolean {
    try {
      return getSubscriptionTokenState().kind === 'ready';
    } catch {
      return false;
    }
  }

  /**
   * Queue an audit event. Synchronous, never blocks.
   * Event is validated against the shared schema; failures drop silently
   * (an unrecognized type would be rejected by the server anyway).
   */
  record(event: AuditEvent): void {
    if (!this.hasToken()) return;
    const parsed = AuditEventSchema.safeParse(event);
    if (!parsed.success) return;
    this.queue.push(parsed.data);
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
    filesTransferred?: number;
    bytesTransferred?: number;
    sessionDurationMs?: number;
  }): void {
    const type = functionNameToEventType(opts.functionName);
    if (!type) return;

    const baseData = {
      functionName: opts.functionName,
      machineName: opts.machineName,
      repoName: opts.repoName,
      success: opts.success,
      exitCode: opts.exitCode,
      durationMs: opts.durationMs,
      cliVersion: VERSION,
      error: opts.error?.slice(0, 500),
    };

    let event: AuditEvent;
    if (type === 'cli.sync.upload' || type === 'cli.sync.download') {
      event = {
        type,
        data: {
          ...baseData,
          filesTransferred: opts.filesTransferred,
          bytesTransferred: opts.bytesTransferred,
        },
      };
    } else if (type === 'cli.term.session') {
      event = {
        type,
        data: {
          ...baseData,
          sessionDurationMs: opts.sessionDurationMs,
        },
      };
    } else {
      event = { type, data: baseData };
    }

    this.record(event);
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
