/**
 * Interactive region selection prompt.
 * Uses inquirer to present a list of available data regions.
 * Shows both production and edge channel options.
 */

import inquirer from 'inquirer';

const { createPromptModule, Separator } = inquirer;
import type { RegionInfo } from '@rediacc/shared/regions';
import { t } from '../i18n/index.js';
import { detectLikelyRegion } from '../services/region-discovery.js';
import { EXIT_CODES } from '../types/index.js';

const prompt = createPromptModule();

export interface RegionSelection {
  region: RegionInfo;
  domain: string;
  isEdge: boolean;
}

export async function promptRegionSelection(regions: RegionInfo[]): Promise<RegionSelection> {
  if (process.stdin.isTTY !== true) {
    console.error(t('errors.regionSelectionRequiresTTY'));
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

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
      type: 'list',
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
