/**
 * `rdc config prune`, sweep stale leftovers from the local config file.
 * The action layer is intentionally thin: parse flags, call the service,
 * render. All policy lives in `services/config-prune.ts`.
 */

import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import {
  analyzeConfigPrune,
  applyConfigPrune,
  type ConfigPruneAnalysis,
  type ConfigPruneOptions,
} from '../services/config/config-prune.js';
import { outputService } from '../services/core/output.js';
import { handleError, ValidationError } from '../utils/errors.js';

interface PruneCommandOptions extends ConfigPruneOptions {
  dryRun?: boolean;
}

function renderCerts(analysis: ConfigPruneAnalysis, verb: string): void {
  if (analysis.staleCerts.length === 0) return;
  outputService.info(
    t('commands.config.prune.removedCerts', { count: analysis.staleCerts.length, verb })
  );
  for (const c of analysis.staleCerts) {
    outputService.info(`  ${c.name}  (${c.reason})`);
  }
}

function renderArchives(analysis: ConfigPruneAnalysis, verb: string): void {
  if (analysis.expiredArchives.length > 0) {
    outputService.info(
      t('commands.config.prune.purgedArchives', { count: analysis.expiredArchives.length, verb })
    );
    for (const a of analysis.expiredArchives) {
      outputService.info(
        `  ${a.name}  (${a.repositoryGuid.slice(0, 8)}…, deletedAt ${a.deletedAt})`
      );
    }
  }
  if (analysis.graceArchives.length > 0) {
    outputService.info(t('commands.config.prune.keptArchivesInGrace'));
    for (const g of analysis.graceArchives) {
      outputService.info(
        `  ${g.name}  (${g.guid.slice(0, 8)}…, ${g.daysAgo}d ago, ${g.daysRemaining}d remaining)`
      );
    }
  }
}

/**
 * Report repository entries that name no machine.
 *
 * Without --orphan-repos this only warns, and points at `config reconcile`
 * first: an entry with no placement may simply never have been reconciled, and
 * a repo entry holds the LUKS credential and SSH key for its image, so removing
 * one that is merely unreconciled loses the only copy of those secrets.
 */
function renderOrphanRepos(analysis: ConfigPruneAnalysis, verb: string, removing: boolean): void {
  if (analysis.orphanRepos.length === 0) return;

  outputService.info(
    removing
      ? t('commands.config.prune.removedOrphanRepos', {
          count: analysis.orphanRepos.length,
          verb,
        })
      : t('commands.config.prune.foundOrphanRepos', { count: analysis.orphanRepos.length })
  );
  for (const r of analysis.orphanRepos) {
    outputService.info(`  ${r.name}${r.guid ? `  (${r.guid.slice(0, 8)}…)` : ''}`);
  }
  if (!removing) {
    outputService.info(t('commands.config.prune.orphanReposHint'));
  }
}

/** Report repository entries placed on a machine the config no longer has (archived only with --gone-machine-repos). */
function renderGoneMachineRepos(
  analysis: ConfigPruneAnalysis,
  verb: string,
  archiving: boolean
): void {
  const count = analysis.goneMachineRepos.length;
  if (count === 0) return;
  outputService.info(
    archiving
      ? t('commands.config.prune.archivedGoneMachineRepos', { count, verb })
      : t('commands.config.prune.foundGoneMachineRepos', { count })
  );
  for (const r of analysis.goneMachineRepos) {
    const guid = r.guid ? `, ${r.guid.slice(0, 8)}…` : '';
    outputService.info(`  ${r.name}  (${r.machine}${guid})`);
  }
  if (!archiving) outputService.info(t('commands.config.prune.goneMachineReposHint'));
}

/** Report the runtime records naming a machine the config no longer has (always dropped). */
function renderGoneMachineState(analysis: ConfigPruneAnalysis, verb: string): void {
  const count = analysis.goneMachineState.length;
  if (count === 0) return;
  outputService.info(t('commands.config.prune.droppedGoneMachineState', { count, verb }));
  for (const path of analysis.goneMachineState) outputService.info(`  ${path}`);
}

function renderRefs(analysis: ConfigPruneAnalysis, verb: string): void {
  if (analysis.droppedRefs.length === 0) return;
  outputService.info(
    t('commands.config.prune.droppedRefs', { count: analysis.droppedRefs.length, verb })
  );
  for (const d of analysis.droppedRefs) {
    outputService.info(`  ${d.path}: "${d.value}"  (${d.reason})`);
  }
}

function renderStateRepos(analysis: ConfigPruneAnalysis, verb: string): void {
  if (analysis.orphanStateRepos.length === 0) return;
  outputService.info(
    t('commands.config.prune.droppedStateRepos', {
      count: analysis.orphanStateRepos.length,
      verb,
    })
  );
  for (const name of analysis.orphanStateRepos) {
    outputService.info(`  ${name}`);
  }
}

/**
 * What the run changes. Orphan and gone-machine repos count only when actually being removed;
 * otherwise their list is informational and must not make an empty run look busy.
 */
function countChanges(
  analysis: ConfigPruneAnalysis,
  removingOrphanRepos: boolean,
  archivingGoneMachineRepos: boolean
): number {
  return (
    analysis.staleCerts.length +
    analysis.expiredArchives.length +
    analysis.droppedRefs.length +
    analysis.orphanStateRepos.length +
    analysis.goneMachineState.length +
    (archivingGoneMachineRepos ? analysis.goneMachineRepos.length : 0) +
    (removingOrphanRepos ? analysis.orphanRepos.length : 0)
  );
}

function renderAnalysis(
  analysis: ConfigPruneAnalysis,
  dryRun: boolean,
  removingOrphanRepos: boolean,
  archivingGoneMachineRepos: boolean
): void {
  const verb = dryRun ? 'would be' : 'were';
  renderCerts(analysis, verb);
  renderArchives(analysis, verb);
  renderRefs(analysis, verb);
  renderOrphanRepos(analysis, verb, removingOrphanRepos);
  renderGoneMachineRepos(analysis, verb, archivingGoneMachineRepos);
  renderGoneMachineState(analysis, verb);
  renderStateRepos(analysis, verb);
  for (const w of analysis.warnings) {
    outputService.warn(w);
  }

  const totalChanges = countChanges(analysis, removingOrphanRepos, archivingGoneMachineRepos);
  if (totalChanges === 0) {
    outputService.success(t('commands.config.prune.nothingToPrune'));
  } else if (dryRun) {
    outputService.warn(t('commands.config.prune.dryRun', { count: totalChanges }));
  } else {
    outputService.success(t('commands.config.prune.completed', { count: totalChanges }));
  }
}

export function registerPruneCommand(config: Command): void {
  config
    .command('prune')
    .summary(t('commands.config.prune.descriptionShort'))
    .description(t('commands.config.prune.description'))
    .option('--dry-run', t('commands.config.prune.dryRunOption'))
    .option('--certs-only', t('commands.config.prune.certsOnlyOption'))
    .option('--archives-only', t('commands.config.prune.archivesOnlyOption'))
    .option('--refs-only', t('commands.config.prune.refsOnlyOption'))
    .option('--purge-archived', t('commands.config.prune.purgeArchivedOption'))
    .option('--orphan-repos', t('commands.config.prune.orphanReposOption'))
    .option('--gone-machine-repos', t('commands.config.prune.goneMachineReposOption'))
    .option('--grace-days <days>', t('commands.config.prune.graceDaysOption'), Number.parseInt)
    .action(async (options: PruneCommandOptions) => {
      try {
        const onlyFlags = [options.certsOnly, options.archivesOnly, options.refsOnly].filter(
          Boolean
        );
        if (onlyFlags.length > 1) {
          throw new ValidationError(t('commands.config.prune.tooManyOnlyFlags'));
        }

        const dryRun = Boolean(options.dryRun);
        outputService.info(t('commands.config.prune.scanning'));

        const analysis = dryRun
          ? await analyzeConfigPrune(options)
          : await applyConfigPrune(options);

        renderAnalysis(
          analysis,
          dryRun,
          Boolean(options.orphanRepos),
          Boolean(options.goneMachineRepos)
        );
      } catch (error) {
        handleError(error);
      }
    });
}
