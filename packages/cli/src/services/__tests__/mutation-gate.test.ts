/**
 * MutationGate tests — knowledge-gate enforcement for agents vs humans.
 *
 * NOTE: These tests mock `isAgentEnvironment` directly because the host process
 * may be running under Claude Code (CLAUDECODE=1 in parent ancestry) which
 * makes `_resetCache()` alone insufficient — the ancestry check reads /proc
 * and would keep detecting the parent agent.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const agentEnvMock = vi.fn<() => boolean>();
const overrideScopeMock = vi.fn<() => string | null>();

vi.mock('../../utils/agent-guard.js', async () => {
  const actual = await vi.importActual<typeof import('../../utils/agent-guard.js')>(
    '../../utils/agent-guard.js'
  );
  return {
    ...actual,
    isAgentEnvironment: () => agentEnvMock(),
    configEditOverrideScope: () => overrideScopeMock(),
  };
});

import {
  evaluateMutations,
  PreconditionMismatchError,
  type MutationEntry,
} from '../mutation-gate.js';
import { digestForPointer } from '../../schema/walker.js';

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

describe('MutationGate — human TTY', () => {
  beforeEach(() => {
    agentEnvMock.mockReturnValue(false);
    overrideScopeMock.mockReturnValue(null);
  });
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('allows any mutation without knowledge claim', () => {
    const entries: MutationEntry[] = [
      {
        pointer: '/credentials/cfDnsApiToken',
        previousValue: 'old-cf-token',
        newValue: 'new-cf-token',
      },
    ];
    const decisions = evaluateMutations(entries, { previousConfig: v2Config });
    expect(decisions[0].action).toBe('allowed');
    expect(decisions[0].reason).toBe('human tty');
  });
});

describe('MutationGate — agent environment', () => {
  beforeEach(() => {
    agentEnvMock.mockReturnValue(true);
    overrideScopeMock.mockReturnValue(null);
  });
  afterEach(() => {
    vi.clearAllMocks();
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

  it('allows rotation with acknowledgement', () => {
    const entries: MutationEntry[] = [
      {
        pointer: '/credentials/cfDnsApiToken',
        previousValue: 'old-cf-token',
        newValue: 'rotated-token',
      },
    ];
    const decisions = evaluateMutations(entries, {
      previousConfig: v2Config,
      rotateAcknowledged: new Set(['/credentials/cfDnsApiToken']),
    });
    expect(decisions[0].action).toBe('allowed');
    expect(decisions[0].reason).toBe('rotate acknowledged');
  });

  it('refuses rotation without override env when ancestry not legit', () => {
    // Without REDIACC_ALLOW_CONFIG_EDIT set by a human parent, scope returns null.
    const entries: MutationEntry[] = [
      {
        pointer: '/credentials/cfDnsApiToken',
        previousValue: 'old-cf-token',
        newValue: 'new-token',
      },
    ];
    expect(() => evaluateMutations(entries, { previousConfig: v2Config })).toThrow(
      PreconditionMismatchError
    );
  });
});
