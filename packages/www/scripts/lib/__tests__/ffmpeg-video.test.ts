import { spawnSync } from 'node:child_process';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, beforeAll, describe, expect, it } from 'vitest';
import { addEdgePad, extractLastFrame } from '../ffmpeg-video.ts';
import { probeDurationSec } from '../ffprobe.ts';

const hasTool = (bin: string): boolean =>
  spawnSync(bin, ['-version'], { stdio: 'ignore' }).status === 0;
const available = hasTool('ffmpeg') && hasTool('ffprobe');
const PNG_MAGIC = Buffer.from([0x89, 0x50, 0x4e, 0x47]);

let dir = '';
let clip = '';

/** Stream kinds of a media file, as ffprobe lists them. */
function streamKinds(file: string): string[] {
  const out = spawnSync(
    'ffprobe',
    ['-v', 'error', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', file],
    { encoding: 'utf8' }
  );
  return out.stdout.split('\n').filter(Boolean).sort();
}

describe.skipIf(!available)('ffmpeg-video (real ffmpeg)', () => {
  beforeAll(() => {
    dir = mkdtempSync(path.join(tmpdir(), 'ffmpeg-video-'));
    clip = path.join(dir, 'clip.mp4');
    const made = spawnSync(
      'ffmpeg',
      [
        '-y',
        '-f',
        'lavfi',
        '-i',
        'color=c=red:s=64x64:r=10:d=1',
        '-f',
        'lavfi',
        '-i',
        'sine=frequency=440:duration=1',
        '-shortest',
        '-c:v',
        'libx264',
        '-pix_fmt',
        'yuv420p',
        '-c:a',
        'aac',
        clip,
      ],
      { stdio: 'ignore' }
    );
    if (made.status !== 0) throw new Error('could not generate the fixture clip');
  });

  afterEach(() => {
    rmSync(path.join(dir, 'frame.png'), { force: true });
    rmSync(path.join(dir, 'padded.partial'), { force: true });
  });

  it('extractLastFrame writes a fresh png over a stale one', () => {
    const png = path.join(dir, 'frame.png');
    writeFileSync(png, 'stale-not-a-png');
    extractLastFrame(clip, png);
    const bytes = readFileSync(png);
    expect(bytes.subarray(0, 4).equals(PNG_MAGIC)).toBe(true);
  });

  it('extractLastFrame writes the frame when no png exists yet', () => {
    const png = path.join(dir, 'frame.png');
    extractLastFrame(clip, png);
    expect(existsSync(png)).toBe(true);
  });

  it('addEdgePad extends the clip by the lead and trail and keeps both streams', () => {
    const out = path.join(dir, 'padded.partial');
    addEdgePad(clip, out, 0.5, 0.5);
    expect(streamKinds(out)).toEqual(['audio', 'video']);
    expect(probeDurationSec(out)).toBeGreaterThan(probeDurationSec(clip) + 0.8);
    // The intermediate audio pass leaves nothing behind.
    expect(existsSync(`${out}.pad-audio.m4a`)).toBe(false);
  });
});
