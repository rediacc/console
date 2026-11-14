import { randomUUID } from 'node:crypto';
import { expect, test } from '@playwright/test';
import { CliMigrateSuite, canRun, DS, imagePath, M1, M2 } from '../src/utils/cliMigrateHarness';
import type { RenetFunctionsTestRunner } from '../src/utils/renet-functions/RenetFunctionsTestRunner';

// Suite 23b (`E2E Full Integration`, ubuntu-24.04 CLI_SUITE leg), Box M1 of agent/plans/PLAN-jobs-backup-real-machine-tests.md: the ordering of the `repository_migrate` job path (the source is deleted only after the target is up), a migrate whose target fails to come up, and the `repository_gc` re-check of a candidate mounted between the list and the delete. Split from suite 23a (operator ruling #12755b25) so each runs in a job of its own; the two share src/utils/cliMigrateHarness.ts and must not run at the same time on one fleet (23a's unfiltered `config reconcile` asserts on every repo in the e2e-cli config).
//
// Gated on TWO worker VMs (machine-11 / machine-12).
// One repo per scenario (ordering, failed target, gc race).
const APP_ORDER = 'e2ecli-order';
const APP_FAIL = 'e2ecli-fail';
const APP_GC = 'e2ecli-gc';

// renet writes one JSON object per line on stdout ({"gc_result": {...}} per candidate, {"gc_summary": {...}} last; private/renet cmd/renet/repository_gc.go runGC). Logrus output rides stderr, so only stdout lines that parse as those objects count.
interface GcResult {
  guid: string;
  status: string;
  reason?: string;
}
interface GcSummary {
  total: number;
  deleted: number;
  skipped: number;
  failed: number;
}
interface GcRun {
  code: number;
  raw: string;
  results: GcResult[];
  summary?: GcSummary;
}

const parseGcLine = (line: string): { gc_result?: GcResult; gc_summary?: GcSummary } => {
  if (!line.trim().startsWith('{')) return {};
  try {
    return JSON.parse(line) as { gc_result?: GcResult; gc_summary?: GcSummary };
  } catch {
    return {};
  }
};

const parseGcOutput = (stdout: string, stderr: string): Omit<GcRun, 'code'> => {
  const parsed = stdout.split('\n').map(parseGcLine);
  return {
    raw: `${stdout}\n${stderr}`.slice(-600),
    results: parsed.flatMap((p) => (p.gc_result ? [p.gc_result] : [])),
    summary: parsed.find((p) => p.gc_summary)?.gc_summary,
  };
};

// Rediaccfile functions run under the sandbox, whose write access is the repository, so the stamp lives there: `up()` starts in the repository root.
const UP_STAMP_FILE = '.e2e-m1-up';
const upStamp = (guid: string): string => `${DS}/mounts/${guid}/${UP_STAMP_FILE}`;
const stopFile = (guid: string): string => `/var/tmp/e2e-m1-stop-${guid}`;
const goneFile = (guid: string): string => `/var/tmp/e2e-m1-gone-${guid}`;
// How long up() holds after its first stamp. The last stamp marks the END of the target's bring-up, so a source delete that overlaps the bring-up lands before it. The hold only has to dwarf the watcher's poll lag (0.1 s), the one error that can hide a violation: a premature delete landing more than 0.1 s before the end stamp still fails the assertion, so 3 s leaves a thirtyfold margin. A correct migrate's margin does not depend on the hold at all (the source delete follows the end of up()).
const UP_HOLD_S = 3;

test.describe
  .serial('rdc migrate ordering, failed target and gc race (CLI-driven) @cli @migrate', () => {
    test.skip(!canRun, 'Requires two worker VMs (machine-11 / machine-12)');
    test.setTimeout(600_000);

    const s = new CliMigrateSuite([APP_ORDER, APP_FAIL, APP_GC]);

    const nowNs = async (runner: RenetFunctionsTestRunner): Promise<bigint> => {
      const res = await runner.executeViaBridge('date +%s%N');
      expect(res.code, `date on a worker: ${res.stderr}`).toBe(0);
      return BigInt(res.stdout.trim().split('\n').pop() ?? '0');
    };

    test.beforeAll(async () => {
      await s.setup();
    });

    test.afterAll(async () => {
      await s.teardown();
    });

    test('10. migrate deletes the source only AFTER the target is up (observed on both machines)', async () => {
      // The CLI migrate dispatches the `repository_migrate` job verb on the source machine: that machine's renet must register it, or the job path under test cannot exist there.
      const registry = await s.w1.executeViaBridge('renet functions list-functions --internal');
      expect(registry.code, `functions list: ${registry.stderr.slice(-400)}`).toBe(0);
      expect(registry.stdout, 'machine-11 renet does not register repository_migrate').toContain(
        'repository_migrate'
      );

      // `up()` appends a nanosecond timestamp to a stamp file inside the repository (UP_STAMP_FILE, so it travels with the repo and is readable on the target), holds, then appends another: the last stamp is the end of the target's bring-up, read off the target itself. seedRepo brings the repository up on machine-11 BEFORE it writes this Rediaccfile, so the source holds no stamp and every stamp on machine-12 is the target's own.
      const guid = await s.seedRepo(
        APP_ORDER,
        () =>
          `    date +%s%N >> ${UP_STAMP_FILE}\n    sleep ${UP_HOLD_S}\n    date +%s%N >> ${UP_STAMP_FILE}`
      );

      // Clock offset between the workers, so both timestamps compare on one scale. Reading machine-12 between two machine-11 reads brackets it: the offset is b minus the midpoint, and the measured error is half the bracket (one SSH round trip), subtracted from the margin below.
      const a = await nowNs(s.w1);
      const b = await nowNs(s.w2);
      const c = await nowNs(s.w1);
      const offsetNs = b - (a + c) / 2n;
      const errNs = (c - a) / 2n + 1n;

      // Watch the SOURCE image from the machine while the migrate runs: the first moment it is gone. The poll lag (about 0.1 s) only delays the reading, so it can hide a violation by that much; up() holds ${UP_HOLD_S} s, far above it. The loop ends at the stop file, which the finally below writes, so a failed assertion never leaves it running.
      await s.w1.executeViaBridge(`sudo rm -f ${stopFile(guid)} ${goneFile(guid)}`);
      const watchScript = `for i in $(seq 1 3000); do sudo test -e ${imagePath(guid)} || { date +%s%N > ${goneFile(guid)}; exit 0; }; [ -e ${stopFile(guid)} ] && { echo stopped; exit 0; }; sleep 0.1; done; echo timeout`;
      const watcher = s.w1.executeViaBridge(
        `echo ${Buffer.from(watchScript).toString('base64')} | base64 -d | bash`
      );
      let gone = '';
      let watcherOutput = '';
      try {
        const mig = await s.cli.run(['repo', 'migrate', `${APP_ORDER}@${M1}`, '--to', M2]);
        expect(mig.code, `migrate: ${(mig.stdout + mig.stderr).slice(-800)}`).toBe(0);
      } finally {
        await s.w1.executeViaBridge(`touch ${stopFile(guid)}`);
        const watched = await watcher;
        watcherOutput = `code ${watched.code}: ${watched.stdout} ${watched.stderr}`.slice(-400);
        gone = (await s.w1.executeViaBridge(`cat ${goneFile(guid)}`)).stdout.trim();
        await s.w1.executeViaBridge(`rm -f ${stopFile(guid)} ${goneFile(guid)}`);
      }
      expect(
        gone,
        `the source image never disappeared during the migrate (watcher ${watcherOutput})`
      ).toMatch(/^\d+$/);
      const sourceGoneNs = BigInt(gone) + offsetNs;

      const stamps = await s.w2.executeViaBridge(`sudo cat ${upStamp(guid)}`);
      expect(stamps.code, 'the target never ran up() (no stamp on machine-12)').toBe(0);
      const stampLines = stamps.stdout.trim().split('\n');
      const targetUpNs = BigInt(stampLines.at(-1) ?? '0');
      expect(
        stampLines.length,
        'up() on machine-12 did not run to its end stamp'
      ).toBeGreaterThanOrEqual(2);
      expect(targetUpNs > 0n).toBe(true);

      expect(
        sourceGoneNs - errNs > targetUpNs,
        `source deleted at ${sourceGoneNs} (machine-12 clock, error ${errNs} ns) before the target finished coming up at ${targetUpNs}`
      ).toBe(true);
      // End state: the target holds the repo, the source does not.
      expect(await s.imageExists(s.w2, guid)).toBe(true);
      expect(await s.imageExists(s.w1, guid)).toBe(false);
    });

    test('11. a migrate whose target fails to come up keeps the source intact', async () => {
      const w1Host = (await s.w1.executeViaBridge('hostname')).stdout.trim();
      const w2Host = (await s.w2.executeViaBridge('hostname')).stdout.trim();
      expect(w2Host, 'machine-12 reported no hostname').not.toBe('');
      expect(
        w2Host,
        'machine-11 and machine-12 share a hostname, so the failure cannot be targeted'
      ).not.toBe(w1Host);
      // `up()` fails on machine-12 only, so the source job and the source bring-up succeed and the target's repo up is the step that fails.
      const guid = await s.seedRepo(
        APP_FAIL,
        () =>
          `    if [ "$(hostname)" = "${w2Host}" ]; then echo "e2e: forced target failure" >&2; return 1; fi`
      );
      expect(await s.imageExists(s.w1, guid)).toBe(true);

      const mig = await s.cli.run(['repo', 'migrate', `${APP_FAIL}@${M1}`, '--to', M2]);
      expect(mig.code, 'migrate reported success though the target could not come up').not.toBe(0);

      // The machine, not the CLI's message, is the evidence: the source copy was never deleted, and the data did reach the target.
      expect(
        await s.imageExists(s.w1, guid),
        'source deleted although the target never came up'
      ).toBe(true);
      expect(await s.repoPresentOnBridge(s.w1, APP_FAIL)).toBe(true);
      expect(await s.imageExists(s.w2, guid)).toBe(true);
    });

    test('12. repository_gc keeps a candidate that was mounted between the list and the delete', async () => {
      const w1 = s.w1;
      const fork = await s.seedRepo(APP_GC, () => '    true');
      const commit = randomUUID();
      s.extraGuids.add(commit);
      const committed = await w1.repositoryCommit(fork, commit, 'e2e gc race', DS);
      expect(committed.code, `commit: ${w1.getCombinedOutput(committed).slice(-600)}`).toBe(0);

      const gcRun = async (): Promise<GcRun> => {
        const res = await w1.executeViaBridge(
          `sudo renet repository gc --candidates ${commit}@${DS} --datastore ${DS}`
        );
        return { code: res.code, ...parseGcOutput(res.stdout, res.stderr) };
      };

      // The list step: the commit is present and unmapped, so a client building its candidate set now includes it.
      expect(await s.imageExists(w1, commit), 'the commit image is absent before the race').toBe(
        true
      );
      const mapped = await w1.executeViaBridge(`test -e /dev/mapper/${commit}`);
      expect(mapped.code, 'the commit is already mapped before the race').not.toBe(0);

      // The race: a device-mapper entry appears AFTER the candidate list was taken and BEFORE gc runs, and `repository gc --candidates` re-checks the machine rather than trusting the list. renet refuses to mount an immutable commit, so a real mapping cannot be made through `repository_mount`: a zero-target entry under the commit's name is the state gc reads, and it holds no data.
      const map = await w1.executeViaBridge(`sudo dmsetup create ${commit} --table '0 8 zero'`);
      expect(map.code, `dmsetup create: ${w1.getCombinedOutput(map).slice(-600)}`).toBe(0);
      // The entry is removed on every path out of the assertions below, so a failed one never leaves a mapping named after a commit on the fleet machine.
      let entryLive = true;
      try {
        const kept = await gcRun();
        expect(kept.code, `gc failed instead of skipping: ${kept.raw}`).toBe(0);
        expect(kept.results, kept.raw).toEqual([
          expect.objectContaining({ guid: commit, status: 'skipped', reason: 'mounted' }),
        ]);
        expect(kept.summary, kept.raw).toMatchObject({
          total: 1,
          deleted: 0,
          skipped: 1,
          failed: 0,
        });
        expect(await s.imageExists(w1, commit), 'gc deleted a mounted commit').toBe(true);

        // Control: with the entry gone, the same call deletes it, so the skip above came from the mapping and from nothing else.
        const unmap = await w1.executeViaBridge(`sudo dmsetup remove ${commit}`);
        expect(unmap.code, `dmsetup remove: ${w1.getCombinedOutput(unmap).slice(-600)}`).toBe(0);
        entryLive = false;
        const deleted = await gcRun();
        expect(deleted.code, deleted.raw).toBe(0);
        expect(deleted.results, deleted.raw).toEqual([
          expect.objectContaining({ guid: commit, status: 'deleted' }),
        ]);
        expect(deleted.summary, deleted.raw).toMatchObject({ total: 1, deleted: 1, failed: 0 });
        expect(await s.imageExists(w1, commit)).toBe(false);
      } finally {
        if (entryLive) {
          await w1.executeViaBridge(`sudo dmsetup remove ${commit}`).catch(() => undefined);
        }
      }
    });
  });
