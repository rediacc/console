import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config/config-resources.js';
import { parseCapturedJson } from '../services/executor/renet-output.js';
import { handleError, ValidationError } from '../utils/errors.js';
import { executeRepoFunction } from '../utils/repo-executor.js';
import { resolveRepoRef } from '../utils/repo-target.js';
import { assertMachineExists } from './_validate.js';

interface GpuOptions {
  device: string;
  exclusive?: boolean;
  debug?: boolean;
}

type GpuVerb = 'grant' | 'revoke';

/** The device names of the grant renet printed (`daemon grant --show`), or undefined when the output carries none. */
function grantedNames(stdout: string | undefined): string[] | undefined {
  try {
    const grant = parseCapturedJson<{ devices?: { name: string }[] | null }>(stdout);
    // `null` is renet's empty grant (a Go nil slice), so the listing is empty; output without a devices key is not a listing and the caller falls back to editing the mirror.
    if (grant.devices === null) return [];
    if (!Array.isArray(grant.devices)) return undefined;
    return grant.devices.map((d) => d.name);
  } catch {
    return undefined;
  }
}

/** The mirror after the verb, when renet's own listing could not be read. */
function mirrorAfter(current: string[], verb: GpuVerb, device: string): string[] {
  const rest = current.filter((d) => d !== device);
  return verb === 'grant' ? [...rest, device] : rest;
}

async function handleGpuVerb(verb: GpuVerb, ref: string, options: GpuOptions): Promise<void> {
  const { name, repoKey, machineName, kubeCluster } = await resolveRepoRef(ref);
  if (kubeCluster) {
    throw new ValidationError(t('errors.cluster.dockerOnlyVerb', { verb: `gpu ${verb}` }));
  }
  await assertMachineExists(machineName);

  const params: Record<string, unknown> = { device: options.device };
  if (verb === 'grant' && options.exclusive) params.exclusive = true;

  const result = await executeRepoFunction(
    `repository_gpu_${verb}`,
    repoKey,
    machineName,
    params,
    { debug: options.debug, captureOutput: true },
    {
      starting: VERB_TEXT[verb].starting({
        device: options.device,
        repository: name,
        machine: machineName,
      }),
      completed: VERB_TEXT[verb].completed({
        device: options.device,
        repository: name,
      }),
      failed: VERB_TEXT[verb].failed(),
    }
  );
  if (!result.success) return;

  const current = (await configService.getRepository(repoKey))?.gpuDevices ?? [];
  const names = grantedNames(result.stdout) ?? mirrorAfter(current, verb, options.device);
  await configService.setRepositoryGpuDevices(repoKey, names);
}

/** Each verb's text, as literal keys so the orphan-key gate sees every one. */
const VERB_TEXT = {
  grant: {
    summary: () => t('commands.repo.gpu.grant.descriptionShort'),
    description: () => t('commands.repo.gpu.grant.description'),
    starting: (vars: Record<string, string>) => t('commands.repo.gpu.grant.starting', vars),
    completed: (vars: Record<string, string>) => t('commands.repo.gpu.grant.completed', vars),
    failed: () => t('commands.repo.gpu.grant.failed'),
  },
  revoke: {
    summary: () => t('commands.repo.gpu.revoke.descriptionShort'),
    description: () => t('commands.repo.gpu.revoke.description'),
    starting: (vars: Record<string, string>) => t('commands.repo.gpu.revoke.starting', vars),
    completed: (vars: Record<string, string>) => t('commands.repo.gpu.revoke.completed', vars),
    failed: () => t('commands.repo.gpu.revoke.failed'),
  },
} as const;

/** Register `repo gpu grant|revoke`: CDI device grants of a repository (the machine's grant store enforces them). */
export function registerRepoGpuCommands(repo: Command): void {
  const gpu = repo
    .command('gpu')
    .summary(t('commands.repo.gpu.descriptionShort'))
    .description(t('commands.repo.gpu.description'));

  for (const verb of ['grant', 'revoke'] as const) {
    const command = gpu
      .command(verb)
      .summary(VERB_TEXT[verb].summary())
      .description(VERB_TEXT[verb].description())
      .argument('<ref>', t('options.repoRef'))
      .requiredOption('--device <cdi-name>', t('commands.repo.gpu.deviceOption'));
    if (verb === 'grant') {
      command.option('--exclusive', t('commands.repo.gpu.grant.exclusiveOption'));
    }
    command
      .option('--debug', t('options.debug'))
      .action(async (ref: string, options: GpuOptions) => {
        try {
          await handleGpuVerb(verb, ref, options);
        } catch (error) {
          handleError(error);
        }
      });
  }
}
