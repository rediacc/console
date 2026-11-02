import { describe, expect, it } from 'vitest';
import { AuditEventsRequestSchema, functionNameToEventType } from '../event-schema.js';

const KEY = '0d6f3a52-8b1e-4c7a-9f2d-5e4b3a2c1d0e';

const outcome = { success: true, exitCode: 0, durationMs: 5, cliVersion: '0.0.0-dev' };

describe('AuditEventsRequestSchema', () => {
  it('accepts cli.command with a command path and no function or machine', () => {
    const parsed = AuditEventsRequestSchema.safeParse({
      events: [
        {
          type: 'cli.command',
          idempotencyKey: KEY,
          data: { ...outcome, commandPath: 'config show', destructive: false },
        },
      ],
    });
    expect(parsed.success).toBe(true);
  });

  it('refuses cli.command without the command path that identifies it', () => {
    const parsed = AuditEventsRequestSchema.safeParse({
      events: [
        { type: 'cli.command', idempotencyKey: KEY, data: { ...outcome, destructive: false } },
      ],
    });
    expect(parsed.success).toBe(false);
  });

  it('keeps commandPath and destructive on a function-mapped event rather than stripping them', () => {
    const parsed = AuditEventsRequestSchema.parse({
      events: [
        {
          type: 'cli.repo.up',
          idempotencyKey: KEY,
          data: {
            ...outcome,
            functionName: 'repository_up',
            machineName: 'prod-1',
            commandPath: 'repo up',
            destructive: true,
          },
        },
      ],
    });
    expect(parsed.events[0].data).toMatchObject({ commandPath: 'repo up', destructive: true });
  });

  it('refuses a null type, the shape the executor shipped before cli.command existed', () => {
    const parsed = AuditEventsRequestSchema.safeParse({
      events: [
        {
          type: null,
          idempotencyKey: KEY,
          data: { ...outcome, functionName: 'machine status', machineName: 'm' },
        },
      ],
    });
    expect(parsed.success).toBe(false);
  });
});

describe('functionNameToEventType', () => {
  it('never maps a function name to cli.command', () => {
    expect(functionNameToEventType('command')).toBeNull();
  });

  it('maps a renet function to its dotted type', () => {
    expect(functionNameToEventType('repository_up')).toBe('cli.repo.up');
  });
});
