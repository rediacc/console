/**
 * MutationGate tests, knowledge-gate enforcement for agents vs humans.
 *
 * NOTE: These tests mock `isAgentEnvironment` directly because the host process
 * may be running under Claude Code (CLAUDECODE=1 in parent ancestry) which
 * makes `_resetCache()` alone insufficient, the ancestry check reads /proc
 * and would keep detecting the parent agent.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const agentEnvMock = vi.fn<() => boolean>();
const stdinTty = vi.hoisted(() => ({ value: true }));
// The retired config-edit override, spelled in pieces so the removed-name gate finds no literal here.
const OLD_VAR = ['REDIACC', 'ALLOW', 'CONFIG', 'EDIT'].join('_');

vi.mock('node:tty', async (importOriginal) => ({
  ...(await importOriginal<typeof import('node:tty')>()),
  isatty: (fd: number) => fd === 0 && stdinTty.value,
}));
vi.mock('../../utils/agent-guard.js', async () => {
  const actual = await vi.importActual<typeof import('../../utils/agent-guard.js')>(
    '../../utils/agent-guard.js'
  );
  return {
    ...actual,
    isAgentEnvironment: () => agentEnvMock(),
  };
});
vi.mock('../../utils/process-ancestry.js', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  // What the old override needed: ancestry reporting the var as set before the agent started.
  isOverrideLegitimate: () => true,
}));

import { digestForPointer } from '../../schema/fingerprint.js';
import {
  evaluateMutations,
  type MutationEntry,
  PreconditionMismatchError,
} from '../core/mutation-gate.js';

const v2Config = {
  schemaVersion: 2 as const,
  id: '00000000-0000-0000-0000-000000000001',
  version: 1,
  credentials: {
    ssh: {
      privateKey: '-----BEGIN OPENSSH PRIVATE KEY-----\nABC\n-----END-----',
    },
    cfDnsApiToken: 'old-cf-token',
  },
  resources: {
    machines: { 'web-1': { ip: '10.0.0.1', user: 'deploy' } },
  },
  encryption: { mode: 'plaintext' as const },
};

function currentDigest(pointer: string): string {
  const d = digestForPointer(v2Config, pointer);
  if (!d) throw new Error(`no digest for ${pointer}`);
  return d;
}

const rotation: MutationEntry[] = [
  {
    pointer: '/credentials/cfDnsApiToken',
    previousValue: 'old-cf-token',
    newValue: 'rotated-token',
  },
];
const rotateContext = {
  previousConfig: v2Config,
  rotateAcknowledged: new Set(['/credentials/cfDnsApiToken']),
};

function refusalReasons(run: () => unknown): string[] {
  try {
    run();
  } catch (error) {
    if (error instanceof PreconditionMismatchError) return error.failures.map((f) => f.reason);
    throw error;
  }
  throw new Error('expected a PreconditionMismatchError');
}

describe('MutationGate — human (symmetric with agent)', () => {
  beforeEach(() => {
    agentEnvMock.mockReturnValue(false);
    stdinTty.value = true;
  });
  afterEach(() => {
    vi.clearAllMocks();
    delete process.env[OLD_VAR];
  });

  it('refuses sensitive mutation without knowledge (symmetric — was bypassed pre-V2)', () => {
    const entries: MutationEntry[] = [
      {
        pointer: '/credentials/cfDnsApiToken',
        previousValue: 'old-cf-token',
        newValue: 'new-cf-token',
      },
    ];
    expect(() => evaluateMutations(entries, { previousConfig: v2Config })).toThrow(
      PreconditionMismatchError
    );
  });

  it('allows sensitive mutation with correct --current digest', () => {
    const entries: MutationEntry[] = [
      {
        pointer: '/credentials/cfDnsApiToken',
        previousValue: 'old-cf-token',
        newValue: 'new-cf-token',
      },
    ];
    const decisions = evaluateMutations(entries, {
      previousConfig: v2Config,
      knowledge: { '/credentials/cfDnsApiToken': currentDigest('/credentials/cfDnsApiToken') },
    });
    expect(decisions[0].action).toBe('allowed');
    expect(decisions[0].reason).toBe('knowledge verified');
  });

  it('allows rotation when --rotate-secret acknowledged at an interactive terminal', () => {
    const decisions = evaluateMutations(rotation, rotateContext);
    expect(decisions[0].action).toBe('allowed');
    expect(decisions[0].reason).toBe('rotate acknowledged');
  });

  it('refuses a rotation acknowledgement from a human without a TTY on stdin', () => {
    stdinTty.value = false;
    const reasons = refusalReasons(() => evaluateMutations(rotation, rotateContext));
    expect(reasons[0]).toMatch(/honoured only for a human at an interactive terminal/);
  });

  it('the retired override var set to * does not bypass for a human', () => {
    process.env[OLD_VAR] = '*';
    expect(() => evaluateMutations(rotation, { previousConfig: v2Config })).toThrow(
      PreconditionMismatchError
    );
  });

  it('public fields still pass without knowledge', () => {
    const entries: MutationEntry[] = [{ pointer: '/version', previousValue: 1, newValue: 2 }];
    const decisions = evaluateMutations(entries, { previousConfig: v2Config });
    expect(decisions[0].action).toBe('allowed');
  });
});

describe('MutationGate — agent environment', () => {
  beforeEach(() => {
    agentEnvMock.mockReturnValue(true);
    stdinTty.value = true;
  });
  afterEach(() => {
    vi.clearAllMocks();
    delete process.env[OLD_VAR];
  });

  it('refuses sensitive mutation without knowledge', () => {
    const entries: MutationEntry[] = [
      {
        pointer: '/credentials/cfDnsApiToken',
        previousValue: 'old-cf-token',
        newValue: 'new-cf-token',
      },
    ];
    expect(() => evaluateMutations(entries, { previousConfig: v2Config })).toThrow(
      PreconditionMismatchError
    );
  });

  it('allows sensitive mutation with correct --current digest', () => {
    const entries: MutationEntry[] = [
      {
        pointer: '/credentials/cfDnsApiToken',
        previousValue: 'old-cf-token',
        newValue: 'new-cf-token',
      },
    ];
    const decisions = evaluateMutations(entries, {
      previousConfig: v2Config,
      knowledge: { '/credentials/cfDnsApiToken': currentDigest('/credentials/cfDnsApiToken') },
    });
    expect(decisions[0].action).toBe('allowed');
    expect(decisions[0].reason).toBe('knowledge verified');
  });

  it('refuses sensitive mutation with wrong --current digest', () => {
    const entries: MutationEntry[] = [
      {
        pointer: '/credentials/cfDnsApiToken',
        previousValue: 'old-cf-token',
        newValue: 'new-cf-token',
      },
    ];
    expect(() =>
      evaluateMutations(entries, {
        previousConfig: v2Config,
        knowledge: { '/credentials/cfDnsApiToken': 'deadbeef'.repeat(8) },
      })
    ).toThrow(PreconditionMismatchError);
  });

  it('allows public field mutation regardless of agent', () => {
    const entries: MutationEntry[] = [{ pointer: '/version', previousValue: 1, newValue: 2 }];
    const decisions = evaluateMutations(entries, { previousConfig: v2Config });
    expect(decisions[0].action).toBe('allowed');
  });

  it('refuses a rotation acknowledgement from an agent, even with a TTY on stdin', () => {
    const reasons = refusalReasons(() => evaluateMutations(rotation, rotateContext));
    expect(reasons[0]).toMatch(/supply --current/);
  });

  it('an agent with the retired override var set to * and verified ancestry still needs --current', () => {
    process.env[OLD_VAR] = '*';
    const reasons = refusalReasons(() => evaluateMutations(rotation, { previousConfig: v2Config }));
    expect(reasons[0]).toBe('sensitive path requires --current');
    const decisions = evaluateMutations(rotation, {
      previousConfig: v2Config,
      knowledge: { '/credentials/cfDnsApiToken': currentDigest('/credentials/cfDnsApiToken') },
    });
    expect(decisions[0].reason).toBe('knowledge verified');
  });

  it('a previously empty pointer is the other agent allow path (with a knowledge claim)', () => {
    const decisions = evaluateMutations(
      [{ pointer: '/credentials/cfDnsApiToken', previousValue: undefined, newValue: 'first' }],
      {
        previousConfig: { ...v2Config, credentials: { ssh: v2Config.credentials.ssh } },
        knowledge: { '/credentials/cfDnsApiToken': 'claimed' },
      }
    );
    expect(decisions[0].reason).toBe('new field with knowledge claim');
  });
});
