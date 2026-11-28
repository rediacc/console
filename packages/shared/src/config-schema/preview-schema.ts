/**
 * The preview overlay of the config document (PLAN-preview-signer.md D5, D8). `schemas.ts` embeds it
 * as the `preview` bucket and re-exports the public names.
 */

import { z } from 'zod';
import { resourceName } from './primitives.js';

/**
 * A preview name: `pv-` and three lowercase words (PLAN-preview-signer.md D5). It is both the preview
 * host `https://<name>.rediacc.workers.dev` and the CLI release channel `cli/<name>/`.
 */
export const PREVIEW_NAME_PATTERN = /^pv-[a-z]+-[a-z]+-[a-z]+$/;

/** One server the preview CLI replaced renet on: the pre-preview slot, kept pinned until `leave` switches it back. */
const PreviewTouchedServerSchema = z.object({
  slot: z.string(),
  version: z.string(),
  sha256: z.string(),
  touchedAt: z.string(),
});

/** The PR's on-disk format warning (D12): the formats a switch back may not read, and why. */
const PreviewFormatChangeSchema = z.object({
  formats: z.array(z.string()),
  reason: z.string(),
});

/**
 * `previewBuild` of a preview's server-info (D6): the build the deploy staged, with one sha256 per
 * platform key (for example `linux-x64`), written by the deploy into the preview Worker beside the R2
 * manifest so `rdc preview use` can refuse a binary the two origins disagree on.
 */
export const PreviewBuildSchema = z.object({
  version: z.string().min(1),
  sha256: z.record(z.string(), z.string().regex(/^[0-9a-f]{64}$/)),
  formatChange: PreviewFormatChangeSchema.optional(),
});

/**
 * The preview overlay (PLAN-preview-signer.md D8). While it exists, the account pointer answers the
 * preview's host, channel and token file; the `account` section stays byte-identical, and removing
 * this block puts the real server, key and token back in force by construction.
 */
export const PreviewOverlaySchema = z.object({
  name: z.string().regex(PREVIEW_NAME_PATTERN),
  host: z.string(),
  enteredAt: z.string(),
  channel: z.string(),
  /** The PR's on-disk format warning (D12), copied from server-info's `previewBuild.formatChange`. */
  formatChange: PreviewFormatChangeSchema.optional(),
  /** When the preview's licences end unless renewed (D4, D11), shown in the banner; `enteredAt` plus the 7-day cap. */
  licenceEndsAt: z.string().optional(),
  /** The CLI before `use`: what `leave` reinstalls. */
  previous: z.object({
    cliVersion: z.string(),
    cliSha256: z.string(),
    updateChannel: z.string().optional(),
    /** Where the installed `rdc` lives, so `leave` run from the kept copy still restores the install (D8). */
    binaryPath: z.string().optional(),
  }),
  /** Machine name -> its pre-preview renet slot (D9). */
  touched: z.record(resourceName, PreviewTouchedServerSchema).optional(),
});

type PreviewBuild = z.infer<typeof PreviewBuildSchema>;

export type { PreviewBuild };
