/**
 * SolutionVideoPlayer -- the solution-page video with a language picker.
 *
 * The section used to be pure Astro emitting two bare `<video>` elements, which gave the
 * viewer no way to reach the other twelve narrations even though all thirteen are
 * published. This island is the smallest surface that adds one: native controls are kept
 * (no Plyr here, unlike the tutorial player), and the only interactive part is the picker.
 *
 * Two `<video>` elements, not one, because the portrait and landscape cuts are genuinely
 * different files and the choice between them is made in CSS by viewport. Both carry
 * `preload="none"`, so the hidden one costs nothing until it is played.
 *
 * Captions are burned into each localized file, so there is no `<track>` and no caption
 * plumbing: switching language switches the visible subtitles with the audio.
 */

import type { FC } from 'react';
import { useCallback, useMemo, useRef, useState } from 'react';
import { SUPPORTED_LANGUAGES } from '../../i18n/language-utils';
import type { Language } from '../../i18n/types';
import type { SolutionVideoUrls } from '../../utils/solution-video';
import LanguageMenu from '../LanguageMenu';
import '../../styles/solution-video.css';

interface SolutionVideoPlayerProps {
  /** The page's language. Decides which video plays first, and nothing else. */
  lang: Language;
  /** locale -> the three URLs for that locale, resolved from the manifest at build time. */
  sources: Record<string, SolutionVideoUrls | undefined>;
  /** Accessible name for the players, already translated by the Astro parent. */
  playLabel: string;
  /** Accessible name for the picker, already translated by the Astro parent. */
  selectLanguageLabel: string;
}

/** Playback state carried across a language swap, per video element. */
interface PlaybackSnapshot {
  time: number;
  paused: boolean;
  volume: number;
  muted: boolean;
  rate: number;
}

function snapshot(video: HTMLVideoElement | null): PlaybackSnapshot | null {
  if (!video) return null;
  return {
    time: video.currentTime,
    paused: video.paused,
    volume: video.volume,
    muted: video.muted,
    rate: video.playbackRate,
  };
}

/**
 * Put the viewer back where they were after the `src` attribute changed.
 *
 * `preload="none"` means the new file is not fetched until something asks for it, so there
 * is no `loadedmetadata` to wait for on a paused player. Assigning `currentTime` while
 * `readyState` is HAVE_NOTHING sets the default playback start position instead, which the
 * browser honours once the file does load. The one-shot listener re-applies it if the
 * browser landed somewhere else.
 */
function restore(video: HTMLVideoElement | null, prev: PlaybackSnapshot | null): void {
  if (!video || !prev || prev.time <= 0) return;
  video.volume = prev.volume;
  video.muted = prev.muted;
  video.playbackRate = prev.rate;
  try {
    video.currentTime = prev.time;
  } catch {
    // Ignored: some browsers reject a seek before the media element has any duration.
  }
  const settle = () => {
    if (Math.abs(video.currentTime - prev.time) > 0.5) video.currentTime = prev.time;
    video.playbackRate = prev.rate;
  };
  video.addEventListener('loadedmetadata', settle, { once: true });
  if (!prev.paused) void video.play();
}

const SolutionVideoPlayer: FC<SolutionVideoPlayerProps> = ({
  lang,
  sources,
  playLabel,
  selectLanguageLabel,
}) => {
  const landscapeRef = useRef<HTMLVideoElement>(null);
  const verticalRef = useRef<HTMLVideoElement>(null);
  const [activeLang, setActiveLang] = useState<Language>(lang);

  // Site order, not JSON key order, and only the locales this slug was published in.
  const pickerLangs = useMemo<Language[]>(
    () => SUPPORTED_LANGUAGES.filter((l) => Boolean(sources[l])),
    [sources]
  );

  const active = sources[activeLang] ?? sources[lang];

  const handleLanguageChange = useCallback((next: Language) => {
    // Snapshot BEFORE the state change: React commits the new `src` attribute before it
    // runs any effect, and writing `src` resets the clock to zero, so a cleanup-time read
    // would always report 0.
    const prevLandscape = snapshot(landscapeRef.current);
    const prevVertical = snapshot(verticalRef.current);
    setActiveLang(next);
    // The refs point at the same two elements after the re-render (same position, same
    // type), so restoring in a microtask lands on the elements that just took the new src.
    queueMicrotask(() => {
      restore(landscapeRef.current, prevLandscape);
      restore(verticalRef.current, prevVertical);
    });
  }, []);

  if (!active) return null;

  return (
    // A fragment, not a wrapper div: the layout box is `.sp-hero-media` in SPHero.astro,
    // and an extra styled-by-nothing element here is exactly what
    // check:ci-css-dom-refs reports.
    <>
      {pickerLangs.length > 1 && (
        <div className="sp-video-toolbar">
          <svg
            className="sp-video-toolbar-icon"
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
            currentLang={activeLang}
            languages={pickerLangs}
            position="top"
            navigationMode="button"
            onLanguageChange={handleLanguageChange}
            persistPreference={false}
            ariaLabel={selectLanguageLabel}
          />
        </div>
      )}
      <video
        ref={landscapeRef}
        className="sp-video-player sp-video-landscape"
        controls
        preload="none"
        playsInline
        poster={active.poster}
        src={active.landscape}
        aria-label={playLabel}
      />
      <video
        ref={verticalRef}
        className="sp-video-player sp-video-vertical"
        controls
        preload="none"
        playsInline
        poster={active.poster}
        src={active.vertical}
        aria-label={playLabel}
      />
    </>
  );
};

export default SolutionVideoPlayer;
