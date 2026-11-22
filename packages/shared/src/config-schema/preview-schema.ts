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
  formatChange: z
    .object({
      formats: z.array(z.string()),
      reason: z.string(),
    })
    .optional(),
  /** The CLI before `use`: what `leave` reinstalls. */
  previous: z.object({
    cliVersion: z.string(),
    cliSha256: z.string(),
    updateChannel: z.string().optional(),
  }),
  /** Machine name -> its pre-preview renet slot (D9). */
  touched: z.record(resourceName, PreviewTouchedServerSchema).optional(),
});
