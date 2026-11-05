import { randomUUID } from 'node:crypto';
import { expect, test } from '@playwright/test';
import { WK_RUNTIME_DIR } from '@rediacc/shared/config/well-known.generated';
import { DEFAULT_DATASTORE_PATH } from '../src/constants';
import { e2eRepoGuid } from '../src/utils/licence';
import { RenetFunctionsTestRunner } from '../src/utils/renet-functions/RenetFunctionsTestRunner';

// Suite 32: detached jobs on a real worker, through the bridge. Every assertion reads machine state (the job spool, `systemctl list-units 'rediacc-job-*'`, `renet job list`, `renet repository status`), never the stdout of the command under test alone. The unit tests of renet drive the same code against a temp dir and a fake systemd; the races here (two processes, one spool) only exist on a real machine.
//
// The holder job of cases 5 to 7: no vault function sleeps, so a job is started for a real repository and its unit is frozen with SIGSTOP in the same shell command (the job is still non-terminal and its unit still loaded while frozen). The freeze races the job's own end, so case 5 first checks the holder is live and names a lost race in its message. Planted reds: case 1b runs the dedupe case with renet's hidden `--no-request-dedupe` seam and needs two jobs; case 2b claims two different steps and needs both claimed; case 5b starts a job for another repository beside the holder and needs it admitted.

const DS = DEFAULT_DATASTORE_PATH;
const GUID = randomUUID();

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

    const loadedJobUnits = async (): Promise<string[]> => {
      const r = await w.executeViaBridge(
        `systemctl list-units 'rediacc-job-*' --all --no-legend --plain | awk '{print $1}'`
      );
      return r.stdout.split('\n').filter((l) => l.startsWith('rediacc-job-'));
    };

    test.beforeAll(async () => {
      w = RenetFunctionsTestRunner.forWorker(1);
      await w.ensureDatastoreReady(DS);
    });

    test.afterAll(async () => {
      await w.executeViaBridge(`sudo renet job gc --older-than 0 --json`).catch(() => undefined);
      await w
        .executeViaBridge(`rm -f /tmp/e2e-jobs-*.json /tmp/e2e-jobs-*.sh`)
        .catch(() => undefined);
    });

    test('1. two concurrent starts with one request id give one job and one spool entry', async () => {
      const vault = await stageVault('dedupe', vaultFor(2890));
      const requestId = `e2e-dedupe-${Date.now()}`;
      const start = `sudo renet job start --executor local --json --request-id ${requestId} --vault @${vault}`;
      const [a, b] = await Promise.all([w.executeViaBridge(start), w.executeViaBridge(start)]);
      expect(a.code, a.stderr.slice(-400)).toBe(0);
      expect(b.code, b.stderr.slice(-400)).toBe(0);
      const ha = parseHandle(a.stdout);
      const hb = parseHandle(b.stdout);
      expect(ha.job_id, 'the two starts returned different jobs').toBe(hb.job_id);
      // Machine state: exactly one job in the spool carries the request id.
      const list = await w.executeViaBridge(`sudo renet job list --request-id ${requestId} --json`);
      expect(list.code, list.stderr.slice(-400)).toBe(0);
      const ids = (list.stdout.match(/j[0-9a-f]+-[0-9a-f]{8}/g) ?? []).filter(
        (id, i, all) => all.indexOf(id) === i
      );
      expect(ids, 'the spool holds more than one job for one request id').toEqual([ha.job_id]);
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

    test('3. two concurrent starts with network_id auto get distinct ids', async () => {
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
      expect(ha.network_id, 'both starts got the same network id').not.toBe(hb.network_id);
      // Machine state: each job's spool dir holds the id its start reported.
      for (const h of [ha, hb]) {
        const rec = await w.executeViaBridge(
          `sudo find /var/lib/rediacc ${WK_RUNTIME_DIR} /run/rediacc -path '*${h.job_id}/network_id' -exec cat {} + 2>/dev/null`
        );
        expect(rec.stdout.trim(), `spool network_id of ${h.job_id}`).toBe(String(h.network_id));
      }
    });

    test('4. job gc --older-than 0 leaves loaded units equal to live jobs', async () => {
      const gc = await w.executeViaBridge(`sudo renet job gc --older-than 0 --json`);
      expect(gc.code, gc.stderr.slice(-400)).toBe(0);
      const live = await w.executeViaBridge(`sudo renet job list --active --json`);
      expect(live.code, live.stderr.slice(-400)).toBe(0);
      const liveIds = new Set(live.stdout.match(/j[0-9a-f]+-[0-9a-f]{8}/g) ?? []);
      const unitIds = (await loadedJobUnits()).map((u) =>
        u.replace(/^rediacc-job-/, '').replace(/\.service$/, '')
      );
      expect(new Set(unitIds), 'a unit stays loaded for a job gc removed').toEqual(liveIds);
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

    test('6. repository status --json lists the running job under jobs', async () => {
      expect(holder, 'case 5 started no holder').toBeTruthy();
      const status = await w.executeViaBridge(
        `sudo renet repository status --name ${REPO} --datastore ${DS} --json`
      );
      expect(status.code, status.stderr.slice(-400)).toBe(0);
      const jsonStart = status.stdout.indexOf('{');
      const doc = JSON.parse(status.stdout.slice(jsonStart)) as {
        jobs?: { job_id?: string; JobID?: string }[];
      };
      expect(Array.isArray(doc.jobs), `no jobs array in: ${status.stdout.slice(-400)}`).toBe(true);
      const ids = (doc.jobs ?? []).map((j) => j.job_id ?? j.JobID);
      expect(ids, 'the holder is missing from the status jobs').toContain(holder?.job_id);
    });

    test('7. cancelling the holder releases the repository', async () => {
      expect(holder, 'case 5 started no holder').toBeTruthy();
      const id = holder?.job_id as string;
      // SIGCONT first so the stopped job process can take the SIGTERM the cancel sends.
      await w.executeViaBridge(`sudo systemctl kill -s CONT ${holder?.unit}`);
      const cancel = await w.executeViaBridge(`sudo renet job cancel --id ${id} --json`);
      expect(cancel.code, cancel.stderr.slice(-400)).toBe(0);
      const vault = await stageVault('third', vaultFor(2897, REPO));
      const again = await w.executeViaBridge(
        `sudo renet job start --executor local --json --vault @${vault}`
      );
      expect(again.code, `repository still held: ${again.stdout.slice(-300)}`).toBe(0);
      parseHandle(again.stdout);
      await w.repositoryRm(REPO, DS).catch(() => undefined);
      await w.repositoryRm(OTHER, DS).catch(() => undefined);
    });
  });
