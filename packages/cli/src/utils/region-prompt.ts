/**
 * Interactive region selection prompt.
 * Uses inquirer to present a list of available data regions.
 */

import { createPromptModule } from 'inquirer';
import type { RegionInfo } from '@rediacc/shared/regions';
import { detectLikelyRegion } from '../services/region-discovery.js';
import { EXIT_CODES } from '../types/index.js';

const prompt = createPromptModule();

export async function promptRegionSelection(regions: RegionInfo[]): Promise<RegionInfo> {
  if (process.stdin.isTTY !== true) {
    console.error(
      'Error: Region selection requires interactive input. Use --server <url> to specify a server directly.'
    );
    process.exit(EXIT_CODES.INVALID_ARGUMENTS);
  }

  const likely = detectLikelyRegion(regions);

  const { region } = await prompt([
    {
      type: 'list',
      name: 'region',
      message: 'Where should your data be stored?',
      choices: regions.map((r) => ({
        name: `${r.label} (${r.domain})`,
        value: r.id,
      })),
      default: likely.id,
    },
  ]);

  const selected = regions.find((r) => r.id === region);
  if (!selected) throw new Error(`Unknown region: ${region}`);
  return selected;
}
