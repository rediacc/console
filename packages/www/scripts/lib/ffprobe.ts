/**
 * The two ffprobe readers: how long a file is, and how big its video stream is.
 *
 * Split out of ffmpeg-video.ts, which encodes rather than measures, and which
 * had grown past the file-length cap.
 */
import { spawnSync } from 'node:child_process';
import { stdio } from './spawn-stdio.ts';

const DEFAULT_FFPROBE_BIN = 'ffprobe';
const FFPROBE_BIN = process.env.FFPROBE_BIN ?? DEFAULT_FFPROBE_BIN;

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
  if (res.status !== 0) throw new Error(`ffprobe dims failed: ${stdio(res.stderr).slice(-300)}`);
  const [width, height] = res.stdout.trim().split('x').map(Number);
  return { width, height };
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
  if (res.status !== 0) throw new Error(`ffprobe failed: ${stdio(res.stderr).slice(-400)}`);
  return Number(res.stdout.trim());
}
