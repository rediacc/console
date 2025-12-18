import { Tag as AntTag } from 'antd';
import styled from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type { TagSize, TagVariant } from './RediaccTag.types';

const TAG_FONT_SIZE_MAP: Record<TagSize, keyof StyledTheme['fontSize']> = {
  sm: 'XS',
  md: 'SM',
  lg: 'MD',
};

/**
 * Resolves font size for each tag size
 */
export const resolveRediaccTagFontSize = (size: TagSize = 'md', theme: StyledTheme): number => {
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
export const resolveRediaccTagPadding = (size: TagSize = 'md', theme: StyledTheme): string => {
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
export const resolveRediaccTagRadius = (size: TagSize = 'md', theme: StyledTheme): number => {
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
    padding: ${({ theme, $size, $compact }) =>
      $compact ? `0 ${theme.spacing.XS}px` : resolveRediaccTagPadding($size, theme)};
    font-size: ${({ theme, $size, $compact }) =>
      $compact ? theme.fontSize.XS : resolveRediaccTagFontSize($size, theme)}px;
    font-weight: ${({ theme, $emphasized }) =>
      $emphasized ? theme.fontWeight.SEMIBOLD : theme.fontWeight.MEDIUM};
    line-height: ${({ theme }) => theme.lineHeight.TIGHT};

    /* Ensure icon inherits color */
    .anticon {
    }

    /* Close icon styling */
    .ant-tag-close-icon {
      font-size: ${({ theme }) => theme.fontSize.XS}px;
    }
  }
`;
