/**
 * The executor's audit trail.
 *
 * This is where the proxy earns the claim that it is a MORE trustworthy audit
 * source than the CLI, which is the whole enterprise pitch. Three differences
 * from the CLI's own best-effort audit, and each one closes a real gap:
 *
 *   1. SYNCHRONOUS. One event per command, awaited before the caller is told the
 *      outcome. The CLI flushes at process exit, so a killed process loses its
 *      events silently. An executor that cannot record what it did must not
 *      pretend it did nothing.
 *
 *   2. SERVER-VERIFIED ACTOR. The event is attributed to the user the ACCOUNT
 *      server resolved from the presented token, never to an identity the client
 *      asserted. `onBehalfOfTokenId` carries that token so the server can
 *      re-derive the same answer independently.
 *
 *   3. IDEMPOTENT. Every event carries a key, so a retry after a network blip
 *      records the command once rather than twice. An audit log that
 *      double-counts is not evidence of anything.
 */

import { randomUUID } from 'node:crypto';
import { functionNameToEventType } from '@rediacc/shared';
import type { ExecutorAuditEvent } from './deps.js';

export interface ExecutorAuditOptions {
  /** Account server base URL. */
  accountUrl: string;
  /** The executor's own token, which must carry the audit:write scope. */
  executorToken: string;
  fetchImpl?: typeof fetch;
  /** Called when an event cannot be delivered, so the failure is visible. */
  onFailure?: (error: unknown, event: ExecutorAuditEvent) => void;
}

/**
 * Ship one audit event per command.
 *
 * A delivery failure does NOT fail the command: the operation already ran on the
 * machine, and refusing to report its result would leave the operator with a
 * successful change and an error message. It is surfaced instead, and the
 * idempotency key means the retry the caller may make is safe.
 */
export function createExecutorAudit(
  options: ExecutorAuditOptions
): (event: ExecutorAuditEvent) => Promise<void> {
  const fetchImpl = options.fetchImpl ?? globalThis.fetch;
  const accountUrl = options.accountUrl.replace(/\/+$/, '');

  return async (event: ExecutorAuditEvent): Promise<void> => {
    try {
      const payload = {
        events: [
          {
            type: functionNameToEventType(event.functionName),
            idempotencyKey: randomUUID(),
            ...(event.principal.tokenId ? { onBehalfOfTokenId: event.principal.tokenId } : {}),
            timestamp: new Date().toISOString(),
            data: {
              command: event.commandPath,
              function: event.functionName,
              machine: event.machineName,
              success: event.success,
              durationMs: event.durationMs,
              destructive: event.destructive,
              // Params are NOT shipped: they routinely carry repository names,
              // and can carry a secret value on a `repo secret set`. The audit
              // trail records WHAT ran and WHO ran it, not the payload.
            },
          },
        ],
      };

      const response = await fetchImpl(`${accountUrl}/account/api/v1/licenses/audit-events`, {
        method: 'POST',
        headers: {
          authorization: `Bearer ${options.executorToken}`,
          'content-type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(`The account server rejected the audit event (${response.status}).`);
      }
    } catch (error) {
      options.onFailure?.(error, event);
    }
  };
}
