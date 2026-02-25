import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { outputService } from '../services/output.js';
import { handleError } from '../utils/errors.js';
import type { Command } from 'commander';

export function registerSnapshotCommands(program: Command): void {
  const snapshot = program.command('snapshot').description(t('commands.snapshot.description'));

  // snapshot create <repo>
  snapshot
    .command('create <repo>')
    .description(t('commands.snapshot.create.description'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('--snapshot-name <name>', t('commands.snapshot.create.optionSnapshotName'))
    .option('--debug', t('options.debug'))
    .action(async (repo, options) => {
      try {
        const machineName = options.machine ?? (await configService.getMachine());
        if (!machineName) {
          throw new Error(t('errors.machineRequiredLocal'));
        }

        outputService.info(t('commands.snapshot.create.creating', { repo, machine: machineName }));

        const { runSnapshotCommand } = await import('../services/snapshot-service.js');
        const flags = ['--name', repo];
        if (options.snapshotName) {
          flags.push('--snapshot-name', options.snapshotName);
        }

        const result = await runSnapshotCommand('create', machineName, flags, {
          debug: options.debug,
        });

        const parsed = JSON.parse(result.output);
        outputService.success(
          t('commands.snapshot.create.success', { name: parsed.name, path: parsed.path })
        );
      } catch (error) {
        handleError(error);
      }
    });

  // snapshot list [repo]
  snapshot
    .command('list [repo]')
    .description(t('commands.snapshot.list.description'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('--debug', t('options.debug'))
    .action(async (repo, options) => {
      try {
        const machineName = options.machine ?? (await configService.getMachine());
        if (!machineName) {
          throw new Error(t('errors.machineRequiredLocal'));
        }

        const { runSnapshotCommand } = await import('../services/snapshot-service.js');
        const flags: string[] = [];
        if (repo) {
          flags.push('--name', repo);
        }

        const result = await runSnapshotCommand('list', machineName, flags, {
          debug: options.debug,
        });

        const parsed = JSON.parse(result.output);
        if (parsed.total === 0) {
          outputService.info(t('commands.snapshot.list.noSnapshots'));
          return;
        }

        outputService.info(
          t('commands.snapshot.list.header', { count: parsed.total, path: parsed.basePath })
        );
        for (const snap of parsed.snapshots) {
          const sizeKB = Math.round(snap.size / 1024);
          outputService.info(`  ${snap.name}  ${sizeKB} KB  ${snap.createdAt}`);
        }
      } catch (error) {
        handleError(error);
      }
    });

  // snapshot delete <repo> <snapshot-name>
  snapshot
    .command('delete <repo> <snapshot-name>')
    .description(t('commands.snapshot.delete.description'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('--debug', t('options.debug'))
    .action(async (repo, snapshotName, options) => {
      try {
        const machineName = options.machine ?? (await configService.getMachine());
        if (!machineName) {
          throw new Error(t('errors.machineRequiredLocal'));
        }

        const { runSnapshotCommand } = await import('../services/snapshot-service.js');
        const result = await runSnapshotCommand(
          'delete',
          machineName,
          ['--name', repo, '--snapshot-name', snapshotName],
          { debug: options.debug }
        );

        const parsed = JSON.parse(result.output);
        outputService.success(t('commands.snapshot.delete.success', { name: parsed.deleted }));
      } catch (error) {
        handleError(error);
      }
    });
}
