import { Command } from 'commander';
import {
  getDeploymentSummary,
  getMachineSystemInfo,
  type ParsedVaultStatus,
  parseListResult,
  parseVaultStatus,
  type SystemInfo,
} from '@rediacc/shared/services/machine';
import { t } from '../../i18n/index.js';
import { getStateProvider } from '../../providers/index.js';
import { authService } from '../../services/auth.js';
import { configService } from '../../services/config-resources.js';
import { outputService } from '../../services/output.js';
import { handleError, ValidationError } from '../../utils/errors.js';
import { withSpinner } from '../../utils/spinner.js';
import type { OutputFormat } from '../../types/index.js';

function displaySystemInfo(systemInfo: SystemInfo): void {
  outputService.info(t('commands.machine.vaultStatus.systemSection'));

  if (systemInfo.hostname) {
    outputService.info(
      t('commands.machine.vaultStatus.systemHostname', { hostname: systemInfo.hostname })
    );
  }
  if (systemInfo.uptime) {
    outputService.info(
      t('commands.machine.vaultStatus.systemUptime', { uptime: systemInfo.uptime })
    );
  }

  const resourceDisplays = [
    { key: 'systemMemory', data: systemInfo.memory },
    { key: 'systemDisk', data: systemInfo.disk },
    { key: 'systemDatastore', data: systemInfo.datastore },
  ];

  for (const { key, data } of resourceDisplays) {
    outputService.info(
      t(`commands.machine.vaultStatus.${key}`, {
        used: data.used,
        total: data.total,
        percent: data.use_percent ?? 'N/A',
      })
    );
  }
}

function displaySummary(summary: ReturnType<typeof getDeploymentSummary>): void {
  outputService.info(
    t('commands.machine.vaultStatus.totalRepos', { count: summary.totalRepositories })
  );
  outputService.info(t('commands.machine.vaultStatus.mounted', { count: summary.mountedCount }));
  outputService.info(
    t('commands.machine.vaultStatus.dockerRunning', { count: summary.dockerRunningCount })
  );
}

function displayRepository(repository: ParsedVaultStatus['repositories'][0]): void {
  const sizeInfo = repository.size_human ? ` (${repository.size_human})` : '';
  outputService.info(`  - ${repository.name}${sizeInfo}`);

  if (repository.mounted !== undefined) {
    outputService.info(
      t('commands.machine.vaultStatus.repoMounted', {
        mounted: repository.mounted ? t('common.yes') : t('common.no'),
      })
    );
  }
  if (repository.docker_running !== undefined) {
    outputService.info(
      t('commands.machine.vaultStatus.repoDocker', {
        status: repository.docker_running ? t('common.running') : t('common.stopped'),
      })
    );
  }
}

function displayRepositories(parsed: ParsedVaultStatus): void {
  if (parsed.repositories.length === 0) return;

  outputService.info(t('commands.machine.vaultStatus.deployedRepos'));
  for (const repository of parsed.repositories) {
    displayRepository(repository);
  }
}

export function registerVaultStatusCommand(machine: Command, program: Command): void {
  machine
    .command('vault-status <name>')
    .description(t('commands.machine.vaultStatus.description'))
    .option('-t, --team <name>', t('options.team'))
    .action(async (name: string, options: { team?: string }) => {
      try {
        const provider = await getStateProvider();
        if (provider.isCloud) {
          await authService.requireAuth();
        }
        const opts = await configService.applyDefaults(options);

        if (provider.isCloud && !opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }

        const machine = await withSpinner(
          t('commands.machine.vaultStatus.fetching'),
          () =>
            provider.machines.getWithVaultStatus({
              teamName: opts.team as string,
              machineName: name,
            }),
          t('commands.machine.vaultStatus.fetched')
        );

        if (!machine) {
          throw new ValidationError(t('errors.machineNotFound', { name }));
        }

        const format = program.opts().output as OutputFormat;
        const parsed = parseVaultStatus(machine.vaultStatus);
        const summary = getDeploymentSummary(machine);
        const systemInfo = getMachineSystemInfo(machine);
        const listResult = parseListResult(machine.vaultStatus);

        if (format === 'json') {
          outputService.print({ parsed, summary, systemInfo, listResult }, format);
          return;
        }

        outputService.info(t('commands.machine.vaultStatus.header', { name }));
        outputService.info(t('commands.machine.vaultStatus.status', { status: summary.status }));

        if (systemInfo) {
          displaySystemInfo(systemInfo);
        }

        displaySummary(summary);
        displayRepositories(parsed);
      } catch (error) {
        handleError(error);
      }
    });
}
