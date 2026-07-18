import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../services/config/config-resources.js', () => ({
  configService: {
    getRepository: vi.fn(),
  },
}));

vi.mock('../agent-guard.js', () => ({
  isAgentEnvironment: vi.fn(),
}));

vi.mock('../process-ancestry.js', () => ({
  isOverrideLegitimate: vi.fn(() => true),
  isAncestryVerificationAvailable: vi.fn(() => true),
  OVERRIDE_VAR_CLUSTER: 'REDIACC_ALLOW_CLUSTER_OPS',
}));

vi.mock('../../services/core/audit-log.js', () => ({
  auditLog: vi.fn(),
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) => {
    if (params) return `${key}:${JSON.stringify(params)}`;
    return key;
  },
}));

import { configService } from '../../services/config/config-resources.js';
import { auditLog } from '../../services/core/audit-log.js';
import type { RepositoryConfig } from '../../types/index.js';
import { isAgentEnvironment } from '../agent-guard.js';
import {
  assertCommandPolicy,
  CMD,
  COMMAND_POLICIES,
  validateRemotePath,
} from '../command-policy.js';
import { isAncestryVerificationAvailable, isOverrideLegitimate } from '../process-ancestry.js';

const mockIsAgent = vi.mocked(isAgentEnvironment);
const mockGetRepo = vi.mocked(configService.getRepository);
const mockIsOverrideLegitimate = vi.mocked(isOverrideLegitimate);
const mockIsAncestryAvailable = vi.mocked(isAncestryVerificationAvailable);
const mockAuditLog = vi.mocked(auditLog);

describe('command-policy', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsOverrideLegitimate.mockReturnValue(true);
    mockIsAncestryAvailable.mockReturnValue(true);
    delete process.env.REDIACC_ALLOW_GRAND_REPO;
    delete process.env.REDIACC_ALLOW_CLUSTER_OPS;
  });

  afterEach(() => {
    delete process.env.REDIACC_ALLOW_GRAND_REPO;
    delete process.env.REDIACC_ALLOW_CLUSTER_OPS;
  });

  describe('assertCommandPolicy', () => {
    it('allows non-agent environments', async () => {
      mockIsAgent.mockReturnValue(false);
      await expect(assertCommandPolicy(CMD.REPO_UP, 'mail')).resolves.not.toThrow();
      expect(mockGetRepo).not.toHaveBeenCalled();
    });

    it('blocks grand repos in agent mode', async () => {
      mockIsAgent.mockReturnValue(true);
      mockGetRepo.mockResolvedValue({ repositoryGuid: 'abc-123' } satisfies RepositoryConfig);

      await expect(assertCommandPolicy(CMD.REPO_UP, 'mail')).rejects.toThrow(
        'errors.agent.grandGuard'
      );
    });

    it('allows fork repos for grandGuard commands', async () => {
      mockIsAgent.mockReturnValue(true);
      mockGetRepo.mockResolvedValue({
        repositoryGuid: 'fork-guid',
        grandGuid: 'parent-guid',
      } satisfies RepositoryConfig);

      await expect(assertCommandPolicy(CMD.REPO_UP, 'mail-fork')).resolves.not.toThrow();
    });

    it('blocks fork repos for forkBlocked commands', async () => {
      mockIsAgent.mockReturnValue(true);
      mockGetRepo.mockResolvedValue({
        repositoryGuid: 'fork-guid',
        grandGuid: 'parent-guid',
      } satisfies RepositoryConfig);

      await expect(assertCommandPolicy(CMD.REPO_RESIZE, 'mail-fork')).rejects.toThrow(
        'errors.agent.forkBlocked'
      );
    });

    it('respects REDIACC_ALLOW_GRAND_REPO=*', async () => {
      mockIsAgent.mockReturnValue(true);
      process.env.REDIACC_ALLOW_GRAND_REPO = '*';
      mockGetRepo.mockResolvedValue({ repositoryGuid: 'abc-123' } satisfies RepositoryConfig);

      await expect(assertCommandPolicy(CMD.REPO_UP, 'mail')).resolves.not.toThrow();
    });

    it('respects REDIACC_ALLOW_GRAND_REPO=<name>', async () => {
      mockIsAgent.mockReturnValue(true);
      process.env.REDIACC_ALLOW_GRAND_REPO = 'mail';
      mockGetRepo.mockResolvedValue({ repositoryGuid: 'abc-123' } satisfies RepositoryConfig);

      await expect(assertCommandPolicy(CMD.REPO_UP, 'mail')).resolves.not.toThrow();
    });

    it('blocks when REDIACC_ALLOW_GRAND_REPO does not match', async () => {
      mockIsAgent.mockReturnValue(true);
      process.env.REDIACC_ALLOW_GRAND_REPO = 'other';
      mockGetRepo.mockResolvedValue({ repositoryGuid: 'abc-123' } satisfies RepositoryConfig);

      await expect(assertCommandPolicy(CMD.REPO_UP, 'mail')).rejects.toThrow(
        'errors.agent.grandGuard'
      );
    });

    it('respects REDIACC_ALLOW_GRAND_REPO=<comma list> for each listed repo', async () => {
      mockIsAgent.mockReturnValue(true);
      process.env.REDIACC_ALLOW_GRAND_REPO = 'mail,web,gitlab';
      mockGetRepo.mockResolvedValue({ repositoryGuid: 'abc-123' } satisfies RepositoryConfig);

      await expect(assertCommandPolicy(CMD.REPO_UP, 'mail')).resolves.not.toThrow();
      await expect(assertCommandPolicy(CMD.REPO_UP, 'web')).resolves.not.toThrow();
      await expect(assertCommandPolicy(CMD.REPO_UP, 'gitlab')).resolves.not.toThrow();
    });

    it('tolerates whitespace around comma-separated entries', async () => {
      mockIsAgent.mockReturnValue(true);
      process.env.REDIACC_ALLOW_GRAND_REPO = ' mail , web ';
      mockGetRepo.mockResolvedValue({ repositoryGuid: 'abc-123' } satisfies RepositoryConfig);

      await expect(assertCommandPolicy(CMD.REPO_UP, 'mail')).resolves.not.toThrow();
      await expect(assertCommandPolicy(CMD.REPO_UP, 'web')).resolves.not.toThrow();
    });

    it('blocks repos not in the comma list', async () => {
      mockIsAgent.mockReturnValue(true);
      process.env.REDIACC_ALLOW_GRAND_REPO = 'web,gitlab';
      mockGetRepo.mockResolvedValue({ repositoryGuid: 'abc-123' } satisfies RepositoryConfig);

      await expect(assertCommandPolicy(CMD.REPO_UP, 'mail')).rejects.toThrow(
        'errors.agent.grandGuard'
      );
    });

    it('grand-repo match is case-sensitive', async () => {
      mockIsAgent.mockReturnValue(true);
      process.env.REDIACC_ALLOW_GRAND_REPO = 'Mail';
      mockGetRepo.mockResolvedValue({ repositoryGuid: 'abc-123' } satisfies RepositoryConfig);

      await expect(assertCommandPolicy(CMD.REPO_UP, 'mail')).rejects.toThrow(
        'errors.agent.grandGuard'
      );
    });

    it('treats `*` inside a list as wildcard', async () => {
      mockIsAgent.mockReturnValue(true);
      process.env.REDIACC_ALLOW_GRAND_REPO = 'mail,*';
      mockGetRepo.mockResolvedValue({ repositoryGuid: 'abc-123' } satisfies RepositoryConfig);

      await expect(assertCommandPolicy(CMD.REPO_UP, 'anything')).resolves.not.toThrow();
    });

    it('reports agent-injected override when ancestry verification is available', async () => {
      mockIsAgent.mockReturnValue(true);
      mockIsOverrideLegitimate.mockReturnValue(false);
      mockIsAncestryAvailable.mockReturnValue(true);
      process.env.REDIACC_ALLOW_GRAND_REPO = 'mail';
      mockGetRepo.mockResolvedValue({ repositoryGuid: 'abc-123' } satisfies RepositoryConfig);

      await expect(assertCommandPolicy(CMD.REPO_UP, 'mail')).rejects.toThrow(
        'errors.agent.grandGuardOverride:'
      );
    });

    it('reports unverifiable override when ancestry verification is unavailable', async () => {
      mockIsAgent.mockReturnValue(true);
      mockIsOverrideLegitimate.mockReturnValue(false);
      mockIsAncestryAvailable.mockReturnValue(false);
      process.env.REDIACC_ALLOW_GRAND_REPO = 'mail';
      mockGetRepo.mockResolvedValue({ repositoryGuid: 'abc-123' } satisfies RepositoryConfig);

      await expect(assertCommandPolicy(CMD.REPO_UP, 'mail')).rejects.toThrow(
        'errors.agent.grandGuardOverrideNonLinux'
      );
    });

    it('agentBlocked ignores comma-list override', async () => {
      mockIsAgent.mockReturnValue(true);
      process.env.REDIACC_ALLOW_GRAND_REPO = 'mail,web';

      await expect(assertCommandPolicy(CMD.RUN)).rejects.toThrow('errors.agent.commandBlocked');
    });

    it('skips check when repo not found', async () => {
      mockIsAgent.mockReturnValue(true);
      mockGetRepo.mockResolvedValue(undefined);

      await expect(assertCommandPolicy(CMD.REPO_UP, 'nonexistent')).resolves.not.toThrow();
    });

    it('skips check when no repoName provided', async () => {
      mockIsAgent.mockReturnValue(true);

      await expect(assertCommandPolicy(CMD.REPO_UP)).resolves.not.toThrow();
      expect(mockGetRepo).not.toHaveBeenCalled();
    });

    it('blocks agentBlocked commands unconditionally in agent mode', async () => {
      mockIsAgent.mockReturnValue(true);

      await expect(assertCommandPolicy(CMD.RUN)).rejects.toThrow('errors.agent.commandBlocked');
      expect(mockGetRepo).not.toHaveBeenCalled();
    });

    it('allows agentBlocked commands for non-agent environments', async () => {
      mockIsAgent.mockReturnValue(false);

      await expect(assertCommandPolicy(CMD.RUN)).resolves.not.toThrow();
    });

    it('agentBlocked ignores REDIACC_ALLOW_GRAND_REPO override', async () => {
      mockIsAgent.mockReturnValue(true);
      process.env.REDIACC_ALLOW_GRAND_REPO = '*';

      await expect(assertCommandPolicy(CMD.RUN)).rejects.toThrow('errors.agent.commandBlocked');
    });
  });

  describe('cluster-ops override (REDIACC_ALLOW_CLUSTER_OPS)', () => {
    it('allows a cluster verb with a legitimate wildcard override in agent mode', async () => {
      mockIsAgent.mockReturnValue(true);
      mockIsOverrideLegitimate.mockReturnValue(true);
      process.env.REDIACC_ALLOW_CLUSTER_OPS = '*';

      await expect(
        assertCommandPolicy(CMD.CLUSTER_CREATE, undefined, 'prod')
      ).resolves.not.toThrow();
      expect(mockGetRepo).not.toHaveBeenCalled();
    });

    it('audits actor.kind=agent (via auditLog) when a legitimate override is honored', async () => {
      mockIsAgent.mockReturnValue(true);
      mockIsOverrideLegitimate.mockReturnValue(true);
      process.env.REDIACC_ALLOW_CLUSTER_OPS = '*';

      await assertCommandPolicy(CMD.CLUSTER_DESTROY, undefined, 'prod');

      expect(mockAuditLog).toHaveBeenCalledTimes(1);
      const draft = mockAuditLog.mock.calls[0][1];
      expect(draft.command).toBe('cluster destroy');
      expect(draft.paths).toEqual(['prod']);
      expect(draft.outcome).toBe('ok');
      expect(draft.reason).toContain('REDIACC_ALLOW_CLUSTER_OPS');
    });

    it('blocks when the override is present only in a descendant (agent self-set)', async () => {
      mockIsAgent.mockReturnValue(true);
      // isOverrideLegitimate=false models the ancestry walk finding the override
      // BELOW the agent boundary (the agent set it itself).
      mockIsOverrideLegitimate.mockReturnValue(false);
      process.env.REDIACC_ALLOW_CLUSTER_OPS = '*';

      await expect(assertCommandPolicy(CMD.CLUSTER_CREATE, undefined, 'prod')).rejects.toThrow(
        'errors.agent.clusterOpBlocked'
      );
      expect(mockAuditLog).not.toHaveBeenCalled();
    });

    it('blocks a cluster verb when no override is set', async () => {
      mockIsAgent.mockReturnValue(true);

      await expect(assertCommandPolicy(CMD.CLUSTER_SCALE, undefined, 'prod')).rejects.toThrow(
        'errors.agent.clusterOpBlocked'
      );
    });

    it('allows cluster verbs for non-agent environments regardless of override', async () => {
      mockIsAgent.mockReturnValue(false);

      await expect(
        assertCommandPolicy(CMD.CLUSTER_DESTROY, undefined, 'prod')
      ).resolves.not.toThrow();
    });

    it('keeps `run` absolutely blocked even with REDIACC_ALLOW_CLUSTER_OPS=*', async () => {
      mockIsAgent.mockReturnValue(true);
      mockIsOverrideLegitimate.mockReturnValue(true);
      process.env.REDIACC_ALLOW_CLUSTER_OPS = '*';

      await expect(assertCommandPolicy(CMD.RUN)).rejects.toThrow('errors.agent.commandBlocked');
      expect(mockAuditLog).not.toHaveBeenCalled();
    });

    it('name-list matches the target cluster and rejects others', async () => {
      mockIsAgent.mockReturnValue(true);
      mockIsOverrideLegitimate.mockReturnValue(true);
      process.env.REDIACC_ALLOW_CLUSTER_OPS = 'prod,edge';

      await expect(
        assertCommandPolicy(CMD.CLUSTER_MIGRATE, undefined, 'prod')
      ).resolves.not.toThrow();
      await expect(
        assertCommandPolicy(CMD.CLUSTER_MIGRATE, undefined, 'edge')
      ).resolves.not.toThrow();
      await expect(assertCommandPolicy(CMD.CLUSTER_MIGRATE, undefined, 'staging')).rejects.toThrow(
        'errors.agent.clusterOpBlocked'
      );
    });

    it('a name-list override does NOT unlock a different cluster even if legitimate', async () => {
      mockIsAgent.mockReturnValue(true);
      mockIsOverrideLegitimate.mockReturnValue(true);
      process.env.REDIACC_ALLOW_CLUSTER_OPS = 'prod';

      await expect(assertCommandPolicy(CMD.CLUSTER_FORK, undefined, 'other')).rejects.toThrow(
        'errors.agent.clusterOpBlocked'
      );
      expect(mockAuditLog).not.toHaveBeenCalled();
    });
  });

  describe('validateRemotePath', () => {
    it('accepts valid relative paths', () => {
      expect(() => validateRemotePath('data')).not.toThrow();
      expect(() => validateRemotePath('data/subdir')).not.toThrow();
      expect(() => validateRemotePath('.')).not.toThrow();
      expect(() => validateRemotePath('./data')).not.toThrow();
    });

    it('rejects ../ traversal', () => {
      expect(() => validateRemotePath('../etc')).toThrow('errors.sync.pathTraversalBlocked');
      expect(() => validateRemotePath('data/../../etc')).toThrow(
        'errors.sync.pathTraversalBlocked'
      );
      expect(() => validateRemotePath('..')).toThrow('errors.sync.pathTraversalBlocked');
    });

    it('rejects absolute paths', () => {
      expect(() => validateRemotePath('/etc/passwd')).toThrow('errors.sync.absolutePathBlocked');
      expect(() => validateRemotePath('/var/run')).toThrow('errors.sync.absolutePathBlocked');
    });
  });

  describe('policy consistency', () => {
    it('every forkBlocked entry also has grandGuard', () => {
      for (const [cmd, policy] of COMMAND_POLICIES) {
        if (policy.forkBlocked) {
          expect(policy.grandGuard, `${cmd} is forkBlocked but not grandGuard`).toBe(true);
        }
      }
    });

    it('all CMD values are unique', () => {
      const values = Object.values(CMD);
      expect(new Set(values).size).toBe(values.length);
    });

    it('every CMD value has a policy entry', () => {
      for (const [key, value] of Object.entries(CMD)) {
        expect(COMMAND_POLICIES.has(value), `${key} (${value}) missing from COMMAND_POLICIES`).toBe(
          true
        );
      }
    });
  });
});
