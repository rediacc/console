#!/usr/bin/env node
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { execSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { castDurationSec, markerTimestamps, parseCast } from './lib/cast-splitter.ts';
import {
  addEdgePad,
  addTailPad,
  assembleWithTransitions,
  extractPosterJpg,
  probeDurationSec,
} from './lib/ffmpeg-video.ts';
import { readStoryboard } from './lib/storyboard.ts';
import { loadNarrationLookup, castMarkerKey } from './lib/narration-lookup.ts';
import {
  compileScene,
  computeSceneDurationDry,
  type CastNarratedDebug,
  type DebugCollector,
  type SceneContext,
  type SceneOutput,
} from './lib/scenes/index.ts';
import { browserSceneWillRecord, hostCommandEnv, substituteEnv } from './lib/scenes/browser.ts';
import { createSessionManager } from './lib/scenes/browser-session.ts';
import { emitChaptersVtt, emitSubtitlesVtt, emitWordTimingsJson } from './lib/vtt-emit.ts';

function parseArgs(argv: string[]): {
  cast: string;
  lang: string;
  keep: boolean;
  debug: boolean;
  cacheReuse: boolean;
  cacheRefresh: boolean;
  captionsOnly: boolean;
} {
  const out: Record<string, string> = {};
  let keep = false;
  let debug = false;
  // Browser silent-segment cache: reuse-if-present by default; --refresh forces
  // a live re-record + overwrite; --no-browser-cache disables both.
  let cacheReuse = true;
  let cacheRefresh = false;
  let captionsOnly = false;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--keep-temp') {
      keep = true;
      continue;
    }
    if (a === '--debug') {
      debug = true;
      continue;
    }
    if (a === '--refresh-browser-cache') {
      cacheRefresh = true;
      continue;
    }
    if (a === '--no-browser-cache') {
      cacheReuse = false;
      continue;
    }
    if (a === '--captions-only') {
      captionsOnly = true;
      continue;
    }
    if (a.startsWith('--')) {
      const key = a.slice(2);
      out[key] = argv[++i];
    }
  }
  if (!out.cast || !out.lang) {
    throw new Error(
      'Usage: generate-tutorial-video.ts --cast <name> --lang <code> [--keep-temp] [--debug] [--refresh-browser-cache] [--no-browser-cache] [--captions-only]'
    );
  }
  return {
    cast: out.cast,
    lang: out.lang,
    keep,
    debug,
    cacheReuse,
    cacheRefresh,
    captionsOnly,
  };
}

async function main(): Promise<void> {
  const {
    cast: tutorial,
    lang,
    keep,
    debug,
    cacheReuse,
    cacheRefresh,
    captionsOnly,
  } = parseArgs(process.argv.slice(2));
  const scriptDir = path.dirname(fileURLToPath(import.meta.url));
  const wwwRoot = path.resolve(scriptDir, '..');
  const wwwPublicRoot = path.join(wwwRoot, 'public');
  // Tracked artifact dir: browser silent segments are expensive to record
  // (live lab/Playwright) and tiny to store, so they're committed alongside
  // the other tutorial assets and reused across languages, machines, and CI.
  const browserCacheDir = path.join(wwwPublicRoot, 'assets', 'tutorials', 'browser-segments');

  const castPath = path.join(wwwPublicRoot, 'assets', 'tutorials', `${tutorial}.cast`);
  const timelinePath = path.join(
    wwwRoot,
    'src',
    'data',
    'tutorial-timeline',
    lang,
    `${tutorial}.json`
  );
  const storyboardPath = path.join(
    wwwRoot,
    'src',
    'data',
    'tutorial-storyboard',
    `${tutorial}.json`
  );
  const outDir = path.join(wwwPublicRoot, 'assets', 'tutorials', 'video', lang);
  const outPath = path.join(outDir, `${tutorial}.mp4`);
  mkdirSync(outDir, { recursive: true });

  const storyboard = readStoryboard(storyboardPath);
  const parsedCast = parseCast(castPath);
  const markers = markerTimestamps(parsedCast);
  const castEnd = castDurationSec(parsedCast);
  const narrations = loadNarrationLookup(timelinePath, wwwPublicRoot);

  // Transcripts hold all user-visible card text (title, chapters, cardLabel).
  // Per-lang first, English second as fallback for not-yet-translated locales.
  const transcriptPath = path.join(
    wwwRoot,
    'src',
    'data',
    'tutorial-transcripts',
    lang,
    `${tutorial}.json`
  );
  const transcriptEnPath = path.join(
    wwwRoot,
    'src',
    'data',
    'tutorial-transcripts',
    'en',
    `${tutorial}.json`
  );
  const transcript = existsSync(transcriptPath)
    ? (JSON.parse(readFileSync(transcriptPath, 'utf8')) as Record<string, unknown>)
    : null;
  const transcriptEn =
    lang === 'en'
      ? transcript
      : existsSync(transcriptEnPath)
        ? (JSON.parse(readFileSync(transcriptEnPath, 'utf8')) as Record<string, unknown>)
        : null;

  console.log(
    `[video] tutorial=${tutorial} lang=${lang} scenes=${storyboard.scenes.length} markers=${markers.length} castDuration=${castEnd.toFixed(2)}s${debug ? ' [debug]' : ''}`
  );

  const tmp = mkdtempSync(path.join(tmpdir(), 'tutorial-video-'));
  console.log(`[video] tmp dir: ${tmp}`);

  // Storyboard-level environment hooks: setupCommand prepares live resources
  // browser scenes depend on (demo forks, tunnels, stacks); teardownCommand
  // is guaranteed below even when compilation throws. Both run from the
  // monorepo root — storyboard commands reference repo-root-relative paths
  // (e.g. .ci/tutorials/lib/…) regardless of where the generator is invoked.
  //
  // Skip the lab hooks entirely when every browser scene reuses a cached
  // silent segment — a fully-cached locale render needs no live resources.
  const browserCache = { dir: browserCacheDir, reuse: cacheReuse, refresh: cacheRefresh };
  const needsLab = storyboard.scenes.some(
    (s) =>
      (s.type === 'browser' || s.type === 'browser-split') &&
      browserSceneWillRecord(storyboard, tutorial, browserCache, s)
  );
  const repoRoot = path.resolve(wwwRoot, '..', '..');
  if (storyboard.setupCommand && needsLab) {
    const setup = substituteEnv(storyboard.setupCommand);
    console.log(`[video] running setupCommand: ${setup}`);
    execSync(setup, { stdio: 'inherit', shell: '/bin/bash', cwd: repoRoot, env: hostCommandEnv() });
  } else if (storyboard.setupCommand) {
    console.log('[video] all browser scenes cached → skipping setupCommand (no lab)');
  }

  // The cast-narrated timing collector is always active — the VTT emitter
  // needs it to compute absolute after-narration start times. The --debug
  // flag only controls whether the JSON sidecar + per-scene last-frame PNGs
  // are written to disk.
  const debugFramesDir = debug ? path.join(outDir, `${tutorial}.debug-frames`) : '';
  if (debug) mkdirSync(debugFramesDir, { recursive: true });
  const debugCollector: DebugCollector = {
    framesDir: debugFramesDir,
    castNarrated: [],
    recordCastNarrated(entry: CastNarratedDebug) {
      this.castNarrated.push(entry);
    },
  };

  const sessions = createSessionManager({
    tmp,
    storyboard,
    debugFramesDir: debug ? debugFramesDir : undefined,
  });
  try {
    const chunks: string[] = [];
    const ctx: SceneContext = {
      tmp,
      wwwPublicRoot,
      tutorial,
      lang,
      storyboard,
      cast: parsedCast,
      markers,
      castEnd,
      narrations,
      chunks,
      sessions,
      browserCache,
      castMarkerToNarrationId: (idx: number) => castMarkerKey(idx, timelinePath),
      debug: debugCollector,
      transcript,
      transcriptEn,
    };

    // --captions-only: recover each scene's duration analytically (no
    // ffmpeg, no live sessions) instead of actually rendering it. Falls
    // back to a full render (by throwing, so the caller re-invokes without
    // the flag) when any scene's timing genuinely cannot be known without
    // one -- currently only a browser/browser-split scene with a cold
    // silent-segment cache. See scenes/index.ts::computeSceneDurationDry.
    const sceneAbsStart: Record<string, number> = {};
    const sceneAbsEnd: Record<string, number> = {};
    let finalDuration: number | undefined;
    let cursorSec = 0;
    const TAIL_PAD_SEC = 0.8;
    const FADE_SEC = 0.3;
    const isBrowserScene = (t: string) => t === 'browser' || t === 'browser-split';
    const fadeAfter = storyboard.scenes
      .slice(0, -1)
      .map((s, i) => isBrowserScene(s.type) || isBrowserScene(storyboard.scenes[i + 1].type));

    if (captionsOnly) {
      console.log(`[video] --captions-only: recovering scene timing without rendering`);
      for (let i = 0; i < storyboard.scenes.length; i++) {
        const scene = storyboard.scenes[i];
        const isLast = i === storyboard.scenes.length - 1;
        const dry = computeSceneDurationDry(scene, ctx);
        if (dry === null) {
          throw new Error(
            `--captions-only: scene ${scene.id} (${scene.type}) needs a live render ` +
              `(cold browser-segment cache) -- re-run without --captions-only for this tutorial`
          );
        }
        if (dry.castNarratedDebug) debugCollector.recordCastNarrated(dry.castNarratedDebug);
        // Mirror the real render's padding/fade accounting exactly so
        // sceneAbsStart/End land on the same absolute timeline a full
        // compile would have produced -- TAIL_PAD_SEC is added by
        // addTailPad to every non-last chunk before assembly, and each
        // crossfade overlaps the boundary by FADE_SEC.
        const dur = dry.durationSec + (isLast ? 0 : TAIL_PAD_SEC);
        sceneAbsStart[scene.id] = cursorSec;
        sceneAbsEnd[scene.id] = cursorSec + dur;
        cursorSec += dur;
        if (!isLast && fadeAfter[i]) cursorSec -= FADE_SEC;
      }
      console.log(`[video] recovered timing for ${storyboard.scenes.length} scenes, no encode`);
    } else {
      // Phase 1 — live execution in storyboard order. Eager scenes (title,
      // slide, cast*) compile to finished chunks immediately; browser scenes
      // run their live interactions against (possibly shared) sessions and
      // return deferred producers — their footage is a slice of a session
      // recording that only exists once the session closes.
      const outputs: SceneOutput[] = [];
      for (let i = 0; i < storyboard.scenes.length; i++) {
        const scene = storyboard.scenes[i];
        console.log(`[video] compiling scene ${scene.id} (${scene.type})...`);
        sessions.beginScene(i);
        const out = await compileScene(scene, ctx);
        outputs.push(out);
        // chunks mirrors compiled output for compileCastFreeze's last-frame
        // peek; deferred scenes leave a sentinel (guarded in cast.ts).
        chunks.push(typeof out === 'string' ? out : `__deferred__:${scene.id}`);
        await sessions.closeFinished(i);
      }
      await sessions.closeAll();

      // Phase 2 — materialize deferred chunks (cut + mux session slices),
      // then pad and assemble exactly as before.
      const finalChunks: string[] = [];
      for (let i = 0; i < storyboard.scenes.length; i++) {
        const scene = storyboard.scenes[i];
        const out = outputs[i];
        const chunk = typeof out === 'string' ? out : out.deferred();
        const isLast = i === storyboard.scenes.length - 1;
        let pushed: string;
        if (isLast) {
          pushed = chunk;
        } else {
          const padded = path.join(tmp, `${scene.id}.padded.mp4`);
          addTailPad(chunk, padded, TAIL_PAD_SEC);
          pushed = padded;
        }
        finalChunks.push(pushed);
        const dur = probeDurationSec(pushed);
        sceneAbsStart[scene.id] = cursorSec;
        sceneAbsEnd[scene.id] = cursorSec + dur;
        cursorSec += dur;
        if (!isLast && fadeAfter[i]) cursorSec -= FADE_SEC;
      }

      const concatOut = path.join(tmp, 'concat.mp4');
      console.log(`[video] assembling ${finalChunks.length} chunks → ${concatOut}`);
      assembleWithTransitions(finalChunks, fadeAfter, concatOut, tmp, FADE_SEC);

      // Add 1s of silent leading + trailing padding so the video doesn't
      // start/end abruptly. Held first/last frames mean the eye has a beat to
      // settle before audio begins and after it ends.
      console.log(`[video] adding 1s edge padding → ${outPath}`);
      addEdgePad(concatOut, outPath, 1.0, 1.0);

      finalDuration = probeDurationSec(outPath);
      console.log(`[video] done. duration=${finalDuration.toFixed(2)}s → ${outPath}`);
    }

    const EDGE_LEAD = 1.0;
    const sceneTimingAbs: Record<string, { start: number; end: number }> = {};
    for (const s of storyboard.scenes) {
      sceneTimingAbs[s.id] = {
        start: (sceneAbsStart[s.id] ?? 0) + EDGE_LEAD,
        end: (sceneAbsEnd[s.id] ?? 0) + EDGE_LEAD,
      };
    }
    const castTimingBySceneId = new Map<string, CastNarratedDebug>();
    for (const entry of debugCollector.castNarrated) {
      castTimingBySceneId.set(entry.sceneId, entry);
    }

    // Emit subtitles + chapters VTT sidecars next to the mp4.
    const timeline = JSON.parse(readFileSync(timelinePath, 'utf8'));
    const subtitlesPath = path.join(outDir, `${tutorial}.${lang}.vtt`);
    const chaptersPath = path.join(outDir, `${tutorial}.${lang}.chapters.vtt`);
    const wordsJsonPath = path.join(outDir, `${tutorial}.${lang}.words.json`);
    const collectArgs = {
      storyboard,
      timeline,
      transcript,
      sceneTiming: sceneTimingAbs,
      castTimingBySceneId,
    };
    emitSubtitlesVtt({ outPath: subtitlesPath, ...collectArgs });
    emitChaptersVtt({
      outPath: chaptersPath,
      storyboard,
      sceneTiming: sceneTimingAbs,
      transcript,
      transcriptEn,
    });
    emitWordTimingsJson({ outPath: wordsJsonPath, ...collectArgs });
    console.log(`[video] subtitles → ${subtitlesPath}`);
    console.log(`[video] chapters  → ${chaptersPath}`);
    console.log(`[video] words     → ${wordsJsonPath}`);

    // Poster: extract a frame from the first cast-narrated scene (so the
    // poster shows a terminal, not the title card); fall back to 1s in.
    // Skipped in --captions-only: the mp4 (and therefore its poster) is
    // unchanged, nothing to re-extract.
    if (!captionsOnly) {
      const firstCastNarrated = storyboard.scenes.find((s) => s.type === 'cast-narrated');
      const posterAtSec = firstCastNarrated
        ? (sceneTimingAbs[firstCastNarrated.id]?.start ?? 1.0) + 0.5
        : 1.0;
      const posterPath = path.join(outDir, `${tutorial}.${lang}.poster.jpg`);
      extractPosterJpg(outPath, posterAtSec, posterPath);
      console.log(`[video] poster    → ${posterPath} (at ${posterAtSec.toFixed(2)}s)`);
    }

    if (debug && !captionsOnly) {
      for (const entry of debugCollector.castNarrated) {
        const dstPng = path.join(
          debugFramesDir,
          `${entry.sceneId.replace(/[:<>"|?*]/g, '-')}.lastframe.png`
        );
        try {
          copyFileSync(entry.lastFramePngSrc, dstPng);
        } catch {
          /* may not exist */
        }
      }
      const sidecar = {
        tutorial,
        lang,
        finalDurationSec: finalDuration,
        edgeLeadSec: EDGE_LEAD,
        scenes: storyboard.scenes.map((s) => ({
          id: s.id,
          type: s.type,
          mp4StartSec: sceneTimingAbs[s.id].start,
          mp4EndSec: sceneTimingAbs[s.id].end,
        })),
        castNarrated: debugCollector.castNarrated.map((d) => ({
          ...d,
          lastFramePngSrc: undefined,
          lastFramePng: path.join(
            debugFramesDir,
            `${d.sceneId.replace(/[:<>"|?*]/g, '-')}.lastframe.png`
          ),
          mp4StartSec: sceneTimingAbs[d.sceneId].start,
          mp4EndSec: sceneTimingAbs[d.sceneId].end,
        })),
        sessions: sessions.debugInfo(),
      };
      const sidecarPath = path.join(outDir, `${tutorial}.debug.json`);
      writeFileSync(sidecarPath, JSON.stringify(sidecar, null, 2));
      console.log(`[video] debug sidecar → ${sidecarPath}`);
      console.log(`[video] debug frames  → ${debugFramesDir}`);
    }
  } finally {
    // Sessions hold chromium instances and tunnel processes pointed at
    // resources teardownCommand may destroy — release them first.
    await sessions.closeAll().catch((err) => {
      console.error(`[video] session cleanup failed: ${String(err)}`);
    });
    if (storyboard.teardownCommand && needsLab) {
      const teardown = substituteEnv(storyboard.teardownCommand);
      console.log(`[video] running teardownCommand: ${teardown}`);
      try {
        execSync(teardown, {
          stdio: 'inherit',
          shell: '/bin/bash',
          cwd: repoRoot,
          env: hostCommandEnv(),
        });
      } catch (teardownErr) {
        console.error(`[video] teardownCommand failed: ${String(teardownErr)}`);
      }
    }
    if (!keep) rmSync(tmp, { recursive: true, force: true });
  }
}

main().catch((err) => {
  console.error(err instanceof Error ? (err.stack ?? err.message) : err);
  process.exit(1);
});
