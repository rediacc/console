/**
 * `rdc preview use <name>`, `rdc preview leave`, `rdc preview status` (PLAN-preview-signer.md D8): one switch
 * that remembers the way back. The flows live in services/preview/switch.ts; this file registers them.
 */
import type { Command } from 'commander';
import { t } from '../i18n/index.js';
import { outputService } from '../services/core/output.js';
import { setExitCode } from '../services/core/request-context.js';
import { realPreviewLeaveDeps, realPreviewUseDeps } from '../services/preview/deps.js';
import { readPreviewOverlay, readRealAccountServer } from '../services/preview/state.js';
import {
  leavePreviewFlow,
  previewBanner,
  previewStatusLines,
  switchToPreview,
} from '../services/preview/switch.js';
import { handleError } from '../utils/errors.js';

/** The banner of the active preview, printed by the root hook before every command. */
export function printPreviewBanner(): void {
  const banner = previewBanner(readPreviewOverlay(), readRealAccountServer());
  if (banner) outputService.info(banner);
}

export function registerPreviewCommand(program: Command): void {
  const preview = program
    .command('preview')
    .summary(t('commands.preview.descriptionShort'))
    .description(t('commands.preview.description'));

  preview
    .command('use')
    .argument('<name>', t('commands.preview.use.nameArgument'))
    .summary(t('commands.preview.use.descriptionShort'))
    .description(t('commands.preview.use.description'))
    .option('--accept-format-change', t('commands.preview.use.acceptFormatChange'))
    .action(async (name: string, options: { acceptFormatChange?: boolean }) => {
      try {
        await switchToPreview(
          name,
          { acceptFormatChange: options.acceptFormatChange },
          realPreviewUseDeps()
        );
      } catch (error) {
        handleError(error);
      }
    });

  preview
    .command('leave')
    .summary(t('commands.preview.leave.descriptionShort'))
    .description(t('commands.preview.leave.description'))
    .option('--machine <name>', t('commands.preview.leave.machine'))
    .action(async (options: { machine?: string }) => {
      try {
        const result = await leavePreviewFlow(options, realPreviewLeaveDeps());
        if (!result.left && result.remaining.length > 0) setExitCode(1);
      } catch (error) {
        handleError(error);
      }
    });

  preview
    .command('status')
    .summary(t('commands.preview.status.descriptionShort'))
    .description(t('commands.preview.status.description'))
    .action(() => {
      try {
        const overlay = readPreviewOverlay();
        if (!overlay) {
          outputService.info(t('commands.preview.msg.notActive'));
          return;
        }
        outputService.report(previewStatusLines(overlay, readRealAccountServer()).join('\n'));
      } catch (error) {
        handleError(error);
      }
    });
}
