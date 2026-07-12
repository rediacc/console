/**
 * CLI Audit Service
 *
 * Fire-and-forget audit event logging for machine-level CLI operations.
 * Events are queued in memory during command execution and flushed
 * to the account server in a single batch on process exit.
 *
 * Only active when a subscription token is available. Users without a
 * token get silent no-ops.
 *
 * Event types are validated against the shared discriminated-union
 * schema at packages/shared/src/audit/event-schema.ts. Unrecognized
 * function names are silently dropped — they would fail server-side
 * validation anyway, and dropping locally keeps the queue clean.
 */

import { randomUUID } from 'node:crypto';
import { type AuditEvent, AuditEventSchema, functionNameToEventType } from '@rediacc/shared';
import { VERSION } from '../../version.js';
import { accountServerFetch } from '../account/account-client.js';
import { getSubscriptionTokenState } from '../account/subscription-auth.js';

export { functionNameToEventType };

const FLUSH_TIMEOUT_MS = 5_000;
const AUDIT_ENDPOINT = '/account/api/v1/licenses/audit-events';

type DistributiveOmit<T, K extends keyof T> = T extends unknown ? Omit<T, K> : never;

/**
 * An event as callers supply it. The wire envelope's `idempotencyKey` is minted
 * by record(), never passed in, so no caller can reuse a key and suppress its
 * own event server-side.
 */
export type AuditEventDraft = DistributiveOmit<AuditEvent, 'idempotencyKey'>;

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
   * Stamps the idempotency key the server dedups on, then validates against the
   * shared schema; failures drop silently (an unrecognized type would be
   * rejected by the server anyway).
   */
  record(event: AuditEventDraft): void {
    if (!this.hasToken()) return;
    const parsed = AuditEventSchema.safeParse({ ...event, idempotencyKey: randomUUID() });
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

    let event: AuditEventDraft;
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

  /**
   * Flush queued events to the account server. Timeout-bounded, swallows errors.
   *
   * A failed attempt is retried exactly once. Every event carries an idempotency
   * key the server dedups on, so a retry can only ever store what the first
   * attempt missed — it can never double-count. The retry is bounded to one
   * extra attempt because this runs at process exit: a losing network must not
   * hold the command open indefinitely.
   */
  async flush(): Promise<void> {
    if (this.queue.length === 0) return;
    if (!this.hasToken()) {
      this.queue = [];
      return;
    }

    const events = this.queue.splice(0);
    if (!(await this.send(events))) {
      await this.send(events);
    }
  }

  /** POST one batch. Resolves true when the server accepted it. */
  private async send(events: AuditEvent[]): Promise<boolean> {
    let timer: NodeJS.Timeout | undefined;
    try {
      const request = accountServerFetch(AUDIT_ENDPOINT, {
        method: 'POST',
        body: {
          events: events.map((e) => ({
            type: e.type,
            data: e.data,
            idempotencyKey: e.idempotencyKey,
            ...(e.onBehalfOfTokenId ? { onBehalfOfTokenId: e.onBehalfOfTokenId } : {}),
          })),
        },
      });
      const timeout = new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error('audit flush timeout')), FLUSH_TIMEOUT_MS);
        // unref: a pending flush timeout must never hold the event loop open
        // after the command has finished (it added ~5s to every wall time).
        timer.unref();
      });
      await Promise.race([request, timeout]);
      return true;
    } catch {
      // Fire-and-forget: audit failures must never block CLI operations
      return false;
    } finally {
      if (timer !== undefined) clearTimeout(timer);
    }
  }
}

export const auditService = new AuditService();
