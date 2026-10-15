import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Mock i18n
vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) => {
    if (key === 'errors.agent.machineGuard' && params?.machine) {
      return `Cannot access machine "${params.machine}" directly in agent mode.`;
    }
    if (key === 'errors.agent.createGuard' && params?.name) {
      return `Cannot create repository "${params.name}" in agent mode.`;
    }
    return key;
  },
}));

// Mock process-ancestry module
const mockIsAgentByAncestry = vi.hoisted(() => vi.fn(() => false));
const mockIsOverrideLegitimate = vi.hoisted(() => vi.fn((_overrideVar?: string) => true));
const mockIsAncestryAvailable = vi.hoisted(() => vi.fn(() => true));
const mockResetAncestryCache = vi.hoisted(() => vi.fn());

vi.mock('../process-ancestry.js', () => ({
  isAgentByAncestry: mockIsAgentByAncestry,
  isOverrideLegitimate: mockIsOverrideLegitimate,
  isAncestryVerificationAvailable: mockIsAncestryAvailable,
  _resetAncestryCache: mockResetAncestryCache,
  OVERRIDE_VAR_GRAND: 'REDIACC_ALLOW_GRAND_REPO',
  OVERRIDE_VAR_CONFIG_EDIT: 'REDIACC_ALLOW_CONFIG_EDIT',
}));

// The active config the ops VM predicate (ops-vm.ts) reads machine addresses from.
// `ops-worker` and `ops-ds-host` sit on the ops fleet's network; `prod-1` does not;
// `ops-worker-prod` carries an ops-looking NAME on a production address; `edge-112`
// sits one /24 away; `ops-hostname` is a hostname that merely starts with the prefix.
const OPS_CONFIG = vi.hoisted(() => ({
  resources: {
    machines: {
      'prod-1': { ip: '10.0.0.5', user: 'root' },
      'ops-worker': { ip: '192.168.111.11', user: 'muhammed' },
      'ops-ds-host': { ip: '192.168.111.12', user: 'muhammed' },
      'ops-worker-prod': { ip: '203.0.113.7', user: 'root' },
      'edge-112': { ip: '192.168.112.11', user: 'muhammed' },
      'ops-hostname': { ip: '192.168.111.11.example.com', user: 'root' },
    },
    datastores: {
      'ops-pool': { backend: { kind: 'local', machine: 'ops-ds-host', path: '/mnt/pool' } },
      'prod-pool': { backend: { kind: 'local', machine: 'prod-1', path: '/mnt/pool' } },
      'ops-ceph': {
        cluster: 'ops-k8s',
        backend: { kind: 'local', machine: 'ops-worker', path: '/x' },
      },
    },
  },
  state: {
    datastores: {
      'ops-pool': { attachedTo: 'ops-ds-host' },
      'prod-pool': { attachedTo: 'prod-1' },
      'ops-ceph': { attachedTo: 'ops-worker' },
    },
  },
}));

vi.mock('../../services/config/config-resources.js', () => ({
  configService: { getCurrent: vi.fn(() => Promise.resolve(OPS_CONFIG)) },
}));

import {
  _resetCache,
  assertAgentMachineAccess,
  assertAgentRepoCreate,
  configEditOverrideScope,
  isAgentEnvironment,
} from '../agent-guard.js';

// All env vars that affect agent detection
const ALL_AGENT_KEYS = [
  'REDIACC_AGENT',
  'CLAUDECODE',
  'GEMINI_CLI',
  'COPILOT_CLI',
  'CURSOR_TRACE_ID',
  'REDIACC_ALLOW_GRAND_REPO',
  'REDIACC_ALLOW_CONFIG_EDIT',
] as const;

function backupAndClearEnv(backup: Record<string, string | undefined>) {
  for (const key of ALL_AGENT_KEYS) {
    backup[key] = process.env[key];
    delete process.env[key];
  }
}

function restoreEnv(backup: Record<string, string | undefined>) {
  for (const [key, value] of Object.entries(backup)) {
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
}

describe('isAgentEnvironment', () => {
  const envBackup: Record<string, string | undefined> = {};

  beforeEach(() => {
    _resetCache();
    vi.clearAllMocks();
    mockIsAgentByAncestry.mockReturnValue(false);
    backupAndClearEnv(envBackup);
  });

  afterEach(() => {
    restoreEnv(envBackup);
  });

  it('returns false with no agent env vars', () => {
    expect(isAgentEnvironment()).toBe(false);
  });

  it('returns true when REDIACC_AGENT=1', () => {
    process.env.REDIACC_AGENT = '1';
    expect(isAgentEnvironment()).toBe(true);
  });

  it('returns true when CLAUDECODE=1', () => {
    process.env.CLAUDECODE = '1';
    expect(isAgentEnvironment()).toBe(true);
  });

  it('returns true when GEMINI_CLI=1', () => {
    process.env.GEMINI_CLI = '1';
    expect(isAgentEnvironment()).toBe(true);
  });

  it('returns true when COPILOT_CLI=1', () => {
    process.env.COPILOT_CLI = '1';
    expect(isAgentEnvironment()).toBe(true);
  });

  it('returns true when CURSOR_TRACE_ID is set', () => {
    process.env.CURSOR_TRACE_ID = 'some-trace-id';
    expect(isAgentEnvironment()).toBe(true);
  });

  it('returns false when env var is not "1"', () => {
    process.env.REDIACC_AGENT = 'true';
    expect(isAgentEnvironment()).toBe(false);
  });

  it('detects agent via ancestry even when process.env is clean', () => {
    mockIsAgentByAncestry.mockReturnValue(true);
    expect(isAgentEnvironment()).toBe(true);
  });

  it('caches result across calls', () => {
    _resetCache();
    vi.clearAllMocks();
    mockIsAgentByAncestry.mockReturnValue(false);
    isAgentEnvironment();
    isAgentEnvironment();
    expect(mockIsAgentByAncestry).toHaveBeenCalledTimes(1);
  });
});

describe('assertAgentMachineAccess', () => {
  const envBackup: Record<string, string | undefined> = {};

  beforeEach(() => {
    _resetCache();
    vi.clearAllMocks();
    mockIsAgentByAncestry.mockReturnValue(false);
    mockIsOverrideLegitimate.mockReturnValue(true);
    mockIsAncestryAvailable.mockReturnValue(true);
    backupAndClearEnv(envBackup);
  });

  afterEach(() => {
    restoreEnv(envBackup);
  });

  it('does nothing when not in agent environment', async () => {
    await expect(assertAgentMachineAccess('prod-1')).resolves.toBeUndefined();
  });

  it('throws in agent mode for machine-level access', async () => {
    process.env.REDIACC_AGENT = '1';
    await expect(assertAgentMachineAccess('prod-1')).rejects.toThrow();
  });

  it('respects legitimate REDIACC_ALLOW_GRAND_REPO=* wildcard', async () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = '*';
    mockIsOverrideLegitimate.mockReturnValue(true);
    await expect(assertAgentMachineAccess('prod-1')).resolves.toBeUndefined();
  });

  it('blocks illegitimate override (injected by agent)', async () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = '*';
    mockIsOverrideLegitimate.mockReturnValue(false);
    await expect(assertAgentMachineAccess('prod-1')).rejects.toThrow();
  });

  it('uses the agent-injected error when ancestry verification is available', async () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = '*';
    mockIsOverrideLegitimate.mockReturnValue(false);
    mockIsAncestryAvailable.mockReturnValue(true);
    await expect(assertAgentMachineAccess('prod-1')).rejects.toThrow(
      /errors\.agent\.machineGuardOverride$/
    );
  });

  it('uses the cannot-verify error when ancestry verification is unavailable', async () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = '*';
    mockIsOverrideLegitimate.mockReturnValue(false);
    mockIsAncestryAvailable.mockReturnValue(false);
    await expect(assertAgentMachineAccess('prod-1')).rejects.toThrow(
      'errors.agent.machineGuardOverrideNonLinux'
    );
  });

  it('does not allow specific repo name as machine access consent', async () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = 'mail';
    await expect(assertAgentMachineAccess('prod-1')).rejects.toThrow();
  });

  it('does not allow a comma-separated repo list as machine access consent', async () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = 'mail,web,gitlab';
    await expect(assertAgentMachineAccess('prod-1')).rejects.toThrow();
  });

  it('allows machine access when `*` appears inside a comma list', async () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = 'mail,*,web';
    mockIsOverrideLegitimate.mockReturnValue(true);
    await expect(assertAgentMachineAccess('prod-1')).resolves.toBeUndefined();
  });
});

describe('assertAgentRepoCreate', () => {
  const envBackup: Record<string, string | undefined> = {};

  beforeEach(() => {
    _resetCache();
    vi.clearAllMocks();
    mockIsAgentByAncestry.mockReturnValue(false);
    mockIsOverrideLegitimate.mockReturnValue(true);
    mockIsAncestryAvailable.mockReturnValue(true);
    backupAndClearEnv(envBackup);
  });

  afterEach(() => {
    restoreEnv(envBackup);
  });

  it('does nothing when not in agent environment', async () => {
    await expect(assertAgentRepoCreate('my-app', { machine: 'prod-1' })).resolves.toBeUndefined();
  });

  it('throws in agent mode', async () => {
    process.env.REDIACC_AGENT = '1';
    await expect(assertAgentRepoCreate('my-app', { machine: 'prod-1' })).rejects.toThrow();
  });

  it('respects legitimate wildcard override', async () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = '*';
    mockIsOverrideLegitimate.mockReturnValue(true);
    await expect(assertAgentRepoCreate('my-app', { machine: 'prod-1' })).resolves.toBeUndefined();
  });

  it('blocks illegitimate override', async () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = '*';
    mockIsOverrideLegitimate.mockReturnValue(false);
    await expect(assertAgentRepoCreate('my-app', { machine: 'prod-1' })).rejects.toThrow();
  });

  it('allows when the exact repo name is set (ancestry-legitimate)', async () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = 'my-app';
    mockIsOverrideLegitimate.mockReturnValue(true);
    await expect(assertAgentRepoCreate('my-app', { machine: 'prod-1' })).resolves.toBeUndefined();
  });

  it('allows when a comma list contains the exact name (ancestry-legitimate)', async () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = 'my-app,other';
    mockIsOverrideLegitimate.mockReturnValue(true);
    await expect(assertAgentRepoCreate('my-app', { machine: 'prod-1' })).resolves.toBeUndefined();
  });

  it('blocks when a different repo name is set', async () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = 'other';
    await expect(assertAgentRepoCreate('my-app', { machine: 'prod-1' })).rejects.toThrow(
      'Cannot create repository "my-app"'
    );
  });

  it('blocks when a comma list does not contain the target name', async () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = 'other,web';
    await expect(assertAgentRepoCreate('my-app', { machine: 'prod-1' })).rejects.toThrow(
      'Cannot create repository "my-app"'
    );
  });

  it('throws the override error when the exact name is set but ancestry is illegitimate', async () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = 'my-app';
    mockIsOverrideLegitimate.mockReturnValue(false);
    mockIsAncestryAvailable.mockReturnValue(true);
    await expect(assertAgentRepoCreate('my-app', { machine: 'prod-1' })).rejects.toThrow(
      /errors\.agent\.createGuardOverride$/
    );
  });

  it('allows when `*` appears inside a comma list', async () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_GRAND_REPO = 'my-app,*';
    mockIsOverrideLegitimate.mockReturnValue(true);
    await expect(assertAgentRepoCreate('my-app', { machine: 'prod-1' })).resolves.toBeUndefined();
  });
});

describe('ops VM exemption (operator ruling 2026-10-15)', () => {
  const envBackup: Record<string, string | undefined> = {};

  beforeEach(() => {
    _resetCache();
    vi.clearAllMocks();
    mockIsAgentByAncestry.mockReturnValue(false);
    mockIsOverrideLegitimate.mockReturnValue(true);
    mockIsAncestryAvailable.mockReturnValue(true);
    backupAndClearEnv(envBackup);
    process.env.REDIACC_AGENT = '1';
  });

  afterEach(() => {
    restoreEnv(envBackup);
  });

  it('allows machine-level access to a machine on the ops VM network', async () => {
    await expect(assertAgentMachineAccess('ops-worker')).resolves.toBeUndefined();
  });

  it('still refuses machine-level access to a non-ops machine with the same message', async () => {
    await expect(assertAgentMachineAccess('prod-1')).rejects.toThrow(
      'Cannot access machine "prod-1" directly in agent mode.'
    );
  });

  it('refuses an ops-looking machine NAME on a production address', async () => {
    await expect(assertAgentMachineAccess('ops-worker-prod')).rejects.toThrow(
      'Cannot access machine "ops-worker-prod" directly in agent mode.'
    );
  });

  it('refuses an address one /24 outside the ops network', async () => {
    await expect(assertAgentMachineAccess('edge-112')).rejects.toThrow(
      'Cannot access machine "edge-112" directly in agent mode.'
    );
  });

  it('refuses a hostname that merely starts with the ops prefix', async () => {
    await expect(assertAgentMachineAccess('ops-hostname')).rejects.toThrow(
      'Cannot access machine "ops-hostname" directly in agent mode.'
    );
  });

  it('refuses a machine the config does not know', async () => {
    await expect(assertAgentMachineAccess('ghost')).rejects.toThrow(
      'Cannot access machine "ghost" directly in agent mode.'
    );
  });

  it('allows creating a grand on an ops VM machine', async () => {
    await expect(
      assertAgentRepoCreate('vmcheck-base', { machine: 'ops-worker' })
    ).resolves.toBeUndefined();
  });

  it('allows creating a grand on a datastore attached to an ops VM', async () => {
    await expect(
      assertAgentRepoCreate('vmcheck-base', { datastore: 'ops-pool' })
    ).resolves.toBeUndefined();
  });

  it('still refuses creating a grand on a non-ops machine with the same message', async () => {
    await expect(assertAgentRepoCreate('my-app', { machine: 'prod-1' })).rejects.toThrow(
      'Cannot create repository "my-app" in agent mode.'
    );
  });

  it('still refuses creating a grand on a datastore attached to a non-ops machine', async () => {
    await expect(assertAgentRepoCreate('my-app', { datastore: 'prod-pool' })).rejects.toThrow(
      'Cannot create repository "my-app" in agent mode.'
    );
  });

  it('keeps a cluster datastore protected even when attached to an ops VM', async () => {
    await expect(assertAgentRepoCreate('my-app', { datastore: 'ops-ceph' })).rejects.toThrow(
      'Cannot create repository "my-app" in agent mode.'
    );
  });

  it('refuses create on an ops-looking name, an address just outside the range, and no placement', async () => {
    for (const placement of [
      { machine: 'ops-worker-prod' },
      { machine: 'edge-112' },
      { machine: 'ops-hostname' },
      undefined,
    ]) {
      await expect(assertAgentRepoCreate('my-app', placement)).rejects.toThrow(
        'Cannot create repository "my-app" in agent mode.'
      );
    }
  });
});

describe('configEditOverrideScope', () => {
  const envBackup: Record<string, string | undefined> = {};

  beforeEach(() => {
    _resetCache();
    vi.clearAllMocks();
    mockIsAgentByAncestry.mockReturnValue(false);
    mockIsOverrideLegitimate.mockReturnValue(true);
    mockIsAncestryAvailable.mockReturnValue(true);
    backupAndClearEnv(envBackup);
  });

  afterEach(() => {
    restoreEnv(envBackup);
  });

  it('returns null when the env var is not set', () => {
    expect(configEditOverrideScope()).toBeNull();
  });

  it('returns the scope outside agent environments without ancestry checks', () => {
    process.env.REDIACC_ALLOW_CONFIG_EDIT = '/credentials/*';
    expect(configEditOverrideScope()).toBe('/credentials/*');
    expect(mockIsOverrideLegitimate).not.toHaveBeenCalled();
  });

  it('verifies REDIACC_ALLOW_CONFIG_EDIT itself, not the grand-repo override', () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_CONFIG_EDIT = '*';
    mockIsOverrideLegitimate.mockReturnValue(true);
    expect(configEditOverrideScope()).toBe('*');
    expect(mockIsOverrideLegitimate).toHaveBeenCalledWith('REDIACC_ALLOW_CONFIG_EDIT');
  });

  it('rejects an agent-injected config-edit override', () => {
    process.env.REDIACC_AGENT = '1';
    process.env.REDIACC_ALLOW_CONFIG_EDIT = '*';
    mockIsOverrideLegitimate.mockReturnValue(false);
    expect(configEditOverrideScope()).toBeNull();
  });
});
