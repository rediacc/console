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
import { baseLocale, mountLanguagePane } from './tutorial-video/language-pane';
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
  title,
  lang,
  sources,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const chapterOverlayRef = useRef<HTMLDivElement>(null);
  const captionRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<Plyr | null>(null);
  const restoreRef = useRef<PlaybackSnapshot | null>(null);
  // Did the in-menu language pane build? False means the in-frame overlay stays up.
  const [menuMounted, setMenuMounted] = useState(false);
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
  // ONE named condition, used by the src, the remount key and the class. It was spelled
  // out three times and each repeat is a branch the complexity limit counts.
  const usePortrait = isNarrow && Boolean(activeVertical);
  const activeSrc = usePortrait && activeVertical ? activeVertical : activeLandscape;
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
  // NORMALISE BEFORE COMPARING. `activeLang` is whatever the mount was given, which can be
  // a full tag like `en-GB`, while `pickerLangs` holds bare site locales. Comparing the raw
  // value marked the wrong entry as current and made every later comparison wrong.
  const activeBase = baseLocale(activeLang);

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
      // THE RATIO HAS TO BE TOLD TO PLYR, not just to the outer box.
      // `.tvp-root--portrait` sets `aspect-ratio: 9 / 16` on the container, but Plyr
      // builds its own wrapper and defaults it to 16:9, so the portrait cut was
      // letterboxed inside it: measured at 390px the mount was a correct 327x581 while
      // the <video> inside was 327x184 with `object-fit: contain`, leaving 397px of dead
      // black under a sliver of picture. The file was right (1080x1920) and the container
      // was right; only Plyr's wrapper disagreed.
      ratio: usePortrait ? '9:16' : '16:9',
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
      // THE LANGUAGE PICKER IS NOT IN THIS MENU, and that was measured, not assumed.
      // Plyr's `quality` pane is the only extension point its settings menu offers and it
      // is numeric by nature: with `forced` options plus an `onChange`, every click came
      // back as min(options). Clicking the radio whose DOM value was "4" delivered 0, and
      // after moving to 1-based values, clicking "5" delivered 1. `setQuality` snaps
      // through `closest()` (plyr.mjs:8460) because its `options.includes()` disagrees
      // with the very list `setQualityMenu` rendered the rows from (plyr.mjs:2154). A
      // control that plays a different language than the one clicked is worse than none,
      // so the picker is rendered INSIDE the player frame instead, over the video, using
      // the switch that already works.
      // `language` IS NOT A PLYR TYPE, and it does not have to be. `config.settings` is
      // iterated verbatim with no allowlist (plyr.mjs:2645): every entry gets a home row,
      // a back-buttoned pane, keyboard shortcuts and the height animation for free. Only
      // POPULATING the pane is Plyr's job for its own three types, so that is the part we
      // do, in `ready` below. The label must come from `i18n`, because `i18n.get` returns
      // '' for an unknown key and the row would render blank.
      settings: [
        ...(activeSubtitles ? ['captions'] : []),
        'speed',
        ...(pickerLangs.length > 1 ? ['language'] : []),
      ],
      captions: { active: Boolean(activeSubtitles), language: activeLang, update: true },
      i18n: { language: t('navigation.selectLanguage') },
      keyboard: { focused: true, global: false },
      tooltips: { controls: true, seek: true },
      storage: { enabled: true, key: PLYR_STORAGE_KEY },
      iconUrl: '/assets/plyr.svg',
    });
    playerRef.current = player;

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
    // POPULATE THE LANGUAGE PANE Plyr built but does not fill.
    //
    // Located by DOM id rather than through `player.elements.settings`, which Plyr's own
    // types do not declare. Every lookup is guarded and a miss is a no-op: if a Plyr
    // upgrade changes the id convention, the row simply never appears and the in-frame
    // overlay below stays visible, so a viewer is never left with no picker at all.
    player.on('ready', () => {
      detachChapterOverlay = mountChapterOverlay();
      mountCaptionOverlay();
      // The overlay is the FALLBACK, not the default: it shows only when the pane could
      // not be built, so there is exactly one picker on screen either way.
      setMenuMounted(
        mountLanguagePane({
          video,
          controlClass:
            (player as unknown as { config?: { classNames?: { control?: string } } }).config
              ?.classNames?.control ?? '',
          langs: pickerLangs,
          active: activeBase,
          hasCaptions: Boolean(activeSubtitles),
          onPick: handleLanguageChange,
        })
      );
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
    // Every added dep is STABLE, so this still rebuilds Plyr only on a real source or
    // language change: `pickerLangs` is a useMemo over `sources`, `t` is memoised on the
    // page locale, `handleLanguageChange` is a useCallback with no deps, and `activeBase`
    // and `activeSubtitles` are primitives derived from `activeLang`, which is already
    // here. They arrived with the in-menu picker and were left out; CI lints with
    // `--max-warnings 0`, so an exhaustive-deps warning is a failing build, and calling it
    // pre-existing was wrong -- it is on lines written this session.
  }, [
    activeSrc,
    activeLang,
    activeBase,
    activeSubtitles,
    handleLanguageChange,
    pickerLangs,
    t,
    // `usePortrait` now feeds Plyr's `ratio`. It moves in lockstep with `activeSrc`
    // today, but exhaustive-deps is a failing build here (`--max-warnings 0`), and a
    // value read inside the effect belongs in the list regardless of what it correlates
    // with.
    usePortrait,
  ]);

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
        key={`${activeLang}:${usePortrait ? 'v' : 'h'}`}
        className={`tvp-root${usePortrait ? ' tvp-root--portrait' : ''}`}
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
        {/* INSIDE the frame, over the video, rather than floating above it. This is what
            "integrated to the player" means here: Plyr's own settings menu cannot host a
            language list correctly (see the comment on the Plyr config above), so the
            control that works is placed within the player's own box. */}
        {toolbar && !menuMounted && <div className="tvp-toolbar-overlay">{toolbar}</div>}
      </div>
    </div>
  );
};

export default TutorialVideoPlayer;
