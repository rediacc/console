import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// i18n stub
vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

// configService — capture addRepository payload to assert isolation
const mockGetRepository = vi.hoisted(() => vi.fn());
const mockAddRepository = vi.hoisted(() => vi.fn());
const mockAllocateNetworkId = vi.hoisted(() => vi.fn().mockResolvedValue(99999));
const mockRemoveRepository = vi.hoisted(() => vi.fn());

vi.mock('../../services/config-resources.js', () => ({
  configService: {
    getRepository: mockGetRepository,
    addRepository: mockAddRepository,
    allocateNetworkId: mockAllocateNetworkId,
    removeRepository: mockRemoveRepository,
  },
}));

// Renet executor — return success so handleForkAction reaches success path
const mockExecute = vi.hoisted(() =>
  vi.fn().mockResolvedValue({ success: true, allSteps: [], steps: [] })
);
vi.mock('../../services/local-executor.js', () => ({
  localExecutorService: { execute: mockExecute },
}));

// Repo-key deployment — no-op
vi.mock('../../services/repo-key-deployment.js', () => ({
  deployRepoKeyIfNeeded: vi.fn().mockResolvedValue(undefined),
}));

// Post-up tasks — no-op
vi.mock('../repo-batch-utils.js', () => ({
  postRepoUpTasks: vi.fn().mockResolvedValue(undefined),
}));

// SSH keypair — deterministic for assertion
vi.mock('../../utils/ssh-keygen.js', () => ({
  generateSSHKeyPair: () => ({ privateKey: 'mock-priv', publicKey: 'mock-pub' }),
}));

// Output / timeline / errors / local-execution-failure — silence
vi.mock('../../services/output.js', () => ({
  outputService: {
    info: vi.fn(),
    success: vi.fn(),
    warn: vi.fn(),
    print: vi.fn(),
    setTimelineRendered: vi.fn(),
  },
}));
vi.mock('../../utils/timeline.js', () => ({
  formatStepDuration: () => '0s',
  getActiveLabel: (s: string) => s,
  getDoneLabel: (s: string) => s,
}));
vi.mock('../../utils/local-execution-failures.js', () => ({
  renderLocalExecutionFailure: vi.fn(),
}));
vi.mock('../../utils/errors.js', async () => {
  const actual =
    await vi.importActual<typeof import('../../utils/errors.js')>('../../utils/errors.js');
  return {
    ...actual,
    handleError: (e: unknown) => {
      throw e;
    },
  };
});

const { handleForkAction } = await import('../repo-fork.js');

const PARENT = {
  repositoryGuid: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  tag: 'latest',
  credential: 'luks-pass',
  networkId: 100,
  sshPrivateKey: 'parent-ssh-priv',
  sshPublicKey: 'parent-ssh-pub',
  // The whole point of the test: parent has live secrets.
  secrets: {
    STRIPE_LIVE_KEY: { mode: 'env' as const, value: 'sk_live_REAL' },
    DKIM_PRIVATE: { mode: 'file' as const, value: '-----BEGIN KEY-----' },
  },
};

describe('repo fork — hard-isolate of secrets', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Parent lookup returns PARENT; fork-key lookup returns undefined (not yet registered)
    mockGetRepository.mockImplementation((ref: string) =>
      Promise.resolve(ref === 'app' ? PARENT : undefined)
    );
    mockExecute.mockResolvedValue({ success: true, allSteps: [], steps: [] });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('runtime: forking a parent with secrets produces a fork registration with NO secrets', async () => {
    await handleForkAction('app', 'staging', {
      machine: 'hostinger',
    });

    expect(mockAddRepository).toHaveBeenCalledOnce();
    const [forkKey, forkConfig] = mockAddRepository.mock.calls[0];
    expect(forkKey).toBe('app:staging');
    // The load-bearing assertion: secrets MUST NOT propagate
    expect(forkConfig.secrets).toBeUndefined();
    // Sanity: other fields propagate as the existing fork model expects
    expect(forkConfig.credential).toBe('luks-pass'); // shared (LUKS image is reflinked)
    expect(forkConfig.parentGuid).toBe(PARENT.repositoryGuid);
    expect(forkConfig.grandGuid).toBe(PARENT.repositoryGuid);
    // Fork mints fresh SSH keypair, never copies parent's
    expect(forkConfig.sshPrivateKey).toBe('mock-priv');
    expect(forkConfig.sshPrivateKey).not.toBe(PARENT.sshPrivateKey);
  });

  it('static: repo-fork.ts source must not reference parentConfig.secrets', () => {
    // Lightweight guard against future foot-guns. If someone adds
    // `secrets: parentConfig.secrets` to the addRepository call, this fires
    // and forces an explicit conversation about the threat model.
    const src = readFileSync(resolve(__dirname, '..', 'repo-fork.ts'), 'utf-8');
    expect(src).not.toMatch(/parentConfig\.secrets/);
  });
});
