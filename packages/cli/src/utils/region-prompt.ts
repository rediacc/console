/**
 * Interactive region selection prompt.
 * Uses inquirer to present a list of available data regions.
 * Shows both production and edge channel options.
 */

import type { RegionInfo } from '@rediacc/shared/regions';
import { t } from '../i18n/index.js';
import { exitProcess } from '../services/core/request-context.js';
import { detectLikelyRegion } from '../services/provision/region-discovery.js';
import { EXIT_CODES } from '../types/index.js';

export interface RegionSelection {
  region: RegionInfo;
  domain: string;
  isEdge: boolean;
}

export async function promptRegionSelection(regions: RegionInfo[]): Promise<RegionSelection> {
  if (process.stdin.isTTY !== true) {
    console.error(t('errors.regionSelectionRequiresTTY'));
    exitProcess(EXIT_CODES.INVALID_ARGUMENTS);
  }

  // Lazy-load inquirer (rxjs + prompt graph) only when the region picker
  // is actually shown during interactive login. `Separator` lives on the
  // default export; `createPromptModule` is a named export.
  const inquirer = await import('inquirer');
  const { createPromptModule } = inquirer;
  const { Separator } = inquirer.default;
  const prompt = createPromptModule();

  const likely = detectLikelyRegion(regions);

  const choices = [
    ...regions.map((r) => ({
      name: `${r.label} (${r.domain})`,
      value: `prod:${r.id}`,
    })),
    new Separator(`── ${t('commands.subscription.login.edgeSeparator', 'Edge Channel')} ──`),
    ...regions.map((r) => ({
      name: `${r.label} - Edge (${r.edgeDomain})`,
      value: `edge:${r.id}`,
    })),
  ];

  const { selection } = await prompt([
    {
      type: 'select',
      name: 'selection',
      message: t('commands.subscription.login.regionPrompt'),
      choices,
      default: `prod:${likely.id}`,
    },
  ]);

  const [channel, regionId] = (selection as string).split(':');
  const isEdge = channel === 'edge';
  const selected = regions.find((r) => r.id === regionId);
  if (!selected) throw new Error(t('errors.unknownRegion', { region: regionId }));
  return {
    region: selected,
    domain: isEdge ? selected.edgeDomain : selected.domain,
    isEdge,
  };
}
