/**
 * Third-party credits / license-compliance surface for rdc.
 *
 * Loads the attribution inventory (data/third-party-credits.json) and the
 * build-generated THIRD_PARTY_LICENSES text, and renders them for `rdc credits`.
 *
 * Data source: in a release SEA build the inventory and the license text are
 * embedded as SEA assets (prepare-cli-assets.sh); in dev the inventory is the
 * bundled source JSON and the license text is only present if a local CLI build
 * has generated it into dist/assets.
 */

import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import chalk from 'chalk';
import bundledCredits from '../../data/third-party-credits.json' with { type: 'json' };
import { t } from '../../i18n/index.js';
import { getEmbeddedAssetText, isSEA } from './embedded-assets.js';

/** One attributed third-party component. */
interface Credit {
  /** Category: embedded-binary (conveyed by renet), runtime, or bundled-deps. */
  kind?: string;
  /** Embed asset base name (criu/rsync/rclone) for renet-embedded binaries. */
  asset?: string;
  name: string;
  version: string;
  spdx: string;
  license: string;
  upstreamSourceUrl?: string;
  plannedMirrorUrl?: string;
  notes?: string;
}

/** The full attribution inventory. */
export interface CreditsData {
  gplWrittenOffer: string;
  components: Credit[];
}

/** SEA asset key for the embedded inventory JSON. */
const CREDITS_ASSET_KEY = 'third-party-credits.json';
/** SEA asset key for the embedded full license text. */
const LICENSES_ASSET_KEY = 'THIRD_PARTY_LICENSES';

/**
 * Load the attribution inventory. In SEA builds this reads the embedded asset;
 * otherwise (and as a safety net) it returns the bundled source-of-truth JSON.
 */
export function loadCreditsData(): CreditsData {
  if (isSEA()) {
    try {
      return JSON.parse(getEmbeddedAssetText(CREDITS_ASSET_KEY)) as CreditsData;
    } catch {
      // Fall back to the bundled inventory below.
    }
  }
  return bundledCredits;
}

/**
 * Candidate paths for the build-generated THIRD_PARTY_LICENSES file in dev mode.
 * The file is written to packages/cli/dist/assets by prepare-cli-assets.sh; it
 * is absent unless a local CLI build has run.
 */
function devLicensesCandidates(): string[] {
  return [
    path.resolve(process.cwd(), 'packages/cli/dist/assets', LICENSES_ASSET_KEY),
    path.resolve(process.cwd(), 'dist/assets', LICENSES_ASSET_KEY),
  ];
}

/**
 * Load the full THIRD_PARTY_LICENSES text, or null if it is not available
 * (dev mode without a CLI build). Never throws.
 */
export function loadLicensesText(): string | null {
  if (isSEA()) {
    try {
      return getEmbeddedAssetText(LICENSES_ASSET_KEY);
    } catch {
      return null;
    }
  }
  for (const candidate of devLicensesCandidates()) {
    try {
      if (existsSync(candidate)) {
        return readFileSync(candidate, 'utf-8');
      }
    } catch {
      // Ignore unreadable candidates and try the next.
    }
  }
  return null;
}

function renderComponent(c: Credit): string {
  const lines = [`  ${chalk.bold(`${c.name} ${c.version}`)}`];
  lines.push(`    SPDX:     ${c.spdx}`);
  lines.push(`    License:  ${c.license}`);
  if (c.upstreamSourceUrl) lines.push(`    Source:   ${c.upstreamSourceUrl}`);
  if (c.plannedMirrorUrl) lines.push(`    Mirror:   ${c.plannedMirrorUrl} (planned)`);
  if (c.notes) lines.push(`    Note:     ${c.notes}`);
  return lines.join('\n');
}

/** Render the inventory as a human-readable report. */
export function renderCredits(data: CreditsData): string {
  const embedded = data.components.filter((c) => c.kind === 'embedded-binary');
  const rest = data.components.filter((c) => c.kind !== 'embedded-binary');

  const sections: string[] = [chalk.bold(t('commands.credits.header')), ''];

  if (embedded.length > 0) {
    sections.push(t('commands.credits.embeddedTitle'));
    sections.push(embedded.map(renderComponent).join('\n\n'));
    sections.push('');
  }
  if (rest.length > 0) {
    sections.push(t('commands.credits.bundledTitle'));
    sections.push(rest.map(renderComponent).join('\n\n'));
    sections.push('');
  }

  sections.push(t('commands.credits.gplHeader'));
  sections.push(`  ${data.gplWrittenOffer}`);

  return sections.join('\n');
}

/** Render the inventory as JSON. */
export function renderCreditsJson(data: CreditsData): string {
  return JSON.stringify(
    { components: data.components, gplWrittenOffer: data.gplWrittenOffer },
    null,
    2
  );
}
