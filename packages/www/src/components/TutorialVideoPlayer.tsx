/**
 * TutorialVideoPlayer: the Video.js 10 player for tutorial and solution videos.
 *
 * Plays a self-contained mp4 with a chapters WebVTT and a custom caption overlay driven by
 * a per-tutorial words.json sidecar, so each spoken word is highlighted as it is narrated.
 * The browser's own cue renderer cannot do per-word highlight, so the subtitles track stays
 * loaded (the skin's CC button and captions menu need it) while its native rendering is
 * hidden in CSS and `.tvp-caption` paints the words instead.
 *
 * The packaged `VideoSkin` is used as is, not ejected. Its settings menu has no slot for
 * an extra item: `VideoSettingsMenu` hard-codes quality, audio track, speed and captions,
 * and the docs say a child of a packaged skin "does not appear in its control bar".
 * Ejecting it would have meant owning 2,786 lines of registry source (measured
 * 2026-10-08 from shadcn.videojs.org/r/react/video.json and its 34 dependencies) plus a
 * Tailwind 4.3 toolchain this site does not have, so the language picker lives in the
 * in-frame toolbar only (agent/plans/PLAN-plyr-to-videojs.md, spike).
 */

import { I18nProvider } from '@videojs/react/i18n';
import { Video, VideoPlayer, VideoSkin } from '@videojs/react/video';
import type { FC } from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getLanguageName, SUPPORTED_LANGUAGES } from '../i18n/language-utils';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';
import LanguageMenu from './LanguageMenu';
import { bindPreferences, subtitlesTrack } from './tutorial-video/preferences';
// The player's stylesheets are NOT imported here. A module-scope import puts them in this chunk's importedCss, and Astro then links them on every page carrying the hydrator -- 794 pages with no player. They load at runtime instead; see ../scripts/tutorial-video-styles.ts, and check:ci-player-css-scope guards it.

/**
 * One locale's assets.
 *
 * Only `mp4` and `poster` are required, because the SOLUTION-page videos reuse this
 * player and have neither sidecars nor a separate caption track: their captions are
 * burned into each localized file. `vertical` is the portrait cut those videos ship, and
 * it is what a phone gets instead of a letterboxed landscape one.
 */
export interface TutorialSourceSet {
  mp4: string;
  poster: string;
  vtt?: string;
  chapters?: string;
  words?: string;
  vertical?: string;
}

interface TutorialVideoPlayerProps {
  src: string;
  posterSrc: string;
  /** Absent for burned-in captions: no <track>, and the skin renders no captions control. */
  subtitlesSrc?: string;
  /** Absent when the video has no chapter marks. */
  chaptersSrc?: string;
  /** Absent when there is no per-word timing sidecar, which disables the caption overlay. */
  wordsSrc?: string;
  /** The portrait cut, shown below 768px. Absent means the landscape one is used at every width. */
  verticalSrc?: string;
  title: string;
  lang: string;
  /**
   * Every locale this video is published in. Absent (or a single entry) hides the
   * language picker and the player behaves exactly as it did before it existed.
   */
  sources?: Record<string, TutorialSourceSet | undefined>;
}

// Shape mirrors the `.words.json` sidecar emitted by `packages/www/scripts/lib/vtt-emit.ts::emitWordTimingsJson`, so extending either side means updating the other.
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

// HTMLVideoElement.currentTime tracks the displayed-frame clock, which trails audio output by ~30-50 ms in most browsers, and our RAF tick adds one more vsync interval (~16 ms) of jitter on top. A small constant look-ahead keeps the active word aligned with what the viewer hears. Leading the audio is worse than trailing, so this stays at or below ~80 ms.
const HIGHLIGHT_LEAD_SEC = 0.06;

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
  // If we are past the last word's end but still inside the cue, keep the last word highlighted so the trailing punctuation doesn't visually "release" the highlight.
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
  // Defensive fallback: a malformed sidecar (or a single-word phrase) lands here with one word entry covering the whole cue. Render as plain text so we don't paint the entire line in the active-word style.
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

/**
 * Keep `.tvp-caption` in step with the subtitles track's mode.
 *
 * The skin's CC button, its captions menu and the `c` hotkey all act on the native track,
 * so the track's mode IS the captions state and its `change` event is the one signal that
 * covers every control. Plyr's `captionsenabled`/`captionsdisabled` events have no Video.js
 * equivalent and are not needed.
 */
function bindCaptionVisibility(video: HTMLVideoElement, caption: HTMLDivElement): () => void {
  const sync = () => {
    caption.classList.toggle('is-hidden-by-cc', subtitlesTrack(video)?.mode !== 'showing');
  };
  sync();
  video.textTracks.addEventListener('change', sync);
  return () => video.textTracks.removeEventListener('change', sync);
}

/**
 * iOS fullscreen is the VIDEO element's own player (`webkitEnterFullscreen`), not the
 * skin's container, so nothing inside the skin -- `.tvp-caption` included -- is drawn.
 * The browser's cue renderer is the only caption there is, so the track is forced to
 * `showing` for the duration and `data-tvp-native-fs` lifts the CSS that hides native
 * cues everywhere else. The viewer's own mode comes back on exit.
 */
function bindNativeFullscreen(video: HTMLVideoElement): { active: () => boolean; off: () => void } {
  let saved: TextTrackMode | null = null;
  const begin = () => {
    video.dataset.tvpNativeFs = '';
    const track = subtitlesTrack(video);
    if (!track) return;
    saved = track.mode;
    track.mode = 'showing';
  };
  const end = () => {
    const track = subtitlesTrack(video);
    if (track && saved !== null) track.mode = saved;
    saved = null;
    delete video.dataset.tvpNativeFs;
  };
  video.addEventListener('webkitbeginfullscreen', begin);
  video.addEventListener('webkitendfullscreen', end);
  return {
    active: () => video.dataset.tvpNativeFs !== undefined,
    off: () => {
      video.removeEventListener('webkitbeginfullscreen', begin);
      video.removeEventListener('webkitendfullscreen', end);
    },
  };
}

/** Playback state carried across a language swap. */
interface PlaybackSnapshot {
  time: number;
  paused: boolean;
  volume: number;
  muted: boolean;
  rate: number;
}

/** Put the viewer back where they were, once the NEW file's metadata is in. */
function applySnapshot(video: HTMLVideoElement, pending: PlaybackSnapshot): void {
  try {
    if (Number.isFinite(pending.time) && pending.time > 0) video.currentTime = pending.time;
    video.volume = pending.volume;
    video.muted = pending.muted;
    video.playbackRate = pending.rate;
    if (!pending.paused) void video.play();
  } catch {
    // A restore is a nicety; never let it break the player.
  }
}

const TutorialVideoPlayer: FC<TutorialVideoPlayerProps> = ({
  src,
  posterSrc,
  subtitlesSrc,
  chaptersSrc,
  wordsSrc,
  verticalSrc,
  title,
  lang,
  sources,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const captionRef = useRef<HTMLDivElement>(null);
  const restoreRef = useRef<PlaybackSnapshot | null>(null);
  // The fetched sidecar is stored WITH the URL it came from. Clearing it on a language change would mean calling setState from an effect body (react-hooks/set-state-in-effect, and a cascading render); carrying the source instead lets the consumer below simply ignore a document that does not belong to the video currently loaded, which also closes the window where the overlay painted the old language's words against the new clock.
  const [words, setWords] = useState<{ src: string; doc: WordsDoc } | null>(null);
  const [activeLang, setActiveLang] = useState<string>(lang);
  // Chrome around the video stays in the PAGE's language; only the media follows the picker.
  const { t } = useTranslation(lang as Language);

  // The picker offers what the manifest published for THIS cast, ordered by the site's own locale list rather than by JSON key order, and disappears below two entries.
  const pickerLangs = useMemo<Language[]>(
    () => (sources ? SUPPORTED_LANGUAGES.filter((l) => Boolean(sources[l])) : []),
    [sources]
  );

  // PORTRAIT BELOW 768px, and chosen in JS rather than by rendering both cuts and hiding one in CSS: two <video> elements would mean two players, two sets of listeners and two caption overlays, only one of them reachable. `matchMedia` gives the same breakpoint with one element.
  /**
   * Snapshot playback BEFORE the state change that remounts the player.
   *
   * React commits DOM mutations before it runs effects, so by the time a cleanup reads
   * `video.currentTime` the new `src` attribute has already been written and the media
   * element load algorithm has already reset the clock to 0. Capturing here is what makes
   * "resume where the viewer was" work at all. Both callers below rebuild the whole subtree, because
   * `activeLang` and `usePortrait` are the React `key`.
   */
  const capturePlayback = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    restoreRef.current = {
      time: video.currentTime,
      paused: video.paused,
      volume: video.volume,
      muted: video.muted,
      rate: video.playbackRate,
    };
  }, []);

  const [isNarrow, setIsNarrow] = useState(false);
  /** Read inside the listener, which must know the PREVIOUS value without re-subscribing. */
  const isNarrowRef = useRef(false);
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)');
    const apply = () => {
      const next = mq.matches;
      // ROTATING A PHONE USED TO RESTART THE VIDEO. `usePortrait` is part of the React `key`, so crossing this breakpoint tears the whole subtree down and builds a new player on the other cut -- and nothing captured the clock on the way through, unlike the language switch. Turning a phone sideways to watch something is the most natural gesture there is, and it sent the viewer back to 00:00.
      if (next === isNarrowRef.current) return;
      isNarrowRef.current = next;
      capturePlayback();
      setIsNarrow(next);
    };
    apply();
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  }, [capturePlayback]);

  // The URLs in play. `sources` is the whole truth once present; the individual props stay the fallback so a page built before the attribute existed still plays.
  const active = sources?.[activeLang];
  const activeLandscape = active?.mp4 ?? src;
  const activeVertical = active?.vertical ?? verticalSrc;
  // ONE named condition, used by the src, the remount key and the class. It was spelled out three times and each repeat is a branch the complexity limit counts.
  const usePortrait = isNarrow && Boolean(activeVertical);
  const activeSrc = usePortrait && activeVertical ? activeVertical : activeLandscape;
  const activePoster = active?.poster ?? posterSrc;
  const activeSubtitles = active?.vtt ?? subtitlesSrc;
  const activeChapters = active?.chapters ?? chaptersSrc;
  const activeWords = active?.words ?? wordsSrc;

  const handleLanguageChange = useCallback(
    (next: Language) => {
      capturePlayback();
      setActiveLang(next);
    },
    [capturePlayback]
  );

  // Fetch words.json once per source change.
  useEffect(() => {
    if (!activeWords) return;
    let cancelled = false;
    fetch(activeWords)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((doc: WordsDoc) => {
        if (!cancelled) setWords({ src: activeWords, doc });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [activeWords]);

  // Null until the sidecar for the CURRENT video has landed.
  //
  // `words &&` FIRST, not optional chaining. With no sidecar at all -- a solution video -- `activeWords` is undefined and so is `words?.src`, so `words?.src === activeWords` is `undefined === undefined`, i.e. TRUE, and the branch then reads `.doc` off null. tsc caught it; at runtime it would have been a crash on every solution page.
  const wordsDoc = words && words.src === activeWords ? words.doc : null;

  // Per-mount wiring of the native element: the snapshot restore, the stored preferences, captions state and iOS fullscreen. The player itself needs no construction or teardown here -- it is React components, and the keyed root below unmounts them.
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    // `readyState` is 0 here because the src attribute changed in the same commit, so the restore waits for metadata of the NEW file.
    const pending = restoreRef.current;
    restoreRef.current = null;
    const restore = () => {
      if (pending) applySnapshot(video, pending);
    };
    if (pending) {
      if (video.readyState >= HTMLMediaElement.HAVE_METADATA) restore();
      else video.addEventListener('loadedmetadata', restore, { once: true });
    }

    const nativeFs = bindNativeFullscreen(video);
    const unbindPrefs = bindPreferences(video, nativeFs.active);
    const caption = captionRef.current;
    const unbindCaption = caption ? bindCaptionVisibility(video, caption) : undefined;

    return () => {
      video.removeEventListener('loadedmetadata', restore);
      nativeFs.off();
      unbindPrefs();
      unbindCaption?.();
    };
    // `activeSrc`, `activeLang` and `usePortrait` are what the root's `key` is built from, so they are what puts a NEW <video> behind videoRef; the effect has to rerun exactly then. They are not read inside, which is why they are named here rather than inferred.
  }, [activeSrc, activeLang, usePortrait]);

  // Word-by-word caption overlay driven by RAF + media events.
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
    // A single tick after scrubbing so the overlay reflects the new position even while paused.
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
    // `activeSrc`, `activeLang` and `usePortrait` build the root's `key`, so a change puts a NEW <video> behind videoRef; the listeners must be rebound to it even when `wordsDoc` is unchanged (the same cue file serves both cuts). They are not read inside.
  }, [wordsDoc, activeSrc, activeLang, usePortrait]);

  const raw = activeLang.split('-')[0].toLowerCase();
  const isSiteLocale = (SUPPORTED_LANGUAGES as readonly string[]).includes(raw);
  const base = (isSiteLocale ? raw : 'en') as Language;
  // getLanguageName, not a local table: the one this component used to carry had twelve entries and no `et`, so Estonian rendered as a raw "ET" next to twelve real names.
  const langLabel = isSiteLocale ? getLanguageName(base) : raw.toUpperCase();
  const selectLabel = t('navigation.selectLanguage');
  // The skin's own labels follow the PAGE locale, like the rest of the chrome; Video.js ships a pack for every site locale and loads the one needed on demand.
  const pageBase = lang.split('-')[0].toLowerCase();

  const toolbar =
    pickerLangs.length > 1 ? (
      <div className="tvp-toolbar">
        <svg
          className="tvp-toolbar-icon"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="9" />
          <path d="M12 3c-2.5 3-2.5 15 0 18M12 3c2.5 3 2.5 15 0 18" />
          <path d="M3 12h18" />
        </svg>
        <LanguageMenu
          variant="flag-name"
          currentLang={base}
          languages={pickerLangs}
          position="top"
          navigationMode="button"
          onLanguageChange={handleLanguageChange}
          persistPreference={false}
          ariaLabel={selectLabel}
        />
      </div>
    ) : null;

  return (
    <div className="tvp-shell">
      {/*
        `key` builds a FRESH player on every language or orientation change. Video.js
        tears itself down on unmount, so this is no longer working around a destroy() that
        swapped in a clone (Plyr's did); it is what discards the old media element, its
        tracks and the store attached to it in one step, and what makes the effects above
        bind to the new <video>.
      */}
      <div
        key={`${activeLang}:${usePortrait ? 'v' : 'h'}`}
        className={`tvp-root${usePortrait ? ' tvp-root--portrait' : ''}`}
      >
        <VideoPlayer poster={activePoster}>
          <I18nProvider locale={pageBase}>
            {/* The overlays are CHILDREN of the skin so they live inside its container,
                which is the element the skin's fullscreen button fullscreens. Anything
                outside it would vanish in fullscreen. */}
            <VideoSkin className="tvp-skin" aria-label={title}>
              <Video
                ref={videoRef}
                src={activeSrc}
                preload="metadata"
                playsInline
                crossOrigin="anonymous"
              >
                {activeSubtitles && (
                  <track
                    kind="subtitles"
                    src={activeSubtitles}
                    srcLang={base}
                    label={langLabel}
                    default
                  />
                )}
                {/* `default` is what the skin reads to segment the time slider and title
                    each chapter; a non-default chapters track is ignored. */}
                {activeChapters && (
                  <track
                    kind="chapters"
                    src={activeChapters}
                    srcLang={base}
                    label={t('video.player.chapters')}
                    default
                  />
                )}
              </Video>
              {activeWords && (
                <div
                  ref={captionRef}
                  className="tvp-caption"
                  aria-live="polite"
                  aria-atomic="true"
                />
              )}
              {toolbar && <div className="tvp-toolbar-overlay">{toolbar}</div>}
            </VideoSkin>
          </I18nProvider>
        </VideoPlayer>
      </div>
    </div>
  );
};

export default TutorialVideoPlayer;
