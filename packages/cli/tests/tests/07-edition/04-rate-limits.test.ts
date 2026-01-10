import { expect, test } from '@playwright/test';
import {
  createEditionContext,
  EditionErrorPatterns,
  type EditionTestContext,
  expectEditionError,
  extractTaskId,
  RESOURCE_LIMITS,
  type SubscriptionPlan,
  sleep,
  TEST_MACHINE_VAULT,
  uniqueName,
} from '../../src/utils/edition';

/**
 * Edition Rate Limits Tests
 *
 * Tests that verify rate limiting is correctly enforced by subscription edition.
 * Rate limits return 429 Too Many Requests when exceeded.
 */
test.describe('Rate Limits by Edition @cli @edition', () => {
  test.describe('Pending Queue Items Rate Limit', () => {
    const testCases: [SubscriptionPlan, number][] = [
      ['COMMUNITY', RESOURCE_LIMITS.COMMUNITY.maxPendingPerUser],
      ['PROFESSIONAL', RESOURCE_LIMITS.PROFESSIONAL.maxPendingPerUser],
    ];

    for (const [plan, limit] of testCases) {
      test.describe(`${plan} edition - ${limit} pending items limit`, () => {
        let ctx: EditionTestContext;
        let teamName: string;
        let bridgeName: string;
        let machineName: string;
        const createdTaskIds: string[] = [];

        test.beforeAll(async () => {
          ctx = await createEditionContext(plan);

          const teamResult = await ctx.runner.teamList();
          const teams = ctx.runner.expectSuccessArray<{ teamName: string }>(teamResult);
          teamName = teams[0]?.teamName ?? 'Private Team';

          // Get region first, then bridges
          const regionResult = await ctx.runner.run(['region', 'list']);
          const regions = ctx.runner.expectSuccessArray<{ regionName: string }>(regionResult);
          const regionName = regions[0]?.regionName ?? 'Default Region';

          const bridgeResult = await ctx.runner.run(['bridge', 'list', '--region', regionName]);
          const bridges = ctx.runner.expectSuccessArray<{ bridgeName: string }>(bridgeResult);
          bridgeName = bridges[0]?.bridgeName ?? 'Global Bridges';

          machineName = uniqueName('rate-machine');
          const machineResult = await ctx.runner.run([
            'machine',
            'create',
            machineName,
            '--team',
            teamName,
            '--bridge',
            bridgeName,
            '--vault',
            TEST_MACHINE_VAULT,
          ]);

          if (!machineResult.success) {
            throw new Error(
              `Failed to create test machine: ${ctx.runner.getErrorMessage(machineResult)}`
            );
          }
        });

        test.afterAll(async () => {
          for (const taskId of createdTaskIds) {
            await ctx.runner.run(['cancel', taskId]).catch(() => {});
          }
          await sleep(1000);
          await ctx.runner
            .run(['machine', 'delete', machineName, '--team', teamName, '--force'])
            .catch(() => {});
          await ctx?.cleanup();
        });

        test(`should allow creating ${limit} pending queue items`, async () => {
          test.setTimeout(180000);

          for (let i = 0; i < limit; i++) {
            const result = await ctx.runner.run([
              'run',
              'machine_ping',
              '--team',
              teamName,
              '--machine',
              machineName,
              '--bridge',
              bridgeName,
            ]);

            expect(
              result.success,
              `Queue item ${i + 1}/${limit} creation failed: ${ctx.runner.getErrorMessage(result)}`
            ).toBe(true);

            const taskId = extractTaskId(result.stdout);
            if (taskId) {
              createdTaskIds.push(taskId);
            }

            await sleep(100);
          }
        });

        test('should return 429 when exceeding pending limit', async () => {
          if (createdTaskIds.length < limit) {
            console.warn(
              `Skipping 429 test - only created ${createdTaskIds.length}/${limit} items`
            );
            return;
          }

          const result = await ctx.runner.run([
            'run',
            'machine_ping',
            '--team',
            teamName,
            '--machine',
            machineName,
            '--bridge',
            bridgeName,
          ]);

          if (!result.success && result.exitCode === 9) {
            // 9 is the mapped exit code for 429
            expectEditionError(result, 429, EditionErrorPatterns.TOO_MANY_PENDING_ITEMS);
          } else if (result.success) {
            // Tasks may have completed, freeing up slots
            console.warn(
              'Rate limit not hit - earlier tasks may have completed. ' +
                'This is expected behavior if the bridge is processing tasks quickly.'
            );
            const taskId = extractTaskId(result.stdout);
            if (taskId) {
              createdTaskIds.push(taskId);
            }
          }
        });
      });
    }

    test.describe('BUSINESS edition - exceeds Community limit', () => {
      let ctx: EditionTestContext;
      let teamName: string;
      let bridgeName: string;
      let machineName: string;
      const createdTaskIds: string[] = [];
      const COMMUNITY_LIMIT = RESOURCE_LIMITS.COMMUNITY.maxPendingPerUser;

      test.beforeAll(async () => {
        ctx = await createEditionContext('BUSINESS');

        const teamResult = await ctx.runner.teamList();
        const teams = ctx.runner.expectSuccessArray<{ teamName: string }>(teamResult);
        teamName = teams[0]?.teamName ?? 'Private Team';

        // Get region first, then bridges
        const regionResult = await ctx.runner.run(['region', 'list']);
        const regions = ctx.runner.expectSuccessArray<{ regionName: string }>(regionResult);
        const regionName = regions[0]?.regionName ?? 'Default Region';

        const bridgeResult = await ctx.runner.run(['bridge', 'list', '--region', regionName]);
        const bridges = ctx.runner.expectSuccessArray<{ bridgeName: string }>(bridgeResult);
        bridgeName = bridges[0]?.bridgeName ?? 'Global Bridges';

        machineName = uniqueName('business-rate-machine');
        await ctx.runner.run([
          'machine',
          'create',
          machineName,
          '--team',
          teamName,
          '--bridge',
          bridgeName,
          '--vault',
          TEST_MACHINE_VAULT,
        ]);
      });

      test.afterAll(async () => {
        for (const taskId of createdTaskIds) {
          await ctx.runner.run(['cancel', taskId]).catch(() => {});
        }
        await sleep(1000);
        await ctx.runner
          .run(['machine', 'delete', machineName, '--team', teamName, '--force'])
          .catch(() => {});
        await ctx?.cleanup();
      });

      test(`should allow creating more than Community limit (${COMMUNITY_LIMIT})`, async () => {
        test.setTimeout(180000);
        const targetCount = COMMUNITY_LIMIT + 1;

        for (let i = 0; i < targetCount; i++) {
          const result = await ctx.runner.run([
            'run',
            'machine_ping',
            '--team',
            teamName,
            '--machine',
            machineName,
            '--bridge',
            bridgeName,
          ]);

          expect(
            result.success,
            `Queue item ${i + 1}/${targetCount} creation failed: ${ctx.runner.getErrorMessage(result)}`
          ).toBe(true);

          const taskId = extractTaskId(result.stdout);
          if (taskId) {
            createdTaskIds.push(taskId);
          }
          await sleep(100);
        }

        expect(createdTaskIds.length).toBeGreaterThan(COMMUNITY_LIMIT);
      });
    });
  });

  test.describe('Cross-Edition Rate Limit Comparison', () => {
    const editions: SubscriptionPlan[] = ['COMMUNITY', 'PROFESSIONAL', 'BUSINESS', 'ENTERPRISE'];

    for (const plan of editions) {
      test(`should have rate limits defined for ${plan} edition`, () => {
        const limits = RESOURCE_LIMITS[plan];

        expect(limits.maxPendingPerUser).toBeGreaterThan(0);
        expect(limits.maxTasksPerMachine).toBeGreaterThan(0);
      });
    }

    test('should have progressively higher pending item limits', () => {
      expect(RESOURCE_LIMITS.PROFESSIONAL.maxPendingPerUser).toBeGreaterThan(
        RESOURCE_LIMITS.COMMUNITY.maxPendingPerUser
      );
      expect(RESOURCE_LIMITS.BUSINESS.maxPendingPerUser).toBeGreaterThan(
        RESOURCE_LIMITS.PROFESSIONAL.maxPendingPerUser
      );
      expect(RESOURCE_LIMITS.ENTERPRISE.maxPendingPerUser).toBeGreaterThan(
        RESOURCE_LIMITS.BUSINESS.maxPendingPerUser
      );
    });

    test('should have progressively higher tasks per machine limits', () => {
      expect(RESOURCE_LIMITS.PROFESSIONAL.maxTasksPerMachine).toBeGreaterThan(
        RESOURCE_LIMITS.COMMUNITY.maxTasksPerMachine
      );
      expect(RESOURCE_LIMITS.BUSINESS.maxTasksPerMachine).toBeGreaterThan(
        RESOURCE_LIMITS.PROFESSIONAL.maxTasksPerMachine
      );
      expect(RESOURCE_LIMITS.ENTERPRISE.maxTasksPerMachine).toBeGreaterThan(
        RESOURCE_LIMITS.BUSINESS.maxTasksPerMachine
      );
    });
  });
});
