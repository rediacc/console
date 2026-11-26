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
import { ERROR_CODES } from '../types/errors.js';
import { CliExitError } from '../utils/cli-exit-error.js';
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
  // Read only once a machine lacks a --machine-key: with every key given, an unreadable
  // export.json or incident.json is never opened.
  let pinned: Promise<Map<string, string>> | undefined;
  const pinnedKeys = (): Promise<Map<string, string>> => {
    pinned ??= Promise.resolve().then(() => {
      const incidentId = exportedIncidentId(options.dir);
      return incidentId === undefined
        ? new Map<string, string>()
        : pinnedMachineKeys(deps.client(), incidentId);
    });
    return pinned;
  };
  return async (machineId) => {
    const explicit = given.get(machineId);
    if (explicit !== undefined) return explicit;
    return (await pinnedKeys()).get(machineId);
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

/** The capture levels of `renet forensics level` (PLAN-forensics-capture D8). */
const FORENSICS_LEVELS = ['basic', 'standard', 'full'] as const;
type ForensicsLevel = (typeof FORENSICS_LEVELS)[number];

function isLevel(value: string): value is ForensicsLevel {
  return (FORENSICS_LEVELS as readonly string[]).includes(value);
}

/**
 * `rdc forensics level <ref> basic|standard|full`: one `forensics_level` renet function on the
 * machine the ref resolves to. The collector caps the level by the plan's entitlement.
 */
export async function runForensicsLevel(ref: string, level: string): Promise<void> {
  if (!isLevel(level)) {
    throw new CliExitError(
      ERROR_CODES.VALIDATION_ERROR,
      t('forensics.badLevel', { level, levels: FORENSICS_LEVELS.join(', ') })
    );
  }
  // Loaded here: the executor chain is heavy, and only this verb of the group reaches a machine.
  const { resolveRepoRef } = await import('../utils/repo-target.js');
  const { executeRepoFunction } = await import('../utils/repo-executor.js');
  const { name, repoKey, machineName, kubeCluster } = await resolveRepoRef(ref);
  const result = await executeRepoFunction(
    'forensics_level',
    repoKey,
    machineName,
    { level },
    {
      ...(kubeCluster === undefined ? {} : { kubeCluster }),
      job: { verb: 'forensics level', steps: [] },
    },
    {
      starting: t('forensics.levelStarting', { repository: name, level, machine: machineName }),
      completed: t('forensics.levelCompleted', { repository: name, level }),
      failed: t('forensics.levelFailed', { repository: name }),
    }
  );
  if (!result.success && result.state !== 'running') setExitCode(result.exitCode || 1);
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
    .option('--since <when>', t('commands.forensics.verify.sinceOption'))
    .option('--until <when>', t('commands.forensics.verify.untilOption'))
    .option('--machine-key <machine=hex>', t('commands.forensics.verify.machineKeyOption'), collect)
    .action(async (options: VerifyOptions) => {
      try {
        await runForensicsVerify(options);
      } catch (error) {
        handleError(error);
      }
    });

  forensics
    .command('level')
    .summary(t('commands.forensics.level.descriptionShort'))
    .description(t('commands.forensics.level.description'))
    .argument('<ref>', t('options.repoRef'))
    .argument('<level>', t('commands.forensics.level.levelArgument'))
    .action(async (ref: string, level: string) => {
      try {
        await runForensicsLevel(ref, level);
      } catch (error) {
        handleError(error);
      }
    });
}
