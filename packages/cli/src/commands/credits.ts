import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import {
  loadCreditsData,
  loadLicensesText,
  renderCredits,
  renderCreditsJson,
} from '../services/core/credits.js';
import { outputService } from '../services/core/output.js';
import type { OutputFormat } from '../types/index.js';

export function registerCreditsCommand(program: Command): void {
  program
    .command('credits')
    .summary(t('commands.credits.descriptionShort'))
    .description(t('commands.credits.description'))
    .option('--licenses', t('options.licenses'))
    .option('--output <format>', t('options.outputFormat'))
    .action((options: { licenses?: boolean; output?: string }) => {
      if (options.licenses) {
        const text = loadLicensesText();
        outputService.print(text ?? t('commands.credits.licensesUnavailable'));
        return;
      }

      const data = loadCreditsData();
      const outputFormat = (options.output ?? program.opts().output) as OutputFormat | undefined;
      if (outputFormat === 'json') {
        outputService.print(renderCreditsJson(data));
      } else {
        outputService.print(renderCredits(data));
      }
    });
}
