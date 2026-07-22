#!/usr/bin/env node
/**
 * Generate the delta-update block index for a released rdc binary.
 *
 * Publish the result beside the binary as `<binary>.delta.json`. A client on any
 * previous version fetches it, finds which blocks it already has on disk, and
 * downloads only the rest over HTTP Range. See
 * packages/cli/src/services/update/delta.ts for the algorithm and for why this
 * is a per-release index rather than a per-version-pair patch.
 *
 * The index is advisory: a client that cannot fetch it, or whose local binary
 * shares nothing with the target, simply downloads the whole file as before.
 * Nothing breaks if this step is skipped, which is why it is safe to run at the
 * end of a build rather than in the critical path.
 *
 * Usage:
 *   npx tsx scripts/generate-update-index.ts dist/cli/rdc-linux-x64
 *   npx tsx scripts/generate-update-index.ts dist/cli/rdc-linux-x64 -o /tmp/x.json
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import { buildIndex } from '../packages/cli/src/services/update/delta.js';
import { GREEN, NC, RED } from './utils/console.js';

async function main(): Promise<void> {
  const args = process.argv.slice(2).filter((a) => a !== '--');
  const outFlag = args.indexOf('-o');
  const output = outFlag >= 0 ? args[outFlag + 1] : undefined;
  const target = args.find((a, i) => !a.startsWith('-') && i !== outFlag + 1);

  if (!target) {
    console.error(`${RED}usage: generate-update-index.ts <binary> [-o <index.json>]${NC}`);
    process.exit(1);
  }

  const stat = await fs.stat(target).catch(() => null);
  if (!stat?.isFile()) {
    console.error(`${RED}✗ not a file: ${target}${NC}`);
    process.exit(1);
  }

  const index = await buildIndex(target);
  const dest = output ?? `${target}.delta.json`;
  await fs.writeFile(dest, `${JSON.stringify(index)}\n`);

  const indexSize = (await fs.stat(dest)).size;
  const pct = ((indexSize / index.totalSize) * 100).toFixed(3);
  console.log(
    `${GREEN}✓${NC} ${path.basename(dest)}: ${index.blocks.length} blocks of ${index.blockSize}B ` +
      `over ${index.totalSize.toLocaleString()}B (index is ${indexSize.toLocaleString()}B, ${pct}% of the target)`
  );
}

main().catch((err) => {
  console.error(`${RED}✗ ${(err as Error).message}${NC}`);
  process.exit(1);
});
