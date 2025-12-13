import { Tag as AntTag } from 'antd';
import styled from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type { TagSize, TagVariant } from './RediaccTag.types';

type TagTokenSet = {
  bg: string;
  color: string;
  border: string;
};

type TagTokenKeys = {
  bg: keyof StyledTheme['colors'];
  color: keyof StyledTheme['colors'];
  border: keyof StyledTheme['colors'];
};

const TAG_VARIANT_MAP: Record<TagVariant, TagTokenKeys> = {
  primary: { bg: 'primaryBg', color: 'primary', border: 'primary' },
  secondary: { bg: 'bgPrimary', color: 'secondary', border: 'secondary' },
  success: { bg: 'bgSuccess', color: 'success', border: 'success' },
  warning: { bg: 'bgWarning', color: 'warning', border: 'warning' },
  error: { bg: 'bgError', color: 'error', border: 'error' },
  info: { bg: 'bgInfo', color: 'info', border: 'info' },
  neutral: { bg: 'bgSecondary', color: 'textSecondary', border: 'borderSecondary' },
  default: { bg: 'bgPrimary', color: 'textPrimary', border: 'borderSecondary' },
};

/**
 * Resolves color tokens for each tag variant
 */
export const resolveRediaccTagVariantTokens = (
  variant: TagVariant = 'default',
  theme: StyledTheme
): TagTokenSet => {
  const keys = TAG_VARIANT_MAP[variant] || TAG_VARIANT_MAP.default;
  return {
    bg: theme.colors[keys.bg],
    color: theme.colors[keys.color],
    border: theme.colors[keys.border],
  };
};

const TAG_FONT_SIZE_MAP: Record<TagSize, keyof StyledTheme['fontSize']> = {
  sm: 'XS',
  md: 'SM',
  lg: 'MD',
};

/**
 * Resolves font size for each tag size
 */
export const resolveRediaccTagFontSize = (theme: StyledTheme, size: TagSize = 'md'): number => {
  return theme.fontSize[TAG_FONT_SIZE_MAP[size] || TAG_FONT_SIZE_MAP.md];
};

const TAG_PADDING_MAP: Record<TagSize, (theme: StyledTheme) => string> = {
  sm: (theme) => `0 ${theme.spacing.XS}px`,
  md: (theme) => `${theme.spacing.XS}px ${theme.spacing.SM}px`,
  lg: (theme) => `${theme.spacing.SM}px ${theme.spacing.MD}px`,
};

/**
 * Resolves padding for each tag size
 */
export const resolveRediaccTagPadding = (theme: StyledTheme, size: TagSize = 'md'): string => {
  return (TAG_PADDING_MAP[size] || TAG_PADDING_MAP.md)(theme);
};

const TAG_RADIUS_MAP: Record<TagSize, keyof StyledTheme['borderRadius']> = {
  sm: 'SM',
  md: 'MD',
  lg: 'LG',
};

/**
 * Resolves border radius for each tag size
 */
export const resolveRediaccTagRadius = (theme: StyledTheme, size: TagSize = 'md'): number => {
  return theme.borderRadius[TAG_RADIUS_MAP[size] || TAG_RADIUS_MAP.md];
};

/**
 * Unified Tag styled component
 */
export const StyledRediaccTag = styled(AntTag)<{
  $variant: TagVariant;
  $size: TagSize;
  $borderless: boolean;
  $compact?: boolean;
  $emphasized?: boolean;
}>`
  && {
    display: inline-flex;
    align-items: center;
    gap: ${({ theme }) => theme.spacing.XS}px;
    padding: ${({ theme, $size, $compact }) =>
      $compact ? `0 ${theme.spacing.XS}px` : resolveRediaccTagPadding(theme, $size)};
    border-radius: ${({ theme, $size, $compact }) =>
      $compact ? theme.borderRadius.SM : resolveRediaccTagRadius(theme, $size)}px;
    font-size: ${({ theme, $size, $compact }) =>
      $compact ? theme.fontSize.XS : resolveRediaccTagFontSize(theme, $size)}px;
    font-weight: ${({ theme, $emphasized }) =>
      $emphasized ? theme.fontWeight.SEMIBOLD : theme.fontWeight.MEDIUM};
    line-height: ${({ theme }) => theme.lineHeight.TIGHT};
    transition: ${({ theme }) => theme.transitions.DEFAULT};

    /* Variant-specific colors */
    background-color: ${({ theme, $variant }) => resolveRediaccTagVariantTokens($variant, theme).bg};
    color: ${({ theme, $variant }) => resolveRediaccTagVariantTokens($variant, theme).color};
    border: ${({ $borderless, theme, $variant }) =>
      $borderless ? 'none' : `1px solid ${resolveRediaccTagVariantTokens($variant, theme).border}`};

    /* Ensure icon inherits color */
    .anticon {
      color: inherit;
    }

    /* Close icon styling */
    .ant-tag-close-icon {
      margin-left: ${({ theme }) => theme.spacing.XS}px;
      font-size: ${({ theme }) => theme.fontSize.XS}px;
      color: inherit;
      opacity: 0.7;
      transition: opacity 0.2s ease;

      &:hover {
        opacity: 1;
      }
    }
  }
`;
