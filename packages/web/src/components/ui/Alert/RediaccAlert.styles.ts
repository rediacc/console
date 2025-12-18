import { Alert as AntAlert } from 'antd';
import styled from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type { AlertSize, AlertSpacing, AlertVariant } from './RediaccAlert.types';

const ALERT_PADDING_MAP: Record<AlertSize, (theme: StyledTheme) => string> = {
  sm: (theme) => `${theme.spacing.SM}px ${theme.spacing.MD}px`,
  md: (theme) => `${theme.spacing.MD}px ${theme.spacing.LG}px`,
};

export const resolveAlertPadding = (size: AlertSize = 'md', theme: StyledTheme): string => {
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
export const resolveAlertSpacing = (spacing: AlertSpacing | undefined, theme: StyledTheme): number => {
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
    padding: ${({ theme, $size }) => resolveAlertPadding($size, theme)};

    /* Icon color */
    .ant-alert-icon {
    }

    /* Message styling */
    .ant-alert-message {
    }

    /* Description styling */
    .ant-alert-description {
    }

    /* Close button */
    .ant-alert-close-icon {
      &:hover {
      }
    }
  }
`;
