import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { ForensicsClient } from '../services/forensics/client.js';
import {
  exportedIncidentId,
  type MachineKeySource,
  parseMachineKeys,
  verifyEvidenceDir,
} from '../services/forensics/evidence.js';
import { pinnedMachineKeys } from '../services/forensics/incident.js';
import { parseWindow } from '../services/forensics/window.js';
import { getOutputFormat, handleError } from '../utils/errors.js';

export interface VerifyOptions {
  dir: string;
  since?: string;
  until?: string;
  machineKey?: string[];
}

export interface VerifyDeps {
  /** The account client the pinned keys are read through; built only when a key is needed. */
  client: () => ForensicsClient;
}

const defaultVerifyDeps = (): VerifyDeps => ({ client: () => new ForensicsClient() });

function collect(value: string, previous: string[] = []): string[] {
  return [...previous, value];
}

/**
 * The trust anchor of a verify run, never the directory itself: a `--machine-key` entry first,
 * then the keys the server pinned for the incident the directory names, fetched once and only
 * when a machine has no `--machine-key`. A machine neither source knows has no key and fails.
 */
function trustedKeys(options: VerifyOptions, deps: VerifyDeps): MachineKeySource {
  const given = parseMachineKeys(options.machineKey ?? []);
  const incidentId = exportedIncidentId(options.dir);
  let pinned: Promise<Map<string, string>> | undefined;
  return async (machineId) => {
    const explicit = given.get(machineId);
    if (explicit !== undefined || incidentId === undefined) return explicit;
    pinned ??= pinnedMachineKeys(deps.client(), incidentId);
    return (await pinned).get(machineId);
  };
}

/**
 * `rdc forensics verify --dir <evidence>`: recompute both chains; exit 1 on any gap or edit. Batch
 * signatures verify under keys from outside the directory (see `trustedKeys`).
 */
export async function runForensicsVerify(
  options: VerifyOptions,
  deps: VerifyDeps = defaultVerifyDeps()
): Promise<void> {
  const window =
    options.since === undefined && options.until === undefined ? undefined : parseWindow(options);
  const report = await verifyEvidenceDir(options.dir, window, trustedKeys(options, deps));
  if (getOutputFormat() === 'json') {
    outputService.print(report, 'json');
  } else {
    outputService.print(
      [
        t('forensics.verifyWindow', { from: report.window.from, to: report.window.to }),
        t('forensics.verifyFiles', { count: report.files }),
        ...report.gaps.map((g) => t('forensics.verifyGap', { ref: g.ref, reason: g.reason })),
        ...report.edits.map((e) => t('forensics.verifyEdit', { ref: e.ref, reason: e.reason })),
        report.clean ? t('forensics.verifyClean') : t('forensics.verifyFailed'),
      ].join('\n')
    );
  }
  if (!report.clean) setExitCode(1);
}

export function registerForensicsCommand(program: Command): void {
  const forensics = program
    .command('forensics')
    .summary(t('commands.forensics.descriptionShort'))
    .description(t('commands.forensics.description'));

  forensics
    .command('verify')
    .summary(t('commands.forensics.verify.descriptionShort'))
    .description(t('commands.forensics.verify.description'))
    .requiredOption('--dir <path>', t('commands.forensics.verify.dirOption'))
    .option('--since <when>', t('commands.repo.rowsSinceOption'))
    .option('--until <when>', t('commands.repo.rowsUntilOption'))
    .option('--machine-key <machine=hex>', t('commands.forensics.verify.machineKeyOption'), collect)
    .action(async (options: VerifyOptions) => {
      try {
        await runForensicsVerify(options);
      } catch (error) {
        handleError(error);
      }
    });
}
