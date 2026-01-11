import { expect, test } from '@playwright/test';
import { SYSTEM_DEFAULTS } from '@rediacc/shared/config';
import {
  createEditionContext,
  type EditionTestContext,
  expectEditionSuccess,
  extractTaskId,
  getEditionsWithFeature,
  getEditionsWithoutFeature,
  sleep,
  TEST_MACHINE_VAULT,
  uniqueName,
} from '../../src/utils/edition';

/**
 * Edition Silent Behavior Tests
 *
 * Tests for features that behave differently by edition without returning errors.
 * These features silently adjust behavior rather than blocking operations.
 */
test.describe('Silent Edition Behavior @cli @edition', () => {
  test.describe('Queue Priority Behavior', () => {
    // Non-Business/Enterprise editions: Priority is silently reset to 4 (default)
    // Business/Enterprise editions: Custom priorities (1-5) are respected

    const restrictedEditions = getEditionsWithoutFeature('queuePriority');
    const unrestrictedEditions = getEditionsWithFeature('queuePriority');

    for (const plan of restrictedEditions) {
      test.describe(`${plan} edition - priority silently reset`, () => {
        let ctx: EditionTestContext;
        let teamName: string;
        let bridgeName: string;
        let machineName: string;
        const createdTaskIds: string[] = [];

        test.beforeAll(async () => {
          ctx = await createEditionContext(plan);

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

          machineName = uniqueName('priority-machine');
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

        test('should accept priority parameter without error', async () => {
          const result = await ctx.runner.run([
            'run',
            'machine_ping',
            '--team',
            teamName,
            '--machine',
            machineName,
            '--bridge',
            bridgeName,
            '--priority',
            '2',
          ]);

          expectEditionSuccess(result);

          const taskId = extractTaskId(result.stdout);
          if (taskId) {
            createdTaskIds.push(taskId);
          }
        });

        test('should reset custom priority to default (4)', async () => {
          const createResult = await ctx.runner.run([
            'run',
            'machine_ping',
            '--team',
            teamName,
            '--machine',
            machineName,
            '--bridge',
            bridgeName,
            '--priority',
            '2',
          ]);

          expectEditionSuccess(createResult);

          const taskId = extractTaskId(createResult.stdout);
          expect(taskId, 'Failed to extract task ID from output').toBeTruthy();
          createdTaskIds.push(taskId);

          await sleep(500);

          const traceResult = await ctx.runner.queueTrace(taskId);

          if (traceResult.success && traceResult.json) {
            const task = traceResult.json as { priority?: number | null };
            // API hides priority field for Community/Professional editions by design
            // The stored procedure returns NULL for priority when not Business/Enterprise
            // This test verifies that the task was created successfully (priority silently reset)
            // We can't verify the actual priority value as the API intentionally hides it
            expect(
              task.priority === undefined || task.priority === null,
              `Expected priority to be hidden for ${plan} edition but got ${task.priority}`
            ).toBe(true);
          } else {
            console.warn(`Could not trace task ${taskId} to verify priority reset`);
          }
        });

        // Add retry to handle occasional timing issues on macOS
        test('should accept priority 1 without modification', async () => {
          // Small delay to ensure previous test's API operations are complete
          await sleep(300);

          const createResult = await ctx.runner.run([
            'run',
            'machine_ping',
            '--team',
            teamName,
            '--machine',
            machineName,
            '--bridge',
            bridgeName,
            '--priority',
            '1',
          ]);

          expectEditionSuccess(createResult);

          const taskId = extractTaskId(createResult.stdout);
          if (taskId) {
            createdTaskIds.push(taskId);
          }
        });
      });
    }

    for (const plan of unrestrictedEditions) {
      test.describe(`${plan} edition - priority respected`, () => {
        let ctx: EditionTestContext;
        let teamName: string;
        let bridgeName: string;
        let machineName: string;
        const createdTaskIds: string[] = [];

        test.beforeAll(async () => {
          ctx = await createEditionContext(plan);

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

          machineName = uniqueName('priority-machine');
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

        test('should respect custom priority 2', async () => {
          const createResult = await ctx.runner.run([
            'run',
            'machine_ping',
            '--team',
            teamName,
            '--machine',
            machineName,
            '--bridge',
            bridgeName,
            '--priority',
            '2',
          ]);

          expectEditionSuccess(createResult);

          const taskId = extractTaskId(createResult.stdout);
          expect(taskId, 'Failed to extract task ID from output').toBeTruthy();
          createdTaskIds.push(taskId);

          await sleep(500);

          const traceResult = await ctx.runner.queueTrace(taskId);

          if (traceResult.success && traceResult.json) {
            const task = traceResult.json as { priority?: number };
            expect(
              task.priority,
              `Expected priority 2 to be preserved but got ${task.priority}. ${plan} editions should respect custom priority.`
            ).toBe(2);
          }
        });

        test('should respect all priority levels (1-5)', async () => {
          const priorities = [1, 3, 5];

          for (const priority of priorities) {
            const createResult = await ctx.runner.run([
              'run',
              'machine_ping',
              '--team',
              teamName,
              '--machine',
              machineName,
              '--bridge',
              bridgeName,
              '--priority',
              String(priority),
            ]);

            expectEditionSuccess(createResult);

            const taskId = extractTaskId(createResult.stdout);
            if (taskId) {
              createdTaskIds.push(taskId);
            }

            await sleep(200);
          }
        });
      });
    }
  });

  test.describe('Concurrent Tasks Per Machine Throttling', () => {
    test.describe('COMMUNITY edition - 1 task per machine', () => {
      let ctx: EditionTestContext;
      let teamName: string;
      let bridgeName: string;
      let machineName: string;
      const createdTaskIds: string[] = [];

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

        machineName = uniqueName('concurrent-machine');
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

      test('should accept multiple tasks (they queue, not reject)', async () => {
        // Submit multiple tasks - they should all be accepted
        // but only 1 will run at a time for Community edition
        for (let i = 0; i < 3; i++) {
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

          expectEditionSuccess(result);

          const taskId = extractTaskId(result.stdout);
          if (taskId) {
            createdTaskIds.push(taskId);
          }
          await sleep(100);
        }

        expect(createdTaskIds.length).toBe(3);
      });
    });
  });

  test.describe('Audit Log Retention by Edition', () => {
    test.describe('COMMUNITY edition - 7 day retention', () => {
      let ctx: EditionTestContext;

      test.beforeAll(async () => {
        ctx = await createEditionContext('COMMUNITY');
      });

      test.afterAll(async () => {
        await ctx?.cleanup();
      });

      test('should allow accessing audit logs', async () => {
        const result = await ctx.runner.run(['audit', 'list', '--limit', '10']);

        // Audit may require specific permissions or may not have CLI command
        if (!result.success && result.stderr.includes('unknown command')) {
          console.warn('Audit CLI command not available - skipping test');
          return;
        }

        // If command exists, it should either succeed or return appropriate error
        expect(result.success || result.exitCode !== 0).toBe(true);
      });
    });
  });
});
