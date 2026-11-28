/**
 * The executor's audit event carries the repository identity of the call it
 * observed: `repoName` from the call's `repository` param, and for a create or
 * a fork the GUID of the image the call made. `executor_orphans` reads both out
 * of the stored event data, so an orphaned image (named on the machine only by
 * its GUID) is traced back to the executor event that made it (finding
 * #26ed959e). Every payload is parsed with the account route's own schema.
 */

import { AuditEventsRequestSchema } from '@rediacc/shared';
import { describe, expect, it } from 'vitest';
import { createExecutorAudit, repositoryIdentity } from '../audit.js';
import type { ExecutorAuditEvent } from '../deps.js';

const GUID = 'E9304FFC-0C96-47F2-A2FB-6076C1DF6F52';

async function shippedData(event: Partial<ExecutorAuditEvent>): Promise<Record<string, unknown>> {
  const bodies: unknown[] = [];
  const audit = createExecutorAudit({
    accountUrl: 'https://account.test',
    executorToken: 'rdt_executor',
    fetchImpl: (_input, init) => {
      bodies.push(JSON.parse(String(init?.body)));
      return Promise.resolve(new Response('{"accepted":1}', { status: 200 }));
    },
  });
  await audit({
    principal: {
      orgId: 'org-1',
      teamId: null,
      userId: 'user-1',
      userEmail: 'owner@example.com',
      orgRole: 'member',
    },
    commandPath: 'repo create',
    params: { secret: 'never-shipped' },
    success: true,
    exitCode: 0,
    durationMs: 1,
    destructive: false,
    ...event,
  });
  const parsed = AuditEventsRequestSchema.safeParse(bodies[0]);
  if (!parsed.success) throw new Error(`schema rejected the payload: ${parsed.error.message}`);
  return parsed.data.events[0].data as Record<string, unknown>;
}

describe('executor audit repository identity', () => {
  it('a repository_create event carries the repo name and the GUID the call made', async () => {
    const data = await shippedData({
      functionName: 'repository_create',
      machineName: 'm1',
      functionParams: { repository: 'alpha', size: '1G', guid: GUID },
    });
    expect(data).toMatchObject({ repoName: 'alpha', guid: GUID.toLowerCase() });
    expect(JSON.stringify(data)).not.toContain('1G');
  });

  it('a repository_fork event carries the GUID of the fork (its tag param), not the parent', async () => {
    const data = await shippedData({
      commandPath: 'repo fork',
      functionName: 'repository_fork',
      machineName: 'm1',
      functionParams: { repository: 'alpha', tag: GUID, network_id: 2816 },
    });
    expect(data).toMatchObject({ repoName: 'alpha', guid: GUID.toLowerCase() });
  });

  it('another function carries the repo name and no GUID (control)', async () => {
    const data = await shippedData({
      commandPath: 'repo up',
      functionName: 'repository_up',
      machineName: 'm1',
      functionParams: { repository: 'alpha', guid: GUID },
    });
    expect(data.repoName).toBe('alpha');
    expect(data).not.toHaveProperty('guid');
  });

  it('a command with no observed params carries neither (control)', async () => {
    const data = await shippedData({ functionName: 'repository_create', machineName: 'm1' });
    expect(data).not.toHaveProperty('repoName');
    expect(data).not.toHaveProperty('guid');
  });
});

describe('repositoryIdentity', () => {
  it('drops a value the audit schema would refuse, keeping the event valid', () => {
    expect(
      repositoryIdentity('repository_create', { repository: 'x'.repeat(201), guid: 'not-a-guid' })
    ).toEqual({});
  });
});
