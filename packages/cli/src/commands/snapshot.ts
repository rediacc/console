import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { configService } from '../services/config-resources.js';
import { outputService } from '../services/output.js';
import { getOutputFormat, handleError } from '../utils/errors.js';

export function registerSnapshotCommands(program: Command): void {
  const snapshot = program.command('snapshot').description(t('commands.snapshot.description'));

  snapshot
    .command('create <repo>')
    .description(t('commands.repo.snapshot.create.description'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('--snapshot-name <name>', t('commands.repo.snapshot.create.optionSnapshotName'))
    .option('--debug', t('options.debug'))
    .action(async (repo, options) => {
      try {
        const machineName = options.machine ?? (await configService.getMachine());
        if (!machineName) throw new Error(t('errors.machineRequiredLocal'));

        outputService.info(
          t('commands.repo.snapshot.create.creating', { repo, machine: machineName })
        );
        const { runSnapshotCommand } = await import('../services/snapshot-service.js');
        const flags = ['--name', repo];
        if (options.snapshotName) flags.push('--snapshot-name', options.snapshotName);

        const result = await runSnapshotCommand('create', machineName, flags, {
          debug: options.debug,
        });
        const parsed = JSON.parse(result.output);
        outputService.success(
          t('commands.repo.snapshot.create.success', { name: parsed.name, path: parsed.path })
        );
      } catch (error) {
        handleError(error);
      }
    });

  snapshot
    .command('list [repo]')
    .description(t('commands.repo.snapshot.list.description'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('--debug', t('options.debug'))
    .option('-o, --output <format>', t('options.output'))
    .action(async (repo, options) => {
      try {
        const machineName = options.machine ?? (await configService.getMachine());
        if (!machineName) throw new Error(t('errors.machineRequiredLocal'));

        const { runSnapshotCommand } = await import('../services/snapshot-service.js');
        const flags: string[] = [];
        if (repo) flags.push('--name', repo);

        const result = await runSnapshotCommand('list', machineName, flags, {
          debug: options.debug,
        });
        const parsed = JSON.parse(result.output);

        if (getOutputFormat() === 'json') {
          outputService.print(JSON.stringify(parsed, null, 2));
          return;
        }

        if (parsed.total === 0) {
          outputService.info(t('commands.repo.snapshot.list.noSnapshots'));
          return;
        }

        outputService.info(
          t('commands.repo.snapshot.list.header', { count: parsed.total, path: parsed.basePath })
        );
        for (const snap of parsed.snapshots) {
          const sizeKB = Math.round(snap.size / 1024);
          outputService.info(`  ${snap.name}  ${sizeKB} KB  ${snap.createdAt}`);
        }
      } catch (error) {
        handleError(error);
      }
    });

  snapshot
    .command('delete <repo> <snapshot-name>')
    .description(t('commands.repo.snapshot.delete.description'))
    .option('-m, --machine <name>', t('options.machine'))
    .option('--debug', t('options.debug'))
    .action(async (repo, snapshotName, options) => {
      try {
        const machineName = options.machine ?? (await configService.getMachine());
        if (!machineName) throw new Error(t('errors.machineRequiredLocal'));

        outputService.info(
          t('commands.repo.snapshot.delete.deleting', {
            snapshot: snapshotName,
            repo,
            machine: machineName,
          })
        );
        const { runSnapshotCommand } = await import('../services/snapshot-service.js');
        await runSnapshotCommand(
          'delete',
          machineName,
          ['--name', repo, '--snapshot-name', snapshotName],
          { debug: options.debug }
        );
        outputService.success(t('commands.repo.snapshot.delete.success', { name: snapshotName }));
      } catch (error) {
        handleError(error);
      }
    });
}
