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

export const TEAM_MEMBERS: Record<string, TeamMemberMedia> = {
  founder: {
    slug: 'founder',
    name: 'Muhammed',
    role: 'Founder',
    email: 'muhammed@rediacc.com',
    photos: {
      headshot: '/media/founder/photos/headshot.jpg',
      'headshot-sm': '/media/founder/photos/headshot-sm.jpg',
      'headshot-xs': '/media/founder/photos/headshot-xs.jpg',
      standing: '/media/founder/photos/standing.jpg',
      casual: '/media/founder/photos/casual.jpg',
      working: '/media/founder/photos/working.jpg',
    },
    videos: {
      'hero-intro': {
        src: '/media/founder/videos/hero-intro.mp4',
        poster: '/media/founder/posters/hero-intro.jpg',
        duration: 30,
        durationLabel: '0:30',
      },
      'our-story': {
        src: '/media/founder/videos/our-story.mp4',
        poster: '/media/founder/posters/our-story.jpg',
        duration: 150,
        durationLabel: '2:30',
      },
      'persona-devops': {
        src: '/media/founder/videos/persona-devops.mp4',
        poster: '/media/founder/posters/persona-devops.jpg',
        duration: 15,
        durationLabel: '0:15',
      },
      'persona-ctos': {
        src: '/media/founder/videos/persona-ctos.mp4',
        poster: '/media/founder/posters/persona-ctos.jpg',
        duration: 15,
        durationLabel: '0:15',
      },
      'persona-ceos': {
        src: '/media/founder/videos/persona-ceos.mp4',
        poster: '/media/founder/posters/persona-ceos.jpg',
        duration: 15,
        durationLabel: '0:15',
      },
      'persona-ai-agents': {
        src: '/media/founder/videos/persona-ai-agents.mp4',
        poster: '/media/founder/posters/persona-ai-agents.jpg',
        duration: 15,
        durationLabel: '0:15',
      },
    },
  },
};

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
