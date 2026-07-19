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

function renderRefs(analysis: ConfigPruneAnalysis, verb: string): void {
  if (analysis.droppedRefs.length === 0) return;
  outputService.info(
    t('commands.config.prune.droppedRefs', { count: analysis.droppedRefs.length, verb })
  );
  for (const d of analysis.droppedRefs) {
    outputService.info(`  ${d.path}: "${d.value}"  (${d.reason})`);
  }
}

function renderAnalysis(
  analysis: ConfigPruneAnalysis,
  dryRun: boolean,
  removingOrphanRepos: boolean
): void {
  const verb = dryRun ? 'would be' : 'were';
  renderCerts(analysis, verb);
  renderArchives(analysis, verb);
  renderRefs(analysis, verb);
  renderOrphanRepos(analysis, verb, removingOrphanRepos);
  if (analysis.orphanStateRepos.length > 0) {
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
  for (const w of analysis.warnings) {
    outputService.warn(w);
  }

  const totalChanges =
    analysis.staleCerts.length +
    analysis.expiredArchives.length +
    analysis.droppedRefs.length +
    analysis.orphanStateRepos.length +
    // Only counted as a change when actually being removed; otherwise the
    // orphan list is informational and must not make an empty run look busy.
    (removingOrphanRepos ? analysis.orphanRepos.length : 0);
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

        renderAnalysis(analysis, dryRun, Boolean(options.orphanRepos));
      } catch (error) {
        handleError(error);
      }
    });
}
