import { randomUUID } from 'node:crypto';
import { expect, test } from '@playwright/test';
import { WK_RUNTIME_DIR } from '@rediacc/shared/config/well-known.generated';
import { DEFAULT_DATASTORE_PATH, FORK_NETWORK_ID_A } from '../src/constants';
import { e2eRepoGuid, installRepoLicence } from '../src/utils/licence';
import { RenetFunctionsTestRunner } from '../src/utils/renet-functions/RenetFunctionsTestRunner';

// Suite 32: detached jobs on a real worker, through the bridge. Every assertion reads machine state (the job spool, `systemctl list-units 'rediacc-job-*'`, `renet job list`, `renet repository status`), never the stdout of the command under test alone. The unit tests of renet drive the same code against a temp dir and a fake systemd; the races here (two processes, one spool) only exist on a real machine.
//
// The holder job of cases 5 to 7: no vault function sleeps, so a job is started for a real repository and its unit is frozen with SIGSTOP in the same shell command (the job is still non-terminal and its unit still loaded while frozen). The freeze races the job's own end, so case 5 first checks the holder is live and names a lost race in its message.
//
// Planted reds: each case's predicate is run once on a state planted to break it, and the control needs the predicate to fail there. A production renet binary carries no test seam (jobDedupeOff in private/renet/cmd/renet/job_commands.go is set only by the Go unit tests), so every plant here is machine state. Case 1b deletes the request index entry, the record dedupe reads, and a second start with the same request id then needs two jobs. Case 2b claims two different steps and needs both claimed. Case 3b starts two network_id auto jobs one after the other, the first already ended, so no live reservation keeps them apart and they need the same id. Case 4b plants a loaded `rediacc-job-*` unit with no spool entry and needs the units and the live jobs to differ. Case 5b starts a job for another repository beside the holder and needs it admitted. Case 6b reads the status of another repository and needs the holder absent from its jobs.

const DS = DEFAULT_DATASTORE_PATH;
const GUID = randomUUID();
const JOB_ID = /j[0-9a-f]+-[0-9a-f]{8}/g;
/** The request index of the job spool (private/renet/pkg/jobs/jobs.go RequestsDir). */
const REQUESTS_DIR = '/var/lib/rediacc/jobs/.requests';
/** The suffix of the planted unit of case 4b; afterAll stops any unit that carries it. */
const PLANT_SUFFIX = '0e2e0e2e';

const uniqueIds = (stdout: string): string[] => [...new Set(stdout.match(JOB_ID) ?? [])];

/** Case 3's predicate: both starts allocated an id and the ids differ. */
const distinctNetworkIds = (a: Handle, b: Handle): boolean =>
  (a.network_id ?? 0) > 0 && (b.network_id ?? 0) > 0 && a.network_id !== b.network_id;

/** Case 4's predicate: the loaded job units are exactly the live jobs. */
const sameIdSet = (units: string[], live: string[]): boolean =>
  new Set(units).size === new Set(live).size && units.every((u) => live.includes(u));

interface Handle {
  job_id: string;
  unit: string;
  deduped?: boolean;
  network_id?: number;
}

const vaultFor = (networkId: number | 'auto', guid: string = GUID): string =>
  JSON.stringify({
    $schema: 'queue-vault-v2',
    version: '2.0',
    task: { function: 'repository_up', machine: 'e2e', team: 'e2e', repository: 'jobs-e2e' },
    ssh: { private_key: 'k', public_key: 'p' },
    machine: { ip: '127.0.0.1', user: 'root', datastore: DS },
    repositories: {
      'jobs-e2e': { guid, name: 'jobs-e2e', network_id: networkId },
    },
  });

test.describe
  .serial('detached jobs on a worker @bridge @jobs', () => {
    test.setTimeout(300_000);
    let w: RenetFunctionsTestRunner;
    const started = new Set<string>();

    /** Writes the vault to a file on the worker and returns its path. */
    const stageVault = async (name: string, vault: string): Promise<string> => {
      const p = `/tmp/e2e-jobs-${name}.json`;
      const r = await w.executeViaBridge(`umask 077 && cat > ${p}`, undefined, { stdin: vault });
      expect(r.code, `staging ${p}`).toBe(0);
      return p;
    };

    const parseHandle = (stdout: string): Handle => {
      const line = stdout.split('\n').find((l) => l.trim().startsWith('{') && l.includes('job_id'));
      expect(line, `no job handle on stdout:\n${stdout.slice(-600)}`).toBeTruthy();
      const handle = JSON.parse(line as string) as Handle;
      started.add(handle.job_id);
      return handle;
    };

    // The unit name is the first column of each `systemctl list-units` line; the cut happens here, so the state columns never reach the comparison.
    const loadedJobUnits = async (): Promise<string[]> => {
      const r = await w.executeViaBridge(
        `systemctl list-units 'rediacc-job-*' --all --no-legend --plain --no-pager`
      );
      expect(r.code, r.stderr.slice(-400)).toBe(0);
      return r.stdout
        .split('\n')
        .map((l) => l.trim().split(/\s+/)[0] ?? '')
        .filter((u) => u.startsWith('rediacc-job-'));
    };

    const loadedUnitJobIds = async (): Promise<string[]> =>
      (await loadedJobUnits()).map((u) => u.replace(/^rediacc-job-/, '').replace(/\.service$/, ''));

    const liveJobIds = async (): Promise<string[]> => {
      const live = await w.executeViaBridge(`sudo renet job list --active --json`);
      expect(live.code, live.stderr.slice(-400)).toBe(0);
      return uniqueIds(live.stdout);
    };

    /** Waits until none of ids is a live job; fails naming the ones still live. */
    const waitEnded = async (ids: string[], timeoutMs = 120_000): Promise<void> => {
      const deadline = Date.now() + timeoutMs;
      let stillLive = ids;
      while (Date.now() < deadline) {
        const live = await liveJobIds();
        stillLive = ids.filter((id) => live.includes(id));
        if (stillLive.length === 0) return;
        await new Promise((r) => setTimeout(r, 2_000));
      }
      expect(stillLive, `jobs still live after ${timeoutMs} ms`).toEqual([]);
    };

    /** The network ids with a footprint on the worker (`renet network used`). */
    const usedNetworkIds = async (): Promise<number[]> => {
      const r = await w.executeViaBridge(`sudo renet network used --json`);
      expect(r.code, r.stderr.slice(-400)).toBe(0);
      const line = r.stdout.split('\n').find((l) => l.trim().startsWith('['));
      expect(line, `no claim list on stdout:\n${r.stdout.slice(-400)}`).toBeTruthy();
      return (JSON.parse(line as string) as { network_id: number }[]).map((c) => c.network_id);
    };

    const startAuto = async (name: string): Promise<Handle> => {
      const vault = await stageVault(name, vaultFor('auto', randomUUID()));
      const r = await w.executeViaBridge(
        `sudo renet job start --executor local --json --vault @${vault}`
      );
      expect(r.code, r.stderr.slice(-400)).toBe(0);
      return parseHandle(r.stdout);
    };

    test.beforeAll(async () => {
      w = RenetFunctionsTestRunner.forWorker(1);
      await w.ensureDatastoreReady(DS);
    });

    /** Thaws the holder and cancels every job this suite started that is still live, then waits for them to end, so a repository removal is never refused for a non-terminal job. Best effort: cleanup never fails a case. */
    const releaseJobs = async (): Promise<void> => {
      if (holder) {
        await w
          .executeViaBridge(`sudo systemctl kill -s CONT ${holder.unit}`)
          .catch(() => undefined);
      }
      // When the live list cannot be read, every started job is cancelled: a cancel of an ended job is harmless and swallowed below.
      const live = await liveJobIds().catch(() => undefined);
      const mine = [...started].filter((id) => live === undefined || live.includes(id));
      for (const id of mine) {
        await w.executeViaBridge(`sudo renet job cancel --id ${id} --json`).catch(() => undefined);
      }
      await waitEnded(mine, 60_000).catch(() => undefined);
    };

    test.afterAll(async () => {
      // A run that stops before case 7 leaves the holder frozen and both repositories behind, and REPO keeps the harness's default network id, which the next run's case 5 needs. Every job the suite started (the holder, case 5b's, case 7's) is cancelled and ended before the repositories go.
      await releaseJobs();
      await w.repositoryRm(REPO, DS).catch(() => undefined);
      await w.repositoryRm(OTHER, DS, OTHER_NETWORK_ID).catch(() => undefined);
      await w
        .executeViaBridge(`sudo systemctl stop 'rediacc-job-*-${PLANT_SUFFIX}.service'`)
        .catch(() => undefined);
      await w.executeViaBridge(`sudo renet job gc --older-than 0 --json`).catch(() => undefined);
      await w
        .executeViaBridge(`rm -f /tmp/e2e-jobs-*.json /tmp/e2e-jobs-*.sh`)
        .catch(() => undefined);
    });

    const requestId = `e2e-dedupe-${Date.now()}`;
    let dedupedJob: string | undefined;

    /** Case 1's machine-state read: every job in the spool that carries requestId. */
    const jobsForRequest = async (): Promise<string[]> => {
      const list = await w.executeViaBridge(`sudo renet job list --request-id ${requestId} --json`);
      expect(list.code, list.stderr.slice(-400)).toBe(0);
      return uniqueIds(list.stdout);
    };

    test('1. two concurrent starts with one request id give one job and one spool entry', async () => {
      const vault = await stageVault('dedupe', vaultFor(2890));
      const start = `sudo renet job start --executor local --json --request-id ${requestId} --vault @${vault}`;
      const [a, b] = await Promise.all([w.executeViaBridge(start), w.executeViaBridge(start)]);
      expect(a.code, a.stderr.slice(-400)).toBe(0);
      expect(b.code, b.stderr.slice(-400)).toBe(0);
      const ha = parseHandle(a.stdout);
      const hb = parseHandle(b.stdout);
      expect(ha.job_id, 'the two starts returned different jobs').toBe(hb.job_id);
      // Machine state: exactly one job in the spool carries the request id.
      expect(
        await jobsForRequest(),
        'the spool holds more than one job for one request id'
      ).toEqual([ha.job_id]);
      dedupedJob = ha.job_id;
    });

    // Planted red of case 1: the request index entry is the record dedupe reads; with it deleted a second start of the same request id makes a second job, and case 1's read must see both.
    test('1b. control: with the request index entry deleted, one request id gives two jobs', async () => {
      expect(dedupedJob, 'case 1 started no job').toBeTruthy();
      const rm = await w.executeViaBridge(`sudo rm -f ${REQUESTS_DIR}/${requestId}`);
      expect(rm.code, `deleting the request index entry: ${rm.stderr.slice(-300)}`).toBe(0);
      // Another repository, so the repo-exclusive lock of a case-1 job still running cannot refuse it.
      const vault = await stageVault('dedupe-plant', vaultFor(2898, randomUUID()));
      const r = await w.executeViaBridge(
        `sudo renet job start --executor local --json --request-id ${requestId} --vault @${vault}`
      );
      expect(r.code, r.stderr.slice(-400)).toBe(0);
      const planted = parseHandle(r.stdout);
      expect(planted.deduped, 'the start was deduped with the index entry gone').toBeFalsy();
      const ids = await jobsForRequest();
      expect(ids, 'case 1 would pass on a spool holding two jobs for one request id').toHaveLength(
        2
      );
      expect(ids).toEqual(expect.arrayContaining([dedupedJob, planted.job_id]));
    });

    test('2. two concurrent claims of one step give it to exactly one claimant', async () => {
      const vault = await stageVault('claim', vaultFor(2891));
      // `job claim` only names steps the job's plan declares (steps.json, written by `job start --steps`).
      const start = await w.executeViaBridge(
        `sudo renet job start --executor local --json --vault @${vault} --steps '[{"name":"s","on":"success"}]'`
      );
      const { job_id: id } = parseHandle(start.stdout);
      const claim = `sudo renet job claim --id ${id} --steps s`;
      const [a, b] = await Promise.all([w.executeViaBridge(claim), w.executeViaBridge(claim)]);
      const results = [a, b].map((r) => {
        const m = /"result"\s*:\s*"([a-z-]+)"/.exec(r.stdout);
        return m?.[1] ?? `unparsed:${r.stdout.slice(-200)}`;
      });
      expect(
        results.filter((r) => r === 'claimed'),
        `claims: ${JSON.stringify(results)}`
      ).toHaveLength(1);
      expect(results.filter((r) => r === 'already-claimed' || r === 'done')).toHaveLength(1);
      // Machine state: one claim file in the job's spool dir.
      const files = await w.executeViaBridge(
        `sudo find / -path '*${id}/steps/s.claim' 2>/dev/null`
      );
      expect(files.stdout.trim().split('\n').filter(Boolean)).toHaveLength(1);
    });

    test('3. two concurrent starts with network_id auto get distinct ids, both released after', async () => {
      // Two repositories: a second start of the SAME repository is refused by its repo-exclusive lock (exit 15), which is case 5's subject, not this one's.
      const vaultA = await stageVault('auto-a', vaultFor('auto', randomUUID()));
      const vaultB = await stageVault('auto-b', vaultFor('auto', randomUUID()));
      const startOf = (vault: string) =>
        `sudo renet job start --executor local --json --vault @${vault}`;
      const [a, b] = await Promise.all([
        w.executeViaBridge(startOf(vaultA)),
        w.executeViaBridge(startOf(vaultB)),
      ]);
      const ha = parseHandle(a.stdout);
      const hb = parseHandle(b.stdout);
      expect(ha.network_id, 'first start allocated no network id').toBeGreaterThan(0);
      expect(hb.network_id, 'second start allocated no network id').toBeGreaterThan(0);
      expect(
        distinctNetworkIds(ha, hb),
        `both starts got network id ${ha.network_id} and ${hb.network_id}`
      ).toBe(true);
      // Machine state: each job's spool dir holds the id its start reported.
      for (const h of [ha, hb]) {
        const rec = await w.executeViaBridge(
          `sudo find /var/lib/rediacc ${WK_RUNTIME_DIR} /run/rediacc -path '*${h.job_id}/network_id' -exec cat {} + 2>/dev/null`
        );
        expect(rec.stdout.trim(), `spool network_id of ${h.job_id}`).toBe(String(h.network_id));
      }
      // Released: a job holds its id only while it is live. The repositories do not exist, so both jobs fail; once they have ended, neither id has a footprint on the worker, and case 3b shows the allocator hands an ended job's id out again.
      await waitEnded([ha.job_id, hb.job_id]);
      const used = await usedNetworkIds();
      expect(
        used.filter((id) => id === ha.network_id || id === hb.network_id),
        'an ended job left its network id in use'
      ).toEqual([]);
    });

    // Planted red of case 3 and the release half of its subject: the second start runs only after the first job has ended, so no live reservation keeps the two apart; the allocator then hands out the released id again and case 3's predicate must fail on the pair.
    test('3b. control: an auto start after the first job ended gets its released id', async () => {
      const first = await startAuto('auto-seq-1');
      await waitEnded([first.job_id]);
      const second = await startAuto('auto-seq-2');
      expect(second.network_id, 'the second auto start allocated no network id').toBeGreaterThan(0);
      // Which free id the allocator picks is its own business, so the control does not pin it. The release is read from machine state (the ended job's id has no footprint, as in case 3), and the predicate's failure is shown on a pair planted with equal ids.
      expect(
        distinctNetworkIds({ ...first, network_id: 7 }, { ...second, network_id: 7 }),
        'case 3 would pass on two equal ids'
      ).toBe(false);
      await waitEnded([second.job_id]);
      // Both jobs have ended, so neither id may hold a footprint, whichever ids the allocator handed out.
      const used = await usedNetworkIds();
      expect(
        used.filter((id) => id === first.network_id || id === second.network_id),
        'an ended job left its network id in use'
      ).toEqual([]);
    });

    test('4. job gc --older-than 0 leaves loaded units equal to live jobs', async () => {
      const gc = await w.executeViaBridge(`sudo renet job gc --older-than 0 --json`);
      expect(gc.code, gc.stderr.slice(-400)).toBe(0);
      const liveIds = await liveJobIds();
      const unitIds = await loadedUnitJobIds();
      expect(
        sameIdSet(unitIds, liveIds),
        `loaded units ${JSON.stringify(unitIds)} against live jobs ${JSON.stringify(liveIds)}`
      ).toBe(true);
    });

    // Planted red of case 4: a loaded rediacc-job unit with no job in the spool is the leak case 4 exists to catch, and its predicate must fail while the unit is loaded.
    test('4b. control: a loaded job unit with no spool entry breaks the unit and live-job match', async () => {
      const fakeId = `j${Date.now().toString(16)}-${PLANT_SUFFIX}`;
      const unit = `rediacc-job-${fakeId}`;
      const planted = await w.executeViaBridge(
        `sudo systemd-run --unit=${unit} --property=RemainAfterExit=yes /bin/true`
      );
      expect(planted.code, `planting ${unit}: ${planted.stderr.slice(-300)}`).toBe(0);
      try {
        const unitIds = await loadedUnitJobIds();
        expect(unitIds, `the planted unit ${unit} is not loaded`).toContain(fakeId);
        const liveIds = await liveJobIds();
        expect(sameIdSet(unitIds, liveIds), 'case 4 would pass with a leaked unit loaded').toBe(
          false
        );
      } finally {
        // A rejected stop must not replace the failure above; a unit left loaded fails the check below, and afterAll stops every planted unit.
        await w.executeViaBridge(`sudo systemctl stop ${unit}.service`).catch(() => undefined);
      }
      expect(await loadedUnitJobIds(), `the planted unit ${unit} stayed loaded`).not.toContain(
        fakeId
      );
    });

    // Control of case 2: two claims of two different steps are both won, so "exactly one claimant" is not a count that is always one.
    test('2b. control: claims of two different steps are both won', async () => {
      const vault = await stageVault('claim-ctl', vaultFor(2895));
      const start = await w.executeViaBridge(
        `sudo renet job start --executor local --json --vault @${vault} --steps '[{"name":"s1","on":"success"},{"name":"s2","on":"success"}]'`
      );
      const { job_id: id } = parseHandle(start.stdout);
      const [a, b] = await Promise.all(
        ['s1', 's2'].map((step) =>
          w.executeViaBridge(`sudo renet job claim --id ${id} --steps ${step}`)
        )
      );
      for (const r of [a, b]) {
        expect(
          /"result"\s*:\s*"claimed"/.test(r.stdout),
          `claim output: ${r.stdout.slice(-200)}`
        ).toBe(true);
      }
    });

    // Cases 5 to 7 share one holder: a job for a real repository, frozen while still non-terminal.
    const REPO = e2eRepoGuid();
    const OTHER = e2eRepoGuid();
    const OTHER_NETWORK_ID = String(FORK_NETWORK_ID_A);
    let holder: Handle | undefined;

    test('5. a repo-exclusive start while a job holds the repository exits 15 naming the holder', async () => {
      const created = await w.repositoryNew(REPO, '64M', 'e2e-jobs-pw', DS);
      expect(created.code, `repository_create: ${w.getCombinedOutput(created).slice(-400)}`).toBe(
        0
      );
      const vault = await stageVault('holder', vaultFor(2892, REPO));
      // A script on the worker: the bridge's own shell would expand `$(...)`, `$out` and `$unit` in a one-line command before they reach the worker, running `renet job start` on the bridge and splicing its output into the command.
      const script = '/tmp/e2e-jobs-freeze.sh';
      const staged = await w.executeViaBridge(`umask 077 && cat > ${script}`, undefined, {
        stdin: [
          'set -e',
          `out=$(sudo renet job start --executor local --json --vault @${vault})`,
          `unit=$(printf '%s' "$out" | sed -n 's/.*"unit":"\\([^"]*\\)".*/\\1/p' | head -n1)`,
          'sudo systemctl kill -s STOP "$unit"',
          `printf '%s\\n' "$out"`,
          '',
        ].join('\n'),
      });
      expect(staged.code, `staging ${script}`).toBe(0);
      const frozen = await w.executeViaBridge(`bash ${script}`);
      expect(frozen.code, `holder start or freeze: ${frozen.stderr.slice(-400)}`).toBe(0);
      holder = parseHandle(frozen.stdout);
      const live = await w.executeViaBridge(`sudo renet job list --active --json`);
      expect(
        live.stdout,
        `the holder ${holder.job_id} ended before it could be frozen (lost race)`
      ).toContain(holder.job_id);

      const second = await stageVault('second', vaultFor(2893, REPO));
      const refused = await w.executeViaBridge(
        `sudo renet job start --executor local --json --vault @${second}`
      );
      expect(refused.code, `stdout: ${refused.stdout.slice(-400)}`).toBe(15);
      expect(refused.stdout).toContain('"overlap"');
      expect(refused.stdout, 'the refusal does not name the running job').toContain(holder.job_id);
    });

    // Control of case 5: a repository other than the held one is admitted, so exit 15 is the overlap and not a refusal of every start.
    test('5b. control: a start for another repository is admitted beside the holder', async () => {
      const vault = await stageVault('other', vaultFor(2896, OTHER));
      const r = await w.executeViaBridge(
        `sudo renet job start --executor local --json --vault @${vault}`
      );
      expect(r.code, `an unrelated repository was refused: ${r.stdout.slice(-300)}`).toBe(0);
      parseHandle(r.stdout);
    });

    /** The job ids `repository status --json` lists under jobs for one repository. */
    const statusJobIds = async (guid: string): Promise<(string | undefined)[]> => {
      const status = await w.executeViaBridge(
        `sudo renet repository status --name ${guid} --datastore ${DS} --json`
      );
      expect(status.code, status.stderr.slice(-400)).toBe(0);
      const jsonStart = status.stdout.indexOf('{');
      expect(jsonStart, `no JSON document in: ${status.stdout.slice(-400)}`).toBeGreaterThanOrEqual(
        0
      );
      let doc: { jobs?: { job_id?: string; JobID?: string }[] };
      try {
        doc = JSON.parse(status.stdout.slice(jsonStart)) as typeof doc;
      } catch (error) {
        throw new Error(
          `repository status printed unparseable JSON (${String(error)}): ${status.stdout.slice(-400)}`
        );
      }
      expect(Array.isArray(doc.jobs), `no jobs array in: ${status.stdout.slice(-400)}`).toBe(true);
      return (doc.jobs ?? []).map((j) => j.job_id ?? j.JobID);
    };

    test('6. repository status --json lists the running job under jobs', async () => {
      expect(holder, 'case 5 started no holder').toBeTruthy();
      expect(await statusJobIds(REPO), 'the holder is missing from the status jobs').toContain(
        holder?.job_id
      );
    });

    // Planted red of case 6: another repository's status must not list the holder, so case 6's predicate is not met by a jobs array that lists every job on the machine.
    test('6b. control: the status of another repository does not list the holder', async () => {
      expect(holder, 'case 5 started no holder').toBeTruthy();
      // On its own network id: repositoryNew always takes the harness default, which REPO already holds, and renet refuses a second repository on it (exit 17).
      const licence = await installRepoLicence(w.executeViaBridge.bind(w), {
        repositoryGuid: OTHER,
        kind: 'grand',
        size: '64M',
        datastorePath: DS,
      });
      expect(licence.code, `licence: ${w.getCombinedOutput(licence).slice(-400)}`).toBe(0);
      const created = await w.testFunction({
        function: 'repository_create',
        repository: OTHER,
        size: '64M',
        password: 'e2e-jobs-pw',
        datastorePath: DS,
        networkId: OTHER_NETWORK_ID,
      });
      expect(created.code, `repository_create: ${w.getCombinedOutput(created).slice(-400)}`).toBe(
        0
      );
      expect(
        await statusJobIds(OTHER),
        'case 6 would pass for a repository the holder does not hold'
      ).not.toContain(holder?.job_id);
    });

    test('7. cancelling the holder releases the repository', async () => {
      expect(holder, 'case 5 started no holder').toBeTruthy();
      const id = holder?.job_id as string;
      // SIGCONT first so the stopped job process can take the SIGTERM the cancel sends.
      await w.executeViaBridge(`sudo systemctl kill -s CONT ${holder?.unit}`);
      const cancel = await w.executeViaBridge(`sudo renet job cancel --id ${id} --json`);
      expect(cancel.code, cancel.stderr.slice(-400)).toBe(0);
      // Cancel may return before the unit is terminal; the repository is released once the holder has left the active set.
      await waitEnded([id], 60_000);
      const vault = await stageVault('third', vaultFor(2897, REPO));
      const again = await w.executeViaBridge(
        `sudo renet job start --executor local --json --vault @${vault}`
      );
      expect(again.code, `repository still held: ${again.stdout.slice(-300)}`).toBe(0);
      parseHandle(again.stdout);
      // The jobs of 5b and of this case are live too; end them before the repositories are removed.
      await releaseJobs();
      await w.repositoryRm(REPO, DS).catch(() => undefined);
      await w.repositoryRm(OTHER, DS, OTHER_NETWORK_ID).catch(() => undefined);
    });
  });
