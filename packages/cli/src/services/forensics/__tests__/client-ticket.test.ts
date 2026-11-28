/**
 * The forensics reads on the executor (PLAN-forensics-investigation D8, FI11): a served dispatch
 * without a ticket refuses before any call, a ticket is redeemed once and its agent read token
 * reused by every later read of the dispatch, and a scope the ticket does not cover refuses.
 * On a laptop (no dispatch) the reads open their own investigation as before.
 */
import { describe, expect, it } from 'vitest';
import { CliExitError } from '../../../utils/cli-exit-error.js';
import {
  ForensicsClient,
  type ForensicsFetch,
  ForensicsTicket,
  withForensicsTicket,
} from '../client.js';

const REPO_A = '11111111-1111-4111-8111-111111111111';
const REPO_B = '22222222-2222-4222-8222-222222222222';
const AGENT_ID = 'agent-body.agent-sig';

interface Call {
  path: string;
  method?: string;
  body?: unknown;
}

function recorder(answers: (call: Call) => unknown): { calls: Call[]; fetchFn: ForensicsFetch } {
  const calls: Call[] = [];
  const fetchFn = ((path: string, options?: { method?: string; body?: unknown }) => {
    const call = { path, method: options?.method, body: options?.body };
    calls.push(call);
    try {
      return Promise.resolve(answers(call));
    } catch (error) {
      return Promise.reject(error);
    }
  }) as ForensicsFetch;
  return { calls, fetchFn };
}

const agentAnswer = (call: Call) =>
  call.path.endsWith('/forensics/agent-investigations')
    ? { id: AGENT_ID, scopeKind: 'repo', scopeRef: REPO_A, from: 'f', to: 't' }
    : { incidents: [] };

describe('ForensicsClient with a read ticket', () => {
  it('refuses a served dispatch that carries no ticket, before any call', async () => {
    const { calls, fetchFn } = recorder(agentAnswer);
    const client = new ForensicsClient(fetchFn);
    await expect(
      withForensicsTicket(null, () => client.openInvestigation({ kind: 'repo', ref: REPO_A }))
    ).rejects.toBeInstanceOf(CliExitError);
    expect(calls).toEqual([]);
  });

  it('redeems the ticket once and reuses the agent read token', async () => {
    const { calls, fetchFn } = recorder(agentAnswer);
    const client = new ForensicsClient(fetchFn);
    const ticket = new ForensicsTicket('the-ticket');
    const ids = await withForensicsTicket(ticket, async () => [
      await client.openInvestigation({ kind: 'repo', ref: REPO_A }),
      await client.openInvestigation({ kind: 'repo', ref: REPO_A }),
    ]);
    expect(ids).toEqual([AGENT_ID, AGENT_ID]);
    const redemptions = calls.filter((c) => c.path.endsWith('/agent-investigations'));
    expect(redemptions).toEqual([
      {
        path: '/account/api/v1/console/forensics/agent-investigations',
        method: 'POST',
        body: { ticket: 'the-ticket', scopeKind: 'repo', scopeRef: REPO_A },
      },
    ]);
  });

  it('refuses a scope the redeemed ticket does not cover', async () => {
    const { fetchFn } = recorder(agentAnswer);
    const client = new ForensicsClient(fetchFn);
    const ticket = new ForensicsTicket('the-ticket');
    await withForensicsTicket(ticket, () =>
      client.openInvestigation({ kind: 'repo', ref: REPO_A })
    );
    await expect(
      withForensicsTicket(ticket, () => client.openInvestigation({ kind: 'repo', ref: REPO_B }))
    ).rejects.toBeInstanceOf(CliExitError);
  });

  it('lists incidents through the agent investigation', async () => {
    const { calls, fetchFn } = recorder(agentAnswer);
    const client = new ForensicsClient(fetchFn);
    await withForensicsTicket(new ForensicsTicket('the-ticket'), () => client.listIncidents());
    expect(calls.map((c) => c.path)).toEqual([
      '/account/api/v1/console/forensics/agent-investigations',
      `/account/api/v1/console/forensics/investigations/${encodeURIComponent(AGENT_ID)}/incidents`,
    ]);
  });

  it('leaves a refused redemption retryable', async () => {
    // The first redemption is refused; the retry with the same ticket goes through.
    let redemptions = 0;
    const { calls, fetchFn } = recorder((call) => {
      if (call.path.endsWith('/agent-investigations') && redemptions++ === 0) {
        throw Object.assign(new Error('The ticket covers another scope'), {
          status: 403,
          code: 'FORENSICS_TICKET_REFUSED',
        });
      }
      return agentAnswer(call);
    });
    const client = new ForensicsClient(fetchFn);
    const ticket = new ForensicsTicket('the-ticket');
    const scope = { kind: 'repo' as const, ref: REPO_A };
    await expect(
      withForensicsTicket(ticket, () => client.openInvestigation(scope))
    ).rejects.toBeInstanceOf(CliExitError);
    await expect(withForensicsTicket(ticket, () => client.openInvestigation(scope))).resolves.toBe(
      AGENT_ID
    );
    expect(calls).toHaveLength(2);
  });

  it('control: on a laptop the read opens its own investigation', async () => {
    const { calls, fetchFn } = recorder(() => ({ id: 'inv-1' }));
    const client = new ForensicsClient(fetchFn);
    await expect(client.openInvestigation({ kind: 'repo', ref: REPO_A })).resolves.toBe('inv-1');
    expect(calls.map((c) => c.path)).toEqual(['/account/api/v1/console/forensics/investigations']);
  });
});
