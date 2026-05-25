/**
 * TutorialVideoPlayer — Plyr-based HTML5 video player for tutorial pages.
 *
 * Plays a self-contained mp4 with a chapters WebVTT and a custom caption
 * overlay driven by a per-tutorial words.json sidecar so we can highlight
 * each spoken word as it is narrated (Plyr's built-in caption renderer
 * cannot do per-word highlight because it strips inline VTT timestamp
 * tags during innerHTML insertion).
 *
 * The subtitles track is kept loaded so Plyr's CC button stays wired and
 * the captions menu lists the language, but the visible captions box is
 * hidden via CSS — our overlay replaces it.
 */

import type { FC } from 'react';
import { useEffect, useRef, useState } from 'react';
import Plyr from 'plyr';
import 'plyr/dist/plyr.css';
import '../styles/tutorial-video.css';

interface TutorialVideoPlayerProps {
  src: string;
  posterSrc: string;
  subtitlesSrc: string;
  chaptersSrc: string;
  wordsSrc: string;
  title: string;
  lang: string;
}

// Shape mirrors the `.words.json` sidecar emitted by
// `packages/www/scripts/lib/vtt-emit.ts::emitWordTimingsJson` — keep in sync
// when extending either side.
interface WordEntry {
  start: number;
  end: number;
  char: [number, number];
}

interface CueEntry {
  start: number;
  end: number;
  text: string;
  words: WordEntry[];
}

interface WordsDoc {
  version: number;
  cues: CueEntry[];
}

// HTMLVideoElement.currentTime tracks the displayed-frame clock, which trails
// audio output by ~30-50 ms in most browsers, and our RAF tick adds one more
// vsync interval (~16 ms) of jitter on top. A small constant look-ahead keeps
// the active word aligned with what the viewer hears. Leading the audio is
// worse than trailing — don't push this higher than ~80 ms.
const HIGHLIGHT_LEAD_SEC = 0.06;

const LANG_LABELS: Record<string, string> = {
  en: 'English',
  de: 'Deutsch',
  es: 'Español',
  fr: 'Français',
  it: 'Italiano',
  ja: '日本語',
  ko: '한국어',
  pt: 'Português',
  ru: 'Русский',
  tr: 'Türkçe',
  zh: '中文',
  ar: 'العربية',
};

function paintChapterOverlay(
  video: HTMLVideoElement,
  chaptersTrack: TextTrack,
  overlay: HTMLDivElement,
  onSeek: (sec: number) => void
): void {
  const duration = video.duration;
  if (!Number.isFinite(duration) || duration <= 0) return;
  const cues = chaptersTrack.cues;
  if (!cues || cues.length === 0) return;
  overlay.innerHTML = '';
  for (let i = 0; i < cues.length; i++) {
    const cue = cues[i] as VTTCue;
    if (i === 0 && cue.startTime <= 0.05) continue;
    const tick = document.createElement('button');
    tick.type = 'button';
    tick.className = 'tvp-chapter-tick';
    tick.style.left = `${(cue.startTime / duration) * 100}%`;
    tick.dataset.label = cue.text;
    tick.setAttribute('aria-label', `Jump to ${cue.text}`);
    const tooltip = document.createElement('span');
    tooltip.className = 'tvp-chapter-tooltip';
    tooltip.textContent = cue.text;
    tick.appendChild(tooltip);
    tick.addEventListener('click', (e) => {
      e.stopPropagation();
      onSeek(cue.startTime);
    });
    overlay.appendChild(tick);
  }
}

/**
 * Binary search the cue covering `t` in seconds. Returns -1 if t lies in a
 * gap between cues (e.g., during silent freezes between narrated steps).
 */
function findActiveCueIndex(cues: CueEntry[], t: number): number {
  let lo = 0;
  let hi = cues.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >>> 1;
    const c = cues[mid];
    if (t < c.start) hi = mid - 1;
    else if (t >= c.end) lo = mid + 1;
    else return mid;
  }
  return -1;
}

function findActiveWordIndex(words: WordEntry[], t: number): number {
  // Words inside a cue are typically <= 10 entries; linear is fastest.
  for (let i = 0; i < words.length; i++) {
    if (t >= words[i].start && t < words[i].end) return i;
  }
  // If we are past the last word's end but still inside the cue, keep the
  // last word highlighted so the trailing punctuation doesn't visually
  // "release" the highlight.
  return words.length > 0 && t >= words[words.length - 1].end ? words.length - 1 : -1;
}

/**
 * Render a cue's text as one <span> per word, applying `is-active` to the
 * matching word. The non-word characters between words (spaces, punctuation
 * that appears outside any word's char range) are emitted as text nodes so
 * the line wraps naturally.
 */
function renderCueIntoOverlay(el: HTMLDivElement, cue: CueEntry, activeWordIdx: number): void {
  el.innerHTML = '';
  // Defensive fallback: a malformed sidecar (or a single-word phrase) lands
  // here with one word entry covering the whole cue. Render as plain text so
  // we don't paint the entire line in the active-word style.
  if (cue.words.length <= 1) {
    el.appendChild(document.createTextNode(cue.text));
    return;
  }
  let cursor = 0;
  for (let i = 0; i < cue.words.length; i++) {
    const w = cue.words[i];
    const [cs, ce] = w.char;
    if (cs > cursor) {
      el.appendChild(document.createTextNode(cue.text.substring(cursor, cs)));
    }
    const span = document.createElement('span');
    span.className = i === activeWordIdx ? 'tvp-caption-word is-active' : 'tvp-caption-word';
    span.textContent = cue.text.substring(cs, ce);
    el.appendChild(span);
    cursor = ce;
  }
  if (cursor < cue.text.length) {
    el.appendChild(document.createTextNode(cue.text.substring(cursor)));
  }
}

const TutorialVideoPlayer: FC<TutorialVideoPlayerProps> = ({
  src,
  posterSrc,
  subtitlesSrc,
  chaptersSrc,
  wordsSrc,
  title,
  lang,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const chapterOverlayRef = useRef<HTMLDivElement>(null);
  const captionRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<Plyr | null>(null);
  const [wordsDoc, setWordsDoc] = useState<WordsDoc | null>(null);

  // Fetch words.json once per source change.
  useEffect(() => {
    if (!wordsSrc) return;
    let cancelled = false;
    fetch(wordsSrc)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((doc: WordsDoc) => {
        if (!cancelled) setWordsDoc(doc);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [wordsSrc]);

  // Plyr lifecycle + chapter overlay.
  useEffect(() => {
    const video = videoRef.current;
    const chapterOverlay = chapterOverlayRef.current;
    if (!video || !chapterOverlay) return;
    // Capture the caption node at mount so the cleanup closure does not read
    // captionRef.current after render (react-hooks/exhaustive-deps); the node
    // is rendered once and stable for the life of this effect.
    const captionNode = captionRef.current;

    const player = new Plyr(video, {
      controls: [
        'play-large',
        'play',
        'progress',
        'current-time',
        'duration',
        'mute',
        'volume',
        'captions',
        'settings',
        'pip',
        'fullscreen',
      ],
      settings: ['captions', 'speed'],
      captions: { active: true, language: lang, update: true },
      keyboard: { focused: true, global: false },
      tooltips: { controls: true, seek: true },
      storage: { enabled: true, key: 'plyr-tutorial' },
    });
    playerRef.current = player;

    const onSeek = (sec: number) => {
      player.currentTime = sec;
    };

    const mountChapterOverlay = () => {
      const tracks = Array.from(video.textTracks);
      const chaptersTrack = tracks.find((t) => t.kind === 'chapters');
      if (!chaptersTrack) return;
      chaptersTrack.mode = 'hidden';

      const plyrRoot = video.closest('.plyr');
      const progress = plyrRoot?.querySelector('.plyr__progress');
      if (progress instanceof HTMLElement) {
        progress.appendChild(chapterOverlay);
      }

      const repaint = () => paintChapterOverlay(video, chaptersTrack, chapterOverlay, onSeek);
      if (chaptersTrack.cues && chaptersTrack.cues.length > 0) {
        repaint();
      } else {
        chaptersTrack.addEventListener('cuechange', repaint, {
          once: true,
        });
      }
      video.addEventListener('loadedmetadata', repaint);
      window.addEventListener('resize', repaint);
      return () => {
        video.removeEventListener('loadedmetadata', repaint);
        window.removeEventListener('resize', repaint);
      };
    };

    // Relocate the word-by-word caption overlay INTO Plyr's video wrapper.
    // The Fullscreen API only renders descendants of the fullscreened element
    // (the .plyr container), so a caption left in .tvp-root vanishes in
    // fullscreen. Moving it inside .plyr__video-wrapper keeps it visible in
    // both modes and lets the `.plyr--fullscreen-active .tvp-caption` CSS match.
    const mountCaptionOverlay = () => {
      const caption = captionRef.current;
      if (!caption) return;
      const plyrRoot = video.closest('.plyr');
      const wrapper = plyrRoot?.querySelector('.plyr__video-wrapper');
      const host = wrapper instanceof HTMLElement ? wrapper : (plyrRoot as HTMLElement | null);
      host?.appendChild(caption);
    };

    let detachChapterOverlay: (() => void) | undefined;
    player.on('ready', () => {
      detachChapterOverlay = mountChapterOverlay();
      mountCaptionOverlay();
    });

    return () => {
      detachChapterOverlay?.();
      // Return the caption to .tvp-root before Plyr.destroy() tears down the
      // .plyr wrapper, so React still finds the node to unmount cleanly.
      const caption = captionNode;
      const root = video.closest('.tvp-root');
      if (caption && root instanceof HTMLElement && caption.parentElement !== root) {
        root.appendChild(caption);
      }
      try {
        player.destroy();
      } catch {
        // ignore teardown errors
      }
      playerRef.current = null;
    };
  }, [src, lang]);

  // Word-by-word caption overlay driven by RAF + Plyr CC events.
  useEffect(() => {
    const video = videoRef.current;
    const caption = captionRef.current;
    if (!video || !caption || !wordsDoc) return;

    const cues = wordsDoc.cues;
    let raf = 0;
    let lastCueIdx = -2;
    let lastWordIdx = -2;
    let lastDomCue: CueEntry | null = null;

    const tick = () => {
      const t = video.currentTime + HIGHLIGHT_LEAD_SEC;
      const cueIdx = findActiveCueIndex(cues, t);
      const cue = cueIdx >= 0 ? cues[cueIdx] : null;
      const wordIdx = cue ? findActiveWordIndex(cue.words, t) : -1;

      if (cueIdx !== lastCueIdx) {
        if (cue) {
          renderCueIntoOverlay(caption, cue, wordIdx);
          caption.classList.add('is-visible');
          lastDomCue = cue;
        } else {
          caption.innerHTML = '';
          caption.classList.remove('is-visible');
          lastDomCue = null;
        }
      } else if (cue && wordIdx !== lastWordIdx && lastDomCue === cue) {
        // Cue unchanged: only flip the is-active class on the relevant spans.
        const spans = caption.querySelectorAll<HTMLSpanElement>('.tvp-caption-word');
        spans.forEach((s, i) => {
          s.classList.toggle('is-active', i === wordIdx);
        });
      }
      lastCueIdx = cueIdx;
      lastWordIdx = wordIdx;
      raf = requestAnimationFrame(tick);
    };

    const start = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(tick);
    };
    const stop = () => {
      cancelAnimationFrame(raf);
      raf = 0;
    };
    // A single tick after scrubbing so the overlay reflects the new position
    // even while paused.
    const stepOnce = () => {
      cancelAnimationFrame(raf);
      tick();
      if (video.paused) cancelAnimationFrame(raf);
    };

    video.addEventListener('play', start);
    video.addEventListener('playing', start);
    video.addEventListener('pause', stop);
    video.addEventListener('ended', stop);
    video.addEventListener('seeked', stepOnce);
    video.addEventListener('loadedmetadata', stepOnce);

    // Initial paint.
    if (video.paused) {
      stepOnce();
    } else {
      start();
    }

    return () => {
      cancelAnimationFrame(raf);
      video.removeEventListener('play', start);
      video.removeEventListener('playing', start);
      video.removeEventListener('pause', stop);
      video.removeEventListener('ended', stop);
      video.removeEventListener('seeked', stepOnce);
      video.removeEventListener('loadedmetadata', stepOnce);
    };
  }, [wordsDoc]);

  // Sync caption visibility with Plyr's CC button state.
  useEffect(() => {
    const video = videoRef.current;
    const caption = captionRef.current;
    if (!video || !caption) return;

    const enable = () => caption.classList.remove('is-hidden-by-cc');
    const disable = () => caption.classList.add('is-hidden-by-cc');

    video.addEventListener('captionsenabled', enable);
    video.addEventListener('captionsdisabled', disable);

    // Initialize from Plyr's persisted preference (default on).
    const stored = (() => {
      try {
        return JSON.parse(window.localStorage.getItem('plyr-tutorial') ?? '{}');
      } catch {
        return {};
      }
    })() as { captions?: boolean };
    if (stored.captions === false) disable();

    return () => {
      video.removeEventListener('captionsenabled', enable);
      video.removeEventListener('captionsdisabled', disable);
    };
  }, []);

  const langLabel = LANG_LABELS[lang.split('-')[0].toLowerCase()] ?? lang.toUpperCase();

  return (
    <div className="tvp-root" aria-label={title}>
      <video
        ref={videoRef}
        src={src}
        poster={posterSrc}
        preload="metadata"
        playsInline
        data-poster={posterSrc}
      >
        <track kind="subtitles" src={subtitlesSrc} srcLang={lang} label={langLabel} default />
        <track kind="chapters" src={chaptersSrc} srcLang={lang} label="Chapters" />
      </video>
      <div ref={chapterOverlayRef} className="tvp-chapter-overlay" aria-hidden="true" />
      <div ref={captionRef} className="tvp-caption" aria-live="polite" aria-atomic="true" />
    </div>
  );
};

export default TutorialVideoPlayer;
