import { Progress as AntProgress } from 'antd';
import styled from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type { ProgressSize, ProgressStatus, ProgressVariant } from './RediaccProgress.types';

const PROGRESS_HEIGHT_MAP: Record<ProgressSize, number> = {
  sm: 6,
  md: 8,
  lg: 12,
};

export const resolveProgressHeight = (size: ProgressSize = 'md'): number => {
  return PROGRESS_HEIGHT_MAP[size] || PROGRESS_HEIGHT_MAP.md;
};

const CIRCLE_WIDTH_MAP: Record<ProgressSize, number> = {
  sm: 60,
  md: 80,
  lg: 120,
};

export const resolveCircleWidth = (size: ProgressSize = 'md'): number => {
  return CIRCLE_WIDTH_MAP[size] || CIRCLE_WIDTH_MAP.md;
};

const PROGRESS_COLOR_MAP: Record<ProgressStatus, keyof StyledTheme['colors']> = {
  success: 'success',
  exception: 'error',
  active: 'primary',
  normal: 'primary',
};

export const resolveProgressColor = (
  status: ProgressStatus = 'normal',
  theme: StyledTheme
): string => {
  return theme.colors[PROGRESS_COLOR_MAP[status] || PROGRESS_COLOR_MAP.normal];
};

export const StyledRediaccProgress = styled(AntProgress)<{
  $variant: ProgressVariant;
  $size: ProgressSize;
  $status: ProgressStatus;
}>`
  && {
    /* Line variant */
    ${({ $variant }) =>
      $variant === 'line' &&
      `
      .ant-progress-outer {
        padding-right: 0;
      }
    `}

    /* Size adjustments for line variant */
    ${({ $variant, $size }) =>
      $variant === 'line' &&
      `
      .ant-progress-inner {
        height: ${resolveProgressHeight($size)}px;
      }
    `}

    /* Circle variant sizing */
    ${({ $variant, $size }) =>
      $variant === 'circle' &&
      `
      width: ${resolveCircleWidth($size)}px;
      height: ${resolveCircleWidth($size)}px;
    `}

    /* Status colors */
    .ant-progress-bg {
    }

    /* Trail color */
    .ant-progress-inner {
    }

    /* Text styling */
    .ant-progress-text {
      font-size: ${({ theme }) => theme.fontSize.SM}px;
    }
  }
`;
