import { useEffect } from 'react';
import { featureFlags } from '@/config/featureFlags';
import { showMessage } from '@/utils/messages';

const getPowerModeToggleMessage = (newState: boolean, onLocalhost: boolean): string => {
  if (onLocalhost) {
    return newState
      ? 'Localhost Mode - All features enabled'
      : 'Localhost Mode - All features disabled';
  }
  return newState ? 'Advanced options enabled' : 'Advanced options disabled';
};

export const usePowerModeShortcut = (onToggle: (newState: boolean) => void) => {
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if (!e.ctrlKey || !e.shiftKey || e.key !== 'E') return;
      e.preventDefault();
      const onLocalhost =
        window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
      const newState = featureFlags.togglePowerMode();
      onToggle(newState);
      showMessage('info', getPowerModeToggleMessage(newState, onLocalhost));
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [onToggle]);
};
