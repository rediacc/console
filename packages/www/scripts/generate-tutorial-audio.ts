#!/usr/bin/env node

import { spawnSync } from 'node:child_process';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, '../../..');
const pythonBin = process.env.QWEN_TTS_PYTHON_BIN || 'python3';
const backendSrc = path.join(repoRoot, 'private', 'generative', 'src');

const args = ['-m', 'tutorial_tts.cli', '--repo-root', repoRoot, ...process.argv.slice(2)];

const result = spawnSync(pythonBin, args, {
  cwd: repoRoot,
  env: {
    ...process.env,
    PYTHONPATH: process.env.PYTHONPATH
      ? `${backendSrc}${path.delimiter}${process.env.PYTHONPATH}`
      : backendSrc,
  },
  stdio: 'inherit',
});

if (result.error) {
  console.error(`Failed to execute Python backend: ${result.error.message}`);
  process.exit(1);
}

process.exit(result.status ?? 1);
