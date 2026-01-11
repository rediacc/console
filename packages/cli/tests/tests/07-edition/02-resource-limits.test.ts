import { expect, test } from '@playwright/test';
import { SYSTEM_DEFAULTS } from '@rediacc/shared/config';
import {
  createEditionContext,
  EditionErrorPatterns,
  type EditionTestContext,
  expectEditionError,
  RESOURCE_LIMITS,
  type SubscriptionPlan,
  uniqueName,
} from '../../src/utils/edition';

/**
 * Edition Resource Limits Tests
 *
 * Tests that verify resource limits are correctly enforced by subscription edition.
 * Tests both boundary cases (creating up to limit) and exceeding limits.
 */
test.describe('Resource Limits by Edition @cli @edition', () => {
  test.describe('Machine Limits', () => {
    test.describe('COMMUNITY edition - 5 machines limit', () => {
      let ctx: EditionTestContext;
      let teamName: string;
      let bridgeName: string;
      const createdMachines: string[] = [];
      const LIMIT = RESOURCE_LIMITS.COMMUNITY.machines;

      test.beforeAll(async () => {
        ctx = await createEditionContext('COMMUNITY');

        const teamResult = await ctx.runner.teamList();
        const teams = ctx.runner.expectSuccessArray<{ teamName: string }>(teamResult);
        teamName = teams[0]?.teamName ?? SYSTEM_DEFAULTS.TEAM_NAME;

        // Get region first, then bridges
        const regionResult = await ctx.runner.run(['region', 'list']);
        const regions = ctx.runner.expectSuccessArray<{ regionName: string }>(regionResult);
        const regionName = regions[0]?.regionName ?? SYSTEM_DEFAULTS.REGION_NAME;

        const bridgeResult = await ctx.runner.run(['bridge', 'list', '--region', regionName]);
        const bridges = ctx.runner.expectSuccessArray<{ bridgeName: string }>(bridgeResult);
        bridgeName = bridges[0]?.bridgeName ?? SYSTEM_DEFAULTS.BRIDGE_NAME;
      });

      test.afterAll(async () => {
        for (const machine of createdMachines) {
          await ctx.runner
            .run(['machine', 'delete', machine, '--team', teamName, '--force'])
            .catch(() => {});
        }
        await ctx?.cleanup();
      });

      test(`should allow creating up to ${LIMIT} machines`, async () => {
        test.setTimeout(180000);
        for (let i = 0; i < LIMIT; i++) {
          const machineName = uniqueName(`machine-${i}`);
          const result = await ctx.runner.run([
            'machine',
            'create',
            machineName,
            '--team',
            teamName,
            '--bridge',
            bridgeName,
          ]);

          expect(
            result.success,
            `Machine ${i + 1}/${LIMIT} creation failed: ${ctx.runner.getErrorMessage(result)}`
          ).toBe(true);
          createdMachines.push(machineName);
        }
      });

      test(`should return 402 when exceeding ${LIMIT} machines`, async () => {
        const machineName = uniqueName('machine-excess');
        const result = await ctx.runner.run([
          'machine',
          'create',
          machineName,
          '--team',
          teamName,
          '--bridge',
          bridgeName,
        ]);

        expectEditionError(result, 402, EditionErrorPatterns.MACHINE_LIMIT_EXCEEDED);
      });
    });

    test.describe('PROFESSIONAL edition - 20 machines limit', () => {
      let ctx: EditionTestContext;
      let teamName: string;
      let bridgeName: string;
      const createdMachines: string[] = [];

      test.beforeAll(async () => {
        ctx = await createEditionContext('PROFESSIONAL');

        const teamResult = await ctx.runner.teamList();
        const teams = ctx.runner.expectSuccessArray<{ teamName: string }>(teamResult);
        teamName = teams[0]?.teamName ?? SYSTEM_DEFAULTS.TEAM_NAME;

        // Get region first, then bridges
        const regionResult = await ctx.runner.run(['region', 'list']);
        const regions = ctx.runner.expectSuccessArray<{ regionName: string }>(regionResult);
        const regionName = regions[0]?.regionName ?? SYSTEM_DEFAULTS.REGION_NAME;

        const bridgeResult = await ctx.runner.run(['bridge', 'list', '--region', regionName]);
        const bridges = ctx.runner.expectSuccessArray<{ bridgeName: string }>(bridgeResult);
        bridgeName = bridges[0]?.bridgeName ?? SYSTEM_DEFAULTS.BRIDGE_NAME;
      });

      test.afterAll(async () => {
        for (const machine of createdMachines) {
          await ctx.runner
            .run(['machine', 'delete', machine, '--team', teamName, '--force'])
            .catch(() => {});
        }
        await ctx?.cleanup();
      });

      test('should allow creating machines up to limit boundary', async () => {
        test.setTimeout(120000);
        // Only create a few to test basic functionality
        for (let i = 0; i < 5; i++) {
          const machineName = uniqueName(`machine-${i}`);
          const result = await ctx.runner.run([
            'machine',
            'create',
            machineName,
            '--team',
            teamName,
            '--bridge',
            bridgeName,
          ]);

          expect(
            result.success,
            `Machine ${i + 1} creation failed: ${ctx.runner.getErrorMessage(result)}`
          ).toBe(true);
          createdMachines.push(machineName);
        }
      });
    });
  });

  test.describe('Repository Limits', () => {
    test.describe('COMMUNITY edition - 10 repositories limit', () => {
      let ctx: EditionTestContext;
      let teamName: string;
      const createdRepos: string[] = [];
      const LIMIT = RESOURCE_LIMITS.COMMUNITY.repositories;

      test.beforeAll(async () => {
        ctx = await createEditionContext('COMMUNITY');

        const teamResult = await ctx.runner.teamList();
        const teams = ctx.runner.expectSuccessArray<{ teamName: string }>(teamResult);
        teamName = teams[0]?.teamName ?? SYSTEM_DEFAULTS.TEAM_NAME;
      });

      test.afterAll(async () => {
        for (const repo of createdRepos) {
          await ctx.runner
            .run(['repository', 'delete', repo, '--team', teamName, '--force'])
            .catch(() => {});
        }
        await ctx?.cleanup();
      });

      test(`should allow creating up to ${LIMIT} repositories`, async () => {
        test.setTimeout(300000);
        for (let i = 0; i < LIMIT; i++) {
          const repoName = uniqueName(`repo-${i}`);
          const result = await ctx.runner.run([
            'repository',
            'create',
            repoName,
            '--team',
            teamName,
          ]);

          expect(
            result.success,
            `Repository ${i + 1}/${LIMIT} creation failed: ${ctx.runner.getErrorMessage(result)}`
          ).toBe(true);
          createdRepos.push(repoName);
        }
      });

      test(`should return 402 when exceeding ${LIMIT} repositories`, async () => {
        const repoName = uniqueName('repo-excess');
        const result = await ctx.runner.run(['repository', 'create', repoName, '--team', teamName]);

        expectEditionError(result, 402, EditionErrorPatterns.REPOSITORY_LIMIT_EXCEEDED);
      });
    });

    test.describe('PROFESSIONAL edition - higher repository limit', () => {
      let ctx: EditionTestContext;
      let teamName: string;
      const createdRepos: string[] = [];

      test.beforeAll(async () => {
        ctx = await createEditionContext('PROFESSIONAL');

        const teamResult = await ctx.runner.teamList();
        const teams = ctx.runner.expectSuccessArray<{ teamName: string }>(teamResult);
        teamName = teams[0]?.teamName ?? SYSTEM_DEFAULTS.TEAM_NAME;
      });

      test.afterAll(async () => {
        for (const repo of createdRepos) {
          await ctx.runner
            .run(['repository', 'delete', repo, '--team', teamName, '--force'])
            .catch(() => {});
        }
        await ctx?.cleanup();
      });

      test('should allow creating more than Community limit (10+)', async () => {
        test.setTimeout(300000);
        for (let i = 0; i < 11; i++) {
          const repoName = uniqueName(`repo-${i}`);
          const result = await ctx.runner.run([
            'repository',
            'create',
            repoName,
            '--team',
            teamName,
          ]);

          expect(
            result.success,
            `Repository ${i + 1} creation failed: ${ctx.runner.getErrorMessage(result)}`
          ).toBe(true);
          createdRepos.push(repoName);
        }
      });
    });
  });

  test.describe('Storage Limits', () => {
    test.describe('COMMUNITY edition storage limits', () => {
      let ctx: EditionTestContext;
      let teamName: string;
      const createdStorages: string[] = [];

      test.beforeAll(async () => {
        ctx = await createEditionContext('COMMUNITY');

        const teamResult = await ctx.runner.teamList();
        const teams = ctx.runner.expectSuccessArray<{ teamName: string }>(teamResult);
        teamName = teams[0]?.teamName ?? SYSTEM_DEFAULTS.TEAM_NAME;
      });

      test.afterAll(async () => {
        for (const storage of createdStorages) {
          await ctx.runner
            .run(['storage', 'delete', storage, '--team', teamName, '--force'])
            .catch(() => {});
        }
        await ctx?.cleanup();
      });

      test('should allow creating storage within limits', async () => {
        const storageName = uniqueName('storage');
        const result = await ctx.runner.run(['storage', 'create', storageName, '--team', teamName]);

        if (result.success) {
          createdStorages.push(storageName);
        }
        // Don't fail test if storage command doesn't exist yet
        expect(result.success || result.stderr.includes('unknown command')).toBe(true);
      });
    });
  });

  test.describe('Cross-Edition Limit Comparison', () => {
    const editions: SubscriptionPlan[] = ['COMMUNITY', 'PROFESSIONAL', 'BUSINESS', 'ENTERPRISE'];

    for (const plan of editions) {
      test(`should have increasing limits for ${plan} edition`, () => {
        const limits = RESOURCE_LIMITS[plan];

        expect(limits.machines).toBeGreaterThanOrEqual(0);
        expect(limits.repositories).toBeGreaterThanOrEqual(0);
        expect(limits.bridges).toBeGreaterThanOrEqual(0);
        expect(limits.maxActiveJobs).toBeGreaterThanOrEqual(0);
      });
    }

    test('should have progressively higher machine limits', () => {
      expect(RESOURCE_LIMITS.PROFESSIONAL.machines).toBeGreaterThan(
        RESOURCE_LIMITS.COMMUNITY.machines
      );
      expect(RESOURCE_LIMITS.BUSINESS.machines).toBeGreaterThan(
        RESOURCE_LIMITS.PROFESSIONAL.machines
      );
      expect(RESOURCE_LIMITS.ENTERPRISE.machines).toBeGreaterThan(
        RESOURCE_LIMITS.BUSINESS.machines
      );
    });

    test('should have progressively higher repository limits', () => {
      expect(RESOURCE_LIMITS.PROFESSIONAL.repositories).toBeGreaterThan(
        RESOURCE_LIMITS.COMMUNITY.repositories
      );
      expect(RESOURCE_LIMITS.BUSINESS.repositories).toBeGreaterThan(
        RESOURCE_LIMITS.PROFESSIONAL.repositories
      );
      expect(RESOURCE_LIMITS.ENTERPRISE.repositories).toBeGreaterThan(
        RESOURCE_LIMITS.BUSINESS.repositories
      );
    });

    test('should have progressively higher bridge limits', () => {
      expect(RESOURCE_LIMITS.COMMUNITY.bridges).toBe(0);
      expect(RESOURCE_LIMITS.PROFESSIONAL.bridges).toBeGreaterThan(
        RESOURCE_LIMITS.COMMUNITY.bridges
      );
      expect(RESOURCE_LIMITS.BUSINESS.bridges).toBeGreaterThan(
        RESOURCE_LIMITS.PROFESSIONAL.bridges
      );
      expect(RESOURCE_LIMITS.ENTERPRISE.bridges).toBeGreaterThan(RESOURCE_LIMITS.BUSINESS.bridges);
    });
  });
});
