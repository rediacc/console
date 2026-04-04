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

const PHRASE_BREAK_RE = /[,;:.!?]|--/;

function findSplitPoint(
  segments: CaptionSegment[],
  pageStart: number,
  overflowIndex: number,
  lastBreak: number,
  charsAtBreak: number,
  minBreakChars: number
): number {
  if (lastBreak >= pageStart && charsAtBreak >= minBreakChars) return lastBreak;
  return overflowIndex;
}

function countChars(segments: CaptionSegment[], from: number, to: number): number {
  let n = 0;
  for (let j = from; j <= to; j += 1) n += segments[j].text.length;
  return n;
}

/**
 * Split caption segments into pages of ~maxCharsPerPage characters each,
 * breaking at natural phrase boundaries (punctuation, dashes).
 * Follows YouTube/Netflix convention: max 2 lines x ~42 chars = 84 chars per page.
 */
export function paginateCaptionSegments(
  segments: CaptionSegment[],
  maxCharsPerPage = 84
): CaptionSegment[][] {
  const totalChars = segments.reduce((sum, s) => sum + s.text.length, 0);
  if (totalChars <= maxCharsPerPage) return [segments];

  const pages: CaptionSegment[][] = [];
  let pageStart = 0;
  let charCount = 0;
  let lastBreak = -1;
  let charsAtBreak = 0;
  const minBreakChars = maxCharsPerPage * 0.5;

  for (let i = 0; i < segments.length; i += 1) {
    charCount += segments[i].text.length;

    if (PHRASE_BREAK_RE.test(segments[i].text)) {
      lastBreak = i;
      charsAtBreak = charCount;
    }

    if (charCount >= maxCharsPerPage && i < segments.length - 1) {
      const splitAfter = findSplitPoint(
        segments,
        pageStart,
        i,
        lastBreak,
        charsAtBreak,
        minBreakChars
      );
      pages.push(segments.slice(pageStart, splitAfter + 1));
      pageStart = splitAfter + 1;
      charCount = countChars(segments, pageStart, i);
      lastBreak = -1;
      charsAtBreak = 0;
    }
  }

  if (pageStart < segments.length) {
    pages.push(segments.slice(pageStart));
  }
  return pages;
}

const NARRATION_OVERLAY_CLASS = 'terminal-player-narration-progress';

function ensureOverlay(bar: HTMLElement): HTMLElement {
  let overlay = bar.querySelector<HTMLElement>(`.${NARRATION_OVERLAY_CLASS}`);
  if (!overlay) {
    overlay = document.createElement('span');
    overlay.className = NARRATION_OVERLAY_CLASS;
    bar.appendChild(overlay);
  }
  return overlay;
}

function markerPct(marker: HTMLElement | undefined, fallback: number): number {
  if (!marker) return fallback;
  return Number.parseFloat(marker.style.left) || fallback;
}

function setTimerChild(
  timer: HTMLElement,
  selector: string,
  text: string | null,
  visible: boolean
): void {
  const el = timer.querySelector<HTMLElement>(selector);
  if (!el) return;
  if (text !== null) el.textContent = text;
  el.style.display = visible ? '' : 'none';
}

function setTimerDisplay(timer: HTMLElement | null, stepLabel: string | null): void {
  if (!timer) return;
  setTimerChild(timer, '.ap-time-elapsed', stepLabel, true);
  setTimerChild(timer, '.ap-time-remaining', null, stepLabel === null);
}

function applyOverlayStyle(
  overlay: HTMLElement,
  startPct: number,
  widthPct: number,
  visible: boolean
): void {
  Object.assign(overlay.style, {
    position: 'absolute',
    left: `${startPct}%`,
    width: `${widthPct}%`,
    top: '0',
    bottom: '0',
    background: 'rgba(85, 107, 47, 0.6)',
    borderRadius: '2px',
    transition: 'opacity 0.18s ease',
    opacity: visible ? '1' : '0',
    zIndex: '1',
    pointerEvents: 'none',
  });
}

/**
 * Manage a narration progress overlay inside the asciinema progress bar.
 * Shows a colored fill during narration and updates the timer display.
 */
export function updateNarrationProgress(
  container: HTMLElement | null,
  phase: string,
  stepIndex: number,
  totalSteps: number,
  narrationProgress: number
): void {
  if (!container) return;
  const bar = container.querySelector<HTMLElement>('.ap-bar');
  if (!bar) return;
  const timer = container.querySelector<HTMLElement>('.ap-timer');
  const overlay = ensureOverlay(bar);

  if (phase !== 'narrating') {
    applyOverlayStyle(overlay, 0, 0, false);
    setTimerDisplay(timer, null);
    return;
  }

  const markers = bar.querySelectorAll<HTMLElement>('.ap-marker-container');
  const startPct = markerPct(markers[stepIndex], 0);
  const endPct = markerPct(markers[stepIndex + 1], 100);
  const fillWidth = (endPct - startPct) * Math.min(1, narrationProgress);

  applyOverlayStyle(overlay, startPct, fillWidth, true);
  setTimerDisplay(timer, `Step ${stepIndex + 1}/${totalSteps}`);
}

/** Find which page contains the word with the given timing index. */
export function pageIndexForWord(pages: CaptionSegment[][], wordIndex: number): number {
  if (wordIndex < 0) return 0;
  for (let p = 0; p < pages.length; p += 1) {
    for (const seg of pages[p]) {
      if (seg.isWord && seg.index === wordIndex) return p;
    }
  }
  return pages.length - 1;
}
