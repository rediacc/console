import styled from 'styled-components';
import type { DefaultToastOptions } from 'react-hot-toast';
import { DESIGN_TOKENS } from '@/utils/styleConstants';

export const ToasterContainer = styled.div`
  position: relative;
  z-index: ${({ theme }) => theme.zIndex.NOTIFICATION};
`;

const baseToastStyles = {
  borderRadius: `${DESIGN_TOKENS.BORDER_RADIUS.LG}px`,
  fontSize: `${DESIGN_TOKENS.FONT_SIZE.SM}px`,
  fontWeight: DESIGN_TOKENS.FONT_WEIGHT.MEDIUM,
  padding: `${DESIGN_TOKENS.SPACING.MD}px`,
  minHeight: `${DESIGN_TOKENS.DIMENSIONS.INPUT_HEIGHT}px`,
  display: 'flex',
  alignItems: 'center',
} as const;

const getToneStyles = (tone: 'success' | 'error' | 'info' | 'warning', isDark: boolean) => {
  const toneMap = {
    success: {
      color: 'var(--color-success)',
      background: isDark ? 'var(--color-bg-secondary)' : 'var(--color-bg-primary)',
    },
    error: {
      color: 'var(--color-error)',
      background: isDark ? 'var(--color-bg-secondary)' : 'var(--color-bg-primary)',
    },
    info: {
      color: 'var(--color-info)',
      background: isDark ? 'var(--color-bg-secondary)' : 'var(--color-bg-primary)',
    },
    warning: {
      color: 'var(--color-warning)',
      background: isDark ? 'var(--color-bg-secondary)' : 'var(--color-bg-primary)',
    },
  };

  return toneMap[tone];
};

export const createToastOptions = (mode: 'light' | 'dark'): DefaultToastOptions => {
  const isDark = mode === 'dark';
  const surface = isDark ? 'var(--color-bg-secondary)' : 'var(--color-bg-primary)';
  const borderColor = 'var(--color-border-primary)';

  return {
    duration: 4000,
    style: {
      ...baseToastStyles,
      background: surface,
      color: 'var(--color-text-primary)',
      border: `1px solid ${borderColor}`,
      boxShadow: 'var(--shadow-lg)',
    },
    success: {
      iconTheme: {
        primary: 'var(--color-success)',
        secondary: surface,
      },
      style: {
        ...baseToastStyles,
        ...getToneStyles('success', isDark),
        border: `2px solid var(--color-success)`,
      },
    },
    error: {
      iconTheme: {
        primary: 'var(--color-error)',
        secondary: surface,
      },
      style: {
        ...baseToastStyles,
        ...getToneStyles('error', isDark),
        border: `2px solid var(--color-error)`,
      },
    },
    loading: {
      iconTheme: {
        primary: 'var(--color-info)',
        secondary: surface,
      },
      style: {
        ...baseToastStyles,
        ...getToneStyles('info', isDark),
        border: `2px solid var(--color-info)`,
      },
    },
    custom: {
      style: {
        ...baseToastStyles,
        ...getToneStyles('warning', isDark),
        border: `2px solid var(--color-warning)`,
      },
    },
  };
};
