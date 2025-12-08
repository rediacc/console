import { Tag as AntTag } from 'antd';
import styled from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type { TagVariant, TagSize } from './RediaccTag.types';

type TagTokenSet = {
  bg: string;
  color: string;
  border: string;
};

/**
 * Resolves color tokens for each tag variant
 */
export const resolveRediaccTagVariantTokens = (
  variant: TagVariant = 'default',
  theme: StyledTheme
): TagTokenSet => {
  switch (variant) {
    case 'primary':
      return {
        bg: theme.colors.primaryBg,
        color: theme.colors.primary,
        border: theme.colors.primary,
      };
    case 'secondary':
      return {
        bg: theme.colors.bgPrimary,
        color: theme.colors.secondary,
        border: theme.colors.secondary,
      };
    case 'success':
      return {
        bg: theme.colors.bgSuccess,
        color: theme.colors.success,
        border: theme.colors.success,
      };
    case 'warning':
      return {
        bg: theme.colors.bgWarning,
        color: theme.colors.warning,
        border: theme.colors.warning,
      };
    case 'error':
      return {
        bg: theme.colors.bgError,
        color: theme.colors.error,
        border: theme.colors.error,
      };
    case 'info':
      return {
        bg: theme.colors.bgInfo,
        color: theme.colors.info,
        border: theme.colors.info,
      };
    case 'neutral':
      return {
        bg: theme.colors.bgSecondary,
        color: theme.colors.textSecondary,
        border: theme.colors.borderSecondary,
      };
    case 'default':
    default:
      return {
        bg: theme.colors.bgPrimary,
        color: theme.colors.textPrimary,
        border: theme.colors.borderSecondary,
      };
  }
};

/**
 * Resolves font size for each tag size
 */
export const resolveRediaccTagFontSize = (theme: StyledTheme, size: TagSize = 'md'): number => {
  switch (size) {
    case 'sm':
      return theme.fontSize.CAPTION; // XS font
    case 'lg':
      return theme.fontSize.BASE; // BASE font
    case 'md':
    default:
      return theme.fontSize.SM; // SM font
  }
};

/**
 * Resolves padding for each tag size
 */
export const resolveRediaccTagPadding = (theme: StyledTheme, size: TagSize = 'md'): string => {
  switch (size) {
    case 'sm':
      return `0 ${theme.spacing.XS}px`;
    case 'lg':
      return `${theme.spacing.SM}px ${theme.spacing.MD}px`;
    case 'md':
    default:
      return `${theme.spacing.XS}px ${theme.spacing.SM}px`;
  }
};

/**
 * Resolves border radius for each tag size
 */
export const resolveRediaccTagRadius = (theme: StyledTheme, size: TagSize = 'md'): number => {
  switch (size) {
    case 'sm':
      return theme.borderRadius.SM;
    case 'lg':
      return theme.borderRadius.LG;
    case 'md':
    default:
      return theme.borderRadius.MD;
  }
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
      $compact ? theme.fontSize.CAPTION : resolveRediaccTagFontSize(theme, $size)}px;
    font-weight: ${({ theme, $emphasized }) =>
      $emphasized ? theme.fontWeight.SEMIBOLD : theme.fontWeight.MEDIUM};
    line-height: 1.2;
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
      font-size: ${({ theme }) => theme.fontSize.CAPTION}px;
      color: inherit;
      opacity: 0.7;
      transition: opacity 0.2s ease;

      &:hover {
        opacity: 1;
      }
    }
  }
`;
