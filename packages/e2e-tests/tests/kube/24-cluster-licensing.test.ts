import { readFile } from 'node:fs/promises';
import { expect, test } from '@playwright/test';
import { BridgeTestRunner } from '../../src/utils/bridge/BridgeTestRunner';
import { CliRunner } from '../../src/utils/CliRunner';
import {
  announcePrerequisites,
  type PrerequisiteVerdict,
  resolvePrerequisites,
} from '../../src/utils/declaredSkip';

/**
 * Suite 24 — the licensing-visible outcomes of the `rdc cluster` verbs (T6).
 *
 * Suite 23 proved the CLI can be driven end-to-end (CliRunner → real `rdc`);
 * this one drives the cluster family and asserts what Wave 2 made observable:
 * a cluster fork re-meters per contained repository, a machine slot is claimed
 * per node during placement, the slot pre-flight refuses BEFORE anything is
 * provisioned, and a migrate does NOT re-meter.
 *
 * ## Two prerequisite tiers, both fail-closed
 *
 * The assertions split by what they cost to run, so the cheap half is not held
 * hostage by the expensive half:
 *
 *   ACCOUNT tier — an account server and a subscription token. No VMs. The
 *     slot pre-flight is a declaration-time check (`assertMachineSlotsAvailable`
 *     runs before any provisioning), so asking for a pool larger than any
 *     plausible ceiling reaches the wall deterministically and spends nothing.
 *   VM tier — the multinode fleet AND an already-created cluster, named by
 *     `E2E_CLUSTER_NAME`. Fork/migrate re-metering can only be observed against
 *     real datastores.
 *
 * Each tier resolves through `declaredSkip`: present → run, absent WITH a
 * declared reason → loud skip on stderr, absent with no declaration → RED. A
 * silent skip is the failure mode that rule exists to prevent (the precedent is
 * renet's `RENET_EXPECT_NO_ACCOUNT_SERVER`, run-tests.sh:72-90).
 *
 * ## Why the VM tier adopts a cluster instead of creating one
 *
 * `rdc cluster create` provisions NEW VMs (libvirt for a kvm provider, a cloud
 * API otherwise). Standing up a second fleet inside the ops fleet is what the
 * 16GB runner ceiling rules out (rediacc/console#521), and suite 17 already
 * builds a two-node cluster on the existing workers through the bridge. So this
 * suite takes the cluster as an input and drives the verbs whose licensing
 * behaviour is the point: join, fork, migrate, replicate.
 *
 * ## Known coverage boundary
 *
 * The pre-flight's FAIL-OPEN direction (no token, or an unreachable server →
 * no refusal) cannot be asserted here: proving it means letting the CLI run
 * past the pre-flight into a real provisioning attempt. It is covered at unit
 * level in `packages/cli/src/services/__tests__/license-preflight.test.ts`.
 *
 * ## CI
 *
 * NOT on CI yet. The project entry in `playwright.k8s-multinode.config.ts` is
 * dark unless `CLUSTER_LICENSING_SUITE=1`, mirroring suite 23's `CLI_SUITE`
 * gate — wiring a ct-tests leg is a workflow change and out of this suite's
 * scope.
 *
 * Argv marked TRANSCRIPT-CONFIRM is the best-derived form from the CLI source
 * and is to be confirmed on the first live run; the assertion SHAPE is final.
 */

// ---------------------------------------------------------------------------
// Prerequisite tiers
// ---------------------------------------------------------------------------

const ACCOUNT_SERVER = (process.env.REDIACC_ACCOUNT_SERVER ?? '').trim();
const ACCOUNT_TOKEN = (process.env.E2E_ACCOUNT_API_TOKEN ?? '').trim();
const CLUSTER = (process.env.E2E_CLUSTER_NAME ?? '').trim();
const CLUSTER_REPO = (process.env.E2E_CLUSTER_REPO ?? '').trim();
const workers = (process.env.VM_WORKERS ?? '').trim().split(/\s+/).filter(Boolean);
const cephNodes = (process.env.VM_CEPH_NODES ?? '').trim();

const accountPrereqs = [
  {
    name: 'REDIACC_ACCOUNT_SERVER',
    satisfied: ACCOUNT_SERVER.length > 0,
    how: 'point it at an account server, e.g. `./run.sh account dev` on http://localhost:4800',
  },
  {
    name: 'E2E_ACCOUNT_API_TOKEN',
    satisfied: ACCOUNT_TOKEN.length > 0,
    how: 'mint an api token for a subscribed user and export it (the CLI logs in with `subscription login -t`)',
  },
];

const accountVerdict: PrerequisiteVerdict = resolvePrerequisites({
  label: 'cluster licensing pre-flight (ACCOUNT tier)',
  declareVar: 'E2E_EXPECT_NO_ACCOUNT_SERVER',
  prerequisites: accountPrereqs,
});

const vmVerdict: PrerequisiteVerdict = resolvePrerequisites({
  label: 'cluster licensing on the fleet (VM tier)',
  declareVar: 'E2E_EXPECT_NO_CLUSTER_VMS',
  prerequisites: [
    ...accountPrereqs,
    {
      name: 'K8S_MODE=1',
      satisfied: process.env.K8S_MODE === '1',
      how: 'set K8S_MODE=1 (the multinode topology)',
    },
    {
      name: 'VM_CEPH_NODES',
      satisfied: cephNodes.length > 0,
      how: 'provision the ceph nodes, e.g. VM_CEPH_NODES="21 22 23"',
    },
    {
      name: 'VM_WORKERS (two worker VMs)',
      satisfied: workers.length >= 2,
      how: 'bring the fleet up with two workers, e.g. VM_WORKERS="11 12"',
    },
    {
      name: 'E2E_CLUSTER_NAME',
      satisfied: CLUSTER.length > 0,
      how: 'name an already-created cluster on the fleet (this suite adopts one, it does not provision VMs)',
    },
    {
      name: 'E2E_CLUSTER_REPO',
      satisfied: CLUSTER_REPO.length > 0,
      how: 'name a repository living on that cluster, whose licences the fork/migrate assertions follow',
    },
  ],
});

// ---------------------------------------------------------------------------
// Shared harness
// ---------------------------------------------------------------------------

/** Own config namespace: suite 23's `e2e-cli` must not see these mutations. */
const CFG = 'e2e-cluster';

const SSH_KEY =
  process.env.E2E_SSH_KEY ??
  `${process.env.RENET_DATA_DIR ?? `${process.env.HOME}/.rediacc`}/staging/.ssh/id_rsa`;

/**
 * Cluster verbs are gate class D: `assertCommandPolicy` refuses them in an
 * agent environment unless the operator unlocked the cluster. Setting it in the
 * runner env is the sanctioned way and the only one available to a test — but
 * note the second half of the check (`isOverrideLegitimate`): when an agent
 * process is an ancestor, the variable must ALSO be present at that ancestor's
 * exec time. A run launched from inside an agent session where the operator did
 * not export it beforehand cannot pass, by design; test 1 detects exactly that
 * and says so rather than failing obscurely eight tests later.
 */
const CLUSTER_OPS_ENV = { REDIACC_ALLOW_CLUSTER_OPS: '*' };

/** The verbatim fragment `errors.agent.clusterOpBlocked` opens with. */
const POLICY_BLOCKED = 'is blocked in agent mode';

/** Verbatim fragments of `errors.license.machineSlotLimit` (en/cli.json:2071). */
const SLOT_LIMIT_FRAGMENTS = [
  'more machine slot(s)',
  'A slot is released automatically 5 hours after',
  'Raise the ceiling by upgrading the plan',
  'Enterprise or partner machine ceiling',
] as const;

/** Verbatim fragments of `errors.license.partialPlacement` (en/cli.json:2072). */
const PARTIAL_PLACEMENT_FRAGMENTS = [
  'The placement stopped part-way',
  'machine(s) completed',
  'were never started',
  'Nothing was rolled back, so the completed machines keep their repositories and their slots',
  'Free a slot or raise the ceiling, then re-run',
] as const;

/** Everything the CLI said, both channels — refusals arrive on stderr. */
const bothChannels = (r: { stdout: string; stderr: string }): string => r.stdout + r.stderr;

/**
 * Pull the four numbers out of the slot-limit message and assert they are
 * internally consistent.
 *
 * This is what makes the assertion falsifiable rather than a substring check on
 * a string the CLI could print for any reason: `free` must be the arithmetic
 * complement of the cap, and the refusal must be justified by its own numbers
 * (`active + needed > max`). A generic error text cannot satisfy that.
 */
function parseSlotLimit(text: string): {
  needed: number;
  free: number;
  active: number;
  max: number;
} {
  const m =
    /needs (\d+) more machine slot\(s\), and the subscription has (\d+) free \((\d+) of (\d+) in use\)/.exec(
      text
    );
  expect(m, `slot-limit message not found in:\n${text.slice(-1200)}`).not.toBeNull();
  const [needed, free, active, max] = m!.slice(1, 5).map(Number);
  expect(free, 'free must be max - active').toBe(Math.max(0, max - active));
  expect(active + needed, 'the refusal must be justified by its own numbers').toBeGreaterThan(max);
  return { needed, free, active, max };
}

/** The slice of rdc's config file these assertions read. */
interface CliConfigFile {
  resources?: {
    machines?: Record<string, unknown>;
    clusters?: Record<string, unknown>;
  };
}

/** `data.license_statuses[]` of `machine status --licenses -o json`. */
interface LicenseStatus {
  repositoryGuid: string;
  status: string;
  datastoreId?: string;
  blockedBackup?: { reason: string; message: string; at: string };
  lastRenewal?: { outcome: string; code?: string };
}

// ---------------------------------------------------------------------------
// ACCOUNT tier — the slot pre-flight refuses before spending anything
// ---------------------------------------------------------------------------

test.describe
  .serial('rdc cluster slot pre-flight @cli @cluster @licensing', () => {
    if (accountVerdict.kind === 'undeclared') {
      // A red, not a skip: the failure text names every unmet prerequisite and
      // the var that would declare the omission.
      test('ACCOUNT tier prerequisites are missing and undeclared', () => {
        expect(() => announcePrerequisites(accountVerdict)).not.toThrow();
      });
    } else {
      const gate = announcePrerequisites(accountVerdict);
      test.skip(gate.skip, gate.reason);
      test.setTimeout(300_000);

      let cli: CliRunner;
      // Two differently-sized asks, so the message can be shown to track the
      // request rather than being a fixed string.
      const BIG = 500;
      const OTHER = 321;
      const CL_BIG = 'e2e-lic-wall';
      const CL_OTHER = 'e2e-lic-wall2';
      const FAKE_NODE = 'e2e-lic-node';

      const machineNames = async (): Promise<string[]> => {
        const cfg = JSON.parse(await readFile(cli.configPath, 'utf8')) as CliConfigFile;
        return Object.keys(cfg.resources?.machines ?? {}).sort();
      };

      // A kvm declaration needs a network, and it must not be one the ops fleet
      // or any other cluster uses (192.168.111 is the harness's own).
      const declareArgs = (name: string, count: number): string[] => [
        'cluster',
        'create',
        name,
        '--provider',
        'kvm',
        '--pool',
        `nodes:k8s-server:${count}`,
        '--net-name',
        'renet-e2e-lic',
        '--net-base',
        '192.168.244',
      ];

      test.beforeAll(async () => {
        await CliRunner.resetConfig(CFG);
        cli = CliRunner.create({
          configName: CFG,
          // MUST be on: the default REDIACC_SKIP_MACHINE_ACTIVATION=1 removes
          // issuance and recovery outright, which is the behaviour under test.
          licensing: true,
          env: { ...CLUSTER_OPS_ENV, REDIACC_ACCOUNT_SERVER: ACCOUNT_SERVER },
        });
        await cli.initConfig(SSH_KEY);
        const login = await cli.run([
          'subscription',
          'login',
          '--server',
          ACCOUNT_SERVER,
          '--token',
          ACCOUNT_TOKEN,
        ]);
        expect(login.code, `subscription login: ${login.stderr.slice(-600)}`).toBe(0);
      });

      test('1. the subscription is readable and the cluster policy gate is open', async () => {
        const status = await cli.run(['subscription', 'status']);
        expect(status.code, `subscription status: ${status.stderr.slice(-600)}`).toBe(0);
        // The pre-flight reads the same two numbers this line prints; without
        // them every later refusal would be unattributable.
        expect(bothChannels(status), 'subscription status printed no machine-slot line').toMatch(
          /Machine slots: \d+\/\d+/
        );

        // Prove the policy gate is not silently eating the cluster verbs.
        const probe = await cli.run(['cluster', 'status']);
        expect(
          bothChannels(probe),
          'cluster verbs are policy-blocked. REDIACC_ALLOW_CLUSTER_OPS must also be present in the ' +
            'environment of the agent process that launched this run (isOverrideLegitimate); export ' +
            'it before starting the session.'
        ).not.toContain(POLICY_BLOCKED);
        expect(probe.code, `cluster status: ${probe.stderr.slice(-600)}`).toBe(0);
      });

      test(`2. a ${BIG}-node cluster is refused AT DECLARATION TIME, naming the limit and the Enterprise path`, async () => {
        const before = await machineNames();
        const res = await cli.run(declareArgs(CL_BIG, BIG));

        // ValidationError -> EXIT_CODES.INVALID_ARGUMENTS.
        expect(
          res.code,
          `expected exit 2, got ${res.code}:\n${bothChannels(res).slice(-800)}`
        ).toBe(2);
        const text = bothChannels(res);
        for (const fragment of SLOT_LIMIT_FRAGMENTS) {
          expect(text, `slot-limit message is missing: ${fragment}`).toContain(fragment);
        }
        const parsed = parseSlotLimit(text);
        expect(parsed.needed, 'the refusal must name the number of nodes asked for').toBe(BIG);

        // "Before anything is provisioned" is the whole product claim: the
        // cluster is declared in the config, and NOT ONE machine was created.
        expect(await machineNames(), 'the refused placement still created machines').toEqual(
          before
        );
      });

      test(`3. control: the same refusal for ${OTHER} nodes names ${OTHER}, so the message tracks the request`, async () => {
        // A fixed error string would pass test 2 and fail here. This is the
        // instrument check: the number is computed from the placement, which
        // means test 2 read the real cap and not a canned failure.
        const res = await cli.run(declareArgs(CL_OTHER, OTHER));
        expect(res.code).toBe(2);
        expect(parseSlotLimit(bothChannels(res)).needed).toBe(OTHER);
      });

      test('4. `cluster scale` past the ceiling is refused with the same message', async () => {
        // TRANSCRIPT-CONFIRM: `--pool` names the pool declared in test 2.
        const res = await cli.run([
          'cluster',
          'scale',
          CL_BIG,
          '--pool',
          'nodes',
          '--count',
          '900',
        ]);
        expect(res.code, `expected exit 2:\n${bothChannels(res).slice(-800)}`).toBe(2);
        const text = bothChannels(res);
        for (const fragment of SLOT_LIMIT_FRAGMENTS) {
          expect(text, `slot-limit message is missing: ${fragment}`).toContain(fragment);
        }
        const parsed = parseSlotLimit(text);
        expect(parsed.needed, 'scale asks for the delta, which must be positive').toBeGreaterThan(
          0
        );
      });

      test('5. control: `cluster join` needs ONE slot and is silent below the wall', async () => {
        // The counterpart to tests 2-4. join pre-flights with machineCount: 1
        // before it reads the cluster or dispatches anything, so under a cap with
        // room it must pass through in silence. Without this, a pre-flight that
        // refused everything would satisfy the tests above.
        const add = await cli.addMachine(FAKE_NODE, '192.168.244.9', process.env.USER ?? 'root');
        expect(add.code, `machine add: ${add.stderr.slice(-400)}`).toBe(0);

        const res = await cli.run(['cluster', 'join', FAKE_NODE, '--cluster', CL_BIG]);
        // It still fails — the cluster was never provisioned, so there is no
        // control plane to join — but NOT for a licensing reason.
        expect(res.code, 'join a non-existent control plane should not succeed').not.toBe(0);
        expect(
          bothChannels(res),
          'the pre-flight refused a single slot that the cap has room for'
        ).not.toContain('more machine slot(s)');
      });

      test.afterAll(async () => {
        // Config-only residue (nothing was provisioned), removed so a re-run
        // starts from the same state. TRANSCRIPT-CONFIRM: `cluster destroy` on a
        // never-provisioned declaration.
        // Guarded: a beforeAll that threw leaves `cli` unassigned, and teardown
        // must not turn that into a second, less informative failure.
        try {
          for (const name of [CL_BIG, CL_OTHER]) {
            await cli.run(['cluster', 'destroy', name, '--force']);
          }
          await cli.run(['machine', 'remove', FAKE_NODE, '-y']);
        } catch {
          // best-effort
        }
      });
    }
  });

// ---------------------------------------------------------------------------
// VM tier — fork re-meters per repo, migrate does not, slots land per node
// ---------------------------------------------------------------------------

test.describe
  .serial('rdc cluster licensing on the fleet @cli @cluster @licensing @bridge', () => {
    if (vmVerdict.kind === 'undeclared') {
      test('VM tier prerequisites are missing and undeclared', () => {
        expect(() => announcePrerequisites(vmVerdict)).not.toThrow();
      });
    } else {
      const gate = announcePrerequisites(vmVerdict);
      test.skip(gate.skip, gate.reason);
      test.setTimeout(1_800_000);

      const NET = process.env.VM_NET_BASE ?? '192.168.111';
      const M1 = 'machine-11';
      const M2 = 'machine-12';
      const FORK_TAG = `lic${Date.now().toString().slice(-6)}`;
      const FORK_CLUSTER = `${CLUSTER}-${FORK_TAG}`;
      const MIGRATE_CLUSTER = `${CLUSTER}-mig`;

      let cli: CliRunner;
      let w1: BridgeTestRunner;

      /** `machine status <m> --licenses -o json` -> data.license_statuses[]. */
      const licenseStatuses = async (machine: string): Promise<LicenseStatus[]> => {
        const { result, json } = await cli.runJson<{
          data?: { license_statuses?: LicenseStatus[] };
        }>(['machine', 'status', machine, '--licenses']);
        expect(
          result.code,
          `machine status ${machine} --licenses: ${result.stderr.slice(-600)}`
        ).toBe(0);
        expect(json?.data, `non-JSON status output: ${result.stdout.slice(0, 400)}`).toBeDefined();
        return json?.data?.license_statuses ?? [];
      };

      const datastoreIds = (statuses: LicenseStatus[]): string[] =>
        [...new Set(statuses.map((s) => s.datastoreId).filter((d): d is string => !!d))].sort();

      /**
       * The monthly issuance counter, from `subscription status`. Every reissue
       * burns one, which is how re-metering is counted rather than inferred.
       */
      const issuanceCount = async (): Promise<number> => {
        const res = await cli.run(['subscription', 'status']);
        expect(res.code, `subscription status: ${res.stderr.slice(-600)}`).toBe(0);
        const m = /Monthly repo license issuances: (\d+)\/(\d+)/.exec(bothChannels(res));
        expect(m, `no issuance line in:\n${bothChannels(res).slice(-800)}`).not.toBeNull();
        return Number(m![1]);
      };

      /** Machine slots as the server counts them right now. */
      const machineSlots = async (): Promise<{ active: number; max: number }> => {
        const res = await cli.run(['subscription', 'status']);
        const m = /Machine slots: (\d+)\/(\d+)/.exec(bothChannels(res));
        expect(m, `no machine-slot line in:\n${bothChannels(res).slice(-800)}`).not.toBeNull();
        return { active: Number(m![1]), max: Number(m![2]) };
      };

      test.beforeAll(async () => {
        w1 = BridgeTestRunner.forWorker(1);
        await CliRunner.resetConfig(CFG);
        cli = CliRunner.create({
          configName: CFG,
          licensing: true,
          env: { ...CLUSTER_OPS_ENV, REDIACC_ACCOUNT_SERVER: ACCOUNT_SERVER },
        });
        await cli.initConfig(SSH_KEY);
        await cli.addMachine(M1, `${NET}.${workers[0]}`, process.env.USER ?? 'root');
        await cli.addMachine(M2, `${NET}.${workers[1]}`, process.env.USER ?? 'root');
        const login = await cli.run([
          'subscription',
          'login',
          '--server',
          ACCOUNT_SERVER,
          '--token',
          ACCOUNT_TOKEN,
        ]);
        expect(login.code, `subscription login: ${login.stderr.slice(-600)}`).toBe(0);
      });

      test('1. baseline: every repo on the cluster holds a datastore-scoped licence', async () => {
        const statuses = await licenseStatuses(M1);
        expect(statuses.length, 'the cluster node reports no licences at all').toBeGreaterThan(0);
        for (const s of statuses) {
          expect(s.status, `${s.repositoryGuid} is not valid at baseline`).toBe('valid');
          // Wave 2 re-scoped the on-machine store under the datastore identity;
          // a licence without one is the pre-Wave-2 unscoped path.
          expect(s.datastoreId, `${s.repositoryGuid} carries no datastoreId`).toBeTruthy();
          expect(s.blockedBackup, `${s.repositoryGuid} already has a backup block`).toBeUndefined();
        }
      });

      test('2. a slot is claimed per node holding repositories', async () => {
        const slots = await machineSlots();
        // Both cluster nodes hold repositories, so both must have claimed.
        expect(
          slots.active,
          'fewer active slots than nodes holding repositories'
        ).toBeGreaterThanOrEqual(2);
        expect(
          slots.active,
          'active slots exceed the cap without a soft-claim'
        ).toBeLessThanOrEqual(slots.max);

        // Per-machine cross-check: each node's own licence table is non-empty,
        // so the count above is two real nodes rather than one counted twice.
        for (const m of [M1, M2]) {
          const per = await cli.run(['subscription', 'status', '-m', m]);
          expect(per.code, `subscription status -m ${m}: ${per.stderr.slice(-400)}`).toBe(0);
          expect(bothChannels(per), `${m} reports no repo licences`).not.toContain(
            'No repo licenses installed'
          );
        }
      });

      test('3. `cluster fork` re-mints the datastore identity, so every contained repo re-meters', async () => {
        const parentIds = datastoreIds(await licenseStatuses(M1));
        expect(parentIds.length, 'no parent datastore identity to compare against').toBeGreaterThan(
          0
        );
        const issuedBefore = await issuanceCount();

        const fork = await cli.run([
          'cluster',
          'fork',
          CLUSTER,
          '--tag',
          FORK_TAG,
          '--to',
          FORK_CLUSTER,
        ]);
        expect(fork.code, `cluster fork: ${bothChannels(fork).slice(-800)}`).toBe(0);

        // The fork's repos live under a NEW datastore identity. That re-mint is
        // the whole metering mechanism: the licence store is keyed by it, so the
        // inherited blobs are not at the path the fork looks in.
        const forkStatuses = await licenseStatuses(M1);
        const forkIds = datastoreIds(forkStatuses).filter((id) => !parentIds.includes(id));
        expect(forkIds.length, 'the fork reused the parent datastore identity').toBeGreaterThan(0);

        // Re-metering is lazy: the fork itself issues nothing, the next licensed
        // touch does. Assert the pre-touch state so the reissue below is a real
        // transition and not a repo that was already licensed.
        const forkRepos = forkStatuses.filter((s) => forkIds.includes(s.datastoreId ?? ''));
        expect(forkRepos.length, 'the fork contains no repositories').toBeGreaterThan(0);
        for (const s of forkRepos) {
          expect(s.status, `${s.repositoryGuid} was already licensed on the fork`).toBe('missing');
        }

        // The touch: an operate-tier verb validates the licence, renet answers
        // exit 10 / missing, and the CLI's recovery reissues per repository.
        // TRANSCRIPT-CONFIRM: the ref form for a forked cluster's repository.
        const touch = await cli.run(['repo', 'up', `${CLUSTER_REPO}:${FORK_TAG}`]);
        expect(touch.code, `repo up on the fork: ${bothChannels(touch).slice(-800)}`).toBe(0);

        const after = await licenseStatuses(M1);
        for (const s of after.filter((x) => forkIds.includes(x.datastoreId ?? ''))) {
          expect(s.status, `${s.repositoryGuid} did not reissue after the touch`).toBe('valid');
        }
        // Counted, not inferred: each re-metered repository burned an issuance.
        expect(
          await issuanceCount(),
          'the fork re-metered without consuming any issuance'
        ).toBeGreaterThan(issuedBefore);
      });

      test('4. `cluster migrate` does NOT re-meter: same identity, same licences, no issuance', async () => {
        const before = await licenseStatuses(M1);
        const idsBefore = datastoreIds(before);
        const issuedBefore = await issuanceCount();

        const mig = await cli.run(['cluster', 'migrate', FORK_CLUSTER, '--to', MIGRATE_CLUSTER]);
        expect(mig.code, `cluster migrate: ${bothChannels(mig).slice(-800)}`).toBe(0);

        // A migrate moves the datastore record; it does not re-mint the identity,
        // so the licence store path is unchanged and nothing reads as missing.
        const after = await licenseStatuses(M2);
        expect(datastoreIds(after), 'migrate re-minted the datastore identity').toEqual(idsBefore);
        for (const s of after) {
          expect(s.status, `${s.repositoryGuid} lost its licence across a migrate`).toBe('valid');
        }
        expect(await issuanceCount(), 'migrate consumed an issuance').toBe(issuedBefore);
      });

      test('5. a placement that stops part-way says what exists and what to re-run', async () => {
        // A replica set is placed one node at a time and is deliberately NOT
        // rolled back, so any mid-loop failure must report the partial state.
        // TRANSCRIPT-CONFIRM: the second run collides on the replica fork tag
        // (`<set>-r1`), which is the cheapest deterministic mid-loop failure; a
        // genuine slot-wall trigger needs a server-side maxActivations setter,
        // which does not exist today (reported as a finding).
        const first = await cli.run([
          'repo',
          'replicate',
          CLUSTER_REPO,
          '--replicas',
          '2',
          '--image',
          'nginx:alpine',
          '--port',
          '80',
        ]);
        expect(first.code, `first replicate: ${bothChannels(first).slice(-800)}`).toBe(0);

        const second = await cli.run([
          'repo',
          'replicate',
          CLUSTER_REPO,
          '--replicas',
          '2',
          '--image',
          'nginx:alpine',
          '--port',
          '80',
        ]);
        expect(second.code, 'a colliding replicate should not succeed').not.toBe(0);
        const text = bothChannels(second);
        for (const fragment of PARTIAL_PLACEMENT_FRAGMENTS) {
          expect(text, `partial-placement guidance is missing: ${fragment}`).toContain(fragment);
        }
        // The guidance must hand back a runnable command, not just a diagnosis.
        expect(text).toContain(`rdc repo replicate ${CLUSTER_REPO} --replicas 2`);
      });

      test('6. the bridge agrees the fork exists (the CLI claims are not self-referential)', async () => {
        // Ground truth from renet, the same cross-check suite 23 uses: the CLI's
        // licence view above is only meaningful if the storage really forked.
        const res = await w1.executeViaBridge(
          'renet functions once --test-mode --debug --function repository_list'
        );
        expect(res.code, `bridge repository_list: ${res.stderr.slice(-400)}`).toBe(0);
        const statuses = await licenseStatuses(M2);
        for (const s of statuses) {
          expect(
            res.stdout + res.stderr,
            `${s.repositoryGuid} is licensed but absent from storage`
          ).toContain(s.repositoryGuid);
        }
      });

      test.afterAll(async () => {
        try {
          for (const name of [MIGRATE_CLUSTER, FORK_CLUSTER]) {
            await cli.run(['cluster', 'destroy', name, '--force']);
          }
        } catch {
          // best-effort
        }
      });
    }
  });
