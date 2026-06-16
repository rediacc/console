import path from 'node:path';
import type { CastScene, CastFreezeScene, CastNarratedScene } from '../storyboard.ts';
import { resolveCastEndpoint } from '../storyboard.ts';
import {
  countDisplayRows,
  countOutputLines,
  findLastPromptTime,
  lastOutputTime,
  writeRestreamedSegment,
  writeSegments,
} from '../cast-splitter.ts';
import {
  addSilentAudio,
  concatMp4,
  cropFramePng,
  encodeAnimMp4,
  encodeAnimMp4Raw,
  extractLastFrame,
  makeFreezeMp4,
  makeScrollPanSilent,
  makeSilentFreezeMp4,
  muxNarratedSegment,
  probeDurationSec,
  renderCastToGif,
  trimMp4Duration,
  videoDimensions,
} from '../ffmpeg-video.ts';
import type { SceneContext } from './index.ts';
import { renderStepCard } from './slide.ts';

/**
 * Dwell time for the per-step "you are here" card prepended to every
 * cast-narrated scene. The card replaces the previous 0.5s held terminal
 * first frame. Exported so the VTT/subtitle emitter can use the same value
 * when computing the main-narration audio start within each scene.
 */
export const STEP_CARD_DURATION_SEC = 2.5;

export function compileCast(scene: CastScene, ctx: SceneContext): string {
  const startSec = resolveCastEndpoint(scene.from, ctx.markers, ctx.castEnd);
  const endSec = resolveCastEndpoint(scene.to, ctx.markers, ctx.castEnd);
  if (endSec <= startSec)
    throw new Error(`Cast scene ${scene.id}: end ${endSec} <= start ${startSec}`);

  const subCastPaths = writeSegments(ctx.cast, [{ startSec, endSec }], ctx.tmp, scene.id);
  const gif = path.join(ctx.tmp, `${scene.id}.gif`);
  const silentMp4 = path.join(ctx.tmp, `${scene.id}.silent.mp4`);
  const mp4 = path.join(ctx.tmp, `${scene.id}.mp4`);
  renderCastToGif(subCastPaths[0], gif, ctx.cast.header.width, ctx.cast.header.height);
  encodeAnimMp4(gif, silentMp4);
  addSilentAudio(silentMp4, mp4);
  return mp4;
}

export function compileCastNarrated(scene: CastNarratedScene, ctx: SceneContext): string {
  const startSec = ctx.markers[scene.markerIndex];
  const rawEndSec =
    scene.markerIndex + 1 < ctx.markers.length ? ctx.markers[scene.markerIndex + 1] : ctx.castEnd;

  const minSliceDur = 1.0;
  const trim = scene.afterTrimSec ?? 2.5;

  // The recording prints a fresh empty prompt after each command finishes (see
  // tutorial-helpers.sh::run_cmd). That prompt is the "command done" cue.
  //
  // For natural pacing, the main narration must play while the cast types +
  // executes + outputs (no empty prompt visible yet), and the after-narration
  // must play over a freeze that DOES show the empty prompt. So we split the
  // cast slice at the empty-prompt point.
  const promptTime = findLastPromptTime(ctx.cast, startSec + 0.2, rawEndSec);

  // mainEndSec: where the main cast playback stops. Just before the prompt
  // prints (so empty prompt isn't visible during main narration).
  // frameEndSec: where we extract the after-narration freeze frame. After the
  // prompt prints, so the freeze shows "output + empty prompt".
  let mainEndSec =
    promptTime !== null
      ? Math.max(startSec + minSliceDur, promptTime - 0.15)
      : Math.max(startSec + minSliceDur, rawEndSec - trim);
  // The output dump and the empty "command done" prompt print within ms of each
  // other, so `promptTime - 0.15` can cut off BEFORE an instant dump (e.g. `cat`
  // of a file), leaving the typed command over an empty screen for the whole
  // main narration. Extend the cutoff to include the last output before the
  // prompt so the command's output is actually visible during the narration.
  if (promptTime !== null) {
    const lastOut = lastOutputTime(ctx.cast, startSec, promptTime);
    // +0.4s margin so the dump frame fully renders (the dump often lands on the
    // exact cutoff and frame-rounding would otherwise drop it) and is then held
    // under the rest of the narration.
    if (lastOut !== null && lastOut + 0.4 > mainEndSec) {
      mainEndSec = Math.min(rawEndSec, Math.max(mainEndSec, lastOut + 0.4));
    }
  }
  const frameEndSec = promptTime !== null ? Math.min(rawEndSec, promptTime + 0.5) : mainEndSec;

  if (mainEndSec <= startSec)
    throw new Error(`cast-narrated ${scene.id}: empty slice [${startSec}, ${mainEndSec}]`);

  // Render the FULL slice (up through the empty prompt) once; we'll trim
  // the front portion for main playback and extract the last frame for after.
  const subCastPaths = writeSegments(
    ctx.cast,
    [{ startSec, endSec: frameEndSec }],
    ctx.tmp,
    scene.id
  );
  const gif = path.join(ctx.tmp, `${scene.id}.gif`);
  const animSilentFull = path.join(ctx.tmp, `${scene.id}.silent-full.mp4`);
  // Hold the last frame for 1s past the final cast event. extractLastFrame
  // uses `-sseof -0.1` which can otherwise land BEFORE the final output +
  // empty-prompt events render — they often cluster within ~50ms of slice
  // end. The held-frame window gives the seek a safe target. animSilentMain
  // is trimmed to mainAnimDur regardless, so the hold doesn't leak into the
  // narrated animation.
  renderCastToGif(subCastPaths[0], gif, ctx.cast.header.width, ctx.cast.header.height, 1.0);
  encodeAnimMp4(gif, animSilentFull);

  // Main mp4: trim the full anim to end at mainEndSec (= command output, no
  // empty prompt yet), then mux with main narration audio.
  const mainAnimDur = Math.max(0.05, mainEndSec - startSec);
  const animSilentMain = path.join(ctx.tmp, `${scene.id}.silent-main.mp4`);
  trimMp4Duration(animSilentFull, animSilentMain, mainAnimDur);

  const narrationKey = scene.narrationKey ?? ctx.castMarkerToNarrationId(scene.markerIndex);
  const narration = ctx.narrations.get(narrationKey);
  const audioPath = ctx.narrations.resolvePath(narration.audioSrc);
  const audioDur = narration.audioDurationSec ?? 0;
  const hold = scene.holdSec ?? 0.6;
  const tailExtra = Math.max(0, audioDur - (hold + mainAnimDur));

  // Tall-output detection. If the command output is taller than the recorded
  // terminal it scrolled off the top, so a static freeze shows only the tail.
  // We re-render the slice in a TALL terminal (nothing scrolls in-terminal) and
  // pan a recorded-height window down it. Computed up front because WHEN we pan
  // depends on it.
  const termRows = ctx.cast.header.height;
  // Wrapped display rows (a long unbroken line, like an inline key in a printed
  // config, still consumes multiple rows) decide whether output scrolled off.
  const displayRows = countDisplayRows(ctx.cast, startSec, frameEndSec, ctx.cast.header.width);
  const needRows = displayRows + 1;
  const isTall = needRows > termRows;
  // The main narration usually runs far longer than the typing+output animation,
  // leaving `tailExtra` seconds of dead freeze on the scrolled-off tail. When
  // that window is substantial we reveal the output by panning slowly across it
  // during the main narration, instead of freezing the tail and cramming the
  // whole reveal into the short after-narration (jarring: ~16s static then a
  // rushed scroll). Below the threshold (e.g. the animation already outruns the
  // main narration) we fall back to the after-narration scroll.
  const MAIN_PAN_MIN_FREEZE_SEC = 2.5;
  const useMainPan = isTall && tailExtra >= MAIN_PAN_MIN_FREEZE_SEC;

  // Tall-frame assets, built once and reused by the main pan and/or the
  // after-narration scroll. `winH` is the recorded-terminal-height window we
  // crop and pan; `maxY` is its lowest position (bottom of the output).
  let tallW = 0;
  let winH = 0;
  let maxY = 0;
  let tallPng = '';
  let tallRaw = '';
  if (isTall) {
    const tallGif = path.join(ctx.tmp, `${scene.id}.tall.gif`);
    tallRaw = path.join(ctx.tmp, `${scene.id}.tall.mp4`);
    tallPng = path.join(ctx.tmp, `${scene.id}.tall.png`);
    renderCastToGif(subCastPaths[0], tallGif, ctx.cast.header.width, needRows, 1.0);
    encodeAnimMp4Raw(tallGif, tallRaw);
    extractLastFrame(tallRaw, tallPng);
    const dims = videoDimensions(tallPng);
    tallW = dims.width;
    winH = Math.max(2, Math.round((dims.height * termRows) / needRows));
    maxY = Math.max(0, dims.height - winH);
  }

  const mainCore = path.join(ctx.tmp, `${scene.id}.main-core.mp4`);
  // Tall output that dumps as an instant burst (a deploy log printing dozens of
  // lines in milliseconds) with no freeze window to pan: re-time the slice so it
  // streams in at a readable cadence under the main narration instead of a flash.
  const useBurstStream = isTall && !useMainPan;
  if (useMainPan) {
    console.log(
      `[video] scroll-reveal ${scene.id}: ${displayRows} rows > ${termRows} → panning during main narration (${tailExtra.toFixed(1)}s window)`
    );
    // Silent visual on the tall canvas: hold the top through typing + output +
    // a short read beat, then pan to the bottom, holding the bottom for a beat
    // before the main narration ends. muxNarratedSegment then lays the main
    // audio over it with the same startHold and total length as the static path
    // (= audioDur), so scene duration and subtitle timing are unchanged.
    const panVisual = path.join(ctx.tmp, `${scene.id}.main-pan.mp4`);
    const panVisualDur = mainAnimDur + tailExtra; // = audioDur - hold
    const readBeat = Math.min(1.2, Math.max(0.6, tailExtra * 0.12));
    const holdBottom = Math.min(1.5, Math.max(0.6, tailExtra * 0.18));
    const panStart = mainAnimDur + readBeat;
    const panDur = Math.max(0.5, panVisualDur - panStart - holdBottom);
    makeScrollPanSilent(tallRaw, tallW, winH, maxY, panVisualDur, panStart, panDur, panVisual);
    muxNarratedSegment(panVisual, audioPath, mainCore, { startHoldSec: hold, endHoldSec: 0 });
  } else if (useBurstStream) {
    // Re-time the slice so the log streams at a steady cadence, render it at the
    // recorded terminal height (the terminal auto-scrolls as lines arrive, so
    // the viewer reads each new line at the bottom), then lay the main narration
    // over it. If the stream is shorter than the narration, hold its tail to
    // fill (endHold); if longer, it keeps streaming silently and the tail is
    // held by the after-narration. The final frame is identical to the static
    // render, so the after-narration hold-tail path needs no change.
    const restreamed = path.join(ctx.tmp, `${scene.id}.restream.cast`);
    const lineCadenceSec = 0.1;
    const streamDur = writeRestreamedSegment(subCastPaths[0], restreamed, {
      lineCadenceSec,
      maxGapSec: 0.4,
    });
    const streamGif = path.join(ctx.tmp, `${scene.id}.stream.gif`);
    const streamAnim = path.join(ctx.tmp, `${scene.id}.stream.mp4`);
    renderCastToGif(restreamed, streamGif, ctx.cast.header.width, termRows, 0);
    encodeAnimMp4(streamGif, streamAnim);
    const endHold = Math.max(0, audioDur - hold - streamDur);
    console.log(
      `[video] burst-stream ${scene.id}: ${displayRows} rows → re-timed log to ${streamDur.toFixed(1)}s @ ${lineCadenceSec}s/line (endHold ${endHold.toFixed(1)}s)`
    );
    muxNarratedSegment(streamAnim, audioPath, mainCore, {
      startHoldSec: hold,
      endHoldSec: endHold,
    });
  } else {
    muxNarratedSegment(animSilentMain, audioPath, mainCore, {
      startHoldSec: hold,
      endHoldSec: tailExtra,
    });
  }

  // Prepend a "you are here" step card: a silent variant of the title card
  // that lists every cast-narrated step with this scene's row at full opacity
  // and the others dimmed. Re-asserts navigation context at every step.
  // Replaces the previous 0.5s held-terminal-first-frame prePause.
  const castNarratedScenes = ctx.storyboard.scenes.filter((s) => s.type === 'cast-narrated');
  const activeIndex = castNarratedScenes.indexOf(scene) + 1;
  const stepCardMp4 = renderStepCard(
    ctx,
    activeIndex,
    STEP_CARD_DURATION_SEC,
    `${scene.id}.stepcard`
  );
  const out = path.join(ctx.tmp, `${scene.id}.mp4`);
  concatMp4([stepCardMp4, mainCore], out, path.join(ctx.tmp, `${scene.id}.pre.concat.txt`));

  // Append post-command narration if authored: extract the empty-prompt frame
  // (last frame of full render, where the empty prompt is visible), freeze
  // it, and play the after-narration over it. Empty prompt appears exactly
  // when after-narration begins — matches "command done, ready for next."
  const stepId = ctx.castMarkerToNarrationId(scene.markerIndex);
  const afterAudio = ctx.narrations.getAfter(stepId);
  if (!afterAudio) {
    if (ctx.debug) {
      const lastFrameNoAfter = path.join(ctx.tmp, `${scene.id}.after.png`);
      extractLastFrame(animSilentFull, lastFrameNoAfter);
      ctx.debug.recordCastNarrated({
        sceneId: scene.id,
        markerIndex: scene.markerIndex,
        startSec,
        rawEndSec,
        promptTime,
        mainEndSec,
        frameEndSec,
        mainAnimDur,
        readPauseSec: 0,
        mainAudioDurSec: audioDur,
        afterAudioDurSec: null,
        lastFramePngSrc: lastFrameNoAfter,
      });
    }
    return out;
  }

  const lastFrame = path.join(ctx.tmp, `${scene.id}.after.png`);
  const afterMp4 = path.join(ctx.tmp, `${scene.id}.after.mp4`);
  const finalMp4 = path.join(ctx.tmp, `${scene.id}.final.mp4`);
  const afterAudioPath = ctx.narrations.resolvePath(afterAudio.audioSrc);
  const afterAudioDur = afterAudio.audioDurationSec ?? 0;
  extractLastFrame(animSilentFull, lastFrame);
  let readPauseSec = 0;

  if (useMainPan) {
    // The full output was already revealed by the main-narration pan; the
    // after-narration holds the bottom of the tall frame (where the pan ended),
    // so there is no jump between the main and after segments.
    const bottomPng = path.join(ctx.tmp, `${scene.id}.tall-bottom.png`);
    cropFramePng(tallPng, tallW, winH, maxY, bottomPng);
    makeFreezeMp4(bottomPng, afterAudioPath, afterAudioDur, afterMp4);
    concatMp4([out, afterMp4], finalMp4, path.join(ctx.tmp, `${scene.id}.after.concat.txt`));
  } else if (isTall) {
    // Tall output with no substantial main freeze window: the typing+output
    // animation is roughly as long as (or longer than) the main narration, so
    // the output already streamed in line-by-line (terminal auto-scroll) during
    // playback. There is no calm window to re-scroll it — a top-to-bottom pan
    // crammed into the short after-narration is fast and jarring, and for the
    // logs this case typically holds (e.g. a deploy log) the meaningful endpoint
    // is the final success tail, which the after-narration is wrapping up. So we
    // hold the frame the animation ended on (the tail) instead of re-scrolling:
    // continuous (no jump) and calm.
    console.log(
      `[video] tall ${scene.id}: ${displayRows} display rows > ${termRows}, no freeze window → holding tail under after-narration`
    );
    makeFreezeMp4(lastFrame, afterAudioPath, afterAudioDur, afterMp4);
    concatMp4([out, afterMp4], finalMp4, path.join(ctx.tmp, `${scene.id}.after.concat.txt`));
  } else {
    // Output fits: hold a reading pause then freeze the full frame under the
    // after-narration. ~250ms per output line, clamped to [0.8s, 3.0s].
    const pauseMp4 = path.join(ctx.tmp, `${scene.id}.pause.mp4`);
    const outputLines = countOutputLines(ctx.cast, startSec, mainEndSec);
    readPauseSec = Math.min(3.0, Math.max(0.8, outputLines * 0.25));
    makeSilentFreezeMp4(lastFrame, readPauseSec, pauseMp4);
    makeFreezeMp4(lastFrame, afterAudioPath, afterAudioDur, afterMp4);
    concatMp4(
      [out, pauseMp4, afterMp4],
      finalMp4,
      path.join(ctx.tmp, `${scene.id}.after.concat.txt`)
    );
  }

  if (ctx.debug) {
    ctx.debug.recordCastNarrated({
      sceneId: scene.id,
      markerIndex: scene.markerIndex,
      startSec,
      rawEndSec,
      promptTime,
      mainEndSec,
      frameEndSec,
      mainAnimDur,
      readPauseSec,
      mainAudioDurSec: audioDur,
      afterAudioDurSec: afterAudio.audioDurationSec ?? null,
      lastFramePngSrc: lastFrame,
    });
  }

  return finalMp4;
}

export function compileCastFreeze(scene: CastFreezeScene, ctx: SceneContext): string {
  const prevAnimSeg = ctx.chunks[ctx.chunks.length - 1];
  if (!prevAnimSeg)
    throw new Error(`cast-freeze ${scene.id}: no preceding scene to extract last frame from`);
  if (prevAnimSeg.startsWith('__deferred__')) {
    throw new Error(
      `cast-freeze ${scene.id}: cannot directly follow a browser scene — its frame is not available until sessions close`
    );
  }
  const png = path.join(ctx.tmp, `${scene.id}.png`);
  const mp4 = path.join(ctx.tmp, `${scene.id}.mp4`);
  extractLastFrame(prevAnimSeg, png);
  const narrationId = ctx.castMarkerToNarrationId(scene.markerIndex);
  const narration = ctx.narrations.get(narrationId);
  const audioPath = ctx.narrations.resolvePath(narration.audioSrc);
  const duration = narration.audioDurationSec ?? 0;
  makeFreezeMp4(png, audioPath, duration, mp4);
  return mp4;
}
