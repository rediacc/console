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
import { tmpdir } from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import { castDurationSec, markerTimestamps, parseCast } from './lib/cast-splitter.ts';
import {
  addEdgePad,
  addTailPad,
  concatMp4,
  extractPosterJpg,
  probeDurationSec,
} from './lib/ffmpeg-video.ts';
import { readStoryboard } from './lib/storyboard.ts';
import { loadNarrationLookup, castMarkerKey } from './lib/narration-lookup.ts';
import {
  compileScene,
  type CastNarratedDebug,
  type DebugCollector,
  type SceneContext,
} from './lib/scenes/index.ts';
import { emitChaptersVtt, emitSubtitlesVtt, emitWordTimingsJson } from './lib/vtt-emit.ts';

function parseArgs(argv: string[]): { cast: string; lang: string; keep: boolean; debug: boolean } {
  const out: Record<string, string> = {};
  let keep = false;
  let debug = false;
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
    if (a.startsWith('--')) {
      const key = a.slice(2);
      out[key] = argv[++i];
    }
  }
  if (!out.cast || !out.lang) {
    throw new Error(
      'Usage: generate-tutorial-video.ts --cast <name> --lang <code> [--keep-temp] [--debug]'
    );
  }
  return { cast: out.cast, lang: out.lang, keep, debug };
}

async function main(): Promise<void> {
  const { cast: tutorial, lang, keep, debug } = parseArgs(process.argv.slice(2));
  const scriptDir = path.dirname(fileURLToPath(import.meta.url));
  const wwwRoot = path.resolve(scriptDir, '..');
  const wwwPublicRoot = path.join(wwwRoot, 'public');

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
      castMarkerToNarrationId: (idx: number) => castMarkerKey(idx, timelinePath),
      debug: debugCollector,
      transcript,
      transcriptEn,
    };

    const TAIL_PAD_SEC = 0.8;
    // Track each scene's contribution to the pre-edge-pad timeline. The VTT
    // emitter needs absolute mp4 timestamps for chapter cues + subtitle cues
    // for non-cast-narrated scenes.
    const sceneAbsStart: Record<string, number> = {};
    const sceneAbsEnd: Record<string, number> = {};
    let cursorSec = 0;
    for (let i = 0; i < storyboard.scenes.length; i++) {
      const scene = storyboard.scenes[i];
      console.log(`[video] compiling scene ${scene.id} (${scene.type})...`);
      const chunk = await compileScene(scene, ctx);
      const isLast = i === storyboard.scenes.length - 1;
      let pushed: string;
      if (isLast) {
        pushed = chunk;
      } else {
        const padded = path.join(tmp, `${scene.id}.padded.mp4`);
        addTailPad(chunk, padded, TAIL_PAD_SEC);
        pushed = padded;
      }
      chunks.push(pushed);
      const dur = probeDurationSec(pushed);
      sceneAbsStart[scene.id] = cursorSec;
      sceneAbsEnd[scene.id] = cursorSec + dur;
      cursorSec += dur;
    }

    const concatOut = path.join(tmp, 'concat.mp4');
    console.log(`[video] concatenating ${chunks.length} chunks → ${concatOut}`);
    concatMp4(chunks, concatOut, path.join(tmp, 'concat.txt'));

    // Add 1s of silent leading + trailing padding so the video doesn't
    // start/end abruptly. Held first/last frames mean the eye has a beat to
    // settle before audio begins and after it ends.
    console.log(`[video] adding 1s edge padding → ${outPath}`);
    addEdgePad(concatOut, outPath, 1.0, 1.0);

    const finalDuration = probeDurationSec(outPath);
    console.log(`[video] done. duration=${finalDuration.toFixed(2)}s → ${outPath}`);

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
    const firstCastNarrated = storyboard.scenes.find((s) => s.type === 'cast-narrated');
    const posterAtSec = firstCastNarrated
      ? (sceneTimingAbs[firstCastNarrated.id]?.start ?? 1.0) + 0.5
      : 1.0;
    const posterPath = path.join(outDir, `${tutorial}.${lang}.poster.jpg`);
    extractPosterJpg(outPath, posterAtSec, posterPath);
    console.log(`[video] poster    → ${posterPath} (at ${posterAtSec.toFixed(2)}s)`);

    if (debug) {
      for (const entry of debugCollector.castNarrated) {
        const dstPng = path.join(debugFramesDir, `${entry.sceneId}.lastframe.png`);
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
          lastFramePng: path.join(debugFramesDir, `${d.sceneId}.lastframe.png`),
          mp4StartSec: sceneTimingAbs[d.sceneId].start,
          mp4EndSec: sceneTimingAbs[d.sceneId].end,
        })),
      };
      const sidecarPath = path.join(outDir, `${tutorial}.debug.json`);
      writeFileSync(sidecarPath, JSON.stringify(sidecar, null, 2));
      console.log(`[video] debug sidecar → ${sidecarPath}`);
      console.log(`[video] debug frames  → ${debugFramesDir}`);
    }
  } finally {
    if (!keep) rmSync(tmp, { recursive: true, force: true });
  }
}

main().catch((err) => {
  console.error(err instanceof Error ? (err.stack ?? err.message) : err);
  process.exit(1);
});
