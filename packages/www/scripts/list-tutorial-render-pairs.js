#!/usr/bin/env node
// ---------------------------------------------------------------------------
// Which (tutorial, language) pairs need a video rendered?
// ---------------------------------------------------------------------------
//
// One place that answers that question, for every caller: `./run.sh www tutorials video`,
// the pair-level render watch, and any ad-hoc check. It used to be duplicated as a bash
// loop in run.sh and again in a scratchpad daemon, which is how a readiness predicate
// drifts — the two already disagreed, because the daemon silently dropped the audio-
// directory precondition.
//
// EMISSION IS LANG-MAJOR, and that is load-bearing rather than cosmetic.
// generate-tutorial-video.ts caches recorded browser segments under
// public/assets/tutorials/browser-segments/ keyed "${tutorial}.${scene.id}.${hash}.mp4"
// with NO language in the key, because the footage is language-independent. Tutorial-major
// ordering therefore puts N languages of the SAME tutorial in flight at --jobs N and, on a
// cold cache, all N record the same scene and copyFileSync to one path. Lang-major puts N
// DISTINCT tutorials in flight, so the shared key is never contended.
//
// STALENESS IS READ FROM THE ARTIFACTS, never from a list anything maintains: a pair is
// stale when its timeline JSON is NEWER than its .mp4, or the .mp4 is missing. That is
// self-correcting — re-narrate anything and it becomes eligible again automatically, with
// no bookkeeping to drift out of sync.
//
// CAVEAT that the mtime test depends on: generate-tutorial-video.ts must write the .mp4
// ATOMICALLY. If a killed render can leave a truncated file with a fresh mtime, this
// predicate will call that pair done forever. See docs/tutorial-render-watch.md (S3).
//
// Usage:
//   node packages/www/scripts/list-tutorial-render-pairs.js [options]
//     --lang a,b            restrict to these locales
//     --cast name           restrict to this tutorial (accepts bare or tutorial- prefixed)
//     --stale-only          only pairs whose video is missing or older than its timeline
//     --require-provider id only timelines produced by this TTS provider (e.g. voxcpm2)
//     --root <dir>          repo root override (tests)
//     --selftest            run the fixture suite and exit
// ---------------------------------------------------------------------------

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..');

function parseArgs(argv) {
  const opts = {
    langs: null,
    cast: null,
    staleOnly: false,
    requireProvider: null,
    root: REPO_ROOT,
    selftest: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = () => argv[(i += 1)];
    if (arg === '--stale-only') opts.staleOnly = true;
    else if (arg === '--selftest') opts.selftest = true;
    else if (arg === '--lang') opts.langs = new Set(next().split(','));
    else if (arg === '--cast') opts.cast = next();
    else if (arg === '--require-provider') opts.requireProvider = next();
    else if (arg === '--root') opts.root = path.resolve(next());
    else if (arg === '--help' || arg === '-h') {
      console.log(
        'Usage: list-tutorial-render-pairs.js [--lang a,b] [--cast name] [--stale-only]\n' +
          '                                    [--require-provider id] [--root dir] [--selftest]'
      );
      process.exit(0);
    } else {
      console.error(`list-tutorial-render-pairs: unknown argument ${arg}`);
      process.exit(2);
    }
  }
  return opts;
}

/**
 * @returns {{pairs: Array<{cast: string, lang: string}>}}
 * @throws if the tree looks empty — see the vacuity note below.
 */
export function listRenderPairs(opts) {
  const tutorialsRoot = path.join(opts.root, 'packages', 'www', 'public', 'assets', 'tutorials');
  const timelineRoot = path.join(opts.root, 'packages', 'www', 'src', 'data', 'tutorial-timeline');
  const videoRoot = path.join(tutorialsRoot, 'video');

  const casts = fs.existsSync(tutorialsRoot)
    ? fs
        .readdirSync(tutorialsRoot)
        .filter((f) => f.endsWith('.cast'))
        .map((f) => f.slice(0, -'.cast'.length))
    : [];
  const locales = fs.existsSync(timelineRoot)
    ? fs
        .readdirSync(timelineRoot)
        .filter((d) => fs.statSync(path.join(timelineRoot, d)).isDirectory())
        .sort((a, b) => a.localeCompare(b))
    : [];

  // Refuse rather than report "0 pairs". A predicate that answers cheerfully on an empty
  // tree is the vacuous-gate failure mode: every caller reads "nothing to do" and a broken
  // checkout looks identical to a finished one.
  if (casts.length === 0 || locales.length === 0) {
    throw new Error(
      `Refusing to run: found ${casts.length} .cast file(s) under ${tutorialsRoot} and ` +
        `${locales.length} locale dir(s) under ${timelineRoot}. One of them is empty, so any ` +
        `answer would be meaningless. Check --root, or that the tree is fully checked out.`
    );
  }

  let wanted = casts;
  if (opts.cast) {
    const base = opts.cast.startsWith('tutorial-') ? opts.cast : `tutorial-${opts.cast}`;
    if (!casts.includes(base)) {
      throw new Error(
        `Unknown cast ${JSON.stringify(opts.cast)} (no ${base}.cast in ${tutorialsRoot})`
      );
    }
    wanted = [base];
  }

  const pairs = [];
  for (const lang of locales) {
    if (opts.langs && !opts.langs.has(lang)) continue;
    for (const cast of wanted) {
      const timelinePath = path.join(timelineRoot, lang, `${cast}.json`);
      if (!fs.existsSync(timelinePath)) continue;
      // Precondition carried over from run.sh's original bash enumeration: without the
      // per-locale audio directory there is nothing to mux, and the render would fail.
      if (!fs.existsSync(path.join(tutorialsRoot, 'audio', lang, cast))) continue;

      if (opts.requireProvider) {
        let provider = null;
        try {
          provider = JSON.parse(fs.readFileSync(timelinePath, 'utf-8')).provider ?? null;
        } catch {
          continue; // unparseable timeline is not renderable
        }
        if (provider !== opts.requireProvider) continue;
      }

      if (opts.staleOnly) {
        const mp4 = path.join(videoRoot, lang, `${cast}.mp4`);
        if (fs.existsSync(mp4)) {
          if (fs.statSync(timelinePath).mtimeMs <= fs.statSync(mp4).mtimeMs) continue;
        }
      }
      pairs.push({ cast, lang });
    }
  }
  return { pairs };
}

// ---------------------------------------------------------------------------
// Self-test. Lives here rather than in .ci/scripts/test/gates/ because this session is
// barred from that directory; a shared-harness gate there is a tracked follow-up. Every
// case below is paired with a control that MUST come out empty, so a predicate that
// returned everything, or nothing, fails rather than passes.
// ---------------------------------------------------------------------------
function selftest() {
  const failures = [];
  const check = (name, actual, expected) => {
    const a = JSON.stringify(actual);
    const e = JSON.stringify(expected);
    if (a === e) console.log(`  PASS  ${name}`);
    else {
      console.error(`  FAIL  ${name}\n        expected ${e}\n        got      ${a}`);
      failures.push(name);
    }
  };

  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'render-pairs-selftest-'));
  const tutorials = path.join(root, 'packages/www/public/assets/tutorials');
  const timelines = path.join(root, 'packages/www/src/data/tutorial-timeline');
  const mk = (p) => fs.mkdirSync(p, { recursive: true });

  // --- empty tree must REFUSE (the anti-vacuity control) ---
  let refused = false;
  try {
    listRenderPairs({ root, langs: null, cast: null, staleOnly: false, requireProvider: null });
  } catch (e) {
    refused = /Refusing to run/.test(e.message);
  }
  check('empty tree refuses to run', refused, true);

  // --- build a small real tree ---
  mk(tutorials);
  fs.writeFileSync(path.join(tutorials, 'tutorial-alpha.cast'), '{}\n');
  fs.writeFileSync(path.join(tutorials, 'tutorial-beta.cast'), '{}\n');
  for (const lang of ['en', 'de']) {
    mk(path.join(timelines, lang));
    for (const cast of ['tutorial-alpha', 'tutorial-beta']) {
      mk(path.join(tutorials, 'audio', lang, cast));
      fs.writeFileSync(
        path.join(timelines, lang, `${cast}.json`),
        JSON.stringify({ provider: 'voxcpm2', steps: [] })
      );
    }
  }
  const base = { root, langs: null, cast: null, staleOnly: false, requireProvider: null };
  const names = (o) => listRenderPairs(o).pairs.map((p) => `${p.lang}/${p.cast}`);

  check('lists every pair', names(base), [
    'de/tutorial-alpha',
    'de/tutorial-beta',
    'en/tutorial-alpha',
    'en/tutorial-beta',
  ]);
  check('emission is lang-major', names(base).slice(0, 2), [
    'de/tutorial-alpha',
    'de/tutorial-beta',
  ]);
  check('--lang filters', names({ ...base, langs: new Set(['en']) }), [
    'en/tutorial-alpha',
    'en/tutorial-beta',
  ]);
  check('--cast filters', names({ ...base, cast: 'alpha' }), [
    'de/tutorial-alpha',
    'en/tutorial-alpha',
  ]);

  // --- staleness ---
  check('mp4 missing => stale', names({ ...base, staleOnly: true }).length, 4);

  const videoDir = path.join(tutorials, 'video', 'en');
  mk(videoDir);
  const mp4 = path.join(videoDir, 'tutorial-alpha.mp4');
  fs.writeFileSync(mp4, 'x');
  const tl = path.join(timelines, 'en', 'tutorial-alpha.json');
  // mp4 NEWER than timeline -> must NOT be listed. This is the control that catches a
  // predicate which just returns everything.
  fs.utimesSync(tl, new Date(1000), new Date(1000));
  fs.utimesSync(mp4, new Date(2000), new Date(2000));
  check(
    'mp4 newer than timeline => NOT stale (control)',
    names({ ...base, staleOnly: true }).includes('en/tutorial-alpha'),
    false
  );

  // timeline newer -> listed again
  fs.utimesSync(tl, new Date(3000), new Date(3000));
  check(
    'timeline newer than mp4 => stale again',
    names({ ...base, staleOnly: true }).includes('en/tutorial-alpha'),
    true
  );

  // --- provider gate ---
  fs.writeFileSync(tl, JSON.stringify({ provider: 'qwen3-tts', steps: [] }));
  check(
    'wrong provider => NOT listed (control)',
    names({ ...base, requireProvider: 'voxcpm2' }).includes('en/tutorial-alpha'),
    false
  );

  // --- audio-dir precondition ---
  fs.writeFileSync(tl, JSON.stringify({ provider: 'voxcpm2', steps: [] }));
  fs.rmSync(path.join(tutorials, 'audio', 'en', 'tutorial-alpha'), { recursive: true });
  check(
    'missing audio dir => NOT listed (control)',
    names(base).includes('en/tutorial-alpha'),
    false
  );

  fs.rmSync(root, { recursive: true, force: true });
  if (failures.length) {
    console.error(`\n✗ ${failures.length} self-test failure(s): ${failures.join(', ')}`);
    process.exit(1);
  }
  console.log('\n✓ list-tutorial-render-pairs self-test passed');
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.selftest) return selftest();
  let result;
  try {
    result = listRenderPairs(opts);
  } catch (e) {
    console.error(`✗ ${e.message}`);
    process.exit(1);
  }
  for (const p of result.pairs) process.stdout.write(`${p.cast}\t${p.lang}\n`);
}

main();
