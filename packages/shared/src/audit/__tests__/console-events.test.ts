import { describe, expect, it } from 'vitest';
import type {
  ContractCommand,
  ContractOption,
  ContractPositional,
} from '../../cli-contract/types.js';
import {
  CONSOLE_AUDIT_TYPES,
  ConsoleAuditEventSchema,
  consoleTargetOf,
} from '../console-events.js';
import { AuditEventsRequestSchema } from '../event-schema.js';

const base = {
  v: 1,
  id: 'evt-1',
  ts: '2026-11-23T10:00:00.000Z',
  orgId: 'org-1',
  teamId: 'team-1',
  actor: { userId: 'u-1', kind: 'human' },
  target: { ref: 'mail' },
};

const DATA: Record<(typeof CONSOLE_AUDIT_TYPES)[number], Record<string, unknown>> = {
  'console.command.run': {
    requestId: 'req-1',
    pathKey: 'repo delete',
    severity: 'destructive',
    method: 'passkey',
  },
  'console.command.result': {
    requestId: 'req-1',
    exitCode: 0,
    success: true,
    jobId: 'j-1',
  },
  'console.config.saved': { configId: 'c-1', action: 'push', version: 3 },
  'console.policy.saved': { storeId: 's-1', configId: 'c-1', version: 2 },
  'console.stepup': { method: 'totp' },
  'console.reveal': { pathKey: 'repo secret list', method: 'password' },
  'console.ai.approval': { pathKey: 'repo up', decision: 'approved' },
  'console.feedback.sent': { feedbackId: 'f-1' },
};

function event(type: string, data: Record<string, unknown>): unknown {
  return { ...base, type, data };
}

describe('ConsoleAuditEventSchema', () => {
  it.each(CONSOLE_AUDIT_TYPES)('parses %s', (type) => {
    expect(ConsoleAuditEventSchema.safeParse(event(type, DATA[type])).success).toBe(true);
  });

  it('admits both reveal shapes and refuses a value or neither shape', () => {
    const editor = {
      configId: 'c-1',
      leafCount: 2,
      revealUntil: '2026-11-22T10:02:00.000Z',
      method: null,
    };
    const parse = (data: Record<string, unknown>) =>
      ConsoleAuditEventSchema.safeParse(event('console.reveal', data)).success;
    expect(parse(editor)).toBe(true);
    expect(parse({ ...editor, value: 's3cret' })).toBe(false);
    expect(parse({ ...DATA['console.reveal'], value: 's3cret' })).toBe(false);
    expect(parse({ ...editor, pathKey: 'repo up' })).toBe(false);
    expect(parse({ method: 'totp' })).toBe(false);
  });

  it('refuses an unknown type', () => {
    expect(ConsoleAuditEventSchema.safeParse(event('console.unknown', {})).success).toBe(false);
  });

  it('refuses a data field the type does not name', () => {
    const data = {
      ...DATA['console.command.run'],
      params: { password: 'hunter2' },
    };
    expect(ConsoleAuditEventSchema.safeParse(event('console.command.run', data)).success).toBe(
      false
    );
  });

  it('refuses a version other than 1 and a missing actor kind', () => {
    const run = event('console.stepup', DATA['console.stepup']) as Record<string, unknown>;
    expect(ConsoleAuditEventSchema.safeParse({ ...run, v: 2 }).success).toBe(false);
    expect(ConsoleAuditEventSchema.safeParse({ ...run, actor: { userId: 'u-1' } }).success).toBe(
      false
    );
  });

  it('accepts a null team for an org-level event', () => {
    const run = event('console.stepup', DATA['console.stepup']) as Record<string, unknown>;
    expect(ConsoleAuditEventSchema.safeParse({ ...run, teamId: null }).success).toBe(true);
  });
});

function positional(name: string): ContractPositional {
  return {
    name,
    kind: 'repo-ref',
    required: true,
    variadic: false,
    descriptionKey: null,
    label: '',
  };
}

function option(long: string, extra: Partial<ContractOption> = {}): ContractOption {
  return {
    flags: `--${long} <v>`,
    long,
    valueTaking: true,
    variadic: false,
    mandatory: false,
    defaultValue: null,
    tier: 'common',
    descriptionKey: null,
    label: '',
    ...extra,
  };
}

describe('consoleTargetOf', () => {
  const entry = {
    positionals: [positional('ref')],
    options: [
      option('machine', { kinds: ['machine'] }),
      option('token', { kinds: ['machine'], sensitive: true }),
      option('value'),
    ],
  } as unknown as Pick<ContractCommand, 'positionals' | 'options'>;

  it('keeps positionals and kinds-bearing options', () => {
    const target = consoleTargetOf(entry, {
      positionals: { ref: 'mail' },
      params: { machine: 'm1' },
    });
    expect(target).toEqual({ ref: 'mail', machine: 'm1' });
  });

  it('never keeps a sensitive option, even one that bears kinds', () => {
    const target = consoleTargetOf(entry, {
      positionals: { ref: 'mail' },
      params: { token: 's3cret', machine: 'm1' },
    });
    expect(JSON.stringify(target)).not.toContain('s3cret');
    expect(target).not.toHaveProperty('token');
  });

  it('drops an option without kinds and a param the contract does not know', () => {
    const target = consoleTargetOf(entry, {
      positionals: {},
      params: { value: 'hunter2', undeclared: 'x', machine: ['a', 'b'] },
    });
    expect(target).toEqual({ machine: ['a', 'b'] });
  });

  it('drops a non-string value', () => {
    const target = consoleTargetOf(entry, {
      positionals: { ref: 5 },
      params: { machine: true },
    });
    expect(target).toEqual({});
  });
});

describe('executor event requestId', () => {
  const data = {
    success: true,
    exitCode: 0,
    durationMs: 5,
    cliVersion: '0.0.0-dev',
    commandPath: 'repo up',
    destructive: false,
  };
  const key = '0d6f3a52-8b1e-4c7a-9f2d-5e4b3a2c1d0e';

  it('accepts a requestId and stays valid without one', () => {
    for (const extra of [{ requestId: 'req-1' }, {}]) {
      const parsed = AuditEventsRequestSchema.safeParse({
        events: [
          {
            type: 'cli.command',
            idempotencyKey: key,
            data: { ...data, ...extra },
          },
        ],
      });
      expect(parsed.success).toBe(true);
    }
  });

  it('refuses a malformed requestId', () => {
    const parsed = AuditEventsRequestSchema.safeParse({
      events: [
        {
          type: 'cli.command',
          idempotencyKey: key,
          data: { ...data, requestId: '../x' },
        },
      ],
    });
    expect(parsed.success).toBe(false);
  });
});
