import { expect, test } from '@playwright/test';
import {
  ACCOUNT_SERVER,
  accountPrereqs,
  bothChannels,
  type CliEnvelope,
  DS,
  engineVerbPresent,
  ensureDatastore,
  localHelp,
  loginCli,
  M1,
  M2,
  type ProvisionedRepo,
  parseSnapshotRecord,
  provisionRepo,
  registerMachines,
  restoreLedger,
  seam,
  workers,
} from '../src/utils/backup/chunkCliHarness';
import {
  type BackupManifest,
  type BackupUsage,
  chunkVerbs,
  incrementalViolations,
  manifestChainViolations,
  type SnapshotRecord,
  snapshotRecordViolations,
  usageViolations,
  verbIsRegistered,
} from '../src/utils/backupStorage';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';
import { CliRunner } from '../src/utils/CliRunner';
import {
  announcePrerequisites,
  type PrerequisiteVerdict,
  resolvePrerequisites,
} from '../src/utils/declaredSkip';

/**
 * Suite 26 — the chunk-store backup path from the CLI and the control plane.
 *
 * THREE tiers, split by what each one needs to exist:
 *
 *   ACCOUNT tier — an account server and an api token carrying `backup:read`.
 *     No VMs. Drives `rdc backup usage` / `rdc backup manifests` and the
 *     over-quota surface, using the server's own `/test/seed-backup-ledger`
 *     seam to plant byte counts instead of uploading real data.
 *   ENGINE tier — that PLUS a two-worker fleet PLUS a renet that registers the
 *     chunk-store run verb. Seed upload, incremental upload, deep verify, and
 *     the quota refusal. Runnable since `renet backup snapshot` landed
 *     (2026-08-14).
 *   RESTORE tier — that PLUS a download path, which landed 2026-08-14
 *     (`renet backup restore`). Kept separate precisely so the engine tier
 *     going green never implies the restore was proven.
 *
 * ## Fail-closed, and probed rather than claimed
 *
 * Each tier resolves through `declaredSkip`: present -> run, absent WITH a
 * declared reason -> loud skip on stderr, absent with no declaration -> RED.
 * The engine and restore tiers do NOT take a version string or an env var as
 * evidence that a verb exists: they execute `renet backup --help` against the
 * local binary the harness deploys, and their first test re-runs that probe on
 * the MACHINE. A tier that lit up because someone exported a variable could go
 * green on a fleet that cannot run it.
 *
 * Both tiers' argv is now FACT, read off the built binary. The engine tier:
 * `--repo --datastore --cell-bytes --parallelism --bwlimit --dry-run
 * --reseed`. The restore tier: `--repo --datastore --lineage --at
 * --parallelism --bwlimit --dry-run`, confirmed 2026-08-14 when the download
 * verb landed. Nothing in this file is derived from the design any more.
 *
 * ## The repository comes from the CLI, because only the CLI licenses it
 *
 * Every tier that touches a repo creates it with `rdc repo create`, never with
 * the bridge's `repository_create`. This is not a style choice and it is what
 * kept this suite from EVER running: `renet backup snapshot` and `renet backup
 * restore` both load the installed repository license first and refuse without
 * one ("no installed repository license: no license data"), and the only thing
 * that installs one is the CLI's `ensureRepoLicenseForProvisioning`
 * (local-executor.ts). A bridge-created repo has no license, so the seed upload
 * failed before any assertion could run. `CliRunner` therefore runs with
 * `licensing: true` here, and `provisionRepo` VERIFIES the license landed with
 * `renet repository license-status` rather than trusting the exit code.
 *
 * A CLI-created repo also mints its OWN guid, credential and network id, so
 * nothing in this file may assume a fixed guid: all three are read back out of
 * the config file the CLI just wrote.
 *
 * ## Why this file is not in the default CI run
 *
 * The E2E Workers job runs `--fail-on-skip`: a skipped test there is a job
 * failure. Every tier here needs something that job does not have, so the
 * project is gated behind `BACKUP_STORAGE_SUITE=1` and collects nothing in CI
 * rather than skipping loudly inside it. The machine-tier coverage CI DOES run
 * is suite 25, which drives `backup snapshot --dry-run` on the fleet alone.
 *
 * Run it locally with the dedicated config, NOT the base one:
 *   ./run.sh account dev                       # gateway + portal
 *   BACKUP_STORAGE_SUITE=1 REDIACC_ACCOUNT_SERVER=http://<host>:<port> \
 *     E2E_ACCOUNT_API_TOKEN=<token with backup:read> VM_WORKERS="11 12" \
 *     npx playwright test --config playwright.backup-storage.config.ts
 *
 * The base config's globalSetup resets the VMs and then runs `renet datastore
 * init --force` on every worker, which DESTROYS every repository on the fleet —
 * including ones other sessions are using. This suite provisions everything it
 * needs itself, so its config drops that setup. See the config file's header.
 */

const stamp = Date.now();

/** Own config namespace: suites 23/24 must not see these mutations. */
const CFG = 'e2e-backup';

/**
 * How many EXTRA cells one small filesystem write may dirty.
 *
 * Measured on this fleet 2026-08-15: a single 4 KiB `dd` into a 1 GiB
 * ext4-in-LUKS repo moved 5 cells of 4 MiB — the data block plus the journal
 * and the group metadata, which sit at fixed offsets far from it. Eight is that
 * measurement with headroom, and it is still a BOUND: the seed of the same repo
 * is 19 cells, so a full re-upload dressed up as an incremental fails it.
 */
const FS_METADATA_CELLS = 8;

const accountVerdict: PrerequisiteVerdict = resolvePrerequisites({
  label: 'backup control plane (ACCOUNT tier)',
  declareVar: 'E2E_EXPECT_NO_ACCOUNT_SERVER',
  prerequisites: accountPrereqs,
});

const restoreVerb = chunkVerbs().restore;
const restoreVerbPresent = restoreVerb.length > 0 && verbIsRegistered(localHelp, restoreVerb);

const engineVerdict: PrerequisiteVerdict = resolvePrerequisites({
  label: 'chunk-store upload engine (ENGINE tier)',
  declareVar: 'E2E_EXPECT_NO_CHUNK_ENGINE',
  prerequisites: [
    ...accountPrereqs,
    {
      name: 'VM_WORKERS (two worker VMs)',
      satisfied: workers.length >= 2,
      how: 'bring the fleet up with two workers: `VM_WORKERS="11 12" ./rdc.sh ops up`',
    },
    {
      name: `the local renet registers \`${chunkVerbs().run}\``,
      satisfied: engineVerbPresent,
      how:
        'build renet (`cd private/renet && ./build.sh dev`) so the harness has a binary that ' +
        'registers the chunk-store run verb, or point E2E_CHUNK_BACKUP_VERB at its real argv if ' +
        'it was renamed. Check by hand: `private/renet/bin/renet backup --help`',
    },
  ],
});

/**
 * The restore tier is SEPARATE, and it is separate on purpose.
 *
 * Seed, incremental, deep verify and the quota refusal became runnable the day
 * `renet backup snapshot` landed. Restore lagged it by hours, arriving as its
 * own verb rather than as `backup pull --at`: that flag still refuses by name
 * and points here, because `backup pull` is TierRepoLicenseFull and restore is
 * TierNone — gating disaster recovery behind a licence tier would let an
 * expired subscription lock a customer out of their own backed-up data.
 *
 * The separation stays even though both tiers are now runnable. Byte-identical
 * cross-machine restore is the most load-bearing claim in this program, so it
 * gets its own gate rather than riding a tier that is otherwise green — a
 * mostly-green tier would imply the restore was proven.
 */
const restoreVerdict: PrerequisiteVerdict = resolvePrerequisites({
  label: 'byte-identical restore (RESTORE tier)',
  declareVar: 'E2E_EXPECT_NO_CHUNK_RESTORE',
  prerequisites: [
    ...accountPrereqs,
    {
      name: 'VM_WORKERS (two worker VMs)',
      satisfied: workers.length >= 2,
      how: 'bring the fleet up with two workers: `VM_WORKERS="11 12" ./rdc.sh ops up`',
    },
    {
      name: 'E2E_CHUNK_RESTORE_VERB (the download path, which renet now has)',
      satisfied: restoreVerbPresent,
      how:
        'the chunk-store DOWNLOAD engine has landed (`renet backup restore`, pkg/chunkstore/' +
        'download.go + restore.go), so this defaults to "backup restore" and needs no export. ' +
        'Unsatisfied here means the DEPLOYED binary predates it. Rebuild and redeploy renet. ' +
        'Check: `private/renet/bin/renet backup --help`',
    },
  ],
});

/** POST a test-mode seam on the account server (dev/TEST_MODE only). */

// --------------------------------------------------------------------------- ACCOUNT tier — usage arithmetic, the manifest index, and the quota surface ---------------------------------------------------------------------------

test.describe
  .serial('rdc backup control plane @cli @backup', () => {
    if (accountVerdict.kind === 'undeclared') {
      test('ACCOUNT tier prerequisites are missing and undeclared', () => {
        expect(() => announcePrerequisites(accountVerdict)).not.toThrow();
      });
    } else {
      const gate = announcePrerequisites(accountVerdict);
      test.skip(gate.skip, gate.reason);
      test.setTimeout(300_000);

      let cli: CliRunner;
      let subscriptionId = '';
      let quotaBytes = 0;

      /**
       * `-o json` wraps every payload in the standard CLI envelope
       * ({ success, command, data, ... } — output.ts formatJson), so the usage
       * row lives under `.data`. Reading it from the top level (which this
       * suite did) yields `undefined` for every field, and the first assertion
       * to notice is `subscriptionId` — reported as an empty usage row rather
       * than as a shape mistake.
       */
      const readUsage = async (): Promise<BackupUsage> => {
        const { result, json } = await cli.runJson<CliEnvelope<BackupUsage>>(['backup', 'usage']);
        expect(result.code, `backup usage: ${result.stderr.slice(-600)}`).toBe(0);
        expect(
          json?.data,
          `backup usage printed no JSON payload:\n${result.stdout.slice(0, 400)}`
        ).toBeDefined();
        return json!.data as BackupUsage;
      };

      test.beforeAll(async () => {
        cli = await loginCli(CFG);
      });

      /** The planted lineage row, zeroed in afterAll so it leaves no residue. */
      const plantedLineage = `aaaaaaaa-0000-4000-8000-${String(stamp).slice(-12)}`;

      test.afterAll(async () => {
        // Retire the planted lineage FIRST, then recompute the aggregate from what is left — the other order would fold the planted bytes back in.
        await seam('seed-backup-ledger', {
          subscriptionId,
          storedBytes: 0,
          chunkCount: 0,
          overLimit: false,
          lineages: [
            {
              lineageGuid: plantedLineage,
              storedBytes: 0,
              chunkCount: 0,
              logicalBytes: 0,
            },
          ],
        }).catch(() => undefined);
        await restoreLedger(cli, subscriptionId);
      });

      test('1. `backup usage` returns a row that adds up', async () => {
        const usage = await readUsage();
        subscriptionId = usage.subscriptionId;
        quotaBytes = usage.quotaBytes;
        expect(subscriptionId, 'usage carried no subscription id').not.toBe('');
        // The quota is the only lever in this feature; a row that does not add up is a row somebody is billed against.
        expect(usageViolations(usage), 'the usage row is internally inconsistent').toEqual([]);
        expect(quotaBytes, 'every subscription has a quota, the free one included').toBeGreaterThan(
          0
        );
      });

      test('2. planted usage above the quota surfaces as OVER LIMIT', async () => {
        // The ledger seam plants bytes without uploading any: the quota surface is what is under test, not the uploader.
        //
        // The aggregate has to be planted ON TOP of the lineage rows this subscription already holds, not instead of them. The seam overwrites the aggregate row but leaves per-lineage rows alone, so an aggregate of exactly `over` on an account that has ever uploaded anything makes the parts exceed the whole — `usageViolations` reports it, correctly, as a ledger that disagrees with
        // itself, and the test fails on its own seeding rather than on the surface it is testing.
        const baseline = await readUsage();
        const others = baseline.lineages.filter((l) => l.lineageGuid !== plantedLineage);
        const otherBytes = others.reduce((sum, l) => sum + l.storedBytes, 0);
        const otherChunks = others.reduce((sum, l) => sum + l.chunkCount, 0);
        const over = quotaBytes + 4096;
        const plantedBytes = over - otherBytes;
        expect(plantedBytes, 'the account already exceeds its quota for real').toBeGreaterThan(0);

        const seeded = await seam('seed-backup-ledger', {
          subscriptionId,
          storedBytes: over,
          chunkCount: otherChunks + 7,
          overLimit: true,
          lineages: [
            {
              lineageGuid: plantedLineage,
              storedBytes: plantedBytes,
              chunkCount: 7,
              logicalBytes: plantedBytes * 2,
            },
          ],
        });
        expect(seeded.status, 'the seed-backup-ledger seam is not mounted').toBe(200);

        const usage = await readUsage();
        expect(usage.storedBytes, 'the seeded bytes did not reach the ledger').toBe(over);
        expect(usage.overLimit, 'usage over the quota did not report OVER LIMIT').toBe(true);
        expect(usageViolations(usage), 'the over-limit row is inconsistent').toEqual([]);

        // The human surface says it too, not only the JSON. `-o table` is REQUIRED, not decoration: with --output left at its default the CLI auto-selects json for a non-TTY stdout (cli.ts resolveOutputFormat), and a spawned CLI never has one — so the bare call this used to make could only ever return json, and the assertion could only ever fail.
        const table = await cli.run(['-o', 'table', 'backup', 'usage']);
        expect(table.code).toBe(0);
        expect(bothChannels(table)).toContain('OVER LIMIT');
      });

      test('3. control: seeding back under the quota clears it', async () => {
        // Without this, a client that hard-coded overLimit (or a server that never clears the flag) would pass test 2.
        const under = Math.max(0, Math.floor(quotaBytes / 4));
        const seeded = await seam('seed-backup-ledger', {
          subscriptionId,
          storedBytes: under,
          chunkCount: 2,
          overLimit: false,
          // Retire the row test 2 planted, or the parts still exceed the whole.
          lineages: [
            {
              lineageGuid: plantedLineage,
              storedBytes: 0,
              chunkCount: 0,
              logicalBytes: 0,
            },
          ],
        });
        expect(seeded.status).toBe(200);

        const usage = await readUsage();
        expect(usage.storedBytes).toBe(under);
        expect(usage.overLimit, 'the over-limit flag never clears').toBe(false);
        expect(usageViolations(usage), 'the cleared row is inconsistent').toEqual([]);
        const table = await cli.run(['-o', 'table', 'backup', 'usage']);
        expect(bothChannels(table)).not.toContain('OVER LIMIT');
      });

      test('4. `backup manifests` returns a well-formed index', async () => {
        const { result, json } = await cli.runJson<CliEnvelope<{ manifests: BackupManifest[] }>>([
          'backup',
          'manifests',
        ]);
        expect(result.code, `backup manifests: ${result.stderr.slice(-600)}`).toBe(0);
        expect(json?.data?.manifests, 'no manifests array in the response').toBeDefined();
        // The index is ACCOUNT-wide, so it interleaves lineages and only the per-lineage slices are chains. Checking the mixed list would fail on any account holding two repos — which is every real one.
        const byLineage = new Map<string, BackupManifest[]>();
        for (const m of json?.data?.manifests ?? []) {
          byLineage.set(m.lineageGuid, [...(byLineage.get(m.lineageGuid) ?? []), m]);
        }
        for (const [lineageGuid, chain] of byLineage) {
          // Empty is a legitimate answer; a malformed chain is not.
          expect(
            manifestChainViolations(chain),
            `lineage ${lineageGuid} is not a valid chain`
          ).toEqual([]);
        }
      });

      test('5. the usage route is authenticated, not merely undocumented', async () => {
        const res = await fetch(`${ACCOUNT_SERVER}/account/api/v1/backups/usage`, {
          headers: { Authorization: 'Bearer not-a-real-token' },
        });
        expect(res.status, 'a garbage bearer read the subscription usage').toBeGreaterThanOrEqual(
          400
        );
        expect(res.status).toBeLessThan(500);
      });
    }
  });

// --------------------------------------------------------------------------- ENGINE tier — seed, incremental, verify, restore, quota refusal ---------------------------------------------------------------------------

test.describe
  .serial('chunk-store upload engine @cli @backup @engine', () => {
    if (engineVerdict.kind === 'undeclared') {
      test('ENGINE tier prerequisites are missing and undeclared', () => {
        expect(() => announcePrerequisites(engineVerdict)).not.toThrow();
      });
    } else {
      const gate = announcePrerequisites(engineVerdict);
      if (gate.skip) {
        // The declared-skip banner prints the OPERATOR's reason and the unmet prerequisite names; this adds the standing next step, so a reader does not have to rediscover what the tier wants.
        process.stderr.write(
          [
            '',
            `  The run verb exists (\`renet ${chunkVerbs().run}\`). What this tier still needs is`,
            '  an account server and a two-worker fleet, because seed and incremental',
            '  uploads move real bytes through a real control plane:',
            '',
            '    ./run.sh account dev     # note the gateway port it prints',
            '    BACKUP_STORAGE_SUITE=1 REDIACC_ACCOUNT_SERVER=http://127.0.0.1:<port> \\',
            '      E2E_ACCOUNT_API_TOKEN=<token with backup:read> VM_WORKERS="11 12" \\',
            '      npx playwright test tests/26-backup-storage-cli.test.ts',
            '',
            '  Test 0 re-verifies the verb ON THE MACHINE before anything else runs.',
            '',
          ].join('\n')
        );
      }
      test.skip(gate.skip, gate.reason);
      test.setTimeout(1_800_000);

      const verbs = chunkVerbs();
      const REPO_NAME = `e2ebk-engine-${String(stamp).slice(-8)}`;
      // A write at a known offset in a known cell: the incremental's upload volume is then a BOUND, not a vibe. It is a bound on the FILESYSTEM's write, so FS_METADATA_CELLS widens it by the measured metadata cost.
      const WRITE_OFFSET = 8 * 1024 * 1024;
      const WRITE_LENGTH = 4096;

      let cli: CliRunner;
      let w1: BridgeTestRunner;
      let repo: ProvisionedRepo;
      let lineage = '';
      let seedManifest: BackupManifest | undefined;
      let subscriptionId = '';

      const manifests = async (): Promise<BackupManifest[]> => {
        const { result, json } = await cli.runJson<CliEnvelope<{ manifests: BackupManifest[] }>>([
          'backup',
          'manifests',
        ]);
        expect(result.code, `backup manifests: ${result.stderr.slice(-600)}`).toBe(0);
        return (json?.data?.manifests ?? []).filter((m) => !lineage || m.lineageGuid === lineage);
      };

      /**
       * Run the chunk-store engine on worker 1 for this repo.
       *
       * Flags verified against the built binary, not guessed: `--repo` is a
       * repeatable GUID filter and `--datastore` is the datastore root
       * (`renet backup snapshot --help`).
       */
      const runEngine = async (runner: BridgeTestRunner) =>
        runner.executeViaBridge(
          `sudo renet ${verbs.run} --repo "${repo.guid}" --datastore "${DS}"`
        );

      /** Mount, write through the filesystem, unmount. */
      const churn = async (fileName: string, dd: string): Promise<void> => {
        const mounted = await w1.repositoryMount(repo.guid, repo.credential, DS, repo.networkId);
        expect(
          mounted.code,
          `mounting ${repo.guid}: ${w1.getCombinedOutput(mounted).slice(-800)}`
        ).toBe(0);
        const write = await w1.executeViaBridge(
          `sudo dd if=/dev/urandom of="${DS}/mounts/${repo.guid}/${fileName}" ${dd} conv=notrunc status=none && sync`
        );
        expect(write.code, `planting the write: ${w1.getCombinedOutput(write)}`).toBe(0);
        const unmounted = await w1.repositoryUnmount(repo.guid, DS);
        expect(
          unmounted.code,
          `unmounting ${repo.guid}: ${w1.getCombinedOutput(unmounted).slice(-800)}`
        ).toBe(0);
      };

      /** The verb's own records for this run, parsed from stdout alone. */
      const recordsOf = (result: { stdout: string }): SnapshotRecord[] =>
        result.stdout.split('\n').flatMap((line) => {
          const record = parseSnapshotRecord(line);
          return record ? [record] : [];
        });

      test.beforeAll(async () => {
        w1 = BridgeTestRunner.forWorker(1);
        cli = await loginCli(CFG);
        // This suite does not call resetWorkerState itself, so it depends on whichever suite ran before it (project order is fixed by playwright.config.ts, not by shard/grep order -- console worklist ea76a8c5) not having wiped the shared worker's datastore. Cheap when already ready; re-runs `renet setup` only after a wipe. ensureDatastore below is a DIFFERENT check (registers the named datastore pool with the CLI), not a substitute for this.
        await w1.ensureDatastoreReady(DS);
        await ensureDatastore(w1, M1);
        await registerMachines(cli);
        repo = await provisionRepo(cli, w1, REPO_NAME, M1);
        // A grand repo is its own lineage, and test 1 checks that claim against the verb's own record rather than leaving it an assumption.
        lineage = repo.guid;

        const usage = await cli.runJson<CliEnvelope<BackupUsage>>(['backup', 'usage']);
        subscriptionId = usage.json?.data?.subscriptionId ?? '';
      });

      test.afterAll(async () => {
        // Test 4 leaves the subscription OVER LIMIT, which refuses every upload on the account — the restore tier's own seed included.
        await restoreLedger(cli, subscriptionId);
        await cli.run(['repo', 'delete', REPO_NAME, '-y']).catch(() => undefined);
      });

      test('0. the run verb is really registered ON THE MACHINE', async () => {
        // The tier's prerequisite probed the LOCAL binary; this probes the one the fleet actually runs. They differ whenever a deploy did not land, and without this the failure would surface as an unknown-command error in test 1 and be read as a broken upload.
        const help = await w1.executeViaBridge('renet backup --help 2>&1 || true');
        const text = w1.getCombinedOutput(help);
        expect(
          verbIsRegistered(text, verbs.run),
          `the fleet's renet does not register \`${verbs.run}\`. Its backup subcommands are:\n${text.slice(-1200)}`
        ).toBe(true);
      });

      test('1. the seed upload commits exactly one full manifest', async () => {
        const before = await manifests();
        const run = await runEngine(w1);
        expect(run.code, `seed run: ${w1.getCombinedOutput(run).slice(-800)}`).toBe(0);

        // The verb's own report first: it is what a scheduled run leaves in the journal and what an operator reads, and it must agree with the server's index rather than being checked instead of it.
        const records = recordsOf(run);
        expect(records.length, `no snapshot record on stdout:\n${run.stdout.slice(-800)}`).toBe(1);
        expect(snapshotRecordViolations(records[0])).toEqual([]);
        expect(records[0].status).toBe('stored');
        expect(records[0].chunksUploaded, 'the seed uploaded no chunks').toBeGreaterThan(0);
        expect(records[0].parentSnapshotId ?? '', 'a seed cannot have a parent').toBe('');
        // The lineage the rest of this tier FILTERS on, taken from the verb rather than assumed: the object keys namespace on the grand guid the license carries, and a grand repo being its own lineage is a property of `repo create`, not a law.
        expect(records[0].lineage, 'the snapshot recorded a different lineage').toBe(lineage);

        const after = await manifests();
        expect(after.length, 'the seed committed no manifest').toBe(before.length + 1);
        seedManifest = after[0];
        expect(
          seedManifest.snapshotId,
          'the committed manifest is not the snapshot the verb reported'
        ).toBe(records[0].snapshotId);
        expect(seedManifest.parentSnapshotId ?? null, 'the seed is not a full manifest').toBeNull();
        expect(seedManifest.addedBytes, 'the seed uploaded nothing').toBeGreaterThan(0);
        expect(seedManifest.addedChunkCount).toBeGreaterThan(0);
        expect(manifestChainViolations(after)).toEqual([]);
      });

      test('2. an incremental after a known write sends only the cells it touched', async () => {
        expect(seedManifest, 'test 1 did not produce a seed').toBeDefined();
        // A 4 KiB write inside one cell. Everything else in the FILE is untouched; ext4 still moves its own metadata, which is what FS_METADATA_CELLS below accounts for.
        await churn('churn.bin', `bs=${WRITE_LENGTH} count=1 seek=${WRITE_OFFSET / WRITE_LENGTH}`);

        const run = await runEngine(w1);
        expect(run.code, `incremental run: ${w1.getCombinedOutput(run).slice(-800)}`).toBe(0);

        const records = recordsOf(run);
        expect(records.length).toBe(1);
        expect(snapshotRecordViolations(records[0])).toEqual([]);
        // Cell-scoped at the RECORD level as well: the machine asked the server about a handful of hashes, not about the whole inventory.
        expect(records[0].chunksUploaded, 'the incremental uploaded nothing').toBeGreaterThan(0);
        expect(
          records[0].chunksUploaded,
          'the incremental re-uploaded the whole image'
        ).toBeLessThan(records[0].chunksAsked);
        expect(records[0].parentSnapshotId, 'the incremental is not a delta').toBe(
          seedManifest!.snapshotId
        );

        const after = await manifests();
        const incremental = after[0];
        expect(incremental.snapshotId).not.toBe(seedManifest!.snapshotId);
        // The whole economic claim of the design, as a bound rather than a comparison: a full re-upload passes "smaller than the seed" whenever the seed was bigger, and fails this.
        expect(
          incrementalViolations({
            seed: seedManifest!,
            incremental,
            writeOffset: WRITE_OFFSET,
            writeLength: WRITE_LENGTH,
            filesystemMetadataCells: FS_METADATA_CELLS,
          }),
          'the incremental is not cell-scoped'
        ).toEqual([]);
        expect(manifestChainViolations(after)).toEqual([]);
      });

      test('3. `rdc backup verify --deep` re-hashes every cell and finds no drift', async () => {
        // A repo REF, not a guid: `backup verify <repo-ref>` takes name[:tag] [@machine] and resolves the guid itself.
        const result = await cli.run(['backup', 'verify', REPO_NAME, '--deep']);
        expect(result.code, `backup verify --deep: ${bothChannels(result).slice(-800)}`).toBe(0);
        expect(bothChannels(result)).toContain('verified');
      });

      test('4. an upload over quota is refused BEFORE any bytes move', async () => {
        // Quota is enforced at grant-mint time by design: the refusal must arrive before I/O is spent, and it must name the quota rather than failing as a generic 4xx somewhere deep in the uploader.
        const usage = await cli.runJson<CliEnvelope<BackupUsage>>(['backup', 'usage']);
        expect(subscriptionId).not.toBe('');
        const res = await seam('seed-backup-ledger', {
          subscriptionId,
          storedBytes: (usage.json?.data?.quotaBytes ?? 0) + 1,
          chunkCount: usage.json?.data?.chunkCount ?? 1,
          overLimit: true,
        });
        expect(res.status).toBe(200);

        // Churn something so the run has work to do; without it a refusal and a no-op look the same.
        await churn('churn2.bin', 'bs=1M count=4');

        const before = (await manifests()).length;
        const run = await runEngine(w1);

        // Exit 16 specifically, not merely non-zero: the verb reserves it for a quota refusal because the operator action is different (prune or upgrade, not debug), and a code nobody asserts degrades to noise.
        expect(
          run.code,
          `expected the quota exit code 16, got ${run.code}:\n${w1.getCombinedOutput(run).slice(-800)}`
        ).toBe(16);

        const records = recordsOf(run);
        expect(records.length).toBe(1);
        expect(records[0].status, 'an over-quota run must say so in its record').toBe(
          'quota-refused'
        );
        expect(snapshotRecordViolations(records[0])).toEqual([]);
        // Refused BEFORE any I/O: quota is enforced at grant-mint time, so a refusal that had already moved bytes would mean the enforcement point moved.
        expect(records[0].bytesUploaded, 'bytes moved despite the quota refusal').toBe(0);
        expect(records[0].grantsMinted, 'a grant was minted despite the quota refusal').toBe(0);
        expect((await manifests()).length, 'the refused run still committed a manifest').toBe(
          before
        );

        // Hand the account back before the next test, which needs to upload.
        await restoreLedger(cli, subscriptionId);
      });

      test('5. a second run of an UNCHANGED repository still succeeds', async () => {
        // The single most common run there is: the hourly backup of a repo nobody wrote to. `renet backup snapshot --help` promises it — "Unchanged repositories still emit a record, with chunksUploaded 0" — and pkg/chunkstore/uploader.go:142-160 has a branch specifically for it, whose comment says getting it wrong "breaks the single most common run there is".
        //
        // Nothing above covers it: every other run in this tier has work to do, so the branch is only ever taken in steady state. This test is last in the block on purpose — it is the one most likely to be red, and a serial block stops at its first failure.
        const withWork = await runEngine(w1);
        expect(
          withWork.code,
          `the run that clears the pending churn: ${w1.getCombinedOutput(withWork).slice(-800)}`
        ).toBe(0);

        const unchanged = await runEngine(w1);
        const records = recordsOf(unchanged);
        expect(records.length).toBe(1);
        expect(
          records[0].status,
          `an unchanged repository must still store a snapshot, not fail: ${records[0].reason ?? ''}`
        ).toBe('stored');
        expect(records[0].chunksUploaded, 'an unchanged repo uploaded chunks').toBe(0);
        expect(records[0].bytesUploaded, 'an unchanged repo moved bytes').toBe(0);
        expect(snapshotRecordViolations(records[0])).toEqual([]);
        expect(
          unchanged.code,
          `an unchanged repository's snapshot exited ${unchanged.code}: ${w1
            .getCombinedOutput(unchanged)
            .slice(-800)}`
        ).toBe(0);
      });
    }
  });

// --------------------------------------------------------------------------- RESTORE tier — the claim the whole feature rests on ---------------------------------------------------------------------------

test.describe
  .serial('byte-identical restore @cli @backup @restore', () => {
    if (restoreVerdict.kind === 'undeclared') {
      test('RESTORE tier prerequisites are missing and undeclared', () => {
        expect(() => announcePrerequisites(restoreVerdict)).not.toThrow();
      });
    } else {
      const gate = announcePrerequisites(restoreVerdict);
      if (gate.skip) {
        process.stderr.write(
          [
            '',
            '  The download path EXISTS (`renet backup restore`, pkg/chunkstore/',
            '  download.go + restore.go, landed 2026-08-14). Unsatisfied here means',
            '  the binary this harness resolves predates it, or the account server /',
            '  fleet prerequisites are missing:',
            '',
            '    ./run.sh account dev     # note the gateway URL it prints',
            '    BACKUP_STORAGE_SUITE=1 REDIACC_ACCOUNT_SERVER=http://<host>:<port> \\',
            '      E2E_ACCOUNT_API_TOKEN=<token with backup:read> VM_WORKERS="11 12" \\',
            '      npx playwright test --config playwright.backup-storage.config.ts',
            '',
            '  Test 1 re-verifies the verb ON THE MACHINE before the restore runs.',
            '',
          ].join('\n')
        );
      }
      test.skip(gate.skip, gate.reason);
      test.setTimeout(1_800_000);

      const verbs = chunkVerbs();
      const REPO_NAME = `e2ebk-restore-${String(stamp).slice(-8)}`;
      const RESTORED_NAME = `${REPO_NAME}-back`;

      let cli: CliRunner;
      let w1: BridgeTestRunner;
      let w2: BridgeTestRunner;
      let repo: ProvisionedRepo;

      const imageSha = async (runner: BridgeTestRunner, guid: string): Promise<string> => {
        const r = await runner.executeViaBridge(
          `sudo sha256sum "${DS}/repositories/${guid}" | cut -d' ' -f1`
        );
        return (/[0-9a-f]{64}/.exec(runner.getCombinedOutput(r)) ?? [''])[0];
      };

      test.beforeAll(async () => {
        w1 = BridgeTestRunner.forWorker(1);
        w2 = BridgeTestRunner.forWorker(2);
        cli = await loginCli(CFG);
        // This suite does not call resetWorkerState itself, so it depends on whichever suite ran before it (project order is fixed by playwright.config.ts, not by shard/grep order -- console worklist ea76a8c5) not having wiped either shared worker's datastore. Cheap when already ready; re-runs `renet setup` only after a wipe.
        await w1.ensureDatastoreReady(DS);
        await w2.ensureDatastoreReady(DS);
        // BOTH workers: the restore lands on w2, and a w2 with no datastore has nowhere to assemble the image. This tier used to init only w1 and then restore onto w2.
        await ensureDatastore(w1, M1);
        await ensureDatastore(w2, M2);
        await registerMachines(cli);
        repo = await provisionRepo(cli, w1, REPO_NAME, M1);

        // A seed to restore FROM. If this fails the restore assertion below would pass vacuously against an empty lineage.
        const seed = await w1.executeViaBridge(
          `sudo renet ${verbs.run} --repo "${repo.guid}" --datastore "${DS}"`
        );
        expect(
          seed.code,
          `seeding for the restore: ${w1.getCombinedOutput(seed).slice(-800)}`
        ).toBe(0);
      });

      test.afterAll(async () => {
        await cli.run(['repo', 'delete', RESTORED_NAME, '-y']).catch(() => undefined);
        await cli.run(['repo', 'delete', REPO_NAME, '-y']).catch(() => undefined);
      });

      test('1. the restore verb is really registered on the machine', async () => {
        const help = await w2.executeViaBridge('renet backup --help 2>&1 || true');
        const text = w2.getCombinedOutput(help);
        expect(
          verbIsRegistered(text, verbs.restore),
          `the fleet's renet does not register \`${verbs.restore}\`:\n${text.slice(-1200)}`
        ).toBe(true);
      });

      test('2. a restore onto a second machine is BYTE-IDENTICAL to the source', async () => {
        const sourceSha = await imageSha(w1, repo.guid);
        expect(sourceSha, 'could not hash the source image').toMatch(/^[0-9a-f]{64}$/);

        const { json } = await cli.runJson<CliEnvelope<{ manifests: BackupManifest[] }>>([
          'backup',
          'manifests',
        ]);
        const latest = (json?.data?.manifests ?? []).filter((m) => m.lineageGuid === repo.guid)[0];
        expect(latest, 'no committed manifest to restore from').toBeDefined();

        // Driven through the CLI rather than through `renet backup restore` on the machine, for a reason the raw call hides: restore resolves a repository license as its credential AND its address book (backup_restore.go resolveRestoreLicense), and when the target guid has none it falls back to ANY license installed on that machine. On a shared fleet the raw call therefore
        // succeeds by borrowing a license some other suite left behind, and passes for a reason the test never states. `rdc backup restore` issues the target's own license first, which is also the path a user actually has.
        //
        // The CLI keeps the SOURCE guid on the target (it is the same image), so both hashes below address the same file name on two machines.
        const restore = await cli.run([
          'backup',
          'restore',
          `${REPO_NAME}@${M1}`,
          '--as',
          RESTORED_NAME,
          '-m',
          M2,
          '--at',
          latest.snapshotId,
        ]);
        expect(restore.code, `backup restore: ${bothChannels(restore).slice(-1200)}`).toBe(0);

        // Not "the restore exited 0", not "the mount has the file": the ciphertext image on the second machine is the same bytes as the first. Everything else in this program is bookkeeping around this one equality.
        expect(
          await imageSha(w2, repo.guid),
          'the restored image is not byte-identical to the source'
        ).toBe(sourceSha);
      });
    }
  });
