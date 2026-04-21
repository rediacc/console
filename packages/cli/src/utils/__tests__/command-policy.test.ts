import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../services/config-resources.js', () => ({
  configService: {
    getRepository: vi.fn(),
  },
}));

vi.mock('../agent-guard.js', () => ({
  isAgentEnvironment: vi.fn(),
}));

vi.mock('../process-ancestry.js', () => ({
  isOverrideLegitimate: vi.fn(() => true),
}));

vi.mock('../../i18n/index.js', () => ({
  t: (key: string, params?: Record<string, unknown>) => {
    if (params) return `${key}:${JSON.stringify(params)}`;
    return key;
  },
}));

import { configService } from '../../services/config-resources.js';
import type { RepositoryConfig } from '../../types/index.js';
import { isAgentEnvironment } from '../agent-guard.js';
import {
  assertCommandPolicy,
  CMD,
  COMMAND_POLICIES,
  validateRemotePath,
} from '../command-policy.js';

const mockIsAgent = vi.mocked(isAgentEnvironment);
const mockGetRepo = vi.mocked(configService.getRepository);

describe('command-policy', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    delete process.env.REDIACC_ALLOW_GRAND_REPO;
  });

  afterEach(() => {
    delete process.env.REDIACC_ALLOW_GRAND_REPO;
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
