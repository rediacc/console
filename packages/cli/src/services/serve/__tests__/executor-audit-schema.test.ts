/**
 * The executor's audit event must validate against the account server's schema.
 *
 * Live on bench 2026-10-24, every event `rdc serve` posted was rejected 400 and
 * swallowed by onFailure: `type` was null for any command whose function mapped
 * to no event type (and for every command that reached no function at all, such
 * as `machine status`), and `data` carried keys the shared baseData does not
 * know while missing the ones it requires. The e2e suite ran against a stub
 * account, so nothing parsed the body. This test parses the real wire payload
 * with the same AuditEventsRequestSchema the account route uses.
 */

import { AuditEventsRequestSchema } from '@rediacc/shared';
import { describe, expect, it } from 'vitest';
import { createExecutorAudit } from '../audit.js';
import type { ExecutorAuditEvent } from '../deps.js';

const TOKEN_ID = '3f2b8c1e-5d4a-4e6b-9c7d-2a1b0e9f8d7c';

async function shipped(event: ExecutorAuditEvent): Promise<unknown> {
  const bodies: unknown[] = [];
  const failures: unknown[] = [];
  const audit = createExecutorAudit({
    accountUrl: 'https://account.test',
    executorToken: 'rdt_executor',
    fetchImpl: (_input, init) => {
      bodies.push(JSON.parse(String(init?.body)));
      return Promise.resolve(new Response('{"accepted":1}', { status: 200 }));
    },
    onFailure: (error) => failures.push(error),
  });
  await audit(event);
  expect(failures).toEqual([]);
  expect(bodies).toHaveLength(1);
  return bodies[0];
}

function event(overrides: Partial<ExecutorAuditEvent>): ExecutorAuditEvent {
  return {
    principal: {
      orgId: 'org-1',
      teamId: null,
      userId: 'user-1',
      userEmail: 'owner@example.com',
      orgRole: 'member',
      tokenId: TOKEN_ID,
    },
    commandPath: 'repo up',
    params: { secret: 'never-shipped' },
    success: true,
    exitCode: 0,
    durationMs: 42,
    destructive: false,
    ...overrides,
  };
}

function parse(body: unknown) {
  const parsed = AuditEventsRequestSchema.safeParse(body);
  if (!parsed.success) throw new Error(`schema rejected the payload: ${parsed.error.message}`);
  return parsed.data.events[0];
}

describe('executor audit payload against AuditEventsRequestSchema', () => {
  it('a command that reached no renet function records as cli.command, keyed by its path', async () => {
    const body = await shipped(event({ commandPath: 'machine status', machineName: 'prod-1' }));
    const parsed = parse(body);
    expect(parsed.type).toBe('cli.command');
    expect(parsed.onBehalfOfTokenId).toBe(TOKEN_ID);
    expect(parsed.data).toMatchObject({
      commandPath: 'machine status',
      machineName: 'prod-1',
      success: true,
      exitCode: 0,
      destructive: false,
    });
    expect(JSON.stringify(body)).not.toContain('never-shipped');
  });

  it('a command that resolved no machine still records, as cli.command', async () => {
    const parsed = parse(await shipped(event({ commandPath: 'config show' })));
    expect(parsed.type).toBe('cli.command');
    expect(parsed.data).not.toHaveProperty('machineName');
  });

  it('a function that maps to no event type records as cli.command with that function', async () => {
    const parsed = parse(
      await shipped(
        event({ commandPath: 'license status', functionName: 'license_status', machineName: 'm' })
      )
    );
    expect(parsed.type).toBe('cli.command');
    expect(parsed.data).toMatchObject({ functionName: 'license_status' });
  });

  it('a mapped function records under its own type, keeping the command path', async () => {
    const parsed = parse(
      await shipped(
        event({
          commandPath: 'repo up',
          functionName: 'repository_up',
          machineName: 'prod-1',
          success: false,
          exitCode: 3,
          destructive: true,
        })
      )
    );
    expect(parsed.type).toBe('cli.repo.up');
    expect(parsed.data).toMatchObject({
      functionName: 'repository_up',
      machineName: 'prod-1',
      success: false,
      exitCode: 3,
      commandPath: 'repo up',
      destructive: true,
    });
    expect(typeof parsed.data.cliVersion).toBe('string');
  });
});
