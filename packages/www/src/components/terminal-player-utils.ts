import type { TutorialTimelineStep, TutorialWordTiming } from '../types/tutorial-timeline';

export const transcriptLabels: Record<string, { transcript: string; step: string }> = {
  en: { transcript: 'Transcript', step: 'Step' },
  de: { transcript: 'Transkript', step: 'Schritt' },
  es: { transcript: 'Transcripción', step: 'Paso' },
  fr: { transcript: 'Transcription', step: 'Étape' },
  ja: { transcript: '文字起こし', step: 'ステップ' },
  ar: { transcript: 'النص', step: 'الخطوة' },
  ru: { transcript: 'Транскрипт', step: 'Шаг' },
  tr: { transcript: 'Transkript', step: 'Adım' },
  zh: { transcript: '文字稿', step: '步骤' },
};

export type CaptionSegment = { text: string; isWord: boolean; index: number };
const INLINE_PLAYBACK_HOST_CLASS = 'terminal-player-inline-playback-host';

export function resolveCastKey(src: string, castKey?: string): string {
  if (castKey) return castKey;
  try {
    const pathname = new URL(src, 'https://www.rediacc.com').pathname;
    const filename = pathname.split('/').pop() ?? '';
    return filename.replace(/\.cast$/i, '');
  } catch {
    return (
      src
        .split('/')
        .pop()
        ?.replace(/\.cast$/i, '') ?? ''
    );
  }
}

export function ensureInlineVolumeHost(playerContainer: HTMLElement): HTMLElement | null {
  const controlBar = playerContainer.querySelector<HTMLElement>('.ap-control-bar');
  if (!controlBar) return null;
  let host = controlBar.querySelector<HTMLElement>('.terminal-player-inline-volume-host');
  if (!host) {
    host = document.createElement('span');
    host.className = 'terminal-player-inline-volume-host';
  }
  const playControl =
    controlBar.querySelector<HTMLElement>('.ap-playback-button') ??
    controlBar.querySelector<HTMLElement>('.ap-playpause-button') ??
    controlBar.querySelector<HTMLElement>('button');
  if (playControl?.parentElement === controlBar) {
    controlBar.insertBefore(host, playControl.nextSibling);
  } else {
    controlBar.appendChild(host);
  }
  return host;
}

export function ensureInlinePlaybackHost(playerContainer: HTMLElement): HTMLElement | null {
  const controlBar = playerContainer.querySelector<HTMLElement>('.ap-control-bar');
  if (!controlBar) return null;
  let host = controlBar.querySelector<HTMLElement>(`.${INLINE_PLAYBACK_HOST_CLASS}`);
  if (!host) {
    host = document.createElement('span');
    host.className = INLINE_PLAYBACK_HOST_CLASS;
  }
  const playControl = controlBar.querySelector<HTMLElement>('.ap-playback-button');
  if (playControl?.parentElement === controlBar) {
    controlBar.insertBefore(host, playControl);
  } else {
    controlBar.insertBefore(host, controlBar.firstChild);
  }
  return host;
}

export function ensureInlineCcHost(playerContainer: HTMLElement): HTMLElement | null {
  const controlBar = playerContainer.querySelector<HTMLElement>('.ap-control-bar');
  if (!controlBar) return null;
  let host = controlBar.querySelector<HTMLElement>('.terminal-player-inline-cc-host');
  if (!host) {
    host = document.createElement('span');
    host.className = 'terminal-player-inline-cc-host';
  }
  const fullscreenControl = controlBar.querySelector<HTMLElement>('.ap-fullscreen-button');
  if (fullscreenControl?.parentElement === controlBar) {
    controlBar.insertBefore(host, fullscreenControl);
  } else {
    controlBar.appendChild(host);
  }
  return host;
}

export function findStepIndex(timeSec: number, steps: TutorialTimelineStep[]): number {
  if (steps.length === 0) return 0;
  if (timeSec <= steps[0].replayStartSec) return 0;
  for (let i = 0; i < steps.length - 1; i += 1) {
    if (timeSec < steps[i + 1].replayStartSec) return i;
  }
  return steps.length - 1;
}

function estimateWordTimings(text: string, durationSec: number): TutorialWordTiming[] {
  const words = Array.from(text.matchAll(/\S+/g));
  if (words.length === 0) return [];
  const span = Math.max(0.2, durationSec) / words.length;
  return words.map((m, i) => ({
    startSec: i * span,
    endSec: (i + 1) * span,
    startChar: m.index,
    endChar: m.index + m[0].length,
  }));
}

export function stepWordTimings(step: TutorialTimelineStep): TutorialWordTiming[] {
  if (step.wordTimings && step.wordTimings.length > 0) return step.wordTimings;
  const duration = step.audioDurationSec ?? step.replayEndSec - step.replayStartSec;
  return estimateWordTimings(step.narrationText, duration);
}

export function activeWordIndex(clockSec: number, timings: TutorialWordTiming[]): number {
  for (let i = 0; i < timings.length; i += 1) {
    if (clockSec >= timings[i].startSec && clockSec <= timings[i].endSec) return i;
  }
  return -1;
}

export function buildCaptionSegments(
  text: string,
  timings: TutorialWordTiming[]
): CaptionSegment[] {
  if (timings.length === 0) return [{ text, isWord: false, index: -1 }];
  const segments: CaptionSegment[] = [];
  let cursor = 0;
  for (let i = 0; i < timings.length; i += 1) {
    const start = Math.max(0, Math.min(timings[i].startChar, text.length));
    const end = Math.max(start, Math.min(timings[i].endChar, text.length));
    if (start > cursor)
      segments.push({ text: text.slice(cursor, start), isWord: false, index: -1 });
    if (end > start) segments.push({ text: text.slice(start, end), isWord: true, index: i });
    cursor = end;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), isWord: false, index: -1 });
  return segments;
}
