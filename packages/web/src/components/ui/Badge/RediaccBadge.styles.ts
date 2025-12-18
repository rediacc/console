import { Badge as AntBadge } from 'antd';
import styled from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import { resolveBadgeColor } from '@/styles/variantMaps';
import type { BadgeSize, BadgeVariant } from './RediaccBadge.types';

const BADGE_SIZE_MAP: Record<BadgeSize, number> = {
  sm: 16,
  md: 20,
};

// Get badge size in pixels
export const resolveBadgeSize = (size?: BadgeSize): number => {
  return BADGE_SIZE_MAP[size || 'md'] || BADGE_SIZE_MAP.md;
};

const BADGE_FONT_SIZE_MAP: Record<BadgeSize, (theme: StyledTheme) => number> = {
  sm: (theme) => theme.fontSize.XS - 2,
  md: (theme) => theme.fontSize.XS,
};

// Get badge font size
export const resolveBadgeFontSize = (theme: StyledTheme, size?: BadgeSize): number => {
  return (BADGE_FONT_SIZE_MAP[size || 'md'] || BADGE_FONT_SIZE_MAP.md)(theme);
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
    font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  }

  .ant-badge-dot {
    background-color: ${({ theme, $variant }) => resolveBadgeColor($variant, theme)};
    width: ${({ theme }) => theme.spacing.SM}px;
    height: ${({ theme }) => theme.spacing.SM}px;
  }
`;
