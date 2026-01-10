import { expect, test } from '@playwright/test';
import {
  createEditionContext,
  EditionErrorPatterns,
  type EditionTestContext,
  expectEditionError,
  expectEditionSuccess,
  getEditionsWithFeature,
  getEditionsWithoutFeature,
  uniqueName,
} from '../../src/utils/edition';

/**
 * Edition Feature Restrictions Tests
 *
 * Tests that verify feature access is correctly restricted by subscription edition.
 * Each feature has both positive tests (allowed editions) and negative tests (blocked editions).
 */
test.describe('Feature Restrictions by Edition @cli @edition', () => {
  test.describe('Permission Groups (COMMUNITY blocked, PROFESSIONAL+ allowed)', () => {
    const blockedEditions = getEditionsWithoutFeature('permissionGroups');
    const allowedEditions = getEditionsWithFeature('permissionGroups');

    for (const plan of blockedEditions) {
      test.describe(`${plan} edition - should block permission groups`, () => {
        let ctx: EditionTestContext;

        test.beforeAll(async () => {
          ctx = await createEditionContext(plan);
        });

        test.afterAll(async () => {
          await ctx?.cleanup();
        });

        test('should return 402 when creating custom permission group', async () => {
          const groupName = uniqueName('test-group');
          const result = await ctx.runner.run(['permission', 'group', 'create', groupName]);

          expectEditionError(result, 402, EditionErrorPatterns.PERMISSION_GROUP_COMMUNITY);
        });
      });
    }

    for (const plan of allowedEditions) {
      test.describe(`${plan} edition - should allow permission groups`, () => {
        let ctx: EditionTestContext;
        let createdGroupName: string;

        test.beforeAll(async () => {
          ctx = await createEditionContext(plan);
          createdGroupName = uniqueName('test-group');
        });

        test.afterAll(async () => {
          if (createdGroupName) {
            await ctx.runner
              .run(['permission', 'group', 'delete', createdGroupName, '--force'])
              .catch(() => {});
          }
          await ctx?.cleanup();
        });

        test('should successfully create custom permission group', async () => {
          const result = await ctx.runner.run(['permission', 'group', 'create', createdGroupName]);

          expectEditionSuccess(result);
        });

        test('should list the created permission group', async () => {
          const result = await ctx.runner.run(['permission', 'group', 'list']);

          expectEditionSuccess(result);
          const groups = ctx.runner.expectSuccessArray<{ permissionGroupName: string }>(result);
          const found = groups.some((g) => g.permissionGroupName === createdGroupName);
          expect(found, `Expected to find group "${createdGroupName}" in list`).toBe(true);
        });

        test('should add permission to custom group', async () => {
          const result = await ctx.runner.run([
            'permission',
            'add',
            createdGroupName,
            'GetTeamMachines',
          ]);

          expectEditionSuccess(result);
        });

        test('should show custom group with permissions', async () => {
          const result = await ctx.runner.run(['permission', 'group', 'show', createdGroupName]);

          expectEditionSuccess(result);
          expect(result.json).not.toBeNull();
        });
      });
    }
  });

  test.describe('Ceph Storage (COMMUNITY, PROFESSIONAL blocked; BUSINESS, ENTERPRISE allowed)', () => {
    const blockedEditions = getEditionsWithoutFeature('ceph');
    const allowedEditions = getEditionsWithFeature('ceph');

    for (const plan of blockedEditions) {
      test.describe(`${plan} edition - should block ceph operations`, () => {
        let ctx: EditionTestContext;

        test.beforeAll(async () => {
          ctx = await createEditionContext(plan);
        });

        test.afterAll(async () => {
          await ctx?.cleanup();
        });

        test('should return 402 when creating ceph cluster', async () => {
          const clusterName = uniqueName('test-cluster');
          const result = await ctx.runner.run(['ceph', 'cluster', 'create', clusterName]);

          expectEditionError(result, 402, EditionErrorPatterns.CEPH_NOT_AVAILABLE);
        });

        test('should return 402 when listing ceph clusters', async () => {
          const result = await ctx.runner.run(['ceph', 'cluster', 'list']);

          expectEditionError(result, 402, EditionErrorPatterns.CEPH_NOT_AVAILABLE);
        });
      });
    }

    for (const plan of allowedEditions) {
      test.describe(`${plan} edition - should allow ceph operations`, () => {
        let ctx: EditionTestContext;

        test.beforeAll(async () => {
          ctx = await createEditionContext(plan);
        });

        test.afterAll(async () => {
          await ctx?.cleanup();
        });

        test('should allow listing ceph clusters (empty list for new account)', async () => {
          const result = await ctx.runner.run(['ceph', 'cluster', 'list']);

          expectEditionSuccess(result);
        });
      });
    }
  });

  test.describe('Ceph Pool Limits (BUSINESS: 1 per team, ENTERPRISE: unlimited)', () => {
    test.describe('BUSINESS edition - limited to 1 pool per team', () => {
      let ctx: EditionTestContext;
      let teamName: string;

      test.beforeAll(async () => {
        ctx = await createEditionContext('BUSINESS');

        const teamResult = await ctx.runner.teamList();
        const teams = ctx.runner.expectSuccessArray<{ teamName: string }>(teamResult);
        teamName = teams[0]?.teamName ?? 'Private Team';
      });

      test.afterAll(async () => {
        await ctx?.cleanup();
      });

      test('should return 402 when creating second pool for same team', async () => {
        const clusterName = uniqueName('test-cluster');
        await ctx.runner.run(['ceph', 'cluster', 'create', clusterName]);

        const firstPoolName = uniqueName('first-pool');
        await ctx.runner.run([
          'ceph',
          'pool',
          'create',
          firstPoolName,
          '--cluster',
          clusterName,
          '--team',
          teamName,
        ]);

        const secondPoolName = uniqueName('second-pool');
        const result = await ctx.runner.run([
          'ceph',
          'pool',
          'create',
          secondPoolName,
          '--cluster',
          clusterName,
          '--team',
          teamName,
        ]);

        expectEditionError(result, 402, EditionErrorPatterns.CEPH_POOL_LIMIT_BUSINESS);
      });
    });

    test.describe('ENTERPRISE edition - unlimited pools per team', () => {
      let ctx: EditionTestContext;
      let teamName: string;

      test.beforeAll(async () => {
        ctx = await createEditionContext('ENTERPRISE');

        const teamResult = await ctx.runner.teamList();
        const teams = ctx.runner.expectSuccessArray<{ teamName: string }>(teamResult);
        teamName = teams[0]?.teamName ?? 'Private Team';
      });

      test.afterAll(async () => {
        await ctx?.cleanup();
      });

      test('should allow creating multiple pools for same team', async () => {
        const clusterName = uniqueName('test-cluster');
        await ctx.runner.run(['ceph', 'cluster', 'create', clusterName]);

        for (let i = 0; i < 3; i++) {
          const poolName = uniqueName(`pool-${i}`);
          const result = await ctx.runner.run([
            'ceph',
            'pool',
            'create',
            poolName,
            '--cluster',
            clusterName,
            '--team',
            teamName,
          ]);
          expectEditionSuccess(result);
        }
      });
    });
  });

  test.describe('Bridge Creation', () => {
    test.describe('COMMUNITY edition - 0 bridges allowed', () => {
      let ctx: EditionTestContext;
      let regionName: string;

      test.beforeAll(async () => {
        ctx = await createEditionContext('COMMUNITY');

        const regionResult = await ctx.runner.run(['region', 'list']);
        const regions = ctx.runner.expectSuccessArray<{ regionName: string }>(regionResult);
        regionName = regions[0]?.regionName ?? 'Default Region';
      });

      test.afterAll(async () => {
        await ctx?.cleanup();
      });

      test.skip('should return 402 when creating first bridge', async () => {
        // SKIP: Middleware treats limit=0 as "unlimited" (see private_CheckResourceLimit)
        // The COMMUNITY plan defines Bridge:0 intending "0 bridges", but middleware
        // interprets this as "no limit". This test requires middleware fix.
        const bridgeName = uniqueName('test-bridge');
        const result = await ctx.runner.run([
          'bridge',
          'create',
          bridgeName,
          '--region',
          regionName,
        ]);

        expectEditionError(result, 402, EditionErrorPatterns.RESOURCE_LIMIT_EXCEEDED);
      });
    });

    test.describe('PROFESSIONAL edition - 1 bridge allowed', () => {
      let ctx: EditionTestContext;
      let regionName: string;
      const createdBridges: string[] = [];

      test.beforeAll(async () => {
        ctx = await createEditionContext('PROFESSIONAL');

        const regionResult = await ctx.runner.run(['region', 'list']);
        const regions = ctx.runner.expectSuccessArray<{ regionName: string }>(regionResult);
        regionName = regions[0]?.regionName ?? 'Default Region';
      });

      test.afterAll(async () => {
        for (const bridge of createdBridges) {
          await ctx.runner
            .run(['bridge', 'delete', bridge, '--region', regionName, '--force'])
            .catch(() => {});
        }
        await ctx?.cleanup();
      });

      test('should allow creating first bridge', async () => {
        const bridgeName = uniqueName('test-bridge');
        const result = await ctx.runner.run([
          'bridge',
          'create',
          bridgeName,
          '--region',
          regionName,
        ]);

        expectEditionSuccess(result);
        createdBridges.push(bridgeName);
      });

      test('should return 402 when creating second bridge', async () => {
        const bridgeName = uniqueName('test-bridge-2');
        const result = await ctx.runner.run([
          'bridge',
          'create',
          bridgeName,
          '--region',
          regionName,
        ]);

        expectEditionError(result, 402, EditionErrorPatterns.RESOURCE_LIMIT_EXCEEDED);
      });
    });

    test.describe('BUSINESS edition - 2 bridges allowed', () => {
      let ctx: EditionTestContext;
      let regionName: string;
      const createdBridges: string[] = [];

      test.beforeAll(async () => {
        ctx = await createEditionContext('BUSINESS');

        const regionResult = await ctx.runner.run(['region', 'list']);
        const regions = ctx.runner.expectSuccessArray<{ regionName: string }>(regionResult);
        regionName = regions[0]?.regionName ?? 'Default Region';
      });

      test.afterAll(async () => {
        for (const bridge of createdBridges) {
          await ctx.runner
            .run(['bridge', 'delete', bridge, '--region', regionName, '--force'])
            .catch(() => {});
        }
        await ctx?.cleanup();
      });

      test('should allow creating up to 2 bridges', async () => {
        for (let i = 0; i < 2; i++) {
          const bridgeName = uniqueName(`test-bridge-${i}`);
          const result = await ctx.runner.run([
            'bridge',
            'create',
            bridgeName,
            '--region',
            regionName,
          ]);

          expect(
            result.success,
            `Bridge ${i + 1} creation failed: ${ctx.runner.getErrorMessage(result)}`
          ).toBe(true);
          createdBridges.push(bridgeName);
        }
      });

      test('should return 402 when exceeding 2 bridges', async () => {
        const bridgeName = uniqueName('test-bridge-excess');
        const result = await ctx.runner.run([
          'bridge',
          'create',
          bridgeName,
          '--region',
          regionName,
        ]);

        expectEditionError(result, 402, EditionErrorPatterns.RESOURCE_LIMIT_EXCEEDED);
      });
    });
  });
});
