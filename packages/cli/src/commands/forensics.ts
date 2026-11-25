import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import {
  manifestMachineKeys,
  parseMachineKeys,
  verifyEvidenceDir,
} from '../services/forensics/evidence.js';
import { parseWindow } from '../services/forensics/window.js';
import { getOutputFormat, handleError } from '../utils/errors.js';

export interface VerifyOptions {
  dir: string;
  since?: string;
  until?: string;
  machineKey?: string[];
}

function collect(value: string, previous: string[] = []): string[] {
  return [...previous, value];
}

/**
 * `rdc forensics verify --dir <evidence>`: recompute both chains; exit 1 on any gap or edit. The
 * machine keys are the ones the directory's raw-manifest.json lists, and a `--machine-key` entry
 * replaces the listed key of its machine.
 */
export async function runForensicsVerify(options: VerifyOptions): Promise<void> {
  const window =
    options.since === undefined && options.until === undefined ? undefined : parseWindow(options);
  const keys = new Map([
    ...manifestMachineKeys(options.dir),
    ...parseMachineKeys(options.machineKey ?? []),
  ]);
  const report = await verifyEvidenceDir(options.dir, window, keys);
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
