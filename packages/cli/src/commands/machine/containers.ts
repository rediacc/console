import { type ContainerInfo, getMachineContainers } from '@rediacc/shared/services/machine';
import { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { getStateProvider } from '../../providers/index.js';
import { authService } from '../../services/auth.js';
import { configService } from '../../services/config-resources.js';
import { outputService } from '../../services/output.js';
import type { OutputFormat } from '../../types/index.js';
import { extractAutoRoute, extractCustomDomain } from '../../utils/domain-helpers.js';
import { handleError, ValidationError } from '../../utils/errors.js';
import { createGuidResolver, loadGuidMap } from '../../utils/guid-resolver.js';
import { withSpinner } from '../../utils/spinner.js';

function enrichContainersForJson(
  containers: ContainerInfo[],
  resolve: (guid: string) => string,
  baseDomain?: string,
  machineName?: string
) {
  return containers.map((c) => ({
    ...c,
    repository: resolve(c.repository),
    repository_guid: c.repository,
    domain: extractCustomDomain(c.labels, baseDomain),
    autoRoute: extractAutoRoute(c.labels, baseDomain, machineName),
  }));
}

function displayUnhealthyContainers(
  unhealthy: ContainerInfo[],
  format: OutputFormat,
  resolve: (guid: string) => string = (g) => g,
  baseDomain?: string,
  machineName?: string
): void {
  outputService.error(t('commands.machine.containers.unhealthyFound', { count: unhealthy.length }));
  if (format === 'json') {
    outputService.print(
      enrichContainersForJson(unhealthy, resolve, baseDomain, machineName),
      format
    );
  } else {
    for (const c of unhealthy) {
      outputService.info(`  - ${c.name} (${resolve(c.repository)})`);
    }
  }
  process.exitCode = 2;
}

function handleHealthCheck(
  containers: ContainerInfo[],
  format: OutputFormat,
  resolve: (guid: string) => string = (g) => g,
  baseDomain?: string,
  machineName?: string
): void {
  const unhealthy = containers.filter((c) => c.health?.status === 'unhealthy');
  if (unhealthy.length > 0) {
    displayUnhealthyContainers(unhealthy, format, resolve, baseDomain, machineName);
  } else {
    outputService.success(t('commands.machine.containers.allHealthy'));
  }
}

function formatContainersForTable(
  containers: ContainerInfo[],
  resolve: (guid: string) => string = (g) => g,
  baseDomain?: string,
  machineName?: string
) {
  return containers.map((c) => ({
    name: c.name,
    state: c.state,
    health: c.health?.status ?? 'none',
    domain: extractCustomDomain(c.labels, baseDomain),
    autoRoute: extractAutoRoute(c.labels, baseDomain, machineName),
    repository: resolve(c.repository),
  }));
}

export function registerContainersCommand(machine: Command, program: Command): void {
  machine
    .command('containers <name>')
    .description(t('commands.machine.containers.description'))
    .option('-t, --team <name>', t('options.team'))
    .option('--health-check', t('commands.machine.containers.healthCheck'))
    .action(async (name: string, options: { team?: string; healthCheck?: boolean }) => {
      try {
        const provider = await getStateProvider();
        if (provider.isCloud) {
          await authService.requireAuth();
        }
        const opts = await configService.applyDefaults(options);

        if (provider.isCloud && !opts.team) {
          throw new ValidationError(t('errors.teamRequired'));
        }

        const [machine, guidMap, machineConfig] = await Promise.all([
          withSpinner(
            t('commands.machine.containers.fetching'),
            () =>
              provider.machines.getWithVaultStatus({
                teamName: opts.team as string,
                machineName: name,
              }),
            t('commands.machine.containers.fetched')
          ),
          loadGuidMap(),
          configService.getLocalMachine(name).catch(() => undefined),
        ]);
        const resolve = createGuidResolver(guidMap);
        const baseDomain = machineConfig?.infra?.baseDomain;

        if (!machine) {
          throw new ValidationError(t('errors.machineNotFound', { name }));
        }

        const containers = getMachineContainers(machine);
        const format = program.opts().output as OutputFormat;

        if (options.healthCheck) {
          handleHealthCheck(containers, format, resolve, baseDomain, name);
          return;
        }

        if (containers.length === 0) {
          outputService.info(t('commands.machine.containers.noContainers'));
          return;
        }

        if (format === 'json') {
          outputService.print(
            enrichContainersForJson(containers, resolve, baseDomain, name),
            format
          );
        } else {
          const tableData = formatContainersForTable(containers, resolve, baseDomain, name);
          outputService.print(tableData, format);
        }
      } catch (error) {
        handleError(error);
      }
    });
}
