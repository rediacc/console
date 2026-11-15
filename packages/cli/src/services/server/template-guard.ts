/**
 * Local edits to the deployed template (Q19). After the template is applied the box records the
 * sha256 of each file it wrote; `rdc server upgrade` checks them before applying a newer template
 * and refuses on an edited file unless `--force`, because the apply would overwrite the edit.
 */

import { type RepoOnBox, runOnBox } from './box.js';
import { TEMPLATE_EDITS, TEMPLATE_SUMS_WRITE } from './box-scripts-offline.js';
import { templateFiles } from './common.js';
import type { ServerDeps } from './types.js';

/** The files the built-in elite template writes. */
export function templateFileNames(): string[] {
  return Object.keys(templateFiles()).sort((a, b) => Number(a > b) - Number(a < b));
}

/** Record the sums of the template's files as they are on the box now (right after an apply). */
export async function writeTemplateSums(deps: ServerDeps, where: RepoOnBox): Promise<void> {
  await runOnBox(deps, where, TEMPLATE_SUMS_WRITE, `${templateFileNames().join('\n')}\n`);
}

export interface TemplateEdits {
  /** False when the box holds no recorded sums (it predates them): nothing can be compared. */
  baseline: boolean;
  edited: string[];
}

export async function readTemplateEdits(
  deps: ServerDeps,
  where: RepoOnBox
): Promise<TemplateEdits> {
  const lines = (await runOnBox(deps, where, TEMPLATE_EDITS)).stdout.split('\n');
  return {
    baseline: lines.some((l) => l.trim() === 'baseline=sums'),
    edited: lines
      .map((l) => l.trim())
      .filter((l) => l.startsWith('edited='))
      .map((l) => l.slice('edited='.length)),
  };
}
