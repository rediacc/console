import { Alert as AntAlert } from 'antd';
import styled, { css } from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type { AlertSize, AlertSpacing, AlertVariant } from './RediaccAlert.types';

type AlertTokenSet = { bg: string; border: string; color: string };

type AlertTokenKeys = {
  bg: keyof StyledTheme['colors'];
  border: keyof StyledTheme['colors'];
  color: keyof StyledTheme['colors'];
};

const ALERT_VARIANT_MAP: Record<AlertVariant, AlertTokenKeys> = {
  success: { bg: 'bgSuccess', border: 'success', color: 'success' },
  warning: { bg: 'bgWarning', border: 'warning', color: 'warning' },
  error: { bg: 'bgError', border: 'error', color: 'error' },
  neutral: { bg: 'bgSecondary', border: 'borderSecondary', color: 'textSecondary' },
  info: { bg: 'bgInfo', border: 'info', color: 'info' },
};

export const resolveAlertVariantTokens = (
  variant: AlertVariant = 'info',
  theme: StyledTheme
): AlertTokenSet => {
  const keys = ALERT_VARIANT_MAP[variant] || ALERT_VARIANT_MAP.info;
  return {
    bg: theme.colors[keys.bg],
    border: theme.colors[keys.border],
    color: theme.colors[keys.color],
  };
};

const ALERT_PADDING_MAP: Record<AlertSize, (theme: StyledTheme) => string> = {
  sm: (theme) => `${theme.spacing.SM}px ${theme.spacing.MD}px`,
  md: (theme) => `${theme.spacing.MD}px ${theme.spacing.LG}px`,
};

export const resolveAlertPadding = (theme: StyledTheme, size: AlertSize = 'md'): string => {
  return (ALERT_PADDING_MAP[size] || ALERT_PADDING_MAP.md)(theme);
};

// Map our variant to antd type
export const mapVariantToAntType = (
  variant: AlertVariant
): 'info' | 'warning' | 'error' | 'success' => {
  if (variant === 'neutral') return 'info';
  return variant;
};

const ALERT_SPACING_MAP: Record<AlertSpacing, keyof StyledTheme['spacing'] | 0> = {
  compact: 'SM',
  default: 'MD',
  spacious: 'LG',
  none: 0,
};

// Resolve spacing to margin-bottom pixels
export const resolveAlertSpacing = (theme: StyledTheme, spacing?: AlertSpacing): number => {
  if (!spacing) return 0;
  const value = ALERT_SPACING_MAP[spacing];
  return typeof value === 'number' ? value : theme.spacing[value];
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
