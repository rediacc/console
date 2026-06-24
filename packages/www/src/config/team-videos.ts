/**
 * Configuration for team member video and photo media assets.
 * Generic structure — keyed by member slug so any team member can be added.
 */

export interface TeamVideo {
  src: string;
  poster: string;
  duration: number;
  durationLabel: string;
}

export interface TeamMemberMedia {
  slug: string;
  name: string;
  role: string;
  email?: string;
  photos: Record<string, string>;
  videos: Record<string, TeamVideo>;
}

export const AUDIO_LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ru', 'zh'] as const;
export const AUDIO_FALLBACK: Record<string, string> = { ar: 'en', tr: 'en' };
export const ALL_CAPTION_LANGUAGES = [
  'en',
  'de',
  'es',
  'fr',
  'ja',
  'ru',
  'zh',
  'ar',
  'tr',
] as const;

export const TEAM_MEMBERS: Record<string, TeamMemberMedia> = {};

export function getCaptionPath(member: string, videoKey: string, lang: string): string {
  return `/media/${member}/captions/${videoKey}.${lang}.vtt`;
}

export function getAudioPath(member: string, videoKey: string, lang: string): string {
  return `/media/${member}/audio/${videoKey}.${lang}.mp3`;
}

export function getMemberPhoto(member: string, pose: string): string {
  const memberData = TEAM_MEMBERS[member] as TeamMemberMedia | undefined;
  return memberData?.photos[pose] ?? `/media/${member}/photos/${pose}.jpg`;
}

export function getMemberVideo(member: string, videoKey: string): TeamVideo | undefined {
  const memberData = TEAM_MEMBERS[member] as TeamMemberMedia | undefined;
  return memberData?.videos[videoKey];
}
