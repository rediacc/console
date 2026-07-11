/**
 * `rdc repo replicate` — instant read replicas (spec 05 §1) with managed-state
 * CRUD from birth (R2-F17): the bare command creates a set; `status`, `remove`
 * and `refresh` operate on recorded sets. Orchestration lives in
 * services/cluster/repo-replicate-ops.ts.
 */

import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import {
  refreshReplicaSet,
  removeReplicaSet,
  replicateRepo,
} from '../services/cluster/repo-replicate-ops.js';
import { listReplicaSets } from '../services/cluster/repo-replicate.js';
import { outputService } from '../services/core/output.js';
import { getOutputFormat, handleError } from '../utils/errors.js';

export function registerRepoReplicateCommands(repo: Command): void {
  const replicate = repo
    .command('replicate')
    .summary(t('commands.repo.replicate.descriptionShort'))
    .description(t('commands.repo.replicate.description'))
    .option('--name <repo>', t('commands.repo.replicate.nameOption'))
    .option('--cluster <name>', t('commands.repo.clusterOption'))
    .option('--replicas <n>', t('commands.repo.replicate.replicasOption'))
    .option('--datastore <name>', t('commands.repo.replicate.datastoreOption'))
    .option('--set <name>', t('commands.repo.replicate.setOption'))
    .option('--image <image>', t('commands.repo.replicate.imageOption'))
    .option('--port <port>', t('commands.repo.replicate.portOption'))
    .option('--pvc <name>', t('commands.repo.replicate.pvcOption'))
    .option('--primary-app <label>', t('commands.repo.replicate.primaryAppOption'))
    .option('--headless', t('commands.repo.replicate.headlessOption'))
    .option('--refresh <interval>', t('commands.repo.replicate.refreshOption'))
    .option('--debug', t('options.debug'))
    .action(
      async (options: {
        name?: string;
        cluster?: string;
        replicas?: string;
        datastore?: string;
        set?: string;
        image?: string;
        port?: string;
        pvc?: string;
        primaryApp?: string;
        headless?: boolean;
        refresh?: string;
        debug?: boolean;
      }) => {
        try {
          for (const [flag, value] of [
            ['--name', options.name],
            ['--cluster', options.cluster],
            ['--replicas', options.replicas],
            ['--image', options.image],
            ['--port', options.port],
          ] as const) {
            if (!value) throw new Error(`${flag} is required`);
          }
          await replicateRepo({
            repo: options.name as string,
            cluster: options.cluster as string,
            replicas: Number(options.replicas),
            datastore: options.datastore,
            set: options.set,
            image: options.image as string,
            port: Number(options.port),
            pvc: options.pvc,
            primaryApp: options.primaryApp,
            headless: options.headless,
            refresh: options.refresh,
            debug: options.debug,
          });
        } catch (error) {
          handleError(error);
        }
      }
    );

  replicate
    .command('status')
    .summary(t('commands.repo.replicate.status.descriptionShort'))
    .description(t('commands.repo.replicate.status.description'))
    .option('--name <set>', t('commands.repo.replicate.status.nameOption'))
    .action(async (options: { name?: string }) => {
      try {
        const all = await listReplicaSets();
        if (options.name && !(options.name in all)) {
          throw new Error(`Replica set "${options.name}" not found.`);
        }
        const sets = options.name ? { [options.name]: all[options.name] } : all;
        outputService.print(sets, getOutputFormat());
      } catch (error) {
        handleError(error);
      }
    });

  replicate
    .command('remove')
    .summary(t('commands.repo.replicate.remove.descriptionShort'))
    .description(t('commands.repo.replicate.remove.description'))
    .requiredOption('--name <set>', t('commands.repo.replicate.remove.nameOption'))
    .option('--debug', t('options.debug'))
    .action(async (options: { name: string; debug?: boolean }) => {
      try {
        await removeReplicaSet(options.name, options.debug);
      } catch (error) {
        handleError(error);
      }
    });

  replicate
    .command('refresh')
    .summary(t('commands.repo.replicate.refresh.descriptionShort'))
    .description(t('commands.repo.replicate.refresh.description'))
    .requiredOption('--name <set>', t('commands.repo.replicate.refresh.nameOption'))
    .option('--debug', t('options.debug'))
    .action(async (options: { name: string; debug?: boolean }) => {
      try {
        await refreshReplicaSet(options.name, options.debug);
      } catch (error) {
        handleError(error);
      }
    });
}
