import { List as AntList } from 'antd';
import styled, { css } from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type { ListSize, ListVariant } from './RediaccList.types';

const LIST_PADDING_MAP: Record<ListSize, keyof StyledTheme['spacing']> = {
  sm: 'SM',
  md: 'MD',
};

export const resolveListPadding = (theme: StyledTheme, size: ListSize = 'md'): number => {
  const paddingKey = LIST_PADDING_MAP[size] ?? 'MD';
  return theme.spacing[paddingKey];
};

export const StyledRediaccList = styled(AntList).withConfig({
  shouldForwardProp: (prop) => !['$variant', '$size', '$split'].includes(prop),
})<{
  $variant: ListVariant;
  $size: ListSize;
  $split?: boolean;
}>`
  && {
    /* Bordered variant */
    ${({ $variant }) =>
      $variant === 'bordered' &&
      css`
    `}

    /* Card variant */
    ${({ $variant }) =>
      $variant === 'card' &&
      css`
    `}

    /* List items */
    .ant-list-item {
      padding: ${({ theme, $size }) => resolveListPadding(theme, $size)}px;

      ${({ $split }) =>
        !$split &&
        css`
      `}
    }

    /* Header */
    .ant-list-header {
      padding: ${({ theme, $size }) => resolveListPadding(theme, $size)}px;
      font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
    }

    /* Footer */
    .ant-list-footer {
      padding: ${({ theme, $size }) => resolveListPadding(theme, $size)}px;
    }

    /* Empty state */
    .ant-list-empty-text {
      padding: ${({ theme }) => theme.spacing.LG}px;
    }
  }
`;
