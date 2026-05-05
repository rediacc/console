/**
 * `rdc config prune` — sweep stale leftovers from the local config file.
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
} from '../services/config-prune.js';
import { outputService } from '../services/output.js';
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

function renderRefs(analysis: ConfigPruneAnalysis, verb: string): void {
  if (analysis.droppedRefs.length === 0) return;
  outputService.info(
    t('commands.config.prune.droppedRefs', { count: analysis.droppedRefs.length, verb })
  );
  for (const d of analysis.droppedRefs) {
    outputService.info(`  ${d.path}: "${d.value}"  (${d.reason})`);
  }
}

function renderAnalysis(analysis: ConfigPruneAnalysis, dryRun: boolean): void {
  const verb = dryRun ? 'would be' : 'were';
  renderCerts(analysis, verb);
  renderArchives(analysis, verb);
  renderRefs(analysis, verb);
  for (const w of analysis.warnings) {
    outputService.warn(w);
  }

  const totalChanges =
    analysis.staleCerts.length + analysis.expiredArchives.length + analysis.droppedRefs.length;
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

        renderAnalysis(analysis, dryRun);
      } catch (error) {
        handleError(error);
      }
    });
}
