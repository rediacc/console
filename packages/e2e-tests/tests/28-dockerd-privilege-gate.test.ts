import { expect, test } from '@playwright/test';
import { repoDockerHost, repoDockerSocketPath } from '@rediacc/shared/config/runtime-paths';
import {
  DEFAULT_DATASTORE_PATH,
  DEFAULT_NETWORK_ID,
  FORK_NETWORK_ID_A,
  TEST_PASSWORD,
} from '../src/constants';
import { RenetFunctionsTestRunner } from '../src/utils/renet-functions/RenetFunctionsTestRunner';
import type { ExecResult } from '../src/utils/renet-functions/types';

/**
 * Suite 28: the per-repo Docker API privilege gate
 * (agent/plans/PLAN-dockerd-api-privilege-gate.md).
 *
 * ## The defect it guards
 *
 * Before private/renet 031d303..c10df9a, a container in repo A that held
 * `${DOCKER_SOCKET}` could ask A's own dockerd for `docker run --privileged
 * --pid=host`, and that container reached repo B's daemon through
 * `/proc/1/root/run/rediacc/net-<B>/docker-<B>.sock` (worklist #8cb01693,
 * reproduced live on ops-worker 2026-10-23). The compose validator only ever
 * read compose files; the Docker API itself had no gate.
 *
 * renet now serves `net-<N>/docker-<N>.sock` through a policy proxy, with
 * dockerd behind it on an internal socket. A refused create answers HTTP 403
 * with "refused by this repository's Docker API gate (...)", which the Docker
 * CLI prints as `Error response from daemon: ...` and exits non-zero.
 *
 * ## What each case proves
 *
 * Both paths go through A's public socket, which is the only socket a repo
 * workload is handed:
 *
 *   1. the host CLI as root through `-H unix://<A's socket>` (the way every
 *      other suite reaches a repo daemon, `RepositoryHelpers.isContainerRunning`);
 *   2. a container in A holding `${DOCKER_SOCKET}` (A's own socket bound at
 *      `/var/run/docker.sock`), driving the attack from inside, which is the
 *      defect's own shape.
 *
 * On each path four attacks must exit non-zero AND name the gate: privileged
 * mode, the host PID namespace, a writable bind of `/etc`, and a bind of repo
 * B's Docker socket. A non-zero exit alone is not enough, because a missing
 * image or a dead daemon also exits non-zero. Each path also carries a
 * CONTROL, a plain `docker run` that must exit 0 through the same socket, so a
 * broken daemon fails the test instead of passing every refusal vacuously.
 *
 * ## Asking the machine
 *
 * Each attack carries a run-unique label and no `--rm`. A gate that failed
 * open would leave a created container behind, so after the attacks the
 * daemon itself is asked to list containers with that label, and it must
 * list none.
 *
 * Expected substrings are lowercase: `getCombinedOutput` lowercases
 * (`TestHelpers.ts`).
 */

const RUN_ID = Date.now();
const CONTROL_IMAGE = 'alpine:3.20';
// The nested client. Pinned so a docker:cli release cannot change what the in-container case runs; the CLI negotiates its API version down to the daemon's.
const NESTED_CLI_IMAGE = 'docker:28-cli';
const GATE_MARKER = 'docker api gate';
const ATTACK_LABEL = `rediacc.e2e.gate-attack=${RUN_ID}`;

interface Attack {
  name: string;
  /** `docker run` flags that carry the attack. */
  flags: string;
  /** Lowercase text the refusal must also carry, naming what was refused. */
  names: string;
}

test.describe
  .serial('Docker API privilege gate @bridge', () => {
    let runner: RenetFunctionsTestRunner;
    const datastorePath = DEFAULT_DATASTORE_PATH;
    const repoA = `gate-a-${RUN_ID}`;
    const repoB = `gate-b-${RUN_ID}`;
    const networkA = DEFAULT_NETWORK_ID;
    const networkB = FORK_NETWORK_ID_A;
    const socketA = repoDockerSocketPath(networkA);
    const socketB = repoDockerSocketPath(networkB);
    const dockerA = `sudo docker -H ${repoDockerHost(networkA)}`;

    const attacks: Attack[] = [
      {
        name: 'privileged mode',
        flags: '--privileged',
        names: 'privileged: privileged mode is refused',
      },
      { name: 'host pid namespace', flags: '--pid=host', names: 'pidmode: pid:host is refused' },
      {
        name: 'writable bind of /etc',
        flags: '-v /etc:/h',
        names: 'binds: bind mount of "/etc" is refused',
      },
      {
        name: "bind of repo B's docker socket",
        flags: `-v ${socketB}:/b.sock`,
        names: `binds: bind mount of host runtime path "${socketB}"`,
      },
    ];

    /** Throw with the command's output unless it succeeded. */
    function must(step: string, result: ExecResult): void {
      if (!runner.isSuccess(result)) {
        throw new Error(`${step} failed: ${runner.getCombinedOutput(result)}`);
      }
    }

    /** Write the nginx fixture into a mounted repo under a container name of its own. */
    async function writeNginx(name: string): Promise<void> {
      must(
        `writing ${name}'s Rediaccfile`,
        await runner.writeFileToRepository(
          name,
          'Rediaccfile',
          runner.readFixture('bridge/Rediaccfile.nginx'),
          datastorePath
        )
      );
      must(
        `writing ${name}'s compose file`,
        await runner.writeFileToRepository(
          name,
          'docker-compose.yaml',
          runner
            .readFixture('bridge/docker-compose.nginx.yaml')
            .replaceAll('${CONTAINER_NAME}', `nginx-${name}`),
          datastorePath
        )
      );
    }

    /** One attack must exit non-zero and name both the gate and what it refused. */
    function expectRefused(attack: Attack, path: string, result: ExecResult): void {
      const output = runner.getCombinedOutput(result);
      expect(result.code, `${path}: ${attack.name} must exit non-zero\n${output}`).not.toBe(0);
      expect(output, `${path}: ${attack.name} must be refused by the gate`).toContain(GATE_MARKER);
      expect(output, `${path}: ${attack.name} refusal must name what it refused`).toContain(
        attack.names
      );
    }

    /** The daemon must hold no container this run's attacks created. */
    async function expectNoAttackContainers(path: string): Promise<void> {
      const listed = await runner.executeViaBridge(
        `${dockerA} ps -a --filter label=${ATTACK_LABEL} --format {{.ID}}`
      );
      expect(listed.code, `${path}: listing A's containers must succeed`).toBe(0);
      expect(listed.stdout.trim(), `${path}: a refused create must leave no container`).toBe('');
    }

    test.beforeAll(async () => {
      runner = RenetFunctionsTestRunner.forWorker();
      await runner.resetWorkerState();
      await runner.datastoreInitPool('5G', datastorePath, true);
      // B is a fork of A on its own network id: repository_create always takes the harness's default network id, so a second fresh repo would collide with A's claim. B is only mounted, which starts its daemon and socket: its services stay down, because the repo's compose runs on the host network and a second nginx would collide with A's on port 80. No daemon pre-start: mount and up claim each network id and start that daemon themselves (see suite 07's beforeAll).
      must(
        'repository_new A',
        await runner.repositoryNew(repoA, '1G', TEST_PASSWORD, datastorePath)
      );
      await writeNginx(repoA);
      must('repository_unmount A', await runner.repositoryUnmount(repoA, datastorePath));
      must(
        'repository fork A -> B',
        await runner.createRepositoryFork(repoA, repoB, datastorePath, networkB)
      );
      must(
        'repository_mount A',
        await runner.repositoryMount(repoA, TEST_PASSWORD, datastorePath, networkA)
      );
      must('repository_up A', await runner.repositoryUp(repoA, datastorePath, networkA));
      must(
        'repository_mount B',
        await runner.repositoryMount(repoB, TEST_PASSWORD, datastorePath, networkB)
      );

      const socketBExists = await runner.executeViaBridge(`sudo test -S ${socketB}`);
      if (socketBExists.code !== 0) {
        throw new Error(
          `repo B's socket ${socketB} is absent, so the cross-repo bind case would prove nothing`
        );
      }
    });

    test.afterAll(async () => {
      await runner.executeViaBridge(
        `${dockerA} ps -aq --filter label=${ATTACK_LABEL} | xargs -r ${dockerA} rm -f`
      );
      // Each repo is torn down with its own network id, so the harness default (A's) never aims at the wrong daemon. A goes first, then B.
      await runner.repositoryDown(repoA, datastorePath, networkA);
      await runner.repositoryUnmount(repoA, datastorePath, networkA);
      await runner.repositoryRm(repoA, datastorePath, networkA);
      await runner.daemonTeardown(networkA);
      await runner.repositoryUnmount(repoB, datastorePath, networkB);
      await runner.repositoryRm(repoB, datastorePath, networkB);
      await runner.daemonTeardown(networkB);
    });

    test("host CLI through repo A's socket: a plain run passes, every attack is refused", async () => {
      const path = 'host CLI';
      const control = await runner.executeViaBridge(`${dockerA} run --rm ${CONTROL_IMAGE} true`);
      expect(
        control.code,
        `${path}: the control run must exit 0\n${runner.getCombinedOutput(control)}`
      ).toBe(0);

      for (const attack of attacks) {
        const result = await runner.executeViaBridge(
          `${dockerA} run --label ${ATTACK_LABEL} ${attack.flags} ${CONTROL_IMAGE} true`
        );
        expectRefused(attack, path, result);
      }
      await expectNoAttackContainers(path);
    });

    test('container in repo A holding ${DOCKER_SOCKET}: a plain run passes, every attack is refused', async () => {
      const path = 'nested container';
      const nested = `${dockerA} run --rm -v ${socketA}:/var/run/docker.sock ${NESTED_CLI_IMAGE} docker`;

      const control = await runner.executeViaBridge(`${nested} run --rm ${CONTROL_IMAGE} true`);
      expect(
        control.code,
        `${path}: the control run must exit 0\n${runner.getCombinedOutput(control)}`
      ).toBe(0);

      for (const attack of attacks) {
        const result = await runner.executeViaBridge(
          `${nested} run --label ${ATTACK_LABEL} ${attack.flags} ${CONTROL_IMAGE} true`
        );
        expectRefused(attack, path, result);
      }
      await expectNoAttackContainers(path);
    });
  });
