/**
 * `rdc repo canary` — release-ladder rung 2 (spec 05 §2) with managed-state
 * CRUD from birth (R2-F17): the bare command creates a canary; `status`,
 * `weight` and `remove` operate on recorded sets. Every release-class mutation
 * first takes the rung-0 group snapshot (universal undo). Orchestration lives
 * in services/cluster/repo-release.ts.
 */

import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import {
  createCanary,
  listCanaries,
  removeCanary,
  setCanaryWeight,
} from '../services/cluster/repo-release.js';
import { outputService } from '../services/core/output.js';
import { getOutputFormat, handleError } from '../utils/errors.js';

export function registerRepoCanaryCommands(repo: Command): void {
  const canary = repo
    .command('canary')
    .summary(t('commands.repo.canary.descriptionShort'))
    .description(t('commands.repo.canary.description'))
    .option('--name <repo>', t('commands.repo.canary.nameOption'))
    .option('--cluster <name>', t('commands.repo.clusterOption'))
    .option('--image <image>', t('commands.repo.canary.imageOption'))
    .option('--port <port>', t('commands.repo.canary.portOption'))
    .option('--weight <percent>', t('commands.repo.canary.weightOption'))
    .option('--service <name>', t('commands.repo.canary.serviceOption'))
    .option('--replicas <n>', t('commands.repo.canary.replicasOption'))
    .option('--debug', t('options.debug'))
    .action(
      async (options: {
        name?: string;
        cluster?: string;
        image?: string;
        port?: string;
        weight?: string;
        service?: string;
        replicas?: string;
        debug?: boolean;
      }) => {
        try {
          for (const [flag, value] of [
            ['--name', options.name],
            ['--cluster', options.cluster],
            ['--image', options.image],
            ['--port', options.port],
            ['--weight', options.weight],
          ] as const) {
            if (!value) throw new Error(`${flag} is required`);
          }
          await createCanary({
            repo: options.name as string,
            cluster: options.cluster as string,
            image: options.image as string,
            port: Number(options.port),
            weight: Number(options.weight),
            service: options.service,
            replicas: options.replicas ? Number(options.replicas) : undefined,
            debug: options.debug,
          });
        } catch (error) {
          handleError(error);
        }
      }
    );

  canary
    .command('status')
    .summary(t('commands.repo.canary.status.descriptionShort'))
    .description(t('commands.repo.canary.status.description'))
    .option('--name <set>', t('commands.repo.canary.status.nameOption'))
    .action(async (options: { name?: string }) => {
      try {
        const all = await listCanaries();
        if (options.name && !(options.name in all)) {
          throw new Error(`Canary "${options.name}" not found.`);
        }
        const sets = options.name ? { [options.name]: all[options.name] } : all;
        outputService.print(sets, getOutputFormat());
      } catch (error) {
        handleError(error);
      }
    });

  canary
    .command('weight')
    .summary(t('commands.repo.canary.weight.descriptionShort'))
    .description(t('commands.repo.canary.weight.description'))
    .requiredOption('--name <set>', t('commands.repo.canary.weight.nameOption'))
    .requiredOption('--weight <percent>', t('commands.repo.canary.weightOption'))
    .option('--debug', t('options.debug'))
    .action(async (options: { name: string; weight: string; debug?: boolean }) => {
      try {
        await setCanaryWeight(options.name, Number(options.weight), options.debug);
      } catch (error) {
        handleError(error);
      }
    });

  canary
    .command('remove')
    .summary(t('commands.repo.canary.remove.descriptionShort'))
    .description(t('commands.repo.canary.remove.description'))
    .requiredOption('--name <set>', t('commands.repo.canary.remove.nameOption'))
    .option('--debug', t('options.debug'))
    .action(async (options: { name: string; debug?: boolean }) => {
      try {
        await removeCanary(options.name, options.debug);
      } catch (error) {
        handleError(error);
      }
    });
}
