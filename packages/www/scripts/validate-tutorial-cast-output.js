#!/usr/bin/env node
/**
 * validate-tutorial-cast-output.js
 *
 * Gate on what the published tutorial videos actually show:
 *  - no error output under any command (renet level=error/fatal included)
 *  - no shell hacks typed on camera (`|| true`, `2>/dev/null`, `timeout N`)
 *  - no raw CLI JSON envelopes where a table should render
 *  - nothing after the "Tutorial complete!" banner (cleanup must be silenced)
 *
 * Commands recorded via run_cmd_expect_fail in the tutorial scripts are
 * exempt from the error-output check — the failure IS the demo there, and
 * the helper already asserts the command cannot accidentally succeed.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { findRegressions, loadBacklog, writeBacklog } from './lib/p7-backlog.js';

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
  /level=(error|fatal)/,
];

/** On-camera shell hacks that must never appear in a typed command. */
const MARKER_HACK_PATTERNS = [
  { pattern: /\|\|\s*true/, message: 'typed command carries "|| true"' },
  { pattern: /2>\s*\/dev\/null/, message: 'typed command carries "2>/dev/null"' },
  { pattern: />\s*\/dev\/null/, message: 'typed command suppresses output with >/dev/null' },
  { pattern: /\btimeout\s+[\d.]+/, message: 'typed command is wrapped in "timeout"' },
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

function validateCastFile(castFile, errors, expectFailLabels) {
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
  let sawComplete = false;
  let leakedAfterComplete = '';

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
        checkMarkerOutput(currentMarker, currentOutput, relPath, errors, expectFailLabels);
      }
      currentMarker = data;
      currentOutput = [];
    } else if (type === 'o' && typeof data === 'string') {
      currentOutput.push(data);
      const plain = stripAnsi(data);
      if (sawComplete && plain.trim()) {
        leakedAfterComplete += plain;
      }
      if (plain.includes('Tutorial complete!')) {
        sawComplete = true;
        // Anything in the same chunk after the banner counts as leakage.
        const tail = plain.split('Tutorial complete!')[1] ?? '';
        leakedAfterComplete += tail.trim() ? tail : '';
      }
    }
  }

  // Flush last marker
  if (currentMarker !== null) {
    checkMarkerOutput(currentMarker, currentOutput, relPath, errors, expectFailLabels);
  }

  const leaked = leakedAfterComplete.trim();
  if (leaked) {
    pushError(
      errors,
      relPath,
      `Output after "Tutorial complete!" banner: "${leaked.slice(0, 100)}"`,
      'Silence cleanup with end_recording (tutorial-helpers.sh) before cleanup commands'
    );
  }
}

function checkMarkerOutput(markerLabel, outputChunks, file, errors, expectFailLabels) {
  for (const { pattern, message } of MARKER_HACK_PATTERNS) {
    if (pattern.test(markerLabel)) {
      pushError(
        errors,
        file,
        `Command "${markerLabel}": ${message}`,
        'Fix the underlying product issue; tutorial commands must run clean'
      );
    }
  }

  const text = stripAnsi(outputChunks.join(''));
  if (/"success":\s*(true|false)/.test(text)) {
    pushError(
      errors,
      file,
      `Command "${markerLabel}" printed a raw CLI JSON envelope`,
      'The command should render a table in recordings (REDIACC_DEFAULT_OUTPUT=table)'
    );
  }

  // Failure demos: the denial output is intentional.
  if (expectFailLabels.some((re) => re.test(markerLabel))) return;

  const errorLine = findErrorInOutput(outputChunks);
  if (errorLine) {
    pushError(
      errors,
      file,
      `Command "${markerLabel}" produced error output: "${errorLine}"`,
      'Fix the command in the tutorial script (run_cmd_expect_fail for intentional failure demos)'
    );
  }
}

/**
 * Collect the display labels of run_cmd_expect_fail invocations across all
 * tutorial scripts — those markers are allowed (required, even) to show
 * failure output. Script labels contain unexpanded shell variables while
 * cast markers carry the expanded values, so each label becomes a regex
 * with `$VAR` / `${VAR}` segments relaxed to wildcards.
 */
function collectExpectFailLabels() {
  const labels = [];
  if (!fs.existsSync(TUTORIAL_SCRIPTS_DIR)) return labels;
  for (const script of fs.readdirSync(TUTORIAL_SCRIPTS_DIR)) {
    if (!script.startsWith('tutorial-') || !script.endsWith('.sh')) continue;
    const content = fs.readFileSync(path.join(TUTORIAL_SCRIPTS_DIR, script), 'utf-8');
    for (const m of content.matchAll(/run_cmd_expect_fail\s+"((?:[^"\\]|\\.)*)"/g)) {
      const placeholder = '\u0001';
      // The script source carries shell escapes (\" \\ \$ \`) that bash
      // resolves before the label reaches the cast marker — unescape them
      // the same way so the derived regex matches the recorded marker.
      const unescaped = m[1].replace(/\\(["\\$`])/g, '$1');
      const templated = unescaped.replace(/\$\{[^}]+\}|\$\w+/g, placeholder);
      const escaped = templated.replace(/[.*+?^()|[\]\\{}$]/g, '\\$&');
      labels.push(new RegExp(`^${escaped.split(placeholder).join('.+?')}$`));
    }
  }
  return labels;
}

/** Patterns forbidden in on-camera tutorial script commands. */
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
  {
    pattern: /\|\|\s*true/,
    message: 'Failure masked with "|| true"',
    suggestion: 'Fix the underlying product issue or use run_cmd_expect_fail',
  },
  {
    pattern: /2>\s*\/dev\/null/,
    message: 'Stderr hidden with 2>/dev/null',
    suggestion: 'Fix the noisy output at the source instead of hiding it',
  },
  {
    pattern: /\btimeout\s+[\d.]+/,
    message: 'Command wrapped in "timeout"',
    suggestion: 'Use run_cmd_interrupt for long-running commands',
  },
];

function validateTutorialScripts(errors) {
  if (!fs.existsSync(TUTORIAL_SCRIPTS_DIR)) return;

  const scripts = fs
    .readdirSync(TUTORIAL_SCRIPTS_DIR)
    .filter((f) => f.startsWith('tutorial-') && f.endsWith('.sh'))
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
  const expectFailLabels = collectExpectFailLabels();

  // Validate cast file output for error patterns
  for (const castFile of castFiles) {
    validateCastFile(castFile, errors, expectFailLabels);
  }

  // Validate tutorial script source for forbidden patterns
  validateTutorialScripts(errors);

  console.log(colors.bold('Tutorial Cast Output Validation'));
  console.log('='.repeat(60));
  console.log(colors.dim(`Checked ${castFiles.length} recording(s).`));

  /**
   * The STALE-RECORDING backlog.
   *
   * BLOCKER: this gate exempts a command's error output when the tutorial script declares it
   * with `run_cmd_expect_fail "<command>"` — and it matches the declaration to the recording
   * BY COMMAND TEXT. The P4 reshape rewrote the 22 scripts in `.ci/tutorials` to the new
   * syntax (`rdc term connect app:work -c …`) while the `.cast` files still hold the OLD
   * recorded text (`rdc term connect --machine machine-11 --repository app:work --command …`).
   * The labels stopped matching, so expected failures became reported failures.
   *
   * The scripts are RIGHT and must stay right — they are the source for the next recording,
   * and reverting them would only move the failure to check-cli-docs, which also scans
   * `.ci/tutorials`. What is stale is the RECORDINGS, and re-recording needs a live VM lab
   * plus re-narration in 13 languages. That is deferred debt with its own ledger entry.
   *
   * ★ SELF-DESTRUCT: every entry here must vanish the moment the tutorials are re-recorded.
   * A stale-cast entry that outlives the re-record is a bug, not a deferral. The gate stays
   * fully armed for every other recording and for any NEW error in these ones.
   *
   * See `docs/design/spec/12-carried-debt.md` — "The website's STRUCTURED command data: 188
   * dead commands". These three recordings are the LIVE PROOF of that deferral: 70 of those
   * 188 are the commands TYPED in these recorded terminals, and 26 are the commands SPOKEN in
   * the narration, in 13 languages. This CI red is the deferral becoming visible, not an
   * inconvenience — it is the evidence that the re-record is real work, not a tidy-up.
   */
  const BASELINE_PATH = path.resolve(__dirname, 'tutorial-cast-baseline.json');
  if (process.argv.includes('--write-baseline')) {
    const { files, violations } = writeBacklog(BASELINE_PATH, errors);
    console.log(
      colors.dim(`Wrote stale-recording backlog: ${files} cast(s), ${violations} errors.`)
    );
    process.exit(0);
  }

  // Reached even when errors is empty: a cleared recording with a surviving baseline entry is
  // the stale case the ratchet exists to catch.
  const regressions = findRegressions(
    errors,
    loadBacklog(BASELINE_PATH),
    (e) => e.file,
    'recording'
  );
  if (errors.length === 0 && regressions.length === 0) {
    console.log(colors.green('✓ No error output detected in tutorial recordings.'));
    console.log('='.repeat(60));
    process.exit(0);
  }
  if (regressions.length === 0) {
    console.log(
      colors.dim(
        `⚠ ${errors.length} error(s), ALL in recordings that PREDATE the P4 reshape and are` +
          ' pending a re-record. A NEW error, or a new cast, still fails.'
      )
    );
    console.log('='.repeat(60));
    process.exit(0);
  }

  console.log(
    colors.red('\n✗ Stale-recording backlog OUT OF SYNC (the ratchet turns both ways):\n')
  );
  for (const r of regressions) console.log(colors.red(`  ✗ ${r}`));

  for (const error of errors) {
    console.log(colors.red(`✗ ${error.file}`));
    console.log(colors.dim(`  ${error.message}`));
    if (error.suggestion) {
      console.log(colors.cyan(`  → ${error.suggestion}`));
    }
  }

  console.log('='.repeat(60));
  console.log(
    colors.red(
      `✗ Validation failed (${errors.length} error(s), ${regressions.length} backlog problem(s))`
    )
  );
  process.exit(1);
}

main();
