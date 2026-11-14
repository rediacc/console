/**
 * Interactive region selection prompt.
 * Uses inquirer to present a list of available data regions.
 */

import type { RegionInfo } from '@rediacc/shared/regions';
import { t } from '../i18n/index.js';
import { exitProcess, writeStderr } from '../services/core/request-context.js';
import { detectLikelyRegion } from '../services/provision/region-discovery.js';
import { EXIT_CODES } from '../types/index.js';

export interface RegionSelection {
  region: RegionInfo;
  domain: string;
}

export async function promptRegionSelection(regions: RegionInfo[]): Promise<RegionSelection> {
  if (process.stdin.isTTY !== true) {
    writeStderr(`${t('errors.regionSelectionRequiresTTY')}\n`);
    exitProcess(EXIT_CODES.INVALID_ARGUMENTS);
  }

  // Lazy-load inquirer (rxjs + prompt graph) only when the region picker is actually shown during interactive login. `createPromptModule` is a named export.
  const inquirer = await import('inquirer');
  const { createPromptModule } = inquirer;
  const prompt = createPromptModule();

  const likely = detectLikelyRegion(regions);

  const choices = regions.map((r) => ({
    name: `${r.label} (${r.domain})`,
    value: r.id,
  }));

  const { selection } = await prompt([
    {
      type: 'select',
      name: 'selection',
      message: t('commands.subscription.login.regionPrompt'),
      choices,
      default: likely.id,
    },
  ]);

  const selected = regions.find((r) => r.id === selection);
  if (!selected) throw new Error(t('errors.unknownRegion', { region: selection as string }));
  return {
    region: selected,
    domain: selected.domain,
  };
}
