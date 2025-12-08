import { Alert as AntAlert } from 'antd';
import styled, { css } from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type { AlertSize, AlertSpacing, AlertVariant } from './RediaccAlert.types';

type AlertTokenSet = { bg: string; border: string; color: string };

export const resolveAlertVariantTokens = (
  variant: AlertVariant = 'info',
  theme: StyledTheme
): AlertTokenSet => {
  switch (variant) {
    case 'success':
      return {
        bg: theme.colors.bgSuccess,
        border: theme.colors.success,
        color: theme.colors.success,
      };
    case 'warning':
      return {
        bg: theme.colors.bgWarning,
        border: theme.colors.warning,
        color: theme.colors.warning,
      };
    case 'error':
      return { bg: theme.colors.bgError, border: theme.colors.error, color: theme.colors.error };
    case 'neutral':
      return {
        bg: theme.colors.bgSecondary,
        border: theme.colors.borderSecondary,
        color: theme.colors.textSecondary,
      };
    case 'info':
    default:
      return { bg: theme.colors.bgInfo, border: theme.colors.info, color: theme.colors.info };
  }
};

export const resolveAlertPadding = (theme: StyledTheme, size: AlertSize = 'md'): string => {
  switch (size) {
    case 'sm':
      return `${theme.spacing.SM}px ${theme.spacing.MD}px`;
    case 'md':
    default:
      return `${theme.spacing.MD}px ${theme.spacing.LG}px`;
  }
};

// Map our variant to antd type
export const mapVariantToAntType = (
  variant: AlertVariant
): 'info' | 'warning' | 'error' | 'success' => {
  if (variant === 'neutral') return 'info';
  return variant;
};

// Resolve spacing to margin-bottom pixels
export const resolveAlertSpacing = (theme: StyledTheme, spacing?: AlertSpacing): number => {
  switch (spacing) {
    case 'compact':
      return theme.spacing.SM; // 8px
    case 'default':
      return theme.spacing.MD; // 16px
    case 'spacious':
      return theme.spacing.LG; // 24px
    case 'none':
    default:
      return 0;
  }
};

export const StyledRediaccAlert = styled(AntAlert).withConfig({
  shouldForwardProp: (prop) =>
    !['$variant', '$size', '$rounded', '$banner', '$spacing'].includes(prop),
})<{
  $variant: AlertVariant;
  $size: AlertSize;
  $rounded?: boolean;
  $banner?: boolean;
  $spacing?: AlertSpacing;
}>`
  && {
    background-color: ${({ theme, $variant }) => resolveAlertVariantTokens($variant, theme).bg};
    border: 1px solid ${({ theme, $variant }) => resolveAlertVariantTokens($variant, theme).border};
    color: ${({ theme }) => theme.colors.textPrimary};
    padding: ${({ theme, $size }) => resolveAlertPadding(theme, $size)};

    /* Spacing (margin-bottom) */
    ${({ theme, $spacing }) => $spacing && css`margin-bottom: ${resolveAlertSpacing(theme, $spacing)}px;`}

    /* Border radius */
    border-radius: ${({ theme, $rounded = true, $banner }) =>
      $banner ? '0' : ($rounded ? `${theme.borderRadius.LG}px` : '0')};

    /* Icon color */
    .ant-alert-icon {
      color: ${({ theme, $variant }) => resolveAlertVariantTokens($variant, theme).color};
    }

    /* Message styling */
    .ant-alert-message {
      color: ${({ theme }) => theme.colors.textPrimary};
    }

    /* Description styling */
    .ant-alert-description {
      color: ${({ theme }) => theme.colors.textSecondary};
    }

    /* Close button */
    .ant-alert-close-icon {
      color: ${({ theme }) => theme.colors.textTertiary};

      &:hover {
        color: ${({ theme }) => theme.colors.textSecondary};
      }
    }
  }
`;
