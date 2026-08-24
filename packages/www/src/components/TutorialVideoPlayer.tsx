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

import Plyr from 'plyr';
import type { FC } from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getLanguageName, SUPPORTED_LANGUAGES } from '../i18n/language-utils';
import { useTranslation } from '../i18n/react';
import type { Language } from '../i18n/types';
import LanguageMenu from './LanguageMenu';
import 'plyr/dist/plyr.css';
import '../styles/tutorial-video.css';

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
  /** Absent for burned-in captions: no <track>, and Plyr drops its CC button. */
  subtitlesSrc?: string;
  /** Absent when the video has no chapter marks. */
  chaptersSrc?: string;
  /** Absent when there is no per-word timing sidecar, which disables the caption overlay. */
  wordsSrc?: string;
  /** The portrait cut, shown below 768px. Absent means the landscape one is used at every width. */
  verticalSrc?: string;
  /**
   * Put the language picker INSIDE Plyr's settings menu, beside Captions and Speed,
   * instead of in the toolbar above the player. Opt-in per caller: solution videos have
   * no caption track, so their settings pane has room and nothing to conflict with.
   */
  inPlayerLanguage?: boolean;
  title: string;
  lang: string;
  /**
   * Every locale this video is published in. Absent (or a single entry) hides the
   * language picker and the player behaves exactly as it did before it existed.
   */
  sources?: Record<string, TutorialSourceSet | undefined>;
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

/** Plyr's persisted-preferences key. One entry holds volume, speed, captions and language. */
const PLYR_STORAGE_KEY = 'plyr-tutorial';

/**
 * Point Plyr's stored caption language at the language we are about to mount.
 *
 * `captions.setup` reads `storage.get('language')` FIRST and only falls back to
 * `config.captions.language` (plyr.js:3085), so a value left there by an earlier player
 * wins over the one we pass. Every instance here carries exactly ONE subtitles track, so a
 * stale value means `languageExists` is false in `captions.update`, Plyr sets a language it
 * has no track for, and the CC button switches itself off -- which also hides our word
 * overlay, since that listens for `captionsdisabled`.
 *
 * Writing the key before construction keeps the volume/speed/captions-on-off preferences
 * shared (they are language independent) while making the language dimension follow the
 * picker. Doing it through `player.language = lang` after construction is NOT equivalent:
 * on `ready` the track metadata Plyr matches against is still being populated, and a miss
 * there calls `captions.toggle(false, false)`, which persists captions:false.
 */
function alignPlyrCaptionLanguage(lang: string): void {
  try {
    const raw = window.localStorage.getItem(PLYR_STORAGE_KEY);
    const stored = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
    stored.language = lang;
    window.localStorage.setItem(PLYR_STORAGE_KEY, JSON.stringify(stored));
  } catch {
    // localStorage can be unavailable (private mode, blocked cookies). Plyr degrades to
    // config.captions.language in that case, which is already the value we want.
  }
}

/** Playback state carried across a language swap. */
interface PlaybackSnapshot {
  time: number;
  paused: boolean;
  volume: number;
  muted: boolean;
  rate: number;
}

const TutorialVideoPlayer: FC<TutorialVideoPlayerProps> = ({
  src,
  posterSrc,
  subtitlesSrc,
  chaptersSrc,
  wordsSrc,
  verticalSrc,
  inPlayerLanguage,
  title,
  lang,
  sources,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const chapterOverlayRef = useRef<HTMLDivElement>(null);
  const captionRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<Plyr | null>(null);
  const restoreRef = useRef<PlaybackSnapshot | null>(null);
  // True only while Plyr is constructing. See the quality config below: Plyr restores a
  // STORED quality during init and that restore is not a user action.
  const settlingRef = useRef(true);
  // The fetched sidecar is stored WITH the URL it came from. Clearing it on a language
  // change would mean calling setState from an effect body (react-hooks/set-state-in-effect,
  // and a cascading render); carrying the source instead lets the consumer below simply
  // ignore a document that does not belong to the video currently loaded, which also closes
  // the window where the overlay painted the old language's words against the new clock.
  const [words, setWords] = useState<{ src: string; doc: WordsDoc } | null>(null);
  const [activeLang, setActiveLang] = useState<string>(lang);
  // Chrome around the video stays in the PAGE's language; only the media follows the picker.
  const { t } = useTranslation(lang as Language);

  // The picker offers what the manifest published for THIS cast, ordered by the site's own
  // locale list rather than by JSON key order, and disappears below two entries.
  const pickerLangs = useMemo<Language[]>(
    () => (sources ? SUPPORTED_LANGUAGES.filter((l) => Boolean(sources[l])) : []),
    [sources]
  );

  // PORTRAIT BELOW 768px, and chosen in JS rather than by rendering both cuts and hiding
  // one in CSS. Two <video> elements was how the solution player did it; with Plyr that
  // would mean two player instances, two sets of listeners and two caption overlays, only
  // one of them reachable. `matchMedia` gives the same breakpoint with one element.
  const [isNarrow, setIsNarrow] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)');
    const apply = () => setIsNarrow(mq.matches);
    apply();
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  }, []);

  // The URLs in play. `sources` is the whole truth once present; the individual props
  // stay the fallback so a page built before the attribute existed still plays.
  const active = sources?.[activeLang];
  const activeLandscape = active?.mp4 ?? src;
  const activeVertical = active?.vertical ?? verticalSrc;
  const activeSrc = isNarrow && activeVertical ? activeVertical : activeLandscape;
  const activePoster = active?.poster ?? posterSrc;
  const activeSubtitles = active?.vtt ?? subtitlesSrc;
  const activeChapters = active?.chapters ?? chaptersSrc;
  const activeWords = active?.words ?? wordsSrc;

  /**
   * Snapshot playback BEFORE the state change, not in the Plyr effect's cleanup.
   *
   * React commits DOM mutations before it runs effects, so by the time cleanup reads
   * `video.currentTime` the new `src` attribute has already been written and the media
   * element load algorithm has already reset the clock to 0. Capturing here is what makes
   * "switch language, keep your place" work at all.
   */
  // THE IN-PLAYER PICKER, built on Plyr's FORCED-QUALITY path rather than on a custom
  // menu. `config.quality.forced` makes `getQualityOptions()` return our own list verbatim
  // (plyr.mjs:980) and `quality.onChange` takes the switch over entirely, without touching
  // any <source> (plyr.mjs:1016). Both are supported config, not a repurposing hack.
  //
  // The option VALUES have to be numbers: Plyr labels each one through
  // `i18n.get('qualityLabel.' + value)` (plyr.mjs:2130). So the options are indices into
  // pickerLangs and the labels come from a per-instance i18n map.
  // NORMALISE BEFORE INDEXING. `activeLang` is whatever the mount was given, which can be
  // a full tag like `en-GB`, and `pickerLangs` holds bare site locales. An unmatched tag
  // fell through `Math.max(0, -1)` to index 0, so an English page opened with the FIRST
  // locale checked (Deutsch, since the list is ordered by native name) and every later
  // comparison was against the wrong language. Same normalisation the render below uses.
  const activeBase = (() => {
    const r = activeLang.split('-')[0].toLowerCase();
    return ((SUPPORTED_LANGUAGES as readonly string[]).includes(r) ? r : 'en') as Language;
  })();
  const langIndex = Math.max(0, pickerLangs.indexOf(activeBase));
  const inPlayerPicker = Boolean(inPlayerLanguage) && pickerLangs.length > 1;

  const handleLanguageChange = useCallback((next: Language) => {
    const video = videoRef.current;
    if (video) {
      restoreRef.current = {
        time: video.currentTime,
        paused: video.paused,
        volume: video.volume,
        muted: video.muted,
        rate: video.playbackRate,
      };
    }
    setActiveLang(next);
  }, []);

  // Fetch words.json once per source change.
  useEffect(() => {
    if (!activeWords) return;
    let cancelled = false;
    const url = activeWords;
    fetch(url)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((doc: WordsDoc) => {
        if (!cancelled) setWords({ src: url, doc });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [activeWords]);

  // Null until the sidecar for the CURRENT video has landed.
  //
  // `words &&` FIRST, not optional chaining. With no sidecar at all -- a solution video --
  // `activeWords` is undefined and so is `words?.src`, so `words?.src === activeWords` is
  // `undefined === undefined`, i.e. TRUE, and the branch then reads `.doc` off null. tsc
  // caught it; at runtime it would have been a crash on every solution page.
  const wordsDoc = words && words.src === activeWords ? words.doc : null;

  // Plyr lifecycle + chapter overlay.
  useEffect(() => {
    const video = videoRef.current;
    settlingRef.current = true;
    // THE OVERLAY IS OPTIONAL, THE PLAYER IS NOT. This guard used to demand the chapter
    // overlay node as well, so a video with no chapters -- every solution video -- would
    // return before constructing Plyr and render as a bare <video> with no controls at
    // all. The overlay's own mount below already handles its absence.
    const chapterOverlay = chapterOverlayRef.current;
    if (!video) return;
    // Capture the caption node at mount so the cleanup closure does not read
    // captionRef.current after render (react-hooks/exhaustive-deps); the node
    // is rendered once and stable for the life of this effect.
    const captionNode = captionRef.current;

    alignPlyrCaptionLanguage(activeLang);

    // A CC BUTTON WITH NO TRACK IS DEAD UI, so the captions control and the captions
    // settings pane are dropped when there is no subtitles file. The solution videos burn
    // their captions into the media, so this is their normal state, not a degraded one.
    const player = new Plyr(video, {
      controls: [
        'play-large',
        'play',
        'progress',
        'current-time',
        'duration',
        'mute',
        'volume',
        ...(activeSubtitles ? ['captions'] : []),
        'settings',
        'pip',
        'fullscreen',
      ],
      settings: [
        ...(activeSubtitles ? ['captions'] : []),
        'speed',
        ...(inPlayerPicker ? ['quality'] : []),
      ],
      captions: { active: Boolean(activeSubtitles), language: activeLang, update: true },
      ...(inPlayerPicker
        ? {
            quality: {
              forced: true,
              // No `selected` here: Plyr's own types do not declare it even though the
              // runtime reads `config.selected`, and the explicit `player.quality`
              // assignment below is the stronger override anyway.
              default: langIndex + 1,
              options: pickerLangs.map((_l, i) => i + 1),
              // DEFERRED PAST THE CLICK. This fires from inside Plyr's own open menu,
              // and the language change unmounts that menu with it (the subtree is keyed
              // on the language). Letting the click handler unwind first is what keeps
              // Plyr from operating on nodes React has already discarded.
              // READ THE ITEM PLYR CHECKED, NOT THE ARGUMENT IT PASSES.
              //
              // Measured, twice, with the handler instrumented: clicking the radio whose
              // DOM value is "4" delivered 0, and after moving to 1-based options,
              // clicking "5" delivered 1. Whatever is clicked, the argument arrives as
              // min(options) -- `setQuality` is snapping through `closest()`, so its
              // `options.includes()` test is failing on values the menu itself rendered
              // from the same list.
              //
              // The click handler sets `menuItem.checked = true` BEFORE dispatching
              // (plyr.mjs:1817), so the checked radio in the quality pane is the truth
              // and it is right there in the DOM. Reading it sidesteps the snap entirely.
              onChange: (value: number) => {
                const pane = videoRef.current
                  ?.closest('.plyr')
                  ?.querySelector('[id$="-quality"] [role="menuitemradio"][aria-checked="true"]');
                const clicked = Number((pane as HTMLInputElement | null)?.value);
                if (Number.isFinite(clicked) && clicked > 0) value = clicked;
                // IGNORE PLYR'S OWN INIT-TIME RESTORE. Measured live: after switching one
                // solution video to German, the NEXT solution page loaded
                // `de/backup-verification.mp4` instead of English, because Plyr reads a
                // stored `quality` during construction (plyr.mjs:8460) from a key every
                // player on the site shares, and that read reaches this handler as though
                // a viewer had clicked. The explicit assignment below arrives too late to
                // undo it, so the restore is refused rather than corrected.
                if (settlingRef.current) return;
                const next = pickerLangs[value - 1];
                if (!next || next === activeBase) return;
                window.setTimeout(() => handleLanguageChange(next), 0);
              },
            },
            i18n: {
              quality: t('navigation.selectLanguage'),
              qualityLabel: Object.fromEntries(pickerLangs.map((l, i) => [i + 1, getLanguageName(l)])),
            },
          }
        : {}),
      keyboard: { focused: true, global: false },
      tooltips: { controls: true, seek: true },
      storage: { enabled: true, key: PLYR_STORAGE_KEY },
      iconUrl: '/assets/plyr.svg',
    });
    playerRef.current = player;
    // OVERRIDE THE STORED QUALITY. Plyr persists `quality` (plyr.mjs:8479) and reads it
    // back at init from a storage key EVERY player on the site shares, then snaps an
    // unknown value to the nearest option with `closest()` and only a debug warning
    // (plyr.mjs:8460-8468). A stored index 9 on a three-language video therefore selects
    // a DIFFERENT language, silently. The explicit assignment is `input` in that
    // `.find(is.number)` chain, which outranks the stored value.
    if (inPlayerPicker) {
      player.quality = langIndex + 1;
      // AND OVERWRITE WHAT IS STORED, not just what is selected. Refusing the init-time
      // restore was not enough on its own: measured live, a page opened in English, and
      // the first click on `Français` still produced `de/...`, because the stale German
      // index was re-applied from storage after the guard had lifted. Storage is per
      // PLAYER, not per setting, so it cannot be disabled for this axis alone without
      // losing volume, speed and captions with it. Writing the current language's index
      // back makes every later restore a no-op instead.
      const store = (player as unknown as { storage?: { set(o: Record<string, unknown>): void } })
        .storage;
      store?.set({ quality: langIndex + 1 });
    }
    settlingRef.current = false;

    const onSeek = (sec: number) => {
      player.currentTime = sec;
    };

    const mountChapterOverlay = () => {
      if (!chapterOverlay) return;
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

    // Put the viewer back where they were. The snapshot is taken in
    // handleLanguageChange; `readyState` is 0 here because the src attribute changed in the
    // same commit, so the restore waits for metadata of the NEW file.
    const pending = restoreRef.current;
    restoreRef.current = null;
    const applyRestore = () => {
      if (!pending) return;
      try {
        if (Number.isFinite(pending.time) && pending.time > 0) video.currentTime = pending.time;
        video.volume = pending.volume;
        video.muted = pending.muted;
        video.playbackRate = pending.rate;
        if (!pending.paused) void video.play();
      } catch {
        // A restore is a nicety; never let it break the player.
      }
    };
    if (pending) {
      if (video.readyState >= HTMLMediaElement.HAVE_METADATA) applyRestore();
      else video.addEventListener('loadedmetadata', applyRestore, { once: true });
    }

    let detachChapterOverlay: (() => void) | undefined;
    player.on('ready', () => {
      detachChapterOverlay = mountChapterOverlay();
      mountCaptionOverlay();
    });

    return () => {
      video.removeEventListener('loadedmetadata', applyRestore);
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
  }, [activeSrc, activeLang]);

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
        return JSON.parse(window.localStorage.getItem(PLYR_STORAGE_KEY) ?? '{}');
      } catch {
        return {};
      }
    })() as { captions?: boolean };
    if (stored.captions === false) disable();

    return () => {
      video.removeEventListener('captionsenabled', enable);
      video.removeEventListener('captionsdisabled', disable);
    };
    // activeLang, because the <video> below is keyed on it: after a switch this effect's
    // captured node is a detached one, and the CC button would stop reaching the overlay.
  }, [activeLang]);

  const raw = activeLang.split('-')[0].toLowerCase();
  const isSiteLocale = (SUPPORTED_LANGUAGES as readonly string[]).includes(raw);
  const base = (isSiteLocale ? raw : 'en') as Language;
  // getLanguageName, not a local table: the one this component used to carry had twelve
  // entries and no `et`, so Estonian rendered as a raw "ET" next to twelve real names.
  const langLabel = isSiteLocale ? getLanguageName(base) : raw.toUpperCase();
  const selectLabel = t('navigation.selectLanguage');

  return (
    <div className="tvp-shell">
      {pickerLangs.length > 1 && !inPlayerPicker && (
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
      )}
      {/*
        `key` forces React to build a FRESH subtree on every language change, and it is
        load-bearing rather than a re-render hint.

        Plyr.destroy() does not hand the element back: it snapshots a CLONE of the media at
        construction time and, on teardown, replaces its whole `.plyr` container with that
        clone. The node React created is left detached, so React's tree and the document
        disagree from then on -- measured live: after one switch, `.tvp-root` held a bare
        `<video>` still pointing at the previous language's mp4, `.plyr` was gone entirely,
        and the src/poster/track attributes React wrote landed on a node nobody could see.
        Discarding the whole subtree is what keeps the two in step.
      */}
      <div
        key={`${activeLang}:${isNarrow && activeVertical ? 'v' : 'h'}`}
        className={`tvp-root${isNarrow && activeVertical ? ' tvp-root--portrait' : ''}`}
        aria-label={title}
      >
        <video
          ref={videoRef}
          src={activeSrc}
          poster={activePoster}
          preload="metadata"
          playsInline
          crossOrigin="anonymous"
          data-poster={activePoster}
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
          {activeChapters && (
            <track kind="chapters" src={activeChapters} srcLang={base} label="Chapters" />
          )}
        </video>
        {/* Both overlays are refs the effects above guard on, so omitting them when there
            is nothing to paint costs those effects nothing and leaves the DOM clean. */}
        {activeChapters && (
          <div ref={chapterOverlayRef} className="tvp-chapter-overlay" aria-hidden="true" />
        )}
        {activeWords && (
          <div ref={captionRef} className="tvp-caption" aria-live="polite" aria-atomic="true" />
        )}
      </div>
    </div>
  );
};

export default TutorialVideoPlayer;
