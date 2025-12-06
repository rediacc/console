import styled from 'styled-components';
import { Progress as AntProgress } from 'antd';
import type { StyledTheme } from '@/styles/styledTheme';
import type { ProgressVariant, ProgressSize, ProgressStatus } from './RediaccProgress.types';

export const resolveProgressHeight = (size: ProgressSize = 'md'): number => {
  switch (size) {
    case 'sm': return 6;
    case 'lg': return 12;
    case 'md':
    default: return 8;
  }
};

export const resolveCircleWidth = (size: ProgressSize = 'md'): number => {
  switch (size) {
    case 'sm': return 60;
    case 'lg': return 120;
    case 'md':
    default: return 80;
  }
};

export const resolveProgressColor = (status: ProgressStatus = 'normal', theme: StyledTheme): string => {
  switch (status) {
    case 'success': return theme.colors.success;
    case 'exception': return theme.colors.error;
    case 'active':
    case 'normal':
    default: return theme.colors.primary;
  }
};

export const StyledRediaccProgress = styled(AntProgress)<{
  $variant: ProgressVariant;
  $size: ProgressSize;
  $status: ProgressStatus;
}>`
  && {
    /* Line variant */
    ${({ $variant }) => $variant === 'line' && `
      .ant-progress-outer {
        margin-right: 0;
        padding-right: 0;
      }

      .ant-progress-inner {
        border-radius: 100px;
      }

      .ant-progress-bg {
        border-radius: 100px;
      }
    `}

    /* Size adjustments for line variant */
    ${({ $variant, $size }) => $variant === 'line' && `
      .ant-progress-inner {
        height: ${resolveProgressHeight($size)}px;
      }
    `}

    /* Circle variant sizing */
    ${({ $variant, $size }) => $variant === 'circle' && `
      width: ${resolveCircleWidth($size)}px;
      height: ${resolveCircleWidth($size)}px;
    `}

    /* Status colors */
    .ant-progress-bg {
      background-color: ${({ theme, $status }) => resolveProgressColor($status, theme)};
    }

    /* Trail color */
    .ant-progress-inner {
      background-color: ${({ theme }) => theme.colors.bgSecondary};
    }

    /* Text styling */
    .ant-progress-text {
      color: ${({ theme }) => theme.colors.textSecondary};
      font-size: ${({ theme }) => theme.fontSize.SM}px;
    }
  }
`;
