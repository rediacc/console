#!/usr/bin/env node
/**
 * validate-tutorial-cast-output.js
 *
 * Scans .cast files for error patterns in command output.
 * Commands whose marker label contains "|| true" are skipped (intentional error tolerance).
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const REPO_ROOT = path.resolve(ROOT, '../..');
const CAST_DIR = path.join(ROOT, 'public', 'assets', 'tutorials');
const TUTORIAL_SCRIPTS_DIR = path.join(REPO_ROOT, '.ci', 'tutorials');

const colors = {
  red: (s) => `\x1b[31m${s}\x1b[0m`,
  green: (s) => `\x1b[32m${s}\x1b[0m`,
  cyan: (s) => `\x1b[36m${s}\x1b[0m`,
  dim: (s) => `\x1b[2m${s}\x1b[0m`,
  bold: (s) => `\x1b[1m${s}\x1b[0m`,
};

/** Patterns that indicate a command produced error output. */
const ERROR_PATTERNS = [
  /^error:\s/i,
  /unknown command/i,
  /command not found/,
  /required option .* not specified/i,
  /too many arguments/i,
  /missing required argument/i,
  /^fatal:/i,
  /panic:/,
];

/** Strip ANSI escape sequences and OSC sequences from text. */
function stripAnsi(text) {
  return text.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '').replace(/\x1b\][^\x07]*\x07/g, '');
}

function pushError(errors, file, message, suggestion) {
  errors.push({ file, message, suggestion });
}

/**
 * Check a single command's concatenated output for error patterns.
 * Returns the first matching error line or null.
 */
function findErrorInOutput(outputChunks) {
  const text = stripAnsi(outputChunks.join(''));
  const lines = text.split(/\r?\n/);

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    for (const pattern of ERROR_PATTERNS) {
      if (pattern.test(trimmed)) {
        return trimmed;
      }
    }
  }
  return null;
}

function validateCastFile(castFile, errors) {
  const relPath = path.relative(ROOT, castFile);
  const raw = fs.readFileSync(castFile, 'utf-8');
  const lines = raw.split('\n').filter(Boolean);

  if (lines.length === 0) {
    pushError(errors, relPath, 'Empty cast file', 'Re-record tutorial');
    return;
  }

  // Line 1 is the JSON header -- skip it
  let currentMarker = null;
  let currentOutput = [];

  for (let i = 1; i < lines.length; i++) {
    let event;
    try {
      event = JSON.parse(lines[i]);
    } catch {
      continue;
    }
    if (!Array.isArray(event) || event.length < 3) continue;

    const [, type, data] = event;

    if (type === 'm') {
      // Flush previous marker's output
      if (currentMarker !== null) {
        checkMarkerOutput(currentMarker, currentOutput, relPath, errors);
      }
      currentMarker = data;
      currentOutput = [];
    } else if (type === 'o' && typeof data === 'string') {
      currentOutput.push(data);
    }
  }

  // Flush last marker
  if (currentMarker !== null) {
    checkMarkerOutput(currentMarker, currentOutput, relPath, errors);
  }
}

function checkMarkerOutput(markerLabel, outputChunks, file, errors) {
  // Skip commands that intentionally tolerate errors
  if (/\|\|\s*true/.test(markerLabel)) return;

  const errorLine = findErrorInOutput(outputChunks);
  if (errorLine) {
    pushError(
      errors,
      file,
      `Command "${markerLabel}" produced error output: "${errorLine}"`,
      'Fix the command in the tutorial script or add "|| true" if the error is intentional'
    );
  }
}

/** Patterns forbidden in tutorial script source files. */
const FORBIDDEN_SCRIPT_PATTERNS = [
  {
    pattern: />\s*\/dev\/null/,
    message: 'Output suppressed with >/dev/null',
    suggestion: 'Tutorial commands should show their output',
  },
  {
    pattern: /2>&1\s*\|?\s*>/,
    message: 'Stderr redirected to suppress output',
    suggestion: 'Tutorial commands should show their output',
  },
];

function validateTutorialScripts(errors) {
  if (!fs.existsSync(TUTORIAL_SCRIPTS_DIR)) return;

  const scripts = fs
    .readdirSync(TUTORIAL_SCRIPTS_DIR)
    .filter((f) => f.endsWith('-tutorial.sh'))
    .sort();

  for (const script of scripts) {
    const filePath = path.join(TUTORIAL_SCRIPTS_DIR, script);
    const lines = fs.readFileSync(filePath, 'utf-8').split('\n');

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      // Only check run_cmd lines (visible tutorial commands), skip setup/infra code
      if (!/run_cmd/.test(line)) continue;
      if (/^\s*#/.test(line)) continue;

      for (const { pattern, message, suggestion } of FORBIDDEN_SCRIPT_PATTERNS) {
        if (pattern.test(line)) {
          pushError(
            errors,
            `.ci/tutorials/${script}:${i + 1}`,
            `${message}: "${line.trim()}"`,
            suggestion
          );
        }
      }
    }
  }
}

function main() {
  const castFiles = fs
    .readdirSync(CAST_DIR)
    .filter((f) => f.endsWith('.cast'))
    .map((f) => path.join(CAST_DIR, f))
    .sort();

  const errors = [];

  // Validate cast file output for error patterns
  for (const castFile of castFiles) {
    validateCastFile(castFile, errors);
  }

  // Validate tutorial script source for forbidden patterns
  validateTutorialScripts(errors);

  console.log(colors.bold('Tutorial Cast Output Validation'));
  console.log('='.repeat(60));

  if (errors.length === 0) {
    console.log(colors.green('✓ No error output detected in tutorial recordings.'));
    console.log('='.repeat(60));
    process.exit(0);
  }

  for (const error of errors) {
    console.log(colors.red(`✗ ${error.file}`));
    console.log(colors.dim(`  ${error.message}`));
    if (error.suggestion) {
      console.log(colors.cyan(`  → ${error.suggestion}`));
    }
  }

  console.log('='.repeat(60));
  console.log(colors.red(`✗ Validation failed (${errors.length} errors)`));
  process.exit(1);
}

main();
