import { Badge as AntBadge } from 'antd';
import styled from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type { BadgeSize, BadgeVariant } from './RediaccBadge.types';

// Get badge color based on variant
export const resolveBadgeColor = (
  variant: BadgeVariant = 'default',
  theme: StyledTheme
): string => {
  switch (variant) {
    case 'primary':
      return theme.colors.primary;
    case 'success':
      return theme.colors.success;
    case 'warning':
      return theme.colors.warning;
    case 'error':
      return theme.colors.error;
    case 'info':
      return theme.colors.info;
    case 'muted':
      return theme.colors.textTertiary;
    case 'default':
    default:
      return theme.colors.primary;
  }
};

// Get badge size in pixels
export const resolveBadgeSize = (size: BadgeSize = 'md'): number => {
  switch (size) {
    case 'sm':
      return 16;
    case 'md':
    default:
      return 20;
  }
};

// Get badge font size
export const resolveBadgeFontSize = (theme: StyledTheme, size: BadgeSize = 'md'): number => {
  switch (size) {
    case 'sm':
      return theme.fontSize.XS - 2; // 10px
    case 'md':
    default:
      return theme.fontSize.XS; // 12px
  }
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
    width: 8px;
    height: 8px;
    box-shadow: none;
  }
`;
