import { Badge as AntBadge } from 'antd';
import styled from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type { BadgeSize, BadgeVariant } from './RediaccBadge.types';

const BADGE_COLOR_MAP: Record<BadgeVariant, keyof StyledTheme['colors']> = {
  primary: 'primary',
  success: 'success',
  warning: 'warning',
  error: 'error',
  info: 'info',
  muted: 'textTertiary',
  default: 'primary',
};

// Get badge color based on variant
export const resolveBadgeColor = (
  variant: BadgeVariant = 'default',
  theme: StyledTheme
): string => {
  return theme.colors[BADGE_COLOR_MAP[variant] || BADGE_COLOR_MAP.default];
};

const BADGE_SIZE_MAP: Record<BadgeSize, number> = {
  sm: 16,
  md: 20,
};

// Get badge size in pixels
export const resolveBadgeSize = (size: BadgeSize = 'md'): number => {
  return BADGE_SIZE_MAP[size] || BADGE_SIZE_MAP.md;
};

const BADGE_FONT_SIZE_MAP: Record<BadgeSize, (theme: StyledTheme) => number> = {
  sm: (theme) => theme.fontSize.XS - 2,
  md: (theme) => theme.fontSize.XS,
};

// Get badge font size
export const resolveBadgeFontSize = (theme: StyledTheme, size: BadgeSize = 'md'): number => {
  return (BADGE_FONT_SIZE_MAP[size] || BADGE_FONT_SIZE_MAP.md)(theme);
};

export const StyledRediaccBadge = styled(AntBadge)<{
  $variant: BadgeVariant;
  $size: BadgeSize;
}>`
  .ant-badge-count,
  .ant-scroll-number {
    background-color: ${({ theme, $variant }) => resolveBadgeColor($variant, theme)};
    height: ${({ $size }) => resolveBadgeSize($size)}px;
    min-width: ${({ $size }) => resolveBadgeSize($size)}px;
    line-height: ${({ $size }) => resolveBadgeSize($size)}px;
    font-size: ${({ theme, $size }) => resolveBadgeFontSize(theme, $size)}px;
    padding: 0 ${({ theme }) => theme.spacing.XS}px;
    border-radius: ${({ $size }) => resolveBadgeSize($size) / 2}px;
    box-shadow: none;
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }

  .ant-badge-dot {
    background-color: ${({ theme, $variant }) => resolveBadgeColor($variant, theme)};
    width: ${({ theme }) => theme.spacing.SM}px;
    height: ${({ theme }) => theme.spacing.SM}px;
    box-shadow: none;
  }
`;
