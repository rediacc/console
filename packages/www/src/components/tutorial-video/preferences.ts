/**
 * The viewer's player preferences: volume, mute, playback rate and captions on/off.
 *
 * Video.js 10 persists nothing (its migration guide lists `storage` under "Known gaps"),
 * so the player keeps them itself, in ONE localStorage entry shared by every player on the
 * site. They are language independent on purpose: a viewer who turned captions off, or
 * set 1.5x, keeps that across a language switch, a portrait/landscape flip and the next
 * page.
 *
 * Everything is read and written through the native <video> element rather than the
 * Video.js store. The store's actions throw until it attaches to the media, while the
 * element is there from the first commit, and the store follows native changes through
 * media events anyway, so its UI stays in step.
 */

/** The localStorage key. Plyr's former key is migrated once, then removed. */
export const PREFS_KEY = 'tvp-prefs';
const LEGACY_PLYR_KEY = 'plyr-tutorial';

export interface PlayerPrefs {
  volume?: number;
  muted?: boolean;
  rate?: number;
  captions?: boolean;
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    // Private mode or blocked cookies: preferences simply do not persist.
    return null;
  }
}

function sanitize(raw: unknown): PlayerPrefs {
  if (!raw || typeof raw !== 'object') return {};
  const r = raw as Record<string, unknown>;
  const out: PlayerPrefs = {};
  if (typeof r.volume === 'number' && r.volume >= 0 && r.volume <= 1) out.volume = r.volume;
  if (typeof r.muted === 'boolean') out.muted = r.muted;
  if (typeof r.rate === 'number' && r.rate > 0 && r.rate <= 4) out.rate = r.rate;
  if (typeof r.captions === 'boolean') out.captions = r.captions;
  return out;
}

/**
 * The ONE-TIME migration from Plyr's entry, which held `volume`, `muted`, `speed`,
 * `captions` and `language`. `language` is dropped: the picker, not storage, decides
 * which language plays. The legacy key is removed so the migration cannot run twice.
 */
function migrateLegacy(store: Storage): PlayerPrefs | null {
  const legacy = store.getItem(LEGACY_PLYR_KEY);
  if (legacy === null) return null;
  store.removeItem(LEGACY_PLYR_KEY);
  try {
    const old = JSON.parse(legacy) as Record<string, unknown>;
    return sanitize({ ...old, rate: old.speed });
  } catch {
    return {};
  }
}

export function readPrefs(): PlayerPrefs {
  const store = storage();
  if (!store) return {};
  try {
    const raw = store.getItem(PREFS_KEY);
    if (raw !== null) return sanitize(JSON.parse(raw));
    const migrated = migrateLegacy(store);
    if (migrated) {
      store.setItem(PREFS_KEY, JSON.stringify(migrated));
      return migrated;
    }
  } catch {
    // A malformed entry reads as "no preferences", never as a broken player.
  }
  return {};
}

export function writePrefs(patch: PlayerPrefs): void {
  const store = storage();
  if (!store) return;
  try {
    store.setItem(PREFS_KEY, JSON.stringify({ ...readPrefs(), ...patch }));
  } catch {
    // Quota or a blocked store: skip persistence.
  }
}

/** The one subtitles/captions track a player carries, if any. */
export function subtitlesTrack(video: HTMLVideoElement): TextTrack | undefined {
  return Array.from(video.textTracks).find((t) => t.kind === 'subtitles' || t.kind === 'captions');
}

/**
 * Apply the stored preferences to `video` and save later changes.
 *
 * The preferences are read ONCE, here, before any event can fire. The `default` track's
 * automatic selection raises a textTracks `change` before metadata arrives, and saving
 * that would overwrite a stored "captions off" before it was ever applied, so nothing is
 * saved until the stored values have been put back. Captions are applied on
 * `loadedmetadata`, by which point the browser's automatic track selection has run and
 * can no longer flip the track back on.
 *
 * `isNativeFullscreen` reports the iOS case where the player forces the track to
 * `showing` for the native renderer; that is not the viewer's choice and is not saved.
 */
export function bindPreferences(
  video: HTMLVideoElement,
  isNativeFullscreen: () => boolean
): () => void {
  const prefs = readPrefs();
  let applied = false;

  if (prefs.volume !== undefined) video.volume = prefs.volume;
  if (prefs.muted !== undefined) video.muted = prefs.muted;
  if (prefs.rate !== undefined) video.playbackRate = prefs.rate;

  const applyCaptions = () => {
    const track = subtitlesTrack(video);
    if (track && prefs.captions === false) track.mode = 'disabled';
    applied = true;
  };
  if (video.readyState >= HTMLMediaElement.HAVE_METADATA) applyCaptions();
  else video.addEventListener('loadedmetadata', applyCaptions, { once: true });

  const onVolume = () => {
    if (applied) writePrefs({ volume: video.volume, muted: video.muted });
  };
  const onRate = () => {
    if (applied) writePrefs({ rate: video.playbackRate });
  };
  const onTracks = () => {
    if (!applied || isNativeFullscreen()) return;
    const track = subtitlesTrack(video);
    if (track) writePrefs({ captions: track.mode === 'showing' });
  };
  video.addEventListener('volumechange', onVolume);
  video.addEventListener('ratechange', onRate);
  video.textTracks.addEventListener('change', onTracks);

  return () => {
    video.removeEventListener('loadedmetadata', applyCaptions);
    video.removeEventListener('volumechange', onVolume);
    video.removeEventListener('ratechange', onRate);
    video.textTracks.removeEventListener('change', onTracks);
  };
}
