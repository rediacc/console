import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// i18n stub — return key + interpolated params for assertable error strings
vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) =>
    params ? `${key}:${JSON.stringify(params)}` : key,
}));

// configService used by the command handlers. `resolveRepoRefLocal` (the
// config-local ref resolver the secret verbs use) reads `getCurrent()`; the
// mutation gate reads the decrypted config (aliased to the same mock).
const mockGetRepository = vi.hoisted(() => vi.fn());
const mockGetCurrent = vi.hoisted(() => vi.fn());
const mockGetResourceState = vi.hoisted(() => vi.fn());

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getRepository: mockGetRepository,
    getCurrent: mockGetCurrent,
    // v3: the precondition gate reads the decrypted config; alias it to the same
    // mock so `mockGetCurrent.mockResolvedValue(...)` drives both.
    getDecryptedConfig: mockGetCurrent,
    getResourceState: mockGetResourceState,
  },
}));

// Storage primitives are mocked separately so individual tests can spy on
// the actual write/delete calls without going through the resource-state
// plumbing.
const mockReadRepositorySecret = vi.hoisted(() => vi.fn());
const mockListRepositorySecretKeyModes = vi.hoisted(() => vi.fn());
const mockWriteRepositorySecret = vi.hoisted(() => vi.fn());
const mockDeleteRepositorySecret = vi.hoisted(() => vi.fn());

vi.mock('../../services/repo/repo-secrets-store.js', () => ({
  readRepositorySecret: mockReadRepositorySecret,
  listRepositorySecretKeyModes: mockListRepositorySecretKeyModes,
  writeRepositorySecret: mockWriteRepositorySecret,
  deleteRepositorySecret: mockDeleteRepositorySecret,
}));

// Capture outputService.print and success calls for assertion
const mockPrint = vi.hoisted(() => vi.fn());
const mockSuccess = vi.hoisted(() => vi.fn());
vi.mock('../../services/core/output.js', () => ({
  outputService: { print: mockPrint, info: vi.fn(), warn: vi.fn(), success: mockSuccess },
}));

// Audit log: silence
vi.mock('../../services/core/audit-log.js', () => ({
  auditLog: vi.fn(),
}));

// process-ancestry override-legitimacy check
const mockIsAgentByAncestry = vi.hoisted(() => vi.fn(() => false));
const mockIsOverrideLegitimate = vi.hoisted(() => vi.fn(() => true));
vi.mock('../../utils/process-ancestry.js', () => ({
  isAgentByAncestry: mockIsAgentByAncestry,
  isOverrideLegitimate: mockIsOverrideLegitimate,
  isAncestryVerificationAvailable: vi.fn(() => true),
  _resetAncestryCache: vi.fn(),
  OVERRIDE_VAR_GRAND: 'REDIACC_ALLOW_GRAND_REPO',
  OVERRIDE_VAR_CONFIG_EDIT: 'REDIACC_ALLOW_CONFIG_EDIT',
}));

// handleError rethrows so we can assert
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

import { _resetCache } from '../../utils/agent-guard.js';

const { registerRepoSecretCommands } = await import('../repo-secret.js');
const { Command } = await import('commander');

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
  for (const k of ALL_AGENT_KEYS) {
    backup[k] = process.env[k];
    delete process.env[k];
  }
}

function restoreEnv(backup: Record<string, string | undefined>) {
  for (const [k, v] of Object.entries(backup)) {
    if (v === undefined) delete process.env[k];
    else process.env[k] = v;
  }
}

const GRAND_GUID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
const FORK_GUID = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';

const grandRepo = {
  repositoryGuid: GRAND_GUID,
  // no parentGuid / grandGuid → grand
};
const forkRepo = {
  repositoryGuid: FORK_GUID,
  parentGuid: GRAND_GUID,
  grandGuid: GRAND_GUID, // points to a different repo → isFork
};

// Config-local resolution (resolveRepoRefLocal → resolveRefLocal) reads
// config.resources.repositories to map a ref to its family/tag WITHOUT any
// placement. Read verbs (get/list) drive this real path, so their configs must
// carry the `app` family. Both tags present so bare `app` (→ grand 'latest')
// and `app:dev` both resolve.
const readConfig = {
  resources: {
    repositories: { app: { grand: 'latest', tags: { latest: grandRepo, dev: forkRepo } } },
  },
};

/**
 * Throw instead of process.exit so tests can assert.
 *
 * Applied to the whole tree, not just the root: a parse error (an out-of-set
 * --mode, say) is raised by the subcommand that owns the option, and a root-only
 * exitOverride leaves that subcommand still calling process.exit.
 */
function applyExitOverride(cmd: Command): void {
  cmd.exitOverride();
  for (const sub of cmd.commands) applyExitOverride(sub);
}

function buildProgram() {
  const program = new Command();
  const repo = program.command('repo');
  registerRepoSecretCommands(repo);
  applyExitOverride(program);
  return program;
}

async function run(args: string[]): Promise<void> {
  const program = buildProgram();
  await program.parseAsync(['node', 'rdc', ...args]);
}

describe('rdc repo secret get/list', () => {
  const envBackup: Record<string, string | undefined> = {};

  beforeEach(() => {
    _resetCache();
    vi.clearAllMocks();
    mockIsAgentByAncestry.mockReturnValue(false);
    mockIsOverrideLegitimate.mockReturnValue(true);
    mockGetResourceState.mockResolvedValue({});
    backupAndClearEnv(envBackup);
  });

  afterEach(() => {
    restoreEnv(envBackup);
  });

  // V2: write-only model. `get` returns digest only — no plaintext for
  // anyone, no agent-vs-human asymmetry. The fork-vs-grand `grandGuard`
  // is gone (mutation-gate is the actual safety property; reads are
  // always safe because there's no plaintext to leak).
  describe('agent on grand repo (V2: read-safe, no grandGuard)', () => {
    beforeEach(() => {
      process.env.REDIACC_AGENT = '1';
      mockGetRepository.mockResolvedValue(grandRepo);
      mockGetCurrent.mockResolvedValue(readConfig);
    });

    it('list works without REDIACC_ALLOW_GRAND_REPO (no grandGuard in V2)', async () => {
      mockListRepositorySecretKeyModes.mockReturnValue([{ key: 'X', mode: 'env' }]);
      await run(['repo', 'secret', 'list', 'app']);
      // Table format prints the entry rows directly.
      expect(mockPrint.mock.calls[0]?.[0]).toEqual([{ key: 'X', mode: 'env' }]);
    });

    it('get returns digest only — never the value', async () => {
      mockReadRepositorySecret.mockReturnValue({ mode: 'env', value: 'sk_live_XYZ' });
      await run(['repo', 'secret', 'get', 'app', '--key', 'STRIPE']);

      const call = mockPrint.mock.calls[0]?.[0][0];
      expect(call).toMatchObject({ key: 'STRIPE', mode: 'env' });
      expect(call.digest).toMatch(/^[0-9a-f]{8}$/);
      // Critical write-only invariant: value never reaches output, ever.
      expect(call).not.toHaveProperty('value');
      expect(JSON.stringify(call)).not.toContain('sk_live_XYZ');
    });
  });

  describe('agent on fork repo (V2)', () => {
    beforeEach(() => {
      process.env.REDIACC_AGENT = '1';
      mockGetRepository.mockResolvedValue(forkRepo);
      mockGetCurrent.mockResolvedValue(readConfig);
    });

    it('get returns digest only on a fork too', async () => {
      mockReadRepositorySecret.mockReturnValue({ mode: 'file', value: 'pem-content' });
      await run(['repo', 'secret', 'get', 'app:dev', '--key', 'KEY']);
      const call = mockPrint.mock.calls[0]?.[0][0];
      expect(call).toMatchObject({ key: 'KEY', mode: 'file' });
      expect(call.digest).toMatch(/^[0-9a-f]{8}$/);
      expect(call).not.toHaveProperty('value');
      expect(JSON.stringify(call)).not.toContain('pem-content');
    });

    it('lists secrets on a fork without leaking values', async () => {
      mockListRepositorySecretKeyModes.mockReturnValue([
        { key: 'A', mode: 'env' },
        { key: 'B', mode: 'file' },
      ]);
      await run(['repo', 'secret', 'list', 'app:dev']);
      const call = mockPrint.mock.calls[0]?.[0];
      expect(call).toEqual([
        { key: 'A', mode: 'env' },
        { key: 'B', mode: 'file' },
      ]);
      // Values are never in the printed payload
      const json = JSON.stringify(call);
      expect(json).not.toMatch(/value/);
    });
  });

  describe('human (no agent env) — also gets digest-only on get (V2 symmetric)', () => {
    beforeEach(() => {
      mockGetRepository.mockResolvedValue(grandRepo);
      mockGetCurrent.mockResolvedValue(readConfig);
    });

    it('get returns digest only — humans no longer see plaintext (write-only)', async () => {
      mockReadRepositorySecret.mockReturnValue({ mode: 'env', value: 'plaintext-secret' });
      await run(['repo', 'secret', 'get', 'app', '--key', 'X']);
      const call = mockPrint.mock.calls[0]?.[0][0];
      expect(call).toMatchObject({ key: 'X', mode: 'env' });
      expect(call.digest).toMatch(/^[0-9a-f]{8}$/);
      expect(call).not.toHaveProperty('value');
      expect(JSON.stringify(call)).not.toContain('plaintext-secret');
    });

    it('throws if secret key not found', async () => {
      mockReadRepositorySecret.mockReturnValue(undefined);
      await expect(run(['repo', 'secret', 'get', 'app', '--key', 'X'])).rejects.toThrow(
        /commands\.repo\.secret\.get\.notFound/
      );
    });

    it('throws if repo not found', async () => {
      // The family is absent from config → resolveRepoRefLocal throws notFound (exit 5).
      await expect(run(['repo', 'secret', 'get', 'ghost', '--key', 'X'])).rejects.toThrow(
        /is not in this config/
      );
    });

    it('list returns sorted keys + modes (never values)', async () => {
      mockListRepositorySecretKeyModes.mockReturnValue([
        { key: 'AAA', mode: 'env' },
        { key: 'BBB', mode: 'file' },
      ]);
      await run(['repo', 'secret', 'list', 'app']);
      const call = mockPrint.mock.calls[0]?.[0];
      expect(call).toEqual([
        { key: 'AAA', mode: 'env' },
        { key: 'BBB', mode: 'file' },
      ]);
    });

    it('list prints nothing tabular when no secrets (info line instead)', async () => {
      mockListRepositorySecretKeyModes.mockReturnValue([]);
      await run(['repo', 'secret', 'list', 'app']);
      expect(mockPrint).not.toHaveBeenCalled();
    });
  });

  // ── set / unset (mutation gate) ────────────────────────────────

  // v3 family config: places `record` under repositories.app.tags[tag].
  function familyConfig(tag: string, record: Record<string, unknown>): Record<string, unknown> {
    return {
      schemaVersion: 3,
      id: '00000000-0000-0000-0000-000000000001',
      version: 1,
      resources: { repositories: { app: { grand: 'latest', tags: { [tag]: record } } } },
    };
  }

  function configWithSecret(value: string): Record<string, unknown> {
    return familyConfig('latest', {
      repositoryGuid: GRAND_GUID,
      secrets: { STRIPE: { mode: 'env', value } },
    });
  }

  function configWithFork(value: string): Record<string, unknown> {
    return familyConfig('dev', {
      repositoryGuid: FORK_GUID,
      parentGuid: GRAND_GUID,
      grandGuid: GRAND_GUID,
      secrets: { STRIPE: { mode: 'env', value } },
    });
  }

  describe('set on a fork (agent context)', () => {
    beforeEach(() => {
      process.env.REDIACC_AGENT = '1';
      mockGetRepository.mockResolvedValue(forkRepo);
    });

    it('first-write of a new key still requires --current under agent (existing precedent)', async () => {
      // The mutation gate refuses any sensitive write without a knowledge claim
      // under agent context, even on first-write. Agents must always be
      // intentional about secrets, even new ones.
      mockReadRepositorySecret.mockReturnValue(undefined);
      mockGetCurrent.mockResolvedValue(familyConfig('dev', forkRepo));

      await expect(
        run(['repo', 'secret', 'set', 'app:dev', '--key', 'NEW', '--value', 'v'])
      ).rejects.toThrow(/sensitive path requires --current/);
      expect(mockWriteRepositorySecret).not.toHaveBeenCalled();
    });

    it('first-write with --current "" passes the new-field branch', async () => {
      mockReadRepositorySecret.mockReturnValue(undefined);
      mockGetCurrent.mockResolvedValue(familyConfig('dev', forkRepo));

      await run([
        'repo',
        'secret',
        'set',
        'app:dev',
        '--key',
        'NEW',
        '--value',
        'v',
        '--current',
        '',
      ]);
      expect(mockWriteRepositorySecret).toHaveBeenCalledWith(expect.anything(), 'app:dev', 'NEW', {
        mode: 'file',
        value: 'v',
      });
    });

    it('overwrite without --current and no override → refused (precondition)', async () => {
      mockReadRepositorySecret.mockReturnValue({ mode: 'env', value: 'old' });
      mockGetCurrent.mockResolvedValue(configWithFork('old'));

      await expect(
        run(['repo', 'secret', 'set', 'app:dev', '--key', 'STRIPE', '--value', 'new'])
      ).rejects.toThrow();
      expect(mockWriteRepositorySecret).not.toHaveBeenCalled();
    });

    it('overwrite with correct --current succeeds', async () => {
      mockReadRepositorySecret.mockReturnValue({ mode: 'env', value: 'old' });
      mockGetCurrent.mockResolvedValue(configWithFork('old'));

      await run([
        'repo',
        'secret',
        'set',
        'app:dev',
        '--key',
        'STRIPE',
        '--value',
        'new',
        '--mode',
        'env',
        '--current',
        'old',
      ]);

      expect(mockWriteRepositorySecret).toHaveBeenCalledWith(
        expect.anything(),
        'app:dev',
        'STRIPE',
        {
          mode: 'env',
          value: 'new',
        }
      );
    });

    it('overwrite with WRONG --current throws PreconditionMismatch', async () => {
      mockReadRepositorySecret.mockReturnValue({ mode: 'env', value: 'old' });
      mockGetCurrent.mockResolvedValue(configWithFork('old'));

      await expect(
        run([
          'repo',
          'secret',
          'set',
          'app:dev',
          '--key',
          'STRIPE',
          '--value',
          'new',
          '--current',
          'WRONG',
        ])
      ).rejects.toThrow(/digest mismatch|precondition/i);
      expect(mockWriteRepositorySecret).not.toHaveBeenCalled();
    });

    it('REDIACC_ALLOW_CONFIG_EDIT scope match bypasses --current requirement', async () => {
      process.env.REDIACC_ALLOW_CONFIG_EDIT = '/resources/repositories/*/tags/*/secrets/*/value';
      mockReadRepositorySecret.mockReturnValue({ mode: 'env', value: 'old' });
      mockGetCurrent.mockResolvedValue(configWithFork('old'));

      await run(['repo', 'secret', 'set', 'app:dev', '--key', 'STRIPE', '--value', 'new']);
      expect(mockWriteRepositorySecret).toHaveBeenCalled();
    });

    // --mode declares .choices(['env', 'file']), so Commander rejects an
    // out-of-set value at parse time, before the handler runs. The handler's own
    // badMode check still guards non-CLI callers.
    it('rejects --mode foo', async () => {
      mockReadRepositorySecret.mockReturnValue(undefined);
      mockGetCurrent.mockResolvedValue(familyConfig('latest', grandRepo));
      await expect(
        run(['repo', 'secret', 'set', 'app:dev', '--key', 'X', '--value', 'v', '--mode', 'foo'])
      ).rejects.toThrow(/Allowed choices are env, file/);
      expect(mockWriteRepositorySecret).not.toHaveBeenCalled();
    });
  });

  describe('set on a grand (agent context) — V2: no grandGuard, mutation-gate gates writes', () => {
    beforeEach(() => {
      process.env.REDIACC_AGENT = '1';
      mockGetRepository.mockResolvedValue(grandRepo);
    });

    it('write to a NEW key on grand requires --current "" (mutation-gate symmetric)', async () => {
      mockReadRepositorySecret.mockReturnValue(undefined);
      mockGetCurrent.mockResolvedValue(familyConfig('latest', grandRepo));
      // Without any precondition flag, mutation-gate refuses (was previously
      // blocked by the now-removed grandGuard policy layer).
      await expect(
        run(['repo', 'secret', 'set', 'app', '--key', 'X', '--value', 'v'])
      ).rejects.toThrow(/sensitive path requires --current/);
      expect(mockWriteRepositorySecret).not.toHaveBeenCalled();
    });

    it('write to grand succeeds with --rotate-secret (audited as rotation)', async () => {
      mockReadRepositorySecret.mockReturnValue(undefined);
      mockGetCurrent.mockResolvedValue(familyConfig('latest', grandRepo));
      await run(['repo', 'secret', 'set', 'app', '--key', 'X', '--value', 'v', '--rotate-secret']);
      expect(mockWriteRepositorySecret).toHaveBeenCalled();
    });
  });

  describe('unset on a fork (agent context)', () => {
    beforeEach(() => {
      process.env.REDIACC_AGENT = '1';
      mockGetRepository.mockResolvedValue(forkRepo);
    });

    it('throws when key not found', async () => {
      mockReadRepositorySecret.mockReturnValue(undefined);
      // Ref must resolve so the flow reaches the key-not-found check.
      mockGetCurrent.mockResolvedValue(configWithFork('old'));
      await expect(run(['repo', 'secret', 'unset', 'app:dev', '--key', 'X'])).rejects.toThrow(
        /notFound/
      );
      expect(mockDeleteRepositorySecret).not.toHaveBeenCalled();
    });

    it('refused without --current and no override', async () => {
      mockReadRepositorySecret.mockReturnValue({ mode: 'env', value: 'old' });
      mockGetCurrent.mockResolvedValue(configWithFork('old'));
      await expect(
        run(['repo', 'secret', 'unset', 'app:dev', '--key', 'STRIPE'])
      ).rejects.toThrow();
      expect(mockDeleteRepositorySecret).not.toHaveBeenCalled();
    });

    it('with correct --current → succeeds', async () => {
      mockReadRepositorySecret.mockReturnValue({ mode: 'env', value: 'old' });
      mockGetCurrent.mockResolvedValue(configWithFork('old'));
      await run(['repo', 'secret', 'unset', 'app:dev', '--key', 'STRIPE', '--current', 'old']);
      expect(mockDeleteRepositorySecret).toHaveBeenCalledWith(
        expect.anything(),
        'app', // repoRef (parsed base name)
        'app:dev', // resolved repoKey
        'STRIPE' // secret name
      );
    });
  });

  describe('human (no agent env) write paths — symmetric with agents in V2', () => {
    beforeEach(() => {
      mockGetRepository.mockResolvedValue(grandRepo);
    });

    it('first-write of a new key requires --current "" (symmetric with agent)', async () => {
      mockReadRepositorySecret.mockReturnValue(undefined);
      mockGetCurrent.mockResolvedValue(configWithSecret('old'));
      await run(['repo', 'secret', 'set', 'app', '--key', 'NEW', '--value', 'v', '--current', '']);
      expect(mockWriteRepositorySecret).toHaveBeenCalled();
    });

    it('overwrite without --current is now refused for humans too', async () => {
      mockReadRepositorySecret.mockReturnValue({ mode: 'env', value: 'old' });
      mockGetCurrent.mockResolvedValue(configWithSecret('old'));
      await expect(
        run(['repo', 'secret', 'set', 'app', '--key', 'STRIPE', '--value', 'new'])
      ).rejects.toThrow();
      expect(mockWriteRepositorySecret).not.toHaveBeenCalled();
    });

    it('unset with correct --current succeeds for human', async () => {
      mockReadRepositorySecret.mockReturnValue({ mode: 'env', value: 'v' });
      mockGetCurrent.mockResolvedValue(configWithSecret('v'));
      await run(['repo', 'secret', 'unset', 'app', '--key', 'STRIPE', '--current', 'v']);
      expect(mockDeleteRepositorySecret).toHaveBeenCalledWith(
        expect.anything(),
        'app',
        'app:latest',
        'STRIPE'
      );
    });
  });

  // V2-specific: --rotate-secret flag, mutual exclusion, structured next.
  describe('V2 rotate-secret + structured next', () => {
    beforeEach(() => {
      mockGetRepository.mockResolvedValue(grandRepo);
    });

    it('--current and --rotate-secret are mutually exclusive', async () => {
      mockReadRepositorySecret.mockReturnValue({ mode: 'env', value: 'old' });
      mockGetCurrent.mockResolvedValue(configWithSecret('old'));
      await expect(
        run([
          'repo',
          'secret',
          'set',
          'app',
          '--key',
          'STRIPE',
          '--value',
          'v',
          '--current',
          'old',
          '--rotate-secret',
        ])
      ).rejects.toThrow(/mutuallyExclusive/);
      expect(mockWriteRepositorySecret).not.toHaveBeenCalled();
    });

    it('--rotate-secret bypasses --current requirement', async () => {
      mockReadRepositorySecret.mockReturnValue({ mode: 'env', value: 'old' });
      mockGetCurrent.mockResolvedValue(configWithSecret('old'));
      await run([
        'repo',
        'secret',
        'set',
        'app',
        '--key',
        'STRIPE',
        '--value',
        'new',
        '--rotate-secret',
      ]);
      expect(mockWriteRepositorySecret).toHaveBeenCalled();
    });

    it('precondition mismatch throws PreconditionValidationError carrying next', async () => {
      const { PreconditionValidationError } = await import('../../utils/errors.js');
      mockReadRepositorySecret.mockReturnValue({ mode: 'env', value: 'old' });
      mockGetCurrent.mockResolvedValue(configWithSecret('old'));
      try {
        await run([
          'repo',
          'secret',
          'set',
          'app',
          '--key',
          'STRIPE',
          '--value',
          'new',
          '--current',
          'WRONG',
        ]);
        throw new Error('should have thrown');
      } catch (err) {
        expect(err).toBeInstanceOf(PreconditionValidationError);
        const next = (err as InstanceType<typeof PreconditionValidationError>).next;
        expect(next.summary).toBeTruthy();
        expect(next.options).toHaveLength(2);
        // Second option should be the rotate-skip variant. The original
        // command is reconstructed verbatim and ends with --rotate-secret.
        const rotateOption = next.options?.find((o) => o.run.includes('--rotate-secret'));
        expect(rotateOption).toBeDefined();
        // First option's `run` is the i18n key stub (mocked t returns the key
        // + params verbatim), so we assert the params interpolation reaches
        // the structured payload — the test mocks t to return the key path,
        // which is enough to confirm the helper wiring is correct.
        const verifyOption = next.options?.find((o) =>
          o.run.startsWith('errors.precondition.next.options.confirm.run')
        );
        expect(verifyOption).toBeDefined();
        expect(verifyOption?.run).toContain('"repository":"app:latest"');
        expect(verifyOption?.run).toContain('"key":"STRIPE"');
      }
    });
  });
});
