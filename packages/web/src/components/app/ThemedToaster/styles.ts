import styled from 'styled-components';
import { DESIGN_TOKENS } from '@/utils/styleConstants';
import type { DefaultToastOptions } from 'react-hot-toast';

export const ToasterContainer = styled.div`
  position: relative;
  z-index: ${({ theme }) => theme.zIndex.NOTIFICATION};
`;

const baseToastStyles = {
  borderRadius: `${DESIGN_TOKENS.BORDER_RADIUS.LG}px`,
  fontSize: `${DESIGN_TOKENS.FONT_SIZE.SM}px`,
  fontWeight: DESIGN_TOKENS.FONT_WEIGHT.MEDIUM,
  padding: `${DESIGN_TOKENS.SPACING.MD}px`,
  minHeight: `${DESIGN_TOKENS.DIMENSIONS.FORM_CONTROL_HEIGHT}px`,
  display: 'flex',
  alignItems: 'center',
} as const;

const getToneStyles = (tone: 'success' | 'error' | 'info' | 'warning') => {
  const toneMap = {
    success: {
      color: 'var(--color-success)',
      background: 'var(--color-bg-primary)',
    },
    error: {
      color: 'var(--color-error)',
      background: 'var(--color-bg-primary)',
    },
    info: {
      color: 'var(--color-info)',
      background: 'var(--color-bg-primary)',
    },
    warning: {
      color: 'var(--color-warning)',
      background: 'var(--color-bg-primary)',
    },
  };

  return toneMap[tone];
};

export const createToastOptions = (): DefaultToastOptions => {
  const surface = 'var(--color-bg-primary)';

  return {
    duration: 4000,
    style: {
      ...baseToastStyles,
      background: surface,
      color: 'var(--color-text-primary)',
    },
    success: {
      iconTheme: {
        primary: 'var(--color-success)',
        secondary: surface,
      },
      style: {
        ...baseToastStyles,
        ...getToneStyles('success'),
      },
    },
    error: {
      iconTheme: {
        primary: 'var(--color-error)',
        secondary: surface,
      },
      style: {
        ...baseToastStyles,
        ...getToneStyles('error'),
      },
    },
    loading: {
      iconTheme: {
        primary: 'var(--color-info)',
        secondary: surface,
      },
      style: {
        ...baseToastStyles,
        ...getToneStyles('info'),
      },
    },
    custom: {
      style: {
        ...baseToastStyles,
        ...getToneStyles('warning'),
      },
    },
  };
};
