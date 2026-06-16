import { spawnSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';

const AGG_BIN = process.env.AGG_BIN ?? `${process.env.HOME}/.local/bin/agg`;
const FFMPEG_BIN = process.env.FFMPEG_BIN ?? 'ffmpeg';
const FFPROBE_BIN = process.env.FFPROBE_BIN ?? 'ffprobe';

export const VIDEO_W = 1920;
export const VIDEO_H = 1080;
export const FPS = 30;
// Right-aligns the input within a 1920x1080 frame on a black background.
// Used for terminal/cast scenes so the left strip is free for future overlays.
export const PAD_FILTER_RIGHT = `scale=${VIDEO_W}:${VIDEO_H}:force_original_aspect_ratio=decrease,pad=${VIDEO_W}:${VIDEO_H}:ow-iw:(oh-ih)/2:color=black,setsar=1,fps=${FPS}`;
// Full-frame fit for title/slide/outro/browser scenes (no padding shift).
export const PAD_FILTER_CENTER = `scale=${VIDEO_W}:${VIDEO_H}:force_original_aspect_ratio=decrease,pad=${VIDEO_W}:${VIDEO_H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,fps=${FPS}`;
const PAD_FILTER = PAD_FILTER_CENTER;

function run(bin: string, args: string[]): void {
  const res = spawnSync(bin, args, { encoding: 'utf8' });
  if (res.status !== 0) {
    const tail = (res.stderr ?? '').slice(-400);
    throw new Error(
      `${bin} ${args.slice(0, 4).join(' ')} ... failed (exit ${res.status}): ${tail}`
    );
  }
}

/**
 * GPU (NVENC) H.264 encode is OPT-IN and DEFAULT-OFF. It only activates when
 * `RDC_TUTORIAL_HWENC=1` AND the running ffmpeg actually advertises the
 * `h264_nvenc` encoder. Anything else (flag unset, no NVENC build, no GPU)
 * silently uses the existing software `libx264` path, so the default render is
 * byte-for-byte identical to before.
 *
 * Scope is deliberately conservative: only the OUTPUT video codec moves to the
 * GPU. Every filter graph (scale/pad/tpad/crop/xfade/hstack) stays on the CPU
 * — frames are filtered on CPU, then handed to NVENC for the final encode.
 * Adding hwupload+scale_cuda/overlay_cuda would be faster still but is fragile
 * for these mixed screen-content graphs, so we leave it out.
 *
 * NVENC ignores `-crf`; the visual-quality knob is `-cq` under VBR rate
 * control. `-cq 20` with `-preset p5 -tune hq` matches the perceptual quality
 * of the software `-preset medium -crf 20` for flat screen-content video at a
 * comparable size, while `-pix_fmt yuv420p` keeps player/web compatibility.
 */
let nvencAvailable: boolean | undefined;
function hasNvenc(): boolean {
  if (nvencAvailable !== undefined) return nvencAvailable;
  const res = spawnSync(FFMPEG_BIN, ['-hide_banner', '-encoders'], { encoding: 'utf8' });
  nvencAvailable = res.status === 0 && /\bh264_nvenc\b/.test(res.stdout ?? '');
  return nvencAvailable;
}

let hwencWarned = false;
function useHwEnc(): boolean {
  if (process.env.RDC_TUTORIAL_HWENC !== '1') return false;
  if (hasNvenc()) return true;
  if (!hwencWarned) {
    hwencWarned = true;
    process.stderr.write(
      '[ffmpeg-video] RDC_TUTORIAL_HWENC=1 but h264_nvenc is unavailable; ' +
        'falling back to software libx264.\n'
    );
  }
  return false;
}

/**
 * Returns the video-codec argument list for an encode. GPU path when HWENC is
 * enabled+available, otherwise the original software path. The exact
 * `-pix_fmt yuv420p`, frame size, and downstream audio args are unchanged by
 * the caller; this only swaps the `-c:v ...` quality block.
 */
export function videoCodecArgs(): string[] {
  if (useHwEnc()) {
    // `-b:v 0` puts NVENC in pure constant-quality VBR (target = -cq), the
    // closest analogue to x264's CRF.
    return [
      '-c:v',
      'h264_nvenc',
      '-preset',
      'p5',
      '-tune',
      'hq',
      '-rc',
      'vbr',
      '-cq',
      '20',
      '-b:v',
      '0',
      '-pix_fmt',
      'yuv420p',
    ];
  }
  return ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-preset', 'medium', '-crf', '20'];
}

export function renderCastToGif(
  castPath: string,
  gifPath: string,
  cols: number,
  rows: number,
  lastFrameHoldSec: number = 0
): void {
  run(AGG_BIN, [
    '--theme',
    'asciinema',
    '--text-font-family',
    'JetBrains Mono,Fira Code,Cascadia Code,DejaVu Sans Mono,monospace',
    '--font-size',
    '28',
    // line-height 1.1 puts the native render at ~16:9 aspect at the 100x30
    // terminal size we record at (1714x955 = 1.795). The default 1.4 produces
    // a near-4:3 frame that leaves heavy letterboxing in the 1920x1080 output.
    '--line-height',
    '1.1',
    '--cols',
    String(cols),
    '--rows',
    String(rows),
    '--no-loop',
    '--idle-time-limit',
    '9999',
    '--last-frame-duration',
    lastFrameHoldSec.toFixed(3),
    '--fps-cap',
    String(FPS),
    castPath,
    gifPath,
  ]);
}

export function encodeAnimMp4(gifPath: string, mp4Path: string): void {
  run(FFMPEG_BIN, ['-y', '-i', gifPath, '-vf', PAD_FILTER, ...videoCodecArgs(), '-an', mp4Path]);
}

/**
 * Encode an agg GIF to mp4 at its NATIVE pixel size (no 1920x1080 letterbox),
 * padded to even dimensions for libx264. Used to capture a tall full-output
 * terminal frame whose native row height we can crop a scroll window over.
 */
export function encodeAnimMp4Raw(gifPath: string, mp4Path: string): void {
  run(FFMPEG_BIN, [
    '-y',
    '-i',
    gifPath,
    '-vf',
    'pad=ceil(iw/2)*2:ceil(ih/2)*2,setsar=1',
    ...videoCodecArgs(),
    '-an',
    mp4Path,
  ]);
}

/** ffprobe the pixel width/height of the first video/image stream. */
export function videoDimensions(filePath: string): { width: number; height: number } {
  const res = spawnSync(
    FFPROBE_BIN,
    [
      '-v',
      'error',
      '-select_streams',
      'v:0',
      '-show_entries',
      'stream=width,height',
      '-of',
      'csv=s=x:p=0',
      filePath,
    ],
    { encoding: 'utf8' }
  );
  if (res.status !== 0) throw new Error(`ffprobe dims failed: ${res.stderr.slice(-300)}`);
  const [width, height] = res.stdout.trim().split('x').map(Number);
  return { width, height };
}

/**
 * Silent scroll-pan: pan a fixed-height window (winH px = recorded terminal row
 * count) down a TALL cast source (animation or still) over `panDurSec`, holding
 * the top until `panStartSec` and the bottom afterwards, for a total of
 * `totalDurSec`. It emits NO audio — it produces the
 * silent visual that is then muxed with the main narration via
 * `muxNarratedSegment`, so the long output reveals slowly across the main
 * narration instead of being crammed into the short after-narration. The source
 * is extended (last-frame clone) to cover `totalDurSec`. `maxY` = tallH - winH.
 */
export function makeScrollPanSilent(
  srcVideo: string,
  winW: number,
  winH: number,
  maxY: number,
  totalDurSec: number,
  panStartSec: number,
  panDurSec: number,
  mp4Path: string,
  padFilter: string = PAD_FILTER
): void {
  // y(t): hold 0 until panStartSec, ramp linearly to maxY over panDurSec, then
  // hold maxY. Commas inside the crop expression are escaped so the filtergraph
  // parser does not read them as filter-argument separators.
  const y = `min(${maxY}\\,max(0\\,${maxY}*(t-${panStartSec.toFixed(3)})/${panDurSec.toFixed(3)}))`;
  run(FFMPEG_BIN, [
    '-y',
    '-i',
    srcVideo,
    '-t',
    totalDurSec.toFixed(3),
    '-vf',
    `tpad=stop_mode=clone:stop_duration=${totalDurSec.toFixed(3)},crop=${winW}:${winH}:0:${y},${padFilter}`,
    '-an',
    ...videoCodecArgs(),
    mp4Path,
  ]);
}

/** Crop a fixed window out of a still PNG (e.g. the bottom of a tall frame). */
export function cropFramePng(
  srcPng: string,
  winW: number,
  winH: number,
  y: number,
  outPng: string
): void {
  run(FFMPEG_BIN, [
    '-y',
    '-i',
    srcPng,
    '-vf',
    `crop=${winW}:${winH}:0:${y}`,
    '-frames:v',
    '1',
    outPng,
  ]);
}

export function extractLastFrame(mp4Path: string, pngPath: string): void {
  run(FFMPEG_BIN, [
    '-y',
    '-sseof',
    '-0.1',
    '-i',
    mp4Path,
    '-update',
    '1',
    '-frames:v',
    '1',
    pngPath,
  ]);
}

export function extractFirstFrame(mp4Path: string, pngPath: string): void {
  run(FFMPEG_BIN, ['-y', '-i', mp4Path, '-update', '1', '-frames:v', '1', pngPath]);
}

export function makeFreezeMp4(
  pngPath: string,
  audioPath: string,
  durationSec: number,
  mp4Path: string,
  padFilter: string = PAD_FILTER
): void {
  run(FFMPEG_BIN, [
    '-y',
    '-loop',
    '1',
    '-framerate',
    String(FPS),
    '-i',
    pngPath,
    '-i',
    audioPath,
    '-t',
    durationSec.toFixed(3),
    '-vf',
    padFilter,
    ...videoCodecArgs(),
    '-c:a',
    'aac',
    '-b:a',
    '128k',
    '-ar',
    '44100',
    '-ac',
    '2',
    '-shortest',
    mp4Path,
  ]);
}

/**
 * Re-encode a silent anim segment so it shares the same audio stream layout
 * as freeze segments. Without this, the concat demuxer skips audio for anim
 * segments and downstream players may stutter.
 */
export function addSilentAudio(mp4InPath: string, mp4OutPath: string): void {
  run(FFMPEG_BIN, [
    '-y',
    '-i',
    mp4InPath,
    '-f',
    'lavfi',
    '-i',
    'anullsrc=channel_layout=stereo:sample_rate=44100',
    '-c:v',
    'copy',
    '-c:a',
    'aac',
    '-b:a',
    '128k',
    '-shortest',
    mp4OutPath,
  ]);
}

export function concatMp4(inputs: string[], outPath: string, listPath: string): void {
  const body = inputs.map((p) => `file '${p.replace(/'/g, "'\\''")}'`).join('\n');
  writeFileSync(listPath, `${body}\n`);
  run(FFMPEG_BIN, [
    '-y',
    '-f',
    'concat',
    '-safe',
    '0',
    '-i',
    listPath,
    '-c',
    'copy',
    '-movflags',
    '+faststart',
    outPath,
  ]);
}

export function muxVideoWithAudio(
  videoPath: string,
  audioPath: string,
  durationSec: number,
  mp4Path: string,
  padFilter: string = PAD_FILTER_CENTER
): void {
  // `apad` extends a shorter narration with trailing silence so `-t` (the
  // scene duration) governs the output length. Without it, `-shortest`
  // truncates the video to the narration length and cuts scripted browser
  // actions mid-flight.
  run(FFMPEG_BIN, [
    '-y',
    '-i',
    videoPath,
    '-i',
    audioPath,
    '-t',
    durationSec.toFixed(3),
    '-af',
    'apad',
    '-vf',
    padFilter,
    ...videoCodecArgs(),
    '-c:a',
    'aac',
    '-b:a',
    '128k',
    '-ar',
    '44100',
    '-ac',
    '2',
    '-shortest',
    mp4Path,
  ]);
}

/**
 * Mux a silent video with a narration mp3, optionally prepending a held-first-frame
 * hold and/or trailing held-last-frame so total duration equals max(hold + video, audio).
 *
 * Audio is padded with trailing silence (`apad`) so the command's full cast
 * playback is preserved when narration is shorter than the cast slice. Without
 * apad, ffmpeg's `-shortest` truncates video to audio length and the command
 * gets cut off mid-execution.
 */
export function muxNarratedSegment(
  inMp4: string,
  audioPath: string,
  outMp4: string,
  opts: { startHoldSec?: number; endHoldSec?: number; padFilter?: string }
): void {
  const startHold = opts.startHoldSec ?? 0;
  const endHold = opts.endHoldSec ?? 0;
  const padFilter = opts.padFilter ?? PAD_FILTER_CENTER;
  const vf: string[] = [];
  if (startHold > 0 || endHold > 0) {
    vf.push(
      `tpad=start_mode=clone:start_duration=${startHold.toFixed(3)}:stop_mode=clone:stop_duration=${endHold.toFixed(3)}`
    );
  }
  vf.push(padFilter);
  run(FFMPEG_BIN, [
    '-y',
    '-i',
    inMp4,
    '-i',
    audioPath,
    '-vf',
    vf.join(','),
    '-af',
    'apad',
    ...videoCodecArgs(),
    '-c:a',
    'aac',
    '-b:a',
    '128k',
    '-ar',
    '44100',
    '-ac',
    '2',
    '-shortest',
    outMp4,
  ]);
}

/**
 * Adds held-frame silent padding at the start and/or end of a video.
 * Lead pad clones the first frame, tail pad clones the last frame.
 */
export function addEdgePad(inMp4: string, outMp4: string, leadSec: number, trailSec: number): void {
  run(FFMPEG_BIN, [
    '-y',
    '-i',
    inMp4,
    '-vf',
    `tpad=start_mode=clone:start_duration=${leadSec.toFixed(3)}:stop_mode=clone:stop_duration=${trailSec.toFixed(3)}`,
    '-af',
    `adelay=${Math.round(leadSec * 1000)}|${Math.round(leadSec * 1000)},apad=pad_dur=${trailSec.toFixed(3)}`,
    ...videoCodecArgs(),
    '-c:a',
    'aac',
    '-b:a',
    '128k',
    '-ar',
    '44100',
    '-ac',
    '2',
    outMp4,
  ]);
}

/**
 * Adds a trailing pause of `padSec` seconds by holding the last frame and
 * inserting silence. Used for inter-scene breathing room.
 */
export function addTailPad(inMp4: string, outMp4: string, padSec: number): void {
  run(FFMPEG_BIN, [
    '-y',
    '-i',
    inMp4,
    '-vf',
    `tpad=stop_mode=clone:stop_duration=${padSec.toFixed(3)}`,
    '-af',
    `apad=pad_dur=${padSec.toFixed(3)}`,
    ...videoCodecArgs(),
    '-c:a',
    'aac',
    '-b:a',
    '128k',
    '-ar',
    '44100',
    '-ac',
    '2',
    outMp4,
  ]);
}

/**
 * Hold a single PNG frame as a silent mp4 for the given duration. Used to
 * insert reading-pause beats between cast playback and after-narration.
 */
export function makeSilentFreezeMp4(
  pngPath: string,
  durationSec: number,
  mp4Path: string,
  padFilter: string = PAD_FILTER
): void {
  run(FFMPEG_BIN, [
    '-y',
    '-loop',
    '1',
    '-framerate',
    String(FPS),
    '-i',
    pngPath,
    '-f',
    'lavfi',
    '-i',
    'anullsrc=channel_layout=stereo:sample_rate=44100',
    '-t',
    durationSec.toFixed(3),
    '-vf',
    padFilter,
    ...videoCodecArgs(),
    '-c:a',
    'aac',
    '-b:a',
    '128k',
    '-ar',
    '44100',
    '-ac',
    '2',
    '-shortest',
    mp4Path,
  ]);
}

/**
 * Trim a silent mp4 to the first `durationSec` seconds. Re-encodes (no stream
 * copy) so the output has frame-accurate length matching downstream tpad math.
 */
export function trimMp4Duration(inMp4: string, outMp4: string, durationSec: number): void {
  run(FFMPEG_BIN, [
    '-y',
    '-i',
    inMp4,
    '-t',
    durationSec.toFixed(3),
    ...videoCodecArgs(),
    '-an',
    outMp4,
  ]);
}

/**
 * Cut [startSec, startSec+durSec] out of a session recording into a silent
 * mp4. `-ss` before `-i` with re-encode is frame-accurate (ffmpeg decodes
 * from the prior keyframe and discards) without decoding the whole session.
 * Encoding settings match every other segment producer so `concatMp4`'s
 * stream-copy keeps working.
 */
export function cutSegmentMp4(
  srcVideo: string,
  startSec: number,
  durSec: number,
  outMp4: string,
  padFilter: string = PAD_FILTER_CENTER
): void {
  run(FFMPEG_BIN, [
    '-y',
    '-ss',
    startSec.toFixed(3),
    '-i',
    srcVideo,
    '-t',
    durSec.toFixed(3),
    '-vf',
    padFilter,
    '-an',
    ...videoCodecArgs(),
    outMp4,
  ]);
}

/**
 * Concatenate chunks with optional crossfades at flagged boundaries.
 * `fadeAfter[i]` = crossfade between chunks[i] and chunks[i+1] (browser scene
 * meeting a different surface); unflagged boundaries stay hard cuts. Chunks
 * connected by fades form groups rendered with one xfade/acrossfade chain;
 * groups are then stream-copy concatenated, so the extra encode cost is
 * limited to the faded neighborhoods.
 *
 * The fade consumes the tail of the earlier chunk (which is held-last-frame
 * padding from addTailPad), so pacing is unchanged.
 */
export function assembleWithTransitions(
  chunks: string[],
  fadeAfter: boolean[],
  outPath: string,
  tmpDir: string,
  fadeSec: number = 0.3
): void {
  // Partition into runs of chunks connected by flagged boundaries.
  const groups: number[][] = [];
  let current: number[] = [0];
  for (let i = 0; i < chunks.length - 1; i++) {
    if (fadeAfter[i]) {
      current.push(i + 1);
    } else {
      groups.push(current);
      current = [i + 1];
    }
  }
  groups.push(current);

  const groupFiles: string[] = [];
  for (let g = 0; g < groups.length; g++) {
    const idxs = groups[g];
    if (idxs.length === 1) {
      groupFiles.push(chunks[idxs[0]]);
      continue;
    }
    // Build one filter_complex chain: v/a xfade pairs across the group.
    const inputs: string[] = [];
    for (const i of idxs) inputs.push('-i', chunks[i]);
    const durs = idxs.map((i) => probeDurationSec(chunks[i]));
    const parts: string[] = [];
    let vPrev = '0:v';
    let aPrev = '0:a';
    let cumulative = durs[0];
    for (let k = 1; k < idxs.length; k++) {
      const offset = Math.max(0, cumulative - fadeSec);
      const vOut = k === idxs.length - 1 ? 'vout' : `v${k}`;
      const aOut = k === idxs.length - 1 ? 'aout' : `a${k}`;
      parts.push(
        `[${vPrev}][${k}:v]xfade=transition=fade:duration=${fadeSec.toFixed(3)}:offset=${offset.toFixed(3)}[${vOut}]`
      );
      // c2=nofade: the outgoing tail is held-frame silence, so only fade IT
      // out and let the incoming chunk's audio (often narration starting at
      // t=0) pass through at full level.
      parts.push(`[${aPrev}][${k}:a]acrossfade=d=${fadeSec.toFixed(3)}:c1=tri:c2=nofade[${aOut}]`);
      vPrev = vOut;
      aPrev = aOut;
      cumulative = offset + durs[k];
    }
    const groupOut = `${tmpDir}/xfade-group-${g}.mp4`;
    run(FFMPEG_BIN, [
      '-y',
      ...inputs,
      '-filter_complex',
      parts.join(';'),
      '-map',
      '[vout]',
      '-map',
      '[aout]',
      ...videoCodecArgs(),
      '-c:a',
      'aac',
      '-b:a',
      '128k',
      '-ar',
      '44100',
      '-ac',
      '2',
      groupOut,
    ]);
    groupFiles.push(groupOut);
  }

  if (groupFiles.length === 1) {
    // Single group — already encoded; remux for faststart.
    run(FFMPEG_BIN, ['-y', '-i', groupFiles[0], '-c', 'copy', '-movflags', '+faststart', outPath]);
    return;
  }
  concatMp4(groupFiles, outPath, `${tmpDir}/concat-groups.txt`);
}

export function extractPosterJpg(mp4Path: string, atSec: number, jpgPath: string): void {
  run(FFMPEG_BIN, [
    '-y',
    '-ss',
    atSec.toFixed(3),
    '-i',
    mp4Path,
    '-frames:v',
    '1',
    '-q:v',
    '3',
    jpgPath,
  ]);
}

export function probeDurationSec(path: string): number {
  const res = spawnSync(
    FFPROBE_BIN,
    [
      '-v',
      'error',
      '-show_entries',
      'format=duration',
      '-of',
      'default=noprint_wrappers=1:nokey=1',
      path,
    ],
    { encoding: 'utf8' }
  );
  if (res.status !== 0) throw new Error(`ffprobe failed: ${res.stderr.slice(-400)}`);
  return Number(res.stdout.trim());
}
