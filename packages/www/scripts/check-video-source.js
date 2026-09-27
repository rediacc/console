#!/usr/bin/env node
// Exit 77 (cannot-run) when a gate that plays tutorial video has no video source.
//
// With PUBLIC_VIDEO_CDN_BASE_URL unset, remark-tutorial-embed.ts embeds the LOCAL path, and a
// clean checkout has no local media (gitignored): the dev server answers the video with a 404
// page, Chrome reports "Format error", and every scenario of the tutorial player gate failed as
// "start did not enter playing state", which reads as a player regression. The ci-runner and the
// CI step both set the variable; a bare `npm run check:test:tutorial-player` in a clean clone did
// not (2026-09-27). Run by package.json ahead of the gate, so the gate file stays at its budget.
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const wwwRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const probe = path.join(wwwRoot, 'public/assets/tutorials/video/en/tutorial-production-mode.mp4');
if (!process.env.PUBLIC_VIDEO_CDN_BASE_URL && !fs.existsSync(probe)) {
  console.error(
    'tutorial player gate: no video source. Set PUBLIC_VIDEO_CDN_BASE_URL=https://media.rediacc.com ' +
      '(what CI and the ci-runner set), or sync the local media into packages/www/public/assets/tutorials/video/ ' +
      '(docs/agent-reference/media-assets.md). Exiting 77 (cannot-run): NOT a verdict on the player.'
  );
  process.exit(77);
}
