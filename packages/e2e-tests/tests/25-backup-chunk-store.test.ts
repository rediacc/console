import { expect, test } from '@playwright/test';
import { DEFAULT_DATASTORE_PATH, TEST_PASSWORD, TEST_TEAM, TEST_USER } from '../src/constants';
import {
  chunkVerbs,
  dryRunViolations,
  type SnapshotRecord,
  snapshotRecordViolations,
} from '../src/utils/backupStorage';
import { BridgeTestRunner } from '../src/utils/bridge/BridgeTestRunner';
import {
  announcePrerequisites,
  type PrerequisiteVerdict,
  resolvePrerequisites,
} from '../src/utils/declaredSkip';
import { VaultBuilder } from '../src/utils/vault/VaultBuilder';

/**
 * Suite 25 — the chunk-store backup path as the MACHINE sees it (spec 04).
 *
 * ## What this suite is replacing
 *
 * The existing backup suites verify nothing: suite 10's 17 tests assert only
 * `hasValidCommandSyntax`, which never reads an exit code (its
 * unreachable-machine test passes ON connection failure), and suite 15
 * string-matches generated rclone flags against fabricated credentials. This
 * one reads exit codes and parses the verb's own JSON records.
 *
 * ## What it can prove with a fleet ALONE, and what it deliberately does not
 *
 * Everything here needs a worker VM and nothing else — no account server, no
 * credentials, no bytes leaving the machine. That boundary is what decides
 * which legs live here and which live in suite 26.
 *
 *   1. verify answers `no-backup` for a repo the engine never touched, and
 *      answers it as a RECORD rather than as silence (a reader counting lines
 *      would read silence as healthy);
 *   2. the `level` parameter genuinely reaches the verb — proven by the
 *      refusal of an invalid level, not by a green run at the default;
 *   3. verify with no filter enumerates the datastore, and says so loudly when
 *      there is nothing to enumerate;
 *   4. verify is a READ: it leaves no anchor, no journal, no state that a later
 *      run could mistake for a committed snapshot;
 *   5. `renet backup snapshot --dry-run` plans without a session and writes no
 *      state — the flag promises "no session, no grant, no upload", and a plan
 *      that left an anchor behind would be state a later incremental TRUSTS;
 *   6. exit 16 belongs to quota alone: an ordinary failure exits 1, so the
 *      signal an operator acts on stays meaningful;
 *   7. `backup pull --at` REFUSES, and leaves the repository image
 *      byte-identical. A flag that parsed and silently did nothing would hand
 *      back a restore of the wrong point in time.
 *
 * NOT here, and NOT because it is expensive: there is still no download path.
 * `backup pull --at` refuses (`cmd/renet/backup_pull.go:196`), `pkg/chunkstore`
 * exports no fetch-to-disk function, and `backup_snapshot.go` says so in its
 * own header. Cross-machine byte-identical restore therefore stays authored and
 * dark in suite 26's own tier rather than being approximated here.
 *
 * ## Fail-closed
 *
 * No worker VM and no declaration is a RED, not a skip (`declaredSkip`, the
 * renet `RENET_EXPECT_NO_ACCOUNT_SERVER` precedent). On the E2E Workers legs a
 * worker is always present, so nothing here skips in CI — which the job's
 * `--fail-on-skip` gate requires.
 */

const DS = DEFAULT_DATASTORE_PATH;
const stamp = Date.now();
const workers = (process.env.VM_WORKERS ?? '').trim().split(/\s+/).filter(Boolean);

/**
 * A GUID-named repository, because the engine is GUID-keyed all the way down:
 * journals are `<datastoreId>-<guid>.json`, anchors are `<guid>`, and
 * `chunkstore.EnumerateRepoGUIDs` only counts repository files whose NAME is a
 * UUID (`prune.IsRepoGUID`). rdc names repositories by GUID on a real machine;
 * a human-named repo would be invisible to the enumeration and test 4 would
 * pass for the wrong reason.
 */
const REPO_GUID = `b0c4a5e0-0000-4000-8000-${String(stamp).slice(-12).padStart(12, '0')}`;

const verdict: PrerequisiteVerdict = resolvePrerequisites({
  label: 'chunk-store backup on a machine (suite 25)',
  declareVar: 'E2E_EXPECT_NO_BACKUP_MACHINE',
  prerequisites: [
    {
      name: 'VM_WORKERS (at least one worker VM)',
      satisfied: workers.length >= 1,
      how: 'bring the fleet up: `./rdc.sh ops up --basic` (or `VM_WORKERS="11 12" ./rdc.sh ops up`)',
    },
  ],
});

/** One NDJSON record of `renet backup verify` (cmd/renet/backup_verify.go:14). */
interface VerifyRecord {
  guid: string;
  status: 'verified' | 'mismatch' | 'no-backup' | 'failed';
  reason?: string;
  snapshotId?: string;
  level: string;
  checkedCells: number;
  mismatchedCells?: number[];
}

/**
 * Parse the verb's records out of stdout.
 *
 * Deliberately reads stdout ONLY. The verb writes its records to stdout and
 * its diagnostics to stderr, and a parser fed the combined stream would accept
 * a run whose records never appeared at all.
 */
/**
 * Verify records, from EITHER shape the harness can deliver them in.
 *
 * A bare JSON line is the shape when the verb's stdout reaches the caller
 * untouched. Through `renet functions once` it does not: the executor swallows
 * the verb's stdout and re-emits it inside its own log line as
 * `msg="[backup_verify] {\"guid\":...}"`, on STDERR, with the quotes escaped.
 * This parser used to accept only the first shape, so a record that was
 * produced correctly and printed plainly read as "no verify record" -- the test
 * was looking at the wrong stream for output that was never missing.
 */
function parseVerifyRecords(stdout: string): VerifyRecord[] {
  const records: VerifyRecord[] = [];
  for (const rawLine of stdout.split('\n')) {
    let line = rawLine;
    const wrapped = /msg="\[[a-z_]+\] (\{.*?\})"\s*$/.exec(rawLine.trim());
    if (wrapped) {
      line = wrapped[1].replaceAll('\\"', '"');
    }
    const trimmed = line.trim();
    if (!trimmed.startsWith('{') || !trimmed.includes('"status"')) continue;
    try {
      records.push(JSON.parse(trimmed) as VerifyRecord);
    } catch {
      // Not one of ours: the harness runs the verb with --debug, so the stream
      // also carries the dispatcher's own JSON logging.
    }
  }
  return records;
}

/**
 * Parse `renet backup snapshot` records out of stdout, same discipline as
 * above: stdout only, and only lines that are self-evidently records.
 */
function parseSnapshotRecords(stdout: string): SnapshotRecord[] {
  const records: SnapshotRecord[] = [];
  for (const line of stdout.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed.startsWith('{') || !trimmed.includes('"chunksAsked"')) continue;
    try {
      records.push(JSON.parse(trimmed) as SnapshotRecord);
    } catch {
      // the dispatcher's own --debug JSON logging shares this stream
    }
  }
  return records;
}

test.describe
  .serial('Chunk-store backup: the machine surface @bridge @backup', () => {
    if (verdict.kind === 'undeclared') {
      // A failing test, not a skip: the message names the unmet prerequisite
      // and the exact command that satisfies it.
      test('suite 25 prerequisites are missing and undeclared', () => {
        expect(() => announcePrerequisites(verdict)).not.toThrow();
      });
    } else {
      const gate = announcePrerequisites(verdict);
      test.skip(gate.skip, gate.reason);

      let runner: BridgeTestRunner;
      const named = `chunk-e2e-${stamp}`;

      /** sha256 of a repository's LUKS image, mount-free (suite 17's technique). */
      const imageSha = async (name: string): Promise<string> => {
        const r = await runner.executeViaBridge(
          `sudo sha256sum "${DS}/repositories/${name}" | cut -d' ' -f1`
        );
        return (/[0-9a-f]{64}/.exec(runner.getCombinedOutput(r)) ?? [''])[0];
      };

      /** Drive `backup_verify` the way rdc does: the FunctionDef, via a vault. */
      const verifyViaFunction = async (guid: string, level?: string) => {
        const vault = new VaultBuilder()
          .withFunction('backup_verify')
          .withTeam(TEST_TEAM)
          .withRepository(guid, guid)
          .withMachine(runner.getTargetVM(), TEST_USER, DS)
          .withDatastore(DS);
        if (level) vault.withParams({ level });
        return runner.executeWithVault('backup_verify', vault);
      };

      test.beforeAll(async () => {
        runner = BridgeTestRunner.forWorker();
        await runner.resetWorkerState();
        const init = await runner.datastoreInitPool('10G', DS, true);
        if (!runner.isSuccess(init)) {
          console.error('[Setup] datastore init:', runner.getCombinedOutput(init));
        }
        await runner.repositoryNew(REPO_GUID, '1G', TEST_PASSWORD, DS);
        await runner.repositoryUnmount(REPO_GUID, DS).catch(() => {});
      });

      test.afterAll(async () => {
        for (const name of [named, REPO_GUID]) {
          await runner.repositoryUnmount(name, DS).catch(() => {});
          await runner.repositoryRm(name, DS).catch(() => {});
        }
      });

      test('1. a repo the engine never touched reports no-backup, as a record', async () => {
        const result = await verifyViaFunction(REPO_GUID);
        expect(
          result.code,
          `backup_verify exited ${result.code}:\n${result.stderr.slice(-800)}`
        ).toBe(0);

        const records = parseVerifyRecords(result.stdout + result.stderr);
        const mine = records.filter((r) => r.guid === REPO_GUID);
        expect(
          mine.length,
          `no verify record for ${REPO_GUID} on stdout:\n${result.stdout.slice(-800)}`
        ).toBe(1);
        // The failure this pins: a verb that says nothing about a repo it could
        // not check. "no-backup" is information; silence is indistinguishable
        // from health.
        expect(mine[0].status, 'a repo with no committed snapshot must not read as verified').toBe(
          'no-backup'
        );
        expect(mine[0].reason ?? '').toContain('no committed snapshot');
        expect(mine[0].snapshotId ?? '').toBe('');
        expect(mine[0].level).toBe('spot');
      });

      test('2. the level parameter reaches the verb (level=full is carried through)', async () => {
        const result = await verifyViaFunction(REPO_GUID, 'full');
        expect(result.code, `backup_verify --level full: ${result.stderr.slice(-600)}`).toBe(0);
        const mine = parseVerifyRecords(result.stdout + result.stderr).filter(
          (r) => r.guid === REPO_GUID
        );
        expect(mine.length).toBe(1);
        // The record echoes the level it ran at; `full` here proves the vault
        // param survived FunctionDef -> `--level` -> the record.
        expect(mine[0].level, 'the level parameter did not reach the verb').toBe('full');
        expect(mine[0].status).toBe('no-backup');
      });

      test('3. control: an invalid level is REFUSED, so test 2 read a real parameter', async () => {
        // Without this, a verb that ignored `level` entirely and stamped the
        // request back into its record would satisfy test 2.
        const result = await verifyViaFunction(REPO_GUID, 'thorough');
        expect(result.code, 'an invalid verify level was accepted').not.toBe(0);
        const text = runner.getCombinedOutput(result);
        expect(text).toContain('invalid verify level');
        expect(text, 'the refusal must name the valid levels').toContain('spot, full');
        expect(
          parseVerifyRecords(result.stdout + result.stderr),
          'a refused run still emitted records'
        ).toEqual([]);
      });

      test('4. an unfiltered verify enumerates the datastore, and says so when it cannot', async () => {
        // No --repo filter: the verb enumerates GUID-named repository files.
        const all = await runner.executeViaBridge(`sudo renet backup verify --datastore "${DS}"`);
        expect(all.code, `unfiltered verify: ${all.stderr.slice(-600)}`).toBe(0);
        const guids = parseVerifyRecords(all.stdout).map((r) => r.guid);
        expect(guids, 'the enumeration missed the GUID-named repository').toContain(REPO_GUID);

        // And the empty case is a loud refusal rather than a silent success:
        // an empty datastore that exited 0 would look exactly like a healthy
        // fleet-wide verify.
        const empty = await runner.executeViaBridge(
          `sudo renet backup verify --datastore /var/tmp/chunk-empty-${stamp}`
        );
        expect(empty.code, 'verify on a datastore with no repositories exited 0').not.toBe(0);
        expect(runner.getCombinedOutput(empty)).toMatch(
          /no repositories found|failed to enumerate/
        );
      });

      test('5. verify is a read: it leaves no anchor and no journal behind', async () => {
        // An anchor or journal conjured by a READ is the state a later
        // incremental would trust — and it would describe a snapshot that was
        // never uploaded.
        // CASE MATTERS HERE. getCombinedOutput() LOWERCASES (TestHelpers.ts:15),
        // so a literal carrying a capital can never match no matter what the
        // machine did. `/No such file/` was exactly that: the anchor directory
        // was correctly absent and the assertion still went red, because only
        // the `total 0` arm was alive. Every matcher in this file is
        // case-insensitive for that reason -- do not "tidy" the flags away.
        const anchors = await runner.executeViaBridge(
          `sudo ls -la "${DS}/.chunk-anchors" 2>&1 || true`
        );
        expect(runner.getCombinedOutput(anchors)).toMatch(/no such file|total 0/i);

        const journal = await runner.executeViaBridge(
          `sudo ls /var/lib/rediacc/backup-journal/ 2>/dev/null | grep -c "${REPO_GUID}" || true`
        );
        expect(runner.getCombinedOutput(journal).trim()).toMatch(/(^|\D)0(\D|$)/);

        // The anchors directory is `.chunk-anchors` and NOT `.backup-anchors`
        // on purpose: three live scanners match `.backup-*` at the datastore
        // root and one of them DELETES what it finds (findStaleBackupSnapshots
        // -> btrfs subvolume delete). A rename back would make every
        // `machine prune` eat the anchors.
        const wrongName = await runner.executeViaBridge(
          `sudo test -e "${DS}/.backup-anchors" && echo PRESENT || echo ABSENT`
        );
        expect(
          runner.getCombinedOutput(wrongName),
          '.backup-anchors exists; the pruner deletes anything matching .backup-*'
        ).toMatch(/absent/i);
      });

      test('6. `backup snapshot --dry-run` plans without a session, and writes no state', async () => {
        // The verb landed on 2026-08-14 (`renet backup snapshot`), and
        // `--dry-run` is "plan only: no session, no grant, no upload"
        // (backup_snapshot.go:128), which is what makes this leg runnable HERE:
        // no account server, no credentials, no bytes.
        //
        // Two honest outcomes, because the plan needs an installed repository
        // licence before it will look at the image (backup_snapshot.go:216):
        //   failed  — this fleet's repos carry no licence (the ops fleet runs
        //             --nolicense renet). The record must SAY so.
        //   stored  — a licensed fleet: the plan really ran and reports what
        //             WOULD move.
        // Both are asserted specifically. What both must share is the part that
        // matters: a dry run moves nothing and leaves nothing behind.
        const result = await runner.executeViaBridge(
          `sudo renet ${chunkVerbs().run} --dry-run --repo "${REPO_GUID}" --datastore "${DS}"`
        );
        const records = parseSnapshotRecords(result.stdout);
        expect(
          records.length,
          `no snapshot record for ${REPO_GUID} on stdout:\n${result.stdout.slice(-800)}\n` +
            `stderr:\n${result.stderr.slice(-400)}`
        ).toBe(1);

        const record = records[0];
        expect(record.guid).toBe(REPO_GUID);
        expect(
          dryRunViolations(record),
          `the dry-run record breaks its own contract: ${JSON.stringify(record)}`
        ).toEqual([]);

        if (record.status === 'failed') {
          // The reason has to name what is missing. "failed" with a shrug is
          // the report that sends someone to read the source.
          expect(record.reason ?? '').toMatch(/licen[cs]e/i);
          expect(result.code, 'a failed repository must carry a non-zero exit').toBe(1);
        } else {
          expect(record.status, 'a dry run can only plan or fail here').toBe('stored');
          expect(record.snapshotId, 'a planned snapshot with no id').toBeTruthy();
          expect(record.cellBytes ?? 0, 'the plan recorded no geometry').toBeGreaterThan(0);
          expect(result.code).toBe(0);
        }

        // The invariant both branches share, and the reason this test is worth
        // running on a fleet at all: planning is not committing. An anchor or a
        // journal written here would be state a later incremental TRUSTS,
        // describing a snapshot that was never uploaded.
        const journals = await runner.executeViaBridge(
          `sudo ls /var/lib/rediacc/backup-journal/ 2>/dev/null | grep -c "${REPO_GUID}" || true`
        );
        expect(
          runner.getCombinedOutput(journals).trim(),
          'the dry run left a journal behind'
        ).toMatch(/(^|\D)0(\D|$)/);
        const anchors = await runner.executeViaBridge(
          `sudo ls -la "${DS}/.chunk-anchors" 2>&1 || true`
        );
        expect(runner.getCombinedOutput(anchors), 'the dry run left an anchor behind').toMatch(
          /no such file|total 0/i
        );
      });

      test('7. quota is the only thing that exits 16; an ordinary failure exits 1', async () => {
        // The verb reserves exit 16 for a quota refusal specifically, because
        // the operator action is different (prune or upgrade, not debug). A
        // blanket mapping would make that signal worthless, so the control is
        // to drive a NON-quota failure and require a plain 1.
        const unknown = 'deadbeef-0000-4000-8000-000000000000';
        const result = await runner.executeViaBridge(
          `sudo renet ${chunkVerbs().run} --dry-run --repo "${unknown}" --datastore "${DS}"`
        );
        expect(result.code, 'a non-quota failure must not claim the quota exit code').toBe(1);

        const records = parseSnapshotRecords(result.stdout);
        expect(records.length, 'a repository that could not be processed emitted no record').toBe(
          1
        );
        expect(records[0].status).toBe('failed');
        expect(records[0].status).not.toBe('quota-refused');
        expect(snapshotRecordViolations(records[0])).toEqual([]);
      });

      test('8. `backup pull --at` refuses loudly and leaves the image byte-identical', async () => {
        const before = await imageSha(REPO_GUID);
        expect(before, 'could not hash the repository image').toMatch(/^[0-9a-f]{64}$/);

        const result = await runner.executeViaBridge(
          `sudo renet backup pull --name "${REPO_GUID}" --datastore "${DS}" --at 2026-01-01T00:00:00Z`
        );
        expect(result.code, 'a snapshot-addressed restore appeared to succeed').not.toBe(0);
        const text = runner.getCombinedOutput(result);
        expect(text).toContain('snapshot-addressed restore');
        expect(text, 'the refusal must quote what was asked for').toContain('2026-01-01T00:00:00Z');

        // The half that matters: refusing is only safe if it refused BEFORE
        // touching anything. A partial restore of the wrong point in time is
        // the failure mode the loud refusal exists to prevent.
        expect(await imageSha(REPO_GUID), 'the refused restore modified the image').toBe(before);
      });
    }
  });
