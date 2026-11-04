import { randomUUID } from 'node:crypto';
import { expect, test } from '@playwright/test';
import { WK_RUNTIME_DIR } from '@rediacc/shared/config/well-known.generated';
import { DEFAULT_DATASTORE_PATH } from '../src/constants';
import { RenetFunctionsTestRunner } from '../src/utils/renet-functions/RenetFunctionsTestRunner';

// Suite 32: detached jobs on a real worker, through the bridge. Every assertion reads machine state (the job spool, `systemctl list-units 'rediacc-job-*'`, `renet job list`, `renet repository status`), never the stdout of the command under test alone. The unit tests of renet drive the same code against a temp dir and a fake systemd; the races here (two processes, one spool) only exist on a real machine.
//
// Not covered here, by design of the harness: the repo-exclusive refusal (exit 15 naming the running job) needs a job that stays live long enough to race, and no vault function sleeps; PLAN-jobs-backup-real-machine-tests E1 keeps that case open until a holder job exists. The repository-status case (the running job listed under `jobs`) needs a provisioned repository with a live job, so it waits with the holder job. The "planted red" half (dedupe disabled through a renet test seam) needs a renet change outside this suite.

const DS = DEFAULT_DATASTORE_PATH;
const GUID = randomUUID();

interface Handle {
  job_id: string;
  unit: string;
  deduped?: boolean;
  network_id?: number;
}

const vaultFor = (networkId: number | 'auto', guid = GUID): string =>
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
      await w.executeViaBridge(`rm -f /tmp/e2e-jobs-*.json`).catch(() => undefined);
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
      const start = await w.executeViaBridge(
        `sudo renet job start --executor local --json --vault @${vault}`
      );
      const { job_id: id } = parseHandle(start.stdout);
      const claim = `sudo renet job claim --id ${id} --steps s --json`;
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
      const vault = await stageVault('auto', vaultFor('auto'));
      const start = `sudo renet job start --executor local --json --vault @${vault}`;
      const [a, b] = await Promise.all([w.executeViaBridge(start), w.executeViaBridge(start)]);
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
  });
