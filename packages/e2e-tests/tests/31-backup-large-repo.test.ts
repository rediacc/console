import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test } from '@playwright/test';
import {
  accountPrereqs,
  bothChannels,
  type CliEnvelope,
  DS,
  engineVerbPresent,
  ensureDatastore,
  loginCli,
  M1,
  type ProvisionedRepo,
  parseSnapshotRecord,
  provisionRepo,
  registerMachines,
  restoreLedger,
  workers,
} from '../src/utils/backup/chunkCliHarness';
import {
  GIB,
  INCR_TIME_CAP_MS,
  incrTimeBudgetMs,
  largeRepoBudgetViolations,
  MIB,
  type SnapshotMeasure,
} from '../src/utils/backup/largeRepoBudget';
import { type BackupUsage, chunkVerbs, type SnapshotRecord } from '../src/utils/backupStorage';
import type { CliRunner } from '../src/utils/CliRunner';
import {
  announcePrerequisites,
  type PrerequisiteVerdict,
  resolvePrerequisites,
} from '../src/utils/declaredSkip';
import { RenetFunctionsTestRunner } from '../src/utils/renet-functions/RenetFunctionsTestRunner';

/**
 * Suite 31 -- large-repository performance (box K10 of agent/plans/PLAN-backup-program.md).
 *
 * Seeds `K10_SEED_GB` GiB (default 50) into one repository, snapshots it, changes 256 MiB, snapshots again, and holds the second snapshot to a byte, no-rehash and time budget (`largeRepoBudgetViolations`). Then it deletes the backup anchor, writes 4 MiB and snapshots a third time: that control MUST rehash and MUST breach the budget, which proves the budget separates "anchor used" from "anchor lost" at this size, every night.
 *
 * Only the standalone nightly `.github/workflows/ct-backup-perf.yml` runs it: a worker VM with a 100 GB disk, a backup plane and an account server. It is not a ct-tests.yml job because check:ci-lane-budget prices jobs from pull_request samples and caps them at 15 minutes.
 *
 * Run it with:
 *   BACKUP_LARGE_REPO_SUITE=1 VM_WORKERS="11" VM_DSK=100 REDIACC_ACCOUNT_SERVER=http://<host>:<port> \
 *     E2E_ACCOUNT_API_TOKEN=<token with backup:read> \
 *     E2E_BACKUP_S3_KEY=<store key> E2E_BACKUP_S3_SECRET=<store secret> \
 *     npx playwright test --config playwright.backup-large-repo.config.ts
 */

const stamp = Date.now();
const CFG = 'e2e-backup-large-repo';

const SEED_GB = Math.max(1, Number.parseInt(process.env.K10_SEED_GB ?? '50', 10) || 50);
const SEED_BYTES = SEED_GB * GIB;
const CHANGE_BYTES = 256 * MIB;
const CONTROL_BYTES = 4 * MIB;
/** The repository's image size and the datastore that holds it. */
const REPO_SIZE = `${SEED_GB + 10}G`;
const DATASTORE_SIZE = `${SEED_GB + 30}G`;
/** Quota the account must admit: the seed plus the change and the control, with margin. */
const QUOTA_NEEDED = SEED_BYTES + 5 * GIB;
/** A seed that takes longer than this is a hang, not a slow runner. */
const SEED_HANG_MS = 3_600_000;
/** Free GiB the worker's datastore filesystem must show before anything is written. */
const FREE_GIB_NEEDED = SEED_GB + 15;

const RESULT_DIR = path.resolve(__dirname, '..', 'reports', 'backup-large-repo-k10');

const verdict: PrerequisiteVerdict = resolvePrerequisites({
  label: 'large-repository incremental budget (K10)',
  declareVar: 'E2E_EXPECT_NO_LARGE_REPO',
  prerequisites: [
    ...accountPrereqs,
    {
      name: 'VM_WORKERS (one worker VM)',
      satisfied: workers.length >= 1,
      how: 'bring the fleet up with a 100 GB worker disk: `VM_DSK=100 ./rdc.sh ops up --basic`',
    },
    {
      name: `the local renet registers \`${chunkVerbs().run}\``,
      satisfied: engineVerbPresent,
      how: 'build renet (`cd private/renet && ./build.sh dev`). Check: `private/renet/bin/renet backup --help`',
    },
  ],
});

const measure = (r: SnapshotRecord): SnapshotMeasure => ({
  durationMs: r.durationMs,
  bytesUploaded: r.bytesUploaded,
  chunksUploaded: r.chunksUploaded,
  rehashReason: r.rehashReason,
});

test.describe
  .serial('large repository incremental budget @cli @backup @large-repo', () => {
    if (verdict.kind === 'undeclared') {
      test('large-repo prerequisites are missing and undeclared', () => {
        expect(() => announcePrerequisites(verdict)).not.toThrow();
      });
    } else {
      const gate = announcePrerequisites(verdict);
      if (gate.skip) {
        process.stderr.write(
          [
            '',
            '  Declared skip: the prerequisites are missing. This suite is run by the nightly',
            '  ct-backup-perf.yml; to run by hand see the header of tests/31-backup-large-repo.test.ts.',
            '',
          ].join('\n')
        );
      }
      test.skip(gate.skip, gate.reason);
      test.setTimeout(6_000_000);

      const verbs = chunkVerbs();
      const REPO_NAME = `e2ebk-large-${String(stamp).slice(-8)}`;

      let cli: CliRunner;
      let w1: RenetFunctionsTestRunner;
      let repo: ProvisionedRepo;
      let subscriptionId = '';
      let seed: SnapshotRecord | undefined;
      let incr: SnapshotRecord | undefined;
      let control: SnapshotRecord | undefined;

      const anchorPath = (): string => `${DS}/.chunk-anchors/${repo.guid}`;

      const snapshot = async (): Promise<SnapshotRecord> => {
        const run = await w1.executeViaBridge(
          `sudo renet ${verbs.run} --repo "${repo.guid}" --datastore "${DS}"`,
          SEED_HANG_MS
        );
        expect(run.code, `snapshot run: ${w1.getCombinedOutput(run).slice(-800)}`).toBe(0);
        const record = run.stdout
          .split('\n')
          .map((line) => parseSnapshotRecord(line))
          .find((r): r is SnapshotRecord => r !== undefined);
        expect(record, `no snapshot record on stdout:\n${run.stdout.slice(-800)}`).toBeDefined();
        const found = record as SnapshotRecord;
        expect(found.status, `snapshot status (${found.reason ?? 'no reason'})`).toBe('stored');
        expect(found.cellBytes, 'the record carries no cellBytes').toBeGreaterThan(0);
        return found;
      };

      /** Mount, run the writes through the filesystem, sync, unmount. */
      const withMount = async (writes: () => Promise<void>): Promise<void> => {
        const mounted = await w1.repositoryMount(repo.guid, repo.credential, DS, repo.networkId);
        expect(
          mounted.code,
          `mounting ${repo.guid}: ${w1.getCombinedOutput(mounted).slice(-800)}`
        ).toBe(0);
        try {
          await writes();
          const synced = await w1.executeViaBridge('sync');
          expect(synced.code, `sync: ${w1.getCombinedOutput(synced)}`).toBe(0);
        } finally {
          const unmounted = await w1.repositoryUnmount(repo.guid, DS);
          expect(
            unmounted.code,
            `unmounting ${repo.guid}: ${w1.getCombinedOutput(unmounted).slice(-800)}`
          ).toBe(0);
        }
      };

      const mountedPath = (file: string): string => `${DS}/mounts/${repo.guid}/${file}`;

      test.beforeAll(async () => {
        w1 = RenetFunctionsTestRunner.forWorker(1);
        cli = await loginCli(CFG);
        await w1.ensureDatastoreReady(DS);
        await ensureDatastore(w1, M1, DATASTORE_SIZE);
        await registerMachines(cli);
        const usage = await cli.runJson<CliEnvelope<BackupUsage>>(['backup', 'usage']);
        subscriptionId = usage.json?.data?.subscriptionId ?? '';
        repo = await provisionRepo(cli, w1, REPO_NAME, M1, REPO_SIZE);
      });

      test.afterAll(async () => {
        await restoreLedger(cli, subscriptionId);
        await cli.run(['repo', 'delete', REPO_NAME, '-y']).catch(() => undefined);
      });

      test('1. preflight: the account quota and the worker disk admit the seed', async () => {
        const usage = await cli.runJson<CliEnvelope<BackupUsage>>(['backup', 'usage']);
        const quota = usage.json?.data?.quotaBytes ?? 0;
        expect(
          quota - (usage.json?.data?.usedBytes ?? 0),
          `backup quota ${quota} bytes cannot admit a ${SEED_GB} GiB seed (needs ${QUOTA_NEEDED}); raise the test subscription's quota`
        ).toBeGreaterThanOrEqual(QUOTA_NEEDED);
        const df = await w1.executeViaBridge(`df -B1G --output=avail "${DS}" | tail -1`);
        const freeGib = Number.parseInt(df.stdout.trim(), 10);
        expect(
          freeGib,
          `the worker shows ${df.stdout.trim() || 'no'} GiB free under ${DS}; the seed needs ${FREE_GIB_NEEDED}. Start the fleet with VM_DSK=100: ${bothChannels(df).slice(-300)}`
        ).toBeGreaterThanOrEqual(FREE_GIB_NEEDED);
      });

      test('2. seed: the full image uploads', async () => {
        await withMount(async () => {
          // Zeros are fast to write, and under LUKS-XTS every sector's ciphertext is unique, so no cell dedupes against another.
          for (let i = 0; i < SEED_GB; i++) {
            const dd = await w1.executeViaBridge(
              `sudo dd if=/dev/zero of="${mountedPath(`seed-${i}.bin`)}" bs=4M count=256 oflag=direct status=none`,
              900_000
            );
            expect(dd.code, `seeding file ${i}: ${w1.getCombinedOutput(dd).slice(-400)}`).toBe(0);
          }
        });
        seed = await snapshot();
        process.stderr.write(`K10 seed: ${JSON.stringify(measure(seed))}\n`);
        expect(seed.durationMs, 'the seed took over the hang ceiling').toBeLessThan(SEED_HANG_MS);
        expect(
          seed.bytesUploaded,
          'the seed uploaded under 98% of what was written'
        ).toBeGreaterThanOrEqual(0.98 * SEED_BYTES);
      });

      test('3. incremental: 256 MiB of change meets the byte, no-rehash and time budgets', async () => {
        expect(seed, 'the seed test did not produce a record').toBeDefined();
        await withMount(async () => {
          const dd = await w1.executeViaBridge(
            `sudo dd if=/dev/urandom of="${mountedPath('k10-delta.bin')}" bs=1M count=256 oflag=direct status=none`,
            600_000
          );
          expect(dd.code, `writing the delta: ${w1.getCombinedOutput(dd).slice(-400)}`).toBe(0);
        });
        incr = await snapshot();
        process.stderr.write(`K10 incremental: ${JSON.stringify(measure(incr))}\n`);
        const violations = largeRepoBudgetViolations({
          seed: measure(seed as SnapshotRecord),
          incr: measure(incr),
          changedBytes: CHANGE_BYTES,
          seedBytes: SEED_BYTES,
          cellBytes: incr.cellBytes ?? 0,
        });
        expect(violations, `the incremental missed its budget:\n${violations.join('\n')}`).toEqual(
          []
        );
      });

      test('4. control: with the anchor deleted the snapshot rehashes and breaches the budget', async () => {
        expect(seed && incr, 'the earlier tests did not produce records').toBeTruthy();
        const removed = await w1.executeViaBridge(`sudo rm -f "${anchorPath()}"`);
        expect(removed.code, `removing the anchor: ${w1.getCombinedOutput(removed)}`).toBe(0);
        const gone = await w1.executeViaBridge(
          `sudo test -e "${anchorPath()}" && echo present || echo absent`
        );
        expect(
          gone.stdout,
          `the anchor ${anchorPath()} is still there; the control did not plant`
        ).toContain('absent');
        await withMount(async () => {
          const dd = await w1.executeViaBridge(
            `sudo dd if=/dev/urandom of="${mountedPath('k10-control.bin')}" bs=1M count=4 oflag=direct status=none`,
            120_000
          );
          expect(dd.code, `writing the control: ${w1.getCombinedOutput(dd).slice(-400)}`).toBe(0);
        });
        control = await snapshot();
        process.stderr.write(`K10 control: ${JSON.stringify(measure(control))}\n`);
        expect(control.rehashReason, 'deleting the anchor did not force a rehash').toBeTruthy();
        const violations = largeRepoBudgetViolations({
          seed: measure(seed as SnapshotRecord),
          incr: measure(control),
          changedBytes: CONTROL_BYTES,
          seedBytes: SEED_BYTES,
          cellBytes: control.cellBytes ?? 0,
        });
        expect(
          violations.length,
          'the budget did not flag the anchor-deleted snapshot'
        ).toBeGreaterThan(0);
        const budgetMs = incrTimeBudgetMs((seed as SnapshotRecord).durationMs);
        expect(
          control.durationMs,
          `the rehash took ${control.durationMs} ms, not over the ${budgetMs} ms incremental budget (cap ${INCR_TIME_CAP_MS}); the budget does not separate the two cases on this runner`
        ).toBeGreaterThan(budgetMs);
      });

      test('5. the result is recorded', () => {
        expect(seed && incr && control, 'a measurement is missing').toBeTruthy();
        const result = {
          seedGb: SEED_GB,
          seed: measure(seed as SnapshotRecord),
          incr: measure(incr as SnapshotRecord),
          control: measure(control as SnapshotRecord),
          incrBudgetMs: incrTimeBudgetMs((seed as SnapshotRecord).durationMs),
          runner: {
            workers: workers.join(' '),
            vmDsk: process.env.VM_DSK ?? '',
            node: process.version,
          },
        };
        mkdirSync(RESULT_DIR, { recursive: true });
        writeFileSync(
          path.join(RESULT_DIR, 'k10-result.json'),
          `${JSON.stringify(result, null, 2)}\n`
        );
        process.stderr.write(`K10_RESULT ${JSON.stringify(result)}\n`);
      });
    }
  });
