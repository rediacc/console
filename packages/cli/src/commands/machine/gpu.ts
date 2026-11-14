import type { Command } from 'commander';
import { t } from '../../i18n/index.js';
import { configService } from '../../services/config/config-resources.js';
import { outputService } from '../../services/core/output.js';
import { setExitCode } from '../../services/core/request-context.js';
import { parseCapturedJson } from '../../services/executor/renet-output.js';
import { pendingExitCode, runCommandJob } from '../../services/jobs/command-job.js';
import { bindStepHandler, planStep } from '../../services/jobs/steps.js';
import { getOutputFormat, handleError } from '../../utils/errors.js';
import { renderLocalExecutionFailure } from '../../utils/local-execution-failures.js';
import { assertMachineExists } from '../_validate.js';

/** Mirror of renet `gpu.GPU` (Go json tags). */
interface GpuRow {
  vendor?: string;
  index: number;
  uuid?: string;
  name?: string;
  driver_version?: string;
  memory_total?: string;
}

interface GpuSpec {
  path: string;
  kind: string;
  devices?: string[] | null;
}

interface DeviceGrant {
  name: string;
  exclusive?: boolean;
  granted_by?: string;
  granted_at?: string;
}

interface GrantList {
  network_id: number;
  repo_mount_path?: string;
  devices?: DeviceGrant[] | null;
  error?: string;
}

/** Mirror of renet `gpuListReport`: the machine's inventory and every network's device grants. */
interface GpuListReport {
  inventory: {
    platform?: string;
    gpus?: GpuRow[] | null;
    specs?: GpuSpec[] | null;
    kfd?: boolean;
    dxg?: boolean;
    toolkit_version?: string;
    warnings?: string[] | null;
  };
  recorded: boolean;
  grants?: GrantList[] | null;
}

/** The repository names, by network id, so a grant row names the repo instead of a bare number. */
async function repoNamesByNetworkId(): Promise<Map<number, string>> {
  const names = new Map<number, string>();
  try {
    for (const { name, config } of await configService.listRepositories()) {
      if (config.networkId) names.set(config.networkId, name);
    }
  } catch {
    // The grants are still listed, by network id.
  }
  return names;
}

function grantRepository(grant: GrantList, names: Map<number, string>): string {
  return names.get(grant.network_id) ?? grant.repo_mount_path ?? `network ${grant.network_id}`;
}

function renderGpuTable(gpus: GpuRow[]): void {
  if (gpus.length === 0) {
    outputService.info(t('commands.machine.gpu.list.noGpus'));
    return;
  }
  outputService.print(
    gpus.map((g) => ({
      index: g.index,
      vendor: g.vendor,
      name: g.name,
      driver: g.driver_version,
      memory: g.memory_total,
    })),
    'table'
  );
}

/** One row per CDI device a spec defines, with the repositories it is granted to. */
function deviceRows(specs: GpuSpec[], grants: GrantList[], names: Map<number, string>) {
  const holders = new Map<string, string[]>();
  for (const grant of grants) {
    for (const device of grant.devices ?? []) {
      const label = grantRepository(grant, names) + (device.exclusive ? ' (exclusive)' : '');
      holders.set(device.name, [...(holders.get(device.name) ?? []), label]);
    }
  }
  return specs.flatMap((spec) =>
    (spec.devices ?? []).map((device) => ({
      device,
      spec: spec.path,
      grantedTo: (holders.get(device) ?? []).join(', ') || '-',
    }))
  );
}

/** Render the report as tables: GPUs, the CDI devices the machine offers, and who holds each. */
async function renderGpuList(report: GpuListReport): Promise<void> {
  const grants = report.grants ?? [];
  const names = await repoNamesByNetworkId();

  if (!report.recorded) outputService.warn(t('commands.machine.gpu.list.notRecorded'));
  for (const warning of report.inventory.warnings ?? []) outputService.warn(warning);

  renderGpuTable(report.inventory.gpus ?? []);

  const rows = deviceRows(report.inventory.specs ?? [], grants, names);
  if (rows.length === 0) {
    outputService.info(t('commands.machine.gpu.list.noDevices'));
  } else {
    outputService.print(rows, 'table');
  }

  for (const grant of grants.filter((g) => g.error)) {
    outputService.warn(
      t('commands.machine.gpu.list.grantUnreadable', {
        repository: grantRepository(grant, names),
        error: grant.error,
      })
    );
  }
}

/** The `renderGpuList` step: print the report the `machine_gpu_list` job produced, as tables or as data. */
function renderGpuReport(output: string | undefined): Promise<void> {
  const report = parseCapturedJson<GpuListReport>(output);
  const format = getOutputFormat();
  if (format === 'table') return renderGpuList(report);
  outputService.print(report, format);
  return Promise.resolve();
}

bindStepHandler('renderGpuList', ({ output }) => renderGpuReport(output));

async function handleGpuList(machineName: string, options: { debug?: boolean }): Promise<void> {
  await assertMachineExists(machineName);
  if (getOutputFormat() === 'table') {
    outputService.info(t('commands.machine.gpu.list.starting', { machine: machineName }));
  }

  // One read job; the render is its step, so a ticket handed back early prints nothing half-done.
  const outcome = await runCommandJob(
    'machine gpu list',
    {
      functionName: 'machine_gpu_list',
      machineName,
      params: {},
      debug: options.debug,
      captureOutput: true,
    },
    [planStep('renderGpuList')]
  );
  if (outcome.kind === 'pending') {
    const code = pendingExitCode(outcome);
    if (code !== undefined) setExitCode(code);
    return;
  }
  if (!outcome.result.success) {
    renderLocalExecutionFailure(outcome.result, t('commands.machine.gpu.list.failed'));
  }
}

/** Register `machine gpu list`: the machine's GPUs, CDI devices and device grants. */
export function registerGpuCommands(machine: Command): void {
  const gpu = machine
    .command('gpu')
    .summary(t('commands.machine.gpu.descriptionShort'))
    .description(t('commands.machine.gpu.description'));

  gpu
    .command('list')
    .summary(t('commands.machine.gpu.list.descriptionShort'))
    .description(t('commands.machine.gpu.list.description'))
    .argument('<name>', t('options.name'))
    .option('--debug', t('options.debug'))
    .action(async (machineName: string, options: { debug?: boolean }) => {
      try {
        await handleGpuList(machineName, options);
      } catch (error) {
        handleError(error);
      }
    });
}
