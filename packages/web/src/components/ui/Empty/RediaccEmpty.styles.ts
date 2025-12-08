import { Empty as AntEmpty } from 'antd';
import styled from 'styled-components';
import type { StyledTheme } from '@/styles/styledTheme';
import type { EmptySize, EmptyVariant } from './RediaccEmpty.types';

export const resolveEmptyPadding = (theme: StyledTheme, size: EmptySize = 'md'): number => {
  switch (size) {
    case 'sm':
      return theme.spacing.LG; // 24px
    case 'lg':
      return theme.spacing.XXXL; // 48px
    case 'md':
    default:
      return theme.spacing.XXL; // 40px
  }
};

export const resolveEmptyImageSize = (size: EmptySize = 'md'): number => {
  switch (size) {
    case 'sm':
      return 40;
    case 'lg':
      return 80;
    case 'md':
    default:
      return 60;
  }
};

export const StyledRediaccEmpty = styled(AntEmpty).withConfig({
  shouldForwardProp: (prop) => !['$variant', '$size'].includes(prop),
})<{
  $variant: EmptyVariant;
  $size: EmptySize;
}>`
  && {
    padding: ${({ theme, $size }) => resolveEmptyPadding(theme, $size)}px 0;

    /* Minimal variant - no image */
    ${({ $variant }) =>
      $variant === 'minimal' &&
      `
      .ant-empty-image {
        display: none;
      }
    `}

    /* Image sizing */
    .ant-empty-image {
      height: ${({ $size }) => resolveEmptyImageSize($size)}px;

      svg {
        height: 100%;
        width: auto;
      }
    }

    /* Description styling */
    .ant-empty-description {
      color: ${({ theme }) => theme.colors.textSecondary};
      font-size: ${({ theme }) => theme.fontSize.SM}px;
    }

    /* Custom title styling (if used) */
    .ant-empty-footer {
      margin-top: ${({ theme }) => theme.spacing.MD}px;
    }
  }
`;

export const EmptyTitle = styled.div`
  color: ${({ theme }) => theme.colors.textPrimary};
  font-size: ${({ theme }) => theme.fontSize.BASE}px;
  font-weight: ${({ theme }) => theme.fontWeight.MEDIUM};
  margin-bottom: ${({ theme }) => theme.spacing.XS}px;
`;

export const EmptyAction = styled.div`
  margin-top: ${({ theme }) => theme.spacing.MD}px;
`;
