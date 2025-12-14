import type { CSSProperties } from 'react';
import type { StyledTheme } from '@/styles/styledTheme';
import type { TooltipVariant } from './RediaccTooltip.types';

type TooltipTokenSet = {
  bg: string;
  color: string;
  borderColor: string;
};

type TooltipTokenKeys = {
  bg: keyof StyledTheme['colors'] | 'tooltipBg';
  color: keyof StyledTheme['colors'];
  borderColor: keyof StyledTheme['colors'] | 'transparent';
};

const TOOLTIP_VARIANT_MAP: Record<TooltipVariant, TooltipTokenKeys> = {
  default: { bg: 'tooltipBg', color: 'textInverse', borderColor: 'transparent' },
  info: { bg: 'bgInfo', color: 'textPrimary', borderColor: 'info' },
  warning: { bg: 'bgWarning', color: 'textPrimary', borderColor: 'warning' },
  error: { bg: 'bgError', color: 'textPrimary', borderColor: 'error' },
  success: { bg: 'bgSuccess', color: 'textPrimary', borderColor: 'success' },
};

/**
 * Resolves color tokens for each tooltip variant
 */
export const resolveTooltipVariantTokens = (
  variant: TooltipVariant = 'default',
  theme: StyledTheme,
  tooltipBg: string
): TooltipTokenSet => {
  const keys = TOOLTIP_VARIANT_MAP[variant] || TOOLTIP_VARIANT_MAP.default;
  return {
    bg: keys.bg === 'tooltipBg' ? tooltipBg : theme.colors[keys.bg as keyof StyledTheme['colors']],
    color: theme.colors[keys.color],
    borderColor:
      keys.borderColor === 'transparent'
        ? 'transparent'
        : theme.colors[keys.borderColor as keyof StyledTheme['colors']],
  };
};

/**
 * Generate overlay styles for tooltip content
 * Applied via overlayInnerStyle prop due to portal rendering
 */
export const getTooltipOverlayStyle = (
  variant: TooltipVariant,
  theme: StyledTheme,
  tooltipBg: string
): CSSProperties => {
  const tokens = resolveTooltipVariantTokens(variant, theme, tooltipBg);

  return {
    backgroundColor: tokens.bg,
    color: tokens.color,
    border: tokens.borderColor !== 'transparent' ? `1px solid ${tokens.borderColor}` : undefined,
    borderRadius: theme.borderRadius.MD,
    fontSize: theme.fontSize.SM,
    padding: `${theme.spacing.XS}px ${theme.spacing.SM}px`,
  };
};
