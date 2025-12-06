import styled, { css } from 'styled-components';
import { List as AntList } from 'antd';
import type { StyledTheme } from '@/styles/styledTheme';
import type { ListVariant, ListSize } from './RediaccList.types';

export const resolveListPadding = (theme: StyledTheme, size: ListSize = 'md'): number => {
  switch (size) {
    case 'sm': return theme.spacing.SM;
    case 'md':
    default: return theme.spacing.MD;
  }
};

export const StyledRediaccList = styled(AntList)<{
  $variant: ListVariant;
  $size: ListSize;
  $split?: boolean;
}>`
  && {
    background-color: ${({ theme }) => theme.colors.bgPrimary};

    /* Bordered variant */
    ${({ $variant, theme }) => $variant === 'bordered' && css`
      border: 1px solid ${theme.colors.borderSecondary};
      border-radius: ${theme.borderRadius.LG}px;
    `}

    /* Card variant */
    ${({ $variant, theme }) => $variant === 'card' && css`
      border: 1px solid ${theme.colors.borderSecondary};
      border-radius: ${theme.borderRadius.LG}px;
      box-shadow: ${theme.shadows.SM};
    `}

    /* List items */
    .ant-list-item {
      padding: ${({ theme, $size }) => resolveListPadding(theme, $size)}px;
      border-color: ${({ theme }) => theme.colors.borderSecondary};

      ${({ $split }) => !$split && css`
        border-bottom: none;
      `}
    }

    /* Header */
    .ant-list-header {
      padding: ${({ theme, $size }) => resolveListPadding(theme, $size)}px;
      border-color: ${({ theme }) => theme.colors.borderSecondary};
      font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
      color: ${({ theme }) => theme.colors.textPrimary};
    }

    /* Footer */
    .ant-list-footer {
      padding: ${({ theme, $size }) => resolveListPadding(theme, $size)}px;
      border-color: ${({ theme }) => theme.colors.borderSecondary};
      color: ${({ theme }) => theme.colors.textSecondary};
    }

    /* Empty state */
    .ant-list-empty-text {
      color: ${({ theme }) => theme.colors.textSecondary};
      padding: ${({ theme }) => theme.spacing.LG}px;
    }
  }
` as typeof AntList;
