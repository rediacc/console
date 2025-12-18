import type { StyledTheme } from './styledTheme';

/**
 * Token set for components with background, border, and color
 */
export type VariantTokenSet = {
  bg: string;
  color: string;
  border: string;
};

/**
 * Keys pointing to theme color tokens
 */
export type VariantTokenKeys = {
  bg: keyof StyledTheme['colors'];
  color: keyof StyledTheme['colors'];
  border: keyof StyledTheme['colors'];
};

/**
 * Status Variant Type
 * Shared across Tag, Badge, and Alert components
 */
export type StatusVariant = 'success' | 'warning' | 'error' | 'info' | 'neutral';

/**
 * Status Variant Map
 * Defines standard status color mappings used across all components
 */
export const STATUS_VARIANT_MAP: Record<StatusVariant, VariantTokenKeys> = {
  success: { bg: 'bgSuccess', color: 'success', border: 'success' },
  warning: { bg: 'bgWarning', color: 'warning', border: 'warning' },
  error: { bg: 'bgError', color: 'error', border: 'error' },
  info: { bg: 'bgInfo', color: 'info', border: 'info' },
  neutral: { bg: 'bgPrimary', color: 'textPrimary', border: 'borderPrimary' },
} as const;

/**
 * Tag Variant Type
 * CONSOLIDATED: Removed 'secondary' (1 use) and 'default' (4 uses)
 * Use 'neutral' instead of 'secondary' or 'default'
 */
export type TagVariant = 'primary' | StatusVariant;

/**
 * Tag Variant Map
 * Maps tag variants to theme color tokens
 */
export const TAG_VARIANT_MAP: Record<TagVariant, VariantTokenKeys> = {
  primary: { bg: 'primaryBg', color: 'primary', border: 'primary' },
  ...STATUS_VARIANT_MAP,
} as const;

/**
 * Tag Semantic Presets
 * Maps domain concepts to visual variants
 */
export type TagPreset = 'team' | 'machine' | 'bridge' | 'region';

export const TAG_PRESET_MAP: Record<TagPreset, TagVariant> = {
  team: 'success',
  machine: 'primary',
  bridge: 'info',
  region: 'warning',
} as const;

/**
 * Badge Variant Type
 * CONSOLIDATED: Removed 'muted' (0 uses)
 */
export type BadgeVariant = 'default' | 'primary' | StatusVariant;

/**
 * Badge Color Map
 * Simpler map - badges only need a single color
 */
export const BADGE_COLOR_MAP: Record<BadgeVariant, keyof StyledTheme['colors']> = {
  default: 'primary',
  primary: 'primary',
  success: 'success',
  warning: 'warning',
  error: 'error',
  info: 'info',
  neutral: 'textSecondary',
} as const;

/**
 * Alert Variant Type
 * Kept all variants - all are used
 */
export type AlertVariant = StatusVariant;

/**
 * Alert Variant Map
 * Uses the status variant map directly
 */
export const ALERT_VARIANT_MAP: Record<AlertVariant, VariantTokenKeys> = STATUS_VARIANT_MAP;

/**
 * Shared Variant Token Resolver
 * Resolves variant token keys to actual theme color values
 */
export const resolveVariantTokens = (
  variantKeys: VariantTokenKeys,
  theme: StyledTheme
): VariantTokenSet => ({
  bg: theme.colors[variantKeys.bg],
  color: theme.colors[variantKeys.color],
  border: theme.colors[variantKeys.border],
});

/**
 * Badge-specific resolver (maintains backward compatibility)
 * Badges only use a single color, not a full token set
 */
export const resolveBadgeColor = (
  variant: BadgeVariant = 'default',
  theme: StyledTheme
): string => {
  return theme.colors[BADGE_COLOR_MAP[variant] || BADGE_COLOR_MAP.default];
};
