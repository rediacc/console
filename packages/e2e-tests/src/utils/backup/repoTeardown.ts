import type { CliRunner } from '../CliRunner';
import type { RenetFunctionsTestRunner } from '../renet-functions/RenetFunctionsTestRunner';
import { bothChannels, configRepoFamilies, DS } from './chunkCliHarness';

/**
 * Teardown for the repositories a backup suite creates, by GUID, on every worker it touches.
 *
 * The suites loginCli into one config namespace, and `loginCli` RESETS that config, so a tier's
 * repositories are only reachable by name until the next tier starts. A tier that deleted nothing
 * (or swallowed a failed delete) left images, locks and mounts behind on the workers, and a repo
 * that stayed mounted kept its network id: suite 32 case 5 then failed on id 9152 and the cause
 * was hidden by the retry.
 *
 * Order: the CLI deletes first (forks before their grand, so the CLI's own bookkeeping runs), then a
 * GUID-level sweep on each worker unmounts what is still mounted and removes what is still on disk.
 * Everything the sweep finds after a CLI delete that reported success is printed, because it is a
 * defect in `repo delete`, not in the suite. Every failure is collected and thrown at the end, so one
 * stuck repo does not stop the others from being removed, and the run still goes red.
 */

const GUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/**
 * What is still on `runner` for `guids`, one `<kind> <guid>` line each.
 *
 * No shell variable anywhere: the bridge call runs the command through nested `ssh`, and an outer shell expands a `$g` to nothing before the inner one sees it (measured: every probe then reported an image for the empty name).
 */
const residue = async (runner: RenetFunctionsTestRunner, guids: string[]): Promise<string[]> => {
  if (guids.length === 0) return [];
  const probes = guids.flatMap((g) => [
    `sudo mountpoint -q "${DS}/mounts/${g}" && echo "mounted ${g}"`,
    `sudo test -e "${DS}/repositories/${g}" && echo "image ${g}"`,
    `sudo test -e "${DS}/repositories/.restore-${g}" && echo "staging ${g}"`,
    `sudo test -e "${DS}/repositories/.lock-${g}" && echo "lock ${g}"`,
    `sudo test -d "${DS}/mounts/${g}" && echo "mountdir ${g}"`,
  ]);
  const probe = await runner.executeViaBridge(`{ ${probes.join('; ')}; true; }`);
  return probe.stdout
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => /^(mounted|image|staging|lock|mountdir) [0-9a-f-]{36}$/.test(line));
};

/** Unmount what is mounted and delete what is on disk, then report what survived. */
const sweepWorker = async (
  label: string,
  runner: RenetFunctionsTestRunner,
  guids: string[],
  failures: string[]
): Promise<void> => {
  const found = await residue(runner, guids);
  if (found.length === 0) return;
  console.warn(`teardown: ${label} still held ${found.join(', ')} after the CLI deletes`);
  for (const line of found.filter((l) => l.startsWith('mounted '))) {
    const guid = line.slice('mounted '.length);
    const out = await runner.repositoryUnmount(guid, DS);
    if (out.code !== 0)
      failures.push(`${label}: unmount ${guid}: ${bothChannels(out).slice(-300)}`);
  }
  const rm = guids
    .map(
      (g) =>
        `sudo rm -f "${DS}/repositories/${g}" "${DS}/repositories/.restore-${g}" "${DS}/repositories/.lock-${g}"; sudo mountpoint -q "${DS}/mounts/${g}" || sudo rm -rf "${DS}/mounts/${g}"`
    )
    .join('; ');
  await runner.executeViaBridge(`${rm}; true`);
  const left = await residue(runner, guids);
  if (left.length > 0) failures.push(`${label}: could not remove ${left.join(', ')}`);
};

/** `repo delete` for every tag of every family, a fork before the grand it was cut from; each refusal is recorded, none stops the rest. */
const deleteFamilies = async (
  cli: CliRunner,
  families: ReturnType<typeof configRepoFamilies>,
  failures: string[]
): Promise<void> => {
  for (const family of families) {
    // Always `name:tag`: a restored copy registers as a fork of its lineage with no grand tag of its own, and the bare name is then refused as ambiguous.
    const tags = Object.keys(family.tags).sort(
      (a, b) => Number(a === family.grand) - Number(b === family.grand)
    );
    for (const ref of tags.map((tag) => `${family.name}:${tag}`)) {
      const out = await cli.run(['repo', 'delete', ref, '-y']);
      if (out.code !== 0) failures.push(`repo delete ${ref}: ${bothChannels(out).slice(-400)}`);
    }
  }
};

export interface TeardownTargets {
  readonly cli: CliRunner;
  /** One entry per worker the suite wrote to, labelled for the failure message. */
  readonly workers: readonly { label: string; runner: RenetFunctionsTestRunner }[];
  /** GUIDs the config never held (raw-verb targets), swept on every worker. */
  readonly extraGuids?: readonly string[];
}

/** Remove every repository in the CLI config and `extraGuids` from the CLI and from each worker; throws one error naming every failure. */
export const teardownRepos = async (targets: TeardownTargets): Promise<void> => {
  const failures: string[] = [];
  const families = configRepoFamilies(targets.cli);
  const guids = [
    ...new Set([...families.flatMap((f) => Object.values(f.tags)), ...(targets.extraGuids ?? [])]),
  ];
  for (const guid of guids) {
    if (!GUID.test(guid)) failures.push(`not a GUID, refusing to put it in a shell: ${guid}`);
  }
  const valid = guids.filter((g) => GUID.test(g));

  await deleteFamilies(targets.cli, families, failures);
  for (const { label, runner } of targets.workers) {
    await sweepWorker(label, runner, valid, failures);
  }
  if (failures.length > 0) {
    throw new Error(`teardown left residue:\n${failures.join('\n')}`);
  }
};
