#!/usr/bin/env node
/**
 * argv-compatible entrypoint replacing `npx postject`. The build calls:
 *
 *   node sea-inject/cli.mjs <binary> NODE_SEA_BLOB <blob> --sentinel-fuse <fuse>
 *
 * postject also accepts --macho-segment-name / --overwrite; we hard-code the
 * segment name to NODE_SEA (what node's __APPLE__ lookup expects) and always
 * treat the operation as a fresh injection, so those flags are accepted and
 * ignored for drop-in compatibility. Anything else unknown is a hard error, so
 * a build passing a flag we do not honour fails loudly instead of silently
 * mis-injecting.
 *
 * See index.mjs for why this exists (#525) and common.mjs for the streaming
 * guarantee.
 */
import { inject } from './index.mjs';

function usage(msg) {
  if (msg) console.error(`error: ${msg}`);
  console.error(
    'usage: cli.mjs <binary> <RESOURCE_NAME> <blob> --sentinel-fuse <fuse> [--macho-segment-name <n>] [--overwrite]'
  );
  process.exit(2);
}

function parseArgs(argv) {
  const positional = [];
  let fuse = null;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--sentinel-fuse') {
      fuse = argv[++i];
    } else if (a === '--macho-segment-name') {
      i++; // accepted for compat; segment name is fixed to NODE_SEA
    } else if (a === '--overwrite') {
      // accepted for compat; every run is a fresh injection
    } else if (a.startsWith('--')) {
      usage(`unsupported option ${a}`);
    } else {
      positional.push(a);
    }
  }
  const [binaryPath, resourceName, blobPath] = positional;
  if (!binaryPath || !resourceName || !blobPath) usage('missing positional argument');
  if (!fuse) usage('--sentinel-fuse is required');
  return { binaryPath, resourceName, blobPath, fuse };
}

const args = parseArgs(process.argv.slice(2));
const result = inject(args);
console.log(
  `sea-inject: ${result.format} injected ${result.blobSize} bytes ` +
    `at offset ${result.blobOffset} (${result.detail})`
);
