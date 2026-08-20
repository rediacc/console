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
import os from 'node:os';
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
/** Cursor-home / erase-line, which restart a display line just as `\r` does. */
const LINE_RESET_RE = /\r(?!\n)|\u001b\[[0-9]*[GK]/;

/**
 * Structured logs BELOW error level. They are not a correctness failure, they are
 * a "should never have been on camera" failure: the widest lines in the corpus
 * were 227-358 column `level=info` go-executor relays. Kept separate from
 * ERROR_PATTERNS so the two failures read differently in the report.
 */
const NOISE_PATTERNS = [/\blevel=(info|warning|warn|debug|trace)\b/, /^time="\d{4}-/];

/**
 * Is this line over-width ONLY because of a single URL nothing may break?
 *
 * `rdc vscode connect --browser` prints a 162-column line whose bulk is one URL
 * with an auth token in it. Wrapping a URL makes it uncopyable, which is worse
 * for the viewer than one long line, so the pipeline deliberately does not wrap
 * it. A gate that demands the impossible gets suppressed, so it is exempted
 * here EXPLICITLY rather than by widening the check.
 *
 * Deliberately narrow, and narrower than the first version: the token must be a
 * URL. Exempting any unbreakable token was tried and the gate's OWN selftest
 * caught it - the 150-column control is a single long token, so that version
 * silently stopped detecting the thing the gate exists for. Only URLs carry the
 * copy-paste argument; a long path, hash or joined field has no such defence and
 * still fails.
 */
function overflowIsOneUnbreakableUrl(line, width) {
  const tokens = line.split(/\s+/).filter(Boolean);
  const urls = tokens.filter((tok) => /^https?:\/\//.test(tok));
  const longest = urls.reduce((a, b) => (b.length > a.length ? b : a), '');
  if (longest.length <= width) return false;
  const withoutIt = line.replace(longest, '').trimEnd();
  return displayWidth(withoutIt) <= width;
}

/** Must match run.sh's TUTORIAL_COLS. A cast recorded at another width is a bug. */
const TUTORIAL_COLS = 107;

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

// Built from named char codes rather than written as `\x1b` literals: raw
// control characters inside a regex are exactly what no-control-regex exists to
// catch, and these two are the only place the gate legitimately needs them.
const ESC = String.fromCharCode(0x1b);
const BEL = String.fromCharCode(0x07);
/** CSI sequence: ESC [ params final-byte (colours, cursor moves). */
const ANSI_CSI_RE = new RegExp(`${ESC}\\[[0-9;]*[a-zA-Z]`, 'g');
/** OSC sequence: ESC ] ... BEL (window title and friends). */
const ANSI_OSC_RE = new RegExp(`${ESC}\\][^${BEL}]*${BEL}`, 'g');

/** Strip ANSI escape sequences and OSC sequences from text. */
function stripAnsi(text) {
  return text.replaceAll(ANSI_CSI_RE, '').replaceAll(ANSI_OSC_RE, '');
}

/**
 * Every run of text the terminal drew as one line, split at the points where the
 * cursor went back to the start.
 *
 * Two wrong models were tried before this one. Measuring raw `\n`-split lines
 * concatenates every spinner frame into a 22,562-column pseudo-line
 * (tutorial-live-migration), so all 24 of its "violations" are phantom. Keeping
 * only the LAST segment -- what finally settles on screen -- is wrong in the
 * opposite direction: a 358-column logrus line WRAPS across four rows when it is
 * written, and a following spinner repaint only overwrites the last of them, so
 * the check silently discarded the exact lines it exists to catch.
 *
 * Each segment is measured on its own. A spinner frame is short and passes; a
 * line that wrapped when it was drawn is caught, whatever happened afterwards.
 */
function drawnSegments(text) {
  const out = [];
  for (const physical of text.split('\n')) {
    for (const segment of physical.split(LINE_RESET_RE)) out.push(stripAnsi(segment));
  }
  return out;
}

/** Display width, counting a wide CJK glyph as the two cells it occupies. */
function displayWidth(line) {
  let w = 0;
  for (const ch of line) {
    const c = ch.codePointAt(0);
    if (c === undefined) continue;
    // Combining marks take no cell; CJK/fullwidth take two.
    if (c >= 0x0300 && c <= 0x036f) continue;
    w +=
      (c >= 0x1100 && c <= 0x115f) ||
      (c >= 0x2e80 && c <= 0xa4cf) ||
      (c >= 0xac00 && c <= 0xd7a3) ||
      (c >= 0xf900 && c <= 0xfaff) ||
      (c >= 0xfe30 && c <= 0xfe6f) ||
      (c >= 0xff00 && c <= 0xff60) ||
      (c >= 0xffe0 && c <= 0xffe6)
        ? 2
        : 1;
  }
  return w;
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

  // The header is line 1. Every other consumer of a cast reads it
  // (scenes/cast.ts passes header.width into the renderer); this validator used
  // to skip it, which is precisely why `width` was the one field no check could
  // see, and why ~200 wrapped lines shipped unnoticed.
  let headerWidth = TUTORIAL_COLS;
  try {
    const header = JSON.parse(lines[0]);
    if (typeof header.width === 'number') headerWidth = header.width;
    if (headerWidth !== TUTORIAL_COLS) {
      pushError(
        errors,
        relPath,
        `Recorded at ${headerWidth} columns, but the pipeline records ${TUTORIAL_COLS}`,
        'Re-record with ./run.sh www tutorials record (record.sh defaults drifted from run.sh once)'
      );
    }
  } catch {
    pushError(errors, relPath, 'Unreadable cast header', 'Re-record tutorial');
  }

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
        checkMarkerOutput(
          currentMarker,
          currentOutput,
          relPath,
          errors,
          expectFailLabels,
          headerWidth
        );
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
    checkMarkerOutput(currentMarker, currentOutput, relPath, errors, expectFailLabels, headerWidth);
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

function checkMarkerOutput(markerLabel, outputChunks, file, errors, expectFailLabels, width) {
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

  // Any settled line that is JSON, not only the CLI envelope. The 322-column
  // {"push_result":...} dump has no "success" key and sailed through the probe
  // above for as long as it existed.
  for (const line of drawnSegments(outputChunks.join(''))) {
    const t = line.trim();
    if (t.length > 40 && t.startsWith('{') && t.endsWith('}')) {
      pushError(
        errors,
        file,
        `Command "${markerLabel}" printed a raw JSON object on camera: ${t.slice(0, 60)}...`,
        'Renet machine-readable output must be consumed by the CLI, not echoed to the terminal'
      );
      break;
    }
  }

  // The check this file existed without: does the output FIT?
  for (const line of drawnSegments(outputChunks.join(''))) {
    const w = displayWidth(line);
    if (w > width && !overflowIsOneUnbreakableUrl(line, width)) {
      pushError(
        errors,
        file,
        `Command "${markerLabel}" printed a ${w}-column line into a ${width}-column terminal: ${line.slice(0, 60)}...`,
        'The terminal wraps it into the row below and shreds the layout. Narrow the output at source'
      );
      break;
    }
  }

  // Structured logs below error level: never intended for a viewer, and the
  // widest lines in the whole corpus.
  //
  // EXCEPT in a failure demo. When a command fails, the CLI deliberately replays
  // the info-level diagnostics it withheld while the command was running,
  // because dropping them outright was tried and made real failures unreadable
  // (executor/output-lines.ts). In a `run_cmd_expect_fail` scene the failure IS
  // the demo, so that explanation is the payoff the viewer came for, and this
  // rule would otherwise require deleting it. Scoped to the noise class ONLY:
  // an over-width line or a raw JSON dump is still a defect in a failure demo,
  // which is why those checks run above this point and are not exempted.
  const isFailureDemo = expectFailLabels.some((re) => re.test(markerLabel));
  for (const line of isFailureDemo ? [] : drawnSegments(outputChunks.join(''))) {
    if (NOISE_PATTERNS.some((re) => re.test(line))) {
      pushError(
        errors,
        file,
        `Command "${markerLabel}" leaked a structured log line: ${line.slice(0, 60)}...`,
        'Withhold info/debug relay lines from the live terminal (see executor/output-lines.ts isQuietLogrusLine)'
      );
      break;
    }
  }

  // Failure demos: the denial output is intentional.
  if (isFailureDemo) return;

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
      const unescaped = m[1].replaceAll(/\\(["\\$`])/g, '$1');
      const templated = unescaped.replaceAll(/\$\{[^}]+\}|\$\w+/g, placeholder);
      const escaped = templated.replaceAll(/[.*+?^()|[\]\\{}$]/g, '\\$&');
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
      if (!line.includes('run_cmd')) continue;
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

/**
 * Prove the detector can both FIRE and STAY QUIET before anyone trusts a green run.
 *
 * The quiet cases are the ones that matter here. Two earlier versions of this
 * check were wrong in opposite directions -- one counted concatenated spinner
 * frames as a 22,562-column line, the other threw away wrapped logrus lines
 * because a later repaint overwrote their last row. Both looked plausible.
 */
function selftest() {
  const ESC = String.fromCharCode(27);
  const cast = (events) =>
    [JSON.stringify({ version: 2, width: TUTORIAL_COLS, height: 32 })]
      .concat(events.map((e) => JSON.stringify(e)))
      .join('\n');

  const spinner = Array.from(
    { length: 200 },
    () => `${ESC}[2K${ESC}[1G_ Provisioning renet...`
  ).join('');
  const wide = 'x'.repeat(150);
  const cases = [
    [
      'clean output passes',
      cast([
        [1, 'm', 'rdc repo list'],
        [1, 'o', 'NAME   STATUS\nweb    up\n'],
      ]),
      false,
    ],
    [
      '200 spinner frames pass (no phantom width)',
      cast([
        [1, 'm', 'rdc repo up demo'],
        [1, 'o', spinner],
      ]),
      false,
    ],
    [
      'a 150-column line FAILS',
      cast([
        [1, 'm', 'rdc config show'],
        [1, 'o', `${wide}\n`],
      ]),
      true,
    ],
    [
      // The exemption that lets `rdc vscode connect --browser` through. Pinned so a
      // future widening of it shows up here rather than silently disarming the
      // width check, which is what the first version of it did.
      'a lone over-long URL is EXEMPT (wrapping one makes it uncopyable)',
      cast([
        [1, 'm', 'rdc vscode connect my-app --browser --no-open'],
        [1, 'o', `Open VS Code in your browser: http://localhost:46287/?tkn=${'M'.repeat(140)}\n`],
      ]),
      false,
    ],
    [
      // Same shape, NOT a URL: a long path has no copy-paste defence and must fail.
      'a lone over-long non-URL token still FAILS',
      cast([
        [1, 'm', 'rdc repo list'],
        [1, 'o', `/var/lib/rediacc/${'p'.repeat(160)}\n`],
      ]),
      true,
    ],
    [
      'a level=info relay line FAILS',
      cast([
        [1, 'm', 'rdc repo up demo'],
        [1, 'o', 'time="2026-01-01T00:00:00Z" level=info msg="x"\n'],
      ]),
      true,
    ],
    [
      'a raw JSON dump FAILS',
      cast([
        [1, 'm', 'rdc backup push demo'],
        [1, 'o', '{"push_result":{"repository":"abc","size":2147483648,"method":"rsync"}}\n'],
      ]),
      true,
    ],
  ];

  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'castgate-'));
  let failed = 0;
  let ran = 0;
  for (const [name, body, expectError] of cases) {
    ran++;
    const file = path.join(tmp, 'tutorial-probe.cast');
    fs.writeFileSync(file, body);
    const errs = [];
    validateCastFile(file, errs, []);
    const fired = errs.length > 0;
    if (fired !== expectError) {
      failed++;
      console.error(
        `FAIL  ${name}: expected ${expectError ? 'an error' : 'no error'}, got ${errs.length}`
      );
      for (const e of errs.slice(0, 2)) console.error(`        ${e.message}`);
    } else {
      console.log(`ok    ${name}`);
    }
  }
  // Header width drift is its own case: a cast recorded at another width.
  const drifted = path.join(tmp, 'tutorial-drift.cast');
  fs.writeFileSync(
    drifted,
    [JSON.stringify({ version: 2, width: 100, height: 30 }), JSON.stringify([1, 'o', 'hi\n'])].join(
      '\n'
    )
  );
  const driftErrs = [];
  validateCastFile(drifted, driftErrs, []);
  ran++;
  if (!driftErrs.some((e) => /columns, but the pipeline records/.test(e.message))) {
    failed++;
    console.error('FAIL  a cast recorded at 100 columns must be reported');
  } else {
    console.log('ok    a cast recorded at 100 columns is reported');
  }

  // The failure-demo exemption, pinned in BOTH directions. It is the only place
  // this gate is allowed to stay quiet about a logrus line, so a widening of it
  // has to show up here rather than silently disarming the noise class.
  const demoLabel = 'rdc repo up my-app:test';
  const demoCases = [
    [
      'a failure demo may replay its info-level diagnostic',
      cast([
        [1, 'm', demoLabel],
        [1, 'o', 'time="2026-08-19T21:47:23Z" level=info msg="denied by the sandbox"\n'],
      ]),
      false,
    ],
    [
      'the SAME line outside a failure demo still FAILS',
      cast([
        [1, 'm', 'rdc repo list'],
        [1, 'o', 'time="2026-08-19T21:47:23Z" level=info msg="denied by the sandbox"\n'],
      ]),
      true,
    ],
    [
      'a failure demo is NOT exempt from the width rule',
      cast([
        [1, 'm', demoLabel],
        [1, 'o', `${'w'.repeat(150)}\n`],
      ]),
      true,
    ],
  ];
  for (const [name, body, expectError] of demoCases) {
    ran++;
    const file = path.join(tmp, 'tutorial-demo-probe.cast');
    fs.writeFileSync(file, body);
    const errs = [];
    validateCastFile(file, errs, [new RegExp(`^${demoLabel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`)]);
    const fired = errs.length > 0;
    if (fired !== expectError) {
      failed++;
      console.error(`FAIL  ${name}: expected ${expectError ? 'an error' : 'no error'}, got ${errs.length}`);
      for (const e of errs.slice(0, 2)) console.error(`        ${e.message}`);
    } else {
      console.log(`ok    ${name}`);
    }
  }

  fs.rmSync(tmp, { recursive: true, force: true });
  if (failed > 0) {
    console.error(`\nselftest: ${failed} control(s) failed. This gate is not trustworthy.`);
    process.exit(1);
  }
  // COUNTED, not hardcoded: the literal said 6 while 8 controls ran, which is a
  // gate quietly misreporting its own coverage.
  console.log(
    `\nselftest: ${ran} controls passed -- fires on width, noise, JSON and drift; quiet on clean output and spinners.`
  );
  process.exit(0);
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

if (process.argv.includes('--selftest')) selftest();
main();
