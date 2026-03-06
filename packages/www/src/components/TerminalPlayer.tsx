/**
 * TerminalPlayer — guided asciinema playback with synchronized narration captions/audio.
 */

import type { FC } from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { loadTutorialTimeline } from '../utils/tutorial-timeline';
import { useAudioPreferences } from './terminal-player-audio';
import {
  type AsciinemaPlayerInstance,
  type AsciinemaPlayerModule,
  CaptionLayer,
  type GuidedPhase,
  isPlayingPhase,
  TerminalPlayerView,
  usePlayerSetup,
} from './terminal-player-shell';
import {
  activeWordIndex,
  buildCaptionSegments,
  findStepIndex,
  resolveCastKey,
  stepWordTimings,
  transcriptLabels,
} from './terminal-player-utils';

interface TerminalPlayerProps {
  src: string;
  title?: string;
  lang?: string;
  castKey?: string;
}

type ResumePhase = 'narrating' | 'replaying';

const TerminalPlayer: FC<TerminalPlayerProps> = ({ src, title, lang = 'en', castKey }) => {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const playerRef = useRef<AsciinemaPlayerInstance | null>(null);
  const asciinemaModuleRef = useRef<AsciinemaPlayerModule | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const activeAudioSrcRef = useRef('');

  const [guidedPhase, setGuidedPhase] = useState<GuidedPhase>('idle');
  const [stepIndex, setStepIndex] = useState(0);
  const [playerClockSec, setPlayerClockSec] = useState(0);
  const [narrationClockSec, setNarrationClockSec] = useState(0);

  const [playbackHostEl, setPlaybackHostEl] = useState<HTMLElement | null>(null);
  const [volumeHostEl, setVolumeHostEl] = useState<HTMLElement | null>(null);
  const [ccHostEl, setCcHostEl] = useState<HTMLElement | null>(null);
  const [fullscreenCaptionHostEl, setFullscreenCaptionHostEl] = useState<HTMLElement | null>(null);

  const guidedPhaseRef = useRef<GuidedPhase>('idle');
  const stepIndexRef = useRef(0);
  const resumePhaseRef = useRef<ResumePhase>('narrating');
  const seekSuppressRef = useRef(0);
  const transitionInFlightRef = useRef(false);

  const {
    isAudioMuted,
    isCcEnabled,
    audioVolume,
    setIsAudioMuted,
    setIsCcEnabled,
    setAudioVolume,
  } = useAudioPreferences();

  const resolvedCastKey = useMemo(() => resolveCastKey(src, castKey), [castKey, src]);
  const timeline = useMemo(
    () => loadTutorialTimeline(resolvedCastKey, lang),
    [resolvedCastKey, lang]
  );
  const steps = useMemo(() => timeline?.steps ?? [], [timeline]);
  const labels = transcriptLabels[String(lang).split('-')[0].toLowerCase()] ?? transcriptLabels.en;

  const setPhase = useCallback((phase: GuidedPhase) => {
    guidedPhaseRef.current = phase;
    setGuidedPhase(phase);
  }, []);

  const withSuppressedSeek = useCallback(async <T,>(fn: () => Promise<T>): Promise<T> => {
    seekSuppressRef.current += 1;
    try {
      return await fn();
    } finally {
      window.setTimeout(() => {
        seekSuppressRef.current = Math.max(0, seekSuppressRef.current - 1);
      }, 0);
    }
  }, []);

  const pauseCast = useCallback(async () => {
    const player = playerRef.current;
    if (!player) return;
    try {
      await player.pause();
    } catch {
      // ignore non-fatal player state errors
    }
  }, []);

  const playCast = useCallback(async () => {
    const player = playerRef.current;
    if (!player) return;
    try {
      await player.play();
    } catch {
      // ignore non-fatal player state errors
    }
  }, []);

  const seekCast = useCallback(
    async (timeSec: number) => {
      const player = playerRef.current;
      if (!player) return;
      await withSuppressedSeek(async () => {
        try {
          await player.seek(Math.max(0, timeSec));
        } catch {
          // ignore non-fatal player state errors
        }
      });
    },
    [withSuppressedSeek]
  );

  const startNarratingStep = useCallback(
    async (index: number, offsetSec = 0) => {
      if (steps.length === 0) return;
      const boundedIndex = Math.max(0, Math.min(index, steps.length - 1));
      const step = steps[boundedIndex];
      const audio = audioRef.current;
      if (!audio) return;

      transitionInFlightRef.current = false;
      stepIndexRef.current = boundedIndex;
      setStepIndex(boundedIndex);
      resumePhaseRef.current = 'narrating';
      setPhase('narrating');
      await pauseCast();

      if (activeAudioSrcRef.current !== step.audioSrc) {
        audio.pause();
        audio.src = step.audioSrc;
        audio.load();
        activeAudioSrcRef.current = step.audioSrc;
      }

      const safeOffset = Math.max(0, offsetSec);
      const playFromOffset = () => {
        try {
          audio.currentTime = safeOffset;
        } catch {
          // ignore metadata race
        }
        void audio.play().catch(() => undefined);
      };

      if (audio.readyState >= 1) {
        playFromOffset();
      } else {
        audio.addEventListener('loadedmetadata', playFromOffset, { once: true });
      }
    },
    [pauseCast, setPhase, steps]
  );

  const startReplayStep = useCallback(
    async (index: number) => {
      if (steps.length === 0) return;
      const boundedIndex = Math.max(0, Math.min(index, steps.length - 1));
      const step = steps[boundedIndex];
      const audio = audioRef.current;

      if (audio) audio.pause();

      stepIndexRef.current = boundedIndex;
      setStepIndex(boundedIndex);
      resumePhaseRef.current = 'replaying';
      setPhase('replaying');

      await seekCast(step.replayStartSec);
      await playCast();
    },
    [playCast, seekCast, setPhase, steps]
  );

  const jumpToGuidedBoundary = useCallback(
    async (timeSec: number) => {
      if (steps.length === 0) return;
      const index = findStepIndex(timeSec, steps);
      const step = steps[index];
      await pauseCast();
      await seekCast(step.replayStartSec);
      await startNarratingStep(index, 0);
    },
    [pauseCast, seekCast, startNarratingStep, steps]
  );

  const resumeFromUserPause = useCallback(async () => {
    const resumePhase = resumePhaseRef.current;
    setPhase(resumePhase);
    if (resumePhase === 'narrating') {
      void audioRef.current?.play().catch(() => undefined);
      return;
    }
    await playCast();
  }, [playCast, setPhase]);

  const startFromCurrentBoundary = useCallback(async () => {
    const player = playerRef.current;
    let currentTime = playerClockSec;

    if (player && typeof player.getCurrentTime === 'function') {
      try {
        currentTime = await player.getCurrentTime();
      } catch {
        // ignore and use sampled clock
      }
    }

    const startTime =
      guidedPhaseRef.current === 'ended' ? (steps[0]?.replayStartSec ?? 0) : currentTime;
    await jumpToGuidedBoundary(startTime);
  }, [jumpToGuidedBoundary, playerClockSec, steps]);

  const pauseForUser = useCallback(async () => {
    resumePhaseRef.current = guidedPhaseRef.current === 'narrating' ? 'narrating' : 'replaying';
    audioRef.current?.pause();
    await pauseCast();
    setPhase('pausedByUser');
  }, [pauseCast, setPhase]);

  const onToggleGuidedPlayback = useCallback(async () => {
    const phase = guidedPhaseRef.current;
    if (phase === 'pausedByUser') {
      await resumeFromUserPause();
      return;
    }
    if (phase === 'idle' || phase === 'ended') {
      await startFromCurrentBoundary();
      return;
    }
    await pauseForUser();
  }, [pauseForUser, resumeFromUserPause, startFromCurrentBoundary]);

  const onPlayerSeeked = useCallback(() => {
    if (seekSuppressRef.current > 0 || steps.length === 0) return;
    if (guidedPhaseRef.current === 'pausedByUser') return;

    const player = playerRef.current;
    if (!player || typeof player.getCurrentTime !== 'function') return;

    void player.getCurrentTime().then((currentTime) => {
      void jumpToGuidedBoundary(currentTime);
    });
  }, [jumpToGuidedBoundary, steps.length]);

  const onPlayerPlay = useCallback(() => {
    if (guidedPhaseRef.current === 'replaying') return;
    void pauseCast();
  }, [pauseCast]);

  useEffect(() => {
    audioRef.current ??= new Audio();
    const audio = audioRef.current;
    audio.preload = 'auto';

    return () => {
      audio.pause();
      audioRef.current = null;
    };
  }, []);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.muted = isAudioMuted;
    audio.volume = audioVolume;
  }, [isAudioMuted, audioVolume]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onEnded = () => {
      if (guidedPhaseRef.current !== 'narrating') return;
      void startReplayStep(stepIndexRef.current);
    };

    audio.addEventListener('ended', onEnded);
    return () => audio.removeEventListener('ended', onEnded);
  }, [startReplayStep]);

  usePlayerSetup({
    src,
    containerRef,
    playerRef,
    asciinemaModuleRef,
    setPlaybackHostEl,
    setVolumeHostEl,
    setCcHostEl,
    onPlayerSeeked,
    onPlayerPlay,
  });

  useEffect(() => {
    const timer = window.setInterval(async () => {
      const player = playerRef.current;
      if (!player || typeof player.getCurrentTime !== 'function') return;

      let currentTime = 0;
      try {
        currentTime = await player.getCurrentTime();
      } catch {
        return;
      }

      setPlayerClockSec(currentTime);
      if (guidedPhaseRef.current !== 'replaying' || steps.length === 0) return;

      const currentStep = steps[Math.min(stepIndexRef.current, steps.length - 1)];
      if (currentTime < currentStep.replayEndSec - 0.06) return;
      if (transitionInFlightRef.current) return;

      transitionInFlightRef.current = true;
      await pauseCast();

      const nextIndex = stepIndexRef.current + 1;
      if (nextIndex >= steps.length) {
        setPhase('ended');
        transitionInFlightRef.current = false;
        return;
      }

      await startNarratingStep(nextIndex, 0);
    }, 90);

    return () => window.clearInterval(timer);
  }, [pauseCast, setPhase, startNarratingStep, steps]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      const audio = audioRef.current;
      setNarrationClockSec(audio ? audio.currentTime : 0);
    }, 90);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const onFullscreenChange = () => {
      const fullscreenElement =
        document.fullscreenElement ??
        (document as Document & { webkitFullscreenElement?: Element }).webkitFullscreenElement;
      const container = containerRef.current;
      const isPlayerFullscreen =
        fullscreenElement instanceof HTMLElement &&
        !!container &&
        (fullscreenElement.contains(container) || container.contains(fullscreenElement));
      setFullscreenCaptionHostEl(isPlayerFullscreen ? fullscreenElement : null);
    };

    document.addEventListener('fullscreenchange', onFullscreenChange);
    document.addEventListener('webkitfullscreenchange', onFullscreenChange as EventListener);
    return () => {
      document.removeEventListener('fullscreenchange', onFullscreenChange);
      document.removeEventListener('webkitfullscreenchange', onFullscreenChange as EventListener);
    };
  }, []);

  useEffect(() => {
    const globalWindow = window as Window & {
      __tutorialDebug?: {
        seekToSec: (timeSec: number) => void;
        getState: () => { phase: GuidedPhase; step: number; playerClockSec: number };
      };
    };

    globalWindow.__tutorialDebug = {
      seekToSec: (timeSec: number) => {
        void jumpToGuidedBoundary(timeSec);
      },
      getState: () => ({
        phase: guidedPhaseRef.current,
        step: stepIndexRef.current,
        playerClockSec,
      }),
    };

    return () => {
      if (globalWindow.__tutorialDebug) delete globalWindow.__tutorialDebug;
    };
  }, [jumpToGuidedBoundary, playerClockSec]);

  useEffect(() => {
    const currentStep = steps.length > 0 ? steps[Math.min(stepIndex, steps.length - 1)] : null;
    if (!currentStep) {
      setPhase('idle');
      return;
    }

    stepIndexRef.current = stepIndex;

    if (guidedPhaseRef.current === 'idle') {
      void seekCast(currentStep.replayStartSec);
    }
  }, [seekCast, setPhase, stepIndex, steps]);

  const activeStep = steps.length > 0 ? steps[Math.min(stepIndex, steps.length - 1)] : null;
  const timings = activeStep ? stepWordTimings(activeStep) : [];
  const segments = activeStep ? buildCaptionSegments(activeStep.narrationText, timings) : [];
  const highlightedWord =
    guidedPhase === 'narrating' ? activeWordIndex(narrationClockSec, timings) : -1;

  const captionNodeClassName = fullscreenCaptionHostEl
    ? 'terminal-player-caption-layer terminal-player-caption-layer--fullscreen'
    : 'terminal-player-caption-layer';

  const captionNode =
    activeStep && isCcEnabled ? (
      <CaptionLayer
        captionNodeClassName={captionNodeClassName}
        transcriptLabel={labels.transcript}
        segments={segments}
        highlightedWord={highlightedWord}
      />
    ) : null;

  const rootClassName = `terminal-tutorial ${isPlayingPhase(guidedPhase) ? 'is-playing' : 'is-paused'} is-ui-visible`;

  return (
    <TerminalPlayerView
      rootClassName={rootClassName}
      wrapperRef={wrapperRef}
      title={title}
      containerRef={containerRef}
      captionNode={captionNode}
      fullscreenCaptionHostEl={fullscreenCaptionHostEl}
      showControls={Boolean(activeStep)}
      playbackHostEl={playbackHostEl}
      volumeHostEl={volumeHostEl}
      ccHostEl={ccHostEl}
      guidedPhase={guidedPhase}
      onToggleGuidedPlayback={() => {
        void onToggleGuidedPlayback();
      }}
      isAudioMuted={isAudioMuted}
      audioVolume={audioVolume}
      isCcEnabled={isCcEnabled}
      setIsAudioMuted={setIsAudioMuted}
      setIsCcEnabled={setIsCcEnabled}
      setAudioVolume={setAudioVolume}
      guidedStep={stepIndex}
    />
  );
};

export default TerminalPlayer;
